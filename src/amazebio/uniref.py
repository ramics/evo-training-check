"""Streaming acquisition of a pinned UniRef release.

Why this exists in this shape
-----------------------------

`DESIGN.md` §A1 wants ESM-2's corpus staged at the version the model states, and
DECISIONS.md D-024 pins that to UniRef 2021_04. The UniProt previous-releases
archive serves 2021_04 only as one 169,188,630,923-byte `uniref2021_04.tar.gz`
with no per-tier files, so staging it is a bulk transfer whether or not the
analysis needs every tier.

Two facts about that archive decide the design:

* It is a **gzip** stream, which is not randomly seekable. The tiers sit inside
  it as sequential tar members, so reaching UniRef50 means decompressing
  everything in front of it. There is no shortcut that fetches one tier.
* The HTTP endpoint advertises `Accept-Ranges: bytes`, so the *compressed* byte
  stream is resumable. A dropped connection costs the bytes in flight, not the
  pass.

Taken together: one sequential pass, nothing buffered to local disk, resumed by
byte offset when the network drops. :class:`ResumableRead` is the resume,
:func:`iter_tar_members` is the sequential scan, and :class:`S3PartSink` lands
the selected members in object storage as they go past. A run that only wants to
know what is inside the archive passes no sink and reads the scan.

The md5 of the whole compressed stream is computed in the same pass and checked
against the release's published value, because a reconstruction that cannot show
it read the released bytes is a proxy, and `AGENTS.md` requires the
stated-versus-used gap to be recorded rather than assumed away.
"""

from __future__ import annotations

import concurrent.futures as futures
import contextlib
import hashlib
import threading
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import IO, Any, Protocol

BLOCK = 512
_READ_CHUNK = 1 << 22  # 4 MiB off the socket at a time.


@dataclass(frozen=True)
class Release:
    """A pinned UniRef release: where it is, how big, and what it says it contains.

    Releases are declared here, as a closed set, rather than passed in by a caller.
    The original reason (DECISIONS.md D-024) was that a caller must not be able to
    point this module's verification at a release nobody pinned, and that still holds:
    a `Release` carries the publisher's own md5 and the publisher's own cluster counts,
    so staging one is checkable, and inventing one at a call site would not be.

    A1.5 made a second release necessary — ESM-2 states 2021_04 and ESM3 states
    2023_02 — which is why these four values moved out of module constants
    (DECISIONS.md D-032). The module constants remain as aliases for 2021_04, because
    A1.3's staged corpus and its manifests cite them.
    """

    release: str
    archive_bytes: int
    archive_md5: str
    stated_clusters: dict[str, int]

    @property
    def archive_url(self) -> str:
        return (
            "https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/"
            f"release-{self.release}/uniref/uniref{self.release}.tar.gz"
        )

    @property
    def archive_name(self) -> str:
        return f"uniref{self.release}.tar.gz"


# ESM-2's release. Cluster counts from the per-tier release notes of the same release,
# which are the authority on composition; the staged corpus is checked against these
# rather than against them being plausible. See `composition_check`. Only the two tiers
# A1.3 staged are listed, because a stated count for a tier nobody counted would read
# as a check that passed.
UNIREF_2021_04 = Release(
    release="2021_04",
    archive_bytes=169_188_630_923,
    archive_md5="444f0a7062a65a988ba1d5949d1d6419",
    stated_clusters={"uniref50": 49_874_565, "uniref90": 138_515_945},
)

# ESM3-open's release. All three tiers are listed here, unlike 2021_04, because ESM3
# does not state which tier it parsed and a proxy therefore cannot stage just one:
# see `amazebio.esm3` and policies/esm3-open.md section 6. Counts from the release
# notes captured under policies/captures/, each verified against the md5 the release's
# own metalink publishes for it.
UNIREF_2023_02 = Release(
    release="2023_02",
    archive_bytes=211_819_312_677,
    archive_md5="353681f464572bb199fa032f714d4669",
    stated_clusters={
        "uniref50": 60_479_070,
        "uniref90": 170_669_877,
        "uniref100": 350_950_053,
    },
)

RELEASES: dict[str, Release] = {r.release: r for r in (UNIREF_2021_04, UNIREF_2023_02)}

# Aliases for the release this module was written to stage. A1.3's manifests and tests
# cite these names; new code should take a `Release`.
RELEASE = UNIREF_2021_04.release
ARCHIVE_URL = UNIREF_2021_04.archive_url
ARCHIVE_BYTES = UNIREF_2021_04.archive_bytes
ARCHIVE_MD5 = UNIREF_2021_04.archive_md5
STATED_CLUSTERS = UNIREF_2021_04.stated_clusters


class VerificationError(RuntimeError):
    """Raised when staged bytes do not match the release's published verification."""


class TarFormatError(RuntimeError):
    """Raised when the archive does not parse as a tar stream."""


# --------------------------------------------------------------------------- #
# Resumable byte source
# --------------------------------------------------------------------------- #


@dataclass
class ResumableRead:
    """A forward-only reader over an HTTP resource, re-opened on failure.

    The point is that `read` never raises for a dropped connection while the
    server still honours ranges: it reconnects at the current offset and carries
    on. `pos` is the number of bytes successfully delivered, which is both the
    resume point and the progress figure worth logging.

    A truncated final response is not treated as success: if the server closes
    early and `expected_bytes` is set, the reader reconnects for the remainder.
    """

    url: str
    expected_bytes: int | None = None
    max_attempts: int = 8
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen
    sleep: Callable[[float], None] = time.sleep
    on_reconnect: Callable[[int, int, BaseException], None] | None = None

    pos: int = 0
    _fh: IO[bytes] | None = field(default=None, repr=False)
    _reconnects: int = 0

    @property
    def reconnects(self) -> int:
        """How many times the stream had to be re-opened. Belongs in the manifest."""
        return self._reconnects

    def _open(self) -> IO[bytes]:
        request = urllib.request.Request(self.url)
        if self.pos:
            request.add_header("Range", f"bytes={self.pos}-")
        response = self.opener(request)
        if self.pos and getattr(response, "status", 200) != 206:
            raise VerificationError(
                f"resume at byte {self.pos} needs a ranged response; the server answered "
                f"{getattr(response, 'status', 'unknown')}. Restarting from zero would be "
                "correct but costs the whole transfer, so it is left to the caller."
            )
        return response

    def read(self, size: int) -> bytes:
        """Return up to `size` bytes, reconnecting through transient failures.

        Returns b"" only at a genuine end of stream.
        """
        attempt = 0
        while True:
            if self._fh is None:
                self._fh = self._open()
            try:
                chunk = self._fh.read(size)
            except (OSError, urllib.error.URLError) as exc:
                attempt += 1
                if attempt >= self.max_attempts:
                    raise
                self._drop(attempt, exc)
                continue
            if chunk:
                self.pos += len(chunk)
                return chunk
            # Empty read: either the end, or a close before the end.
            if self.expected_bytes is not None and self.pos < self.expected_bytes:
                attempt += 1
                if attempt >= self.max_attempts:
                    raise VerificationError(
                        f"stream ended at byte {self.pos} of {self.expected_bytes} and "
                        f"would not resume after {attempt} attempts"
                    )
                self._drop(attempt, EOFError("server closed before the end of the resource"))
                continue
            return b""

    def _drop(self, attempt: int, exc: BaseException) -> None:
        if self._fh is not None:
            # Closing an already-broken socket can raise, and that failure is of no
            # interest: the reconnect below is the recovery.
            with contextlib.suppress(Exception):
                self._fh.close()
            self._fh = None
        self._reconnects += 1
        if self.on_reconnect is not None:
            self.on_reconnect(attempt, self.pos, exc)
        self.sleep(min(2.0 * attempt, 30.0))

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class GunzipStream:
    """Incremental gunzip over a reader, exposing `read(n)` with no seeking.

    Also carries the md5 of the *compressed* bytes, because that is what the
    release publishes a checksum for. The digest is only meaningful once the
    stream is exhausted, so :meth:`compressed_md5` refuses to answer early
    rather than returning a hash of a prefix that looks like a verification.
    """

    def __init__(
        self,
        source: Any,
        *,
        digest: str = "md5",
        tap: Callable[[bytes], None] | None = None,
    ) -> None:
        """
        Args:
            tap: receives every compressed chunk as it arrives, before
                decompression. This is how the release archive is retained
                verbatim in the same pass that extracts from it: the raw bytes
                are the only form whose md5 matches the published one, and
                pulling 169 GB twice to get both would be the alternative.
        """
        self._source = source
        self._decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self._digest = hashlib.new(digest)
        self._tap = tap
        self._buffer = bytearray()
        self._source_exhausted = False
        self.compressed_bytes = 0
        self.read_bytes = 0

    def _pull(self) -> bool:
        """Pull one chunk from the source into the output buffer. False at the end."""
        while True:
            raw = self._source.read(_READ_CHUNK)
            if not raw:
                self._buffer += self._decompressor.flush()
                self._source_exhausted = True
                return False
            self._digest.update(raw)
            self.compressed_bytes += len(raw)
            if self._tap is not None:
                self._tap(raw)
            out = self._decompressor.decompress(raw)
            if self._decompressor.eof and self._decompressor.unused_data:
                # Concatenated gzip members: start the next one where this ended.
                leftover = self._decompressor.unused_data
                self._decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                out += self._decompressor.decompress(leftover)
            if out:
                self._buffer += out
                return True

    def read(self, size: int) -> bytes:
        while len(self._buffer) < size and not self._source_exhausted:
            self._pull()
        take = bytes(self._buffer[:size])
        del self._buffer[: len(take)]
        self.read_bytes += len(take)
        return take

    def unread(self, data: bytes) -> None:
        """Push bytes back to the front of the stream, undoing a read.

        This is what lets a caller inspect the head of the stream without
        consuming it. Without pushback, reading the XML root element would eat
        the first chunk of markup and every cluster tag in it would go uncounted
        — a silent undercount at the start of each tier.
        """
        if not data:
            return
        self._buffer[:0] = data
        self.read_bytes -= len(data)

    def drain(self) -> int:
        """Read the stream to its end, discarding the rest. Returns bytes discarded.

        A tar archive ends at two zero blocks but the file usually continues with
        padding to the archive's record size, so a walk that stops at the marker
        leaves compressed bytes unread — and an md5 over only the bytes read is
        not the published md5 of the release. Draining is what makes the
        verification cover the whole artefact.
        """
        discarded = 0
        while chunk := self.read(_READ_CHUNK):
            discarded += len(chunk)
        return discarded

    def read_exact(self, size: int) -> bytes:
        got = self.read(size)
        if len(got) != size:
            raise TarFormatError(f"archive ended mid-record: wanted {size} bytes, got {len(got)}")
        return got

    @property
    def exhausted(self) -> bool:
        return self._source_exhausted and not self._buffer

    def compressed_md5(self) -> str:
        if not self._source_exhausted:
            raise VerificationError(
                "the compressed md5 is only a verification once the whole stream has "
                "been read; asking early would hash a prefix"
            )
        return self._digest.hexdigest()


# --------------------------------------------------------------------------- #
# Sequential tar scan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Member:
    """One tar member's header. `path` includes any enclosing archive names."""

    name: str
    size: int
    typeflag: str
    path: tuple[str, ...] = ()

    @property
    def is_file(self) -> bool:
        return self.typeflag in ("0", "\0", "")

    @property
    def qualified(self) -> str:
        return "/".join((*self.path, self.name))


def _numeric(raw: bytes) -> int:
    """Read a tar header numeric field, octal or GNU base-256.

    This release needs the second form. A tar size field is 12 bytes of octal
    digits, which tops out just under 8 GiB, and the archive's UniRef100 member
    is 93.8 GB. GNU's extension for that case sets the high bit of the first byte
    and stores the value as a big-endian two's-complement integer in the rest of
    the field. A reader that only knows octal does not misread such a member —
    it fails outright on the first header, which is how this was found.
    """
    if raw and raw[0] in (0o200, 0o377):
        value = int.from_bytes(raw[1:], "big")
        if raw[0] == 0o377:  # Negative, which no field this code reads should be.
            value -= 1 << (8 * (len(raw) - 1))
        return value
    text = raw.split(b"\0")[0].strip()
    if not text:
        return 0
    try:
        return int(text, 8)
    except ValueError as exc:
        raise TarFormatError(f"bad numeric field {raw!r}") from exc


def _checksum_ok(header: bytes) -> bool:
    """Whether the header's stored checksum matches its bytes.

    Deliberately returns False rather than propagating a parse error on a
    malformed field: a block that is not a header at all fails here, and the
    caller's "stream is misaligned" message is the useful diagnosis. A
    `TarFormatError` about an unparseable octal field would describe the symptom.
    """
    try:
        stated = _numeric(header[148:156])
    except TarFormatError:
        return False
    blanked = header[:148] + b" " * 8 + header[156:]
    return stated in (sum(blanked), sum(bytearray(c & 0x7F for c in blanked)))


def iter_tar_members(
    stream: GunzipStream,
    *,
    want: Callable[[Member], bool] | None = None,
    recurse_into: Callable[[Member], bool] | None = None,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[Member, Iterator[bytes]]]:
    """Walk a tar stream in order, yielding each member and a payload iterator.

    The payload iterator is live: it must be consumed (or abandoned, which
    discards it) before the next member is read, because the underlying stream
    only moves forward. Abandoning is the normal case — this archive's UniRef100
    member is ~94 GB that Phase A has no use for, and skipping it costs only the
    time to pull it past.

    `want` selects which members yield payload worth reading; everything else is
    still reported, with its bytes discarded. `recurse_into` selects members that
    are themselves tar archives — this release nests one tar per tier inside the
    outer archive, so without recursion the scan sees three opaque blobs.
    """
    want = want or (lambda _m: False)
    recurse_into = recurse_into or (lambda _m: False)
    pending_longname: str | None = None
    zero_blocks = 0

    while True:
        header = stream.read(BLOCK)
        if len(header) < BLOCK:
            return
        if not header.strip(b"\0"):
            zero_blocks += 1
            if zero_blocks >= 2:
                return
            continue
        zero_blocks = 0
        if not _checksum_ok(header):
            raise TarFormatError(
                "tar header checksum mismatch — the stream is not aligned on a record "
                "boundary, which usually means a member's payload was partly consumed"
            )

        raw_name = header[0:100].split(b"\0")[0].decode("utf-8", "surrogateescape")
        prefix = header[345:500].split(b"\0")[0].decode("utf-8", "surrogateescape")
        size = _numeric(header[124:136])
        typeflag = chr(header[156]) if header[156] else "0"
        name = pending_longname or (f"{prefix}/{raw_name}" if prefix else raw_name)
        pending_longname = None
        padded = (size + BLOCK - 1) // BLOCK * BLOCK

        if typeflag == "L":  # GNU long name: the payload is the next member's name.
            pending_longname = (
                stream.read_exact(padded)[:size].split(b"\0")[0].decode("utf-8", "surrogateescape")
            )
            continue

        member = Member(name=name, size=size, typeflag=typeflag, path=path)

        if member.is_file and recurse_into(member):
            # The nested archive occupies the next `size` bytes. The inner walk
            # stops at the inner archive's end-of-archive marker, which is NOT
            # its last byte: a tar is padded out to its record size, so the walk
            # typically leaves several KiB unread. Those bytes have to be skipped
            # explicitly or the next outer header is read from inside the padding
            # and the whole remaining scan is garbage. Hence the measurement:
            # consumed is what the inner walk actually took, not what it should
            # have taken.
            before = stream.read_bytes
            yield member, iter(())
            yield from iter_tar_members(
                stream,
                want=want,
                recurse_into=recurse_into,
                path=(*path, name),
            )
            consumed = stream.read_bytes - before
            if consumed > size:
                raise TarFormatError(
                    f"nested archive {name!r} declared {size} bytes but its walk consumed "
                    f"{consumed}; the stream is no longer aligned"
                )
            _discard(stream, padded - consumed)
            continue

        if member.is_file and want(member):
            yield member, _payload(stream, size, padded)
        else:
            yield member, iter(())
            _discard(stream, padded)


def _payload(stream: GunzipStream, size: int, padded: int) -> Iterator[bytes]:
    remaining = size
    while remaining:
        chunk = stream.read(min(_READ_CHUNK, remaining))
        if not chunk:
            raise TarFormatError(f"member ended {remaining} bytes early")
        remaining -= len(chunk)
        yield chunk
    _discard(stream, padded - size)


def _discard(stream: GunzipStream, count: int) -> None:
    while count:
        chunk = stream.read(min(_READ_CHUNK, count))
        if not chunk:
            return
        count -= len(chunk)


# --------------------------------------------------------------------------- #
# Object-storage sink
# --------------------------------------------------------------------------- #


class _Client(Protocol):  # pragma: no cover - structural type for the S3 client.
    def create_multipart_upload(self, **kw: Any) -> Any: ...
    def upload_part(self, **kw: Any) -> Any: ...
    def complete_multipart_upload(self, **kw: Any) -> Any: ...
    def abort_multipart_upload(self, **kw: Any) -> Any: ...


class S3PartSink:
    """Multipart-upload sink that takes a stream of chunks of any size.

    Streaming into object storage has one awkward constraint: every part except
    the last must be at least 5 MiB, while the chunks arriving from a gunzipped
    tar member are whatever the decompressor produced. So chunks are coalesced
    into a part buffer and flushed at `part_bytes`.

    Parts upload concurrently, because sequentially they do not. Measured against
    this bucket: one connection sustains ~52 MB/s and eight sustain ~123 MB/s,
    while the release downloads at ~87 MB/s. With a single connection the upload
    is the bottleneck and the whole pass runs at upload speed — 2.1 hours for this
    archive rather than about 40 minutes — and a pass that long is one a container
    reclaim can destroy outright, since an abandoned multipart upload leaves
    nothing reusable behind.

    In-flight parts are capped rather than merely queued: an unbounded queue would
    let a fast reader buffer the whole archive in memory while the uploads trail.

    Used as a context manager: an exception aborts the upload instead of leaving
    a half-finished one accruing storage. The bucket this project writes to
    withholds `s3:DeleteObject`, so an upload that completes is permanent —
    aborting on the way out is the only cleanup available, and it has to work.
    """

    MIN_PART = 5 << 20

    def __init__(
        self,
        client: _Client,
        bucket: str,
        key: str,
        *,
        part_bytes: int = 64 << 20,
        concurrency: int = 8,
    ) -> None:
        if part_bytes < self.MIN_PART:
            raise ValueError(f"part_bytes must be at least {self.MIN_PART} bytes")
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._client = client
        self.bucket = bucket
        self.key = key
        self._part_bytes = part_bytes
        self._concurrency = concurrency
        self._buffer = bytearray()
        self._parts: dict[int, str] = {}
        self._lock = threading.Lock()
        self._pool: futures.ThreadPoolExecutor | None = None
        self._inflight: list[futures.Future[None]] = []
        # Two spare slots keep the uploaders fed across a part boundary without
        # letting the backlog grow with the archive.
        self._slots = threading.BoundedSemaphore(concurrency + 2)
        self._next_part = 1
        self._upload_id: str | None = None
        self._digest = hashlib.sha256()
        self.bytes_written = 0
        self.completed = False

    def open(self) -> S3PartSink:
        """Begin the upload. Separate from `__enter__` so a sink whose lifetime
        does not match a `with` block — the archive retained across the whole
        pass, rather than one member of it — can still be driven explicitly."""
        self._upload_id = self._client.create_multipart_upload(Bucket=self.bucket, Key=self.key)[
            "UploadId"
        ]
        self._pool = futures.ThreadPoolExecutor(
            max_workers=self._concurrency, thread_name_prefix="s3part"
        )
        return self

    def __enter__(self) -> S3PartSink:
        return self.open()

    def write(self, chunk: bytes) -> None:
        self._digest.update(chunk)
        self.bytes_written += len(chunk)
        self._buffer += chunk
        while len(self._buffer) >= self._part_bytes:
            self._flush(self._part_bytes)

    def _flush(self, count: int) -> None:
        """Hand one part to the pool. Blocks when the in-flight cap is reached."""
        body = bytes(self._buffer[:count])
        del self._buffer[:count]
        number = self._next_part
        self._next_part += 1
        self._reap()
        self._slots.acquire()
        assert self._pool is not None
        self._inflight.append(self._pool.submit(self._send, number, body))

    def _send(self, number: int, body: bytes) -> None:
        try:
            etag = self._client.upload_part(
                Bucket=self.bucket,
                Key=self.key,
                UploadId=self._upload_id,
                PartNumber=number,
                Body=body,
            )["ETag"]
            with self._lock:
                self._parts[number] = etag
        finally:
            self._slots.release()

    def _reap(self) -> None:
        """Surface a failed part at the next write rather than at completion.

        Without this a credentials or network failure on part 3 stays invisible
        until the end of a multi-hour pass, by which point the whole transfer has
        been paid for.
        """
        still_running = []
        for future in self._inflight:
            if future.done():
                future.result()
            else:
                still_running.append(future)
        self._inflight = still_running

    def complete(self) -> None:
        """Finish the upload, making the object permanent."""
        if self._buffer or not self._parts:
            self._flush(len(self._buffer))
        self._drain_pool()
        self._client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self._upload_id,
            # S3 requires the parts in ascending order, and concurrent uploads
            # finish out of order.
            MultipartUpload={
                "Parts": [{"ETag": self._parts[n], "PartNumber": n} for n in sorted(self._parts)]
            },
        )
        self.completed = True

    def _drain_pool(self) -> None:
        if self._pool is None:
            return
        pending, self._inflight = self._inflight, []
        try:
            for future in futures.as_completed(pending):
                future.result()
        finally:
            self._pool.shutdown(wait=True)
            self._pool = None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            self.abort()
            return
        self.complete()

    def abort(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
        if self._upload_id is None:
            return
        # Called while an exception is already propagating, so a failure to abort
        # must not replace it — the original error is the one worth reporting. The
        # cost of a silent failure here is an incomplete upload, which S3 charges
        # for until a lifecycle rule or a later abort clears it.
        with contextlib.suppress(Exception):
            self._client.abort_multipart_upload(
                Bucket=self.bucket, Key=self.key, UploadId=self._upload_id
            )

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()

    def describe(self) -> dict[str, Any]:
        return {
            "uri": f"s3://{self.bucket}/{self.key}",
            "bytes": self.bytes_written,
            "sha256": self.sha256,
            "parts": len(self._parts),
            "part_bytes": self._part_bytes,
        }


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def composition_check(
    counted: dict[str, int], release: Release = UNIREF_2021_04
) -> list[dict[str, Any]]:
    """Compare counted cluster totals against the release notes' stated totals.

    Returned as rows rather than a pass/fail, because a mismatch is a finding to
    report, not an error to raise: `AGENTS.md` is explicit that the gap between
    stated and used is itself a result.

    `release` defaults to ESM-2's, which is the only one A1.3 counted. Pass the
    release actually staged — a 2023_02 count checked against 2021_04's stated totals
    would disagree for reasons that have nothing to do with the staging.
    """
    rows = []
    for tier, stated in sorted(release.stated_clusters.items()):
        got = counted.get(tier)
        rows.append(
            {
                "tier": tier,
                "stated_clusters": stated,
                "counted_clusters": got,
                "agrees": None if got is None else got == stated,
                "delta": None if got is None else got - stated,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Counting what was staged
# --------------------------------------------------------------------------- #

# One UniRef cluster is one <entry>; its representative and any further members
# are <representativeMember> and <member>. Counting is done by scanning for these
# literal byte sequences rather than by parsing the XML, for two reasons. It is
# roughly two orders of magnitude faster, which matters across 50 GB of markup.
# And it is safe precisely because this is XML: a literal "<" cannot appear in
# text or in an attribute value, it must be escaped as &lt;, so an occurrence of
# b"<entry " is necessarily a start tag and never content that happens to look
# like one.
MARKERS = {
    "clusters": b"<entry id=",
    "representatives": b"<representativeMember>",
    "members": b"<member>",
}


def count_markers(
    stream: Any,
    markers: dict[str, bytes] | None = None,
    *,
    chunk: int = 1 << 22,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    """Count occurrences of each marker in a forward-only byte stream.

    Chunk boundaries cut both ways, and both failures are silent:

    * A marker split across two reads is missed by naive per-chunk counting, and
      the shortfall grows with the number of chunks.
    * Retaining an overlap to fix that, and then counting the whole retained
      window, counts anything inside the overlap *twice* — which is worse, since
      it inflates rather than deflates.

    So the overlap is carried forward, but a match starting inside the region
    that will be carried forward is deferred rather than counted: it is counted
    when it reappears at the head of the next window. Every occurrence is
    therefore counted exactly once, whatever the chunk size — which
    `test_counting_is_independent_of_chunk_size` checks directly, because a count
    that depends on buffer size is not a measurement.
    """
    markers = markers or MARKERS
    counts = dict.fromkeys(markers, 0)
    # The longest marker minus one byte: enough that any marker spanning a
    # boundary is wholly contained in the next window.
    overlap = max(len(m) for m in markers.values()) - 1
    tail = b""
    total = 0
    while True:
        data = stream.read(chunk)
        if not data:
            break
        total += len(data)
        window = tail + data
        # Start positions at or past `limit` live in the carried-forward tail.
        limit = max(len(window) - overlap, 0)
        for name, marker in markers.items():
            counts[name] += _count_starting_before(window, marker, limit)
        tail = window[limit:]
        if progress is not None:
            progress(total)
    # At the end nothing is carried forward, so the tail is counted in full.
    for name, marker in markers.items():
        counts[name] += _count_starting_before(tail, marker, len(tail))
    return counts


def _count_starting_before(buf: bytes, marker: bytes, limit: int) -> int:
    """Occurrences of `marker` in `buf` whose first byte lies before `limit`."""
    found = 0
    at = buf.find(marker)
    while at != -1 and at < limit:
        found += 1
        at = buf.find(marker, at + 1)
    return found


def read_root_attributes(stream: Any, *, limit: int = 1 << 16) -> dict[str, str]:
    """Pull the attributes of the XML root element from the head of a stream.

    UniRef's root element carries `version` and `releaseDate`, which is a
    first-party statement of which release these bytes are — independent of the
    filename and of the directory they were downloaded from. Worth capturing: it
    is the difference between trusting a path and reading the data.

    This is a peek, not a read: whatever it consumes is pushed back when the
    stream supports it, so a caller can count markers afterwards without losing
    the head of the file.
    """
    head = b""
    attrs: dict[str, str] = {}
    try:
        while len(head) < limit:
            data = stream.read(min(1 << 16, limit - len(head)))
            if not data:
                break
            head += data
            # The root element is the first tag that is not a processing
            # instruction; find its closing bracket.
            start = head.find(b"<UniRef")
            if start != -1 and b">" in head[start:]:
                tag = head[start : head.index(b">", start)]
                for key in (b"version", b"releaseDate"):
                    marker = key + b'="'
                    at = tag.find(marker)
                    if at != -1:
                        value = tag[at + len(marker) : tag.index(b'"', at + len(marker))]
                        attrs[key.decode()] = value.decode()
                attrs["element"] = tag[1:].split(b" ")[0].decode()
                break
    finally:
        unread = getattr(stream, "unread", None)
        if unread is not None:
            unread(head)
    return attrs


class S3RangeRead:
    """Forward-only reader over an S3 object, re-opened on failure.

    The same contract as :class:`ResumableRead` and for the same reason: these
    objects are tens of gigabytes, a read that long will meet a dropped
    connection, and restarting it costs the whole transfer. S3 always honours
    ranges, so resuming is a `Range` header on a fresh `get_object`.
    """

    def __init__(
        self,
        client: Any,
        bucket: str,
        key: str,
        *,
        max_attempts: int = 8,
        sleep: Callable[[float], None] = time.sleep,
        on_reconnect: Callable[[int, int, BaseException], None] | None = None,
    ) -> None:
        self._client = client
        self.bucket = bucket
        self.key = key
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._on_reconnect = on_reconnect
        self._body: Any = None
        self.pos = 0
        self.reconnects = 0
        self.size: int | None = None

    def _open(self) -> Any:
        response = self._client.get_object(
            Bucket=self.bucket,
            Key=self.key,
            **({"Range": f"bytes={self.pos}-"} if self.pos else {}),
        )
        if self.size is None:
            self.size = response["ContentLength"] + self.pos
        return response["Body"]

    def read(self, size: int) -> bytes:
        attempt = 0
        while True:
            if self._body is None:
                self._body = self._open()
            try:
                chunk = self._body.read(size)
            except Exception as exc:  # Any transport failure is a retry, not a result.
                attempt += 1
                if attempt >= self._max_attempts:
                    raise
                self._drop(attempt, exc)
                continue
            if chunk:
                self.pos += len(chunk)
                return chunk
            if self.size is not None and self.pos < self.size:
                attempt += 1
                if attempt >= self._max_attempts:
                    raise VerificationError(
                        f"s3://{self.bucket}/{self.key} ended at {self.pos} of {self.size}"
                    )
                self._drop(attempt, EOFError("object stream closed early"))
                continue
            return b""

    def _drop(self, attempt: int, exc: BaseException) -> None:
        if self._body is not None:
            with contextlib.suppress(Exception):
                self._body.close()
            self._body = None
        self.reconnects += 1
        if self._on_reconnect is not None:
            self._on_reconnect(attempt, self.pos, exc)
        self._sleep(min(2.0 * attempt, 30.0))

    def close(self) -> None:
        if self._body is not None:
            with contextlib.suppress(Exception):
                self._body.close()
            self._body = None

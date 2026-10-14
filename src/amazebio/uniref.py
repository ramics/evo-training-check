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

import contextlib
import hashlib
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import IO, Any, Protocol

BLOCK = 512
_READ_CHUNK = 1 << 22  # 4 MiB off the socket at a time.

# The release this module exists to stage. Pinned here rather than passed in, so a
# caller cannot quietly stage a different release and inherit this module's
# verification. DECISIONS.md D-024.
RELEASE = "2021_04"
ARCHIVE_URL = (
    "https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/"
    f"release-{RELEASE}/uniref/uniref{RELEASE}.tar.gz"
)
ARCHIVE_BYTES = 169_188_630_923
ARCHIVE_MD5 = "444f0a7062a65a988ba1d5949d1d6419"

# From the per-tier release notes of the same release, which are the authority on
# composition. The staged corpus is checked against these, not against them being
# plausible: see `composition_check`.
STATED_CLUSTERS = {"uniref50": 49_874_565, "uniref90": 138_515_945}


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

    def __init__(self, source: Any, *, digest: str = "md5") -> None:
        self._source = source
        self._decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self._digest = hashlib.new(digest)
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
    ) -> None:
        if part_bytes < self.MIN_PART:
            raise ValueError(f"part_bytes must be at least {self.MIN_PART} bytes")
        self._client = client
        self.bucket = bucket
        self.key = key
        self._part_bytes = part_bytes
        self._buffer = bytearray()
        self._parts: list[dict[str, Any]] = []
        self._upload_id: str | None = None
        self._digest = hashlib.sha256()
        self.bytes_written = 0
        self.completed = False

    def __enter__(self) -> S3PartSink:
        self._upload_id = self._client.create_multipart_upload(Bucket=self.bucket, Key=self.key)[
            "UploadId"
        ]
        return self

    def write(self, chunk: bytes) -> None:
        self._digest.update(chunk)
        self.bytes_written += len(chunk)
        self._buffer += chunk
        while len(self._buffer) >= self._part_bytes:
            self._flush(self._part_bytes)

    def _flush(self, count: int) -> None:
        body = bytes(self._buffer[:count])
        del self._buffer[:count]
        number = len(self._parts) + 1
        etag = self._client.upload_part(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self._upload_id,
            PartNumber=number,
            Body=body,
        )["ETag"]
        self._parts.append({"ETag": etag, "PartNumber": number})

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            self._abort()
            return
        if self._buffer or not self._parts:
            self._flush(len(self._buffer))
        self._client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self._upload_id,
            MultipartUpload={"Parts": self._parts},
        )
        self.completed = True

    def _abort(self) -> None:
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
        }


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def composition_check(counted: dict[str, int]) -> list[dict[str, Any]]:
    """Compare counted cluster totals against the release notes' stated totals.

    Returned as rows rather than a pass/fail, because a mismatch is a finding to
    report, not an error to raise: `AGENTS.md` is explicit that the gap between
    stated and used is itself a result.
    """
    rows = []
    for tier, stated in sorted(STATED_CLUSTERS.items()):
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

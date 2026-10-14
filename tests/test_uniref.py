"""Tests for the streaming UniRef acquisition path.

The real archive is 169 GB, so what is testable here is the machinery, against
synthetic archives built to the same shape: tiers as nested tars inside an outer
gzipped tar. The three failures worth catching before a multi-hour transfer are
losing tar alignment after skipping a member, hashing a prefix and calling it a
verification, and a dropped connection restarting instead of resuming.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import tarfile
import threading
import time

import pytest

from amazebio import uniref

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def make_tar(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def noise(n: int) -> bytes:
    """Incompressible bytes. Compressible filler makes truncation tests vacuous:
    chopping the tail of a stream of zeros loses no payload at all."""
    return os.urandom(n)


def nested_release(
    *, fifty: bytes = b">c1\nMKV\n", ninety: bytes = b">m1\nMKVA\n", hundred: bytes | None = None
) -> bytes:
    """An archive shaped like the real one: one tar per tier, UniRef100 first and big."""
    hundred = noise(40_000) if hundred is None else hundred
    outer = {
        "uniref100.tar": make_tar({"uniref100.fasta": hundred}),
        "uniref90.tar": make_tar({"uniref90.fasta": ninety}),
        "uniref50.tar": make_tar({"uniref50.fasta": fifty}),
    }
    return gzip.compress(make_tar(outer))


def walk(raw: bytes, **kw):
    stream = uniref.GunzipStream(io.BytesIO(raw))
    out = []
    for member, payload in uniref.iter_tar_members(stream, **kw):
        out.append((member, b"".join(payload)))
    return stream, out


# --------------------------------------------------------------------------- #
# Tar scanning
# --------------------------------------------------------------------------- #


def test_walks_nested_tiers_in_order():
    _, seen = walk(nested_release(), recurse_into=lambda m: m.name.endswith(".tar"))
    names = [m.qualified for m, _ in seen]
    assert names == [
        "uniref100.tar",
        "uniref100.tar/uniref100.fasta",
        "uniref90.tar",
        "uniref90.tar/uniref90.fasta",
        "uniref50.tar",
        "uniref50.tar/uniref50.fasta",
    ]


def test_payload_is_read_only_for_wanted_members():
    """The ~94 GB UniRef100 member is skipped, and skipping must not lose alignment."""
    _, seen = walk(
        nested_release(),
        want=lambda m: m.name == "uniref50.fasta",
        recurse_into=lambda m: m.name.endswith(".tar"),
    )
    got = {m.qualified: body for m, body in seen}
    assert got["uniref50.tar/uniref50.fasta"] == b">c1\nMKV\n"
    # Reported, but not delivered.
    assert got["uniref100.tar/uniref100.fasta"] == b""
    assert got["uniref90.tar/uniref90.fasta"] == b""


def test_member_sizes_survive_the_walk():
    _, seen = walk(nested_release(), recurse_into=lambda m: m.name.endswith(".tar"))
    sizes = {m.qualified: m.size for m, _ in seen}
    assert sizes["uniref100.tar/uniref100.fasta"] == 40_000
    assert sizes["uniref50.tar/uniref50.fasta"] == len(b">c1\nMKV\n")


def test_unpadded_member_keeps_the_next_header_aligned():
    """A payload that is not a multiple of 512 is the case that breaks naive readers."""
    raw = gzip.compress(make_tar({"odd.txt": b"a" * 513, "next.txt": b"b" * 3}))
    _, seen = walk(raw, want=lambda m: True)
    assert [(m.name, body) for m, body in seen] == [
        ("odd.txt", b"a" * 513),
        ("next.txt", b"bbb"),
    ]


def test_long_member_names_are_resolved():
    long_name = "uniref50/" + "d" * 150 + ".fasta"
    raw = gzip.compress(make_tar({long_name: b"payload"}))
    _, seen = walk(raw, want=lambda m: True)
    assert [m.name for m, _ in seen] == [long_name]
    assert seen[0][1] == b"payload"


def test_misalignment_is_reported_not_guessed():
    stream = uniref.GunzipStream(io.BytesIO(gzip.compress(make_tar({"a": b"x" * 1024}))))
    stream.read(600)  # Consume into the middle of the first member's payload.
    with pytest.raises(uniref.TarFormatError, match="checksum mismatch"):
        list(uniref.iter_tar_members(stream))


def test_truncated_member_is_an_error():
    raw = gzip.compress(make_tar({"a": noise(20_000)}))
    raw = raw[: len(raw) // 2]
    stream = uniref.GunzipStream(io.BytesIO(raw))
    with pytest.raises(uniref.TarFormatError):
        for _member, payload in uniref.iter_tar_members(stream, want=lambda m: True):
            b"".join(payload)


# --------------------------------------------------------------------------- #
# Compressed-stream verification
# --------------------------------------------------------------------------- #


def test_compressed_md5_matches_the_source_bytes():
    raw = nested_release()
    stream, _ = walk(raw, recurse_into=lambda m: m.name.endswith(".tar"))
    stream.drain()  # The archive's trailing padding sits past the end-of-archive marker.
    assert stream.compressed_md5() == hashlib.md5(raw).hexdigest()
    assert stream.compressed_bytes == len(raw)


def test_md5_is_refused_before_the_stream_is_exhausted():
    stream = uniref.GunzipStream(io.BytesIO(nested_release()))
    stream.read(16)
    with pytest.raises(uniref.VerificationError, match="prefix"):
        stream.compressed_md5()


def test_concatenated_gzip_members_are_read_through():
    raw = gzip.compress(make_tar({"a": b"one"})[:1024]) + gzip.compress(
        make_tar({"a": b"one"})[1024:]
    )
    _, seen = walk(raw, want=lambda m: True)
    assert [(m.name, body) for m, body in seen] == [("a", b"one")]


# --------------------------------------------------------------------------- #
# Resume
# --------------------------------------------------------------------------- #


class FlakyServer:
    """Serves `body`, failing after `fail_after` bytes of each response."""

    def __init__(self, body: bytes, fail_after: int | None = None, truncate_at: int | None = None):
        self.body = body
        self.fail_after = fail_after
        self.truncate_at = truncate_at
        self.requests: list[int] = []

    def __call__(self, request):
        header = request.get_header("Range")
        start = int(header.removeprefix("bytes=").rstrip("-")) if header else 0
        self.requests.append(start)
        return _Response(self, start)


class _Response(io.RawIOBase):
    def __init__(self, server: FlakyServer, start: int):
        self._server = server
        self._pos = start
        self._served = 0
        self.status = 206 if start else 200

    def read(self, size=-1):
        srv = self._server
        if srv.truncate_at is not None and self._pos >= srv.truncate_at:
            return b""
        if srv.fail_after is not None and self._served >= srv.fail_after:
            raise OSError("connection reset by peer")
        limit = size if size and size > 0 else len(srv.body)
        if srv.fail_after is not None:
            limit = min(limit, srv.fail_after - self._served)
        if srv.truncate_at is not None:
            limit = min(limit, srv.truncate_at - self._pos)
        chunk = srv.body[self._pos : self._pos + limit]
        self._pos += len(chunk)
        self._served += len(chunk)
        return chunk


def drain(reader: uniref.ResumableRead, size: int = 64) -> bytes:
    out = bytearray()
    while chunk := reader.read(size):
        out += chunk
    return bytes(out)


def test_resume_continues_at_the_offset_instead_of_restarting():
    body = bytes(range(256)) * 40
    server = FlakyServer(body, fail_after=300)
    reader = uniref.ResumableRead(
        url="https://example.invalid/a",
        expected_bytes=len(body),
        opener=server,
        sleep=lambda _s: None,
        max_attempts=64,
    )
    assert drain(reader) == body
    assert server.requests[0] == 0
    # Every later request picks up where the last one died, so no byte is re-fetched.
    assert server.requests[1:] == [300 * n for n in range(1, len(server.requests))]
    assert reader.reconnects == len(server.requests) - 1


def test_early_close_is_resumed_not_accepted_as_the_end():
    body = b"z" * 5000
    server = FlakyServer(body, truncate_at=2000)
    reader = uniref.ResumableRead(
        url="https://example.invalid/a",
        expected_bytes=len(body),
        opener=server,
        sleep=lambda _s: None,
        max_attempts=4,
    )
    with pytest.raises(uniref.VerificationError, match="would not resume"):
        drain(reader)
    assert reader.pos == 2000  # It noticed the shortfall rather than reporting success.


def test_a_server_that_ignores_range_is_refused():
    class NoRange(FlakyServer):
        def __call__(self, request):
            response = super().__call__(request)
            response.status = 200
            return response

    body = b"q" * 2000
    server = NoRange(body, fail_after=500)
    reader = uniref.ResumableRead(
        url="https://example.invalid/a",
        expected_bytes=len(body),
        opener=server,
        sleep=lambda _s: None,
    )
    with pytest.raises(uniref.VerificationError, match="ranged response"):
        drain(reader)


def test_resumed_stream_still_gunzips_and_verifies():
    """The payoff: a mid-transfer reset must not corrupt the corpus or the md5."""
    fifty = b">c1\n" + noise(60_000)
    raw = nested_release(fifty=fifty)
    server = FlakyServer(raw, fail_after=777)
    reader = uniref.ResumableRead(
        url="https://example.invalid/uniref.tar.gz",
        expected_bytes=len(raw),
        opener=server,
        sleep=lambda _s: None,
        max_attempts=200,
    )
    stream = uniref.GunzipStream(reader)
    bodies = {}
    for member, payload in uniref.iter_tar_members(
        stream, want=lambda m: True, recurse_into=lambda m: m.name.endswith(".tar")
    ):
        bodies[member.qualified] = b"".join(payload)
    stream.drain()
    assert reader.reconnects > 3
    assert bodies["uniref50.tar/uniref50.fasta"] == fifty
    assert stream.compressed_md5() == hashlib.md5(raw).hexdigest()


# --------------------------------------------------------------------------- #
# Object-storage sink
# --------------------------------------------------------------------------- #


class FakeS3:
    def __init__(self):
        self.parts: dict[int, bytes] = {}
        self.completed: dict | None = None
        self.aborted = False
        self.uploads = 0

    def create_multipart_upload(self, **kw):
        self.uploads += 1
        self.key = kw["Key"]
        return {"UploadId": "upload-1"}

    def upload_part(self, **kw):
        self.parts[kw["PartNumber"]] = kw["Body"]
        return {"ETag": f'"etag-{kw["PartNumber"]}"'}

    def complete_multipart_upload(self, **kw):
        self.completed = kw["MultipartUpload"]
        return {}

    def abort_multipart_upload(self, **kw):
        self.aborted = True
        return {}

    def assembled(self) -> bytes:
        return b"".join(self.parts[n] for n in sorted(self.parts))


def test_small_chunks_are_coalesced_into_legal_parts():
    client = FakeS3()
    body = b"a" * (13 << 20)
    with uniref.S3PartSink(client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART) as sink:
        for i in range(0, len(body), 7919):  # Awkward chunking, as a decompressor gives.
            sink.write(body[i : i + 7919])
    assert client.assembled() == body
    # Every part but the last clears the 5 MiB floor.
    sizes = [len(client.parts[n]) for n in sorted(client.parts)]
    assert all(s >= uniref.S3PartSink.MIN_PART for s in sizes[:-1])
    assert sink.sha256 == hashlib.sha256(body).hexdigest()
    assert client.completed is not None


def test_an_empty_member_still_completes_as_an_object():
    client = FakeS3()
    with uniref.S3PartSink(client, "bucket", "k"):
        pass
    assert client.completed is not None
    assert client.assembled() == b""


def test_failure_aborts_rather_than_leaving_a_partial_upload():
    client = FakeS3()
    with (
        pytest.raises(RuntimeError, match="network"),
        uniref.S3PartSink(client, "bucket", "k") as sink,
    ):
        sink.write(b"x" * 1024)
        raise RuntimeError("network died")
    assert client.aborted
    assert client.completed is None


def test_part_size_below_the_floor_is_rejected_up_front():
    with pytest.raises(ValueError, match="at least"):
        uniref.S3PartSink(FakeS3(), "bucket", "k", part_bytes=1024)


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def test_composition_reports_the_gap_rather_than_raising():
    rows = uniref.composition_check({"uniref50": 49_874_565, "uniref90": 1})
    by_tier = {r["tier"]: r for r in rows}
    assert by_tier["uniref50"]["agrees"] is True
    assert by_tier["uniref90"]["agrees"] is False
    assert by_tier["uniref90"]["delta"] == 1 - 138_515_945


def test_an_uncounted_tier_is_unknown_not_zero():
    rows = uniref.composition_check({})
    assert all(r["counted_clusters"] is None and r["agrees"] is None for r in rows)


def test_the_pinned_release_constants_are_the_ones_decisions_recorded():
    """A typo in these silently stages a different dataset, so pin them in a test."""
    assert uniref.RELEASE == "2021_04"
    assert uniref.ARCHIVE_BYTES == 169_188_630_923
    assert uniref.ARCHIVE_MD5 == "444f0a7062a65a988ba1d5949d1d6419"
    assert uniref.STATED_CLUSTERS["uniref50"] == 49_874_565
    assert uniref.STATED_CLUSTERS["uniref90"] == 138_515_945


# --------------------------------------------------------------------------- #
# Header numeric fields
# --------------------------------------------------------------------------- #


def test_gnu_base256_sizes_are_read():
    """The real archive needs this: its UniRef100 member overflows the octal field.

    A 12-byte octal size tops out just under 8 GiB and that member is 93.7 GB, so
    GNU's high-bit form is not an edge case here — it is the first header in the
    archive. The literal field below is the one the release actually serves.
    """
    field = b"\x80\x00\x00\x00\x00\x00\x00\x15\xd2\x178\x00"
    assert uniref._numeric(field) == 93_719_050_240


def test_octal_fields_still_read():
    assert uniref._numeric(b"00000004000\x00") == 2048
    assert uniref._numeric(b"\x00" * 12) == 0


def test_a_field_that_is_neither_is_refused():
    with pytest.raises(uniref.TarFormatError, match="bad numeric field"):
        uniref._numeric(b"not-a-number")


def test_a_large_member_is_walked_without_reading_it():
    """A 93 GB member cannot be materialised in a test, so assert on the header.

    This builds a header claiming a base-256 size and checks the walk reports it
    and then stops cleanly when the payload is absent, rather than misparsing the
    size as something small and resuming mid-payload.
    """
    header = bytearray(make_tar({"big.tar": b""})[:512])
    header[124:136] = b"\x80\x00\x00\x00\x00\x00\x00\x15\xd2\x178\x00"
    header[148:156] = b" " * 8
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}\x00 ".encode()
    stream = uniref.GunzipStream(io.BytesIO(gzip.compress(bytes(header))))
    members = [m for m, _ in uniref.iter_tar_members(stream)]
    assert [(m.name, m.size) for m in members] == [("big.tar", 93_719_050_240)]


# --------------------------------------------------------------------------- #
# Retaining the archive verbatim in the same pass
# --------------------------------------------------------------------------- #


def test_tap_sees_the_compressed_bytes_not_the_decompressed_ones():
    """The retained copy must be the released bytes, since only those match the
    published md5. A tap that received decompressed bytes would silently retain
    something that can never be verified against the release."""
    raw = nested_release()
    captured = bytearray()
    stream = uniref.GunzipStream(io.BytesIO(raw), tap=captured.extend)
    for _member, payload in uniref.iter_tar_members(
        stream, want=lambda m: True, recurse_into=lambda m: m.name.endswith(".tar")
    ):
        b"".join(payload)
    stream.drain()
    assert bytes(captured) == raw
    assert stream.compressed_md5() == hashlib.md5(raw).hexdigest()


def test_one_pass_both_retains_and_extracts():
    """The whole point of the tap: 169 GB is pulled once, not twice."""
    fifty = b">c1\n" + noise(30_000)
    raw = nested_release(fifty=fifty)
    client = FakeS3()
    archive = uniref.S3PartSink(client, "bucket", "archive.tar.gz").open()
    stream = uniref.GunzipStream(io.BytesIO(raw), tap=archive.write)
    extracted = {}
    for member, payload in uniref.iter_tar_members(
        stream,
        want=lambda m: m.name == "uniref50.fasta",
        recurse_into=lambda m: m.name.endswith(".tar"),
    ):
        if member.name == "uniref50.fasta":
            extracted[member.name] = b"".join(payload)
    stream.drain()
    archive.complete()
    assert extracted["uniref50.fasta"] == fifty
    assert client.assembled() == raw


def test_an_aborted_archive_upload_leaves_no_object():
    client = FakeS3()
    sink = uniref.S3PartSink(client, "bucket", "archive.tar.gz").open()
    sink.write(b"partial")
    sink.abort()
    assert client.aborted
    assert client.completed is None
    assert not sink.completed


# --------------------------------------------------------------------------- #
# Concurrent part uploads
# --------------------------------------------------------------------------- #


class ThreadSafeS3(FakeS3):
    """FakeS3 with a lock, since parts now arrive from several threads."""

    def __init__(self, delay: float = 0.0, fail_on: int | None = None):
        super().__init__()
        self._lock = threading.Lock()
        self._delay = delay
        self._fail_on = fail_on
        self.max_concurrent = 0
        self._active = 0

    def upload_part(self, **kw):
        with self._lock:
            self._active += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
        try:
            if self._delay:
                time.sleep(self._delay)
            if self._fail_on is not None and kw["PartNumber"] == self._fail_on:
                raise RuntimeError(f"part {self._fail_on} rejected")
            with self._lock:
                self.parts[kw["PartNumber"]] = kw["Body"]
            return {"ETag": f'"etag-{kw["PartNumber"]}"'}
        finally:
            with self._lock:
                self._active -= 1


def test_parts_are_reassembled_in_order_despite_finishing_out_of_order():
    """The correctness risk of concurrency: S3 needs ascending part numbers, and
    a reversed or shuffled list yields a corrupt object that still uploads."""
    client = ThreadSafeS3(delay=0.01)
    body = noise(40 << 20)
    with uniref.S3PartSink(
        client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART, concurrency=8
    ) as sink:
        for i in range(0, len(body), 1 << 16):
            sink.write(body[i : i + (1 << 16)])
    numbers = [p["PartNumber"] for p in client.completed["Parts"]]
    assert numbers == sorted(numbers)
    assert client.assembled() == body
    assert sink.sha256 == hashlib.sha256(body).hexdigest()


def test_uploads_actually_overlap():
    client = ThreadSafeS3(delay=0.05)
    with uniref.S3PartSink(
        client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART, concurrency=6
    ) as sink:
        sink.write(noise(30 << 20))
    assert client.max_concurrent > 1


def test_in_flight_parts_are_capped():
    """An unbounded queue would buffer the whole 169 GB archive in memory."""
    client = ThreadSafeS3(delay=0.02)
    concurrency = 2
    with uniref.S3PartSink(
        client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART, concurrency=concurrency
    ) as sink:
        sink.write(noise(60 << 20))
    assert client.max_concurrent <= concurrency


def test_a_failed_part_surfaces_rather_than_completing_a_corrupt_object():
    client = ThreadSafeS3(fail_on=2)
    with (
        pytest.raises(RuntimeError, match="part 2 rejected"),
        uniref.S3PartSink(
            client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART, concurrency=4
        ) as sink,
    ):
        for _ in range(8):
            sink.write(noise(uniref.S3PartSink.MIN_PART))
    assert client.completed is None
    assert client.aborted


def test_concurrency_below_one_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        uniref.S3PartSink(FakeS3(), "bucket", "k", concurrency=0)

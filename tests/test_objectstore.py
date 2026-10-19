"""Tests for the staged-object readers, and for the one property every sharded count rests on.

`shard_lines` is the interesting one. A7.2 reads a 5 GB TSV with four processes by splitting it
into byte ranges, and the whole arithmetic of the task — 15.7 million records, a confidence
split, a vOTU grouping — is wrong by exactly the number of lines that get read twice or not at
all. A line belongs to the shard its *first* byte falls in; a shard therefore reads past its end
to finish its last line and drops the partial line its own start landed inside.

That is cheap to get subtly wrong and expensive to notice: an off-by-one here would produce a
record count a few lines out, which looks like the data and not like the reader. So the property
is tested directly — every shard boundary of a small file, against the true line list — rather
than at the one boundary a single example would exercise.
"""

from __future__ import annotations

import itertools

import pytest
from conftest import FakeS3

from amazebio import objectstore

TSV = b"header\ta\tb\n" + b"".join(f"row{i}\tx\t{i * 11}\n".encode() for i in range(40))


def _lines_of(body: bytes, *, skip_header: bool) -> list[str]:
    text = body.decode().split("\n")
    if text and text[-1] == "":
        text.pop()
    return text[1:] if skip_header else text


@pytest.mark.parametrize("n_shards", list(range(1, 13)))
def test_every_line_is_read_exactly_once_whatever_the_shard_count(n_shards):
    client = FakeS3(TSV)
    shards = objectstore.byte_shards(len(TSV), n_shards)
    got: list[str] = []
    for start, end in shards:
        got += list(
            objectstore.shard_lines(client, "b", "k", start, end, chunk=7, skip_header=(start == 0))
        )
    assert got == _lines_of(
        TSV, skip_header=True
    ), f"{n_shards} shards lost or duplicated lines; every count in A7.2 is off by that many"


def test_a_shard_boundary_landing_inside_a_line_gives_it_to_the_shard_before():
    # The specific case the contract exists for, pinned on its own rather than only inside the
    # property above: a boundary mid-line must not split the line and must not emit it twice.
    client = FakeS3(TSV)
    mid = TSV.index(b"row20") + 3  # inside the "row20" line
    first = list(objectstore.shard_lines(client, "b", "k", 0, mid, chunk=8, skip_header=True))
    second = list(objectstore.shard_lines(client, "b", "k", mid, len(TSV), chunk=8))
    assert first[-1] == "row20\tx\t220"
    assert second[0] == "row21\tx\t231"
    assert first + second == _lines_of(TSV, skip_header=True)


def test_a_shard_ending_exactly_on_a_newline_does_not_steal_the_next_line():
    # The bug this is here for: finishing "the line that straddles the end" when nothing
    # straddles it reads on into the next shard's territory and counts a line twice.
    client = FakeS3(TSV)
    boundary = TSV.index(b"row20")
    first = list(objectstore.shard_lines(client, "b", "k", 0, boundary, chunk=9, skip_header=True))
    assert first[-1] == "row19\tx\t209"
    assert "row20\tx\t220" not in first


def test_a_file_without_a_trailing_newline_keeps_its_last_line():
    body = b"h\n" + b"one\n" + b"two"
    client = FakeS3(body)
    got: list[str] = []
    for start, end in objectstore.byte_shards(len(body), 3):
        got += list(
            objectstore.shard_lines(client, "b", "k", start, end, chunk=2, skip_header=(start == 0))
        )
    assert got == ["one", "two"]


def test_byte_shards_cover_the_object_once_and_no_further():
    shards = objectstore.byte_shards(1000, 7)
    assert shards[0][0] == 0
    assert shards[-1][1] == 1000
    assert all(a[1] == b[0] for a, b in itertools.pairwise(shards))
    assert objectstore.byte_shards(0, 4) == []
    with pytest.raises(ValueError):
        objectstore.byte_shards(10, 0)


def test_stream_lines_does_not_depend_on_the_chunk_falling_on_a_newline():
    client = FakeS3(TSV)
    for chunk in (1, 3, 11, 4096):
        got = list(objectstore.stream_lines(client, "b", "k", chunk=chunk))
        assert got == _lines_of(TSV, skip_header=False)


def test_a_short_range_read_raises_rather_than_being_treated_as_data():
    # A broken stream that does not raise is the failure A7.1 hit at sixteen readers. Treating
    # a short read as data would truncate a line and the count would be wrong, not absent.
    class Truncating(FakeS3):
        def get_object(self, Bucket, Key, Range=None):
            out = super().get_object(Bucket, Key, Range)
            out["Body"].data = out["Body"].data[:-1]
            return out

    reader = objectstore.S3RandomRead(Truncating(TSV), "b", "k")
    reader.ATTEMPTS, reader.BACKOFF = 2, 0.0
    with pytest.raises(OSError, match="short range read"):
        reader.read(10)


def test_split_uri_rejects_anything_that_is_not_an_s3_uri():
    assert objectstore.split_uri("s3://bucket/prefix/") == ("bucket", "prefix")
    assert objectstore.split_uri("s3://bucket") == ("bucket", "")
    with pytest.raises(ValueError):
        objectstore.split_uri("/local/path")


# --- Sequential reads (A1.8's release count) ---------------------------------------------


class _FakeBody:
    def __init__(self, data: bytes, fail_after: int | None = None) -> None:
        self._data, self._pos, self._fail_after = data, 0, fail_after
        self._served = 0

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = len(self._data) - self._pos
        if self._fail_after is not None and self._served >= self._fail_after:
            raise OSError("connection reset")
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        self._served += len(chunk)
        return chunk

    def close(self) -> None:
        pass


class _FakeS3:
    """Counts requests, so a per-read regression is visible rather than merely slow."""

    def __init__(self, data: bytes, fail_after: int | None = None) -> None:
        self.data, self.fail_after = data, fail_after
        self.ranges: list[str | None] = []

    def head_object(self, **kw: object) -> dict:
        return {"ContentLength": len(self.data)}

    def get_object(self, **kw: object) -> dict:
        rng = kw.get("Range")
        self.ranges.append(rng)  # type: ignore[arg-type]
        start = int(str(rng).split("=")[1].split("-")[0]) if rng else 0
        fail = self.fail_after if len(self.ranges) == 1 else None
        return {"Body": _FakeBody(self.data[start:], fail_after=fail)}


def test_a_sequential_read_opens_the_object_once() -> None:
    """The regression that cost a launch: one request, not one per block."""
    from amazebio.objectstore import S3SequentialRead

    data = bytes(range(256)) * 400
    fake = _FakeS3(data)
    reader = S3SequentialRead(fake, "b", "k")
    out = b"".join(iter(lambda: reader.read(1024), b""))
    assert out == data
    assert reader.requests == 1, f"{reader.requests} requests for one sequential read"


def test_a_broken_stream_resumes_from_the_offset_rather_than_restarting() -> None:
    """A single GET held for hours will break; the caller must still see one byte sequence."""
    from amazebio.objectstore import S3SequentialRead

    data = bytes(range(256)) * 400
    fake = _FakeS3(data, fail_after=5000)
    reader = S3SequentialRead(fake, "b", "k")
    reader.BACKOFF = 0  # type: ignore[misc]
    out = b"".join(iter(lambda: reader.read(1024), b""))
    assert out == data, "resuming must not duplicate or drop bytes"
    assert any(r is not None for r in fake.ranges), "the resume should be a ranged request"


def test_reading_past_the_end_returns_empty() -> None:
    from amazebio.objectstore import S3SequentialRead

    fake = _FakeS3(b"abcdef")
    reader = S3SequentialRead(fake, "b", "k")
    assert reader.read(6) == b"abcdef"
    assert reader.read(10) == b""

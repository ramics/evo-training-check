"""Reading staged corpora out of object storage: ranged, resumable, and splittable.

Three access patterns, one per shape of staged artefact, kept here rather than in a tool
because A7.2 needs all three and A7.1 already needed one of them.

**Random access** (:class:`S3RandomRead`) is what Parquet wants: footer first, then the row
groups the caller asks for. A range GET per read is more requests than a stream would make and
costs nothing in-region, which is where this runs.

**Line streaming** (:func:`stream_lines`) is what a 5 GB TSV wants when it is read once, start
to finish.

**Byte shards** (:func:`byte_shards`, :func:`shard_lines`) are what a 5 GB TSV wants when it is
read once by four processes. A line-oriented text file is splittable in a way a gzip stream is
not, which is the distinction AGENTS.md's EC2 note turns on: the IMG/VR metadata tables are
plain TSV, so the parallelism ceiling here is cores and the outbound proxy rather than the
format. Each shard is extended to the next newline and drops its own first partial line, so
every line is read exactly once by exactly one shard — the property a count depends on, and the
one :func:`shard_lines` is tested for directly.

A short range read is treated as a failure rather than as data. That is the lesson A7.1 learned
at sixteen concurrent readers: a broken stream that does not raise would corrupt a column chunk
or silently truncate a line, and a count over a truncated read is not a count.
"""

from __future__ import annotations

import io
import os
import time
from collections.abc import Iterator
from typing import Any

__all__ = [
    "REGION",
    "S3_ENDPOINT",
    "S3RandomRead",
    "byte_shards",
    "client",
    "shard_lines",
    "split_uri",
    "stream_lines",
]

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"

#: Read size for sequential streaming. Four megabytes: large enough that the per-request
#: overhead disappears, small enough that a retry re-reads little.
CHUNK = 1 << 22


def client() -> Any:
    import boto3

    return boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)


def split_uri(uri: str) -> tuple[str, str]:
    """`s3://bucket/prefix` -> `(bucket, prefix)`, with the trailing slash removed."""
    if not uri.startswith("s3://"):
        raise ValueError(f"not an s3 URI: {uri!r}")
    bucket, _, prefix = uri[len("s3://") :].partition("/")
    return bucket, prefix.rstrip("/")


class S3RandomRead(io.RawIOBase):
    """A seekable reader over an S3 object, backed by range requests."""

    #: Attempts per range, and the backoff between them. A range GET that breaks mid-stream is
    #: the normal failure at this concurrency rather than an exceptional one.
    ATTEMPTS = 5
    BACKOFF = 2.0

    def __init__(self, client: Any, bucket: str, key: str) -> None:
        self._c, self._bucket, self._key = client, bucket, key
        self.size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            self._pos = offset
        elif whence == os.SEEK_CUR:
            self._pos += offset
        else:
            self._pos = self.size + offset
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self._pos
        size = min(size, self.size - self._pos)
        if size <= 0:
            return b""
        end = self._pos + size - 1
        last: Exception | None = None
        for attempt in range(self.ATTEMPTS):
            try:
                body = self._c.get_object(
                    Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}"
                )["Body"].read()
            except Exception as exc:  # any transport failure here is worth one more attempt
                last = exc
                time.sleep(self.BACKOFF**attempt)
                continue
            if len(body) != size:
                # A short read is a broken stream that did not raise. Treating it as data would
                # corrupt the caller's parse and fail far from the cause.
                last = OSError(f"short range read: got {len(body)} of {size} bytes")
                time.sleep(self.BACKOFF**attempt)
                continue
            self._pos += len(body)
            return body
        raise OSError(
            f"range {self._pos}-{end} of s3://{self._bucket}/{self._key} failed "
            f"{self.ATTEMPTS} times; last error: {last}"
        ) from last

    def readinto(self, buf: Any) -> int:
        """Required by `io.BufferedReader`, which calls this and never `read`."""
        chunk = self.read(len(buf))
        buf[: len(chunk)] = chunk
        return len(chunk)


def stream_lines(client: Any, bucket: str, key: str, *, chunk: int = CHUNK) -> Iterator[str]:
    """Stream one staged object as decoded lines, without holding it in memory.

    `iter_lines` on a botocore stream buffers unboundedly on input without newlines, so this
    does the chunking itself and keeps only the tail.
    """
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    tail = b""
    while block := body.read(chunk):
        tail += block
        *complete, tail = tail.split(b"\n")
        for line in complete:
            yield line.decode("utf-8", "replace")
    if tail:
        yield tail.decode("utf-8", "replace")


def byte_shards(size: int, n: int) -> list[tuple[int, int]]:
    """Split `size` bytes into at most `n` half-open `[start, end)` ranges.

    Ranges are byte offsets and ignore line boundaries entirely; :func:`shard_lines` is what
    makes them line-safe. Returned smallest-offset first so a caller can special-case the shard
    that holds the header.
    """
    if n < 1:
        raise ValueError("need at least one shard")
    if size <= 0:
        return []
    n = min(n, size)
    step = -(-size // n)  # ceiling, so the last shard is the short one
    return [(start, min(start + step, size)) for start in range(0, size, step)]


def shard_lines(
    client: Any,
    bucket: str,
    key: str,
    start: int,
    end: int,
    *,
    chunk: int = CHUNK,
    skip_header: bool = False,
) -> Iterator[str]:
    """Yield the complete lines of one byte shard, exactly once each.

    The contract, which is what every sharded count rests on: a line belongs to the shard its
    **first** byte falls in. So a shard reads past `end` to finish its last line, and drops the
    partial line its own `start` landed inside — except the shard starting at byte 0, which has
    no partial line and instead drops the header when asked to.

    "Landed inside" is decided by looking, not by assuming. A shard whose `start` falls exactly
    on the first byte of a line owns that line and must not drop it, and that case is common
    rather than exotic: byte shards of a file with short fixed-width rows land on a boundary
    often. Getting it wrong loses one line per shard, which looks like the data rather than like
    the reader — so the byte before `start` is read, one byte, and the line is dropped only if it
    is not a newline.

    Reading past `end` is bounded by the length of one line, not by the next shard: the extra
    read stops at the first newline it finds.
    """
    reader = S3RandomRead(client, bucket, key)
    size = reader.size
    if start >= size:
        return
    if start > 0:
        preceding = client.get_object(
            Bucket=bucket, Key=key, Range=f"bytes={start - 1}-{start - 1}"
        )["Body"].read()
        drop_first = preceding != b"\n"
    else:
        drop_first = skip_header
    reader.seek(start)
    tail = b""
    pos = start
    first = True
    while pos < end:
        block = reader.read(min(chunk, end - pos))
        if not block:
            break
        pos += len(block)
        tail += block
        *complete, tail = tail.split(b"\n")
        for line in complete:
            if first and drop_first:
                # Either a line this shard landed inside — which belongs to the shard before
                # it — or the header.
                first = False
                continue
            first = False
            yield line.decode("utf-8", "replace")
    # Finish the line that straddles `end`, reading only as far as its newline. An empty tail
    # means the shard ended exactly on a line boundary, and reading on from there would yield a
    # line whose first byte belongs to the next shard — counted twice across the pass.
    while tail:
        if b"\n" in tail:
            line, _, tail = tail.partition(b"\n")
            if not (first and drop_first):
                yield line.decode("utf-8", "replace")
            first = False
            break
        block = reader.read(chunk)
        if not block:
            if tail and not (first and drop_first):
                yield tail.decode("utf-8", "replace")
            break
        tail += block

"""Shared test fixtures.

`FakeS3` is here rather than in one test module because three of them need it: the sharded
reader, the input-side scan, and the end-to-end conformance pass. One fake that behaves like the
real client's ranged reads is worth more than three that each behave slightly differently —
a count that is right against one fake and wrong against another tells you nothing.
"""

from __future__ import annotations


class FakeS3:
    """Enough of the S3 client to serve ranged reads out of a bytes object."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.ranges: list[str] = []

    def head_object(self, Bucket: str, Key: str) -> dict:
        return {"ContentLength": len(self.body)}

    def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
        if Range is None:
            return {"Body": _Stream(self.body)}
        self.ranges.append(Range)
        start, _, end = Range.removeprefix("bytes=").partition("-")
        return {"Body": _Stream(self.body[int(start) : int(end) + 1])}


class _Stream:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self.data) - self.pos
        out = self.data[self.pos : self.pos + size]
        self.pos += len(out)
        return out

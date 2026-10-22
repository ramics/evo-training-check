"""A seekable reader over an HTTPS URL, backed by range requests — task B4.1.

The same shape as :class:`amazebio.objectstore.S3RandomRead`, one protocol over. It exists for
one reason: ProteinGym's multiple-sequence alignments ship as a 1.5 GB zip of 217 files and
this project needs 31 of them. A zip's directory lives at the end of the file, so a reader that
can seek lets :mod:`zipfile` open the archive over the network and extract only the members
asked for. Pulling the whole archive to take a fifth of it would spend the session's writable
disk on files nothing reads.

Not every host serves ranges, and one that ignores the header answers 200 with the whole body
rather than failing — which would look like a successful read of the wrong bytes. So the first
read checks for 206 and refuses otherwise, rather than discovering the problem as a corrupt
parse somewhere downstream.
"""

from __future__ import annotations

import io
import os
import time
import urllib.error
import urllib.request

__all__ = ["RangesUnsupported", "WebRandomRead"]


class RangesUnsupported(RuntimeError):
    """The server answered a range request with the whole body."""


class WebRandomRead(io.RawIOBase):
    """A seekable reader over an HTTPS URL."""

    #: Attempts per range, and the backoff between them. A range GET that breaks mid-stream is
    #: an ordinary failure over a long archive rather than an exceptional one.
    ATTEMPTS = 5
    BACKOFF = 2.0

    def __init__(self, url: str, *, agent: str, timeout: int = 120) -> None:
        self.url, self._agent, self._timeout = url, agent, timeout
        self.size = self._length()
        self._pos = 0

    def _length(self) -> int:
        request = urllib.request.Request(
            self.url, method="HEAD", headers={"User-Agent": self._agent}
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            length = response.headers.get("Content-Length")
        if length is None:
            raise RangesUnsupported(f"{self.url} does not state its length")
        return int(length)

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

    def _get(self, start: int, end: int) -> bytes:
        request = urllib.request.Request(
            self.url, headers={"User-Agent": self._agent, "Range": f"bytes={start}-{end}"}
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            if response.status != 206:
                raise RangesUnsupported(
                    f"{self.url} answered {response.status} to a range request, so the body is "
                    "the whole file rather than the bytes asked for"
                )
            return response.read()

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
                body = self._get(self._pos, end)
            except RangesUnsupported:
                raise
            except (urllib.error.URLError, OSError) as exc:
                last = exc
                time.sleep(self.BACKOFF**attempt)
                continue
            if len(body) != size:
                # A short read is a broken stream that did not raise. Treating it as data would
                # corrupt the caller's parse and fail far from the cause.
                last = OSError(f"short range read: got {len(body)} of {size} bytes")
                time.sleep(self.BACKOFF**attempt)
                continue
            self._pos += size
            return body
        raise OSError(f"range read failed after {self.ATTEMPTS} attempts: {last}")

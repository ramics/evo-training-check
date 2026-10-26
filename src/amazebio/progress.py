"""A heartbeat that comes from the stream rather than from the consumer's loop.

`AGENTS.md` requires a long pass to report where it got to, and to answer that for a run that
was killed as readily as for one that ended. The failure it records (D-192) is not a missing
heartbeat but a *misplaced* one: a line printed at the consumer's loop boundary says nothing
while the reader is traversing the part of the object the consumer has no reason to speak up
about. A2.6's census spent fourteen hours and published nothing, and A7.5's first real pass —
314 named records inside an 11.22 GB object — printed one line at the start and the next one
forty minutes later, because its progress was tied to a record chunk and the whole run was one
chunk. Both are the same bug: the progress belonged to the wrong loop.

So the heartbeat attaches to the **reader**:

    reader = progress.beating(obj.buffered(), total=source.bytes, label=source.key)
    for record in iter_fasta_selected(GunzipStream(reader), ids=ids, component=...):
        ...

Every read reports, on an interval, how far through the object it is — whatever the consumer is
doing with the records, and whether or not it has found any. A consumer that also wants to say
something per chunk still can; this is the floor beneath it.

Two deliberate properties:

**It reports bytes, not records.** Bytes are monotonic in a sequential pass and are the thing
whose remainder can be divided by a rate, so a line from this is enough to decide whether to
wait or to kill the run. A record count is neither when the records are sparse.

**It never changes what is read.** It is a pass-through: the same bytes, the same EOF, the same
exceptions. A heartbeat that could alter the pass would be a worse trade than no heartbeat.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

__all__ = ["Beating", "beating"]

#: Report about this often, in bytes read. Four hundred megabytes is roughly half a minute of
#: in-region sequential reading, which is frequent enough to see a stall and rare enough that a
#: multi-gigabyte pass does not drown its own output.
EVERY = 400 << 20


class Beating:
    """A read-through wrapper that reports progress on a byte interval.

    Anything with `read(size)` can be wrapped, and the wrapper offers `read`, `tell`, `close`
    and attribute access to the stream beneath, which is what the gzip and FASTA readers in
    this project use.
    """

    def __init__(
        self,
        stream: Any,
        *,
        total: int | None = None,
        label: str = "",
        every: int = EVERY,
        out: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stream = stream
        self._total = total
        self._label = label.rsplit("/", 1)[-1] if label else ""
        self._every = max(int(every), 1)
        self._out = out if out is not None else _print
        self._clock = clock
        self._read = 0
        self._announced = 0
        self._started = clock()

    def read(self, size: int = -1) -> bytes:
        block = self._stream.read(size)
        if block:
            self._read += len(block)
            if self._read - self._announced >= self._every:
                self._announced = self._read
                self._out(self.line())
        return block

    def line(self) -> str:
        """The progress line: where it is, how long it has taken, and what is left."""
        elapsed = max(self._clock() - self._started, 1e-9)
        rate = self._read / elapsed
        parts = [f"  {self._label}: " if self._label else "  "]
        if self._total:
            share = self._read / self._total
            remaining = (self._total - self._read) / rate if rate else 0.0
            parts.append(
                f"{self._read / 1e9:.2f}/{self._total / 1e9:.2f} GB ({share:.0%}), "
                f"{rate / 1e6:.0f} MB/s, {elapsed / 60:.1f} min in, "
                f"~{remaining / 60:.0f} min left"
            )
        else:
            # No total is the honest case for a stream whose length nothing declared; the rate
            # and the elapsed time still distinguish a slow pass from a stopped one.
            parts.append(
                f"{self._read / 1e9:.2f} GB, {rate / 1e6:.0f} MB/s, {elapsed / 60:.1f} min in"
            )
        return "".join(parts)

    @property
    def bytes_read(self) -> int:
        return self._read

    def tell(self) -> int:
        """Bytes delivered so far, which for a sequential pass is the position."""
        return self._read

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()

    def __getattr__(self, name: str) -> Any:
        # Only reached for names this class does not define, so the wrapper stays transparent
        # to a reader that wants `readable()`, `seekable()` or the retry counters underneath.
        return getattr(self._stream, name)


def beating(
    stream: Any,
    *,
    total: int | None = None,
    label: str = "",
    every: int = EVERY,
    out: Callable[[str], None] | None = None,
) -> Beating:
    """Wrap `stream` so a long sequential pass over it reports where it has got to."""
    return Beating(stream, total=total, label=label, every=every, out=out)


def _print(line: str) -> None:
    # Flushed, because the whole point is that the line arrives while the run is still going;
    # and to stdout, where the other progress lines of these tools go.
    print(line, flush=True)

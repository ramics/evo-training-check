"""`amazebio.progress` — the heartbeat that comes from the stream, not the consumer's loop.

What is under test is the property D-192 was about: a line arrives while the pass is running,
on an interval of bytes, whether or not the consumer has anything to say. And the property that
makes it safe to wrap a corpus read in: it does not change what is read.
"""

from __future__ import annotations

import io

from amazebio import progress


class _Clock:
    """A clock the test moves, so a rate and an estimate are assertable."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_line_arrives_on_the_byte_interval_not_at_the_end() -> None:
    lines: list[str] = []
    wrapped = progress.beating(io.BytesIO(b"x" * 1000), every=100, out=lines.append)
    for _ in range(10):
        wrapped.read(50)
    # Ten reads of fifty bytes crosses the hundred-byte interval five times.
    assert len(lines) == 5


def test_nothing_is_reported_before_the_interval_is_crossed() -> None:
    lines: list[str] = []
    wrapped = progress.beating(io.BytesIO(b"x" * 1000), every=100, out=lines.append)
    wrapped.read(99)
    assert lines == []


def test_the_line_says_where_it_is_how_fast_and_what_is_left() -> None:
    lines: list[str] = []
    clock = _Clock()
    wrapped = progress.Beating(
        io.BytesIO(b"x" * 4_000_000_000),
        total=4_000_000_000,
        label="corpora/opengenome2/fasta/imgvr.fasta.gz",
        every=1_000_000_000,
        out=lines.append,
        clock=clock,
    )
    clock.now = 60.0
    wrapped.read(1_000_000_000)
    assert len(lines) == 1
    line = lines[0]
    assert "imgvr.fasta.gz" in line  # the key's last segment, not the whole key
    assert "1.00/4.00 GB (25%)" in line
    assert "17 MB/s" in line  # 1 GB in one minute
    assert "~3 min left" in line  # three quarters to go at that rate


def test_a_stream_of_unknown_length_still_reports_rate_and_elapsed() -> None:
    # The honest case for a stream whose length nothing declared: no share and no estimate, but
    # a rate and an elapsed time still tell a slow pass from a stopped one.
    lines: list[str] = []
    clock = _Clock()
    wrapped = progress.Beating(io.BytesIO(b"x" * 2000), every=1000, out=lines.append, clock=clock)
    clock.now = 10.0
    wrapped.read(1000)
    assert "GB," in lines[0] and "min in" in lines[0]
    assert "left" not in lines[0]


def test_wrapping_does_not_change_what_is_read() -> None:
    data = bytes(range(256)) * 40
    plain = io.BytesIO(data)
    wrapped = progress.beating(io.BytesIO(data), every=100, out=lambda _: None)
    # Read the whole stream and then past its end, so the comparison covers EOF too.
    got_plain = [plain.read(3000) for _ in range(5)]
    got_wrapped = [wrapped.read(3000) for _ in range(5)]
    assert got_plain == got_wrapped
    assert b"".join(got_wrapped) == data
    assert got_wrapped[-1] == b""  # the read past the end
    assert wrapped.read(1) == b"" == plain.read(1)


def test_bytes_read_and_tell_track_the_pass() -> None:
    wrapped = progress.beating(io.BytesIO(b"x" * 500), every=1 << 30, out=lambda _: None)
    wrapped.read(200)
    assert wrapped.bytes_read == wrapped.tell() == 200


def test_the_stream_underneath_stays_reachable() -> None:
    """A corpus reader's retry counters and `seekable()` live on the object beneath."""
    underlying = io.BytesIO(b"x" * 10)
    wrapped = progress.beating(underlying, out=lambda _: None)
    assert wrapped.seekable() is True
    assert wrapped.getvalue() == b"x" * 10


def test_an_exception_from_underneath_is_not_swallowed() -> None:
    class Broken:
        def read(self, size: int = -1) -> bytes:
            raise OSError("connection reset")

    wrapped = progress.beating(Broken(), out=lambda _: None)
    try:
        wrapped.read(10)
    except OSError as exc:
        assert "connection reset" in str(exc)
    else:  # pragma: no cover - the point of the test
        raise AssertionError("the wrapper swallowed a read failure")

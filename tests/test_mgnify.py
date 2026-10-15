"""Tests for `amazebio.mgnify` — task A1.5.

The thing worth testing is the ordering, not the copying. The corpus bucket has no
delete, so an object that completes is permanent, and the whole design rests on a
mismatch raising *before* `complete_multipart_upload` is reached. So the tests drive the
real `S3PartSink` against a fake client and assert on which of `completed` and `aborted`
the client saw — a test that only checked the exception would pass while the bytes were
written anyway.
"""

from __future__ import annotations

import hashlib
import io

import pytest

# The sink's fake client lives with the sink's own tests; one fake, so it cannot drift
# from the client interface `uniref.S3PartSink` actually calls.
from test_uniref import FakeS3

from amazebio import mgnify, uniref


class Reader:
    """Minimal stand-in for `uniref.ResumableRead`: forward-only, with a position."""

    def __init__(self, body: bytes, *, reconnects: int = 0, url: str = "https://example/f.gz"):
        self._buf = io.BytesIO(body)
        self.url = url
        self.reconnects = reconnects

    def read(self, size: int) -> bytes:
        return self._buf.read(size)


def md5(body: bytes) -> str:
    return hashlib.md5(body).hexdigest()


BODY = b"MGYP" * (3 << 20)  # 12 MiB, enough for several minimum-size parts.


def test_a_matching_transfer_is_verified_and_completed():
    client = FakeS3()
    with uniref.S3PartSink(client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART) as sink:
        staged = mgnify.stream_verified(
            Reader(BODY), sink, expected_bytes=len(BODY), expected_md5=md5(BODY)
        )

    assert staged.verified is True
    assert staged.partial is False
    assert staged.bytes_read == len(BODY)
    assert staged.md5 == md5(BODY)
    assert staged.sha256 == hashlib.sha256(BODY).hexdigest()
    assert client.assembled() == BODY
    assert client.completed is not None
    assert client.aborted is False


def test_a_wrong_md5_aborts_the_upload_instead_of_completing_it():
    client = FakeS3()
    with (
        pytest.raises(uniref.VerificationError, match="does not match the published"),
        uniref.S3PartSink(client, "bucket", "k", part_bytes=uniref.S3PartSink.MIN_PART) as sink,
    ):
        mgnify.stream_verified(Reader(BODY), sink, expected_bytes=len(BODY), expected_md5="0" * 32)

    # This is the assertion the design depends on. The bucket cannot delete, so
    # "raised, but completed anyway" would be an unfixable corpus, not a failed run.
    assert client.completed is None
    assert client.aborted is True


def test_a_short_transfer_aborts_too():
    """A server that closes early must not leave a truncated object behind."""
    client = FakeS3()
    with (
        pytest.raises(uniref.VerificationError, match="read 100 bytes"),
        uniref.S3PartSink(client, "bucket", "k") as sink,
    ):
        mgnify.stream_verified(
            Reader(b"x" * 100), sink, expected_bytes=1_000_000, expected_md5=md5(b"x" * 100)
        )

    assert client.completed is None
    assert client.aborted is True


def test_the_size_check_runs_before_the_md5_check():
    """A truncated stream whose md5 happens to be checked first would report the wrong
    cause. The size is the specific diagnosis, so it is the one reported."""
    client = FakeS3()
    short = b"x" * 100
    with (
        pytest.raises(uniref.VerificationError, match=r"read 100 bytes, the release"),
        uniref.S3PartSink(client, "bucket", "k") as sink,
    ):
        mgnify.stream_verified(Reader(short), sink, expected_bytes=200, expected_md5="0" * 32)


def test_a_smoke_test_aborts_the_upload_rather_than_completing_a_prefix():
    """The hazard `--max-compressed-bytes` creates, and the one A1.3 fell into.

    A truncated upload completed into a bucket with no delete is a corpus object that
    is permanently wrong and looks staged. So a partial run must abort, not complete.
    """
    client = FakeS3()
    with (
        pytest.raises(mgnify.PartialRun) as caught,
        uniref.S3PartSink(client, "bucket", "k") as sink,
    ):
        mgnify.stream_verified(
            Reader(BODY),
            sink,
            expected_bytes=len(BODY),
            expected_md5=md5(BODY),
            max_bytes=1 << 20,
        )

    assert client.completed is None
    assert client.aborted is True
    # A PartialRun is a VerificationError, because the sink has to treat it like one.
    assert isinstance(caught.value, uniref.VerificationError)

    staged = caught.value.staged
    assert staged.partial is True
    assert staged.verified is False
    assert staged.bytes_read == 1 << 20
    assert staged.as_manifest()["verified"] is False


def test_a_partial_run_can_be_tolerated_where_nothing_is_written():
    """`abort_on_partial=False` exists for a read-only pass, and still records the
    run as unverified so no manifest of one can read as a staged corpus."""
    client = FakeS3()
    with uniref.S3PartSink(client, "bucket", "k") as sink:
        staged = mgnify.stream_verified(
            Reader(BODY),
            sink,
            expected_bytes=len(BODY),
            expected_md5=md5(BODY),
            max_bytes=1 << 20,
            abort_on_partial=False,
        )
    assert (staged.partial, staged.verified) == (True, False)


def test_progress_is_reported_in_bytes_read_so_far():
    seen: list[int] = []
    client = FakeS3()
    with uniref.S3PartSink(client, "bucket", "k") as sink:
        mgnify.stream_verified(
            Reader(BODY),
            sink,
            expected_bytes=len(BODY),
            expected_md5=md5(BODY),
            chunk=1 << 20,
            progress=seen.append,
        )
    assert seen == sorted(seen)
    assert seen[-1] == len(BODY)


def test_the_manifest_row_carries_both_the_expected_and_the_actual():
    """A manifest that recorded only the actual digest could not show it was checked."""
    client = FakeS3()
    with uniref.S3PartSink(client, "bucket", "k") as sink:
        staged = mgnify.stream_verified(
            Reader(BODY, reconnects=3),
            sink,
            expected_bytes=len(BODY),
            expected_md5=md5(BODY),
        )
    row = staged.as_manifest()
    assert row["md5"] == row["expected_md5"] == md5(BODY)
    assert row["bytes"] == row["expected_bytes"] == len(BODY)
    assert row["reconnects"] == 3
    assert row["url"] == "https://example/f.gz"

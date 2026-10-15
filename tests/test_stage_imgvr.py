"""Tests for the transfer path in `tools/stage_imgvr.py` — task A1.7.

The pins, the release taxonomy and the inventory arithmetic are `amazebio.imgvr`'s and are
tested in `test_imgvr.py`. What is tested here is the one step that writes to a bucket with no
`s3:DeleteObject`, where a mistake is permanent: a file must be uploaded only after its bytes
have been shown to match the md5 the publisher published, and a file that fails that check must
leave nothing behind — not a partial object, and not a spool file on disk.

The real transfer is 7.9 GB per release and needs a credential, so these drive the function
against a fake listing response and a fake S3 client.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import zipfile

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "stage_imgvr.py"
_spec = importlib.util.spec_from_file_location("stage_imgvr_under_test", _PATH)
stage = importlib.util.module_from_spec(_spec)
sys.modules["stage_imgvr_under_test"] = stage
_spec.loader.exec_module(stage)

from amazebio import imgvr  # noqa: E402  (after the tool, which sets up `src` on the path)

BODY = b"uvig\tvotu\tconfidence\n" * 4096
NBYTES = len(BODY)
MEMBER = "Cus_VR/IMG_VR_2022-09-20_6/IMGVR_all_Sequence_information.tsv"


def _zip(members):
    """The publisher serves a zip, not raw bytes (D-062). Build one the same shape."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Download_1_File_Manifest.csv", "filename,md5 checksum\n")
        for name, body in members.items():
            zf.writestr(name, body)
    return buf.getvalue()


class FakeClient:
    """Records what was asked of S3, and from where."""

    def __init__(self):
        self.uploaded = []

    def upload_fileobj(self, fileobj, bucket, key):
        # Read it here: the point of streaming the member is that the bytes handed to the
        # upload are the ones that were just verified, never a second copy on disk.
        self.uploaded.append((key, fileobj.read()))

    def put_object(self, **kw):  # pragma: no cover - a regression guard, see test below
        raise AssertionError(
            "put_object caps a single upload at 5 GiB and the largest file staged here is "
            "within a few hundred MB of that; use upload_fileobj"
        )


def _file(md5, *, nbytes=NBYTES):
    return imgvr.ReleaseFile(
        name="IMGVR_all_Sequence_information.tsv",
        role="sequence_information",
        bytes=nbytes,
        md5=md5,
        high_confidence=False,
        directory="AUTO-420894",
    )


@pytest.fixture
def served(monkeypatch):
    """Serve BODY from the tool's own request helper, and assert the auth shape."""

    @contextlib.contextmanager
    def fake_request(url, *, token=None, data=None):
        import json

        expected_url, expected_body = imgvr.download_request(
            ["abc123"], organism_id="Custom_MPI-IMG_VR", top_hit="th"
        )
        assert url == expected_url, "must POST to the route that actually serves bytes"
        assert token == "tok", "the token must reach the download, as a Bearer header"
        assert json.loads(data) == expected_body, "the body names the organism and the file"
        yield io.BytesIO(_zip({MEMBER: BODY}))

    monkeypatch.setattr(stage, "_request", fake_request)


def _stage(file, tmp_path, client):
    return stage.download_verify_upload(
        file,
        "abc123",
        date="2022-09-20",
        token="tok",
        client=client,
        bucket="corpus",
        prefix="staged",
        dry_run=False,
        spool=tmp_path,
        organism_id="Custom_MPI-IMG_VR",
        top_hit="th",
    )


def test_a_matching_md5_uploads_the_bytes_that_were_verified(served, tmp_path):
    import hashlib

    client = FakeClient()
    row = _stage(_file(hashlib.md5(BODY).hexdigest()), tmp_path, client)

    assert len(client.uploaded) == 1
    key, sent = client.uploaded[0]
    assert key == "staged/imgvr/2022-09-20/IMGVR_all_Sequence_information.tsv"
    assert sent == BODY, "the uploaded bytes must be the ones that were hashed"
    assert row["verified"] is True
    assert row["md5"] == hashlib.md5(BODY).hexdigest()
    assert row["sha256"] == hashlib.sha256(BODY).hexdigest()


def test_a_wrong_md5_uploads_nothing(served, tmp_path):
    client = FakeClient()
    with pytest.raises(SystemExit, match="does not match the publisher"):
        _stage(_file("0" * 32), tmp_path, client)
    assert client.uploaded == [], "the bucket has no DeleteObject; a bad object is permanent"


def test_a_short_read_uploads_nothing(served, tmp_path):
    import hashlib

    client = FakeClient()
    # Right digest, wrong length: a truncated transfer that happened to hash is not the case
    # being guarded, but a listing/bytes disagreement means one of the two is wrong.
    with pytest.raises(SystemExit, match="bytes read"):
        _stage(_file(hashlib.md5(BODY).hexdigest(), nbytes=NBYTES + 1), tmp_path, client)
    assert client.uploaded == []


@pytest.mark.parametrize("md5", ["match", "mismatch"])
def test_the_spool_file_is_removed_either_way(served, tmp_path, md5):
    import hashlib

    client = FakeClient()
    expected = hashlib.md5(BODY).hexdigest() if md5 == "match" else "0" * 32
    with contextlib.suppress(SystemExit):
        _stage(_file(expected), tmp_path, client)
    # Staging both releases is 15.8 GB through a spool that must only ever hold one file:
    # a leak here turns a working run into a disk-full failure part-way through.
    assert list(tmp_path.iterdir()) == [], "the spool file must not survive the call"


def test_a_dry_run_transfers_nothing(tmp_path):
    client = FakeClient()
    row = stage.download_verify_upload(
        _file("0" * 32),
        "abc123",
        date="2022-09-20",
        token="tok",
        client=client,
        bucket="corpus",
        prefix="",
        dry_run=True,
        spool=tmp_path,
        organism_id="Custom_MPI-IMG_VR",
        top_hit="th",
    )
    assert row["skipped"] == "dry-run"
    assert row["verified"] is None
    assert client.uploaded == []
    assert list(tmp_path.iterdir()) == []


def test_a_zip_without_the_expected_member_uploads_nothing(monkeypatch, tmp_path):
    import hashlib

    # One file is requested per call, so the zip should hold exactly one member with that
    # name. A zip that does not is the publisher having changed something, and guessing which
    # member was meant would write a permanent object under the wrong key.
    @contextlib.contextmanager
    def fake_request(url, *, token=None, data=None):
        yield io.BytesIO(_zip({"Cus_VR/IMG_VR_2022-09-20_6/something_else.tsv": BODY}))

    monkeypatch.setattr(stage, "_request", fake_request)
    client = FakeClient()
    with pytest.raises(SystemExit, match="zip holds 0 members"):
        _stage(_file(hashlib.md5(BODY).hexdigest()), tmp_path, client)
    assert client.uploaded == []
    assert list(tmp_path.iterdir()) == []

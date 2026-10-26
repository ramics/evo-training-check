"""Tests for the non-destructive write path — `objectstore.put_once` and the guard around it.

D-216 is the defect these cover. The corpora bucket withholds `s3:DeleteObject`, which reads
like immutability and is not: `PutObject` on an existing key succeeds and the earlier bytes
stop being readable. One key held a 2,446-byte partial run and then the 215,098-byte full run,
and nothing was lost only because the replacement happened to be the better of the two.

So the properties worth testing are the ones luck supplied that day:

* two commits never land on one object,
* the same commit producing *different* bytes is refused before anything is written,
* the same commit producing the *same* bytes is a no-op rather than an error, because a
  re-run that reproduces is the thing the project wants people to do,
* and a caller with no commit at all still cannot silently replace a result.

The last test in the file is of a different kind: it reads the source tree and fails if any
module builds its own S3 client. That is not a style rule. An S3 client without an explicit
regional `endpoint_url` resolves to the legacy global hostname, which the egress proxy does not
inject credentials for, so the request arrives unsigned and comes back as a bare `AccessDenied`
indistinguishable from a missing IAM grant. That cost most of a day in October. A grep is the
only thing that keeps the fix from being re-spelled wrongly at the fourteenth call site.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib

import pytest

from amazebio import objectstore

BUCKET = "test-bucket"
KEY = "corpora/results/a9-9/table.json"


class RecordingS3:
    """An in-memory S3 that keeps bodies and metadata, and counts the calls it was asked for."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.puts: list[str] = []
        self.heads: list[str] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes, Metadata: dict | None = None) -> dict:
        self.puts.append(Key)
        self.objects[Key] = (Body, dict(Metadata or {}))
        return {}

    def head_object(self, Bucket: str, Key: str) -> dict:
        self.heads.append(Key)
        if Key not in self.objects:
            raise _missing(Key)
        body, meta = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": meta}


def _missing(key: str) -> Exception:
    exc = Exception(f"no such key: {key}")
    exc.response = {  # type: ignore[attr-defined]
        "Error": {"Code": "404", "Message": "Not Found"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }
    return exc


def _denied() -> Exception:
    exc = Exception("Access Denied")
    exc.response = {  # type: ignore[attr-defined]
        "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
        "ResponseMetadata": {"HTTPStatusCode": 403},
    }
    return exc


class TestCommitKeyedNames:
    def test_the_twin_sits_one_level_in_rather_than_beside_its_stable_copy(self):
        assert (
            objectstore.commit_keyed("corpora/results/a9-9/table.json", "abc123")
            == "corpora/results/a9-9/by-commit/abc123/table.json"
        )

    def test_a_key_with_no_directory_still_gets_a_twin(self):
        assert objectstore.commit_keyed("table.json", "abc123") == "by-commit/abc123/table.json"

    def test_two_commits_name_two_different_twins(self):
        a = objectstore.commit_keyed(KEY, "aaaaaaa")
        b = objectstore.commit_keyed(KEY, "bbbbbbb")
        assert a != b

    def test_the_same_commit_names_the_same_twin_every_time(self):
        # The guard is only a guard if a re-run computes the key it is meant to collide with.
        assert objectstore.commit_keyed(KEY, "abc123") == objectstore.commit_keyed(KEY, "abc123")

    def test_a_twin_is_not_a_sibling_of_the_results_a_prefix_listing_returns(self):
        # D-246: the A3.2 merge listed a task's prefix recursively, read the twins as results
        # and unioned superseded families back into the headline. The segment is what a reader
        # filters on, so it has to be exactly this and has to be in the path.
        twin = objectstore.commit_keyed(KEY, "abc123")
        assert f"/{objectstore.BY_COMMIT}/" in twin

    def test_a_commitless_call_is_a_programming_error_rather_than_a_silent_passthrough(self):
        with pytest.raises(ValueError):
            objectstore.commit_keyed(KEY, "")


class TestPutOnce:
    def test_it_writes_the_stable_key_and_the_twin(self):
        s3 = RecordingS3()
        written = objectstore.put_once(s3, BUCKET, KEY, b"payload", commit="abc123")
        twin = objectstore.commit_keyed(KEY, "abc123")
        assert set(s3.objects) == {KEY, twin}
        assert written == {
            "stable": f"s3://{BUCKET}/{KEY}",
            "by_commit": f"s3://{BUCKET}/{twin}",
        }

    def test_both_copies_carry_the_digest_and_the_commit(self):
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"payload", commit="abc123")
        digest = hashlib.sha256(b"payload").hexdigest()
        for _, meta in s3.objects.values():
            assert meta["sha256"] == digest
            assert meta["commit"] == "abc123"

    def test_caller_metadata_survives_but_cannot_forge_the_digest(self):
        s3 = RecordingS3()
        objectstore.put_once(
            s3, BUCKET, KEY, b"payload", commit="abc123", metadata={"role": "table", "sha256": "x"}
        )
        _, meta = s3.objects[KEY]
        assert meta["role"] == "table"
        assert meta["sha256"] == hashlib.sha256(b"payload").hexdigest()

    def test_two_commits_produce_two_durable_objects(self):
        # X1.7's first Done-when criterion, stated as a test.
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="aaaaaaa")
        objectstore.put_once(s3, BUCKET, KEY, b"second", commit="bbbbbbb")
        assert s3.objects[objectstore.commit_keyed(KEY, "aaaaaaa")][0] == b"first"
        assert s3.objects[objectstore.commit_keyed(KEY, "bbbbbbb")][0] == b"second"

    def test_the_stable_key_follows_the_latest_run(self):
        # Overwriting the stable key is the point of the stable key: readers that know a
        # result by name must find the current one.
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="aaaaaaa")
        objectstore.put_once(s3, BUCKET, KEY, b"second", commit="bbbbbbb")
        assert s3.objects[KEY][0] == b"second"

    def test_a_rerun_at_the_same_commit_reproducing_its_bytes_is_allowed(self):
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"payload", commit="abc123")
        objectstore.put_once(s3, BUCKET, KEY, b"payload", commit="abc123")
        assert s3.objects[KEY][0] == b"payload"

    def test_the_same_commit_producing_different_bytes_is_refused(self):
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="abc123")
        with pytest.raises(objectstore.ObjectStoreError) as caught:
            objectstore.put_once(s3, BUCKET, KEY, b"second", commit="abc123")
        message = str(caught.value)
        assert hashlib.sha256(b"first").hexdigest() in message
        assert hashlib.sha256(b"second").hexdigest() in message
        assert objectstore.commit_keyed(KEY, "abc123") in message

    def test_a_refusal_writes_nothing_at_all(self):
        # Including the stable key. A guard that refuses the twin after replacing the stable
        # copy has destroyed exactly the thing it was asked to protect.
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="abc123")
        before = dict(s3.objects)
        with pytest.raises(objectstore.ObjectStoreError):
            objectstore.put_once(s3, BUCKET, KEY, b"second", commit="abc123")
        assert s3.objects == before

    def test_replace_with_a_reason_is_the_way_past_the_guard(self):
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="abc123")
        objectstore.put_once(
            s3, BUCKET, KEY, b"second", commit="abc123", replace="rebuilt after D-999"
        )
        assert s3.objects[objectstore.commit_keyed(KEY, "abc123")][0] == b"second"

    def test_a_caller_with_no_commit_still_cannot_replace_a_result_silently(self):
        # No commit means no twin to protect, so the guard falls back to the stable key. A
        # pipeline that cannot say which code it ran is the one that should not be overwriting.
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first")
        with pytest.raises(objectstore.ObjectStoreError):
            objectstore.put_once(s3, BUCKET, KEY, b"second")

    def test_a_caller_with_no_commit_writes_no_twin(self):
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first")
        assert set(s3.objects) == {KEY}

    def test_guard_key_none_turns_the_check_off_for_a_caller_that_ran_its_own(self):
        # `amazebio.repro` does exactly this: it checks every output of a run before uploading
        # any of them, so that a three-output run cannot publish two and refuse the third.
        s3 = RecordingS3()
        objectstore.put_once(s3, BUCKET, KEY, b"first", commit="abc123", guard_key=None)
        objectstore.put_once(s3, BUCKET, KEY, b"second", commit="abc123", guard_key=None)
        assert s3.heads == []
        assert s3.objects[KEY][0] == b"second"

    def test_twin_key_overrides_where_the_twin_goes(self):
        # repro anchors `by-commit/` at the run's durable prefix rather than at the key's last
        # directory. Recomputing it here instead would move every twin it has published.
        s3 = RecordingS3()
        written = objectstore.put_once(
            s3,
            BUCKET,
            "corpora/results/a9-9/sub/dir/table.json",
            b"payload",
            commit="abc123",
            twin_key="corpora/results/a9-9/by-commit/abc123/sub/dir/table.json",
        )
        assert written["by_commit"].endswith("by-commit/abc123/sub/dir/table.json")

    def test_an_object_with_no_recorded_digest_does_not_block_a_write(self):
        # Everything written before this guard existed has no `sha256` metadata. Refusing on
        # those would make every pre-existing key permanently unwritable, which is not the ask:
        # the ask is that the same code never silently disagrees with itself.
        s3 = RecordingS3()
        s3.objects[objectstore.commit_keyed(KEY, "abc123")] = (b"old", {})
        objectstore.put_once(s3, BUCKET, KEY, b"new", commit="abc123")
        assert s3.objects[objectstore.commit_keyed(KEY, "abc123")][0] == b"new"


class TestHead:
    def test_a_missing_key_is_none(self):
        s3 = RecordingS3()
        assert objectstore.head(s3, BUCKET, KEY) is None

    def test_a_denial_is_raised_rather_than_read_as_absence(self):
        # The difference matters here more than anywhere: a guard that reads "denied" as "not
        # there" overwrites precisely when it has lost the ability to look.
        class Denying(RecordingS3):
            def head_object(self, Bucket: str, Key: str) -> dict:
                raise _denied()

        with pytest.raises(Exception, match="Access Denied"):
            objectstore.head(Denying(), BUCKET, KEY)

    def test_a_write_does_not_proceed_when_the_guard_cannot_see(self):
        class Denying(RecordingS3):
            def head_object(self, Bucket: str, Key: str) -> dict:
                raise _denied()

        s3 = Denying()
        with pytest.raises(Exception, match="Access Denied"):
            objectstore.put_once(s3, BUCKET, KEY, b"payload", commit="abc123")
        assert s3.objects == {}


ROOT = pathlib.Path(__file__).resolve().parent.parent
#: The one module allowed to construct an S3 client, because it is where the endpoint is pinned.
CLIENT_HOME = ROOT / "src" / "amazebio" / "objectstore.py"


def _s3_client_calls(tree: ast.AST) -> list[int]:
    """Line numbers of `boto3.client("s3", ...)` and `boto3.resource("s3", ...)` calls."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"client", "resource"}:
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and first.value == "s3":
            found.append(node.lineno)
    return found


class TestTheEndpointIsPinnedInOnePlace:
    """A bare S3 client is a half-day outage waiting to be rediscovered, so fail the build.

    `boto3.client("s3", region_name=...)` with no `endpoint_url` resolves to the legacy global
    hostname `s3.amazonaws.com`, outside the egress proxy's allow-and-inject pattern
    `*.us-east-1.amazonaws.com`. The request reaches AWS unsigned and is refused as anonymous,
    with a terse `AccessDenied` carrying no principal — identical in shape to a missing grant,
    and the reason three correct theories about the account were argued past in October. Other
    services are not affected and are deliberately not covered here.
    """

    def test_no_module_outside_objectstore_builds_its_own_s3_client(self):
        offenders = []
        for directory in ("src", "tools"):
            for path in sorted((ROOT / directory).rglob("*.py")):
                if path == CLIENT_HOME:
                    continue
                for line in _s3_client_calls(ast.parse(path.read_text())):
                    offenders.append(f"{path.relative_to(ROOT)}:{line}")
        assert offenders == [], (
            "these build an S3 client directly instead of calling objectstore.client(), "
            "which pins the regional endpoint: " + ", ".join(offenders)
        )

    def test_the_one_allowed_client_pins_the_regional_endpoint(self):
        source = CLIENT_HOME.read_text()
        assert "endpoint_url=S3_ENDPOINT" in source
        assert objectstore.S3_ENDPOINT == "https://s3.us-east-1.amazonaws.com"

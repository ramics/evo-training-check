"""Tests for the UniProtKB release-count launcher.

The instance cannot be inspected once running, and this one spends about three hours and
writes a permanent 182.7 GB object. So the checks that matter all run before launch: that the
payload carries every module and every data file the shipped tool needs, that a dry run writes
nothing, and that the watcher cannot mistake an earlier run's result for this one's.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import pathlib
import sys
from datetime import UTC, datetime, timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "tools" / "ec2_uniprot_count.py"
SHIPPED_TOOL = ROOT / "tools" / "uniprot_release_count.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `dataclasses` resolves a class's annotations through
    # `sys.modules[cls.__module__]`, so a module loaded by spec alone raises an opaque
    # AttributeError the moment it defines a dataclass.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _load(LAUNCHER, "ec2_uniprot_count_under_test")


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from the shipped tool, transitively."""
    src_root = ROOT / "src" / "amazebio"
    seen: set[str] = set()
    queue = [entry]
    while queue:
        path = queue.pop()
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("amazebio"):
                parts = (node.module or "").split(".")
                names = [a.name for a in node.names] if len(parts) == 1 else [parts[1]]
            elif isinstance(node, ast.Import):
                names = [a.name.split(".")[1] for a in node.names if a.name.startswith("amazebio.")]
            for name in names:
                candidate = src_root / f"{name}.py"
                if candidate.exists() and name not in seen:
                    seen.add(name)
                    queue.append(candidate)
    return seen


def test_payload_ships_every_module_the_tool_imports() -> None:
    needed = {f"src/amazebio/{m}.py" for m in _first_party_closure(SHIPPED_TOOL)}
    missing = needed - set(tool.PAYLOAD_MODULES)
    assert not missing, f"PAYLOAD_MODULES is short: {sorted(missing)}"


def test_payload_ships_the_data_files_no_closure_can_see() -> None:
    """The captures and the reading table are data, not imports."""
    for rel in tool.payload_data_files():
        assert (ROOT / rel).exists(), rel


def test_the_payload_builds_and_contains_everything_it_lists() -> None:
    import io
    import tarfile

    blob = tool.build_payload(ROOT)
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        names = set(tar.getnames())
    for rel in (*tool.PAYLOAD_MODULES, *tool.payload_data_files()):
        assert rel in names, rel


def test_user_data_arms_the_timer_and_cancels_it_before_shutting_down() -> None:
    script = tool.USER_DATA
    assert "shutdown -h +{hard_stop_minutes}" in script
    # Checked inside `die` rather than over the whole script: the comment above it quotes
    # both commands, so a naive search finds the prose and passes whatever the code does.
    die = script[script.index("die() {{") : script.index("dnf install")]
    assert die.index("shutdown -c") < die.index("shutdown -h now")
    assert "systemctl --no-block poweroff" in die and "halt -p" in die
    assert "python3.12" in script, "AL2023 ships 3.9 as python3 and this needs 3.12"
    assert "--check-inputs" in script, "resolve the taxa before reading 182.7 GB"


def test_a_volume_over_the_policy_cap_is_refused_before_launch() -> None:
    with pytest.raises(SystemExit, match="200 GB"):
        tool.main(["--s3-uri", "s3://b/corpora", "--volume-size", "300"])


def test_a_dirty_tree_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool._sim, "_git_head", lambda root: ("abc123def456", True))
    with pytest.raises(SystemExit, match="dirty tree"):
        tool.main(["--s3-uri", "s3://b/corpora"])


def test_a_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dry run that uploads leaves a permanent object in a bucket with no DeleteObject."""
    puts: list[str] = []

    class FakeS3:
        def put_object(self, **kw: object) -> None:
            puts.append(str(kw.get("Key")))

    class FakeEc2:
        def describe_images(self, **kw: object) -> dict:
            return {"Images": [{"ImageId": "ami-1", "CreationDate": "2026-01-01"}]}

        def run_instances(self, **kw: object) -> dict:
            assert kw.get("DryRun") is True
            raise RuntimeError("An error occurred (DryRunOperation) when calling RunInstances")

    import boto3

    monkeypatch.setattr(boto3, "client", lambda svc, **kw: FakeS3() if svc == "s3" else FakeEc2())
    monkeypatch.setattr(tool._sim, "_git_head", lambda root: ("abc123def456", False))
    assert tool.main(["--s3-uri", "s3://b/corpora", "--dry-run"]) == 0
    assert puts == [], f"a dry run wrote {puts}"


def test_a_previous_runs_result_does_not_end_this_one() -> None:
    launched = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    stale = {
        "Key": "corpora/results/a1-8/uniprotkb-release-count.json",
        "Size": 900,
        "LastModified": launched - timedelta(hours=6),
    }

    class FakeS3:
        def list_objects_v2(self, **kw: object) -> dict:
            return {"Contents": [stale]}

    class FakeEc2:
        def get_console_output(self, **kw: object) -> dict:
            return {"Output": ""}

    args = argparse.Namespace(watch_seconds=0, max_watch_minutes=0.001)
    assert tool._watch(FakeEc2(), FakeS3(), "i-1", "b", "corpora", args, launched) == 1


def test_this_runs_result_is_recognised() -> None:
    launched = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    fresh = {
        "Key": "corpora/results/a1-8/uniprotkb-release-count.json",
        "Size": 900,
        "LastModified": launched + timedelta(hours=3),
    }

    class FakeS3:
        def list_objects_v2(self, **kw: object) -> dict:
            return {"Contents": [fresh]}

    class FakeEc2:
        def get_console_output(self, **kw: object) -> dict:
            return {"Output": ""}

    args = argparse.Namespace(watch_seconds=0, max_watch_minutes=1)
    assert tool._watch(FakeEc2(), FakeS3(), "i-1", "b", "corpora", args, launched) == 0


def test_the_staged_key_is_fixed_rather_than_derived() -> None:
    """The bucket has no DeleteObject, so the key is reviewed before it is written once."""
    shipped = _load(SHIPPED_TOOL, "uniprot_release_count_for_key_test")
    assert shipped.STAGED_KEY == "uniprotkb/2023_02/knowledgebase2023_02.tar.gz"


# --- the instance path, rehearsed locally -------------------------------------------------


def _extract_payload(dest: pathlib.Path) -> pathlib.Path:
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(tool.build_payload(ROOT))) as tar:
        tar.extractall(dest, filter="data")
    return dest


def test_the_user_data_precheck_actually_runs_against_the_shipped_payload(
    tmp_path: pathlib.Path,
) -> None:
    """The precheck is a program, and nothing executed it before an instance did.

    This is the failure that cost launch i-0a5252d10b65d2a8d on 2026-10-18. The snippet
    loaded the tool by spec without registering it in `sys.modules`, so the tool's first
    dataclass raised `AttributeError` from inside `dataclasses`; `die` then reported it as
    "PAYLOAD_MODULES is short", which it was not. The unit test above ran a *corrected* copy
    of the same snippet, so it passed while the shipped one could not work.

    So the snippet is extracted from `USER_DATA` verbatim and run against the extracted
    payload, in a separate interpreter with no repository on the path.
    """
    import subprocess

    script = tool.USER_DATA
    body = script.split("<<'PRECHECK'", 1)[1].split("\nPRECHECK", 1)[0]
    body = body.split("\n", 1)[1]  # drop the remainder of the `|| die ...` line
    root = _extract_payload(tmp_path)
    assert not (root / "pyproject.toml").exists(), "the instance has no repository"

    done = subprocess.run(
        [sys.executable, "-I", "-"],
        input=body,
        text=True,
        capture_output=True,
        cwd=root,
    )
    assert done.returncode == 0, f"the shipped precheck fails:\n{done.stderr}"
    assert "payload imports cleanly" in done.stdout


def test_the_rendered_user_data_is_valid_bash() -> None:
    """A bash program assembled by str.format, with {{ }} escaping, run as root once."""
    import subprocess

    rendered = tool.USER_DATA.format(
        hard_stop_minutes=480,
        bucket="b",
        prefix="corpora",
        code_key="corpora/code/x.tar.gz",
        region="us-east-1",
        taxdump_url="https://example.invalid/taxdmp.zip",
        taxdump_sha256="0" * 64,
        stage_flag="--stage",
        reading_flags="",
        commit="abc123",
    )
    done = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr
    # Shell braces are legitimate here (`die() {`, `${2:-1}`); an unfilled `str.format`
    # field is not, and would reach the instance as a literal.
    import re

    leftover = re.findall(r"(?<![$\w]){([a-z_][a-z0-9_]*)}", rendered)
    assert not leftover, f"unsubstituted format fields: {sorted(set(leftover))}"

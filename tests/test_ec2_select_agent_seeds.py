"""Tests for A1.8's seed-pass launcher.

An instance here cannot be inspected once running: no shell, no SSH, no SSM, and a
best-effort console. So everything that can be checked before launch has to be, and the
things worth checking are the ones AGENTS.md records as having cost real launches — a short
payload, a shutdown that never fires, a missing tag that reads as a permissions error.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "tools" / "ec2_select_agent_seeds.py"
SHIPPED_TOOL = ROOT / "tools" / "select_agent_seeds.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load(LAUNCHER, "ec2_select_agent_seeds_under_test")


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from a shipped tool, transitively."""
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


# --- the payload --------------------------------------------------------------------------


def test_payload_ships_every_module_the_tool_imports() -> None:
    """Derived rather than trusted: a hand-kept list cost A1.6 two launches."""
    needed = {f"src/amazebio/{m}.py" for m in _first_party_closure(SHIPPED_TOOL)}
    missing = needed - set(tool.PAYLOAD_MODULES)
    assert not missing, f"PAYLOAD_MODULES is short: {sorted(missing)}"


def test_payload_ships_every_data_file_the_tool_reads() -> None:
    """The failure mode the import closure cannot see.

    The three CFR captures and the reading table are data, not imports, so no closure
    derivation will ever notice them missing — and the instance dies the same way, a minute
    in, with the hour of corpus reading wasted. The launcher asks the tool what it reads.
    """
    shipped = _load(SHIPPED_TOOL, "select_agent_seeds_for_closure_test")
    assert set(tool.payload_data_files()) == set(shipped.required_data_files())
    for rel in tool.payload_data_files():
        assert (ROOT / rel).exists(), rel


def test_the_data_files_cover_every_parsed_section() -> None:
    """Adding a CFR part must not be able to fail to ship it."""
    shipped = _load(SHIPPED_TOOL, "select_agent_seeds_for_section_test")
    for name in shipped.SECTION_FILES.values():
        assert f"policies/captures/{name}" in tool.payload_data_files()


def test_everything_in_the_payload_exists() -> None:
    for rel in (*tool.PAYLOAD_MODULES, *tool.payload_data_files()):
        assert (ROOT / rel).exists(), rel


def test_the_payload_tar_contains_both_halves() -> None:
    import io
    import tarfile

    blob = tool.build_payload(ROOT)
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        names = set(tar.getnames())
    assert "tools/select_agent_seeds.py" in names
    assert "src/amazebio/selectagents.py" in names
    assert any(n.startswith("policies/captures/") for n in names)
    assert "policies/specs/select-agents-2024-06-01.json" in names


# --- the shutdown paths, which are what a lost launch is made of --------------------------


def test_user_data_arms_the_dead_mans_switch_before_anything_fallible() -> None:
    data = _user_data()
    armed = data.index("shutdown -h +")
    for fallible in ("dnf install", "aws s3 cp", "curl -sSL"):
        assert armed < data.index(fallible), f"{fallible} runs before the timer is armed"


def test_die_cancels_the_pending_timer_before_shutting_down() -> None:
    """`shutdown -h now` does nothing while a timer is pending, which cost most of a day."""
    data = _user_data()
    die = data[data.index("die() {") : data.index("dnf install")]
    assert "shutdown -c" in die
    assert die.index("shutdown -c") < die.index("shutdown -h now")
    assert "systemctl --no-block poweroff" in die
    assert "halt -p" in die


def test_every_failure_path_goes_through_die() -> None:
    """A failure that does not shut down burns the whole window looking like a long pass."""
    data = _user_data()
    for guard in ("no python 3.11+", "taxdump checksum mismatch", "cannot import"):
        assert guard in data
    assert data.rstrip().endswith('die "run complete" 0')


def test_the_interpreter_is_named_not_assumed() -> None:
    """Amazon Linux 2023 ships 3.9 as python3; `datetime.UTC` alone needs 3.11+."""
    data = _user_data()
    assert "python3.12" in data
    assert "for cand in python3.12" in data


def test_check_inputs_runs_before_the_corpus_pass() -> None:
    """A second here against an hour and a launch there."""
    data = _user_data()
    check = data.index("--check-inputs")
    pass_start = data.index("--upload-results")
    assert check < pass_start
    assert "the payload's data files are short" in data


def test_the_payload_is_imported_before_the_pass() -> None:
    data = _user_data()
    assert data.index("PRECHECK") < data.index("--upload-results")
    assert "PAYLOAD_MODULES is short" in data


def test_the_commit_is_carried_in() -> None:
    """The instance has no checkout, so a manifest written there is otherwise untraceable."""
    assert "--code-commit" in _user_data()


def _user_data() -> str:
    from amazebio import seeds

    return tool.USER_DATA.format(
        hard_stop_minutes=180,
        bucket="b",
        prefix="p",
        code_key="p/code/x.tar.gz",
        region="us-east-1",
        taxdump_url=seeds.TAXDUMP_2023_04.url,
        taxdump_sha256=seeds.TAXDUMP_2023_04.sha256,
        release="2023_02",
        tier="uniref100",
        reading_flags="",
        workers=7,
        commit="abc123",
    )


# --- the launch request -------------------------------------------------------------------


def test_a_volume_over_the_policy_cap_is_refused_before_launch() -> None:
    with pytest.raises(SystemExit, match="200 GB"):
        tool.main(["--s3-uri", "s3://b/p", "--volume-size", "300"])


def test_a_non_s3_uri_is_refused() -> None:
    with pytest.raises(SystemExit, match="s3:// uri"):
        tool.main(["--s3-uri", "/local/path"])


def test_the_reading_flags_pass_the_sensitivity_through() -> None:
    import argparse

    assert tool.reading_flags(argparse.Namespace(toxin_producers=False, alternatives=False)) == ""
    both = tool.reading_flags(argparse.Namespace(toxin_producers=True, alternatives=True))
    assert "--toxin-producers" in both and "--alternatives" in both


def test_print_user_data_needs_no_credentials_and_no_clean_tree() -> None:
    """The only way to read the script before it is the only thing that can be read."""
    assert tool.main(["--s3-uri", "s3://b/p", "--print-user-data"]) == 0


def test_a_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dry run that uploads leaves an object behind in a bucket with no DeleteObject.

    It did, until it was run: the payload upload sat above the dry-run branch, so the one mode
    whose whole point is to change nothing wrote a permanent object first.
    """
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


def test_a_previous_runs_artefacts_do_not_end_this_one() -> None:
    """The results prefix is stable across runs, so presence alone is not completion.

    This killed the first attributed re-run ninety seconds in: the watcher listed the prefix,
    found the earlier pass's `seed-counts-` object still sitting there, declared the run
    finished and terminated the instance — then printed the *old* reconciliation as if it
    were the new one. Nothing about that output says it is stale, which is what makes it
    worth a test rather than a note. A2.4 hit the same shape with its heartbeat.
    """
    from datetime import UTC, datetime, timedelta

    launched = datetime(2026, 10, 17, 22, 0, tzinfo=UTC)
    stale = {
        "Key": "corpora/results/a1-8/seed-counts-2023_02-uniref100.json",
        "Size": 2739,
        "LastModified": launched - timedelta(hours=4),
    }

    class FakeS3:
        def list_objects_v2(self, **kw: object) -> dict:
            return {"Contents": [stale]}

    class FakeEc2:
        def get_console_output(self, **kw: object) -> dict:
            return {"Output": ""}

    # The watch window closes without the stale object ever counting, so this returns 1.
    # The test below is the same object and the same fakes with a later `LastModified`, and
    # returns 0 — so the pair isolates the timestamp as the thing that decides, which a
    # single test asserting "not finished" could not.
    args = argparse.Namespace(watch_seconds=0, max_watch_minutes=0.001)
    assert tool._watch(FakeEc2(), FakeS3(), "i-1", "b", "corpora", args, launched) == 1


def test_an_artefact_written_after_launch_is_this_runs() -> None:
    """The other half: the filter must not reject the run's own output."""
    from datetime import UTC, datetime, timedelta

    launched = datetime(2026, 10, 17, 22, 0, tzinfo=UTC)
    fresh = {
        "Key": "corpora/results/a1-8/seed-counts-2023_02-uniref100.json",
        "Size": 2739,
        "LastModified": launched + timedelta(minutes=55),
    }

    class FakeS3:
        def list_objects_v2(self, **kw: object) -> dict:
            return {"Contents": [fresh]}

        def get_object(self, **kw: object) -> dict:
            body = json.dumps(
                {"counts": {"clusters": 10, "seeded": 3}, "reconciliation": None}
            ).encode()
            return {"Body": io.BytesIO(body)}

    class FakeEc2:
        def get_console_output(self, **kw: object) -> dict:
            return {"Output": ""}

    args = argparse.Namespace(watch_seconds=0, max_watch_minutes=1)
    assert tool._watch(FakeEc2(), FakeS3(), "i-1", "b", "corpora", args, launched) == 0


def test_the_user_data_precheck_actually_runs_against_the_shipped_payload(
    tmp_path: pathlib.Path,
) -> None:
    """Run the precheck snippet verbatim, not a corrected copy of it.

    The sibling launcher's precheck loaded its tool by spec without registering it in
    `sys.modules`; the tool defined a dataclass, so the import raised from inside
    `dataclasses` and `die` reported it as a short payload. It cost a launch on 2026-10-18.
    The unit tests passed throughout, because they ran their own fixed version of the
    snippet. This one extracts the real thing and runs it against the real payload.
    """
    import io
    import subprocess
    import sys
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(tool.build_payload(ROOT))) as tar:
        tar.extractall(tmp_path, filter="data")
    assert not (tmp_path / "pyproject.toml").exists(), "the instance has no repository"

    body = tool.USER_DATA.split("<<'PRECHECK'", 1)[1].split("\nPRECHECK", 1)[0]
    body = body.split("\n", 1)[1]
    done = subprocess.run(
        [sys.executable, "-I", "-"], input=body, text=True, capture_output=True, cwd=tmp_path
    )
    assert done.returncode == 0, f"the shipped precheck fails:\n{done.stderr}"
    assert "payload imports cleanly" in done.stdout

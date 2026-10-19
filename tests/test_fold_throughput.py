"""Tests for A2.2's 3Di throughput measurement.

The one that matters is `test_a_long_rung_reports_while_it_runs`. The first version of this tool
published its heartbeat *between* rungs, so the 32-minute CPU rung was 32 minutes of silence —
half of what AGENTS.md requires, and precisely the condition it warns about: from outside, with
no shell on the instance and a console that cannot be trusted to be fresh, a rung still working
and a rung whose process died look identical. Two launches were lost to that reading on
2026-10-16. A test is the only thing that notices if the tick is refactored back out.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load("fold_throughput", "tools/fold_throughput.py")


def _fake_foldseek(tmp_path: Path, *, sleep_s: float, rc: int = 0, stderr: str = "") -> Path:
    """A stand-in for the binary: sleeps, writes output, exits with `rc`."""
    path = tmp_path / "fake-foldseek"
    path.write_text(
        "#!/bin/sh\n"
        f"sleep {sleep_s}\n"
        'echo "createdb done"\n'
        f'>&2 printf "%s" "{stderr}"\n'
        f"exit {rc}\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_a_long_rung_reports_while_it_runs(tool, tmp_path):
    """The regression: ticks must arrive during the rung, not only after it."""
    faa = tmp_path / "q.faa"
    faa.write_text(">a\nMKV\n")
    ticks: list[float] = []
    got = tool.time_createdb(
        str(_fake_foldseek(tmp_path, sleep_s=1.0)),
        faa,
        tmp_path / "model",
        tmp_path,
        gpu=False,
        threads=1,
        on_tick=ticks.append,
        tick_interval_s=0.1,
        poll_interval_s=0.02,
    )
    assert got["ok"] is True
    assert len(ticks) >= 3, f"expected several mid-rung ticks, got {ticks}"
    assert ticks == sorted(ticks), "elapsed time must be reported monotonically"
    assert all(t <= got["seconds"] + 0.5 for t in ticks)


def test_a_rung_with_no_tick_callback_still_runs(tool, tmp_path):
    """The heartbeat is a reporting channel, never a dependency of the measurement."""
    faa = tmp_path / "q.faa"
    faa.write_text(">a\nMKV\n")
    got = tool.time_createdb(
        str(_fake_foldseek(tmp_path, sleep_s=0.05)),
        faa,
        tmp_path / "model",
        tmp_path,
        gpu=False,
        threads=1,
        tick_interval_s=0.01,
        poll_interval_s=0.01,
    )
    assert got["ok"] is True
    assert got["seconds"] > 0


def test_a_failing_rung_is_not_ok_and_keeps_its_stderr(tool, tmp_path):
    faa = tmp_path / "q.faa"
    faa.write_text(">a\nMKV\n")
    got = tool.time_createdb(
        str(_fake_foldseek(tmp_path, sleep_s=0.02, rc=3, stderr="boom")),
        faa,
        tmp_path / "model",
        tmp_path,
        gpu=False,
        threads=1,
        poll_interval_s=0.01,
    )
    assert got["ok"] is False
    assert got["returncode"] == 3
    assert "boom" in got["stderr_tail"]


def test_a_gpu_rung_that_fell_back_to_cpu_is_not_ok(tool, tmp_path):
    """A GPU figure measured on the CPU looks right, which is what makes it dangerous."""
    faa = tmp_path / "q.faa"
    faa.write_text(">a\nMKV\n")
    got = tool.time_createdb(
        str(_fake_foldseek(tmp_path, sleep_s=0.02, stderr=tool.NO_GPU_MARKER)),
        faa,
        tmp_path / "model",
        tmp_path,
        gpu=True,
        threads=1,
        poll_interval_s=0.01,
    )
    assert got["fell_back_to_cpu"] is True
    assert got["ok"] is False


def test_output_goes_to_files_not_pipes(tool, tmp_path):
    """A pipe nobody drains can deadlock the child, and the child is the thing being timed."""
    faa = tmp_path / "q.faa"
    faa.write_text(">a\nMKV\n")
    noisy = "x" * 200_000
    got = tool.time_createdb(
        str(_fake_foldseek(tmp_path, sleep_s=0.02, stderr=noisy)),
        faa,
        tmp_path / "model",
        tmp_path,
        gpu=False,
        threads=1,
        poll_interval_s=0.01,
    )
    assert got["ok"] is True
    assert (tmp_path / "createdb-cpu.err").stat().st_size >= 200_000


def test_heartbeat_never_fails_the_run_it_reports_on(tool):
    """There is no shell on the instance: a failed upload must not take the measurement with it."""

    class Broken:
        def put_object(self, **kw):
            raise RuntimeError("no network")

    tool.heartbeat(Broken(), "s3://bucket/prefix", "p.json", {"stage": "timing"})


def test_heartbeat_is_a_noop_without_a_destination(tool):
    tool.heartbeat(None, None, "p.json", {"stage": "timing"})


def test_heartbeat_stamps_and_serialises_the_body(tool):
    seen: dict[str, object] = {}

    class Recorder:
        def put_object(self, **kw):
            seen.update(kw)

    tool.heartbeat(Recorder(), "s3://bucket/pre/fix", "p.json", {"stage": "timing"})
    assert seen["Bucket"] == "bucket"
    assert seen["Key"] == "pre/fix/p.json"
    body = json.loads(seen["Body"].decode())
    assert body["stage"] == "timing"
    assert body["written_at"].endswith("Z")


@pytest.mark.skipif(os.name != "posix", reason="the fake binary is a shell script")
def test_the_cpu_ladder_is_shorter_than_the_gpu_one(tool):
    """D-163's rate puts the largest GPU rung at ~20 hours on CPU; no window holds that."""
    assert max(tool.CPU_LADDER) < max(tool.LADDER)
    assert set(tool.CPU_LADDER) <= set(tool.LADDER), "rungs must be nested to be comparable"

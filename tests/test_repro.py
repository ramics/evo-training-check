"""Tests for amazebio.repro.

The strictness tests matter more than the happy path. `AGENTS.md` enforces its
commitments in code, so a regression that quietly allows a parameter to be declared
after results exist, or an artefact to be produced from uncommitted code, would turn
the manifest from evidence into decoration.
"""

from __future__ import annotations

import json
import random
import subprocess

import pytest

from amazebio.repro import (
    MANIFEST_NAME,
    ReproError,
    RunManifest,
    git_state,
    run,
    set_seeds,
    sha256_file,
    tool_version,
)


def _git_repo(path):
    """A throwaway git repo with one commit, so git_state has something to report."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "seed.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    return path


class TestSha256File:
    def test_matches_known_digest(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"abc")
        assert sha256_file(f) == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_streams_file_larger_than_chunk(self, tmp_path):
        f = tmp_path / "big.bin"
        f.write_bytes(b"\x00" * (1 << 21))
        assert len(sha256_file(f)) == 64


class TestSetSeeds:
    def test_is_deterministic(self):
        set_seeds(123)
        first = [random.random() for _ in range(5)]
        set_seeds(123)
        assert [random.random() for _ in range(5)] == first

    def test_different_seeds_differ(self):
        set_seeds(1)
        a = random.random()
        set_seeds(2)
        assert random.random() != a

    def test_returns_the_seed(self):
        assert set_seeds(77) == 77


class TestGitState:
    def test_reports_commit_and_cleanliness(self, tmp_path):
        repo = _git_repo(tmp_path)
        state = git_state(repo)
        assert state["available"] is True
        assert len(state["commit"]) == 40
        assert state["dirty"] is False
        assert state["dirty_paths"] == []

    def test_reports_dirty_paths(self, tmp_path):
        repo = _git_repo(tmp_path)
        (repo / "new.txt").write_text("y\n")
        state = git_state(repo)
        assert state["dirty"] is True
        assert "new.txt" in state["dirty_paths"]

    def test_marks_unavailable_outside_a_repo(self, tmp_path):
        assert git_state(tmp_path)["available"] is False


class TestToolVersion:
    def test_captures_first_line(self):
        assert tool_version(["python3", "-V"]).startswith("Python")

    def test_returns_none_for_missing_tool(self):
        assert tool_version(["definitely-not-a-real-tool-xyz", "--version"]) is None


class TestParameterOrdering:
    """The ordering constraint is the commitment; see the module docstring."""

    def test_parameter_before_output_is_fine(self, tmp_path):
        m = RunManifest(task="T")
        m.parameter("threshold", 50.0)
        f = tmp_path / "out.txt"
        f.write_text("r\n")
        m.output_file(f)
        assert m.parameters == {"threshold": 50.0}

    def test_parameter_after_output_is_refused(self, tmp_path):
        m = RunManifest(task="T")
        f = tmp_path / "out.txt"
        f.write_text("r\n")
        m.output_file(f)
        with pytest.raises(ReproError, match="before results are inspected"):
            m.parameter("threshold", 50.0)

    def test_redeclaring_with_a_different_value_is_refused(self):
        m = RunManifest(task="T")
        m.parameter("threshold", 50.0)
        with pytest.raises(ReproError, match="redeclared"):
            m.parameter("threshold", 60.0)

    def test_redeclaring_the_same_value_is_allowed(self):
        m = RunManifest(task="T")
        m.parameter("threshold", 50.0)
        m.parameter("threshold", 50.0)
        assert m.parameters["threshold"] == 50.0


class TestManifestContents:
    def test_records_inputs_outputs_and_notes(self, tmp_path):
        src = tmp_path / "in.txt"
        src.write_bytes(b"abc")
        out = tmp_path / "out.txt"
        out.write_bytes(b"def")

        m = RunManifest(task="A1.4", seed=7, outdir=tmp_path)
        m.parameter("k", 3)
        m.input_file(src, role="corpus")
        m.output_file(out, role="result")
        m.tool("python", ["python3", "-V"])
        m.note("proxy version used; see DECISIONS.md")

        d = m.to_dict()
        assert d["task"] == "A1.4"
        assert d["seed"] == 7
        assert d["inputs"][0]["sha256"] == sha256_file(src)
        assert d["inputs"][0]["role"] == "corpus"
        assert d["outputs"][0]["bytes"] == 3
        assert d["tools"]["python"].startswith("Python")
        assert d["notes"] == ["proxy version used; see DECISIONS.md"]
        assert d["environment"]["python"]

    def test_write_defaults_to_outdir(self, tmp_path):
        m = RunManifest(task="T", outdir=tmp_path)
        written = m.write()
        assert written == tmp_path / MANIFEST_NAME
        assert json.loads(written.read_text())["task"] == "T"

    def test_write_without_outdir_needs_explicit_path(self):
        with pytest.raises(ReproError, match="outdir"):
            RunManifest(task="T").write()

    def test_input_and_output_file_return_the_path(self, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("z\n")
        m = RunManifest(task="T")
        assert m.input_file(f) == f
        assert m.output_file(f) == f


class TestRunBlock:
    def test_writes_manifest_on_success(self, tmp_path):
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        with run("A1.4", seed=42, outdir=outdir, repo=repo) as m:
            result = outdir / "r.txt"
            result.write_text("ok\n")
            m.output_file(result)

        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        assert manifest["seed"] == 42
        assert manifest["git"]["dirty"] is False
        assert manifest["finished_at"]
        assert manifest["outputs"][0]["path"].endswith("r.txt")

    def test_refuses_a_dirty_tree(self, tmp_path):
        repo = _git_repo(tmp_path)
        (repo / "uncommitted.txt").write_text("y\n")
        with (
            pytest.raises(ReproError, match="dirty git tree"),
            run("A1.4", seed=1, outdir=repo / "out", repo=repo),
        ):
            pass

    def test_allow_dirty_opt_out(self, tmp_path):
        repo = _git_repo(tmp_path)
        (repo / "uncommitted.txt").write_text("y\n")
        with run("A1.4", seed=1, outdir=repo / "out", allow_dirty=True, repo=repo) as m:
            assert m.git["dirty"] is True

    def test_writes_manifest_even_when_the_body_raises(self, tmp_path):
        repo = _git_repo(tmp_path)
        outdir = repo / "out"
        with (
            pytest.raises(ValueError, match="boom"),
            run("A1.4", seed=1, outdir=outdir, repo=repo) as m,
        ):
            m.note("failed partway")
            raise ValueError("boom")
        # A failed run still leaves evidence it happened, which is the point.
        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        assert manifest["notes"] == ["failed partway"]

    def test_seeds_rngs(self, tmp_path):
        repo = _git_repo(tmp_path)
        with run("T", seed=99, repo=repo):
            first = random.random()
        with run("T", seed=99, repo=repo):
            assert random.random() == first

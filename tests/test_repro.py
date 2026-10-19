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

    def test_reports_a_modified_tracked_path_in_full(self, tmp_path):
        """The case a fixed `line[3:]` slice got wrong, and the untracked case hid.

        A modified-yet-unstaged file's porcelain line begins with a space, and the captured
        output is stripped as a whole, so the first one arrives a character short: the
        dirty-tree refusal named "ixi.lock" for `pixi.lock` and "ests/..." for `tests/...`.
        A refusal that names a file nobody can find is worse than no detail at all.
        """
        repo = _git_repo(tmp_path)
        tracked = next(p for p in repo.iterdir() if p.is_file() and p.name != ".gitignore")
        tracked.write_text("changed\n")
        state = git_state(repo)
        assert state["dirty"] is True
        assert tracked.name in state["dirty_paths"], state["dirty_paths"]

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
        with run(
            "A1.4",
            seed=42,
            outdir=outdir,
            repo=repo,
            durable_exempt="unit test; nothing to persist",
        ) as m:
            result = outdir / "r.txt"
            result.write_text("ok\n")
            m.output_file(result)

        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        assert manifest["seed"] == 42
        assert manifest["git"]["dirty"] is False
        assert manifest["finished_at"]
        assert manifest["outputs"][0]["path"].endswith("r.txt")
        assert manifest["durable_exempt"] == "unit test; nothing to persist"

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


def test_two_runs_sharing_a_directory_keep_separate_manifests(tmp_path):
    """A1.5 ran two staging passes into one directory and the second would have
    overwritten the first's provenance. A manifest that can be silently replaced is
    not provenance, so the filename is settable."""
    from amazebio.repro import run

    with run("A1.5", outdir=tmp_path, allow_dirty=True) as first:
        first.parameter("which", "uniref")
    with run("A1.5", outdir=tmp_path, allow_dirty=True, manifest_name="run-mgnify.json") as second:
        second.parameter("which", "mgnify")

    import json

    assert json.loads((tmp_path / "run.json").read_text())["parameters"]["which"] == "uniref"
    assert json.loads((tmp_path / "run-mgnify.json").read_text())["parameters"]["which"] == "mgnify"


class TestDurability:
    """The guard added after the 2026-10-19 audit (D-188).

    Nine finished tasks had written their results only to `artifacts/`, which is git-ignored,
    and the container that held them was reclaimed — A2.1's deepened profile pass and A4.2's
    taxonomy benchmark among them. Every task whose tool uploaded was intact. The figures
    survived in task files and the decisions log, which is exactly what "artefacts before
    prose" exists to stop a write-up relying on.

    So these tests pin the one thing that makes it structural rather than a convention: a run
    that produces a local output and names nowhere for it to live **fails**.
    """

    def test_a_local_output_with_no_durable_destination_is_refused(self, tmp_path):
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        with (
            pytest.raises(ReproError, match="named no durable destination"),
            run("A9.9", outdir=outdir, repo=repo) as m,
        ):
            result = outdir / "r.txt"
            result.write_text("ok\n")
            m.output_file(result)

    def test_the_refusal_names_the_two_ways_out(self, tmp_path):
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        with pytest.raises(ReproError) as caught, run("A9.9", outdir=outdir, repo=repo) as m:
            (outdir / "r.txt").write_text("ok\n")
            m.output_file(outdir / "r.txt")
        message = str(caught.value)
        assert "durable=" in message and "durable_exempt=" in message
        assert "D-188" in message

    def test_a_run_with_no_outputs_needs_no_destination(self, tmp_path):
        """A probe or a dry run produces nothing to lose, and must not be made harder."""
        repo = _git_repo(tmp_path)
        with run("A9.9", outdir=repo / "artifacts" / "t", repo=repo) as m:
            m.parameter("threshold", 1)
        assert m.durable is None

    def test_an_object_output_alone_needs_no_destination(self, tmp_path):
        """A run that wrote straight to object storage is already durable."""
        repo = _git_repo(tmp_path)
        with run("A9.9", outdir=repo / "artifacts" / "t", repo=repo) as m:
            m.output_object("s3://bucket/key", bytes=3)
        assert m.uploaded == {}

    def test_a_failing_run_is_not_masked_by_the_guard(self, tmp_path):
        """The body's exception is the real failure; the guard must not replace it."""
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        with (
            pytest.raises(ValueError, match="the real problem"),
            run("A9.9", outdir=outdir, repo=repo) as m,
        ):
            (outdir / "r.txt").write_text("ok\n")
            m.output_file(outdir / "r.txt")
            raise ValueError("the real problem")

    def test_durable_and_exempt_together_are_refused(self, tmp_path):
        repo = _git_repo(tmp_path)
        with (
            pytest.raises(ReproError, match="not both"),
            run(
                "A9.9",
                outdir=repo / "artifacts" / "t",
                repo=repo,
                durable="s3://b/p",
                durable_exempt="why",
            ),
        ):
            pass

    def test_outputs_are_uploaded_and_recorded_as_uris(self, tmp_path):
        """The upload is what makes the result survive, and `run.json` has to point at it —
        a durable copy nobody can find is not a durable copy."""
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        puts = {}

        class FakeClient:
            def put_object(self, *, Bucket, Key, Body):
                puts[f"s3://{Bucket}/{Key}"] = Body

        with run(
            "A9.9",
            outdir=outdir,
            repo=repo,
            durable="s3://corpora-bucket/corpora/results/a9-9",
            uploader=FakeClient(),
        ) as m:
            (outdir / "table.json").write_text('{"x": 1}\n')
            m.output_file(outdir / "table.json")
            nested = outdir / "sub"
            nested.mkdir()
            (nested / "rows.jsonl").write_text('{"y": 2}\n')
            m.output_file(nested / "rows.jsonl")

        assert "s3://corpora-bucket/corpora/results/a9-9/table.json" in puts
        # The key keeps the path relative to outdir, so a nested layout survives the copy.
        assert "s3://corpora-bucket/corpora/results/a9-9/sub/rows.jsonl" in puts
        # run.json itself is uploaded too: outputs without their provenance are not citable.
        assert "s3://corpora-bucket/corpora/results/a9-9/run.json" in puts

        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        assert manifest["durable"] == "s3://corpora-bucket/corpora/results/a9-9"
        for entry in manifest["outputs"]:
            assert entry["durable_uri"].startswith("s3://corpora-bucket/")

    def test_a_non_s3_destination_is_refused(self, tmp_path):
        repo = _git_repo(tmp_path)
        outdir = repo / "artifacts" / "t"
        with (
            pytest.raises(ReproError, match="s3:// URI"),
            run("A9.9", outdir=outdir, repo=repo, durable="/mnt/somewhere") as m,
        ):
            (outdir / "r.txt").write_text("ok\n")
            m.output_file(outdir / "r.txt")


#: Every `run(...)` call site in `tools/` that claims `durable_exempt`, with the task that
#: owns converting it. This list may **shrink** but must not grow: a new tool that writes a
#: result belongs in object storage, and the audit behind D-188 happened because nothing made
#: the local-only default visible. A legitimately exempt new tool goes here with a reason in
#: the same commit, so adding one is a deliberate, reviewed act rather than a default.
EXEMPT_CALL_SITES: set[str] = set()


def test_no_tool_silently_writes_results_only_locally():
    """A greppable inventory of exemptions, so the default cannot drift back.

    This does not re-litigate each tool: it asserts that the set of tools claiming an
    exemption is the set we wrote down. A tool added with `durable_exempt` and no entry here
    fails, which is the moment to ask whether its results are really disposable.
    """
    import pathlib
    import re

    tools = pathlib.Path(__file__).resolve().parent.parent / "tools"
    claiming = {
        path.name
        for path in sorted(tools.glob("*.py"))
        if re.search(r"durable_exempt\s*=", path.read_text())
    }
    assert claiming == EXEMPT_CALL_SITES, (
        "tools claiming durable_exempt have changed. Added one? Put it in EXEMPT_CALL_SITES "
        "with a reason, or give it durable= instead. Removed one? Delete its entry."
    )

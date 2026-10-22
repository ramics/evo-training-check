"""Tests for amazebio.repro.

The strictness tests matter more than the happy path. `AGENTS.md` enforces its
commitments in code, so a regression that quietly allows a parameter to be declared
after results exist, or an artefact to be produced from uncommitted code, would turn
the manifest from evidence into decoration.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
from typing import ClassVar

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


class _NotFound(Exception):
    """What botocore raises for a `head_object` on a key that is not there."""

    response: ClassVar[dict] = {
        "Error": {"Code": "404"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


def _missing():
    return _NotFound()


class Store:
    """An object store that records what it was given, and refuses nothing.

    `Metadata` is kept because the overwrite guard reads the published digest out of it:
    a fake that dropped it would make the guard untestable and the test would pass.
    """

    def __init__(self, existing: dict[str, dict] | None = None) -> None:
        self.objects: dict[str, dict] = dict(existing or {})

    def put_object(self, *, Bucket, Key, Body, Metadata=None, **kw):
        self.objects[f"s3://{Bucket}/{Key}"] = {"Body": Body, "Metadata": Metadata or {}}

    def head_object(self, *, Bucket, Key):
        found = self.objects.get(f"s3://{Bucket}/{Key}")
        if found is None:
            raise _missing()
        return {"Metadata": found["Metadata"], "ContentLength": len(found["Body"])}


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
            def put_object(self, *, Bucket, Key, Body, **kw):
                puts[f"s3://{Bucket}/{Key}"] = Body

            def head_object(self, *, Bucket, Key):
                raise _missing()

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
        # Refused at entry, before any compute — so the body never runs.
        with (
            pytest.raises(ReproError, match="s3:// URI"),
            run("A9.9", outdir=outdir, repo=repo, durable="/mnt/somewhere"),
        ):
            pass


#: Every `run(...)` call site in `tools/` that claims `durable_exempt`, with the task that
#: owns converting it. This list may **shrink** but must not grow: a new tool that writes a
#: result belongs in object storage, and the audit behind D-188 happened because nothing made
#: the local-only default visible. A legitimately exempt new tool goes here with a reason in
#: the same commit, so adding one is a deliberate, reviewed act rather than a default.
EXEMPT_CALL_SITES: set[str] = {
    # B4.1's baseline, conditional on `--out` like the others here. `--assay` makes a rehearsal
    # over one assay cheap, and a one-assay table published under the deliverable's key would
    # read exactly like the full 31.
    "baseline_scores.py",
    # B2.4's register, conditional on `--out` exactly as the three below are. The register is a
    # committed file, so a rehearsal that published would put a draft of a deliverable under the
    # real prefix permanently; pointing `--out` at `artifacts/b2-4` publishes as normal.
    "assay_register.py",
    # B3.4's depth covariate, conditional on `--out` like the rest. `--only` runs part of the
    # alignment set, and a table covering three of 28 targets published under the deliverable's
    # key would read exactly like the whole covariate — which is the one artefact B5 may not
    # have a partial copy of.
    "assay_depth.py",
    # A3.4's bin builder. `--limit` reads the first N families, so its denominator is a
    # fragment of the pinned universe wearing the published artefact's name, and the result
    # bucket has no delete; D-232 says the subset flag blocks publication, and this tool was
    # publishing regardless. A run without `--limit` names a durable destination as before.
    "diversity_bins.py",
    # A2.5's marker arm. The exemption is **conditional and is the fix for a real incident**,
    # not a carve-out for the deliverable: `durable_for` publishes only when `--out` is the
    # canonical `artifacts/a2-5`, and claims the exemption otherwise. A probe run from a scratch
    # directory published to the real prefix on 2026-10-19 because `run`'s `durable` is derived
    # from the task id and cannot see `--out`; the corpus bucket has no delete, so that file is
    # permanent (D-193). The deliverable path is still guarded — point `--out` at the canonical
    # directory and this tool names a durable destination like any other.
    "detect_segmented.py",
    # A7.4's contig pass, for the same shape of reason. The full pass runs on an instance
    # and always publishes; the exemption is claimed only by a run without `--upload-results`,
    # which is how the tool is smoke-tested against a local tar or a `--limit` slice. A
    # truncated table published under a commit's key would be permanent and would read
    # exactly like a complete one, so `--limit` refuses to publish at all.
    "opengenome_contigs.py",
    # A7.3's JSON-tree count, conditional on the same principle. The full pass publishes to
    # `corpora/results/a7-3/` like any other result; the exemption is claimed only when
    # `--max-records` bounds the read, which marks the artefact `partial` and the verdict
    # `not_measured`. A bounded read that reached the durable prefix would be permanent and
    # would sit beside the real count looking exactly like it — which is how a 20-record part
    # landed in A2.6's census prefix on 2026-10-20.
    "evo2_json_tree.py",
    # A7.3's repeated-accession pass, conditionally, on the same principle as the two above:
    # the full pass publishes, and the exemption is claimed only when `--max-headers` bounds
    # the read. A bounded read answers the question for a prefix of the release and would be
    # indistinguishable in the prefix from an answer for the whole of it.
    "evo2_duplicates.py",
    # A2.1 and A2.6's profile search, conditionally, and for the same incident one task over.
    # `detect_segmented.py`'s entry above describes the failure; on 2026-10-20 it happened
    # again here, because the lesson was fixed in one tool rather than in the shape both
    # share. An end-to-end rehearsal of `--assemble`, run from a scratch directory with three
    # synthetic band parts, published six tables to `corpora/results/a2-6/` under the exact
    # names the census will use (D-224). `durable_for` now publishes only from the task's
    # canonical `artifacts/<task>` directory and claims the exemption otherwise.
    "detect_profiles.py",
    # B2.3's control set, conditionally and for the same two reasons as the tools above: a
    # run written outside the task's canonical directory is a rehearsal, and a `--max-rows`
    # run has not seen the whole release. A bounded corpus-presence count is the dangerous
    # one here — it looks exactly like a complete count and would understate presence, which
    # is the direction that makes the control look weaker than it is.
    "control_set.py",
    # A7.5's matched-region metrics, conditionally and for both of the reasons the tools above
    # record: `durable_for` publishes only from the canonical `artifacts/a7-5`, so a rehearsal
    # pointed at a scratch directory cannot reach the prefix, and `--limit-records` refuses to
    # publish at all because a table over the first N records of the list would sit in the
    # prefix under the deliverable's own name looking exactly like the whole of it.
    "extract_matched_regions.py",
    # X1.9's per-record label join, conditionally on `--outdir` like the tools above. The
    # table is the record list A7.5 reads, so a rehearsal published under the deliverable's key
    # would hand a later pass a record set nobody chose, permanently.
    "denylist_label_records.py",
    # B1.2's reference-check table, conditionally: it reads the score artefacts already on
    # disk and writes a summary of them, so a run pointed at a scratch directory is a
    # rehearsal over whatever happens to be there. From the canonical directory it publishes
    # like any other result.
    "scoring_summary.py",
}


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


def test_every_run_call_site_in_tools_names_a_durable_destination():
    """The static half of D-188's guard, so a missed call site fails review not a six-hour run.

    `repro.run` refuses a local-only result at runtime, which is what binds a tool nobody has
    written yet. But a tool whose long pass only reaches `run`'s exit after hours of compute
    would learn about it the expensive way, and `stage_opengenome.py` showed the gap is easy to
    miss by inspection: it was skipped during the conversion *because* it uploads the staged
    corpus, and it also writes local composition tables.

    So every `run(...)` in `tools/` must name `durable=` or `durable_exempt=`, checked by
    parsing rather than grepping — a call spanning several lines is the normal case here.
    """
    import ast
    import pathlib

    def is_run(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id == "run"
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "repro"
        )

    bare = []
    seen = 0
    for path in sorted((pathlib.Path(__file__).resolve().parent.parent / "tools").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if is_run(node):
                seen += 1
                if not {"durable", "durable_exempt"} & {kw.arg for kw in node.keywords}:
                    bare.append(f"{path.name}:{node.lineno}")

    assert seen > 30, f"only found {seen} run() call sites; has the check stopped matching?"
    assert not bare, (
        "these run() call sites name no durable destination, so their results would not "
        f"survive the session (D-188): {bare}"
    )


def test_a_test_run_never_reaches_the_real_object_store(tmp_path):
    """The regression that cost four A1.6 objects.

    Several tests drive a tool's `main()` end-to-end with no client injected — deliberately,
    since the on-instance path is the one thing a dry run cannot check. Giving those tools
    `durable=` made them upload their synthetic fixtures to the corpus bucket, which has no
    `s3:DeleteObject`. So under pytest the upload is skipped unless the test supplied the
    client itself, and the manifest records that it was skipped: a manifest produced under test
    must not read as one whose outputs were actually persisted.
    """
    repo = _git_repo(tmp_path)
    outdir = repo / "artifacts" / "t"
    with run(
        "A9.9", outdir=outdir, repo=repo, durable="s3://real-bucket/corpora/results/a9-9"
    ) as m:
        (outdir / "r.txt").write_text("ok\n")
        m.output_file(outdir / "r.txt")

    assert m.uploaded == {}
    assert m.upload_skipped == "test run: no uploader injected"
    manifest = json.loads((outdir / MANIFEST_NAME).read_text())
    assert manifest["upload_skipped"] == "test run: no uploader injected"
    assert manifest["uploaded"] == {}
    # And the output has no durable_uri, so nothing downstream can cite a copy that is not there.
    assert "durable_uri" not in manifest["outputs"][0]


#: Scripts in `tools/` that produce no result of their own, and so legitimately run outside
#: `repro.run`. This is X1.5's half of D-188's guard: the runtime refusal and the call-site
#: check above both key on a `run(...)` block, so a tool with no block at all is invisible to
#: them — which is exactly how `uniprot_denylist_count.py` came to write a cited count with no
#: provenance. Like `EXEMPT_CALL_SITES`, this list may shrink but should not grow without a
#: reason written here in the same commit.
NOT_PIPELINES: dict[str, str] = {
    # Repository validators and generators. Their output is either nothing or a git-tracked
    # file, and git is the one store D-188 found was never at risk.
    "board.py": "regenerates tasks/BOARD.md, which is committed",
    "decisions.py": "validates D-NNN citations; writes nothing",
    "policies.py": "verifies the quotes in policies/ against their sources; writes nothing",
    "specquotes.py": "checks spec quotes against the captures; writes nothing",
    "specs.py": "validates the filter policy specs; writes nothing",
    "stage_assay_msas.py": (
        "pulls B4.1's alignments and structures out of the published archives into data/, "
        "which `metrics/` describes as a cache of pinned inputs rather than a result. It "
        "writes a digest manifest beside them; nothing it produces is a measurement"
    ),
    "assay_licences.py": (
        "acquires B2.4's licence evidence into assays/licences.json, which is committed. It is "
        "the one online step in B2.4 and is deliberately outside the guard: a run(...) block "
        "fetching the web would make the register's inputs change under it, and the register "
        "that does run under the guard reads this file offline"
    ),
    # EC2 launchers. The measurement happens on the instance and is published to object
    # storage from there; the launcher only tars the payload and *downloads* finished
    # artefacts into `artifacts/`, which `metrics/` describes as a cache.
    "ec2_agreement.py": "launcher; the instance publishes A8.1's cross-tab",
    "ec2_count.py": "launcher; the instance publishes A1.3's cluster counts",
    "ec2_exclusivity.py": "launcher; the instance publishes the seed-exclusivity pass",
    "ec2_folds.py": "launcher; the instance publishes A2.2's fold detections",
    "ec2_opengenome_contigs.py": "launcher; the instance publishes A7.4's contig tables",
    "baseline_knob_probe.py": (
        "a diagnostic, and deliberately not a pipeline: it samples the baseline's filtering "
        "knobs against the published column to show that the shortfall B4.2 explains is not a "
        "mis-set parameter. Its table must not choose a parameter, so it publishes nothing and "
        "its findings live in D-248 and the B4.2 task file instead"
    ),
    "ec2_detect_census.py": (
        "launcher; the instance's own detect_profiles workers publish A2.6's band parts, "
        "and the assembly that merges them runs in the session container"
    ),
    "ec2_proviruses.py": "launcher; the instance publishes A2.4's provirus detections",
    "ec2_select_agent_seeds.py": "launcher; the instance publishes A1.8's seed set",
    "ec2_similarity.py": "launcher; the instance publishes A1.6's similarity pass",
    "ec2_uniprot_count.py": "launcher; the instance publishes the UniProtKB staging and count",
}


def test_every_tool_either_runs_under_the_guard_or_says_why_not():
    """The gap X1.5 closes: a writer with no `run(...)` block at all.

    `test_every_run_call_site_in_tools_names_a_durable_destination` can only see tools that
    already have a block, and `repro.run`'s own refusal only fires once a run is under way.
    Neither sees a script that opens a file and writes a result straight out. So the inventory
    is inverted here: every script in `tools/` runs under the guard unless it is written down
    as producing no result, with the reason beside it.
    """
    import ast
    import pathlib

    tools = pathlib.Path(__file__).resolve().parent.parent / "tools"
    outside = set()
    for path in sorted(tools.glob("*.py")):
        if any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "run")
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "repro"
                )
            )
            for node in ast.walk(ast.parse(path.read_text()))
        ):
            continue
        outside.add(path.name)

    assert outside == set(NOT_PIPELINES), (
        "the set of tools running outside repro.run has changed. A new one that produces a "
        "result belongs in a run(...) block with durable=; one that genuinely produces no "
        "result goes in NOT_PIPELINES with its reason. Removed one? Delete its entry. "
        f"unexpected={sorted(outside - set(NOT_PIPELINES))} "
        f"stale={sorted(set(NOT_PIPELINES) - outside)}"
    )


class TestTheCommitKeyedCopy:
    """D-216. The bucket cannot delete, but it can be written over, and for most of this
    project's life a re-run of a pipeline replaced its own earlier result in place."""

    def _run(self, repo, store, *, body: str, replace=None):
        outdir = repo / "artifacts" / "t"
        with run(
            "A9.9",
            outdir=outdir,
            repo=repo,
            durable="s3://corpora-bucket/corpora/results/a9-9",
            replace_durable=replace,
            # The second run of a pair sees the first one's `artifacts/` as untracked.
            # The commit is still recorded, which is all these tests read.
            allow_dirty=True,
            uploader=store,
        ) as m:
            (outdir / "table.json").write_text(body)
            m.output_file(outdir / "table.json")
        return outdir

    def test_every_output_lands_under_its_commit_as_well_as_its_name(self, tmp_path):
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        commit = git_state(repo)["commit"]
        stable = "s3://corpora-bucket/corpora/results/a9-9/table.json"
        keyed = f"s3://corpora-bucket/corpora/results/a9-9/by-commit/{commit}/table.json"
        assert stable in store.objects
        assert keyed in store.objects
        assert store.objects[stable]["Body"] == store.objects[keyed]["Body"]

    def test_the_commit_keyed_copy_is_not_under_the_prefix_a_reader_globs(self, tmp_path):
        """A tool listing `corpora/results/a9-9/*.json` must not start finding one result
        once per commit that ever produced it."""
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        prefix = "s3://corpora-bucket/corpora/results/a9-9/"
        alongside = [
            k for k in store.objects if k.startswith(prefix) and "/" not in k[len(prefix) :]
        ]
        assert sorted(alongside) == [prefix + "run.json", prefix + "table.json"]

    def test_two_commits_produce_two_objects(self, tmp_path):
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        first = git_state(repo)["commit"]
        (repo / "seed.txt").write_text("moved\n")
        subprocess.run(["git", "commit", "-aqm", "second"], cwd=repo, check=True)
        self._run(repo, store, body='{"x": 2}\n')
        second = git_state(repo)["commit"]
        assert first != second
        base = "s3://corpora-bucket/corpora/results/a9-9/by-commit"
        assert store.objects[f"{base}/{first}/table.json"]["Body"] == b'{"x": 1}\n'
        assert store.objects[f"{base}/{second}/table.json"]["Body"] == b'{"x": 2}\n'
        # The stable name holds the latest, as it always has.
        stable = "s3://corpora-bucket/corpora/results/a9-9/table.json"
        assert store.objects[stable]["Body"] == b'{"x": 2}\n'

    def test_rerunning_the_same_commit_over_the_same_bytes_is_a_no_op(self, tmp_path):
        """Re-running a deterministic pipeline is a normal thing to do and must not be a
        failure; what it writes is what is already there."""
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        self._run(repo, store, body='{"x": 1}\n')
        stable = "s3://corpora-bucket/corpora/results/a9-9/table.json"
        assert store.objects[stable]["Body"] == b'{"x": 1}\n'

    def test_the_same_commit_publishing_different_bytes_is_refused(self, tmp_path):
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        with pytest.raises(ReproError, match="already published different bytes"):
            self._run(repo, store, body='{"x": 999}\n')
        # And the published copy is still the published copy.
        stable = "s3://corpora-bucket/corpora/results/a9-9/table.json"
        assert store.objects[stable]["Body"] == b'{"x": 1}\n'

    def test_the_refusal_names_the_object_and_both_digests(self, tmp_path):
        """A refusal that does not say which object or how it differs sends whoever hits
        it back to the console output of a run that has already finished."""
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        with pytest.raises(ReproError) as caught:
            self._run(repo, store, body='{"x": 999}\n')
        message = str(caught.value)
        assert "by-commit" in message and "table.json" in message
        was = hashlib.sha256(b'{"x": 1}\n').hexdigest()
        now = hashlib.sha256(b'{"x": 999}\n').hexdigest()
        assert was in message and now in message
        assert "replace_durable" in message

    def test_a_declared_reason_allows_the_replacement_and_is_recorded(self, tmp_path):
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        outdir = self._run(repo, store, body='{"x": 999}\n', replace="D-216 test: input repinned")
        stable = "s3://corpora-bucket/corpora/results/a9-9/table.json"
        assert store.objects[stable]["Body"] == b'{"x": 999}\n'
        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        assert manifest["replace_durable"] == "D-216 test: input repinned"

    def test_the_manifest_points_at_the_copy_no_later_run_can_replace(self, tmp_path):
        """The stable URI is the one a reader uses; the commit-keyed URI is the one a
        citation needs, because it is the only one guaranteed to still hold these bytes."""
        repo = _git_repo(tmp_path)
        store = Store()
        outdir = self._run(repo, store, body='{"x": 1}\n')
        manifest = json.loads((outdir / MANIFEST_NAME).read_text())
        entry = next(o for o in manifest["outputs"] if o["path"].endswith("table.json"))
        assert entry["by_commit_uri"].endswith(f"/by-commit/{manifest['git']['commit']}/table.json")
        assert manifest["by_commit"]

    def test_a_published_digest_is_stored_beside_the_object(self, tmp_path):
        """The guard compares digests rather than sizes, so the digest has to travel with
        the object: two different results of the same shape are the case that matters."""
        repo = _git_repo(tmp_path)
        store = Store()
        self._run(repo, store, body='{"x": 1}\n')
        stable = store.objects["s3://corpora-bucket/corpora/results/a9-9/table.json"]
        assert stable["Metadata"]["sha256"] == sha256_file(repo / "artifacts" / "t" / "table.json")
        assert stable["Metadata"]["commit"] == git_state(repo)["commit"]

    def test_a_run_with_no_commit_still_uploads_to_the_stable_key(self, tmp_path):
        """On an EC2 instance there is no checkout. A tool that passes no `code_commit`
        gets the old behaviour rather than no upload at all — the manifest already says
        such a run cannot be traced, and losing the result as well helps nobody."""
        store = Store()
        outdir = tmp_path / "out"
        with run(
            "A9.9",
            outdir=outdir,
            repo=tmp_path,
            allow_dirty=True,
            durable="s3://corpora-bucket/corpora/results/a9-9",
            uploader=store,
        ) as m:
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "table.json").write_text('{"x": 1}\n')
            m.output_file(outdir / "table.json")
        assert "s3://corpora-bucket/corpora/results/a9-9/table.json" in store.objects
        assert not any("by-commit" in k for k in store.objects)

    def test_a_code_commit_parameter_keys_the_copy_when_there_is_no_checkout(self, tmp_path):
        """What the EC2 path actually does: the launcher knows the commit and passes it in."""
        store = Store()
        outdir = tmp_path / "out"
        with run(
            "A9.9",
            outdir=outdir,
            repo=tmp_path,
            allow_dirty=True,
            durable="s3://corpora-bucket/corpora/results/a9-9",
            uploader=store,
        ) as m:
            m.parameter("code_commit", "deadbeef")
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "table.json").write_text('{"x": 1}\n')
            m.output_file(outdir / "table.json")
        keyed = "s3://corpora-bucket/corpora/results/a9-9/by-commit/deadbeef/table.json"
        assert keyed in store.objects

    def test_a_head_failure_that_is_not_a_missing_key_is_raised(self, tmp_path):
        """Treating every `head_object` error as absence would turn a denied permission
        into a silent overwrite, which is the thing this guard exists to prevent."""
        repo = _git_repo(tmp_path)

        class Denied(Store):
            def head_object(self, *, Bucket, Key):
                raise RuntimeError("AccessDenied")

        with pytest.raises(RuntimeError, match="AccessDenied"):
            self._run(repo, Denied(), body='{"x": 1}\n')

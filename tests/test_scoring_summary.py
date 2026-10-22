"""B1.2's reference-check table, which is the artefact its Done-when is read against.

The table's job is to answer three questions honestly: did every in-scope model score the
same thing, is the scoring deterministic, and was the published reference reproduced *where
one exists*. Each of those has a way of passing without being true — a model omitted rather
than reported as not run, a determinism claim over zero rescored runs, an agreement floor met
by no comparisons at all. Those are what these tests pin.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

_spec = importlib.util.spec_from_file_location(
    "scoring_summary",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "scoring_summary.py",
)
assert _spec and _spec.loader
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


def scores(checkpoint, assay="ASSAY_1", *, deterministic=True, reference=None, n=100):
    doc = {
        "checkpoint": checkpoint,
        "assay": assay,
        "variants_scored": n,
        "determinism": {"bitwise_identical": deterministic, "variants_rescored": 32},
        "scores": {},
    }
    if reference is None:
        doc["reference_check"] = {"compared": False, "why_not": "no published column"}
    else:
        est, lo, hi, verdict = reference
        doc["published_column"] = "SomeModel"
        doc["reference_check"] = {
            "compared": True,
            "agreement_floor": 0.99,
            "ours_vs_published": {"estimate": est, "low": lo, "high": hi},
            "difference_vs_truth": {"estimate": 0.0, "low": -0.01, "high": 0.01},
            "verdict": verdict,
        }
    return doc


def write(tmp_path, docs):
    for i, d in enumerate(docs):
        (tmp_path / f"scores-{d['checkpoint']}-{d['assay']}-{i}.json").write_text(json.dumps(d))
    return ss.load(tmp_path)


class TestAModelThatWasNotRunIsReportedNotOmitted:
    def test_a_roster_checkpoint_with_no_artefact_still_appears(self, tmp_path):
        report = ss.summarise(write(tmp_path, [scores("esm2_t33_650M_UR50D")]))
        names = [r["checkpoint"] for r in report["checkpoints"]]
        assert set(ss.ROSTER) <= set(names)

    def test_the_nucleotide_arm_carries_its_reason_rather_than_a_blank(self, tmp_path):
        report = ss.summarise(write(tmp_path, []))
        evo = next(r for r in report["checkpoints"] if r["checkpoint"] == "evo2_7b")
        assert evo["run"] is False
        assert "published coding sequence" in evo["not_run"]

    def test_a_checkpoint_missing_for_no_recorded_reason_says_so(self, tmp_path):
        report = ss.summarise(write(tmp_path, []))
        esm = next(r for r in report["checkpoints"] if r["checkpoint"] == "ESMC-600M")
        assert "no reason recorded" in esm["not_run"]


class TestTheCommonTestSet:
    def test_only_assays_every_scored_checkpoint_covers_count(self, tmp_path):
        docs = [
            scores("esm2_t33_650M_UR50D", "A"),
            scores("esm2_t33_650M_UR50D", "B"),
            scores("ESMC-600M", "A"),
        ]
        common = ss.summarise(write(tmp_path, docs))["done_when"]["common_test_set"]
        assert common["assays_every_scored_checkpoint_covers"] == ["A"]
        assert common["checkpoints_scored"] == 2

    def test_the_checkpoints_not_run_are_named(self, tmp_path):
        report = ss.summarise(write(tmp_path, [scores("ESMC-600M")]))
        assert "evo2_7b" in report["done_when"]["common_test_set"]["not_run"]


class TestDeterminism:
    def test_a_non_deterministic_run_fails_the_claim(self, tmp_path):
        docs = [scores("ESMC-600M"), scores("esm2_t36_3B_UR50D", deterministic=False)]
        det = ss.summarise(write(tmp_path, docs))["done_when"]["determinism"]
        assert det["all_bitwise_identical"] is False

    def test_zero_runs_is_not_a_pass(self, tmp_path):
        """`all([])` is True, and a Done-when field reading True because nothing was tested
        is how a gap gets signed off."""
        det = ss.summarise(write(tmp_path, []))["done_when"]["determinism"]
        assert det["runs_checked"] == 0
        assert det["all_bitwise_identical"] is None


class TestTheReferenceCheck:
    def test_the_verdict_is_the_artefacts_own_not_a_second_one(self, tmp_path):
        """A boolean derived here would be a coarser standard beside the authoritative one,
        collapsing `undetermined` into `diverges`. The table reads; it does not re-decide."""
        docs = [scores("ESMC-600M", reference=(0.9912, 0.9898, 0.9924, "undetermined"))]
        report = ss.summarise(write(tmp_path, docs))
        run = next(r for r in report["checkpoints"] if r["checkpoint"] == "ESMC-600M")["runs"][0]
        assert run["reference_compared"] is True
        assert run["verdict"] == "undetermined"
        assert "meets_floor" not in run

    def test_undetermined_is_not_counted_as_reproduced(self, tmp_path):
        docs = [
            scores("ESMC-600M", reference=(0.9912, 0.9898, 0.9924, "undetermined")),
            scores("esm2_t36_3B_UR50D", reference=(0.9997, 0.9995, 0.9998, "reproduced")),
        ]
        refs = ss.summarise(write(tmp_path, docs))["done_when"][
            "reference_reproduced_where_one_exists"
        ]
        assert refs["verdicts"] == {"reproduced": 1, "undetermined": 1}
        assert refs["all_reproduced"] is False

    def test_a_checkpoint_without_one_is_listed_with_its_reason(self, tmp_path):
        docs = [scores("esm3-sm-open-v1")]
        refs = ss.summarise(write(tmp_path, docs))["done_when"][
            "reference_reproduced_where_one_exists"
        ]
        assert refs["runs_with_a_published_reference"] == 0
        assert refs["runs_without_one"] == [
            {"checkpoint": "esm3-sm-open-v1", "why": "no published column"}
        ]

    def test_no_comparisons_at_all_is_not_a_pass(self, tmp_path):
        refs = ss.summarise(write(tmp_path, [scores("esm3-sm-open-v1")]))["done_when"][
            "reference_reproduced_where_one_exists"
        ]
        assert refs["all_reproduced"] is None

    def test_the_lowest_agreement_is_reported_so_the_weakest_case_is_visible(self, tmp_path):
        docs = [
            scores("ESMC-600M", reference=(0.9912, 0.9990, 0.9999, "reproduced")),
            scores("esm2_t36_3B_UR50D", reference=(0.9997, 0.9995, 0.9998, "reproduced")),
        ]
        refs = ss.summarise(write(tmp_path, docs))["done_when"][
            "reference_reproduced_where_one_exists"
        ]
        assert refs["lowest_agreement"] == 0.9912


class TestTheMarkdown:
    def test_a_checkpoint_that_was_not_run_appears_as_a_row(self, tmp_path):
        md = ss.markdown(ss.summarise(write(tmp_path, [scores("ESMC-600M")])))
        assert "`evo2_7b`" in md and "not run" in md

    def test_a_missing_reference_is_named_rather_than_left_blank(self, tmp_path):
        md = ss.markdown(ss.summarise(write(tmp_path, [scores("esm3-sm-open-v1")])))
        assert "no published column" in md


class TestPublishing:
    def test_a_run_written_elsewhere_publishes_nothing(self, tmp_path):
        assert ss.durable_for(tmp_path) is None

    def test_the_canonical_directory_publishes(self):
        assert ss.durable_for(ss.CANONICAL_OUT).endswith("/results/b1-2")

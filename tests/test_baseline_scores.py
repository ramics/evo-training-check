"""B4.1's baseline run, and the three integration mistakes that would make it look fine.

The method itself is the authors' (D-229), so what is pinned here is the seam between their
output and this project's: the sign, the coordinate offset, and which column of their output is
read. Each of those can be wrong in a way that still produces a number for every variant, which
is why none of them is left as an assertion in a comment.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "baseline_scores",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "baseline_scores.py",
)
assert _spec and _spec.loader
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)


class TestTheCoordinateOffset:
    """ProteinGym trims each alignment to a range of the target and numbers variants on the
    whole protein. Getting this wrong loses variants rather than raising, and an assay that
    quietly scored a third of its variants reads as a weak baseline, not as a bug."""

    def test_an_untrimmed_alignment_leaves_positions_alone(self):
        assert bs.translate("K5A", 1) == "K5A"

    def test_a_trimmed_alignment_shifts_the_position(self):
        assert bs.translate("K285A", 281) == "K5A"

    def test_a_variant_before_the_aligned_region_is_not_scored(self):
        assert bs.translate("K2A", 281) is None

    def test_the_first_aligned_residue_is_position_one_not_zero(self):
        assert bs.translate("M281A", 281) == "M1A"


class TestWhichColumnIsRead:
    def test_the_combined_score_is_found_by_name(self):
        assert bs.score_key([{"mutation_fasta": "S1A", "RSA*LOR": 1.0, "LOR": 2.0}]) == "RSA*LOR"

    def test_a_missing_combined_column_refuses_rather_than_using_the_bare_lor(self):
        """LOR alone is the evolutionary half without the structural one — a different method
        from the one fixed in advance, and one that would silently score every variant."""
        with pytest.raises(RuntimeError, match="no combined-score column"):
            bs.score_key([{"mutation_fasta": "S1A", "LOR": 2.0, "RSA": 30.0}])

    def test_no_output_at_all_is_an_error(self):
        with pytest.raises(RuntimeError, match="no mutations"):
            bs.score_key([])

    def test_rows_without_a_value_are_dropped_not_zeroed(self):
        rows = [
            {"mutation_fasta": "S1A", "RSA*LOR": 1.5},
            {"mutation_fasta": "S1C", "RSA*LOR": None},
            {"mutation_fasta": None, "RSA*LOR": 2.0},
        ]
        assert bs.by_mutation(rows, "RSA*LOR") == {"S1A": 1.5}


class TestTheSummary:
    def _result(self, assay, *, verdict="reproduced", unscored=0, total=100):
        return {
            "assay": assay,
            "variants_in_assay": total,
            "variants_unscored": unscored,
            "reference_check": {"compared": True, "verdict": verdict},
        }

    def test_a_verdict_other_than_reproduced_fails_the_claim(self):
        out = bs.summarise([self._result("A"), self._result("B", verdict="diverges")])
        assert out["reference"]["all_reproduced"] is False
        assert out["reference"]["verdicts"] == {"diverges": 1, "reproduced": 1}

    def test_nothing_compared_is_not_a_pass(self):
        """`all([])` is True, and a baseline signed off as reproducing a reference it was never
        compared against is the failure this field exists to prevent."""
        out = bs.summarise([{**self._result("A"), "reference_check": {"compared": False}}])
        assert out["reference"]["assays_compared"] == 0
        assert out["reference"]["all_reproduced"] is None

    def test_an_assay_that_lost_variants_is_named_with_its_denominator(self):
        out = bs.summarise([self._result("A"), self._result("B", unscored=40, total=100)])
        assert out["assays_with_unscored_variants"] == [{"assay": "B", "unscored": 40, "of": 100}]

    def test_an_assay_that_lost_none_is_not_listed(self):
        assert bs.summarise([self._result("A")])["assays_with_unscored_variants"] == []

    def test_the_parameters_travel_with_the_result(self):
        """A run manifest records what was used; a decision entry records what was intended.
        They are only the same thing if the result carries the former."""
        out = bs.summarise([self._result("A")])
        assert out["parameters"]["seqid_weights"] == 0.80
        assert out["parameters"]["decision_ref"] == "D-229"

    def test_the_absence_of_training_exposure_is_stated_not_implied(self):
        out = bs.summarise([])
        assert "no weights" in out["no_training_exposure"]


class TestTheTemporaryCopy:
    def test_a_gzipped_alignment_is_readable_and_then_gone(self, tmp_path):
        source = tmp_path / "a.a2m.gz"
        with gzip.open(source, "wb") as handle:
            handle.write(b">target\nMKV\n>other\nMKA\n")
        with bs.plain_copy(source, ".a2m") as plain:
            assert plain.read_bytes().startswith(b">target")
            seen = plain
        assert not seen.exists()

    def test_it_is_cleaned_up_even_when_the_body_raises(self, tmp_path):
        source = tmp_path / "a.a2m.gz"
        with gzip.open(source, "wb") as handle:
            handle.write(b">t\nM\n")
        seen = None
        with pytest.raises(ZeroDivisionError), bs.plain_copy(source, ".a2m") as plain:
            seen = plain
            raise ZeroDivisionError
        assert seen is not None and not seen.exists()


class TestPublishing:
    def test_a_run_written_elsewhere_publishes_nothing(self, tmp_path):
        assert bs.durable_for(tmp_path) is None

    def test_the_canonical_directory_publishes(self):
        assert bs.durable_for(bs.CANONICAL_OUT).endswith("/results/b4-1")


def test_the_package_is_reported_missing_rather_than_crashing():
    """The baseline lives in its own environment, so running this tool from the wrong one is
    an ordinary mistake and should say which one to use."""
    try:
        bs.load_rsalor()
    except bs.Unavailable as exc:
        assert "pixi run -e baseline" in str(exc)


class TestCarryingOverAnAlreadyScoredAssay:
    """A restart mid-pass cost two hours of scoring once. Resuming is worth having and is
    also how a result from the wrong code slips into a deliverable looking like the rest, so
    every one of these is a case where the carry-over must be refused."""

    @staticmethod
    def _now(**over):
        base = {"parameters": dict(bs.PARAMETERS), "commit": "a" * 40, "dirty": False}
        base.update(over)
        return base

    def _write(self, tmp_path, body):
        path = tmp_path / "baseline-X.json"
        path.write_text(json.dumps(body))
        return path

    def test_an_identical_run_is_carried_over(self, tmp_path):
        now = self._now()
        path = self._write(tmp_path, {"assay": "X", "provenance": now})
        assert bs.reusable(path, now)["assay"] == "X"

    def test_a_missing_file_is_scored(self, tmp_path):
        assert bs.reusable(tmp_path / "absent.json", self._now()) is None

    def test_a_different_commit_is_scored_again(self, tmp_path):
        path = self._write(tmp_path, {"provenance": self._now(commit="b" * 40)})
        assert bs.reusable(path, self._now()) is None

    def test_a_changed_parameter_is_scored_again(self, tmp_path):
        stale = dict(bs.PARAMETERS)
        stale["min_seqid"] = 0.5
        path = self._write(tmp_path, {"provenance": self._now(parameters=stale)})
        assert bs.reusable(path, self._now()) is None

    def test_a_file_from_before_provenance_was_recorded_is_scored_again(self, tmp_path):
        path = self._write(tmp_path, {"assay": "X", "scores": {}})
        assert bs.reusable(path, self._now()) is None

    def test_nothing_is_carried_over_when_either_tree_was_dirty(self, tmp_path):
        dirty = self._now(dirty=True)
        path = self._write(tmp_path, {"provenance": dirty})
        assert bs.reusable(path, dirty) is None

    def test_nothing_is_carried_over_when_the_commit_is_unknown(self, tmp_path):
        unknown = self._now(commit=None)
        path = self._write(tmp_path, {"provenance": unknown})
        assert bs.reusable(path, unknown) is None

    def test_an_unreadable_file_is_scored_again_rather_than_raising(self, tmp_path):
        path = tmp_path / "baseline-X.json"
        path.write_text("{not json")
        assert bs.reusable(path, self._now()) is None

    def test_the_provenance_block_carries_the_parameters_and_the_commit(self):
        got = bs.provenance()
        assert got["parameters"] == dict(bs.PARAMETERS)
        assert set(got) == {"parameters", "commit", "dirty"}


class TestASubsetRunDoesNotPublish:
    """`--assay` is how a single assay is rehearsed, and the natural place to rehearse it is
    the canonical directory, where its per-assay file belongs. So `--out` cannot be the signal
    that separates a rehearsal from the deliverable here: a three-assay `baseline.json` under
    the deliverable's key reads exactly like a 31-assay one, and the store has no delete."""

    def test_the_full_pass_publishes(self):
        assert bs.durable_for(bs.CANONICAL_OUT) is not None

    def test_a_scratch_directory_does_not(self, tmp_path):
        assert bs.durable_for(tmp_path) is None

    def test_the_subset_flag_is_what_blocks_the_canonical_run(self):
        source = (
            pathlib.Path(__file__).resolve().parent.parent / "tools" / "baseline_scores.py"
        ).read_text()
        assert "partial = bool(args.assay)" in source
        assert "None if partial else durable_for(out)" in source

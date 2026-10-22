"""B1.2's published-reference check: what it reproduces, and what it refuses to call agreement."""

from __future__ import annotations

import math

import pytest

from amazebio import proteingym, reference
from amazebio.reference import ReferenceError, check_against_published

SEED = 20261020
# Small enough to read, large enough to clear MIN_VARIANTS.
MUTANTS = [f"A{i}G" for i in range(1, 41)]


def scores(values):  # type: ignore[no-untyped-def]
    return dict(zip(MUTANTS, values, strict=True))


def linear(slope: float = 1.0, offset: float = 0.0):  # type: ignore[no-untyped-def]
    return scores([slope * i + offset for i in range(len(MUTANTS))])


def noisy(step: int):  # type: ignore[no-untyped-def]
    """A deterministic reordering: every `step`-th pair swapped."""
    values = list(range(len(MUTANTS)))
    for i in range(0, len(values) - 1, step):
        values[i], values[i + 1] = values[i + 1], values[i]
    return scores([float(v) for v in values])


class TestVerdict:
    def check(self, ours, published, truth=None, resamples=400):  # type: ignore[no-untyped-def]
        return check_against_published(
            "stub",
            "ASSAY_1",
            ours,
            published,
            truth or linear(),
            seed=SEED,
            resamples=resamples,
        )

    def test_two_implementations_that_rank_identically_are_reproduced(self) -> None:
        result = self.check(linear(), linear(slope=2.0, offset=-5.0))
        assert result.ours_vs_published.estimate == pytest.approx(1.0)
        assert result.verdict == "reproduced"

    def test_a_reversed_ranking_diverges_rather_than_passing_on_magnitude(self) -> None:
        result = self.check(linear(slope=-1.0), linear())
        assert result.ours_vs_published.estimate == pytest.approx(-1.0)
        assert result.verdict == "diverges"

    def test_a_verdict_rests_on_the_interval_not_the_point_estimate(self) -> None:
        """A point estimate just over the floor with an interval reaching below it is
        undetermined. Calling that `reproduced` is how a harness bug ships."""
        result = self.check(noisy(2), linear())
        assert result.ours_vs_published.estimate > reference.AGREEMENT_FLOOR
        assert result.ours_vs_published.low < reference.AGREEMENT_FLOOR
        assert result.verdict == "undetermined"

    def test_a_tiny_assay_is_refused_a_verdict_rather_than_given_a_weak_one(self) -> None:
        few = MUTANTS[:5]
        result = check_against_published(
            "stub",
            "TINY",
            {m: float(i) for i, m in enumerate(few)},
            {m: float(i) for i, m in enumerate(few)},
            {m: float(i) for i, m in enumerate(few)},
            seed=SEED,
            resamples=100,
        )
        assert result.verdict == "too_few_variants"
        assert math.isnan(result.ours_vs_published.low)


class TestJoining:
    def test_variants_only_one_side_scored_are_counted_and_excluded(self) -> None:
        ours = linear()
        published = linear()
        published.pop(MUTANTS[0])
        ours["Z99Y"] = 1.0
        result = check_against_published(
            "stub", "A", ours, published, linear(), seed=SEED, resamples=100
        )
        assert result.variants_compared == len(MUTANTS) - 1
        assert result.variants_ours_only == 2  # the popped one, plus our extra
        assert result.variants_published_only == 0

    def test_no_shared_variant_is_a_join_failure_not_zero_agreement(self) -> None:
        with pytest.raises(ReferenceError, match="join failure"):
            check_against_published(
                "stub", "A", linear(), {"Q1W": 1.0}, linear(), seed=SEED, resamples=10
            )

    def test_an_assay_with_no_dms_scores_is_refused(self) -> None:
        with pytest.raises(ReferenceError, match="nothing to validate against"):
            check_against_published("stub", "A", linear(), linear(), {}, seed=SEED)


class TestIntervals:
    def test_the_paired_interval_brackets_its_point_estimate(self) -> None:
        interval = reference.paired_spearman_interval(
            [float(v) for v in range(40)],
            [float(v) for v in noisy(5).values()],
            seed=SEED,
            resamples=500,
        )
        assert interval.low <= interval.estimate <= interval.high
        assert interval.method.startswith("bootstrap_percentile_p500")

    def test_unequal_lengths_are_refused_rather_than_truncated(self) -> None:
        with pytest.raises(ReferenceError, match="equal lengths"):
            reference.paired_spearman_interval([1.0, 2.0], [1.0], seed=SEED, resamples=10)

    def test_the_difference_interval_is_narrower_than_the_two_marginals_combined(self) -> None:
        """The whole reason it is computed paired rather than from the two marginals."""
        result = check_against_published(
            "stub", "A", noisy(3), noisy(5), linear(), seed=SEED, resamples=1000
        )
        paired_width = result.difference_vs_truth.high - result.difference_vs_truth.low
        naive_width = (result.ours_vs_truth.high - result.ours_vs_truth.low) + (
            result.published_vs_truth.high - result.published_vs_truth.low
        )
        assert paired_width < naive_width

    def test_the_resampling_spearman_matches_the_one_the_point_estimate_uses(self) -> None:
        """`_fast_spearman` exists only to be quick inside the resampling loop. If it
        disagreed with `proteingym.spearman` the interval would be around a different
        quantity than the estimate it brackets, which ties are the usual way to discover."""
        import numpy as np

        for x, y in (
            ([1.0] * 10 + [2.0] * 10, [float(i) for i in range(20)]),
            ([3.0, 3.0, 1.0, 2.0, 2.0, 2.0], [1.0, 4.0, 4.0, 2.0, 9.0, 4.0]),
        ):
            assert reference._fast_spearman(np.asarray(x), np.asarray(y)) == pytest.approx(
                proteingym.spearman(x, y)
            )


class TestAssayLevel:
    def test_the_published_assay_number_is_reported_with_its_gap(self) -> None:
        result = check_against_published(
            "stub",
            "A",
            linear(),
            linear(),
            linear(),
            seed=SEED,
            resamples=100,
            published_assay_spearman=0.95,
        )
        assert result.ours_vs_truth.estimate == pytest.approx(1.0)
        assert result.assay_level_gap == pytest.approx(0.05)

    def test_no_published_number_reports_none_rather_than_zero(self) -> None:
        result = check_against_published(
            "stub", "A", linear(), linear(), linear(), seed=SEED, resamples=100
        )
        assert result.published_assay_spearman is None
        assert result.assay_level_gap is None

    def test_the_verdict_ignores_the_assay_level_agreement(self) -> None:
        """Agreement on the headline Spearman must not rescue a harness that disagrees per
        variant — that combination is exactly what a systematic offset error looks like."""
        result = check_against_published(
            "stub",
            "A",
            linear(slope=-1.0),
            linear(),
            linear(),
            seed=SEED,
            resamples=200,
            published_assay_spearman=-1.0,
        )
        assert result.assay_level_gap == pytest.approx(0.0)
        assert result.verdict == "diverges"


class TestThePlanPath:
    """`tools/score_variants.py --plan` costs a pass without loading a model, which is what
    lets the request be reviewed before a GPU is billed — and what lets this run in CI."""

    def tool(self):  # type: ignore[no-untyped-def]
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "score_variants.py"
        spec = importlib.util.spec_from_file_location("score_variants", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def assay(self, sequence: str = "MKTAYIAKQR"):  # type: ignore[no-untyped-def]
        from amazebio.proteingym import Assay, Taxon

        return Assay(
            dms_id="TEST",
            uniprot_id="T",
            taxon=Taxon.VIRUS,
            source_organism="x",
            filename="TEST.csv",
            target_sequence=sequence,
            seq_len=len(sequence),
            n_singles=2,
            n_multiples=0,
            selection_assay="Growth",
            selection_type="Growth",
            msa_depth_category="Low",
            doi="10.0/x",
            year="2024",
        )

    def test_a_masked_marginal_plan_costs_batches_not_variants(self) -> None:
        from amazebio import scoring

        tool = self.tool()
        variants = scoring.variants_from_mutants(["M1A", "K2A", "T3A", "A4G"])
        doc = tool.plan(
            "esm2_t33_650M_UR50D",
            self.assay(),
            variants,
            batch_size=2,
            variants_source="test",
        )
        assert doc["variants"] == 4
        assert doc["masked_positions"] == 4
        assert doc["forward_passes"] == 2  # four positions, two per batch

    def test_a_sequence_delta_plan_costs_one_pass_per_mutant_plus_the_wild_type(self) -> None:
        from amazebio import scoring

        tool = self.tool()
        variants = scoring.variants_from_mutants(["M1A", "K2A"])
        doc = tool.plan("evo2_7b", self.assay(), variants, batch_size=8, variants_source="test")
        assert doc["mode"] == "sequence_delta"
        assert doc["forward_passes"] == 3

    def test_the_plan_records_that_the_request_has_nowhere_to_put_a_prompt(self) -> None:
        from amazebio import scoring

        tool = self.tool()
        doc = tool.plan(
            "esm2_t33_650M_UR50D",
            self.assay(),
            scoring.variants_from_mutants(["M1A"]),
            batch_size=8,
            variants_source="test",
        )
        assert doc["scope"]["request_fields"] == list(scoring.request_fields())

    def test_a_checkpoint_outside_the_inventory_is_refused_by_the_plan(self) -> None:
        from amazebio import scoring

        tool = self.tool()
        with pytest.raises(scoring.ScoringError, match="not in the B1.1 inventory"):
            tool.plan(
                "gpt-4",
                self.assay(),
                scoring.variants_from_mutants(["M1A"]),
                batch_size=8,
                variants_source="test",
            )


class TestWhetherTheCheckRanIsAlwaysStated:
    """One of the four Tier-1 checkpoints has no column in the published score table, so its
    artefact carries no comparison. A missing key cannot distinguish that from a check that
    was skipped by accident, and the difference is the whole value of the reference arm."""

    def test_a_real_comparison_says_it_compared(self) -> None:
        ours = {f"v{i}": float(i) for i in range(30)}
        published = {f"v{i}": float(i) + 0.01 for i in range(30)}
        truth = {f"v{i}": float(i) * 0.5 for i in range(30)}
        out = reference.check_against_published(
            "some-checkpoint", "SOME_ASSAY", ours, published, truth, seed=1
        ).to_dict()
        assert out["compared"] is True

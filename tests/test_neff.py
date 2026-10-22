"""The depth statistic, against hand-computable alignments.

Neff is one line of arithmetic and three implementations of it, which is exactly the shape
that goes wrong quietly: the duplicate shortcut, the exact self-comparison and the sampled
estimator must agree, and only an alignment small enough to sum by hand says they do.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from amazebio import neff


class TestMatchColumns:
    def test_insertions_are_dropped_so_every_row_has_the_same_width(self):
        rows = ["ABcDE", "AB.DE", "ABxyzDE", "A-cDE"]
        widths = {len(neff.match_columns(r)) for r in rows}
        assert widths == {4}

    def test_a_gap_is_a_match_column_and_a_dot_is_not(self):
        assert neff.match_columns("A-B.C") == "A-BC"


class TestTheNeighbourFloor:
    def test_the_inclusive_reading_admits_a_pair_exactly_on_the_threshold(self):
        # 0.8 of 10 columns is 8 exactly, so a pair matching 8 is a neighbour under the
        # inclusive reading and is not under the strict one.
        assert neff.neighbour_floor(10, 0.8, inclusive=True) == 8
        assert neff.neighbour_floor(10, 0.8, inclusive=False) == 9

    def test_the_readings_agree_where_the_threshold_lands_between_integers(self):
        assert neff.neighbour_floor(7, 0.8, inclusive=True) == 6
        assert neff.neighbour_floor(7, 0.8, inclusive=False) == 6

    def test_a_threshold_of_one_admits_only_an_identical_row(self):
        assert neff.neighbour_floor(12, 1.0, inclusive=True) == 12

    def test_the_floor_never_exceeds_the_column_count(self):
        assert neff.neighbour_floor(9, 0.999, inclusive=False) == 9

    def test_an_alignment_with_no_columns_is_refused(self):
        with pytest.raises(neff.DepthError, match="no match columns"):
            neff.neighbour_floor(0, 0.9, inclusive=True)

    @pytest.mark.parametrize("threshold", [0.0, -0.5, 1.5])
    def test_a_threshold_outside_the_unit_interval_is_refused(self, threshold):
        with pytest.raises(neff.DepthError, match="not a fraction"):
            neff.neighbour_floor(10, threshold, inclusive=True)


class TestCollapsingIdenticalRows:
    def test_rows_are_collapsed_with_their_multiplicities(self):
        codes, mult = neff.encode(["AB", "AB", "CD"])
        assert codes.shape == (2, 2)
        assert sorted(mult.tolist()) == [1, 2]

    def test_rows_of_different_length_are_not_one_alignment(self):
        with pytest.raises(neff.DepthError, match="not one alignment"):
            neff.encode(["ABC", "AB"])

    def test_an_empty_alignment_is_refused(self):
        with pytest.raises(neff.DepthError, match="no depth"):
            neff.encode([])


class TestDepthAgainstHandComputedSums:
    def test_the_duplicate_path_counts_distinct_rows(self):
        # At a threshold of 1.0 only an identical row is a neighbour, so three distinct rows
        # among five sequences weigh 1 each.
        d = neff.depth(["AAAA", "AAAA", "AAAC", "AAAC", "CCCC"], 1.0, seed=1)
        assert d.method == "duplicates"
        assert d.neff == 3.0
        assert d.distinct_rows == 3

    def test_the_exact_path_sums_the_weights(self):
        # Floor 3 of 4: AAAA (two of them) and AAAC are mutually neighbours, so each of those
        # three sequences has three neighbours and they weigh 1 between them; CCCC is alone.
        d = neff.depth(["AAAA", "AAAA", "AAAC", "CCCC"], 0.75, seed=1)
        assert d.method == "exact"
        assert d.neff == pytest.approx(2.0)
        assert d.interval is None

    def test_a_sequence_counts_itself_so_depth_never_exceeds_the_alignment(self):
        rows = ["ACDE", "FGHI", "KLMN"]
        d = neff.depth(rows, 0.9, seed=1)
        assert d.neff == pytest.approx(len(rows))

    def test_the_strict_reading_can_split_a_group_the_inclusive_one_merges(self):
        rows = ["AAAAAAAAAA", "AAAAAAAACC"]
        merged = neff.depth(rows, 0.8, inclusive=True, seed=1)
        split = neff.depth(rows, 0.8, inclusive=False, seed=1)
        assert merged.neff == pytest.approx(1.0)
        assert split.neff == pytest.approx(2.0)

    def test_gaps_count_as_mismatches_rather_than_being_skipped(self):
        # Over the ungapped positions these two rows are identical; over all four columns they
        # match on two. The definition D-231 pins says the second, so they are not neighbours.
        d = neff.depth(["AC--", "--AC"], 0.75, seed=1)
        assert d.neff == pytest.approx(2.0)


class TestTheSampledEstimatorAgreesWithTheExactSum:
    def _alignment(self, seed: int = 7, rows: int = 900, columns: int = 12) -> list[str]:
        rng = np.random.default_rng(seed)
        alphabet = np.array(list("ACDEFGHIKL"))
        # A few clusters with noise, so the weights are not all 1 and the estimator has
        # something to get wrong.
        centres = rng.choice(alphabet, size=(12, columns))
        out = []
        for _ in range(rows):
            row = centres[rng.integers(0, len(centres))].copy()
            for position in rng.choice(columns, size=rng.integers(0, 3), replace=False):
                row[position] = rng.choice(alphabet)
            out.append("".join(row))
        return out

    def test_the_estimate_brackets_the_exact_sum(self):
        rows = self._alignment()
        exact = neff.depth(rows, 0.8, seed=11)
        estimated = neff.depth(
            rows, 0.8, seed=11, budget=0.0, verify_budget=0.0, sample_rows=600, resamples=400
        )
        assert exact.method == "exact"
        assert estimated.method == "sampled"
        low, high = estimated.interval
        assert low <= exact.neff <= high
        assert estimated.neff == pytest.approx(exact.neff, rel=0.1)

    def test_an_estimate_never_ships_without_an_interval(self):
        d = neff.depth(
            self._alignment(),
            0.8,
            seed=3,
            budget=0.0,
            verify_budget=0.0,
            sample_rows=200,
            resamples=200,
        )
        assert d.interval is not None
        assert d.sample == 200
        assert d.as_dict()["interval"][0] < d.as_dict()["interval"][1]

    def test_the_same_seed_gives_the_same_estimate(self):
        rows = self._alignment()
        first = neff.depth(
            rows, 0.8, seed=5, budget=0.0, verify_budget=0.0, sample_rows=300, resamples=200
        )
        second = neff.depth(
            rows, 0.8, seed=5, budget=0.0, verify_budget=0.0, sample_rows=300, resamples=200
        )
        assert first.neff == second.neff
        assert first.interval == second.interval


class TestThePigeonholePathAgreesWithTheDirectOne:
    """The prefilter is an optimisation, so the only thing that matters is that it changes
    nothing. It is exercised by forcing the direct comparison off its budget."""

    def _alignment(self, seed: int = 4, rows: int = 500, columns: int = 40) -> list[str]:
        rng = np.random.default_rng(seed)
        alphabet = np.array(list("ACDEFGHIKLMNPQ"))
        centres = rng.choice(alphabet, size=(30, columns))
        out = []
        for _ in range(rows):
            row = centres[rng.integers(0, len(centres))].copy()
            for position in rng.choice(columns, size=rng.integers(0, 3), replace=False):
                row[position] = rng.choice(alphabet)
            out.append("".join(row))
        return out

    def test_it_gives_the_same_sum_as_comparing_every_pair(self):
        rows = self._alignment()
        direct = neff.depth(rows, 0.95, seed=1)
        prefiltered = neff.depth(rows, 0.95, seed=1, budget=0.0)
        assert direct.method == "exact"
        assert prefiltered.method == "exact"
        assert prefiltered.neff == pytest.approx(direct.neff)
        assert prefiltered.notes and "pigeonhole" in prefiltered.notes[0]

    def test_it_stands_aside_rather_than_spending_more_than_its_budget(self):
        rows = self._alignment()
        # A loose threshold makes the blocks a couple of columns wide and every row collides
        # with every other, so the candidate set approaches the whole product. Where that costs
        # more than the budget allows, the sampled path takes over rather than the prefilter
        # quietly doing the expensive thing.
        got = neff.depth(rows, 0.3, seed=1, budget=0.0, verify_budget=1e3, resamples=200)
        assert got.method == "sampled"
        assert got.interval is not None

    def test_an_alignment_whose_rows_share_no_block_has_no_candidate_pairs(self):
        rows = ["ACDEFGHIKL", "MNPQRSTVWY"]
        assert neff.depth(rows, 0.9, seed=1, budget=0.0).neff == pytest.approx(2.0)


class TestWhatTheArtefactCarries:
    def test_the_record_says_which_path_produced_the_number(self):
        d = neff.depth(["AAAA", "AAAC"], 0.75, seed=1)
        record = d.as_dict()
        assert record["method"] == "exact"
        assert record["boundary"] == "inclusive"
        assert record["neighbour_floor_columns"] == 3
        assert record["sequences"] == 2

    def test_depth_per_column_is_the_normalised_figure(self):
        d = neff.depth(["ACDEFGHIKL"] * 3, 0.9, seed=1)
        assert d.neff_per_column == pytest.approx(d.neff / 10)

    def test_the_duplicate_path_says_why_it_was_free(self):
        d = neff.depth(["AAAA", "CCCC"], 1.0, seed=1)
        assert d.notes and "identical row" in d.notes[0]


class TestTheBlockedComparisonMatchesAnUnblockedOne:
    def test_a_database_block_smaller_than_the_alignment_changes_nothing(self, monkeypatch):
        rng = np.random.default_rng(2)
        rows = ["".join(rng.choice(list("ACDE"), size=8)) for _ in range(400)]
        whole = neff.depth(rows, 0.75, seed=1)
        monkeypatch.setattr(neff, "DB_BLOCK", 37)
        blocked = neff.depth(rows, 0.75, seed=1)
        assert whole.neff == pytest.approx(blocked.neff)
        assert not math.isnan(blocked.neff)

"""Tests for A1.6's similarity instrument.

Two of these are worth more than the rest. `test_three_readings_from_one_relaxed_search`
pins the trade D-109 buys the coverage sweep with — if the post-filter does not reproduce
what the aligner's own `--cov-mode` would have kept, the saving is an error instead. And
`test_design_effect_exceeds_one_when_hits_are_clumped` pins the reason D-109 refuses a
binomial interval: the clumped case has to come out with a design effect well above 1, or the
interval the pass publishes is the confident-looking wrong one D-104 warned about.
"""

from __future__ import annotations

import math

import pytest

from amazebio import similarity as sim


def test_band_edges_cover_the_unit_interval_without_overlap() -> None:
    labels = sim.band_labels()
    assert len(labels) == len(sim.IDENTITY_BAND_EDGES) - 1
    assert labels[1] == "0.70-0.75", "the band D-105 reports separately has to be its own cell"
    assert [sim.band_of(x) for x in (0.0, 0.69, 0.70, 0.745, 0.75, 0.80, 0.90)] == [
        0,
        0,
        1,
        1,
        2,
        3,
        4,
    ]


def test_band_of_counts_a_perfect_identity_rather_than_dropping_it() -> None:
    # A seed whose own cluster is also a corpus record matches itself at 1.0. That is a
    # surviving record, and a half-open top band would silently discard the clearest case.
    assert sim.band_of(1.0) == len(sim.band_labels()) - 1


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_band_of_rejects_identities_outside_the_unit_interval(bad: float) -> None:
    with pytest.raises(ValueError):
        sim.band_of(bad)


def test_coverage_modes_match_mmseqs_semantics() -> None:
    # mode 0 both sides, mode 1 target, mode 2 query. The whole post-filter rests on this
    # mapping, so it is asserted directly rather than exercised only through the ledger.
    assert sim.coverage_passes(0, 0.9, 0.9)
    assert not sim.coverage_passes(0, 0.9, 0.5)
    assert sim.coverage_passes(1, 0.1, 0.9)
    assert not sim.coverage_passes(1, 0.9, 0.1)
    assert sim.coverage_passes(2, 0.9, 0.1)
    assert not sim.coverage_passes(2, 0.1, 0.9)
    assert sim.coverage_passes(1, 0.0, sim.COVERAGE), "the boundary is inclusive, as -c is"


def test_coverage_passes_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError):
        sim.coverage_passes(3, 1.0, 1.0)


def test_search_argv_relaxes_coverage_by_default_and_never_prefilters_identity() -> None:
    argv = sim.search_argv(sensitivity=5.7)
    assert argv == ("-s", "5.7", "--max-seqs", "100000")
    assert "-c" not in argv, "the relaxed search is what makes the three readings recoverable"
    assert "--min-seq-id" not in argv, "banded reporting needs the rows below the cut too"


def test_search_argv_can_build_the_unrelaxed_fallback() -> None:
    argv = sim.search_argv(sensitivity=7.5, coverage_mode=1, cap=300, min_identity=0.70)
    assert argv == (
        "-s",
        "7.5",
        "--max-seqs",
        "300",
        "-c",
        "0.8",
        "--cov-mode",
        "1",
        "--min-seq-id",
        "0.7",
    )


def test_hit_row_parses_and_rejects_a_truncated_row() -> None:
    row = sim.HitRow.parse("SEED1\tUniRef100_A0A\t0.812\t0.95\t0.44\n")
    assert (row.query, row.target) == ("SEED1", "UniRef100_A0A")
    assert row.fident == pytest.approx(0.812)
    with pytest.raises(ValueError):
        sim.HitRow.parse("SEED1\tUniRef100_A0A\t0.812")


def test_parse_hits_skips_blanks_but_not_malformed_rows() -> None:
    assert len(list(sim.parse_hits(["", "a\tb\t1.0\t1.0\t1.0", "  \n"]))) == 1
    with pytest.raises(ValueError):
        list(sim.parse_hits(["a\tb\tnot-a-number\t1.0\t1.0"]))


def test_three_readings_from_one_relaxed_search() -> None:
    """One relaxed search, three coverage readings, and they do not agree — which is the point.

    Row 2 covers the target but not the query, so it survives mode 1 and dies under modes 0
    and 2. If the readings came out identical the sweep would be measuring nothing.
    """
    rows = [
        sim.HitRow("s1", "recA", 0.95, 0.9, 0.9),
        sim.HitRow("s2", "recB", 0.80, 0.2, 0.9),
        sim.HitRow("s3", "recC", 0.72, 0.9, 0.2),
    ]
    ledger = sim.RecordLedger().extend(rows)
    assert ledger.records(0) == {"recA"}
    assert ledger.records(1) == {"recA", "recB"}
    assert ledger.records(2) == {"recA", "recC"}


def test_ledger_counts_a_record_once_and_keeps_its_best_identity() -> None:
    # A corpus record matching forty seeds is one surviving record. Counting hit rows would
    # inflate every rate by the seed set's own redundancy.
    rows = [
        sim.HitRow("s1", "recA", 0.71, 1.0, 1.0),
        sim.HitRow("s2", "recA", 0.93, 1.0, 1.0),
        sim.HitRow("s3", "recA", 0.80, 1.0, 1.0),
    ]
    ledger = sim.RecordLedger().extend(rows)
    counts = ledger.counts_by_band(1)
    assert sum(counts) == 1
    assert counts[sim.band_of(0.93)] == 1


def test_ledger_takes_the_best_identity_among_rows_that_pass_the_reading() -> None:
    """The best identity is per reading, not global — a higher-identity row that fails the
    coverage predicate must not raise the band of a record that only survives on a weaker row."""
    rows = [
        sim.HitRow("s1", "recA", 0.99, 0.1, 0.1),  # fails every reading
        sim.HitRow("s2", "recA", 0.72, 0.9, 0.9),  # passes all three
    ]
    ledger = sim.RecordLedger().extend(rows)
    for mode in sim.COVERAGE_READINGS:
        assert ledger.counts_by_band(mode)[sim.band_of(0.72)] == 1
        assert ledger.counts_by_band(mode)[sim.band_of(0.99)] == 0


def test_threshold_sweep_is_free_from_one_ledger() -> None:
    rows = [
        sim.HitRow(f"s{i}", f"rec{i}", ident, 1.0, 1.0)
        for i, ident in enumerate((0.55, 0.71, 0.74, 0.88, 1.0))
    ]
    ledger = sim.RecordLedger().extend(rows)
    assert ledger.counts_at_or_above(1, 0.0) == 5
    assert ledger.counts_at_or_above(1, 0.70) == 4
    assert ledger.counts_at_or_above(1, 0.75) == 2
    assert ledger.counts_at_or_above(1, 1.0) == 1


def test_saturation_guard_reports_binding_and_headroom() -> None:
    guard = sim.Saturation(cap=3)
    for _ in range(2):
        guard.observe("s1")
    guard.observe("s2")
    assert not guard.saturated
    assert guard.headroom() == pytest.approx(2 / 3)

    guard.observe("s1")
    assert guard.saturated, "a seed reaching the cap makes every count a lower bound"
    assert guard.to_dict()["queries_at_cap"] == 1
    assert guard.to_dict()["max_hits_per_query"] == 3


def test_saturation_guard_is_empty_rather_than_undefined_with_no_hits() -> None:
    guard = sim.Saturation(cap=10)
    assert guard.max_hits == 0
    assert not guard.saturated
    assert guard.headroom() == 0.0


def test_perfectly_even_spread_leaves_no_between_family_variance() -> None:
    # Ten families, one hit in ten records each. The estimator's variance is between-family
    # only, so identical families give zero — a design effect *below* 1, not 1. Pinned
    # because it is the boundary that makes the clumped case below interpretable: the
    # reported design effect is a ratio against binomial, and it is free to go either way.
    rate = sim.rate_with_interval([(1, 10)] * 10)
    assert rate.rate == pytest.approx(0.1)
    assert rate.families == 10
    assert rate.records == 100
    assert rate.design_effect == pytest.approx(0.0, abs=1e-12)
    assert rate.standard_error == pytest.approx(0.0, abs=1e-12)


def test_design_effect_exceeds_one_when_hits_are_clumped() -> None:
    """The case D-109 exists for: the same overall rate, concentrated in two families.

    Binomial would call this 10% +/- 3%; the cluster estimator has to widen it, because the
    evidence is two families rather than a hundred records.
    """
    clusters = [(10, 10), (10, 10)] + [(0, 10)] * 18
    rate = sim.rate_with_interval(clusters)
    assert rate.rate == pytest.approx(0.1)
    assert rate.design_effect is not None and rate.design_effect > 10
    binomial_se = math.sqrt(0.1 * 0.9 / 200)
    assert rate.standard_error is not None and rate.standard_error > 3 * binomial_se
    assert rate.low == 0.0, "an interval that wide has to be allowed to touch zero"


def test_rate_with_one_family_has_no_interval() -> None:
    rate = sim.rate_with_interval([(3, 100)])
    assert rate.rate == pytest.approx(0.03)
    assert rate.standard_error is None and rate.design_effect is None
    assert rate.families == 1


def test_rate_with_an_empty_denominator_is_none_rather_than_zero() -> None:
    rate = sim.rate_with_interval([])
    assert rate.rate is None
    assert rate.to_dict()["ci95"] == [None, None]


def test_rate_interval_stays_inside_the_unit_interval() -> None:
    rate = sim.rate_with_interval([(9, 10), (10, 10), (8, 10)])
    assert rate.high is not None and rate.high <= 1.0
    assert rate.low is not None and rate.low >= 0.0

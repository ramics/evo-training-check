"""Tests for A1.6's similarity instrument.

Two of these are worth more than the rest. `test_three_readings_from_one_relaxed_search`
pins the trade D-109 buys the coverage sweep with — if the post-filter does not reproduce
what the aligner's own `--cov-mode` would have kept, the saving is an error instead. And
`test_design_effect_exceeds_one_when_hits_are_clumped` pins the reason D-109 refuses a
binomial interval: the clumped case has to come out with a design effect well above 1, or the
interval the pass publishes is the confident-looking wrong one D-104 warned about.
"""

from __future__ import annotations

import itertools
import math

import pytest

from amazebio import seeds
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


def test_two_filtered_searches_recover_all_three_readings_exactly() -> None:
    """The replacement for D-109's relaxed search plus post-filter.

    The mode-1 search returns every pair with tcov >= c, and mode 0 is qcov >= c AND
    tcov >= c, so every mode-0 pair is in those results and the emitted qcov column
    identifies it. Mode 2 is not a subset of mode 1, so it needs its own search. Here recB
    passes mode 1 only, recC mode 2 only, recA all three.
    """
    universe = [
        sim.HitRow("s1", "recA", 0.95, 0.9, 0.9),
        sim.HitRow("s2", "recB", 0.80, 0.2, 0.9),
        sim.HitRow("s3", "recC", 0.72, 0.9, 0.2),
    ]
    # What each aligner-filtered search would return.
    mode1_rows = [r for r in universe if r.tcov >= sim.COVERAGE]
    mode2_rows = [r for r in universe if r.qcov >= sim.COVERAGE]

    ledger = sim.RecordLedger()
    ledger.extend_from_search(mode1_rows, 1)
    ledger.extend_from_search(mode2_rows, 2)

    # Identical to what one unfiltered search post-filtered three ways would have produced.
    reference = sim.RecordLedger().extend(universe)
    for mode in sim.COVERAGE_READINGS:
        assert ledger.records(mode) == reference.records(mode), f"reading {mode} differs"
    assert ledger.records(0) == {"recA"}
    assert ledger.records(1) == {"recA", "recB"}
    assert ledger.records(2) == {"recA", "recC"}


def test_the_mode_one_search_is_not_allowed_to_speak_for_reading_two() -> None:
    """recC has qcov >= c and tcov < c, so the mode-1 search never sees it. Deriving reading 2
    from those rows would report a floor as a measurement."""
    universe = [
        sim.HitRow("s1", "recA", 0.95, 0.9, 0.9),
        sim.HitRow("s3", "recC", 0.72, 0.9, 0.2),
    ]
    mode1_rows = [r for r in universe if r.tcov >= sim.COVERAGE]
    ledger = sim.RecordLedger().extend_from_search(mode1_rows, 1)
    assert ledger.records(2) == set(), "reading 2 must stay empty until its own search runs"
    assert ledger.records(1) == {"recA"}
    assert ledger.records(0) == {"recA"}


def test_search_readings_covers_every_reading_exactly_once() -> None:
    derived = [m for modes in sim.SEARCH_READINGS.values() for m in modes]
    assert sorted(derived) == sorted(sim.COVERAGE_READINGS)
    assert len(sim.SEARCH_READINGS) == 2, "two searches, not three cells and not one relaxed"


def test_an_unknown_search_mode_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="not one of the searches"):
        sim.RecordLedger().extend_from_search([], 0)


def _rows_sorted(rows: list[sim.HitRow]) -> list[sim.HitRow]:
    return sorted(rows, key=lambda r: r.target)


def test_streaming_aggregate_matches_the_ledger_exactly() -> None:
    """The streaming path is only worth having if it is the same answer in constant memory."""
    rows = [
        sim.HitRow("s1", "recA", 0.71, 0.9, 0.9),
        sim.HitRow("s2", "recA", 0.93, 0.9, 0.9),
        sim.HitRow("s3", "recB", 0.80, 0.2, 0.9),
        sim.HitRow("s4", "recC", 0.72, 0.9, 0.9),
        sim.HitRow("s5", "recC", 0.55, 0.9, 0.9),
        sim.HitRow("s6", "recD", 1.00, 0.9, 0.9),
    ]
    ledger = sim.RecordLedger().extend(rows)
    stream = sim.TargetStream().extend(_rows_sorted(rows)).close()
    for mode in sim.COVERAGE_READINGS:
        assert stream.bands[mode] == ledger.counts_by_band(mode), f"reading {mode}"
        assert stream.records[mode] == len(ledger.records(mode))


def test_streaming_aggregate_keeps_only_the_current_target() -> None:
    """The property the whole item rests on: memory does not grow with hit records, which is
    the quantity the pass exists to measure and therefore cannot be used to size a machine."""
    stream = sim.TargetStream()
    for i in range(20000):
        stream.observe(sim.HitRow("s1", f"rec{i:06d}", 0.9, 0.9, 0.9))
    stream.close()
    assert stream.records[1] == 20000
    assert stream._target is None and stream._best == []


def test_unsorted_rows_are_refused_rather_than_double_counted() -> None:
    """Unsorted input splits a record across runs and counts it once per run — inflating every
    band count in the direction of more apparent leakage. Remembering seen targets is the
    memory this class avoids, so order is required and checked."""
    stream = sim.TargetStream()
    stream.observe(sim.HitRow("s1", "recB", 0.9, 0.9, 0.9))
    with pytest.raises(ValueError, match="not sorted by target"):
        stream.observe(sim.HitRow("s2", "recA", 0.9, 0.9, 0.9))


def test_close_is_idempotent() -> None:
    stream = sim.TargetStream().extend([sim.HitRow("s1", "recA", 0.9, 0.9, 0.9)])
    stream.close()
    stream.close()
    assert stream.records[1] == 1


def test_a_stream_for_one_search_derives_only_its_readings() -> None:
    rows = _rows_sorted([sim.HitRow("s1", "recA", 0.95, 0.9, 0.9)])
    stream = sim.TargetStream.for_search(1).extend(rows).close()
    assert set(stream.bands) == {0, 1}
    assert 2 not in stream.records, "the mode-1 search cannot speak for reading 2 (D-124)"


def test_threshold_counts_come_free_at_a_band_edge() -> None:
    rows = _rows_sorted(
        [
            sim.HitRow("s1", "recA", 0.55, 0.9, 0.9),
            sim.HitRow("s2", "recB", 0.71, 0.9, 0.9),
            sim.HitRow("s3", "recC", 0.88, 0.9, 0.9),
            sim.HitRow("s4", "recD", 1.00, 0.9, 0.9),
        ]
    )
    stream = sim.TargetStream().extend(rows).close()
    assert stream.counts_at_or_above(1, 0.70) == 3
    assert stream.counts_at_or_above(1, 0.75) == 2
    assert stream.counts_at_or_above(1, 0.90) == 1


def test_a_threshold_inside_a_band_is_refused_not_interpolated() -> None:
    """Banded reporting buys every threshold on a band edge and none between them. Saying so
    is better than returning a number nobody can reproduce."""
    stream = sim.TargetStream().extend([sim.HitRow("s1", "recA", 0.9, 0.9, 0.9)]).close()
    with pytest.raises(ValueError, match="cannot be recovered"):
        stream.counts_at_or_above(1, 0.72)


def _cell(
    shard: int,
    s: float,
    mode: int,
    bands: list[int],
    fams: list[tuple[int, int]],
    denominator: int = 1,
    seeds: int = 3_159_223,
    seed_families: int = 4_000,
) -> sim.CellResult:
    return sim.CellResult(
        key=sim.CellKey(shard=shard, sensitivity=s, cov_mode=mode, seed_denominator=denominator),
        bands={m: list(bands) for m in sim.SEARCH_READINGS[mode]},
        families={m: list(fams) for m in sim.SEARCH_READINGS[mode]},
        searched_clusters=1_000_000,
        searched_residues=417_000_000,
        seeds_searched=seeds,
        seed_families=seed_families,
    )


def test_cells_from_different_shards_sum_exactly() -> None:
    """The property the incremental design rests on: shards are a disjoint hash partition, so
    no corpus record is in two of them and counts add without double counting."""
    cells = [
        _cell(0, 5.7, 1, [10, 1, 2, 3, 4], [(1, 100), (0, 100)]),
        _cell(1, 5.7, 1, [20, 2, 4, 6, 8], [(3, 100)]),
    ]
    out = sim.combine_cells(cells)
    (g0, g1) = sorted(out["groups"], key=lambda g: g["reading"])
    assert g1["bands"] == [30, 3, 6, 9, 12]
    assert g1["shards"] == [0, 1]
    assert g1["searched_clusters"] == 2_000_000
    assert g1["rate"]["families"] == 3, "families accumulate across shards"


def test_the_denominator_is_what_was_searched_not_what_was_planned() -> None:
    """Three shards of eight must report a rate over three shards. Anything else is a claim
    about work not yet paid for."""
    out = sim.combine_cells([_cell(0, 5.7, 1, [1, 0, 0, 0, 0], [(1, 50)])])
    g = out["groups"][0]
    assert g["searched_clusters"] == 1_000_000
    assert g["shards"] == [0]


def test_the_same_shard_counted_twice_is_refused() -> None:
    """A re-run that appends instead of replacing would inflate every band silently."""
    cells = [_cell(0, 5.7, 1, [1, 1, 1, 1, 1], [(1, 10)])] * 2
    with pytest.raises(ValueError, match="already contributed"):
        sim.combine_cells(cells)


def test_sensitivities_are_grouped_not_summed() -> None:
    """Summing across sensitivities would double count the same records."""
    out = sim.combine_cells(
        [
            _cell(0, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100)]),
            _cell(0, 7.5, 1, [12, 0, 0, 0, 0], [(1, 100)]),
        ]
    )
    sens = sorted({g["sensitivity"] for g in out["groups"]})
    assert sens == [5.7, 7.5]
    for g in out["groups"]:
        assert sum(g["bands"]) in (10, 12), "each sensitivity keeps its own count"


def test_a_cell_slug_is_stable_and_distinct() -> None:
    """It is an artefact key: once results exist under it, it must not change."""
    assert sim.CellKey(0, 5.7, 1).slug() == "shard00-s5.7-cov1"
    keys = {
        sim.CellKey(s, sv, cm).slug()
        for s in (0, 1)
        for sv in sim.SENSITIVITIES
        for cm in sim.SEARCH_READINGS
    }
    assert len(keys) == 2 * len(sim.SENSITIVITIES) * len(sim.SEARCH_READINGS)


def test_a_cell_knows_which_readings_it_may_speak_for() -> None:
    assert sim.CellKey(0, 5.7, 1).readings == (0, 1)
    assert sim.CellKey(0, 5.7, 2).readings == (2,)


# --- D-134: the seed axis ---------------------------------------------------------------


def _ids(n: int) -> list[str]:
    return [f"UniRef100_A0A{i:06d}" for i in range(n)]


def test_the_seed_bands_are_nested_so_the_accumulation_curve_is_monotone() -> None:
    """The property the whole nested design rests on, and it is not a coincidence of hashing.

    `bucket_of(x, 100) == 0` implies `bucket_of(x, 10) == 0`, because the bucket is a hash
    modulo the denominator and 100 is a multiple of 10. So band 1's seeds are a *subset* of
    band 2's, band 2's of the full set, and a record found at 1/100 is found again at 1/10.
    Without that, the two bands would be different samples rather than a deepening, and the
    difference between their counts would not be an accumulation of anything.
    """
    ids = _ids(5_000)
    band1 = set(sim.select_seeds(ids, 100))
    band2 = set(sim.select_seeds(ids, 10))
    band3 = set(sim.select_seeds(ids, 1))
    assert band1, "a 1/100 sample of 5,000 ids should not be empty"
    assert band1 < band2 < band3
    assert band3 == set(ids)
    assert all(
        d1 % d2 == 0 for d1, d2 in itertools.pairwise(sim.SEED_BANDS)
    ), "every band denominator must divide the one before it, or the bands are not nested"


def test_a_seed_sample_is_the_rule_the_cap_run_used() -> None:
    """Band 1 has to re-run the cap measurement's query set, or it does not price band 2."""
    ids = _ids(2_000)
    assert list(sim.select_seeds(ids, 100)) == [i for i in ids if seeds.bucket_of(i, 100) == 0]


def test_a_seed_sample_is_stable_across_calls_and_keeps_input_order() -> None:
    ids = _ids(1_000)
    first = list(sim.select_seeds(ids, 10))
    assert first == list(sim.select_seeds(ids, 10))
    assert first == [i for i in ids if i in set(first)], "order must follow the input"


def test_a_seed_denominator_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        list(sim.select_seeds(_ids(10), 0))
    with pytest.raises(ValueError, match="at least 1"):
        sim.CellKey(0, 5.7, 1, seed_denominator=0)


def test_a_full_seed_cell_keeps_the_slug_it_had_before_the_seed_axis_existed() -> None:
    """D-128's band-3 cells must not be renamed by this field having been added: the corpus
    bucket has no DeleteObject, so a rename orphans an object rather than replacing it."""
    assert sim.CellKey(0, 5.7, 1).slug() == "shard00-s5.7-cov1"
    assert sim.CellKey(0, 5.7, 1, seed_denominator=1).slug() == "shard00-s5.7-cov1"


def test_two_seed_bands_against_one_shard_get_different_artefact_names() -> None:
    """Same reason, the other direction: a shared name means band 2 silently reads as band 1."""
    keys = {
        sim.CellKey(0, sv, cm, seed_denominator=d).slug()
        for sv in sim.SENSITIVITIES
        for cm in sim.SEARCH_READINGS
        for d in sim.SEED_BANDS
    }
    assert len(keys) == len(sim.SENSITIVITIES) * len(sim.SEARCH_READINGS) * len(sim.SEED_BANDS)
    assert sim.CellKey(0, 5.7, 1, seed_denominator=100).slug() == "shard00-s5.7-cov1-q100"


def test_a_sampled_cell_knows_it_is_a_lower_bound_and_a_full_one_knows_it_is_not() -> None:
    assert sim.CellKey(0, 5.7, 1, seed_denominator=100).lower_bound is True
    assert sim.CellKey(0, 5.7, 1, seed_denominator=10).lower_bound is True
    assert sim.CellKey(0, 5.7, 1, seed_denominator=1).lower_bound is False


def test_seed_bands_are_not_pooled() -> None:
    """Two bands cover overlapping seed sets — nested, in fact — so adding their counts double
    counts every record both found. D-134's third no-pooling axis."""
    cells = [
        _cell(0, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100)], denominator=100, seeds=31_381),
        _cell(0, 5.7, 1, [40, 0, 0, 0, 0], [(4, 100)], denominator=10, seeds=315_922),
    ]
    with pytest.raises(ValueError, match="span seed bands"):
        sim.combine_cells(cells)


def test_the_bound_travels_with_every_rate_rather_than_beside_it() -> None:
    """The non-negotiables require the limit enforced in the harness. A caller cannot read the
    rate out of this structure without the qualifier coming too."""
    out = sim.combine_cells(
        [_cell(0, 5.7, 1, [10, 2, 1, 0, 0], [(1, 100), (2, 100)], denominator=100, seeds=31_381)]
    )
    assert out["lower_bound"] is True
    assert out["seed_denominator"] == 100
    for g in out["groups"]:
        assert g["rate"]["lower_bound"] is True
        assert g["seeds_searched"] == 31_381


def test_a_full_seed_pass_is_not_labelled_a_bound() -> None:
    out = sim.combine_cells([_cell(0, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100), (2, 100)])])
    assert out["lower_bound"] is False
    for g in out["groups"]:
        assert g["rate"]["lower_bound"] is False


def test_the_rate_describes_itself_with_at_least_only_when_it_is_a_bound() -> None:
    clusters = [(1, 100), (3, 100), (2, 100)]
    assert sim.rate_with_interval(clusters, lower_bound=True).describe().startswith("at least ")
    bare = sim.rate_with_interval(clusters).describe()
    assert not bare.startswith("at least ")
    assert "95% CI" in bare and "3 families" in bare


def test_a_rate_with_no_interval_says_so_rather_than_implying_precision() -> None:
    said = sim.rate_with_interval([(3, 100)], lower_bound=True).describe()
    assert "at least" in said and "no interval" in said


def test_the_seed_set_must_be_identical_across_shards_for_counts_to_be_summable() -> None:
    """Shards sum because they partition the corpus, not the query. Two shards run against
    different seed sets have record counts that are not summable at all."""
    cells = [
        _cell(0, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100)], denominator=100, seeds=31_381),
        _cell(1, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100)], denominator=100, seeds=31_000),
    ]
    with pytest.raises(ValueError, match="seeds_searched"):
        sim.combine_cells(cells)


def test_the_seed_family_count_is_carried_not_summed() -> None:
    """It is a property of the query set, identical on every shard. Summing it would report
    four thousand families as eight thousand for having searched two shards."""
    cells = [
        _cell(0, 5.7, 1, [10, 0, 0, 0, 0], [(1, 100)], denominator=100, seed_families=1_234),
        _cell(1, 5.7, 1, [20, 0, 0, 0, 0], [(2, 100)], denominator=100, seed_families=1_234),
    ]
    out = sim.combine_cells(cells)
    for g in out["groups"]:
        assert g["seed_families"] == 1_234
        assert g["searched_clusters"] == 2_000_000, "the corpus side still sums"


def test_pooling_unplaced_records_makes_the_interval_track_one_strata_rate() -> None:
    """D-141's measurement, pinned so the refutation is in the suite and not only in the log.

    D-140 asserted that pooling the taxonomy-unplaced records into one pseudo-family would
    understate the interval. It does not have a direction: a pooled stratum contributes
    `(A - r*B)^2`, which vanishes when its own rate equals the overall one and explodes when
    it does not. With A4.2's 36% unplaced fraction behind it, that is the whole interval.
    """
    placed = [(100 if i % 10 == 0 else 0, 100) for i in range(640)]
    n = 36_000

    # Unplaced records whose rate matches the overall one: pooling barely moves the interval.
    same = [(1 if i % 10 == 0 else 0, 1) for i in range(n)]
    se_single = sim.rate_with_interval(placed + same).standard_error
    se_pooled = sim.rate_with_interval([*placed, (sum(a for a, _ in same), n)]).standard_error
    assert se_single is not None and se_pooled is not None
    assert 0.99 < se_pooled / se_single < 1.0, "the understatement D-140 claimed is negligible"

    # Unplaced records at a different rate: pooling inflates it by an order of magnitude.
    hot = [(1 if i % 2 == 0 else 0, 1) for i in range(n)]
    se_single_hot = sim.rate_with_interval(placed + hot).standard_error
    se_pooled_hot = sim.rate_with_interval([*placed, (sum(a for a, _ in hot), n)]).standard_error
    assert se_single_hot is not None and se_pooled_hot is not None
    assert se_pooled_hot / se_single_hot > 10, "pooling runs the other way, and far"


def test_singleton_strata_contribute_the_binomial_term_and_nothing_more() -> None:
    """Which is the positive reason for the singleton treatment: records the taxonomy cannot
    place carry no family information, and that is exactly what a design effect of 1 says."""
    singles = [(1 if i % 4 == 0 else 0, 1) for i in range(4_000)]
    rate = sim.rate_with_interval(singles)
    assert rate.design_effect is not None
    assert math.isclose(rate.design_effect, 1.0, rel_tol=1e-3)
    assert math.isclose(rate.rate or 0.0, 0.25)

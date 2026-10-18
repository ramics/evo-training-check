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


def test_at_least_needs_an_asserted_direction_not_just_a_sampled_seed_set() -> None:
    """`lower_bound` marks one axis; "at least" is a claim about the whole figure.

    D-154 found the two being conflated after the number existed: the seed set implements
    clause (a) only, so seed *construction* overstates while seed *sampling* understates, and
    the net direction is not established. A1.8's arm has the same shape with a broadening
    term measured at 1.7x to 6.8x (D-157, D-159). So a sampled seed set alone no longer
    renders "at least" — a caller has to assert the direction, and the default is "unknown".

    This is the reporting limit put in the harness rather than in the write-up's good
    intentions, which is what the non-negotiables ask for.
    """
    clusters = [(1, 100), (3, 100), (2, 100)]
    sampled = sim.rate_with_interval(clusters, lower_bound=True)
    assert not sampled.describe().startswith("at least "), "a sampled seed axis is not a bound"
    assert "net direction not established" in sampled.describe()
    assert sampled.to_dict()["lower_bound"] is True, "the seed axis is still recorded"
    assert sampled.to_dict()["net_direction"] == "unknown"

    asserted = sim.rate_with_interval(clusters, lower_bound=True, net_direction="lower")
    assert asserted.describe().startswith("at least ")

    bare = sim.rate_with_interval(clusters, net_direction="lower").describe()
    assert bare.startswith("at least ")
    assert "95% CI" in bare and "3 families" in bare


def test_a_rate_with_no_interval_says_so_rather_than_implying_precision() -> None:
    said = sim.rate_with_interval([(3, 100)], lower_bound=True, net_direction="lower").describe()
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


# --- D-140/D-141: the interval's strata ---------------------------------------------------


class _Tax:
    """A stand-in for `seeds.Taxonomy` with the one method the index uses."""

    def __init__(self, families: dict[int, int | None]) -> None:
        self.families = families

    def ancestor_at_rank(self, taxid: int, rank: str = "family") -> int | None:
        return self.families.get(taxid)


def test_the_denominator_counts_records_searched_not_records_hit() -> None:
    """The misses only appear in the target shard, so the denominator can only come from
    there. A denominator built from the hit table would make every rate 100%."""
    tax = _Tax({10: 11157, 11: 11157, 12: None})
    idx = sim.FamilyIndex.build([("A", 10), ("B", 11), ("C", 12)], tax)
    assert idx.totals == {"f:11157": 2, "u:C": 1}
    assert idx.searched_records == 3
    assert sim.rate_with_interval(idx.pairs({"f:11157": 1})).rate == pytest.approx(1 / 3)


def test_a_searched_stratum_with_no_hits_still_counts() -> None:
    """Dropping it would divide by a denominator the search did not use — the same error as
    reporting a rate over the sample as designed instead of the shards actually run."""
    tax = _Tax({10: 11157, 20: 11158})
    idx = sim.FamilyIndex.build([("A", 10), ("B", 20)], tax)
    pairs = idx.pairs({"f:11157": 1})
    assert sorted(pairs) == [(0, 1), (1, 1)]


def test_an_unplaced_cluster_is_its_own_stratum() -> None:
    tax = _Tax({10: None, 11: None})
    idx = sim.FamilyIndex.build([("A", 10), ("B", 11)], tax)
    assert idx.totals == {"u:A": 1, "u:B": 1}
    assert idx.unplaced_records == 2


def test_a_cluster_with_no_taxid_is_unplaced_rather_than_dropped() -> None:
    idx = sim.FamilyIndex.build([("A", None)], _Tax({}))
    assert idx.totals == {"u:A": 1}


def test_placed_and_unplaced_stratum_ids_cannot_collide() -> None:
    """They live in one dict. A family id that happened to spell a cluster id would merge two
    strata and silently change the denominator."""
    assert sim.stratum_id("11157", 11157) != sim.stratum_id("11157", None)


def test_a_record_in_two_strata_is_refused() -> None:
    tax = _Tax({10: 11157, 20: 11158})
    with pytest.raises(ValueError, match="different families"):
        sim.FamilyIndex.build([("A", 10), ("A", 20)], tax)


def test_hits_in_a_stratum_that_was_never_searched_are_refused() -> None:
    """The hit table and the target shard must describe the same records, or the rate is over
    a denominator that does not contain its numerator."""
    idx = sim.FamilyIndex.build([("A", 10)], _Tax({10: 11157}))
    with pytest.raises(ValueError, match="never searched"):
        idx.pairs({"f:99999": 1})


def test_more_hits_than_records_in_a_stratum_is_refused() -> None:
    """The guard on the one bug that would overstate leakage: a record counted twice. Rows
    arriving unsorted is how it would happen, and `TargetStream` refuses that too."""
    idx = sim.FamilyIndex.build([("A", 10)], _Tax({10: 11157}))
    with pytest.raises(ValueError, match="inflates the rate"):
        idx.pairs({"f:11157": 2})


def test_the_stream_counts_hit_records_per_stratum() -> None:
    """The numerator side of the interval, taken in the same pass as the bands so the hit
    table is read once."""
    # recA and recD share a family; recB has its own and is never hit; recC is unplaced.
    tax = _Tax({10: 11157, 11: 11158, 12: None, 13: 11157})
    idx = sim.FamilyIndex.build([("recA", 10), ("recB", 11), ("recC", 12), ("recD", 13)], tax)
    stream = sim.TargetStream(derive=(1,), index=idx)
    # Sorted by target, as the class requires. recA is hit twice by different seeds and must
    # count once; recC is unplaced and is its own stratum.
    stream.extend(
        [
            sim.HitRow("s1", "recA", 0.95, 0.9, 0.9),
            sim.HitRow("s2", "recA", 0.80, 0.9, 0.9),
            sim.HitRow("s1", "recC", 0.76, 0.9, 0.9),
        ]
    ).close()
    assert stream.stratum_hits[1] == {"f:11157": 1, "u:recC": 1}
    assert stream.records[1] == 2, "recA hit twice counts once"
    pairs = idx.pairs(stream.stratum_hits[1])
    assert sorted(pairs) == [(0, 1), (1, 1), (1, 2)], (
        "recB's family is searched and unhit, and recA's family holds two searched records "
        "of which one was hit"
    )


def test_a_hit_target_outside_the_shards_strata_is_refused() -> None:
    """It means the hit table and the target shard are from different runs, which would put
    the numerator and denominator on different record sets."""
    idx = sim.FamilyIndex.build([("recA", 10)], _Tax({10: 11157}))
    stream = sim.TargetStream(derive=(1,), index=idx)
    with pytest.raises(ValueError, match="not in the shard's strata"):
        stream.extend([sim.HitRow("s1", "recZ", 0.95, 0.9, 0.9)]).close()


def test_the_stream_still_works_without_strata() -> None:
    """The cap measurement and the cost curve do not need them, and the bands must not depend
    on an index being supplied."""
    stream = sim.TargetStream(derive=(1,))
    stream.extend([sim.HitRow("s1", "recA", 0.95, 0.9, 0.9)]).close()
    assert stream.records[1] == 1
    assert stream.stratum_hits[1] == {}


def test_a_cell_is_assembled_from_the_search_and_the_index() -> None:
    tax = _Tax({10: 11157, 11: 11158})
    idx = sim.FamilyIndex.build([("recA", 10), ("recB", 11)], tax)
    stream = sim.TargetStream(derive=sim.SEARCH_READINGS[2], index=idx)
    stream.extend([sim.HitRow("s1", "recA", 0.95, 0.9, 0.9)]).close()
    cell = sim.cell_from_stream(
        sim.CellKey(0, 5.7, 2, seed_denominator=100),
        stream,
        idx,
        seeds_searched=31_381,
        seed_families=1_200,
        searched_residues=417_000_000,
    )
    assert cell.searched_clusters == 2, "the denominator comes from the index, not the caller"
    assert sorted(cell.families[2]) == [(0, 1), (1, 1)]
    assert cell.to_dict()["lower_bound"] is True
    assert cell.to_dict()["slug"] == "shard00-s5.7-cov2-q100"


def test_a_cell_cannot_report_a_reading_its_search_does_not_support() -> None:
    """D-124's whole argument is which search speaks for which reading. A cell built from the
    wrong one would publish mode 2 numbers under a mode 0/1 search."""
    idx = sim.FamilyIndex.build([("recA", 10)], _Tax({10: 11157}))
    stream = sim.TargetStream(derive=(2,), index=idx)
    with pytest.raises(ValueError, match="speaks for"):
        sim.cell_from_stream(
            sim.CellKey(0, 5.7, 1),
            stream,
            idx,
            seeds_searched=1,
            seed_families=1,
            searched_residues=1,
        )


def test_a_strata_sidecar_round_trips_including_the_unplaced_rows(tmp_path) -> None:
    path = tmp_path / "shard00.taxids.tsv"
    with path.open("wb") as fh:
        sim.write_taxid_row(fh, "UniRef100_A", 11158)
        sim.write_taxid_row(fh, "UniRef100_B", None)
    with path.open() as fh:
        assert list(sim.parse_taxid_rows(fh)) == [("UniRef100_A", 11158), ("UniRef100_B", None)]


def test_an_unplaced_cluster_is_written_explicitly_rather_than_omitted() -> None:
    """An absent row and a row saying "no taxid" are different claims, and only one of them
    survives a truncated file. The denominator depends on telling them apart."""
    rows = list(sim.parse_taxid_rows([f"UniRef100_B\t{sim.NO_TAXID}"]))
    assert rows == [("UniRef100_B", None)]


def test_a_malformed_sidecar_row_raises_rather_than_being_skipped() -> None:
    """The sidecar is the denominator of every rate this arm publishes. A row quietly dropped
    is a record quietly removed from the denominator, which moves the rate up."""
    with pytest.raises(ValueError, match="not a cluster/taxid pair"):
        list(sim.parse_taxid_rows(["UniRef100_A"]))
    with pytest.raises(ValueError, match="non-numeric taxid"):
        list(sim.parse_taxid_rows(["UniRef100_A\tnotanumber"]))


def test_the_sidecar_builds_the_index_it_exists_for() -> None:
    tax = _Tax({11158: 11157})
    rows = sim.parse_taxid_rows(["UniRef100_A\t11158", f"UniRef100_B\t{sim.NO_TAXID}"])
    idx = sim.FamilyIndex.build(rows, tax)
    assert idx.totals == {"f:11157": 1, "u:UniRef100_B": 1}
    assert idx.searched_records == 2
    assert idx.unplaced_records == 1


def test_a_published_cell_rehydrates_into_the_same_numbers() -> None:
    """The read half of the skip. A resumed band carries completed cells forward, so it must
    get back exactly what it published — a lossy round trip would silently change a rate."""
    tax = _Tax({10: 11157, 11: 11158})
    idx = sim.FamilyIndex.build([("recA", 10), ("recB", 11)], tax)
    stream = sim.TargetStream(derive=sim.SEARCH_READINGS[2], index=idx)
    stream.extend([sim.HitRow("s1", "recA", 0.95, 0.9, 0.9)]).close()
    original = sim.cell_from_stream(
        sim.CellKey(0, 7.5, 2, seed_denominator=100),
        stream,
        idx,
        seeds_searched=31_381,
        seed_families=7_366,
        searched_residues=417_056_773,
    )
    back = sim.cell_from_dict(original.to_dict())
    assert back.to_dict() == original.to_dict()
    assert back.key == original.key
    assert sim.combine_cells([back]) == sim.combine_cells([original])


def test_a_published_cell_whose_slug_contradicts_its_fields_is_refused() -> None:
    """A cell is reused on the strength of its slug, so the slug and the fields have to agree
    or a resumed run could skip the wrong cell and report it as done."""
    raw = sim.CellResult(
        key=sim.CellKey(0, 5.7, 1, seed_denominator=100),
        bands={m: [0, 0, 0, 0, 0] for m in sim.SEARCH_READINGS[1]},
        families={m: [] for m in sim.SEARCH_READINGS[1]},
    ).to_dict()
    raw["slug"] = "shard00-s7.5-cov1-q100"
    with pytest.raises(ValueError, match="identity is ambiguous"):
        sim.cell_from_dict(raw)


def test_resuming_does_not_change_the_combined_result() -> None:
    """The property that makes the skip safe: five published cells plus one new one must give
    the same answer as six computed in one run. Without it a reclaim would cost correctness as
    well as time, since one result object is rewritten on every publish."""
    cells = [
        _cell(0, s, m, [10, 2, 1, 0, 0], [(1, 100), (2, 100)], denominator=100, seeds=31_381)
        for s in sim.SENSITIVITIES
        for m in sim.SEARCH_READINGS
    ]
    one_run = sim.combine_cells(cells)
    resumed = sim.combine_cells([sim.cell_from_dict(c.to_dict()) for c in cells[:-1]] + [cells[-1]])
    assert resumed == one_run


# --- The fine cut inside the top band ------------------------------------------------------


def test_the_frozen_bands_are_not_changed_by_the_fine_cut() -> None:
    """`IDENTITY_BAND_EDGES` is frozen by D-105 and metrics/survival.md. This is extra."""
    assert sim.IDENTITY_BAND_EDGES == (0.0, 0.70, 0.75, 0.80, 0.90, 1.0)
    assert sim.FINE_TOP_EDGES[0] == 0.90, "the fine cut lives inside the top band"
    assert sim.FINE_TOP_EDGES[-1] == 1.0


def test_exact_identity_gets_its_own_slot() -> None:
    """ "The sequence is present" and "present bar one residue in a hundred" differ."""
    labels = sim.fine_top_labels()
    assert labels[-1] == "1.00 exact"
    assert sim.fine_top_slot(1.0) == len(sim.FINE_TOP_EDGES) - 1
    assert sim.fine_top_slot(0.999) != sim.fine_top_slot(1.0)
    assert sim.fine_top_slot(0.90) == 0
    assert sim.fine_top_slot(0.96) == 1
    assert sim.fine_top_slot(0.985) == 2
    assert sim.fine_top_slot(0.995) == 3


def test_the_fine_histogram_sums_to_the_top_band() -> None:
    """If these disagree the detail is describing a different set from the band it refines."""
    rows = [
        sim.HitRow(query="q", target=f"t{i:03d}", fident=f, qcov=0.9, tcov=0.9)
        for i, f in enumerate([0.91, 0.93, 0.96, 0.985, 0.995, 1.0, 1.0, 0.5, 0.72])
    ]
    stream = sim.TargetStream.for_search(1).extend(rows).close()
    mode = 1
    assert sum(stream.fine_top[mode]) == stream.bands[mode][-1]
    assert stream.fine_top[mode][-1] == 2, "two exact matches"


def test_a_cell_published_before_the_fine_cut_contributes_no_silent_zero() -> None:
    """An old cell did not measure this; it must not look like it measured zero."""
    raw = {
        "shard": 0,
        "sensitivity": 5.7,
        "cov_mode": 1,
        "seed_denominator": 100,
        "bands": {"1": [10, 2, 1, 1, 4]},
        "families": {"1": [[1, 10]]},
    }
    cell = sim.cell_from_dict(raw)
    assert cell.fine_top == {}, "absent, not zeroed"

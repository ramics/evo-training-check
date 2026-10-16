"""Tests for `tools/esm3_calibrate.py` — task A1.6's in-region pricing pass.

The timings this tool produces cannot be unit-tested; what can, and what the whole pass
rests on, is the sampling. Three ways it can be plausible and wrong:

* **An unstable hash.** `hash()` is salted per process, so the same cluster would land in
  a different shard on every run and the sample would be unreproducible — the one thing a
  pinned pipeline cannot have. The partition has to be stable across runs and machines.
* **A prefix mistaken for a sample.** UniRef is ordered by accession. The reason this tool
  partitions by hash at all is that a prefix is not a sample, so hit rates taken from one
  mean nothing. The sampler must not depend on position in the file.
* **Shards that are not nested samples.** The scaling curve is read off buckets 1..k for
  each k, which is only a valid sample at k times the rate if the bucket assignment is
  independent of the sampling decision. Deriving both from the same hash value would
  correlate them and tilt every shard the same way.
"""

from __future__ import annotations

import collections
import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "esm3_calibrate.py"
_spec = importlib.util.spec_from_file_location("esm3_calibrate_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["esm3_calibrate_under_test"] = tool
_spec.loader.exec_module(tool)

IDS = [f"UniRef100_A{i:06d}" for i in range(20000)]


def test_bucket_assignment_is_stable_across_calls() -> None:
    first = [tool.bucket_of(i, 8) for i in IDS[:500]]
    second = [tool.bucket_of(i, 8) for i in IDS[:500]]
    assert first == second


def test_bucket_assignment_is_pinned_to_known_values() -> None:
    """Pinned so a change of hash shows up as a failing test, not as a different sample."""
    assert [tool.bucket_of(f"UniRef100_Q6GZX{i}", 8) for i in range(6)] == [3, 1, 0, 2, 3, 1]


def test_sampling_is_roughly_uniform_and_independent_of_position() -> None:
    kept = [i for i in IDS if tool.bucket_of(i, 50) == 0]
    # 1 in 50 of 20,000 is 400; allow a generous band rather than pinning a count.
    assert 300 < len(kept) < 500
    # Position-independence: the keep rate in each tenth of the file is comparable.
    tenths = collections.Counter(IDS.index(i) // 2000 for i in kept)
    assert len(tenths) == 10, "a whole tenth of the file contributed nothing"
    assert max(tenths.values()) < 4 * min(tenths.values())


def test_shard_assignment_is_independent_of_the_sampling_decision() -> None:
    """Buckets 1..k must be a fair sample, so the two hashes must not agree."""
    kept = [i for i in IDS if tool.bucket_of(i, 50) == 0]
    shards = collections.Counter(tool.bucket_of(i + "#shard", 8) for i in kept)
    assert len(shards) == 8, "some shard got nothing, so nested shards would not be fair"
    assert max(shards.values()) < 3 * min(shards.values())


def test_a_single_bucket_puts_everything_in_it() -> None:
    assert {tool.bucket_of(i, 1) for i in IDS[:100]} == {0}


def test_readings_are_fixed_constants_not_computed() -> None:
    """The thresholds are fixed before results are inspected; they are not knobs."""
    assert tool.CHARITABLE == ("--min-seq-id", "0.70", "-c", "0.8", "--cov-mode", "1")
    # The strict reading removes on any detected hit, so it sets no identity floor.
    assert "--min-seq-id" not in tool.STRICT
    assert "-s" in tool.STRICT


def _slack(reading: str, shards: int, residues: int, wall: float, rows: int, mx: int) -> dict:
    return {
        "measurement": "hit-cap",
        "reading": reading,
        "shards": shards,
        "residues": residues,
        "cap": tool.similarity.HIT_CAP,
        "search_wall_seconds": wall,
        "hit_rows": rows,
        "saturation": {"max_hits_per_query": mx},
    }


def test_cap_and_curve_write_to_different_artefacts() -> None:
    """The corpus bucket has no DeleteObject, so a shared default would be unrecoverable."""
    assert tool.ARTEFACT_NAMES["caps"] != tool.ARTEFACT_NAMES["curve"]
    assert len(set(tool.ARTEFACT_NAMES.values())) == len(tool.ARTEFACT_NAMES)


def test_cap_summary_prices_relaxed_coverage_against_the_three_cell_fallback() -> None:
    """D-109's provisional item: relaxed coverage is only worth it below three separate cells."""
    cells = [
        _slack("relaxed", 1, 1_000_000_000, 250.0, 9000, 400),
        _slack("covmode1", 1, 1_000_000_000, 100.0, 3000, 150),
    ]
    summary = tool._cap_summary(cells)
    (cost,) = summary["coverage_cost"]
    assert cost["cost_ratio"] == 2.5
    assert cost["cheaper_than_three_cells"] is True

    cells[0]["search_wall_seconds"] = 400.0
    cost = tool._cap_summary(cells)["coverage_cost"][0]
    assert cost["cost_ratio"] == 4.0
    assert cost["cheaper_than_three_cells"] is False, "above 3x the fallback wins"


def test_cap_summary_reports_hits_per_seed_per_residue_for_extrapolation() -> None:
    """Whether the published cap binds at the pass's scale is this number times that scale."""
    summary = tool._cap_summary([_slack("relaxed", 2, 2_000_000_000, 10.0, 10, 500)])
    (row,) = summary["hits_per_seed"]
    assert row["max_hits_per_seed_per_g_residue"] == 250.0
    assert summary["published_cap"] == tool.similarity.HIT_CAP


def test_cap_summary_ignores_the_binding_cells_when_pricing_coverage() -> None:
    """A binding cap truncates, so its wall time prices truncation rather than coverage."""
    cells = [
        _slack("relaxed", 1, 1_000_000_000, 250.0, 9000, 400),
        _slack("covmode1", 1, 1_000_000_000, 100.0, 3000, 150),
        {**_slack("relaxed", 1, 1_000_000_000, 5.0, 100, 80), "cap": 80},
    ]
    assert tool._cap_summary(cells)["coverage_cost"][0]["cost_ratio"] == 2.5


def test_cap_summary_omits_a_shard_size_measured_at_only_one_coverage_setting() -> None:
    """A budget can stop the run between the two settings; half a ratio is not a ratio."""
    summary = tool._cap_summary([_slack("relaxed", 1, 1_000_000_000, 250.0, 9000, 400)])
    assert summary["coverage_cost"] == []
    assert len(summary["hits_per_seed"]) == 1, "the half that ran is still reported"

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

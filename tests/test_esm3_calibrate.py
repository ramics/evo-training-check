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

import pytest

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


def test_cap_summary_surfaces_the_reading_one_agreement_check() -> None:
    """D-109's premise, not its price: if the post-filter and the aligner's own --cov-mode 1
    pick different records, the three readings are recovered approximately and the write-up
    has to say by how much. A local rehearsal disagreed by one record out of 138."""
    agreement = {
        "post_filtered_records": 138,
        "aligner_filtered_records": 137,
        "only_post_filtered": 1,
        "only_aligner_filtered": 0,
        "jaccard": 0.9927,
    }
    cells = [
        _slack("relaxed", 1, 1_000_000_000, 250.0, 9000, 400),
        {**_slack("covmode1", 1, 1_000_000_000, 100.0, 3000, 150), "reading1_agreement": agreement},
    ]
    (row,) = tool._cap_summary(cells)["reading1_agreement"]
    assert row["shards"] == 1
    assert row["only_aligner_filtered"] == 0, "the post-filter being a superset is the safe side"


class _S3:
    def __init__(self, fail: bool = False) -> None:
        self.puts: list[tuple[str, str, bytes]] = []
        self.fail = fail

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
        if self.fail:
            raise RuntimeError("no network")
        self.puts.append((Bucket, Key, Body))


def test_heartbeat_reports_corpus_pass_progress_to_its_own_key() -> None:
    """The channel of last resort. Measured 2026-10-16: an instance ran 95 minutes on a pass
    due in 53 with no way to tell work from a wedge — console frozen, CloudWatch and console
    screenshot both denied, no SSH or SSM. S3 was the only way out and the pass wrote nothing
    until it finished."""
    import json

    client = _S3()
    beat = tool._make_heartbeat(client, "buk", "corpora", "progress-caps.json", "abc123")
    beat(8 << 20, 120.0)
    (bucket, key, body) = client.puts[0]
    assert (bucket, key) == ("buk", "corpora/results/a1-6/progress-caps.json")
    payload = json.loads(body)
    assert payload["decompressed_bytes"] == 8 << 20
    assert payload["bytes_per_second"] == round((8 << 20) / 120.0)
    assert payload["code_commit"] == "abc123"
    assert payload["stage"] == "corpus-pass"


def test_heartbeat_is_a_separate_key_from_the_result_artefact() -> None:
    """A progress file is not a deliverable, and the corpus bucket cannot delete anything."""
    assert set(tool.HEARTBEAT_NAMES) == set(tool.ARTEFACT_NAMES)
    assert not set(tool.HEARTBEAT_NAMES.values()) & set(tool.ARTEFACT_NAMES.values())


def test_a_failed_heartbeat_does_not_fail_the_run_it_reports_on() -> None:
    beat = tool._make_heartbeat(_S3(fail=True), "buk", "corpora", "progress-caps.json", None)
    beat(1024, 1.0)  # must not raise


def test_no_client_means_no_heartbeat_rather_than_a_crash() -> None:
    """A local run against --source has no S3 client and must be unaffected."""
    assert tool._make_heartbeat(None, "", "", "progress-caps.json", None) is None


class _StageS3:
    """Enough S3 to exercise staging: puts, a listing, and one readable manifest."""

    def __init__(self, existing: list[str] | None = None, manifest: bytes | None = None) -> None:
        self.existing = existing or []
        self.manifest = manifest
        self.puts: list[str] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
        self.puts.append(Key)

    def list_objects_v2(self, **kw: object) -> dict:
        prefix = str(kw.get("Prefix", ""))
        return {
            "Contents": [{"Key": k} for k in self.existing if k.startswith(prefix)],
            "IsTruncated": False,
        }

    def get_object(self, Bucket: str, Key: str) -> dict:
        class _B:
            def __init__(self, data: bytes) -> None:
                self.data = data

            def read(self) -> bytes:
                return self.data

        return {"Body": _B(self.manifest or b"{}")}


def _stage_args(tmp_path, **over):
    import argparse

    base = dict(
        release="2023_02",
        tier="uniref100",
        sample_rate=40,
        buckets=2,
        code_commit="abc123",
        sample_from=None,
        measure="caps",
        stage_sidecars_only=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _staged_files(tmp_path):
    seed = tmp_path / "viral-seeds.faa"
    seed.write_bytes(b">UniRef100_S1\nMKVL\n")
    shards = []
    for i in range(2):
        p = tmp_path / f"shard-{i:02d}.faa"
        p.write_bytes(f">UniRef100_C{i}\nMKVLAAAA\n".encode())
        shards.append(p)
    return seed, shards


def test_staging_refuses_to_overwrite_an_existing_object(tmp_path) -> None:
    """The corpus bucket has no DeleteObject, so an overwrite is not a replacement but the
    irreversible loss of the earlier object. AGENTS.md records what that cost once already."""
    from amazebio import seeds as sd
    from amazebio import shardstore as ss

    seed, shards = _staged_files(tmp_path)
    prefix = "corpora/" + ss.sample_prefix("2023_02", "uniref100", 40)
    client = _StageS3(existing=[f"{prefix}/shard-00.faa"])
    counts = sd.SeedCounts(clusters=10, viral_seeded=4)
    with pytest.raises(SystemExit, match="refusing to stage over existing objects"):
        tool._stage_sample(
            _stage_args(tmp_path), client, "buk", "corpora", seed, shards, counts, [1, 1], [8, 8]
        )
    assert client.puts == [], "nothing may be written once a clash is known"


def test_staging_writes_every_object_and_a_manifest(tmp_path) -> None:
    from amazebio import seeds as sd

    seed, shards = _staged_files(tmp_path)
    client = _StageS3()
    counts = sd.SeedCounts(clusters=10, residues=80, viral_seeded=4, viral_residues=32)
    uri = tool._stage_sample(
        _stage_args(tmp_path), client, "buk", "corpora", seed, shards, counts, [1, 1], [8, 8]
    )
    assert uri and uri.endswith("manifest.json")
    staged = [k for k in client.puts if "/results/" not in k]
    assert len(staged) == 4, f"two shards, the seed set, and the manifest: {staged}"
    # Every key under the run's prefix. Staging used sample_prefix() as an absolute key once,
    # which would have written gigabytes outside corpora/ in a bucket that cannot delete.
    assert all(
        k.startswith("corpora/samples/a1-6/uniref100/2023_02/rate40/") for k in staged
    ), f"keys escaped the run prefix: {staged}"
    assert uri.startswith("s3://buk/corpora/samples/")


def test_loading_refuses_a_sample_from_another_release_or_tier(tmp_path) -> None:
    """Shards from one release paired with this run's seeds would be undetectable downstream."""
    from amazebio import seeds as sd
    from amazebio import shardstore as ss

    seed, shards = _staged_files(tmp_path)
    manifest = ss.ShardManifest(
        release="2021_04",
        tier="uniref100",
        sample_rate=40,
        buckets=2,
        corpus_clusters=100,
        viral_seeded_clusters=4,
        seed_fasta=ss.describe(seed, "k/viral-seeds.faa"),
        shards=[ss.describe_shard(p, f"k/{p.name}", i, 1, 8) for i, p in enumerate(shards)],
    )
    client = _StageS3(manifest=manifest.to_json().encode())
    args = _stage_args(tmp_path, sample_from="s3://buk/k/manifest.json")
    with pytest.raises(SystemExit, match="staged sample is"):
        tool._load_staged_sample(args, client, tmp_path, seed, shards)
    assert isinstance(sd.SeedCounts(), sd.SeedCounts)


def test_loading_refuses_a_different_shard_count(tmp_path) -> None:
    """Shards 1..k is only a valid sample at k times the rate if the partition matches."""
    from amazebio import shardstore as ss

    seed, shards = _staged_files(tmp_path)
    manifest = ss.ShardManifest(
        release="2023_02",
        tier="uniref100",
        sample_rate=40,
        buckets=2,
        corpus_clusters=100,
        viral_seeded_clusters=4,
        seed_fasta=ss.describe(seed, "k/viral-seeds.faa"),
        shards=[ss.describe_shard(p, f"k/{p.name}", i, 1, 8) for i, p in enumerate(shards)],
    )
    client = _StageS3(manifest=manifest.to_json().encode())
    args = _stage_args(tmp_path, buckets=4, sample_from="s3://buk/k/manifest.json")
    with pytest.raises(SystemExit, match="refused rather than reinterpreted"):
        tool._load_staged_sample(args, client, tmp_path, seed, shards)


def test_s3_uri_parsing() -> None:
    assert tool._parse_s3_uri("s3://buk/a/b/manifest.json") == ("buk", "a/b/manifest.json")


def test_hit_tables_are_sorted_in_byte_order_so_the_aggregator_agrees(tmp_path) -> None:
    """LC_ALL=C is load-bearing, not cosmetic. TargetStream verifies order with Python string
    comparison (codepoint order); a UTF-8 locale sort collates case and punctuation
    differently, so a locale-sorted file is not sorted by the comparison the aggregator checks
    and the run would die claiming its own sorted input was unsorted. These identifiers are
    chosen to order differently under the two rules."""
    import sys as _sys

    _sys.path.insert(0, str(_PATH.parent.parent / "src"))
    from amazebio import similarity as sim

    tsv = tmp_path / "hits.tsv"
    tsv.write_text(
        "".join(
            f"s{i}\t{t}\t0.90\t0.90\t0.90\n"
            for i, t in enumerate(["UniRef100_b2", "UniRef100_B1", "UniRef100_a1", "UniRef100_A2"])
        )
    )
    out = tool._sort_by_target(tsv, tmp_path)
    targets = [line.split("\t")[1] for line in out.read_text().splitlines()]
    assert targets == sorted(targets), "byte order, which is what the aggregator checks"

    # The whole point: the sorted file must feed the aggregator without an order complaint.
    stream = sim.TargetStream().extend(tool._stream_hit_rows(out)).close()
    assert stream.records[1] == 4


def test_streaming_a_hit_table_reproduces_the_in_memory_ledger(tmp_path) -> None:
    import sys as _sys

    _sys.path.insert(0, str(_PATH.parent.parent / "src"))
    from amazebio import similarity as sim

    rows = [
        ("q1", "recC", 0.95, 0.9, 0.9),
        ("q2", "recA", 0.71, 0.9, 0.9),
        ("q3", "recA", 0.93, 0.9, 0.9),
        ("q4", "recB", 0.80, 0.2, 0.9),
    ]
    tsv = tmp_path / "hits.tsv"
    tsv.write_text("".join(f"{q}\t{t}\t{f}\t{qc}\t{tc}\n" for q, t, f, qc, tc in rows))

    ledger = sim.RecordLedger().extend(sim.HitRow(q, t, f, qc, tc) for q, t, f, qc, tc in rows)
    stream = (
        sim.TargetStream()
        .extend(tool._stream_hit_rows(tool._sort_by_target(tsv, tmp_path)))
        .close()
    )
    for mode in sim.COVERAGE_READINGS:
        assert stream.bands[mode] == ledger.counts_by_band(mode)


def test_staging_reports_progress_as_it_goes(tmp_path) -> None:
    """The corpus pass got a heartbeat this morning because an unobservable hour cost a day.
    Staging was written after that, got none, and then hung for 25 minutes — so the blindness
    came back inside the code added to cure it. Every step that can take minutes reports."""
    from amazebio import seeds as sd

    seed, shards = _staged_files(tmp_path)
    client = _StageS3()
    tool._stage_sample(
        _stage_args(tmp_path),
        client,
        "buk",
        "corpora",
        seed,
        shards,
        sd.SeedCounts(clusters=10, viral_seeded=4),
        [1, 1],
        [8, 8],
    )
    progress = [k for k in client.puts if k.endswith("progress-caps.json")]
    assert progress, "staging wrote no progress object"


def test_large_uploads_prefer_a_managed_transfer(tmp_path) -> None:
    """A 450 MB single PUT is one long call a read timeout can strand and a retry restarts
    from zero. upload_file chunks, retries parts and streams from disk."""
    calls: list[tuple[str, str]] = []

    class _Managed:
        def upload_file(self, filename: str, bucket: str, key: str) -> None:
            calls.append(("upload_file", key))

        def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
            calls.append(("put_object", Key))

    path = tmp_path / "shard.faa"
    path.write_bytes(b">x\nMKVL\n")
    tool._put_large(_Managed(), "buk", "corpora/k/shard.faa", path)
    assert calls == [("upload_file", "corpora/k/shard.faa")]

    # The fallback keeps local stand-ins and tests working, where files are bytes not gigabytes.
    class _Plain:
        def put_object(self, Bucket: str, Key: str, Body: bytes) -> None:
            calls.append(("put_object", Key))

    tool._put_large(_Plain(), "buk", "corpora/k/shard.faa", path)
    assert calls[-1] == ("put_object", "corpora/k/shard.faa")


def test_sidecars_can_be_staged_into_an_existing_sample_without_rewriting_it(tmp_path) -> None:
    """The sample staged before D-142 has no strata sidecars, and its shards must not be
    rewritten to add them — an overwrite in this bucket destroys the earlier object. Without
    this every later band pays the 52-minute corpus pass again just to rebuild them, and
    D-134's band 2 is six launches."""
    seed = tmp_path / "viral-seeds.faa"
    seed.write_bytes(b">UniRef100_S1\nMKVL\n")
    shards = []
    sidecars = []
    for i in range(2):
        s = tmp_path / f"shard-{i:02d}.faa"
        s.write_bytes(b">UniRef100_C\nMKVLAA\n")
        shards.append(s)
        side = s.with_suffix(".taxids.tsv")
        side.write_bytes(b"UniRef100_C\t11157\n")
        sidecars.append(side)
    seed_side = seed.with_suffix(".taxids.tsv")
    seed_side.write_bytes(b"UniRef100_S1\t11157\n")
    sidecars.append(seed_side)

    prefix = f"corpora/{tool.shardstore.sample_prefix('2023_02', 'uniref100', 40)}"
    # Everything the earlier staging wrote is already present, including the manifest.
    client = _StageS3(
        existing=[f"{prefix}/{p.name}" for p in (seed, *shards)]
        + [f"{prefix}/{tool.shardstore.MANIFEST_NAME}"]
    )
    uri = tool._stage_sample(
        _stage_args(tmp_path, stage_sidecars_only=True),
        client,
        "bucket",
        "corpora",
        seed,
        shards,
        tool.seeds.SeedCounts(clusters=2, viral_seeded=1),
        [1, 1],
        [6, 6],
        sidecars,
    )
    # Scoped to the sample prefix: the progress heartbeat is a separate key and a legitimate
    # write, and asserting on every put would fail for the wrong reason.
    written = {k for k in client.puts if k.startswith(prefix + "/")}
    assert written == {f"{prefix}/{p.name}" for p in sidecars}, "only the sidecars go up"
    assert not any(k.endswith(".faa") for k in written), "the sample's own objects are untouched"
    assert tool.shardstore.MANIFEST_NAME not in "".join(written), "the manifest is left alone"
    assert uri.endswith(tool.shardstore.MANIFEST_NAME)


def test_staging_sidecars_only_does_not_need_stage_sample_and_refuses_both(tmp_path) -> None:
    """The flag was unreachable when first written: staging was gated on --stage-sample alone,
    so --stage-sidecars-only bought a launch that staged nothing. Caught in review of the
    handoff that told the next worker to run it."""
    argv = [
        "--measure",
        "band",
        "--source",
        str(tmp_path / "x.xml.gz"),
        "--taxdump",
        str(tmp_path / "t.zip"),
        "--stage-sample",
        "--stage-sidecars-only",
    ]
    with pytest.raises(SystemExit, match="Pick one"):
        tool.main(argv)

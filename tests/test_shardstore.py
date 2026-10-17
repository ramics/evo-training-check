"""Tests for the staged corpus sample.

The staged sample's whole job is to let a search run skip a 52-minute corpus pass without
anyone having to wonder which bytes it searched. So the tests that matter are the refusals:
a wrong digest, a wrong size, a manifest from another version, a sample that claims more
clusters than it was drawn from. A staged sample that loads when it should not is worse than
no staging at all, because the output looks like a measurement either way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amazebio import shardstore as ss


def _sample(tmp: Path, buckets: int = 2) -> tuple[ss.ShardManifest, dict[str, Path]]:
    seed = tmp / "viral-seeds.faa"
    seed.write_bytes(b">UniRef100_S1\nMKVL\n")
    prefix = ss.sample_prefix("2023_02", "uniref100", 40)
    local = {}
    seed_key = f"{prefix}/{seed.name}"
    local[seed_key] = seed
    shards = []
    for i in range(buckets):
        p = tmp / f"shard-{i:02d}.faa"
        p.write_bytes(f">UniRef100_C{i}\nMKVLAAAA\n".encode())
        key = f"{prefix}/{p.name}"
        local[key] = p
        shards.append(ss.describe_shard(p, key, index=i, clusters=1, residues=8))
    manifest = ss.ShardManifest(
        release="2023_02",
        tier="uniref100",
        sample_rate=40,
        buckets=buckets,
        corpus_clusters=350_950_053,
        viral_seeded_clusters=3_159_223,
        seed_fasta=ss.describe(seed, seed_key),
        shards=shards,
        code_commit="abc123",
        taxdump_pin="2023-04-01",
    )
    return manifest, local


def test_a_staged_sample_round_trips_through_json(tmp_path: Path) -> None:
    manifest, _ = _sample(tmp_path)
    back = ss.ShardManifest.from_json(manifest.to_json())
    assert back.corpus_clusters == 350_950_053
    assert back.viral_seeded_clusters == 3_159_223
    assert back.shard_count() == 2
    assert back.residues() == 16
    assert back.seed_fasta.sha256 == manifest.seed_fasta.sha256
    assert back.taxdump_pin == "2023-04-01"


def test_the_denominators_survive_staging(tmp_path: Path) -> None:
    """A run that skips the corpus pass has no other source for them, and a numerator with no
    denominator is not a rate (D-100, D-109)."""
    manifest, _ = _sample(tmp_path)
    back = ss.ShardManifest.from_json(manifest.to_json())
    assert back.corpus_clusters == manifest.corpus_clusters
    assert back.viral_seeded_clusters == manifest.viral_seeded_clusters


def test_verify_accepts_the_bytes_it_staged(tmp_path: Path) -> None:
    manifest, local = _sample(tmp_path)
    ss.verify_all(manifest, local)  # must not raise


def test_a_modified_shard_is_refused(tmp_path: Path) -> None:
    """The corpus bucket cannot delete, so a bad shard can only be superseded. Verifying on
    load is the only thing standing between that and a published number."""
    manifest, local = _sample(tmp_path)
    target = local[manifest.shards[1].key]
    target.write_bytes(b">UniRef100_C1\nMKVLAAAB\n")  # same length, different bytes
    with pytest.raises(ss.ShardStoreError, match="sha256"):
        ss.verify_all(manifest, local)


def test_a_truncated_shard_is_refused_on_size_before_hashing(tmp_path: Path) -> None:
    manifest, local = _sample(tmp_path)
    local[manifest.shards[0].key].write_bytes(b">UniRef100_C0\n")
    with pytest.raises(ss.ShardStoreError, match="bytes"):
        ss.verify_all(manifest, local)


def test_a_modified_seed_set_is_refused(tmp_path: Path) -> None:
    """Shards paired with a seed set from another release or taxonomy pin would be
    undetectable in the output, so the seed set is verified like everything else."""
    manifest, local = _sample(tmp_path)
    local[manifest.seed_fasta.key].write_bytes(b">UniRef100_S9\nWWWW\n")
    with pytest.raises(ss.ShardStoreError):
        ss.verify_all(manifest, local)


def test_a_missing_object_is_refused_rather_than_skipped(tmp_path: Path) -> None:
    manifest, local = _sample(tmp_path)
    del local[manifest.shards[0].key]
    with pytest.raises(ss.ShardStoreError, match="not fetched"):
        ss.verify_all(manifest, local)


def test_a_manifest_from_another_version_is_refused(tmp_path: Path) -> None:
    manifest, _ = _sample(tmp_path)
    raw = json.loads(manifest.to_json())
    raw["version"] = ss.MANIFEST_VERSION + 1
    with pytest.raises(ss.ShardStoreError, match="manifest version"):
        ss.ShardManifest.from_json(json.dumps(raw))


def test_a_malformed_manifest_is_refused(tmp_path: Path) -> None:
    manifest, _ = _sample(tmp_path)
    raw = json.loads(manifest.to_json())
    del raw["seed_fasta"]
    with pytest.raises(ss.ShardStoreError, match="missing or malformed"):
        ss.ShardManifest.from_json(json.dumps(raw))


def test_a_sample_larger_than_its_corpus_is_refused(tmp_path: Path) -> None:
    manifest, local = _sample(tmp_path)
    manifest.corpus_clusters = 1
    with pytest.raises(ss.ShardStoreError, match="more than"):
        ss.verify_all(manifest, local)


def test_a_bucket_count_disagreeing_with_the_shard_list_is_refused(tmp_path: Path) -> None:
    manifest, local = _sample(tmp_path)
    manifest.buckets = 3
    with pytest.raises(ss.ShardStoreError, match="buckets"):
        ss.verify_all(manifest, local)


def test_shard_indices_must_be_the_whole_partition(tmp_path: Path) -> None:
    """Shards 1..k is only a valid sample at k times the rate if the partition is complete;
    a gap would make every cumulative target silently mis-scaled."""
    manifest, local = _sample(tmp_path)
    manifest.shards[1] = ss.StagedShard(
        key=manifest.shards[1].key,
        sha256=manifest.shards[1].sha256,
        bytes=manifest.shards[1].bytes,
        index=5,
        clusters=1,
        residues=8,
    )
    with pytest.raises(ss.ShardStoreError, match="indices"):
        ss.verify_all(manifest, local)


def test_the_staging_prefix_separates_rates_and_releases() -> None:
    """The bucket cannot delete, so two samples must never be able to collide by name."""
    a = ss.sample_prefix("2023_02", "uniref100", 40)
    b = ss.sample_prefix("2023_02", "uniref100", 50)
    c = ss.sample_prefix("2021_04", "uniref100", 40)
    d = ss.sample_prefix("2023_02", "uniref90", 40)
    assert len({a, b, c, d}) == 4


def test_plan_uploads_names_every_object_before_anything_is_written(tmp_path: Path) -> None:
    """In a bucket with no DeleteObject the moment to be sure about a key is before the put."""
    seed = tmp_path / "viral-seeds.faa"
    seed.write_bytes(b">x\nM\n")
    shards = [tmp_path / "shard-00.faa", tmp_path / "shard-01.faa"]
    for p in shards:
        p.write_bytes(b">y\nM\n")
    plan = ss.plan_uploads("samples/a1-6/uniref100/2023_02/rate40", shards, seed)
    assert [k for _, k in plan] == [
        "samples/a1-6/uniref100/2023_02/rate40/viral-seeds.faa",
        "samples/a1-6/uniref100/2023_02/rate40/shard-00.faa",
        "samples/a1-6/uniref100/2023_02/rate40/shard-01.faa",
    ]
    assert len({k for _, k in plan}) == len(plan), "no two objects may share a key"


class _S3:
    def __init__(self, keys: list[str], page: int = 2) -> None:
        self.keys, self.page = keys, page

    def list_objects_v2(self, **kw: object) -> dict:
        start = 0
        token = kw.get("ContinuationToken")
        if token is not None:
            start = int(str(token))
        chunk = self.keys[start : start + self.page]
        nxt = start + self.page
        return {
            "Contents": [{"Key": k} for k in chunk],
            "IsTruncated": nxt < len(self.keys),
            "NextContinuationToken": str(nxt),
        }


def test_existing_keys_pages_through_everything() -> None:
    """A staging run checks for collisions before writing, so a half-read listing would be a
    collision check that passes by not looking."""
    keys = [f"samples/a1-6/uniref100/2023_02/rate40/shard-{i:02d}.faa" for i in range(5)]
    assert ss.existing_keys(_S3(keys), "buk", "samples/") == set(keys)


def test_the_already_staged_manifest_still_loads_after_the_counter_rename(
    tmp_path: Path,
) -> None:
    """D-139 renamed `SeedCounts`' counters; the staged 2.5% sample predates that rename.

    That object is in a bucket with no DeleteObject, so it cannot be rewritten, and it is the
    input A1.8's pass reads. Its `seed_counts` carries the old `viral_seeded` spelling, so the
    self-consistency check accepts either — the alternative was a manifest version bump, which
    `from_json` turns into an outright refusal of exactly the manifest we need.
    """
    manifest, _ = _sample(tmp_path)
    manifest.seed_counts = {"clusters": 350_950_053, "viral_seeded": 3_159_223}
    ss.ShardManifest.from_json(manifest.to_json()).check_self_consistent()


def test_the_new_counter_spelling_is_checked_too(tmp_path: Path) -> None:
    manifest, _ = _sample(tmp_path)
    manifest.seed_counts = {"clusters": 350_950_053, "seeded": 3_159_223}
    ss.ShardManifest.from_json(manifest.to_json()).check_self_consistent()


def test_a_disagreeing_counter_still_fails_under_either_spelling(tmp_path: Path) -> None:
    """Accepting two spellings must not accept a manifest that contradicts itself."""
    for spelling in ("seeded", "viral_seeded"):
        manifest, _ = _sample(tmp_path)
        manifest.seed_counts = {"clusters": 350_950_053, spelling: 999}
        with pytest.raises(ss.ShardStoreError, match="disagrees with itself"):
            ss.ShardManifest.from_json(manifest.to_json()).check_self_consistent()

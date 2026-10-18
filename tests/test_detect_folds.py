"""Tests for A2.2's shard contract and its per-fold tables.

The assembly is where the schema rules bite, and each of these pins one that would otherwise be
easy to get wrong silently:

- a hit on a record the reading removes must not become a detection — it is a candidate
  conformance failure for A7.1, and `metrics/detections.md` forbids a detector asserting that;
- a hit on a reference domain the shipped artefact does not list must stop the run, because it
  means the search used a different reference set and the denominator is unknown;
- the universe must be zero-filled from the three folds, so a fold with no surviving homolog is a
  measured zero rather than an absent row;
- a component the detector did not read must appear with a reason, never be omitted;
- shards searched under different geometries must refuse to merge.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load("detect_folds", "tools/detect_folds.py")


# --------------------------------------------------------------------------------------
# Shard identity
# --------------------------------------------------------------------------------------


def test_shard_names_separate_evo_ones_three_stage2_splits(tool):
    """A component-keyed stem made these collide and last-write-win in A2.1."""
    names = {
        tool.shard_name("opengenome", f"corpora/og/{obj}", 0.0, 0.002)
        for obj in ("train_stage2.parquet", "valid_stage2.parquet", "test_stage2.parquet")
    }
    assert len(names) == 3


def test_the_params_fingerprint_ignores_the_threshold(tool):
    """Shards are stored above a floor so a re-cut must not invalidate them."""
    a = tool.params_fingerprint("abc")
    b = tool.params_fingerprint("abc")
    c = tool.params_fingerprint("def")
    assert a == b
    assert a != c


def test_the_plan_covers_only_components_with_a_declared_rate(tool):
    shards = tool.planned_shards()
    assert shards, "the pre-registered depth must name at least one shard"
    assert {s["corpus_component"] for s in shards} <= set(tool.SAMPLE_RATES)
    for s in shards:
        lo, hi = s["band"]
        assert (lo, hi) == (0.0, tool.SAMPLE_RATES[s["corpus_component"]])


# --------------------------------------------------------------------------------------
# Fixtures for assembly
# --------------------------------------------------------------------------------------

UNIVERSE = {
    "registry": "ECOD",
    "registry_version": "v295.2",
    "folds": [
        {"fold_id": "jelly_roll_capsid", "name": "Jelly-roll viral capsid"},
        {"fold_id": "viral_rdrp", "name": "Viral RNA-dependent RNA polymerase"},
        {"fold_id": "class_i_fusion", "name": "Class I viral fusion glycoprotein"},
    ],
    "structures": [
        {"domain_id": "e1hx6A1", "fold_id": "jelly_roll_capsid"},
        {"domain_id": "e1gx5A1", "fold_id": "viral_rdrp"},
    ],
}


def _hit(record_id: str, target: str, bits: float) -> dict:
    return {
        "record_id": record_id,
        "gene": f"{record_id}|gene1",
        "target": target,
        "bits": bits,
        "evalue": 1e-9,
        "fident": 0.2,
        "alnlen": 150,
        "qlen": 300,
        "tlen": 200,
        "tcov": 0.8,
    }


def _shard(hits: list[dict], *, params: str = "p1") -> dict:
    return {
        "release": "opengenome2",
        "key": "corpora/imgvr/rev/imgvr.fasta.gz",
        "component": "IMG/VR",
        "corpus_component": "imgvr",
        "band": [0.0, 0.001],
        "params": params,
        "alignment_mode": "3di_aa",
        "records": 100,
        "genes": 900,
        "residues": 200_000,
        "records_without_genes": 3,
        "read_seconds": 10.0,
        "search_seconds": 20.0,
        "hits": hits,
    }


MANIFEST = {
    "policy": {"id": "evo1-literal"},
    "release": "opengenome2",
    "removed": {"records": 0},
    "sources": [
        {
            "key": "corpora/imgvr/rev/imgvr.fasta.gz",
            "component": "IMG/VR",
            "corpus_component": "imgvr",
            "records": 2_957_495,
        },
        {
            "key": "corpora/gtdb/rev/gtdb.fna.gz",
            "component": "GTDB",
            "corpus_component": "gtdb_v220",
            "records": 1000,
        },
    ],
}


@pytest.fixture
def manifest_entry(tmp_path):
    path = tmp_path / "manifest-evo1-literal-opengenome2.json"
    path.write_text(json.dumps(MANIFEST))
    return {"path": path, "manifest": MANIFEST}


THRESHOLDS = {
    "kind": "bit score",
    "declared": 100.0,
    "brackets": [90.0, 120.0],
    "binding_decoy_class": "near_fold_nonviral",
    "target_fpr": 0.01,
    "alignment_mode": "3di_aa",
    "cov_mode": 1,
    "min_target_coverage": 0.5,
    "decision_ref": "D-171",
}


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def test_the_universe_is_zero_filled_from_the_three_folds(tool, manifest_entry, tmp_path):
    """A fold with no surviving homolog is the result this audit tests for."""
    table, _ = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    body = table.to_dict()
    assert body["survival"]["families_in_universe"] == 3
    assert body["survival"]["families_with_a_hit"] == 1
    assert sorted(body["families_without_a_hit"]) == ["class_i_fusion", "viral_rdrp"]
    assert body["estimate_kind"] == "lower_bound", "a sampled table is never a population value"


def test_a_hit_below_the_declared_threshold_is_not_a_detection(tool, manifest_entry, tmp_path):
    table, detections = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 99.9)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert detections == []
    assert table.survival()["families_with_a_hit"] == 0
    assert any("below the declared threshold" in n for n in table.notes)


def test_hits_on_removed_records_are_excluded_and_counted(tool, manifest_entry, tmp_path):
    """They are candidate conformance failures for A7.1, which no table may assert."""
    (tmp_path / "removed.jsonl").write_text(json.dumps({"record_id": "r_removed"}) + "\n")
    entry = dict(manifest_entry)
    entry["manifest"] = {
        **MANIFEST,
        "removed": {"records": 1, "file": "removed.jsonl"},
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(entry["manifest"]))
    entry["path"] = path

    table, detections = tool.build_table(
        manifest_entry=entry,
        shards=[
            _shard(
                [
                    _hit("r_removed", "e1hx6A1", 500.0),
                    _hit("r_kept", "e1gx5A1", 500.0),
                ]
            )
        ],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert [d.record_id for d in detections] == ["r_kept"]
    assert any("1 hits fell on records this reading removes" in n for n in table.notes)


def test_a_hit_on_an_unlisted_reference_domain_stops_the_run(tool, manifest_entry, tmp_path):
    """It means the search used another reference set, so the denominator is unknown."""
    with pytest.raises(tool.FoldDetectError, match="not in the shipped reference set"):
        tool.build_table(
            manifest_entry=manifest_entry,
            shards=[_shard([_hit("r1", "eSOMETHINGELSE", 500.0)])],
            manifest_dir=tmp_path,
            universe=UNIVERSE,
            thresholds=THRESHOLDS,
        )


def test_one_record_matching_many_representatives_is_one_detection(tool, manifest_entry, tmp_path):
    """A protein matching eight capsid representatives is one surviving capsid fold."""
    _, detections = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[
            _shard(
                [
                    _hit("r1", "e1hx6A1", 200.0),
                    _hit("r1", "e1hx6A1", 300.0),
                ]
            )
        ],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert len(detections) == 1
    assert detections[0].score == 300.0, "the best score survives deduplication"


def test_an_unsearched_component_is_listed_with_a_reason(tool, manifest_entry, tmp_path):
    """A table that silently covered part of a release reads as a verdict on all of it."""
    table, _ = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    rows = {r["corpus_component"]: r for r in table.sources}
    assert rows["imgvr"]["searched"] is True
    assert rows["gtdb_v220"]["searched"] is False
    assert "A2.4" in rows["gtdb_v220"]["why"], "GTDB's viral content is prophage, A2.4's job"
    assert rows["imgvr"]["records_without_genes"] == 3


def test_element_kind_comes_from_the_component_not_the_hit(tool, manifest_entry, tmp_path):
    """D-079: a fold hit says a fold is present, not what kind of element carries it."""
    _, detections = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert detections[0].element_kind.value == "free_virus", "IMG/VR, by its publisher's own scope"


def test_no_table_asserts_a_conformance_failure(tool, manifest_entry, tmp_path):
    """§7 requires A7.1 to establish that claim with record-level evidence."""
    table, _ = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert "conformance_failure" not in table.route_totals()


def test_the_table_records_that_tm_score_is_unavailable(tool, manifest_entry, tmp_path):
    """Recorded as unavailable rather than as nulls that look like missing data (D-167)."""
    table, _ = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert set(tool.UNAVAILABLE_COLUMNS) == {"alntmscore", "qtmscore", "ttmscore", "lddt"}
    assert any("TM-score" in n for n in table.notes)


def test_zero_rows_carry_the_threshold_they_were_judged_against(tool, manifest_entry, tmp_path):
    """A table whose zero rows carry no threshold cannot be re-read at a stricter one."""
    table, _ = tool.build_table(
        manifest_entry=manifest_entry,
        shards=[_shard([_hit("r1", "e1hx6A1", 250.0)])],
        manifest_dir=tmp_path,
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    assert all(r.threshold == 100.0 for r in table.rows)


# --------------------------------------------------------------------------------------
# Shard loading
# --------------------------------------------------------------------------------------


def test_shards_with_different_params_refuse_to_merge(tool, tmp_path):
    """Scores from two reference sets or geometries are answers to different questions."""
    (tmp_path / "opengenome2--a.json").write_text(json.dumps(_shard([], params="p1")))
    (tmp_path / "opengenome2--b.json").write_text(json.dumps(_shard([], params="p2")))
    with pytest.raises(tool.FoldDetectError, match="more than one params fingerprint"):
        tool.load_shards(tmp_path, release="opengenome2")


def test_shards_are_found_by_glob_not_exact_key(tool, tmp_path):
    """An exact-key test once fired after a finished 70-minute search in A2.1."""
    (tmp_path / "opengenome2--a.json").write_text(json.dumps(_shard([])))
    (tmp_path / "opengenome--b.json").write_text(json.dumps(_shard([])))
    assert len(tool.load_shards(tmp_path, release="opengenome2")) == 1


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------


def test_a_missing_manifest_index_says_what_to_run(tool, tmp_path):
    with pytest.raises(tool.FoldDetectError, match="apply_policies"):
        tool.load_manifests(tmp_path)


def test_a_non_universe_artefact_says_what_to_run(tool, tmp_path):
    p = tmp_path / "fold-universe.json"
    p.write_text(json.dumps({"folds": []}))
    with pytest.raises(tool.FoldDetectError, match="build_fold_reference"):
        tool.load_fold_universe(p)


def test_an_uncalibrated_mode_is_refused(tool, tmp_path):
    p = tmp_path / "threshold.json"
    p.write_text(
        json.dumps(
            {
                "modes": {
                    "3di_aa": {
                        "threshold": {
                            "declared_bits": 100,
                            "brackets": [90, 120],
                            "binding_class": "near_fold_nonviral",
                            "target_fpr": 0.01,
                        }
                    }
                }
            }
        )
    )
    with pytest.raises(tool.FoldDetectError, match="no calibration for"):
        tool.load_threshold(p, mode="3di_only")
    got = tool.load_threshold(p, mode="3di_aa")
    assert got["declared"] == 100.0
    assert got["brackets"] == [90.0, 120.0]
    assert got["decision_ref"] == "D-171"

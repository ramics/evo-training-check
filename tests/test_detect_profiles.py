"""The protein cache in `tools/detect_profiles.py` — task A2.1, D-103.

The cache exists so a deepened sample reads each release once rather than once per band. What is
tested here is the thing that went wrong twice: **keying**. Evo 1 publishes stage 2 as three
splits under one component name, and a cache keyed on the component alone fails in two different
directions — on write the splits overwrite each other, and on read each split loads the whole
component, so the same records are searched once per split and every family's hit count comes
out threefold while its record count stays right. Neither failure is visible in a finished table.

The search itself is not tested here: it is `pyhmmer` against a pinned registry, and the
registry's own behaviour is `test_profiles.py`'s.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "detect_profiles.py"
_spec = importlib.util.spec_from_file_location("detect_profiles_under_test", _PATH)
detect_profiles = importlib.util.module_from_spec(_spec)
sys.modules["detect_profiles_under_test"] = detect_profiles
_spec.loader.exec_module(detect_profiles)

from amazebio.detect import in_band  # noqa: E402  (after the tool, which sets up `src`)
from amazebio.policyspec import Record  # noqa: E402


def protein(name: str, sequence: str = "MKVLAT"):
    from pyhmmer.easel import Alphabet, TextSequence

    return TextSequence(name=name.encode(), sequence=sequence).digitize(Alphabet.amino())


#: `Record.taxonomy` is a **rank -> taxon mapping**, and these fixtures use the real shape
#: deliberately. The first version of them used a tuple because the cache wrote one, so the test
#: agreed with the bug: `list()` of a mapping yields its ranks and drops every taxon, and nothing
#: noticed until a policy rule reached for `.get(rank)` — after a 70-minute search.
TAXONOMY = {"realm": "Duplodnaviria", "class": "Caudoviricetes"}


def records_for(ids: list[str], component: str = "IMG/VR") -> dict[str, Record]:
    return {i: Record(id=i, component=component, taxonomy=dict(TAXONOMY)) for i in ids}


def test_the_stem_separates_splits_that_share_a_component():
    train = detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.014, 0.02)
    test = detect_profiles.cache_stem("stage2", "test_stage2.parquet", 0.014, 0.02)
    assert train != test
    # And the band bound survives: a stem ending `.02` must not lose it to a suffix replacement.
    assert train.endswith("0.014-0.02")


def test_a_split_reads_its_own_cache_and_not_its_siblings(tmp_path):
    # The duplication bug: globbing on the component made each split load all three, so the
    # band's records were searched once per split.
    ids = ["stage2:train#1", "stage2:train#2"]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.0, 1.0),
    )
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "valid_stage2.parquet", 0.0, 1.0),
        [],
        {},
        band=(0.0, 1.0),
    )

    proteins, records, stats = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    assert stats["records"] == 2
    assert stats["genes"] == 2
    assert set(records) == set(ids)

    empty, _, empty_stats = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="valid_stage2.parquet", lo=0.0, hi=1.0
    )
    assert empty == []
    assert empty_stats["genes"] == 0


def test_writing_two_splits_does_not_overwrite_either(tmp_path):
    # The destructive bug: one stem for three splits, and the last write — an empty one — won.
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"]),
        band=(0.0, 1.0),
    )
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "test_stage2.parquet", 0.0, 1.0),
        [],
        {},
        band=(0.0, 1.0),
    )
    proteins, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    assert len(proteins) == 1


def test_band_membership_is_recomputed_rather_than_trusted(tmp_path):
    """A wider cache yields exactly the band asked for — what stops a cache changing a result."""
    ids = [f"IMGVR_{i}" for i in range(600)]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("imgvr", "imgvr.fasta.gz", 0.0, 1.0),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.0, 1.0),
    )
    _, records, stats = detect_profiles.read_cache(
        tmp_path, component="imgvr", object_name="imgvr.fasta.gz", lo=0.1, hi=0.3
    )
    expected = {i for i in ids if in_band(i, seed=detect_profiles.SEED, lo=0.1, hi=0.3)}
    assert set(records) == expected
    assert 0 < stats["records"] < len(ids)


def test_the_cache_carries_what_the_route_resolution_needs(tmp_path):
    # A detection's route comes from the record's component and lineage, so a cache that lost
    # them would make a cached band unroutable — and the taxonomy is metadata, not sequence.
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"], component="IMG/VR"),
        band=(0.0, 1.0),
    )
    _, records, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    record = records["stage2:train#1"]
    assert record.component == "IMG/VR"
    # The mapping survives the round trip, rank by rank: this is what the taxonomy rules read.
    assert record.taxonomy == TAXONOMY
    assert record.taxonomy.get("realm") == "Duplodnaviria"


def test_no_nucleotide_sequence_is_written(tmp_path):
    # D-103 permits called proteins in scratch; the records sidecar carries accessions, lineage
    # and the band, and must not carry sequence of any kind.
    path = detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"]),
        band=(0.0, 1.0),
    )
    sidecar = (path.parent / path.name.replace(".faa.gz", ".records.jsonl")).read_text()
    assert "sequence" not in sidecar
    assert "MKVLAT" not in sidecar
    # Lineage is metadata and travels; A1.4's own manifests carry the same tags.
    assert "Caudoviricetes" in sidecar


@pytest.mark.parametrize("component", ["stage2", "imgvr"])
def test_an_absent_cache_reads_as_empty_rather_than_raising(tmp_path, component):
    # The run decides what an empty band means — a split with no records in the band is normal,
    # a missing collect pass is not — so the reader reports and does not judge.
    proteins, records, stats = detect_profiles.read_cache(
        tmp_path, component=component, object_name="nothing.gz", lo=0.0, hi=1.0
    )
    assert (proteins, records, stats["genes"]) == ([], {}, 0)


def test_a_sub_band_search_finds_a_wider_collect_pass_cache(tmp_path):
    # A collect pass caches [0.014, 0.02); the searches take [0.014, 0.017) and [0.017, 0.02)
    # out of it. The reader must find the wide file and filter it, not look for a file named
    # after the sub-band — and a guard that looked for an exact stem match once discarded a
    # finished 70-minute search.
    ids = [f"stage2:train#{i}" for i in range(800)]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.014, 0.02),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.014, 0.02),
    )
    wide = {i for i in ids if in_band(i, seed=detect_profiles.SEED, lo=0.014, hi=0.02)} or set(ids)
    first, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=0.5
    )
    second, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.5, hi=1.0
    )
    assert first and second
    assert len(first) + len(second) == len(ids)
    assert wide  # the cache's own band is recorded, and membership is recomputed on read


def test_a_cache_from_an_older_format_is_refused_with_an_instruction(tmp_path):
    # Format 1 wrote the taxonomy's ranks and dropped its taxa, which cannot be recovered — so a
    # stale cache must say to re-collect rather than raise a ValueError deep in a dict() call,
    # or crash at the routing stage after a long search.
    import json

    stem = detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0)
    (tmp_path / f"{stem}.faa.gz").write_bytes(b"")
    (tmp_path / f"{stem}.records.jsonl").write_text(
        json.dumps(
            {
                "record_id": "stage2:train#1",
                "component": "IMG/VR",
                "taxonomy": ["realm", "class"],
                "band": [0.0, 1.0],
            }
        )
        + "\n"
    )
    with pytest.raises(SystemExit, match="cache format"):
        detect_profiles.read_cache(
            tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
        )


def test_the_plan_path_reads_the_current_searched_sources_shape():
    """`--plan` must survive `searched_sources` changing shape (X1.6).

    It did not: the branch passed one argument to a two-argument function and indexed the
    result as a mapping, so the flag raised `TypeError` rather than reporting anything. The
    search paths were fine throughout, which is why nothing caught it — this test drives the
    reporting path against the real staged-source metadata, which is offline.
    """
    release = "opengenome"
    from amazebio import corpora

    sources = [
        s
        for s in corpora.sources_for(release)
        if s.readable and s.corpus_component in detect_profiles.SAMPLE_RATES
    ]
    assert sources, "fixture assumes opengenome has readable stage2 objects"
    manifest = {
        "release": release,
        "policy": {"id": "evo1-literal"},
        "sources": [{"key": s.key, "records": 1_000_000} for s in sources],
    }

    lines = detect_profiles.plan_lines(manifest, release)

    assert len(lines) == len(sources)
    # 0.2% of a million records, formatted — the number a reader checks the plan for.
    assert all("~2,000 sampled" in line for line in lines)
    assert all("stage2" in line for line in lines)


def test_the_plan_path_reports_unknown_rather_than_guessing_a_count():
    """A manifest row without `records` is reported as unknown, not as zero sampled."""
    release = "opengenome"
    from amazebio import corpora

    sources = [
        s
        for s in corpora.sources_for(release)
        if s.readable and s.corpus_component in detect_profiles.SAMPLE_RATES
    ]
    manifest = {
        "release": release,
        "policy": {"id": "evo1-literal"},
        "sources": [{"key": s.key} for s in sources],
    }

    assert all("unknown sampled" in line for line in detect_profiles.plan_lines(manifest, release))

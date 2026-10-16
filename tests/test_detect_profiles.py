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


def records_for(ids: list[str], component: str = "IMG/VR") -> dict[str, Record]:
    return {i: Record(id=i, component=component, taxonomy=("r__Duplodnaviria",)) for i in ids}


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
    expected = {
        i for i in ids if in_band(i, seed=detect_profiles.SEED, lo=0.1, hi=0.3)
    }
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
    assert record.taxonomy == ("r__Duplodnaviria",)


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


@pytest.mark.parametrize("component", ["stage2", "imgvr"])
def test_an_absent_cache_reads_as_empty_rather_than_raising(tmp_path, component):
    # The run decides what an empty band means — a split with no records in the band is normal,
    # a missing collect pass is not — so the reader reports and does not judge.
    proteins, records, stats = detect_profiles.read_cache(
        tmp_path, component=component, object_name="nothing.gz", lo=0.0, hi=1.0
    )
    assert (proteins, records, stats["genes"]) == ([], {}, 0)

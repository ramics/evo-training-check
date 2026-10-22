"""The equal-rate comparison in `tools/equal_rate_pair.py` — task A3.2, D-247.

The figures themselves are a count of distinct families, which the module tests of `quantify`
already cover. What these cover is the three refusals, because the tool's whole purpose is that
a pairing cannot be made from measurements at different depths: if a part names the wrong
release, or a source inside it was sampled at a rate the row does not claim, the comparison is
not equal-rate and publishing it would be worse than not having it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "equal_rate_pair.py"
_spec = importlib.util.spec_from_file_location("equal_rate_pair_under_test", _PATH)
equal_rate_pair = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = equal_rate_pair
_spec.loader.exec_module(equal_rate_pair)


def part(release: str = "opengenome", rate: float = 0.002) -> dict[str, object]:
    return {
        "release": release,
        "sources": [
            {"searched": True, "sample_rate": rate},
            {"searched": False, "why": "host-side"},
        ],
        "tables": {
            "evo1-literal|pfam": [
                {"family_id": "PF00001", "record_id": "stage2:train_stage2.parquet#1"},
                {"family_id": "PF00001", "record_id": "stage2:train_stage2.parquet#2"},
                {"family_id": "PF00002", "record_id": "stage2:train_stage2.parquet#3"},
            ]
        },
    }


def test_counts_distinct_families_and_rows_by_prefix() -> None:
    families, prefixes = equal_rate_pair.families_in_part(part(), "opengenome")
    assert families == 2
    assert prefixes == {"stage2": 3}


def test_a_part_naming_another_release_is_refused() -> None:
    """D-245 was rows from one release counted in another's table; this is the same question
    asked of the part itself."""
    with pytest.raises(SystemExit, match="opengenome2"):
        equal_rate_pair.families_in_part(part(release="opengenome2"), "opengenome")


def test_accession_prefixes_show_which_corpus_the_rows_came_from() -> None:
    doc = part()
    doc["tables"]["evo1-literal|pfam"].append(
        {"family_id": "PF00003", "record_id": "IMGVR_1234567"}
    )
    _families, prefixes = equal_rate_pair.families_in_part(doc, "opengenome")
    assert prefixes == {"stage2": 3, "IMGVR": 1}


class _FakeStore:
    """Serves the four inputs and the headline from a dict of key to document."""

    def __init__(self, docs: dict[str, object]) -> None:
        self.docs = docs

    def download_file(self, _bucket: str, key: str, dest: str) -> None:
        import json

        name = key[len(equal_rate_pair.PREFIX) :]
        pathlib.Path(dest).write_text(json.dumps(self.docs[name]))


def _protein_table(rate: float, hits: int) -> dict[str, object]:
    return {
        "sample": {"rate": rate},
        "survival": {"families_with_a_hit": hits, "families_in_universe": 13679},
    }


def _docs(*, protein_rate: float = 0.002) -> dict[str, object]:
    return {
        "a2-1/parts/part-opengenome-0-1.json": part("opengenome", 0.002),
        "a2-1/parts/part-opengenome2-0-1.json": part("opengenome2", 0.001),
        "a2-1/detections-rvdb-prot-evo1-literal-opengenome.json": _protein_table(protein_rate, 572),
        "a2-1/detections-rvdb-prot-evo1-literal-opengenome2.json": _protein_table(0.001, 1456),
        "a3-2/headline.json": {"groups": []},
    }


class _Manifest:
    def parameter(self, *_args: object, **_kwargs: object) -> None:
        return None


def test_build_pairs_each_release_at_one_rate(tmp_path: pathlib.Path) -> None:
    doc = equal_rate_pair.build(cache=tmp_path, client=_FakeStore(_docs()), manifest=_Manifest())
    assert [p["rate"] for p in doc["pairs"]] == [0.002, 0.001]
    first = doc["pairs"][0]
    assert first["nucleotide"]["families_with_a_hit"] == 2
    assert first["protein"]["families_with_a_hit"] == 572
    assert 0.0 < first["protein"]["ci_low"] < first["protein"]["fraction"]


def test_a_protein_table_at_another_rate_is_refused(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit, match="rate"):
        equal_rate_pair.build(
            cache=tmp_path,
            client=_FakeStore(_docs(protein_rate=0.02)),
            manifest=_Manifest(),
        )

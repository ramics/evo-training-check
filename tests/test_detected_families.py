"""The refusals `tools/detected_families.py` makes, and the round trip into A4.5's reader.

The tool transcribes published tables, so its tests are about the checks rather than about
arithmetic: each of D-245, D-246 and D-247 was a table whose halves described different things,
and every assertion here is one of those failures made to happen on purpose.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


detected_families = _load("detected_families")
family_background = _load("family_background")


UNIVERSE = {f"PF{n:05d}" for n in range(1, 11)}


def table(
    *,
    key: str = "corpora/results/a2-1/detections-pfam-evo1-literal-opengenome.json",
    release: str = "opengenome",
    detector: str = "profile-hmmer",
    hit: tuple[str, ...] = ("PF00001", "PF00002"),
    claimed: int | None = None,
    missed: tuple[str, ...] | None = None,
    registry_version: str = "38.2",
) -> dict:
    rest = tuple(sorted(UNIVERSE - set(hit))) if missed is None else missed
    return {
        "_key": key,
        "task": "A2.1",
        "detector": detector,
        "registry": "pfam",
        "registry_version": registry_version,
        "manifest": {"release": release},
        "survival": {"families_with_a_hit": len(hit) if claimed is None else claimed},
        "families": [{"family_id": a} for a in hit],
        "families_without_a_hit": list(rest),
    }


def check(**kwargs):
    return detected_families.check(
        table(**kwargs), release="opengenome", detector="profile-hmmer", universe=UNIVERSE
    )


def test_a_well_formed_table_yields_its_detected_families():
    assert check() == {"PF00001", "PF00002"}


def test_a_table_naming_another_release_is_refused():
    with pytest.raises(SystemExit, match="not 'opengenome'"):
        check(release="opengenome2")


def test_a_table_naming_another_detector_is_refused():
    with pytest.raises(SystemExit, match="detector"):
        check(detector="provirus-genomad")


def test_a_table_from_another_registry_release_is_refused():
    with pytest.raises(SystemExit, match="expected pfam 38.2"):
        check(registry_version="37.0")


def test_a_table_that_disagrees_with_its_own_survival_block_is_refused():
    with pytest.raises(SystemExit, match="does not agree with itself"):
        check(claimed=9)


def test_the_two_lists_must_partition_the_universe():
    with pytest.raises(SystemExit, match="not a partition"):
        check(missed=("PF00003",))


def test_a_family_on_both_lists_is_refused():
    with pytest.raises(SystemExit, match="not a partition"):
        check(missed=tuple(sorted(UNIVERSE)))


def test_a_repeated_accession_is_refused():
    with pytest.raises(SystemExit, match="repeat"):
        check(hit=("PF00001", "PF00001"))


def test_readings_that_agree_reduce_to_one_set():
    sets = {p: {"PF00001"} for p in detected_families.POLICIES}
    assert detected_families.agreed(sets, "x") == {"PF00001"}


def test_readings_that_disagree_are_refused_rather_than_chosen_between():
    sets = {p: {"PF00001"} for p in detected_families.POLICIES}
    sets["evo1-strict"] = {"PF00002"}
    with pytest.raises(SystemExit, match="reading changes what survives"):
        detected_families.agreed(sets, "opengenome profile-hmmer")


def test_equal_counts_over_different_members_do_not_pass_as_agreement():
    """The check is on the sets. Three readings can agree on a count and not on a corpus."""
    sets = {p: {"PF00001", "PF00002"} for p in detected_families.POLICIES}
    sets["evo1-literal"] = {"PF00001", "PF00003"}
    assert len({len(s) for s in sets.values()}) == 1
    with pytest.raises(SystemExit):
        detected_families.agreed(sets, "x")


def test_a_commit_keyed_copy_is_refused_before_it_is_read():
    """A task prefix holds provenance twins of its own tables one segment deeper (D-246)."""

    class Boom:
        def get_object(self, **_):  # pragma: no cover - must not be reached
            raise AssertionError("the key should have been refused before any read")

    key = "corpora/results/a2-1/by-commit/abc123/detections-pfam-evo1-literal-opengenome.json"
    with pytest.raises(SystemExit, match="D-246"):
        detected_families.fetch(Boom(), key, Path("/nonexistent"))


def test_the_written_list_is_what_a4_5_s_reader_requires(tmp_path):
    """The two tools' contract: `read_detected` refuses a list that does not say what it is."""
    built = {
        "lists": [
            {
                "release": "opengenome",
                "detector": "profile-hmmer",
                "tasks": ["a2-1"],
                "source_keys": [
                    "corpora/results/a2-1/detections-pfam-evo1-literal-opengenome.json"
                ],
                "families": ["PF00001", "PF00002"],
            }
        ],
        "tables": [],
    }
    written = detected_families.write(built, tmp_path)
    listing = tmp_path / "detected-opengenome-profile-hmmer.txt"
    assert listing in written

    one = family_background.read_detected(listing, UNIVERSE)
    assert one["release"] == "opengenome"
    assert one["detector"] == "profile-hmmer"
    assert one["accessions"] == ["PF00001", "PF00002"]
    assert "a2-1" in (one["source_keys"] or "")

    sources = json.loads((tmp_path / "detected-sources.json").read_text())
    assert sources["lists"][0]["families"] == 2


def test_the_table_key_is_directly_under_the_task_prefix():
    key = detected_families.table_key("a2-4", "evo1-strict", "opengenome2")
    assert key == "corpora/results/a2-4/detections-pfam-evo1-strict-opengenome2.json"
    assert key.count("/") == 3

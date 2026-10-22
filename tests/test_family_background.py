"""Tests for `tools/family_background.py` — the refusals and the variant arithmetic.

The measurement itself is `amazebio.background`'s and is tested there. What is tested here is
the handover that the project has got wrong three times: a detected-family list that does not
say which release and which detector it came from (D-245), a list built against a different
registry, and a variant table that has to put the unjudgeable families on one side.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "family_background", _PATH.parent.parent / "tools" / "family_background.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

from amazebio import background  # noqa: E402

UNIVERSE = {"PF00001", "PF00002", "PF00003", "PF00004"}


def _list(tmp_path, body: str, name: str = "detected.txt") -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_a_list_must_say_which_release_and_detector_it_is(tmp_path):
    path = _list(tmp_path, "PF00001\nPF00002\n")
    with pytest.raises(SystemExit, match="release"):
        tool.read_detected(path, UNIVERSE)


def test_a_list_missing_only_the_detector_is_still_refused(tmp_path):
    path = _list(tmp_path, "# release: opengenome\nPF00001\n")
    with pytest.raises(SystemExit, match="detector"):
        tool.read_detected(path, UNIVERSE)


def test_an_accession_outside_the_universe_is_a_refusal(tmp_path):
    """The detected set is a subset of the denominator; a stranger means a different registry."""
    path = _list(tmp_path, "# release: opengenome\n# detector: profile\nPF00001\nPF99999\n")
    with pytest.raises(SystemExit, match="not in the pinned universe"):
        tool.read_detected(path, UNIVERSE)


def test_a_labelled_list_parses_and_deduplicates(tmp_path):
    path = _list(
        tmp_path,
        "# release: opengenome2\n# detector: profile+provirus\n"
        "# source_keys: corpora/results/a3-2/x.json\n"
        "PF00002\nPF00001\nPF00002\n\n",
    )
    read = tool.read_detected(path, UNIVERSE)
    assert read["release"] == "opengenome2"
    assert read["detector"] == "profile+provirus"
    assert read["source_keys"] == "corpora/results/a3-2/x.json"
    assert read["accessions"] == ["PF00001", "PF00002"]


def _table() -> dict[str, background.FamilyBackground]:
    return {
        # viral only
        "PF00001": background.FamilyBackground("PF00001", 5, 0),
        # shared, and every non-viral occurrence is marked integrated viral material
        "PF00002": background.FamilyBackground("PF00002", 2, 3, 3),
        # shared with cellular members
        "PF00003": background.FamilyBackground("PF00003", 1, 4, 0),
        # no curated occurrence at all
        "PF00004": background.FamilyBackground("PF00004", 0, 0),
    }


def test_each_variant_is_reported_with_and_without_the_unjudgeable_families():
    detected = {
        "release": "opengenome",
        "detector": "profile",
        "path": "x",
        "source_keys": None,
        "accessions": ["PF00001", "PF00002", "PF00003", "PF00004"],
    }
    out = tool.restrict(detected, _table())
    assert out["detected"] == 4
    assert (out["viral_only"], out["shared"], out["unmeasurable"]) == (1, 2, 1)
    assert out["shared_endogenous_only"] == 1
    assert out["variants"]["headline"] == {
        "excluding_unmeasurable": 4,
        "including_unmeasurable": 4,
    }
    assert out["variants"]["specific"] == {
        "excluding_unmeasurable": 1,
        "including_unmeasurable": 2,
    }
    assert out["variants"]["specific_plus_endogenous"] == {
        "excluding_unmeasurable": 2,
        "including_unmeasurable": 3,
    }


def test_the_variants_never_exceed_the_headline():
    """A variant is a subset of the detected set, so no cut may count more than it."""
    detected = {
        "release": "opengenome",
        "detector": "profile",
        "path": "x",
        "source_keys": None,
        "accessions": sorted(UNIVERSE),
    }
    out = tool.restrict(detected, _table())
    headline = out["variants"]["headline"]["including_unmeasurable"]
    for variant in tool.VARIANTS:
        for counts in out["variants"][variant].values():
            assert counts <= headline


def test_the_classes_partition_the_detected_set():
    detected = {
        "release": "opengenome",
        "detector": "profile",
        "path": "x",
        "source_keys": None,
        "accessions": sorted(UNIVERSE),
    }
    out = tool.restrict(detected, _table())
    assert out["viral_only"] + out["shared"] + out["unmeasurable"] == out["detected"]


def test_the_shared_share_is_taken_of_the_judgeable_families_only():
    """An unjudgeable family is not a quiet denominator: it belongs to neither side."""
    detected = {
        "release": "opengenome",
        "detector": "profile",
        "path": "x",
        "source_keys": None,
        "accessions": ["PF00001", "PF00002", "PF00003", "PF00004"],
    }
    out = tool.restrict(detected, _table())
    assert out["judgeable"] == 3
    assert out["shared_share_of_judgeable"] == pytest.approx(2 / 3)


def test_a_detected_set_the_curated_section_cannot_judge_at_all_has_no_share():
    detected = {
        "release": "opengenome",
        "detector": "profile",
        "path": "x",
        "source_keys": None,
        "accessions": ["PF00004"],
    }
    out = tool.restrict(detected, _table())
    assert out["judgeable"] == 0
    assert out["shared_share_of_judgeable"] is None
    assert tool.share(out["shared_share_of_judgeable"]) == "—"

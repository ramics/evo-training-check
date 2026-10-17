"""The scope and attribution logic in `tools/detect_proviruses.py` — task A2.4.

Two things in this tool decide whether its numbers mean anything, and neither is visible in a
finished table:

**Scope.** Which sources it searched, and whether the ones it did not are reported. A table that
silently covered part of a release reads as a verdict on all of it (D-080, D-116).

**Attribution.** Which record a protein found inside a provirus is counted on. geNomad invents a
name for every provirus it delineates; counting on that name instead of on the host genome would
inflate the denominator and attribute a prophage's families to a sequence that exists nowhere
outside the run (D-113).

The search itself is `pyhmmer` against a pinned registry and is `test_profiles.py`'s; geNomad's
output parsing is `test_proviruses.py`'s.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "detect_proviruses.py"
_spec = importlib.util.spec_from_file_location("detect_proviruses_under_test", _PATH)
dp = importlib.util.module_from_spec(_spec)
sys.modules["detect_proviruses_under_test"] = dp
_spec.loader.exec_module(dp)

from amazebio.survival import ElementKind, Route  # noqa: E402


def source(component, outcome="out_of_scope", **extra):
    return {
        "component": component.upper(),
        "corpus_component": component,
        "uniform_outcome": outcome,
        **extra,
    }


# --------------------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------------------


def test_both_releases_bacterial_components_are_searched():
    for component in ("gtdb_v220", "stage1_gtdb"):
        searched, skipped = dp.source_rows({"sources": [source(component)]})
        assert len(searched) == 1, component
        assert skipped == []


def test_a_viral_component_is_skipped_and_says_why():
    searched, skipped = dp.source_rows({"sources": [source("imgvr")]})
    assert searched == []
    assert skipped[0]["searched"] is False
    assert "A2.1" in skipped[0]["why"]


def test_every_source_appears_in_exactly_one_list():
    """None is dropped: an omitted component is an invisible gap in coverage."""
    components = ["gtdb_v220", "imgvr", "imgpr", "ncrna", "mrna", "organelles"]
    manifest = {"sources": [source(c) for c in components]}
    searched, skipped = dp.source_rows(manifest)
    assert len(searched) + len(skipped) == len(components)
    assert {s["corpus_component"] for s in skipped} | {
        s["corpus_component"] for s in searched
    } == set(components)


def test_an_unknown_component_is_skipped_with_a_reason_not_silently():
    _, skipped = dp.source_rows({"sources": [source("something_new")]})
    assert skipped[0]["why"]


def test_a_protein_corpus_says_the_detector_is_not_defined_over_it():
    """ESM3's proxy is protein: not a coverage gap but a category A2.4 cannot act on."""
    _, skipped = dp.source_rows({"sources": [source("uniref_2023_02")]})
    assert "not defined over" in skipped[0]["why"]


def test_a_manifest_with_no_bacterial_component_searches_nothing():
    searched, skipped = dp.source_rows({"sources": [source("uniref_2023_02"), source("pdb")]})
    assert searched == []
    assert len(skipped) == 2


# --------------------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------------------


def test_the_route_is_read_from_the_manifest_not_recomputed():
    assert dp.route_of_source(source("gtdb_v220", "out_of_scope")) is Route.OUT_OF_SCOPE


def test_the_strict_readings_wildcard_scope_gives_a_different_route():
    """The same prophage sits on different routes in different readings. That is the finding."""
    assert dp.route_of_source(source("gtdb_v220", "retained")) is Route.RETAINED_BY_DESIGN


def test_a_source_without_a_uniform_outcome_stops_the_run():
    with pytest.raises(dp.RunError, match="uniform_outcome"):
        dp.route_of_source({"corpus_component": "gtdb_v220"})


# --------------------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------------------


def test_a_provirus_protein_is_counted_on_its_genome():
    assert dp.host_of_protein("GCF_000001.1~3|provirus_1000_2000_7") == "GCF_000001.1"


def test_two_proviruses_in_one_genome_are_one_record():
    a = dp.host_of_protein("GCF_000001.1~0|provirus_1_100_1")
    b = dp.host_of_protein("GCF_000001.1~9|provirus_5000_6000_1")
    assert a == b == "GCF_000001.1"


def test_proviruses_in_different_genomes_are_different_records():
    a = dp.host_of_protein("GCF_000001.1~0|provirus_1_100_1")
    b = dp.host_of_protein("GCF_000002.1~0|provirus_1_100_1")
    assert a != b


def test_an_evo_1_derived_genome_key_round_trips():
    """Evo 1's genome is a WGS project accession (D-136); it must survive the same path."""
    header = dp.contig_header("JAHFAU01", 42)
    assert header == "JAHFAU01~42"
    assert dp.host_of_protein(f"{header}|provirus_1_100_1") == "JAHFAU01"


def test_a_genome_id_containing_the_separator_is_refused():
    """Silently accepting it would make the attribution back to the host ambiguous."""
    with pytest.raises(dp.RunError, match="ambiguous"):
        dp.contig_header("odd~name", 0)


def test_a_name_without_the_separator_still_yields_something():
    """Defensive: a header geNomad rewrote should not resolve to the empty string."""
    assert dp.host_of_protein("plaincontig|provirus_1_2_1") == "plaincontig"


# --------------------------------------------------------------------------------------
# Detections
# --------------------------------------------------------------------------------------


def test_a_detection_is_a_prophage_regardless_of_which_family_was_hit():
    """D-079/D-113: the kind comes from the provirus finder, never from the families hit."""
    (detection,) = dp.detections_from_hits(
        [{"profile": "PF05505.16", "record_id": "GCF_1", "score": 40.0}],
        registry_id="pfam",
        registry_version="38.2",
        thresholds={"PF05505": 20.0},
        route=Route.OUT_OF_SCOPE,
        profile_to_family={"PF05505.16": "PF05505"},
    )
    assert detection.element_kind is ElementKind.PROPHAGE
    assert detection.route is Route.OUT_OF_SCOPE
    assert detection.detector == "provirus-genomad"
    assert detection.family_id == "PF05505"


def test_a_profile_outside_the_pinned_universe_stops_the_run():
    """An unknown family id would change the denominator without showing it."""
    with pytest.raises(dp.RunError, match="pinned universe"):
        dp.detections_from_hits(
            [{"profile": "PF99999.1", "record_id": "GCF_1", "score": 40.0}],
            registry_id="pfam",
            registry_version="38.2",
            thresholds={},
            route=Route.OUT_OF_SCOPE,
            profile_to_family={},
        )


def test_notes_warn_when_no_concordance_was_run():
    notes = dp.table_notes(genomes=10, proviruses=3, concordance=None)
    assert any("one instrument" in n for n in notes)
    assert any("lower bound" in n.lower() for n in notes)

"""The A2.3 detector's manifest handling — A2.3, D-186.

Three things get tests here and each is a way the pass could produce a plausible wrong table
rather than an error: a component silently missing a reason, a reading that has gained a rule
reaching these genomes, and an absent component being reported as an unsearched one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_tool():
    """Import the tool by path; `tools/` is scripts rather than a package."""
    spec = importlib.util.spec_from_file_location("detect_eve", REPO / "tools" / "detect_eve.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["detect_eve"] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def test_every_component_the_manifest_can_carry_has_a_reason():
    """A component added later must arrive without a reason, not inherit a wrong one.

    Keyed on `corpus_component`, which is the name a manifest's `sources[]` row carries —
    **not** `opengenome.Component.name`. The two namespaces differ: Evo 2's prokaryotic
    component is `gtdb` in the release's component table and `gtdb_v220` in the source
    declarations. Checking the wrong one is how this test first reported a false gap.
    """
    from amazebio import corpora

    declared = {s.corpus_component for s in corpora.SOURCES}
    unexplained = sorted(
        name for name in declared if name != tool.COVERED and name not in tool.NOT_SEARCHED
    )
    assert not unexplained, (
        f"components with no recorded reason for not being searched: {unexplained}. "
        "Add one rather than letting the table omit the row."
    )


def test_no_reason_names_a_component_that_does_not_exist():
    """The other direction: a key that matches nothing is a row that will never be written.

    This is what a stale or misspelled key looks like, and it is silent — the table simply
    carries a default reason for the real component instead of the specific one.
    """
    from amazebio import corpora

    declared = {s.corpus_component for s in corpora.SOURCES}
    stale = sorted(name for name in tool.NOT_SEARCHED if name not in declared)
    assert not stale, f"reasons keyed on components no source declares: {stale}"


def test_the_covered_component_is_not_also_listed_as_unsearched():
    assert tool.COVERED not in tool.NOT_SEARCHED


def test_component_row_finds_the_covered_component():
    manifest = {
        "sources": [
            {"corpus_component": "imgvr"},
            {"corpus_component": tool.COVERED, "uniform": True, "uniform_outcome": "out_of_scope"},
        ]
    }
    row = tool.component_row(manifest)
    assert row is not None
    assert row["corpus_component"] == tool.COVERED


def test_component_row_is_none_for_a_release_without_it():
    """Evo 1 exposes no such component, and that must be distinguishable from an empty one."""
    assert tool.component_row({"sources": [{"corpus_component": "stage2"}]}) is None
    assert tool.component_row({}) is None


def test_outcome_is_read_from_the_manifest():
    from amazebio.policyspec import Outcome

    for name, expected in (
        ("out_of_scope", Outcome.OUT_OF_SCOPE),
        ("retained", Outcome.RETAINED),
    ):
        assert tool.outcome_of({"uniform": True, "uniform_outcome": name}) is expected


def test_a_non_uniform_component_stops_the_run():
    """It would mean a reading gained a rule reaching these genomes — D-016's premise gone."""
    with pytest.raises(RuntimeError, match="not uniform"):
        tool.outcome_of({"uniform": False, "uniform_outcome": "out_of_scope"})


def test_an_unknown_outcome_stops_the_run():
    with pytest.raises(RuntimeError, match="unknown outcome"):
        tool.outcome_of({"uniform": True, "uniform_outcome": "something_else"})


def test_the_two_not_searched_reasons_are_distinct():
    """An absent component and a protein corpus are different claims from A2.2's `not_searched`."""
    assert tool.ABSENT != tool.PROTEIN_PROXY
    assert "no eukaryotic genome component" in tool.ABSENT
    assert "by construction" in tool.ABSENT


def test_a_removed_outcome_cannot_become_a_route():
    """route_for refuses it, so no table can assert a conformance failure in passing."""
    from amazebio.apply import ManifestError, route_for
    from amazebio.policyspec import Outcome

    with pytest.raises(ManifestError):
        route_for(Outcome.REMOVED)


def test_tables_only_mode_is_documented_as_refusing_a_covered_release():
    """The guard is in `main`, so this pins the message a reader will act on.

    A `not_searched` table for a release that *does* carry the component would be the one
    reading `metrics/detections.md` forbids: a zero that looks like absence when nothing was
    searched. The refusal text has to say which release and why.
    """
    source = (REPO / "tools" / "detect_eve.py").read_text()
    assert "args.tables_only and row is not None" in source
    assert "must never be produced without a" in source


def test_one_row_per_component_even_when_a_component_has_several_objects():
    """Evo 1 publishes its viral component as three splits; the table must show it once.

    Pinned by reading the tool's source because the loop lives inside `main`. The behaviour is
    checked end to end by the artefacts, but a regression here is silent: three identical rows
    for one component read as three components.
    """
    source = (REPO / "tools" / "detect_eve.py").read_text()
    assert 'existing["staged_objects"] += 1' in source
    assert "One row per component, not per staged object" in source

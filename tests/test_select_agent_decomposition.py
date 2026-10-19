"""Tests for the halves decomposition of A1.8's release count.

The tool itself does no counting — it regroups an artefact — so what is worth testing is the
grouping: that overlapping entries are unioned rather than summed, that each scope selects
the entries it claims to, and that the reading as a whole still sums to the figure D-157
reported. The last of those is the one that would catch a regrouping that quietly lost an
entry, which is the failure mode a decomposition has and a total does not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from amazebio import selectagents as sa
from amazebio.seeds import Taxonomy

ROOT = Path(__file__).resolve().parent.parent
TAXDUMP = ROOT / "data" / "taxdmp_2023-04-01.zip"
needs_taxonomy = pytest.mark.skipif(not TAXDUMP.exists(), reason="pinned taxonomy dump not staged")


def _load() -> object:
    spec = importlib.util.spec_from_file_location(
        "select_agent_decomposition", ROOT / "tools" / "select_agent_decomposition.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the tool defines dataclasses, and a module absent from
    # `sys.modules` makes their annotations unresolvable (the UserData precheck's bug).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load()


def test_two_entries_sharing_a_taxon_count_it_once() -> None:
    """Sum-after-split would double it, and several listed organisms do overlap."""
    got = TOOL.decompose(
        {"a": frozenset({7}), "b": frozenset({7})},
        {7: 100},
        frozenset(),
        {"a": {"73.3"}, "b": {"121.3"}},
        (),
    )
    assert got["all_three_parts"]["non_viral"] == 100
    assert got["by_entry"]["a"]["non_viral"] == 100
    assert got["by_entry"]["b"]["non_viral"] == 100


def test_the_hhs_scope_keeps_only_entries_that_appear_in_42_cfr_73() -> None:
    got = TOOL.decompose(
        {"human": frozenset({1}), "plant": frozenset({2})},
        {1: 10, 2: 90},
        frozenset(),
        {"human": {"73.3"}, "plant": {"331.3"}},
        (),
    )
    assert got["hhs_list_only"]["non_viral"] == 10
    assert got["all_three_parts"]["non_viral"] == 100


def test_an_entry_listed_in_both_a_usda_part_and_the_hhs_overlap_stays_in_the_hhs_scope() -> None:
    """42 CFR 73.4 *is* the overlap list, so an entry carrying it is an HHS entry."""
    got = TOOL.decompose(
        {"both": frozenset({1})}, {1: 5}, frozenset(), {"both": {"73.4", "121.3"}}, ()
    )
    assert got["hhs_list_only"]["non_viral"] == 5


def test_removing_influenza_removes_only_influenza() -> None:
    got = TOOL.decompose(
        {"flu": frozenset({1}), "other": frozenset({2})},
        {1: 900, 2: 100},
        frozenset({1, 2}),
        {"flu": {"73.3"}, "other": {"73.3"}},
        ("flu",),
    )
    assert got["all_three_parts"]["viral"] == 1000
    assert got["all_three_parts_less_influenza_a"]["viral"] == 100


def test_removing_influenza_keeps_a_taxon_another_entry_also_claims() -> None:
    """Subtracting the entry's *set* would delete shared taxa the other entry still names."""
    got = TOOL.decompose(
        {"flu": frozenset({1, 2}), "other": frozenset({2})},
        {1: 900, 2: 100},
        frozenset({1, 2}),
        {"flu": {"73.3"}, "other": {"73.3"}},
        ("flu",),
    )
    # 2 is claimed by both, so it survives the removal of the influenza entry.
    assert got["all_three_parts_less_influenza_a"]["viral"] == 100


def test_an_empty_reading_does_not_crash_on_the_union() -> None:
    got = TOOL.decompose({}, {1: 5}, frozenset(), {}, ())
    assert got["all_three_parts"]["total"] == 0


@needs_taxonomy
def test_the_readings_still_sum_to_the_totals_d_157_reported() -> None:
    """The decomposition must be *of* the measurement, not near it.

    These two figures are quoted in D-157 and in the task's write-up, so a regrouping that
    changed either of them would be changing a published number without saying so.
    """
    entries, mapping = TOOL.load_reading(TOOL.DEFAULT_CAPTURES, TOOL.DEFAULT_MAPPING)
    taxonomy = Taxonomy.from_taxdump_zip(TAXDUMP)
    per_reading = TOOL.readings(entries, mapping, taxonomy)
    pooled = {name: frozenset().union(*by_entry.values()) for name, by_entry in per_reading.items()}
    assert len(pooled["named_and_strains"]) == len(sa.seed_taxa(entries, mapping).expand(taxonomy))
    assert len(pooled["named_only"]) == len(sa.seed_taxa(entries, mapping).named)

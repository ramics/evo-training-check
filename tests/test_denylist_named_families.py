"""The matching rule in `tools/denylist_named_families.py`, and the group list it reads.

Three threads counted the same thing three ways, so the rule is the thing under test rather
than the arithmetic. Each assertion below is one of the disagreements made to happen on
purpose, `E217_GP41` above all: a substring match over protein names counted a phage baseplate
protein as a retroviral family, which is the `macrophage` blind spot this project already has
on record.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from amazebio import profiles

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load("denylist_named_families")


def family(name: str, description: str) -> profiles.FamilyMeta:
    return profiles.FamilyMeta(
        accession="PF00000",
        name=name,
        description=description,
        gathering=(25.0, 25.0),
        model_length=100,
        clan=None,
        entry_type="Domain",
    )


@pytest.fixture(scope="module")
def groups() -> list[str]:
    return tool.group_names()


class TestGroupList:
    def test_the_nineteen_groups_come_from_the_spec(self, groups):
        assert len(groups) == 19
        assert len(set(groups)) == 19
        assert "Flaviviridae" in groups and "Picobirnaviridae" in groups

    def test_every_group_has_a_stem(self, groups):
        assert [tool.stem(g) for g in groups if g == "Flaviviridae"] == ["Flavi"]
        for group in groups:
            assert tool.stem(group) and not tool.stem(group).endswith("viridae")

    def test_a_name_that_is_not_a_family_is_refused(self):
        with pytest.raises(SystemExit, match="no stem"):
            tool.stem("Picornavirales")


class TestMatching:
    def test_the_identifier_stem_matches_as_a_whole_token(self, groups):
        hit, on = tool.match(family("Flavi_NS5", "Flavivirus RNA polymerase"), groups)
        assert hit == ["Flaviviridae"]
        assert on == "identifier"

    def test_a_stem_inside_a_longer_token_does_not_match(self, groups):
        # `Flavin` is not `Flavi`: tokens are compared whole, not as substrings.
        assert tool.match(family("Flavin_Reduct", "Flavin reductase like domain"), groups) == (
            [],
            None,
        )

    def test_gp41_in_a_phage_protein_is_not_a_retroviral_family(self, groups):
        """The row that made an earlier count 42 instead of 41."""
        assert tool.match(family("E217_GP41", "Baseplate hub gp41"), groups) == ([], None)

    def test_a_description_only_match_is_labelled_as_one(self, groups):
        hit, on = tool.match(family("Peptidase_C5", "Adenovirus endoprotease"), groups)
        assert hit == ["Adenoviridae"]
        assert on == "description", "the identifier names a protease, not a taxon"

    def test_matching_both_ways_counts_as_the_identifier(self, groups):
        """`matched_on == 'identifier'` is the 31-row floor, so it must not be diluted."""
        hit, on = tool.match(family("Pox_D5", "Poxvirus D5 protein-like"), groups)
        assert hit == ["Poxviridae"]
        assert on == "identifier"

    def test_the_prose_forms_are_the_five_the_rule_names(self):
        assert tool.prose_forms("Flaviviridae") == (
            "flaviviridae",
            "flavivirus",
            "flaviviruses",
            "flaviviral",
            "flavivirinae",
        )

    def test_a_family_may_carry_two_groups(self, groups):
        hit, _ = tool.match(family("Chimera", "Poxvirus and herpesvirus shared domain"), groups)
        assert hit == ["Herpesviridae", "Poxviridae"]

    def test_the_selection_rule_is_not_the_matching_rule(self, groups):
        """A family in the universe for naming a viral entity need not name a denylisted one."""
        meta = family("Phage_integrase", "Phage integrase family")
        assert meta.is_viral
        assert tool.match(meta, groups) == ([], None)


class TestColumns:
    def test_both_routes_have_their_own_columns(self):
        assert "evo1_hits" in tool.COLUMNS and "evo1_provirus_hits" in tool.COLUMNS
        assert "evo2_hits" in tool.COLUMNS and "evo2_provirus_hits" in tool.COLUMNS

    def test_the_route_column_map_covers_every_route(self):
        assert set(tool.ROUTE_COLUMNS) == {task for task, _ in tool.detected.ROUTES}

    def test_the_reading_hit_counts_come_from_is_one_of_the_three(self):
        assert tool.HIT_POLICY in tool.detected.POLICIES


class TestFamilyMetaFixture:
    def test_the_fixture_matches_the_real_dataclass(self):
        """A FamilyMeta built by hand must stay a FamilyMeta the tool would be handed."""
        assert dataclasses.is_dataclass(family("X", "y"))
        assert family("X", "y").selected_by == ""

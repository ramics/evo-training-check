"""The refusals and the lineage parse in `tools/denylisted_label_records.py`.

Nothing here touches the network. What is tested is what the tool refuses and how it reads the
publisher's lineage field, because the figures it produces are joins and a join's failure mode
is a silent partial match.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load("denylisted_label_records")


class TestTaxonLists:
    def test_the_family_and_order_lists_come_from_the_spec(self):
        assert len(tool.rule_names("remove-denylisted-families", "family", 19)) == 19
        assert len(tool.rule_names("remove-denylisted-orders", "order", 12)) == 12

    def test_a_wrong_count_is_a_refusal(self):
        with pytest.raises(SystemExit, match="expected 18 distinct"):
            tool.rule_names("remove-denylisted-families", "family", 18)

    def test_a_wrong_rank_is_a_refusal(self):
        with pytest.raises(SystemExit, match="not 'order'"):
            tool.rule_names("remove-denylisted-families", "order", 19)

    def test_an_unknown_rule_is_a_refusal(self):
        with pytest.raises(SystemExit, match="no rule"):
            tool.rule_names("remove-everything", "family", 19)


class TestLineage:
    def test_every_rank_is_read_by_its_prefix(self):
        ranks = tool.ranks(
            "r__Monodnaviria;k__Shotokuvirae;p__Cossaviricota;c__Arfiviricetes;"
            "o__Cirlivirales;f__Circoviridae;g__Circovirus;s__Circovirus example"
        )
        assert ranks["realm"] == "Monodnaviria"
        assert ranks["order"] == "Cirlivirales"
        assert ranks["family"] == "Circoviridae"
        assert ranks["species"] == "Circovirus example"

    def test_a_truncated_lineage_leaves_the_lower_ranks_empty(self):
        """The common case: 93% of records stop above family, and empty must mean unlabelled."""
        ranks = tool.ranks("r__Monodnaviria;k__Loebvirae;p__Hofneiviricota;;;;;")
        assert ranks["phylum"] == "Hofneiviricota"
        assert ranks["family"] == "" and ranks["order"] == "" and ranks["species"] == ""

    def test_an_entirely_empty_lineage_is_all_blank(self):
        assert set(tool.ranks(";;;;;;;").values()) == {""}

    def test_a_rank_the_publisher_omits_is_not_inferred(self):
        ranks = tool.ranks("r__Riboviria;f__Flaviviridae")
        assert ranks["realm"] == "Riboviria" and ranks["family"] == "Flaviviridae"
        assert ranks["order"] == "", "an absent order must not be filled in from the family"


class TestPins:
    def test_the_release_and_reading_are_named_not_defaulted(self):
        assert tool.RELEASE == "opengenome2"
        assert tool.POLICY == "evo1-literal"

    def test_the_label_key_is_the_pinned_release(self):
        assert "2022-09-20" in tool.LABELS_KEY

    def test_the_host_column_is_the_vmr_release_the_project_pins(self):
        from amazebio import ictv

        assert tool.VMR_RELEASE in ictv.RELEASES

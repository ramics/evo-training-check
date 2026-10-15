"""Tests for `amazebio.unfilterable` and `tools/unfilterable.py` — task A4.1.

The arithmetic here is a division, so it is not what needs pinning. What needs pinning is the
set of ways this measurement can come out plausible and wrong:

* **A ceiling that ignores the direction a rule reads its evidence.** Evo's pipeline removes a
  record *because* its realm is missing. Counting that rule as blocked by the missing realm
  would report a filter as blind where it is blunt, which overstates the finding — and §2's
  commitment cuts both ways, so an error in the audit's favour is the same failure as one in the
  filter's.
* **A single "unclassified fraction".** There is one per rank. Collapsing them hides the whole
  result: IMG/VR labels 96.7% of its records at realm and 6.3% at family, and the hazard-naming
  rule is the one keyed on family.
* **Unlabelled read as out of scope, or either read as the other.** Different findings, different
  remedies, and the artefact must never let them be summed.
* **A released component with no lineage field read as unclassified.** Evo 2's release carries no
  taxonomy and every accession in it resolves in IMG/VR. "100% unclassified" is the easiest
  wrong number in this task.
* **A share taken from a histogram that is not a partition.** Every share here divides by a
  total counted independently of the histogram, and the guard has to fire rather than be assumed
  to — which is the lesson D-074 paid for.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from amazebio import policyspec, unfilterable
from amazebio.conformance import RANKS

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "unfilterable.py"
_spec = importlib.util.spec_from_file_location("unfilterable_tool_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["unfilterable_tool_under_test"] = tool
_spec.loader.exec_module(tool)

SPECS = pathlib.Path(__file__).resolve().parent.parent / "policies" / "specs"

#: A histogram with every shape the publisher actually emits: a gapless deep lineage, the
#: dominant four-rank one, a lineage with a hole in it, and the empty tag.
HISTOGRAM = {
    "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;": 100,
    "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;o__Picornavirales;"
    "f__Marnaviridae;;": 10,
    ";;;;;;g__Dinodnavirus;s__Heterocapsa circularisquama DNA virus 01": 1,
    ";;;;;;;": 9,
}


@pytest.fixture(scope="module")
def policies():
    return policyspec.load_policy_dir(SPECS)


@pytest.fixture(scope="module")
def fill():
    return unfilterable.rank_fill(HISTOGRAM)


class TestLabellingIsPerRank:
    def test_each_rank_is_counted_separately(self, fill):
        assert fill.total == 120
        assert fill.labelled("realm") == 110
        assert fill.labelled("class") == 110
        assert fill.labelled("family") == 10
        assert fill.labelled("genus") == 1
        assert fill.unlabelled("family") == 110

    def test_a_lineage_with_a_hole_fills_only_what_it_states(self, fill):
        # `;;;;;;g__Dinodnavirus;s__...` is the publisher's own output. A reading that treated
        # depth as a prefix would credit it with a realm it does not have, and a realm-keyed
        # rule would then be reported as able to see it.
        assert fill.labelled("realm") == 110
        assert fill.labelled("species") == 1
        assert fill.depth[2] == 1

    def test_unclassified_is_the_records_filling_no_rank(self, fill):
        assert fill.unclassified == 9
        assert fill.to_dict()["unclassified_share"] == pytest.approx(9 / 120)

    def test_every_rank_appears_in_the_artefact_even_at_zero(self, fill):
        assert list(fill.to_dict()["per_rank"]) == list(RANKS)

    def test_a_share_of_nothing_is_not_zero_coverage(self):
        empty = unfilterable.rank_fill({})
        assert empty.share("family") is None
        assert empty.total == 0

    def test_an_unknown_rank_raises_rather_than_reading_as_unlabelled(self, fill):
        with pytest.raises(KeyError):
            fill.labelled("subfamily")

    def test_a_negative_count_is_refused(self):
        with pytest.raises(ValueError):
            unfilterable.rank_fill({";;;;;;;": -1})


class TestAbsenceIsKeptApartFromValue:
    def test_the_publishers_two_spellings_of_absent_are_counted_apart(self):
        f = unfilterable.host_fill({"Bacteria": 7, "(empty)": 2, "(separators only)": 11})
        assert f.present == 7
        assert f.absent == 13
        assert f.absent_by_reason == {"(empty)": 2, "(separators only)": 11}

    def test_a_field_this_audit_cannot_parse_counts_as_absent_under_its_own_reason(self):
        f = unfilterable.host_fill({"Bacteria": 1, "(unparsed: Eukaryota)": 1})
        assert f.present == 1
        assert "(unparsed: Eukaryota)" in f.absent_by_reason

    def test_the_absence_convention_is_the_one_imgvr_writes(self):
        assert unfilterable.absence_reason("(empty)") == "(empty)"
        assert unfilterable.absence_reason("Bacteria") is None


class TestTheCeilingRespectsHowARuleReadsItsEvidence:
    def test_a_rule_firing_on_an_absent_label_discriminates_nowhere_and_decides_everywhere(
        self, policies, fill
    ):
        rule = _rule(policies["evo1-literal"], "remove-taxonomically-unspecific")
        c = unfilterable.rule_ceiling(rule, ranks=fill)
        assert c.fires_on == "label_absent"
        assert c.decidable == fill.total
        assert c.discriminating == 0

    def test_a_denylist_can_only_act_where_the_rank_it_names_is_labelled(self, policies, fill):
        rule = _rule(policies["evo1-literal"], "remove-denylisted-families")
        c = unfilterable.rule_ceiling(rule, ranks=fill)
        assert c.key == "family"
        assert c.discriminating == fill.labelled("family")
        assert c.discriminating_share == pytest.approx(10 / 120)

    def test_the_order_denylist_and_the_family_denylist_get_different_ceilings(self, policies):
        # Two rules of the same kind reading two ranks. In IMG/VR v4.1 the gap between them is
        # 1,359,211 records against 979,864, so a ceiling that keyed on the kind instead of the
        # rank would report the family denylist as 39% more capable than it is.
        local = unfilterable.rank_fill(
            {
                "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
                "o__Picornavirales;;;": 30,
                "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
                "o__Picornavirales;f__Marnaviridae;;": 10,
            }
        )
        family = unfilterable.rule_ceiling(
            _rule(policies["evo1-literal"], "remove-denylisted-families"), ranks=local
        )
        order = unfilterable.rule_ceiling(
            _rule(policies["evo1-literal"], "remove-denylisted-orders"), ranks=local
        )
        assert (family.key, family.discriminating) == ("family", 10)
        assert (order.key, order.discriminating) == ("order", 40)

    def test_a_keep_list_on_host_evidence_is_decidable_everywhere(self, policies, fill):
        rule = _rule(policies["evo1-literal"], "keep-prokaryotic-host-twice")
        host = unfilterable.host_fill({"Bacteria": 20, "(separators only)": 100})
        c = unfilterable.rule_ceiling(rule, ranks=fill, host=host)
        assert c.channel == "host_occurrences"
        assert c.decidable == fill.total
        assert c.discriminating == 20

    def test_a_rule_whose_rank_the_source_leaves_unspecified_binds_nothing(self, fill):
        rule = policyspec.Rule(
            id="r",
            kind="remove_if_taxon_in",
            params={"rank": policyspec.Unspecified("not stated"), "names": []},
            source="S-TEST",
        )
        c = unfilterable.rule_ceiling(rule, ranks=fill)
        assert c.binds is False
        assert c.discriminating == 0
        assert "unspecified" in c.why

    def test_a_similarity_rule_reports_no_taxonomic_ceiling_rather_than_zero(self, policies, fill):
        policy = policies["esm3-open-literal"]
        ceilings = unfilterable.policy_ceilings(policy, ranks=fill)
        assert ceilings
        assert all(not c.binds for c in ceilings)
        assert all(c.channel == "alignment_to_seed_set" for c in ceilings)
        assert all("not taxonomy" in c.why for c in ceilings)

    def test_discriminating_never_exceeds_decidable_never_exceeds_the_component(
        self, policies, fill
    ):
        host = unfilterable.host_fill({"Bacteria": 20, "(separators only)": 100})
        attrs = {
            "confidence": unfilterable.field_fill("Confidence", {"High-confidence": 120}),
            "vOTU": unfilterable.field_fill("vOTU", {"assigned": 120}),
        }
        for pid, policy in policies.items():
            for c in unfilterable.policy_ceilings(policy, ranks=fill, host=host, attributes=attrs):
                assert 0 <= c.discriminating <= c.decidable <= fill.total, f"{pid}/{c.rule}"

    def test_a_rule_kind_with_no_declared_direction_raises(self, fill):
        rule = policyspec.Rule(id="r", kind="keep_if_mood_improves", params={}, source="S-TEST")
        with pytest.raises(unfilterable.UnknownRuleKind):
            unfilterable.rule_ceiling(rule, ranks=fill)

    def test_every_rule_kind_the_repo_declares_has_a_reading_direction(self):
        # Driven off `RULE_INPUTS` rather than a list written here, because a list written here
        # is exactly the guard D-074 found to be structurally blind to an addition.
        assert set(unfilterable.FIRES_ON) == set(policyspec.RULE_INPUTS)
        assert set(unfilterable.FIRES_ON.values()) <= {"label_present", "label_absent", "either"}


class TestTheShallownessBackstop:
    def test_it_counts_the_finest_assigned_taxon_not_any_match(self):
        histogram = {
            # Terminal at class: the unspecificity rule's own example.
            "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Tectiliviricetes;;;;": 5,
            # Riboviria appears, but the lineage runs deeper, so the rule does not catch it.
            "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
            "o__Picornavirales;f__Marnaviridae;;": 7,
        }
        assert unfilterable.terminal_taxa(histogram, ["Tectiliviricetes", "Riboviria"]) == {
            "Tectiliviricetes": 5
        }

    def test_an_empty_lineage_is_not_a_terminal_taxon(self):
        assert unfilterable.terminal_taxa({";;;;;;;": 3}, ["Riboviria"]) == {}


class TestTheDistinctionsTheArtefactMustKeep:
    def test_out_of_scope_and_unlabelled_are_different_values(self):
        assert unfilterable.OUT_OF_POLICY_SCOPE != unfilterable.ABSENT
        assert unfilterable.NOT_ANNOTATED != unfilterable.ABSENT

    def test_a_component_never_reached_carries_no_fill_and_names_a4_3_for_its_share(self, policies):
        rows = tool.out_of_scope_rows(policies)
        evo = [r for r in rows if r["policy_id"] == "evo1-literal"]
        assert evo, "the literal reading declares three components it never reaches"
        for row in evo:
            assert row["labelling"] == unfilterable.OUT_OF_POLICY_SCOPE
            assert row["ranks"] is None
            assert row["ceilings"] == []
            assert "A4.3" in row["note"]

    def test_a_wildcard_reading_examines_the_same_component_and_is_recorded_differently(
        self, policies
    ):
        rows = {(r["policy_id"], r["component"]): r for r in tool.out_of_scope_rows(policies)}
        literal = rows[("evo1-literal", "GTDB")]
        strict = rows[("evo1-strict", "GTDB")]
        # D-014: different claims about the same sequence. Neither is "unlabelled".
        assert literal["labelling"] == unfilterable.OUT_OF_POLICY_SCOPE
        assert strict["labelling"] == unfilterable.NOT_MEASURED
        assert strict["scope_state"] != literal["scope_state"]

    def test_esm3_components_are_reported_as_bound_by_no_taxonomy(self, policies):
        rows = [r for r in tool.out_of_scope_rows(policies) if r["policy_id"].startswith("esm3")]
        assert rows
        assert {r["labelling"] for r in rows} == {unfilterable.NOT_TAXONOMY_DEPENDENT}

    def test_every_caveat_the_artefact_ships_has_an_id_and_a_body(self):
        ids = {c["id"] for c in tool.caveats()}
        assert "unlabelled-is-not-out-of-scope" in ids
        assert "ceiling-is-not-survival" in ids
        assert "not-annotated-is-not-unclassified" in ids
        assert all(c["text"].strip() for c in tool.caveats())


class TestAShareIsOnlyTakenFromAPartition:
    def test_a_histogram_that_does_not_sum_to_the_counted_total_is_refused(self):
        # Confirmed to fire, not assumed to: this is the only thing standing between a dropped
        # shard and a ceiling that looks fine.
        with pytest.raises(SystemExit, match="partition"):
            tool._fills(
                {
                    "classes": {";;;;;;;": 5},
                    "rows": 6,
                    "hosts": {},
                    "confidence": {},
                    "votu": {},
                    "method": {},
                }
            )

    def test_a_matching_total_passes_and_yields_one_fill_per_field_a_rule_reads(self):
        fills = tool._fills(
            {
                "classes": dict(HISTOGRAM),
                "rows": 120,
                "hosts": {"Bacteria": 120},
                "confidence": {"High-confidence": 120},
                "votu": {"assigned": 120},
                "method": {"geNomad": 120},
            }
        )
        assert fills["ranks"].total == 120
        assert set(fills["attributes"]) == {"confidence", "vOTU"}

    def test_the_high_confidence_subset_is_checked_against_its_own_total(self):
        # The gate's own population needs its own guard: checking the subset histogram against
        # the full row count would pass silently whenever the subset is complete and fail
        # wrongly whenever it is not, which is the opposite of useful.
        scanned = {
            "classes": dict(HISTOGRAM),
            "rows": 120,
            "classes_hc": {";;;;;;;": 5},
            "rows_hc": 6,
            "hosts": {},
            "hosts_hc": {},
            "confidence": {},
            "votu": {},
            "votu_hc": {},
            "method": {},
        }
        with pytest.raises(SystemExit, match="partition"):
            tool._fills(scanned, high_confidence=True)
        # ... and the full-table reading of the same scan is unaffected.
        assert tool._fills(scanned)["ranks"].total == 120

    def test_the_gate_population_is_measured_from_its_own_cross_tab(self):
        scanned = {
            "classes": dict(HISTOGRAM),
            "rows": 120,
            # The gate keeps the deep lineage and drops the dominant shallow one, which is the
            # direction that matters: the denylist's ceiling is better on what the gate kept.
            "classes_hc": {
                "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
                "o__Picornavirales;f__Marnaviridae;;": 10
            },
            "rows_hc": 10,
            "hosts": {"Bacteria": 120},
            "hosts_hc": {"Bacteria": 10},
            "confidence": {"High-confidence": 10, "Putative": 110},
            "votu": {"assigned": 120},
            "votu_hc": {"assigned": 10},
            "method": {"geNomad": 120},
        }
        full = tool._fills(scanned)
        gated = tool._fills(scanned, high_confidence=True)
        assert full["ranks"].total == 120
        assert gated["ranks"].total == 10
        assert full["ranks"].share("family") == pytest.approx(10 / 120)
        assert gated["ranks"].share("family") == pytest.approx(1.0)
        # Every record in the gated population carries the value the gate kept, by definition.
        assert gated["attributes"]["confidence"].present == 10

    def test_the_confidence_value_measured_is_the_one_the_spec_names(self, policies):
        # Declared in two places — the spec's rule and this pass's cross-tab — so the agreement
        # is pinned rather than trusted. A drift here would silently measure an empty subset.
        (rule,) = [r for r in policies["evo1-literal"].rules if r.kind == "keep_if_attribute_in"]
        assert tool.HIGH_CONFIDENCE in rule.params["values"]

    def test_the_tool_measures_every_channel_the_evo_rules_read(self, policies):
        # If a reading grows a rule reading a channel this pass does not measure, the ceiling
        # for it would be missing rather than wrong — so the agreement is pinned here.
        channels = {
            policyspec.RULE_INPUTS[rule.kind]
            for pid, policy in policies.items()
            if pid.startswith("evo")
            for rule in policy.rules
        }
        assert channels <= {"taxonomy", "host_occurrences", "record_attributes"}


class TestTheSummaryPicksTheBlindestDiscriminatingRule:
    def test_the_binding_rule_is_the_lowest_discriminating_share(self, policies, fill):
        host = unfilterable.host_fill({"Bacteria": 20, "(separators only)": 100})
        attrs = {
            "confidence": unfilterable.field_fill("Confidence", {"High-confidence": 120}),
            "vOTU": unfilterable.field_fill("vOTU", {"assigned": 120}),
        }
        policy = policies["evo1-literal"]
        row = {
            "component": "test",
            "population": "all records",
            "policy_id": "evo1-literal",
            "reading": policy.reading,
            "ranks": fill.to_dict(),
            "ceilings": [
                c.to_dict()
                for c in unfilterable.policy_ceilings(
                    policy, ranks=fill, host=host, attributes=attrs
                )
            ],
        }
        (summary,) = tool.ceiling_summary([row])
        assert summary["binding_rule"] == "remove-denylisted-families"
        assert summary["binding_rank"] == "family"
        assert summary["ceiling"] == pytest.approx(10 / 120)
        # The rule that fires on absence is not a candidate for the ceiling at all.
        assert "remove-taxonomically-unspecific" not in summary["rules_summarised"]


def _rule(policy: policyspec.Policy, rule_id: str) -> policyspec.Rule:
    (rule,) = [r for r in policy.rules if r.id == rule_id]
    return rule

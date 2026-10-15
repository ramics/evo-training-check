"""Tests for `amazebio.scope` and `tools/scope_map.py` — task A4.3.

What is worth pinning here is not arithmetic. It is the set of distinctions the task exists to
keep apart, each of which is one edit away from collapsing into a wrong but plausible number:

* a component the scope never reached, against one a wildcard reading examined and did not
  remove from — different claims about the same sequence (D-014);
* a component the source neither names nor excludes, against one it excludes — reporting the
  first as the second asserts a conclusion the source declines to make;
* a detection limit, against a scope failure — folding the first into the second reports a
  filter that *was* applied as one that was not;
* a share within one representation, against a share of a release spanning two.

The last one is here because it was a real bug: Evo 2's out-of-scope share came out at 49%
rather than 99.6% because the denominator silently included the other tree.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from amazebio import policyspec, scope

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "scope_map.py"
_spec = importlib.util.spec_from_file_location("scope_map_under_test", _PATH)
scope_map = importlib.util.module_from_spec(_spec)
sys.modules["scope_map_under_test"] = scope_map
_spec.loader.exec_module(scope_map)

SPECS = pathlib.Path(__file__).resolve().parent.parent / "policies" / "specs"


@pytest.fixture(scope="module")
def policies():
    return policyspec.load_policy_dir(SPECS)


class TestTheDistinctionsA43ExistsToKeep:
    def test_a_wildcard_reading_examines_what_a_listed_reading_never_saw(self, policies):
        # The whole of D-014, and the spread A0.4 reports: the same eukaryotic genome is
        # never looked at under the literal reading and looked at under the strict one.
        literal = scope.classify(policies["evo1-literal"], "ncbi_eukaryotic_genomes", family="evo")
        strict = scope.classify(policies["evo1-strict"], "ncbi_eukaryotic_genomes", family="evo")

        assert literal.state == scope.OUT_OF_SCOPE
        assert strict.state == scope.REACHED_NO_RULE
        assert literal.never_a_candidate is True
        assert strict.never_a_candidate is False, (
            "a wildcard reading examined this component; saying it was never a candidate "
            "would overstate the finding in the direction that favours it"
        )

    def test_an_unnamed_component_is_not_addressed_rather_than_excluded(self, policies):
        # esm3.py's `esm3-filter-scope-list-not-exhaustive`: "including PDB, UniRef, MGnify,
        # and JGI" does not say the list is exhaustive, so OAS is neither in nor out.
        cell = scope.classify(
            policies["esm3-open-literal"],
            "OAS",
            family="esm3",
            not_addressed=scope_map.ESM3_NOT_ADDRESSED,
        )
        assert cell.state == scope.NOT_ADDRESSED
        assert cell.never_a_candidate is False
        assert cell.rules == ()

    def test_a_wildcard_scope_overrides_not_addressed(self, policies):
        # A reading that takes "the full set of training databases" as the scope has already
        # answered the question: it reaches every component, named or not. `not_addressed`
        # describes a list, so it can only arise where the scope is a list.
        for reading in ("esm3-open-charitable", "esm3-open-strict"):
            cell = scope.classify(
                policies[reading],
                "OAS",
                family="esm3",
                not_addressed=scope_map.ESM3_NOT_ADDRESSED,
            )
            assert cell.state == scope.IN_SCOPE, reading

    def test_a_detection_limit_is_not_a_scope_failure(self, policies):
        # ESM3-open's literal reading leaves both thresholds unspecified. The component is
        # still in scope: the filter was pointed at it and what it removed is uncomputable,
        # which is a different finding with a different remedy.
        cell = scope.classify(
            policies["esm3-open-literal"],
            "UniRef",
            family="esm3",
            not_addressed=scope_map.ESM3_NOT_ADDRESSED,
        )
        assert cell.state == scope.IN_SCOPE
        assert cell.never_a_candidate is False
        assert {limit.kind for limit in cell.limits} == {"undetermined"}
        assert all("identity_threshold" in limit.detail for limit in cell.limits)

    def test_the_viral_component_is_in_scope_under_every_evo_reading(self, policies):
        # The regression that matters most: the spec says "IMG/VR" and the composition says
        # "imgvr", so an unmapped label would report the one component the filter does reach
        # as never filtered — this task's headline, inverted.
        for reading in ("evo1-literal", "evo1-charitable", "evo1-strict"):
            for component in ("imgvr", "stage2"):
                cell = scope.classify(policies[reading], component, family="evo")
                assert cell.state == scope.IN_SCOPE, f"{reading}/{component}"
                assert cell.rules, "an in-scope viral component must name the rules reaching it"

    def test_an_unmapped_scope_label_raises_rather_than_matching_nothing(self):
        with pytest.raises(KeyError, match="not mapped to any"):
            scope.resolve_label("evo", "Genbank")

    def test_a_component_with_no_declared_label_falls_back_to_its_own_name(self):
        assert scope.labels_for_component("evo", "imgvr") == ("IMG/VR",)
        assert scope.labels_for_component("esm3", "OAS") == ("OAS",)


class TestTheAssembledTable:
    def test_the_scope_gap_widened_as_the_corpus_grew_under_an_unchanged_policy(self):
        # D-007's claim, quantified, and the inheritance finding §A4 asks for. The same
        # policy, inherited verbatim ("As previously described"), covers a steadily smaller
        # fraction of each successive corpus.
        rows = scope_map.evo_rows()
        summary = {(r["corpus"], r["reading"]): r for r in scope_map._coverage_summary(rows)}
        v1 = summary[("opengenome", "literal")]["share"][scope.OUT_OF_SCOPE]
        v2 = summary[("opengenome2", "literal")]["share"][scope.OUT_OF_SCOPE]

        assert 0.85 < v1 < 0.90
        assert v2 > 0.99
        assert v2 > v1, "the scope gap must be reported as widening, which is the finding"

    def test_shares_are_normalised_within_one_representation(self):
        # The bug this test exists for: `composition()` divides by the whole release, which
        # spans two trees, so a per-representation share taken from it uses a denominator
        # that includes the other tree and halves the answer.
        rows = [r for r in scope_map.evo_rows() if r["corpus"] == "opengenome2"]
        literal = [r for r in rows if r["reading"] == "literal"]
        assert (
            abs(sum(r["share"] for r in literal) - 1.0) < 1e-3
        ), "one reading's component shares must sum to the whole of its representation"
        viral = next(r for r in literal if r["component"] == "imgvr")
        assert viral["share"] > viral["share_of_whole_release"], (
            "the within-tree share is the larger one, so the correction does not flatter "
            "the filter"
        )

    def test_every_figure_carries_the_frozen_volume_caveat(self):
        # metrics/survival.md §5 is frozen: a volume figure is reported as context, never as
        # the headline, and labelled with what it does not mean.
        doc = scope_map.build()
        assert "volume figure" in doc["share_note"]
        assert "M1-M3" in doc["share_note"]
        ids = {c["id"] for c in doc["caveats"]}
        assert "absence-of-mention-is-the-evidence" in ids, (
            "A4.3's last Done-when criterion: no claim about what a filter did not cover may "
            "rest on absence of mention without that absence being stated as the evidence"
        )
        assert "esm3-has-no-corpus-denominator" in ids
        assert "representations-are-not-summable" in ids

    def test_the_cards_broken_phase_2_column_is_flagged_not_silently_replaced(self):
        doc = scope_map.build()
        phases = doc["evo_token_shares"]
        p1 = phases["Phase 1: Pretraining"]
        p2 = phases["Phase 2: Context Extension"]

        assert p1["stated_composition_column_usable"] is True
        assert p2["stated_composition_column_usable"] is False
        assert p2["stated_composition_column_totals_pct"] > 200
        # And the recomputed share is still present, so the table is usable despite it.
        assert 0 < p2["filtered_component_computed_share"] < p1["filtered_component_computed_share"]

    def test_the_three_failure_kinds_appear_separately_in_the_output(self):
        doc = scope_map.build()
        states = {r["state"] for r in doc["rows"]}
        assert scope.OUT_OF_SCOPE in states, "not applied to a component"
        assert any(r["limits"] for r in doc["rows"]), "applied but unable to detect"
        assert any(r["retains_by_design"] for r in doc["rows"]), "applied and retaining"
        assert scope.NOT_ADDRESSED in states, "and the fourth state, which is not a failure"

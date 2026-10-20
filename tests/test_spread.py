"""A0.4's spread measurement, and the distinctions it is not allowed to blur.

The one that matters is the last class: two readings that agree because the corpus cannot tell
them apart must not report as two readings that agree.
"""

from __future__ import annotations

import pytest

from amazebio import spread
from amazebio.spread import PolicyManifest, SpreadError


def manifest(reading: str, *, removed=(), uniform=None, undecidable=(), scope=("IMG/VR",)):
    """One A1.4 manifest for the Evo arm, reduced to the fields A0.4 reads."""
    return {
        "policy": {
            "id": f"evo1-{reading}",
            "model": "Evo 1",
            "reading": reading,
            "scope": list(scope),
        },
        "release": "opengenome",
        "records_enumerated": 100,
        "removed": {
            "file": f"removed-evo1-{reading}.jsonl" if removed else None,
            "records": len(removed),
        },
        "sources": [
            {
                "component": "IMG/VR",
                "uniform_outcome": None,
                "rules_undecidable": {r: "corpus does not carry it" for r in undecidable},
            },
            {"component": "GTDB", "uniform_outcome": uniform, "rules_undecidable": {}},
        ],
    }


def built(reading: str, **kw) -> PolicyManifest:
    removed = kw.pop("removed", ())
    return PolicyManifest.from_document(manifest(reading, removed=removed, **kw), removed=removed)


class TestReadingAManifest:
    def test_a_removed_count_that_disagrees_with_the_supplied_set_is_refused(self) -> None:
        doc = manifest("literal", removed=("a", "b"))
        with pytest.raises(SpreadError, match="needs both sides complete"):
            PolicyManifest.from_document(doc, removed=["a"])

    def test_an_unenumerated_removal_set_is_none_not_empty(self) -> None:
        assert PolicyManifest.from_document(manifest("literal")).removed is None
        assert built("literal", removed=()).removed == frozenset()

    def test_a_uniform_verdict_is_carried_and_a_per_record_one_is_named(self) -> None:
        m = built("strict", uniform="retained")
        assert m.component_verdicts == {"IMG/VR": "per-record", "GTDB": "retained"}

    def test_a_manifest_with_no_policy_block_is_refused(self) -> None:
        with pytest.raises(SpreadError, match="no policy block"):
            PolicyManifest.from_document({"release": "opengenome", "sources": []})


class TestExclusionSets:
    def test_identical_sets_report_as_identical(self) -> None:
        pairs = spread.pair_spreads(
            [built("literal", removed=("a", "b")), built("strict", removed=("b", "a"))]
        )
        assert len(pairs) == 1
        assert pairs[0].identical and pairs[0].jaccard == 1.0

    def test_two_empty_sets_are_identical_rather_than_undefined(self) -> None:
        pairs = spread.pair_spreads([built("literal"), built("strict")])
        assert pairs[0].jaccard == 1.0 and pairs[0].union == 0

    def test_a_difference_is_counted_on_the_side_it_falls(self) -> None:
        pairs = spread.pair_spreads(
            [built("literal", removed=("a",)), built("strict", removed=("a", "b", "c"))]
        )
        p = pairs[0]
        assert (p.shared, p.only_left, p.only_right) == (1, 0, 2)
        assert p.symmetric_difference == 2 and not p.identical

    def test_a_reading_with_no_enumerated_removals_is_left_out_rather_than_read_as_empty(
        self,
    ) -> None:
        unmeasured = PolicyManifest.from_document(manifest("charitable"))
        pairs = spread.pair_spreads([built("literal", removed=("a",)), unmeasured])
        assert pairs == []


class TestMetricCells:
    def groups(self, *, m1, routes):
        return [
            {
                "release": "opengenome",
                "universe": "pfam/38.2",
                "policy_id": pid,
                "m1_fraction": value,
                "m2": {"detections_total": 10},
                "routes": {r: {} for r in routes[pid]},
            }
            for pid, value in m1.items()
        ]

    def test_identical_metrics_under_different_route_names_are_reported_as_both(self) -> None:
        cells = spread.metric_cells(
            self.groups(
                m1={"evo1-literal": 0.5, "evo1-strict": 0.5},
                routes={
                    "evo1-literal": ("out_of_scope", "unresolved"),
                    "evo1-strict": ("retained_by_design", "unresolved"),
                },
            )
        )
        cell = cells[0]
        assert cell.m1_identical and cell.m2_identical
        assert not cell.routes_identical
        assert cell.m1_span == 0.0

    def test_a_group_that_was_not_searched_contributes_no_metric(self) -> None:
        groups = self.groups(m1={"evo1-literal": 0.5}, routes={"evo1-literal": ("unresolved",)})
        groups.append(
            {
                "release": "opengenome",
                "universe": "dfam/4.0",
                "policy_id": "evo1-literal",
                "m1_fraction": None,
                "m2": {},
                "routes": {},
            }
        )
        assert [c.universe for c in spread.metric_cells(groups)] == ["pfam/38.2"]

    def test_a_real_difference_shows_as_a_span(self) -> None:
        cells = spread.metric_cells(
            self.groups(
                m1={"evo1-literal": 0.25, "evo1-strict": 0.75},
                routes={"evo1-literal": ("unresolved",), "evo1-strict": ("unresolved",)},
            )
        )
        assert cells[0].m1_span == 0.5 and not cells[0].m1_identical


class TestComponents:
    def test_a_component_whose_verdict_flips_with_scope_is_flagged(self) -> None:
        spreads = spread.component_spreads(
            [built("literal", uniform="out_of_scope"), built("strict", uniform="retained")]
        )
        gtdb = next(s for s in spreads if s.component == "GTDB")
        assert gtdb.verdict_differs and not gtdb.disputed_rules

    def test_a_rule_one_reading_names_and_another_does_not_is_disputed(self) -> None:
        spreads = spread.component_spreads(
            [
                built("literal", undecidable=("keep-high-confidence",)),
                built("strict", undecidable=("keep-high-confidence", "keep-only-prokaryotic")),
            ]
        )
        imgvr = next(s for s in spreads if s.component == "IMG/VR")
        assert imgvr.disputed_rules == ("keep-only-prokaryotic",)
        assert imgvr.undecidable_differs

    def test_a_rule_every_reading_cannot_decide_is_not_a_dispute(self) -> None:
        spreads = spread.component_spreads(
            [built("literal", undecidable=("r",)), built("strict", undecidable=("r",))]
        )
        imgvr = next(s for s in spreads if s.component == "IMG/VR")
        assert imgvr.disputed_rules == () and not imgvr.undecidable_differs


class TestVerdict:
    def build(self, manifests, m1=None, routes=None):
        cells = spread.metric_cells(
            TestMetricCells().groups(
                m1=m1 or {m.policy_id: 0.5 for m in manifests},
                routes=routes or {m.policy_id: ("unresolved",) for m in manifests},
            )
        )
        return spread.verdict_for("Evo 1", manifests, cells, spread.component_spreads(manifests))

    def test_agreement_over_an_undecidable_rule_is_not_reported_as_agreement(self) -> None:
        verdict = self.build(
            [
                built("literal", removed=("a",), undecidable=("keep-prokaryotic-host-twice",)),
                built("strict", removed=("a",), undecidable=("keep-only-exclusively",)),
            ]
        )
        assert verdict.reproducible == "agree_on_the_corpus"
        assert verdict.rules_disputed_but_undecidable == (
            "keep-only-exclusively",
            "keep-prokaryotic-host-twice",
        )

    def test_agreement_with_every_rule_decidable_is_plain_agreement(self) -> None:
        verdict = self.build([built("literal", removed=("a",)), built("strict", removed=("a",))])
        assert verdict.reproducible == "agree"

    def test_different_removals_are_a_disagreement_whatever_the_metrics_say(self) -> None:
        verdict = self.build([built("literal", removed=("a",)), built("strict", removed=("b",))])
        assert verdict.reproducible == "readings_disagree"

    def test_one_executed_reading_is_not_measurable_rather_than_agreement(self) -> None:
        verdict = self.build([built("literal", removed=("a",))])
        assert verdict.reproducible == "not_measurable"
        assert verdict.removals_identical is None

    def test_a_scope_difference_is_recorded_even_when_nothing_else_moves(self) -> None:
        verdict = self.build(
            [
                built("literal", removed=("a",)),
                built("strict", removed=("a",), scope=("*",)),
            ]
        )
        assert verdict.scope_differs

    def test_a_model_with_no_manifest_is_refused_rather_than_reported_as_agreeing(self) -> None:
        with pytest.raises(SpreadError, match="its spread was not measured"):
            spread.verdict_for("ESM3-open", [built("literal", removed=("a",))], [], [])

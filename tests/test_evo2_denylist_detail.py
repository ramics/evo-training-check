"""The denylist breakdown has one way to be wrong that would not look wrong.

Counting released records whose family is on the denylist gives 4,706 where the chain's
own attribution gives 2,102, because the host rule fires first. Both are defensible
sentences in English and only one answers the question A7.3 asks. These tests pin the
chain-ordered attribution, pin the naive figure as a *reported* quantity rather than an
accident, and pin the guard that fires if a record is attributed to a rule whose rank it
does not carry.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from amazebio.policyspec import Outcome

_spec = importlib.util.spec_from_file_location(
    "evo2_denylist_detail",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "evo2_denylist_detail.py",
)
assert _spec and _spec.loader
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)


FAMILY_RULE = "remove-denylisted-families"
ORDER_RULE = "remove-denylisted-orders"
HOST_RULE = "keep-prokaryotic-host-twice"


def _tag(**ranks: str) -> str:
    order = ("r", "k", "p", "c", "o", "f", "g", "s")
    return ";".join(f"{r}__{ranks[r]}" if r in ranks else "" for r in order)


def _scan(released: dict[str, int], hc: dict[str, int] | None = None) -> dict:
    return {
        "evo2": {
            "released_by_classification": released,
            "released_hc_by_classification": hc or dict.fromkeys(released, 0),
        }
    }


def _run(verdicts: dict[str, str | None]) -> dict:
    """A re-execution stub: classification -> the rule that removes it, or None to retain."""
    return {
        "verdicts": {
            c: {
                group: {
                    "outcome": Outcome.RETAINED if rule is None else Outcome.REMOVED,
                    "rule_id": rule,
                    "cause": None,
                    "why": "",
                }
                for group in ("hc", "non_hc")
            }
            for c, rule in verdicts.items()
        }
    }


class TestSplittingALineage:
    def test_it_reads_each_rank(self):
        assert dl.ranks_of(_tag(f="Poxviridae", o="Chitovirales"))["f"] == "Poxviridae"

    def test_an_unassigned_rank_is_absent_rather_than_empty(self):
        """A record with no family is not a record in a family called nothing."""
        assert "f" not in dl.ranks_of(_tag(o="Caudovirales"))

    def test_a_lineage_with_nothing_assigned_yields_nothing(self):
        assert dl.ranks_of(";;;;;;;") == {}


class TestAttributingToTheRuleThatFiresFirst:
    def test_a_record_the_host_rule_removes_is_not_counted_against_the_family_rule(self):
        """The whole point of the pass: 4,706 and 2,102 differ by exactly this case."""
        released = {_tag(f="Poxviridae"): 10, _tag(f="Filoviridae"): 5}
        run_ = _run({_tag(f="Poxviridae"): HOST_RULE, _tag(f="Filoviridae"): FAMILY_RULE})
        out = dl.breakdown(_scan(released), run_, {})
        assert out["rules"][FAMILY_RULE]["by_taxon"] == {"Filoviridae": 5}
        assert out["rules"][FAMILY_RULE]["records"] == 5

    def test_a_retained_record_is_counted_nowhere(self):
        released = {_tag(f="Poxviridae"): 10}
        out = dl.breakdown(_scan(released), _run({_tag(f="Poxviridae"): None}), {})
        assert out["rules"][FAMILY_RULE]["records"] == 0

    def test_a_classification_the_re_execution_does_not_know_is_skipped(self):
        out = dl.breakdown(_scan({_tag(f="Poxviridae"): 10}), _run({}), {})
        assert out["rules"][FAMILY_RULE]["records"] == 0

    def test_high_confidence_and_the_rest_are_both_counted(self):
        tag = _tag(f="Filoviridae")
        out = dl.breakdown(_scan({tag: 10}, hc={tag: 4}), _run({tag: FAMILY_RULE}), {})
        assert out["rules"][FAMILY_RULE]["by_taxon"] == {"Filoviridae": 10}

    def test_the_order_rule_is_broken_down_at_order_rank(self):
        tag = _tag(o="Picornavirales", f="Marnaviridae")
        out = dl.breakdown(_scan({tag: 7}), _run({tag: ORDER_RULE}), {})
        assert out["rules"][ORDER_RULE]["by_taxon"] == {"Picornavirales": 7}

    def test_per_taxon_totals_sum_to_the_per_rule_total(self):
        released = {_tag(f="Poxviridae"): 3, _tag(f="Filoviridae"): 4}
        run_ = dict.fromkeys(released, FAMILY_RULE)
        out = dl.breakdown(_scan(released), _run(run_), {})
        row = out["rules"][FAMILY_RULE]
        assert sum(row["by_taxon"].values()) == row["records"] == 7


class TestTheGuardOnAMisattributedRecord:
    def test_a_record_removed_by_the_family_rule_must_carry_a_family(self):
        """If the rule and the attribution disagree, that is a bug here, not a finding."""
        tag = _tag(o="Caudovirales")
        with pytest.raises(SystemExit, match="carry no name at rank"):
            dl.breakdown(_scan({tag: 1}), _run({tag: FAMILY_RULE}), {})


class TestReportingTheOrderDependence:
    def test_the_naive_figure_is_published_beside_the_real_one(self):
        released = {_tag(f="Poxviridae"): 10, _tag(f="Filoviridae"): 5}
        run_ = _run({_tag(f="Poxviridae"): HOST_RULE, _tag(f="Filoviridae"): FAMILY_RULE})
        row = dl.breakdown(_scan(released), run_, {})["rules"][FAMILY_RULE]
        assert row["naive_records_ignoring_chain_order"] == 15
        assert row["records_the_chain_removes_earlier"] == 10

    def test_the_reporting_limit_is_stated_in_the_artefact_not_only_in_the_prose(self):
        out = dl.breakdown(_scan({}), _run({}), {})
        assert "§4" in out["note_on_reporting_limits"]
        assert "capability" in out["note_on_reporting_limits"]

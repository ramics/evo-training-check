"""Tests for the frozen survival metrics — task A3.1.

These tests exist to stop the frozen definitions drifting. Three kinds of assertion carry
weight: the worked examples from `metrics/survival.md` §4, the route taxonomy's membership
(downstream tasks tag their output with these names, so a rename silently rewires A3.2's
breakdowns), and the properties that keep a null result visible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from amazebio.survival import (
    Detection,
    ElementKind,
    Route,
    SurvivalError,
    family_survival,
    surviving_counts_by_family,
    wilson_interval,
)

SPEC = Path(__file__).resolve().parents[1] / "metrics" / "survival.md"


def detection(
    family_id: str, *, route: Route = Route.OUT_OF_SCOPE, record: str = "r1"
) -> Detection:
    return Detection(
        family_id=family_id,
        registry="pfam_viral_clans",
        registry_version="37.0",
        record_id=record,
        route=route,
        element_kind=ElementKind.PROPHAGE,
        detector="hmmsearch",
        score=42.0,
        threshold=25.0,
    )


# --- the route taxonomy ---------------------------------------------------------------------


def test_route_names_are_the_frozen_six():
    """A3.2, A7.1 and the shipped tool all tag output with these strings."""
    assert [r.value for r in Route] == [
        "out_of_scope",
        "retained_by_design",
        "undetected",
        "misassigned",
        "conformance_failure",
        "unresolved",
    ]


def test_element_kinds_are_the_frozen_seven():
    assert [k.value for k in ElementKind] == [
        "free_virus",
        "prophage",
        "endogenous_retroelement",
        "non_retroviral_eve",
        "satellite",
        "viral_derived_fragment",
        "unclassified_element",
    ]


def test_out_of_scope_is_declared_first():
    """D-007: the scope route is first-class and leads the reporting order."""
    assert next(iter(Route)) is Route.OUT_OF_SCOPE


def test_every_route_is_documented_in_the_spec():
    """A3.3 reimplements from the spec, so a route absent from it is unimplementable."""
    text = SPEC.read_text(encoding="utf-8")
    for route in Route:
        assert f"`{route.value}`" in text, f"{route.value} missing from metrics/survival.md"


def test_conformance_failure_is_separate_from_the_detection_blind_spots():
    """Collapsing these would turn a claim about taxonomy into a claim about a named lab."""
    assert Route.CONFORMANCE_FAILURE is not Route.UNDETECTED
    assert Route.CONFORMANCE_FAILURE is not Route.MISASSIGNED


# --- the worked examples in the spec --------------------------------------------------------


def test_family_survival_worked_example():
    """metrics/survival.md §4: counts {A:3, B:0, C:1, D:0, E:0} -> 0.4, [0.1176, 0.7693]."""
    result = family_survival({"A": 3, "B": 0, "C": 1, "D": 0, "E": 0})
    assert result.estimate == pytest.approx(0.4)
    assert result.low == pytest.approx(0.1176, abs=5e-5)
    assert result.high == pytest.approx(0.7693, abs=5e-5)


def test_the_worked_example_numbers_appear_in_the_spec():
    """Pins the prose to the implementation: a drifting example is a wrong specification."""
    text = SPEC.read_text(encoding="utf-8")
    assert "0.1176" in text
    assert "0.7693" in text


def test_wilson_stays_inside_the_unit_interval_at_the_extremes():
    """The reason for choosing Wilson: the normal interval leaves [0, 1] exactly here."""
    none_survive = wilson_interval(0, 100)
    all_survive = wilson_interval(100, 100)
    assert none_survive.estimate == 0.0
    assert none_survive.low == 0.0
    assert 0.0 < none_survive.high < 0.05
    assert all_survive.estimate == 1.0
    assert all_survive.high == 1.0
    assert 0.95 < all_survive.low < 1.0


def test_wilson_interval_brackets_its_estimate():
    for successes in range(0, 21):
        interval = wilson_interval(successes, 20)
        assert interval.low <= interval.estimate <= interval.high


def test_confidence_level_travels_with_the_estimate():
    """AGENTS.md: no point estimate ships without its interval, and the method is recorded."""
    assert wilson_interval(3, 10).method.startswith("wilson_z1.95996")


def test_an_empty_family_universe_is_an_error_not_a_zero():
    with pytest.raises(SurvivalError, match="empty family universe"):
        wilson_interval(0, 0)


def test_successes_cannot_exceed_trials():
    with pytest.raises(SurvivalError, match="outside 0"):
        wilson_interval(5, 3)


# --- keeping a null visible -----------------------------------------------------------------


def test_counts_are_zero_filled_across_the_pinned_universe():
    """A null is 'every family absent', which only survives if absent families are rows."""
    counts = surviving_counts_by_family(
        [detection("PF00001")], family_universe={"PF00001", "PF00002", "PF00003"}
    )
    assert counts == {"PF00001": 1, "PF00002": 0, "PF00003": 0}


def test_a_total_null_reports_zero_survival_rather_than_failing():
    counts = surviving_counts_by_family([], family_universe={"PF00001", "PF00002"})
    result = family_survival(counts)
    assert result.estimate == 0.0
    assert result.high > 0.0


def test_repeated_detections_in_one_family_count_separately():
    counts = surviving_counts_by_family(
        [detection("PF00001", record="r1"), detection("PF00001", record="r2")],
        family_universe={"PF00001", "PF00002"},
    )
    assert counts["PF00001"] == 2
    # One family surviving out of two, however many sequences it holds: M1 is per family.
    assert family_survival(counts).estimate == pytest.approx(0.5)


def test_a_detection_outside_the_pinned_universe_is_an_error():
    """A mismatched registry version would otherwise change the denominator silently."""
    with pytest.raises(SurvivalError, match="pinned family universe"):
        surviving_counts_by_family([detection("PF99999")], family_universe={"PF00001"})


def test_a_detection_below_its_own_threshold_is_refused():
    with pytest.raises(SurvivalError, match="below its declared threshold"):
        Detection(
            family_id="PF00001",
            registry="rvdb",
            registry_version="29.0",
            record_id="r1",
            route=Route.UNDETECTED,
            element_kind=ElementKind.FREE_VIRUS,
            detector="foldseek",
            score=0.4,
            threshold=0.5,
        )


# --- the spec's own commitments --------------------------------------------------------------


def test_spec_records_both_registries_and_forbids_pooling():
    text = SPEC.read_text(encoding="utf-8")
    assert "`pfam_viral_clans`" in text
    assert "`rvdb`" in text
    assert re.search(r"never pooled", text)


def test_spec_states_why_volume_is_not_the_headline():
    """A3.1 Done-when requires this stated explicitly, not implied."""
    text = SPEC.read_text(encoding="utf-8")
    assert "Why raw sequence volume is not the headline" in text


def test_spec_is_frozen_with_a_decision_reference():
    text = SPEC.read_text(encoding="utf-8")
    assert "D-022" in text

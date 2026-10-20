"""Tests for A3.3's second-method recount.

The statistical worked examples come from `metrics/survival.md` itself rather than from the
first implementation's tests, for the same reason the module does: a second implementation
checked against the first's fixtures is not a second implementation.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

from amazebio import recount

# --------------------------------------------------------------------------- statistics


def test_wilson_matches_the_specifications_worked_example():
    """`metrics/survival.md` §4: 2 of 5 families gives 0.4, Wilson [0.1176, 0.7693]."""
    result = recount.wilson_interval(2, 5)
    assert result["estimate"] == pytest.approx(0.4)
    assert result["low"] == pytest.approx(0.1176, abs=5e-5)
    assert result["high"] == pytest.approx(0.7693, abs=5e-5)


def test_wilson_stays_inside_the_unit_interval_at_the_extremes():
    for k, n in ((0, 20), (20, 20), (1, 2653047), (95, 2653047)):
        result = recount.wilson_interval(k, n)
        assert 0.0 <= result["low"] <= result["estimate"] <= result["high"] <= 1.0


def test_wilson_refuses_an_empty_denominator_and_an_impossible_count():
    with pytest.raises(recount.RecountError):
        recount.wilson_interval(0, 0)
    with pytest.raises(recount.RecountError):
        recount.wilson_interval(5, 4)


def test_quantile_interpolates_like_the_convention_it_declares():
    values = [0, 1, 2, 3]
    assert recount.quantile(values, 0.5) == pytest.approx(1.5)
    assert recount.quantile(values, 0.25) == pytest.approx(0.75)
    assert recount.quantile(values, 0.75) == pytest.approx(2.25)


def test_bootstrap_is_reproducible_from_the_seed_and_brackets_the_median():
    values = [0.0] * 40 + [1.0, 2.0, 5.0, 50.0]
    first = recount.bootstrap_median_interval(values, seed=20261020, resamples=200)
    again = recount.bootstrap_median_interval(values, seed=20261020, resamples=200)
    assert first == again
    assert first["low"] <= first["estimate"] <= first["high"]
    other = recount.bootstrap_median_interval(values, seed=7, resamples=200)
    assert other["method"] == first["method"]


# ------------------------------------------------------------------------- the fact table


def _table(**overrides):
    doc = {
        "task": "A2.1",
        "detector": "profile-hmmer",
        "registry": "pfam",
        "registry_version": "38.2",
        "manifest": {"policy_id": "evo1-literal", "release": "opengenome", "sha256": "a" * 64},
        "estimate_kind": "lower_bound",
        "sources": [{"corpus_component": "stage2", "searched": True}],
        "families": [
            {"family_id": "PF0001", "hits": 3, "records": 2, "routes": {"unresolved": 3}},
            {"family_id": "PF0002", "hits": 1, "records": 1, "routes": {"out_of_scope": 1}},
        ],
        "families_without_a_hit": ["PF0003"],
        "routes": {"unresolved": 3, "out_of_scope": 1},
    }
    doc.update(overrides)
    return doc


UNIVERSE = {"pfam/38.2": {"PF0001", "PF0002", "PF0003"}}


def test_a_group_is_one_reading_one_release_and_one_universe():
    assert recount.group_key("evo1-literal", "opengenome", "pfam/38.2") == (
        "evo1-literal|opengenome|pfam/38.2"
    )


def test_a_restriction_is_part_of_the_universes_identity():
    doc = _table(
        registry={
            "id": "rvdb-prot",
            "version": "32.0",
            "restricted_to": 1285,
            "selection": {"decision": "D-190"},
        }
    )
    assert recount.universe_name(doc) == "rvdb-prot/32.0+D-190"


def test_detection_rows_beat_the_tables_aggregate_where_they_disagree():
    """Hits are lines and records are distinct ids, however the table has summarised them."""
    doc = _table()
    rows = [
        {"family_id": "PF0001", "route": "unresolved", "record_id": "r1"},
        {"family_id": "PF0001", "route": "unresolved", "record_id": "r1"},
        {"family_id": "PF0001", "route": "unresolved", "record_id": "r2"},
        {"family_id": "PF0002", "route": "out_of_scope", "record_id": "r3"},
    ]
    facts = recount.facts_from_detection_rows(doc, rows, where="test")
    by_family = {f.family_id: f for f in facts}
    assert by_family["PF0001"].hits == 3
    assert by_family["PF0001"].records == 2
    assert all(f.basis == "detection-rows" for f in facts)


def test_a_double_encoded_detection_file_is_read_rather_than_refused():
    line = json.dumps(json.dumps({"family_id": "PF0001", "route": "unresolved", "record_id": "r"}))
    rows = recount.parse_detection_rows([line], where="test")
    assert rows == [{"family_id": "PF0001", "route": "unresolved", "record_id": "r"}]


def test_per_route_records_are_apportioned_only_for_a_table_with_several_routes():
    doc = _table(
        families=[
            {
                "family_id": "PF0001",
                "hits": 4,
                "records": 2,
                "routes": {"unresolved": 3, "out_of_scope": 1},
            }
        ],
        families_without_a_hit=["PF0002", "PF0003"],
        routes={"unresolved": 3, "out_of_scope": 1},
    )
    facts = {f.route: f for f in recount.facts_from_table(doc, where="test")}
    assert facts["unresolved"].records == pytest.approx(1.5)
    assert facts["out_of_scope"].records == pytest.approx(0.5)
    assert sum(f.records for f in facts.values()) == pytest.approx(2.0)


def test_a_table_level_route_is_used_only_when_it_is_the_only_one():
    doc = _table(
        families=[{"family_id": "PF0001", "hits": 2, "records": 2, "routes": {}}],
        routes={"unresolved": 2},
        families_without_a_hit=["PF0002", "PF0003"],
    )
    assert recount.facts_from_table(doc, where="test")[0].route == "unresolved"

    ambiguous = _table(
        families=[{"family_id": "PF0001", "hits": 2, "records": 2, "routes": {}}],
        routes={"unresolved": 1, "out_of_scope": 1},
        families_without_a_hit=["PF0002", "PF0003"],
    )
    with pytest.raises(recount.RecountError, match="undetermined"):
        recount.facts_from_table(ambiguous, where="test")


def test_a_rows_route_counts_must_sum_to_its_hits():
    doc = _table(families=[{"family_id": "PF0001", "hits": 9, "records": 2, "routes": {"a": 1}}])
    with pytest.raises(recount.RecountError):
        recount.facts_from_table(doc, where="test")


def test_no_detector_may_assert_a_conformance_failure():
    doc = _table(
        families=[
            {
                "family_id": "PF0001",
                "hits": 1,
                "records": 1,
                "routes": {"conformance_failure": 1},
            }
        ]
    )
    with pytest.raises(recount.RecountError, match="A7.1"):
        recount.facts_from_table(doc, where="test")


def test_a_route_outside_the_frozen_taxonomy_stops_the_run():
    doc = _table(
        families=[{"family_id": "PF0001", "hits": 1, "records": 1, "routes": {"leaked": 1}}]
    )
    with pytest.raises(recount.RecountError, match="frozen taxonomy"):
        recount.facts_from_table(doc, where="test")


# ----------------------------------------------------------------------------- the checks


def _inputs(*docs):
    return [{"doc": d, "rows": None, "source": "test"} for d in docs]


def test_two_detectors_on_one_component_are_refused():
    other = _table(detector="provirus-genomad", task="A2.4")
    with pytest.raises(recount.RecountError, match="stage2"):
        recount.recount_groups(
            _inputs(_table(), other), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
        )


def test_tables_computed_against_different_manifests_are_refused():
    other = _table(
        detector="provirus-genomad",
        task="A2.4",
        sources=[{"corpus_component": "stage1_gtdb", "searched": True}],
        manifest={"policy_id": "evo1-literal", "release": "opengenome", "sha256": "b" * 64},
    )
    with pytest.raises(recount.RecountError, match="different A1.4 manifests"):
        recount.recount_groups(
            _inputs(_table(), other), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
        )


def test_a_universe_that_disagrees_with_the_registry_artefact_is_refused():
    with pytest.raises(recount.RecountError, match="rebuilt from the registry artefact"):
        recount.recount_groups(
            _inputs(_table()),
            universes={"pfam/38.2": {"PF0001", "PF0002", "PF0003", "PF0004"}},
            removed_records={},
            seed=1,
            resamples=10,
        )


def test_a_detection_on_a_removed_record_is_refused():
    doc = _table()
    rows = [{"family_id": "PF0001", "route": "unresolved", "record_id": "gone"}]
    with pytest.raises(recount.RecountError, match="removes"):
        recount.recount_groups(
            [{"doc": doc, "rows": rows, "source": "test"}],
            universes=UNIVERSE,
            removed_records={"evo1-literal|opengenome": {"gone"}},
            seed=1,
            resamples=10,
        )


def test_an_unsearched_group_withholds_its_metrics_rather_than_reporting_zero():
    doc = _table(
        estimate_kind="not_searched",
        families=[],
        families_without_a_hit=["PF0001", "PF0002", "PF0003"],
        routes={},
        sources=[{"corpus_component": "stage2", "searched": False, "why": "nothing to search"}],
    )
    result = recount.recount_groups(
        _inputs(doc), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
    )
    group = result["groups"][0]
    assert group["m1"] is None and group["m2"] is None
    assert "evidence of absence" in group["withheld"]


def test_m1_is_a_union_over_routes_and_the_routes_do_not_sum_to_it():
    doc = _table(
        families=[
            {
                "family_id": "PF0001",
                "hits": 2,
                "records": 2,
                "routes": {"unresolved": 1, "out_of_scope": 1},
            },
            {"family_id": "PF0002", "hits": 1, "records": 1, "routes": {"unresolved": 1}},
        ],
        families_without_a_hit=["PF0003"],
        routes={"unresolved": 2, "out_of_scope": 1},
    )
    group = recount.recount_groups(
        _inputs(doc), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
    )["groups"][0]
    assert group["m1"]["families_detected"] == 2
    per_route = group["m1"]["per_route"]
    assert per_route["unresolved"]["families_detected"] == 2
    assert per_route["out_of_scope"]["families_detected"] == 1
    assert sum(r["families_detected"] for r in per_route.values()) != 2


def test_m2_is_zero_filled_over_the_whole_universe():
    group = recount.recount_groups(
        _inputs(_table()), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
    )["groups"][0]
    m2 = group["m2"]["records_zero_filled"]
    assert m2["n"] == 3  # including the family with no detection
    assert m2["total"] == pytest.approx(3.0)
    assert m2["max"] == pytest.approx(2.0)
    assert group["m2"]["records_detected_only"]["n"] == 2


def test_a_detection_row_naming_a_family_outside_the_universe_stops_the_run():
    """A `.jsonl` carrying a family the table's own lists do not hold is not countable."""
    doc = _table()
    rows = [{"family_id": "PF9999", "route": "unresolved", "record_id": "r1"}]
    with pytest.raises(recount.RecountError, match="outside the pinned universe"):
        recount.recount_groups(
            [{"doc": doc, "rows": rows, "source": "test"}],
            universes=UNIVERSE,
            removed_records={},
            seed=1,
            resamples=10,
        )


def test_a_universe_wider_than_the_table_states_is_refused_before_any_count():
    doc = _table(
        families=[{"family_id": "PF9999", "hits": 1, "records": 1, "routes": {"unresolved": 1}}],
        families_without_a_hit=["PF0001", "PF0002", "PF0003"],
        routes={"unresolved": 1},
    )
    with pytest.raises(recount.RecountError, match="rebuilt from the registry artefact"):
        recount.recount_groups(
            _inputs(doc), universes=UNIVERSE, removed_records={}, seed=1, resamples=10
        )


# ------------------------------------------------------------------------- the conformance arm


SPEC = {
    "policy": {
        "id": "evo1-literal",
        "rules": [
            {"id": "keep-high-confidence", "kind": "keep_if_attribute_in", "params": {}},
            {
                "id": "remove-denylisted-families",
                "kind": "remove_if_taxon_in",
                "params": {"rank": "family", "names": ["Retroviridae"]},
            },
            {
                "id": "remove-taxonomically-unspecific",
                "kind": "remove_if_unspecific",
                "params": {"require_rank": "realm", "stop_taxa": ["Riboviria"]},
            },
        ],
    }
}


def _scan(tag_counts):
    return {
        "release": "opengenome-stage2",
        "rows": sum(tag_counts.values()),
        "tag_counts": tag_counts,
        "structure": {"one_row_one_record": True, "block_chars": 131072},
    }


def test_split_tag_reads_the_released_rank_grammar():
    assigned = recount.split_tag("r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__X;;;;")
    assert assigned == {
        "realm": "Duplodnaviria",
        "kingdom": "Heunggongvirae",
        "phylum": "Uroviricota",
        "class": "X",
    }
    assert recount.split_tag(";;;;;f__Fuselloviridae;;") == {"family": "Fuselloviridae"}


def test_split_tag_refuses_a_field_in_the_wrong_position():
    with pytest.raises(recount.RecountError):
        recount.split_tag("k__Heunggongvirae;;;;;;;")
    with pytest.raises(recount.RecountError):
        recount.split_tag("r__Riboviria;;;")


def test_conformance_counts_each_published_cause_separately():
    scan = _scan(
        {
            "r__Duplodnaviria;k__H;p__U;c__Caudoviricetes;;;;": 100,
            ";;;;;f__Fuselloviridae;;": 7,  # no realm assigned
            "r__Riboviria;;;;;;;": 3,  # assigned only up to a stop taxon
            "r__Riboviria;k__K;p__P;c__C;o__O;f__Retroviridae;;": 2,  # denylisted family
        }
    )
    result = recount.conformance_from_scan(scan, {"evo1-literal": SPEC})
    reading = result["readings"]["evo1-literal"]
    assert reading["conformance_failures"] == 12
    assert reading["by_rule"]["remove-denylisted-families"] == 2
    assert reading["by_rule"]["remove-taxonomically-unspecific"] == 10
    assert reading["by_cause"]["no realm assigned"] == 7
    assert reading["coverage"]["stated"] == "2/3"
    assert reading["coverage"]["rules_not_executed"] == ["keep-high-confidence"]
    assert reading["rate"]["low"] <= reading["rate"]["estimate"] <= reading["rate"]["high"]


def test_a_removal_is_attributed_to_the_first_published_rule_that_makes_it():
    scan = _scan({"r__Riboviria;k__K;p__P;c__C;o__O;f__Retroviridae;;": 5})
    reading = recount.conformance_from_scan(scan, {"evo1-literal": SPEC})["readings"][
        "evo1-literal"
    ]
    assert reading["by_rule"]["remove-denylisted-families"] == 5
    assert reading["by_rule"]["remove-taxonomically-unspecific"] == 0


def test_readings_that_decide_identically_are_reported_as_identical():
    scan = _scan({";;;;;f__Fuselloviridae;;": 4, "r__D;k__K;p__P;c__C;;;;": 10})
    result = recount.conformance_from_scan(
        scan, {"evo1-literal": SPEC, "evo1-strict": json.loads(json.dumps(SPEC))}
    )
    assert result["readings_identical"]
    assert "by construction" in result["why_identical"]


def test_an_incomplete_census_is_refused():
    scan = _scan({"r__D;k__K;p__P;c__C;;;;": 10})
    scan["rows"] = 99
    with pytest.raises(recount.RecountError, match="not complete"):
        recount.conformance_from_scan(scan, {"evo1-literal": SPEC})


def test_a_failed_structure_check_bars_every_count_drawn_from_the_scan():
    scan = _scan({"r__D;k__K;p__P;c__C;;;;": 10})
    scan["structure"]["one_row_one_record"] = False
    with pytest.raises(recount.RecountError, match="count of rows"):
        recount.conformance_from_scan(scan, {"evo1-literal": SPEC})


# ------------------------------------------------------- the bounded re-read of the census


def test_the_reread_agrees_with_a_census_it_is_consistent_with():
    tag = "r__D;k__K;p__P;c__Caudoviricetes;;;;"
    scan = _scan({tag: 10})
    result = recount.verify_scan_sample(
        [f"|{tag}|ACGT", f"|{tag}|ACGTACGT"], scan, block_chars=131072
    )
    assert result["agrees"]
    assert result["records_read"] == 2


def test_the_reread_reports_a_tag_the_census_does_not_hold():
    scan = _scan({"r__D;k__K;p__P;c__Caudoviricetes;;;;": 10})
    result = recount.verify_scan_sample(["|r__D;;;;;;;|ACGT"], scan, block_chars=131072)
    assert not result["agrees"]
    assert result["tags_not_in_the_census"] == ["r__D;;;;;;;"]


def test_the_reread_reports_a_record_carrying_two_tags():
    tag = "r__D;k__K;p__P;c__Caudoviricetes;;;;"
    other = "r__Riboviria;;;;;;;"
    scan = _scan({tag: 10, other: 10})
    result = recount.verify_scan_sample([f"|{tag}|ACGT|{other}|TTTT"], scan, block_chars=131072)
    assert result["records_with_more_than_one_tag"] == 1
    assert not result["agrees"]


def test_the_sampled_row_groups_are_reproducible_from_the_seed():
    first = recount.sample_row_groups(2653, 16, seed=20261020)
    assert first == recount.sample_row_groups(2653, 16, seed=20261020)
    assert len(first) == 16 and first == sorted(set(first))
    assert recount.sample_row_groups(4, 16, seed=1) == [0, 1, 2, 3]


# ------------------------------------------------------------------- universes and the tool


def test_each_registry_universe_is_rebuilt_by_its_own_rule():
    pfam = {"families": [{"accession": "PF0001"}, {"accession": "PF0002"}]}
    assert recount.universe_from_registry("pfam", pfam) == {"PF0001", "PF0002"}

    rvdb = {"entries": [{"family_id": "FAM000001"}, {"family_id": "FAM000002"}]}
    assert recount.universe_from_registry("rvdb-prot", rvdb) == {"FAM000001", "FAM000002"}

    dfam = {
        "families": [
            {"family_id": "DF1", "is_erv": True, "threshold": 31.5},
            {"family_id": "DF2", "is_erv": True, "threshold": None},  # no curated threshold
            {"family_id": "DF3", "is_erv": False, "threshold": 20.0},  # not an ERV model
        ]
    }
    assert recount.universe_from_registry("dfam-curated-ltr", dfam) == {"DF1"}


def test_a_registry_with_no_rule_is_refused_rather_than_guessed_at():
    with pytest.raises(recount.RecountError):
        recount.universe_from_registry("some-new-registry", {})


_TOOL_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "recount.py"
_spec = importlib.util.spec_from_file_location("recount_tool_under_test", _TOOL_PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["recount_tool_under_test"] = tool
_spec.loader.exec_module(tool)


def test_the_comparison_joins_on_the_group_key_and_refuses_an_unknown_shape():
    headline = {
        "groups": [
            {
                "policy_id": "evo1-literal",
                "release": "opengenome",
                "universe": "pfam/38.2",
                "families_in_universe": 3,
                "m1_families_with_a_hit": 2,
                "m1_fraction": 2 / 3,
            }
        ]
    }
    keyed = tool.a32_groups(headline)
    assert set(keyed) == {"evo1-literal|opengenome|pfam/38.2"}
    with pytest.raises(SystemExit):
        tool.a32_groups({"groups": [{"policy_id": "x", "release": "y"}]})
    with pytest.raises(SystemExit):
        tool.a32_groups({})


def test_the_comparison_marks_a_divergence_rather_than_rounding_it_away():
    survival = recount.recount_groups(
        [{"doc": _table(), "rows": None, "source": "test"}],
        universes=UNIVERSE,
        removed_records={},
        seed=1,
        resamples=10,
    )
    conformance = recount.conformance_from_scan(
        _scan({";;;;;f__Fuselloviridae;;": 4}), {"evo1-literal": SPEC}
    )
    headline = {
        "groups": [
            {
                "policy_id": "evo1-literal",
                "release": "opengenome",
                "universe": "pfam/38.2",
                "families_in_universe": 3,
                "m1_families_with_a_hit": 1,  # the recount finds 2
                "m1_fraction": 1 / 3,
                "m1_ci_low": 0.0,
                "m1_ci_high": 1.0,
            }
        ]
    }
    comparison = tool.build_comparison(survival, conformance, headline)
    quantities = {row["quantity"] for row in comparison["divergent"]}
    assert "M1 families detected" in quantities
    assert "**NO**" in comparison["markdown"]
    # The conformance arm diverges too: the fixture is not the released component.
    assert any(row.get("quantity") == "conformance failures" for row in comparison["divergent"])

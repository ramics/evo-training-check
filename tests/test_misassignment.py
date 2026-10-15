"""Tests for the error taxonomy, the exact intervals, and the leakage propagation.

The interval tests check against values computed independently of this implementation:
Clopper-Pearson has closed forms at the endpoints (`1 - (alpha/2)**(1/n)` when there are no
successes) and published values in the middle, so the continued fraction and the bisection
can both be wrong in ways a self-consistency test would not catch.

The classification tests are mostly about the two directions not being collapsible. Each
`escape` cause gets its own case because `AGENTS.md` makes the breakdown by direction the
deliverable, and a cause that silently falls through to the catch-all would report
under-assignment as confident misassignment — the opposite of the finding.
"""

from __future__ import annotations

import math

import pytest

from amazebio import misassignment as mis

DENYLIST = mis.Denylist(
    families=frozenset({"Coronaviridae", "Herpesviridae", "Geminiviridae"}),
    orders=frozenset({"Picornavirales", "Herpesvirales"}),
    policy="test",
)


def _classify(
    true: dict[str, str],
    predicted: dict[str, str],
    *,
    viral: bool = True,
    length: int | None = None,
) -> mis.Judgement:
    return mis.classify(
        record="r1",
        species="Test virus",
        true_lineage=true,
        predicted_lineage=predicted,
        denylist=DENYLIST,
        called_viral=viral,
        length=length,
    )


# --------------------------------------------------------------------------------------
# The denylist
# --------------------------------------------------------------------------------------


class _Rule:
    def __init__(self, kind: str, params: dict) -> None:
        self.kind = kind
        self.params = params


class _Policy:
    def __init__(self, rules: list[_Rule], ident: str = "p") -> None:
        self.rules = rules
        self.id = ident


def test_denylist_is_read_from_the_policy_rules() -> None:
    policy = _Policy(
        [
            _Rule("remove_if_taxon_in", {"rank": "family", "names": ["Coronaviridae"]}),
            _Rule("remove_if_taxon_in", {"rank": "order", "names": ["Picornavirales"]}),
            _Rule("keep_if_host_count_at_least", {"count": 2}),
        ]
    )
    denylist = mis.Denylist.from_policy(policy, name="p")
    assert denylist.families == frozenset({"Coronaviridae"})
    assert denylist.orders == frozenset({"Picornavirales"})


def test_denylist_merges_several_rules_at_one_rank() -> None:
    policy = _Policy(
        [
            _Rule("remove_if_taxon_in", {"rank": "family", "names": ["A"]}),
            _Rule("remove_if_taxon_in", {"rank": "family", "names": ["B"]}),
        ]
    )
    assert mis.Denylist.from_policy(policy).families == frozenset({"A", "B"})


def test_denylist_refuses_a_rank_the_benchmark_cannot_evaluate() -> None:
    """A policy that denylists at genus is not silently read as if it denylisted nothing.

    D-071 found one release writing a taxon at an unexpected rank, so this is a live case
    rather than a hypothetical: a new rank must stop the benchmark, because the evaluation
    set would not have been built to cover it.
    """
    policy = _Policy([_Rule("remove_if_taxon_in", {"rank": "genus", "names": ["X"]})])
    with pytest.raises(ValueError, match="rank"):
        mis.Denylist.from_policy(policy, name="p")


def test_covers_ignores_blank_names() -> None:
    """An empty family must not match an empty entry and remove everything unlabelled."""
    assert DENYLIST.covers({"family": "", "order": ""}) is False
    assert DENYLIST.covers({}) is False


# --------------------------------------------------------------------------------------
# Directions
# --------------------------------------------------------------------------------------


def test_correct_removal() -> None:
    j = _classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"})
    assert j.direction == "correct_removal"
    assert j.family_outcome == "correct"
    assert j.escape_cause is None


def test_correct_retention() -> None:
    j = _classify({"family": "Siphoviridae"}, {"family": "Siphoviridae"})
    assert j.direction == "correct_retention"
    assert j.removed is False


def test_escape_when_family_is_absent() -> None:
    """The under-assignment route: labelled at class, which no rule reads."""
    j = _classify({"family": "Coronaviridae", "order": "Nidovirales"}, {"class": "Pisoniviricetes"})
    assert j.direction == "escape"
    assert j.escape_cause == "absent_at_rule_ranks"
    assert j.family_outcome == "absent"


def test_escape_when_label_stops_at_order() -> None:
    j = _classify(
        {"family": "Geminiviridae", "order": "Geplafuvirales"},
        {"order": "Mulpavirales"},
    )
    assert j.direction == "escape"
    # The predicted order is present and wrong, which is a confident error rather than a
    # truncation, so it must not be reported as "shallower".
    assert j.escape_cause == "misassigned_order"


def test_escape_when_order_is_right_but_not_denylisted() -> None:
    j = _classify({"family": "Geminiviridae", "order": "Cirlivirales"}, {"order": "Cirlivirales"})
    assert j.direction == "escape"
    assert j.escape_cause == "shallower_than_rule"


def test_escape_by_misassigned_family() -> None:
    j = _classify({"family": "Coronaviridae"}, {"family": "Siphoviridae"})
    assert j.direction == "escape"
    assert j.escape_cause == "misassigned_family"
    assert j.family_outcome == "wrong"


def test_escape_when_unclassified() -> None:
    j = _classify({"family": "Coronaviridae"}, {})
    assert j.direction == "escape"
    assert j.escape_cause == "unclassified"
    assert j.family_outcome == "unclassified"


def test_escape_when_not_called_viral() -> None:
    """Distinct from `unclassified` on purpose.

    A sequence the tool does not call viral never reaches the taxonomy rules, so attributing
    that escape to the taxonomy step would blame the wrong stage of the pipeline.
    """
    j = _classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"}, viral=False)
    assert j.direction == "escape"
    assert j.escape_cause == "not_viral"
    assert j.removed is False
    assert j.family_outcome == "not_viral"


def test_spurious_removal() -> None:
    j = _classify({"family": "Siphoviridae"}, {"family": "Herpesviridae"})
    assert j.direction == "spurious_removal"
    assert j.should_remove is False
    assert j.removed is True


def test_order_rule_removes_without_a_family_label() -> None:
    j = _classify({"order": "Picornavirales", "family": "Secoviridae"}, {"order": "Picornavirales"})
    assert j.direction == "correct_removal"


def test_denylisted_order_catches_a_family_the_list_does_not_name() -> None:
    """Secoviridae is not on the family list; Picornavirales is on the order list."""
    assert DENYLIST.covers({"family": "Secoviridae", "order": "Picornavirales"}) is True


# --------------------------------------------------------------------------------------
# Intervals
# --------------------------------------------------------------------------------------


def test_clopper_pearson_matches_published_values() -> None:
    low, high = mis.clopper_pearson(5, 100)
    assert low == pytest.approx(0.016431, abs=1e-5)
    assert high == pytest.approx(0.112834, abs=1e-5)


def test_clopper_pearson_zero_successes_has_the_closed_form_upper_bound() -> None:
    """With no successes the interval is one-sided: upper = 1 - (alpha/2)**(1/n)."""
    n = 87
    low, high = mis.clopper_pearson(0, n)
    assert low == 0.0
    assert high == pytest.approx(1.0 - (0.025) ** (1.0 / n), abs=1e-12)


def test_clopper_pearson_all_successes_is_the_mirror_image() -> None:
    n = 87
    low, high = mis.clopper_pearson(n, n)
    assert high == 1.0
    assert low == pytest.approx((0.025) ** (1.0 / n), abs=1e-12)


def test_clopper_pearson_contains_the_point_estimate() -> None:
    for successes, trials in ((1, 10), (3, 7), (40, 100), (999, 1000)):
        low, high = mis.clopper_pearson(successes, trials)
        assert low <= successes / trials <= high


def test_clopper_pearson_narrows_with_more_data() -> None:
    narrow = mis.clopper_pearson(50, 1000)
    wide = mis.clopper_pearson(5, 100)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_clopper_pearson_refuses_an_empty_denominator() -> None:
    """An unmeasured family must not be able to appear in a results table as measured."""
    with pytest.raises(ValueError, match="not a measurement"):
        mis.clopper_pearson(0, 0)


def test_clopper_pearson_refuses_impossible_counts() -> None:
    with pytest.raises(ValueError):
        mis.clopper_pearson(11, 10)


def test_incomplete_beta_symmetry() -> None:
    """I_x(a,b) = 1 - I_{1-x}(b,a): exercises both branches of the continued fraction."""
    for a, b, x in ((2.0, 5.0, 0.3), (0.5, 0.5, 0.7), (30.0, 3.0, 0.9)):
        left = mis.regularized_incomplete_beta(a, b, x)
        right = 1.0 - mis.regularized_incomplete_beta(b, a, 1.0 - x)
        assert left == pytest.approx(right, abs=1e-12)


def test_incomplete_beta_known_value() -> None:
    # I_x(1, 1) = x, which the implementation must reproduce without special-casing.
    assert mis.regularized_incomplete_beta(1.0, 1.0, 0.42) == pytest.approx(0.42, abs=1e-12)


def test_incomplete_beta_rejects_out_of_range_x() -> None:
    with pytest.raises(ValueError):
        mis.regularized_incomplete_beta(1.0, 1.0, 1.5)


# --------------------------------------------------------------------------------------
# Rates
# --------------------------------------------------------------------------------------


def _set() -> list[mis.Judgement]:
    """Two escapes out of four in-scope records, one spurious removal out of three controls."""
    return [
        _classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"}),
        _classify({"family": "Coronaviridae"}, {"class": "Pisoniviricetes"}),
        _classify({"family": "Herpesviridae"}, {"family": "Siphoviridae"}),
        _classify({"family": "Geminiviridae"}, {"family": "Geminiviridae"}),
        _classify({"family": "Siphoviridae"}, {"family": "Siphoviridae"}),
        _classify({"family": "Myoviridae"}, {"family": "Herpesviridae"}),
        _classify({"family": "Inoviridae"}, {"family": "Inoviridae"}),
    ]


def test_each_rate_uses_the_population_it_is_a_rate_of() -> None:
    """The denominators are the point: neither rate is over the whole evaluation set."""
    out = mis.rates(_set())
    assert out["escape"]["numerator"] == 2
    assert out["escape"]["denominator"] == 4
    assert out["spurious_removal"]["numerator"] == 1
    assert out["spurious_removal"]["denominator"] == 3
    assert out["counts"]["records"] == 7


def test_rates_report_escape_causes() -> None:
    causes = mis.rates(_set())["escape"]["causes"]
    assert causes["absent_at_rule_ranks"] == 1
    assert causes["misassigned_family"] == 1
    assert sum(causes.values()) == 2


def test_rates_carry_intervals() -> None:
    out = mis.rates(_set())
    assert out["escape"]["ci_lower"] < out["escape"]["point"] < out["escape"]["ci_upper"]


def test_rates_omit_a_direction_with_no_population() -> None:
    """No controls means no spurious-removal rate, rather than a rate of zero."""
    only_in_scope = [_classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"})]
    out = mis.rates(only_in_scope)
    assert "spurious_removal" not in out
    assert "escape" in out


def test_per_family_splits_before_pooling() -> None:
    out = mis.per_family(_set())
    assert out["Coronaviridae"]["denominator"] == 2
    assert out["Coronaviridae"]["numerator"] == 1
    assert out["Herpesviridae"]["numerator"] == 1
    assert out["Geminiviridae"]["numerator"] == 0
    # A family with no escapes still ships an interval, which is the whole reason the exact
    # method is used: its upper bound is not zero.
    assert out["Geminiviridae"]["ci_upper"] > 0


def test_per_family_keys_an_order_only_record_by_its_order() -> None:
    judged = [_classify({"order": "Picornavirales"}, {"class": "Pisoniviricetes"})]
    out = mis.per_family(judged)
    assert "(order:Picornavirales)" in out


# --------------------------------------------------------------------------------------
# Propagation
# --------------------------------------------------------------------------------------


def test_propagate_scales_the_rate_and_its_interval() -> None:
    escape = mis.rates(_set())["escape"]
    out = mis.propagate(escape=escape, corpus_records=1_000_000, in_scope_records=10_000)
    assert out["escaping_records"]["point"] == pytest.approx(0.5 * 10_000)
    assert out["escaping_records"]["ci_lower"] < out["escaping_records"]["point"]
    assert out["escaping_records"]["ci_upper"] > out["escaping_records"]["point"]


def test_propagate_declares_the_direction_of_its_bias() -> None:
    """The number gets quoted; the caveat has to travel in the artefact, not in a comment."""
    out = mis.propagate(escape=mis.rates(_set())["escape"], corpus_records=10, in_scope_records=5)
    assert out["bound"] == "lower"
    assert "fragment" in out["bound_reason"]


def test_propagate_handles_an_empty_corpus_without_dividing_by_zero() -> None:
    out = mis.propagate(escape=mis.rates(_set())["escape"], corpus_records=0, in_scope_records=0)
    assert out["share_of_corpus"]["point"] is None


# --------------------------------------------------------------------------------------
# Length strata
# --------------------------------------------------------------------------------------


def test_length_strata_bucket_by_length_and_skip_empty_buckets() -> None:
    judged = [
        _classify({"family": "Coronaviridae"}, {"class": "X"}, length=1_000),
        _classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"}, length=1_500),
        _classify({"family": "Herpesviridae"}, {"class": "X"}, length=150_000),
    ]
    strata = mis.length_strata(judged, edges=(0, 2_500, 10_000, 100_000))
    labels = {s["label"]: s for s in strata}
    assert labels["0-2500"]["denominator"] == 2
    assert labels["0-2500"]["numerator"] == 1
    assert "2500-10000" not in labels  # empty bucket omitted rather than shown as 0/0
    assert labels["100000-inf"]["numerator"] == 1


def test_length_strata_ignore_controls() -> None:
    """A spurious-removal case must not land in an escape-rate denominator."""
    judged = [
        _classify({"family": "Siphoviridae"}, {"family": "Herpesviridae"}, length=1_000),
        _classify({"family": "Coronaviridae"}, {"class": "X"}, length=1_000),
    ]
    strata = mis.length_strata(judged, edges=(0, 2_500))
    assert strata[0]["denominator"] == 1


def test_length_strata_skip_records_without_a_length() -> None:
    judged = [_classify({"family": "Coronaviridae"}, {"class": "X"}, length=None)]
    assert mis.length_strata(judged, edges=(0, 2_500)) == []


def test_frozen_vocabularies_are_complete() -> None:
    """Every cause `classify` can emit must be in the published vocabulary.

    The artefact is keyed on these strings, so a cause the taxonomy does not list would
    appear in results as an unexplained key.
    """
    emitted = {
        j.escape_cause
        for j in (
            _classify({"family": "Coronaviridae"}, {}),
            _classify({"family": "Coronaviridae"}, {"class": "X"}),
            _classify({"family": "Coronaviridae"}, {"family": "Siphoviridae"}),
            _classify(
                {"family": "Geminiviridae", "order": "Cirlivirales"}, {"order": "Cirlivirales"}
            ),
            _classify({"order": "Picornavirales"}, {"order": "Mulpavirales"}),
            _classify({"family": "Coronaviridae"}, {"family": "Coronaviridae"}, viral=False),
        )
    }
    assert emitted <= set(mis.ESCAPE_CAUSES)
    assert len(emitted) == 6, f"expected every cause to be exercised, got {sorted(emitted)}"
    assert not math.isnan(0.0)

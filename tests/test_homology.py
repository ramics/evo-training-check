"""Tests for the §B3 homology axis — `amazebio.homology`, tasks B3.1-B3.3.

The rules worth pinning are the ones a consumer cannot see being broken: a score sitting beside
a kind that means "not looked for", a bound that does not follow from the depth, and a table
that is well-formed row by row and missing a cell. Each of those is a silent wrong answer
downstream rather than a crash, which is why they are tests rather than review comments.
"""

from __future__ import annotations

import math

import pytest

from amazebio import homology


def target(**kwargs) -> homology.Target:
    base = {"dms_id": "A_B_C_2020", "uniprot_id": "A_B", "length": 100}
    return homology.Target(**{**base, **kwargs})


def measured(**kwargs) -> homology.Row:
    base = {
        "policy": "evo1-literal",
        "release": "opengenome",
        "measure": "sequence_profile",
        "score": 250.0,
        "searched_fraction": 1.0,
        "params": {},
        "evidence": {},
    }
    return homology.Row.measured(target(), **{**base, **kwargs})


def without_score(**kwargs) -> homology.Row:
    base = {
        "policy": "evo1-literal",
        "release": "opengenome",
        "measure": "sequence_profile",
        "kind": "absent",
        "reason": "searched, nothing met the cut",
        "searched_fraction": 1.0,
        "params": {},
    }
    return homology.Row.without_score(target(), **{**base, **kwargs})


class TestTarget:
    def test_needs_a_register_key(self) -> None:
        with pytest.raises(homology.HomologyError, match="register key"):
            target(dms_id="")

    def test_needs_a_positive_length(self) -> None:
        with pytest.raises(homology.HomologyError, match="length"):
            target(length=0)


class TestKinds:
    def test_measured_carries_its_score_and_normalised_value(self) -> None:
        row = measured(score=250.0)
        assert row.score == 250.0
        assert row.normalised == pytest.approx(2.5)

    def test_measured_without_a_score_is_refused(self) -> None:
        with pytest.raises(homology.HomologyError, match="measured with no score"):
            homology.Row(
                dms_id="x",
                uniprot_id=None,
                target_length=10,
                policy="p",
                release="r",
                measure="sequence_profile",
                kind="measured",
                score=None,
                normalised=None,
                searched_fraction=1.0,
                bound="none",
                reason=None,
                params={},
                evidence={},
            )

    @pytest.mark.parametrize("kind", ["absent", "not_searched", "unanswerable"])
    def test_a_kind_that_is_not_measured_may_not_carry_a_score(self, kind: str) -> None:
        with pytest.raises(homology.HomologyError, match="carries a score"):
            homology.Row(
                dms_id="x",
                uniprot_id=None,
                target_length=10,
                policy="p",
                release="r",
                measure="sequence_profile",
                kind=kind,
                score=0.0,
                normalised=None,
                searched_fraction=1.0,
                bound="none",
                reason="because",
                params={},
                evidence={},
            )

    @pytest.mark.parametrize("kind", ["absent", "not_searched", "unanswerable"])
    def test_a_kind_that_is_not_measured_needs_its_reason(self, kind: str) -> None:
        with pytest.raises(homology.HomologyError, match="needs its reason"):
            without_score(kind=kind, reason="")

    def test_without_score_refuses_the_measured_kind(self) -> None:
        with pytest.raises(homology.HomologyError, match="Row.measured"):
            without_score(kind="measured")

    def test_unknown_measure_and_kind_are_refused(self) -> None:
        with pytest.raises(homology.HomologyError, match="unknown measure"):
            measured(measure="vibes")
        with pytest.raises(homology.HomologyError, match="unknown kind"):
            without_score(kind="maybe")


class TestBound:
    def test_a_census_is_unbounded(self) -> None:
        assert homology.bound_for(1.0) == "none"

    @pytest.mark.parametrize("fraction", [0.001, 0.01, 0.5, 0.999])
    def test_anything_less_than_a_census_is_a_floor(self, fraction: float) -> None:
        assert homology.bound_for(fraction) == "lower"

    @pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1])
    def test_a_fraction_outside_the_range_is_refused(self, fraction: float) -> None:
        with pytest.raises(homology.HomologyError, match="searched_fraction"):
            homology.bound_for(fraction)

    def test_a_row_whose_bound_does_not_follow_from_its_depth_is_refused(self) -> None:
        with pytest.raises(homology.HomologyError, match="does not follow"):
            homology.Row(
                dms_id="x",
                uniprot_id=None,
                target_length=10,
                policy="p",
                release="r",
                measure="sequence_profile",
                kind="measured",
                score=1.0,
                normalised=0.1,
                searched_fraction=0.01,
                bound="none",
                reason=None,
                params={},
                evidence={},
            )

    def test_a_sampled_measured_row_is_a_floor(self) -> None:
        assert measured(searched_fraction=0.01).bound == "lower"


class TestNormalisation:
    def test_sequence_profile_is_bits_per_query_residue(self) -> None:
        assert homology.normalise("sequence_profile", 300.0, target(length=150)) == 2.0

    def test_domain_presence_is_families_present_over_families_annotated(self) -> None:
        assert homology.normalise("domain_presence", 2.0, target(), over=4) == 0.5

    def test_domain_presence_refuses_a_zero_denominator(self) -> None:
        with pytest.raises(homology.HomologyError, match="unanswerable"):
            homology.normalise("domain_presence", 0.0, target(), over=0)

    def test_structural_has_no_normalised_value(self) -> None:
        with pytest.raises(homology.HomologyError, match="no normalised value"):
            homology.normalise("structural", 1.0, target())

    def test_a_measured_domain_presence_row_needs_the_denominator(self) -> None:
        with pytest.raises(homology.HomologyError, match="annotated family count"):
            measured(measure="domain_presence", score=1.0)

    def test_a_measured_structural_row_needs_no_normalised_value(self) -> None:
        row = measured(measure="structural", score=0.6)
        assert row.normalised is None


class TestBitThreshold:
    def test_it_inverts_the_gumbel_tail(self) -> None:
        mu, lam, e_value, z = 10.0, 0.7, 1e-5, 1_000_000
        bits = homology.bit_threshold(mu=mu, lambda_=lam, e_value=e_value, z=z)
        assert z * math.exp(-lam * (bits - mu)) == pytest.approx(e_value)

    def test_it_does_not_depend_on_profile_length(self) -> None:
        a = homology.bit_threshold(100, mu=10.0, lambda_=0.7)
        b = homology.bit_threshold(900, mu=10.0, lambda_=0.7)
        assert a == b

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"e_value": 0.0, "lambda_": 0.7, "mu": 10.0},
            {"e_value": 1e-5, "lambda_": 0.0, "mu": 10.0},
            {"e_value": 1e-5, "lambda_": 0.7, "mu": 10.0, "z": 0},
        ],
    )
    def test_degenerate_parameters_are_refused(self, kwargs: dict) -> None:
        with pytest.raises(homology.HomologyError):
            homology.bit_threshold(**kwargs)


class TestGrid:
    manifests = (("evo1-literal", "opengenome"), ("esm3-open-literal", "esm3-proxy"))

    def full(self, targets) -> list[homology.Row]:
        rows = []
        for t in targets:
            for policy, release in self.manifests:
                for measure in homology.MEASURES:
                    rows.append(
                        homology.Row.without_score(
                            t,
                            policy=policy,
                            release=release,
                            measure=measure,
                            kind="not_searched",
                            reason="because",
                            searched_fraction=1.0,
                            params={},
                        )
                    )
        return rows

    def test_a_complete_grid_passes(self) -> None:
        targets = [target(dms_id="a"), target(dms_id="b")]
        homology.check_complete(self.full(targets), targets=targets, manifests=self.manifests)

    def test_a_missing_cell_is_refused(self) -> None:
        targets = [target(dms_id="a"), target(dms_id="b")]
        rows = self.full(targets)
        with pytest.raises(homology.HomologyError, match="cells missing"):
            homology.check_complete(rows[:-1], targets=targets, manifests=self.manifests)

    def test_a_duplicate_cell_is_refused(self) -> None:
        targets = [target(dms_id="a")]
        rows = self.full(targets)
        with pytest.raises(homology.HomologyError, match="duplicate"):
            homology.check_complete(rows + rows[:1], targets=targets, manifests=self.manifests)

    def test_a_row_outside_the_declared_grid_is_refused(self) -> None:
        targets = [target(dms_id="a")]
        rows = self.full(targets)
        stray = homology.Row.without_score(
            target(dms_id="never-declared"),
            policy="evo1-literal",
            release="opengenome",
            measure="structural",
            kind="not_searched",
            reason="because",
            searched_fraction=1.0,
            params={},
        )
        with pytest.raises(homology.HomologyError, match="outside the declared grid"):
            homology.check_complete([*rows, stray], targets=targets, manifests=self.manifests)


class TestGrouping:
    def test_rows_group_by_assay_in_first_seen_order(self) -> None:
        rows = [
            measured(measure="sequence_profile"),
            measured(measure="structural", score=0.5),
        ]
        grouped = dict(homology.rows_by_target(rows))
        assert list(grouped) == ["A_B_C_2020"]
        assert len(grouped["A_B_C_2020"]) == 2


class TestContractConstants:
    def test_the_acceptance_rule_is_a2_1s_rather_than_a_restatement(self) -> None:
        from amazebio import profiles

        assert homology.PINNED_E_VALUE is profiles.PINNED_E_VALUE
        assert homology.PINNED_Z is profiles.PINNED_Z
        assert homology.MIN_MODEL_COVERAGE is profiles.MIN_MODEL_COVERAGE

    def test_the_primary_measure_is_in_the_vocabulary(self) -> None:
        assert "structural" in homology.MEASURES
        assert set(homology.KINDS) == {
            "measured",
            "absent",
            "not_searched",
            "unanswerable",
        }

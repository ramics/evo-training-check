"""C5.1's frozen definitions, pinned as tests — `metrics/costcurve.md` is the text.

These are the worked examples that document promises, so a change to a boundary, an axis or
the published view fails here rather than being noticed in a figure.
"""

from __future__ import annotations

import pytest

from amazebio import costcurve as cc

# The collateral universe is held at 10,000,000 clusters throughout so a collateral count
# reads directly as a share: 111,540 is V, 1,115 is V/100.
UNIVERSE = 10_000_000
V_CLUSTERS = round(cc.VIRAL_SHARE_UNIREF50 * UNIVERSE)


def coverage(*, singletons: int = 0, doubletons: int = 10, genera: int = 40, top: int = 10):  # type: ignore[no-untyped-def]
    return cc.Coverage(
        observed_clusters=100,
        singletons=singletons,
        doubletons=doubletons,
        genera=genera,
        top_genus_clusters=top,
    )


def sweep(collateral: int, *, hazard: int = 95, hazard_total: int = 100):  # type: ignore[no-untyped-def]
    """A flat sweep: every stringency removes the same thing, so s* is the loosest point."""
    return cc.points_from_counts(
        [
            {"hazard_removed": hazard, "collateral_removed": collateral, "families_touched": 3}
            for _ in cc.STRINGENCIES
        ],
        hazard_total=hazard_total,
        collateral_total=UNIVERSE,
    )


def curve(collateral: int, **kw):  # type: ignore[no-untyped-def]
    return cc.FamilyCurve(
        family=kw.pop("family", "PF00001"),
        stratum=kw.pop("stratum", "V"),
        clan=kw.pop("clan", "CL0001"),
        fold_family=kw.pop("fold_family", "f.1"),
        points=kw.pop(
            "points", sweep(collateral, **{k: kw.pop(k) for k in ("hazard",) if k in kw})
        ),
        coverage=kw.pop("coverage", coverage()),
        **kw,
    )


class TestTheFrozenAxis:
    def test_the_sweep_is_the_one_the_decision_fixed(self) -> None:
        assert cc.STRINGENCIES == (0.95, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30)
        assert cc.STRINGENCIES[-1] == cc.IDENTITY_FLOOR
        assert list(cc.STRINGENCIES) == sorted(cc.STRINGENCIES, reverse=True)

    def test_a_point_off_the_axis_is_refused(self) -> None:
        points = (*sweep(10)[:-1], cc.Point(0.25, 95, 100, 10, UNIVERSE, 3))
        with pytest.raises(cc.CostCurveError, match="frozen sweep"):
            curve(10, points=points)

    def test_a_partial_sweep_is_not_padded(self) -> None:
        with pytest.raises(cc.CostCurveError, match="partial sweep"):
            cc.points_from_counts(
                [{"hazard_removed": 1, "collateral_removed": 1, "families_touched": 0}],
                hazard_total=10,
                collateral_total=UNIVERSE,
            )

    def test_points_must_run_strict_to_loose_once_each(self) -> None:
        points = tuple(reversed(sweep(10)))
        with pytest.raises(cc.CostCurveError, match="strictest stringency down"):
            curve(10, points=points)


class TestTheRegimeBoundary:
    """The anchor is A8.1's measurement, and both labels are made at the conservative end."""

    def test_the_anchor_is_a8_1s_measured_viral_share(self) -> None:
        assert pytest.approx(674_571 / 60_479_070) == cc.VIRAL_SHARE_UNIREF50
        assert pytest.approx(0.011154, abs=1e-6) == cc.VIRAL_SHARE_UNIREF50

    def test_well_under_a_hundredth_of_the_viral_share_is_cheap(self) -> None:
        label, why = curve(100).regime()
        assert label == cc.CHEAP
        assert why["s_star"] == cc.IDENTITY_FLOOR  # the loosest qualifying point, not the first

    def test_well_over_the_viral_share_is_catastrophic(self) -> None:
        assert cc.classify(curve(V_CLUSTERS * 3)) == cc.CATASTROPHIC

    def test_between_the_two_is_intermediate(self) -> None:
        assert cc.classify(curve(V_CLUSTERS // 5)) == cc.INTERMEDIATE

    def test_a_count_whose_interval_crosses_the_boundary_straddles_rather_than_labels(
        self,
    ) -> None:
        """The whole reason the comparison uses the interval and not the point estimate."""
        points = cc.points_from_counts(
            [
                {"hazard_removed": 95, "collateral_removed": 11, "families_touched": 1}
                for _ in cc.STRINGENCIES
            ],
            hazard_total=100,
            collateral_total=round(11 / cc.VIRAL_SHARE_UNIREF50),  # estimate sits exactly on V
        )
        label, why = curve(0, points=points).regime()
        assert label == cc.STRADDLING
        assert cc.CATASTROPHIC in why["spans"]

    def test_a_family_no_stringency_reaches_is_unreachable_not_missing(self) -> None:
        label, why = curve(10, hazard=10).regime()
        assert label == cc.UNREACHABLE
        assert "no stringency" in str(why["note"])

    def test_a_nomination_that_enumerated_the_family_carries_no_curve_result(self) -> None:
        label, why = curve(10, seed_equals_target=True).regime()
        assert label == cc.UNREACHABLE
        assert "generalise" in str(why["note"])

    def test_the_basis_travels_with_every_label(self) -> None:
        _, why = curve(100).regime()
        assert why["viral_share_anchor"] == cc.VIRAL_SHARE_UNIREF50
        assert "collateral" in why and "unbounded_below" in why


class TestCoverage:
    """§C7: no curve without coverage, and a thin family gets no label at all."""

    def test_a_thinly_sampled_family_is_withheld_not_caveated(self) -> None:
        thin = coverage(singletons=90, doubletons=2)
        assert thin.limited
        assert cc.classify(curve(100, coverage=thin)) == cc.COVERAGE_LIMITED

    def test_a_family_from_one_genus_is_withheld_however_saturated(self) -> None:
        narrow = coverage(singletons=0, genera=1, top=100)
        assert narrow.saturation == 1.0
        assert cc.classify(curve(100, coverage=narrow)) == cc.COVERAGE_LIMITED

    def test_chao1_is_undefined_without_doubletons_and_says_so(self) -> None:
        assert cc.chao1_saturation(5, 0, 100) is None
        assert coverage(singletons=5, doubletons=0).limited

    def test_no_singletons_is_complete_sampling(self) -> None:
        assert cc.chao1_saturation(0, 0, 100) == 1.0

    def test_saturation_over_an_empty_family_is_refused(self) -> None:
        with pytest.raises(cc.CostCurveError, match="undefined, not 1.0"):
            cc.chao1_saturation(1, 1, 0)


class TestTheStrata:
    def test_an_organism_nomination_carries_no_curve(self) -> None:
        with pytest.raises(cc.CostCurveError, match="nominates an organism"):
            curve(10, stratum="S")

    def test_an_unknown_stratum_is_refused(self) -> None:
        with pytest.raises(cc.CostCurveError, match="unknown nomination stratum"):
            curve(10, stratum="X")

    def test_a_family_cannot_be_both_a_subject_and_organism_nominated(self) -> None:
        with pytest.raises(cc.CostCurveError, match="both a curve subject"):
            cc.CurveSet(
                release="2023_02",
                pfam_version="38.2",
                uniprot_release="2026_03",
                curves=(curve(10, family="PF00002"),),
                organism_nominated_families=("PF00002",),
            )


class TestThePublishedView:
    """§4: by homology class, and nothing in it names a family."""

    def test_a_class_of_one_is_merged_rather_than_published(self) -> None:
        curves = [curve(100, family=f"PF0000{i}", clan="CL0001") for i in range(3)] + [
            curve(100, family="PF00009", clan="CL0099")
        ]
        view = cc.published_view(curves)
        names = [c["homology_class"] for c in view["classes"]]
        assert names == ["CL0001"]
        assert view["merged_into_no_clan"] == ["CL0099"]
        # Withheld, never named, and still counted: the totals reconcile with the per-family
        # artefact without the reader being able to tell which family it was.
        assert view["withheld_families"] == 1
        assert sum(c["families"] for c in view["classes"]) + view["withheld_families"] == 4

    def test_clanless_families_pool_rather_than_each_becoming_a_class(self) -> None:
        curves = [curve(100, family=f"PF1000{i}", clan=None) for i in range(4)]
        view = cc.published_view(curves)
        assert [c["homology_class"] for c in view["classes"]] == [cc.NO_CLAN]
        assert view["classes"][0]["families"] == 4

    def test_a_pooled_class_still_below_the_floor_is_withheld_not_printed(self) -> None:
        """Nowhere left to aggregate: the family is counted and never named, and the view
        is still produced — refusing the whole artefact over one orphan helps nobody."""
        view = cc.published_view([curve(100, family="PF00001", clan=None)])
        assert view["classes"] == []
        assert view["withheld_families"] == 1
        assert "PF00001" not in repr(view)

    def test_the_floor_cannot_be_lowered_by_a_caller(self) -> None:
        with pytest.raises(cc.CostCurveError, match="under another name"):
            cc.published_view([curve(100)], min_members=1)

    def test_the_published_view_names_no_family(self) -> None:
        curves = [curve(100, family=f"PF0000{i}", clan="CL0001") for i in range(3)]
        rendered = repr(cc.published_view(curves))
        assert "PF0000" not in rendered

    def test_the_two_views_come_from_one_artefact_with_no_recomputation(self) -> None:
        curves = tuple(curve(100, family=f"PF0000{i}", clan="CL0001") for i in range(3))
        cs = cc.CurveSet(
            release="2023_02",
            pfam_version="38.2",
            uniprot_release="2026_03",
            curves=curves,
            organism_nominated_families=("PF50000",),
        )
        published, disclosure = cs.published(), cs.disclosure_view()
        assert published["families"] == len(disclosure["curves"]) == 3
        assert published["organism_nominated_families"] == 1
        assert disclosure["uniprot_release_is_dated_not_pinned"] is True
        assert [c["family"] for c in disclosure["curves"]] == ["PF00000", "PF00001", "PF00002"]


class TestRefusals:
    def test_an_empty_universe_is_a_setup_error_not_a_result(self) -> None:
        with pytest.raises(cc.CostCurveError, match="setup error"):
            cc.Point(0.9, 0, 0, 0, UNIVERSE, 0)

    def test_removing_more_of_a_family_than_it_has_is_refused(self) -> None:
        with pytest.raises(cc.CostCurveError, match="more of the family"):
            cc.Point(0.9, 101, 100, 1, UNIVERSE, 0)

    def test_collateral_beyond_its_universe_is_refused(self) -> None:
        with pytest.raises(cc.CostCurveError, match="collateral exceeds"):
            cc.Point(0.9, 1, 100, UNIVERSE + 1, UNIVERSE, 0)

    def test_a_family_twice_in_one_set_is_refused(self) -> None:
        with pytest.raises(cc.CostCurveError, match="appears twice"):
            cc.CurveSet(
                release="2023_02",
                pfam_version="38.2",
                uniprot_release="2026_03",
                curves=(curve(10), curve(10)),
            )


def test_a_curve_still_rising_at_the_floor_is_marked_unbounded_below() -> None:
    rows = [
        {"hazard_removed": 95, "collateral_removed": c, "families_touched": 2}
        for c in (10, 20, 30, 40, 50, 60, 70, 80)
    ]
    points = cc.points_from_counts(rows, hazard_total=100, collateral_total=UNIVERSE)
    subject = curve(0, points=points)
    assert subject.unbounded_below
    assert subject.regime()[1]["unbounded_below"] is True


def test_every_fraction_ships_with_its_interval() -> None:
    point = sweep(100)[0]
    for interval in (point.hazard, point.collateral):
        assert interval.low <= interval.estimate <= interval.high
        assert interval.method

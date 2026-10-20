"""Tests for the headline merge — task A3.2.

Four things carry weight here and the rest is scaffolding:

*The merge refuses what it cannot combine honestly.* An unknown route, an untagged detection,
route counts that do not reconcile with the table's own hits, and two detectors reading the
same corpus component all raise. Each of those produces a plausible-looking headline if it is
allowed through, which is the whole reason the checks exist (D-042, D-194).

*A not_searched group reports no fraction.* Zero detections from nothing searched is not a
filter that worked, and the one way that error reaches a reader is a Wilson interval printed
over it.

*Zero-filling holds.* The denominator is the pinned universe, not the families that happened
to be detected (metrics/survival.md §6).

*The bootstrap's multinomial form agrees with direct resampling.* M2's interval is computed by
drawing multinomial counts over distinct values rather than indices, which is an optimisation,
and an optimisation to a frozen metric has to be shown equivalent rather than asserted.
"""

from __future__ import annotations

import dataclasses
import statistics

import pytest

from amazebio.quantify import (
    GroupKey,
    MergeError,
    RegistryUniverse,
    bootstrap_median_interval,
    check_component_disjointness,
    group_tables,
    load_table,
    merge_group,
    quantify,
)

UNIVERSE = ["F1", "F2", "F3", "F4"]


def table(
    *,
    task: str = "A2.1",
    detector: str = "profile-hmmer",
    families: list[dict] | None = None,
    components: list[tuple[str, bool]] = (("stage2", True),),
    registry: object = "pfam",
    version: str = "38.2",
    policy_id: str = "evo1-literal",
    release: str = "opengenome",
    routes: dict | None = None,
    sample: dict | None = None,
) -> dict:
    families = (
        [{"family_id": "F1", "hits": 2, "records": 2, "routes": {"out_of_scope": 2}}]
        if families is None
        else families
    )
    hit = {f["family_id"] for f in families}
    return {
        "task": task,
        "detector": detector,
        "registry": registry,
        "registry_version": version,
        "manifest": {
            "policy_id": policy_id,
            "release": release,
            "sha256": "abc",
            "removed_records": 0,
        },
        "estimate_kind": "lower_bound" if any(s for _, s in components) else "not_searched",
        "sample": sample,
        "sources": [{"corpus_component": c, "searched": s} for c, s in components],
        "families": families,
        "families_without_a_hit": [f for f in UNIVERSE if f not in hit],
        "routes": routes or {},
        "notes": [],
    }


def loaded(**kw):
    return load_table(table(**kw), source=kw.pop("source", "test"))


def test_unknown_route_is_refused() -> None:
    doc = table(families=[{"family_id": "F1", "hits": 1, "records": 1, "routes": {"escaped": 1}}])
    with pytest.raises(MergeError, match="not in the A3.1 taxonomy"):
        load_table(doc, source="t")


def test_route_counts_must_reconcile_with_hits() -> None:
    doc = table(
        families=[{"family_id": "F1", "hits": 3, "records": 3, "routes": {"out_of_scope": 2}}]
    )
    with pytest.raises(MergeError, match="route counts sum to 2"):
        load_table(doc, source="t")


def test_uniform_route_is_accepted_only_when_it_is_the_only_one() -> None:
    rows = [{"family_id": "F1", "hits": 2, "records": 2}]
    ok = load_table(table(families=rows, routes={"unresolved": 500}), source="t")
    assert ok.route_attribution == "uniform"
    assert ok.routes["F1"] == {"unresolved": 2}

    with pytest.raises(MergeError, match="no route and the table declares"):
        load_table(table(families=rows, routes={"unresolved": 5, "out_of_scope": 5}), source="t")


def test_a_detection_with_no_route_at_all_is_refused() -> None:
    with pytest.raises(MergeError, match="no route and the table declares 0"):
        load_table(table(families=[{"family_id": "F1", "hits": 1, "records": 1}]), source="t")


def test_overlapping_components_refuse_the_group() -> None:
    a = loaded()
    b = loaded(task="A2.4", detector="provirus-genomad", components=[("stage2", True)])
    with pytest.raises(MergeError, match="both searched component"):
        check_component_disjointness([a, b])


def test_disjoint_components_sum_per_family() -> None:
    a = loaded()
    b = loaded(
        task="A2.4",
        detector="provirus-genomad",
        components=[("stage1_gtdb", True)],
        families=[{"family_id": "F1", "hits": 5, "records": 5, "routes": {"out_of_scope": 5}}],
    )
    key = GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 4))
    merged = merge_group(key, [a, b])
    assert merged.counts == {"F1": 7}


def test_universes_are_never_pooled() -> None:
    restricted = {"id": "rvdb-prot", "version": "32.0", "selection": {"decision": "D-190"}}
    groups = group_tables(
        [
            loaded(registry="rvdb-prot", version="32.0"),
            loaded(registry=restricted, version="32.0"),
        ]
    )
    assert len(groups) == 2
    assert {k.universe.key for k in groups} == {"rvdb-prot/32.0", "rvdb-prot/32.0+D-190"}


def test_counts_are_zero_filled_across_the_pinned_universe() -> None:
    key = GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 4))
    merged = merge_group(key, [loaded()])
    assert merged.zero_filled() == [0, 0, 0, 2]

    # A universe smaller than the families carrying detections means the denominator and the
    # detections came from different registry releases, which would silently raise M1.
    shrunk = dataclasses.replace(
        merged,
        key=GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 0)),
    )
    with pytest.raises(MergeError, match="different registry releases"):
        shrunk.zero_filled()


def test_not_searched_group_withholds_the_fraction() -> None:
    t = loaded(components=[("stage2", False)], families=[])
    key = GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 4))
    doc = quantify(merge_group(key, [t]), seed=1, resamples=100).document
    assert doc["estimate_kind"] == "not_searched"
    assert doc["m1_fraction"] is None and doc["m2"] is None
    assert any("evidence of absence" in line for line in doc["reading_this_table"])


def test_a_sampled_detector_makes_the_whole_group_a_lower_bound() -> None:
    census = loaded(components=[("stage2", True)])
    object.__setattr__(census, "estimate_kind", "population")
    sampled = loaded(task="A2.4", detector="provirus-genomad", components=[("stage1_gtdb", True)])
    key = GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 4))
    assert merge_group(key, [census, sampled]).estimate_kind == "lower_bound"


def test_m1_and_the_route_breakdown_do_not_have_to_sum() -> None:
    a = loaded(
        families=[{"family_id": "F1", "hits": 1, "records": 1, "routes": {"out_of_scope": 1}}]
    )
    b = loaded(
        task="A2.4",
        detector="provirus-genomad",
        components=[("stage1_gtdb", True)],
        families=[{"family_id": "F1", "hits": 1, "records": 1, "routes": {"unresolved": 1}}],
    )
    key = GroupKey("evo1-literal", "opengenome", RegistryUniverse("pfam", "38.2", None, 4))
    doc = quantify(merge_group(key, [a, b]), seed=1, resamples=100).document
    assert doc["m1_families_with_a_hit"] == 1
    per_route = sum(r["m1_families_with_a_hit"] for r in doc["routes"].values())
    assert per_route == 2, "one family on two routes: the per-route counts over-count by design"
    assert any("do not sum" in line for line in doc["reading_this_table"])


@pytest.mark.parametrize("values", [[0] * 40 + [1, 2, 3, 9], [0, 1] * 25, list(range(17))])
def test_bootstrap_matches_direct_resampling(values: list[int]) -> None:
    """The multinomial form is an optimisation of a frozen metric, so it is shown equivalent."""
    import numpy as np

    got = bootstrap_median_interval(values, seed=7, resamples=4000)
    rng = np.random.default_rng(99)
    arr = np.asarray(values)
    direct = sorted(
        statistics.median(rng.choice(arr, size=arr.size, replace=True).tolist())
        for _ in range(4000)
    )
    lo, hi = direct[int(0.025 * 4000)], direct[int(0.975 * 4000)]
    assert got.estimate == pytest.approx(statistics.median(values))
    spread = max(1.0, hi - lo)
    assert abs(got.low - lo) <= 0.35 * spread
    assert abs(got.high - hi) <= 0.35 * spread


def test_bootstrap_on_an_all_zero_universe_is_a_zero_width_interval() -> None:
    iv = bootstrap_median_interval([0] * 100, seed=3, resamples=50)
    assert (iv.estimate, iv.low, iv.high) == (0.0, 0.0, 0.0)


def test_bootstrap_refuses_an_empty_universe() -> None:
    with pytest.raises(MergeError, match="empty family universe"):
        bootstrap_median_interval([], seed=1)


def test_a_table_with_no_registry_is_refused() -> None:
    doc = table()
    doc["registry"] = None
    with pytest.raises(MergeError, match="no registry universe"):
        load_table(doc, source="t")

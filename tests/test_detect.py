"""The shared detection schema: sampling, zero-filling, element kinds and the route guard."""

from __future__ import annotations

import json

import pytest

from amazebio.detect import (
    DetectionError,
    DetectionTable,
    ManifestRef,
    SampleDesign,
    build_rows,
    check_route_coverage,
    detection_rows,
    element_kind_for,
    in_sample,
    sample_hash,
)
from amazebio.survival import Detection, ElementKind, Route

UNIVERSE = {"PF00001": "fam_a", "PF00002": "fam_b", "PF00003": "fam_c"}
THRESHOLDS = {"PF00001": 25.0, "PF00002": 30.0, "PF00003": 20.0}

REF = ManifestRef(
    policy_id="evo1-literal",
    release="opengenome",
    path="artifacts/a1-4/manifest-evo1-literal-opengenome.json",
    sha256="0" * 64,
    removed_records=95,
)


def detection(family="PF00001", record="r1", score=40.0, route=Route.UNRESOLVED):
    return Detection(
        family_id=family,
        registry="pfam",
        registry_version="38.2",
        record_id=record,
        route=route,
        element_kind=ElementKind.UNCLASSIFIED_ELEMENT,
        detector="profile-hmmer",
        score=score,
        threshold=THRESHOLDS[family],
    )


# --------------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------------


def test_sample_membership_is_reproducible_across_processes():
    # Python's own hash is randomised per process; a sampler built on it would draw a different
    # sample every run and no count from it would regenerate.
    assert sample_hash("IMGVR_UViG_1", seed=20261015) == sample_hash("IMGVR_UViG_1", seed=20261015)


def test_sample_membership_depends_on_the_seed():
    ids = [f"r{i}" for i in range(2000)]
    a = {i for i in ids if in_sample(i, seed=1, rate=0.1)}
    b = {i for i in ids if in_sample(i, seed=2, rate=0.1)}
    assert a != b


def test_a_wider_rate_extends_the_same_sample():
    # D-078 relies on this: funding a deeper pass must not re-search what has been searched.
    ids = [f"r{i}" for i in range(5000)]
    narrow = {i for i in ids if in_sample(i, seed=7, rate=0.01)}
    wide = {i for i in ids if in_sample(i, seed=7, rate=0.05)}
    assert narrow <= wide


def test_rate_one_is_a_census():
    assert in_sample("anything", seed=1, rate=1)
    assert SampleDesign(seed=1, rate=1, population=10).is_census


def test_sample_rate_is_roughly_the_rate_it_claims():
    ids = [f"IMGVR_UViG_{i}" for i in range(40_000)]
    drawn = sum(in_sample(i, seed=20261015, rate=0.01) for i in ids)
    assert 250 < drawn < 550


@pytest.mark.parametrize("rate", [0, -0.1, 1.5])
def test_an_impossible_rate_is_refused(rate):
    with pytest.raises(DetectionError, match="sample rate"):
        in_sample("r", seed=1, rate=rate)


# --------------------------------------------------------------------------------------
# Element kind
# --------------------------------------------------------------------------------------


def test_imgvr_hits_are_free_virus_by_the_publishers_own_definition():
    assert element_kind_for("imgvr") is ElementKind.FREE_VIRUS


def test_everything_else_is_unclassified_rather_than_guessed():
    # D-079: a profile hit in a bacterial genome becomes a prophage when A2.4 says so.
    assert element_kind_for("stage2") is ElementKind.UNCLASSIFIED_ELEMENT
    assert element_kind_for("gtdb") is ElementKind.UNCLASSIFIED_ELEMENT
    assert element_kind_for("something_new") is ElementKind.UNCLASSIFIED_ELEMENT


# --------------------------------------------------------------------------------------
# Rows and tables
# --------------------------------------------------------------------------------------


def test_rows_are_zero_filled_across_the_whole_universe():
    rows = build_rows([detection()], universe=UNIVERSE, thresholds=THRESHOLDS)
    assert [r.family_id for r in rows] == ["PF00001", "PF00002", "PF00003"]
    assert [r.hits for r in rows] == [1, 0, 0]
    # A zero row still carries the threshold it was measured against, so the table can be
    # re-read at a stricter one without re-running the search.
    assert all(r.threshold for r in rows)


def test_a_zero_row_is_a_measured_zero_not_a_missing_one():
    rows = build_rows([], universe=UNIVERSE, thresholds=THRESHOLDS)
    assert len(rows) == 3
    assert all(r.hits == 0 and r.best_score is None for r in rows)


def test_a_family_outside_the_universe_is_refused():
    with pytest.raises(DetectionError, match="outside the pinned family universe"):
        build_rows([detection(family="PF00001")], universe={"PF00002": "b"}, thresholds=THRESHOLDS)


def test_records_are_counted_distinctly_from_hits():
    rows = build_rows(
        [detection(record="r1"), detection(record="r1"), detection(record="r2")],
        universe=UNIVERSE,
        thresholds=THRESHOLDS,
    )
    hit = next(r for r in rows if r.family_id == "PF00001")
    assert (hit.hits, hit.records) == (3, 2)


def table(detections=(), *, sample=None, sources=None):
    return DetectionTable(
        task="A2.1",
        detector="profile-hmmer",
        registry="pfam",
        registry_version="38.2",
        manifest=REF,
        sources=sources if sources is not None else [{"searched": True}],
        sample=sample,
        rows=build_rows(detections, universe=UNIVERSE, thresholds=THRESHOLDS),
    )


def test_a_sampled_table_reports_a_lower_bound():
    t = table([detection()], sample=SampleDesign(seed=1, rate=0.001, population=1000))
    assert t.estimate_kind == "lower_bound"
    assert "lower bound" in t.survival()["reading"]


def test_a_census_reports_a_population_figure():
    t = table([detection()], sample=SampleDesign(seed=1, rate=1, population=1000))
    assert t.estimate_kind == "population"


def test_an_unsearched_manifest_is_not_a_measured_zero():
    # The ESM3 proxy corpus has no reader until A1.6. Reporting its table as a population zero
    # would read as a filter that removed everything, which is the opposite of the finding.
    t = table(sources=[{"searched": False, "why": "no reader yet"}])
    assert t.estimate_kind == "not_searched"
    assert "none of it is evidence of absence" in t.survival()["reading"]


def test_survival_counts_families_not_hits():
    t = table([detection(record="r1"), detection(record="r2")])
    survival = t.survival()
    assert survival["families_with_a_hit"] == 1
    assert survival["families_in_universe"] == 3
    assert survival["fraction"] == pytest.approx(1 / 3)
    assert survival["ci_low"] < survival["fraction"] < survival["ci_high"]


def test_survival_refuses_an_empty_universe():
    t = table()
    t.rows = []
    with pytest.raises(DetectionError, match="no family rows"):
        t.survival()


def test_the_table_lists_every_family_either_way(tmp_path):
    t = table([detection()])
    written = json.loads(t.write(tmp_path / "t.json").read_text())
    assert [f["family_id"] for f in written["families"]] == ["PF00001"]
    assert written["families_without_a_hit"] == ["PF00002", "PF00003"]
    assert len(written["families"]) + len(written["families_without_a_hit"]) == 3


def test_a_table_may_not_assert_a_conformance_failure():
    t = table([detection(route=Route.CONFORMANCE_FAILURE)])
    with pytest.raises(DetectionError, match="conformance_failure"):
        check_route_coverage(t)


def test_a_table_with_ordinary_routes_passes_the_guard():
    check_route_coverage(table([detection(route=Route.OUT_OF_SCOPE)]))


def test_record_level_rows_carry_no_sequence():
    rows = [json.loads(line) for line in detection_rows([detection()])]
    assert rows[0]["record_id"] == "r1"
    assert not any("sequence" in key for key in rows[0])
    assert set(rows[0]) == {
        "record_id",
        "family_id",
        "registry",
        "registry_version",
        "detector",
        "score",
        "threshold",
        "route",
        "element_kind",
    }

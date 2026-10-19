"""Tests for `tools/sweep_problem_taxa.py` — task A2.5's label-side arm.

`tests/test_problemtaxa.py` pins the predicates. This file pins the *tally*, where a different
set of mistakes lives — all of them mistakes that make a table look like a stronger result than
it is:

* **`unlabelled` folded into `absent`.** The one that turns "we could not tell" into a clean
  bill of health over a corpus labelled only to class.
* **A single survival rate.** There are two honest denominators — records whose label can answer
  the question, and all records — and they differ by two orders of magnitude here. Shipping one
  unnamed rate is the D-161 failure one task over.
* **A category with no detections rendered as an absent row** rather than a measured zero.
* **A component quietly left out** of `sources[]`, which makes a table over part of a release
  read as a verdict on all of it.
* **A route asserted as a conformance failure**, which §7 reserves for A7.1.
* **A census that does not add up** to the record count it claims to cover.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from amazebio import ictv, policyspec, problemtaxa
from amazebio.apply import ManifestError, route_for
from amazebio.problemtaxa import Category, Verdict
from amazebio.survival import Route

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "sweep_problem_taxa.py"
_spec = importlib.util.spec_from_file_location("sweep_problem_taxa_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["sweep_problem_taxa_under_test"] = tool
_spec.loader.exec_module(tool)

_VMR = pathlib.Path(__file__).resolve().parent.parent / "data" / "ictv"
_PINNED = _VMR / ictv.release(tool.REFERENCE).filename
_needs_vmr = pytest.mark.skipif(
    not _PINNED.exists(), reason="the pinned VMR is not staged in this checkout"
)


@pytest.fixture
def checklist() -> problemtaxa.Checklist:
    return problemtaxa.build_checklist(ictv.read_vmr(_PINNED), reference=tool.REFERENCE)


# A census in the shape A7.2 publishes: classification -> released record count.
CENSUS = {
    "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;": 1_000_000,
    ";;;;;f__Mimiviridae;;": 500,
    ";;;;;f__Phycodnaviridae;;": 300,
    ";;;;;f__Cystoviridae;;": 40,
    ";;;;;f__Alphasatellitidae;;": 7,
    ";;;;;;g__Albetovirus;": 2,
    ";;;;;;;": 11,
}


@pytest.fixture
def swept(checklist: problemtaxa.Checklist):
    return tool.sweep_joined(
        CENSUS, checklist=checklist, route="unresolved", element_kind="free_virus"
    )


# --------------------------------------------------------------------------------------
# The census adds up, and the three verdicts stay three
# --------------------------------------------------------------------------------------


@_needs_vmr
def test_every_record_is_accounted_for_exactly_once(swept, checklist) -> None:
    """A census is only a census if the verdicts partition it."""
    tallies, stats = swept
    assert stats["records_surviving"] == sum(CENSUS.values())
    for category, tally in tallies.items():
        assert sum(tally.verdicts.values()) == sum(CENSUS.values()), category


@_needs_vmr
def test_unlabelled_is_never_folded_into_absent(swept, checklist) -> None:
    """The 11 records with no label at all must be `unlabelled` for every category."""
    tallies, _ = swept
    for category, tally in tallies.items():
        emitted = tally.to_dict(checklist=checklist, category=category)
        assert emitted["verdicts"]["unlabelled"] >= 11, category
        assert emitted["unlabelled_by_reason"], category
        # The three verdicts must partition, so folding one into another is detectable here.
        assert (
            emitted["verdicts"]["unlabelled"]
            + emitted["verdicts"].get("present", 0)
            + emitted["verdicts"].get("absent", 0)
            == emitted["records"]
        ), category


@_needs_vmr
def test_no_taxonomic_label_is_reported_as_its_own_reason(swept, checklist) -> None:
    tallies, _ = swept
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert emitted["unlabelled_by_reason"]["no taxonomic label at any rank"] == 11


@_needs_vmr
def test_giant_viruses_are_found_and_attributed_to_the_records_own_label(swept, checklist) -> None:
    """800 NCLDV records, reported as `f__Mimiviridae` and `f__Phycodnaviridae` rather than as
    the phylum that matched — the composition is what carries the finding (D-173)."""
    tallies, _ = swept
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert emitted["verdicts"]["present"] == 800
    assert emitted["composition"][0] == {"taxon": "f__Mimiviridae", "records": 500}
    assert emitted["composition"][1] == {"taxon": "f__Phycodnaviridae", "records": 300}


@_needs_vmr
def test_composition_ties_break_by_name(checklist) -> None:
    """A quoted parts list has to reproduce from pinned inputs, so ties are not hash order."""
    tallies, _ = tool.sweep_joined(
        {";;;;;f__Mimiviridae;;": 5, ";;;;;f__Iridoviridae;;": 5, ";;;;;f__Ascoviridae;;": 5},
        checklist=checklist,
        route="unresolved",
        element_kind="free_virus",
    )
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert [c["taxon"] for c in emitted["composition"]] == [
        "f__Ascoviridae",
        "f__Iridoviridae",
        "f__Mimiviridae",
    ]


# --------------------------------------------------------------------------------------
# Two denominators, both named
# --------------------------------------------------------------------------------------


@_needs_vmr
def test_both_shares_ship_and_name_their_denominator(swept, checklist) -> None:
    """`of_settled` and `of_all` differ by orders of magnitude for a family-keyed category over
    a class-labelled corpus. Either alone misleads, in opposite directions."""
    tallies, _ = swept
    emitted = tallies[Category.SEGMENTED].to_dict(checklist=checklist, category=Category.SEGMENTED)
    settled = emitted["present_share_of_settled"]
    everything = emitted["present_share_of_all"]
    assert settled["denominator"] < everything["denominator"]
    assert settled["rate"] > everything["rate"]
    for share in (settled, everything):
        assert share["interval"][0] <= share["rate"] <= share["interval"][1]


@_needs_vmr
def test_a_share_over_an_empty_denominator_is_null_not_zero(checklist) -> None:
    """Zero over zero is not a rate, and reporting 0.0 would read as a measured null."""
    tallies, _ = tool.sweep_joined(
        {}, checklist=checklist, route="unresolved", element_kind="free_virus"
    )
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert emitted["present_share_of_all"]["rate"] is None


# --------------------------------------------------------------------------------------
# Measured zeros, not absent rows
# --------------------------------------------------------------------------------------


@_needs_vmr
def test_members_with_no_record_are_listed(swept, checklist) -> None:
    """47 of the 48 segmented families are not in this census, and every one is named."""
    tallies, _ = swept
    emitted = tallies[Category.SEGMENTED].to_dict(checklist=checklist, category=Category.SEGMENTED)
    assert "Orthomyxoviridae" in emitted["members_without_a_record"]
    assert len(emitted["members_without_a_record"]) == emitted["members"] - 1


@_needs_vmr
def test_a_category_with_no_detections_reports_a_measured_zero(checklist) -> None:
    tallies, _ = tool.sweep_joined(
        {"r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;": 10},
        checklist=checklist,
        route="unresolved",
        element_kind="free_virus",
    )
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert emitted["verdicts"].get("present", 0) == 0
    assert emitted["verdicts"]["absent"] == 10
    # Decided at class, not unlabelled: the zero rests on a label that genuinely excludes the
    # phylum, and `decided_at` is what lets a reader see which label that was.
    assert emitted["decided_at"] == {"phylum": 10}
    assert emitted["members_without_a_record"] == ["Nucleocytoviricota"]


@_needs_vmr
def test_satellites_are_not_summed(swept, checklist) -> None:
    """Two categories, two rows. A single satellite number would be the one a reader quotes."""
    tallies, _ = swept
    viruses = tallies[Category.SATELLITE_VIRUS].to_dict(
        checklist=checklist, category=Category.SATELLITE_VIRUS
    )
    acids = tallies[Category.SATELLITE_NUCLEIC_ACID].to_dict(
        checklist=checklist, category=Category.SATELLITE_NUCLEIC_ACID
    )
    assert viruses["verdicts"]["present"] == 2
    assert acids["verdicts"]["present"] == 7
    assert viruses["category"] != acids["category"]


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


def test_the_conformance_route_cannot_be_asserted_by_this_detector() -> None:
    """A2.5 relies on `route_for` refusing it. Pinned here because the whole reason the sweep
    may report survival without a conformance claim is that this call raises (§7, D-022)."""
    with pytest.raises(ManifestError, match="candidate conformance"):
        route_for(policyspec.Outcome.REMOVED)


@_needs_vmr
def test_present_records_carry_a_route_and_an_element_kind(swept, checklist) -> None:
    tallies, _ = swept
    emitted = tallies[Category.NCLDV].to_dict(checklist=checklist, category=Category.NCLDV)
    assert emitted["routes"] == {Route.UNRESOLVED.value: 800}
    assert emitted["element_kinds"] == {"free_virus": 800}


def test_outcome_of_reads_the_field_a1_4_actually_writes() -> None:
    """A1.4 writes `uniform_outcome`. Reading `outcome` alone would silently route everything
    as `unresolved` — a plausible-looking table built on a field that is not there."""
    assert tool.outcome_of({"uniform_outcome": "out_of_scope"}) is policyspec.Outcome.OUT_OF_SCOPE
    assert tool.outcome_of({"outcome": "retained"}) is policyspec.Outcome.RETAINED
    assert tool.outcome_of({}) is None
    assert tool.outcome_of({"uniform_outcome": "not-an-outcome"}) is None


# --------------------------------------------------------------------------------------
# What was not swept is listed, with a reason
# --------------------------------------------------------------------------------------


def test_every_unswept_component_gets_a_reason() -> None:
    """`metrics/manifests.md`'s rule: a table that silently covered part of a release reads as a
    verdict on all of it."""
    from amazebio import corpora

    for release in ("opengenome", "opengenome2", "esm3-proxy"):
        for source in corpora.sources_for(release):
            why = tool._why_not(source, release)
            assert why and isinstance(why, str)
            assert why != ""


def test_the_proxy_corpus_says_why_a_category_is_not_expressible() -> None:
    from amazebio import corpora

    sources = corpora.sources_for("esm3-proxy")
    assert sources, "the proxy corpus declares no sources"
    assert "no viral taxonomy" in tool._why_not(sources[0], "esm3-proxy")


def test_notes_warn_against_reading_a_zero_as_absence() -> None:
    notes = " ".join(tool._notes(True))
    assert "not evidence of absence" in notes
    assert "conformance_failure" in notes
    unsearched = " ".join(tool._notes(False))
    assert "zero by construction" in unsearched


# --------------------------------------------------------------------------------------
# Labelling
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("taxonomy", "expected"),
    [
        ({"family": "Mimiviridae"}, "f__Mimiviridae"),
        ({"genus": "Mimivirus", "family": "Mimiviridae"}, "g__Mimivirus"),
        ({"phylum": "Nucleocytoviricota"}, "p__Nucleocytoviricota"),
    ],
)
def test_a_detection_is_attributed_to_the_records_finest_label(
    taxonomy: dict[str, str], expected: str
) -> None:
    detail = problemtaxa.VerdictDetail(Verdict.PRESENT, matched=("phylum", "Nucleocytoviricota"))
    assert tool._label(detail, taxonomy) == expected


def test_a_detection_with_no_usable_label_falls_back_to_the_member() -> None:
    detail = problemtaxa.VerdictDetail(Verdict.PRESENT, matched=("phylum", "Nucleocytoviricota"))
    assert tool._label(detail, {"species": "something"}) == "Nucleocytoviricota"

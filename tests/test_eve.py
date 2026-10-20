"""A2.3's retroelement arm: the acceptance rule and the detections — D-186.

The acceptance rule is the part a reviewer will check, so each of its three conditions gets a
test that fails if that condition alone is dropped. The identity-normalisation test is the one
that matters most: a percentage read as a fraction loosens the cut by two orders of magnitude
and every table would still look plausible.
"""

from __future__ import annotations

import pytest

from amazebio.eve import (
    ACCEPT,
    DETECTOR,
    ELEMENT_KIND,
    MMSEQS_FORMAT,
    Alignment,
    EveError,
    accept,
    detections_for,
    parse_alignments,
)
from amazebio.survival import ElementKind, Route


def row(
    family="DF000000001.1",
    contig="contig1",
    fident=0.9,
    alnlen=500,
    evalue=1e-30,
    bits=400.0,
) -> str:
    values = {
        "query": family,
        "target": contig,
        "fident": fident,
        "alnlen": alnlen,
        "evalue": evalue,
        "bits": bits,
    }
    return "\t".join(str(values[name]) for name in MMSEQS_FORMAT)


def aln(**kw) -> Alignment:
    base = {
        "family_id": "DF000000001.1",
        "contig": "contig1",
        "identity": 0.9,
        "alignment_length": 500,
        "evalue": 1e-30,
        "bits": 400.0,
    }
    return Alignment(**{**base, **kw})


# --- parsing -------------------------------------------------------------------------------


def test_columns_are_read_by_name():
    (parsed,) = list(parse_alignments([row(family="DF7.2", contig="ctg9", alnlen=321)]))
    assert parsed.family_id == "DF7.2"
    assert parsed.contig == "ctg9"
    assert parsed.alignment_length == 321


def test_a_percentage_identity_is_normalised_not_accepted_as_a_fraction():
    """Read as a fraction, 85.0 would pass a 0.70 cut on anything above 0.7%."""
    (parsed,) = list(parse_alignments([row(fident=85.0)]))
    assert parsed.identity == 0.85


def test_an_identity_that_is_neither_a_fraction_nor_a_percentage_raises():
    with pytest.raises(EveError, match="neither a fraction nor a percentage"):
        list(parse_alignments([row(fident=850.0)]))


def test_blank_and_comment_lines_are_skipped():
    assert len(list(parse_alignments(["", "# header", row(), "  "]))) == 1


def test_a_row_with_the_wrong_field_count_raises():
    with pytest.raises(EveError, match="expected 6"):
        list(parse_alignments(["a\tb\tc"]))


# --- the acceptance rule, one test per condition ----------------------------------------------


def test_a_hit_satisfying_every_condition_is_accepted():
    assert accept(aln())


def test_the_evalue_condition_is_enforced():
    assert accept(aln(evalue=ACCEPT["max_evalue"]))
    assert not accept(aln(evalue=ACCEPT["max_evalue"] * 10))


def test_the_alignment_length_condition_is_enforced():
    assert accept(aln(alignment_length=int(ACCEPT["min_alignment_length"])))
    assert not accept(aln(alignment_length=int(ACCEPT["min_alignment_length"]) - 1))


def test_the_identity_condition_is_enforced():
    assert accept(aln(identity=ACCEPT["min_identity"]))
    assert not accept(aln(identity=ACCEPT["min_identity"] - 0.01))


def test_the_rule_is_a_conjunction_so_one_failure_rejects():
    assert not accept(aln(identity=0.99, alignment_length=10))
    assert not accept(aln(identity=0.99, evalue=1.0))


def test_the_declared_rule_is_the_one_d186_fixed():
    assert ACCEPT == {"max_evalue": 1e-10, "min_alignment_length": 100, "min_identity": 0.70}


# --- detections ----------------------------------------------------------------------------


def kwargs(route=Route.OUT_OF_SCOPE):
    return {
        "record_id": "GCA_000000001.1",
        "route": route,
        "registry": "dfam-curated-ltr",
        "registry_version": "4.0",
    }


def test_many_copies_of_one_family_are_one_detection():
    """Counting alignments would report an element's copy number as families detected."""
    alignments = [aln(contig=f"c{i}", identity=0.8 + i / 1000) for i in range(2000)]
    detections = detections_for(alignments, **kwargs())
    assert len(detections) == 1
    assert detections[0].score == pytest.approx(0.8 + 1999 / 1000)


def test_distinct_families_are_distinct_detections_sorted_by_family():
    alignments = [aln(family_id=f"DF{i}.1") for i in (3, 1, 2)]
    detections = detections_for(alignments, **kwargs())
    assert [d.family_id for d in detections] == ["DF1.1", "DF2.1", "DF3.1"]


def test_rejected_alignments_produce_no_detection():
    assert detections_for([aln(identity=0.1), aln(alignment_length=5)], **kwargs()) == []


def test_a_family_with_one_good_and_many_bad_alignments_is_detected_once():
    alignments = [aln(identity=0.2, contig=f"c{i}") for i in range(50)] + [aln(identity=0.95)]
    detections = detections_for(alignments, **kwargs())
    assert len(detections) == 1
    assert detections[0].score == pytest.approx(0.95)


def test_every_detection_carries_the_arms_detector_kind_and_threshold():
    (detection,) = detections_for([aln()], **kwargs())
    assert detection.detector == DETECTOR
    assert detection.element_kind is ELEMENT_KIND is ElementKind.ENDOGENOUS_RETROELEMENT
    assert detection.threshold == ACCEPT["min_identity"]
    assert detection.registry == "dfam-curated-ltr"


def test_the_route_is_carried_through_not_inferred():
    for route in (Route.OUT_OF_SCOPE, Route.RETAINED_BY_DESIGN):
        (detection,) = detections_for([aln()], **kwargs(route))
        assert detection.route is route


def test_a_stricter_rule_can_be_applied_without_re_searching():
    """The reason identity is the score: score and threshold share an axis."""
    alignments = [aln(identity=0.75), aln(family_id="DF2.1", identity=0.95)]
    strict = {**ACCEPT, "min_identity": 0.90}
    assert len(detections_for(alignments, **kwargs())) == 2
    kept = detections_for(alignments, rule=strict, **kwargs())
    assert [d.family_id for d in kept] == ["DF2.1"]
    assert kept[0].threshold == 0.90

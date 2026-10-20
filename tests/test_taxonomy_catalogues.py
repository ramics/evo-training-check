"""The catalogue benchmark-feasibility pass in `tools/taxonomy_catalogues.py` — task A4.4.

What these tests hold in place is the definition of "benchmarkable", because that word is
doing the work in A4.4's result. A method is benchmarkable here only if the records it
labelled *and* the denylist removes carry ground truth that is independent of the label.
Three ways that can fail, and each has a test: no such record exists, the ground truth and
the label are the same fact, or there are so few that the interval carries nothing.

The remaining tests pin the counting rules themselves: a hit on `order` is recorded as a
coarser claim than one on `family` and not merged with it, and the share that matters is the
one after the confidence gate, because that gate runs before the denylist.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "taxonomy_catalogues.py"
_spec = importlib.util.spec_from_file_location("taxonomy_catalogues_under_test", _PATH)
tc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tc
_spec.loader.exec_module(tc)

from amazebio import imgvr  # noqa: E402
from amazebio.misassignment import Denylist  # noqa: E402

FAMILIES = frozenset({"Coronaviridae"})
ORDERS = frozenset({"Picornavirales"})
RATIFIED = frozenset({"Coronaviridae", "Picornavirales", "Riboviria", "Pisuviricota"})
DENYLIST = Denylist(FAMILIES, ORDERS, "test")
VMR = tc.ictv.release(tc.VMR_RELEASE)

HEADER = [
    "UVIG",
    "Taxon_oid",
    "Scaffold_oid",
    "Coordinates ('whole' if the UViG is the entire contig)",
    "Ecosystem classification",
    "vOTU",
    "Length",
    "Topology",
    "geNomad score",
    "Confidence",
    "Estimated completeness",
    "Estimated contamination",
    "MIUViG quality",
    "Gene content (total genes;cds;tRNA;geNomad marker)",
    "Taxonomic classification",
    "Taxonomic classification method",
    "Host taxonomy prediction",
    "Host prediction method",
    "Sequence origin (doi)",
]


def row(
    *,
    classification: str,
    method: str,
    confidence: str = "High-confidence",
    quality: str = "Genome fragment",
) -> str:
    fields = [""] * len(HEADER)
    fields[HEADER.index("Confidence")] = confidence
    fields[HEADER.index("MIUViG quality")] = quality
    fields[HEADER.index("Taxonomic classification")] = classification
    fields[HEADER.index("Taxonomic classification method")] = method
    fields[HEADER.index("Length")] = "5000"
    return "\t".join(fields)


def tally(lines: list[str]):
    out = tc.tally_rows(lines, HEADER, FAMILIES, ORDERS, RATIFIED)
    # The fields `scan` adds around the counters, so `report` sees the shape it sees in a run.
    out.update(key="corpora/imgvr/test.tsv", bytes=0, release="2022-12-20", version="v4.1")
    return out


def test_the_header_this_test_uses_is_the_release_s_own() -> None:
    """A drifting column name would make every other test here pass against nothing."""
    for name in imgvr.SEQ_COLUMNS.values():
        assert name in HEADER


def test_a_hit_on_order_is_not_merged_with_a_hit_on_family() -> None:
    out = tally(
        [
            row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="RVMT"),
            row(classification="r__Riboviria;;;;;f__Coronaviridae;;", method="RVMT"),
        ]
    )
    assert out["hits"] == 2
    assert tc._split(out["hits_rank_by_method"], "RVMT") == {"order": 1, "family": 1}


def test_only_denylisted_records_are_counted_as_hits() -> None:
    out = tally(
        [
            row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="geNomad"),
            row(classification="r__Riboviria;;;;o__Durnavirales;;;", method="geNomad"),
            row(classification="", method="geNomad"),
        ]
    )
    assert out["hits"] == 1
    assert out["rows"] == 3


def test_the_share_that_matters_is_the_one_after_the_confidence_gate() -> None:
    """The gate runs before the denylist, so a hit it drops is not a removal the filter makes."""
    lines = (
        [row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="geNomad")]
        + [
            row(
                classification="r__Riboviria;;;;o__Picornavirales;;;",
                method="geNomad",
                confidence="Low-confidence",
            )
            for _ in range(3)
        ]
        + [row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="RVMT")]
    )
    out = tally(lines)
    assert out["hits"] == 5
    assert out["hits_hc"] == 2
    assert out["hits_by_method"]["geNomad"] == 4
    assert out["hits_by_method_hc"]["geNomad"] == 1


def test_a_method_with_no_reference_flagged_hit_is_not_benchmarkable() -> None:
    out = tally([row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="RVMT")] * 40)
    doc = tc.report(out, DENYLIST, vmr=VMR)
    rvmt = next(m for m in doc["methods"] if m["method"] == "RVMT")
    assert rvmt["independent_ground_truth_in_corpus"]["reference_flagged_hits"] == 0
    assert rvmt["benchmarkable"] == "no"
    assert "non-circular evaluation set" in rvmt["why"]


def test_refseq_is_refused_as_circular_even_though_every_hit_has_ground_truth() -> None:
    """Its label and its ground truth are one fact, so a high count is not evidence."""
    out = tally(
        [
            row(
                classification="r__Riboviria;;;;;f__Coronaviridae;;",
                method="RefSeq",
                quality="Reference",
            )
        ]
        * 50
    )
    doc = tc.report(out, DENYLIST, vmr=VMR)
    refseq = next(m for m in doc["methods"] if m["method"] == "RefSeq")
    assert refseq["independent_ground_truth_in_corpus"]["reference_flagged_hits"] == 50
    assert refseq["benchmarkable"] == "no"
    assert "Circular" in refseq["why"]


def test_a_handful_of_ground_truth_records_carries_its_interval_not_a_rate() -> None:
    lines = [row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="geNomad")] * 99
    lines.append(
        row(
            classification="r__Riboviria;;;;o__Picornavirales;;;",
            method="geNomad",
            quality="Reference",
        )
    )
    doc = tc.report(tally(lines), DENYLIST, vmr=VMR)
    genomad = next(m for m in doc["methods"] if m["method"] == "geNomad")
    assert genomad["independent_ground_truth_in_corpus"]["reference_flagged_hits"] == 1
    assert genomad["benchmarkable"] == "only at a depth that cannot carry a rate"
    assert "95% CI" in genomad["why"]


def test_an_unratified_name_anywhere_in_the_lineage_is_counted() -> None:
    """If a catalogue's own novel taxa reached the release, this is where they surface."""
    out = tally(
        [
            row(
                classification="r__Riboviria;;;;o__Picornavirales;f__f.0127.base-Noda;;",
                method="RVMT",
            ),
            row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="RVMT"),
        ]
    )
    assert out["unratified_lineage_by_method"]["RVMT"] == 1


def test_every_catalogue_says_how_it_assigned_and_whether_it_can_be_scored() -> None:
    for method, meta in tc.CATALOGUES.items():
        assert meta.get("what"), method
        assert meta.get("assigned_how"), method
        assert meta.get("benchmarkable"), method


def test_coverage_is_reported_against_the_gated_population() -> None:
    lines = [row(classification="r__Riboviria;;;;o__Picornavirales;;;", method="RVMT")] * 3
    lines += [
        row(
            classification="r__Riboviria;;;;o__Picornavirales;;;",
            method="geNomad",
            confidence="Low-confidence",
        )
    ] * 7
    doc = tc.report(tally(lines), DENYLIST, vmr=VMR)
    cov = doc["coverage"]
    assert cov["share_of_hits"] == pytest.approx(0.7)
    assert cov["share_of_hits_after_gate"] == pytest.approx(0.0)

"""Tests for `tools/taxonomy_dependency.py` — A4.2's input-side pass.

What this pass can get plausibly and badly wrong:

* **Naming the wrong tool.** The headline of the pass is which method the denylist's own
  removals rest on, and that is *not* the method with the largest share of the corpus. On
  the real release geNomad assigns 89.97% of all classifications and 38.56% of the
  denylist's hits, because the denylist names eukaryotic RNA-virus taxa and those labels
  came from elsewhere. A pass that reported only the corpus-wide mix would name geNomad as
  the dependency and be wrong about the thing that matters, so the cross-tab against the
  denylist is tested directly.
* **Counting a share over the wrong denominator.** Every share here divides by a total
  counted independently of the histogram it comes from — the lesson D-074 paid for, and
  A4.1 found the same bug in itself.
* **Reading a `Reference` record's label as a prediction.** Those records carry ground
  truth, so whether they constitute an internal benchmark turns entirely on whether a
  predictor or a lookup assigned them. The cross-tab that decides it must not silently
  conflate the two.
* **Losing a row at a shard boundary**, which looks like the data rather than the reader.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest
from conftest import FakeS3

from amazebio import objectstore

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "taxonomy_dependency.py"
_spec = importlib.util.spec_from_file_location("taxonomy_dependency_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["taxonomy_dependency_under_test"] = tool
_spec.loader.exec_module(tool)

from amazebio.misassignment import Denylist  # noqa: E402

DENYLIST = Denylist(
    families=frozenset({"Coronaviridae", "Geminiviridae"}),
    orders=frozenset({"Picornavirales"}),
    policy="test",
)

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


def _row(
    uvig: str,
    *,
    lineage: str,
    method: str,
    confidence: str = "High-confidence",
    quality: str = "Genome fragment",
    length: str = "5000",
) -> str:
    fields = [""] * len(HEADER)
    fields[0] = uvig
    fields[6] = length
    fields[9] = confidence
    fields[12] = quality
    fields[14] = lineage
    fields[15] = method
    return "\t".join(fields)


def _table(rows: list[str]) -> bytes:
    return ("\t".join(HEADER) + "\n" + "\n".join(rows) + "\n").encode()


def _scan(rows: list[str], *, shards: int = 1) -> dict:
    body = _table(rows)
    fake = FakeS3(body)
    original = objectstore.client
    objectstore.client = lambda: fake  # type: ignore[assignment]
    try:
        pieces = [
            tool._scan_shard("b", "k", start, end, HEADER, DENYLIST.families, DENYLIST.orders)
            for start, end in objectstore.byte_shards(len(body), shards)
        ]
    finally:
        objectstore.client = original  # type: ignore[assignment]
    return tool._merge(pieces)


# --------------------------------------------------------------------------------------
# Strata
# --------------------------------------------------------------------------------------


def test_stratum_edges_are_half_open_from_below() -> None:
    assert tool._stratum(0) == "0-2500"
    assert tool._stratum(2_499) == "0-2500"
    assert tool._stratum(2_500) == "2500-5000"
    assert tool._stratum(199_999) == "80000-200000"
    assert tool._stratum(200_000) == "200000-inf"


# --------------------------------------------------------------------------------------
# Lineage parsing is delegated, not re-derived
# --------------------------------------------------------------------------------------


def test_lineage_parsing_delegates_to_the_single_parser() -> None:
    """D-057 made `conformance.parse_lineage_tag` the one reader of this format."""
    parsed = tool._rank_depth("r__Riboviria;;;c__Pisoniviricetes;o__Picornavirales;f__;;")
    assert parsed["order"] == "Picornavirales"
    assert parsed["class"] == "Pisoniviricetes"
    assert "family" not in parsed  # `f__` names no taxon, so it fills no rank


# --------------------------------------------------------------------------------------
# The scan
# --------------------------------------------------------------------------------------


def test_counts_methods_and_rows() -> None:
    scanned = _scan(
        [
            _row("u1", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="geNomad"),
            _row("u2", lineage="r__Riboviria;;;;;f__Siphoviridae;;", method="vOTU consensus"),
        ]
    )
    assert scanned["rows"] == 2
    assert scanned["method"]["geNomad"] == 1
    assert scanned["method"]["vOTU consensus"] == 1


def test_blank_method_is_labelled_not_dropped() -> None:
    scanned = _scan([_row("u1", lineage="r__Riboviria;;;;;;;", method="")])
    assert scanned["method"][tool.EMPTY] == 1


def test_denylist_hits_are_cross_tabbed_by_method() -> None:
    """The pass's headline: which method the removals rest on, not which is commonest."""
    rows = [
        # One denylist hit, assigned by a method that is a minority of the corpus.
        _row("u1", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="RVMT (doi:x)"),
        # Many non-hits assigned by geNomad.
        *[
            _row(f"g{i}", lineage="r__Duplodnaviria;;;c__Caudoviricetes;;;;", method="geNomad")
            for i in range(9)
        ],
    ]
    scanned = _scan(rows)
    assert scanned["method"]["geNomad"] == 9
    assert scanned["denylisted"] == 1
    assert scanned["method_of_denylisted"] == {"RVMT (doi:x)": 1}


def test_order_denylist_hit_without_a_family_label() -> None:
    scanned = _scan([_row("u1", lineage="r__Riboviria;;;;o__Picornavirales;;;", method="geNomad")])
    assert scanned["denylisted"] == 1


def test_a_taxon_at_the_wrong_rank_is_not_a_hit() -> None:
    """`Picornavirales` written at family must not fire the order rule.

    D-071 found a real release writing one taxon at two ranks, so this is the live case.
    """
    scanned = _scan([_row("u1", lineage="r__Riboviria;;;;;f__Picornavirales;;", method="geNomad")])
    assert scanned["denylisted"] == 0


def test_confidence_gate_subsets_every_tally() -> None:
    rows = [
        _row("u1", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="geNomad"),
        _row(
            "u2",
            lineage="r__Riboviria;;;;;f__Coronaviridae;;",
            method="geNomad",
            confidence="Putative",
        ),
    ]
    scanned = _scan(rows)
    assert scanned["rows"] == 2
    assert scanned["rows_hc"] == 1
    assert scanned["denylisted"] == 2
    assert scanned["denylisted_hc"] == 1


def test_reference_records_are_cross_tabbed_by_method() -> None:
    """Whether an internal benchmark exists turns on this distinction.

    A `Reference` record labelled `RefSeq` has had its own reference looked up: label and
    ground truth are one fact and it tests nothing. One labelled `geNomad` is a real corpus
    record with trustworthy ground truth, scored by a predictor.
    """
    rows = [
        _row(
            "u1",
            lineage="r__Riboviria;;;;;f__Coronaviridae;;",
            method="RefSeq",
            quality="Reference",
        ),
        _row(
            "u2",
            lineage="r__Riboviria;;;;;f__Coronaviridae;;",
            method="geNomad",
            quality="Reference",
        ),
        _row("u3", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="geNomad"),
    ]
    scanned = _scan(rows)
    assert scanned["quality"]["Reference"] == 2
    assert scanned["method_of_reference"] == {"RefSeq": 1, "geNomad": 1}
    assert scanned["reference_family_labelled"]["geNomad|labelled"] == 1


def test_reference_without_a_family_label_is_recorded_as_absent() -> None:
    rows = [
        _row(
            "u1",
            lineage="r__Riboviria;;;c__Pisoniviricetes;;;;",
            method="geNomad",
            quality="Reference",
        )
    ]
    scanned = _scan(rows)
    assert scanned["reference_family_labelled"]["geNomad|absent"] == 1


def test_unparseable_length_is_counted_separately() -> None:
    scanned = _scan([_row("u1", lineage="r__Riboviria;;;;;;;", method="geNomad", length="n/a")])
    assert scanned["length"]["unparseable"] == 1


def test_malformed_row_is_counted_never_dropped_silently() -> None:
    body = _table([_row("u1", lineage="r__Riboviria;;;;;;;", method="geNomad")])
    body += b"too\tfew\tfields\n"
    fake = FakeS3(body)
    original = objectstore.client
    objectstore.client = lambda: fake  # type: ignore[assignment]
    try:
        scanned = tool._scan_shard(
            "b", "k", 0, len(body), HEADER, DENYLIST.families, DENYLIST.orders
        )
    finally:
        objectstore.client = original  # type: ignore[assignment]
    assert scanned["rows"] == 1
    assert scanned["malformed"] == 1


@pytest.mark.parametrize("shards", [1, 2, 3, 5, 9, 17])
def test_sharding_does_not_lose_or_double_count_rows(shards: int) -> None:
    """A row belongs to the shard its first byte falls in, at every split count."""
    rows = [
        _row(
            f"u{i}",
            lineage="r__Riboviria;;;;;f__Coronaviridae;;" if i % 3 == 0 else "r__Riboviria;;;;;;;",
            method="geNomad" if i % 2 else "RVMT (doi:x)",
        )
        for i in range(40)
    ]
    scanned = _scan(rows, shards=shards)
    assert scanned["rows"] == 40
    assert scanned["malformed"] == 0
    assert sum(scanned["method"].values()) == 40
    assert scanned["denylisted"] == len([i for i in range(40) if i % 3 == 0])


# --------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------


def _report(rows: list[str]) -> dict:
    scanned = _scan(rows)
    scanned.update(key="k", bytes=1, release="2022-12-20", version="v4.1")
    return tool.report(scanned, DENYLIST)


def test_report_shares_divide_by_an_independently_counted_total() -> None:
    rows = [
        _row("u1", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="geNomad"),
        _row("u2", lineage="r__Riboviria;;;;;f__Siphoviridae;;", method="geNomad"),
        _row("u3", lineage="r__Riboviria;;;;;f__Siphoviridae;;", method="RVMT (doi:x)"),
        _row("u4", lineage="r__Riboviria;;;;;f__Siphoviridae;;", method="RVMT (doi:x)"),
    ]
    built = _report(rows)
    mix = built["method_mix"]["all_records"]
    assert mix["geNomad"]["share"] == pytest.approx(0.5)
    assert mix["RVMT (doi:x)"]["share"] == pytest.approx(0.5)
    assert sum(entry["records"] for entry in mix.values()) == built["release"]["records"]


def test_report_names_the_genomad_share_of_the_denylists_own_hits() -> None:
    rows = [
        _row("u1", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="geNomad"),
        _row("u2", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="RVMT (doi:x)"),
        _row("u3", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="RVMT (doi:x)"),
        _row("u4", lineage="r__Riboviria;;;;;f__Coronaviridae;;", method="RVMT (doi:x)"),
    ]
    built = _report(rows)
    assert built["denylisted_records"]["records"] == 4
    assert built["denylisted_records"]["genomad_share"] == pytest.approx(0.25)


def test_report_describes_each_method_or_says_it_cannot() -> None:
    """The artefact should state what a method *is*, and admit when the publisher does not."""
    rows = [
        _row("u1", lineage="r__Riboviria;;;;;;;", method="geNomad"),
        _row("u2", lineage="r__Riboviria;;;;;;;", method="RVMT (doi:x)"),
    ]
    mix = _report(rows)["method_mix"]["all_records"]
    assert "marker-based" in mix["geNomad"]["meaning"]
    assert mix["RVMT (doi:x)"]["meaning"] == "not described by the publisher"


def test_report_carries_the_denylist_it_was_run_with() -> None:
    built = _report([_row("u1", lineage="r__Riboviria;;;;;;;", method="geNomad")])
    assert built["denylist"]["families"] == sorted(DENYLIST.families)
    assert built["denylist"]["orders"] == sorted(DENYLIST.orders)


def test_report_shares_are_none_rather_than_zero_when_nothing_was_counted() -> None:
    """An unmeasured share must not appear as 0%."""
    assert tool._share(0, 0) is None
    assert tool._share(1, 2) == 0.5

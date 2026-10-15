"""Tests for the IMG/VR composition counts in `tools/imgvr_composition.py` — task A1.7.

The real pass is 15.8 GB out of object storage, so these drive the counting functions against
a fake S3 client holding small tables of the publisher's own shape. What is worth testing is
not the arithmetic but the judgement calls around it: a row that does not fit its own header is
counted rather than dropped, an absent host prediction is distinguished from a malformed one,
and a reconciliation disagreement is reported rather than raised. §A0 is explicit that
under-specification is a result, and a tool that crashes on it produces no result at all.
"""

from __future__ import annotations

import importlib.util
import io
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "imgvr_composition.py"
_spec = importlib.util.spec_from_file_location("imgvr_composition_under_test", _PATH)
comp = importlib.util.module_from_spec(_spec)
sys.modules["imgvr_composition_under_test"] = comp
_spec.loader.exec_module(comp)

SEQ_HEADER = [
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


def _seq_row(uvig, votu, confidence, host):
    row = [""] * len(SEQ_HEADER)
    row[0], row[5], row[9], row[16] = uvig, votu, confidence, host
    return "\t".join(row)


def _table(header, rows):
    return ("\t".join(header) + "\n" + "\n".join(rows) + "\n").encode()


class FakeClient:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.objects[kw["Key"]])}


BACTERIA = "d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
ARCHAEA = "d__Archaea;p__Euryarchaeota"


def _seq_table():
    return _table(
        SEQ_HEADER,
        [
            _seq_row("UViG_1", "vOTU_1", "High-confidence", BACTERIA),
            _seq_row("UViG_2", "vOTU_1", "High-confidence", ARCHAEA),
            _seq_row("UViG_3", "vOTU_2", "Putative", ""),
            _seq_row("UViG_4", "vOTU_3", "Putative", ";;;;;;"),
            "\t".join(["short", "row"]),
        ],
    )


def test_records_votus_and_the_confidence_split_are_counted():
    client = FakeClient({"k": _seq_table()})
    out = comp.count_sequence_information(client, "b", "k")

    assert out["records"] == 4, "the malformed row is not a record"
    assert out["malformed_rows"] == 1, "and it is not silently dropped either"
    assert out["distinct_votus"] == 3, "two records share vOTU_1"
    assert out["confidence"] == {"High-confidence": 2, "Putative": 2}


def test_an_absent_host_prediction_is_distinguished_from_a_separators_only_one():
    # Which of the two the publisher emits for "no prediction" is not documented, and Evo 1's
    # third rule counts prokaryotic hosts — so collapsing them would hide how that rule's
    # denominator was built.
    client = FakeClient({"k": _seq_table()})
    out = comp.count_sequence_information(client, "b", "k")

    assert out["host_domain"]["Bacteria"] == 1
    assert out["host_domain"]["Archaea"] == 1
    assert out["host_domain"]["(empty)"] == 1
    assert out["host_domain"]["(separators only)"] == 1


def test_the_host_table_separates_rows_from_distinct_uvigs():
    # One UViG can carry several host predictions, so rows and genomes are different
    # denominators and the published rule does not say which it counts.
    header = ["UViG", "Host prediction method", "Host taxonomy prediction"]
    client = FakeClient(
        {
            "k": _table(
                header,
                [
                    f"UViG_1\tCRISPR\t{BACTERIA}",
                    f"UViG_1\tIsolate taxonomy\t{BACTERIA}",
                    f"UViG_2\tCRISPR\t{ARCHAEA}",
                ],
            )
        }
    )
    out = comp.count_host_information(client, "b", "k")

    assert out["rows"] == 3
    assert out["distinct_uvigs"] == 2


def test_a_table_longer_than_one_chunk_is_streamed_without_losing_rows(monkeypatch):
    # The real sequence-information table is 5.0 GB and is read in chunks that fall in the
    # middle of lines. A row split across two chunk boundaries must still be one row.
    monkeypatch.setattr(comp, "_CHUNK", 7)
    rows = [_seq_row(f"UViG_{i}", f"vOTU_{i}", "Putative", BACTERIA) for i in range(50)]
    client = FakeClient({"k": _table(SEQ_HEADER, rows)})
    out = comp.count_sequence_information(client, "b", "k")

    assert out["records"] == 50
    assert out["malformed_rows"] == 0
    assert out["distinct_votus"] == 50


def test_the_high_confidence_check_reports_a_disagreement_rather_than_raising():
    per_release = {
        "2022-09-20": {
            "version": "v4",
            "components": {
                "sequence_information": {
                    "records": 100,
                    "confidence": {"High-confidence": 40, "Putative": 60},
                    "distinct_votus": 90,
                },
                "sequence_information_high_confidence": {
                    "records": 41,  # one more than the label says
                    "confidence": {"High-confidence": 41},
                    "distinct_votus": 38,
                },
            },
        }
    }
    checks = comp.reconcile(per_release)
    hc = [c for c in checks if c["check"].startswith("high-confidence file")]

    assert len(hc) == 1
    assert hc[0]["agrees"] is False, "a mismatch is a finding, and must survive to the artefact"
    assert hc[0]["high_confidence_file_records"] == 41
    assert hc[0]["high_confidence_label_in_full_file"] == 40


def test_the_erratum_check_only_fires_with_both_releases():
    one = {"2022-09-20": {"version": "v4", "components": {}}}
    assert not [c for c in comp.reconcile(one) if "erratum" in c["check"]]

    both = {
        d: {
            "version": v,
            "components": {
                "sequence_information": {
                    "records": n,
                    "confidence": {"High-confidence": 1},
                    "distinct_votus": 1,
                }
            },
        }
        for d, v, n in [("2022-09-20", "v4", 100), ("2022-12-20", "v4.1", 103)]
    }
    erratum = [c for c in comp.reconcile(both) if "erratum" in c["check"]]
    assert len(erratum) == 1
    assert erratum[0]["record_difference"] == 3


def test_the_evo1_comparison_uses_the_published_figure_not_the_released_census():
    # Both are recorded and they differ by one record (D-055). The retained fraction must be
    # against Evo 1's own stated figure; A7.1's census of the release is the separate number.
    per_release = {
        "2022-09-20": {
            "version": "v4",
            "components": {
                "sequence_information": {
                    "records": 5_000_000,
                    "confidence": {},
                    "distinct_votus": 1,
                }
            },
        }
    }
    (check,) = [c for c in comp.reconcile(per_release) if "Table S3" in c["check"]]

    assert check["evo1_table_s3_records"] == comp.EVO1_TABLE_S3_RECORDS
    assert check["a7_1_released_records"] == comp.A7_1_RELEASED_RECORDS
    assert check["evo1_table_s3_records"] != check["a7_1_released_records"]
    assert check["retained_fraction_vs_table_s3"] == comp.EVO1_TABLE_S3_RECORDS / 5_000_000

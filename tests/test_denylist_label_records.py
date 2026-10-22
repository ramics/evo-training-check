"""The join in `tools/denylist_label_records.py` — task X1.9.

The arithmetic here is a set intersection; what can be wrong without anything failing is
everything around it. Four things are therefore the thing under test: that the denylist rule is
the *published* one executed rather than a matching rule reinvented in this tool, that the label
table's columns are read by name rather than by position, that the publisher's digest is checked
over the bytes actually read, and that the three readings of the filter are required to agree
about which records carry a detection.

No test touches object storage or the network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys

import pytest
from conftest import FakeS3

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "denylist_label_records.py"
_spec = importlib.util.spec_from_file_location("denylist_label_records_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["denylist_label_records_under_test"] = tool
_spec.loader.exec_module(tool)

CIRCO = "r__Monodnaviria;k__Shotokuvirae;p__Cressdnaviricota;c__Arfiviricetes;o__Cirlivirales;f__Circoviridae;;"  # noqa: E501
PHAGE = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;"
RETRO = "r__Riboviria;k__Pararnavirae;p__Artverviricota;c__Revtraviricetes;o__Ortervirales;f__Retroviridae;;"  # noqa: E501


def label_table(
    rows: list[tuple[str, str, str]], *, columns: tuple[str, ...] | None = None
) -> bytes:
    """A label table in the real file's shape: nineteen columns, three of which are read."""
    columns = columns or (
        "UVIG",
        "Taxon_oid",
        "Taxonomic classification",
        "Taxonomic classification method",
        "Length",
    )
    lines = ["\t".join(columns)]
    for uvig, lineage, method in rows:
        cell = {
            "UVIG": uvig,
            "Taxonomic classification": lineage,
            "Taxonomic classification method": method,
            "Taxon_oid": "123",
            "Length": "5000",
        }
        lines.append("\t".join(cell[c] for c in columns))
    return ("\n".join(lines) + "\n").encode()


def entry_for(body: bytes, *, md5: str | None = None) -> dict:
    return {
        "id": tool.SOURCE_ID,
        "held_at": "s3://bucket/corpora/imgvr/2022-09-20/table.tsv",
        "md5": md5 or hashlib.md5(body, usedforsecurity=False).hexdigest(),
        "bytes": len(body),
    }


class FakeDetections(FakeS3):
    """`FakeS3` that also answers `get_object` for the three published per-hit tables."""

    def __init__(self, body: bytes, per_reading: dict[str, list[str]]) -> None:
        super().__init__(body)
        self.per_reading = per_reading

    def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
        for reading, ids in self.per_reading.items():
            if Key == tool.detections_key(reading):
                rows = "".join(json.dumps({"record_id": i}) + "\n" for i in ids)
                return {"Body": _Bytes(rows.encode())}
        return super().get_object(Bucket=Bucket, Key=Key, Range=Range)


class _Bytes:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self, size: int = -1) -> bytes:
        out = self.data if size is None or size < 0 else self.data[:size]
        self.data = b"" if size is None or size < 0 else self.data[size:]
        return out


# --------------------------------------------------------------------------------------
# The rule is the published one, executed
# --------------------------------------------------------------------------------------


class TestTheRuleComesFromTheSpec:
    def test_it_is_the_family_rank_denylist_of_nineteen_groups(self) -> None:
        rule = tool.denylist_rule()
        assert rule.kind == "remove_if_taxon_in"
        assert rule.params["rank"] == "family"
        assert len(rule.params["names"]) == 19
        assert "Circoviridae" in rule.params["names"]

    def test_a_denylisted_family_label_is_removed_by_the_published_rule(self) -> None:
        assert self.outcome(CIRCO) == "removed"
        assert self.outcome(RETRO) == "removed"

    def test_a_label_naming_no_denylisted_family_is_not(self) -> None:
        # A caudovirus is the overwhelming majority of this component and names no denylisted
        # family at any rank, so the rule does not fire on it at all.
        assert self.outcome(PHAGE) is None

    def test_a_record_with_no_family_rank_at_all_is_not_a_match(self) -> None:
        assert self.outcome("r__Monodnaviria;;;;;;;") is None

    def outcome(self, lineage: str) -> str | None:
        from amazebio import policyspec
        from amazebio.conformance import parse_lineage_tag

        tag = parse_lineage_tag(lineage)
        decision = policyspec.decide(
            tool.denylist_rule(),
            policyspec.Record(id="x", component=tool.COMPONENT, taxonomy=dict(tag.taxonomy)),
            kept_values={},
        )
        return None if decision is None else decision.outcome.value


# --------------------------------------------------------------------------------------
# The label table
# --------------------------------------------------------------------------------------


class TestReadingTheLabelTable:
    def test_the_wanted_records_labels_come_back(self) -> None:
        body = label_table(
            [("A", CIRCO, "reference"), ("B", PHAGE, "geNomad"), ("C", RETRO, "geNomad")]
        )
        found, counts = tool.stream_labels(
            FakeS3(body), entry=entry_for(body), wanted={"A", "C", "Z"}
        )
        assert set(found) == {"A", "C"}
        assert found["A"] == (CIRCO, "reference")
        assert counts["rows"] == 3 and counts["md5_verified"]

    def test_columns_are_read_by_name_not_by_position(self) -> None:
        # The real file has nineteen columns and one header containing a comma and a
        # parenthesis; a positional read is a silent dependency on their order.
        shuffled = (
            "Length",
            "Taxonomic classification method",
            "UVIG",
            "Taxonomic classification",
            "Taxon_oid",
        )
        body = label_table([("A", CIRCO, "reference")], columns=shuffled)
        found, _ = tool.stream_labels(FakeS3(body), entry=entry_for(body), wanted={"A"})
        assert found["A"] == (CIRCO, "reference")

    def test_a_missing_column_is_a_refusal(self) -> None:
        body = label_table([("A", CIRCO, "reference")], columns=("UVIG", "Length"))
        with pytest.raises(SystemExit, match="no 'Taxonomic classification' column"):
            tool.stream_labels(FakeS3(body), entry=entry_for(body), wanted={"A"})

    def test_a_row_crossing_a_read_boundary_is_still_one_row(self) -> None:
        rows = [(f"R{i}", CIRCO, "reference") for i in range(200)]
        body = label_table(rows)
        found, counts = tool.stream_labels(
            FakeS3(body), entry=entry_for(body), wanted={r[0] for r in rows}
        )
        assert counts["rows"] == 200
        assert len(found) == 200

    def test_the_last_row_without_a_trailing_newline_is_not_lost(self) -> None:
        body = label_table([("A", CIRCO, "reference"), ("B", RETRO, "geNomad")]).rstrip(b"\n")
        found, counts = tool.stream_labels(FakeS3(body), entry=entry_for(body), wanted={"A", "B"})
        assert counts["rows"] == 2 and set(found) == {"A", "B"}

    def test_a_digest_that_is_not_the_publishers_is_a_refusal(self) -> None:
        # The pin is the publisher's md5 over the whole object, which is why the whole object is
        # read: a digest over part of a file pins nothing.
        body = label_table([("A", CIRCO, "reference")])
        with pytest.raises(SystemExit, match="is not the publisher's"):
            tool.stream_labels(FakeS3(body), entry=entry_for(body, md5="0" * 32), wanted={"A"})

    def test_a_staged_object_of_another_length_is_refused_before_the_read(self) -> None:
        body = label_table([("A", CIRCO, "reference")])
        entry = entry_for(body) | {"bytes": len(body) + 1}
        client = FakeS3(body)
        with pytest.raises(SystemExit, match="is a different release"):
            tool.stream_labels(client, entry=entry, wanted={"A"})
        assert client.ranges == []


# --------------------------------------------------------------------------------------
# The detected set
# --------------------------------------------------------------------------------------


class TestTheDetectedRecordSet:
    def test_the_three_readings_agreeing_gives_one_set(self) -> None:
        ids = ["A", "B", "A"]
        client = FakeDetections(b"", {r: list(ids) for r in tool.READINGS})
        detected, tables = tool.detected_records(client)
        assert detected == {"A", "B"}
        assert [t["reading"] for t in tables] == list(tool.READINGS)
        assert all(t["sha256"] for t in tables)

    def test_a_disagreement_is_a_refusal_rather_than_a_union(self) -> None:
        # Every taxonomy rule is unresolvable against this component, so the readings cannot
        # differ here; a union would paper over a table that is not what it claims to be.
        per_reading = {r: ["A", "B"] for r in tool.READINGS}
        per_reading[tool.READINGS[1]] = ["A"]
        with pytest.raises(SystemExit, match="disagree about which records"):
            tool.detected_records(FakeDetections(b"", per_reading))


class TestTheWritePath:
    def test_only_the_canonical_directory_publishes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        assert tool.durable_for(tmp_path) is None
        assert tool.durable_for(tool.OUTDIR) == tool.objectstore.durable_results("x1-9")


class TestTheTableItWrites:
    def test_the_columns_are_the_five_and_carry_no_sequence(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        rows = [
            {
                "record_id": "A",
                "denylisted_family": "Circoviridae",
                "rule_outcome": "removed",
                "label_method": "reference",
                "taxonomy": CIRCO,
            }
        ]
        path = tool.write_table(tmp_path / "t.tsv", rows)
        header, row = path.read_text().splitlines()
        assert header.split("\t") == list(tool.COLUMNS)
        assert row.split("\t")[0] == "A"
        assert "ACGT" not in path.read_text()

    def test_the_summary_states_the_floor_and_the_two_ceilings(self) -> None:
        doc = {
            "summary": {
                "release": "opengenome2",
                "component": "IMG/VR",
                "counts": {
                    "detected_records": 100,
                    "found_in_label_table": 90,
                    "absent_from_label_table": 10,
                    "labelled_at_family_rank": 20,
                    "denylisted_label_records": 3,
                },
                "per_family": {"Circoviridae": 3},
                "by_label_method": {"reference": 3},
            }
        }
        text = tool.summarise(doc)
        assert "floor, not a census" in text
        assert "unlabelled here rather than" in text
        assert "Internal under X3.1" in text

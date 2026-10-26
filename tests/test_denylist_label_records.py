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
        "source": tool.SOURCE_ID,
        "release": tool.LABEL_RELEASE,
        "held_at": "s3://bucket/corpora/imgvr/2022-09-20/table.tsv",
        "md5": md5 or hashlib.md5(body, usedforsecurity=False).hexdigest(),
        "bytes": len(body),
    }


class FakeDetections(FakeS3):
    """`FakeS3` that also answers for the three per-hit tables and X1.8's family table.

    `per_reading` maps a reading to its `(record_id, family_id)` hit rows, which is the shape
    the published table has: one row per hit, so a record appears once per family it hits.
    """

    def __init__(
        self,
        body: bytes,
        per_reading: dict[str, list[tuple[str, str]]],
        named: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body)
        self.per_reading = per_reading
        self.named = named if named is not None else {"PF00001": "Circoviridae"}

    def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
        for reading, rows in self.per_reading.items():
            if Key == tool.detections_key(reading):
                body = "".join(json.dumps({"record_id": r, "family_id": f}) + "\n" for r, f in rows)
                return {"Body": _Bytes(body.encode())}
        if Key == tool.NAMED_FAMILIES_KEY:
            lines = ["accession\tname\tdenylisted_group"]
            lines += [f"{a}\tX\t{g}" for a, g in self.named.items()]
            return {"Body": _Bytes(("\n".join(lines) + "\n").encode())}
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


class TestTheLabelTablePin:
    """The digest is the publisher's own, read from their captured listing.

    `AGENTS.md`'s rule is that a pin is the publisher's digest and never a checksum of bytes
    already held. The listing holds forty-two files across ten dated releases and two of those
    releases carry this file name with different bytes, so the selection is by date *and* name.
    """

    def test_the_pin_is_the_publishers_digest_for_the_dated_release(self) -> None:
        pin = tool.label_table_pin()
        assert pin["source"] == "S-IMGVR-JGI-INVENTORY"
        assert pin["release"] == tool.LABEL_RELEASE == "2022-09-20"
        assert pin["md5"] == "a2eedc151e557a78a327d6bf9a95bd25"
        assert pin["bytes"] == 1_888_622_388
        assert pin["md5_source"].startswith("S-IMGVR-JGI-INVENTORY")

    def test_the_staged_key_is_derived_from_the_release_and_the_file_name(self) -> None:
        assert tool.label_table_key("2022-09-20", "x.tsv") == "corpora/imgvr/2022-09-20/x.tsv"
        assert tool.label_table_key(tool.LABEL_RELEASE, tool.LABEL_FILE) in pin_key()

    def test_the_other_release_of_the_same_file_name_is_a_different_size(self) -> None:
        # Which is what the length check in `stream_labels` uses to tell them apart.
        import json

        listing = json.loads(tool.INVENTORY.read_text())
        sizes = {
            f["added_date"]: f["file_size"]
            for f in listing["files"]
            if f["file_name"] == tool.LABEL_FILE
        }
        assert len(sizes) > 1
        assert len(set(sizes.values())) == len(sizes)


def pin_key() -> str:
    return tool.label_table_pin()["held_at"]


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


HITS = [("A", "PF00001"), ("A", "PF99999"), ("B", "PF99999"), ("C", "PF00001")]


class TestTheDetectedRecordSet:
    def test_the_three_readings_agreeing_gives_one_set(self) -> None:
        client = FakeDetections(b"", {r: list(HITS) for r in tool.READINGS})
        named, _ = tool.denylist_named_families(client)
        detected, hits, tables = tool.detected_records(client, named)
        assert detected == {"A", "B", "C"}
        # Only the records whose *detected family* is one X1.8 named: B hit PF99999 only.
        assert hits == {"A": ["PF00001"], "C": ["PF00001"]}
        assert [t["reading"] for t in tables] == list(tool.READINGS)
        assert all(t["sha256"] for t in tables)

    def test_a_disagreement_is_a_refusal_rather_than_a_union(self) -> None:
        # Every taxonomy rule is unresolvable against this component, so the readings cannot
        # differ here; a union would paper over a table that is not what it claims to be.
        per_reading = {r: list(HITS) for r in tool.READINGS}
        per_reading[tool.READINGS[1]] = HITS[:1]
        with pytest.raises(SystemExit, match="disagree about which records"):
            tool.detected_records(FakeDetections(b"", per_reading), {"PF00001": "Circoviridae"})

    def test_hits_are_counted_from_one_named_reading(self) -> None:
        # D-247: the detected set is the three readings' agreement, a per-record hit list is a
        # measurement of one table, and mixing them would sum over overlapping corpora.
        assert tool.HIT_READING in tool.READINGS

    def test_the_family_axis_comes_from_x1_8s_published_table_with_its_digest(self) -> None:
        client = FakeDetections(b"", {r: list(HITS) for r in tool.READINGS})
        named, table = tool.denylist_named_families(client)
        assert named == {"PF00001": "Circoviridae"}
        assert table["key"] == tool.NAMED_FAMILIES_KEY and table["sha256"]

    def test_a_family_table_of_the_wrong_shape_is_a_refusal(self) -> None:
        class Wrong(FakeDetections):
            def get_object(self, Bucket: str, Key: str, Range: str | None = None) -> dict:
                if Key == tool.NAMED_FAMILIES_KEY:
                    return {"Body": _Bytes(b"accession\tname\n PF1\tX\n")}
                return super().get_object(Bucket=Bucket, Key=Key, Range=Range)

        with pytest.raises(SystemExit, match="denylisted_group"):
            tool.denylist_named_families(Wrong(b"", {}))


class TestTheWritePath:
    def test_only_the_canonical_directory_publishes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        assert tool.durable_for(tmp_path) is None
        assert tool.durable_for(tool.OUTDIR) == tool.objectstore.durable_results("x1-9")


class TestTheTableItWrites:
    def test_the_columns_carry_no_sequence(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        rows = [
            {
                "record_id": "IMGVR_A",
                "component": "IMG/VR",
                "pfam_families": "PF00001",
                "denylisted_groups_named": "Circoviridae",
                "in_label_table": True,
                "label_family": "Circoviridae",
                "label_method": "reference",
                "label_rule_outcome": "removed",
                "taxonomy": CIRCO,
            }
        ]
        written = tool.write_tables(tmp_path, "t", rows)
        header, row = written[0].read_text().splitlines()
        assert header.split("\t") == list(tool.COLUMNS)
        assert row.split("\t")[0] == "IMGVR_A"
        assert "ACGT" not in written[0].read_text()

    def test_each_component_gets_its_own_list(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The consumer streams one staged object, so a mixed list reports the other
        component's records as missing from a corpus they were never in."""
        rows = [
            {c: "" for c in tool.COLUMNS} | {"record_id": "IMGVR_1", "component": "IMG/VR"},
            {c: "" for c in tool.COLUMNS} | {"record_id": "IMGPR_1", "component": "IMG/PR"},
        ]
        written = {p.name: p for p in tool.write_tables(tmp_path, "t", rows)}
        assert set(written) == {"t.tsv", "t-imgvr.tsv", "t-imgpr.tsv"}
        assert "IMGPR_1" not in written["t-imgvr.tsv"].read_text()
        assert written["t-imgvr.tsv"].read_text().count("\n") == 2  # header and one row


class TestTheComponentOfARecord:
    def test_the_two_declared_prefixes(self) -> None:
        assert tool.component_of("IMGVR_UViG_1_1") == "IMG/VR"
        assert tool.component_of("IMGPR_plasmid_1_1") == "IMG/PR"

    def test_an_undeclared_prefix_is_a_refusal_rather_than_a_guess(self) -> None:
        # A2.1's rows carry no component field, so the prefix is the only signal; filing a
        # record under the wrong component joins it against a table that cannot contain it.
        with pifail():
            tool.component_of("GTDB_something_1")


def pifail():
    import pytest as _pytest

    return _pytest.raises(SystemExit, match="belongs to no declared component")

    def test_the_summary_keeps_the_two_axes_apart(self) -> None:
        doc = {
            "summary": {
                "release": "opengenome2",
                "component": "IMG/VR",
                "counts": {
                    "detected_records": 100,
                    "found_in_label_table": 90,
                    "absent_from_label_table": 10,
                    "labelled_at_family_rank": 20,
                    "records_with_denylist_named_family_hit": 7,
                    "of_those_in_label_table": 6,
                    "of_those_with_a_family_label": 4,
                    "of_those_the_label_rule_removes": 2,
                    "records_the_label_rule_removes": 3,
                },
                "per_group_named": {"Circoviridae": 7},
                "by_label_method": {"reference": 6},
            }
        }
        text = tool.summarise(doc)
        assert "Neither contains the other." in text
        assert "A floor:" in text
        assert "unlabelled here" in text
        assert "Internal under X3.1" in text

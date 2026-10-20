"""The repeated-accession pass decides a question two earlier tasks declined to decide.

A7.1 and A7.2 both counted the 39,974 and neither read a base, because the header cannot
tell a duplicated entry from a record published in parts. This pass tells them apart by
arithmetic against the publisher's own length, so the arithmetic is what these tests pin —
including the case where the release and the input simply disagree, which must not be
rounded into either of the other two.
"""

from __future__ import annotations

import array
import gzip
import importlib.util
import io
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "evo2_duplicates",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "evo2_duplicates.py",
)
assert _spec and _spec.loader
dup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dup)


class TestUnpackingAnAccession:
    def test_it_round_trips_the_publishers_own_form(self):
        from amazebio import imgvr

        for accession in ("IMGVR_UViG_2505313053_000001", "IMGVR_UViG_2510461032_000002"):
            assert dup.unpack(imgvr.uvig_key(accession)) == accession


class TestFindingTheRepeats:
    def test_an_accession_seen_once_is_not_repeated(self):
        keys, lengths = array.array("q", [1, 2]), array.array("q", [10, 20])
        assert dup.repeated(keys, lengths, {}) == {}

    def test_both_populations_come_back_on_one_key(self):
        """Dropping the giant-virus MAG forms here would lose them from the whole answer."""
        from amazebio import imgvr

        packed = imgvr.uvig_key("IMGVR_UViG_2505313053_000001")
        out = dup.repeated(
            array.array("q", [packed, packed]),
            array.array("q", [10, 20]),
            {"IMGVR_UViG_GVMAG-M-3300000115-12_000001": [5, 6], "lonely": [7]},
        )
        assert out == {
            "IMGVR_UViG_2505313053_000001": [10, 20],
            "IMGVR_UViG_GVMAG-M-3300000115-12_000001": [5, 6],
        }

    def test_mismatched_arrays_are_an_error_rather_than_a_silent_truncation(self):
        with pytest.raises(ValueError):
            dup.repeated(array.array("q", [1, 2]), array.array("q", [10]), {})


class TestClassifyingARepeat:
    def test_every_occurrence_at_the_published_length_is_a_republished_record(self):
        out = dup.classify({"a": [500, 500]}, {"a": 500})
        assert out["by_outcome"] == {"republished_whole": 1}
        assert out["republished_whole"]["surplus_records"] == 1
        assert out["republished_whole"]["surplus_nucleotides"] == 500

    def test_occurrences_summing_to_the_published_length_are_parts_of_one_record(self):
        out = dup.classify({"a": [300, 200]}, {"a": 500})
        assert out["by_outcome"] == {"published_in_parts": 1}
        assert out["republished_whole"]["surplus_records"] == 0

    def test_neither_is_its_own_outcome_rather_than_the_nearest_one(self):
        out = dup.classify({"a": [300, 200]}, {"a": 499})
        assert out["by_outcome"] == {"disagrees_with_the_input": 1}

    def test_an_accession_missing_from_the_input_table_is_said_to_be_missing(self):
        out = dup.classify({"a": [1, 2]}, {})
        assert out["by_outcome"] == {"not_in_the_input_table": 1}

    def test_the_outcomes_are_counted_separately_rather_than_one_verdict_assigned(self):
        out = dup.classify(
            {"a": [5, 5], "b": [3, 2], "c": [1, 1], "d": [9, 9]},
            {"a": 5, "b": 5, "c": 7, "d": 9},
        )
        assert out["by_outcome"] == {
            "disagrees_with_the_input": 1,
            "published_in_parts": 1,
            "republished_whole": 2,
        }
        assert out["repeated_accessions"] == 4

    def test_three_copies_count_two_surplus_records(self):
        out = dup.classify({"a": [40, 40, 40]}, {"a": 40})
        assert out["republished_whole"]["surplus_records"] == 2
        assert out["republished_whole"]["surplus_nucleotides"] == 80
        assert out["occurrences_per_accession"] == {3: 1}


class TestReadingTheInputTable:
    def _served(self, monkeypatch, payload: bytes):
        class _Fake(io.RawIOBase):
            def __init__(self, *a, **k):
                self._buf = io.BytesIO(payload)

            def readable(self):
                return True

            def readinto(self, b):
                chunk = self._buf.read(len(b))
                b[: len(chunk)] = chunk
                return len(chunk)

        monkeypatch.setattr(dup.objectstore, "S3RandomRead", _Fake)
        monkeypatch.setattr(dup.objectstore, "client", lambda: None)

    def _table(self, rows: list[tuple[str, int]]) -> bytes:
        head = "\t".join(f"c{i}" for i in range(19)) + "\n"
        body = "".join(
            "\t".join([uvig, "", "", "", "", "", str(length)] + [""] * 12) + "\n"
            for uvig, length in rows
        )
        return (head + body).encode()

    def test_it_reads_the_length_for_the_accessions_asked_for(self, monkeypatch):
        self._served(monkeypatch, self._table([("a", 100), ("b", 200), ("c", 300)]))
        assert dup.published_lengths("bucket", "key", {"a", "c"}) == {"a": 100, "c": 300}

    def test_an_empty_request_reads_nothing_at_all(self, monkeypatch):
        """Scanning 1.9 GB to find nothing is how the first smoke run spent its budget."""

        def _boom():
            raise AssertionError("the table must not be opened for an empty request")

        monkeypatch.setattr(dup.objectstore, "client", _boom)
        assert dup.published_lengths("bucket", "key", set()) == {}

    def test_the_giant_virus_mag_form_resolves_by_the_same_route(self, monkeypatch):
        name = "IMGVR_UViG_GVMAG-M-3300000115-12_000001"
        self._served(monkeypatch, self._table([(name, 77)]))
        assert dup.published_lengths("bucket", "key", {name}) == {name: 77}


class TestScanningTheRelease:
    def test_it_pairs_each_header_with_its_sequence_length(self, monkeypatch):
        from amazebio import imgvr

        fasta = (
            b">IMGVR_UViG_2505313053_000001\nACGTACGT\n"
            b">IMGVR_UViG_2505313053_000002\nACGT\n"
            b">IMGVR_UViG_GVMAG-M-3300000115-12_000001\nAC\n"
        )
        payload = io.BytesIO()
        with gzip.GzipFile(fileobj=payload, mode="wb") as gz:
            gz.write(fasta)
        blob = payload.getvalue()

        class _Fake(io.RawIOBase):
            def __init__(self, *a, **k):
                self._buf = io.BytesIO(blob)

            def readable(self):
                return True

            def readinto(self, b):
                chunk = self._buf.read(len(b))
                b[: len(chunk)] = chunk
                return len(chunk)

        monkeypatch.setattr(dup.objectstore, "S3RandomRead", _Fake)
        monkeypatch.setattr(dup.objectstore, "client", lambda: None)

        keys, lengths, unpackable, meta = dup.scan_lengths(
            "bucket", "key", max_headers=None, progress=1e9
        )
        assert meta["headers"] == 3
        assert list(keys) == [
            imgvr.uvig_key("IMGVR_UViG_2505313053_000001"),
            imgvr.uvig_key("IMGVR_UViG_2505313053_000002"),
        ]
        assert list(lengths) == [8, 4]
        assert unpackable == {"IMGVR_UViG_GVMAG-M-3300000115-12_000001": [2]}
        assert meta["partial"] is False

"""What the JSON-tree count must get right before it is allowed to settle anything.

The pass exists to rule out one alternative explanation for A7.3's headline, and a
counting bug here would rule it out wrongly — which is worse than not having run it,
because the write-up would then record a check that was performed rather than a check
that worked. So the verdict logic is tested on all three branches, including the one
that says neither reading is supported.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "evo2_json_tree",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "evo2_json_tree.py",
)
assert _spec and _spec.loader
jt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jt)


def _gz(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write("".join(lines).encode())
    return buf.getvalue()


def _records(*texts: str) -> list[str]:
    return [json.dumps({"text": t}) + "\n" for t in texts]


@pytest.fixture
def served(monkeypatch):
    """Serve one gzip payload to `count_file` without a socket."""

    def install(payload: bytes):
        class _Fake:
            def __init__(self, **kwargs):
                self._buf = io.BytesIO(payload)

            def read(self, n: int = -1) -> bytes:
                return self._buf.read(n)

        monkeypatch.setattr(jt, "ResumableRead", _Fake)

    return install


class TestCountingOneFile:
    def test_it_counts_records_and_nucleotides(self, served):
        served(_gz(_records("ACGT", "ACGTACGT", "A")))
        row = jt.count_file("https://example/x.gz", 0)
        assert row["records"] == 3
        assert row["sequence_chars"] == 13
        assert row["shortest"] == 1
        assert row["longest"] == 8
        assert row["partial"] is False

    def test_a_blank_line_is_not_a_record(self, served):
        served(_gz([*_records("ACGT"), "\n", "   \n", *_records("GG")]))
        assert jt.count_file("https://example/x.gz", 0)["records"] == 2

    def test_a_record_without_text_is_counted_as_such_rather_than_skipped_silently(self, served):
        served(_gz([json.dumps({"id": 1}) + "\n", *_records("ACGT")]))
        row = jt.count_file("https://example/x.gz", 0)
        assert row["records"] == 1
        assert row["records_without_text"] == 1

    def test_an_unparsable_line_is_counted_rather_than_raised(self, served):
        served(_gz(["{not json\n", *_records("ACGT")]))
        row = jt.count_file("https://example/x.gz", 0)
        assert row["records"] == 1
        assert row["unparsable_lines"] == 1

    def test_a_bounded_read_stops_and_says_it_is_partial(self, served):
        served(_gz(_records(*["ACGT"] * 100)))
        row = jt.count_file("https://example/x.gz", 0, max_records=7)
        assert row["records"] == 7
        assert row["partial"] is True

    def test_the_length_histogram_bins_by_power_of_two(self, served):
        served(_gz(_records("A" * 3, "A" * 5, "A" * 6)))
        assert jt.count_file("https://example/x.gz", 0)["length_buckets"] == {"2": 1, "4": 2}


def _files(**splits: tuple[int, int]) -> dict[str, dict[str, int]]:
    """Per-file rows keyed by the publisher's own path shape."""
    return {
        f"{jt.JSON_PREFIX}data_imgvr_{split}_chunk1.jsonl.gz": {
            "records": records,
            "sequence_chars": chars,
        }
        for split, (records, chars) in splits.items()
    }


class TestReadingTheSplitFromTheName:
    def test_each_split_is_named_rather_than_inferred_from_order(self):
        assert jt.split_of("a/b/data_imgvr_train_chunk3.jsonl.gz") == "train"
        assert jt.split_of("a/b/data_imgvr_valid_chunk1.jsonl.gz") == "valid"
        assert jt.split_of("a/b/data_imgvr_test_chunk1.jsonl.gz") == "test"

    def test_an_unrecognised_name_stops_the_pass_rather_than_guessing(self):
        with pytest.raises(SystemExit, match="cannot tell which split"):
            jt.split_of("a/b/data_imgvr_holdout_chunk1.jsonl.gz")


class TestFindingADuplicatedSplit:
    def test_two_splits_with_the_same_totals_are_reported_as_one(self):
        dups = jt.duplicate_splits(
            {
                "train": {"records": 10, "sequence_chars": 100},
                "test": {"records": 2, "sequence_chars": 20},
                "valid": {"records": 2, "sequence_chars": 20},
            }
        )
        assert dups == [("valid", "test")]

    def test_splits_that_merely_look_similar_are_not_duplicates(self):
        dups = jt.duplicate_splits(
            {
                "test": {"records": 2, "sequence_chars": 20},
                "valid": {"records": 2, "sequence_chars": 21},
            }
        )
        assert dups == []

    def test_two_empty_splits_are_not_called_duplicates_of_each_other(self):
        dups = jt.duplicate_splits(
            {
                "test": {"records": 0, "sequence_chars": 0},
                "valid": {"records": 0, "sequence_chars": 0},
            }
        )
        assert dups == []


class TestWhatTheComparisonMaySay:
    def test_totals_equal_to_the_fasta_rule_the_alternative_out(self):
        verdict = jt.compare(
            _files(train=(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS)), partial=False
        )
        assert verdict["verdict"] == "same_content"

    def test_totals_equal_to_evo1s_release_are_the_finding_rather_than_a_near_miss(self):
        verdict = jt.compare(
            _files(train=(jt.EVO1_RELEASE_RECORDS, jt.EVO1_RELEASE_SEQUENCE_CHARS)),
            partial=False,
        )
        assert verdict["verdict"] == "training_format_is_evo1s_release"
        assert verdict["against_evo1_release"]["equal"] is True
        assert verdict["against_evo2_fasta"]["equal"] is False

    def test_the_duplicated_split_is_excluded_from_the_distinct_total(self):
        """Summing all six published files double-counts `valid`, by 50 records."""
        verdict = jt.compare(
            _files(
                train=(jt.EVO1_RELEASE_RECORDS - 50, jt.EVO1_RELEASE_SEQUENCE_CHARS - 363_466),
                test=(50, 363_466),
                valid=(50, 363_466),
            ),
            partial=False,
        )
        assert verdict["distinct_records"] == jt.EVO1_RELEASE_RECORDS
        assert verdict["splits_counted"] == ["test", "train"]
        assert verdict["duplicate_splits"][0]["split"] == "valid"
        assert verdict["verdict"] == "training_format_is_evo1s_release"

    def test_a_shortfall_of_exactly_the_forward_mismatch_is_its_own_verdict(self):
        verdict = jt.compare(
            _files(train=(jt.FASTA_RECORDS - jt.EVO2_FORWARD_MISMATCH, 1)), partial=False
        )
        assert verdict["verdict"] == "filtered_downstream"

    def test_any_other_shortfall_is_neither_and_says_so(self):
        verdict = jt.compare(_files(train=(jt.FASTA_RECORDS - 17, 1)), partial=False)
        assert verdict["verdict"] == "differs_otherwise"

    def test_matching_records_but_not_nucleotides_is_not_a_match(self):
        """The record count alone would call this `same_content`, and it is not."""
        verdict = jt.compare(
            _files(train=(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS - 1)), partial=False
        )
        assert verdict["verdict"] == "differs_otherwise"

    def test_a_smoke_run_settles_nothing_however_the_numbers_fall(self):
        verdict = jt.compare(
            _files(train=(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS)), partial=True
        )
        assert verdict["verdict"] == "not_measured"


class TestWhatAProbeMayNotPublish:
    def test_a_bounded_run_is_exempt_from_the_durable_copy_rather_than_writing_one(self):
        """The corpus bucket has no delete, so a smoke run must not reach its prefix."""
        source = str(jt.__file__)
        with open(source) as fh:
            text = fh.read()
        assert "durable=None if smoke else" in text
        assert "durable_exempt=" in text

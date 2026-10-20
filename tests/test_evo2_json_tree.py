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


class TestWhatTheComparisonMaySay:
    def test_identical_totals_rule_the_alternative_out(self):
        verdict = jt.compare(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS, partial=False)
        assert verdict["verdict"] == "same_content"
        assert verdict["record_delta"] == 0

    def test_a_shortfall_of_exactly_the_forward_mismatch_is_its_own_verdict(self):
        verdict = jt.compare(jt.FASTA_RECORDS - jt.EVO2_FORWARD_MISMATCH, 1, partial=False)
        assert verdict["verdict"] == "filtered_downstream"

    def test_any_other_shortfall_is_neither_and_says_so(self):
        verdict = jt.compare(jt.FASTA_RECORDS - 17, 1, partial=False)
        assert verdict["verdict"] == "differs_otherwise"

    def test_matching_records_but_not_nucleotides_is_not_a_match(self):
        """The record count alone would call this `same_content`, and it is not."""
        verdict = jt.compare(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS - 1, partial=False)
        assert verdict["verdict"] == "differs_otherwise"

    def test_a_smoke_run_settles_nothing_however_the_numbers_fall(self):
        verdict = jt.compare(jt.FASTA_RECORDS, jt.FASTA_SEQUENCE_CHARS, partial=True)
        assert verdict["verdict"] == "not_measured"


class TestWhatAProbeMayNotPublish:
    def test_a_bounded_run_is_exempt_from_the_durable_copy_rather_than_writing_one(self):
        """The corpus bucket has no delete, so a smoke run must not reach its prefix."""
        source = str(jt.__file__)
        with open(source) as fh:
            text = fh.read()
        assert "durable=None if smoke else" in text
        assert "durable_exempt=" in text

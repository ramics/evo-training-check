"""Streaming sampled records with their sequence — the reader A2.1 needed and A1.4 did not."""

from __future__ import annotations

import io

import pytest

from amazebio.detect import in_sample
from amazebio.seqstream import iter_fasta_sampled, iter_stage2_sampled

TAG = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;"


def test_fasta_reads_every_entry_at_a_census():
    fasta = b">A one\nACGT\nACGT\n>B two\nTTTT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, rate=1))
    assert [r.id for r in got] == ["A", "B"]
    assert got[0].sequence == "ACGTACGT"
    assert got[1].sequence == "TTTT"


def test_fasta_emits_the_last_entry_without_a_trailing_newline():
    fasta = b">A\nACGT"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, rate=1))
    assert [(r.id, r.sequence) for r in got] == [("A", "ACGT")]


def test_fasta_identifier_is_the_headers_first_token():
    fasta = b">IMGVR_UViG_2505313053_000001|contig|1 length=42\nACGT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, rate=1))
    assert got[0].id == "IMGVR_UViG_2505313053_000001|contig|1"


def test_fasta_reads_across_chunk_boundaries():
    fasta = b">A\n" + b"ACGT\n" * 50 + b">B\nTTTT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, rate=1, chunk=7))
    assert [r.id for r in got] == ["A", "B"]
    assert got[0].sequence == "ACGT" * 50


def test_fasta_yields_only_the_sampled_entries():
    ids = [f"IMGVR_{i}" for i in range(400)]
    fasta = "".join(f">{i}\nACGTACGT\n" for i in ids).encode()
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=3, rate=0.2))
    expected = [i for i in ids if in_sample(i, seed=3, rate=0.2)]
    assert [r.id for r in got] == expected
    assert 0 < len(got) < len(ids)


def test_fasta_records_carry_no_taxonomy_because_the_component_carries_none():
    got = list(iter_fasta_sampled(io.BytesIO(b">A\nACGT\n"), component="IMG/VR", seed=1, rate=1))
    assert got[0].record.component == "IMG/VR"
    assert not got[0].record.taxonomy


# --------------------------------------------------------------------------------------
# stage2 Parquet
# --------------------------------------------------------------------------------------


def stage2_object(rows: list[str]):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    buffer = io.BytesIO()
    pq.write_table(pa.table({"text": rows}), buffer)
    buffer.seek(0)
    return buffer


def test_stage2_reads_the_sequence_out_of_a_tag_block_row():
    obj = stage2_object([f"|{TAG}|ACGTACGT"])
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=1, rate=1)
    )
    assert [r.id for r in got] == ["stage2:x#0"]
    assert got[0].sequence == "ACGTACGT"
    assert got[0].record.taxonomy


def test_stage2_concatenates_the_blocks_of_a_long_record():
    # D-048: one row is one record, and a record over the block budget arrives as several
    # `|tag|block` pairs in that row, every pair carrying the same tag.
    obj = stage2_object([f"|{TAG}|AAAA|{TAG}|CCCC"])
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=1, rate=1)
    )
    assert got[0].sequence == "AAAACCCC"


def test_stage2_identifier_is_the_row_index_within_the_object():
    obj = stage2_object([f"|{TAG}|AAAA", f"|{TAG}|CCCC", f"|{TAG}|GGGG"])
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:train", seed=1, rate=1)
    )
    assert [r.id for r in got] == ["stage2:train#0", "stage2:train#1", "stage2:train#2"]


def test_stage2_reports_a_row_whose_tag_will_not_parse_rather_than_skipping_it_silently():
    # An unlabelled record is one of this audit's own findings, so a malformed row must not be
    # able to imitate one.
    seen: list[str] = []
    obj = stage2_object(["ACGTACGT"])
    got = list(
        iter_stage2_sampled(
            obj,
            component="IMG/VR",
            record_prefix="stage2:x",
            seed=1,
            rate=1,
            on_parse_error=lambda record_id, exc: seen.append(record_id),
        )
    )
    assert got == []
    assert seen == ["stage2:x#0"]


def test_stage2_yields_only_the_sampled_rows():
    rows = [f"|{TAG}|ACGT"] * 500
    obj = stage2_object(rows)
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=5, rate=0.1)
    )
    expected = [
        f"stage2:x#{i}" for i in range(len(rows)) if in_sample(f"stage2:x#{i}", seed=5, rate=0.1)
    ]
    assert [r.id for r in got] == expected


def test_stage2_refuses_a_schema_that_is_not_the_documented_one():
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    buffer = io.BytesIO()
    pq.write_table(pa.table({"sequence": ["ACGT"]}), buffer)
    buffer.seek(0)
    with pytest.raises(ValueError, match="documented single-column"):
        list(iter_stage2_sampled(buffer, component="x", record_prefix="p", seed=1, rate=1))

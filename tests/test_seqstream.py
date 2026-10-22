"""Streaming sampled records with their sequence — the reader A2.1 needed and A1.4 did not."""

from __future__ import annotations

import io

import pytest

from amazebio.detect import in_sample
from amazebio.seqstream import (
    iter_fasta_sampled,
    iter_fasta_selected,
    iter_stage2_sampled,
)

TAG = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;"


def test_fasta_reads_every_entry_at_a_census():
    fasta = b">A one\nACGT\nACGT\n>B two\nTTTT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, hi=1))
    assert [r.id for r in got] == ["A", "B"]
    assert got[0].sequence == "ACGTACGT"
    assert got[1].sequence == "TTTT"


def test_fasta_emits_the_last_entry_without_a_trailing_newline():
    fasta = b">A\nACGT"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, hi=1))
    assert [(r.id, r.sequence) for r in got] == [("A", "ACGT")]


def test_fasta_identifier_is_the_headers_first_token():
    fasta = b">IMGVR_UViG_2505313053_000001|contig|1 length=42\nACGT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, hi=1))
    assert got[0].id == "IMGVR_UViG_2505313053_000001|contig|1"


def test_fasta_reads_across_chunk_boundaries():
    fasta = b">A\n" + b"ACGT\n" * 50 + b">B\nTTTT\n"
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=1, hi=1, chunk=7))
    assert [r.id for r in got] == ["A", "B"]
    assert got[0].sequence == "ACGT" * 50


def test_fasta_yields_only_the_sampled_entries():
    ids = [f"IMGVR_{i}" for i in range(400)]
    fasta = "".join(f">{i}\nACGTACGT\n" for i in ids).encode()
    got = list(iter_fasta_sampled(io.BytesIO(fasta), component="IMG/VR", seed=3, hi=0.2))
    expected = [i for i in ids if in_sample(i, seed=3, rate=0.2)]
    assert [r.id for r in got] == expected
    assert 0 < len(got) < len(ids)


def test_fasta_band_reads_the_records_a_shallower_pass_left_unread():
    # D-099's deepening promise: widening the sample re-reads nothing. The band [0.2, 0.5) and
    # the prefix [0, 0.2) are disjoint and together are exactly the sample at 0.5.
    ids = [f"IMGVR_{i}" for i in range(400)]
    fasta = "".join(f">{i}\nACGTACGT\n" for i in ids).encode()
    prefix = {r.id for r in iter_fasta_sampled(io.BytesIO(fasta), component="x", seed=3, hi=0.2)}
    band = {
        r.id for r in iter_fasta_sampled(io.BytesIO(fasta), component="x", seed=3, lo=0.2, hi=0.5)
    }
    wide = {r.id for r in iter_fasta_sampled(io.BytesIO(fasta), component="x", seed=3, hi=0.5)}
    assert prefix and band
    assert not prefix & band
    assert prefix | band == wide


def test_stage2_band_is_disjoint_from_the_prefix_it_extends():
    rows = [f"|{TAG}|ACGT"] * 500
    kwargs = {"component": "IMG/VR", "record_prefix": "stage2:x", "seed": 5}
    prefix = {r.id for r in iter_stage2_sampled(stage2_object(rows), hi=0.1, **kwargs)}
    band = {r.id for r in iter_stage2_sampled(stage2_object(rows), lo=0.1, hi=0.4, **kwargs)}
    wide = {r.id for r in iter_stage2_sampled(stage2_object(rows), hi=0.4, **kwargs)}
    assert prefix and band
    assert not prefix & band
    assert prefix | band == wide


def test_fasta_records_carry_no_taxonomy_because_the_component_carries_none():
    got = list(iter_fasta_sampled(io.BytesIO(b">A\nACGT\n"), component="IMG/VR", seed=1, hi=1))
    assert got[0].record.component == "IMG/VR"
    assert not got[0].record.taxonomy


# --------------------------------------------------------------------------------------
# Selection by name, and the one thing the early stop hides
# --------------------------------------------------------------------------------------


def test_selected_yields_the_named_entries_in_file_order():
    fasta = b">A one\nACGT\nACGT\n>B\nTTTT\n>C three\nGGGG\n"
    got = list(iter_fasta_selected(io.BytesIO(fasta), component="IMG/VR", ids={"C", "A"}))
    assert [(r.id, r.sequence) for r in got] == [("A", "ACGTACGT"), ("C", "GGGG")]


def test_the_early_stop_hides_a_second_entry_under_an_identifier_already_yielded():
    """The docstring says so; this is what makes it a property rather than a hope.

    It is the behaviour that bit A7.5. Evo 2's viral component repeats accessions — A7.3 counts
    1,775 of them, one appearing 161 times — with different residues under one name, so a pass
    that stops at the first sighting of the last requested identifier reports entry counts
    truncated at whatever byte the stop fell on. The identifier set is the same either way,
    which is exactly why the bug was invisible until a column counted entries.
    """
    fasta = b">A\nAAAA\n>B\nTTTT\n>A\nGGGG\n>C\nCCCC\n"
    ids = {"A", "B"}
    stopped = list(iter_fasta_selected(io.BytesIO(fasta), component="x", ids=ids))
    whole = list(
        iter_fasta_selected(io.BytesIO(fasta), component="x", ids=ids, stop_when_complete=False)
    )
    # Same identifiers...
    assert {r.id for r in stopped} == {r.id for r in whole} == ids
    # ...and not the same entries: the repeat of A is only in the complete read.
    assert [r.sequence for r in stopped] == ["AAAA", "TTTT"]
    assert [r.sequence for r in whole] == ["AAAA", "TTTT", "GGGG"]


def test_an_identifier_the_stream_never_carries_is_simply_absent():
    ids = {"A", "ABSENT"}
    got = list(iter_fasta_selected(io.BytesIO(b">A\nACGT\n"), component="x", ids=ids))
    assert [r.id for r in got] == ["A"]
    assert ids - {r.id for r in got} == {"ABSENT"}


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
    got = list(iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=1, hi=1))
    assert [r.id for r in got] == ["stage2:x#0"]
    assert got[0].sequence == "ACGTACGT"
    assert got[0].record.taxonomy


def test_stage2_concatenates_the_blocks_of_a_long_record():
    # D-048: one row is one record, and a record over the block budget arrives as several
    # `|tag|block` pairs in that row, every pair carrying the same tag.
    obj = stage2_object([f"|{TAG}|AAAA|{TAG}|CCCC"])
    got = list(iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=1, hi=1))
    assert got[0].sequence == "AAAACCCC"


def test_stage2_identifier_is_the_row_index_within_the_object():
    obj = stage2_object([f"|{TAG}|AAAA", f"|{TAG}|CCCC", f"|{TAG}|GGGG"])
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:train", seed=1, hi=1)
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
            hi=1,
            on_parse_error=lambda record_id, exc: seen.append(record_id),
        )
    )
    assert got == []
    assert seen == ["stage2:x#0"]


def test_stage2_yields_only_the_sampled_rows():
    rows = [f"|{TAG}|ACGT"] * 500
    obj = stage2_object(rows)
    got = list(
        iter_stage2_sampled(obj, component="IMG/VR", record_prefix="stage2:x", seed=5, hi=0.1)
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
        list(iter_stage2_sampled(buffer, component="x", record_prefix="p", seed=1, hi=1))

"""Tests for amazebio.corpora — reading records out of the staged corpora, task A1.4.

The parsing tests carry the weight here. A lineage tag mis-parsed one slot to the left turns a
family assignment into an order assignment, and the taxonomy rules would keep reporting counts
as though nothing were wrong; a parse failure swallowed as "no taxonomy assigned" would be read
downstream as an unlabelled record, which is one of the audit's own findings. So both are
errors, and both are tested.

The declaration tests are the other half: `SOURCES` is the mapping from published-method
vocabulary to staged objects, and a wrong entry there silently moves a component in or out of a
policy's scope.
"""

from __future__ import annotations

import io

import pytest

from amazebio.conformance import RANKS, parse_lineage_tag
from amazebio.corpora import (
    ESM3_SOURCES,
    SOURCES,
    LineageError,
    RangedObject,
    Stage2Structure,
    has_lineage_tag,
    iter_fasta_records,
    iter_stage2_records,
    sources_for,
    tag_of,
)

TAG = "|r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;|"


# --------------------------------------------------------------------------------------
# The inline lineage tag
# --------------------------------------------------------------------------------------


def test_the_head_tag_reads_the_documented_format() -> None:
    assert parse_lineage_tag(tag_of(TAG + "ACGT")).taxonomy == {
        "realm": "Duplodnaviria",
        "kingdom": "Heunggongvirae",
        "phylum": "Uroviricota",
        "class": "Caudoviricetes",
    }


def test_empty_slots_are_absent_rather_than_empty_strings() -> None:
    """Most released records resolve no deeper than class, and the rules must see that."""
    taxonomy = parse_lineage_tag(tag_of(TAG + "ACGT")).taxonomy
    for rank in ("order", "family", "genus", "species"):
        assert rank not in taxonomy


def test_a_family_without_a_realm_parses_rather_than_failing() -> None:
    """95 released records are exactly this, and they are what the realm rule acts on (D-051)."""
    tag = parse_lineage_tag(tag_of("|;;;;;f__Fuselloviridae;;|ATG"))
    assert tag.taxonomy == {"family": "Fuselloviridae"}
    assert not tag.is_malformed


def test_all_eight_ranks_round_trip() -> None:
    from amazebio.conformance import RANK_PREFIXES

    by_rank = {rank: prefix for prefix, rank in RANK_PREFIXES.items()}
    raw = ";".join(f"{by_rank[rank]}__{rank.title()}" for rank in RANKS)
    assert parse_lineage_tag(raw).taxonomy == {rank: rank.title() for rank in RANKS}


def test_a_row_not_opening_with_a_tag_is_an_error() -> None:
    """Never read as "no taxonomy assigned": an unlabelled record is a finding of its own."""
    with pytest.raises(LineageError, match="does not open"):
        tag_of("ACGTACGT")


def test_an_unclosed_tag_is_an_error() -> None:
    with pytest.raises(LineageError, match="no closing"):
        tag_of("|r__Duplodnaviria;k__Heunggongvirae")


def test_a_short_tag_is_a_formatting_variation_not_a_finding() -> None:
    """A7.1's reading, adopted here so one parser serves both (D-057)."""
    tag = parse_lineage_tag(tag_of("|r__Duplodnaviria;k__Heunggongvirae|ACGT"))
    assert tag.taxonomy == {"realm": "Duplodnaviria", "kingdom": "Heunggongvirae"}
    assert not tag.is_malformed


def test_a_prefix_disagreeing_with_its_position_is_recorded_not_discarded() -> None:
    """The one case worth keeping the detail for: the taxonomy is still usable."""
    tag = parse_lineage_tag(tag_of("|k__Heunggongvirae;r__Duplodnaviria;;;;;;|ACGT"))
    assert tag.is_malformed
    assert tag.taxonomy == {"kingdom": "Heunggongvirae", "realm": "Duplodnaviria"}


def test_has_lineage_tag_finds_a_tag_anywhere_in_a_head() -> None:
    assert has_lineage_tag(">acc\n" + TAG + "ACGT")
    assert has_lineage_tag(">acc " + TAG)
    assert not has_lineage_tag(">IMGVR_UViG_2505313053_000001\nACGTACGT")
    assert not has_lineage_tag(">acc|not_a_rank__x|ACGT")


# --------------------------------------------------------------------------------------
# FASTA
# --------------------------------------------------------------------------------------

FASTA = (
    b">IMGVR_UViG_1_000001 some description\nACGTACGT\nTTTTTTTT\n"
    b">IMGVR_UViG_2_000002\nGGGG\n"
    b">IMGVR_UViG_3_000003\n" + TAG.encode() + b"ACGT\n"
)


@pytest.mark.parametrize("chunk", [1, 3, 17, 64, 1 << 20])
def test_fasta_records_are_independent_of_chunk_boundaries(chunk: int) -> None:
    """A record split across two reads is the bug this reader exists to not have."""
    records = list(iter_fasta_records(io.BytesIO(FASTA), component="IMG/VR", chunk=chunk))
    assert [r.id for r in records] == [
        "IMGVR_UViG_1_000001",
        "IMGVR_UViG_2_000002",
        "IMGVR_UViG_3_000003",
    ]
    assert all(r.component == "IMG/VR" for r in records)


def test_fasta_head_carries_the_first_sequence_line() -> None:
    """Evo 1 puts its tag at the head of the sequence, so checking for its absence needs it."""
    records = list(iter_fasta_records(io.BytesIO(FASTA), component="IMG/VR", chunk=7))
    assert not has_lineage_tag(records[0].attributes["head"])
    assert has_lineage_tag(records[2].attributes["head"])


def test_a_final_record_without_a_trailing_newline_is_not_lost() -> None:
    data = b">a\nACGT\n>b\nTTTT"
    assert [r.id for r in iter_fasta_records(io.BytesIO(data), component="c")] == ["a", "b"]


def test_a_header_only_final_record_is_not_lost() -> None:
    data = b">a\nACGT\n>b"
    assert [r.id for r in iter_fasta_records(io.BytesIO(data), component="c")] == ["a", "b"]


# --------------------------------------------------------------------------------------
# Parquet
# --------------------------------------------------------------------------------------


def _parquet(rows: list[str], *, row_group_size: int = 2) -> io.BytesIO:
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = io.BytesIO()
    pq.write_table(
        pa.table({"text": rows}), sink, row_group_size=row_group_size, compression="snappy"
    )
    sink.seek(0)
    return sink


def test_stage2_records_are_identified_by_row_across_row_groups() -> None:
    rows = [TAG + "ACGT" * 3, TAG + "TTTT", "|r__Monodnaviria;;;;;;;|GG", TAG + "CC", TAG + "A"]
    records = list(
        iter_stage2_records(_parquet(rows), component="IMG/VR", record_prefix="stage2:x.parquet")
    )
    assert [r.id for r in records] == [f"stage2:x.parquet#{i}" for i in range(5)]
    assert records[2].taxonomy == {"realm": "Monodnaviria"}


def test_stage2_parse_failures_are_reported_and_skipped() -> None:
    """Counted, never absorbed: a skipped row that looked unlabelled would become a finding."""
    seen: list[str] = []
    records = list(
        iter_stage2_records(
            _parquet([TAG + "ACGT", "no tag at all", TAG + "GG"]),
            component="IMG/VR",
            record_prefix="p",
            on_parse_error=lambda rid, exc: seen.append(rid),
        )
    )
    assert [r.id for r in records] == ["p#0", "p#2"]
    assert seen == ["p#1"]


def test_stage2_rejects_an_unexpected_schema() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = io.BytesIO()
    pq.write_table(pa.table({"sequence": ["ACGT"], "lineage": ["r__X"]}), sink)
    sink.seek(0)
    with pytest.raises(ValueError, match="single-column"):
        list(iter_stage2_records(sink, component="IMG/VR", record_prefix="p"))


# --------------------------------------------------------------------------------------
# The ranged reader
# --------------------------------------------------------------------------------------


class _FakeS3:
    """A client that serves ranges out of a bytes blob, and counts what was asked for."""

    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.ranges: list[str] = []

    def head_object(self, **kw: object) -> dict[str, int]:
        return {"ContentLength": len(self.blob)}

    def get_object(self, **kw: object) -> dict[str, object]:
        header = str(kw["Range"])
        self.ranges.append(header)
        start, end = (int(v) for v in header.removeprefix("bytes=").split("-"))
        return {"Body": io.BytesIO(self.blob[start : end + 1])}


def test_ranged_object_reads_a_whole_object_in_order() -> None:
    blob = bytes(range(256)) * 40
    client = _FakeS3(blob)
    obj = RangedObject(client, bucket="b", key="k")
    assert obj.size == len(blob)
    assert obj.buffered(chunk=1024).read() == blob
    assert obj.bytes_read == len(blob)


def test_ranged_object_seeks_from_the_end() -> None:
    """Parquet is read footer-first, so SEEK_END has to be right or nothing opens."""
    client = _FakeS3(b"0123456789")
    obj = RangedObject(client, bucket="b", key="k")
    obj.seek(-3, io.SEEK_END)
    assert obj.read(3) == b"789"
    obj.seek(2)
    obj.seek(1, io.SEEK_CUR)
    assert obj.read(2) == b"34"


def test_ranged_object_never_reads_past_the_end() -> None:
    client = _FakeS3(b"abc")
    obj = RangedObject(client, bucket="b", key="k")
    assert obj.buffered(chunk=64).read() == b"abc"
    assert all(int(r.removeprefix("bytes=").split("-")[1]) <= 2 for r in client.ranges)


# --------------------------------------------------------------------------------------
# The source declarations
# --------------------------------------------------------------------------------------


def test_every_source_is_declared_once() -> None:
    keys = [s.key for s in (*SOURCES, *ESM3_SOURCES) if s.key]
    assert len(keys) == len(set(keys))


def test_a_readable_source_has_a_reader_and_a_pinned_size() -> None:
    for source in (*SOURCES, *ESM3_SOURCES):
        if source.readable:
            assert source.reader in {"stage2_parquet", "fasta"}, source.key
            assert source.bytes and source.bytes > 0, source.key
        else:
            # Unreadable sources exist to be reported, so each must still say why.
            assert source.why, source.corpus_component
            assert source.reader == "none", source.key


def test_unstaged_components_are_listed_rather_than_omitted() -> None:
    """A wildcard-scope reading's manifest is only honest if the whole release is in it."""
    unstaged = {s.corpus_component for s in SOURCES if s.extra.get("staged") is False}
    assert {
        "stage1_imgpr",
        "ncbi_eukaryotic_genomes",
        "eukaryotic_genic_windows",
        "metagenomes",
        "mrna",
    } <= unstaged


def test_evo_1s_prokaryotic_component_is_staged_and_declared() -> None:
    """D-119 staged it, reversing D-031's reading that OpenGenome2's GTDB superseded it.

    The two releases pin different GTDB snapshots (D-130), so substituting one for the other
    would have put a superset in place of a subset. Declared as a prefix, like Evo 2's: the
    objects under it are not read by A1.4, and `undeclared_objects` matches prefixes so that
    staging them does not silently fail the inventory guard.
    """
    gtdb = [s for s in SOURCES if s.corpus_component == "stage1_gtdb"]
    assert len(gtdb) == 1
    (source,) = gtdb
    assert source.extra.get("staged") is not False
    assert source.key.endswith("/stage1/gtdb/")
    assert source.readable is False, "no rule reaches it, so A1.4 does not enumerate it"
    assert source.extra["objects"] == 14


def test_the_viral_components_declare_complementary_evidence() -> None:
    """The finding this module exists for: neither release carries both id and taxonomy."""
    stage2 = next(s for s in SOURCES if s.corpus_component == "stage2")
    imgvr = next(s for s in SOURCES if s.corpus_component == "imgvr")
    assert stage2.evidence.taxonomy_ranks and not stage2.evidence.attributes
    assert imgvr.evidence.attributes and not imgvr.evidence.taxonomy_ranks
    assert imgvr.verify_evidence, "an absence this audit asserts must be checked, not assumed"


def test_sources_for_narrows_by_release_and_readability() -> None:
    assert {s.release for s in sources_for("opengenome")} == {"opengenome"}
    assert all(s.readable for s in sources_for("opengenome2", readable_only=True))
    with pytest.raises(ValueError, match="no staged sources"):
        sources_for("not-a-release")


# --------------------------------------------------------------------------------------
# The inventory guard
# --------------------------------------------------------------------------------------


def test_the_three_stage2_splits_are_all_declared() -> None:
    """Regression: the first version of SOURCES had train and valid, and stage 2 has three."""
    splits = {s.key.rsplit("/", 1)[-1] for s in SOURCES if s.corpus_component == "stage2" and s.key}
    assert splits == {"train_stage2.parquet", "valid_stage2.parquet", "test_stage2.parquet"}


def test_an_undeclared_staged_object_is_reported() -> None:
    from amazebio.corpora import undeclared_objects

    declared = next(s.key for s in SOURCES if s.corpus_component == "imgvr")
    found = undeclared_objects(
        [(declared, 11), ("corpora/opengenome/rev/stage3/surprise.parquet", 99)]
    )
    assert found == [("corpora/opengenome/rev/stage3/surprise.parquet", 99)]


def test_objects_under_a_declared_prefix_are_accounted_for() -> None:
    """GTDB is declared as a prefix because it is four tar objects, not one."""
    from amazebio.corpora import undeclared_objects

    gtdb = next(s.key for s in SOURCES if s.corpus_component == "gtdb_v220")
    assert undeclared_objects([(gtdb + "v214/batch1.tar", 27_891_189_760)]) == []


def test_zero_byte_objects_never_fail_a_run() -> None:
    """A1.3 left four behind and the bucket withholds DeleteObject, so they are permanent."""
    from amazebio.corpora import undeclared_objects

    assert undeclared_objects([("corpora/opengenome2/rev/.probe", 0)]) == []


# --------------------------------------------------------------------------------------
# Resuming a broken read
# --------------------------------------------------------------------------------------


class _BreakingBody:
    """A response body that delivers a few bytes and then drops the connection."""

    def __init__(self, data: bytes, after: int) -> None:
        self.data = data
        self.after = after
        self.sent = False

    def read(self, size: int = -1) -> bytes:
        if not self.sent:
            self.sent = True
            return self.data[: self.after]
        raise OSError("connection broken: IncompleteRead")


class _FlakyS3(_FakeS3):
    """Serves ranges, but breaks the body mid-stream the first `breaks` times.

    Models what ended a 28 GB pass: botocore delivered six of the eight megabytes asked for and
    then raised, so a reader that discards partial progress makes no headway, and one that
    refetches the whole window does several times the I/O it needs to.
    """

    def __init__(self, blob: bytes, *, breaks: int, after: int = 3) -> None:
        super().__init__(blob)
        self.breaks = breaks
        self.after = after

    def get_object(self, **kw: object) -> dict[str, object]:
        served = super().get_object(**kw)
        if self.breaks <= 0:
            return served
        self.breaks -= 1
        whole = served["Body"].read()  # type: ignore[union-attr]
        return {"Body": _BreakingBody(whole, self.after)}


def test_a_broken_stream_resumes_from_where_it_stopped() -> None:
    blob = bytes(range(256)) * 8
    client = _FlakyS3(blob, breaks=2, after=5)
    obj = RangedObject(client, bucket="b", key="k", sleep=lambda _: None)
    assert obj.buffered(chunk=512).read() == blob
    assert obj.reconnects == 2
    # Resumed rather than restarted: no byte is fetched twice.
    assert obj.bytes_read == len(blob)


def test_a_read_gives_up_after_its_attempt_budget() -> None:
    client = _FlakyS3(b"abcdefgh", breaks=99, after=1)
    obj = RangedObject(client, bucket="b", key="k", attempts=3, sleep=lambda _: None)
    with pytest.raises(OSError, match="connection broken"):
        obj.buffered(chunk=64).read()
    assert obj.reconnects == 3


def test_retries_are_reported_to_the_caller() -> None:
    seen: list[tuple[int, int]] = []
    client = _FlakyS3(b"0123456789", breaks=1, after=2)
    obj = RangedObject(
        client,
        bucket="b",
        key="k",
        sleep=lambda _: None,
        on_retry=lambda attempt, pos, _exc: seen.append((attempt, pos)),
    )
    assert obj.buffered(chunk=32).read() == b"0123456789"
    assert seen == [(1, 2)], "a retry must report the position it resumed from"


# --------------------------------------------------------------------------------------
# The record unit
# --------------------------------------------------------------------------------------


def _full_block() -> int:
    """A block length that exactly fills the budget, by the splitter's own definition.

    `amazebio.conformance.split_row` counts the tag and the block against `BLOCK_CHARS` and not
    the two delimiters, so a test that builds its row from the whole tag falls two characters
    short and silently stops exercising the boundary.
    """
    from amazebio.conformance import BLOCK_CHARS

    return BLOCK_CHARS - len(TAG.strip("|"))


def _structure(rows: list[str], *, row_group_size: int = 2) -> Stage2Structure:
    from amazebio.corpora import Stage2Structure

    found = Stage2Structure()
    list(
        iter_stage2_records(
            _parquet(rows, row_group_size=row_group_size),
            component="IMG/VR",
            record_prefix="p",
            structure=found,
            on_parse_error=lambda _rid, _exc: None,
        )
    )
    return found


def test_ordinary_rows_confirm_one_row_one_record() -> None:
    found = _structure([TAG + "ACGT" * 5, TAG + "TTTT", TAG + "GG"])
    assert found.rows == 3
    assert found.max_blocks == 1
    assert found.rows_multi_block == 0
    assert found.one_row_one_record


def test_a_long_record_chunked_under_one_tag_is_still_one_record() -> None:
    """D-048: over the budget, a record repeats its tag within the same row."""
    long_row = TAG + "A" * _full_block() + TAG + "GGGG"
    found = _structure([TAG + "ACGT", long_row])
    assert found.rows_multi_block == 1
    assert found.rows_multi_distinct_tag == 0
    assert found.max_blocks == 2
    assert found.one_row_one_record, "repeating one tag is a chunked genome, not two records"


def test_two_distinct_tags_in_a_row_falsify_the_reading() -> None:
    found = _structure([TAG + "ACGT", "|r__Monodnaviria;;;;;;;|GG" + TAG + "TT"])
    assert found.rows_multi_distinct_tag == 1
    assert not found.one_row_one_record


def test_a_final_block_on_the_budget_falsifies_the_reading() -> None:
    """A record that fills its last block may continue into the next row."""
    filled = TAG + "A" * _full_block()
    found = _structure([filled])
    assert found.rows_final_block_at_budget == 1
    assert not found.one_row_one_record


def test_rows_without_a_tag_are_counted_not_ignored() -> None:
    found = _structure([TAG + "ACGT", "ACGTACGT"])
    assert found.rows_without_tag == 1


def test_the_structure_scan_does_not_change_which_records_are_yielded() -> None:
    """The scan is evidence about the pass, and must not perturb it."""
    rows = [TAG + "ACGT", "no tag", "|r__Monodnaviria;;;;;;;|GG"]
    plain = [
        r.id
        for r in iter_stage2_records(
            _parquet(rows), component="c", record_prefix="p", on_parse_error=lambda *_: None
        )
    ]
    scanned = [
        r.id
        for r in iter_stage2_records(
            _parquet(rows),
            component="c",
            record_prefix="p",
            structure=Stage2Structure(),
            on_parse_error=lambda *_: None,
        )
    ]
    assert plain == scanned == ["p#0", "p#2"]


def test_a_null_row_is_looked_at_rather_than_skipped() -> None:
    """A row that answers neither structural test must not pass by default."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    sink = io.BytesIO()
    pq.write_table(pa.table({"text": [TAG + "ACGT", None]}), sink, row_group_size=2)
    sink.seek(0)
    found = Stage2Structure()
    records = list(
        iter_stage2_records(
            sink,
            component="c",
            record_prefix="p",
            structure=found,
            on_parse_error=lambda *_: None,
        )
    )
    assert [r.id for r in records] == ["p#0"]
    assert found.rows_without_tag == 1

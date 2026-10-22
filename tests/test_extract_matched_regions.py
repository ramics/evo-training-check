"""The joins and the refusals in `tools/extract_matched_regions.py` — task A7.5.

What is tested here is what can be wrong without anything failing. A record selected by
identifier either comes back whole or comes back short, and a short one reads as a weaker match
rather than as an error. An output key written twice is permanent in a bucket that cannot delete.
And the identity this tool adds is a definition rather than a library call, so its arithmetic is
pinned on alignments built by hand: the three statistics reported about one region have to be
statistics of the *same* region, which is the one claim a reader of the table cannot check.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys

import pytest

from amazebio import corpora, profilesearch
from amazebio.seqstream import iter_fasta_selected

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "extract_matched_regions.py"
_spec = importlib.util.spec_from_file_location("extract_matched_regions_under_test", _PATH)
extract = importlib.util.module_from_spec(_spec)
sys.modules["extract_matched_regions_under_test"] = extract
_spec.loader.exec_module(extract)


FASTA = (
    b">r1 first record\nACGTACGT\nACGT\n"
    b">r2\nTTTT\n"
    b">r3 third\nGGGGCCCC\n"
    b">r4\nAAAA\n"
    b">r5\nCCCC\n"
    b">r6\nGGGG\n"
)


class CountingStream:
    """A stream that records how many bytes were pulled out of it."""

    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)
        self.read_bytes = 0

    def read(self, size: int) -> bytes:
        block = self._inner.read(size)
        self.read_bytes += len(block)
        return block


class TestSelectingRecordsByIdentifier:
    def test_only_the_named_records_come_back_whole_and_in_file_order(self) -> None:
        got = list(
            iter_fasta_selected(io.BytesIO(FASTA), component="IMG/VR", ids={"r3", "r1"}, chunk=7)
        )
        assert [r.id for r in got] == ["r1", "r3"]
        # Wrapped lines joined, and the header's description is not part of the identifier.
        assert got[0].sequence == "ACGTACGTACGT"
        assert got[1].sequence == "GGGGCCCC"

    def test_a_requested_identifier_absent_from_the_stream_is_simply_not_yielded(self) -> None:
        """The caller reports it as missing; this is what makes that report possible."""
        got = list(iter_fasta_selected(io.BytesIO(FASTA), component="IMG/VR", ids={"r1", "rX"}))
        assert [r.id for r in got] == ["r1"]

    def test_a_record_with_no_newline_at_end_of_stream_is_still_whole(self) -> None:
        got = list(iter_fasta_selected(io.BytesIO(b">r1\nACGT"), component="x", ids={"r1"}))
        assert [(r.id, r.sequence) for r in got] == [("r1", "ACGT")]


class TestTheEarlyStop:
    def test_the_stream_is_not_read_past_the_last_wanted_record(self) -> None:
        stream = CountingStream(FASTA)
        got = list(iter_fasta_selected(stream, component="x", ids={"r1", "r2"}, chunk=8))
        assert [r.id for r in got] == ["r1", "r2"]
        assert stream.read_bytes < len(FASTA)

    def test_switching_it_off_reads_the_object_through_and_yields_the_same_records(self) -> None:
        stream = CountingStream(FASTA)
        got = list(
            iter_fasta_selected(
                stream, component="x", ids={"r1", "r2"}, chunk=8, stop_when_complete=False
            )
        )
        assert [r.id for r in got] == ["r1", "r2"]
        assert stream.read_bytes == len(FASTA)


class FakeAlignment:
    def __init__(self, hmm: str, target: str, *, hmm_from: int = 1, hmm_to: int | None = None):
        self.hmm_sequence = hmm
        self.target_sequence = target
        self.hmm_from = hmm_from
        self.hmm_to = hmm_to if hmm_to is not None else sum(1 for c in hmm if c.isalpha())
        self.target_from = 1
        self.target_to = sum(1 for c in target if c.isalpha())


class FakeDomain:
    def __init__(self, alignment: FakeAlignment, *, included: bool = True) -> None:
        self.alignment = alignment
        self.included = included


class FakeHit:
    def __init__(self, domains: list[FakeDomain]) -> None:
        self.domains = domains


class TestIdentityToTheModelConsensus:
    def test_case_folding_inserts_and_target_gaps(self) -> None:
        """Consensus `ACdef.GH` against target `ACDQF-GH`.

        Match-state columns are the seven letters of the consensus; the `.` insert column is
        excluded from both sides of the fraction. `A C D f G H` agree — `d` against `D` is the
        same residue written with the model's own emphasis — `e` against `Q` does not, and the
        target's gap counts in the denominator only. So 6 of 7.
        """
        domain = FakeDomain(FakeAlignment("ACdef.GH", "ACDQF-GH"))
        assert profilesearch.consensus_identity(domain) == pytest.approx(6 / 7)

    def test_a_region_with_no_match_state_column_is_unanswerable_not_zero(self) -> None:
        assert profilesearch.consensus_identity(FakeDomain(FakeAlignment("...", "ABC"))) is None

    def test_nothing_identical_is_zero(self) -> None:
        assert profilesearch.consensus_identity(FakeDomain(FakeAlignment("AAA", "CCC"))) == 0.0


class TestOneRegionThreeStatistics:
    def test_coverage_coordinates_and_identity_come_from_the_same_domain(self) -> None:
        """The best-covering domain is not the first one, and all three must follow it."""
        short = FakeDomain(FakeAlignment("AC", "AC", hmm_from=1, hmm_to=2))
        long = FakeDomain(FakeAlignment("ACDEFGHI", "ACDEFGHQ", hmm_from=10, hmm_to=17))
        hit = FakeHit([short, long])

        assert profilesearch.best_domain(hit) is long
        assert profilesearch.best_model_coverage(hit, 16) == pytest.approx(8 / 16)
        assert profilesearch.best_domain_region(hit) == (1, 8)
        assert profilesearch.consensus_identity(profilesearch.best_domain(hit)) == pytest.approx(
            7 / 8
        )

    def test_an_excluded_domain_is_not_the_best_one(self) -> None:
        excluded = FakeDomain(FakeAlignment("ACDEFGHI", "ACDEFGHI"), included=False)
        included = FakeDomain(FakeAlignment("AC", "AC"))
        hit = FakeHit([excluded, included])
        assert profilesearch.best_domain(hit) is included

    def test_a_hit_with_no_included_domain_has_no_region_and_no_coverage(self) -> None:
        hit = FakeHit([FakeDomain(FakeAlignment("AC", "AC"), included=False)])
        assert profilesearch.best_domain(hit) is None
        assert profilesearch.best_domain_region(hit) is None
        assert profilesearch.best_model_coverage(hit, 16) == 0.0


class TestReadingTheInputLists:
    def test_a_tsv_with_a_header_is_read_as_its_first_column(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "records.tsv"
        path.write_text("record_id\tvOTU\nr1\tv1\nr2\tv2\n")
        assert extract.read_first_column(path, header_names=("record_id",)) == ["r1", "r2"]

    def test_a_bare_list_blank_lines_and_comments(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "ids.txt"
        path.write_text("# a note\nr1\n\nr2\n")
        assert extract.read_first_column(path, header_names=("record_id",)) == ["r1", "r2"]

    def test_duplicates_are_dropped_and_order_is_kept(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "ids.txt"
        path.write_text("r2\nr1\nr2\n")
        assert extract.read_first_column(path, header_names=("record_id",)) == ["r2", "r1"]

    def test_an_empty_list_is_a_refusal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "ids.txt"
        path.write_text("# nothing but a comment\n")
        with pytest.raises(SystemExit):
            extract.read_first_column(path, header_names=("record_id",))


class FakeClient:
    """Enough S3 for the pin check and the write-path pre-flight."""

    def __init__(self, *, length: int | None = None, published: set[str] | None = None) -> None:
        self.length = length
        self.published = published or set()
        self.put_calls: list[str] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if Key in self.published:
            return {"ContentLength": 1, "Metadata": {}}
        if self.length is not None and not Key.startswith("corpora/results/"):
            return {"ContentLength": self.length}
        raise _not_found()

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(str(kwargs.get("Key")))


def _not_found() -> Exception:
    exc = Exception("Not Found")
    exc.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}  # type: ignore[attr-defined]
    return exc


class TestThePinCheck:
    def test_a_staged_object_of_another_length_is_a_refusal_before_any_read(self) -> None:
        with pytest.raises(SystemExit) as exc:
            extract.resolve_source(FakeClient(length=1))
        assert "the pin says" in str(exc.value)

    def test_the_pinned_length_passes(self) -> None:
        source = next(
            s for s in corpora.sources_for(extract.RELEASE) if s.component == extract.COMPONENT
        )
        got = extract.resolve_source(FakeClient(length=source.bytes))
        assert got.key == source.key


class TestTheWritePathPreflight:
    def test_a_published_key_is_a_refusal_and_nothing_is_written(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        durable = "s3://bucket/corpora/results/a7-5"
        client = FakeClient(published={"corpora/results/a7-5/regions-x.tsv"})
        with pytest.raises(SystemExit) as exc:
            extract.preflight(
                client,
                paths=[tmp_path / "regions-x.tsv"],
                durable=durable,
                outdir=tmp_path,
                replace=None,
            )
        assert "already published" in str(exc.value)
        assert client.put_calls == []

    def test_an_existing_local_output_is_a_refusal(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "regions-x.tsv"
        path.write_text("stale\n")
        with pytest.raises(SystemExit) as exc:
            extract.preflight(
                FakeClient(), paths=[path], durable=None, outdir=tmp_path, replace=None
            )
        assert "already exist" in str(exc.value)

    def test_a_reason_is_the_only_way_past(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "regions-x.tsv"
        path.write_text("stale\n")
        extract.preflight(
            FakeClient(published={"corpora/results/a7-5/regions-x.tsv"}),
            paths=[path],
            durable="s3://bucket/corpora/results/a7-5",
            outdir=tmp_path,
            replace="re-running after the identity definition was fixed",
        )

    def test_a_clean_destination_passes(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        extract.preflight(
            FakeClient(),
            paths=[tmp_path / "regions-x.tsv"],
            durable="s3://bucket/corpora/results/a7-5",
            outdir=tmp_path,
            replace=None,
        )


class TestWhatMayPublishAtAll:
    """The other half of the write path: `preflight` stops a replacement, this stops a rehearsal.

    A first rehearsal reaching a clean prefix is not a replacement, so the pre-flight passes it —
    and the bucket has no delete. Both incidents behind this are named in `durable_for`.
    """

    def test_the_canonical_directory_publishes(self) -> None:
        assert extract.durable_for(extract.OUTDIR, limit_records=None) == (
            extract.objectstore.durable_results("a7-5")
        )

    def test_a_run_written_anywhere_else_is_a_rehearsal_and_does_not(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        assert extract.durable_for(tmp_path, limit_records=None) is None

    def test_a_record_limit_does_not_publish_even_from_the_canonical_directory(self) -> None:
        # A table over the first twenty records of the list is indistinguishable in the prefix
        # from a table over all of it, and reads as "no match" for every record the limit cut.
        assert extract.durable_for(extract.OUTDIR, limit_records=20) is None


# --------------------------------------------------------------------------------------
# End to end, offline: a stream, a gene call, a search, a table — no object storage.
# --------------------------------------------------------------------------------------


def build_hmm(path: pathlib.Path, *, name: str, protein: str) -> None:
    """A single-model HMM built from one protein, at test time.

    Built rather than committed: a binary fixture is a thing nobody can review, and the builder
    is already a dependency. The model is built *from the protein the fixture record encodes*, so
    the search has something to find and the identity is high by construction.
    """
    from pyhmmer.easel import Alphabet, TextMSA, TextSequence
    from pyhmmer.plan7 import Background, Builder

    amino = Alphabet.amino()
    msa = TextMSA(
        name=name.encode(),
        sequences=[
            TextSequence(name=b"seq1", sequence=protein),
            TextSequence(name=b"seq2", sequence=protein),
        ],
    ).digitize(amino)
    builder = Builder(amino, seed=1)
    background = Background(amino)
    hmm, _, _ = builder.build_msa(msa, background)
    with path.open("wb") as handle:
        hmm.write(handle)


class TestTheTableItWrites:
    def test_columns_hold_the_six_asked_for_and_no_residues(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        rows = [
            {
                "accession": "PF00001",
                "profile": "Model_1",
                "record_id": "r1",
                "entry": 1,
                "gene": "gene0",
                "score": 101.5,
                "threshold": 25.0,
                "identity": 0.9123,
                "model_coverage": 0.9876,
                "model_length": 120,
                "hmm_from": 1,
                "hmm_to": 118,
                "target_from": 3,
                "target_to": 120,
            }
        ]
        path = tmp_path / "regions.tsv"
        extract.write_table(path, rows)
        header, body = path.read_text().splitlines()
        assert header.split("\t") == list(extract.COLUMNS)
        for asked in ("accession", "record_id", "score", "threshold", "identity"):
            assert asked in header.split("\t")
        assert "model_coverage" in header.split("\t")
        assert not any("sequence" in column or "residue" in column for column in extract.COLUMNS)
        assert body.split("\t")[0] == "PF00001"

    def test_the_entry_column_is_what_makes_a_rows_key_unique(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The released component repeats accessions and the repeats are not identical, so
        (record_id, accession, gene) is not a key — the first real pass produced two rows
        sharing it with different scores. `entry` is the occurrence that separates them."""
        base = {
            "accession": "PF04848",
            "profile": "Model_1",
            "record_id": "IMGVR_X",
            "gene": "gene6",
            "threshold": 25.0,
            "model_coverage": 0.96,
            "model_length": 120,
            "hmm_from": 1,
            "hmm_to": 118,
            "target_from": 2,
            "target_to": 160,
        }
        rows = [
            {**base, "entry": 1, "score": 38.0, "identity": 0.2754},
            {**base, "entry": 2, "score": 34.4, "identity": 0.2},
        ]
        path = tmp_path / "regions.tsv"
        extract.write_table(path, rows)
        keyed = {(r["record_id"], r["entry"], r["accession"], r["gene"]) for r in rows}
        assert len(keyed) == 2
        assert "entry" in extract.COLUMNS
        assert path.read_text().count("IMGVR_X") == 2

    def test_what_the_entry_column_is_for_travels_in_the_tools_own_output(self) -> None:
        assert "does not identify an entry" in extract.ENTRY_NOTE
        assert "fans out" in extract.ENTRY_NOTE

    def test_a_none_is_written_as_an_empty_field_rather_than_the_word_none(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        rows = [{c: None for c in extract.COLUMNS}]
        path = tmp_path / "regions.tsv"
        extract.write_table(path, rows)
        assert path.read_text().splitlines()[1] == "\t".join([""] * len(extract.COLUMNS))

    def test_a_searched_fixture_record_produces_one_region_per_profile_and_gene(
        self, tmp_path
    ) -> None:  # type: ignore[no-untyped-def]
        """The whole middle of the tool, with the stream and the search real and S3 absent."""
        fixture = pathlib.Path(__file__).resolve().parent / "data" / "a7-5" / "records.fasta"
        protein = (fixture.parent / "protein.txt").read_text().strip()
        hmm = tmp_path / "model.hmm"
        build_hmm(hmm, name="Fixture_1", protein=protein)

        with fixture.open("rb") as stream:
            records = list(
                iter_fasta_selected(stream, component="IMG/VR", ids={"fixture_r1", "fixture_rX"})
            )
        assert [r.id for r in records] == ["fixture_r1"]

        proteins, stats = profilesearch.call_genes(records)
        assert stats["records"] == 1
        assert proteins, "the fixture record has to carry a callable gene"

        rows = profilesearch.search(
            _PfamLike(),
            proteins,
            restrict_to=None,
            hmm_file=hmm,
            cpus=1,
            with_identity=True,
        )
        assert rows, "the model was built from this record's protein, so it has to be found"
        row = rows[0]
        assert row["record_id"] == "fixture_r1"
        assert row["score"] > 0
        assert 0.0 < row["identity"] <= 1.0
        assert row["hmm_from"] <= row["hmm_to"]
        assert not any("sequence" in key for key in row)


class TestTheMeterOnTheCorpusPass:
    """The pass reports where it is, and what it read is recorded rather than assumed.

    Both halves were missing: progress was printed when a record was *found*, and with 314
    accessions in an 11.22 GB object that is one line at the start and the next at the end
    (D-192). And the design asks the run to record the bytes actually read, because the early
    stop's saving cannot be predicted from the identifiers.
    """

    def source(self, body: bytes):  # type: ignore[no-untyped-def]
        from amazebio import corpora

        return corpora.StagedSource(
            key="corpora/test/imgvr.fasta.gz",
            release="opengenome2",
            component="IMG/VR",
            corpus_component="imgvr",
            reader="fasta",
            evidence=corpora.Evidence(note="test"),
            why="test",
            gzipped=True,
            bytes=len(body),
        )

    def test_the_meter_measures_the_compressed_object_the_pin_declares(self) -> None:
        import gzip

        from conftest import FakeS3

        body = gzip.compress(b">a\nACGTACGTAA\n>b\nTTTTTTTTTT\n>c\nGGGGGGGGGG\n")
        source = self.source(body)
        records, meter = extract.open_records(FakeS3(body), source, ["a", "c"])
        got = [r.id for r in records]
        assert got == ["a", "c"]
        # Compressed bytes, because the object's declared length is the compressed one and a
        # share of an unknown decompressed total would have an invented denominator.
        assert 0 < meter.bytes_read <= source.bytes
        assert meter.tell() == meter.bytes_read

    def test_the_line_it_would_print_names_the_object_and_what_is_left(self) -> None:
        from amazebio import progress

        meter = progress.beating(
            __import__("io").BytesIO(b"x" * 100),
            total=1000,
            label="corpora/opengenome2/fasta/plasmids_phage/imgvr.fasta.gz",
            every=10,
            out=lambda _: None,
        )
        meter.read(100)
        assert "imgvr.fasta.gz" in meter.line()
        assert "left" in meter.line()


class _PfamLike:
    """A registry stand-in: curated cutoffs off, so the fixture HMM needs no GA line."""

    id = "fixture"
    version = "0"
    curated_cutoffs = False


class TestTheDocumentItWrites:
    def test_the_identity_definition_travels_in_the_output(self) -> None:
        """A number whose definition lives only in a task file is a number nobody can read."""
        assert "consensus" in extract.IDENTITY_DEFINITION
        assert "not identity to any member of the family" in extract.IDENTITY_DEFINITION

    def test_the_summary_survives_an_empty_table(self) -> None:
        doc = {
            "component": "IMG/VR",
            "release": "opengenome2",
            "registry": {"id": "pfam", "version": "38.2"},
            "records_found": 0,
            "records_requested": 3,
            "genes_called": 0,
            "profiles_searched": 2,
            "regions": 0,
            "records_with_a_region": 0,
            "accessions_with_a_region": 0,
            "records_missing": ["r1", "r2", "r3"],
            "records_without_genes": 0,
            "rows": [],
        }
        text = extract.summarise(doc)
        assert "0 of 3 requested records found" in text
        assert "not in the staged object" in text
        json.dumps(doc)  # the document has to stay serialisable

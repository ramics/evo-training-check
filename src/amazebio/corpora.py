"""Reading records out of the staged corpora, and declaring what each one can answer — A1.4.

A1.2 and A1.5 staged the corpora. This module turns a staged object back into the record stream
a policy predicate acts on, which is where a fact about these releases becomes unavoidable:

**Neither Evo release carries the metadata its own published filter keys on, and the two fail
differently.** Evo 1's viral component — `stage2`, Parquet, one `text` column — carries a
taxonomic lineage inline on every record and no identifier at all. Evo 2's — `imgvr.fasta.gz` —
carries an IMG/VR accession on every record and no lineage. So the component that can be labelled
cannot be named, the component that can be named cannot be labelled, and *neither* carries the
high-confidence flag, the vOTU or the prokaryotic-host count that three of the filter's six
published rules read.

That is why :class:`amazebio.policyspec.Evidence` exists and why every source here declares one.
The alternative — letting a predicate read an absent field and draw a conclusion — fails in the
unsafe direction: `keep_if_attribute_in` on a record with no `confidence` attribute would report
the record as removed, and a corpus-scale run would conclude that Evo's filter removed its entire
viral component. A clean pass, manufactured out of missing metadata.

Three further things are declarations rather than inferences, and each is load-bearing:

**Component names.** A policy spec's scope is written in the vocabulary of the published methods
(`IMG/VR`, `GTDB`, `IMG/PR`), and the staged corpus is organised by the component names in
`amazebio.opengenome` (`imgvr`, `stage2`, `gtdb_v220`). The mapping between them is written out in
:data:`SOURCES` rather than produced by normalising strings, because a scope decision that falls
out of punctuation handling is a scope decision nobody reviewed. Evo 1's `stage2` maps to `IMG/VR`
on the evidence in `policies/corpora.md` §3, which is a documented finding and not a guess from
the path — the release names no viral component at all.

**The record unit.** For `imgvr.fasta.gz` a record is a FASTA entry with the publisher's own
accession. For `stage2` a record is a Parquet row — one row is one record (D-048), and a record
longer than the per-block budget arrives as several `|tag|block` pairs concatenated into that one
row, all carrying the same tag, rather than as several rows. `policies/corpora.md` §3 first read
these rows as context windows from an 800-row sample and was corrected by a full scan; this
module re-measures the claim on every pass (:class:`Stage2Structure`) rather than inherit it,
because every count published for this component is a count of records. The identifier is still
synthesised from the object key and the row index: the release carries no accession here, so it
is stable and reproducible but cannot be joined to IMG/VR at all.

**What is not read.** Both releases' prokaryotic components, and for the same reason: no rule in
any reading reaches GTDB, so the strict reading's verdict on it follows from the policy without
counting a single record. Evo 2's is 101 GiB across four tar objects; Evo 1's is 118.5 GiB across
fourteen Parquet objects, staged later than the rest under D-119 so that A2.4's prophage route
covers both corpora rather than one. Each is listed with its record count absent and the reason
recorded, rather than omitted or estimated. A2.4 reads them and can fill the counts in passing.
"""

from __future__ import annotations

import io
import re
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from amazebio.conformance import BLOCK_CHARS, RANKS, parse_lineage_tag, split_row
from amazebio.policyspec import Evidence, Record

__all__ = [
    "BUCKET",
    "ESM3_SOURCES",
    "S3_ENDPOINT",
    "S3_REGION",
    "SOURCES",
    "LineageError",
    "RangedObject",
    "Stage2Structure",
    "StagedSource",
    "durable_results",
    "has_lineage_tag",
    "iter_fasta_records",
    "iter_stage2_records",
    "scan_row_structure",
    "sources_for",
    "tag_of",
    "undeclared_objects",
]

from amazebio.objectstore import CORPORA_BUCKET, durable_results

BUCKET = CORPORA_BUCKET
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"


#: Read size for the ranged object reader. 8 MiB keeps the number of GETs over a 15.8 GiB
#: Parquet file in the low thousands while staying far below the memory a session container has.
READ_CHUNK = 8 << 20


#: Errors a ranged read retries. `botocore` raises its streaming failures as `BotoCoreError`
#: subclasses rather than as `OSError`, so catching the socket errors alone would miss the one
#: that actually killed a 28 GB pass (`ResponseStreamingError`, an `IncompleteRead` underneath).
try:  # pragma: no cover - exercised whenever boto3 is installed, which is always in dev
    from botocore.exceptions import BotoCoreError, ClientError

    _RETRYABLE: tuple[type[BaseException], ...] = (OSError, BotoCoreError, ClientError)
except ImportError:  # pragma: no cover - keeps the module importable without boto3
    _RETRYABLE = (OSError,)


class LineageError(ValueError):
    """Raised when a record's inline lineage tag cannot be parsed.

    Never swallowed. A tag this module cannot read is a record whose taxonomy rules cannot be
    evaluated, and counting it as "no taxonomy assigned" would feed the unspecificity rule a
    parse failure dressed up as a finding.
    """


# --------------------------------------------------------------------------------------
# Reading staged objects
# --------------------------------------------------------------------------------------


class RangedObject(io.RawIOBase):
    """A seekable file over an object-storage object, served by ranged GETs.

    Parquet is read back-to-front — footer, then the row groups wanted — so a sequential
    streaming reader cannot open one, and `pyarrow`'s own object-storage layer brings a second
    AWS SDK that does not see this environment's injected credentials. A few hundred lines of
    streaming machinery in `amazebio.uniref` already handle the sequential case over HTTP; this
    is the seekable case over the pinned `boto3` client, which keeps one client story for every
    object this project reads.

    Nothing is written to local disk. A session container's disk allowance is a fraction of the
    corpus, so every pass over a staged object has to be a stream.
    """

    def __init__(
        self,
        client: Any,
        *,
        bucket: str,
        key: str,
        size: int | None = None,
        attempts: int = 8,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, int, BaseException], None] | None = None,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key
        self._pos = 0
        self._size = (
            size
            if size is not None
            else int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
        )
        self._attempts = attempts
        self._sleep = sleep
        self._on_retry = on_retry
        self.gets = 0
        self.bytes_read = 0
        self.reconnects = 0

    @property
    def size(self) -> int:
        return self._size

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = max(0, min(base + offset, self._size))
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readinto(self, buffer: Any) -> int:  # type: ignore[override]
        """Fill `buffer` from the current position, resuming across a broken connection.

        A ranged GET over tens of gigabytes does not survive on first principles: a 28 GB pass
        died on `IncompleteRead` partway through Evo 1's Parquet, which is why
        `amazebio.uniref.ResumableRead` exists for the HTTP case. The same applies here, with
        one addition — bytes already delivered into the buffer are kept and the retry resumes
        from where the stream broke, rather than re-fetching a window to discard most of it.
        """
        want = min(len(buffer), self._size - self._pos)
        if want <= 0:
            return 0
        view = memoryview(buffer)
        got = 0
        attempt = 0
        while got < want:
            end = self._pos + want - 1
            try:
                body = self._client.get_object(
                    Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}"
                )["Body"]
                self.gets += 1
                while got < want:
                    chunk = body.read(want - got)
                    if not chunk:
                        break
                    view[got : got + len(chunk)] = chunk
                    got += len(chunk)
                    self._pos += len(chunk)
                    self.bytes_read += len(chunk)
            except _RETRYABLE as exc:
                attempt += 1
                self.reconnects += 1
                if attempt >= self._attempts:
                    raise
                if self._on_retry is not None:
                    self._on_retry(attempt, self._pos, exc)
                self._sleep(min(2.0**attempt, 30.0))
                continue
            if got < want:
                # A clean end of body short of the window. Treated as the object ending early
                # rather than retried, so a wrong size pin surfaces as a short read.
                break
        return got

    def buffered(self, *, chunk: int = READ_CHUNK) -> io.BufferedReader:
        """The reader wrapped so small reads do not become small GETs."""
        return io.BufferedReader(self, buffer_size=chunk)


# --------------------------------------------------------------------------------------
# The inline lineage tag
# --------------------------------------------------------------------------------------

# The rank table, the tag parser and the row splitter live in `amazebio.conformance`, which
# reached the released format first and reads it more carefully than this module first did:
# prefix wins over position, a disagreement is recorded rather than resolved, and a short tag
# is a formatting variation rather than a finding. Two parsers of the same bytes disagree
# exactly on the records that matter — the malformed ones — so there is one (D-057).


@dataclass
class Stage2Structure:
    """Whether one released row is one released record — measured on every pass, not assumed.

    `policies/corpora.md` §3 first read these rows as context windows, from an 800-row sample.
    D-048 corrected it from a full scan: the row is the record. Every count A1.4 publishes for
    this component is a count of records, so the claim is re-measured here rather than
    inherited — a count of records that is really a count of rows is exactly the error that
    survives review and then gets quoted.

    Two of these counts would falsify the reading: more than one *distinct* tag in a row, or a
    final block sitting on the block budget, would mean a row packs several records or a record
    continues into the next row. Several blocks carrying the *same* tag would not — that
    is one long genome, chunked.
    """

    rows: int = 0
    rows_without_tag: int = 0
    rows_multi_block: int = 0
    rows_multi_distinct_tag: int = 0
    rows_final_block_at_budget: int = 0
    #: Tags A7.1's parser could read but flagged: a field whose prefix disagrees with its
    #: position, or one carrying no prefix at all. Counted rather than discarded, because the
    #: taxonomy is still usable and the anomaly is evidence about the release either way.
    malformed_tags: int = 0
    max_blocks: int = 0
    longest_row: int = 0
    block_budget: int = BLOCK_CHARS

    @property
    def one_row_one_record(self) -> bool:
        """True when nothing in the scan contradicts the row being the record."""
        return self.rows_multi_distinct_tag == 0 and self.rows_final_block_at_budget == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "rows_without_tag": self.rows_without_tag,
            "rows_multi_block": self.rows_multi_block,
            "rows_multi_distinct_tag": self.rows_multi_distinct_tag,
            "rows_final_block_at_budget": self.rows_final_block_at_budget,
            "malformed_tags": self.malformed_tags,
            "max_blocks": self.max_blocks,
            "longest_row": self.longest_row,
            "block_budget": self.block_budget,
            "one_row_one_record": self.one_row_one_record,
            "basis": (
                "A row is one or more `|tag|block` pairs. Several blocks with one tag are a "
                "single long record, chunked at the budget (D-048). More than one distinct tag, "
                "or a final block at the budget, would falsify that — both are counted."
            ),
        }


def scan_row_structure(text: str, structure: Stage2Structure) -> None:
    """Fold one row's shape into `structure`, using A7.1's splitter.

    Only the rows that could falsify one-row-one-record reach here, so the whole-row cost is
    paid on a small minority of the component rather than on all of it.
    """
    shape = split_row(text)
    structure.longest_row = max(structure.longest_row, shape.total_chars)
    if shape.n_blocks == 0:
        structure.rows_without_tag += 1
        return
    structure.max_blocks = max(structure.max_blocks, shape.n_blocks)
    if shape.n_blocks > 1:
        structure.rows_multi_block += 1
        if len(shape.distinct_tags) > 1:
            structure.rows_multi_distinct_tag += 1
    if shape.last_block_full:
        structure.rows_final_block_at_budget += 1


#: How far into a record to look for the closing `|` of the lineage tag. Eight ranks of taxon
#: names do not reach 512 bytes; a record whose tag is not closed by then is a parse failure,
#: not a long lineage. Bounded deliberately: the alternative is materialising 42 kB of sequence
#: per row to find a 72-byte prefix, which is a hundred gigabytes of string allocation over the
#: component.
LINEAGE_WINDOW = 512

#: A lineage tag anywhere in a record's head, not only at its start. Used to check an evidence
#: declaration of *absence*: Evo 2's viral component is declared to carry no taxonomy, and a
#: pattern anchored at offset 0 would miss a tag the publisher moved into the header.
_TAG_ANYWHERE = re.compile(r"\|[rkpcofgs]__[^|]*\|")


def has_lineage_tag(head: str) -> bool:
    """True if a record's head carries an Evo-style lineage tag anywhere in it."""
    return _TAG_ANYWHERE.search(head) is not None


def tag_of(head: str) -> str:
    """The lineage tag at the head of a stage-2 row, without its delimiters.

    Only each row's head is materialised — see :func:`iter_stage2_records` — so the tag is taken
    from there rather than from the whole row. What comes back is parsed by
    `amazebio.conformance.parse_lineage_tag`, which is the one reading of this format.

    Raises:
        LineageError: if the head does not open with a tag, or the tag is not closed within
            :data:`LINEAGE_WINDOW` characters. Both mean the row is not in the documented form,
            and neither may be quietly read as "no taxonomy assigned" — an unlabelled record is
            a finding of this audit, so a malformed row must not be able to imitate one.
    """
    if not head.startswith("|"):
        raise LineageError(f"row does not open with a lineage tag: {head[:64]!r}")
    closing = head.find("|", 1)
    if closing < 0:
        raise LineageError(
            f"no closing '|' within {LINEAGE_WINDOW} characters of the row head: {head[:64]!r}"
        )
    return head[1:closing]


# --------------------------------------------------------------------------------------
# Record iteration
# --------------------------------------------------------------------------------------


def iter_stage2_records(
    reader: io.BufferedReader | io.RawIOBase,
    *,
    component: str,
    record_prefix: str,
    on_parse_error: Callable[[str, LineageError], None] | None = None,
    structure: Stage2Structure | None = None,
) -> Iterator[Record]:
    """Yield one :class:`Record` per Parquet row of an Evo 1 stage-2 object.

    One row is one record (D-048). A record longer than the block budget
    (`amazebio.conformance.BLOCK_CHARS`) arrives as several `|tag|block` pairs in that one row,
    all carrying the same tag, so reading the leading tag reads the record's taxonomy whatever
    its length.

    Only the first :data:`LINEAGE_WINDOW` code units of each row are materialised, sliced in
    Arrow rather than Python: the column holds tens of kB of sequence per row and the audit needs
    a 72-byte tag, so decoding whole rows would move about 110 GB through Python strings to read
    none of it. Pass `structure` to check the one-row-one-record reading on this pass as well;
    only rows that could falsify it are materialised in full, which keeps the scan nearly free.

    `record_prefix` is the stable-ID stem, normally the object key. The identifier is
    `{record_prefix}#{row}` with `row` the index within the object — reproducible from pinned
    inputs, and *not* an accession: the release carries none for this component, so no join to
    IMG/VR is possible from it at all.

    A row whose tag will not parse is reported to `on_parse_error` and skipped, so the count of
    such rows lands in the manifest instead of being absorbed into the unlabelled population.
    """
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(reader)
    column = parquet.schema_arrow.names[0]
    if parquet.schema_arrow.names != ["text"]:
        raise ValueError(
            f"expected the documented single-column `text` schema, got "
            f"{parquet.schema_arrow.names}; the record unit this reader assumes is that schema"
        )
    row = 0
    for group in range(parquet.metadata.num_row_groups):
        table = parquet.read_row_group(group, columns=[column])
        text = table.column(column)
        heads = pc.utf8_slice_codeunits(text, 0, LINEAGE_WINDOW)
        if structure is not None:
            # All of this arithmetic is vectorised in Arrow, so it costs nothing in Python, and
            # only the rows that could falsify one-row-one-record are materialised. Two kinds
            # can: a row that is not exactly one `|tag|block` pair, and a row long enough to
            # have been cut at the block budget — which a single-pair row can be, and which is
            # the case that matters, since such a record may continue into the next row.
            pipes = pc.count_substring(text, pattern="|")
            lengths = pc.utf8_length(text)
            structure.rows += table.num_rows
            structure.longest_row = max(structure.longest_row, pc.max(lengths).as_py() or 0)
            structure.max_blocks = max(structure.max_blocks, (pc.max(pipes).as_py() or 0) // 2)
            suspect = pc.indices_nonzero(
                pc.fill_null(
                    pc.or_kleene(
                        pc.not_equal(pipes, 2),
                        pc.greater_equal(lengths, structure.block_budget),
                    ),
                    # A null row answers neither test, so it is looked at rather than skipped.
                    True,
                )
            )
            if len(suspect):
                for full in text.take(suspect).to_pylist():
                    scan_row_structure(full or "", structure)
        for head in heads.to_pylist():
            record_id = f"{record_prefix}#{row}"
            row += 1
            if head is None:
                error: LineageError | None = LineageError("row holds no text at all")
            else:
                try:
                    tag = parse_lineage_tag(tag_of(head))
                except LineageError as exc:
                    error = exc
                else:
                    error = None
                    if tag.is_malformed and structure is not None:
                        structure.malformed_tags += 1
                    yield Record(id=record_id, component=component, taxonomy=tag.taxonomy)
            if error is not None and on_parse_error is not None:
                on_parse_error(record_id, error)


def iter_fasta_records(
    stream: Any,
    *,
    component: str,
    chunk: int = READ_CHUNK,
) -> Iterator[Record]:
    """Yield one :class:`Record` per FASTA entry, reading headers and each record's first line.

    `stream` is anything with `read(size)` — a :class:`RangedObject` for a plain FASTA, or
    `amazebio.uniref.GunzipStream` wrapped around one for a `.gz`. The identifier is the
    header's first token, which for Evo 2's viral component is the IMG/VR accession
    (`IMGVR_UViG_2505313053_000001`).

    No taxonomy is parsed, because there is none to parse. That absence is this component's
    finding, and the evidence declaration in :data:`SOURCES` is what turns it into `unresolved`
    outcomes rather than into silent retention — so the absence has to be *checked*, not
    assumed. `head` on each record carries the start of both the header and the first sequence
    line, which is where Evo 1 puts its tag, and the caller verifies the declaration against it.

    Sequence past that first line is discarded. Records are yielded one entry behind the reader
    so the head is complete before the record is handed over.
    """
    pending_id: str | None = None
    pending_head: bytes = b""
    seen_first_line = False
    tail = b""

    def _record(record_id: str, head: bytes) -> Record:
        return Record(
            id=record_id,
            component=component,
            attributes={"head": head[:LINEAGE_WINDOW].decode("utf-8", "replace")},
        )

    while True:
        block = stream.read(chunk)
        if not block:
            break
        data = tail + block
        lines = data.split(b"\n")
        tail = lines.pop()
        for line in lines:
            if line.startswith(b">"):
                if pending_id is not None:
                    yield _record(pending_id, pending_head)
                pending_id = line[1:].split()[0].decode("utf-8", "replace") if len(line) > 1 else ""
                pending_head = line
                seen_first_line = False
            elif pending_id is not None and not seen_first_line:
                pending_head = pending_head + b"\n" + line[:LINEAGE_WINDOW]
                seen_first_line = True
    if tail.startswith(b">"):
        if pending_id is not None:
            yield _record(pending_id, pending_head)
        pending_id = tail[1:].split()[0].decode("utf-8", "replace") if len(tail) > 1 else ""
        pending_head = tail
    elif pending_id is not None and not seen_first_line:
        pending_head = pending_head + b"\n" + tail[:LINEAGE_WINDOW]
    if pending_id is not None:
        yield _record(pending_id, pending_head)


# --------------------------------------------------------------------------------------
# The staged sources
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StagedSource:
    """One staged object: where it is, which policy component it is, and what it can answer."""

    key: str
    release: str
    #: The component name a policy spec's scope is written in, e.g. `IMG/VR`.
    component: str
    #: The component name `amazebio.opengenome` uses, e.g. `stage2`. Both are recorded so the
    #: manifest can be reconciled against A1.2's composition table without re-deriving either.
    corpus_component: str
    reader: str
    evidence: Evidence
    why: str
    #: False when A1.4 has no reader for the object at all, so no count is obtainable from it.
    readable: bool = True
    #: True when the source is read even where the policy makes its verdict uniform, because
    #: the absence this source declares is itself a claim the audit makes. Evo 2's viral
    #: component is the case: "no record carries a lineage tag" was a four-file sample in A1.2
    #: and is a census here, and the same pass yields the component's record count.
    verify_evidence: bool = False
    gzipped: bool = False
    bytes: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


#: Evo 1's viral component carries taxonomy on every record and nothing else. All eight rank
#: slots are present in the tag, so an empty slot is an unassigned rank rather than missing
#: evidence — which is what the unspecificity rule is there to act on.
_STAGE2_EVIDENCE = Evidence(
    taxonomy_ranks=frozenset(RANKS),
    note=(
        "Inline lineage tag, eight ranks, on every record (policies/corpora.md §3). No "
        "identifier, no IMG/VR metadata: the high-confidence flag, the vOTU and the "
        "prokaryotic-host count do not travel with the released records."
    ),
)

#: Evo 2's viral component carries an accession and nothing else. The lineage tags Evo 1
#: published inline are absent, which A1.2 saw on a four-file sample and A1.4 confirms over the
#: whole component: no taxonomy channel at all, so every taxonomy rule is unresolvable here.
_IMGVR_EVIDENCE = Evidence(
    attributes=frozenset({"accession"}),
    note=(
        "IMG/VR accession per record (`IMGVR_UViG_*`). No inline lineage, and none of the "
        "IMG/VR metadata the published rules read."
    ),
)

#: Components no reading's rules reach. They carry no evidence any rule asks for, which is not
#: a defect: the wildcard-scope readings examine them and remove nothing, and that is the
#: `retained` outcome rather than `unresolved`.
_SEQUENCE_ONLY = Evidence(note="Sequence and an accession. No rule in any reading reads either.")

_OG1 = "corpora/opengenome/84369c058d192dcb607086d71679b877421e3250"
_OG2 = "corpora/opengenome2/84d2a7e690c8bb395d1f4868822dfa031ea561c6"

#: Every staged object A1.4 evaluates, with the two it deliberately does not enumerate.
SOURCES: tuple[StagedSource, ...] = (
    StagedSource(
        key=f"{_OG1}/stage2/train_stage2.parquet",
        release="opengenome",
        component="IMG/VR",
        corpus_component="stage2",
        reader="stage2_parquet",
        evidence=_STAGE2_EVIDENCE,
        why=(
            "Evo 1's viral component: the filter's own output, labelled with the taxonomy "
            "the published rules act on."
        ),
        bytes=16_920_332_545,
    ),
    StagedSource(
        key=f"{_OG1}/stage2/test_stage2.parquet",
        release="opengenome",
        component="IMG/VR",
        corpus_component="stage2",
        reader="stage2_parquet",
        evidence=_STAGE2_EVIDENCE,
        why="The same component's test split. Stage 2 is published as three splits, not two.",
        bytes=584_279,
    ),
    StagedSource(
        key=f"{_OG1}/stage2/valid_stage2.parquet",
        release="opengenome",
        component="IMG/VR",
        corpus_component="stage2",
        reader="stage2_parquet",
        evidence=_STAGE2_EVIDENCE,
        why="The same component's validation split; small, and part of the released corpus.",
        bytes=678_965,
    ),
    # Evo 1's other two components. Not staged — A1.2 superseded both with OpenGenome2's
    # equivalents (D-031) — and listed anyway, because the strict reading's wildcard scope
    # covers them. Omitting them would let that reading's manifest read as a verdict on the
    # whole of OpenGenome v1 when it has only seen the viral component.
    StagedSource(
        key=f"{_OG1}/stage1/gtdb/",
        release="opengenome",
        component="GTDB",
        corpus_component="stage1_gtdb",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "118.5 GiB across fourteen Parquet objects, and no rule in any reading reaches it: "
            "the strict reading's verdict follows from the policy without counting a record. "
            "Staged under D-119, reversing D-031's call that OpenGenome2's GTDB superseded it "
            "— the two releases pin different GTDB snapshots (v214.1 against v214.1 plus a "
            "220.0 increment, D-130), so substituting one for the other would have put a "
            "superset in place of a subset. Enumerated by A2.4, which reads the component for "
            "integrated elements."
        ),
        extra={"objects": 14, "bytes_stated": 127_261_074_759},
    ),
    StagedSource(
        key="",
        release="opengenome",
        component="IMG/PR",
        corpus_component="stage1_imgpr",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why="Same: 2.7 GB, superseded by OpenGenome2's IMG/PR component (D-031).",
        extra={"staged": False, "bytes_stated": 2_700_000_000},
    ),
    StagedSource(
        key=f"{_OG2}/fasta/plasmids_phage/imgvr.fasta.gz",
        release="opengenome2",
        component="IMG/VR",
        corpus_component="imgvr",
        reader="fasta",
        gzipped=True,
        evidence=_IMGVR_EVIDENCE,
        verify_evidence=True,
        why=(
            "Evo 2's viral component: the same procedure's output, by the paper's own "
            "statement. Read in full even though every rule is unresolvable against it, "
            "because the absence of any lineage tag is a claim this audit makes and A1.2 "
            "could only sample it."
        ),
        bytes=11_220_266_895,
    ),
    StagedSource(
        key=f"{_OG2}/fasta/plasmids_phage/imgpr.fasta.gz",
        release="opengenome2",
        component="IMG/PR",
        corpus_component="imgpr",
        reader="fasta",
        gzipped=True,
        evidence=_SEQUENCE_ONLY,
        why=(
            "In the corpus and named by the published methods, but outside every reading's "
            "rules, so its verdict is uniform and a record count would add nothing to it."
        ),
        bytes=1_676_593_425,
    ),
    StagedSource(
        key=f"{_OG2}/fasta/ncrna/mmseqs_results_rep_seq.fasta.gz",
        release="opengenome2",
        component="ncRNA",
        corpus_component="ncrna",
        reader="fasta",
        gzipped=True,
        evidence=_SEQUENCE_ONLY,
        why=(
            "Reached only by the strict reading's wildcard scope, and by no rule in it: "
            "examined and retained, uniformly."
        ),
        bytes=4_246_816_780,
    ),
    StagedSource(
        key=f"{_OG2}/fasta/organelles/organelle_sequences.fasta.gz",
        release="opengenome2",
        component="organelles",
        corpus_component="organelles",
        reader="fasta",
        gzipped=True,
        evidence=_SEQUENCE_ONLY,
        why="Same as ncRNA: in scope for the strict reading, untouched by its rules.",
        bytes=809_032_735,
    ),
    StagedSource(
        key=f"{_OG2}/fasta/promoters/mmseqs_results_rep_seq.fasta",
        release="opengenome2",
        component="promoters",
        corpus_component="promoters",
        reader="fasta",
        gzipped=False,
        evidence=_SEQUENCE_ONLY,
        why="Same again, and the only staged object published uncompressed.",
        bytes=115_378_506,
    ),
    # OpenGenome2's deferred components. Unstaged by D-031 on cost, and listed for the same
    # reason as Evo 1's: the strict reading's scope covers them. The first two matter beyond
    # bookkeeping — they are 82% of Evo 2's corpus, were added after the filter was designed,
    # and have no viral screening step in their published curation (policies/evo.md §7). A
    # manifest that left them out would hide the scope gap A4.3 is built to measure.
    StagedSource(
        key="",
        release="opengenome2",
        component="eukaryotic genomes",
        corpus_component="ncbi_eukaryotic_genomes",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "2.17 TB, unstaged (D-031), and named by no published filter step: added after the "
            "procedure was designed. A2.3's target for endogenous viral elements."
        ),
        extra={"staged": False, "bytes_stated": 2_170_000_000_000},
    ),
    StagedSource(
        key="",
        release="opengenome2",
        component="eukaryotic genic windows",
        corpus_component="eukaryotic_genic_windows",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why="129 GB of windows cut from those genomes; unstaged with them (D-031).",
        extra={"staged": False, "bytes_stated": 129_000_000_000},
    ),
    StagedSource(
        key="",
        release="opengenome2",
        component="metagenomes",
        corpus_component="metagenomes",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "252 GB, unstaged (D-031). Taxonomy has never labelled most of this sequence, so a "
            "taxonomy-based filter cannot act on it at all — A4.1 measures the fraction."
        ),
        extra={"staged": False, "bytes_stated": 252_000_000_000},
    ),
    StagedSource(
        key="",
        release="opengenome2",
        component="mRNA and transcripts",
        corpus_component="mrna",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why="52 GB, eukaryote-derived, unstaged (D-031).",
        extra={"staged": False, "bytes_stated": 52_000_000_000},
    ),
    StagedSource(
        key=f"{_OG2}/fasta/gtdb_v220/",
        release="opengenome2",
        component="GTDB",
        corpus_component="gtdb_v220",
        reader="none",
        evidence=_SEQUENCE_ONLY,
        readable=False,
        why=(
            "101 GiB across four tar objects, and no rule in any reading reaches it: the strict "
            "reading's verdict follows from the policy without counting a record. Enumerated by "
            "A2.4, which reads the component in full for integrated elements."
        ),
        extra={"objects": 4, "bytes_stated": 109_142_824_960},
    ),
)


#: ESM3-open's four scope components, as its literal reading names them.
#:
#: None is readable here, and none needs to be. Every rule in that reading carries an
#: unspecified threshold, so every in-scope record is `undetermined` whatever the component
#: holds: the verdict follows from the published words alone. What the manifest records instead
#: is which of the four this project can even see, because that is the §A1 finding — two are
#: staged (A1.5), PDB was deliberately not bought (D-033), and JGI cannot be reconstructed at
#: all, which is why no "share of ESM3's corpus" figure is supportable from any of this.
#:
#: The UniRef row carries no record count on purpose. ESM3 does not state which tier it trained
#: on (D-032), and the three tiers of the release it names differ by a factor of six —
#: 350,950,053 / 170,669,877 / 60,479,070 clusters, each counted in region by A1.5 with delta
#: zero against the release note. Picking one would convert an under-specification into a
#: denominator.
ESM3_SOURCES: tuple[StagedSource, ...] = (
    StagedSource(
        key="corpora/uniref/2023_02/",
        release="esm3-proxy",
        component="UniRef",
        corpus_component="uniref_2023_02",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "Staged and verified by A1.5. Which tier ESM3 used is unstated, so the component "
            "is present without a usable record count."
        ),
        extra={
            "staged": True,
            "counted_clusters": {
                "uniref100": 350_950_053,
                "uniref90": 170_669_877,
                "uniref50": 60_479_070,
            },
            "tier_stated": False,
        },
    ),
    StagedSource(
        key="corpora/mgnify/2023_02/",
        release="esm3-proxy",
        component="MGnify",
        corpus_component="mgnify_2023_02",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why="Staged and verified by A1.5 at the 90%-clustered granularity; granularity unstated.",
        extra={"staged": True, "granularity_stated": False},
    ),
    StagedSource(
        key="",
        release="esm3-proxy",
        component="PDB",
        corpus_component="pdb",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why="Not staged: D-033 deliberately did not buy the structure-side components.",
        extra={"staged": False},
    ),
    StagedSource(
        key="",
        release="esm3-proxy",
        component="JGI",
        corpus_component="jgi",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "Cannot be reconstructed at all, and is about a third of ESM3's unique training "
            "tokens (A1.5). The limit no amount of spending fixes."
        ),
        extra={"staged": False},
    ),
)


#: Prefixes the staged-object inventory is checked against. Everything the two Evo releases
#: staged lives under one of these, so anything found there and not declared in :data:`SOURCES`
#: is a component this module would silently omit.
INVENTORY_PREFIXES = ("corpora/opengenome/", "corpora/opengenome2/")


def undeclared_objects(objects: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """Staged objects no entry in :data:`SOURCES` accounts for, as (key, bytes) pairs.

    This exists because of a near miss. Evo 1 publishes stage 2 as *three* splits — train,
    valid and test — and the first version of `SOURCES` declared two. The run completed, every
    count reconciled against itself, and the manifests would have under-counted the filter's own
    output with nothing anywhere to show it. An inventory this project writes by hand against a
    bucket it cannot list for free is exactly the place to check rather than trust, so the
    pipeline refuses to start on a mismatch.

    Zero-byte objects are ignored: A1.3 left four behind that are not corpus data, and the
    bucket withholds `s3:DeleteObject`, so they are permanent and must not fail a run.
    """
    declared = {s.key for s in SOURCES if s.key}
    prefixes = tuple(s.key for s in SOURCES if s.key.endswith("/"))
    return [
        (key, size)
        for key, size in objects
        if size > 0 and key not in declared and not key.startswith(prefixes)
    ]


def sources_for(release: str | None = None, *, readable_only: bool = False) -> list[StagedSource]:
    """The staged sources, optionally narrowed to one release or to the ones with a reader."""
    every = (*SOURCES, *ESM3_SOURCES)
    chosen = [s for s in every if release is None or s.release == release]
    if readable_only:
        chosen = [s for s in chosen if s.readable]
    if not chosen:
        raise ValueError(f"no staged sources for release {release!r}")
    return chosen

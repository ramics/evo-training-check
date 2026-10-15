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
accession. For `stage2` a record is a Parquet row, which is a *context window* rather than a
biological record: v1's stage 2 is a 131k-token stage, one genome may span several rows, and
nothing in the release says which. So the identifier is synthesised from the object key and the
row index, which is stable and reproducible but is not an accession, and no per-genome proportion
may be computed from it. `policies/corpora.md` §3 established this and the manifest repeats it.

**What is not read.** GTDB is 101 GiB across four tar objects and no rule in any reading reaches
it, so A1.4 does not enumerate it: the strict reading's verdict on it follows from the policy
without counting a single record. The component is listed with its record count absent and the
reason recorded, rather than omitted or estimated. A2.4 reads it in full and can fill the count
in passing.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from amazebio.policyspec import Evidence, Record

__all__ = [
    "BUCKET",
    "ESM3_SOURCES",
    "S3_ENDPOINT",
    "S3_REGION",
    "SOURCES",
    "LineageError",
    "RangedObject",
    "StagedSource",
    "has_lineage_tag",
    "iter_fasta_records",
    "iter_stage2_records",
    "parse_lineage",
    "sources_for",
]

BUCKET = "amazebio-corpora-897641797669"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"

#: Read size for the ranged object reader. 8 MiB keeps the number of GETs over a 15.8 GiB
#: Parquet file in the low thousands while staying far below the memory a session container has.
READ_CHUNK = 8 << 20


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

    def __init__(self, client: Any, *, bucket: str, key: str, size: int | None = None) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key
        self._pos = 0
        self._size = (
            size
            if size is not None
            else int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
        )
        self.gets = 0
        self.bytes_read = 0

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
        want = len(buffer)
        if want == 0 or self._pos >= self._size:
            return 0
        end = min(self._pos + want, self._size) - 1
        body = self._client.get_object(
            Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}"
        )["Body"].read()
        buffer[: len(body)] = body
        self._pos += len(body)
        self.gets += 1
        self.bytes_read += len(body)
        return len(body)

    def buffered(self, *, chunk: int = READ_CHUNK) -> io.BufferedReader:
        """The reader wrapped so small reads do not become small GETs."""
        return io.BufferedReader(self, buffer_size=chunk)


# --------------------------------------------------------------------------------------
# The inline lineage tag
# --------------------------------------------------------------------------------------

#: The eight ranks Evo 1's lineage tag carries, in order, with the single-letter prefix each
#: slot uses. The same rank list the published unspecificity rule enumerates, and the same
#: prefix scheme its stop-taxa use (`r:Riboviria`, `c:Tectiliviricetes`).
LINEAGE_RANKS = (
    ("r", "realm"),
    ("k", "kingdom"),
    ("p", "phylum"),
    ("c", "class"),
    ("o", "order"),
    ("f", "family"),
    ("g", "genus"),
    ("s", "species"),
)

#: How far into a record to look for the closing `|` of the lineage tag. Eight ranks of taxon
#: names do not reach 512 bytes; a record whose tag is not closed by then is a parse failure,
#: not a long lineage. Bounded deliberately: the alternative is materialising 42 kB of sequence
#: per row to find a 72-byte prefix, which is a hundred gigabytes of string allocation over the
#: component.
LINEAGE_WINDOW = 512

_TAG = re.compile(r"^\|([^|]*)\|")

#: A lineage tag anywhere in a record's head, not only at its start. Used to check an evidence
#: declaration of *absence*: Evo 2's viral component is declared to carry no taxonomy, and a
#: pattern anchored at offset 0 would miss a tag the publisher moved into the header.
_TAG_ANYWHERE = re.compile(r"\|[rkpcofgs]__[^|]*\|")


def has_lineage_tag(head: str) -> bool:
    """True if a record's head carries an Evo-style lineage tag anywhere in it."""
    return _TAG_ANYWHERE.search(head) is not None


def parse_lineage(prefix: str) -> dict[str, str]:
    """Parse the inline lineage tag at the head of a stage-2 record.

    The format is `|r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;|`:
    eight `;`-separated slots in rank order, each either empty or `x__Name`. Empty slots are
    data — most released records resolve no deeper than class — so they are returned absent
    rather than as empty strings, which is what the taxonomy rules need to see.

    Raises:
        LineageError: if there is no closing delimiter in :data:`LINEAGE_WINDOW` bytes, if the
            slot count is not eight, or if a filled slot does not carry its rank's prefix. All
            three mean the record is not in the format `policies/corpora.md` §3 documents, and
            a mis-parse would be read downstream as an unlabelled record.
    """
    match = _TAG.match(prefix)
    if match is None:
        raise LineageError(
            f"no closing '|' within {LINEAGE_WINDOW} bytes of the record head: {prefix[:64]!r}"
        )
    slots = match.group(1).split(";")
    if len(slots) != len(LINEAGE_RANKS):
        raise LineageError(
            f"lineage tag has {len(slots)} slots, expected {len(LINEAGE_RANKS)}: "
            f"{match.group(1)[:120]!r}"
        )
    taxonomy: dict[str, str] = {}
    for (prefix_letter, rank), slot in zip(LINEAGE_RANKS, slots, strict=True):
        if not slot:
            continue
        expected = f"{prefix_letter}__"
        if not slot.startswith(expected):
            raise LineageError(
                f"slot for {rank} is {slot[:40]!r}, which does not carry its {expected!r} "
                "prefix, so the slots are not in the documented rank order"
            )
        taxonomy[rank] = slot[len(expected) :]
    return taxonomy


# --------------------------------------------------------------------------------------
# Record iteration
# --------------------------------------------------------------------------------------


def iter_stage2_records(
    reader: io.BufferedReader | io.RawIOBase,
    *,
    component: str,
    record_prefix: str,
    on_parse_error: Callable[[str, LineageError], None] | None = None,
) -> Iterator[Record]:
    """Yield one :class:`Record` per Parquet row of an Evo 1 stage-2 object.

    Only the first :data:`LINEAGE_WINDOW` code units of each row are materialised, sliced in
    Arrow rather than Python: the column holds ~42 kB of sequence per row and the audit needs a
    72-byte tag, so decoding whole rows would move about 110 GB through Python strings to read
    none of it.

    `record_prefix` is the stable-ID stem, normally the object key. The identifier is
    `{record_prefix}#{row}` with `row` the index within the object — reproducible from pinned
    inputs, and *not* an accession: the release carries none for this component, and a row is a
    context window rather than a biological record.

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
        heads = pc.utf8_slice_codeunits(table.column(column), 0, LINEAGE_WINDOW)
        for head in heads.to_pylist():
            record_id = f"{record_prefix}#{row}"
            row += 1
            if head is None:
                error = LineageError("row holds no text at all")
            else:
                try:
                    yield Record(
                        id=record_id,
                        component=component,
                        taxonomy=parse_lineage(head),
                    )
                    continue
                except LineageError as exc:
                    error = exc
            if on_parse_error is not None:
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
    taxonomy_ranks=frozenset(rank for _, rank in LINEAGE_RANKS),
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
        key="",
        release="opengenome",
        component="GTDB",
        corpus_component="stage1_gtdb",
        reader="none",
        readable=False,
        evidence=_SEQUENCE_ONLY,
        why=(
            "In the release and in the strict reading's scope, not staged: 130 GB, superseded "
            "for every Phase A purpose by OpenGenome2's GTDB component (D-031)."
        ),
        extra={"staged": False, "bytes_stated": 130_000_000_000},
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


def sources_for(release: str | None = None, *, readable_only: bool = False) -> list[StagedSource]:
    """The staged sources, optionally narrowed to one release or to the ones with a reader."""
    every = (*SOURCES, *ESM3_SOURCES)
    chosen = [s for s in every if release is None or s.release == release]
    if readable_only:
        chosen = [s for s in chosen if s.readable]
    if not chosen:
        raise ValueError(f"no staged sources for release {release!r}")
    return chosen

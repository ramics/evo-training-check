"""Streaming the sampled records *with* their sequence — the reader A2.1 needed and A1.4 did not.

`amazebio.corpora` reads these same objects header-first and deliberately materialises almost
nothing: A1.4 needed a 72-byte lineage tag per row and decoding whole rows would have moved
about 110 GB of string through Python to read none of it. A profile search needs the opposite —
the residues — so this module is the sequence-bearing counterpart rather than a change to the
readers A1.4's manifests were produced by, which are done and cited.

Two properties keep the cost sane and the conventions intact.

**Only sampled records are materialised.** Sample membership is a function of the record
identifier (`amazebio.detect.in_sample`), so it is decided from the row index or the FASTA
header before any sequence is touched, and an unsampled record costs a hash. The *object* is
still read end to end — object storage has no index into a gzip stream — but a 0.1% sample
costs 0.1% of the memory and the search, which is the part that is out of reach (D-078).

**No sequence reaches an artefact.** D-103 draws the line: residues may live in memory, and
in ephemeral scratch outside the working tree when a later pass has to search them again, but
never in the repository, in `artifacts/`, in the audit store, or in anything a reviewer reads
as a result — which is why A7.1's splitter measures the sequence and drops it. What this module
yields is for computing on, not for keeping.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from amazebio.conformance import parse_lineage_tag
from amazebio.corpora import LINEAGE_WINDOW, LineageError, tag_of
from amazebio.detect import in_band
from amazebio.policyspec import Record

__all__ = [
    "SampledRecord",
    "iter_fasta_sampled",
    "iter_fasta_selected",
    "iter_stage2_sampled",
]


@dataclasses.dataclass(frozen=True, slots=True)
class SampledRecord:
    """One sampled record: the policy-side record, and its residues for as long as they are used.

    `sequence` is nucleotide for both Evo components. It is never serialised — see the module
    docstring and D-020.
    """

    record: Record
    sequence: str

    @property
    def id(self) -> str:
        return self.record.id

    def __len__(self) -> int:
        return len(self.sequence)


def iter_stage2_sampled(
    reader: Any,
    *,
    component: str,
    record_prefix: str,
    seed: int,
    hi: float,
    lo: float = 0.0,
    on_parse_error: Callable[[str, LineageError], None] | None = None,
) -> Iterator[SampledRecord]:
    """Yield the sampled rows of an Evo 1 stage-2 object, with sequence.

    One row is one record (D-048), and a record longer than the block budget arrives as several
    `|tag|block` pairs in that one row, every pair carrying the same tag — so the record's
    sequence is the blocks concatenated, in order. The taxonomy comes from the leading tag, the
    same reading `amazebio.corpora.iter_stage2_records` applies, so a record's route here is
    resolved from the same evidence A1.4's manifest resolved its outcome from.

    Rows are selected by hash band (`amazebio.detect.in_band`) before being materialised: the
    row index gives the identifier, the identifier gives band membership, and only the selected
    rows are decoded out of Arrow.
    """
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(reader)
    if parquet.schema_arrow.names != ["text"]:
        raise ValueError(
            f"expected the documented single-column `text` schema, got "
            f"{parquet.schema_arrow.names}; the record unit this reader assumes is that schema"
        )
    row = 0
    for group in range(parquet.metadata.num_row_groups):
        table = parquet.read_row_group(group, columns=["text"])
        text = table.column("text")
        first = row
        row += table.num_rows
        wanted = [
            i
            for i in range(table.num_rows)
            if in_band(f"{record_prefix}#{first + i}", seed=seed, lo=lo, hi=hi)
        ]
        if not wanted:
            continue
        for i, full in zip(wanted, text.take(wanted).to_pylist(), strict=True):
            record_id = f"{record_prefix}#{first + i}"
            if full is None:
                if on_parse_error is not None:
                    on_parse_error(record_id, LineageError("row holds no text at all"))
                continue
            try:
                tag = parse_lineage_tag(tag_of(full[:LINEAGE_WINDOW]))
            except LineageError as exc:
                if on_parse_error is not None:
                    on_parse_error(record_id, exc)
                continue
            yield SampledRecord(
                record=Record(id=record_id, component=component, taxonomy=tag.taxonomy),
                sequence=_blocks_of(full),
            )
        del text, table


def _blocks_of(row: str) -> str:
    """The sequence of one released row: its `|tag|block` pairs' blocks, concatenated.

    A trailing tag with no block is a truncated pair and contributes nothing, which is A7.1's
    reading of the same format (`amazebio.conformance.split_row`).
    """
    if not row.startswith("|"):
        return row
    body = row.split("|")[1:]
    return "".join(body[i + 1] for i in range(0, len(body) - 1, 2))


def iter_fasta_sampled(
    stream: Any,
    *,
    component: str,
    seed: int,
    hi: float,
    lo: float = 0.0,
    chunk: int = 8 << 20,
) -> Iterator[SampledRecord]:
    """Yield the sampled entries of a FASTA stream, with sequence.

    `stream` is anything with `read(size)` — a `RangedObject.buffered()` for a plain FASTA, or
    `amazebio.uniref.GunzipStream` around one for a `.gz`. The identifier is the header's first
    token, which for Evo 2's viral component is the IMG/VR accession.

    No taxonomy is parsed because this component carries none; that absence is A1.4's finding and
    the manifest's evidence declaration is what turns it into `unresolved` outcomes. Sampling is
    decided from the header, so an unsampled entry's residues are discarded as they stream rather
    than accumulated.
    """
    yield from _iter_fasta(
        stream,
        component=component,
        keep=lambda record_id: in_band(record_id, seed=seed, lo=lo, hi=hi),
        chunk=chunk,
    )


def iter_fasta_selected(
    stream: Any,
    *,
    component: str,
    ids: Iterable[str],
    chunk: int = 8 << 20,
    stop_when_complete: bool = True,
) -> Iterator[SampledRecord]:
    """Yield the entries of a FASTA stream whose identifier is in `ids`, with sequence.

    The sibling of :func:`iter_fasta_sampled` for the case where the records are *named* rather
    than sampled: A7.5 re-reads a handful of records whose identifiers a published table already
    carries, so membership is a set lookup and not a hash band (D-078). Same stream contract,
    same `SampledRecord`, same discarding of an unwanted entry's residues as they pass.

    `stop_when_complete` ends the stream once every requested identifier has been seen, which a
    band selector can never do because it cannot know it is finished. It changes nothing a caller
    can observe except the time taken and the bytes read: an identifier not seen by the early stop
    and one not seen by the end of the object are the same absence, since the stop happens only
    after the last requested record has been yielded. A second entry carrying an identifier
    already yielded is the one thing it hides, so a caller that has to count duplicate headers
    passes `stop_when_complete=False` and reads the object through.
    """
    wanted = set(ids)
    remaining = set(wanted)
    for record in _iter_fasta(
        stream,
        component=component,
        keep=lambda record_id: record_id in wanted,
        chunk=chunk,
    ):
        remaining.discard(record.id)
        yield record
        if stop_when_complete and not remaining:
            return


def _iter_fasta(
    stream: Any,
    *,
    component: str,
    keep: Callable[[str], bool],
    chunk: int,
) -> Iterator[SampledRecord]:
    """The FASTA loop both selectors share: `keep` decides from the identifier alone.

    Factored out for A7.5 rather than parameterising `iter_fasta_sampled`, whose signature is
    cited from A2.1 and A3.4. `keep` is called with the header's first token and never with an
    empty one, so a headerless or blank-named entry is dropped by the same rule in both.
    """
    record_id: str | None = None
    wanted = False
    parts: list[str] = []
    tail = b""

    def emit() -> Iterator[SampledRecord]:
        if record_id is not None and wanted:
            yield SampledRecord(
                record=Record(id=record_id, component=component),
                sequence="".join(parts),
            )

    def header_of(raw: bytes) -> tuple[str, bool]:
        header = raw[1:].decode("utf-8", "replace").strip()
        token = header.split()[0] if header.split() else ""
        return token, bool(token) and keep(token)

    while True:
        block = stream.read(chunk)
        if not block:
            break
        data = tail + block
        lines = data.split(b"\n")
        tail = lines.pop()
        for raw in lines:
            if raw.startswith(b">"):
                yield from emit()
                record_id, wanted = header_of(raw)
                parts = []
            elif wanted:
                parts.append(raw.decode("ascii", "replace").strip())
    if tail:
        if tail.startswith(b">"):
            yield from emit()
            record_id, wanted = header_of(tail)
            parts = []
        elif wanted:
            parts.append(tail.decode("ascii", "replace").strip())
    yield from emit()

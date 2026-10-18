"""Reading the two releases' prokaryotic components, and agreeing what a genome is.

A2.4 detects integrated elements in surviving bacterial genomes, so its record unit is the
*genome*. Neither release hands one over directly, and they fail to in opposite ways — which is
the whole reason this module exists rather than a reader being bolted onto
`amazebio.corpora`.

**Evo 2's component is already genome-shaped.** `fasta/gtdb_v220/...` is a tar whose every member
is one gzipped FASTA named for its assembly — `batch1/GCF_017922435.1.fasta.gz` — so one member
is one genome and the member name is the identifier. Nothing has to be derived.

**Evo 1's component is contigs with no genome column.** `stage1/gtdb/*.parquet` carries two
columns, `record` and `text`: an INSDC nucleotide accession and a sequence. There is no assembly
accession, no organism, no grouping key of any kind published alongside. Taken at face value the
record unit would be the contig, and that is the wrong unit for this task twice over — a provirus
is a feature of a genome, and a per-contig denominator would make a 400-contig draft assembly
count four hundred times a complete one.

So the grouping is **derived** from the accessions themselves, and D-136 records it as a reading
with what it costs. An INSDC WGS accession encodes its project: `JAHFAU010000149.1` is contig
`0000149` of WGS project `JAHFAU01`, and a project is an assembly. :func:`genome_key` recovers
that, and reports the kind of key it recovered so a caller can never confuse a derived grouping
with a published one. Measured over 40,000 contigs of `gtdb_train_shard_0`, 99.72% carry a WGS
project accession and group into genomes at a median of 43 contigs each; the remaining 0.28% are
complete-genome and scaffold accessions (`NZ_CP038213.1`, `NZ_GL890993.1`, `NZ_CM001022.1`) which
carry no project and therefore cannot be grouped at all. Those become one "genome" per accession,
which **under-groups**: a chromosome and its plasmids are counted as separate genomes. The error
is bounded, measured and in the direction of a larger denominator, which makes the survival
fraction this feeds a conservative one.
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

__all__ = [
    "GenomeKey",
    "GtdbError",
    "assembly_of_member",
    "genome_key",
    "iter_og1_contigs",
    "iter_og2_genomes",
]


class GtdbError(RuntimeError):
    """Raised when a staged prokaryotic object cannot be read as what it claims to be."""


#: An INSDC WGS accession: an optional two-letter RefSeq prefix (`NZ_`), then the four-to-six
#: letter project code and its two-digit version, then the contig number and the version.
#:
#: The letter count is what separates a WGS contig from a complete replicon, and it is doing
#: real work: `NZ_LIXJ01000001.1` is WGS (four letters, project `LIXJ01`), while
#: `NZ_CP038213.1` is a complete chromosome (two letters) and `NZ_GL890993.1` a scaffold. A
#: looser pattern would read `CP038213` as project `CP03` and silently merge unrelated genomes,
#: which is the failure this regex is shaped to avoid.
_WGS = re.compile(r"^(?:[A-Z]{2}_)?([A-Z]{4,6}\d{2})\d{6,}(?:\.\d+)?$")


@dataclass(frozen=True, slots=True)
class GenomeKey:
    """The genome a record belongs to, and how confidently that was established."""

    key: str
    #: `wgs_project` when the key is a published WGS project accession shared by the assembly's
    #: contigs. `accession` when no project could be recovered and the record stands alone —
    #: a grouping of one, which may under-group a multi-replicon genome.
    kind: str

    @property
    def is_derived_grouping(self) -> bool:
        return self.kind == "wgs_project"


def genome_key(record_id: str) -> GenomeKey:
    """The genome key for one Evo 1 GTDB contig accession.

    Never raises on an unrecognised accession. An id this cannot parse is a genome of one rather
    than an error, because the alternative — dropping it — would shrink the corpus silently, and
    `AGENTS.md` forbids designing any part of the pipeline so that a gap is harder to see.
    """
    text = record_id.strip()
    if not text:
        raise GtdbError("empty record id: the Parquet row carries no accession to group on")
    match = _WGS.match(text)
    if match:
        return GenomeKey(key=match.group(1), kind="wgs_project")
    return GenomeKey(key=text, kind="accession")


def assembly_of_member(name: str) -> str:
    """The assembly accession from an Evo 2 GTDB tar member name.

    `batch1/GCF_017922435.1.fasta.gz` -> `GCF_017922435.1`. Published rather than derived: the
    publisher named the member for the assembly, so this strips a path and two suffixes and
    invents nothing.
    """
    base = name.rsplit("/", 1)[-1]
    for suffix in (".fasta.gz", ".fna.gz", ".fasta", ".fna", ".gz"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    raise GtdbError(
        f"tar member {name!r} does not look like a genome FASTA; the component's layout has "
        "changed, which invalidates the staged pin rather than this parser"
    )


def iter_og1_contigs(
    parquet_file: Any, *, columns: tuple[str, str] = ("record", "text")
) -> Iterator[tuple[str, str]]:
    """Yield `(accession, sequence)` for every contig in one Evo 1 GTDB Parquet object.

    Row group by row group, because the shards are ~10.5 GB each with a thousand row groups and
    a session container does not hold one whole. The two columns are named rather than taken by
    position, for the reason D-090 cost A4.2 a headline.
    """
    schema = {name for name in parquet_file.schema_arrow.names}
    missing = [c for c in columns if c not in schema]
    if missing:
        raise GtdbError(
            f"Evo 1 GTDB object is missing the column(s) {missing!r}; it has {sorted(schema)!r}"
        )
    ident, seq = columns
    for group in range(parquet_file.metadata.num_row_groups):
        table = parquet_file.read_row_group(group, columns=list(columns))
        for accession, sequence in zip(
            table[ident].to_pylist(), table[seq].to_pylist(), strict=True
        ):
            if accession is None or sequence is None:
                continue
            yield accession, sequence


def iter_og2_genomes(stream: Any) -> Iterator[tuple[str, list[tuple[str, str]]]]:
    """Yield `(assembly_accession, [(contig_header, sequence), ...])` from an Evo 2 GTDB tar.

    Streamed with `r|`, not `r`, which matters: the seekable mode builds an index of the whole
    archive before yielding anything, and these are 25-28 GB objects read over the network. The
    streaming mode gives up random access and reads each member once, in order, which is the
    access pattern a one-pass detector wants anyway.

    A member that is not a genome FASTA stops the run rather than being skipped — a silently
    skipped member is a genome missing from the denominator.
    """
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is None:  # pragma: no cover - defensive; isfile() implies extractable
                raise GtdbError(f"tar member {member.name!r} is a file but could not be read")
            payload = handle.read()
            if member.name.endswith(".gz"):
                payload = gzip.decompress(payload)
            yield assembly_of_member(member.name), _parse_fasta(payload.decode("ascii", "replace"))


def _parse_fasta(text: str) -> list[tuple[str, str]]:
    """FASTA into `[(header, sequence)]`, headers without the `>`."""
    out: list[tuple[str, str]] = []
    header: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header is not None:
                out.append((header, "".join(chunks)))
            header = line[1:].strip()
            chunks = []
        elif header is not None:
            chunks.append(line.strip())
    if header is not None:
        out.append((header, "".join(chunks)))
    return out


def tar_stream(client: Any, bucket: str, key: str, *, chunk: int = 1 << 23) -> io.RawIOBase:
    """A file-like object over an S3 object, for `tarfile`'s streaming mode.

    `get_object`'s body is already a stream, but `tarfile` asks for `read(n)` to return exactly
    `n` bytes until EOF and a raw botocore body does not guarantee that. Wrapping it keeps the
    short-read-is-a-failure discipline `amazebio.objectstore` documents: a truncated member would
    decompress to a shorter genome, and a provirus search over a truncated genome is not a
    search over that genome.
    """

    class _Body(io.RawIOBase):
        def __init__(self) -> None:
            self._body = client.get_object(Bucket=bucket, Key=key)["Body"]
            self._buf = b""

        def readable(self) -> bool:
            return True

        def read(self, size: int = -1) -> bytes:
            if size is None or size < 0:
                parts = [self._buf, self._body.read()]
                self._buf = b""
                return b"".join(parts)
            while len(self._buf) < size:
                piece = self._body.read(max(chunk, size - len(self._buf)))
                if not piece:
                    break
                self._buf += piece
            out, self._buf = self._buf[:size], self._buf[size:]
            return out

    return _Body()

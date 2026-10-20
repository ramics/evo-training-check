"""What a contig is on each side of the OpenGenome comparison — task A7.4, §A7.

The two staged representations of the same sequence set do not agree on their shape.
OpenGenome v1 is Parquet with one row per contig, carrying an INSDC accession in `record`
and the residues in `text`. OpenGenome2's GTDB subtree is a tar of gzipped multi-FASTA, one
member per assembly, each holding that assembly's contigs under their own headers. D-213
fixes the comparison key as the contig accession, with a sequence digest settling the set
the accessions disagree about.

So this module answers one question for both sides: given a record, what is its accession
and what is the digest of its sequence? Everything that could be decided differently on one
side than the other is decided here, once:

* **The accession is the first whitespace-delimited token of the FASTA header**, which is
  the INSDC convention and is what v1's `record` column holds. A header's description is
  not part of its identity.
* **The digest is over uppercased residues with all whitespace removed.** FASTA wraps at a
  line width the publisher chooses and v1's Parquet does not wrap at all, so a digest over
  the bytes as stored would report every contig as different. Case is normalised for the
  same reason: lowercase in a genome FASTA is soft-masking, a property of the annotation
  rather than of the sequence.
* **The digest covers the residues and nothing else**, not the header, so a renamed contig
  with identical sequence is a representation difference and says so.

**What it refuses.** A member with two contigs under one accession, and a header with no
token after the `>`. Both would silently collapse two records into one, and a count of
records that silently lost some is the one output this task cannot use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Iterable, Iterator

__all__ = [
    "Contig",
    "ContigError",
    "accession_of",
    "digest_sequence",
    "parse_fasta",
    "strain_of",
]

#: A GTDB member is named for its assembly; a contig inside it is named for its INSDC record.
_ASSEMBLY = re.compile(r"^GC[AF]_\d+\.\d+$")


class ContigError(ValueError):
    """A refusal: the record cannot be given an identity this comparison can use."""


@dataclasses.dataclass(frozen=True, slots=True)
class Contig:
    """One sequence record, identified and digested, with its residues not retained."""

    accession: str
    length: int
    sha256: str


def accession_of(header: str) -> str:
    """`>JAHFAU010000168.1 Pseudomonas sp., whole genome shotgun` -> `JAHFAU010000168.1`.

    Raises rather than returning the whole header or an empty string: an unnameable record
    joined on an empty key matches every other unnameable record, which turns a parse
    failure into a spurious agreement.
    """
    token = header.lstrip(">").split(maxsplit=1)
    if not token or not token[0]:
        raise ContigError(f"a header with no accession before its description: {header[:80]!r}")
    return token[0]


def digest_sequence(chunks: Iterable[str | bytes]) -> tuple[str, int]:
    """The sha256 of the residues, and how many there are, over an iterable of pieces.

    Streaming rather than joined: a bacterial chromosome runs to several megabases and the
    pass holds tens of millions of them, so a `"".join` over one contig's lines is the
    difference between a flat memory profile and an instance that is sized for the longest
    genome it happens to meet.
    """
    digest = hashlib.sha256()
    length = 0
    for chunk in chunks:
        text = chunk.decode("ascii", "strict") if isinstance(chunk, bytes) else chunk
        residues = "".join(text.split()).upper()
        if not residues:
            continue
        digest.update(residues.encode("ascii"))
        length += len(residues)
    return digest.hexdigest(), length


def parse_fasta(lines: Iterable[str | bytes], *, source: str = "") -> Iterator[Contig]:
    """Yield one `Contig` per record of a FASTA stream, holding one record at a time.

    Args:
        lines: the file's lines, as text or ASCII bytes.
        source: what to name in a refusal — a member name, usually.

    Raises:
        ContigError: on a repeated accession within the stream, or an unnameable header.
    """
    seen: set[str] = set()
    header: str | None = None
    pieces: list[str] = []

    def finish(name: str) -> Contig:
        sha, length = digest_sequence(pieces)
        if name in seen:
            raise ContigError(
                f"{source or 'stream'}: {name} appears twice. Two records under one "
                "accession cannot both be compared, and dropping either silently changes "
                "the count this task reports."
            )
        seen.add(name)
        return Contig(accession=name, length=length, sha256=sha)

    for raw in lines:
        line = raw.decode("ascii", "replace") if isinstance(raw, bytes) else raw
        if line.startswith(">"):
            if header is not None:
                yield finish(accession_of(header))
            header, pieces = line.rstrip("\n"), []
        elif header is not None:
            pieces.append(line)
        elif line.strip():
            raise ContigError(f"{source or 'stream'}: residues before any header")
    if header is not None:
        yield finish(accession_of(header))


def strain_of(member_name: str) -> str:
    """`batch1/GCA_018384735.1.fasta.gz` -> `GCA_018384735.1`.

    The same derivation `tools/opengenome_reuse.py` uses for the genome-level half, kept
    here so the contig pass names a genome the same way the genome pass did — a comparison
    whose two halves disagree about what an assembly is called is two comparisons.
    """
    leaf = member_name.rsplit("/", 1)[-1]
    for suffix in (".fasta.gz", ".fna.gz", ".fasta", ".fna"):
        if leaf.endswith(suffix):
            leaf = leaf[: -len(suffix)]
            break
    if not _ASSEMBLY.match(leaf):
        raise ContigError(f"{member_name!r} is not named for an assembly accession")
    return leaf

"""Evo 2's eukaryotic genome component: indexing it, and sampling assemblies out of it.

A2.3 detects endogenous elements in surviving host genomes, and the only host genomes in either
audited release are Evo 2's `fasta/ncbi_eukaryotic_genomes` (D-182). Three properties of that
component are why this module exists rather than a reader being added to `amazebio.gtdb`:

**It is not staged, and most of it never will be.** 2.17 TB against a corpus bucket with no
`s3:DeleteObject`, so D-031 deferred the tier and the project owner chose a 1% sample of whole
assemblies (D-182). A sampled stage of an unstaged component needs a way to address one assembly
inside a 20-44 GB archive without reading the archive.

**It is 90 tars, not 15,000 files.** The publisher batched it, so the smallest thing addressable
by name is a tar. Members are `batch1/GCA_018245875.1.fasta.gz` — one gzipped FASTA per assembly,
named for its NCBI assembly accession, which is the same shape Evo 2's GTDB component has and the
reason `gtdb.assembly_of_member` is reused here rather than reimplemented.

**A tar is addressable without being read.** Each member is a 512-byte header followed by its
data padded to 512, so the header chain can be walked by transferring 512 bytes per member and
seeking past the data. :func:`walk_index` does that over an injected range reader, which is what
turns "stage a sample of 2.17 TB" into about 8 MB of transfer for the index and 22 GB for the
sample itself.

The walker is deliberately a pure function of `read_range`. The same code indexes the publisher's
tree over HTTP and a staged object over S3, and the tests drive it with a real tar built in
memory — no network, and no fixture that could drift from the format it claims to parse.

**Every structural surprise stops the walk.** A header whose checksum does not verify, an
extension the format allows but this component does not use, a member that is not a genome FASTA:
each raises. The reason is the same one `gtdb.iter_og2_genomes` gives for refusing to skip a
member — a silently skipped member is a genome missing from the denominator, and this index *is*
the denominator for every figure A2.3 reports.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from amazebio.gtdb import assembly_of_member

__all__ = [
    "BLOCK",
    "COMPONENT",
    "EukaryoteError",
    "Member",
    "index_to_rows",
    "rows_to_index",
    "sampled_members",
    "size_summary",
    "walk_index",
]

#: The tar block size. Headers are one block; member data is padded to a whole number of them.
BLOCK = 512

#: The release component this module reads. The prefix is `opengenome.OG2_COMPONENTS`'
#: `ncbi_eukaryotic_genomes` entry, repeated here as the string the walker filters a tree on.
COMPONENT = "fasta/ncbi_eukaryotic_genomes"


class EukaryoteError(RuntimeError):
    """Raised when the component cannot be read as the layout D-182 pinned."""


#: A reader for one byte range of one path, `(path, start, end_inclusive) -> bytes`. Injected so
#: the walker is independent of whether the bytes come from the publisher or from object storage.
RangeReader = Callable[[str, int, int], bytes]


@dataclasses.dataclass(frozen=True, slots=True)
class Member:
    """One assembly inside one tar of the component.

    `offset` is where the *data* starts, not the header, because that is what a ranged GET of the
    member needs. The header's own offset is `offset - BLOCK` and is not carried: nothing reads
    it twice, and a second coordinate that must agree with the first is a second thing to get
    wrong.
    """

    accession: str
    tar: str
    offset: int
    size: int

    @property
    def end(self) -> int:
        """The last byte of the member's data, inclusive — an HTTP/S3 range's upper bound."""
        return self.offset + self.size - 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "tar": self.tar,
            "offset": self.offset,
            "size": self.size,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Member:
        try:
            return cls(
                accession=str(row["accession"]),
                tar=str(row["tar"]),
                offset=int(row["offset"]),
                size=int(row["size"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EukaryoteError(f"index row is not a member: {row!r} ({exc})") from exc


def _octal(field: bytes, *, what: str) -> int:
    """A tar numeric field, which is octal ASCII padded with NULs and spaces.

    Tolerates an empty field as zero, because the format allows it for a directory's size, and
    refuses anything else rather than guessing — a misparsed size walks the chain off a header
    boundary, and every member after it would be garbage.
    """
    text = field.rstrip(b"\0 ").lstrip(b" ")
    if not text:
        return 0
    try:
        return int(text, 8)
    except ValueError as exc:
        raise EukaryoteError(f"tar {what} field is not octal: {field!r}") from exc


def _checksum_ok(header: bytes) -> bool:
    """Verify the header's own checksum, treating the checksum field as spaces.

    This is the walk's integrity check and it is not decoration. The chain is walked by arithmetic
    on sizes, so one wrong size silently lands the next read in the middle of a member's data,
    where almost any bytes can be misread as a plausible name. A header that does not checksum is
    the earliest possible place to notice, and it is one `sum()` per member.

    Both the unsigned and the signed sum are accepted, because historical writers differed over
    whether the bytes were signed and readers are expected to take either.
    """
    recorded = _octal(header[148:156], what="checksum")
    blanked = header[:148] + b" " * 8 + header[156:]
    unsigned = sum(blanked)
    signed = sum(b - 256 if b > 127 else b for b in blanked)
    return recorded in (unsigned, signed)


def walk_index(
    tar: str,
    total: int,
    read_range: RangeReader,
    *,
    expect_suffix: str = ".fasta.gz",
) -> Iterator[Member]:
    """Walk one tar's header chain, yielding one :class:`Member` per assembly.

    Transfers one block per member plus nothing for the data, so indexing a 20 GB archive of 170
    assemblies costs about 87 KB. `total` is the archive's size from the pinned tree: the walk
    stops there rather than on the end-of-archive marker alone, so a truncated object cannot be
    read as a short-but-complete one.

    Directories are skipped. Regular files must end in `expect_suffix` and must yield an assembly
    accession. Anything else — a long-name extension, a PAX header, a symlink, a sparse entry —
    raises, because each would mean the component's layout has changed and the pin D-182 took is
    describing something else.
    """
    offset = 0
    seen = 0
    zero_blocks = 0
    while offset + BLOCK <= total:
        header = read_range(tar, offset, offset + BLOCK - 1)
        if len(header) != BLOCK:
            raise EukaryoteError(
                f"{tar}: short read of {len(header)} bytes for the header at {offset}; a partial "
                "header cannot be distinguished from a different member, so the walk stops"
            )
        if not header.strip(b"\0"):
            # Two consecutive zero blocks end the archive. One on its own is not a terminator and
            # must not be read as the end of the component.
            zero_blocks += 1
            offset += BLOCK
            if zero_blocks >= 2:
                return
            continue
        zero_blocks = 0
        if not _checksum_ok(header):
            raise EukaryoteError(
                f"{tar}: header checksum mismatch at offset {offset} after {seen} members; the "
                "walk has lost the block boundary and every member after this would be garbage"
            )
        name = header[0:100].rstrip(b"\0").decode("utf-8", "replace")
        prefix = header[345:500].rstrip(b"\0").decode("utf-8", "replace")
        full = f"{prefix}/{name}" if prefix else name
        kind = header[156:157]
        size = _octal(header[124:136], what=f"size of {full!r}")
        data = offset + BLOCK
        padded = ((size + BLOCK - 1) // BLOCK) * BLOCK

        if kind in (b"5",):  # directory
            offset = data + padded
            continue
        if kind not in (b"0", b"\0"):  # regular file, old-style or new
            raise EukaryoteError(
                f"{tar}: member {full!r} has tar type {kind!r}, which this component does not "
                "use; the layout has changed and the D-182 pin no longer describes it"
            )
        if not full.endswith(expect_suffix):
            raise EukaryoteError(
                f"{tar}: member {full!r} does not end in {expect_suffix!r}; a member that is not "
                "a genome FASTA is a genome missing from the denominator, so it is not skipped"
            )
        if data + size > total:
            raise EukaryoteError(
                f"{tar}: member {full!r} claims bytes {data}-{data + size - 1} beyond the "
                f"archive's {total}; the object is truncated relative to its pin"
            )
        yield Member(accession=assembly_of_member(full), tar=tar, offset=data, size=size)
        seen += 1
        offset = data + padded


def sampled_members(
    members: Iterable[Member], *, seed: int, lo: float = 0.0, hi: float
) -> list[Member]:
    """The members whose accession falls in the hash band `[lo, hi)`.

    The selection rule is the project's, not a new one: `amazebio.detect.in_band` over the
    assembly accession, at the seed D-182 pinned. Keyed on the accession rather than on the
    member name so that the same assembly selects identically however the publisher batches it —
    a re-batched release would move members between tars without changing which genomes are in
    the sample.

    Returned sorted by accession so a staging run's order is a property of the sample rather than
    of the order the tars happened to be indexed in.
    """
    from amazebio.detect import in_band

    chosen = [m for m in members if in_band(m.accession, seed=seed, lo=lo, hi=hi)]
    return sorted(chosen, key=lambda m: m.accession)


def index_to_rows(members: Iterable[Member]) -> list[dict[str, Any]]:
    """The index as JSON-ready rows, sorted by `(tar, offset)` — the order a tar reader wants."""
    return [m.to_dict() for m in sorted(members, key=lambda m: (m.tar, m.offset))]


def rows_to_index(rows: Iterable[dict[str, Any]]) -> list[Member]:
    """Rows back into members, refusing a duplicated accession.

    A duplicate would double-count a genome in the denominator and, if the two rows disagreed on
    coordinates, make which bytes were searched depend on dictionary order.
    """
    out: list[Member] = []
    seen: dict[str, Member] = {}
    for row in rows:
        member = Member.from_dict(row)
        if member.accession in seen:
            raise EukaryoteError(
                f"assembly {member.accession} appears twice in the index: "
                f"{seen[member.accession].tar} and {member.tar}"
            )
        seen[member.accession] = member
        out.append(member)
    return out


def load_index(path: str | Path) -> list[Member]:
    """Read an index artefact written by `tools/index_eukaryotes.py`."""
    payload = json.loads(Path(path).read_text())
    rows = payload["members"] if isinstance(payload, dict) else payload
    return rows_to_index(rows)


def size_summary(members: Iterable[Member]) -> dict[str, Any]:
    """Count and compressed-byte totals, with the quantiles that decide what a sample costs.

    Reported because the sample's byte cost is not 1% of the component unless the size
    distribution is tame, and these members span two orders of magnitude — 4.7 MB to 428 MB
    compressed. The realized bytes of a hash sample are a draw from this distribution, so the
    quantiles are what make a staged sample's size a checked expectation rather than a surprise.
    """
    sizes = sorted(m.size for m in members)
    if not sizes:
        return {"assemblies": 0, "bytes": 0}

    def q(p: float) -> int:
        return sizes[min(len(sizes) - 1, max(0, round(p * (len(sizes) - 1))))]

    return {
        "assemblies": len(sizes),
        "bytes": sum(sizes),
        "min": sizes[0],
        "p25": q(0.25),
        "median": q(0.5),
        "p75": q(0.75),
        "p95": q(0.95),
        "max": sizes[-1],
    }

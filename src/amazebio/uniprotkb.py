"""Count UniProtKB entries by taxon at a *pinned past release*, streaming the bulk archive.

**Why this exists.** ESM3 says its select-agent denylist is "all sequences in UniProt belonging
to organisms on the Select Agents and Toxins List", 147K non-viral plus 40K viral (version of
record, A.6.1 p47). A1.8 can execute that procedure against today's UniProtKB over the REST
API, and did — but UniProtKB has shrunk 40% since the release ESM3 names, from 249,878,458
entries at 2023_02 to 150,006,383 now, because redundant proteomes were removed. The shrinkage
falls hardest on over-sequenced bacteria, which is exactly what the non-viral half of the
select-agent list is. So a count at the current release cannot settle whether the reading is
right, and the gap it leaves is the same size as the effect (D-150, and the correction to it).

The REST service serves the current release only. The dated archive is not blocked, though —
`previous_releases/release-2023_02/` holds the whole knowledgebase, and UniProt numbers
UniProtKB and UniRef together, so that directory is exactly the release the filter saw.

**What the archive actually contains, which decides the whole design.** One tarball,
182,691,908,438 bytes, holding `docs/`, `reldate.txt`, `uniprot_sprot.dat.gz` (656 MB) and
`uniprot_trembl.dat.gz` (181.8 GB). **There are no FASTA files** — only the flat-file format —
and tar is sequential, so there is no way to fetch the one member or to skip ahead. The pass
reads the archive end to end, once.

Three consequences worth stating before someone tries to improve on them:

* **Two layers of gzip, and neither can be parallelised.** The outer stream is the tarball; the
  members are separately gzipped inside it. A gzip stream is inherently single-threaded, so
  instance size buys nothing here — the same lesson the UniRef tiers taught (AGENTS.md).
* **Per-line iteration in Python would dominate the run.** About 250M entries at ~30 lines each
  is some 7.5 billion lines, and Python's line loop is far slower than the decompressor feeding
  it. So this module never iterates lines: it scans fixed byte chunks with a compiled regex and
  `bytes.count`, both of which run at C speed, and carries a remainder across the boundary so a
  record split between chunks is still seen exactly once.
* **Truncation is the failure mode that looks like success.** A stream cut short yields a
  smaller count and no error, which would read as "the reading over-counts" — an error in the
  direction that flatters the safeguard. The release's own published entry total is therefore
  checked against the entries actually seen, and a mismatch fails the run rather than being
  reported as a result.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from amazebio.seeds import Attribution, EntryCounts

#: The flat-file line carrying the organism's NCBI taxon, one per entry.
#:
#: Anchored to a line start, because `OX` can appear inside free text on `CC` and `RL` lines
#: and an unanchored match would count those. Multi-line `OX` does not occur in UniProtKB —
#: every entry has exactly one taxon — so one match per entry is the invariant the totals
#: below are checked against.
OX_LINE = re.compile(rb"(?m)^OX   NCBI_TaxID=(\d+)")

#: Entry starts, counted to verify the stream arrived whole. `ID` is the first line of every
#: flat-file record, so this is the release's entry count as the publisher reports it.
ID_LINE = b"\nID   "

#: Published totals for release 2023_02, from the release statistics served beside the
#: archive. Checked rather than trusted: the point of carrying them is to fail a truncated
#: stream, and a figure nobody compares anything to would not do that.
RELEASE_2023_02 = {
    "release": "2023_02",
    "date": "2023-05-03",
    "trembl_entries": 249_308_459,
    "sprot_entries": 569_516,
    "url": (
        "https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/"
        "release-2023_02/knowledgebase/knowledgebase2023_02.tar.gz"
    ),
    "bytes": 182_691_908_438,
    "members": ("uniprot_sprot.dat.gz", "uniprot_trembl.dat.gz"),
}


@dataclass
class TaxonCounts:
    """Entries seen, and how many of them carry a denylisted taxon.

    `entries` counts every record in the member, which is what the release statistic can be
    compared against; `seeded` counts only the matches. Keeping both is what turns a short
    read into a failure instead of a smaller answer.

    `viral` is counted for A1.6 rather than for this arm, and the reason is arithmetic: ESM3
    states its viral denylist as "roughly 4M sequences that are annotated as viral in UniProt" — a
    UniProt count at a release that has since lost 40% of its entries, so A1.6 cannot check
    its reading against 4M with current data any more than A1.8 could check 187K. Counting
    the Viruses superkingdom costs one set lookup per `OX` line on a pass that is already
    reading every one of them, against a second 182.7 GB download if it were done separately.
    A1.6 owns what the number means; this module only refuses to read the archive twice.
    """

    entries: int = 0
    with_taxon: int = 0
    seeded: int = 0
    viral: int = 0
    by_taxid: dict[int, int] = field(default_factory=dict)
    by_entry: EntryCounts = field(default_factory=EntryCounts)

    def merge(self, other: TaxonCounts) -> None:
        self.entries += other.entries
        self.with_taxon += other.with_taxon
        self.seeded += other.seeded
        self.viral += other.viral
        for taxid, n in other.by_taxid.items():
            self.by_taxid[taxid] = self.by_taxid.get(taxid, 0) + n
        self.by_entry.merge(other.by_entry)

    def to_dict(self) -> dict[str, object]:
        return {
            "entries": self.entries,
            "with_taxon": self.with_taxon,
            "seeded": self.seeded,
            "seeded_share": (self.seeded / self.entries if self.entries else None),
            "viral": self.viral,
            "by_entry": self.by_entry.to_dict(),
            # Taxon-level detail stays keyed by id and is not published by organism (D-125).
            "by_taxid": dict(sorted(self.by_taxid.items(), key=lambda kv: (-kv[1], kv[0]))),
        }


def scan_chunks(
    chunks: Iterable[bytes],
    denylist: frozenset[int],
    attribution: Attribution | None = None,
    counts: TaxonCounts | None = None,
    viral: frozenset[int] | None = None,
    on_chunk: Callable[[TaxonCounts], None] | None = None,
) -> TaxonCounts:
    """Count entries and denylisted taxa over a decompressed flat-file byte stream.

    `chunks` is any iterable of byte blocks — the member stream read in fixed sizes. Blocks
    are not records and a record will straddle them, so the tail after the last newline is
    held back and prepended to the next block; that makes the result independent of the block
    size, which a test asserts across several.

    **Pass the whole stream in one call.** The remainder lives in this frame, so calling it
    once per block throws that state away between blocks and silently loses any token the
    boundary splits. A1.8's first full run did exactly that and came up 126 entries short of
    the release statistic across 249,308,459 — about what a six-byte token and 162,000 block
    boundaries predicts. It was caught only because the publisher's own total is checked;
    nothing in the output looked wrong. `on_chunk` exists so that a caller wanting progress
    reports has no reason to break the stream up: it is called after each block with the
    running counts.
    """
    out = counts if counts is not None else TaxonCounts()
    remainder = b""
    for chunk in chunks:
        if not chunk:
            continue
        buffer = remainder + chunk
        cut = buffer.rfind(b"\n")
        if cut == -1:
            remainder = buffer
            continue
        body, remainder = buffer[: cut + 1], buffer[cut + 1 :]
        _absorb(out, body, denylist, attribution, viral)
        if on_chunk is not None:
            on_chunk(out)
    if remainder:
        _absorb(out, remainder + b"\n", denylist, attribution, viral)
    return out


def _absorb(
    out: TaxonCounts,
    body: bytes,
    denylist: frozenset[int],
    attribution: Attribution | None,
    viral: frozenset[int] | None = None,
) -> None:
    """Fold one whole-line block in. Both scans are C-level; nothing here loops per line.

    The leading newline `ID_LINE` carries is why the block is prefixed before counting: the
    first record of the stream begins at byte zero with no newline in front of it, and
    without the prefix every member would under-count by exactly one entry — a discrepancy
    small enough to look like rounding against a 249M total and large enough to mean the
    scanner is wrong.
    """
    out.entries += (b"\n" + body).count(ID_LINE)
    for match in OX_LINE.finditer(body):
        out.with_taxon += 1
        taxid = int(match.group(1))
        if viral is not None and taxid in viral:
            out.viral += 1
        if taxid in denylist:
            out.seeded += 1
            out.by_taxid[taxid] = out.by_taxid.get(taxid, 0) + 1
            if attribution is not None:
                out.by_entry.observe(attribution.claiming((taxid,)))


def iter_member_chunks(stream: object, size: int = 8 << 20) -> Iterator[bytes]:
    """Read a decompressed member in fixed blocks until it ends.

    Written against `read` rather than iteration for the reason the module docstring gives:
    the line loop is the thing to avoid, and a file object's own iterator is that loop.
    """
    read = stream.read  # type: ignore[attr-defined]
    while True:
        chunk = read(size)
        if not chunk:
            return
        yield chunk


def verify_whole(counts: TaxonCounts, expected: int, member: str) -> None:
    """Refuse a short read instead of reporting it as a smaller count.

    A truncated stream produces a plausible number and no exception. Here it would understate
    how much denylisted material UniProt held, which is the direction that makes the filter
    look more complete than it was — the failure §2 treats as equivalent to overstating
    leakage. So the publisher's own total is the gate.
    """
    if counts.entries != expected:
        raise ValueError(
            f"{member}: read {counts.entries:,} entries, the release reports {expected:,} "
            f"({counts.entries - expected:+,}). The stream did not arrive whole, and a "
            f"partial count here understates the denylist — refusing rather than reporting it."
        )

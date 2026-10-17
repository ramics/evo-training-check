"""Reconstruct ESM3-open's two denylist seed sets from pinned, already-staged inputs.

ESM3-open's filter is similarity-based rather than taxonomic: it queries the training
databases against two denylists and removes what matches. Neither denylist is published as
a set, so A1.6 has to rebuild both before any alignment can run. This module is that
rebuild, and every choice it makes is a reading rather than a recovery.

The two seed sets, as the source describes them:

* **Viral denylist** — "sequences that are annotated as viral in UniProt and align almost
  exclusively to other viral sequences in UniProt", roughly 4M sequences.
* **Select-agent denylist** — "all sequences in UniProt belonging to organisms on the
  Select Agents and Toxins List".

Three things about this module's approach are decisions, not implementation detail, and each
is recorded in DECISIONS.md rather than only here.

**The seed set is built from the staged UniRef100 release, not from UniProtKB.** "Annotated
as viral in UniProt" is a statement about UniProtKB entries, and the faithful source would be
UniProtKB itself. UniProt does not serve a 2023_02 viral taxonomic division as a separate
file — only whole-release tarballs — so using it would mean acquiring and streaming the entire
knowledgebase archive to reach one member inside it. UniRef100 is already staged, covers every
UniProtKB entry, and carries each member's own NCBI taxonomy id, so the viral membership
question is answerable from bytes this project already holds.

**What that costs is exactness about the sequence, and the cost is measured rather than
assumed.** UniRef100 merges identical sequences *and sub-fragments of 11 or more residues*, so
a cluster's members are not guaranteed to be the same sequence, and the only sequence the
release carries per cluster is the representative's. A cluster can therefore be viral-seeded
through a member while its representative is not viral. On the first 796,477 clusters of
UniRef 2023_02 that is 2.38% of viral-seeded clusters, with 7.75% taxonomically mixed. Both
figures are reported beside the seed count rather than folded into it, and the direction
matters: an over-long representative makes the seed set slightly over-inclusive, which pushes
removal up and survival down, so it is the conservative error for an audit of a safeguard.

**"Almost exclusively" is left unquantified, exactly as the source leaves it.** The viral
denylist's second clause is a condition on how a candidate aligns against the rest of UniProt,
and the source attaches no number to "almost exclusively". This module therefore produces the
*annotation-only* seed set — the first clause alone — and the second clause is a separate,
later restriction that needs its own alignment pass and its own reading. A seed set built from
the first clause alone is a superset of the one the source describes, which again overstates
removal rather than understating it.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections import deque
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

#: NCBI taxonomy id of the Viruses superkingdom. Everything beneath it is viral, phages
#: included — they are viruses, and nothing in ESM3's description carves them out.
VIRAL_ROOT = 10239


@dataclass(frozen=True)
class TaxdumpPin:
    """A dated NCBI taxonomy dump, pinned by checksum.

    The undated `taxdump.tar.gz` NCBI serves at the top of its taxonomy directory is
    rewritten in place every day, so it cannot pin anything. The `taxdump_archive`
    directory keeps dated snapshots, which can. The snapshot chosen is contemporaneous
    with the corpus release being filtered rather than current: ESM3's UniRef component
    is release 2023_02, and whether a given organism was classified as viral is a
    property of the taxonomy in force then. Using today's taxonomy would answer a
    question about today.
    """

    date: str
    url: str
    sha256: str
    bytes: int


#: Contemporaneous with UniRef 2023_02, which is what ESM3 states it parsed.
TAXDUMP_2023_04 = TaxdumpPin(
    date="2023-04-01",
    url="https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump_archive/taxdmp_2023-04-01.zip",
    sha256="6afaee952d95df95d0ec374e53472eeb590693013159b7b36ae3726c15871d07",
    bytes=60742039,
)


class Taxonomy:
    """The parent-of relation from `nodes.dmp`, and descent queries over it."""

    __slots__ = ("parent",)

    def __init__(self, parent: dict[int, int]) -> None:
        self.parent = parent

    @classmethod
    def from_nodes_dmp(cls, lines: Iterable[bytes | str]) -> Taxonomy:
        """Parse `nodes.dmp`. Each row is `taxid\\t|\\tparent\\t|\\t...`."""
        parent: dict[int, int] = {}
        for raw in lines:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            fields = line.split("\t|\t", 2)
            if len(fields) < 2:
                continue
            try:
                parent[int(fields[0])] = int(fields[1])
            except ValueError:
                continue
        return cls(parent)

    @classmethod
    def from_taxdump_zip(cls, path: str | Path) -> Taxonomy:
        """Parse `nodes.dmp` out of a dated `taxdmp_*.zip` without extracting it."""
        with zipfile.ZipFile(path) as archive, archive.open("nodes.dmp") as handle:
            return cls.from_nodes_dmp(handle)

    def descendants(self, root: int) -> set[int]:
        """Every taxid at or beneath `root`.

        Walks children rather than ancestors: the alternative — testing each of three
        million taxids by climbing to its root — repeats the same ancestry millions of
        times, and at this size that difference is minutes against seconds.
        """
        children: dict[int, list[int]] = {}
        for child, par in self.parent.items():
            if child != par:
                children.setdefault(par, []).append(child)
        seen: set[int] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(children.get(node, ()))
        return seen


_ENTRY_END = b"</entry>"
_ENTRY_ID = re.compile(rb'<entry id="([^"]+)"')
_MEMBER_TAXID = re.compile(rb'"NCBI taxonomy" value="(\d+)"')
_REPRESENTATIVE = re.compile(rb"<representativeMember>(.*?)</representativeMember>", re.S)
_SEQUENCE = re.compile(rb'<sequence length="\d+" checksum="[^"]*">(.*?)</sequence>', re.S)
_WHITESPACE = re.compile(rb"\s+")


@dataclass(frozen=True)
class UniRefEntry:
    """One UniRef cluster, reduced to what the seed-set question needs.

    `member_taxids` covers the representative and every member, because a cluster is
    viral-seeded if *any* of its members is viral. `representative_taxid` is kept
    separately so the representative-versus-member gap can be counted rather than
    assumed away.
    """

    cluster_id: str
    sequence: str
    representative_taxid: int | None
    member_taxids: tuple[int, ...]

    def is_viral_seeded(self, viral: set[int]) -> bool:
        """True if any member is viral — the first clause of the denylist's definition."""
        return any(t in viral for t in self.member_taxids)

    def representative_is_viral(self, viral: set[int]) -> bool:
        return self.representative_taxid is not None and self.representative_taxid in viral

    def is_mixed(self, viral: set[int]) -> bool:
        """True if members disagree about being viral."""
        flags = [t in viral for t in self.member_taxids]
        return bool(flags) and any(flags) and not all(flags)


def iter_entries(chunks: Iterable[bytes]) -> Iterator[UniRefEntry]:
    """Stream UniRef XML entries out of an iterable of decompressed byte chunks.

    Deliberately not an XML parser. `uniref100.xml` is 400-odd GB uncompressed and the
    question asked of each entry is narrow — an id, one sequence, a list of taxids — so
    entries are split on their own closing tag and matched with expressions. An
    incremental parser over this file spends most of its time building element trees
    that are discarded immediately.

    The pending buffer is carried across chunks rather than re-sliced, because the
    obvious `buf = buf[i:]` form is quadratic in the chunk size and turns a two-hour
    pass into something much longer. That cost was measured, not guessed.
    """
    pending = b""
    for chunk in chunks:
        parts = (pending + chunk).split(_ENTRY_END)
        pending = parts.pop()
        for part in parts:
            entry = _parse_entry(part)
            if entry is not None:
                yield entry
    leftover = _parse_entry(pending)
    if leftover is not None:
        yield leftover


def _parse_entry(block: bytes) -> UniRefEntry | None:
    """Build an entry from one `<entry>...</entry>` block, or None if it is not one."""
    ident = _ENTRY_ID.search(block)
    if ident is None:
        return None
    representative = _REPRESENTATIVE.search(block)
    if representative is None:
        return None
    sequence = _SEQUENCE.search(representative.group(1))
    if sequence is None:
        return None
    residues = _WHITESPACE.sub(b"", sequence.group(1))
    if not residues:
        return None
    rep_taxids = _MEMBER_TAXID.findall(representative.group(1))
    return UniRefEntry(
        cluster_id=ident.group(1).decode("ascii", "replace"),
        sequence=residues.decode("ascii", "replace"),
        representative_taxid=int(rep_taxids[0]) if rep_taxids else None,
        member_taxids=tuple(int(t) for t in _MEMBER_TAXID.findall(block)),
    )


def write_fasta(handle: IO[bytes], cluster_id: str, sequence: str) -> int:
    """Write one FASTA record, returning the residues written.

    The header is the bare cluster id with no description. MMseqs2 keys results on the
    first whitespace-delimited token, so anything after it is carried through the whole
    pipeline for nothing.
    """
    handle.write(b">" + cluster_id.encode("ascii") + b"\n" + sequence.encode("ascii") + b"\n")
    return len(sequence)


@dataclass
class SeedCounts:
    """What a seed-building pass saw, for the manifest and the write-up.

    `representative_not_viral` and `mixed` are the measured size of the limitation this
    module's docstring describes. They are counts rather than a rate so that a later
    pass over a different tier can be added to them.
    """

    clusters: int = 0
    residues: int = 0
    viral_seeded: int = 0
    viral_residues: int = 0
    representative_not_viral: int = 0
    mixed: int = 0

    def observe(self, entry: UniRefEntry, viral: set[int]) -> bool:
        """Count one entry, returning whether it is viral-seeded."""
        self.clusters += 1
        self.residues += len(entry.sequence)
        if not entry.is_viral_seeded(viral):
            return False
        self.viral_seeded += 1
        self.viral_residues += len(entry.sequence)
        if not entry.representative_is_viral(viral):
            self.representative_not_viral += 1
        if entry.is_mixed(viral):
            self.mixed += 1
        return True

    def merge(self, other: SeedCounts) -> None:
        """Fold another pass's counts in. Used to recombine parallel batches."""
        self.clusters += other.clusters
        self.residues += other.residues
        self.viral_seeded += other.viral_seeded
        self.viral_residues += other.viral_residues
        self.representative_not_viral += other.representative_not_viral
        self.mixed += other.mixed

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "clusters": self.clusters,
            "residues": self.residues,
            "viral_seeded": self.viral_seeded,
            "viral_residues": self.viral_residues,
            "representative_not_viral": self.representative_not_viral,
            "mixed": self.mixed,
            "viral_share": (self.viral_seeded / self.clusters if self.clusters else None),
            "representative_not_viral_share": (
                self.representative_not_viral / self.viral_seeded if self.viral_seeded else None
            ),
            "mixed_share": (self.mixed / self.viral_seeded if self.viral_seeded else None),
        }


def bucket_of(key: str, buckets: int) -> int:
    """Which bucket a key falls in, from a stable hash of it.

    `hash()` is salted per process, so it would put the same cluster in a different
    bucket on two runs — and, worse here, in a *different bucket in each worker*, which
    would make a parallel pass disagree with itself. blake2b is stable across runs,
    processes and machines.
    """
    digest = hashlib.blake2b(key.encode("ascii"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % buckets


@dataclass(frozen=True)
class ScanConfig:
    """What a worker needs to reduce a batch of entries without shipping them back.

    The point of the parallel path is that the corpus does not make the return trip:
    workers see raw entry blocks and send back only the viral-seeded clusters, the
    sampled ones, and counts — on UniRef100 that is a few percent of what went out.
    Shipping parsed entries back instead would move the bottleneck to the pipe.

    `viral` is the expensive member and is sent once per worker at pool start, not once
    per batch.
    """

    viral: frozenset[int]
    sample_rate: int = 0
    buckets: int = 1

    def scan(self, blocks: Iterable[bytes]) -> BatchResult:
        result = BatchResult()
        for block in blocks:
            entry = _parse_entry(block)
            if entry is None:
                continue
            if result.counts.observe(entry, self.viral):  # type: ignore[arg-type]
                result.seeds.append((entry.cluster_id, entry.sequence))
            if self.sample_rate and bucket_of(entry.cluster_id, self.sample_rate) == 0:
                shard = bucket_of(entry.cluster_id + "#shard", self.buckets)
                result.samples.append((shard, entry.cluster_id, entry.sequence))
        return result


@dataclass
class BatchResult:
    """One batch's reduction: counts, the seeds it found, and the sample it drew."""

    counts: SeedCounts = field(default_factory=SeedCounts)
    seeds: list[tuple[str, str]] = field(default_factory=list)
    samples: list[tuple[int, str, str]] = field(default_factory=list)


def iter_entry_blocks(chunks: Iterable[bytes], batch_bytes: int = 8 << 20) -> Iterator[list[bytes]]:
    """Split a decompressed stream into batches of raw entry blocks.

    Same splitting as `iter_entries`, including the trailing block, so the serial and
    parallel paths see exactly the same entries — which is what makes them testable
    against each other rather than merely similar.
    """
    pending = b""
    batch: list[bytes] = []
    size = 0
    for chunk in chunks:
        parts = (pending + chunk).split(_ENTRY_END)
        pending = parts.pop()
        for part in parts:
            batch.append(part)
            size += len(part)
            if size >= batch_bytes:
                yield batch
                batch, size = [], 0
    if pending:
        batch.append(pending)
    if batch:
        yield batch


_WORKER_CONFIG: ScanConfig | None = None


def _init_worker(config: ScanConfig) -> None:
    global _WORKER_CONFIG
    _WORKER_CONFIG = config


def _scan_batch(blocks: list[bytes]) -> BatchResult:
    assert _WORKER_CONFIG is not None, "worker started without a config"
    return _WORKER_CONFIG.scan(blocks)


def scan_parallel(
    chunks: Iterable[bytes],
    config: ScanConfig,
    *,
    workers: int,
    batch_bytes: int = 8 << 20,
    max_in_flight: int | None = None,
) -> Iterator[BatchResult]:
    """Parse entries across worker processes, yielding batch reductions **in order**.

    Decompression stays in the calling process because a gzip stream cannot be split;
    measured, it runs at about 218 MB/s and is not the bottleneck. The per-entry matching
    is, at roughly four times the cost of the decompression feeding it, and it is
    embarrassingly parallel — so that is what moves.

    Two properties this has to keep, or the parallel path is not the same pass:

    * **Order.** Batches are yielded in the order they were read, so the seed set and the
      shards come out byte-identical to the serial path. A result that depends on how the
      scheduler interleaved workers is not reproducible, whatever its contents.
    * **Bounded memory.** Submission is throttled to `max_in_flight` batches. The obvious
      `executor.map` submits the whole iterable immediately, which against a 706 GB stream
      means reading all of it into memory as fast as the decompressor can go.
    """
    if workers <= 1:
        for batch in iter_entry_blocks(chunks, batch_bytes):
            yield config.scan(batch)
        return

    limit = max_in_flight if max_in_flight is not None else workers * 2
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(config,)
    ) as pool:
        pending: deque = deque()
        for batch in iter_entry_blocks(chunks, batch_bytes):
            pending.append(pool.submit(_scan_batch, batch))
            if len(pending) >= limit:
                yield pending.popleft().result()
        while pending:
            yield pending.popleft().result()

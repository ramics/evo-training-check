"""How much of the viral seed set has cellular homologues, at the publisher's own identities.

ESM3-open's viral denylist has two clauses: a sequence qualifies if it is (a) annotated as
viral in UniProt **and** (b) "align[s] almost exclusively to other viral sequences in
UniProt". D-015 fixed the readings on this point and D-156 settled what follows: the strict
reading deliberately drops clause (b), so the annotation-only seed set in `seeds.py` is the
strict reading's own seed set rather than a defective charitable one, and quantifying "almost
exclusively" would invent the number the specs declined to invent.

This module measures something narrower and answerable: **how much of that seed set has
cellular homologues anyway.** UniRef90 and UniRef50 are the publisher's own homology
groupings at 90% and 50% identity, staged for 2023_02 beside the UniRef100 tier the seed set
was built from. For each seed, the question is whether the cluster containing it, at each of
those two identities, holds any non-viral member.

**It is not clause (b), and nothing here may be labelled as it.** Clause (b) conditions on
alignment against the whole of UniProt; cluster co-membership is a proxy at two fixed
identities. The output bounds how much of a survival figure is *exposed* to the dropped
clause. It does not correct the figure and no corrected figure is to be derived from it
(D-158).

**Why the workers only need the viral taxid set.** UniRef is strictly hierarchical — every
member of a UniRef100 cluster sits in the same UniRef90 cluster, and likewise at 50% — so the
cluster containing a seed also contains that seed's viral member. Emitting a row for every
member whose own taxid is viral therefore reaches every seed without any worker holding the
3.16M-id seed set, and the join happens once, afterwards, against the staged seed FASTA. The
alternative — shipping the seed set to each of seven workers — costs a few hundred megabytes
per worker to answer the same question.

**Three facts about the staged XML, read from the bytes rather than assumed** (D-158; this
task has been bitten three times by a field whose meaning was taken on trust):

* Every member and representative in **both** tiers carries a `UniRef100 ID` property and an
  `NCBI taxonomy` property, so each tier joins to the seed set directly and neither tier has
  to be reconstructed from the other.
* The `member count` property **includes** the representative, so counting `<member>`
  elements alone is short by one per cluster.
* `uniref.xsd` cannot settle either point: properties are generic `type`/`value` pairs there.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from amazebio.seeds import VIRAL_ROOT

__all__ = [
    "EXCLUSIVE",
    "NON_EXCLUSIVE",
    "UNDETERMINED",
    "VERDICTS",
    "VIRAL_ROOT",
    "ClusterReduction",
    "ExclusivityConfig",
    "ExclusivityCounts",
    "ExclusivityResult",
    "Tally",
    "cluster_rows",
    "iter_member_blocks",
]

#: A seed whose containing cluster holds only viral members at this identity.
EXCLUSIVE = "exclusive"
#: A seed whose containing cluster holds at least one non-viral member — a cellular
#: homologue at this identity, and so material clause (b) would plausibly have dropped.
NON_EXCLUSIVE = "non_exclusive"
#: A seed whose containing cluster yields no placed taxid at all, so the question cannot be
#: answered for it. Counted and reported as its own share rather than folded into either
#: other verdict (D-158, and D-152's lesson one level down).
UNDETERMINED = "undetermined"

#: Reporting order. Fixed here so every artefact and table lists the three the same way.
VERDICTS: tuple[str, ...] = (EXCLUSIVE, NON_EXCLUSIVE, UNDETERMINED)

#: Each member and representative holds exactly one `<dbReference>`, so splitting a cluster
#: block on the opening tag yields one piece per member — with the text before the first
#: occurrence being the entry's own `<name>` and `<property>` elements, which carry a
#: `common taxon ID` rather than an `NCBI taxonomy` and so contribute no member taxid.
_DBREF_OPEN = b"<dbReference"

#: Anchored on the property type, because the 50 tier also carries a `UniRef90 ID` and the 90
#: tier a `UniRef50 ID`; an unanchored id match would pick up whichever came first.
_UNIREF100_ID = re.compile(rb'type="UniRef100 ID" value="(UniRef100_[^"]+)"')
_NCBI_TAXONOMY = re.compile(rb'type="NCBI taxonomy" value="(\d+)"')
_ENTRY_ID = re.compile(rb'<entry id="([^"]+)"')


def iter_member_blocks(block: bytes) -> list[bytes]:
    """Split one cluster block into its per-member `<dbReference>` pieces.

    The leading piece — everything before the first `<dbReference` — is dropped. It holds
    the entry-level properties, whose `common taxon ID` is a *summary* of the members rather
    than a member of its own; counting it as one would make a mixed cluster look as though
    it had an extra member at the common ancestor's taxid.
    """
    pieces = block.split(_DBREF_OPEN)
    return pieces[1:]


@dataclass(frozen=True)
class ClusterReduction:
    """What one cluster block says: whether any member is placed, and about which seeds.

    `verdict` is `None` exactly when the cluster covers no viral member, which is the
    overwhelming majority of clusters and the reason this pass returns a small fraction of
    what it reads.

    There is deliberately no cluster-level `UNDETERMINED`. A cluster with no placed taxid
    cannot have a *viral* member either, so it can never carry a verdict about a seed;
    `UNDETERMINED` is a seed-level outcome, reached in `Tally` when no row was ever emitted
    for that seed. `placed` is still recorded, because the share of wholly unplaced clusters
    is worth reporting on its own (D-158).
    """

    placed: int
    verdict: str | None
    viral_ids: tuple[str, ...]


def cluster_rows(block: bytes, viral: frozenset[int]) -> ClusterReduction | None:
    """Reduce one cluster block, or `None` if the block is not an entry at all.

    The verdict is a property of the **whole** cluster, so it is computed over every member's
    taxid and then attached to each viral member's id. Two members of one cluster can map to
    the same UniRef100 id; de-duplication is left to the caller, which is already holding a
    set to join against the seed FASTA.
    """
    if _ENTRY_ID.search(block) is None:
        return None

    viral_ids: list[str] = []
    placed = 0
    non_viral = 0
    for piece in iter_member_blocks(block):
        taxon = _NCBI_TAXONOMY.search(piece)
        if taxon is None:
            # A member with no placed taxid cannot make the cluster non-exclusive and cannot
            # be a viral seed, so it contributes nothing but is not itself an unknown.
            continue
        placed += 1
        if int(taxon.group(1)) in viral:
            ident = _UNIREF100_ID.search(piece)
            if ident is not None:
                viral_ids.append(ident.group(1).decode("ascii", "replace"))
        else:
            non_viral += 1

    if not viral_ids:
        return ClusterReduction(placed=placed, verdict=None, viral_ids=())
    return ClusterReduction(
        placed=placed,
        verdict=NON_EXCLUSIVE if non_viral else EXCLUSIVE,
        viral_ids=tuple(viral_ids),
    )


@dataclass
class ExclusivityCounts:
    """Whole-tier counts, kept beside the rows so the pass describes what it read.

    These are over *clusters of the tier being read*, not over seeds — the seed-side shares
    need the join and are computed by `Tally`. Both are reported: a tier-level share says
    whether the hit-producing seeds are unusual among the rest (D-158).
    """

    clusters: int = 0
    unplaced_clusters: int = 0
    viral_covering: int = 0
    exclusive: int = 0
    non_exclusive: int = 0

    def observe(self, reduction: ClusterReduction) -> None:
        self.clusters += 1
        if reduction.placed == 0:
            self.unplaced_clusters += 1
        if reduction.verdict is None:
            return
        self.viral_covering += 1
        if reduction.verdict == EXCLUSIVE:
            self.exclusive += 1
        else:
            self.non_exclusive += 1

    def merge(self, other: ExclusivityCounts) -> None:
        self.clusters += other.clusters
        self.unplaced_clusters += other.unplaced_clusters
        self.viral_covering += other.viral_covering
        self.exclusive += other.exclusive
        self.non_exclusive += other.non_exclusive

    def to_dict(self) -> dict[str, int | float | None]:
        covering = self.viral_covering
        return {
            "clusters": self.clusters,
            "unplaced_clusters": self.unplaced_clusters,
            "viral_covering": covering,
            "exclusive": self.exclusive,
            "non_exclusive": self.non_exclusive,
            "non_exclusive_share": (self.non_exclusive / covering if covering else None),
        }


@dataclass
class ExclusivityResult:
    """One batch's reduction: counts, and `(uniref100_id, verdict)` for viral members."""

    counts: ExclusivityCounts = field(default_factory=ExclusivityCounts)
    rows: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ExclusivityConfig:
    """What a worker needs, which is only the viral taxid set.

    Deliberately the same shape as `seeds.ScanConfig` — a frozen config with a `scan` method
    over raw entry blocks — so `seeds.scan_parallel` drives this pass unchanged rather than
    the project carrying two parallel-pass implementations that can drift apart.
    """

    viral: frozenset[int]

    def scan(self, blocks: Iterable[bytes]) -> ExclusivityResult:
        result = ExclusivityResult()
        for block in blocks:
            reduced = cluster_rows(block, self.viral)
            if reduced is None:
                continue
            result.counts.observe(reduced)
            if reduced.verdict is not None:
                result.rows.extend((ident, reduced.verdict) for ident in reduced.viral_ids)
        return result


@dataclass
class Tally:
    """Seed-side shares: the verdict for each seed of a named set, at one identity.

    The denominator is the seed set handed in, not the rows observed, because a seed the pass
    never emitted a row for is still a seed — it is `UNDETERMINED`, and silently dropping it
    would shrink the denominator and flatter the share. D-158 fixes that both denominators
    are reported, so the caller builds one `Tally` per seed set: all realised sample seeds,
    and the subset that produced a hit record.
    """

    name: str
    tier: str
    verdicts: dict[str, str] = field(default_factory=dict)

    def observe(self, uniref100_id: str, verdict: str) -> None:
        """Record one row, keeping the stronger claim when a seed is seen twice.

        A seed can be reached through more than one viral member, and the members can sit in
        different clusters only if the release's hierarchy is violated — but the pass does
        not assume it holds. `NON_EXCLUSIVE` wins over `EXCLUSIVE`, which wins over
        `UNDETERMINED`: a cellular homologue found by any route is a cellular homologue, and
        resolving a tie the other way would let the order of the stream decide the result.
        """
        current = self.verdicts.get(uniref100_id)
        if current is None or _PRECEDENCE[verdict] > _PRECEDENCE[current]:
            self.verdicts[uniref100_id] = verdict

    def summarise(self, seeds: Iterable[str]) -> dict[str, object]:
        counts = dict.fromkeys(VERDICTS, 0)
        total = 0
        for seed in seeds:
            total += 1
            counts[self.verdicts.get(seed, UNDETERMINED)] += 1
        return {
            "set": self.name,
            "tier": self.tier,
            "seeds": total,
            "counts": counts,
            "non_exclusive_share": (counts[NON_EXCLUSIVE] / total if total else None),
            "undetermined_share": (counts[UNDETERMINED] / total if total else None),
        }


#: `observe` keeps the strongest claim seen for a seed; this is what "strongest" means.
_PRECEDENCE = {UNDETERMINED: 0, EXCLUSIVE: 1, NON_EXCLUSIVE: 2}

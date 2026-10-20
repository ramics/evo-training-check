"""Do the two filters mean the same thing by "viral"? — task A8.1, DESIGN.md §A8.

Both filters under audit claim to remove viral sequence, by different machines: Evo's is a
list of taxon names applied to records a virus database has already labelled, ESM3-open's is
an alignment against a seed set. §A8 asks what happens when both are applied to the same
records, because if the answer is "different things" then "we filtered viral data" does not
denote a definite operation.

**The common corpus is UniRef100 of the pinned release, read through UniRef90 and UniRef50.**
That choice is what makes the pass affordable and it is also what bounds the claim. Three
things follow from it and each is carried in the artefact rather than left to the write-up.

**1. The similarity side is cluster co-membership, not an alignment we ran.** UniRef90 and
UniRef50 are the publisher's own homology groupings at 90% and 50% identity over exactly
these records. A record whose cluster holds a seed is within that identity of a seed, so the
similarity predicate removes it. This is the same proxy `exclusivity.py` uses for a different
question, and it has the same limit: it is co-membership at a fixed identity, not ESM3's
alignment against the whole of UniProt. What it buys is a threshold that is the publisher's
rather than ours — ESM3's own threshold is unpublished (D-015), and A1.6's banded curve is
the sweep over *our* stated range. Both are reported; neither is presented as the other.

**2. Only part of Evo's pipeline can run here.** Four of its six rules read IMG/VR metadata —
a confidence label, a vOTU, a host count — that a protein corpus does not have. The two taxon
rules and the taxonomic-specificity rule are the whole of what a protein record can be judged
by, and `LabelPredicate.rules_not_runnable` names the rest so the artefact says what was left
out rather than implying the pipeline ran.

**3. A non-viral record is not a retained record.** Evo's filter runs over a virus database:
every record it sees is already asserted to be viral, and the taxon rules say nothing at all
about a bacterial protein. Scoring one as "retained by the label filter" would manufacture
agreement out of a question that was never asked. So the label side has three states — removed,
retained, out of scope — and the cross-tab is 3x2, not 2x2. This is `survival.py`'s
`out_of_scope` route one corpus over.

**What the pass can prove before it runs, and why it runs anyway.** Every record Evo's taxon
rules remove is viral by NCBI taxonomy, and the strict reading's seed set is every
viral-annotated record (D-156), so such a record is itself a seed and its own cluster covers
it. `label_only` is therefore empty by construction, and `check_dominance` asserts it rather
than hoping. The disagreement is one-sided and the measurement is of its size and its
composition: how much material the similarity filter removes that no taxon rule would reach,
split by whether it is viral at all.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from amazebio.exclusivity import iter_member_blocks
from amazebio.seeds import VIRAL_ROOT

__all__ = [
    "CELLS",
    "CELL_BOTH",
    "CELL_LABEL_ONLY",
    "CELL_NEITHER",
    "CELL_OUT_OF_SCOPE",
    "CELL_OUT_OF_SCOPE_REMOVED",
    "CELL_SIMILARITY_ONLY",
    "KINDS",
    "LABEL_RANKS",
    "AgreementConfig",
    "AgreementCounts",
    "ClusterAgreement",
    "LabelPredicate",
    "build_predicate",
    "check_dominance",
    "reduce_cluster",
]

#: Both filters remove the record.
CELL_BOTH = "both"
#: The label rules remove it and the similarity predicate does not.
CELL_LABEL_ONLY = "label_only"
#: The similarity predicate removes it and the label rules, having seen it, do not.
CELL_SIMILARITY_ONLY = "similarity_only"
#: Neither removes it, the label rules having seen it.
CELL_NEITHER = "neither"
#: The label rules were never in a position to judge it: it is not viral, so Evo's filter —
#: which runs over a virus database — would never have been handed it. Reported as its own
#: cell and never folded into `neither`, which would read as agreement.
CELL_OUT_OF_SCOPE = "out_of_scope_kept"
#: Out of the label filter's scope and removed by the similarity filter anyway: a record the
#: taxonomy does not call viral, sitting within the tier's identity of something it does.
#: Split from `out_of_scope_kept` because this cell is the collateral the similarity
#: mechanism takes and the other cell is the corpus it leaves alone; one number pooling both
#: would answer neither question.
CELL_OUT_OF_SCOPE_REMOVED = "out_of_scope_removed"

#: Reporting order, fixed so every artefact and table lists the cells the same way.
CELLS: tuple[str, ...] = (
    CELL_BOTH,
    CELL_LABEL_ONLY,
    CELL_SIMILARITY_ONLY,
    CELL_NEITHER,
    CELL_OUT_OF_SCOPE_REMOVED,
    CELL_OUT_OF_SCOPE,
)

#: What kind of sequence a record is, independent of either verdict. §A8's third step asks
#: what falls in the gap, and this is the axis that answers it.
KIND_VIRAL_DENYLISTED = "viral_denylisted"
KIND_VIRAL_UNSPECIFIC = "viral_unspecific"
KIND_VIRAL_OTHER = "viral_other"
KIND_CELLULAR = "cellular"
KIND_UNPLACED = "unplaced"
KINDS: tuple[str, ...] = (
    KIND_VIRAL_DENYLISTED,
    KIND_VIRAL_UNSPECIFIC,
    KIND_VIRAL_OTHER,
    KIND_CELLULAR,
    KIND_UNPLACED,
)

#: Which of the two taxon rules reached a removed record. A removal on `order` alone is a
#: coarser claim than one on `family`, and A4.4 found that distinction carries two thirds of
#: one filter's removals, so it is never collapsed here either.
LABEL_RANKS: tuple[str, ...] = ("family", "order", "unspecific")

_NCBI_TAXONOMY = re.compile(rb'type="NCBI taxonomy" value="(\d+)"')
_ENTRY_ID = re.compile(rb'<entry id="([^"]+)"')


@dataclass(frozen=True)
class LabelPredicate:
    """Evo's taxon rules as a verdict on one taxid, with what it cannot run declared.

    Built once, in the parent process, from a policy spec and the pinned taxonomy; shipped to
    the workers as plain frozensets because a worker that had to climb a lineage per member
    would pay for the climb a quarter of a billion times.

    `by_family` and `by_order` are each the full descendant closure of that rule's named
    taxa, so membership is one hash lookup. They can overlap — a family sits inside an order —
    and `rank_of` resolves that the way the rules themselves do: the family rule is the more
    specific claim, so it is reported as the reason.
    """

    viral: frozenset[int]
    by_family: frozenset[int]
    by_order: frozenset[int]
    unspecific: frozenset[int]
    family_names: tuple[str, ...] = ()
    order_names: tuple[str, ...] = ()
    rules_not_runnable: tuple[tuple[str, str], ...] = ()

    @property
    def removed(self) -> frozenset[int]:
        return self.by_family | self.by_order | self.unspecific

    def kind_of(self, taxid: int | None) -> str:
        """What the record is, before any verdict."""
        if taxid is None:
            return KIND_UNPLACED
        if taxid not in self.viral:
            return KIND_CELLULAR
        if taxid in self.by_family or taxid in self.by_order:
            return KIND_VIRAL_DENYLISTED
        if taxid in self.unspecific:
            return KIND_VIRAL_UNSPECIFIC
        return KIND_VIRAL_OTHER

    def rank_of(self, taxid: int) -> str | None:
        """Which rule removed it, or `None` if none did."""
        if taxid in self.by_family:
            return "family"
        if taxid in self.by_order:
            return "order"
        if taxid in self.unspecific:
            return "unspecific"
        return None


def _taxid(piece: bytes) -> int | None:
    found = _NCBI_TAXONOMY.search(piece)
    return int(found.group(1)) if found is not None else None


@dataclass(frozen=True)
class ClusterAgreement:
    """One cluster's contribution: whether it covers a seed, and its members' taxids.

    Kept as a reduction rather than a row per member because the deliverable is a table of
    counts and the corpus has a quarter of a billion members. `covers_seed` is a property of
    the whole cluster and has to be known before any member can be scored, which is why the
    reduction is per cluster and not per member.
    """

    covers_seed: bool
    taxids: tuple[int | None, ...]


def reduce_cluster(block: bytes, viral: frozenset[int]) -> ClusterAgreement | None:
    """Read one cluster block, or `None` if it is not an entry at all.

    The seed set is every viral-annotated record (the strict reading, D-156), so a cluster
    covers a seed exactly when one of its members carries a viral taxid. That is the same
    test `exclusivity.cluster_rows` makes, for the opposite purpose: there it asks what else
    is in a seed's cluster, here it asks what a seed's cluster drags in.
    """
    if _ENTRY_ID.search(block) is None:
        return None
    taxids = tuple(_taxid(piece) for piece in iter_member_blocks(block))
    covers = any(t is not None and t in viral for t in taxids)
    return ClusterAgreement(covers_seed=covers, taxids=taxids)


@dataclass
class AgreementCounts:
    """The cross-tab, and the two breakdowns §A8 asks for.

    `cells` is the headline. `kind_by_cell` is what kind of sequence falls in each cell, which
    is the third step of §A8 and the only part that says anything about *what* the two filters
    disagree about. `rank_by_cell` records which taxon rule reached a label removal, kept
    separate because a removal on an order is a coarser claim than one on a family.
    """

    clusters: int = 0
    covering_clusters: int = 0
    members: int = 0
    cells: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CELLS, 0))
    kind_by_cell: dict[str, dict[str, int]] = field(
        default_factory=lambda: {c: dict.fromkeys(KINDS, 0) for c in CELLS}
    )
    rank_by_cell: dict[str, dict[str, int]] = field(
        default_factory=lambda: {c: dict.fromkeys(LABEL_RANKS, 0) for c in CELLS}
    )

    def observe(self, reduction: ClusterAgreement, predicate: LabelPredicate) -> None:
        self.clusters += 1
        if reduction.covers_seed:
            self.covering_clusters += 1
        for taxid in reduction.taxids:
            self.members += 1
            kind = predicate.kind_of(taxid)
            rank = None if taxid is None else predicate.rank_of(taxid)
            if kind in (KIND_CELLULAR, KIND_UNPLACED):
                # Evo's filter never sees it, so it has no verdict to agree or disagree with.
                cell = CELL_OUT_OF_SCOPE_REMOVED if reduction.covers_seed else CELL_OUT_OF_SCOPE
            elif rank is not None:
                cell = CELL_BOTH if reduction.covers_seed else CELL_LABEL_ONLY
            else:
                cell = CELL_SIMILARITY_ONLY if reduction.covers_seed else CELL_NEITHER
            self.cells[cell] += 1
            self.kind_by_cell[cell][kind] += 1
            if rank is not None:
                self.rank_by_cell[cell][rank] += 1

    def merge(self, other: AgreementCounts) -> None:
        self.clusters += other.clusters
        self.covering_clusters += other.covering_clusters
        self.members += other.members
        for cell in CELLS:
            self.cells[cell] += other.cells[cell]
            for kind in KINDS:
                self.kind_by_cell[cell][kind] += other.kind_by_cell[cell][kind]
            for rank in LABEL_RANKS:
                self.rank_by_cell[cell][rank] += other.rank_by_cell[cell][rank]

    def to_dict(self) -> dict[str, object]:
        out_of_scope = self.cells[CELL_OUT_OF_SCOPE] + self.cells[CELL_OUT_OF_SCOPE_REMOVED]
        judged = self.members - out_of_scope
        agreed = self.cells[CELL_BOTH] + self.cells[CELL_NEITHER]
        return {
            "clusters": self.clusters,
            "covering_clusters": self.covering_clusters,
            "members": self.members,
            "cells": dict(self.cells),
            "out_of_scope_members": out_of_scope,
            "judged_members": judged,
            "agreement": (agreed / judged if judged else None),
            "kind_by_cell": {c: dict(self.kind_by_cell[c]) for c in CELLS},
            "rank_by_cell": {c: dict(self.rank_by_cell[c]) for c in CELLS},
        }


def check_dominance(counts: AgreementCounts) -> None:
    """Refuse a result where the label filter removed something the similarity filter did not.

    Not a sanity check on arithmetic — it is the structural claim this task rests on. Evo's
    taxon rules only ever fire on a viral-annotated record, and every viral-annotated record
    is a seed under the reading in force, so such a record's own cluster covers a seed. A
    non-empty `label_only` means one of those three premises is false — the seed set is not
    annotation-only, the tier's hierarchy does not hold, or a denylisted taxon is not under
    the viral root — and each of those changes what the number means. Better to stop than to
    publish a one-sided table with an unexplained cell in it.
    """
    stray = counts.cells[CELL_LABEL_ONLY]
    if stray:
        raise ValueError(
            f"{stray:,} records were removed by the taxon rules but sit in no cluster with a "
            "seed; under an annotation-only seed set that is impossible, so either the seed "
            "set, the tier hierarchy or the denylist closure is not what this pass assumed"
        )


@dataclass(frozen=True)
class AgreementConfig:
    """What a worker needs. Shaped like `seeds.ScanConfig` so `seeds.scan_parallel` drives it.

    The whole predicate travels to each worker, which is a few million ints rather than the
    seed FASTA's gigabyte; the alternative — climbing each member's lineage in the worker —
    does the same ancestry walk once per member instead of once per taxid.
    """

    predicate: LabelPredicate

    def scan(self, blocks: Iterable[bytes]) -> AgreementCounts:
        counts = AgreementCounts()
        for block in blocks:
            reduced = reduce_cluster(block, self.predicate.viral)
            if reduced is None:
                continue
            counts.observe(reduced, self.predicate)
        return counts


def build_predicate(
    *,
    taxonomy: object,
    names: Mapping[int, str],
    family_names: Sequence[str],
    order_names: Sequence[str],
    stop_taxa: Sequence[str],
    require_rank: str,
    ranks: Sequence[str],
    rules_not_runnable: Sequence[tuple[str, str]] = (),
) -> LabelPredicate:
    """Close the rules' named taxa over the pinned taxonomy.

    `taxonomy` is an `amazebio.seeds.Taxonomy`, typed loosely for the same reason
    `exclusivity.FamilyIndex.build` does it: the predicate's logic is testable on synthetic
    taxa and should not drag a taxdump into the test suite.

    A name the taxonomy does not carry is an error, not a zero. The eight stop taxa and the
    thirty-one families and orders are a static enumeration against a taxonomy that keeps
    moving — that decay is what A9.1 measures — and a silently-dropped name would show up
    here as a filter that removes less, which is a finding about the filter rather than about
    the dump.
    """
    index: dict[str, list[int]] = {}
    for taxid, name in names.items():
        index.setdefault(name, []).append(taxid)

    def close(wanted: Sequence[str], what: str) -> frozenset[int]:
        out: set[int] = set()
        for name in wanted:
            hits = index.get(name)
            if not hits:
                raise ValueError(
                    f"{what} {name!r} is not a scientific name in the pinned taxonomy; a "
                    "rule whose taxon has been renamed removes nothing and must not be "
                    "scored as removing nothing by accident"
                )
            for taxid in hits:
                out |= taxonomy.descendants(taxid)  # type: ignore[attr-defined]
        return frozenset(out)

    viral = frozenset(taxonomy.descendants(VIRAL_ROOT))  # type: ignore[attr-defined]
    by_family = close(family_names, "denylisted family") & viral
    by_order = close(order_names, "denylisted order") & viral

    # The stop taxa are matched as *assignments*, not as clades. "only assigned up to the
    # level of Riboviria" means the record sits at Riboviria and nowhere finer; closing the
    # eight over their descendants would make almost every RNA virus unspecific, which is the
    # opposite of what the rule says. `policyspec.decide` resolves it by finest assigned rank
    # and this reproduces that, one taxid at a time rather than one record at a time.
    stop_names = set(stop_taxa)
    for name in stop_names:
        if name not in index:
            raise ValueError(f"stop taxon {name!r} is not a scientific name in the taxonomy")
    parent = taxonomy.parent  # type: ignore[attr-defined]
    rank_of = taxonomy.rank  # type: ignore[attr-defined]
    order = {rank: i for i, rank in enumerate(ranks)}
    unspecific: set[int] = set()
    for taxid in viral:
        # One climb per taxid, not one per rank: the lineage is the same walk eight times
        # over, and at this many taxa that is the difference between seconds and minutes.
        node, seen, finest, best, has_required = taxid, set(), None, -1, False
        while node not in seen:
            seen.add(node)
            rank = rank_of.get(node)
            if rank == require_rank:
                has_required = True
            place = order.get(rank)
            if place is not None and place > best:
                best, finest = place, node
            par = parent.get(node)
            if par is None or par == node:
                break
            node = par
        if not has_required or (finest is not None and names.get(finest) in stop_names):
            unspecific.add(taxid)
    return LabelPredicate(
        viral=viral,
        by_family=by_family,
        by_order=by_order,
        unspecific=frozenset(unspecific) - by_family - by_order,
        family_names=tuple(family_names),
        order_names=tuple(order_names),
        rules_not_runnable=tuple(rules_not_runnable),
    )

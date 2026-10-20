"""Does a filter written as a list of names have a shelf life? — task A9.1, DESIGN.md §A9.

Evo's exclusion is nineteen family names and twelve order names, written once and applied
ever since. The taxonomy those names index is not fixed: families are erected, split,
renamed and moved, and every one of those events changes what the same sentence removes
without anyone editing the sentence. §A9 asks how fast that happens and what re-validation
interval it implies.

**The separation that makes the number honest.** A taxon renamed from one word to another
moves no sequence: the records are where they were and a filter that no longer names them is
failing on the same material it always covered. A family erected for genuinely new material
is different — the filter never covered it. Both show up as "the list reaches a smaller share
of the viral taxonomy", and pooling them would let a busy quarter at the ICTV masquerade as
leakage. So this module counts them apart and never adds them, which D-201 fixes before any
of it is run.

**What a release is reduced to.** Twenty-eight dumps cannot be held at once — each is about
2.5 million nodes — so each is parsed, compared against the baseline, and reduced to one
small :class:`Measurement` before the next is opened. The baseline keeps only what the
comparison needs: every taxid it knew, and the name and rank of the viral ones.

**What this cannot measure, and says so.** §A9's "in scope by the policy's stated intent"
means eukaryote-infecting, and NCBI carries no host. The replay measures what the names reach
against what the taxonomy holds. The host-conditioned question belongs to the charitable
reading's own host rule and is named as unanswered rather than approximated (D-201).
"""

from __future__ import annotations

import dataclasses
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from amazebio.seeds import VIRAL_ROOT

__all__ = [
    "Baseline",
    "Measurement",
    "Release",
    "measure",
    "reach_of",
]


@dataclasses.dataclass(frozen=True, slots=True)
class Release:
    """One dated dump, parsed far enough to answer A9.1 and no further.

    `merged` is why a rename and a deletion can be told apart at all: NCBI retires a taxid by
    pointing it at its successor, so a taxon that looks absent is often present under another
    number. Reading `nodes.dmp` without it would report every merge as lost diversity.
    """

    date: str
    names: dict[int, str]
    parent: dict[int, int]
    rank: dict[int, str]
    merged: dict[int, int]
    synonyms: dict[str, tuple[int, ...]]

    @classmethod
    def from_zip(cls, path: str | Path, date: str) -> Release:
        names: dict[int, str] = {}
        synonyms: dict[str, list[int]] = {}
        parent: dict[int, int] = {}
        rank: dict[int, str] = {}
        merged: dict[int, int] = {}
        with zipfile.ZipFile(path) as archive:
            with archive.open("names.dmp") as handle:
                for raw in handle:
                    f = [c.strip() for c in raw.decode("utf-8", "replace").split("\t|")]
                    if len(f) < 4:
                        continue
                    try:
                        taxid = int(f[0])
                    except ValueError:
                        continue
                    if f[3] == "scientific name":
                        names[taxid] = f[1]
                    else:
                        synonyms.setdefault(f[1], []).append(taxid)
            with archive.open("nodes.dmp") as handle:
                for raw in handle:
                    f = raw.decode("utf-8", "replace").split("\t|\t", 3)
                    if len(f) < 3:
                        continue
                    try:
                        taxid, par = int(f[0]), int(f[1])
                    except ValueError:
                        continue
                    parent[taxid] = par
                    rank[taxid] = f[2].split("\t|", 1)[0].strip()
            # `merged.dmp` is absent from a handful of the oldest archived dumps. Its absence
            # means no merges can be resolved, which overstates loss — so it is recorded as
            # empty rather than assumed, and `measure` reports whether it was there.
            if "merged.dmp" in archive.namelist():
                with archive.open("merged.dmp") as handle:
                    for raw in handle:
                        f = [c.strip() for c in raw.decode("utf-8", "replace").split("\t|")]
                        if len(f) < 2:
                            continue
                        try:
                            merged[int(f[0])] = int(f[1])
                        except ValueError:
                            continue
        return cls(
            date=date,
            names=names,
            parent=parent,
            rank=rank,
            merged=merged,
            synonyms={k: tuple(v) for k, v in synonyms.items()},
        )

    def descendants(self, root: int) -> set[int]:
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

    def viral(self) -> frozenset[int]:
        return frozenset(self.descendants(VIRAL_ROOT))

    def resolve(self, taxid: int) -> int:
        """Follow `merged.dmp` to the taxid this one became, if it became another."""
        seen: set[int] = set()
        while taxid in self.merged and taxid not in seen:
            seen.add(taxid)
            taxid = self.merged[taxid]
        return taxid

    def has_ancestor_in(self, taxid: int, roots: frozenset[int]) -> bool:
        node, seen = taxid, set()
        while node not in seen:
            seen.add(node)
            if node in roots:
                return True
            par = self.parent.get(node)
            if par is None or par == node:
                return False
            node = par
        return False


def reach_of(
    release: Release,
    *,
    viral: frozenset[int],
    named: Mapping[str, Sequence[str]],
) -> tuple[frozenset[int], tuple[tuple[str, str], ...]]:
    """What the frozen names resolve to in this release, and which of them do not.

    `named` maps a declared rank to the names the rule gives at it. A name is only counted
    where the release carries it as a scientific name **at that rank**: that is the rule read
    as written, and it is how `Reoviridae` — a family name that is now a synonym of an order
    — registers as unreachable rather than as a silent zero (D-199).
    """
    index: dict[str, list[int]] = {}
    for taxid, name in release.names.items():
        index.setdefault(name, []).append(taxid)

    out: set[int] = set()
    unreachable: list[tuple[str, str]] = []
    for rank, wanted in named.items():
        for name in wanted:
            hits = [t for t in index.get(name, ()) if release.rank.get(t) == rank]
            if not hits:
                # Three distinct ways a name stops working, and they are not the same
                # failure: a name the release has never heard of, a name it carries at
                # another rank, and a name it has demoted to a synonym of a taxon that may
                # well still be at the right rank. The last is the one that reads as
                # harmless and is not — `Herpesviridae` is in it by 2026.
                scientific = index.get(name)
                if scientific:
                    why = f"a {release.rank.get(scientific[0], 'no rank')}, not a {rank}"
                elif synonym_of := release.synonyms.get(name):
                    target = release.names.get(synonym_of[0], "an unnamed taxon")
                    found = release.rank.get(synonym_of[0], "no rank")
                    why = f"no longer a name of its own: a synonym of {target}, a {found}"
                else:
                    why = "absent from this release"
                unreachable.append((name, why))
                continue
            for taxid in hits:
                out |= release.descendants(taxid)
    return frozenset(out) & viral, tuple(unreachable)


@dataclasses.dataclass(frozen=True, slots=True)
class Baseline:
    """What the comparison needs from the release the denylist was written against.

    Deliberately not a whole :class:`Release`: twenty-eight of those will not fit at once, and
    all a later release is asked is whether it has taxa this one never had, and whether the
    ones it shares have been renamed or re-ranked under it.
    """

    date: str
    all_taxids: frozenset[int]
    viral: frozenset[int]
    name: Mapping[int, str]
    rank: Mapping[int, str]

    @classmethod
    def of(cls, release: Release) -> Baseline:
        viral = release.viral()
        return cls(
            date=release.date,
            all_taxids=frozenset(release.parent),
            viral=viral,
            name={t: release.names.get(t, "") for t in viral},
            rank={t: release.rank.get(t, "") for t in viral},
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Measurement:
    """One release's answer. Every field is a count of taxa, never of records."""

    date: str
    viral_taxa: int
    reach: int
    unreachable_names: tuple[tuple[str, str], ...]
    new_not_named: int
    new_named: int
    renumbered: int
    reassigned_into_viral: int
    renamed: int
    reranked: int
    computed_rule_reach: int
    has_merged_dmp: bool

    @property
    def reach_share(self) -> float | None:
        return self.reach / self.viral_taxa if self.viral_taxa else None

    @property
    def computed_share(self) -> float | None:
        return self.computed_rule_reach / self.viral_taxa if self.viral_taxa else None

    def to_dict(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "unreachable_names": [list(p) for p in self.unreachable_names],
            "reach_share": self.reach_share,
            "computed_share": self.computed_share,
        }


def measure(
    release: Release,
    baseline: Baseline,
    *,
    named: Mapping[str, Sequence[str]],
    realms: Iterable[str],
) -> Measurement:
    """Reduce one release to its counts against the baseline.

    `new_*` counts a viral taxon of this release that the baseline did not have **and** that
    is not the successor of something it did — the merge check is what stops a renumbering
    being read as new material. `renamed` and `reranked` count the other side: taxa both
    releases have, under a different word or a different rank. The two are returned separately
    and are never summed (D-201).
    """
    viral = release.viral()
    reach, unreachable = reach_of(release, viral=viral, named=named)

    realm_ids = frozenset(
        t for t, name in release.names.items() if name in set(realms) and t in viral
    )
    computed = sum(1 for t in viral if release.has_ancestor_in(t, realm_ids))

    # Every taxid this release reached by retiring one the baseline knew. Built from the
    # release's own merge table rather than by testing each new taxon, because the table is
    # a hundred thousand rows against the baseline's two and a half million.
    renumbered_from_baseline = {
        release.resolve(old) for old in release.merged if old in baseline.all_taxids
    }

    new_named = new_not_named = reassigned = renamed = reranked = renumbered = 0
    for taxid in viral:
        if taxid in baseline.all_taxids:
            if taxid in baseline.viral:
                if release.names.get(taxid, "") != baseline.name.get(taxid, ""):
                    renamed += 1
                if release.rank.get(taxid, "") != baseline.rank.get(taxid, ""):
                    reranked += 1
            else:
                reassigned += 1
            continue
        if taxid in renumbered_from_baseline:
            # The baseline had this taxon under another number. Not new material, and
            # counting it as such is the single easiest way to overstate decay.
            renumbered += 1
            continue
        if taxid in reach:
            new_named += 1
        else:
            new_not_named += 1

    return Measurement(
        date=release.date,
        viral_taxa=len(viral),
        reach=len(reach),
        unreachable_names=unreachable,
        new_not_named=new_not_named,
        new_named=new_named,
        renumbered=renumbered,
        reassigned_into_viral=reassigned,
        renamed=renamed,
        reranked=reranked,
        computed_rule_reach=computed,
        has_merged_dmp=bool(release.merged),
    )

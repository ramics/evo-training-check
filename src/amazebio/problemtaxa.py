"""The §A2 problem-taxa checklist, and what a lineage can say about it — task A2.5.

`DESIGN.md` §A2's last detection bullet names three categories "known to defeat taxonomic
filters" — giant viruses and NCLDV, segmented genomes, satellite viruses — and defines none of
them. DECISIONS.md **D-187** resolves all three against the pinned ICTV VMR rather than against
this project's judgement of what counts as a giant virus, and this module is that entry made
executable. Nothing here reads a corpus: the tool does the I/O, this is the vocabulary and the
arithmetic, so both are testable without a 5 GB TSV.

Three things make this harder than matching a name, and each changes what gets counted.

**A category has a rank, and a record's label has a depth.** `Nucleocytoviricota` is a phylum;
`Cystoviridae` is a family. A record labelled `r__Duplodnaviria;k__Heunggongvirae;
p__Uroviricota;c__Caudoviricetes;;;;` fills four ranks of eight, so it answers a phylum-level
question perfectly and a family-level one not at all. There is therefore no single "does this
category survive" answer per corpus — there is one per category, and the share of records that
can answer it is a property of the category's rank. `amazebio.unfilterable` makes the same point
for the filter's own rules; this is the detection side of it.

**A coarse label can refute a fine category, and that is most of the result.** Evo 1's surviving
component is 2,628,513 records labelled to class `Caudoviricetes` and no further. On a naive
reading that is 99% of the corpus unable to answer anything below class — but every NCLDV family
sits under phylum `Nucleocytoviricota`, whose classes are a set `Caudoviricetes` is not in, so
those records are **decided**, not unlabelled: they cannot be giant viruses. The same records are
genuinely unlabelled for the segmented-genome category, which is keyed on family. So refutation
runs *up* the ladder as well as down, and :class:`Checklist` resolves each category at the
coarsest rank that settles it. Collapsing that into one "unclassified fraction" would understate
the NCLDV result and overstate the segmented one, in opposite directions, from the same corpus.

**A taxon the pinned taxonomy does not know cannot be refuted.** IMG/VR's classifications were
assigned under some taxonomy release and this module reasons under MSL37.3; a name absent from
it is reported as :attr:`Verdict.UNLABELLED` with `taxon_unknown_to_reference`, never as absent.
That gap is taxonomic drift, which is A9.1's subject, and silently treating an unknown name as
"not NCLDV" would bury A9.1's finding inside A2.5's zero.

**Membership is a set of (rank, taxon) pairs, not a rank plus a list.** Satellite viruses are
four family-unassigned genera plus one family (D-187), so a category spanning two ranks is the
normal case rather than a special one, and :meth:`Checklist.verdict` is written over pairs.

The three-way verdict — present, absent, unlabelled — is the whole point. `AGENTS.md` forbids
designing any part of the pipeline so that a null is harder to see, and a two-way
present/absent split would record "we could not tell" as "it is not there", which is the
specific way a label-based sweep manufactures a clean bill of health.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Iterator, Mapping
from enum import Enum
from typing import Any

from amazebio.conformance import RANKS

__all__ = [
    "GVMAG_PATTERN",
    "RANK_ORDER",
    "Category",
    "CategoryDefinition",
    "Checklist",
    "ProblemTaxaError",
    "Verdict",
    "VerdictDetail",
    "build_checklist",
    "is_gvmag",
]


class ProblemTaxaError(RuntimeError):
    """Raised when the checklist is asked for something the pinned taxonomy cannot support."""


#: Rank -> position, coarsest first, taken from `amazebio.conformance.RANKS` rather than
#: restated so the two cannot drift. Comparing two ranks is comparing two of these.
RANK_ORDER: dict[str, int] = {rank: i for i, rank in enumerate(RANKS)}


class Category(Enum):
    """One §A2 problem category. The values are the artefact's own keys.

    `SATELLITE_VIRUS` and `SATELLITE_NUCLEIC_ACID` are separate members because §A2 names
    satellite *viruses* and most of ICTV's satellites are not viruses — they encode no capsid.
    D-187 measures both and forbids summing them: whether a capsid is encoded is exactly the
    difference that decides whether a filter looking for viral sequence could reach one.
    """

    NCLDV = "ncldv"
    """Giant viruses and nucleocytoplasmic large DNA viruses — ICTV phylum Nucleocytoviricota."""

    SEGMENTED = "segmented"
    """Families with a multipartite genome, by the VMR's own segment labelling."""

    SATELLITE_VIRUS = "satellite_virus"
    """Satellites that encode their own capsid: four genera plus Sarthroviridae."""

    SATELLITE_NUCLEIC_ACID = "satellite_nucleic_acid"
    """Capsid-less helper-dependent satellites: Alphasatellitidae, Tolecusatellitidae."""


class Verdict(Enum):
    """What a record's lineage says about one category. Exactly one per record per category."""

    PRESENT = "present"
    """A member of the category matched the record's own label."""

    ABSENT = "absent"
    """Every member of the category was refuted — at the member's rank or a coarser one."""

    UNLABELLED = "unlabelled"
    """The label neither matches nor refutes. **Not evidence of absence**, and never counted as
    such: a record labelled only to class cannot answer a family-level category, and a corpus
    whose labels stop early is the filter's blind spot rather than a clean result."""


@dataclasses.dataclass(frozen=True, slots=True)
class VerdictDetail:
    """A verdict with the evidence that produced it, so a count can be taken apart again.

    `decided_at` and `matched` are what let a reader ask *why* a record was called absent. A
    zero established at class over two million records and a zero established family by family
    are both zeros, and they do not support the same sentence in a write-up.
    """

    verdict: Verdict
    decided_at: str | None = None
    """The rank the verdict was settled at — the category's own rank, or a coarser one that
    refuted it. `None` when the verdict is `UNLABELLED`."""

    matched: tuple[str, str] | None = None
    """The `(rank, taxon)` member that matched, for `PRESENT`."""

    why: str = ""
    """Why an `UNLABELLED` verdict could not be settled. Empty otherwise."""


@dataclasses.dataclass(frozen=True)
class CategoryDefinition:
    """One category's membership, as `(rank, taxon)` pairs.

    `species_count` is the number of VMR exemplar species the set was derived from. It is
    carried because it is the only thing that distinguishes a category this release knows a lot
    about from one it barely knows, and a reader comparing a zero across categories needs that.
    """

    category: Category
    members: frozenset[tuple[str, str]]
    species_count: int
    note: str = ""

    def __post_init__(self) -> None:
        if not self.members:
            raise ProblemTaxaError(
                f"{self.category.value} has no members; an empty category would make every "
                "record absent from it and publish that as a result"
            )
        for rank, taxon in self.members:
            if rank not in RANK_ORDER:
                raise ProblemTaxaError(f"{self.category.value} member {taxon!r} has rank {rank!r}")

    @property
    def ranks(self) -> tuple[str, ...]:
        """The ranks this category's members sit at, coarsest first."""
        return tuple(sorted({r for r, _ in self.members}, key=RANK_ORDER.__getitem__))


# --------------------------------------------------------------------------------------
# Giant-virus MAGs — a handle that does not go through the lineage column at all
# --------------------------------------------------------------------------------------

#: IMG/VR names its giant-virus metagenome-assembled genomes in the accession itself, as
#: `IMGVR_UViG_GVMAG-M-<taxon oid>-<n>_<n>`. A7.2 counted 2,055 of them in the input release
#: while recording them only as an accession shape its packing could not handle; D-187 promotes
#: that to a signal, because it is a giant-virus label **the publisher applied** that survives
#: the lineage column being empty. It is evidence about one corpus, not a general method: it
#: works because IMG/VR chose to encode provenance in its identifiers.
GVMAG_PATTERN = re.compile(r"GVMAG-[A-Z]-")


def is_gvmag(accession: str) -> bool:
    """Whether an IMG/VR accession names a giant-virus MAG.

    Matched on the `GVMAG-<letter>-` infix rather than a literal `GVMAG-M-`, because the letter
    distinguishes the assembly route and a release that adds one would otherwise go uncounted.
    """
    return bool(GVMAG_PATTERN.search(accession or ""))


# --------------------------------------------------------------------------------------
# The checklist
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Checklist:
    """The four category definitions plus the lineage index that lets them be refuted.

    `ancestors` maps `(rank, taxon)` to that taxon's full lineage in the pinned release, which
    is what makes refutation at a coarser rank possible: a record whose class is known can be
    compared against the classes every member of a category sits under.
    """

    reference: str
    definitions: Mapping[Category, CategoryDefinition]
    ancestors: Mapping[tuple[str, str], Mapping[str, str]]

    def definition(self, category: Category) -> CategoryDefinition:
        try:
            return self.definitions[category]
        except KeyError:
            raise ProblemTaxaError(f"no definition for {category}") from None

    def _member_ancestors(self, rank: str, taxon: str, at: str) -> frozenset[str]:
        """Every name a member `(rank, taxon)` can carry at the coarser rank `at`.

        A member whose own lineage the reference does not record contributes nothing, which
        makes it unrefutable at that rank rather than vacuously refuted.
        """
        lineage = self.ancestors.get((rank, taxon))
        if not lineage:
            return frozenset()
        name = lineage.get(at)
        return frozenset({name}) if name else frozenset()

    def verdict(self, taxonomy: Mapping[str, str], category: Category) -> VerdictDetail:
        """Decide one category against one record's rank -> taxon mapping.

        `PRESENT` as soon as a member matches. Otherwise every member must be refuted for
        `ABSENT`: at its own rank if the record fills it, at a finer rank by lifting the
        record's taxon to the member's rank, or at a coarser rank the record fills by showing
        the record's name is not one the member sits under. A single unrefuted member leaves the
        whole category `UNLABELLED`, which is the conservative direction — it is the direction
        that does not turn an unanswered question into a null.
        """
        definition = self.definition(category)

        # Membership is checked at the member's own rank **and by lifting a finer label to
        # it**. The lift is not a nicety: `f__Mimiviridae` with no phylum field is a giant
        # virus, and a check that only compared ranks directly would return `UNLABELLED` for
        # it — hiding a detection as "could not tell", which is the one direction this module
        # must never fail in.
        for rank, taxon in sorted(definition.members):
            if taxonomy.get(rank) == taxon:
                return VerdictDetail(Verdict.PRESENT, decided_at=rank, matched=(rank, taxon))
            for other, name in taxonomy.items():
                if (
                    other in RANK_ORDER
                    and RANK_ORDER[other] > RANK_ORDER[rank]
                    and self.ancestors.get((other, name), {}).get(rank) == taxon
                ):
                    return VerdictDetail(Verdict.PRESENT, decided_at=other, matched=(rank, taxon))

        refuted_at: list[str] = []
        unrefuted: list[str] = []
        for rank, taxon in sorted(definition.members):
            where = self._refute(taxonomy, rank, taxon)
            (refuted_at if where is not None else unrefuted).append(where or rank)

        if unrefuted:
            return VerdictDetail(Verdict.UNLABELLED, why=self._why(taxonomy, unrefuted))

        # The **finest** rank any member needed is the binding one: it is the label this zero
        # actually rests on. Reporting the coarsest would overstate how little evidence sufficed.
        return VerdictDetail(Verdict.ABSENT, decided_at=max(refuted_at, key=RANK_ORDER.__getitem__))

    def _refute(self, taxonomy: Mapping[str, str], rank: str, taxon: str) -> str | None:
        """The rank a member was refuted at, or `None` if it could not be."""
        here = taxonomy.get(rank)
        if here is not None:
            # The record fills the member's own rank and carries a different name there.
            return rank

        for other, name in taxonomy.items():
            if other not in RANK_ORDER:
                continue
            if RANK_ORDER[other] > RANK_ORDER[rank]:
                # Finer than the member: lift the record's taxon to the member's rank.
                lifted = self.ancestors.get((other, name), {}).get(rank)
                if lifted is not None and lifted != taxon:
                    return other
            elif RANK_ORDER[other] < RANK_ORDER[rank]:
                # Coarser than the member: the member sits under exactly one name here.
                allowed = self._member_ancestors(rank, taxon, other)
                if allowed and name not in allowed:
                    return other
        return None

    def _why(self, taxonomy: Mapping[str, str], unrefuted: list[str]) -> str:
        """Why a category could not be settled — one reason per record, by fixed precedence.

        The precedence is the point. Picking among per-member reasons by sort order, which an
        earlier version did, reported "the label stops too high" for a record whose labels the
        reference does not contain at all — burying taxonomic drift, which is A9.1's finding,
        inside a formatting detail of A2.5's.
        """
        labelled = {r: n for r, n in taxonomy.items() if r in RANK_ORDER}
        if not labelled:
            return "no taxonomic label at any rank"
        if not any(self.ancestors.get(pair) for pair in labelled.items()):
            return "taxon_unknown_to_reference"

        # A taxon the reference **knows but does not place** is a third thing, and it is the
        # finding this category exists to surface. `Dinodnavirus` — Heterocapsa circularisquama
        # DNA virus, a large dsDNA algal virus — is a VMR genus at MSL37.3 with no family,
        # order, class, phylum or realm above it. No phylum-keyed rule can reach it, however
        # complete the record's label is, so calling that "the label stops too high" would
        # blame the corpus for a gap in the taxonomy.
        finest = max(unrefuted, key=RANK_ORDER.__getitem__)
        deepest_rank = max(labelled, key=RANK_ORDER.__getitem__)
        lineage = self.ancestors.get((deepest_rank, labelled[deepest_rank])) or {}
        if RANK_ORDER[finest] < RANK_ORDER[deepest_rank] and not lineage.get(finest):
            # The category sits at a rank **coarser** than the record's deepest label and the
            # reference still assigns the taxon nothing there. A missing *finer* rank is mere
            # truncation; a missing coarser one means the taxonomy itself does not place this
            # taxon, so no amount of labelling by the corpus would help.
            return f"taxon_unplaced_in_reference above {finest}"
        return f"label stops above {finest} and does not refute it"

    def classify(self, taxonomy: Mapping[str, str]) -> dict[Category, VerdictDetail]:
        """Every category's verdict for one record."""
        return {c: self.verdict(taxonomy, c) for c in self.definitions}


# --------------------------------------------------------------------------------------
# Deriving the checklist from the pinned VMR
# --------------------------------------------------------------------------------------

#: Satellite taxa, by rank, exactly as D-187 names them. Written out rather than matched on a
#: name pattern: `*satellitidae` would catch the two satellite-nucleic-acid families and miss
#: every satellite virus, all four of which are family-unassigned genera, and a pattern would
#: also silently absorb a future family whose membership nobody checked.
SATELLITE_VIRUS_MEMBERS: frozenset[tuple[str, str]] = frozenset(
    {
        ("genus", "Albetovirus"),
        ("genus", "Aumaivirus"),
        ("genus", "Papanivirus"),
        ("genus", "Virtovirus"),
        ("family", "Sarthroviridae"),
    }
)

SATELLITE_NUCLEIC_ACID_MEMBERS: frozenset[tuple[str, str]] = frozenset(
    {("family", "Alphasatellitidae"), ("family", "Tolecusatellitidae")}
)

#: The phylum that defines the NCLDV category. One name, because ICTV's own circumscription is
#: one phylum and D-187 rejected a genome-size rule that would have made it ours.
NCLDV_PHYLUM = "Nucleocytoviricota"

#: Satellite-like and deliberately **not** in either satellite category (D-187). Deltavirus-like
#: agents are helper-dependent, but ICTV ratifies `Ribozyviria` as a realm and does not classify
#: them as satellites. Named so the boundary is visible and a later task can include them
#: without re-deriving anything.
EXCLUDED_SATELLITE_LIKE: frozenset[tuple[str, str]] = frozenset({("realm", "Ribozyviria")})


def _exemplars(vmr: Any) -> Iterator[Any]:
    yield from (vmr.exemplars if hasattr(vmr, "exemplars") else vmr)


def _segmented_families(exemplars: Iterable[Any]) -> tuple[frozenset[str], int, int]:
    """Families holding at least one **labelled** multi-segment exemplar, per D-187.

    The label is the discriminator and dropping it is wrong in the admitting direction: the VMR
    lists several accessions for plenty of monopartite genomes — Adenoviridae's `Y09598` plus
    `AC_000004`, four partial Poxviridae records, two Phycodnaviridae — while genuinely
    multipartite families label their segments (`L`/`M`/`S`, `RNA1`…`RNA8`, `DNA-A`/`DNA-B`).
    Requiring one label excludes those three families and keeps the segmented ones.

    Returns the families, the exemplar species they came from, and the count of labelled
    multi-segment species carrying **no** family — which contribute to no set and are returned
    rather than dropped, because a species this rule cannot place is a limit of the rule.
    """
    families: set[str] = set()
    species = 0
    without_family = 0
    for exemplar in exemplars:
        accessions = exemplar.accessions
        if len(accessions) <= 1 or not any(label for label, _ in accessions):
            continue
        species += 1
        family = exemplar.lineage.get("family")
        if family:
            families.add(family)
        else:
            without_family += 1
    return frozenset(families), species, without_family


def build_checklist(vmr: Any, *, reference: str) -> Checklist:
    """Derive the four category definitions and the lineage index from a pinned VMR.

    `reference` is the release key the sets are derived under, carried into the artefact so a
    table cannot be read against a different taxonomy than it was built from. Deriving rather
    than hard-coding the sets is what makes D-187 re-executable: the entry quotes 7 NCLDV
    families, 48 segmented families and 216 satellite-nucleic-acid species, and a later release
    that changes those numbers is A9.1's decay result rather than a broken test.
    """
    exemplars = list(_exemplars(vmr))
    if not exemplars:
        raise ProblemTaxaError("the VMR yielded no exemplar rows")

    ancestors: dict[tuple[str, str], dict[str, str]] = {}
    for exemplar in exemplars:
        lineage = {r: n for r, n in exemplar.lineage.items() if r in RANK_ORDER and n}
        for rank, name in lineage.items():
            ancestors.setdefault((rank, name), {}).update(
                {r: n for r, n in lineage.items() if RANK_ORDER[r] <= RANK_ORDER[rank]}
            )

    ncldv_families = frozenset(
        f
        for exemplar in exemplars
        if exemplar.lineage.get("phylum") == NCLDV_PHYLUM and (f := exemplar.lineage.get("family"))
    )
    ncldv_species = sum(1 for e in exemplars if e.lineage.get("phylum") == NCLDV_PHYLUM)
    segmented, segmented_species, segmented_no_family = _segmented_families(exemplars)

    def species_in(members: frozenset[tuple[str, str]]) -> int:
        return sum(1 for e in exemplars if any(e.lineage.get(r) == t for r, t in members))

    definitions = {
        Category.NCLDV: CategoryDefinition(
            category=Category.NCLDV,
            # The phylum itself, not its families: matching at phylum is what lets a
            # class-level label refute the category, which is most of Evo 1's corpus.
            members=frozenset({("phylum", NCLDV_PHYLUM)}),
            species_count=ncldv_species,
            note=(
                f"{len(ncldv_families)} families at {reference}: "
                f"{', '.join(sorted(ncldv_families))}"
            ),
        ),
        Category.SEGMENTED: CategoryDefinition(
            category=Category.SEGMENTED,
            members=frozenset(("family", f) for f in segmented),
            species_count=segmented_species,
            note=(
                f"{len(segmented)} families holding a labelled multi-segment exemplar; "
                f"{segmented_no_family} labelled multi-segment species carry no family and "
                "contribute to none"
            ),
        ),
        Category.SATELLITE_VIRUS: CategoryDefinition(
            category=Category.SATELLITE_VIRUS,
            members=SATELLITE_VIRUS_MEMBERS,
            species_count=species_in(SATELLITE_VIRUS_MEMBERS),
            note="capsid-encoding satellites; four family-unassigned genera plus Sarthroviridae",
        ),
        Category.SATELLITE_NUCLEIC_ACID: CategoryDefinition(
            category=Category.SATELLITE_NUCLEIC_ACID,
            members=SATELLITE_NUCLEIC_ACID_MEMBERS,
            species_count=species_in(SATELLITE_NUCLEIC_ACID_MEMBERS),
            note=(
                "capsid-less helper-dependent satellites; carry no rank above family in the "
                "VMR, which is why a realm-level sweep cannot see them"
            ),
        ),
    }
    return Checklist(reference=reference, definitions=definitions, ancestors=ancestors)

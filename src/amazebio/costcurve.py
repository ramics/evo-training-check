"""The frozen cost-curve definitions — task C5.1, DESIGN.md §C5 to §C7 and §4.

`metrics/costcurve.md` is the authoritative text and this is the first implementation of it.
C6.3 reimplements the headline curves from that document by a second method before anything is
published (§7), so nothing here is load-bearing for the published result on its own.

**Nothing in this module trains, fine-tunes or runs a model** (§C5). Every quantity is a count
over pinned databases, or arithmetic on such counts.

Three things here are the frozen decisions rather than code, each with a the project decision log (see `docs/working-record.md`)
entry (D-204):

**The regime boundary is anchored to a measured quantity, not to a round number.** A family is
catastrophic when removing nine tenths of its known diversity costs at least as much general
biology as removing every virus does — :data:`VIRAL_SHARE_UNIREF50`, which A8.1 measured. §C6's
claim that filtering *cannot* work for a family is too strong to rest on a threshold this
project picked to taste.

**A regime label is made at the conservative end of its own interval.** A point estimate that
crosses a boundary by less than its own width would otherwise produce a label out of sampling
noise, and the label is the whole deliverable.

**The published view cannot name a family.** §4 publishes by homology class, never as a
per-family hazard ranking, so the aggregation refuses a class small enough to be one — and the
refusal is in the schema rather than in anyone's care at write-up time.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence

from amazebio.survival import Interval, wilson_interval

__all__ = [
    "CATASTROPHIC",
    "CHEAP",
    "COVERAGE_LIMITED",
    "HAZARD_REMOVED_TARGET",
    "IDENTITY_FLOOR",
    "INTERMEDIATE",
    "MIN_CLASS_MEMBERS",
    "NO_CLAN",
    "SATURATION_FLOOR",
    "STRADDLING",
    "STRATA",
    "STRINGENCIES",
    "TOP_GENUS_CEILING",
    "UNBOUNDED_BELOW",
    "UNREACHABLE",
    "VIRAL_SHARE_UNIREF50",
    "CostCurveError",
    "Coverage",
    "CurveSet",
    "FamilyCurve",
    "Point",
    "chao1_saturation",
    "classify",
    "points_from_counts",
    "published_view",
]


class CostCurveError(Exception):
    """A refusal. Every one marks a case where a plausible wrong number would be produced."""


#: The stringency sweep, as sequence identity at >= 80% coverage of the shorter sequence
#: (M3's rule, `metrics/survival.md`). Descending, because a filter gets broader as s falls.
STRINGENCIES: tuple[float, ...] = (0.95, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30)

#: The lowest honest threshold. Below this a pairwise alignment stops distinguishing homology
#: from chance at protein length and the prefilter is not calibrated to be exhaustive, so a
#: curve drawn past it reports the aligner's sensitivity rather than biology.
IDENTITY_FLOOR = 0.30

#: s* is the loosest stringency still removing this much of a family's known diversity.
HAZARD_REMOVED_TARGET = 0.90

#: The share of UniRef50 2023_02's 60,479,070 clusters containing a viral seed — 674,571 of
#: them — measured by A8.1 (D-200, `artifacts/a8-1/agreement-2023_02-uniref50.json`). This is
#: what the filters Phase A audited already cost, and it is the anchor the regime boundary is
#: expressed against so that "catastrophic" means "dearer than what the field already does".
VIRAL_SHARE_UNIREF50 = 674_571 / 60_479_070

#: The three published nominations a family can enter by. V and T are curve subjects; S is
#: counted and reported and gets no curve, because a regulation naming an organism nominates
#: no protein family and choosing one would be this project's judgement (D-204).
STRATA: tuple[str, ...] = ("V", "T", "S")
CURVE_STRATA: frozenset[str] = frozenset({"V", "T"})

CHEAP = "cheap"
INTERMEDIATE = "intermediate"
CATASTROPHIC = "catastrophic"
STRADDLING = "straddling"
UNREACHABLE = "unreachable"
UNBOUNDED_BELOW = "unbounded_below"
COVERAGE_LIMITED = "coverage_limited"

#: Coverage gates. A family failing either gets no regime label at all, because a caveat
#: printed under a label is read as the label (§C7).
SATURATION_FLOOR = 0.5
TOP_GENUS_CEILING = 0.8

#: Fewer subjects than this and the class is the family. Two is not enough either: a reader
#: holding one of the two values derives the other.
MIN_CLASS_MEMBERS = 3
NO_CLAN = "no_clan"


def chao1_saturation(singletons: int, doubletons: int, observed: int) -> float | None:
    """Observed richness over the Chao1 estimate — has the database stopped finding new F?

    Abundances are a cluster's UniRef90 sub-cluster count, so a "singleton" is a UniRef50
    cluster seen in exactly one UniRef90 cluster. Returns None where the estimator is
    undefined (no doubletons), which is reported as null rather than as 1.0: an estimator
    that cannot be computed is not an estimate of complete sampling.
    """
    if observed <= 0:
        raise CostCurveError("saturation over an empty family is undefined, not 1.0")
    if singletons == 0:
        return 1.0
    if doubletons == 0:
        return None
    return observed / (observed + singletons**2 / (2 * doubletons))


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    """§C7's pair. A curve is never reported without it, so it is not optional here."""

    observed_clusters: int
    singletons: int
    doubletons: int
    genera: int
    top_genus_clusters: int

    @property
    def saturation(self) -> float | None:
        return chao1_saturation(self.singletons, self.doubletons, self.observed_clusters)

    @property
    def top_genus_share(self) -> float:
        if self.observed_clusters <= 0:
            raise CostCurveError("a top-genus share over an empty family is undefined")
        return self.top_genus_clusters / self.observed_clusters

    @property
    def limited(self) -> bool:
        """True when the databases are too thin for a regime label to mean anything.

        An undefined saturation counts as limited: it means the family has no doubletons,
        which at any size is a family the database has barely sampled twice.
        """
        saturation = self.saturation
        return (
            saturation is None
            or saturation < SATURATION_FLOOR
            or self.top_genus_share > TOP_GENUS_CEILING
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "saturation": self.saturation,
            "top_genus_share": self.top_genus_share,
            "coverage_limited": self.limited,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Point:
    """One stringency's reading for one family. Counts are UniRef50 clusters throughout."""

    stringency: float
    hazard_removed: int
    hazard_total: int
    collateral_removed: int
    collateral_total: int
    families_touched: int
    #: The same two numerators in the reported units, carried so a reader can convert without
    #: recomputing. Never summed with the cluster counts and never a denominator.
    uniref90_clusters_removed: int = 0
    records_removed: int = 0
    #: Collateral clusters carrying no Pfam annotation at all. A collateral set made mostly of
    #: unannotated clusters is a different finding from one made of named families.
    collateral_unannotated: int = 0

    def __post_init__(self) -> None:
        if self.hazard_total <= 0 or self.collateral_total <= 0:
            raise CostCurveError(
                "a cost curve over an empty hazard or collateral universe is a setup error, "
                "not a result: check the family set and the pinned release"
            )
        if self.hazard_removed > self.hazard_total:
            raise CostCurveError(
                f"at s={self.stringency} the filter removes more of the family than the family "
                f"has ({self.hazard_removed} > {self.hazard_total})"
            )
        if self.collateral_removed > self.collateral_total:
            raise CostCurveError(
                f"at s={self.stringency} the collateral exceeds its universe "
                f"({self.collateral_removed} > {self.collateral_total})"
            )

    @property
    def hazard(self) -> Interval:
        return wilson_interval(self.hazard_removed, self.hazard_total)

    @property
    def collateral(self) -> Interval:
        return wilson_interval(self.collateral_removed, self.collateral_total)

    def to_dict(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "hazard": dataclasses.asdict(self.hazard),
            "collateral": dataclasses.asdict(self.collateral),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyCurve:
    """One family's whole curve, its coverage, and the regime that follows from them."""

    family: str
    stratum: str
    clan: str | None
    fold_family: str | None
    points: tuple[Point, ...]
    coverage: Coverage
    #: True when the nomination enumerated the family — seed set and target are one set — so
    #: there is nothing for a filter to generalise to and H(s)=1 everywhere means nothing.
    seed_equals_target: bool = False

    def __post_init__(self) -> None:
        if self.stratum not in STRATA:
            raise CostCurveError(f"{self.family}: unknown nomination stratum {self.stratum!r}")
        if self.stratum not in CURVE_STRATA:
            raise CostCurveError(
                f"{self.family}: stratum {self.stratum} nominates an organism and no protein "
                "family, so it is counted and reported but carries no curve (D-204)"
            )
        if not self.points:
            raise CostCurveError(f"{self.family}: a curve with no points")
        seen = [p.stringency for p in self.points]
        if sorted(seen, reverse=True) != seen or len(set(seen)) != len(seen):
            raise CostCurveError(
                f"{self.family}: points must run from the strictest stringency down, once "
                f"each; got {seen}"
            )
        unknown = sorted(set(seen) - set(STRINGENCIES))
        if unknown:
            raise CostCurveError(
                f"{self.family}: {unknown} is not on the frozen sweep {list(STRINGENCIES)}. "
                "A point off the axis cannot be compared with any other family's."
            )

    @property
    def s_star(self) -> Point | None:
        """The loosest stringency still removing HAZARD_REMOVED_TARGET of the family.

        Loosest, not strictest: the curve is read as "what is the cheapest filter that does the
        job", and the points run strict-to-loose, so this is the last one that qualifies.
        """
        qualifying = [p for p in self.points if p.hazard.estimate >= HAZARD_REMOVED_TARGET]
        return qualifying[-1] if qualifying else None

    @property
    def unbounded_below(self) -> bool:
        """Collateral still growing at the identity floor — the curve has not closed.

        Reported whatever the regime, because a family whose cost is still rising at the
        lowest honest threshold has no measured ceiling, only a measured floor.
        """
        floor = [p for p in self.points if p.stringency == IDENTITY_FLOOR]
        if not floor or len(self.points) < 2:
            return False
        previous = self.points[-2]
        return floor[0].collateral_removed > previous.collateral_removed

    def regime(self) -> tuple[str, dict[str, object]]:
        """The §C6 triage, with everything the label rests on beside it."""
        why: dict[str, object] = {
            "viral_share_anchor": VIRAL_SHARE_UNIREF50,
            "unbounded_below": self.unbounded_below,
        }
        if self.seed_equals_target:
            why["note"] = (
                "the nomination enumerated the family: seed set and target are the same set, "
                "so there is nothing for a filter to generalise to"
            )
            return UNREACHABLE, why
        if self.coverage.limited:
            why["note"] = (
                "the databases are too thin for a label: saturation "
                f"{self.coverage.saturation}, top-genus share "
                f"{self.coverage.top_genus_share:.4f}"
            )
            return COVERAGE_LIMITED, why
        point = self.s_star
        if point is None:
            why["note"] = (
                f"no stringency in the sweep removes {HAZARD_REMOVED_TARGET:.0%} of the "
                "family, so no filter in the honest range reaches it"
            )
            return UNREACHABLE, why

        collateral = point.collateral
        why["s_star"] = point.stringency
        why["collateral"] = dataclasses.asdict(collateral)
        cheap = collateral.high <= VIRAL_SHARE_UNIREF50 / 100
        catastrophic = collateral.low >= VIRAL_SHARE_UNIREF50
        if cheap and catastrophic:  # pragma: no cover - V/100 < V, so this cannot both hold
            raise CostCurveError("the boundary is inconsistent; V must exceed V/100")
        if cheap:
            return CHEAP, why
        if catastrophic:
            return CATASTROPHIC, why
        # Neither end of the interval clears a boundary. Say which boundaries it spans rather
        # than defaulting to the middle label, which would read as a measurement.
        spans = [
            name
            for name, crossed in (
                (CHEAP, collateral.low <= VIRAL_SHARE_UNIREF50 / 100),
                (CATASTROPHIC, collateral.high >= VIRAL_SHARE_UNIREF50),
            )
            if crossed
        ]
        if spans:
            why["spans"] = [*spans, INTERMEDIATE]
            return STRADDLING, why
        return INTERMEDIATE, why

    def to_dict(self) -> dict[str, object]:
        regime, why = self.regime()
        return {
            "family": self.family,
            "stratum": self.stratum,
            "clan": self.clan,
            "fold_family": self.fold_family,
            "seed_equals_target": self.seed_equals_target,
            "points": [p.to_dict() for p in self.points],
            "coverage": self.coverage.to_dict(),
            "regime": regime,
            "regime_basis": why,
        }


def classify(curve: FamilyCurve) -> str:
    """The regime label alone, for a caller that does not want the basis."""
    return curve.regime()[0]


def _class_of(curve: FamilyCurve) -> str:
    """A family's homology class: its Pfam clan, or the pooled clanless class.

    Pfam leaves 1,127 viral families clanless (D-075), and a singleton class republishes the
    per-family curve under another name.
    """
    return curve.clan or NO_CLAN


def published_view(
    curves: Iterable[FamilyCurve],
    *,
    min_members: int = MIN_CLASS_MEMBERS,
) -> dict[str, object]:
    """§4's aggregated view: regimes by homology class, with no family nameable from it.

    Produced from the full artefact with no recomputation. Classes below `min_members` merge
    into the pooled clanless class rather than being dropped — a dropped class would make the
    counts stop reconciling with the per-family artefact, and the reader could not tell a
    merge from a missing family.

    Where even the pooled class is below the floor, it is withheld and its families are
    reported as a bare count. That is the only honest end state: there is nowhere left to
    aggregate them, and the alternatives are naming a family or refusing the whole artefact
    over one orphan. The count keeps the totals reconciling.
    """
    if min_members < MIN_CLASS_MEMBERS:
        raise CostCurveError(
            f"a published class of fewer than {MIN_CLASS_MEMBERS} subjects is a per-family "
            "curve under another name, which §4 does not publish"
        )
    curves = list(curves)
    by_class: dict[str, list[FamilyCurve]] = {}
    for curve in curves:
        by_class.setdefault(_class_of(curve), []).append(curve)

    merged: list[str] = []
    pooled: list[FamilyCurve] = list(by_class.pop(NO_CLAN, []))
    for name in sorted(by_class):
        if len(by_class[name]) < min_members:
            pooled.extend(by_class.pop(name))
            merged.append(name)
    if pooled:
        by_class[NO_CLAN] = pooled

    classes = []
    for name in sorted(by_class):
        members = by_class[name]
        regimes: dict[str, int] = {}
        for curve in members:
            label = classify(curve)
            regimes[label] = regimes.get(label, 0) + 1
        classes.append(
            {
                "homology_class": name,
                "families": len(members),
                "fold_families": sorted(
                    {c.fold_family for c in members if c.fold_family is not None}
                ),
                "regimes": dict(sorted(regimes.items())),
            }
        )
    withheld = sum(c["families"] for c in classes if c["families"] < min_members)  # type: ignore[misc]
    classes = [c for c in classes if c["families"] >= min_members]  # type: ignore[operator]
    named = sum(c["families"] for c in classes)  # type: ignore[misc]
    if named + withheld != len(curves):  # pragma: no cover - arithmetic guard
        raise CostCurveError("the published view does not account for every curve")
    return {
        "aggregated_by": "homology class (Pfam clan), per DESIGN.md §4",
        "min_class_members": min_members,
        "classes": classes,
        "merged_into_no_clan": sorted(merged),
        "withheld_families": withheld,
        "families": len(curves),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class CurveSet:
    """Every curve of one run, plus the strata that were nominated and carry none."""

    release: str
    pfam_version: str
    uniprot_release: str
    curves: tuple[FamilyCurve, ...]
    #: Stratum S: nominated by a regulation naming an organism, counted and reported, no curve.
    organism_nominated_families: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = [c.family for c in self.curves]
        if len(set(names)) != len(names):
            raise CostCurveError("a family appears twice in one curve set")
        overlap = sorted(set(names) & set(self.organism_nominated_families))
        if overlap:
            raise CostCurveError(
                f"{overlap} is both a curve subject and organism-nominated; a family that any "
                "of V or T nominates is a subject, and the strata are recorded per family"
            )

    def disclosure_view(self) -> dict[str, object]:
        """The per-family form. Disclosure package only — §4 keeps it out of the preprint."""
        return {
            "release": self.release,
            "pfam_version": self.pfam_version,
            "uniprot_release": self.uniprot_release,
            "uniprot_release_is_dated_not_pinned": True,
            "curves": [c.to_dict() for c in self.curves],
            "organism_nominated_families": list(self.organism_nominated_families),
        }

    def published(self, *, min_members: int = MIN_CLASS_MEMBERS) -> dict[str, object]:
        return {
            "release": self.release,
            "pfam_version": self.pfam_version,
            "uniprot_release": self.uniprot_release,
            "organism_nominated_families": len(self.organism_nominated_families),
            **published_view(self.curves, min_members=min_members),
        }


def points_from_counts(
    counts: Sequence[Mapping[str, int]],
    *,
    hazard_total: int,
    collateral_total: int,
) -> tuple[Point, ...]:
    """Build the sweep from one mapping per stringency, in the frozen order.

    A convenience for a pipeline that has the counts and should not be re-deriving the axis:
    the order and membership of :data:`STRINGENCIES` are the contract, and a caller that
    supplies its own order gets the refusal in :class:`FamilyCurve` rather than a curve whose
    x-axis is its own.
    """
    if len(counts) != len(STRINGENCIES):
        raise CostCurveError(
            f"the sweep has {len(STRINGENCIES)} points and {len(counts)} were given; a partial "
            "sweep is reported as a partial sweep, not padded"
        )
    return tuple(
        Point(
            stringency=s,
            hazard_total=hazard_total,
            collateral_total=collateral_total,
            **{k: int(v) for k, v in row.items()},
        )
        for s, row in zip(STRINGENCIES, counts, strict=True)
    )

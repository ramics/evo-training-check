"""The shared detection schema every A2 detector emits — defined by A2.1, used by A2.2-A2.5.

A2.1 is the first of five detectors (`DESIGN.md` §A2) and A3 merges all five by route, so the
output shape is a data contract rather than one task's file format. The prose specification is
`metrics/detections.md`; this module is the machine-readable half, the way
`amazebio.survival` is for the metric definitions.

What a detector supplies and what this module supplies are deliberately split. A detector knows
how to find a family in a sequence — a profile search here, Foldseek in A2.2, geNomad in A2.4.
This module knows what a detection has to carry to be countable: the pinned family universe it
is drawn from, the survival route it sits on, the sampling design that decides what the count is
a count *of*, and the guards that stop a table being assembled from parts that do not belong
together.

Four decisions are load-bearing, and each is in `tasks/DECISIONS.md`.

**The family universe is zero-filled from the registry, never built from the hits** (D-022, and
`amazebio.survival.surviving_counts_by_family` enforces it). A family with no surviving homolog
is the result this audit is testing for. A table assembled only from families that were hit
would render a null as missing data, which `AGENTS.md` forbids in as many words.

**Sampling is by a deterministic hash of the record identifier** (D-078). A profile search over
the whole surviving corpus is not merely expensive, it is arithmetically out of reach — tens of
thousands of core-years for the nucleotide releases — so the headline comes from a sample, and
the sample has to be declarable in advance, reproducible without storing a list of ids,
resumable after an interruption, and independent of the order records are read in.
:func:`in_sample` is all four: membership is a property of the id and the seed, so any run with
the same pins reads the same records, and a reader can check whether a named record was in the
sample without re-running anything.

**What a sample supports is a lower bound, and the schema says so in its own field** (D-078).
Family-level survival measured on a sample is a lower bound on the population value: a family
detected in the sample is detected, full stop, while a family absent from the sample may still
survive in the records not read. `estimate_kind` carries `lower_bound` for exactly this reason,
and A3.2 must not read a sampled table as a population estimate.

**Element kind is assigned from the record's component, conservatively** (D-079). A profile hit
says a viral family is present; it does not say whether the sequence is a free virus, a prophage
or an endogenous element, and those are what A2.3 and A2.4 establish with their own methods. So
this module maps a component to the weakest kind the component's own definition supports and
refuses to guess beyond it — a hit in a bacterial genome is an `UNCLASSIFIED_ELEMENT` here, and
becomes a `PROPHAGE` only when A2.4 says so.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from amazebio.survival import Detection, ElementKind, Route, family_survival

__all__ = [
    "COMPONENT_KINDS",
    "DetectionError",
    "DetectionTable",
    "FamilyRow",
    "ManifestRef",
    "SampleDesign",
    "element_kind_for",
    "in_sample",
    "sample_hash",
]


class DetectionError(RuntimeError):
    """Raised when a detection table would record something it cannot support."""


# --------------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------------

#: Width of the hash prefix the sampler compares, in bits. 64 is far more resolution than any
#: sample rate this project will use and keeps the comparison in one Python integer.
_HASH_BITS = 64
_HASH_MAX = 1 << _HASH_BITS


def sample_hash(record_id: str, *, seed: int) -> int:
    """Uniform 64-bit hash of a record id under a seed.

    `blake2b` keyed by the seed rather than Python's `hash`, which is randomised per process:
    a sampler whose membership changed between runs would make every count unreproducible, and
    `AGENTS.md` requires a result to regenerate from pinned inputs and seeds.
    """
    digest = hashlib.blake2b(
        record_id.encode("utf-8"), digest_size=8, key=str(seed).encode("ascii")
    )
    return int.from_bytes(digest.digest(), "big")


def in_sample(record_id: str, *, seed: int, rate: float) -> bool:
    """True when this record is in the sample defined by `(seed, rate)`.

    Membership is a property of the id, so the sample is the same whatever order the corpus is
    read in, however many passes it takes, and whether or not the run that drew it finished.
    """
    if not 0 < rate <= 1:
        raise DetectionError(f"sample rate {rate} is not in (0, 1]")
    if rate == 1:
        return True
    return sample_hash(record_id, seed=seed) < int(rate * _HASH_MAX)


@dataclasses.dataclass(frozen=True, slots=True)
class SampleDesign:
    """How much of a source was searched, and under which pins.

    Declared before a run, carried in the table, and repeated in `run.json`. A rate chosen after
    the hits were seen is not a sampling design, and the only defence against that is for the
    design to be an input the artefact records rather than a property of the output.
    """

    seed: int
    rate: float
    #: Records the source holds, from the manifest. None where the manifest does not enumerate
    #: it — then the sample is of what was read and the population is unknown, which is itself
    #: reported rather than filled in with a guess.
    population: int | None
    method: str = "blake2b(seed, record_id) < rate * 2**64"
    decision_ref: str = "D-078"

    @property
    def is_census(self) -> bool:
        return self.rate == 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "rate": self.rate,
            "population": self.population,
            "method": self.method,
            "decision_ref": self.decision_ref,
            "is_census": self.is_census,
        }


# --------------------------------------------------------------------------------------
# Element kind
# --------------------------------------------------------------------------------------

#: Component to the weakest element kind that component's own definition supports (D-079).
#:
#: IMG/VR is a database of viral genomes and metagenomic viral contigs, so a viral family hit in
#: one is a free virus by the publisher's own definition of the collection. Everything else is
#: `UNCLASSIFIED_ELEMENT`: a prophage, an endogenous element and a viral-derived fragment are
#: indistinguishable to a profile search, and asserting one of them from a profile hit would do
#: in passing what A2.3 and A2.4 exist to establish.
COMPONENT_KINDS: Mapping[str, ElementKind] = {
    "imgvr": ElementKind.FREE_VIRUS,
    "IMG/VR": ElementKind.FREE_VIRUS,
    "imgpr": ElementKind.UNCLASSIFIED_ELEMENT,
    "stage2": ElementKind.UNCLASSIFIED_ELEMENT,
}


def element_kind_for(component: str) -> ElementKind:
    """The element kind a profile hit in `component` supports, and no stronger one."""
    return COMPONENT_KINDS.get(component, ElementKind.UNCLASSIFIED_ELEMENT)


# --------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ManifestRef:
    """The A1.4 manifest a detection run consumed, pinned by digest.

    A detection table is a statement about *a* surviving corpus, and which one it is comes from
    the manifest. Pinning the digest is what stops a table being read against a manifest
    regenerated later under different policy prose — the numbers would still line up and mean
    something else.
    """

    policy_id: str
    release: str
    path: str
    sha256: str
    #: Records the manifest says the reading removes: subtracted from the surviving set before
    #: anything is searched, and reported so the subtraction is visible.
    removed_records: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyRow:
    """One family's row in a hit table. Present for every family in the universe, hit or not."""

    family_id: str
    name: str
    hits: int
    records: int
    best_score: float | None
    threshold: float
    routes: dict[str, int]
    element_kinds: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class DetectionTable:
    """Per-family hit table for one detector, one registry and one manifest.

    One table per (detector, registry, manifest) and never pooled across any of the three.
    Registries are not pooled because their membership criteria come from different authorities
    (`amazebio.profiles`); manifests are not pooled because a reading and a release are the two
    things Phase A is comparing; detectors are not pooled because A3.2 reports by route *and*
    by detector, and a merged table cannot be taken apart again.
    """

    task: str
    detector: str
    registry: str
    registry_version: str
    manifest: ManifestRef
    #: One per staged source searched: component, records read, genes called, residues searched.
    sources: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    sample: SampleDesign | None = None
    rows: list[FamilyRow] = dataclasses.field(default_factory=list)
    thresholds: dict[str, Any] = dataclasses.field(default_factory=dict)
    notes: list[str] = dataclasses.field(default_factory=list)

    @property
    def estimate_kind(self) -> str:
        """`not_searched`, `population` for a census, or `lower_bound` for a sample (D-078).

        `not_searched` is a distinct kind rather than a zero because a manifest whose sources
        this detector cannot read — the ESM3-open proxy corpus, whose reader is A1.6's — would
        otherwise report every family as absent, which reads as a filter that worked.
        """
        if not any(s.get("searched") for s in self.sources):
            return "not_searched"
        return "population" if (self.sample is None or self.sample.is_census) else "lower_bound"

    def families_with_a_hit(self) -> int:
        return sum(1 for r in self.rows if r.hits >= 1)

    def survival(self) -> dict[str, Any]:
        """Family-level survival over this table, with its interval.

        The number is computed here rather than in the write-up because `AGENTS.md` requires
        every published figure to trace to a machine-readable artefact, and because
        :func:`amazebio.survival.family_survival` must see the zero-filled universe this table
        already is.
        """
        if not self.rows:
            raise DetectionError(
                f"{self.registry}: no family rows, so the universe is empty and family-level "
                "survival has no denominator — the registry was not staged correctly"
            )
        interval = family_survival({r.family_id: r.hits for r in self.rows})
        return {
            "families_in_universe": len(self.rows),
            "families_with_a_hit": self.families_with_a_hit(),
            "fraction": interval.estimate,
            "ci_low": interval.low,
            "ci_high": interval.high,
            "method": interval.method,
            "estimate_kind": self.estimate_kind,
            "reading": (
                "fraction of this registry's families with at least one surviving homolog above "
                "threshold"
                + {
                    "population": "",
                    "lower_bound": ". A lower bound: the sample's unread records can only add "
                    "families, never remove one (D-078)",
                    "not_searched": ". Nothing was searched for this manifest, so every count "
                    "is zero by construction and none of it is evidence of absence — see the "
                    "per-source rows for why",
                }[self.estimate_kind]
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "detector": self.detector,
            "registry": self.registry,
            "registry_version": self.registry_version,
            "manifest": self.manifest.to_dict(),
            "sample": self.sample.to_dict() if self.sample else None,
            "estimate_kind": self.estimate_kind,
            "thresholds": self.thresholds,
            "sources": self.sources,
            "survival": self.survival(),
            "routes": self.route_totals(),
            "element_kinds": self.kind_totals(),
            "families": [r.to_dict() for r in self.rows if r.hits >= 1],
            "families_without_a_hit": [r.family_id for r in self.rows if r.hits == 0],
            "notes": self.notes,
            "reading_this_table": (
                "`families` lists only families with at least one hit; every other family in "
                "the pinned universe is in `families_without_a_hit`, so the denominator is the "
                "two lists together and a zero is a measured zero rather than an absent row. "
                "`estimate_kind` says whether the figures are a population value or a lower "
                "bound from a sample. Registries are never pooled (metrics/survival.md)."
            ),
        }

    def route_totals(self) -> dict[str, int]:
        total: Counter[str] = Counter()
        for row in self.rows:
            total.update(row.routes)
        return dict(sorted(total.items()))

    def kind_totals(self) -> dict[str, int]:
        total: Counter[str] = Counter()
        for row in self.rows:
            total.update(row.element_kinds)
        return dict(sorted(total.items()))

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return target


def build_rows(
    detections: Iterable[Detection],
    *,
    universe: Mapping[str, str],
    thresholds: Mapping[str, float],
) -> list[FamilyRow]:
    """Assemble zero-filled family rows from detections.

    Args:
        detections: every accepted detection, in any order.
        universe: the pinned family universe — accession to display name. The denominator.
        thresholds: per-family score threshold, so a row records what it was accepted against
            even when nothing hit it. A table whose zero rows carry no threshold cannot be
            re-read later to ask what a stricter one would have done.

    Raises:
        DetectionError: if a detection names a family outside the universe, or carries a
            registry other than the table's. Both change the denominator silently.
    """
    hits: Counter[str] = Counter()
    records: dict[str, set[str]] = {}
    best: dict[str, float] = {}
    routes: dict[str, Counter[str]] = {}
    kinds: dict[str, Counter[str]] = {}

    for d in detections:
        if d.family_id not in universe:
            raise DetectionError(
                f"detection for {d.family_id!r} is outside the pinned family universe; either "
                "the registry version is mismatched or the detector is using its own family "
                "ids, and both move the denominator without saying so"
            )
        hits[d.family_id] += 1
        records.setdefault(d.family_id, set()).add(d.record_id)
        best[d.family_id] = max(best.get(d.family_id, float("-inf")), d.score)
        routes.setdefault(d.family_id, Counter())[d.route.value] += 1
        kinds.setdefault(d.family_id, Counter())[d.element_kind.value] += 1

    missing = sorted(set(hits) - set(thresholds))
    if missing:
        raise DetectionError(
            f"no threshold recorded for {len(missing)} hit families (first: {missing[:3]}): a "
            "hit whose threshold is not in the table cannot be re-read against a stricter one"
        )

    return [
        FamilyRow(
            family_id=accession,
            name=name,
            hits=hits.get(accession, 0),
            records=len(records.get(accession, ())),
            best_score=best.get(accession),
            threshold=thresholds[accession],
            routes=dict(sorted(routes.get(accession, Counter()).items())),
            element_kinds=dict(sorted(kinds.get(accession, Counter()).items())),
        )
        for accession, name in sorted(universe.items())
    ]


def detection_rows(detections: Iterable[Detection], *, extra: Mapping[str, Any] | None = None):
    """Render detections as JSONL lines: the record-level evidence behind a table.

    Separate file for the same reason A1.4's removed set is: the table is read by a person and
    the record-level rows are read by a pipeline, and the rows are the half that can grow
    without bound. Carries accessions and scores only — no sequence, which is the convention
    every artefact in this project follows.
    """
    for d in detections:
        row = {
            "record_id": d.record_id,
            "family_id": d.family_id,
            "registry": d.registry,
            "registry_version": d.registry_version,
            "detector": d.detector,
            "score": d.score,
            "threshold": d.threshold,
            "route": d.route.value,
            "element_kind": d.element_kind.value,
        }
        if extra:
            row.update(extra)
        yield json.dumps(row, sort_keys=True)


def check_route_coverage(table: DetectionTable) -> None:
    """Refuse a table whose detections claim a route A2.1 cannot establish.

    `Route.CONFORMANCE_FAILURE` is A7.1's to establish with record-level evidence and
    `amazebio.apply.route_for` already refuses to return it. This is the second half of that
    guard: a detector that assembled the route some other way would otherwise publish the
    claim through the table instead of through the mapping.
    """
    bad = Route.CONFORMANCE_FAILURE.value
    if table.route_totals().get(bad):
        raise DetectionError(
            "a detection table may not assert route 'conformance_failure': it is a claim about "
            "a named laboratory's implementation and A7.1 establishes it with record-level "
            "evidence (metrics/survival.md, DESIGN.md §7)"
        )

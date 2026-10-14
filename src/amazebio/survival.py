"""Survival routes and the frozen headline metrics — task A3.1.

The prose specification is `metrics/survival.md` and it is the authoritative text. This module
is the machine-readable half: the route taxonomy every A2 detector must tag its output with,
and a reference implementation of the metric definitions small enough that the worked examples
in the specification can be pinned by tests.

Read the specification before changing anything here. The definitions are frozen (DECISIONS.md
D-022) because `DESIGN.md` §A3 makes family-level survival the headline number and `AGENTS.md`
requires thresholds and analysis specs to be fixed before results are inspected. A metric
redefined after the counts are in is not a metric, it is an outcome.

Two classifications live here and they are not interchangeable:

**Route** (:class:`Route`) is filter-side: *why* this sequence is still in the corpus. It is a
partition — every detection carries exactly one route — and DECISIONS.md D-007 requires
:attr:`Route.OUT_OF_SCOPE` to be first-class, separate both from what the filter examined and
could not detect and from what it kept deliberately. Those three claims have different
remedies and collapsing them would blur the strongest Phase A finding into the weakest.

**Element kind** (:class:`ElementKind`) is biology-side: *what* the surviving sequence is. It is
reported as a cross-tabulation against route, never as a route itself. A prophage in a bacterial
genome the filter never looked at is `PROPHAGE` by kind and `OUT_OF_SCOPE` by route; a prophage
in a record the filter examined and kept is the same kind on a different route, and the
difference is the entire point.

The corpus-scale computation is A3.2 and the independent second implementation is A3.3, which
reads `metrics/survival.md` rather than this file — so keep the specification complete enough to
work from alone.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from enum import Enum

__all__ = [
    "Detection",
    "ElementKind",
    "Interval",
    "Route",
    "SurvivalError",
    "family_survival",
    "surviving_counts_by_family",
    "wilson_interval",
]

# 95% two-sided normal quantile. Declared as a constant because the confidence level is part of
# the frozen specification, not a caller's choice: a figure mixing 90% and 95% intervals is
# unreadable and the shipped tool must report one level everywhere.
Z_95 = 1.959963984540054


class SurvivalError(Exception):
    """Raised when a metric is asked for on input the specification does not define it over."""


class Route(Enum):
    """Why a surviving sequence is still in the corpus. Exactly one per detection.

    The order of declaration is the reporting order in `metrics/survival.md`: it runs from the
    claim that needs no new bioinformatics to establish to the claim that needs the most.
    """

    OUT_OF_SCOPE = "out_of_scope"
    """The record's corpus component was never examined by the filter.

    Determined from the policy spec's declared scope (`amazebio.policyspec.Scope`), not inferred
    from whether anything was removed. First-class per D-007: this is the headline Phase A
    finding and it is established from published methods rather than from detection.
    """

    RETAINED_BY_DESIGN = "retained_by_design"
    """In scope, examined, and the filter's own stated rules keep it.

    Prokaryotic-host phage in IMG/VR is the worked case: retention is a published decision, so
    counting it as leakage would be misreading the policy rather than auditing it. Reported
    because it is the within-corpus contrast Phase B needs, never as a failure.
    """

    UNDETECTED = "undetected"
    """In scope, the stated rule reaches it, but the filter's mechanism could not see it.

    No taxonomic label, a label too unspecific to place, or similarity below the policy's
    threshold. The filter's blind spot, and A4 sizes it.
    """

    MISASSIGNED = "misassigned"
    """In scope and labelled, but labelled wrongly, so the rule did not fire.

    Separate from :attr:`UNDETECTED` because the remedy differs: this one is a property of the
    taxonomy tool, which A4.2 benchmarks directly.
    """

    CONFORMANCE_FAILURE = "conformance_failure"
    """In scope, labelled, the stated rule should have fired, and it did not.

    A claim about a named laboratory's implementation rather than about taxonomy's limits, so it
    is never merged into another route and never reported without the record-level evidence.
    A7.1 is the task that establishes it; §7 requires it to be airtight.
    """

    UNRESOLVED = "unresolved"
    """Route cannot be determined from the metadata that travels with the release.

    Not a residual bucket to be tidied away. A1.2 established that three of Evo 1's published
    rules cannot be checked from the released corpus because their inputs — the
    high-confidence flag, the vOTU representative, the prokaryotic-host count — are not in the
    records. Detections turning on those rules land here and are reported as their own row, so
    a reader sees the limit of the evidence instead of a cleaner table than we can support.
    """


class ElementKind(Enum):
    """What the surviving sequence is. Cross-tabulated against :class:`Route`, never a route."""

    FREE_VIRUS = "free_virus"
    PROPHAGE = "prophage"
    ENDOGENOUS_RETROELEMENT = "endogenous_retroelement"
    NON_RETROVIRAL_EVE = "non_retroviral_eve"
    SATELLITE = "satellite"
    VIRAL_DERIVED_FRAGMENT = "viral_derived_fragment"
    UNCLASSIFIED_ELEMENT = "unclassified_element"


@dataclasses.dataclass(frozen=True, slots=True)
class Detection:
    """One surviving sequence matched to one family, as every A2 detector must emit it.

    `registry` and `registry_version` are carried per detection rather than per run because the
    headline is reported once per registry and never pooled across them (DECISIONS.md D-022),
    and a pooled number assembled by accident is exactly the failure the separation prevents.
    """

    family_id: str
    registry: str
    registry_version: str
    record_id: str
    route: Route
    element_kind: ElementKind
    detector: str
    score: float
    threshold: float

    def __post_init__(self) -> None:
        if self.score < self.threshold:
            raise SurvivalError(
                f"{self.detector} detection for {self.family_id} scores {self.score}, "
                f"below its declared threshold {self.threshold}: a detection below threshold "
                "is not a detection, and dropping it here rather than at the detector would "
                "hide a threshold mismatch between the two"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with its interval. Nothing in this project ships one without the other."""

    estimate: float
    low: float
    high: float
    method: str


def wilson_interval(successes: int, trials: int, *, z: float = Z_95) -> Interval:
    """Wilson score interval for a proportion.

    Wilson rather than the normal approximation because family-level survival is expected at
    both ends of the range — a filter that works puts it near zero and a filter that does not
    puts it near one — and the normal interval is worthless there, straying outside [0, 1] and
    collapsing to zero width at exactly the values the audit is most likely to report.
    """
    if trials <= 0:
        raise SurvivalError(
            "a proportion over an empty family universe is undefined; an empty universe means "
            "the registry was not pinned correctly, which is a setup error, not a result"
        )
    if not 0 <= successes <= trials:
        raise SurvivalError(f"successes {successes} outside 0..{trials}")

    n = float(trials)
    centre = (successes + z * z / 2) / (n + z * z)
    half = (z / (n + z * z)) * math.sqrt(successes * (n - successes) / n + z * z / 4)

    # At the extremes the exact bound is the endpoint, and floating point lands a few ulps off
    # it — 1.4e-17 rather than 0. Pinned rather than clamped because "no family survived, lower
    # bound 1.4e-17" is the headline this project most needs to report cleanly.
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == trials else min(1.0, centre + half)
    return Interval(estimate=successes / n, low=low, high=high, method=f"wilson_z{z:.6f}")


def surviving_counts_by_family(
    detections: tuple[Detection, ...] | list[Detection],
    *,
    family_universe: Mapping[str, object] | frozenset[str] | set[str],
) -> dict[str, int]:
    """Surviving sequence count per family, zero-filled across the whole pinned universe.

    Zero-filling is load-bearing. A family with no surviving sequence is the result the audit is
    testing for, and a count table built only from the detections that happened would drop those
    families and make a null look like missing data. `AGENTS.md` is explicit that nothing in the
    pipeline may be designed so the null is harder to see.
    """
    universe = frozenset(family_universe)
    counts = dict.fromkeys(universe, 0)
    for d in detections:
        if d.family_id not in universe:
            raise SurvivalError(
                f"detection for {d.family_id!r} is not in the pinned family universe; either "
                "the registry version is mismatched or the detector is using its own family "
                "ids, and both change the denominator silently"
            )
        counts[d.family_id] += 1
    return counts


def family_survival(counts: Mapping[str, int]) -> Interval:
    """Family-level survival: the fraction of families with at least one surviving homolog.

    The headline metric of `DESIGN.md` §A3. `counts` must already be zero-filled across the
    pinned family universe — see :func:`surviving_counts_by_family` — because this function
    reads its denominator from the mapping it is given and cannot tell a pinned zero from an
    absent key.
    """
    return wilson_interval(sum(1 for n in counts.values() if n >= 1), len(counts))

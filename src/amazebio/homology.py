"""The homology axis: §B3's three measures in one shape. Tasks B3.1, B3.2, B3.3.

`metrics/homology.md` is the contract and this module is its only producer. The split between
the two is the same one `metrics/depth.md` and :mod:`amazebio.neff` keep: the file states what a
row means so that B3.5 and B5 can be written against it without reading this code, and this
module refuses to emit a row the file does not describe.

Three things here are load-bearing rather than convenience.

**A score and its kind travel together, and the type enforces it.** §B3's measures are produced
at different depths by different instruments, and the failure this axis is most exposed to is a
consumer reading "no hit" as a zero. :class:`Row` raises on a `score` beside any `kind` but
`measured`, and on a `measured` row with no score, so the distinction cannot be lost by a
careless constructor call rather than by a decision.

**The bound is derived from the depth, never passed in.** A best hit over a sample cannot
exceed the best hit over the whole corpus, so a sampled row is a floor whether or not its
producer remembered to say so. :func:`bound_for` is the one place that reasoning lives.

**The acceptance rule is A2.1's, imported rather than restated.** A target-derived profile has
no curated cutoff, so the inclusion threshold is `profiles.PINNED_E_VALUE` against
`profiles.PINNED_Z` — a fixed per-model bit score, independent of how much corpus a run read
(D-076) — held to `profiles.MIN_MODEL_COVERAGE` of the profile's length. Restating those
numbers here would let the two drift and leave B3's hits incomparable with A2.1's.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from amazebio.profiles import MIN_MODEL_COVERAGE, PINNED_E_VALUE, PINNED_Z

__all__ = [
    "KINDS",
    "MEASURES",
    "MIN_MODEL_COVERAGE",
    "PINNED_E_VALUE",
    "PINNED_Z",
    "HomologyError",
    "Row",
    "Target",
    "bit_threshold",
    "bound_for",
    "normalise",
    "rows_by_target",
]


class HomologyError(ValueError):
    """A row, target or parameter that `metrics/homology.md` does not describe."""


#: The three measures, in §B3's own order. `structural` is the pre-registered primary; the
#: order here is the design's and carries no precedence of its own.
MEASURES = ("sequence_profile", "domain_presence", "structural")

#: How to read a row's `score`. `metrics/homology.md` has the table; the short of it is that
#: only `measured` carries a number and the other three carry a reason.
KINDS = ("measured", "absent", "not_searched", "unanswerable")

#: Measures whose `normalised` value is defined. `structural` has none: the scale the measure
#: would be reported on is already length-independent, and no manifest has been searched for it.
_NORMALISED = {"sequence_profile", "domain_presence"}


def bit_threshold(
    profile_length: int | None = None,
    *,
    mu: float,
    lambda_: float,
    e_value: float = PINNED_E_VALUE,
    z: int = PINNED_Z,
) -> float:
    """The bit score corresponding to `e_value` against a database of `z` sequences.

    HMMER's Gumbel tail for a local alignment score: `E = z * exp(-lambda * (bits - mu))`,
    inverted. Pinning `z` rather than taking the searched count is the whole point — it makes
    the cut a property of the profile instead of a property of how much corpus this run read,
    which is D-076's rule stated as arithmetic.

    `profile_length` is accepted and unused, so a caller can pass the profile it is cutting
    without the signature implying the cut depends on its length. It does not.
    """
    if e_value <= 0 or z <= 0:
        raise HomologyError("e_value and z must both be positive")
    if lambda_ <= 0:
        raise HomologyError("lambda must be positive")
    return mu - math.log(e_value / z) / lambda_


@dataclasses.dataclass(frozen=True)
class Target:
    """One assay target, as B2.4's register and B2.1's reference file describe it.

    `alignment` is the alignment B3.4 resolved for this target, or `None` where its maintainers
    distribute none. A target with no alignment has no profile, so its `sequence_profile` row is
    `unanswerable` rather than `absent` — nothing was looked for, and the two are not the same
    statement about surviving space.
    """

    dms_id: str
    uniprot_id: str | None
    length: int
    alignment: str | None = None

    def __post_init__(self) -> None:
        if not self.dms_id:
            raise HomologyError("a target needs its register key")
        if self.length <= 0:
            raise HomologyError(f"{self.dms_id}: target length must be positive")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def bound_for(searched_fraction: float) -> str:
    """What a row is relative to the same measure at census depth.

    A census is `none`. Anything less is `lower`, for both kinds that carry a verdict: the best
    hit over a sample cannot exceed the best hit over the whole, and "not found in a sample" is
    not "not present". There is no case in this axis that produces an upper bound, and `upper`
    stays in the contract's vocabulary rather than this function's so that a later measure which
    does produce one is not forced to redefine the field.
    """
    if not 0.0 < searched_fraction <= 1.0:
        raise HomologyError(f"searched_fraction out of range: {searched_fraction!r}")
    return "none" if searched_fraction == 1.0 else "lower"


def normalise(measure: str, score: float, target: Target, *, over: int | None = None) -> float:
    """The length-normalised value `metrics/homology.md` defines for `measure`.

    `sequence_profile` is bits per residue of the query, which is the normalisation §B3 item 1
    asks for. `domain_presence` is the count of families present over `over`, the number
    annotated, so a single-domain and a six-domain target are comparable.
    """
    if measure == "sequence_profile":
        return score / target.length
    if measure == "domain_presence":
        if not over:
            raise HomologyError(
                f"{target.dms_id}: domain_presence needs the annotated family count to "
                "normalise over; a target with none is unanswerable, not a zero denominator"
            )
        return score / over
    raise HomologyError(f"{measure!r} has no normalised value")


@dataclasses.dataclass(frozen=True)
class Row:
    """One target x manifest x measure, in the shape `metrics/homology.md` specifies."""

    dms_id: str
    uniprot_id: str | None
    target_length: int
    policy: str
    release: str
    measure: str
    kind: str
    score: float | None
    normalised: float | None
    searched_fraction: float
    bound: str
    reason: str | None
    params: Mapping[str, Any]
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.measure not in MEASURES:
            raise HomologyError(f"unknown measure {self.measure!r}")
        if self.kind not in KINDS:
            raise HomologyError(f"unknown kind {self.kind!r}")
        if self.kind == "measured":
            if self.score is None:
                raise HomologyError(f"{self.dms_id}/{self.measure}: measured with no score")
            if self.measure in _NORMALISED and self.normalised is None:
                raise HomologyError(
                    f"{self.dms_id}/{self.measure}: measured with no normalised value, and "
                    "this measure defines one"
                )
        else:
            if self.score is not None or self.normalised is not None:
                raise HomologyError(
                    f"{self.dms_id}/{self.measure}: kind {self.kind!r} carries a score. "
                    "Only `measured` does; an absent hit is a censored observation at the "
                    "cut and never a number (metrics/homology.md)"
                )
            if not self.reason:
                raise HomologyError(
                    f"{self.dms_id}/{self.measure}: kind {self.kind!r} needs its reason"
                )
        if self.bound != bound_for(self.searched_fraction):
            raise HomologyError(
                f"{self.dms_id}/{self.measure}: bound {self.bound!r} does not follow from "
                f"searched_fraction {self.searched_fraction!r}"
            )

    @classmethod
    def measured(
        cls,
        target: Target,
        *,
        policy: str,
        release: str,
        measure: str,
        score: float,
        searched_fraction: float,
        params: Mapping[str, Any],
        evidence: Mapping[str, Any],
        normalise_over: int | None = None,
    ) -> Row:
        normalised = (
            normalise(measure, score, target, over=normalise_over)
            if measure in _NORMALISED
            else None
        )
        return cls(
            dms_id=target.dms_id,
            uniprot_id=target.uniprot_id,
            target_length=target.length,
            policy=policy,
            release=release,
            measure=measure,
            kind="measured",
            score=score,
            normalised=normalised,
            searched_fraction=searched_fraction,
            bound=bound_for(searched_fraction),
            reason=None,
            params=dict(params),
            evidence=dict(evidence),
        )

    @classmethod
    def without_score(
        cls,
        target: Target,
        *,
        policy: str,
        release: str,
        measure: str,
        kind: str,
        reason: str,
        searched_fraction: float,
        params: Mapping[str, Any],
        evidence: Mapping[str, Any] | None = None,
    ) -> Row:
        if kind == "measured":
            raise HomologyError("use Row.measured for a row that carries a score")
        return cls(
            dms_id=target.dms_id,
            uniprot_id=target.uniprot_id,
            target_length=target.length,
            policy=policy,
            release=release,
            measure=measure,
            kind=kind,
            score=None,
            normalised=None,
            searched_fraction=searched_fraction,
            bound=bound_for(searched_fraction),
            reason=reason,
            params=dict(params),
            evidence=dict(evidence or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def rows_by_target(rows: Iterable[Row]) -> Iterator[tuple[str, tuple[Row, ...]]]:
    """Group rows by assay, in first-seen order.

    Per-assay before pooled is §B5's presentation rule and `metrics/homology.md` applies it to
    this artefact's own output, so grouping by target is provided and pooling is not.
    """
    grouped: dict[str, list[Row]] = {}
    for row in rows:
        grouped.setdefault(row.dms_id, []).append(row)
    for dms_id, group in grouped.items():
        yield dms_id, tuple(group)


def check_complete(
    rows: Sequence[Row],
    *,
    targets: Sequence[Target],
    manifests: Sequence[tuple[str, str]],
) -> None:
    """Refuse an artefact that is missing a cell, which is what both Done-whens ask for.

    "Scores computed for all targets against all manifests" is checkable, and a silently short
    table is the failure mode D-245 found four shape checks blind to: every row well-formed and
    the set of rows wrong. A missing cell raises here rather than being noticed downstream.
    """
    want = {
        (t.dms_id, policy, release, measure)
        for t in targets
        for policy, release in manifests
        for measure in MEASURES
    }
    have = {(r.dms_id, r.policy, r.release, r.measure) for r in rows}
    if len(have) != len(rows):
        raise HomologyError("duplicate target x manifest x measure rows")
    missing = want - have
    if missing:
        example = ", ".join("/".join(m) for m in sorted(missing)[:3])
        raise HomologyError(f"{len(missing)} cells missing, e.g. {example}")
    extra = have - want
    if extra:
        example = ", ".join("/".join(m) for m in sorted(extra)[:3])
        raise HomologyError(f"{len(extra)} rows outside the declared grid, e.g. {example}")

"""Taxonomy-tool error, in the terms a filter's leakage is made of (DESIGN.md §A4).

A label-based filter does not act on a sequence. It acts on a *label*, which some tool
attached to that sequence, and it removes the record if the label names a taxon on a list.
So the filter's behaviour is the composition of two things: the rule, which A1.4 and A7.1
have already executed, and the labelling, which no one has checked. This module is the
vocabulary for the second one.

The central move is to refuse to report a single accuracy figure. "geNomad is 94% accurate
at family" is not a statement about a filter, because the two ways of being wrong have
opposite consequences and land on different people:

* **Escape** — the record's true family is on the denylist, and the label does not put it
  there, so the record survives a filter that was written to remove it. This is leakage. It
  is the direction the audit exists to measure, and it is the direction a developer's own
  validation is least likely to look for, because the filter reports success.
* **Spurious removal** — the record's true family is *not* on the denylist, and the label
  puts it there anyway, so a record the policy never meant to touch is deleted. This is a
  cost rather than a hazard, and it is what makes a filter look thorough while it removes
  the wrong things.

Both are errors of the same tool and neither is recoverable from the other, so
:func:`classify` returns the direction, and :func:`rates` reports the two separately with
intervals. A pooled "accuracy" is deliberately not offered by this module.

**Escape has causes, and they are not interchangeable.** A record escapes because the label
is absent at the rank the rule reads, because the label stops at a shallower rank, because
the label names the wrong family, or because the tool never called the sequence viral at
all. The first two are under-assignment, which a filter author could in principle detect by
counting blanks; the third is confident and wrong, which they could not. §A4 asks for the
breakdown by direction, and :data:`ESCAPE_CAUSES` is the finer split underneath it.

One asymmetry to keep in view when reading the rates. Under-assignment and misassignment
both cause escape, but only under-assignment is visible in the corpus as a missing field —
which is exactly what A4.1 measured as the filter's ceiling. The part of leakage this module
adds to that ceiling is the part A4.1 could not see: records that *are* labelled at family,
confidently, and labelled wrongly.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ASSIGNMENT_OUTCOMES",
    "DIRECTIONS",
    "ESCAPE_CAUSES",
    "Denylist",
    "Judgement",
    "classify",
    "clopper_pearson",
    "propagate",
    "rates",
]

#: How a prediction stands to the truth at one rank. Frozen vocabulary: the artefact is
#: keyed on these strings and a renamed outcome silently breaks every comparison with an
#: earlier run.
ASSIGNMENT_OUTCOMES: tuple[str, ...] = (
    "correct",  # predicted name at this rank equals the ratified name
    "wrong",  # both present, and they differ
    "absent",  # the tool left this rank empty
    "unclassified",  # the tool returned no lineage at all
    "not_viral",  # the tool did not call the sequence viral
)

#: What the filter does, against what the policy meant it to do. The two error directions
#: are `escape` and `spurious_removal`; the other two are the filter working.
DIRECTIONS: tuple[str, ...] = (
    "correct_removal",
    "correct_retention",
    "escape",
    "spurious_removal",
)

#: Why a record that should have been removed was not. Reported underneath `escape`.
ESCAPE_CAUSES: tuple[str, ...] = (
    "absent_at_rule_ranks",  # labelled, but not at family or order
    "shallower_than_rule",  # labelled at order only, and that order is not denylisted
    "misassigned_family",  # labelled at family, wrong family, not denylisted
    "misassigned_order",  # labelled at order, wrong order, not denylisted
    "unclassified",  # no lineage at all
    "not_viral",  # not called viral, so never reaches the taxonomy rules
)


@dataclass(frozen=True)
class Denylist:
    """The taxa a policy's remove-rules name, and the ranks they read.

    Constructed from a loaded policy rather than typed out again: `AGENTS.md` and D-057
    both treat a fact declared twice as a defect, and the denylist is already the policy
    specs' content. :meth:`from_policy` is the only intended constructor.
    """

    families: frozenset[str]
    orders: frozenset[str]
    policy: str = ""

    @classmethod
    def from_policy(cls, policy: Any, *, name: str = "") -> Denylist:
        """Read the family and order denylists out of a loaded `policyspec.Policy`.

        Reads every `remove_if_taxon_in` rule and groups its names by the rank the rule
        declares, so a policy that adds a third rank, or moves a taxon between ranks (which
        D-071 found one release had done), is picked up without editing this function.
        """
        by_rank: dict[str, set[str]] = {}
        for rule in getattr(policy, "rules", ()):
            if getattr(rule, "kind", "") != "remove_if_taxon_in":
                continue
            params = getattr(rule, "params", {}) or {}
            rank = params.get("rank")
            names = params.get("names") or ()
            if not isinstance(rank, str) or not isinstance(names, list | tuple | set):
                continue
            by_rank.setdefault(rank, set()).update(str(n) for n in names)
        unexpected = set(by_rank) - {"family", "order"}
        if unexpected:
            raise ValueError(
                f"policy {name or getattr(policy, 'id', '?')!r} denylists taxa at "
                f"rank(s) {sorted(unexpected)}, which this benchmark does not read. "
                "Extend `Denylist` and the evaluation set before reporting a rate."
            )
        return cls(
            families=frozenset(by_rank.get("family", ())),
            orders=frozenset(by_rank.get("order", ())),
            policy=name or str(getattr(policy, "id", "")),
        )

    @property
    def ranks(self) -> tuple[str, ...]:
        return ("family", "order")

    def covers(self, lineage: Mapping[str, str]) -> bool:
        """Whether these rules would remove a record carrying `lineage`."""
        return (lineage.get("family", "") in self.families and bool(lineage.get("family"))) or (
            lineage.get("order", "") in self.orders and bool(lineage.get("order"))
        )


@dataclass(frozen=True)
class Judgement:
    """One record scored: what the tool said, what the ICTV says, and the consequence."""

    record: str
    species: str
    true_family: str
    true_order: str
    predicted_family: str
    predicted_order: str
    family_outcome: str
    order_outcome: str
    should_remove: bool
    removed: bool
    direction: str
    escape_cause: str | None
    length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.record,
            "species": self.species,
            "true_family": self.true_family,
            "true_order": self.true_order,
            "predicted_family": self.predicted_family,
            "predicted_order": self.predicted_order,
            "family_outcome": self.family_outcome,
            "order_outcome": self.order_outcome,
            "should_remove": self.should_remove,
            "removed": self.removed,
            "direction": self.direction,
            "escape_cause": self.escape_cause,
            "length": self.length,
        }


def _outcome(predicted: str, truth: str, *, viral: bool, any_lineage: bool) -> str:
    if not viral:
        return "not_viral"
    if not any_lineage:
        return "unclassified"
    if not predicted:
        return "absent"
    return "correct" if predicted == truth else "wrong"


def classify(
    *,
    record: str,
    species: str,
    true_lineage: Mapping[str, str],
    predicted_lineage: Mapping[str, str],
    denylist: Denylist,
    called_viral: bool = True,
    length: int | None = None,
) -> Judgement:
    """Score one record against the ratified lineage.

    `predicted_lineage` is the tool's output, already parsed to `{rank: name}`; an empty
    mapping means the tool returned no lineage. `called_viral` is separate from an empty
    lineage on purpose: a sequence the tool does not call viral never reaches the taxonomy
    rules at all, and counting that as "unlabelled" would attribute to the taxonomy step an
    escape that happened one step earlier.
    """
    any_lineage = any(v for v in predicted_lineage.values())
    true_family = true_lineage.get("family", "")
    true_order = true_lineage.get("order", "")
    predicted_family = predicted_lineage.get("family", "") if called_viral else ""
    predicted_order = predicted_lineage.get("order", "") if called_viral else ""

    family_outcome = _outcome(
        predicted_family, true_family, viral=called_viral, any_lineage=any_lineage
    )
    order_outcome = _outcome(
        predicted_order, true_order, viral=called_viral, any_lineage=any_lineage
    )

    should_remove = denylist.covers(true_lineage)
    removed = called_viral and denylist.covers(
        {"family": predicted_family, "order": predicted_order}
    )

    if should_remove and removed:
        direction = "correct_removal"
    elif should_remove and not removed:
        direction = "escape"
    elif not should_remove and removed:
        direction = "spurious_removal"
    else:
        direction = "correct_retention"

    cause: str | None = None
    if direction == "escape":
        if not called_viral:
            cause = "not_viral"
        elif not any_lineage:
            cause = "unclassified"
        elif predicted_family and predicted_family != true_family:
            cause = "misassigned_family"
        elif predicted_order and predicted_order != true_order:
            cause = "misassigned_order"
        elif predicted_order and not predicted_family:
            cause = "shallower_than_rule"
        else:
            cause = "absent_at_rule_ranks"

    return Judgement(
        record=record,
        species=species,
        true_family=true_family,
        true_order=true_order,
        predicted_family=predicted_family,
        predicted_order=predicted_order,
        family_outcome=family_outcome,
        order_outcome=order_outcome,
        should_remove=should_remove,
        removed=removed,
        direction=direction,
        escape_cause=cause,
        length=length,
    )


# --------------------------------------------------------------------------------------
# Intervals
# --------------------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float, *, iterations: int = 400) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """`I_x(a, b)`, the regularized incomplete beta function.

    Implemented here rather than imported because the project's pinned environment carries
    no scientific-stack dependency, and an exact binomial interval is not something to
    approximate away: the per-family counts in this benchmark are small, several are zero,
    and a normal approximation puts a zero-error family's upper bound at zero, which would
    report a certainty the data does not contain.
    """
    if not 0.0 <= x <= 1.0:
        raise ValueError(f"x must be in [0, 1], got {x}")
    if x in (0.0, 1.0):
        return x
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return (
        1.0
        - math.exp(
            math.lgamma(a + b)
            - math.lgamma(a)
            - math.lgamma(b)
            + b * math.log1p(-x)
            + a * math.log(x)
        )
        * _betacf(b, a, 1.0 - x)
        / b
    )


def _beta_quantile(p: float, a: float, b: float) -> float:
    """Inverse of :func:`regularized_incomplete_beta` in `x`, by bisection.

    Bisection rather than Newton: 200 halvings reach 1e-15 on a bounded interval, the
    function is monotone in `x`, and there is no derivative to get wrong. The cost is
    irrelevant — this is called a few hundred times per run, not per record.
    """
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if regularized_incomplete_beta(a, b, mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def clopper_pearson(
    successes: int, trials: int, *, confidence: float = 0.95
) -> tuple[float, float]:
    """Exact (Clopper-Pearson) binomial confidence interval for `successes / trials`.

    Returns `(lower, upper)`. The endpoints are the conventional ones: `0` is the lower
    bound when there are no successes and `1` the upper bound when every trial succeeds,
    because the interval is one-sided there rather than degenerate.

    `trials == 0` raises. A rate over an empty denominator is not a wide interval, it is
    the absence of a measurement, and returning `(0, 1)` for it would let an unmeasured
    family appear in a results table as though it had been tested.
    """
    if trials <= 0:
        raise ValueError("no trials: a rate over an empty denominator is not a measurement")
    if not 0 <= successes <= trials:
        raise ValueError(f"successes={successes} outside 0..{trials}")
    alpha = 1.0 - confidence
    lower = (
        0.0
        if successes == 0
        else _beta_quantile(alpha / 2.0, float(successes), float(trials - successes + 1))
    )
    upper = (
        1.0
        if successes == trials
        else _beta_quantile(1.0 - alpha / 2.0, float(successes + 1), float(trials - successes))
    )
    return lower, upper


# --------------------------------------------------------------------------------------
# Rates
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rate:
    """A proportion with the interval that travels with it (`AGENTS.md`)."""

    label: str
    numerator: int
    denominator: int
    lower: float
    upper: float

    @property
    def point(self) -> float:
        return self.numerator / self.denominator

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "point": self.point,
            "ci_lower": self.lower,
            "ci_upper": self.upper,
        }


def rate(label: str, numerator: int, denominator: int, *, confidence: float = 0.95) -> Rate:
    low, high = clopper_pearson(numerator, denominator, confidence=confidence)
    return Rate(label=label, numerator=numerator, denominator=denominator, lower=low, upper=high)


def rates(
    judgements: Iterable[Judgement], *, confidence: float = 0.95
) -> dict[str, dict[str, Any]]:
    """The two error rates, each over the population it is a rate *of*.

    The denominators are the point of this function. An escape rate is a proportion of the
    records the policy meant to remove, and a spurious-removal rate a proportion of the
    records it meant to keep; dividing either by the whole evaluation set would produce a
    number that moves when the control set is resized, which is a property of the
    experiment rather than of the tool.
    """
    items = list(judgements)
    should_remove = [j for j in items if j.should_remove]
    should_retain = [j for j in items if not j.should_remove]
    out: dict[str, dict[str, Any]] = {}
    if should_remove:
        escapes = sum(1 for j in should_remove if j.direction == "escape")
        out["escape"] = rate(
            "escape (of records the policy meant to remove)",
            escapes,
            len(should_remove),
            confidence=confidence,
        ).to_dict()
        causes: dict[str, int] = {c: 0 for c in ESCAPE_CAUSES}
        for j in should_remove:
            if j.direction == "escape" and j.escape_cause:
                causes[j.escape_cause] += 1
        out["escape"]["causes"] = causes
    if should_retain:
        spurious = sum(1 for j in should_retain if j.direction == "spurious_removal")
        out["spurious_removal"] = rate(
            "spurious removal (of records the policy meant to keep)",
            spurious,
            len(should_retain),
            confidence=confidence,
        ).to_dict()
    out["counts"] = {
        "records": len(items),
        "should_remove": len(should_remove),
        "should_retain": len(should_retain),
        **{d: sum(1 for j in items if j.direction == d) for d in DIRECTIONS},
    }
    return out


def per_family(
    judgements: Iterable[Judgement], *, confidence: float = 0.95, minimum: int = 1
) -> dict[str, dict[str, Any]]:
    """Escape rate per true family.

    Per-family before pooled, which `AGENTS.md` makes the default presentation everywhere:
    a pooled escape rate over this evaluation set is weighted by how many species the ICTV
    has ratified in each family, and that is a fact about taxonomic effort rather than
    about the tool. `Geminiviridae` alone contributes a fifth of the in-scope exemplars.
    """
    grouped: dict[str, list[Judgement]] = {}
    for j in judgements:
        if j.should_remove:
            grouped.setdefault(j.true_family or f"(order:{j.true_order})", []).append(j)
    out: dict[str, dict[str, Any]] = {}
    for family, items in sorted(grouped.items()):
        if len(items) < minimum:
            continue
        escapes = sum(1 for j in items if j.direction == "escape")
        entry = rate(family, escapes, len(items), confidence=confidence).to_dict()
        entry["causes"] = {
            c: sum(1 for j in items if j.escape_cause == c)
            for c in ESCAPE_CAUSES
            if any(j.escape_cause == c for j in items)
        }
        out[family] = entry
    return out


def propagate(
    *,
    escape: Mapping[str, Any],
    corpus_records: int,
    in_scope_records: int,
    label: str = "",
) -> dict[str, Any]:
    """Turn an escape rate into a count of records the filter was meant to remove and did not.

    This is the step §A4 asks for — "state how tool error propagates into filter leakage" —
    and it is where the benchmark's bias has to be carried rather than dropped. The rate is
    measured on complete reference genomes and applied to a corpus of assembly fragments,
    so the product is a **lower bound** on leakage from this cause: a fragment carries fewer
    marker genes than the genome it came from, and a marker-based classifier that is given
    less evidence assigns a shallower lineage, which is the first escape cause in
    :data:`ESCAPE_CAUSES`. The returned dict says so in a field rather than in a comment,
    because the number is what gets quoted.

    `in_scope_records` is the count of corpus records whose true taxon the policy meant to
    remove. It is not observable — knowing it exactly would require the ground truth this
    benchmark exists because the corpus lacks — so a caller passes an estimate and the
    result records it as an input, not as a finding.
    """
    point = float(escape["point"])
    low = float(escape["ci_lower"])
    high = float(escape["ci_upper"])
    return {
        "label": label,
        "escape_rate": {"point": point, "ci_lower": low, "ci_upper": high},
        "in_scope_records": in_scope_records,
        "corpus_records": corpus_records,
        "escaping_records": {
            "point": point * in_scope_records,
            "ci_lower": low * in_scope_records,
            "ci_upper": high * in_scope_records,
        },
        "share_of_corpus": {
            "point": point * in_scope_records / corpus_records if corpus_records else None,
        },
        "bound": "lower",
        "bound_reason": (
            "The escape rate is measured on complete reference genomes and applied to a "
            "corpus that is predominantly assembly fragments. A marker-based classifier "
            "given fewer markers assigns a shallower lineage, and a shallower lineage is "
            "itself an escape route, so the true rate on fragments is at least this one."
        ),
    }


def length_strata(
    judgements: Sequence[Judgement], *, edges: Sequence[int], confidence: float = 0.95
) -> list[dict[str, Any]]:
    """Escape rate by sequence length.

    The curve is what makes the benchmark transferable. A rate measured on whole genomes
    answers a question nobody asked — the corpus does not contain whole genomes — and the
    only honest way to carry a reference-genome result onto fragments is to measure how the
    rate moves as the evidence shrinks.
    """
    strata: list[dict[str, Any]] = []
    bounds = list(edges)
    for index, low_edge in enumerate(bounds):
        high_edge = bounds[index + 1] if index + 1 < len(bounds) else None
        bucket = [
            j
            for j in judgements
            if j.should_remove
            and j.length is not None
            and j.length >= low_edge
            and (high_edge is None or j.length < high_edge)
        ]
        if not bucket:
            continue
        escapes = sum(1 for j in bucket if j.direction == "escape")
        entry = rate(
            f"{low_edge}-{high_edge if high_edge else 'inf'}",
            escapes,
            len(bucket),
            confidence=confidence,
        ).to_dict()
        entry["low"] = low_edge
        entry["high"] = high_edge
        strata.append(entry)
    return strata

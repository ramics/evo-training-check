"""Applying policy specs to staged corpora at scale, and the manifests that come out — A1.4.

`amazebio.policyspec` holds the rule semantics and a reference evaluator over in-memory records.
This module is the corpus-scale half: it streams a staged release, resolves one verdict per
record, and writes the manifests A2.* and B3.* consume. The rule predicates are not restated
here — :func:`amazebio.policyspec.decide` is called for every rule, so there is one
implementation of what each kind means and A7.1 can reuse it unchanged.

Three decisions make this more than a loop, and each is in the project decision log (see `docs/working-record.md`).

**Resolution runs every applicable rule, rather than stopping at the first decision** (D-044).
The reference evaluator stops, which is how a filter implementation behaves. On a real release
that is wrong in a way that destroys the result: three of Evo's six rules read metadata the
release does not carry, and they come *first* in the published pipeline. Stopping at the first
undecidable rule would report every record in the corpus as unknown, including records the
denylist removes beyond any doubt. So every applicable rule runs and the outcomes resolve by
precedence:

    removed  >  undetermined  >  unresolved  >  retained

Removal wins because it is the only definite verdict: if any rule removes a record, the record
does not survive, whatever an earlier rule could not decide. Retention loses because it is
contingent — "no rule removed it" is only true if every rule was actually checked. Between the
two undecidable outcomes, the policy gap (`undetermined`, a parameter the developer never
published) outranks the corpus gap (`unresolved`, metadata the release does not ship), because
stating the parameter is a precondition for the corpus question even arising.

**A component is enumerated only when a rule can discriminate between its records**
(:func:`is_uniform`). If every rule reaching a component is undecidable there — no published
parameter, or no evidence in the release — then every record in it gets the same verdict, and
reading 101 GiB to write that verdict a billion times would be theatre. The uniform case is
recorded as a component-level verdict with its cause. The one exception is deliberate: a
component whose verdict is uniform *because the release carries no evidence* is still read when
that absence is a claim this audit makes, because an evidence declaration this project asserts
rather than verifies is the failure mode it exists to document. See `verify_absence`.

**Manifests carry the removed set record by record, and everything else by count** (D-045). The
surviving corpus is the released corpus minus what a reading removes, so the removed set is the
small, load-bearing half and the only one whose rows name individual records. It is also the
half §7 demands record-level evidence for: a record our reading says should not be in the
released corpus is a conformance claim about a named laboratory, and :func:`route_for` refuses
to convert it into `Route.CONFORMANCE_FAILURE` here precisely because that is A7.1's to
establish.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from amazebio.policyspec import Decision, Evidence, Outcome, Policy, Record, Rule, decide
from amazebio.survival import Route

__all__ = [
    "PRECEDENCE",
    "ManifestError",
    "PolicyManifest",
    "SourceVerdict",
    "applicable_rules",
    "is_uniform",
    "resolve",
    "route_for",
    "uniform_verdict",
]


class ManifestError(RuntimeError):
    """Raised when a manifest would record something it cannot support."""


#: Outcome precedence, strongest first. See the module docstring for why this order.
PRECEDENCE = (Outcome.REMOVED, Outcome.UNDETERMINED, Outcome.UNRESOLVED, Outcome.RETAINED)

_RANK = {outcome: i for i, outcome in enumerate(PRECEDENCE)}


# --------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------


def applicable_rules(policy: Policy, component: str) -> list[Rule]:
    """The policy's rules that reach `component`, in published order."""
    return [r for r in policy.rules if r.applies_to(component, scope=policy.scope)]


def resolve(
    policy: Policy,
    record: Record,
    *,
    evidence: Evidence,
    kept_values: dict[str, set] | None = None,
) -> Decision:
    """One verdict for one record, from every applicable rule rather than the first to fire.

    Returns the highest-precedence decision, and for a removal that is the *first* rule in
    published order that removes — so the attributed rule is the one a conformance claim would
    cite, not whichever happens to sort highest.
    """
    if not policy.scope.covers(record.component):
        return Decision(
            record.id,
            Outcome.OUT_OF_SCOPE,
            None,
            f"component {record.component!r} is not in this policy's scope "
            f"({', '.join(policy.scope.components)})",
        )
    kept = kept_values if kept_values is not None else {}
    best: Decision | None = None
    for rule in applicable_rules(policy, record.component):
        decision = decide(rule, record, kept_values=kept, evidence=evidence)
        if decision is None:
            continue
        if best is None or _RANK[decision.outcome] < _RANK[best.outcome]:
            best = decision
        if decision.outcome is Outcome.REMOVED:
            # Nothing outranks a removal, and the first one in published order is the one to
            # attribute, so stop rather than let a later removal overwrite it.
            break
    return best or Decision(record.id, Outcome.RETAINED, None, "no rule removed it")


def is_uniform(policy: Policy, component: str, evidence: Evidence) -> bool:
    """True when every record in `component` must get the same verdict.

    That holds when no rule reaches the component at all, or when every rule that reaches it is
    undecidable there — an unpublished parameter, or evidence the release does not carry. In
    either case no rule can read anything that varies between records, so enumerating them adds
    a count and nothing else.
    """
    rules = applicable_rules(policy, component)
    if not rules:
        return True
    return all(rule.unspecified_params() or evidence.missing_for(rule) for rule in rules)


def uniform_verdict(policy: Policy, component: str, evidence: Evidence) -> Decision:
    """The verdict every record in a uniform component gets, with its cause.

    Raises:
        ManifestError: if the component is not uniform. Calling this on a component where a
            rule discriminates would record one record's verdict as every record's.
    """
    if not is_uniform(policy, component, evidence):
        raise ManifestError(
            f"{policy.id}: component {component!r} has a rule that can discriminate between "
            "its records, so there is no single verdict for it — enumerate instead"
        )
    probe = Record(id=f"<uniform:{component}>", component=component)
    return resolve(policy, probe, evidence=evidence)


# --------------------------------------------------------------------------------------
# Route mapping
# --------------------------------------------------------------------------------------

#: Policy outcome to survival route, for the outcomes where the mapping is sound.
#:
#: `Route.UNRESOLVED` takes both undecidable outcomes. The route taxonomy is frozen (D-022) and
#: has one route for "cannot be determined from what travels with the release", while A1.4
#: distinguishes two causes for it. Rather than widen a frozen taxonomy, the manifest keeps the
#: cause in its own field and the route stays as specified — so a reader asking "why is this
#: sequence still here" gets the frozen answer, and a reader asking "what stopped the audit"
#: gets the finer one.
_ROUTES = {
    Outcome.OUT_OF_SCOPE: Route.OUT_OF_SCOPE,
    Outcome.RETAINED: Route.RETAINED_BY_DESIGN,
    Outcome.UNDETERMINED: Route.UNRESOLVED,
    Outcome.UNRESOLVED: Route.UNRESOLVED,
}


def route_for(outcome: Outcome) -> Route:
    """The survival route a policy outcome implies, for a detector tagging its output.

    Raises:
        ManifestError: for `Outcome.REMOVED`. A record a reading removes which is nonetheless
            in the released corpus is a conformance claim about a named laboratory's
            implementation, and `metrics/survival.md` requires A7.1 to establish it with
            record-level evidence. Returning `Route.CONFORMANCE_FAILURE` from a mapping table
            would let a detector assert it in passing, which §7 does not permit — so the
            refusal is the enforcement.
    """
    if outcome is Outcome.REMOVED:
        raise ManifestError(
            "a removed record present in the released corpus is a candidate conformance "
            "failure, not an established one: A7.1 establishes the route with record-level "
            "evidence (metrics/survival.md, DESIGN.md §7). Read the manifest's removed set as "
            "candidates and tag the route there."
        )
    try:
        return _ROUTES[outcome]
    except KeyError:  # pragma: no cover - Outcome is closed
        raise ManifestError(f"no route defined for outcome {outcome!r}") from None


# --------------------------------------------------------------------------------------
# Manifests
# --------------------------------------------------------------------------------------


@dataclass
class SourceVerdict:
    """What a policy did to one staged source."""

    key: str
    component: str
    corpus_component: str
    release: str
    bytes: int | None
    #: Records read. None when the source was not enumerated — never zero, which would read as
    #: an empty component.
    records: int | None
    enumerated: bool
    uniform: bool
    #: Outcome name -> count. Empty for a uniform source that was not enumerated; the verdict
    #: is then in `uniform_outcome`.
    counts: dict[str, int] = field(default_factory=dict)
    uniform_outcome: str | None = None
    #: "outcome|rule-id" -> count: which rule produced each verdict, so a manifest says *why*
    #: rather than only how many.
    attribution: dict[str, int] = field(default_factory=dict)
    rules_applicable: list[str] = field(default_factory=list)
    rules_undecidable: dict[str, str] = field(default_factory=dict)
    parse_failures: int = 0
    #: Records carrying evidence the source declares it does not have. Any non-zero value
    #: invalidates the declaration and therefore the verdicts drawn from it.
    evidence_contradictions: int = 0
    #: Evidence about the record unit itself, where a source's reader measures it. Empty where
    #: the unit is the publisher's own (a FASTA entry) and needs no establishing.
    structure: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "component": self.component,
            "corpus_component": self.corpus_component,
            "release": self.release,
            "bytes": self.bytes,
            "records": self.records,
            "enumerated": self.enumerated,
            "uniform": self.uniform,
            "uniform_outcome": self.uniform_outcome,
            "counts": dict(sorted(self.counts.items())),
            "attribution": dict(sorted(self.attribution.items())),
            "rules_applicable": self.rules_applicable,
            "rules_undecidable": dict(sorted(self.rules_undecidable.items())),
            "parse_failures": self.parse_failures,
            "evidence_contradictions": self.evidence_contradictions,
            "structure": self.structure,
            "why": self.why,
            "note": self.note,
        }


@dataclass
class PolicyManifest:
    """One model x reading x release manifest: the artefact A2.* and B3.* consume.

    The record-level half lives beside this in a `.jsonl` file holding the removed set, one
    JSON object per line. Two files rather than one because the summary is read by a person and
    the removed set is read by a pipeline, and because a removed set that grows to millions of
    rows must stream rather than be assembled in memory.
    """

    policy_id: str
    model: str
    reading: str
    release: str
    scope: list[str]
    sources: list[SourceVerdict] = field(default_factory=list)
    removed_file: str | None = None
    removed_records: int = 0
    notes: list[str] = field(default_factory=list)

    def totals(self) -> dict[str, int]:
        total: Counter[str] = Counter()
        for source in self.sources:
            total.update(source.counts)
        return dict(sorted(total.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": {
                "id": self.policy_id,
                "model": self.model,
                "reading": self.reading,
                "scope": self.scope,
            },
            "release": self.release,
            "records_enumerated": sum(s.records or 0 for s in self.sources if s.enumerated),
            "totals": self.totals(),
            "removed": {"file": self.removed_file, "records": self.removed_records},
            "sources": [s.to_dict() for s in self.sources],
            "notes": self.notes,
            "reading_this_manifest": (
                "`totals` counts only enumerated sources. A source with `enumerated: false` "
                "carries its verdict in `uniform_outcome` and applies it to every record in "
                "the component; its record count is absent rather than zero because nothing "
                "counted it. `removed` names candidate conformance failures — records this "
                "reading removes which are present in the released corpus — and establishing "
                "that route is A7.1's, not this manifest's."
            ),
        }

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n")
        return target


def tally(
    policy: Policy,
    records: Iterable[Record],
    *,
    evidence: Evidence,
    on_removed: Any | None = None,
) -> tuple[Counter[str], Counter[str]]:
    """Resolve a record stream, returning (outcome counts, outcome|rule attribution).

    `on_removed` is called with each removed record's :class:`Decision`, which is how the
    record-level rows reach the `.jsonl` without this function holding them.
    """
    counts: Counter[str] = Counter()
    attribution: Counter[str] = Counter()
    kept: dict[str, set] = {}
    for record in records:
        decision = resolve(policy, record, evidence=evidence, kept_values=kept)
        counts[decision.outcome.value] += 1
        attribution[f"{decision.outcome.value}|{decision.rule_id or '-'}"] += 1
        if decision.outcome is Outcome.REMOVED and on_removed is not None:
            on_removed(decision)
    return counts, attribution


def removed_rows(decisions: Iterable[Decision], *, policy_id: str, release: str) -> Iterator[str]:
    """Render removed decisions as JSONL lines for the record-level half of a manifest."""
    for decision in decisions:
        yield json.dumps(
            {
                "record_id": decision.record_id,
                "policy": policy_id,
                "release": release,
                "rule_id": decision.rule_id,
                "why": decision.why,
            },
            sort_keys=True,
        )

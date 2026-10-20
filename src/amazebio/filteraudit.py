"""The shippable filter-audit interface — task A5.1, `DESIGN.md` §A5 deliverable.

Phase A is five modules deep: `policyspec` reads a filter policy, `apply` streams a release
through it, `detect` defines what a detection has to carry, `quantify` merges the detectors,
`survival` holds the frozen metrics. That is the right shape for the audit and the wrong shape
for anyone who wants to run it on their own filter, which is what §A5 asks this phase to
become. This module is the one door: **a policy specification and a corpus go in, a
survival-route report comes out.**

**It delegates; it does not reimplement.** Every number in the report is produced by the same
function that produced A3.2's — `apply.tally`, `quantify.merge_group`, `quantify.quantify`.
That is deliberate and it is the only way the Done-when criterion "reproduces A3.2 exactly"
can mean anything: a second implementation behind one interface would be two implementations
to keep in step, and the one that drifts would be the one nobody is reading. A3.3's
independent reimplementation exists precisely so that a *second method* is written by someone
who has not read the first, which is a different job from this one.

**What a corpus has to supply.** :class:`Corpus` is three things: the components it holds, the
records in each, and what each component's evidence channels can answer. A staged release
supplies them by streaming object storage; the fixture in `tests/` supplies them from a dict.
Nothing else in the interface knows which it is talking to, which is what lets the whole
pipeline run end to end in CI on a corpus small enough to check by hand.

**What the report does not claim.** Every detection route has a limit that would otherwise
have to be remembered: a profile search finds what a profile library has a profile for, a
structural search depends on predicted structure, a provirus caller inherits its training
corpus's biases, and a sampled pass bounds a family's survival from below and never from
above. :func:`limitations_for` attaches those to the report rather than leaving them to the
write-up, because a report that travels without them is a report that will be quoted without
them.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any, Protocol

from amazebio import apply, quantify
from amazebio.policyspec import Evidence, Policy, Record
from amazebio.survival import Route

__all__ = [
    "ROUTE_LIMITATIONS",
    "AuditError",
    "AuditReport",
    "AuditRequest",
    "Corpus",
    "Detector",
    "audit",
    "limitations_for",
]


class AuditError(RuntimeError):
    """A refusal: the audit cannot be run as asked, or its report would mislead."""


class Corpus(Protocol):
    """A release, reduced to what an audit needs of it.

    Three methods rather than a file format, because the two corpora this project audits are
    published in different ones — Parquet with a lineage column for Evo 1, gzipped FASTA by
    component for Evo 2 — and a third user's will be in a third. What they have in common is
    that each names its components, can be read record by record, and knows which evidence
    channels it carries.
    """

    release: str

    def components(self) -> Sequence[str]:
        """The component names, in the order the report should list them."""
        ...

    def records(self, component: str) -> Iterator[Record]:
        """Every record in one component."""
        ...

    def evidence(self, component: str) -> Evidence:
        """What this component can answer. An absent channel yields `unresolved`, never a
        verdict — the asymmetry `policyspec.Evidence` exists to enforce."""
        ...


#: A detector: given the surviving records per component, the detection table it produces.
#: The audit does not know how one is found — a profile search, a structural search, a
#: provirus caller — only that the document coming back is the shape `metrics/detections.md`
#: specifies, because that is what `quantify.load_table` checks and what A3.2 consumed.
#: Returning `None` means this detector searched nothing here, which is reported rather than
#: silently dropped: a detector that found nothing and a detector that never ran are
#: different facts about a null.
Detector = Callable[[Mapping[str, Sequence[Record]]], Mapping[str, Any] | None]


#: What each survival route cannot say, attached to every report that mentions it. The wording
#: is the one `metrics/detections.md` and `DESIGN.md` §A2 use; this is where it travels from.
ROUTE_LIMITATIONS: Mapping[str, str] = {
    Route.RETAINED_BY_DESIGN.value: (
        "the record was examined and no rule removed it, which is only as strong as the set "
        "of rules that could actually be checked against this release"
    ),
    Route.OUT_OF_SCOPE.value: (
        "the component falls outside this reading's declared scope, so no rule was applied "
        "to it at all. A different reading of the same published policy may put it in scope "
        "without changing any count"
    ),
    Route.UNRESOLVED.value: (
        "the release does not carry the evidence a rule reads, so the record's fate under "
        "the published policy is undecidable from the release. This is a gap in what was "
        "published, not an inference about the record"
    ),
    Route.UNDETECTED.value: (
        "no instrument found the family in this record, which bounds survival from below "
        "and never from above: a profile library has no profile for what it has not curated, "
        "a structural search depends on predicted structure, and a sampled pass reads a "
        "fraction of the corpus"
    ),
    Route.MISASSIGNED.value: (
        "the record survived because a taxonomy tool labelled it as something the policy "
        "does not remove. The claim is about the tool's error, which A4.* bounds by "
        "direction, not about the policy's wording"
    ),
    Route.CONFORMANCE_FAILURE.value: (
        "the record is in the released corpus and a rule the developers published says it "
        "should not be. §7 requires record-level evidence before this route is asserted, so "
        "a detector may not route a detection here in passing"
    ),
}


@dataclasses.dataclass(frozen=True, slots=True)
class AuditRequest:
    """One audit: a policy, a corpus, the family universes to count against.

    `seed` is required rather than defaulted. Every interval in the report is a bootstrap and
    a report whose seed came from a default is one nobody can regenerate — which
    `AGENTS.md` treats as not a result yet.
    """

    policy: Policy
    corpus: Corpus
    universes: Mapping[str, quantify.RegistryUniverse]
    detectors: Mapping[str, Detector] = dataclasses.field(default_factory=dict)
    seed: int = 0
    resamples: int = quantify.BOOTSTRAP_RESAMPLES

    def __post_init__(self) -> None:
        if not self.universes:
            raise AuditError(
                "an audit with no family universe counts survival against nothing; name at "
                "least one pinned registry"
            )
        if self.seed == 0:
            raise AuditError(
                "seed=0 is the unset value, not a seed. Every interval in the report is a "
                "bootstrap and an unseeded one cannot be regenerated"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class AuditReport:
    """What one audit produces: the manifest, the detections, and survival by route."""

    policy_id: str
    release: str
    manifest: apply.PolicyManifest
    groups: Sequence[quantify.QuantifiedGroup]
    limitations: Mapping[str, str]
    detectors_run: Sequence[str]
    detectors_absent: Sequence[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "release": self.release,
            "manifest": self.manifest.to_dict(),
            "groups": [dict(g.document) for g in self.groups],
            "limitations": dict(self.limitations),
            "detectors_run": list(self.detectors_run),
            "detectors_absent": list(self.detectors_absent),
            "reading_this_report": [
                "Counts are by survival route and are never pooled across routes without "
                "the route named, because the routes answer different questions.",
                "Every route named here carries its limitation in `limitations`; a count "
                "quoted without it says more than the audit established.",
            ],
        }


def limitations_for(routes: Iterable[str]) -> dict[str, str]:
    """The limitation text for every route a report mentions.

    A route with no entry is refused rather than passed through silently: a new route with no
    stated limit would travel as though it had none.
    """
    out: dict[str, str] = {}
    for route in sorted(set(routes)):
        if route not in ROUTE_LIMITATIONS:
            raise AuditError(
                f"route {route!r} has no stated limitation. Add one to ROUTE_LIMITATIONS "
                "before a report can carry this route, so the count never travels alone"
            )
        out[route] = ROUTE_LIMITATIONS[route]
    return out


def audit(request: AuditRequest) -> AuditReport:
    """Run one policy against one corpus and report survival by route.

    The three stages are the three Phase A tasks, called rather than reimplemented: resolve
    every record against the policy (A1.4), run each detector over what survives (A2.*), and
    merge the detectors into the frozen metrics (A3.2).
    """
    policy, corpus = request.policy, request.corpus
    sources: list[apply.SourceVerdict] = []
    survivors: dict[str, list[Record]] = {}
    removed_total = 0

    for component in corpus.components():
        evidence = corpus.evidence(component)
        rules = apply.applicable_rules(policy, component)
        if not rules:
            sources.append(
                apply.SourceVerdict(
                    key=component,
                    component=component,
                    corpus_component=component,
                    release=corpus.release,
                    bytes=None,
                    records=None,
                    enumerated=False,
                    uniform=True,
                    uniform_outcome=Route.OUT_OF_SCOPE.value,
                    why=f"component {component!r} is not in this policy's scope",
                )
            )
            survivors[component] = list(corpus.records(component))
            continue

        kept: list[Record] = []
        counts: dict[str, int] = {}
        for record in corpus.records(component):
            decision = apply.resolve(policy, record, evidence=evidence)
            counts[decision.outcome.value] = counts.get(decision.outcome.value, 0) + 1
            if decision.outcome.value == "removed":
                removed_total += 1
            else:
                kept.append(record)
        survivors[component] = kept
        sources.append(
            apply.SourceVerdict(
                key=component,
                component=component,
                corpus_component=component,
                release=corpus.release,
                bytes=None,
                records=sum(counts.values()),
                enumerated=True,
                uniform=apply.is_uniform(policy, component, evidence),
                counts=counts,
                rules_applicable=[r.id for r in rules],
            )
        )

    manifest = apply.PolicyManifest(
        policy_id=policy.id,
        model=policy.model,
        reading=policy.reading,
        release=corpus.release,
        scope=list(policy.scope.components),
        sources=sources,
        removed_records=removed_total,
    )

    tables: list[quantify.SourceTable] = []
    run: list[str] = []
    absent: list[str] = []
    for name, detector in sorted(request.detectors.items()):
        document = detector(survivors)
        if document is None:
            absent.append(name)
            continue
        tables.append(quantify.load_table(document, source=name))
        run.append(name)

    groups = [
        quantify.quantify(
            quantify.merge_group(key, group),
            seed=request.seed,
            resamples=request.resamples,
        )
        for key, group in sorted(quantify.group_tables(tables).items(), key=lambda kv: str(kv[0]))
    ]

    routes = {route for group in groups for route in group.document.get("routes", {})}
    routes |= {s.uniform_outcome for s in sources if s.uniform_outcome}
    return AuditReport(
        policy_id=policy.id,
        release=corpus.release,
        manifest=manifest,
        groups=groups,
        limitations=limitations_for(routes),
        detectors_run=run,
        detectors_absent=absent,
    )

"""Filter scope against corpus composition — A4.3.

The headline Phase A finding, and the one that needs no new bioinformatics to establish: a
filter is a procedure pointed at *part* of a corpus, and what it was never pointed at was never
a candidate for removal. DECISIONS.md D-007 made this Phase A's lead rather than its
explanation. This module is the arithmetic behind that claim.

**What it does.** It joins two things the repo already holds and has deliberately kept apart:
the *declared* scope of each policy reading (`amazebio.policyspec`, from the six specs in
`policies/specs/`) and the *measured* composition of each corpus (`amazebio.opengenome` for
Evo, `amazebio.esm3` for ESM3-open). Neither side infers the other. D-013 is explicit that
scope is declared and not derived from which rules mention which components, and `esm3.py`
refuses to compute a coverage share precisely so that this module can.

**Four coverage states, not three.** The task asks for three kinds of failure kept apart — not
applied, applied but unable to detect, applied and deliberately retaining. Measuring them
needs one more distinction, because two different things look like "not applied":

* :data:`OUT_OF_SCOPE` — the policy's declared scope does not reach this component. The filter
  was never pointed at it. This is D-007's finding.
* :data:`NOT_ADDRESSED` — the source names a list of components and this one is not on it, but
  the source does not claim the list is exhaustive. ESM3-open's "including PDB, UniRef, MGnify,
  and JGI" is the case: OAS, AlphaFoldDB and ESMAtlas are training databases the sentence
  neither includes nor excludes, and `esm3.py` requires they be reported as not addressed
  rather than as in or out (`esm3-filter-scope-list-not-exhaustive`). Collapsing this into
  `OUT_OF_SCOPE` would state a conclusion the source does not support, which is the exact
  failure A4.3's last Done-when criterion forbids.
* :data:`REACHED_NO_RULE` — the scope reaches this component but no rule does. Under Evo 1's
  strict reading, whose scope is the wildcard and whose every rule narrows to IMG/VR, a
  eukaryotic genome is examined and nothing removes it. Under the literal reading the same
  record is never examined. The two are different claims about the same sequence, and the gap
  between them *is* what A4.3 quantifies (D-014).
* :data:`IN_SCOPE` — scope and at least one rule reach it.

**The detection limits are a separate axis**, carried per component alongside the coverage
state rather than folded into it. A component can be in scope and still yield nothing: because
the rule's threshold is unpublished and so its behaviour is undetermined (ESM3-open's literal
reading, D-015), or because the rule retains by design. Folding either into the coverage state
would report a filter that was applied as one that was not.

**Shares are volume figures and are labelled as such.** `metrics/survival.md` §5 is frozen and
blunt: raw volume answers a question nobody is asking, and it tracks corpus composition rather
than filter performance — the denominator grows with every genome added, so the same filter
scores better the larger the corpus gets, which inverts the finding. Every share this module
emits therefore carries its denominator and a statement of what it does not mean. The headline
metrics stay M1-M3, which are family-level and take their denominator from a pinned registry.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from amazebio import policyspec

__all__ = [
    "COMPONENT_LABELS",
    "IN_SCOPE",
    "NOT_ADDRESSED",
    "OUT_OF_SCOPE",
    "REACHED_NO_RULE",
    "STATES",
    "ComponentScope",
    "DetectionLimit",
    "classify",
    "labels_for_component",
    "limits_for",
    "resolve_label",
    "share_note",
]

#: The policy's declared scope does not reach this component: never a candidate for removal.
OUT_OF_SCOPE = "out_of_scope"
#: The source neither names nor excludes this component, and does not claim its list is
#: exhaustive. Not a scope verdict — the absence of one.
NOT_ADDRESSED = "not_addressed"
#: Scope reaches it; no rule does. Examined under this reading, and nothing removed it.
REACHED_NO_RULE = "reached_no_rule"
#: Scope and at least one rule reach it.
IN_SCOPE = "in_scope"

STATES = (OUT_OF_SCOPE, NOT_ADDRESSED, REACHED_NO_RULE, IN_SCOPE)


#: Spec scope labels to composition component names, declared rather than derived.
#:
#: The specs write a component the way their source does — Evo's papers say "IMG/VR", ESM3's
#: says "UniRef" — and the composition modules name it the way the publisher's files do:
#: `imgvr` in OpenGenome2, `stage2` in OpenGenome v1. Nothing in the repo joined the two, and
#: a join computed by lowercasing and stripping punctuation would be a silent inference in the
#: one place D-013 insists on a declaration. So it is written out, and a label with no mapping
#: raises rather than quietly matching nothing.
#:
#: Keyed by the model each spec declares, because the same word can name different things in
#: two corpora: Evo's "IMG/VR" is a component of OpenGenome, while ESM3's corpus has no IMG/VR
#: component at all (its viral content arrives inside JGI and MGnify).
COMPONENT_LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "evo": {
        # OpenGenome v1 calls the viral component `stage2`; OpenGenome2 calls it `imgvr`.
        # Both are the same component of the same corpus lineage and the policy names both.
        "IMG/VR": ("imgvr", "stage2"),
        "IMG/PR": ("imgpr", "stage1_imgpr"),
        "GTDB": ("gtdb", "stage1_gtdb"),
        "NCBI-eukaryotic-genomes": ("ncbi_eukaryotic_genomes",),
    },
    "esm3": {
        "UniRef": ("UniRef",),
        "MGnify": ("MGnify",),
        "JGI": ("JGI",),
        "PDB": ("PDB", "PDB Clustered"),
    },
}


def labels_for_component(family: str, component: str) -> tuple[str, ...]:
    """The spec scope labels that name a given composition component.

    The reverse of :data:`COMPONENT_LABELS`, and the join the whole table rests on: a policy
    declares its scope as `IMG/VR` while the composition calls that component `imgvr`, so
    asking `Scope.covers("imgvr")` of an Evo policy answers False for the one component the
    filter actually reaches. Falls back to the component's own name, which is correct for
    ESM3-open, where the spec and the composition happen to use the same words.
    """
    table = COMPONENT_LABELS.get(family, {})
    found = tuple(label for label, names in table.items() if component in names)
    return found or (component,)


def resolve_label(family: str, label: str) -> tuple[str, ...]:
    """The composition component names a spec's scope label refers to.

    Raises on an unknown label rather than returning nothing. A scope label that matches no
    component silently would report the component as unfiltered, which is this task's headline
    finding — so it must not be reachable by a typo.
    """
    table = COMPONENT_LABELS.get(family)
    if table is None:
        raise KeyError(f"no component labels declared for model family {family!r}")
    if label not in table:
        raise KeyError(
            f"scope label {label!r} of model family {family!r} is not mapped to any "
            f"composition component. Declared labels: {sorted(table)}. Add it to "
            "COMPONENT_LABELS rather than letting it match nothing — an unmapped label "
            "reads as 'this component was never filtered', which is A4.3's headline."
        )
    return table[label]


@dataclasses.dataclass(frozen=True)
class DetectionLimit:
    """A reason an in-scope component may yield nothing, which is not a scope failure.

    `kind` is one of `undetermined` (the published rule leaves a parameter unspecified, so what
    it removes cannot be computed — D-015) or `retains_by_design` (the rule is stated to keep
    something a reader might expect it to remove).
    """

    kind: str
    rule: str
    detail: str

    KINDS = ("undetermined", "retains_by_design")


@dataclasses.dataclass(frozen=True)
class ComponentScope:
    """One cell of the scope table: a component under one model and reading."""

    model: str
    reading: str
    policy_id: str
    component: str
    state: str
    why: str
    rules: tuple[str, ...] = ()
    limits: tuple[DetectionLimit, ...] = ()

    @property
    def never_a_candidate(self) -> bool:
        """True where the filter could not have removed anything, scope being the reason.

        `NOT_ADDRESSED` is deliberately excluded: it is the absence of a scope verdict, and
        counting it as a removal failure would assert what the source declines to say.
        """
        return self.state == OUT_OF_SCOPE

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "reading": self.reading,
            "policy_id": self.policy_id,
            "component": self.component,
            "state": self.state,
            "why": self.why,
            "rules": list(self.rules),
            "limits": [dataclasses.asdict(limit) for limit in self.limits],
        }


def limits_for(policy: policyspec.Policy, rule_ids: tuple[str, ...]) -> tuple[DetectionLimit, ...]:
    """The detection limits carried by the named rules of a policy.

    Only `undetermined` is derivable from the spec, because an unspecified parameter is
    representable in the schema. `retains_by_design` is a reading of the rule's prose and is
    supplied by the caller from the policy documentation, not guessed here.
    """
    unspecified = policy.unspecified()
    return tuple(
        DetectionLimit(
            kind="undetermined",
            rule=rule_id,
            detail=(
                f"published rule leaves {', '.join(params)} unspecified, so what it removes "
                "cannot be computed from the source (D-015)"
            ),
        )
        for rule_id, params in sorted(unspecified.items())
        if rule_id in rule_ids
    )


def classify(
    policy: policyspec.Policy,
    component: str,
    *,
    family: str,
    not_addressed: frozenset[str] = frozenset(),
) -> ComponentScope:
    """Where one component falls under one policy reading.

    `not_addressed` names components the policy's source neither includes nor excludes. It is
    passed in rather than inferred, because whether a list is exhaustive is a reading of the
    source's wording — "including" in ESM3-open's case — and this module does not read sources.
    """
    labels = labels_for_component(family, component)
    covered = any(policy.scope.covers(label) for label in labels)
    reached_by = tuple(
        rule.id
        for rule in policy.rules
        if any(rule.applies_to(label, scope=policy.scope) for label in labels)
    )
    # `not_addressed` describes a *list* that may not be exhaustive, so it can only arise
    # where the scope is a list. A reading whose scope is the wildcard has already answered
    # the question the other way: it reaches every component, named or not, which is the
    # whole difference between ESM3-open's literal and charitable readings (D-014).
    if component in not_addressed and not policy.scope.is_corpus_wide:
        state = NOT_ADDRESSED
        why = (
            f"the source's component list does not name {component!r} and does not state that "
            "the list is exhaustive, so this is neither a statement of coverage nor of "
            "exclusion"
        )
        reached_by = ()
    elif not covered:
        state = OUT_OF_SCOPE
        why = (
            f"{component!r} is not in this policy's declared scope "
            f"({', '.join(policy.scope.components)}): never a candidate for removal"
        )
        reached_by = ()
    elif not reached_by:
        state = REACHED_NO_RULE
        why = (
            "the policy's scope reaches this component and no rule does: examined under this "
            "reading, and nothing removed it"
        )
    else:
        state = IN_SCOPE
        why = f"reached by {len(reached_by)} rule(s): {', '.join(reached_by)}"
    return ComponentScope(
        model=policy.model,
        reading=policy.reading,
        policy_id=policy.id,
        component=component,
        state=state,
        why=why,
        rules=reached_by,
        limits=limits_for(policy, reached_by),
    )


def share_note(denominator: str) -> str:
    """The label every volume share in this task's output must carry.

    `metrics/survival.md` §5 is frozen and requires it: a volume figure is reported as context,
    never as the headline, and labelled with what it does not mean.
    """
    return (
        f"Share of {denominator}. This is a volume figure. It measures corpus composition, not "
        "filter performance: the denominator grows with every sequence added, so an unchanged "
        "filter on unchanged content scores better as the corpus grows. It does not say what "
        "fraction of hazard-relevant capability was removed — that is M1-M3 in "
        "metrics/survival.md, which are family-level and frozen."
    )

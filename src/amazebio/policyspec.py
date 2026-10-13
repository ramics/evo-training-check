"""The policy specification language: published filter prose as an executable predicate.

This is task A0.2, and it is the asset the rest of Phase A is built on. A0.1 established that
the two filters under audit are different machines:

* **Label-based** (Evo 1, inherited by Evo 2) — a pipeline applied to one corpus component:
  keep high-confidence records, keep one representative per viral operational taxonomic unit,
  keep only records whose taxon appears in a prokaryotic host at least twice, then drop records
  assigned to any of 19 named families or 12 named orders, then drop records too taxonomically
  unspecific to place.
* **Similarity-based** (ESM3-open) — build a seed set from annotation, then drop everything in
  the corpus that aligns to it above a sequence-identity threshold.

A schema that only expressed clade membership could not represent the second at all. So the
language has to cover both, and three properties matter more than expressive power:

**1. Scope is declared, not assumed.** The headline Phase A finding is that Evo's filter was
applied to the viral component of a corpus that later grew to include whole eukaryotic genomes.
A policy therefore declares which components it acts on, so the audit can compute what was
never a candidate for removal (A4.3) rather than inferring it.

**2. An unspecified value is representable.** ESM3-open's filter turns on a threshold its
authors never published. The schema must be able to say "this number is not in the source"
rather than forcing a guess that would silently become a finding. See :class:`Unspecified`.

**3. Every rule cites the text it came from.** A rule carries the source id and locator from
`policies/sources.json`, so a reviewer can go from predicate back to published sentence. A
filter policy nobody can trace to its source is the problem this project exists to document;
reproducing that failure in our own specs would be indefensible.

A0.3 added what the broader readings need, without redefining anything above. Two rule kinds
(``remove_if_host_class_in`` and ``keep_if_host_evidence_exclusive``),
a wildcard scope (:attr:`Scope.ANY`) for a reading that holds a policy to the whole corpus rather
than to the components its methods happen to name, and an optional per-rule ``components`` list so
such a policy can still say which rules reach which components — a viral-taxonomy predicate has
nothing to say about a bacterial genome record. Note the asymmetry that makes this worth the
machinery: a record in a wildcard-scope policy that no rule reaches is ``RETAINED``, meaning it was
examined and nothing removed it, which is a different claim from ``OUT_OF_SCOPE``.

Evaluation here is a *reference* implementation over an in-memory record model. It exists to
prove the schema is executable and to pin its semantics with tests. The corpus-scale evaluator
is A1.4, and the conformance diff is A7.1; both should consume these specs rather than
reimplementing the semantics.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "Decision",
    "Outcome",
    "Policy",
    "PolicyError",
    "Record",
    "Rule",
    "Scope",
    "Unspecified",
    "describe",
    "evaluate",
    "load_policy",
    "load_policy_dir",
]


class PolicyError(Exception):
    """Raised when a policy specification is malformed or unusable."""


# --------------------------------------------------------------------------------------
# Unspecified values
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Unspecified:
    """A value the published source does not state.

    The whole point is that this is *not* a default and *not* a guess. A rule holding an
    `Unspecified` value cannot be decided, and evaluation returns
    :attr:`Outcome.UNDETERMINED` rather than quietly picking a number. `DESIGN.md` §A0 treats
    under-specification as a finding; this type is how that finding survives contact with code.

    In YAML:

        identity_threshold:
          unspecified: 'Stated only as "a given sequence identity threshold".'
    """

    reason: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"<unspecified: {self.reason}>"


def _parse_value(raw: Any) -> Any:
    if isinstance(raw, Mapping) and set(raw) == {"unspecified"}:
        reason = raw["unspecified"]
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError("`unspecified` must give a non-empty reason")
        return Unspecified(reason.strip())
    return raw


# --------------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------------


@dataclasses.dataclass
class Record:
    """One corpus record, reduced to what a filter predicate can act on.

    `similarity_hits` is precomputed deliberately: this module does not run an aligner. A
    similarity rule consumes alignment results produced elsewhere, which keeps the reference
    evaluator honest about what it does and does not do.
    """

    id: str
    component: str
    attributes: dict[str, Any] = dataclasses.field(default_factory=dict)
    # rank -> taxon name, e.g. {"realm": "Riboviria", "family": "Coronaviridae"}
    taxonomy: dict[str, str] = dataclasses.field(default_factory=dict)
    # host class -> number of times this record's taxon was seen in that host class
    host_occurrences: dict[str, int] = dataclasses.field(default_factory=dict)
    # seed set name -> best fractional identity found against it
    similarity_hits: dict[str, float] = dataclasses.field(default_factory=dict)

    def most_specific_rank(self, ranks: Sequence[str]) -> str | None:
        """The finest rank in `ranks` this record is assigned at, or None."""
        for rank in reversed(list(ranks)):
            if self.taxonomy.get(rank):
                return rank
        return None


# --------------------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------------------


class Outcome(Enum):
    """What a policy decided about a record."""

    RETAINED = "retained"
    REMOVED = "removed"
    #: A rule that applies could not be decided, because a value it needs is unspecified in
    #: the published source. Never collapse this into retained or removed.
    UNDETERMINED = "undetermined"
    #: The policy does not act on this record's corpus component at all. Distinct from
    #: retained: the filter was never pointed at it. This is the distinction A4.3 measures.
    OUT_OF_SCOPE = "out_of_scope"


#: Rule kinds, each mapping to a predicate over a Record. Keyed by the `kind` field in YAML.
#: A0.3 may add kinds; it must not change the meaning of an existing one, since specs and
#: results are version-pinned against these semantics.
RULE_KINDS = {
    # keep only records whose attribute is one of `values`; drop the rest
    "keep_if_attribute_in": {"attribute", "values"},
    # keep one representative per distinct value of `attribute`
    "keep_one_per": {"attribute"},
    # keep only records whose taxon was seen in `host_class` at least `count` times
    "keep_if_host_occurrence_at_least": {"host_class", "count"},
    # drop records assigned to any of `names` at `rank`
    "remove_if_taxon_in": {"rank", "names"},
    # drop records not assigned below a rank, or whose finest assignment is a listed stop-taxon
    "remove_if_unspecific": {"require_rank", "stop_taxa", "ranks"},
    # drop records aligning to `seed_set` at or above `identity_threshold`
    "remove_if_similar_to": {"seed_set", "identity_threshold"},
    # --- added by A0.3 for the charitable and strict readings ---
    # drop records whose taxon has any recorded host occurrence in one of `host_classes`
    "remove_if_host_class_in": {"host_classes"},
    # keep only records seen in `host_class` at least `count` times and in no other host class
    "keep_if_host_evidence_exclusive": {"host_class", "count"},
}


@dataclasses.dataclass
class Rule:
    """One step of a filter policy, traceable to the text it came from."""

    id: str
    kind: str
    params: dict[str, Any]
    source: str
    locator: str = ""
    note: str = ""
    #: Components this rule acts on. `None` means the policy's whole scope. Added by A0.3:
    #: a reading that holds a policy to the whole corpus still cannot apply a viral-taxonomy
    #: predicate to a bacterial genome, so a corpus-wide policy declares which of its rules
    #: reach which components. Narrowing only — a rule cannot act outside its policy's scope.
    components: list[str] | None = None

    def unspecified_params(self) -> list[str]:
        return sorted(k for k, v in self.params.items() if isinstance(v, Unspecified))

    def applies_to(self, component: str, *, scope: Scope) -> bool:
        if self.components is None:
            return scope.covers(component)
        return scope.covers(component) and (
            Scope.ANY in self.components or component in self.components
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, where: str) -> Rule:
        known = {"id", "kind", "source", "locator", "note", "components"} | set(RULE_KINDS)
        unknown = set(raw) - known - {"params"}
        if unknown:
            raise PolicyError(f"{where}: unknown rule field(s) {sorted(unknown)}")
        for field in ("id", "kind", "source"):
            if not raw.get(field):
                raise PolicyError(f"{where}: rule is missing required field {field!r}")
        kind = raw["kind"]
        if kind not in RULE_KINDS:
            raise PolicyError(
                f"{where}: unknown rule kind {kind!r}. Known kinds: {sorted(RULE_KINDS)}. "
                "Adding a kind is allowed; changing an existing kind's meaning is not."
            )
        params_raw = raw.get("params", {})
        if not isinstance(params_raw, Mapping):
            raise PolicyError(f"{where}: rule params must be a mapping")
        params = {k: _parse_value(v) for k, v in params_raw.items()}
        required = RULE_KINDS[kind]
        missing = required - set(params)
        if missing:
            raise PolicyError(f"{where}: rule kind {kind!r} needs param(s) {sorted(missing)}")
        extra = set(params) - required
        if extra:
            raise PolicyError(
                f"{where}: rule kind {kind!r} got unexpected param(s) {sorted(extra)}"
            )
        components = raw.get("components")
        if components is not None and (not isinstance(components, list) or not components):
            raise PolicyError(
                f"{where}: rule `components` must be a non-empty list when present; omit it "
                "for a rule that acts on the policy's whole scope"
            )
        return cls(
            id=raw["id"],
            kind=kind,
            params=params,
            source=raw["source"],
            locator=raw.get("locator", ""),
            note=raw.get("note", ""),
            components=list(components) if components is not None else None,
        )


# --------------------------------------------------------------------------------------
# Scope and policy
# --------------------------------------------------------------------------------------


@dataclasses.dataclass
class Scope:
    """The corpus components a policy acts on.

    Declared rather than inferred. A component absent from this list is not filtered, and the
    audit reports that as `out_of_scope` rather than as survival.
    """

    components: list[str]
    note: str = ""

    #: A scope of `["*"]` covers every component, including ones nobody has enumerated.
    #: Added by A0.3: a reading that holds a policy to the whole corpus cannot be expressed
    #: by listing components, because the question it answers is what happens to the ones the
    #: published methods never name. Still a declaration, not an inference.
    ANY = "*"

    def covers(self, component: str) -> bool:
        return self.ANY in self.components or component in self.components

    @property
    def is_corpus_wide(self) -> bool:
        return self.ANY in self.components


@dataclasses.dataclass
class Policy:
    """A filter policy: a scope, an ordered rule pipeline, and its provenance."""

    id: str
    model: str
    reading: str
    source: str
    scope: Scope
    rules: list[Rule]
    note: str = ""

    READINGS = ("literal", "charitable", "strict")

    def unspecified(self) -> dict[str, list[str]]:
        """Rule id -> unspecified param names. Empty when the policy is fully determined."""
        return {r.id: r.unspecified_params() for r in self.rules if r.unspecified_params()}

    @property
    def is_determined(self) -> bool:
        return not self.unspecified()


def _parse_policy(raw: Mapping[str, Any], *, where: str) -> Policy:
    if not isinstance(raw, Mapping):
        raise PolicyError(f"{where}: policy must be a mapping")
    unknown = set(raw) - {"id", "model", "reading", "source", "scope", "rules", "note"}
    if unknown:
        raise PolicyError(f"{where}: unknown policy field(s) {sorted(unknown)}")
    for field in ("id", "model", "reading", "source", "scope", "rules"):
        if field not in raw:
            raise PolicyError(f"{where}: policy is missing required field {field!r}")
    if raw["reading"] not in Policy.READINGS:
        raise PolicyError(
            f"{where}: reading must be one of {Policy.READINGS}, got {raw['reading']!r}. "
            "DESIGN.md §A0 requires exactly these three readings per policy."
        )
    scope_raw = raw["scope"]
    if not isinstance(scope_raw, Mapping) or "components" not in scope_raw:
        raise PolicyError(f"{where}: scope must be a mapping with a `components` list")
    components = scope_raw["components"]
    if not isinstance(components, list) or not components:
        raise PolicyError(
            f"{where}: scope.components must be a non-empty list. A policy that acts on nothing "
            "is not a policy; if the source does not say, that is a finding to record in "
            "policies/, not an empty scope."
        )
    rules_raw = raw["rules"]
    if not isinstance(rules_raw, list) or not rules_raw:
        raise PolicyError(f"{where}: rules must be a non-empty list")
    rules = [Rule.from_dict(r, where=f"{where} rule[{i}]") for i, r in enumerate(rules_raw)]
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            raise PolicyError(f"{where}: duplicate rule id {rule.id!r}")
        seen.add(rule.id)
    return Policy(
        id=raw["id"],
        model=raw["model"],
        reading=raw["reading"],
        source=raw["source"],
        scope=Scope(components=list(components), note=scope_raw.get("note", "")),
        rules=rules,
        note=raw.get("note", ""),
    )


def load_policy(path: str | Path) -> Policy:
    """Load and validate one policy spec from YAML."""
    import yaml

    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise PolicyError(f"{p.name}: not valid YAML: {exc}") from exc
    if not isinstance(raw, Mapping) or "policy" not in raw:
        raise PolicyError(f"{p.name}: file must contain a top-level `policy:` mapping")
    return _parse_policy(raw["policy"], where=p.name)


def load_policy_dir(path: str | Path) -> dict[str, Policy]:
    """Load every `*.yaml` policy in a directory, keyed by policy id."""
    policies: dict[str, Policy] = {}
    for file in sorted(Path(path).glob("*.yaml")):
        policy = load_policy(file)
        if policy.id in policies:
            raise PolicyError(f"duplicate policy id {policy.id!r} in {file.name}")
        policies[policy.id] = policy
    if not policies:
        raise PolicyError(f"no policy specs found in {path}")
    return policies


# --------------------------------------------------------------------------------------
# Reference evaluation
# --------------------------------------------------------------------------------------


@dataclasses.dataclass
class Decision:
    """What a policy did to one record, and which rule did it."""

    record_id: str
    outcome: Outcome
    rule_id: str | None = None
    why: str = ""

    @property
    def removed(self) -> bool:
        return self.outcome is Outcome.REMOVED


def _decide(rule: Rule, record: Record, *, kept_values: dict[str, set]) -> Decision | None:
    """Apply one rule. Returns a Decision to stop on, or None to continue the pipeline."""
    if unspecified := rule.unspecified_params():
        return Decision(
            record.id,
            Outcome.UNDETERMINED,
            rule.id,
            f"rule {rule.id!r} needs {', '.join(unspecified)}, which the source does not state: "
            + "; ".join(str(rule.params[k]) for k in unspecified),
        )
    p = rule.params
    match rule.kind:
        case "keep_if_attribute_in":
            value = record.attributes.get(p["attribute"])
            if value not in p["values"]:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"{p['attribute']}={value!r} not in {p['values']!r}",
                )
        case "keep_one_per":
            key = record.attributes.get(p["attribute"])
            bucket = kept_values.setdefault(rule.id, set())
            if key in bucket:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"not the representative for {p['attribute']}={key!r}",
                )
            bucket.add(key)
        case "keep_if_host_occurrence_at_least":
            seen = record.host_occurrences.get(p["host_class"], 0)
            if seen < p["count"]:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"seen in {p['host_class']} {seen} time(s), needs >= {p['count']}",
                )
        case "remove_if_taxon_in":
            taxon = record.taxonomy.get(p["rank"])
            if taxon and taxon in p["names"]:
                return Decision(
                    record.id, Outcome.REMOVED, rule.id, f"{p['rank']}={taxon!r} is denylisted"
                )
        case "remove_if_unspecific":
            ranks = p["ranks"]
            if not record.taxonomy.get(p["require_rank"]):
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"no {p['require_rank']} assigned",
                )
            finest = record.most_specific_rank(ranks)
            if finest and record.taxonomy[finest] in p["stop_taxa"]:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"finest assignment {record.taxonomy[finest]!r} is a stop-taxon",
                )
        case "remove_if_similar_to":
            identity = record.similarity_hits.get(p["seed_set"])
            if identity is not None and identity >= p["identity_threshold"]:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"aligns to {p['seed_set']} at {identity:.3f} >= {p['identity_threshold']}",
                )
        case "remove_if_host_class_in":
            hit = [hc for hc in p["host_classes"] if record.host_occurrences.get(hc, 0) > 0]
            if hit:
                return Decision(
                    record.id,
                    Outcome.REMOVED,
                    rule.id,
                    f"has host evidence in {', '.join(sorted(hit))}",
                )
        case "keep_if_host_evidence_exclusive":
            wanted, needed = p["host_class"], p["count"]
            seen = record.host_occurrences.get(wanted, 0)
            other = sorted(
                hc for hc, n in record.host_occurrences.items() if n > 0 and hc != wanted
            )
            if seen < needed or other:
                why = (
                    f"seen in {wanted} {seen} time(s), needs >= {needed}"
                    if seen < needed
                    else f"also has host evidence in {', '.join(other)}"
                )
                return Decision(record.id, Outcome.REMOVED, rule.id, why)
        case _:  # pragma: no cover - guarded by Rule.from_dict
            raise PolicyError(f"no evaluator for rule kind {rule.kind!r}")
    return None


def evaluate(policy: Policy, records: Iterable[Record]) -> list[Decision]:
    """Apply a policy to records in order, returning one Decision each.

    Rules run as a pipeline in the order written, which is how the published procedures read.
    `keep_one_per` is order-dependent by nature, so records are processed in the order given;
    callers who need a deterministic representative must sort before calling.
    """
    kept_values: dict[str, set] = {}
    decisions: list[Decision] = []
    for record in records:
        if not policy.scope.covers(record.component):
            decisions.append(
                Decision(
                    record.id,
                    Outcome.OUT_OF_SCOPE,
                    None,
                    f"component {record.component!r} is not in this policy's scope "
                    f"({', '.join(policy.scope.components)})",
                )
            )
            continue
        decision = None
        for rule in policy.rules:
            if not rule.applies_to(record.component, scope=policy.scope):
                continue
            decision = _decide(rule, record, kept_values=kept_values)
            if decision is not None:
                break
        decisions.append(
            decision or Decision(record.id, Outcome.RETAINED, None, "no rule removed it")
        )
    return decisions


def describe(policy: Policy) -> str:
    """Render a policy as prose, for the write-up and for eyeballing against the source."""
    lines = [
        f"{policy.id} — {policy.model}, {policy.reading} reading",
        f"  source: {policy.source}",
        f"  scope: {', '.join(policy.scope.components)}",
    ]
    if policy.scope.note:
        lines.append(f"    ({policy.scope.note})")
    lines.append("  rules, in order:")
    for i, rule in enumerate(policy.rules, 1):
        where = f"{rule.source}" + (f" {rule.locator}" if rule.locator else "")
        on = f" on {', '.join(rule.components)}" if rule.components else ""
        lines.append(f"    {i}. [{rule.kind}] {rule.id}{on}  <- {where}")
        for key, value in rule.params.items():
            shown = (
                f"UNSPECIFIED ({value.reason})" if isinstance(value, Unspecified) else repr(value)
            )
            lines.append(f"         {key}: {shown}")
    if not policy.is_determined:
        lines.append(
            "  NOT FULLY DETERMINED: "
            + "; ".join(f"{rid} needs {', '.join(ps)}" for rid, ps in policy.unspecified().items())
        )
    return "\n".join(lines)

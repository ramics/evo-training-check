"""What taxonomy has not labelled, and therefore what a taxonomy filter cannot reach — A4.1.

`DESIGN.md` §A4 asks one question: a taxonomy-based filter can only act on sequence that
taxonomy has labelled, so what share of the corpus is outside its reach *in principle*? This
module is the definition of that share, and nothing in it reads a corpus. The tool does the
I/O; this is the arithmetic and the vocabulary, so that both are testable without 5 GB of TSV.

Three distinctions do the work, and getting any of them wrong would turn a measurement into a
slogan.

**Labelled is per rank, not per record.** A record carrying `r__Duplodnaviria;k__Heunggongvirae;
p__Uroviricota;c__Caudoviricetes;;;;` is labelled — at four ranks of eight. A rule keyed on
family cannot see it at all, and a rule keyed on realm sees it perfectly. So there is no single
"unclassified fraction" of a corpus: there is one per rank, and a ceiling is only meaningful
against the rank the rule reads. :class:`RankFill` holds all eight.

**A rule that fires on an absent label is not limited by the absence.** Evo 1's pipeline is
mostly keep-listing: "keep only sequences whose assigned taxonomic classification was found
within a prokaryotic host at least twice" removes a record with no host prediction *because* it
has none, and "viruses with poor taxonomic specificity were excluded, including those with no
assigned realm at all" removes a record with no realm *because* it has none. Those rules are
decidable on every record in the database. Counting them as blocked by missing labels would
overstate the finding badly, and §2's commitment to a publishable null cuts both ways: a
measurement designed to make the filter look worse than it is would be the same failure in the
other direction.

What such a rule cannot do is *discriminate*. It removes the unlabelled majority wholesale,
without reference to what the sequence is. So each rule carries two shares, and they answer
different questions:

* `decidable_share` — where the rule produces its stated outcome. Blunt rules score 1.0.
* `discriminating_share` — where the rule's own criterion can be evaluated against a label
  that is actually present. This is the ceiling §A4 asks for (D-081).

The 19-family denylist is the case that matters: it is the only part of Evo's published
procedure that names a hazard, and it can only act where a family label exists.

**Unlabelled is not out of scope.** A component the filter was never applied to is A4.3's
finding and has a different remedy — widen the scope. A component the filter was applied to and
could not label is this task's, and widening the scope does not help it. The two are kept in
separate fields all the way to the artefact (:class:`ComponentFill` carries `scope_state` from
`amazebio.scope` rather than folding it into the labelling), because a reader who conflates
them gets a number that means neither thing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any

from amazebio import policyspec
from amazebio.conformance import RANKS, parse_lineage_tag

__all__ = [
    "ABSENT",
    "FIRES_ON",
    "LABELLED",
    "NOT_ANNOTATED",
    "NOT_MEASURED",
    "NOT_TAXONOMY_DEPENDENT",
    "OUT_OF_POLICY_SCOPE",
    "ComponentFill",
    "FieldFill",
    "RankFill",
    "RuleCeiling",
    "absence_reason",
    "field_fill",
    "host_fill",
    "policy_ceilings",
    "rank_fill",
    "rule_ceiling",
    "terminal_taxa",
]

#: A label the corpus carries.
LABELLED = "labelled"

#: A label the corpus's own annotation field leaves empty. The field exists and says nothing.
ABSENT = "unlabelled"

#: The component carries no such annotation field at all. Distinct from :data:`ABSENT` on
#: purpose: an empty field is the publisher declining to classify a record, and a missing field
#: is the *release* not carrying what its input knew. Evo 2's released viral component is the
#: second case — 2,957,495 FASTA headers with no lineage tag, whose accessions all resolve in
#: IMG/VR (D-073). Reporting that as 100% unclassified would be false.
NOT_ANNOTATED = "not_annotated"

#: The filter was never applied to this component, so it has no labelling obligation and no
#: ceiling. The distinction A4.1's task file asks for in as many words: unlabelled is a limit of
#: taxonomy, out of scope is a limit of the policy, and the remedies differ. A4.3 owns the
#: shares; this value exists so the two can never be summed by accident.
OUT_OF_POLICY_SCOPE = "out_of_policy_scope"

#: No ceiling was measured for this component here, and the `scope_state` beside it says why.
#: Distinct from :data:`OUT_OF_POLICY_SCOPE` because a wildcard-scope reading *examines* a
#: component and removes nothing from it, which is a third thing again (D-014): not reached by
#: any rule, not outside the policy, and not measured by this task.
NOT_MEASURED = "not_measured"

#: The rule reads something other than taxonomy, so no taxonomy ceiling binds it. ESM3-open's
#: published rule is a similarity threshold against a seed set (`alignment_to_seed_set`), and
#: §A4's question simply does not apply to it. Saying so is better than reporting a zero.
NOT_TAXONOMY_DEPENDENT = "not_taxonomy_dependent"

#: What each published rule kind needs in order to fire, and what it needs in order to
#: discriminate. `label_absent` means absence is itself the trigger, so the rule is decidable
#: everywhere and discriminates nowhere; `label_present` means the rule cannot fire without the
#: label; `either` means it fires either way but only discriminates on a present label.
#:
#: Declared rather than derived, for the reason D-013 gives and D-074 paid for: the direction a
#: rule reads its evidence is a reading of the author's words, and inferring it from the schema
#: would be inventing a fact about someone else's procedure. An unknown kind raises.
FIRES_ON = {
    "keep_if_attribute_in": "either",
    "keep_one_per": "label_present",
    "keep_if_host_occurrence_at_least": "either",
    "remove_if_host_class_in": "label_present",
    "keep_if_host_evidence_exclusive": "either",
    "remove_if_taxon_in": "label_present",
    "remove_if_unspecific": "label_absent",
    "remove_if_similar_to": "label_present",
}


class UnknownRuleKind(KeyError):
    """A rule kind with no declared reading direction.

    Its own exception because the correct response is to declare the kind after reading the
    source, never to pick a default: a default here would silently decide whether an author's
    rule counts as reaching a record.
    """


@dataclasses.dataclass(frozen=True)
class RankFill:
    """Per-rank labelling of one component, from its own classification histogram.

    `per_rank` counts records carrying a name at that rank — not records whose lineage *reaches*
    that rank, which would be the same number only if every lineage were gapless. They are not:
    `;;;;;;g__Dinodnavirus;s__Heterocapsa circularisquama DNA virus 01` fills genus and species
    and nothing above them, and it is the publisher's own output.

    `depth` is the number of ranks filled, which is the shape A7.1 reported for the released
    corpus and is kept so the two are comparable.
    """

    total: int
    per_rank: Mapping[str, int]
    depth: Mapping[int, int]
    malformed: int = 0
    distinct_classifications: int = 0

    def labelled(self, rank: str) -> int:
        if rank not in RANKS:
            raise KeyError(f"{rank!r} is not one of the eight ranks: {RANKS}")
        return int(self.per_rank.get(rank, 0))

    def unlabelled(self, rank: str) -> int:
        return self.total - self.labelled(rank)

    def share(self, rank: str) -> float | None:
        """The labelled share at one rank, or `None` on an empty component.

        `None` rather than 0.0: a share of nothing is not zero coverage, and a figure that
        cannot be computed must not look like one that came out low.
        """
        return self.labelled(rank) / self.total if self.total else None

    @property
    def unclassified(self) -> int:
        """Records filling no rank at all — the dark matter of the component."""
        return int(self.depth.get(0, 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "distinct_classifications": self.distinct_classifications,
            "malformed_records": self.malformed,
            "unclassified_records": self.unclassified,
            "unclassified_share": (self.unclassified / self.total if self.total else None),
            "depth": {str(d): n for d, n in sorted(self.depth.items())},
            "per_rank": {
                rank: {
                    "labelled": self.labelled(rank),
                    "unlabelled": self.unlabelled(rank),
                    "labelled_share": self.share(rank),
                }
                for rank in RANKS
            },
        }


def rank_fill(histogram: Mapping[str, int]) -> RankFill:
    """Per-rank labelling from `{classification string: records}`.

    The histogram is a partition of the component — every record contributes to exactly one
    key — so this is exact rather than an estimate, and the caller is expected to have checked
    that it sums to the component's record count before trusting the output. The check is the
    caller's because only the caller holds the independent total.

    Parsing is `conformance.parse_lineage_tag`, which is the released-tag parser: IMG/VR's
    `Taxonomic classification` column is formatted identically to the inline lineage tag Evo 1's
    release carries (`amazebio.imgvr.SEQ_COLUMNS`), and using one parser for both is what makes
    the input and the output of the filter comparable at all.
    """
    per_rank: dict[str, int] = dict.fromkeys(RANKS, 0)
    depth: dict[int, int] = {}
    malformed = 0
    total = 0
    for raw, records in histogram.items():
        n = int(records)
        if n < 0:
            raise ValueError(f"negative record count {n} for {raw!r}")
        total += n
        tag = parse_lineage_tag(raw)
        if tag.is_malformed:
            malformed += n
        depth[tag.depth] = depth.get(tag.depth, 0) + n
        for rank in tag.taxonomy:
            per_rank[rank] += n
    return RankFill(
        total=total,
        per_rank=per_rank,
        depth=depth,
        malformed=malformed,
        distinct_classifications=len(histogram),
    )


@dataclasses.dataclass(frozen=True)
class FieldFill:
    """Presence of one non-taxonomic annotation field, with the absences kept apart.

    `absent_by_reason` is why each absent record is absent, in the publisher's own terms rather
    than ours. IMG/VR writes a missing host prediction two ways — an empty field and a field of
    bare separators — and which one it emits is itself under-specified (`imgvr.host_domain`), so
    they are counted separately and summed only here.
    """

    field: str
    total: int
    present: int
    absent_by_reason: Mapping[str, int] = dataclasses.field(default_factory=dict)

    @property
    def absent(self) -> int:
        return self.total - self.present

    @property
    def share(self) -> float | None:
        return self.present / self.total if self.total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "total": self.total,
            "present": self.present,
            "absent": self.absent,
            "present_share": self.share,
            "absent_by_reason": dict(sorted(self.absent_by_reason.items())),
        }


def absence_reason(label: str) -> str | None:
    """The absence a `host_domain`-style label records, or `None` if it records a value.

    `imgvr.host_domain` returns a parenthesised label for every way a field can fail to carry a
    domain — `(empty)`, `(separators only)`, `(unparsed: ...)`, `(empty d__)` — and a bare taxon
    name otherwise. That convention is the contract this reads, so a new absence label needs no
    change here.
    """
    return label if label.startswith("(") else None


def field_fill(field: str, counts: Mapping[str, int]) -> FieldFill:
    """Presence from a label histogram following the `host_domain` convention.

    An `(unparsed: ...)` label counts as absent for the ceiling, which is a choice worth being
    explicit about: a field whose content this audit cannot read is not evidence the rule can
    act on, whatever it meant to the publisher. It is reported under its own reason rather than
    folded in with the empty fields, so the choice can be reversed by a reader who disagrees.
    """
    present = 0
    absent: dict[str, int] = {}
    total = 0
    for label, n in counts.items():
        n = int(n)
        total += n
        reason = absence_reason(label)
        if reason is None:
            present += n
        else:
            absent[reason] = absent.get(reason, 0) + n
    return FieldFill(field=field, total=total, present=present, absent_by_reason=absent)


def host_fill(counts: Mapping[str, int]) -> FieldFill:
    """:func:`field_fill` over IMG/VR's host-prediction domains."""
    return field_fill("Host taxonomy prediction", counts)


@dataclasses.dataclass(frozen=True)
class RuleCeiling:
    """What one published rule can reach on one component, and what it can tell apart there.

    `discriminating_share` is §A4's ceiling. `decidable_share` is beside it because the
    difference between the two *is* the finding for a keep-list filter: a rule can be decidable
    on every record and discriminate on a twentieth of them.
    """

    rule: str
    kind: str
    channel: str
    key: str | None
    fires_on: str
    total: int
    decidable: int
    discriminating: int
    why: str
    binds: bool = True

    @property
    def decidable_share(self) -> float | None:
        return self.decidable / self.total if self.total else None

    @property
    def discriminating_share(self) -> float | None:
        return self.discriminating / self.total if self.total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "kind": self.kind,
            "channel": self.channel,
            "key": self.key,
            "fires_on": self.fires_on,
            "binds": self.binds,
            "total": self.total,
            "decidable": self.decidable,
            "decidable_share": self.decidable_share,
            "discriminating": self.discriminating,
            "discriminating_share": self.discriminating_share,
            "why": self.why,
        }


#: The parameter naming the rank a taxonomy rule reads, by rule kind. `remove_if_unspecific`
#: names `require_rank`; `remove_if_taxon_in` names `rank`. Declared for the same reason
#: `FIRES_ON` is.
_RANK_PARAM = {"remove_if_taxon_in": "rank", "remove_if_unspecific": "require_rank"}


def rule_ceiling(
    rule: policyspec.Rule,
    *,
    ranks: RankFill,
    host: FieldFill | None = None,
    attributes: Mapping[str, FieldFill] | None = None,
) -> RuleCeiling:
    """The reach of one rule over one component, from that component's own annotation fills.

    Raises :class:`UnknownRuleKind` for a kind with no declared reading direction, and
    `KeyError` for a taxonomy rule naming a rank outside the eight. Both are failures to
    declare, not conditions to tolerate: a rule this does not understand must not be reported as
    reaching nothing, because nothing-reached reads as a finding.
    """
    kind = rule.kind
    if kind not in FIRES_ON:
        raise UnknownRuleKind(
            f"rule {rule.id!r} is of kind {kind!r}, which has no declared reading direction in "
            "amazebio.unfilterable.FIRES_ON. Declare it from the source before measuring it."
        )
    channel = policyspec.RULE_INPUTS[kind]
    fires_on = FIRES_ON[kind]
    total = ranks.total
    attributes = attributes or {}

    if channel == "taxonomy":
        param = _RANK_PARAM[kind]
        rank = rule.params.get(param)
        if isinstance(rank, policyspec.Unspecified) or rank is None:
            return RuleCeiling(
                rule=rule.id,
                kind=kind,
                channel=channel,
                key=None,
                fires_on=fires_on,
                total=total,
                decidable=0,
                discriminating=0,
                binds=False,
                why=(
                    f"the published rule does not state which rank it reads ({param} "
                    "unspecified), so its reach cannot be computed from the source (D-015)"
                ),
            )
        present = ranks.labelled(str(rank))
        key = str(rank)
        detail = f"{present:,} of {total:,} records carry a {key} label"
    elif channel == "host_occurrences":
        if host is None:
            raise ValueError(f"rule {rule.id!r} reads host evidence and none was measured")
        present = host.present
        key = host.field
        detail = f"{present:,} of {total:,} records carry a host prediction"
    elif channel == "record_attributes":
        name = str(rule.params.get("attribute", ""))
        fill = attributes.get(name)
        if fill is None:
            raise ValueError(
                f"rule {rule.id!r} reads record attribute {name!r} and no fill was measured"
            )
        present = fill.present
        key = name
        detail = f"{present:,} of {total:,} records carry a {name!r} value"
    else:
        return RuleCeiling(
            rule=rule.id,
            kind=kind,
            channel=channel,
            key=None,
            fires_on=fires_on,
            total=total,
            decidable=0,
            discriminating=0,
            binds=False,
            why=(
                f"reads {channel}, not taxonomy: no taxonomic labelling ceiling binds this "
                "rule, and reporting one as zero would misdescribe it"
            ),
        )

    decidable = total if fires_on in ("either", "label_absent") else present
    discriminating = 0 if fires_on == "label_absent" else present
    if fires_on == "label_absent":
        why = (
            f"fires on the absence of the label, so it is decidable on every record and "
            f"discriminates on none: {detail}, and the rule's trigger is the rest"
        )
    elif fires_on == "either":
        why = f"decidable on every record because absence of evidence is itself removal; {detail}"
    else:
        why = f"cannot fire without the label it reads; {detail}"
    return RuleCeiling(
        rule=rule.id,
        kind=kind,
        channel=channel,
        key=key,
        fires_on=fires_on,
        total=total,
        decidable=decidable,
        discriminating=discriminating,
        why=why,
    )


def policy_ceilings(
    policy: policyspec.Policy,
    *,
    ranks: RankFill,
    host: FieldFill | None = None,
    attributes: Mapping[str, FieldFill] | None = None,
) -> tuple[RuleCeiling, ...]:
    """:func:`rule_ceiling` for every rule of one policy reading, in the policy's own order."""
    return tuple(
        rule_ceiling(rule, ranks=ranks, host=host, attributes=attributes) for rule in policy.rules
    )


def terminal_taxa(histogram: Mapping[str, int], names: Iterable[str]) -> dict[str, int]:
    """Records whose *finest* assigned taxon is one of `names`.

    Not a ceiling and not reported as one. It is the caveat the family ceiling needs: Evo 1's
    unspecificity rule removes records "only assigned up to the level of" eight named taxa, so
    some of the records a family-keyed rule cannot see are removed anyway by a rule that reads
    their shallowness instead. Quantifying that is what keeps the ceiling from being read as a
    claim about what survived — which is A3.2's question, over a different population.
    """
    wanted = frozenset(names)
    out: dict[str, int] = {}
    for raw, records in histogram.items():
        tag = parse_lineage_tag(raw)
        if not tag.taxonomy:
            continue
        finest = next(
            tag.taxonomy[rank] for rank in reversed(RANKS) if rank in tag.taxonomy
        )  # pragma: no branch - the lineage is non-empty here
        if finest in wanted:
            out[finest] = out.get(finest, 0) + int(records)
    return out


@dataclasses.dataclass(frozen=True)
class ComponentFill:
    """One row of A4.1's table: a component, how well it is labelled, and whether it was reached.

    `scope_state` is `amazebio.scope`'s verdict, carried rather than recomputed, so that
    "unlabelled" and "never a candidate" stay two columns. A component that is `out_of_scope`
    has no labelling obligation and its fills are `None`; one that is `in_scope` and unlabelled
    is this task's finding.
    """

    component: str
    corpus: str
    role: str
    scope_state: str | None
    labelling: str
    ranks: RankFill | None = None
    fields: tuple[FieldFill, ...] = ()
    ceilings: tuple[RuleCeiling, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "corpus": self.corpus,
            "role": self.role,
            "scope_state": self.scope_state,
            "labelling": self.labelling,
            "ranks": self.ranks.to_dict() if self.ranks else None,
            "fields": [f.to_dict() for f in self.fields],
            "ceilings": [c.to_dict() for c in self.ceilings],
            "note": self.note,
        }

"""Conformance re-execution: run a developer's own predicate against their own release.

This is task A7.1, and it is the cheapest airtight question in the project. It claims nothing
about homology, capability or hazard. It compares a stated rule against delivered data: a record
that survives a rule its own authors published is a **conformance failure**, and a clean result
is as publishable as a dirty one (DESIGN.md §2, §A7).

Four things shape this module, and three of them are properties of the release rather than
choices of ours.

**Only part of a published policy can be re-executed against a published corpus.** Evo 1's
procedure reads four kinds of input: IMG/VR confidence labels, vOTU identifiers, host-occurrence
counts, and taxonomic lineage. Exactly one of those — the lineage — travels with the released
records. So the audited pipeline here is a *restriction* of the published one, derived
mechanically by :func:`restrict` from a declared inventory of what the release carries
(:data:`RELEASE_INPUTS`) rather than by hand-picking rules, and the rules it drops are reported
as a coverage limit rather than quietly omitted. Running the full pipeline against these records
would not be stricter: with no `confidence` attribute on any released record the first rule
removes all of them, and the result would measure our missing metadata rather than their filter.

**A rule the release cannot test is not an undetermined rule.**
:attr:`~amazebio.policyspec.Outcome.UNDETERMINED` already means something specific and
different — the *published source* does not state a value the rule needs (ESM3's identity
threshold is the case it exists for). Here the source states the value and the *release* omits
the input. Conflating the two would merge a gap in somebody's prose with a gap in somebody's
data, which are separate findings about separate artefacts. Hence :class:`Coverage`, kept apart
from `Outcome` entirely.

**Causes are defined before counting**, which §A7 requires and which this module enforces by
construction: :data:`CAUSES` is frozen here, :func:`classify` is a total function onto it, and
nothing in the pipeline can invent a category once the numbers are in view.

**The three readings cannot disagree about anything the release can test.** Every rule the
literal, charitable and strict readings of Evo's policy differ over — the host-occurrence
proxies, the scope wildcard, the exclusivity requirement — reads an input the release does not
carry. The taxonomy rules are identical across all three. So the spread across readings, which
§A7 says matters as much as any single number, is *exactly zero* on the checkable subset. That
is a finding about the release, not agreement between the readings, and
:func:`readings_agree_by_construction` is here so the write-up asserts it from the specs rather
than from three identical columns of output.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum

from amazebio import policyspec
from amazebio.policyspec import Decision, Outcome, Policy, Record, Rule, evaluate

__all__ = [
    "BLOCK_CHARS",
    "CAUSES",
    "COMPARISON_KEYS",
    "HOST_UNITS",
    "INPUT_RELEASES",
    "ORDER_DEPENDENT_KINDS",
    "PRIMARY_HOST_UNIT",
    "RANKS",
    "RELEASE_INPUTS",
    "RULE_INPUTS",
    "Cause",
    "Coverage",
    "Failure",
    "HostUnit",
    "LineageTag",
    "Restriction",
    "RowShape",
    "VotuComparison",
    "classify",
    "diff",
    "parse_lineage_tag",
    "readings_agree_by_construction",
    "record_from_row",
    "restrict",
    "split_row",
    "votu_bounds",
    "votu_comparison",
]


# --------------------------------------------------------------------------------------
# The lineage tag
# --------------------------------------------------------------------------------------

#: The eight ranks, finest last. Same order and same names as the `ranks` list in the
#: published `remove_if_unspecific` rule, so a tag parsed here drops straight into
#: :class:`~amazebio.policyspec.Record.taxonomy` without a translation step.
RANKS = ("realm", "kingdom", "phylum", "class", "order", "family", "genus", "species")

#: The one-letter prefix each rank carries in the released tag. These are the authors' own
#: annotations — Evo 1 Appendix B.2 prints its stop-taxa as `r:Riboviria`, `k:Heunggongvirae`,
#: `p:Preplasmiviricota`, `c:Tectiliviricetes` — and the released records use the same scheme
#: with a doubled underscore. The agreement between the two is what makes the release testable
#: against the published rule at all (DECISIONS.md D-020).
RANK_PREFIXES = {
    "r": "realm",
    "k": "kingdom",
    "p": "phylum",
    "c": "class",
    "o": "order",
    "f": "family",
    "g": "genus",
    "s": "species",
}

_FIELD = re.compile(r"^([a-z])__(.*)$")


@dataclasses.dataclass(frozen=True)
class LineageTag:
    """A parsed released lineage tag, and whether it parsed cleanly.

    `taxonomy` is rank -> name for the ranks the tag fills, omitting the empty ones. A tag
    filling no rank at all is well-formed and empty, which is not a parse failure: it is a
    record with no taxonomic assignment, and the published rule has something to say about
    exactly that case.

    `malformed` carries the fields that could not be read, rather than a bare flag. A tag whose
    prefix disagrees with its position is the one case worth keeping the detail for: it means
    either the release or our reading of it is wrong, and which it is cannot be settled by
    discarding the evidence.
    """

    raw: str
    taxonomy: dict[str, str]
    malformed: tuple[str, ...] = ()

    @property
    def is_malformed(self) -> bool:
        return bool(self.malformed)

    @property
    def depth(self) -> int:
        """How many of the eight ranks this tag fills."""
        return len(self.taxonomy)


def parse_lineage_tag(raw: str) -> LineageTag:
    """Parse one released lineage tag into rank -> taxon name.

    The released form is eight `;`-separated fields, each either empty or `<prefix>__<name>`,
    finest rank last: `r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;`.

    Two decisions about how to read it, both of which matter for what gets counted.

    **Prefix wins over position, and a disagreement is recorded rather than resolved.** Position
    alone would be the simpler rule and would quietly mis-rank a tag whose fields are not in
    canonical order; prefix alone would discard a field with no prefix. So a prefixed field is
    assigned to the rank its prefix names, a disagreement with its position is recorded in
    `malformed`, and an unprefixed non-empty field is recorded there too rather than guessed at.

    **A short tag is not malformed.** Fewer than eight fields fills what it has and leaves the
    rest unassigned, because a tag that stops early says the same thing as one padded with
    empties, and treating the padding as a requirement would turn a formatting variation into a
    finding.
    """
    taxonomy: dict[str, str] = {}
    malformed: list[str] = []
    fields = raw.split(";")
    if len(fields) > len(RANKS):
        malformed.append(f"{len(fields)} fields, expected at most {len(RANKS)}")
    for i, field in enumerate(fields):
        field = field.strip()
        if not field:
            continue
        m = _FIELD.match(field)
        if not m:
            malformed.append(f"field {i} {field!r} carries no rank prefix")
            continue
        prefix, name = m.group(1), m.group(2).strip()
        rank = RANK_PREFIXES.get(prefix)
        if rank is None:
            malformed.append(f"field {i} {field!r} has unknown rank prefix {prefix!r}")
            continue
        if i < len(RANKS) and RANKS[i] != rank:
            malformed.append(f"field {i} is {rank!r} by prefix but {RANKS[i]!r} by position")
        if not name:
            malformed.append(f"field {i} {field!r} names no taxon")
            continue
        taxonomy[rank] = name
    return LineageTag(raw=raw, taxonomy=taxonomy, malformed=tuple(malformed))


# --------------------------------------------------------------------------------------
# The released row
# --------------------------------------------------------------------------------------

#: The sequence-block size the release chunks long records at, in characters. A record longer
#: than this appears as several `|tag|block` pairs concatenated into one row, each carrying the
#: same tag, rather than as several rows. Established empirically from the release and asserted
#: on every pass rather than trusted: :class:`RowShape` carries the evidence per row, and a row
#: whose last block is full-length is the signature of a record that might continue into the
#: next row — the one thing that would break "one row, one record".
BLOCK_CHARS = 131_072


@dataclasses.dataclass(frozen=True)
class RowShape:
    """What one released row turned out to contain.

    The fields exist to be checked rather than assumed. `tags` holding more than one distinct
    value would mean a row packs more than one record, and the row would stop being a countable
    unit; `last_block_full` being true would mean a record may continue into the following row,
    with the same consequence. Both are counted over the whole pass and reported with the
    result, because "one row is one record" is the premise every count in A7.1 rests on and it
    is a property of the release that nobody published.
    """

    n_blocks: int
    tags: tuple[str, ...]
    total_chars: int
    sequence_chars: int
    last_block_full: bool

    @property
    def distinct_tags(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.tags)))

    @property
    def is_single_record(self) -> bool:
        return len(self.distinct_tags) == 1 and not self.last_block_full


def split_row(row: str) -> RowShape:
    """Split one released row into its `|tag|block` pairs, keeping no sequence.

    The sequence is measured and dropped. That is deliberate and not merely tidy: this project
    keeps no genomic sequence in an artefact (D-103), and a scan that never holds any cannot leak
    any, so the
    in-region pass can emit its result straight to the audit store.
    """
    if not row.startswith("|"):
        return RowShape(0, (), len(row), len(row), False)
    parts = row.split("|")
    # parts[0] is the empty string before the leading delimiter; thereafter the row alternates
    # tag, block, tag, block. A trailing tag with no block is a truncated row, not a pair.
    body = parts[1:]
    tags: list[str] = []
    seq_chars = 0
    last_full = False
    for i in range(0, len(body) - 1, 2):
        tags.append(body[i])
        block = body[i + 1]
        seq_chars += len(block)
        # A block is full when tag and block together fill the chunk: the release's long
        # records come back as `|tag|block` pairs whose tag and block sum to exactly
        # BLOCK_CHARS, with the delimiters on top.
        last_full = len(block) >= BLOCK_CHARS - len(body[i])
    return RowShape(
        n_blocks=len(tags),
        tags=tuple(tags),
        total_chars=len(row),
        sequence_chars=seq_chars,
        last_block_full=last_full,
    )


def record_from_row(row: str, *, record_id: str, component: str) -> tuple[Record, RowShape]:
    """Build a :class:`~amazebio.policyspec.Record` from one released row.

    `attributes`, `host_occurrences` and `similarity_hits` are left empty, and that emptiness is
    the whole point: it is what the release does not carry, and :func:`restrict` reads
    :data:`RELEASE_INPUTS` rather than these fields so that a rule is dropped for a declared
    reason instead of silently evaluating against a blank.
    """
    shape = split_row(row)
    tag = parse_lineage_tag(shape.tags[0]) if shape.tags else LineageTag(raw="", taxonomy={})
    return (
        Record(id=record_id, component=component, taxonomy=dict(tag.taxonomy)),
        shape,
    )


# --------------------------------------------------------------------------------------
# What the release carries, and therefore which rules can be re-executed
# --------------------------------------------------------------------------------------

#: Rule kind -> the input it reads. One name per kind, so a release declares what it carries
#: once and every policy written against these kinds is restricted the same way. Keyed by the
#: kinds frozen in :data:`~amazebio.policyspec.RULE_KINDS`; a new kind there needs an entry
#: here, and :func:`restrict` refuses a kind it does not know rather than assuming it checkable.
#: Which input each frozen rule kind reads. **Re-exported from `amazebio.policyspec`, which is
#: now the single declaration** — A1.4's record-level evaluator derives its `Evidence` checks
#: from the same table (D-057). It was duplicated here and there until they were unified, and
#: they agreed; that they did was luck, and this mapping decides which of an author's rules we
#: hold them to, so one copy is the point. The names and semantics are unchanged.
RULE_INPUTS = policyspec.RULE_INPUTS

#: What each audited release carries per record, by the input names above. This is the
#: declaration the whole restriction hangs on, so it records a property of the published
#: artefact and nothing else.
#:
#: `opengenome-stage2` is Evo 1's own released viral component: one inline lineage tag per
#: record and nothing else — no accession, no vOTU, no confidence label, no host counts
#: (D-020). `opengenome2-imgvr` is Evo 2's release of the same component in FASTA, whose
#: headers carry the IMG/VR accession and no lineage at all, which inverts the problem: its
#: records are traceable to the filter's input and not testable against the filter's taxonomy
#: rules without that input in hand.
#: `imgvr-v4` and `imgvr-v4.1` are not releases of a *filtered* corpus at all: they are the
#: filter's **input**, staged by A1.7, and they carry every input the published procedure reads
#: — the confidence label, the vOTU assignment, the taxonomic classification, and the host
#: predictions the occurrence count is built from. So a policy restricted to them loses no rule
#: for want of an input, which is what moves A7.2's coverage from A7.1's `3/6` (D-047). The
#: declaration is what changed; no rule was hand-picked back in.
RELEASE_INPUTS = {
    "opengenome-stage2": frozenset({"taxonomy"}),
    "opengenome2-imgvr": frozenset({"source_accession"}),
    "imgvr-v4": frozenset({"taxonomy", "record_attributes", "host_occurrences"}),
    "imgvr-v4.1": frozenset({"taxonomy", "record_attributes", "host_occurrences"}),
}

#: What a released record can be *compared* on, which is a different question from what a rule
#: can be *re-executed* against and has to be kept separate from it.
#:
#: Re-executing the published procedure over `imgvr-v4` yields a predicted survivor set. Turning
#: that into a conformance number means matching it against what the developer actually
#: released, and the two Evo releases permit that at different units:
#:
#: * `opengenome-stage2` carries a lineage tag and no accession, so its records cannot be
#:   identified individually at all. The comparison is per lineage — the unit the taxonomy rules
#:   act on anyway — and `imgvr.SEQ_COLUMNS["classification"]` is formatted identically, which is
#:   what makes it a join key rather than a coincidence.
#: * `opengenome2-imgvr` carries the IMG/VR accession and no lineage, which is the exact inverse
#:   (D-049). With the input in hand the accession is a record-level join key and both directions
#:   open per record.
#:
#: A release absent from this mapping can have a predicate re-executed over the input and cannot
#: have the result compared against it. Those are separate findings and the artefact reports them
#: separately.
COMPARISON_KEYS = {
    "opengenome-stage2": "lineage_tag",
    "opengenome2-imgvr": "source_accession",
}

#: The entries in :data:`RELEASE_INPUTS` that are the filter's **input** rather than a corpus
#: some developer released. They have no comparison key because there is nothing to compare them
#: against: a predicate is re-executed *over* them and the result is compared against a release.
#:
#: Declared rather than inferred from absence, and the reason is a near miss. A1.4 declares the
#: same fact at a different granularity — per-record `Evidence` on each `corpora.StagedSource` —
#: and D-057 left both standing with a test pinning their agreement. That test hard-coded the two
#: releases it knew and never enumerated this table, so when A7.2 added `imgvr-v4` and
#: `imgvr-v4.1` it did not fire, and the guard the decision rested on did not cover the case it
#: was written for. Every key here must now be classified as an input or a released output, and
#: a key in neither set fails a test rather than being silently tolerated.
INPUT_RELEASES = frozenset({"imgvr-v4", "imgvr-v4.1"})

#: Rule kinds whose result depends on the order records arrive in. One kind, one rule: Evo 1's
#: vOTU representative. A release or an input can supply every field such a rule reads and still
#: not make it re-executable per record, because what it needs is the *sequence* of records and
#: no published source states one (D-017, D-049). :func:`restrict` therefore holds these apart
#: from both the checkable and the uncheckable rules: they are compared at the unit of the
#: attribute they deduplicate on, by :func:`votu_comparison`, and never at record level.
ORDER_DEPENDENT_KINDS = frozenset({"keep_one_per"})


@dataclasses.dataclass(frozen=True)
class Restriction:
    """A published policy, split into the part a release can re-execute and the part it cannot.

    `policy` is the restricted pipeline, carrying the same id, reading and scope as the
    published one so that a result traces back to the spec it came from. `dropped` is not a
    footnote: it is the coverage limit the write-up has to state, and it is why
    :attr:`Coverage.rule_coverage` is reported next to every count.

    `deferred` is the third category, and it exists because A7.2 made the second one too coarse.
    A rule lands there when the input carries every field it reads and the rule still cannot be
    re-executed per record, which on the published procedures means one thing: it is
    order-dependent and no input order is published. Folding those into `dropped` would say the
    input is missing when it is not, and folding them into `kept` would hand :func:`diff` a rule
    that reports zero removals for a structural reason and reads as conformance. They are
    compared at their own unit instead, and counted in the coverage denominator either way —
    a rule nobody can run is not a rule nobody has to mention.

    Note what the restricted pipeline therefore is when `deferred` is non-empty: a
    **deduplication-free** chain. Every record is put to the remaining rules rather than only
    the vOTU representatives, which is the right question to ask per record and is not the
    published procedure's own record count. :func:`votu_bounds` is what puts the dedup back.
    """

    policy: Policy
    kept: tuple[Rule, ...]
    dropped: tuple[tuple[Rule, str], ...]
    release: str
    deferred: tuple[tuple[Rule, str], ...] = ()

    @property
    def n_rules(self) -> int:
        return len(self.kept) + len(self.dropped) + len(self.deferred)

    @property
    def rule_coverage(self) -> str:
        """Record-level coverage: how many of the published rules this input runs per record."""
        return f"{len(self.kept)}/{self.n_rules}"


def restrict(policy: Policy, *, release: str) -> Restriction:
    """Derive the part of `policy` a named release can re-execute.

    Mechanical on purpose. Hand-picking the testable rules would put the most consequential
    judgement in A7.1 — which of an author's rules we hold them to — into an unreviewable list,
    and a reader could not tell a rule dropped because the release omits its input from one
    dropped because it was inconvenient.
    """
    if release not in RELEASE_INPUTS:
        raise KeyError(
            f"no input inventory declared for release {release!r}; "
            f"known: {sorted(RELEASE_INPUTS)}"
        )
    available = RELEASE_INPUTS[release]
    kept: list[Rule] = []
    dropped: list[tuple[Rule, str]] = []
    deferred: list[tuple[Rule, str]] = []
    for rule in policy.rules:
        needed = RULE_INPUTS.get(rule.kind)
        if needed is None:
            raise KeyError(
                f"rule {rule.id!r} is of kind {rule.kind!r}, which declares no input in "
                "RULE_INPUTS. Add it there rather than letting it default to checkable."
            )
        if needed not in available:
            dropped.append((rule, needed))
        elif rule.kind in ORDER_DEPENDENT_KINDS:
            # The input is there; the published input *order* is not. Held out of the
            # record-level chain and compared at the unit it deduplicates on.
            deferred.append((rule, f"order-dependent on {rule.params['attribute']}"))
        else:
            kept.append(rule)
    if not kept:
        raise ValueError(
            f"release {release!r} can re-execute none of policy {policy.id!r}: it carries "
            f"{sorted(available)} and the policy reads "
            f"{sorted({RULE_INPUTS[r.kind] for r in policy.rules})}. That is a reportable "
            "limit, not a run."
        )
    return Restriction(
        policy=dataclasses.replace(policy, rules=kept),
        kept=tuple(kept),
        dropped=tuple(dropped),
        release=release,
        deferred=tuple(deferred),
    )


@dataclasses.dataclass(frozen=True)
class Coverage:
    """How much of a published policy a release let us re-execute, and what it did not.

    Reported alongside every conformance number, never separately. A failure rate computed over
    three of a policy's six rules is a statement about those three rules, and a reader given the
    rate without the denominator will take it for the policy.
    """

    release: str
    policy_id: str
    reading: str
    kept_rules: tuple[str, ...]
    dropped_rules: tuple[tuple[str, str], ...]
    deferred_rules: tuple[tuple[str, str], ...] = ()

    @property
    def n_rules(self) -> int:
        return len(self.kept_rules) + len(self.dropped_rules) + len(self.deferred_rules)

    @property
    def rule_coverage(self) -> str:
        """Record-level coverage. A deferred rule counts against it, like a dropped one."""
        return f"{len(self.kept_rules)}/{self.n_rules}"

    @property
    def unit_coverage(self) -> str:
        """Coverage once rules compared at their own unit are counted as run.

        Reported *beside* :attr:`rule_coverage` and never instead of it. The vOTU rule is
        compared at vOTU level, which is a real check of a real rule and is not a record-level
        conformance rate; a single number that mixed the two would be neither.
        """
        return f"{len(self.kept_rules) + len(self.deferred_rules)}/{self.n_rules}"

    @classmethod
    def of(cls, restriction: Restriction, policy: Policy) -> Coverage:
        return cls(
            release=restriction.release,
            policy_id=policy.id,
            reading=policy.reading,
            kept_rules=tuple(r.id for r in restriction.kept),
            dropped_rules=tuple((r.id, why) for r, why in restriction.dropped),
            deferred_rules=tuple((r.id, why) for r, why in restriction.deferred),
        )


# --------------------------------------------------------------------------------------
# Causes, frozen before anything is counted
# --------------------------------------------------------------------------------------


class Cause(Enum):
    """Why a record survived a rule that says it should not have.

    The first four are §A7's own four causes. The fifth is the one §A7 implies without naming
    and the only one that is a finding about the filter rather than about the corpus or the
    prose: the rule applies, the annotation it reads is present and sufficient, and the record
    is in the release anyway.
    """

    PREDICATE_AMBIGUOUS = "predicate_ambiguous"
    ANNOTATION_MISSING = "annotation_missing"
    ANNOTATION_MALFORMED = "annotation_malformed"
    POSTDATES_FILTER = "postdates_filter"
    OUT_OF_COMPONENT = "out_of_component"
    UNEXPLAINED = "unexplained"


#: Cause -> what it means and what it licenses a write-up to say. Frozen here, before any
#: counting, because §A7 requires the causes defined before the count and because a category
#: invented once the numbers are visible is a category chosen to suit them.
CAUSES = {
    Cause.PREDICATE_AMBIGUOUS: (
        "The rule fired, but the published words underdetermine whether this record is within "
        "it. Evo 1's unspecificity rule is the live case: it enumerates eight stop-taxa after "
        "the word 'including', and the generalisation that word invites is not recoverable from "
        "the text. A record the enumeration does not name but a generalisation would is counted "
        "here, not as a failure."
    ),
    Cause.ANNOTATION_MISSING: (
        "The rule fired because an annotation it reads is absent from the record — no realm "
        "assigned, no rank filled at all. The rule as published removes such a record, and the "
        "release kept it. A failure of the filter, with the cause located in the data it ran on."
    ),
    Cause.ANNOTATION_MALFORMED: (
        "The record's lineage tag did not parse against the scheme the rest of the release "
        "uses. Counted apart from everything else: it may be a release defect and it may be our "
        "reading, and until that is settled it is neither a failure nor a clean record."
    ),
    Cause.POSTDATES_FILTER: (
        "The record entered the released corpus after the filter ran, so no re-execution of the "
        "filter could have removed it. Not assignable from the OpenGenome releases, which "
        "publish no per-record provenance date; reserved rather than used, and a count of zero "
        "here means unassignable, not absent."
    ),
    Cause.OUT_OF_COMPONENT: (
        "The rule does not reach this record's component, so the filter was never pointed at "
        "it. Survival is then the published design rather than a failure — the distinction "
        "DECISIONS.md D-007 insists on and A4.3 quantifies."
    ),
    Cause.UNEXPLAINED: (
        "The rule applies to this record's component, the annotation it reads is present and "
        "names a taxon the published rule removes, and the record is in the release. Nothing in "
        "the release or the prose accounts for it. This is the conformance failure A7 is looking "
        "for, and the only cause that is a finding about the filter itself."
    ),
}


# --------------------------------------------------------------------------------------
# The diff
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Failure:
    """One released record the policy says should have been removed, and why it survived."""

    record_id: str
    rule_id: str
    cause: Cause
    why: str
    taxonomy: dict[str, str]
    n_records: int = 1


def classify(decision: Decision, record: Record, *, tag: LineageTag, rule: Rule) -> Cause:
    """Assign a cause to one removal the release did not perform. Total onto :data:`CAUSES`.

    Ordered most-specific first, and the ordering carries weight. A malformed tag is classified
    as malformed whatever else is true of it, because every later test reads the fields that
    failed to parse. An absent annotation is separated from a present one because the two license
    different claims: the first says the filter did not remove what its own rule calls
    unassigned, the second says it did not remove a taxon it names.
    """
    if tag.is_malformed:
        return Cause.ANNOTATION_MALFORMED
    if decision.outcome is Outcome.OUT_OF_SCOPE:
        return Cause.OUT_OF_COMPONENT
    if rule.kind == "remove_if_unspecific":
        # The rule has two limbs. "No assigned realm at all" is stated outright, so a record
        # it fires on is an absent-annotation failure. The stop-taxon limb is the enumeration
        # after "including", and a record whose finest assignment is one of the eight named
        # taxa is squarely inside the stated list rather than inside the generalisation.
        if not record.taxonomy.get(rule.params["require_rank"]):
            return Cause.ANNOTATION_MISSING
        return Cause.UNEXPLAINED
    # `remove_if_taxon_in` fires only on a record that *has* the rank and whose taxon is on the
    # published list, so there is no missing-annotation case left for it to reach: a record with
    # no family assigned is removed, if at all, by the unspecificity rule above. Any removal
    # arriving here is a named taxon the release kept.
    return Cause.UNEXPLAINED


def diff(
    policy: Policy,
    rows: Iterable[tuple[str, Record, LineageTag, int]],
    *,
    release: str,
) -> tuple[list[Failure], Coverage]:
    """Re-execute the checkable part of `policy` against released records.

    `rows` yields `(record_id, record, parsed_tag, n_records)`. The weight is there because the
    in-region pass aggregates identical lineage tags before this runs: the tag space is a few
    hundred values against millions of records, so the scan emits counts per distinct tag and
    the diff is computed over those. The arithmetic is identical and the intermediate is small
    enough to publish, which is what makes the headline numbers reproducible from an artefact
    rather than from a re-run of the scan.

    A removal the restricted policy makes is a record the release should not contain. Everything
    the policy retains is simply absent from the result: this is the forward direction only. The
    converse — records removed that the policy does not call for — needs the filter's input,
    IMG/VR v4, which this project has not acquired, and no count here speaks to it.
    """
    restriction = restrict(policy, release=release)
    order_dependent = [r.id for r in restriction.kept if r.kind == "keep_one_per"]
    if order_dependent:
        # Each record is evaluated on its own, and the scan aggregates identical tags before
        # getting here, so the input order the published pipeline depends on is gone twice over.
        # `keep_one_per` would then retain every record as its own representative and report
        # zero removals, which reads as conformance. D-017 already records that the vOTU rule is
        # not reproducible for want of a published input order; this refuses rather than
        # producing the number that would hide it.
        raise ValueError(
            f"policy {policy.id!r} keeps order-dependent rule(s) {order_dependent} against "
            f"release {release!r}. This diff evaluates records independently and over tags "
            "aggregated by the scan, so an order-dependent rule cannot be re-executed here: "
            "compute it at the level of the attribute it deduplicates on, per D-017."
        )
    by_rule = {r.id: r for r in restriction.kept}
    failures: list[Failure] = []
    for record_id, record, tag, weight in rows:
        decisions: Sequence[Decision] = evaluate(restriction.policy, [record])
        decision = decisions[0]
        if decision.outcome is Outcome.RETAINED:
            continue
        rule = by_rule.get(decision.rule_id or "")
        if rule is None:
            # OUT_OF_SCOPE carries no rule; nothing removed the record, so nothing failed.
            continue
        failures.append(
            Failure(
                record_id=record_id,
                rule_id=rule.id,
                cause=classify(decision, record, tag=tag, rule=rule),
                why=decision.why,
                taxonomy=dict(record.taxonomy),
                n_records=weight,
            )
        )
    return failures, Coverage.of(restriction, policy)


def readings_agree_by_construction(
    policies: Mapping[str, Policy], *, release: str
) -> tuple[bool, dict[str, tuple[str, ...]]]:
    """Whether a release can test any rule the readings of one policy disagree about.

    Returns the verdict and the kept-rule list per reading. When the lists are identical the
    readings cannot diverge on this release whatever the data says, and the write-up must report
    that as a limit of the release rather than as three readings agreeing. §A7 asks for the
    spread across readings; this is how A7.1 answers that the spread is unmeasurable here, and
    says so from the specs rather than from identical output columns.
    """
    kept = {
        p.reading: tuple(r.id for r in restrict(p, release=release).kept) for p in policies.values()
    }
    return len(set(kept.values())) == 1, kept


# --------------------------------------------------------------------------------------
# The input side: the counting unit of the host rule, and the vOTU rule's own unit
# --------------------------------------------------------------------------------------


class HostUnit(Enum):
    """What "found within a prokaryotic host at least twice" counts two of.

    The published sentence is "keeping only sequences whose assigned taxonomic classification
    was found within a prokaryotic host at least twice". Two things in it are settled and one is
    not. Settled: the subject of the count is the **classification**, not the record — D-058
    establishes that from the developers' own Figure S1B, where 89.5% of retained records carry
    no host kingdom at all, which a per-record reading cannot produce. Not settled: what one
    "finding" is, because the publisher's data offers three countable things per classification
    and the sentence does not say which.

    All three are computed; :data:`PRIMARY_HOST_UNIT` is the one the headline uses, and it was
    declared before any of them was computed.
    """

    #: Sequences of this classification carrying a host prediction in the class. One sequence
    #: found in a host is one finding, which is the reading that takes "found" to be about the
    #: viral sequence the sentence's own subject ("sequences") is about.
    RECORDS = "records"
    #: Rows of the host-prediction table for sequences of this classification. The publisher
    #: emits one row per prediction and a sequence may have several, so this counts predictions
    #: rather than sequences — the most literal reading of "found", and the one that inflates
    #: fastest where a single sequence has many predicted hosts.
    HOST_ROWS = "host_rows"
    #: Distinct host taxa this classification was predicted in. The reading that takes "twice"
    #: to mean corroboration by two different hosts rather than two observations.
    HOST_TAXA = "host_taxa"


#: The reading the headline numbers use. Declared here, before the pass that computes any of
#: them, which is what AGENTS.md's rule about fixing parameters before inspecting results
#: requires. The argument for it in one line: the sentence's grammatical subject is "sequences",
#: so a sequence found in a prokaryotic host is the natural unit of a finding, and it is the
#: only one of the three that neither inflates with the publisher's prediction-method count
#: (:attr:`HostUnit.HOST_ROWS`) nor demands two *different* hosts where the text asks only for
#: two findings (:attr:`HostUnit.HOST_TAXA`). The other two travel with it as a sensitivity,
#: because the choice is ours and a reader is entitled to see what it cost.
PRIMARY_HOST_UNIT = HostUnit.RECORDS

#: Human-readable gloss per unit, carried into the artefact so the unit is named where the
#: number is read rather than in a module nobody opens.
HOST_UNITS = {
    HostUnit.RECORDS: (
        "Sequences of this taxonomic classification that carry a host prediction in the class. "
        "The primary reading."
    ),
    HostUnit.HOST_ROWS: (
        "Rows of the host-prediction table for sequences of this classification. Counts "
        "predictions, not sequences: one sequence with three predicted hosts contributes three."
    ),
    HostUnit.HOST_TAXA: (
        "Distinct host taxa this classification was predicted in. Reads 'twice' as two "
        "different hosts rather than two findings."
    ),
}


@dataclasses.dataclass(frozen=True)
class VotuComparison:
    """How many released records each predicted-surviving vOTU contributed.

    This is the vOTU rule's conformance check and the only one it has. The rule keeps one
    representative per vOTU; which one depends on an input order nobody published (D-017), so
    *which* record survives is undetermined and a record-level diff of this rule would measure
    our sort order rather than their filter. What is determined, and is exactly what the rule
    claims, is the **count per vOTU**: one. A vOTU contributing two released records is a
    conformance failure that no order could explain, and a vOTU contributing none is the
    converse direction.

    `unit` is carried in the artefact next to every number here so that it cannot be read as a
    record-level rate.
    """

    unit: str = "vOTU"
    considered: int = 0
    exactly_one: int = 0
    none: int = 0
    more_than_one: int = 0
    released_records_in_multi: int = 0
    histogram: dict[str, int] = dataclasses.field(default_factory=dict)

    @property
    def conformance_rate(self) -> float | None:
        """Share of predicted-surviving vOTUs that contributed exactly one released record."""
        return self.exactly_one / self.considered if self.considered else None

    @property
    def verdict(self) -> str:
        if not self.considered:
            return "No predicted-surviving vOTU could be compared; nothing is claimed."
        if not self.more_than_one and not self.none:
            return (
                f"Every one of {self.considered:,} predicted-surviving vOTUs contributed "
                "exactly one released record. The vOTU rule conforms at its own unit."
            )
        parts = []
        if self.more_than_one:
            parts.append(
                f"{self.more_than_one:,} vOTUs contributed more than one released record "
                f"({self.released_records_in_multi:,} records between them) — a failure no "
                "input order can explain"
            )
        if self.none:
            parts.append(
                f"{self.none:,} contributed none, which is the converse direction and is "
                "accounted for by the other rules only if they remove the whole vOTU"
            )
        return (
            f"Of {self.considered:,} predicted-surviving vOTUs, {self.exactly_one:,} "
            f"contributed exactly one released record; " + "; ".join(parts) + "."
        )


def votu_comparison(histogram: Mapping[int, int]) -> VotuComparison:
    """Summarise a `released records per vOTU -> number of vOTUs` histogram.

    The histogram is computed over the vOTUs the re-executed procedure predicts should survive,
    so the comparison is against the rule's own claim and not against the whole database.
    """
    considered = sum(histogram.values())
    return VotuComparison(
        considered=considered,
        exactly_one=histogram.get(1, 0),
        none=histogram.get(0, 0),
        more_than_one=sum(n for k, n in histogram.items() if k > 1),
        released_records_in_multi=sum(k * n for k, n in histogram.items() if k > 1),
        histogram={str(k): n for k, n in sorted(histogram.items())},
    )


def votu_bounds(
    single: Mapping[str, int],
    mixed: Sequence[tuple[Sequence[str], int]],
    passes: Mapping[str, bool],
) -> tuple[int, int]:
    """Bound the number of vOTUs the published chain retains, given which classifications pass.

    The published order is: keep high-confidence, keep one representative per vOTU, then the
    host and taxonomy rules. So a vOTU contributes its representative and that record is
    retained if its own classification passes the later rules — which makes the retained count a
    function of a choice nobody published. It is therefore an interval and not a number, and
    reporting it as a number would be reporting our sort order as their result.

    * `single` maps a classification to the number of vOTUs **all** of whose high-confidence
      records carry it. For these the representative's classification is determined.
    * `mixed` lists the vOTUs whose high-confidence records carry more than one classification,
      as `(classifications, n_votus)`. These are where the interval comes from.
    * `passes` says whether a classification survives the later rules.

    Returns `(lower, upper)`: the lower bound takes every mixed vOTU to pick a failing
    representative where it can, the upper bound takes every one to pick a passing one. They
    coincide exactly when no mixed vOTU straddles the predicate — which is the common case, and
    is why the interval is usually tight enough to compare against a published count.
    """
    lower = upper = sum(n for c, n in single.items() if passes.get(c, False))
    for classifications, n in mixed:
        verdicts = [passes.get(c, False) for c in classifications]
        if all(verdicts):
            lower += n
            upper += n
        elif any(verdicts):
            upper += n
    return lower, upper

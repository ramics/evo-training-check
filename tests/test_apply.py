"""Tests for amazebio.apply and the evidence semantics it depends on — task A1.4.

Three things here are worth more than coverage.

**The unsafe default.** Before A1.4, a rule reading an attribute the corpus does not carry read
`None`, found it absent from the allowed values, and removed the record. Run over Evo's release
that would report the filter as having removed its entire viral component — a clean pass,
manufactured from missing metadata. `test_a_missing_attribute_is_unresolved_not_removed` is the
regression test for the most consequential wrong answer this pipeline could give.

**The resolution lattice** (D-044). Three of Evo's six published rules read metadata the
release does not carry, and they run first. Stopping at the first undecidable rule, as the
reference evaluator does, would lose every removal the denylist rules make — including the
records that are candidate conformance failures, which are the point.

**The refusal to route a removal.** `metrics/survival.md` reserves `CONFORMANCE_FAILURE` for
A7.1 with record-level evidence, and §7 requires it to be airtight. `route_for` enforces that
in code rather than trusting a detector to remember.
"""

from __future__ import annotations

import pytest

from amazebio.apply import (
    PRECEDENCE,
    ManifestError,
    PolicyManifest,
    SourceVerdict,
    applicable_rules,
    is_uniform,
    resolve,
    route_for,
    uniform_verdict,
)
from amazebio.policyspec import (
    Evidence,
    Outcome,
    Policy,
    Record,
    Rule,
    Scope,
    decide,
    evaluate,
)
from amazebio.survival import Route

# --------------------------------------------------------------------------------------
# Fixtures: a miniature of Evo's published pipeline, with its real shape
# --------------------------------------------------------------------------------------

CONFIDENCE = Rule(
    id="keep-high-confidence",
    kind="keep_if_attribute_in",
    params={"attribute": "confidence", "values": ["High-confidence"]},
    source="S-TEST",
)
VOTU = Rule(id="keep-one-per-votu", kind="keep_one_per", params={"attribute": "vOTU"}, source="S")
HOSTS = Rule(
    id="keep-prokaryotic-host-twice",
    kind="keep_if_host_occurrence_at_least",
    params={"host_class": "prokaryotic", "count": 2},
    source="S",
)
FAMILIES = Rule(
    id="remove-denylisted-families",
    kind="remove_if_taxon_in",
    params={"rank": "family", "names": ["Coronaviridae", "Filoviridae"]},
    source="S",
)
UNSPECIFIC = Rule(
    id="remove-taxonomically-unspecific",
    kind="remove_if_unspecific",
    params={
        "require_rank": "realm",
        "ranks": ["realm", "family"],
        "stop_taxa": ["Riboviria"],
    },
    source="S",
)

#: What Evo 1's release actually carries for its viral component: taxonomy, nothing else.
RELEASED = Evidence(taxonomy_ranks=frozenset({"realm", "family"}))


def policy(*rules: Rule, components: list[str] | None = None) -> Policy:
    return Policy(
        id="test",
        model="test",
        reading="literal",
        source="S",
        scope=Scope(components=components or ["IMG/VR"]),
        rules=list(rules),
    )


def record(**kw: object) -> Record:
    kw.setdefault("id", "r1")
    kw.setdefault("component", "IMG/VR")
    return Record(**kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------


def test_a_missing_attribute_is_unresolved_not_removed() -> None:
    decision = decide(CONFIDENCE, record(), kept_values={}, evidence=RELEASED)
    assert decision is not None
    assert decision.outcome is Outcome.UNRESOLVED
    assert "does not carry" in decision.why


def test_the_same_rule_still_removes_where_the_evidence_exists() -> None:
    evidence = Evidence(attributes=frozenset({"confidence"}))
    decision = decide(
        CONFIDENCE, record(attributes={"confidence": "Low"}), kept_values={}, evidence=evidence
    )
    assert decision is not None and decision.outcome is Outcome.REMOVED


def test_an_absent_rank_inside_a_carried_channel_is_data_not_missing_evidence() -> None:
    """ "No family assigned" is what the denylist and unspecificity rules are there to see."""
    subject = record(taxonomy={"realm": "Duplodnaviria"})
    decision = decide(FAMILIES, subject, kept_values={}, evidence=RELEASED)
    assert decision is None


def test_exclusivity_rules_need_the_whole_host_channel() -> None:
    """Partial host evidence cannot establish "and in no other host class"."""
    rule = Rule(
        id="x",
        kind="keep_if_host_evidence_exclusive",
        params={"host_class": "prokaryotic", "count": 2},
        source="S",
    )
    partial = Evidence(host_classes=frozenset({"prokaryotic"}))
    assert rule.required_evidence() == (("host_occurrences", "*"),)
    assert partial.missing_for(rule) == ["host_occurrences:*"]
    assert not Evidence(host_classes=frozenset({"*"})).missing_for(rule)


def test_every_rule_kind_declares_what_it_reads() -> None:
    """A new kind cannot be added without saying which channels it reads."""
    from amazebio.policyspec import RULE_KINDS, _required_evidence

    samples = {
        "keep_if_attribute_in": {"attribute": "a", "values": []},
        "keep_one_per": {"attribute": "a"},
        "keep_if_host_occurrence_at_least": {"host_class": "p", "count": 1},
        "remove_if_taxon_in": {"rank": "family", "names": []},
        "remove_if_unspecific": {"require_rank": "realm", "stop_taxa": [], "ranks": ["realm"]},
        "remove_if_similar_to": {"seed_set": "s", "identity_threshold": 0.7},
        "remove_if_host_class_in": {"host_classes": []},
        "keep_if_host_evidence_exclusive": {"host_class": "p", "count": 1},
    }
    assert set(samples) == set(RULE_KINDS), "a rule kind was added without an evidence sample"
    for kind, params in samples.items():
        assert _required_evidence(kind, params), kind


def test_an_unpublished_parameter_outranks_a_missing_corpus_channel() -> None:
    """The policy gap is the finding; the corpus gap is only reachable once it is closed."""
    from amazebio.policyspec import Unspecified

    rule = Rule(
        id="esm3",
        kind="remove_if_similar_to",
        params={"seed_set": "viral-denylist", "identity_threshold": Unspecified("never published")},
        source="S",
    )
    decision = decide(rule, record(), kept_values={}, evidence=Evidence())
    assert decision is not None and decision.outcome is Outcome.UNDETERMINED


# --------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------


def test_a_removal_survives_earlier_undecidable_rules() -> None:
    """The lattice's reason for existing: the undecidable rules come first in the real pipeline."""
    spec = policy(CONFIDENCE, VOTU, HOSTS, FAMILIES)
    decision = resolve(
        spec, record(taxonomy={"realm": "Riboviria", "family": "Coronaviridae"}), evidence=RELEASED
    )
    assert decision.outcome is Outcome.REMOVED
    assert decision.rule_id == "remove-denylisted-families"


def test_the_reference_evaluator_stops_where_the_corpus_evaluator_continues() -> None:
    """Pins the difference D-044 records, so neither is changed into the other by accident."""
    spec = policy(CONFIDENCE, FAMILIES)
    subject = record(taxonomy={"realm": "Riboviria", "family": "Coronaviridae"})
    # The reference evaluator assumes every channel is present, so it removes at rule 1.
    assert evaluate(spec, [subject])[0].rule_id == "keep-high-confidence"
    assert resolve(spec, subject, evidence=RELEASED).rule_id == "remove-denylisted-families"


def test_retention_requires_every_rule_to_have_been_checked() -> None:
    spec = policy(CONFIDENCE, FAMILIES)
    decision = resolve(spec, record(taxonomy={"realm": "Duplodnaviria"}), evidence=RELEASED)
    assert decision.outcome is Outcome.UNRESOLVED
    assert decision.rule_id == "keep-high-confidence"


def test_retained_only_when_nothing_is_undecidable() -> None:
    spec = policy(FAMILIES, UNSPECIFIC)
    decision = resolve(
        spec, record(taxonomy={"realm": "Duplodnaviria", "family": "Inoviridae"}), evidence=RELEASED
    )
    assert decision.outcome is Outcome.RETAINED


def test_the_first_removing_rule_in_published_order_is_attributed() -> None:
    """A conformance claim cites a rule, so it must be the one the authors wrote first."""
    spec = policy(UNSPECIFIC, FAMILIES)
    decision = resolve(spec, record(taxonomy={"family": "Coronaviridae"}), evidence=RELEASED)
    assert decision.outcome is Outcome.REMOVED
    assert decision.rule_id == "remove-taxonomically-unspecific"


def test_out_of_scope_beats_every_rule() -> None:
    spec = policy(FAMILIES)
    subject = record(component="GTDB", taxonomy={"family": "Coronaviridae"})
    decision = resolve(spec, subject, evidence=RELEASED)
    assert decision.outcome is Outcome.OUT_OF_SCOPE
    assert decision.rule_id is None


def test_precedence_order_is_the_documented_one() -> None:
    assert PRECEDENCE == (
        Outcome.REMOVED,
        Outcome.UNDETERMINED,
        Outcome.UNRESOLVED,
        Outcome.RETAINED,
    )


def test_a_wildcard_scope_retains_what_no_rule_reaches() -> None:
    """A0.3's asymmetry, and the whole difference between the strict and literal readings."""
    narrowed = Rule(
        id="remove-denylisted-families",
        kind="remove_if_taxon_in",
        params={"rank": "family", "names": ["Coronaviridae"]},
        source="S",
        components=["IMG/VR"],
    )
    spec = policy(narrowed, components=[Scope.ANY])
    assert resolve(spec, record(component="GTDB"), evidence=RELEASED).outcome is Outcome.RETAINED
    assert resolve(spec, record(component="GTDB"), evidence=RELEASED).why == "no rule removed it"


# --------------------------------------------------------------------------------------
# Uniformity
# --------------------------------------------------------------------------------------


def test_a_component_no_rule_reaches_is_uniform() -> None:
    narrowed = Rule(
        id="remove-denylisted-families",
        kind="remove_if_taxon_in",
        params={"rank": "family", "names": ["Coronaviridae"]},
        source="S",
        components=["IMG/VR"],
    )
    spec = policy(narrowed, components=[Scope.ANY])
    assert applicable_rules(spec, "GTDB") == []
    assert applicable_rules(spec, "IMG/VR") == [narrowed]
    assert is_uniform(spec, "GTDB", RELEASED)
    assert uniform_verdict(spec, "GTDB", RELEASED).outcome is Outcome.RETAINED


def test_a_component_with_no_usable_evidence_is_uniform() -> None:
    """Evo 2's viral component: every rule reaches it and none can be decided against it."""
    spec = policy(CONFIDENCE, FAMILIES, UNSPECIFIC)
    no_taxonomy = Evidence(attributes=frozenset({"accession"}))
    assert is_uniform(spec, "IMG/VR", no_taxonomy)
    assert uniform_verdict(spec, "IMG/VR", no_taxonomy).outcome is Outcome.UNRESOLVED


def test_a_component_a_rule_can_discriminate_is_not_uniform() -> None:
    spec = policy(CONFIDENCE, FAMILIES)
    assert not is_uniform(spec, "IMG/VR", RELEASED)
    with pytest.raises(ManifestError, match="enumerate instead"):
        uniform_verdict(spec, "IMG/VR", RELEASED)


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


def test_routes_map_the_outcomes_a_manifest_can_support() -> None:
    assert route_for(Outcome.OUT_OF_SCOPE) is Route.OUT_OF_SCOPE
    assert route_for(Outcome.RETAINED) is Route.RETAINED_BY_DESIGN
    assert route_for(Outcome.UNRESOLVED) is Route.UNRESOLVED
    assert route_for(Outcome.UNDETERMINED) is Route.UNRESOLVED


def test_a_removal_cannot_be_routed_as_a_conformance_failure() -> None:
    with pytest.raises(ManifestError, match="A7.1"):
        route_for(Outcome.REMOVED)


# --------------------------------------------------------------------------------------
# Manifests
# --------------------------------------------------------------------------------------


def test_totals_count_only_enumerated_sources() -> None:
    """An unenumerated component's verdict is uniform; counting it as zero would be a lie."""
    manifest = PolicyManifest(
        policy_id="p", model="m", reading="literal", release="r", scope=["IMG/VR"]
    )
    manifest.sources = [
        SourceVerdict(
            key="a",
            component="IMG/VR",
            corpus_component="stage2",
            release="r",
            bytes=1,
            records=10,
            enumerated=True,
            uniform=False,
            counts={"removed": 3, "unresolved": 7},
        ),
        SourceVerdict(
            key="b",
            component="GTDB",
            corpus_component="gtdb",
            release="r",
            bytes=None,
            records=None,
            enumerated=False,
            uniform=True,
            uniform_outcome="retained",
        ),
    ]
    assert manifest.totals() == {"removed": 3, "unresolved": 7}
    payload = manifest.to_dict()
    assert payload["records_enumerated"] == 10
    assert payload["sources"][1]["records"] is None
    assert "candidate conformance failures" in payload["reading_this_manifest"]


# --------------------------------------------------------------------------------------
# The two input declarations must not drift
# --------------------------------------------------------------------------------------


def test_rule_inputs_is_one_table_not_two() -> None:
    """A1.4 reads it through Evidence, A7.1 through its restriction. One table (D-057)."""
    from amazebio import conformance as cf
    from amazebio.policyspec import RULE_INPUTS

    assert cf.RULE_INPUTS is RULE_INPUTS


def test_every_rule_kind_is_declared_in_it() -> None:
    from amazebio.policyspec import RULE_INPUTS, RULE_KINDS

    assert set(RULE_INPUTS) == set(RULE_KINDS), (
        "a rule kind with no declared input would be silently treated as checkable by A7.1 "
        "and as answerable by A1.4"
    )


def test_the_two_release_declarations_agree_on_what_can_be_re_executed() -> None:
    """The inventory A7.1 restricts by and the evidence A1.4 checks per record are different
    granularities of the same fact, and D-057 left both standing rather than refactor a module
    under review. This is the guard that makes that safe: if they ever disagree about which
    rules a release can re-execute, the audit is claiming two different things about the same
    rules, and the one that drifted is whichever this test names.
    """
    from pathlib import Path

    from amazebio import conformance as cf
    from amazebio import corpora
    from amazebio.policyspec import load_policy_dir

    specs = load_policy_dir(Path(__file__).resolve().parents[1] / "policies" / "specs")
    evo = [p for p in specs.values() if p.id.startswith("evo1-")]
    assert evo, "the Evo specs are what both declarations are declared over"

    def kept_by_evidence(policy: Policy, source: object) -> set[str]:
        return {
            rule.id
            for rule in policy.rules
            if not rule.unspecified_params() and not source.evidence.missing_for(rule)
        }

    stage2 = next(s for s in corpora.SOURCES if s.corpus_component == "stage2")
    for policy in evo:
        kept = {r.id for r in cf.restrict(policy, release="opengenome-stage2").kept}
        assert kept == kept_by_evidence(policy, stage2), (
            f"{policy.id} on opengenome-stage2: A7.1 would re-execute {kept}, "
            f"A1.4's evidence says {kept_by_evidence(policy, stage2)}"
        )

    # Evo 2's release carries an accession and nothing any rule reads, so both declarations say
    # nothing is re-executable against it. A7.1 raises rather than returning an empty pipeline
    # a caller could run and report zero failures from; A1.4 records every record as unresolved.
    imgvr = next(s for s in corpora.SOURCES if s.corpus_component == "imgvr")
    for policy in evo:
        assert kept_by_evidence(policy, imgvr) == set()
        with pytest.raises(ValueError, match="can re-execute none"):
            cf.restrict(policy, release="opengenome2-imgvr")


def test_the_release_declarations_are_checked_for_every_release_not_just_two() -> None:
    """Enumerate the inventory, which the test above does not.

    `test_the_two_release_declarations_agree_on_what_can_be_re_executed` names the two releases
    it knows. That catches the pair drifting apart and is blind to a third being added, which is
    exactly what happened: A7.2 added `imgvr-v4` and `imgvr-v4.1` to
    `conformance.RELEASE_INPUTS` and nothing failed, although A1.4's own closing note predicted
    it would. This drives off the table instead, so a release added on one side and forgotten on
    the other fails here.

    The join is mechanical rather than a second hard-coded map: a `corpora.StagedSource` is
    addressed by `f"{release}-{corpus_component}"`, which is the key `RELEASE_INPUTS` uses.
    """
    from pathlib import Path

    from amazebio import conformance as cf
    from amazebio import corpora
    from amazebio.policyspec import load_policy_dir

    specs = load_policy_dir(Path(__file__).resolve().parents[1] / "policies" / "specs")
    evo = [p for p in specs.values() if p.id.startswith("evo1-")]
    by_key = {
        f"{s.release}-{s.corpus_component}": s for s in corpora.SOURCES + corpora.ESM3_SOURCES
    }

    for key in sorted(cf.RELEASE_INPUTS):
        if key in cf.INPUT_RELEASES:
            # The filter's input. A1.4 evaluates released corpora, so it must not claim one.
            assert key not in by_key, (
                f"{key} is declared as the filter's input but `corpora` also stages it as a "
                "released source; one of the two declarations is wrong about what it is"
            )
            continue
        source = by_key.get(key)
        assert source is not None, (
            f"{key} is in RELEASE_INPUTS and classified as a released output, but no "
            f"corpora.StagedSource is addressed by it. Known: {sorted(by_key)}"
        )
        for policy in evo:
            by_evidence = {
                rule.id
                for rule in policy.rules
                if not rule.unspecified_params() and not source.evidence.missing_for(rule)
            }
            try:
                restricted = {r.id for r in cf.restrict(policy, release=key).kept}
            except ValueError:
                # `restrict` refuses a release that can re-execute nothing rather than handing
                # back an empty pipeline a caller could report zero failures from.
                restricted = set()
            assert restricted == by_evidence, (
                f"{policy.id} on {key}: the inventory says {sorted(restricted)}, the staged "
                f"source's evidence says {sorted(by_evidence)}"
            )

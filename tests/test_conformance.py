"""Tests for A7.1's conformance re-execution.

Three things are pinned here, in rough order of how expensive they would be to get wrong.

The **restriction** is first, because it decides which of an author's rules we hold them to.
A bug that let a rule through whose input the release does not carry would not raise: it would
evaluate against an empty field and remove every record in the corpus, and the resulting
"conformance failure rate of 100%" would be a statement about our missing metadata published as
a statement about somebody's filter.

The **cause assignment** is second. §A7 requires causes defined before counting, and the test
that matters is not that each cause can be produced but that the headline one cannot be reached
by accident — an absent annotation and a named taxon are different findings and must not collapse
into each other.

The **tag parser** is third and is tested against the shapes the release actually contains,
including the two that a parser written from the documented format alone would get wrong: a tag
with no realm but a family, and a long record arriving as several same-tag blocks in one row.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amazebio import conformance as cf
from amazebio.policyspec import Policy, Rule, Scope, load_policy_dir

SPECS = Path(__file__).resolve().parent.parent / "policies" / "specs"

# Tags taken from the release itself, via the row groups sampled while A7.1 was designed.
CAUDO = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;"
INOVIRIDAE = (
    "r__Monodnaviria;k__Loebvirae;p__Hofneiviricota;c__Faserviricetes;"
    "o__Tubulavirales;f__Inoviridae;;"
)
NO_REALM = ";;;;;f__Fuselloviridae;;"
LEVI = "r__Riboviria;k__Orthornavirae;p__Lenarviricota;c__Leviviricetes;;;;"


# --------------------------------------------------------------------------------------
# The tag parser
# --------------------------------------------------------------------------------------


def test_parses_a_canonical_tag_to_the_ranks_the_published_rule_names():
    tag = cf.parse_lineage_tag(CAUDO)
    assert not tag.is_malformed
    assert tag.taxonomy == {
        "realm": "Duplodnaviria",
        "kingdom": "Heunggongvirae",
        "phylum": "Uroviricota",
        "class": "Caudoviricetes",
    }
    assert tag.depth == 4


def test_a_tag_with_no_realm_but_a_family_is_well_formed_and_realmless():
    # The case the published unspecificity rule is written for, and the case a positional
    # parser gets wrong: five empty fields then a family.
    tag = cf.parse_lineage_tag(NO_REALM)
    assert not tag.is_malformed
    assert tag.taxonomy == {"family": "Fuselloviridae"}
    assert "realm" not in tag.taxonomy


def test_an_empty_tag_is_well_formed_and_assigns_nothing():
    tag = cf.parse_lineage_tag(";;;;;;;")
    assert not tag.is_malformed
    assert tag.taxonomy == {}
    assert tag.depth == 0


def test_a_short_tag_fills_what_it_has_without_being_malformed():
    tag = cf.parse_lineage_tag("r__Duplodnaviria;k__Heunggongvirae")
    assert not tag.is_malformed
    assert tag.taxonomy == {"realm": "Duplodnaviria", "kingdom": "Heunggongvirae"}


@pytest.mark.parametrize(
    "raw, complaint",
    [
        ("Duplodnaviria;;;;;;;", "no rank prefix"),
        ("x__Something;;;;;;;", "unknown rank prefix"),
        ("k__Heunggongvirae;r__Duplodnaviria;;;;;;", "by prefix but"),
        ("r__;;;;;;;", "names no taxon"),
        (";" * 9, "expected at most"),
    ],
)
def test_malformed_fields_are_recorded_rather_than_guessed(raw, complaint):
    tag = cf.parse_lineage_tag(raw)
    assert tag.is_malformed
    assert any(complaint in m for m in tag.malformed)


def test_a_prefix_position_disagreement_keeps_the_prefix_and_records_the_conflict():
    # Prefix wins, because a mis-ranked taxon would be tested against the wrong denylist.
    tag = cf.parse_lineage_tag("k__Heunggongvirae;r__Duplodnaviria;;;;;;")
    assert tag.taxonomy == {"kingdom": "Heunggongvirae", "realm": "Duplodnaviria"}
    assert tag.is_malformed


# --------------------------------------------------------------------------------------
# Row shape
# --------------------------------------------------------------------------------------


def test_a_short_record_is_one_row_one_block_one_tag():
    shape = cf.split_row(f"|{CAUDO}|" + "ACGT" * 100)
    assert shape.n_blocks == 1
    assert shape.distinct_tags == (CAUDO,)
    assert shape.sequence_chars == 400
    assert not shape.last_block_full
    assert shape.is_single_record


def test_a_long_record_arrives_as_several_same_tag_blocks_in_one_row():
    full = cf.BLOCK_CHARS - len(CAUDO)
    row = f"|{CAUDO}|" + "A" * full + f"|{CAUDO}|" + "C" * 5_786
    shape = cf.split_row(row)
    assert shape.n_blocks == 2
    assert shape.distinct_tags == (CAUDO,)
    assert shape.sequence_chars == full + 5_786
    # The final block is partial, so the record ends inside this row: one row, one record.
    assert not shape.last_block_full
    assert shape.is_single_record


def test_a_row_whose_last_block_is_full_is_not_asserted_to_be_a_whole_record():
    full = cf.BLOCK_CHARS - len(CAUDO)
    shape = cf.split_row(f"|{CAUDO}|" + "A" * full)
    assert shape.last_block_full
    assert not shape.is_single_record


def test_two_distinct_tags_in_one_row_defeats_the_one_row_one_record_premise():
    shape = cf.split_row(f"|{CAUDO}|AAAA|{INOVIRIDAE}|CCCC")
    assert shape.distinct_tags == tuple(sorted({CAUDO, INOVIRIDAE}))
    assert not shape.is_single_record


def test_a_row_with_no_leading_delimiter_yields_no_tag_rather_than_a_wrong_one():
    shape = cf.split_row("ACGTACGT")
    assert shape.n_blocks == 0
    assert shape.distinct_tags == ()
    assert not shape.is_single_record


def test_record_from_row_carries_the_taxonomy_and_nothing_the_release_lacks():
    record, shape = cf.record_from_row(f"|{INOVIRIDAE}|ACGT", record_id="row-7", component="IMG/VR")
    assert record.taxonomy["family"] == "Inoviridae"
    assert record.attributes == {}
    assert record.host_occurrences == {}
    assert record.similarity_hits == {}
    assert shape.n_blocks == 1


# --------------------------------------------------------------------------------------
# The restriction — the part that decides which rules we hold the authors to
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evo_policies() -> dict[str, Policy]:
    return {k: v for k, v in load_policy_dir(SPECS).items() if k.startswith("evo1-")}


def test_stage2_can_re_execute_exactly_the_taxonomy_rules(evo_policies):
    r = cf.restrict(evo_policies["evo1-literal"], release="opengenome-stage2")
    assert [rule.id for rule in r.kept] == [
        "remove-denylisted-families",
        "remove-denylisted-orders",
        "remove-taxonomically-unspecific",
    ]
    assert {rule.id for rule, _ in r.dropped} == {
        "keep-high-confidence",
        "keep-one-per-votu",
        "keep-prokaryotic-host-twice",
    }
    assert r.rule_coverage == "3/6"


def test_the_restricted_policy_keeps_its_identity_so_a_result_traces_to_its_spec(evo_policies):
    published = evo_policies["evo1-strict"]
    r = cf.restrict(published, release="opengenome-stage2")
    assert r.policy.id == published.id
    assert r.policy.reading == published.reading
    assert r.policy.scope == published.scope
    assert len(r.policy.rules) < len(published.rules)


def test_every_dropped_rule_names_the_input_the_release_does_not_carry(evo_policies):
    r = cf.restrict(evo_policies["evo1-charitable"], release="opengenome-stage2")
    reasons = dict((rule.id, why) for rule, why in r.dropped)
    assert reasons["keep-high-confidence"] == "record_attributes"
    assert reasons["keep-one-per-votu"] == "record_attributes"
    assert reasons["keep-prokaryotic-host-twice"] == "host_occurrences"
    assert reasons["remove-eukaryotic-host-evidence"] == "host_occurrences"


def test_every_frozen_rule_kind_declares_an_input():
    from amazebio.policyspec import RULE_KINDS

    assert set(cf.RULE_INPUTS) == set(RULE_KINDS), (
        "a rule kind with no declared input would default to checkable, which is the one "
        "failure mode that silently inflates a conformance count"
    )


def test_a_rule_kind_with_no_declared_input_is_refused_rather_than_assumed_checkable(
    monkeypatch,
):
    policy = Policy(
        id="made-up",
        model="m",
        reading="literal",
        source="S-X",
        scope=Scope(components=["IMG/VR"]),
        rules=[
            Rule(
                id="r",
                kind="remove_if_taxon_in",
                params={"rank": "family", "names": ["Picornaviridae"]},
                source="S-X",
            )
        ],
    )
    without = {k: v for k, v in cf.RULE_INPUTS.items() if k != "remove_if_taxon_in"}
    monkeypatch.setattr(cf, "RULE_INPUTS", without)
    with pytest.raises(KeyError, match="declares no input"):
        cf.restrict(policy, release="opengenome-stage2")


def test_the_imgvr_fasta_release_can_re_execute_nothing_and_says_so(evo_policies):
    # Evo 2's FASTA carries accessions and no lineage, so it inverts the problem: traceable to
    # the filter's input, untestable against the filter's rules. That must raise rather than
    # return an empty pipeline a caller could run and report zero failures from.
    with pytest.raises(ValueError, match="re-execute none"):
        cf.restrict(evo_policies["evo1-literal"], release="opengenome2-imgvr")


def test_an_undeclared_release_is_refused(evo_policies):
    with pytest.raises(KeyError, match="no input inventory"):
        cf.restrict(evo_policies["evo1-literal"], release="some-other-corpus")


def test_the_three_readings_cannot_diverge_on_what_stage2_can_test(evo_policies):
    agree, kept = cf.readings_agree_by_construction(evo_policies, release="opengenome-stage2")
    assert agree, "if this ever fails, the reading spread became measurable and A7.1 must report it"
    assert set(kept) == {"literal", "charitable", "strict"}
    assert len(set(kept.values())) == 1


# --------------------------------------------------------------------------------------
# The diff and the causes
# --------------------------------------------------------------------------------------


def _rows(*tags: str, weight: int = 1):
    for i, raw in enumerate(tags):
        record, _ = cf.record_from_row(f"|{raw}|ACGT", record_id=f"row-{i}", component="IMG/VR")
        yield f"row-{i}", record, cf.parse_lineage_tag(raw), weight


def test_a_retained_phage_record_produces_no_failure(evo_policies):
    failures, coverage = cf.diff(
        evo_policies["evo1-literal"], _rows(CAUDO, INOVIRIDAE), release="opengenome-stage2"
    )
    assert failures == []
    assert coverage.rule_coverage == "3/6"


def test_an_rna_phage_record_is_retained_because_its_finest_rank_is_not_a_stop_taxon(
    evo_policies,
):
    # r__Riboviria is a published stop-taxon, but the rule removes a record whose *finest*
    # assignment is one — and this record resolves to class Leviviricetes. Retention is the
    # published rule working as written, and getting this wrong would manufacture a failure.
    failures, _ = cf.diff(evo_policies["evo1-literal"], _rows(LEVI), release="opengenome-stage2")
    assert failures == []


def test_a_record_with_no_assigned_realm_is_a_failure_caused_by_the_absent_annotation(
    evo_policies,
):
    failures, _ = cf.diff(
        evo_policies["evo1-literal"], _rows(NO_REALM), release="opengenome-stage2"
    )
    assert len(failures) == 1
    assert failures[0].rule_id == "remove-taxonomically-unspecific"
    assert failures[0].cause is cf.Cause.ANNOTATION_MISSING
    assert failures[0].taxonomy == {"family": "Fuselloviridae"}


def test_a_denylisted_family_in_the_release_is_the_unexplained_headline_failure(evo_policies):
    failures, _ = cf.diff(
        evo_policies["evo1-literal"],
        _rows(
            "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
            "o__Picornavirales;f__Picornaviridae;;"
        ),
        release="opengenome-stage2",
    )
    assert len(failures) == 1
    assert failures[0].cause is cf.Cause.UNEXPLAINED
    # The family rule runs before the order rule, so a record on both lists is attributed to
    # the first that fires — which is what the published pipeline order means.
    assert failures[0].rule_id == "remove-denylisted-families"


def test_a_record_whose_finest_assignment_is_a_published_stop_taxon_is_unexplained(
    evo_policies,
):
    failures, _ = cf.diff(
        evo_policies["evo1-literal"], _rows("r__Riboviria;;;;;;;"), release="opengenome-stage2"
    )
    assert len(failures) == 1
    assert failures[0].cause is cf.Cause.UNEXPLAINED
    assert failures[0].rule_id == "remove-taxonomically-unspecific"


def test_a_malformed_tag_is_neither_a_clean_record_nor_a_conformance_failure(evo_policies):
    failures, _ = cf.diff(
        evo_policies["evo1-literal"], _rows("Picornaviridae;;;;;;;"), release="opengenome-stage2"
    )
    assert len(failures) == 1
    assert failures[0].cause is cf.Cause.ANNOTATION_MALFORMED


def test_weights_from_the_aggregated_scan_carry_into_the_failure_count(evo_policies):
    failures, _ = cf.diff(
        evo_policies["evo1-literal"],
        _rows(NO_REALM, weight=2_317),
        release="opengenome-stage2",
    )
    assert sum(f.n_records for f in failures) == 2_317


def test_every_cause_is_documented(evo_policies):
    assert set(cf.CAUSES) == set(cf.Cause), (
        "§A7 requires the causes defined before the count; an undocumented cause is one "
        "defined after it"
    )


def test_an_order_dependent_rule_is_refused_rather_than_reported_as_zero_removals(
    evo_policies, monkeypatch
):
    # If a release ever carried vOTU identifiers, `keep_one_per` would become "checkable" and
    # this diff would retain every record as its own representative — zero removals, reading as
    # conformance. D-017 records that the rule is not reproducible for want of a published input
    # order; the guard is what stops that becoming a number.
    monkeypatch.setitem(
        cf.RELEASE_INPUTS, "opengenome-stage2", frozenset({"taxonomy", "record_attributes"})
    )
    with pytest.raises(ValueError, match="order-dependent"):
        cf.diff(evo_policies["evo1-literal"], _rows(CAUDO), release="opengenome-stage2")


# --------------------------------------------------------------------------------------
# The published-figure checks
# --------------------------------------------------------------------------------------


def test_the_published_figure_panels_sum_to_the_published_record_count():
    # The only thing standing in for a machine-extractable source on Figure S1: its values were
    # read off a raster, and a misread digit would almost certainly break these sums. The
    # production code asserts this on import; this is the same check, where a reader looks.
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "conformance_diff",
        pathlib.Path(__file__).resolve().parent.parent / "tools" / "conformance_diff.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    total = mod.PUBLISHED_IMGVR["records"]
    assert sum(mod.PUBLISHED_REALMS["counts"].values()) == total
    assert sum(mod.PUBLISHED_HOST_KINGDOMS["counts"].values()) == total


def test_the_malformed_archaea_label_is_recorded_as_printed():
    # The source prints "N = 17,44", which is not a number. The recovered value is only
    # defensible because the panel has to sum; keeping the printed form is what lets a reviewer
    # check that reasoning rather than take 1,744 on trust.
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "conformance_diff",
        pathlib.Path(__file__).resolve().parent.parent / "tools" / "conformance_diff.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.PUBLISHED_HOST_KINGDOMS["archaea_label_as_printed"] == "17,44"
    assert mod.PUBLISHED_HOST_KINGDOMS["counts"]["Archaea"] == 1_744

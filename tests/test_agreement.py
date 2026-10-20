"""A8.1's cross-tab, on synthetic taxa so the logic is pinned without a taxdump."""

from __future__ import annotations

import pytest

from amazebio import agreement
from amazebio.seeds import VIRAL_ROOT, Taxonomy

# A small viral tree that carries every case the predicate distinguishes.
#
#   10239 Viruses
#     +-- 100 Riboviria (realm)                  <- a stop taxon
#     |     +-- 110 Pisuviricota (phylum)        <- a stop taxon
#     |     |     +-- 120 Picornavirales (order) <- denylisted by order
#     |     |     |     +-- 130 Picornaviridae (family)  <- denylisted by family too
#     |     |     |     +-- 140 Dicistroviridae (family) <- order-only removal
#     |     |     +-- 150 Caudovirales (order)   <- not denylisted
#     |     |           +-- 160 Siphoviridae (family)
#     +-- 200 Unclassified viruses               <- no realm at all
#   1 root
#     +-- 2 Bacteria
#           +-- 300 Escherichia coli
NODES = {
    1: (1, "no rank"),
    2: (1, "superkingdom"),
    300: (2, "species"),
    VIRAL_ROOT: (1, "superkingdom"),
    100: (VIRAL_ROOT, "realm"),
    110: (100, "phylum"),
    120: (110, "order"),
    130: (120, "family"),
    140: (120, "family"),
    150: (110, "order"),
    160: (150, "family"),
    200: (VIRAL_ROOT, "no rank"),
}
NAMES = {
    VIRAL_ROOT: "Viruses",
    100: "Riboviria",
    110: "Pisuviricota",
    120: "Picornavirales",
    130: "Picornaviridae",
    140: "Dicistroviridae",
    150: "Caudovirales",
    160: "Siphoviridae",
    200: "unclassified viruses",
    2: "Bacteria",
    300: "Escherichia coli",
}
RANKS = ["realm", "kingdom", "phylum", "class", "order", "family", "genus", "species"]


@pytest.fixture
def predicate() -> agreement.LabelPredicate:
    taxonomy = Taxonomy(
        {t: p for t, (p, _) in NODES.items()}, {t: r for t, (_, r) in NODES.items()}
    )
    return agreement.build_predicate(
        taxonomy=taxonomy,
        names=NAMES,
        family_names=["Picornaviridae"],
        order_names=["Picornavirales"],
        stop_taxa=["Riboviria", "Pisuviricota"],
        require_rank="realm",
        ranks=RANKS,
        rules_not_runnable=(("keep-high-confidence", "no confidence label on a protein"),),
    )


def cluster(*taxids: int | None) -> bytes:
    body = b'<entry id="UniRef90_X">'
    for taxid in taxids:
        body += b'<dbReference type="UniProtKB ID" id="M">'
        if taxid is not None:
            body += b'<property type="NCBI taxonomy" value="%d"/>' % taxid
        body += b"</dbReference>"
    return body + b"</entry>"


def tally(predicate: agreement.LabelPredicate, *blocks: bytes) -> agreement.AgreementCounts:
    return agreement.AgreementConfig(predicate=predicate).scan(blocks)


def test_family_rule_beats_the_order_it_sits_in(predicate):
    assert predicate.rank_of(130) == "family"
    assert predicate.rank_of(140) == "order"


def test_a_stop_taxon_is_an_assignment_not_a_clade(predicate):
    # Riboviria is a stop taxon, so a record assigned only to it is unspecific...
    assert predicate.kind_of(100) == agreement.KIND_VIRAL_UNSPECIFIC
    # ...but a record in a family beneath it is placed as finely as the taxonomy allows and
    # is not. Closing the stop taxa over their descendants would remove almost every virus.
    assert predicate.kind_of(160) == agreement.KIND_VIRAL_OTHER


def test_a_virus_with_no_realm_is_unspecific(predicate):
    assert predicate.kind_of(200) == agreement.KIND_VIRAL_UNSPECIFIC


def test_a_cellular_record_is_out_of_scope_not_retained(predicate):
    # Evo's filter runs over a virus database and never sees this record, so scoring it as
    # "neither filter removed it" would manufacture agreement.
    counts = tally(predicate, cluster(300))
    assert counts.cells[agreement.CELL_OUT_OF_SCOPE] == 1
    assert counts.cells[agreement.CELL_NEITHER] == 0


def test_an_unplaced_member_is_out_of_scope(predicate):
    counts = tally(predicate, cluster(None))
    assert counts.cells[agreement.CELL_OUT_OF_SCOPE] == 1
    assert counts.kind_by_cell[agreement.CELL_OUT_OF_SCOPE][agreement.KIND_UNPLACED] == 1


def test_a_cellular_member_sharing_a_cluster_with_a_virus_is_collateral(predicate):
    # It is still out of Evo's scope, but the similarity filter removes it. The two
    # out-of-scope cells are kept apart because this one is the collateral and the other is
    # the corpus left alone.
    counts = tally(predicate, cluster(130, 300))
    assert counts.cells[agreement.CELL_BOTH] == 1
    assert counts.cells[agreement.CELL_OUT_OF_SCOPE_REMOVED] == 1
    assert counts.cells[agreement.CELL_OUT_OF_SCOPE] == 0
    assert counts.covering_clusters == 1


def test_a_viral_record_outside_the_denylist_is_similarity_only(predicate):
    # Siphoviridae is viral, so the seed set holds it and its own cluster covers a seed —
    # but no taxon rule names it. This is the whole of the disagreement.
    counts = tally(predicate, cluster(160))
    assert counts.cells[agreement.CELL_SIMILARITY_ONLY] == 1
    assert counts.kind_by_cell[agreement.CELL_SIMILARITY_ONLY][agreement.KIND_VIRAL_OTHER] == 1


def test_the_rank_breakdown_separates_family_from_order_removals(predicate):
    counts = tally(predicate, cluster(130, 140, 100))
    assert counts.rank_by_cell[agreement.CELL_BOTH] == {
        "family": 1,
        "order": 1,
        "unspecific": 1,
    }


def test_agreement_is_over_judged_records_only(predicate):
    counts = tally(predicate, cluster(130), cluster(160), cluster(300), cluster(300))
    # Two cellular records are out of scope; of the two judged, one agrees and one does not.
    assert counts.to_dict()["judged_members"] == 2
    assert counts.to_dict()["agreement"] == pytest.approx(0.5)


def test_merge_adds_every_axis(predicate):
    left = tally(predicate, cluster(130, 300))
    right = tally(predicate, cluster(160))
    left.merge(right)
    assert left.members == 3
    assert left.cells[agreement.CELL_BOTH] == 1
    assert left.cells[agreement.CELL_SIMILARITY_ONLY] == 1
    assert left.cells[agreement.CELL_OUT_OF_SCOPE_REMOVED] == 1
    assert left.clusters == 2


def test_dominance_holds_on_a_real_reduction(predicate):
    counts = tally(predicate, cluster(130), cluster(140), cluster(160), cluster(300))
    agreement.check_dominance(counts)
    assert counts.cells[agreement.CELL_LABEL_ONLY] == 0


def test_dominance_refuses_a_label_only_record(predicate):
    counts = agreement.AgreementCounts()
    counts.cells[agreement.CELL_LABEL_ONLY] = 7
    with pytest.raises(ValueError, match="removed by the taxon rules"):
        agreement.check_dominance(counts)


def test_a_renamed_taxon_is_an_error_not_a_silent_zero():
    taxonomy = Taxonomy(
        {t: p for t, (p, _) in NODES.items()}, {t: r for t, (_, r) in NODES.items()}
    )
    with pytest.raises(ValueError, match="Deltavirus"):
        agreement.build_predicate(
            taxonomy=taxonomy,
            names=NAMES,
            family_names=["Deltavirus"],
            order_names=[],
            stop_taxa=["Riboviria"],
            require_rank="realm",
            ranks=RANKS,
        )


def test_a_non_entry_block_is_not_a_cluster(predicate):
    assert agreement.reduce_cluster(b"<copyright>...</copyright>", predicate.viral) is None


def test_the_entry_level_taxid_is_not_counted_as_a_member(predicate):
    # The text before the first <dbReference carries a `common taxon ID`, which is a summary
    # of the members rather than a member of its own.
    block = (
        b'<entry id="UniRef90_X">'
        b'<property type="common taxon ID" value="10239"/>'
        b'<dbReference type="UniProtKB ID" id="M">'
        b'<property type="NCBI taxonomy" value="160"/>'
        b"</dbReference></entry>"
    )
    counts = tally(predicate, block)
    assert counts.members == 1

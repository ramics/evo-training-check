"""The viral assay register — task B2.2.

The register exists to answer one question: can §B5's regression identify its own interaction
term on the assays that already exist? So what these tests hold in place is the arithmetic of
*identifiability*, not of counting.

- A covariate level present in only one arm is reported as such, because within it the arm is
  determined and the covariate cannot be separated from the effect being measured.
- An assay with no pinned organism raises rather than defaulting into the retained arm, which
  is the direction an unplaced assay would silently fall.
- A lineage with no family node keeps its own value and is never read as "some other family".
- A policy that decides by sequence similarity gets no taxonomic verdict at all, and the
  register says so instead of reporting it as retained.
"""

from __future__ import annotations

import dataclasses

import pytest

from amazebio.assays import (
    NO_RANK,
    AssayPlacement,
    AssayRegisterError,
    Organism,
    cross_tab,
    place,
    usable_n,
)
from amazebio.misassignment import Denylist

DENY = {
    "evo1-literal": Denylist(frozenset({"Orthomyxoviridae"}), frozenset({"Picornavirales"}), "x")
}
SIMILARITY = {"esm3-open-literal": "decides by sequence similarity"}


@dataclasses.dataclass(frozen=True)
class FakeAssay:
    dms_id: str
    uniprot_id: str
    selection_type: str = "Growth"
    msa_depth_category: str = "Medium"
    n_variants: int = 100
    seq_len: int = 500
    doi: str = "10.0/x"


def placement(
    family: str, *, arm_id: str = "a", readout: str = "Growth", order: str = ""
) -> AssayPlacement:
    return place(
        FakeAssay(dms_id=arm_id, uniprot_id="NRAM_I33A0", selection_type=readout),
        lineage={k: v for k, v in (("family", family), ("order", order)) if v},
        denylists=DENY,
        similarity_policies=SIMILARITY,
    )


def test_an_assay_with_no_pinned_organism_is_refused() -> None:
    with pytest.raises(AssayRegisterError, match="no pinned organism"):
        place(
            FakeAssay(dms_id="x", uniprot_id="NOT_A_REAL_ENTRY"),
            lineage={"family": "Orthomyxoviridae"},
            denylists=DENY,
            similarity_policies=SIMILARITY,
        )


def test_a_similarity_policy_gets_a_reason_and_no_verdict() -> None:
    p = placement("Orthomyxoviridae")
    assert p.excluded_by == {"evo1-literal": True}
    assert "esm3-open-literal" not in p.excluded_by
    assert p.undecidable_by["esm3-open-literal"] == "decides by sequence similarity"


def test_a_policy_cannot_be_both_decidable_and_not() -> None:
    with pytest.raises(AssayRegisterError, match="both taxon-decidable and not"):
        place(
            FakeAssay(dms_id="x", uniprot_id="NRAM_I33A0"),
            lineage={"family": "Orthomyxoviridae"},
            denylists=DENY,
            similarity_policies={"evo1-literal": "also similarity, somehow"},
        )


def test_a_missing_family_node_is_its_own_value_and_never_matches_a_denylist() -> None:
    p = placement("")
    assert p.family == NO_RANK and p.order == NO_RANK
    assert p.excluded_by == {"evo1-literal": False}

    # And a denylist that somehow named the sentinel still would not match on it.
    deny = {"evo1-literal": Denylist(frozenset({NO_RANK}), frozenset(), "x")}
    q = place(
        FakeAssay(dms_id="y", uniprot_id="NRAM_I33A0"),
        lineage={},
        denylists=deny,
        similarity_policies=SIMILARITY,
    )
    assert q.excluded_by == {"evo1-literal": False}


def test_an_order_level_denylist_hit_counts() -> None:
    assert placement("Caliciviridae", order="Picornavirales").excluded_by["evo1-literal"]


def test_cross_tab_splits_by_arm() -> None:
    rows = [
        placement("Orthomyxoviridae", readout="Growth"),
        placement("Orthomyxoviridae", readout="Growth"),
        placement("Siphoviridae", readout="FACS"),
    ]
    assert cross_tab(rows, "evo1-literal", "selection_type") == {
        "excluded": {"Growth": 2},
        "retained": {"FACS": 1},
    }


def test_a_covariate_level_in_one_arm_only_is_named_as_such() -> None:
    rows = [
        placement("Orthomyxoviridae", readout="Growth"),
        placement("Siphoviridae", readout="FACS"),
        placement("Siphoviridae", readout="Growth"),
    ]
    n = usable_n(rows, "evo1-literal")
    assert (n["excluded_arm"], n["retained_arm"]) == (1, 2)
    readout = n["covariate_overlap"]["selection_type"]
    assert readout["in_both_arms"] == ["Growth"]
    assert readout["only_in_retained_arm"] == ["FACS"]
    assert readout["only_in_excluded_arm"] == []


def test_family_is_confounded_with_arm_by_construction() -> None:
    """The exclusion rule *is* a family rule, so no family can appear in both arms.

    Pinned because §B5 pre-registers a random effect for protein family alongside a fixed
    exclusion term. If family determines arm, those two cannot both be estimated, and that is
    a fact about the design rather than about how many assays were curated.
    """
    rows = [placement("Orthomyxoviridae"), placement("Siphoviridae"), placement("Myoviridae")]
    overlap = usable_n(rows, "evo1-literal")["covariate_overlap"]["family"]
    assert overlap["in_both_arms"] == []


def test_the_pinned_organism_table_records_where_each_came_from() -> None:
    from amazebio.assays import VIRAL_ASSAY_ORGANISMS

    assert VIRAL_ASSAY_ORGANISMS
    for name, organism in VIRAL_ASSAY_ORGANISMS.items():
        assert isinstance(organism, Organism), name
        assert organism.taxid > 0, name
        assert organism.source in {"uniprot", "proteingym-name"}, name
        # A fallback placement must say why it is one; a UniProt one must carry its accession.
        if organism.source == "proteingym-name":
            assert organism.note, name
        else:
            assert organism.accession, name

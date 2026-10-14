"""Tests for the Phase B model inventory — task B1.1.

The inventory is a set of claims about other people's models, every one of which has to stay
traceable to a stored source. So the assertions that carry weight here are not about the data
structure: they are that every cited source exists and is quotable, that the design's own
role/exclusion logic holds, and that the two places where no first-party source states a
field stay marked as unstated rather than quietly acquiring a plausible value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amazebio.models import (
    TIER_1,
    TIER_2,
    Checkpoint,
    Exclusion,
    GpuNeed,
    InventoryError,
    Modality,
    Role,
    checkpoint,
    feasibility,
    inventory,
    validate,
)

REPO = Path(__file__).resolve().parents[1]
SOURCES = REPO / "policies" / "sources.json"
EVIDENCE = REPO / "policies" / "models.md"


@pytest.fixture(scope="module")
def sources() -> dict[str, dict]:
    return {s["id"]: s for s in json.loads(SOURCES.read_text())["sources"]}


def test_inventory_validates_against_the_real_source_inventory(sources):
    validate(inventory(), sources=sources)


def test_every_cited_source_is_retrieved_and_stored(sources):
    """An unretrieved source is not quotable, so a claim resting on one is not verified."""
    for c in inventory():
        for sid in c.sources:
            assert sid in sources, f"{c.id} cites unknown source {sid}"
            assert sources[sid]["status"] == "retrieved", f"{c.id} cites unquotable {sid}"
            capture = REPO / sources[sid]["capture"]
            assert capture.exists(), f"{sid} capture missing: {capture}"


def test_tiers_are_disjoint_and_complete():
    ids = [c.id for c in inventory()]
    assert len(ids) == len(set(ids))
    assert {c.id for c in inventory(tiers=(1,))} == {c.id for c in TIER_1}
    assert {c.id for c in inventory(tiers=(2,))} == {c.id for c in TIER_2}


def test_both_mechanisms_and_both_modalities_are_represented():
    """The design needs a label-based and a similarity-based filter, and both modalities.

    Losing either contrast would not break anything mechanically — it would just quietly
    turn the audit into a single-filter case study, which §A8 exists to avoid.
    """
    tier1 = inventory(tiers=(1,))
    mechanisms = {c.exclusion for c in tier1 if c.role is Role.TEST_CONDITION}
    assert mechanisms == {Exclusion.LABEL_BASED, Exclusion.SIMILARITY_BASED}
    assert {c.modality for c in tier1} == {Modality.PROTEIN, Modality.NUCLEOTIDE}
    assert any(c.role is Role.POSITIVE_CONTROL for c in tier1)


def test_esm3_open_parameter_count_stays_unstated():
    """No retrieved first-party source states it; see policies/models.md §2.

    "1.4B" comes from the ESM-C preprint — a second lab describing someone else's model, which
    §B1 step 0 rules out. If someone fills this in, they need a primary source, and this test
    is where they are told so.
    """
    c = checkpoint("esm3-sm-open-v1")
    assert c.params is None
    assert any("params" in u for u in c.unverified)


def test_esm3_open_has_no_corpus_pin():
    """A1.1 settled that no corpus was released, so Phase A audits a proxy (D-017)."""
    assert checkpoint("esm3-sm-open-v1").corpus_pin is None


def test_esm2_is_not_described_as_unfiltered():
    """It carries no biosecurity exclusion but it is not unfiltered (policies/esm2.md §6)."""
    for cid in ("esm2_t33_650M_UR50D", "esm2_t36_3B_UR50D"):
        c = checkpoint(cid)
        assert c.exclusion is Exclusion.NONE
        assert c.exclusion_note and "de-novo" in c.exclusion_note


def test_evidence_file_covers_every_checkpoint():
    """Each row has to be arguable from quotations, not just present in the dataclass."""
    text = EVIDENCE.read_text()
    for c in inventory():
        assert c.id in text, f"{c.id} is in the inventory but not in policies/models.md"


def test_validate_rejects_a_test_condition_with_no_exclusion():
    bad = Checkpoint(
        id="x",
        model="X",
        params=None,
        modality=Modality.PROTEIN,
        role=Role.TEST_CONDITION,
        exclusion=Exclusion.NONE,
        corpus_pin=None,
        licence="MIT",
        access="somewhere",
        sources=("S-ESM2-REPO",),
    )
    with pytest.raises(InventoryError, match="no stated exclusion"):
        validate([bad])


def test_validate_rejects_a_positive_control_with_an_exclusion():
    bad = Checkpoint(
        id="x",
        model="X",
        params=None,
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.LABEL_BASED,
        corpus_pin=None,
        licence="MIT",
        access="somewhere",
        sources=("S-ESM2-REPO",),
    )
    with pytest.raises(InventoryError, match="positive control with a stated exclusion"):
        validate([bad])


def test_validate_rejects_an_unretrieved_source():
    c = Checkpoint(
        id="x",
        model="X",
        params=None,
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.NONE,
        corpus_pin=None,
        licence="MIT",
        access="somewhere",
        sources=("S-MADE-UP",),
    )
    with pytest.raises(InventoryError, match="unknown source"):
        validate([c], sources={})
    with pytest.raises(InventoryError, match="not quotable"):
        validate([c], sources={"S-MADE-UP": {"status": "unretrieved"}})


def test_validate_rejects_duplicate_ids():
    c = checkpoint("evo2_7b")
    with pytest.raises(InventoryError, match="duplicate"):
        validate([c, c])


def test_feasibility_separates_the_requirement_from_what_is_allowed():
    """Model requirements are published; what this account can launch is measured."""
    cpu_only = feasibility(inventory(), gpu_types=())
    assert cpu_only["evo2_7b"].startswith("blocked")
    assert cpu_only["esm2_t33_650M_UR50D"] == "runnable"

    measured = feasibility(inventory(tiers=(1,)), gpu_types=("g5.xlarge", "g6.xlarge"))
    assert set(measured.values()) == {"runnable"}


def test_a_single_card_does_not_make_evo2_40b_runnable():
    """The regression this file exists for.

    `needs_gpu` was a boolean, so the measured allowlist — one 24 GB card, no Hopper — made
    the inventory report evo2_40b as runnable, contradicting policies/models.md §4 and
    DECISIONS.md D-034. The requirement is not "a GPU": it is FP8 on Hopper across several of
    them.
    """
    verdicts = feasibility(inventory(), gpu_types=("g5.xlarge", "g6.xlarge"))
    assert verdicts["evo2_40b"].startswith("blocked")
    assert "Hopper" in verdicts["evo2_40b"]

    with_hopper = feasibility(inventory(), gpu_types=("p5.48xlarge",))
    assert with_hopper["evo2_40b"] == "runnable"


def test_p4d_is_not_hopper():
    """Eight A100s are eight GPUs and no FP8, so they do not satisfy the 40B requirement."""
    assert feasibility([checkpoint("evo2_40b")], gpu_types=("p4d.24xlarge",))[
        "evo2_40b"
    ].startswith("blocked")


def test_evo2_sizes_have_different_requirements():
    """One lineage, two requirements. Collapsing them is what caused the regression above."""
    assert checkpoint("evo2_7b").gpu_need is GpuNeed.SINGLE_ANY
    assert checkpoint("evo2_40b").gpu_need is GpuNeed.MULTI_HOPPER
    assert checkpoint("esm2_t33_650M_UR50D").gpu_need is GpuNeed.NONE
    assert "H100" in checkpoint("evo2_40b").access


def test_tuple_fields_are_tuples_not_strings():
    """A missing trailing comma makes a 1-tuple a string that iterates as characters.

    It happened: ESMC-600M's single finding was written into an artefact as 255 separate
    one-character entries. The fields are checked here and rejected in validate().
    """
    for c in inventory():
        assert isinstance(c.sources, tuple), f"{c.id}: sources is {type(c.sources).__name__}"
        assert isinstance(c.unverified, tuple), f"{c.id}: unverified is a string"
        for entry in c.unverified:
            assert len(entry) > 1, f"{c.id}: a one-character finding means a string slipped in"


def test_validate_rejects_a_string_where_a_tuple_belongs():
    bad = Checkpoint(
        id="x",
        model="X",
        params=None,
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.NONE,
        corpus_pin=None,
        licence="MIT",
        access="somewhere",
        sources=("S-ESM2-REPO",),
        unverified="one finding, no comma",
    )
    with pytest.raises(InventoryError, match="not a tuple"):
        validate([bad])


def test_licence_claims_cite_a_licence_source(sources):
    """A licence is quoted from a licence file, so that file has to be cited.

    Without this the CI check validated every source a checkpoint listed while the licence
    evidence sat outside the list, unverifiable.
    """
    licence_ids = {sid for sid, s in sources.items() if s["kind"] == "license"}
    for c in inventory():
        assert licence_ids & set(c.sources), f"{c.id}: licence {c.licence!r} cites no licence file"

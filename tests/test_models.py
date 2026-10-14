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


def test_feasibility_separates_the_gpu_requirement_from_availability():
    """Model requirements are published; what this account can launch is measured."""
    without = feasibility(inventory(), gpu_available=False)
    assert without["evo2_7b"].startswith("blocked")
    assert without["esm2_t33_650M_UR50D"] == "runnable"

    with_gpu = feasibility(inventory(tiers=(1,)), gpu_available=True)
    assert set(with_gpu.values()) == {"runnable"}


def test_evo2_40b_needs_a_gpu_this_account_does_not_have():
    """Tier 2's exclusion is a measurement, so it must not be hard-coded as a verdict.

    `needs_gpu` records the developers' stated requirement. That a 24 GB card is not enough
    for 40B is argued in policies/models.md §4 from their own text, and the allowlist that
    decides it lives in the artefact, not here.
    """
    c = checkpoint("evo2_40b")
    assert c.tier == 2
    assert c.needs_gpu
    assert "H100" in c.access

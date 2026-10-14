"""The Phase B model inventory — task B1.1.

`DESIGN.md` §B1 opens with "verify every exclusion policy from primary sources ... Do not
trust secondary sources, including this document", and `AGENTS.md` repeats it as a
non-negotiable. So this module does not import §B1's model table. It records, per checkpoint,
what the retrieved first-party sources in `policies/sources.json` actually establish, and
marks everything they do not.

The prose half is `policies/models.md`, where every claim here carries a quotation that
`tools/policies.py` checks against the stored source. Read that file alongside this one: a
field here is a summary of a quotation there, and the quotation is the evidence.

Three distinctions this module keeps apart, because collapsing any of them would weaken a
Phase B claim:

**Exclusion** (:class:`Exclusion`) is what the developers' own sources say was removed from
the training data, by what mechanism. :attr:`Exclusion.NONE` means no retrieved source states
a hazard-driven exclusion — it does not mean the corpus was unfiltered, and
:attr:`Checkpoint.exclusion_note` carries the difference where there is one. ESM-2 is the case
that matters: it carries no biosecurity exclusion and is this audit's positive control, but it
does carry a de-novo-protein filter with published parameters (`policies/esm2.md` §6).

**Role** (:class:`Role`) is what the checkpoint does in the design. A test condition carries a
stated exclusion whose consequences Phase B measures; a positive control carries none and
establishes what unfiltered capability looks like.

**Verification** (:class:`Checkpoint.unverified`) is whether a first-party source states the
field at all. §A0 and §7 make under-specification a finding in its own right, so an unstated
parameter count is recorded as unstated rather than filled in from a second lab's description
of the model — which is what `esm3-sm-open-v1` would otherwise invite.

Compute feasibility is deliberately not a field here. What this account can launch is a
measurement, not a property of a model: `tools/ec2_capability.py` measures it and
:func:`feasibility` combines the two.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from enum import Enum

__all__ = [
    "TIER_1",
    "TIER_2",
    "Checkpoint",
    "Exclusion",
    "InventoryError",
    "Modality",
    "Role",
    "checkpoint",
    "feasibility",
    "inventory",
    "validate",
]


class InventoryError(ValueError):
    """Raised when the inventory is internally inconsistent."""


class Modality(Enum):
    """What the model reads. Phase B scores protein models; Evo 2 is the nucleotide arm."""

    PROTEIN = "protein"
    NUCLEOTIDE = "nucleotide"


class Role(Enum):
    """What the checkpoint is for in the Phase B design (`DESIGN.md` §B1)."""

    TEST_CONDITION = "test_condition"
    POSITIVE_CONTROL = "positive_control"


class Exclusion(Enum):
    """The mechanism a first-party source states, not the one a reader would assume.

    The two mechanisms are the two filters this audit compares (`DESIGN.md` §A8): a denylist
    over taxonomy labels, versus alignment against a denylist of sequences. `NONE` is the
    absence of a *stated hazard-driven* exclusion and is evidenced by recorded searches —
    `policies/esm-c.md` §3 is the pattern — never by silence alone.
    """

    NONE = "none"
    LABEL_BASED = "label_based"
    SIMILARITY_BASED = "similarity_based"


@dataclasses.dataclass(frozen=True)
class Checkpoint:
    """One checkpoint, as its own developers' retrieved sources describe it.

    Attributes:
        id: the identifier the developers publish. Not a nickname: `esm3-sm-open-v1` is the
            open ESM3 checkpoint's published id, and it is absent from the ESM3 family table
            that would give its size (see `unverified`).
        model: the family name as used in write-ups.
        params: parameter count as a first-party source states it, or None if none does.
        modality: protein or nucleotide.
        role: test condition or positive control.
        exclusion: the stated mechanism.
        exclusion_note: what the mechanism does not cover, where that is load-bearing.
        corpus_pin: the training corpus as pinned by a first-party source, or None where no
            corpus was released (ESM3-open; A1.1 and DECISIONS.md D-017).
        licence: the licence the weights are released under, as stated.
        access: how the weights are obtained. B1.2 builds on this.
        sources: source ids in `policies/sources.json`. Every one must be `retrieved`.
        tier: 1 for the core list, 2 for `DESIGN.md` §B1's "if compute allows" set.
        unverified: fields no retrieved first-party source states, named. Non-empty means the
            checkpoint carries a §A0 finding, and `tools/model_inventory.py` reports it.
        needs_gpu: whether the published run instructions require an accelerator. Stated by
            the developers, so it belongs here; whether one is available does not.
    """

    id: str
    model: str
    params: str | None
    modality: Modality
    role: Role
    exclusion: Exclusion
    corpus_pin: str | None
    licence: str
    access: str
    sources: tuple[str, ...]
    tier: int = 1
    exclusion_note: str | None = None
    unverified: tuple[str, ...] = ()
    needs_gpu: bool = False

    def to_dict(self) -> dict[str, object]:
        d = dataclasses.asdict(self)
        for key in ("modality", "role", "exclusion"):
            d[key] = getattr(self, key).value
        d["sources"] = list(self.sources)
        d["unverified"] = list(self.unverified)
        return d


# ---------------------------------------------------------------------------
# Tier 1 — the core list. Every field traces to a quotation in policies/models.md.
# ---------------------------------------------------------------------------

TIER_1: tuple[Checkpoint, ...] = (
    Checkpoint(
        id="esm2_t33_650M_UR50D",
        model="ESM-2 650M",
        params="650M",
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.NONE,
        exclusion_note=(
            "No hazard-driven exclusion is stated. Not unfiltered, though: a de-novo-protein "
            "filter with published parameters removed an unquantified share of the release "
            "(policies/esm2.md §6). Stated purpose is generalisation work, not biosecurity."
        ),
        corpus_pin="UniRef50 2021_04, UR50/D (UniRef90 members, resampled per update)",
        licence="MIT",
        access=(
            "direct download from dl.fbaipublicfiles.com, or torch.hub / the fair-esm package; "
            "mirrored on HuggingFace at facebook/esm2_t33_650M_UR50D"
        ),
        sources=("S-ESM2-REPO", "S-ESM2-PREPRINT", "S-ESM2-HF-650M"),
    ),
    Checkpoint(
        id="esm2_t36_3B_UR50D",
        model="ESM-2 3B",
        params="3B",
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.NONE,
        exclusion_note=(
            "As for 650M: the corpus pin and the de-novo filter are properties of the ESM-2 "
            "training run, which every ESM-2 checkpoint shares."
        ),
        corpus_pin="UniRef50 2021_04, UR50/D (UniRef90 members, resampled per update)",
        licence="MIT",
        access=(
            "direct download from dl.fbaipublicfiles.com, or torch.hub / the fair-esm package; "
            "mirrored on HuggingFace at facebook/esm2_t36_3B_UR50D"
        ),
        sources=("S-ESM2-REPO", "S-ESM2-PREPRINT", "S-ESM2-HF-3B"),
    ),
    Checkpoint(
        id="esm3-sm-open-v1",
        model="ESM3-open",
        params=None,
        modality=Modality.PROTEIN,
        role=Role.TEST_CONDITION,
        exclusion=Exclusion.SIMILARITY_BASED,
        exclusion_note=(
            "Two denylists — viral and Select Agent — expanded by MMseqs2 alignment above an "
            "unpublished identity threshold, applied across every training database. The "
            "model card says 'related to viruses'; the paper says 'unique to viruses'. The "
            "second is the narrower set and the one actually operationalised "
            "(policies/esm3-open.md §1)."
        ),
        corpus_pin=None,
        licence="MIT",
        access="HuggingFace biohub/esm3-sm-open-v1, loaded via the esm package",
        sources=("S-ESM3-HF-OPEN", "S-ESM3-PREPRINT", "S-ESM3-REPO", "S-ESM-LICENSE"),
        unverified=(
            "params: the ESM3 family table lists esm3-small/medium/large at 1.4B/7B/98B and "
            "does not list esm3-sm-open-v1, so no first-party source retrieved here states "
            "the open checkpoint's size or which flagship checkpoint it corresponds to",
            "corpus_pin: no training corpus was released, so Phase A audits a proxy (A1.1, "
            "DECISIONS.md D-017)",
            "the MMseqs2 identity threshold, which is the filter's one free parameter",
        ),
    ),
    Checkpoint(
        id="ESMC-600M",
        model="ESM-C 600M",
        params="600M",
        modality=Modality.PROTEIN,
        role=Role.POSITIVE_CONTROL,
        exclusion=Exclusion.NONE,
        exclusion_note=(
            "Viral sequence is present and version-pinned — IMG/VR release 7, almost all "
            "metagenomic and largely bacteriophage. The published safeguards are release-time "
            "evaluation and a platform-side keyword guardrail, neither of which is training-"
            "data filtering (policies/esm-c.md §2)."
        ),
        corpus_pin="UniRef, MGnify and JGI; viral content from IMG/VR release 7 (Dec 19, 2022)",
        licence="MIT, with a third-party notice",
        access="HuggingFace biohub/ESMC-600M; also in transformers from v5.16.0",
        sources=("S-ESMC-HF-600M", "S-ESMC-PREPRINT", "S-ESM-REPO"),
        unverified=(
            "exclusion status at variant level: the ESMC-600M and ESMC-6B cards are "
            "byte-identical, so neither evidences anything about a specific variant. The "
            "corpus claim rests on the preprint, which describes the training data for the "
            "family (policies/esm-c.md §5)."
        ),
    ),
    Checkpoint(
        id="evo2_7b",
        model="Evo 2 7B",
        params="7B",
        modality=Modality.NUCLEOTIDE,
        role=Role.TEST_CONDITION,
        exclusion=Exclusion.LABEL_BASED,
        exclusion_note=(
            "Eukaryote-infecting viruses excluded; phage retained. The procedure is published "
            "only for Evo 1, which Evo 2 inherits by reference, and it is a host-occurrence "
            "rule over IMG/VR metadata applied to the viral component alone. Nothing states "
            "what becomes of viral-derived sequence inside retained eukaryotic genomes "
            "(policies/evo.md §1, §2)."
        ),
        corpus_pin="OpenGenome2",
        licence="Apache-2.0",
        access=(
            "HuggingFace arcinstitute/evo2_7b via the evo2 package; runs in bfloat16 without "
            "Transformer Engine on any supported GPU"
        ),
        sources=("S-EVO2-HF-7B", "S-EVO2-PREPRINT", "S-EVO2-REPO", "S-EVO1-PREPRINT"),
        needs_gpu=True,
    ),
)


# ---------------------------------------------------------------------------
# Tier 2 — `DESIGN.md` §B1's "if compute allows". The scope call is B1.1's to record.
# ---------------------------------------------------------------------------

TIER_2: tuple[Checkpoint, ...] = (
    Checkpoint(
        id="evo2_40b",
        model="Evo 2 40B",
        params="40B",
        modality=Modality.NUCLEOTIDE,
        role=Role.TEST_CONDITION,
        exclusion=Exclusion.LABEL_BASED,
        exclusion_note="Same policy and same corpus as evo2_7b; one lineage, two sizes.",
        corpus_pin="OpenGenome2",
        licence="Apache-2.0",
        access=(
            "HuggingFace arcinstitute/evo2_40b via the evo2 package; requires FP8 via "
            "Transformer Engine on a Hopper GPU, and multiple H100s for the 40B weights"
        ),
        sources=("S-EVO2-HF-40B", "S-EVO2-PREPRINT", "S-EVO2-REPO"),
        tier=2,
        needs_gpu=True,
    ),
)

# Nucleotide Transformer and ProGen2 are named in `DESIGN.md` §B1's Tier 2 list and are
# deliberately absent from TIER_2. Nothing about either has been retrieved into
# `policies/sources.json`, and §B1 step 0 forbids inheriting a training-data claim from this
# document. Adding them is an acquisition task, not an inventory entry — and under the compute
# finding below there is nothing to acquire them for yet.


def inventory(*, tiers: Iterable[int] = (1, 2)) -> tuple[Checkpoint, ...]:
    """The inventory, optionally restricted to given tiers."""
    wanted = set(tiers)
    return tuple(c for c in (*TIER_1, *TIER_2) if c.tier in wanted)


def checkpoint(cid: str) -> Checkpoint:
    """Look a checkpoint up by its published identifier."""
    for c in inventory():
        if c.id == cid:
            return c
    raise InventoryError(f"no checkpoint with id {cid!r}")


def validate(
    checkpoints: Iterable[Checkpoint] | None = None,
    *,
    sources: Mapping[str, Mapping[str, object]] | None = None,
) -> None:
    """Check the inventory's internal consistency, and its sources if given.

    Args:
        checkpoints: defaults to the full inventory.
        sources: `policies/sources.json` entries keyed by id. When given, every cited source
            must exist and be `retrieved` — an unretrieved source is not quotable, so a claim
            resting on one is not verified. `tools/specs.py` enforces the same rule for policy
            specs.

    Raises:
        InventoryError: on a duplicate id, an empty required field, a test condition with no
            stated exclusion mechanism, a positive control with one, or a bad source.
    """
    checkpoints = tuple(inventory() if checkpoints is None else checkpoints)

    seen: set[str] = set()
    for c in checkpoints:
        if c.id in seen:
            raise InventoryError(f"duplicate checkpoint id {c.id!r}")
        seen.add(c.id)

        for field in ("model", "licence", "access"):
            if not getattr(c, field):
                raise InventoryError(f"{c.id}: {field} is empty")
        if not c.sources:
            raise InventoryError(f"{c.id}: cites no source")
        if c.tier not in (1, 2):
            raise InventoryError(f"{c.id}: tier {c.tier} is not 1 or 2")

        # The design's own logic: a test condition exists to have a stated exclusion whose
        # consequences Phase B measures, and a positive control exists to lack one. A
        # checkpoint on the wrong side of that is a design error, not a data-entry slip.
        if c.role is Role.TEST_CONDITION and c.exclusion is Exclusion.NONE:
            raise InventoryError(f"{c.id}: test condition with no stated exclusion")
        if c.role is Role.POSITIVE_CONTROL and c.exclusion is not Exclusion.NONE:
            raise InventoryError(f"{c.id}: positive control with a stated exclusion")

        if sources is not None:
            for sid in c.sources:
                entry = sources.get(sid)
                if entry is None:
                    raise InventoryError(f"{c.id}: cites unknown source {sid!r}")
                if entry.get("status") != "retrieved":
                    raise InventoryError(
                        f"{c.id}: cites {sid!r}, whose status is "
                        f"{entry.get('status')!r} — not quotable, so not verified"
                    )


def feasibility(
    checkpoints: Iterable[Checkpoint] | None = None,
    *,
    gpu_available: bool,
) -> dict[str, str]:
    """Classify each checkpoint as runnable or not, given whether a GPU can be had.

    Kept separate from :class:`Checkpoint` on purpose. What a model needs is published by its
    developers; what this project can launch is measured by `tools/ec2_capability.py`, changes
    when the account's policy changes, and must not be frozen into the inventory.

    This answers the hard requirement only — whether the published instructions demand an
    accelerator at all. It says nothing about throughput, and `"runnable"` here does not mean
    a 200-assay zero-shot pass finishes in useful time on 8 CPU cores. Measuring that is
    B1.2's first job, not a claim to make from an inventory.

    Returns:
        checkpoint id -> `"runnable"`, or a one-line reason it is not.
    """
    checkpoints = tuple(inventory() if checkpoints is None else checkpoints)
    out: dict[str, str] = {}
    for c in checkpoints:
        if c.needs_gpu and not gpu_available:
            out[c.id] = "blocked: published run instructions require a GPU, and none is available"
        else:
            out[c.id] = "runnable"
    return out

"""The zero-shot scoring harness — task B1.2, DESIGN.md §B1 and §4.

One interface, five checkpoints, and the §4 scope limits enforced here rather than trusted.
`tools/score_variants.py` is the pipeline and `tools/ec2_score.py` puts it on a GPU; this
module is the contract they both run under and is importable without a deep-learning stack,
so the refusals and the schema are testable in the pinned environment.

**§4 is enforced three ways, because one way is a convention.**

*By what the request can say.* :class:`ScoringRequest` carries a checkpoint, a wild-type
sequence and a list of substitutions, and has no field for a prompt, an example, a
demonstration or a retrieved neighbour. §4 declines in-context capability-recovery
experiments, and the absence of anywhere to put the context is what makes that structural
rather than a promise. :func:`ScoringRequest.__post_init__` refuses anything it cannot read as
a substitution set.

*By what a backend may expose.* :func:`enforce_scope` refuses a backend carrying a generation,
sampling or training entry point at all, and refuses one reporting a trainable parameter. A
GPU became available to this project at B1.1, which is the moment fine-tuning stopped being
impossible and started being merely forbidden; `policies/models.md` says to constrain the
harness instead of relying on intent, and this is that.

*By what the source tree contains.* `tests/test_scoring.py` parses `src/` and `tools/` for
generation and training calls, the same inverted inventory X1.5 used for the durability guard
(D-203). A convention nobody can grep is a convention that drifts.

**Two primitives, declared per backend, and no third.** A masked or wild-type protein language
model gives per-position distributions and the score is the summed log-ratio at the mutated
positions. An autoregressive nucleotide model gives whole-sequence log-likelihoods and the
score is the mutant's minus the wild type's. Both are likelihood readings of a frozen model.
Nothing else is in the interface, so nothing else can be run through it by accident.

**Determinism is measured, not asserted.** :func:`determinism_evidence` re-scores a sample and
records whether the two passes agree bitwise, which goes in the run manifest. A harness that
claims determinism without re-running is claiming a property of code it did not test.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "AMINO_ACIDS",
    "FORBIDDEN_BACKEND_ATTRS",
    "Backend",
    "Mode",
    "ScopeError",
    "ScoringError",
    "ScoringRequest",
    "Substitution",
    "Variant",
    "determinism_evidence",
    "enforce_scope",
    "request_fields",
    "score_request",
    "variants_from_mutants",
]

#: The twenty, in the one order every artefact prints them in.
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"

_SUBSTITUTION = re.compile(r"^([A-Z])(\d+)([A-Z])$")


class ScoringError(RuntimeError):
    """The harness cannot stand behind a score it would otherwise return."""


class ScopeError(ScoringError):
    """A DESIGN.md §4 scope limit would be crossed. Never caught inside this package."""


class Mode(str, Enum):
    """How a backend produces a score. Recorded on every row: a published reference number is
    a number *for a mode*, and comparing across modes is comparing two different measurements.
    """

    #: Mask each mutated position, read the distribution there. The protein-LM default.
    MASKED_MARGINALS = "masked_marginals"
    #: One forward pass over the wild type, read the distributions at the mutated positions.
    WT_MARGINALS = "wt_marginals"
    #: Whole-sequence log-likelihood, mutant minus wild type. Autoregressive models.
    SEQUENCE_DELTA = "sequence_delta"


MARGINAL_MODES = frozenset({Mode.MASKED_MARGINALS, Mode.WT_MARGINALS})

#: A backend carrying any of these is refused outright. Not a list of things not to call: a
#: list of things a zero-shot scoring backend has no business being able to do (§4).
FORBIDDEN_BACKEND_ATTRS: tuple[str, ...] = (
    "backward",
    "fine_tune",
    "fit",
    "generate",
    "sample",
    "train",
    "train_step",
)


@dataclasses.dataclass(frozen=True, slots=True)
class Substitution:
    """One single-residue substitution, 1-based, in the benchmark's own notation."""

    wild: str
    position: int
    mutant: str

    @classmethod
    def parse(cls, text: str) -> Substitution:
        match = _SUBSTITUTION.match(text.strip())
        if not match:
            raise ScoringError(
                f"{text!r} is not a substitution in the benchmark's notation (e.g. 'A123G')"
            )
        wild, position, mutant = match.group(1), int(match.group(2)), match.group(3)
        for residue in (wild, mutant):
            if residue not in AMINO_ACIDS:
                raise ScoringError(f"{text!r}: {residue!r} is not one of the twenty")
        if position < 1:
            raise ScoringError(f"{text!r}: positions are 1-based")
        return cls(wild=wild, position=position, mutant=mutant)

    def __str__(self) -> str:
        return f"{self.wild}{self.position}{self.mutant}"

    def check(self, wild_type: str) -> None:
        """Refuse a substitution whose stated wild-type residue is not the one in the sequence.

        An off-by-one in an offset convention produces plausible scores for the wrong
        positions, which is the failure that does not announce itself.
        """
        if self.position > len(wild_type):
            raise ScoringError(
                f"{self}: position {self.position} is past the end of a "
                f"{len(wild_type)}-residue sequence"
            )
        found = wild_type[self.position - 1]
        if found != self.wild:
            raise ScoringError(
                f"{self}: the sequence has {found!r} at position {self.position}, not "
                f"{self.wild!r} — the offset convention does not match the benchmark's"
            )

    def apply(self, sequence: str) -> str:
        self.check(sequence)
        return sequence[: self.position - 1] + self.mutant + sequence[self.position :]


@dataclasses.dataclass(frozen=True, slots=True)
class Variant:
    """One benchmark row: its identifier and the substitutions it names.

    Multi-mutants are kept. Dropping them would silently redefine the benchmark, which
    `amazebio.proteingym` already refuses to do for the same reason.
    """

    mutant: str
    substitutions: tuple[Substitution, ...]

    @classmethod
    def parse(cls, mutant: str) -> Variant:
        parts = [p for p in mutant.strip().split(":") if p]
        if not parts:
            raise ScoringError("an empty variant identifier")
        subs = tuple(Substitution.parse(p) for p in parts)
        positions = [s.position for s in subs]
        if len(set(positions)) != len(positions):
            raise ScoringError(f"{mutant!r}: two substitutions at the same position")
        return cls(mutant=mutant.strip(), substitutions=subs)

    def apply(self, sequence: str) -> str:
        out = sequence
        for sub in self.substitutions:
            out = sub.apply(out)
        return out


@dataclasses.dataclass(frozen=True, slots=True)
class ScoringRequest:
    """Everything the harness is allowed to know about a scoring job.

    The field list is the §4 enforcement: there is no prompt, no exemplar, no demonstration
    set and no retrieved context, so an in-context capability-recovery experiment cannot be
    expressed through this interface at all. A test asserts the field names, because the
    enforcement is the absence and an absence is easy to end by accident.
    """

    checkpoint: str
    wild_type: str
    variants: tuple[Variant, ...]
    #: Required only by a nucleotide backend, and never synthesised. Reverse-translating a
    #: protein would make this project choose the codons, and a score would then depend on a
    #: choice no published source states. A missing CDS is reported, not filled in.
    nucleotide_wild_type: str | None = None

    def __post_init__(self) -> None:
        if not self.wild_type:
            raise ScoringError(f"{self.checkpoint}: an empty wild-type sequence")
        unknown = sorted(set(self.wild_type) - set(AMINO_ACIDS))
        if unknown:
            raise ScoringError(
                f"{self.checkpoint}: the wild type carries {unknown}, which are not among the "
                "twenty; a non-standard residue changes what a marginal means and is refused "
                "rather than mapped to X"
            )
        if not self.variants:
            raise ScoringError(f"{self.checkpoint}: a scoring request with no variants")
        seen = [v.mutant for v in self.variants]
        if len(set(seen)) != len(seen):
            raise ScoringError(f"{self.checkpoint}: the same variant appears twice")
        for variant in self.variants:
            for sub in variant.substitutions:
                sub.check(self.wild_type)

    @property
    def positions(self) -> tuple[int, ...]:
        """Every mutated position, ascending. What a marginal backend is asked for."""
        return tuple(sorted({s.position for v in self.variants for s in v.substitutions}))


@runtime_checkable
class Backend(Protocol):
    """What a checkpoint must offer, and the whole of what it may.

    Implementations live behind a lazy import so this module stays importable without a
    deep-learning stack; `tools/score_variants.py` loads the one it needs.
    """

    checkpoint_id: str
    mode: Mode
    #: Parameters the loaded model reports as trainable. Anything but zero is refused.
    trainable_parameters: int
    #: What the backend reads: `"protein"` or `"nucleotide"`.
    modality: str

    def position_log_probs(
        self, sequence: str, positions: Sequence[int]
    ) -> Mapping[int, Mapping[str, float]]:
        """Log-probabilities over the alphabet at each requested 1-based position."""

    def sequence_log_likelihood(self, sequences: Sequence[str]) -> Sequence[float]:
        """Total log-likelihood of each sequence."""


def enforce_scope(backend: object) -> None:
    """Refuse a backend that could do anything §4 forbids. Called before every pass.

    This checks what the object *exposes*, not what the caller intends to use. A backend
    holding a `generate` is a backend one line away from generation, and §4 says to constrain
    the harness rather than rely on the harness being used carefully.
    """
    present = sorted(name for name in FORBIDDEN_BACKEND_ATTRS if hasattr(backend, name))
    if present:
        raise ScopeError(
            f"{getattr(backend, 'checkpoint_id', backend)!r} exposes {present}. DESIGN.md §4 "
            "permits zero-shot scoring only: no generation, no sampling, no fine-tuning. "
            "Wrap the model so the harness cannot reach these, rather than agreeing not to "
            "call them."
        )
    trainable = getattr(backend, "trainable_parameters", None)
    if trainable is None:
        raise ScopeError(
            f"{getattr(backend, 'checkpoint_id', backend)!r} does not report its trainable "
            "parameter count, so the harness cannot establish the model is frozen"
        )
    if trainable != 0:
        raise ScopeError(
            f"{getattr(backend, 'checkpoint_id', backend)!r} reports {trainable:,} trainable "
            "parameters. §4 forbids fine-tuning to restore excluded capability; a frozen "
            "model reports zero."
        )
    mode = getattr(backend, "mode", None)
    if not isinstance(mode, Mode):
        raise ScopeError(
            f"{getattr(backend, 'checkpoint_id', backend)!r} declares no scoring mode; a score "
            "whose mode is unrecorded cannot be compared with a published reference"
        )


def score_request(backend: Backend, request: ScoringRequest) -> dict[str, float]:
    """Every variant's zero-shot score under one frozen checkpoint.

    A score is a log-ratio against the wild type in both modes, so it is positive when the
    model prefers the mutant. That sign convention is the benchmark's and is not negotiable
    here: a flipped sign turns a Spearman correlation into its negative and reads as a model
    that is exactly wrong rather than as a bug.
    """
    enforce_scope(backend)
    if backend.checkpoint_id != request.checkpoint:
        raise ScoringError(
            f"the request names {request.checkpoint!r} and the backend is "
            f"{backend.checkpoint_id!r}; a score filed under the wrong checkpoint is worse "
            "than no score"
        )

    if backend.modality == "nucleotide":
        if request.nucleotide_wild_type is None:
            raise ScoringError(
                f"{backend.checkpoint_id}: a nucleotide model needs the assay's coding "
                "sequence, and this request carries none. It is not synthesised: "
                "reverse-translating would make this project choose the codons, and the "
                "score would then depend on a choice no published source states."
            )
        raise ScoringError(
            f"{backend.checkpoint_id}: scoring protein substitutions through a nucleotide "
            "model needs a pinned CDS per assay and a stated codon-to-residue mapping. "
            "Neither is pinned yet, so the arm is reported as not run rather than estimated."
        )

    if backend.mode in MARGINAL_MODES:
        return _score_marginals(backend, request)
    if backend.mode is Mode.SEQUENCE_DELTA:
        return _score_sequence_delta(backend, request)
    raise ScoringError(f"{backend.checkpoint_id}: unhandled scoring mode {backend.mode!r}")


def _score_marginals(backend: Backend, request: ScoringRequest) -> dict[str, float]:
    table = backend.position_log_probs(request.wild_type, request.positions)
    missing = [p for p in request.positions if p not in table]
    if missing:
        raise ScoringError(
            f"{backend.checkpoint_id}: no distribution at positions {missing[:8]}; a variant "
            "scored from a partial table would be scored against a different model"
        )
    out: dict[str, float] = {}
    for variant in request.variants:
        total = 0.0
        for sub in variant.substitutions:
            row = table[sub.position]
            for residue in (sub.wild, sub.mutant):
                if residue not in row:
                    raise ScoringError(
                        f"{backend.checkpoint_id}: position {sub.position} has no "
                        f"log-probability for {residue!r}"
                    )
            total += row[sub.mutant] - row[sub.wild]
        out[variant.mutant] = total
    return out


def _score_sequence_delta(backend: Backend, request: ScoringRequest) -> dict[str, float]:
    sequences = [request.wild_type, *(v.apply(request.wild_type) for v in request.variants)]
    likelihoods = list(backend.sequence_log_likelihood(sequences))
    if len(likelihoods) != len(sequences):
        raise ScoringError(
            f"{backend.checkpoint_id}: asked for {len(sequences)} likelihoods and got "
            f"{len(likelihoods)}"
        )
    wild = likelihoods[0]
    return {v.mutant: likelihoods[i + 1] - wild for i, v in enumerate(request.variants)}


def determinism_evidence(
    backend: Backend,
    request: ScoringRequest,
    *,
    sample: int = 32,
) -> dict[str, object]:
    """Re-score a sample and report whether the two passes agree bitwise.

    Evidence for the run manifest, not an assertion: a harness that declares itself
    deterministic without re-running has tested nothing. A disagreement is reported with its
    largest gap so a reader can tell a non-deterministic kernel from a reordered reduction.
    """
    if sample < 1:
        raise ScoringError("a determinism check over no variants establishes nothing")
    subset = request.variants[:sample]
    probe = dataclasses.replace(request, variants=subset)
    first = score_request(backend, probe)
    second = score_request(backend, probe)
    gaps = {k: abs(first[k] - second[k]) for k in first if first[k] != second.get(k)}
    return {
        "variants_rescored": len(subset),
        "bitwise_identical": not gaps,
        "disagreeing_variants": len(gaps),
        "largest_gap": max(gaps.values()) if gaps else 0.0,
        "mode": backend.mode.value,
        "checkpoint": backend.checkpoint_id,
    }


def request_fields() -> tuple[str, ...]:
    """The request's field names, so a test can pin the absence that §4 rests on."""
    return tuple(f.name for f in dataclasses.fields(ScoringRequest))


def variants_from_mutants(mutants: Iterable[str]) -> tuple[Variant, ...]:
    """Parse a benchmark's mutant column, in the order given."""
    return tuple(Variant.parse(m) for m in mutants)

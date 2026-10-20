"""Checkpoint adapters for the scoring harness — task B1.2, DESIGN.md §B1 and §4.

`amazebio.scoring` is the contract; this is what sits behind it for each checkpoint in the
B1.1 inventory. The split exists so that `scoring` imports with no deep-learning stack and the
refusals stay testable in the pinned environment, while the weights load only where a GPU is.

**The torch-touching surface is one function per backend, and it is injected.** Everything
else here — tokenising, choosing which positions to mask, batching, turning a logit row into
log-probabilities over the twenty, assembling the table — is ordinary Python over lists and is
exercised by `tests/test_backends.py` with a stub in place of the model. That is deliberate: a
masked-marginals implementation is a pile of off-by-one risks around an unremarkable forward
pass, and testing the pile needs no accelerator. A bug in the offset convention produces
plausible scores at the wrong residues, which is the failure that does not announce itself,
and `Substitution.check` plus these tests are what catch it.

**A loaded model is wrapped, not trusted.** :class:`FrozenLM` exposes exactly the two
operations the harness uses and does not define `generate`, `sample`, `train` or `fit` at all,
so `scoring.enforce_scope` passes for the reason that matters: the entry points are absent
rather than present-and-not-called. §4 says to constrain the harness, and the GPU that B1.1
obtained is what turned that from impossible into merely forbidden.

**Nothing in this module downloads or caches weights.** :func:`recipe` says what to load and
from where, as a data record traceable to `policies/models.md`; the loader is the caller's,
runs where the weights are, and passes its forward function in.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping, Sequence

from amazebio.scoring import AMINO_ACIDS, Mode, ScoringError

__all__ = [
    "RECIPES",
    "FrozenLM",
    "Recipe",
    "log_softmax",
    "mask_batches",
    "recipe",
]

#: A forward pass: a batch of token-id rows in, a logit row per position per row out. The one
#: thing a backend needs an accelerator for, and the one thing these tests stub.
Forward = Callable[[Sequence[Sequence[int]]], Sequence[Sequence[Sequence[float]]]]


@dataclasses.dataclass(frozen=True, slots=True)
class Recipe:
    """What to load for a checkpoint, and how its vocabulary maps to the twenty.

    Every field traces to `policies/models.md`, where the access route carries a quotation
    `tools/policies.py` checks against the stored source. Nothing here is inferred from a
    package's defaults.
    """

    checkpoint_id: str
    mode: Mode
    modality: str
    #: How the weights are obtained, verbatim from the inventory's `access` field.
    access: str
    #: The loader the published instructions name, as a string rather than an import: this
    #: module does not import any of them.
    loader: str
    #: This checkpoint's column in ProteinGym's own zero-shot score archive, where it has
    #: one. It is what B1.2's validation step compares against (D-208), and it is pinned here
    #: beside the checkpoint rather than passed in, because pairing our scores with another
    #: model's column would produce a divergence with no obvious cause. `None` means the
    #: benchmark publishes no scores for this checkpoint and the check cannot run.
    published_column: str | None = None

    def __post_init__(self) -> None:
        if self.modality not in {"protein", "nucleotide"}:
            raise ScoringError(f"{self.checkpoint_id}: unknown modality {self.modality!r}")


RECIPES: tuple[Recipe, ...] = (
    Recipe(
        checkpoint_id="esm2_t33_650M_UR50D",
        published_column="ESM2_650M",
        mode=Mode.MASKED_MARGINALS,
        modality="protein",
        access="facebook/esm2_t33_650M_UR50D on HuggingFace, or the fair-esm package",
        loader="transformers.EsmForMaskedLM",
    ),
    Recipe(
        checkpoint_id="esm2_t36_3B_UR50D",
        published_column="ESM2_3B",
        mode=Mode.MASKED_MARGINALS,
        modality="protein",
        access="facebook/esm2_t36_3B_UR50D on HuggingFace, or the fair-esm package",
        loader="transformers.EsmForMaskedLM",
    ),
    Recipe(
        checkpoint_id="esm3-sm-open-v1",
        published_column="ESM3",
        mode=Mode.MASKED_MARGINALS,
        modality="protein",
        access="HuggingFace biohub/esm3-sm-open-v1, loaded via the esm package",
        loader="esm.models.esm3.ESM3",
    ),
    Recipe(
        checkpoint_id="ESMC-600M",
        published_column="ESMC-600M",
        mode=Mode.MASKED_MARGINALS,
        modality="protein",
        access="HuggingFace biohub/ESMC-600M; also in transformers from v5.16.0",
        loader="esm.models.esmc.ESMC",
    ),
    Recipe(
        checkpoint_id="evo2_7b",
        mode=Mode.SEQUENCE_DELTA,
        modality="nucleotide",
        access="HuggingFace arcinstitute/evo2_7b via the evo2 package",
        loader="evo2.Evo2",
    ),
)


def recipe(checkpoint_id: str) -> Recipe:
    """The recipe for a checkpoint in the inventory, or a refusal naming what is there.

    Keyed to B1.1's inventory rather than open: a checkpoint nobody verified the exclusion
    status of has no place in a Phase B comparison, and silently accepting one would put an
    unaudited model in the same table as the audited ones.
    """
    for item in RECIPES:
        if item.checkpoint_id == checkpoint_id:
            return item
    raise ScoringError(
        f"{checkpoint_id!r} is not in the B1.1 inventory. Known: "
        f"{[r.checkpoint_id for r in RECIPES]}"
    )


def log_softmax(row: Sequence[float]) -> list[float]:
    """Log-softmax of one logit row, in plain Python.

    Shifted by the maximum before exponentiating, which is the ordinary trick and is the
    difference between a usable number and an overflow on a 33-token vocabulary with large
    logits.
    """
    if not row:
        raise ScoringError("a log-softmax over an empty logit row")
    top = max(row)
    exps = [math.exp(v - top) for v in row]
    total = sum(exps)
    return [math.log(e / total) if e > 0 else -math.inf for e in exps]


def mask_batches(positions: Sequence[int], *, batch_size: int) -> list[tuple[int, ...]]:
    """Group mutated positions into forward-pass batches, in ascending order.

    One masked copy of the sequence per position: masked marginals cannot batch two masks into
    one row without changing what each distribution is conditioned on, which is a different
    measurement and not a faster one.
    """
    if batch_size < 1:
        raise ScoringError("a batch of no sequences")
    ordered = sorted(set(positions))
    return [tuple(ordered[i : i + batch_size]) for i in range(0, len(ordered), batch_size)]


@dataclasses.dataclass(frozen=True, slots=True)
class FrozenLM:
    """A masked protein language model, reduced to the one reading the harness needs.

    Holds a forward function and a vocabulary; defines no generation, sampling or training
    entry point, which is what `scoring.enforce_scope` checks for. `trainable_parameters` is
    supplied by whoever loaded the weights and is asserted zero there rather than computed
    here, because this object never sees the parameters.
    """

    checkpoint_id: str
    mode: Mode
    modality: str
    trainable_parameters: int
    #: token string -> column in the logit row. Only the twenty are read; the rest are
    #: ignored, so a special token never becomes a residue by position.
    vocabulary: Mapping[str, int]
    #: residue string -> token id, for building an input row.
    encoder: Mapping[str, int]
    mask_token_id: int
    #: How many tokens precede residue 1 in a tokenised row — 1 for a BOS/CLS prefix. Stated
    #: rather than discovered, because getting it wrong shifts every distribution by one.
    prefix_tokens: int
    forward: Forward
    batch_size: int = 8
    #: Called with (batches done, batches total) after each forward pass. A long pass that
    #: prints nothing is indistinguishable from a dead one — the lesson `AGENTS.md` records
    #: for EC2 applies to a model pass in a container too, where the only difference is that
    #: the silence is cheaper. Defaults to doing nothing, so nothing is forced to care.
    progress: Callable[[int, int], None] | None = None

    def __post_init__(self) -> None:
        if self.trainable_parameters != 0:
            raise ScoringError(
                f"{self.checkpoint_id}: loaded with {self.trainable_parameters:,} trainable "
                "parameters; freeze the model before wrapping it (DESIGN.md §4)"
            )
        missing = sorted(set(AMINO_ACIDS) - set(self.vocabulary))
        if missing:
            raise ScoringError(
                f"{self.checkpoint_id}: the vocabulary has no column for {missing}; a "
                "marginal over a partial alphabet is not a marginal"
            )
        unencodable = sorted(set(AMINO_ACIDS) - set(self.encoder))
        if unencodable:
            raise ScoringError(f"{self.checkpoint_id}: cannot encode {unencodable}")

    def _encode(self, sequence: str) -> list[int]:
        try:
            body = [self.encoder[residue] for residue in sequence]
        except KeyError as exc:  # pragma: no cover - ScoringRequest rejects these first
            raise ScoringError(f"{self.checkpoint_id}: cannot encode {exc.args[0]!r}") from exc
        return [0] * self.prefix_tokens + body

    def position_log_probs(
        self, sequence: str, positions: Sequence[int]
    ) -> Mapping[int, Mapping[str, float]]:
        """Masked marginals: one masked copy per position, read at that position.

        The row index for residue `p` is `prefix_tokens + p - 1`. That arithmetic appears once,
        here, for the reason the module docstring gives.
        """
        base = self._encode(sequence)
        table: dict[int, Mapping[str, float]] = {}
        batches = mask_batches(positions, batch_size=self.batch_size)
        for done, batch in enumerate(batches, start=1):
            rows = []
            for position in batch:
                if not 1 <= position <= len(sequence):
                    raise ScoringError(
                        f"{self.checkpoint_id}: position {position} is outside a "
                        f"{len(sequence)}-residue sequence"
                    )
                row = list(base)
                row[self.prefix_tokens + position - 1] = self.mask_token_id
                rows.append(row)
            logits = self.forward(rows)
            if len(logits) != len(rows):
                raise ScoringError(
                    f"{self.checkpoint_id}: asked for {len(rows)} rows and got {len(logits)}"
                )
            for position, row_logits in zip(batch, logits, strict=True):
                index = self.prefix_tokens + position - 1
                if index >= len(row_logits):
                    raise ScoringError(
                        f"{self.checkpoint_id}: the model returned {len(row_logits)} "
                        f"positions and residue {position} needs index {index}"
                    )
                logprobs = log_softmax(row_logits[index])
                table[position] = {
                    residue: logprobs[self.vocabulary[residue]] for residue in AMINO_ACIDS
                }
            if self.progress is not None:
                self.progress(done, len(batches))
        return table

    def sequence_log_likelihood(self, sequences: Sequence[str]) -> Sequence[float]:
        raise ScoringError(
            f"{self.checkpoint_id} scores by {self.mode.value}; a whole-sequence likelihood "
            "from a masked model is a pseudo-likelihood and is a different measurement, so it "
            "is refused rather than returned under the same name"
        )

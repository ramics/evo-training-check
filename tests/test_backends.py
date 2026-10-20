"""The masked-marginals machinery, with a stub in place of the model.

A masked-marginals implementation is a pile of off-by-one risks around an unremarkable
forward pass. The pile is what these test — no accelerator, no weights — because an offset
bug produces plausible scores at the wrong residues and never announces itself.
"""

from __future__ import annotations

import math

import pytest

from amazebio import backends, scoring
from amazebio.backends import FrozenLM, Recipe, log_softmax, mask_batches
from amazebio.scoring import AMINO_ACIDS, Mode, ScoringError

# A toy vocabulary: a CLS token at 0, then the twenty, then a mask token.
VOCAB = {a: i + 1 for i, a in enumerate(AMINO_ACIDS)}
ENCODER = dict(VOCAB)
MASK_ID = len(AMINO_ACIDS) + 1
WT = "MKTAYIAKQR"


def make(forward, **kw):  # type: ignore[no-untyped-def]
    return FrozenLM(
        checkpoint_id=kw.pop("checkpoint_id", "stub"),
        mode=kw.pop("mode", Mode.MASKED_MARGINALS),
        modality="protein",
        trainable_parameters=kw.pop("trainable_parameters", 0),
        vocabulary=kw.pop("vocabulary", VOCAB),
        encoder=ENCODER,
        mask_token_id=MASK_ID,
        prefix_tokens=kw.pop("prefix_tokens", 1),
        prefix_token_ids=kw.pop("prefix_token_ids", (0,)),
        suffix_token_ids=kw.pop("suffix_token_ids", ()),
        forward=forward,
        **kw,
    )


def echo_forward(rows):  # type: ignore[no-untyped-def]
    """Logits that encode which token sits at each index, so a misread index is visible.

    Column `v` of position `i` is `row[i] * 100 + v`, so the distribution read at the wrong
    index is numerically different from the right one rather than merely plausible.
    """
    return [[[tok * 100.0 + v for v in range(MASK_ID + 1)] for tok in row] for row in rows]


class TestTheOffsetConvention:
    def test_the_masked_position_is_the_one_the_caller_asked_for(self) -> None:
        seen: list[list[int]] = []

        def forward(rows):  # type: ignore[no-untyped-def]
            seen.extend(list(r) for r in rows)
            return echo_forward(rows)

        make(forward).position_log_probs(WT, [1, 4, 10])
        # One masked copy per position, and the mask lands at prefix + p - 1.
        assert [r.index(MASK_ID) for r in seen] == [1, 4, 10]
        # Everything else is the wild type, unchanged.
        for row, position in zip(seen, (1, 4, 10), strict=True):
            rest = [t for i, t in enumerate(row) if i not in (0, position)]
            expected = [VOCAB[a] for i, a in enumerate(WT, start=1) if i != position]
            assert rest == expected

    def test_a_model_with_no_prefix_token_shifts_by_zero(self) -> None:
        seen: list[list[int]] = []

        def forward(rows):  # type: ignore[no-untyped-def]
            seen.extend(list(r) for r in rows)
            return echo_forward(rows)

        make(forward, prefix_tokens=0, prefix_token_ids=()).position_log_probs(WT, [1, 4])
        assert [r.index(MASK_ID) for r in seen] == [0, 3]

    def test_the_distribution_is_read_at_the_masked_index_not_at_position_minus_one(
        self,
    ) -> None:
        table = make(echo_forward).position_log_probs(WT, [4])
        # The echo puts MASK_ID * 100 in the logits at the masked index alone, so reading one
        # index off would give a row derived from a residue token instead.
        row = [MASK_ID * 100.0 + v for v in range(MASK_ID + 1)]
        expected = log_softmax(row)
        assert table[4]["A"] == pytest.approx(expected[VOCAB["A"]])

    def test_a_position_outside_the_sequence_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="outside a 10-residue sequence"):
            make(echo_forward).position_log_probs(WT, [11])


class TestRefusals:
    def test_a_model_with_trainable_parameters_cannot_be_wrapped(self) -> None:
        with pytest.raises(ScoringError, match="freeze the model"):
            make(echo_forward, trainable_parameters=1)

    def test_a_vocabulary_missing_a_residue_is_refused(self) -> None:
        short = {a: i for i, a in enumerate(AMINO_ACIDS) if a != "W"}
        with pytest.raises(ScoringError, match="not a marginal"):
            make(echo_forward, vocabulary=short)

    def test_a_forward_returning_the_wrong_number_of_rows_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="asked for"):
            make(lambda rows: echo_forward(rows)[:-1]).position_log_probs(WT, [1, 2])

    def test_a_truncated_logit_row_is_refused_rather_than_read_at_the_end(self) -> None:
        def truncated(rows):  # type: ignore[no-untyped-def]
            return [row[:3] for row in echo_forward(rows)]

        with pytest.raises(ScoringError, match="needs index"):
            make(truncated).position_log_probs(WT, [9])

    def test_a_masked_model_refuses_to_produce_a_sequence_likelihood(self) -> None:
        with pytest.raises(ScoringError, match="different measurement"):
            make(echo_forward).sequence_log_likelihood([WT])


class TestPureHelpers:
    def test_log_softmax_sums_to_one_in_probability_space(self) -> None:
        out = log_softmax([2.0, 1.0, -3.0, 0.5])
        assert sum(math.exp(v) for v in out) == pytest.approx(1.0)
        assert out[0] == max(out)

    def test_log_softmax_survives_logits_large_enough_to_overflow(self) -> None:
        out = log_softmax([1000.0, 999.0])
        assert all(math.isfinite(v) for v in out)

    def test_log_softmax_over_an_empty_row_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="empty logit row"):
            log_softmax([])

    def test_positions_are_batched_ascending_and_deduplicated(self) -> None:
        assert mask_batches([4, 1, 4, 9, 2], batch_size=2) == [(1, 2), (4, 9)]

    def test_a_batch_of_none_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="batch of no sequences"):
            mask_batches([1], batch_size=0)

    def test_batching_does_not_change_the_table(self) -> None:
        positions = [1, 2, 4, 7, 10]
        wide = make(echo_forward, batch_size=99).position_log_probs(WT, positions)
        narrow = make(echo_forward, batch_size=1).position_log_probs(WT, positions)
        assert wide == narrow


class TestTheInventoryIsTheGate:
    def test_every_recipe_names_a_checkpoint_the_inventory_verified(self) -> None:
        from amazebio import models

        known = {c.id for c in models.TIER_1}
        assert {r.checkpoint_id for r in backends.RECIPES} <= known

    def test_every_tier_1_checkpoint_has_a_recipe(self) -> None:
        from amazebio import models

        assert {r.checkpoint_id for r in backends.RECIPES} == {c.id for c in models.TIER_1}

    def test_a_checkpoint_outside_the_inventory_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="not in the B1.1 inventory"):
            backends.recipe("gpt-4")

    def test_the_nucleotide_model_is_the_one_that_scores_by_sequence_delta(self) -> None:
        assert backends.recipe("evo2_7b").mode is Mode.SEQUENCE_DELTA
        assert backends.recipe("evo2_7b").modality == "nucleotide"
        assert all(
            r.mode is Mode.MASKED_MARGINALS for r in backends.RECIPES if r.modality == "protein"
        )

    def test_an_unknown_modality_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="unknown modality"):
            Recipe(
                checkpoint_id="x",
                mode=Mode.MASKED_MARGINALS,
                modality="structure",
                access="",
                loader="",
            )


def test_a_wrapped_model_passes_the_scope_check_because_the_entry_points_are_absent() -> None:
    model = make(echo_forward)
    scoring.enforce_scope(model)
    for attr in scoring.FORBIDDEN_BACKEND_ATTRS:
        assert not hasattr(model, attr), f"FrozenLM must not define {attr}"


def test_the_harness_scores_through_a_wrapped_model_end_to_end() -> None:
    model = make(echo_forward, checkpoint_id="esm2_t33_650M_UR50D")
    request = scoring.ScoringRequest(
        checkpoint="esm2_t33_650M_UR50D",
        wild_type=WT,
        variants=scoring.variants_from_mutants(["M1A", "A4G", "M1A:A4G"]),
    )
    scores = scoring.score_request(model, request)
    assert set(scores) == {"M1A", "A4G", "M1A:A4G"}
    assert scores["M1A:A4G"] == pytest.approx(scores["M1A"] + scores["A4G"])
    assert scoring.determinism_evidence(model, request)["bitwise_identical"] is True


def test_a_long_pass_reports_progress_so_its_silence_can_be_read():
    """A pass that prints nothing is indistinguishable from a dead one. The callback fires
    once per forward pass and carries the total, so a caller can say how much is left."""
    seen: list[tuple[int, int]] = []
    model = make(echo_forward, batch_size=2, progress=lambda d, n: seen.append((d, n)))
    model.position_log_probs(WT, [1, 2, 3, 4, 5])
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_a_backend_with_no_progress_callback_still_scores():
    model = make(echo_forward, batch_size=2)
    assert len(model.position_log_probs(WT, [1, 2])) == 2


class TestTheRowCarriesBothEnds:
    """D-230. The models are trained with a start and an end token, and a row that carries
    only the first shows the model a truncation. It cost every protein score this project had
    produced, and it hid because the start id is zero on all four checkpoints, so a row filled
    with zeros was right at one end and silently wrong at the other."""

    def _row(self, **kw):
        seen = []

        def forward(rows):
            seen.extend(rows)
            return echo_forward(rows)

        make(forward, **kw).position_log_probs(WT, [1])
        return seen[0]

    def test_the_closing_token_is_in_the_row(self):
        assert self._row(suffix_token_ids=(2,))[-1] == 2

    def test_a_row_without_one_stops_at_the_last_residue(self):
        """The old behaviour, kept as a test so the difference is visible rather than
        remembered: with no closing token the row ends on a residue."""
        assert self._row(suffix_token_ids=())[-1] == ENCODER[WT[-1]]

    def test_the_opening_token_is_the_checkpoints_own_not_a_zero(self):
        assert self._row(prefix_token_ids=(7,))[0] == 7

    def test_adding_a_closing_token_does_not_shift_the_read_index(self):
        """The index arithmetic counts from the front, so the distribution read for residue 1
        must be the same with and without a suffix. If it moved, the fix would trade one
        off-by-one for another."""
        with_suffix = make(echo_forward, suffix_token_ids=(2,)).position_log_probs(WT, [1])
        without = make(echo_forward, suffix_token_ids=()).position_log_probs(WT, [1])
        assert with_suffix[1] == without[1]

    def test_opening_tokens_that_disagree_with_the_index_arithmetic_are_refused(self):
        with pytest.raises(ScoringError, match="would disagree"):
            make(echo_forward, prefix_tokens=1, prefix_token_ids=(0, 0))

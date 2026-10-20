"""B1.2's harness contract, and the §4 limits it is supposed to make unreachable.

These run without a deep-learning stack, which is the point of the split between
`amazebio.scoring` and whatever loads the weights: a refusal nobody can test in CI is a
refusal that stops holding.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from amazebio import scoring
from amazebio.scoring import Mode, ScopeError, ScoringError, ScoringRequest, Variant

ROOT = pathlib.Path(__file__).resolve().parent.parent
WT = "MKTAYIAKQR"


class Stub:
    """A minimal conforming backend. Nothing it can do is outside §4, by construction."""

    modality = "protein"

    def __init__(self, mode: Mode = Mode.MASKED_MARGINALS, *, trainable: int = 0) -> None:
        self.checkpoint_id = "stub"
        self.mode = mode
        self.trainable_parameters = trainable
        self.calls = 0

    def position_log_probs(self, sequence, positions):  # type: ignore[no-untyped-def]
        self.calls += 1
        # A fixed, position-dependent table: deterministic, and different per residue so a
        # score that ignored the mutant residue would come out zero and be caught.
        return {
            p: {a: -1.0 - (ord(a) % 7) - 0.1 * p for a in scoring.AMINO_ACIDS} for p in positions
        }

    def sequence_log_likelihood(self, sequences):  # type: ignore[no-untyped-def]
        self.calls += 1
        return [-float(len(s)) - sum(ord(c) for c in s) / 1000 for s in sequences]


def request(mutants=("A4G",), wt: str = WT, **kw):  # type: ignore[no-untyped-def]
    return ScoringRequest(
        checkpoint=kw.pop("checkpoint", "stub"),
        wild_type=wt,
        variants=scoring.variants_from_mutants(mutants),
        **kw,
    )


class TestTheRequestIsTheEnforcement:
    """§4 declines in-context capability recovery. There is nowhere to put the context."""

    def test_the_request_has_no_field_a_prompt_could_go_in(self) -> None:
        assert scoring.request_fields() == (
            "checkpoint",
            "wild_type",
            "variants",
            "nucleotide_wild_type",
        )

    def test_an_unexpected_keyword_is_a_type_error_not_an_ignored_field(self) -> None:
        with pytest.raises(TypeError):
            ScoringRequest(  # type: ignore[call-arg]
                checkpoint="stub",
                wild_type=WT,
                variants=scoring.variants_from_mutants(["A4G"]),
                prompt="here are five examples of active variants",
            )

    def test_a_wild_type_residue_that_does_not_match_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="offset convention"):
            request(["G5A"])

    def test_a_position_past_the_end_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="past the end"):
            request(["R99A"])

    def test_a_non_standard_residue_in_the_wild_type_is_refused_not_mapped_to_x(self) -> None:
        with pytest.raises(ScoringError, match="not among the twenty"):
            request(["M1A"], wt="MKUTAYIAKQR")

    def test_the_same_variant_twice_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="appears twice"):
            request(["A4G", "A4G"])

    def test_an_empty_request_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="no variants"):
            request([])


class TestVariantNotation:
    def test_a_multi_mutant_is_kept_not_dropped(self) -> None:
        variant = Variant.parse("M1A:A4G")
        assert len(variant.substitutions) == 2
        assert variant.apply(WT) == "AKTGYIAKQR"

    def test_two_substitutions_at_one_position_are_refused(self) -> None:
        with pytest.raises(ScoringError, match="same position"):
            Variant.parse("A4G:A4V")

    @pytest.mark.parametrize("bad", ["A5", "5G", "a5g", "A0G", "B5G", "A5B", ""])
    def test_malformed_notation_is_refused(self, bad: str) -> None:
        with pytest.raises(ScoringError):
            Variant.parse(bad)


class TestScopeEnforcement:
    @pytest.mark.parametrize("attr", scoring.FORBIDDEN_BACKEND_ATTRS)
    def test_a_backend_exposing_a_forbidden_entry_point_is_refused(self, attr: str) -> None:
        stub = Stub()
        setattr(stub, attr, lambda *a, **k: None)
        with pytest.raises(ScopeError, match="zero-shot scoring only"):
            scoring.enforce_scope(stub)

    def test_a_backend_with_trainable_parameters_is_refused(self) -> None:
        with pytest.raises(ScopeError, match="forbids fine-tuning"):
            scoring.enforce_scope(Stub(trainable=650_000_000))

    def test_a_backend_that_does_not_report_its_parameters_is_refused(self) -> None:
        class Silent:
            checkpoint_id = "silent"
            mode = Mode.MASKED_MARGINALS

        with pytest.raises(ScopeError, match="cannot establish the model is frozen"):
            scoring.enforce_scope(Silent())

    def test_a_backend_with_no_declared_mode_is_refused(self) -> None:
        stub = Stub()
        stub.mode = "masked"  # type: ignore[assignment]
        with pytest.raises(ScopeError, match="declares no scoring mode"):
            scoring.enforce_scope(stub)

    def test_scoring_enforces_scope_before_it_touches_the_model(self) -> None:
        stub = Stub(trainable=1)
        with pytest.raises(ScopeError):
            scoring.score_request(stub, request())
        assert stub.calls == 0


class TestScores:
    def test_a_marginal_score_is_the_summed_log_ratio_at_the_mutated_positions(self) -> None:
        stub = Stub()
        table = stub.position_log_probs(WT, [4])
        scores = scoring.score_request(stub, request(["A4G"]))
        assert scores["A4G"] == pytest.approx(table[4]["G"] - table[4]["A"])

    def test_a_multi_mutant_sums_its_substitutions(self) -> None:
        stub = Stub()
        scores = scoring.score_request(stub, request(["M1A", "A4G", "M1A:A4G"]))
        assert scores["M1A:A4G"] == pytest.approx(scores["M1A"] + scores["A4G"])

    def test_a_sequence_delta_score_is_mutant_minus_wild_type(self) -> None:
        stub = Stub(Mode.SEQUENCE_DELTA)
        scores = scoring.score_request(stub, request(["A4G"]))
        wild, mutant = stub.sequence_log_likelihood([WT, "MKTGYIAKQR"])
        assert scores["A4G"] == pytest.approx(mutant - wild)

    def test_a_score_filed_under_the_wrong_checkpoint_is_refused(self) -> None:
        with pytest.raises(ScoringError, match="worse than no score"):
            scoring.score_request(Stub(), request(checkpoint="esm2_t33_650M_UR50D"))

    def test_a_partial_marginal_table_is_refused_rather_than_scored_around(self) -> None:
        class Partial(Stub):
            def position_log_probs(self, sequence, positions):  # type: ignore[no-untyped-def]
                return {
                    p: row
                    for p, row in super().position_log_probs(sequence, positions).items()
                    if p != 4
                }

        with pytest.raises(ScoringError, match="no distribution at positions"):
            scoring.score_request(Partial(), request(["A4G"]))


class TestTheNucleotideArm:
    """Refused with its reason, not estimated. The codon choice would be ours."""

    def test_a_nucleotide_backend_without_a_coding_sequence_says_what_is_missing(self) -> None:
        stub = Stub(Mode.SEQUENCE_DELTA)
        stub.modality = "nucleotide"
        with pytest.raises(ScoringError, match="reverse-translating"):
            scoring.score_request(stub, request())

    def test_even_with_one_the_arm_is_reported_as_not_run(self) -> None:
        stub = Stub(Mode.SEQUENCE_DELTA)
        stub.modality = "nucleotide"
        with pytest.raises(ScoringError, match="not run rather than estimated"):
            scoring.score_request(stub, request(nucleotide_wild_type="ATG" * 10))


class TestDeterminism:
    def test_a_deterministic_backend_reports_bitwise_agreement(self) -> None:
        evidence = scoring.determinism_evidence(Stub(), request(["A4G", "M1A"]))
        assert evidence["bitwise_identical"] is True
        assert evidence["variants_rescored"] == 2
        assert evidence["largest_gap"] == 0.0

    def test_a_drifting_backend_is_caught_and_its_largest_gap_reported(self) -> None:
        """A shift common to both residues of a substitution very nearly cancels in the
        log-ratio — and `nearly` is the whole reason the check is bitwise rather than
        approximate. A tolerance wide enough to forgive this drift would forgive a
        non-deterministic kernel too."""

        class Drifts(Stub):
            def __init__(self) -> None:
                super().__init__()
                self.nudge = 0.0

            def position_log_probs(self, sequence, positions):  # type: ignore[no-untyped-def]
                self.nudge += 1e-6
                return {
                    p: {a: v + self.nudge for a, v in row.items()}
                    for p, row in super().position_log_probs(sequence, positions).items()
                }

        evidence = scoring.determinism_evidence(Drifts(), request(["M1A:A4G"]))
        assert evidence["bitwise_identical"] is False
        assert evidence["disagreeing_variants"] == 1
        assert 0.0 < float(evidence["largest_gap"]) < 1e-9

    def test_a_check_over_no_variants_establishes_nothing_and_says_so(self) -> None:
        with pytest.raises(ScoringError, match="establishes nothing"):
            scoring.determinism_evidence(Stub(), request(), sample=0)


#: Modules that may legitimately contain one of the forbidden call shapes. Empty, and the
#: point is that it stays empty: an entry here is a deliberate, reviewed act.
SCOPE_EXEMPT: set[str] = set()

#: Attribute calls §4 forbids anywhere in the shipped source. `.train(` catches both a
#: training loop and `model.train()`, and either is out of scope.
FORBIDDEN_CALLS = ("generate", "backward", "fine_tune", "train_step")


def test_no_shipped_module_calls_a_generation_or_training_entry_point():
    """§4 in the source tree, the inverted inventory X1.5 used for the durability guard.

    The harness refuses a backend that *exposes* these; this refuses a module that *calls*
    one, which is the other half. A GPU is available to this project now, so "we would not
    fine-tune" stopped being a statement about capability and became a statement about
    intent — and `policies/models.md` says to constrain the harness instead.
    """
    offenders = []
    for path in sorted([*(ROOT / "src" / "amazebio").glob("*.py"), *(ROOT / "tools").glob("*.py")]):
        if path.name in SCOPE_EXEMPT:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN_CALLS
            ):
                offenders.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
    assert not offenders, (
        "DESIGN.md §4 permits zero-shot scoring only — no generation, no fine-tuning, no "
        f"capability recovery. These calls cross that line: {offenders}"
    )


def test_no_shipped_module_imports_a_fine_tuning_library():
    """The other way the line gets crossed: a dependency that does it for you."""
    banned = {"peft", "trl", "bitsandbytes", "accelerate", "deepspeed", "lightning"}
    offenders = []
    for path in sorted([*(ROOT / "src" / "amazebio").glob("*.py"), *(ROOT / "tools").glob("*.py")]):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in banned:
                    offenders.append(f"{path.name}:{node.lineno} {name}")
    assert not offenders, f"these imports exist to train models, which §4 forbids: {offenders}"

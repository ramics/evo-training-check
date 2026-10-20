"""Tests for `tools/score_variants.py` — B1.2's scoring driver.

The pass itself needs weights and three quarters of an hour, so what is tested here is
everything around it that can throw the pass away: which published column it checks itself
against, and that the scores reach disk before the check that can fail on them.
"""

from __future__ import annotations

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "score_variants", _PATH.parent.parent / "tools" / "score_variants.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

from amazebio import backends  # noqa: E402


def test_a_checkpoint_falls_back_to_the_column_its_recipe_names() -> None:
    """The bug this exists for: the resolved column was computed and the unresolved one
    passed on, so the run looked for a column named `None` after scoring everything."""
    spec = backends.recipe("esm2_t33_650M_UR50D")
    assert spec.published_column
    assert tool.resolve_published_column(None, spec) == spec.published_column


def test_an_explicit_column_wins_over_the_recipe() -> None:
    spec = backends.recipe("esm2_t33_650M_UR50D")
    assert tool.resolve_published_column("CARP_640M", spec) == "CARP_640M"


def test_a_checkpoint_with_no_published_column_asks_for_no_check() -> None:
    """Evo 2 has no column in the benchmark, and inventing one would compare our scores
    against somebody else's model."""
    spec = backends.recipe("evo2_7b")
    assert spec.published_column is None
    assert tool.resolve_published_column(None, spec) is None


def test_the_scores_are_written_before_the_check_that_can_fail_on_them() -> None:
    """Asserted on the call rather than the prose: `_score` takes a `checkpoint` callback
    and calls it before `load_model_scores`, so a failure in the verification does not cost
    the forward passes."""
    import ast
    import inspect

    source = inspect.getsource(tool._score)
    tree = ast.parse(source.strip())
    order = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "checkpoint")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "load_model_scores")
        )
    ]
    assert len(order) == 2, "expected one checkpoint call and one published-scores read"
    assert order[0] < order[1]


class _Recipe:
    def __init__(self, loader: str) -> None:
        self.loader = loader


def test_the_evolutionaryscale_route_is_chosen_by_the_published_access_route() -> None:
    """Not by checkpoint name. The inventory records how each model's authors say to load
    it, and a route this harness picked for itself would be a claim they did not make."""
    assert tool.is_evolutionaryscale(_Recipe("esm.models.esm3.ESM3"))
    assert tool.is_evolutionaryscale(_Recipe("esm.models.esmc.ESMC"))
    assert not tool.is_evolutionaryscale(_Recipe("transformers.EsmForMaskedLM"))


def test_each_route_reads_its_own_output_objects_sequence_logits() -> None:
    """The two output objects name the same tensor differently, and reading the wrong
    attribute on either is the kind of mistake that produces plausible numbers."""

    class MaskedLM:
        def __call__(self, *, input_ids):
            return type("Out", (), {"logits": ("masked", input_ids)})()

    class Multitrack:
        def __call__(self, *, sequence_tokens):
            return type("Out", (), {"sequence_logits": ("sequence", sequence_tokens)})()

    assert tool._masked_lm_logits(MaskedLM(), "rows") == ("masked", "rows")
    assert tool._sequence_logits(Multitrack(), "rows") == ("sequence", "rows")

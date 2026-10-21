"""The audit in `tools/baseline_reference_audit.py` — task B4.2, D-248.

The claim the audit rests on is that "absent from the alignment column" is readable off a score
table: within one position the structural factor is a constant, so every amino acid missing from
the column shares the most extreme score. These cover that reading, the direction of the
difference it measures, and the two cases that would make it meaningless — a position where our
own scores are all zero, and an assay with nothing in common to compare.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "baseline_reference_audit.py"
_spec = importlib.util.spec_from_file_location("baseline_reference_audit_under_test", _PATH)
audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = audit
_spec.loader.exec_module(audit)


def test_agreement_and_no_flips_when_both_sides_see_the_same_column() -> None:
    """Scores that differ by a positive scale factor rank identically, and nothing is flipped:
    a published column computed to a different precision must not read as a disagreement."""
    ours = {"A1C": -1.0, "A1D": -2.0, "A1E": -5.0, "A1F": -5.0}
    published = {k: v * 1.5 for k, v in ours.items()}
    result = audit.audit_assay(ours, published)
    assert result["agreement"] == 1.0
    assert result["absent_in_published_only"] == 0
    assert result["absent_on_our_side_only"] == 0


def test_an_amino_acid_absent_only_in_the_published_column_is_counted() -> None:
    """D-248's measurement. `A1D` is at the published column's per-position extreme and not at
    ours, so the published side treats it as missing from the alignment and we do not."""
    ours = {"A1C": -1.0, "A1D": -2.0, "A1E": -5.0}
    published = {"A1C": -1.0, "A1D": -5.0, "A1E": -5.0}
    result = audit.audit_assay(ours, published)
    assert result["absent_in_published_only"] == 1
    assert result["examples_absent_in_published_only"] == ["A1D"]
    assert result["absent_on_our_side_only"] == 0


def test_the_difference_is_counted_in_both_directions() -> None:
    """The finding is that the flips run one way. A measurement that could only see one
    direction would make that finding vacuous, so the reverse case is counted too."""
    ours = {"A1C": -1.0, "A1D": -5.0, "A1E": -5.0}
    published = {"A1C": -1.0, "A1D": -2.0, "A1E": -5.0}
    result = audit.audit_assay(ours, published)
    assert result["absent_on_our_side_only"] == 1
    assert result["absent_in_published_only"] == 0


def test_a_position_with_no_ranking_of_ours_is_counted_not_compared() -> None:
    """Where the structural factor is zero every score at the position is zero, so the position
    carries no ranking at all on our side and cannot contribute a flip either way."""
    ours = {"A1C": 0.0, "A1D": 0.0, "B2C": -1.0, "B2D": -4.0, "B2E": -4.0}
    published = {"A1C": -1.0, "A1D": -9.0, "B2C": -1.0, "B2D": -4.0, "B2E": -4.0}
    result = audit.audit_assay(ours, published)
    assert result["positions_without_a_ranking"] == 2
    assert result["absent_in_published_only"] == 0


def test_untied_agreement_excludes_the_shared_extreme_block() -> None:
    ours = {f"A1{aa}": -float(i) for i, aa in enumerate("CDEFGH", start=1)}
    ours["A1G"] = ours["A1H"] = min(ours.values())
    published = dict(ours)
    result = audit.audit_assay(ours, published)
    assert result["variants_untied"] == len(ours) - 2
    assert result["agreement_untied"] == 1.0


def test_too_few_shared_variants_is_not_compared() -> None:
    result = audit.audit_assay({"A1C": -1.0}, {"A1C": -1.0, "A1D": -2.0})
    assert result == {"compared": False, "why": "fewer than three variants in common"}


def test_the_flip_threshold_is_stated_above_what_reproducing_assays_show() -> None:
    """D-248 fixes the threshold before the per-assay figures, an order of magnitude above the
    largest share seen among the assays that reproduce the column."""
    assert audit.FLIP_SHARE == 0.05


def test_assay_level_reads_the_interval_not_the_estimate() -> None:
    assert audit._assay_level({"estimate": -0.08, "low": -0.12, "high": -0.04}) == "worse"
    assert audit._assay_level({"estimate": 0.01, "low": 0.005, "high": 0.02}) == "better"
    assert (
        audit._assay_level({"estimate": -0.01, "low": -0.03, "high": 0.01}) == "indistinguishable"
    )
    assert audit._assay_level({}) == "not compared"

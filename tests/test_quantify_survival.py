"""The assembly in `tools/quantify_survival.py` — task A3.2.

The module tests cover the merge rules. These cover the two things the tool adds and that a
reader of the output depends on: which A2 artefacts are consumed and which are deliberately
left out with a reason attached, and that a group with nothing searched prints as withheld
rather than as a survival fraction of zero.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "quantify_survival.py"
_spec = importlib.util.spec_from_file_location("quantify_survival_under_test", _PATH)
quantify_survival = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = quantify_survival
_spec.loader.exec_module(quantify_survival)

from test_quantify import table  # noqa: E402


def test_every_excluded_artefact_carries_a_reason() -> None:
    """An arm left out of the headline with no line saying so reads as an arm nobody ran."""
    for entry in quantify_survival.DETECTORS_ABSENT:
        assert entry["why"].strip()
    for entry in quantify_survival.TABLES_NOT_MERGED:
        assert entry["why"].strip()


def test_the_consumed_prefixes_cover_every_detector_that_produced_detections() -> None:
    consumed = {prefix for prefix, _ in quantify_survival.TABLE_SOURCES}
    absent = {e["task"].lower().replace(".", "-") for e in quantify_survival.DETECTORS_ABSENT}
    assert consumed | absent == {"a2-1", "a2-2", "a2-3", "a2-4", "a2-5"}


def test_build_groups_by_universe_and_reading() -> None:
    tables = [
        ("s3://x/a", table(policy_id="evo1-literal")),
        ("s3://x/b", table(policy_id="evo1-strict")),
        ("s3://x/c", table(policy_id="evo1-literal", registry="rvdb-prot", version="32.0")),
    ]
    doc = quantify_survival.build(tables, seed=11, resamples=200)
    assert len(doc["groups"]) == 3
    assert {u["universe"] for u in doc["universes"]} == {"pfam/38.2", "rvdb-prot/32.0"}
    assert doc["metrics_not_computed_here"][0]["metric"].startswith("M3")


def test_an_unsearched_group_prints_withheld_not_zero() -> None:
    tables = [("s3://x/a", table(components=[("stage2", False)], families=[]))]
    doc = quantify_survival.build(tables, seed=11, resamples=200)
    text = quantify_survival.summarise(doc)
    assert "withheld" in text
    assert "not evidence of absence" in text
    assert "| 0.0000 |" not in text

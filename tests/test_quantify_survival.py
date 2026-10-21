"""The assembly in `tools/quantify_survival.py` — task A3.2.

The module tests cover the merge rules. These cover the two things the tool adds and that a
reader of the output depends on: which A2 artefacts are consumed and which are deliberately
left out with a reason attached, and that a group with nothing searched prints as withheld
rather than as a survival fraction of zero.
"""

from __future__ import annotations

import importlib.util
import json
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


class _FakeStore:
    """A `list_objects_v2` paginator over a fixed set of keys, with a recording downloader."""

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self.downloaded: list[str] = []

    def get_paginator(self, _name: str) -> _FakeStore:
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, object]]:  # noqa: N803
        del Bucket
        return [{"Contents": [{"Key": k} for k in self.keys if k.startswith(Prefix)]}]

    def download_file(self, _bucket: str, key: str, dest: str) -> None:
        self.downloaded.append(key)
        pathlib.Path(dest).write_text(json.dumps(table(policy_id="evo1-literal")))


def test_fetch_tables_skips_the_commit_keyed_twins(tmp_path: pathlib.Path) -> None:
    """D-246. The twins D-216 publishes are copies of tables already merged under their stable
    key. A recursive listing reaches them, and a twin from before a correction would union its
    superseded families back into the headline."""
    store = _FakeStore(
        [
            "corpora/results/a2-1/detections-pfam-evo1-literal-opengenome.json",
            "corpora/results/a2-1/by-commit/deadbeef/detections-pfam-evo1-literal-opengenome.json",
            "corpora/results/a2-1/by-commit/cafe1234/detections-pfam-evo1-literal-opengenome.json",
        ]
    )
    fetched = quantify_survival.fetch_tables(tmp_path, client=store)
    assert [key for key, _ in fetched] == [
        "s3://" + quantify_survival.objectstore.CORPORA_BUCKET
        + "/corpora/results/a2-1/detections-pfam-evo1-literal-opengenome.json"
    ]
    assert not any("by-commit" in key for key in store.downloaded)


def test_fetch_tables_does_not_reach_a_neighbouring_slug(tmp_path: pathlib.Path) -> None:
    """`a2-1` is a prefix of `a2-10`; the listing is anchored with its trailing slash."""
    store = _FakeStore(
        [
            "corpora/results/a2-1/detections-pfam-evo1-literal-opengenome.json",
            "corpora/results/a2-10/detections-pfam-evo1-literal-opengenome.json",
        ]
    )
    fetched = quantify_survival.fetch_tables(tmp_path, client=store)
    assert len(fetched) == 1
    assert "a2-10" not in fetched[0][0]

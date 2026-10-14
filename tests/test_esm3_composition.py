"""Tests for `tools/esm3_composition.py` — task A1.5.

The tool's own arithmetic is `amazebio.esm3`'s and tested there. What is tested here is
the join between what ESM3 states and what a staging run actually produced, because
that join is where an unverified transfer could quietly start reading as a staged
corpus — and the whole point of the ESM3 proxy qualifier is that it must not.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "esm3_composition.py"
_spec = importlib.util.spec_from_file_location("esm3_composition_under_test", _PATH)
composition = importlib.util.module_from_spec(_spec)
sys.modules["esm3_composition_under_test"] = composition
_spec.loader.exec_module(composition)


def manifest(
    path,
    *,
    task="A1.5",
    release="2023_02",
    verified=True,
    outputs=(),
):
    path.write_text(
        json.dumps(
            {
                "task": task,
                "parameters": {"release": release},
                "inputs": [
                    {"url": "https://example/f", "checksum_type": "md5", "verified": verified}
                ],
                "outputs": list(outputs),
            }
        )
    )
    return path


UNIREF_OUTPUTS = [
    {"uri": "s3://b/uniref/2023_02/uniref50.xml.gz", "bytes": 3, "role": "corpus:uniref50"},
    {"uri": "s3://b/uniref/2023_02/uniref90.xml.gz", "bytes": 3, "role": "corpus:uniref90"},
    {"uri": "s3://b/uniref/2023_02/uniref100.xml.gz", "bytes": 3, "role": "corpus:uniref100"},
]
MGNIFY_OUTPUTS = [
    {
        "uri": "s3://b/mgnify/2023_02/mgy_clusters.fa.gz",
        "bytes": 3,
        "role": "staged corpus component",
    }
]


def test_a_verified_uniref_run_records_every_tier_it_staged(tmp_path):
    manifest(tmp_path / "run.json", outputs=UNIREF_OUTPUTS)
    staged = composition.load_staged(tmp_path)

    assert set(staged) == {"UniRef"}
    assert staged["UniRef"]["release"] == "2023_02"
    assert "uniref100" in staged["UniRef"]["granularity"]
    # The reason all three are staged travels with the row, because a later reader
    # otherwise has to go and find out why.
    assert "does not name a tier" in staged["UniRef"]["granularity"]
    assert len(staged["UniRef"]["objects"]) == 3


def test_a_verified_mgnify_run_records_the_granularity_it_chose(tmp_path):
    manifest(tmp_path / "run-mgnify.json", outputs=MGNIFY_OUTPUTS)
    staged = composition.load_staged(tmp_path)

    assert set(staged) == {"MGnify"}
    assert "90%-clustered product" in staged["MGnify"]["granularity"]
    assert "not staged" in staged["MGnify"]["granularity"]


def test_both_passes_are_read_from_their_separate_manifests(tmp_path):
    manifest(tmp_path / "run.json", outputs=UNIREF_OUTPUTS)
    manifest(tmp_path / "run-mgnify.json", outputs=MGNIFY_OUTPUTS)
    assert set(composition.load_staged(tmp_path)) == {"UniRef", "MGnify"}


def test_an_unverified_run_leaves_the_component_unstaged(tmp_path):
    """A transfer whose checksum was never matched is not a staged corpus."""
    manifest(tmp_path / "run.json", verified=False, outputs=UNIREF_OUTPUTS)
    assert composition.load_staged(tmp_path) == {}


def test_a_partial_object_is_not_counted_as_staged(tmp_path):
    partial = [dict(MGNIFY_OUTPUTS[0], partial=True)]
    manifest(tmp_path / "run-mgnify.json", outputs=partial)
    assert composition.load_staged(tmp_path) == {}


def test_another_tasks_manifest_in_the_directory_is_ignored(tmp_path):
    manifest(tmp_path / "run.json", task="A1.3", outputs=UNIREF_OUTPUTS)
    assert composition.load_staged(tmp_path) == {}


def test_unreadable_manifests_do_not_stop_the_others_being_read(tmp_path):
    (tmp_path / "run-broken.json").write_text("{not json")
    manifest(tmp_path / "run-mgnify.json", outputs=MGNIFY_OUTPUTS)
    assert set(composition.load_staged(tmp_path)) == {"MGnify"}


def test_the_report_states_which_components_were_staged(tmp_path):
    manifest(tmp_path / "run.json", outputs=UNIREF_OUTPUTS)
    report = composition.build(composition.load_staged(tmp_path))

    assert report["summary"]["components_staged"] == ["UniRef"]
    rows = {r["component"]: r for r in report["stated_vs_used"]}
    assert rows["UniRef"]["gap_kind"] == "release-exact"
    assert rows["JGI"]["gap_kind"] == "no-proxy-exists"
    assert rows["MGnify"]["gap_kind"] == "obtainable-not-staged"


def test_no_row_carries_a_coverage_share(tmp_path):
    """A share over the staged components would be a fraction of what could be staged,
    not of ESM3's corpus — JGI alone is about a third of its unique training tokens."""
    report = composition.build(composition.load_staged(tmp_path))
    for row in report["stated_vs_used"]:
        assert not [k for k in row if "share" in k or "percent" in k or "fraction" in k]

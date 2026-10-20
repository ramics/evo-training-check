"""A8.1's two-tier report: the comparison neither pass can produce on its own."""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from amazebio import agreement

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "agreement_report", ROOT / "tools" / "agreement_report.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def doc(tier: str, identity: float, **over: object) -> dict:
    counts = agreement.AgreementCounts()
    counts.cells[agreement.CELL_BOTH] = 10
    counts.cells[agreement.CELL_SIMILARITY_ONLY] = 3
    counts.cells[agreement.CELL_NEITHER] = 7
    counts.cells[agreement.CELL_OUT_OF_SCOPE_REMOVED] = 5
    counts.cells[agreement.CELL_OUT_OF_SCOPE] = 100
    counts.members = 125
    counts.loose_only_members = 2
    body = {
        "task": "A8.1",
        "release": "2023_02",
        "tier": tier,
        "identity": identity,
        "bounded": False,
        "counts": counts.to_dict(),
        "rules_not_runnable": [["evo1-literal:keep-one-per-votu", "keep_one_per"]],
        "name_resolution": [
            ["Picornaviridae", "scientific name", "family"],
            ["Reoviridae", "synonym of a order, not a family", "order"],
        ],
        "confound": "measures the predicates and not the deployments",
    }
    body.update(over)
    return body


def write(tmp_path, *docs):  # type: ignore[no-untyped-def]
    paths = []
    for d in docs:
        p = tmp_path / f"agreement-{d['tier']}.json"
        p.write_text(json.dumps(d))
        paths.append(p)
    return paths


def test_the_report_puts_the_two_identities_side_by_side(tmp_path):  # type: ignore[no-untyped-def]
    paths = write(tmp_path, doc("uniref50", 0.50), doc("uniref90", 0.90))
    assert tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"]) == 0
    text = (tmp_path / "agreement.md").read_text()
    # Highest identity first, so the columns read as a sweep downwards.
    assert text.index("| records | 90% | 50% |") > 0
    assert "`out_of_scope_removed`" in text
    assert "not viral, and nothing removes it" in text


def test_a_bounded_pass_is_refused(tmp_path):  # type: ignore[no-untyped-def]
    paths = write(tmp_path, doc("uniref90", 0.90, bounded=True))
    with pytest.raises(SystemExit, match="read a prefix"):
        tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"])


def test_two_passes_of_the_same_tier_are_refused(tmp_path):  # type: ignore[no-untyped-def]
    docs = [doc("uniref90", 0.90), doc("uniref90", 0.90)]
    paths = [tmp_path / "a.json", tmp_path / "b.json"]
    for p, d in zip(paths, docs, strict=True):
        p.write_text(json.dumps(d))
    with pytest.raises(SystemExit, match="double-count"):
        tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"])


def test_mixed_releases_are_refused(tmp_path):  # type: ignore[no-untyped-def]
    paths = write(tmp_path, doc("uniref90", 0.90), doc("uniref50", 0.50, release="2024_01"))
    with pytest.raises(SystemExit, match="different releases"):
        tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"])


def test_the_report_carries_the_names_that_did_not_resolve(tmp_path):  # type: ignore[no-untyped-def]
    paths = write(tmp_path, doc("uniref90", 0.90))
    tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"])
    text = (tmp_path / "agreement.md").read_text()
    assert "**Reoviridae**" in text
    assert "Picornaviridae" not in text.split("## What could not be run")[1]
    assert "2 at 90%" in text


def test_the_report_states_the_confound(tmp_path):  # type: ignore[no-untyped-def]
    paths = write(tmp_path, doc("uniref90", 0.90))
    tool.main([*map(str, paths), "--outdir", str(tmp_path), "--allow-dirty"])
    text = (tmp_path / "agreement.md").read_text()
    assert "measures the predicates and not the deployments" in text
    assert "unpublished" in text

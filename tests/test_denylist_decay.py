"""A9.1's pipeline: the pinned window, and the interval it refuses to hide in a constant."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "denylist_decay", ROOT / "tools" / "denylist_decay.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def test_the_window_is_the_one_the_decision_fixed() -> None:
    assert tool.BASELINE == "2023-04-01"
    assert tool.RELEASES[0] == "2020-01-01"
    assert tool.RELEASES[-1] == "2026-10-01"
    assert len(tool.RELEASES) == 28
    assert tool.BASELINE in tool.RELEASES, "the baseline has to be a point on its own curve"


def test_the_names_come_from_the_committed_specs_not_from_this_tool() -> None:
    named, stops = tool.frozen_names(ROOT / "policies" / "specs")
    assert len(named["family"]) == 19
    assert len(named["order"]) == 12
    assert len(stops) == 8
    assert "Reoviridae" in named["family"]


def write(cache: pathlib.Path, date: str, nodes: dict, names: dict) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cache / f"taxdmp_{date}.zip", "w") as archive:
        archive.writestr(
            "nodes.dmp", "\n".join(f"{t}\t|\t{p}\t|\t{r}\t|" for t, (p, r) in nodes.items())
        )
        archive.writestr(
            "names.dmp",
            "\n".join(f"{t}\t|\t{n}\t|\t\t|\tscientific name\t|" for t, n in names.items()),
        )
        archive.writestr("merged.dmp", "")


BASE_NODES = {1: (1, "no rank"), 10239: (1, "superkingdom"), 100: (10239, "realm")}
BASE_NAMES = {1: "root", 10239: "Viruses", 100: "Riboviria"}


def test_build_runs_over_a_cached_window_without_fetching(tmp_path):  # type: ignore[no-untyped-def]
    cache = tmp_path / "dumps"
    write(cache, "2023-04-01", BASE_NODES, BASE_NAMES)
    later_nodes = {**BASE_NODES, 500: (100, "order")}
    write(cache, "2026-10-01", later_nodes, {**BASE_NAMES, 500: "Newvirales"})
    doc = tool.build(cache, ROOT / "policies" / "specs", releases=("2023-04-01", "2026-10-01"))
    assert [p["date"] for p in doc["releases"]] == ["2023-04-01", "2026-10-01"]
    assert doc["releases"][-1]["new_not_named"] == 1
    assert doc["decision"] == "D-201"
    # Every dump the replay read is digested, which is what makes it replayable at all.
    assert set(doc["digests"]) == {"2023-04-01", "2026-10-01"}
    assert all(len(d) == 64 for d in doc["digests"].values())


def test_the_artefact_names_what_it_did_not_measure(tmp_path):  # type: ignore[no-untyped-def]
    cache = tmp_path / "dumps"
    write(cache, "2023-04-01", BASE_NODES, BASE_NAMES)
    doc = tool.build(cache, ROOT / "policies" / "specs", releases=("2023-04-01",))
    joined = " ".join(doc["not_measured_here"])
    assert "eukaryote-infecting" in joined
    assert "Counts are of taxa" in joined


def test_the_interval_is_reported_at_several_tolerances_with_its_assumptions() -> None:
    points = [
        {"date": "2023-04-01", "new_not_named": 0, "viral_taxa": 1000},
        {"date": "2025-04-01", "new_not_named": 20, "viral_taxa": 1000},
    ]
    iv = tool.intervals(points)
    assert iv["years"] == pytest.approx(2.0)
    assert iv["rate_per_year"] == pytest.approx(0.01)
    assert set(iv["revalidation_years"]) == {f"{t:.3%}" for t in tool.TOLERANCES}
    assert iv["revalidation_years"]["1.000%"] == pytest.approx(1.0)
    assert any("not an instantaneous rate" in a for a in iv["assumptions"])
    assert any("Renames and renumberings are excluded" in a for a in iv["assumptions"])


def test_one_post_baseline_release_yields_no_interval_rather_than_a_guess() -> None:
    iv = tool.intervals([{"date": "2023-04-01", "new_not_named": 0, "viral_taxa": 10}])
    assert iv["rate_per_year"] is None
    assert "fewer than two" in iv["note"]


def test_the_summary_prints_both_curves(tmp_path):  # type: ignore[no-untyped-def]
    cache = tmp_path / "dumps"
    write(cache, "2023-04-01", BASE_NODES, BASE_NAMES)
    write(cache, "2026-10-01", {**BASE_NODES, 500: (100, "order")}, {**BASE_NAMES, 500: "N"})
    doc = tool.build(cache, ROOT / "policies" / "specs", releases=("2023-04-01", "2026-10-01"))
    text = tool.summarise(doc)
    assert "asks the release its own question" in text
    assert "renumbered" in text
    json.dumps(doc)  # the artefact has to be serialisable, which a dataclass field can break

"""Tests for the select-agent seed builder — task A1.8.

The pass this tool drives reads 133.5 G residues on a machine with no shell, so the things
worth testing are the ones that would otherwise fail an hour in or, worse, succeed with a
number nobody can interpret: the digest refusals, the provenance arithmetic, and the
reconciliation's refusal to compare a bounded prefix with a published total.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
TAXDUMP = ROOT / "data" / "taxdmp_2023-04-01.zip"
CAPTURES = ROOT / "policies" / "captures"
MAPPING = ROOT / "policies" / "specs" / "select-agents-2024-06-01.json"

needs_taxonomy = pytest.mark.skipif(not TAXDUMP.exists(), reason="pinned taxonomy dump not staged")


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "select_agent_seeds", ROOT / "tools" / "select_agent_seeds.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


# --- the reading, and the provenance that makes a count interpretable ----------------------


def test_the_reading_resolves_against_the_pinned_captures() -> None:
    taxa, prov = tool.load_reading(CAPTURES, MAPPING, toxin_producers=False, alternatives=False)
    assert prov["list_entries"] == 70
    assert prov["named_taxa"] == len(taxa.named) == 53
    assert prov["list_as_of"] == "2024-06-01"
    assert len(prov["cfr_parts"]) == 3


def test_the_entry_arithmetic_closes() -> None:
    """Naming plus contributing-none must equal the list, or a reader cannot audit the gap.

    It did not, briefly: `len(entries) - len(unresolved)` overstated by one, because the
    heading entry contributes no taxon while not being one of the four kinds `unresolved()`
    reports — its content is the sub-entries beneath it, not something we failed to represent.
    """
    _, prov = tool.load_reading(CAPTURES, MAPPING, toxin_producers=False, alternatives=False)
    assert (
        prov["entries_naming_taxa"] + prov["entries_contributing_no_taxon"]
        == (prov["list_entries"])
    )
    assert sum(prov["no_taxon_by_kind"].values()) == prov["entries_contributing_no_taxon"]
    # Unrepresentable is the stricter subset, and excludes the heading.
    assert prov["entries_unrepresentable"] < prov["entries_contributing_no_taxon"]
    assert prov["no_taxon_by_kind"]["heading"] == 1


def test_the_provenance_pins_everything_a_rerun_needs() -> None:
    """A seed count is not interpretable without the list version and the reading (D-137)."""
    _, prov = tool.load_reading(CAPTURES, MAPPING, toxin_producers=False, alternatives=False)
    assert prov["mapping_sha256"]
    assert prov["taxdump_pin"] == "2023-04-01"
    assert prov["reading"] == {"toxin_producers": False, "alternatives": False}
    for part in prov["cfr_parts"]:
        assert part["sha256"] and part["effective"] and part["as_of"]


def test_the_toxin_reading_is_visible_in_the_provenance() -> None:
    """The switch has to be legible in the artefact, not only in the command line."""
    literal, lit_prov = tool.load_reading(
        CAPTURES, MAPPING, toxin_producers=False, alternatives=False
    )
    producers, prod_prov = tool.load_reading(
        CAPTURES, MAPPING, toxin_producers=True, alternatives=False
    )
    assert prod_prov["reading"]["toxin_producers"] is True
    assert prod_prov["named_taxa"] > lit_prov["named_taxa"]
    assert literal.named < producers.named


# --- the refusals -------------------------------------------------------------------------


def test_a_tampered_capture_is_refused(tmp_path: Path) -> None:
    """The digest is the only thing standing between a result and unknown bytes."""
    for name in {Path(p.capture).name for p in _pins()}:
        (tmp_path / name).write_bytes((CAPTURES / name).read_bytes())
    victim = tmp_path / "cfr-title42-part73-2024-06-01.xml"
    victim.write_bytes(victim.read_bytes() + b"<!-- edited -->")
    with pytest.raises(SystemExit, match="does not match its recorded digest"):
        tool.load_reading(tmp_path, MAPPING, toxin_producers=False, alternatives=False)


def test_a_missing_capture_names_the_file_and_says_why(tmp_path: Path) -> None:
    """This fires on the instance, where the payload is the thing that went wrong."""
    with pytest.raises(SystemExit, match="missing pinned CFR capture"):
        tool.load_reading(tmp_path, MAPPING, toxin_producers=False, alternatives=False)


def test_a_missing_reading_table_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="curated reading table"):
        tool.load_reading(
            CAPTURES, tmp_path / "absent.json", toxin_producers=False, alternatives=False
        )


def _pins() -> Any:
    from amazebio import selectagents

    return selectagents.PINS_2024


# --- the reconciliation -------------------------------------------------------------------


def test_the_reconciliation_names_both_biases() -> None:
    """A bare delta invites reading a shortfall as a reconstruction failure (D-137)."""
    rec = tool.reconcile(150_000)
    assert rec["published_sequences"] == 187_000
    assert rec["rebuilt_sequences"] == 150_000
    assert rec["delta"] == -37_000
    assert rec["known_downward_pressure"] and rec["known_upward_pressure"]
    assert "not expected" in rec["note"]


def test_the_reconciliation_handles_an_overshoot() -> None:
    rec = tool.reconcile(200_000)
    assert rec["delta"] == 13_000
    assert rec["delta_share"] == pytest.approx(13_000 / 187_000)


# --- the pass itself ----------------------------------------------------------------------


def _mini_corpus(path: Path) -> Path:
    """A UniRef-shaped corpus with the three cases the counters distinguish."""

    def entry(cid: str, rep: int, members: list[int], seq: str) -> str:
        body = "".join(
            f'<member><dbReference type="UniProtKB ID" id="M{i}">'
            f'<property type="NCBI taxonomy" value="{t}"/></dbReference></member>'
            for i, t in enumerate(members)
        )
        return (
            f'<entry id="{cid}"><representativeMember>'
            f'<dbReference type="UniProtKB ID" id="R">'
            f'<property type="NCBI taxonomy" value="{rep}"/></dbReference>'
            f'<sequence length="{len(seq)}" checksum="X">{seq}</sequence>'
            f"</representativeMember>{body}</entry>"
        )

    xml = "".join(
        [
            entry("UniRef100_A", 632, [632], "MKVLAAAA"),  # Yersinia pestis: listed
            entry("UniRef100_B", 9606, [9606], "MKVLBBBB"),  # human: not listed
            entry("UniRef100_C", 9606, [9606, 1392], "MKVLCCCC"),  # listed via a member
        ]
    )
    path.write_bytes(gzip.compress(f"<UniRef100>{xml}</UniRef100>".encode()))
    return path


@needs_taxonomy
def test_the_pass_counts_the_three_cases_apart(tmp_path: Path) -> None:
    """Seeded, not seeded, and seeded only through a non-representative member.

    The third is the representative-versus-member gap `amazebio.seeds` documents, and it has
    to be counted rather than assumed away for this arm as much as for the viral one.
    """
    corpus = _mini_corpus(tmp_path / "mini.xml.gz")
    outdir = tmp_path / "out"
    assert (
        tool.main(
            [
                "--taxdump",
                str(TAXDUMP),
                "--source",
                str(corpus),
                "--outdir",
                str(outdir),
                "--workers",
                "1",
                "--allow-dirty",
            ]
        )
        == 0
    )
    payload = json.loads((outdir / "seed-counts-2023_02-uniref100.json").read_text())
    counts = payload["counts"]
    assert counts["clusters"] == 3
    assert counts["seeded"] == 2
    assert counts["representative_not_seeded"] == 1
    assert counts["mixed"] == 1
    fasta = (outdir / "select-agent-seeds-2023_02-uniref100.faa").read_text()
    assert "UniRef100_A" in fasta and "UniRef100_C" in fasta
    assert "UniRef100_B" not in fasta


@needs_taxonomy
def test_the_artefact_carries_the_reading_not_just_the_count(tmp_path: Path) -> None:
    corpus = _mini_corpus(tmp_path / "mini.xml.gz")
    outdir = tmp_path / "out"
    tool.main(
        [
            "--taxdump",
            str(TAXDUMP),
            "--source",
            str(corpus),
            "--outdir",
            str(outdir),
            "--workers",
            "1",
            "--allow-dirty",
        ]
    )
    payload = json.loads((outdir / "seed-counts-2023_02-uniref100.json").read_text())
    prov = payload["list_provenance"]
    assert prov["mapping_sha256"] and prov["cfr_parts"]
    assert payload["reconciliation"]["published_sequences"] == 187_000


@needs_taxonomy
def test_a_bounded_run_withholds_the_reconciliation(tmp_path: Path) -> None:
    """A prefix compared against a published total reads as a 100% shortfall.

    UniRef is ordered by accession, so a bounded read is not a sample of the tier and its
    count is not a quantity — publishing a delta against it would be the kind of number that
    looks like a finding.
    """
    corpus = _mini_corpus(tmp_path / "mini.xml.gz")
    outdir = tmp_path / "out"
    tool.main(
        [
            "--taxdump",
            str(TAXDUMP),
            "--source",
            str(corpus),
            "--outdir",
            str(outdir),
            "--workers",
            "1",
            "--limit-bytes",
            "1",
            "--allow-dirty",
        ]
    )
    payload = json.loads((outdir / "seed-counts-2023_02-uniref100.json").read_text())
    assert payload["bounded"] is True
    assert payload["reconciliation"] is None
    manifest = json.loads((outdir / "run-select-agent-seeds-uniref100.json").read_text())
    assert any("BOUNDED RUN" in note for note in manifest.get("notes", []))


@needs_taxonomy
def test_check_inputs_does_not_touch_the_corpus(tmp_path: Path) -> None:
    """It exists to fail in a second on the instance rather than an hour in."""
    assert tool.main(["--taxdump", str(TAXDUMP), "--check-inputs"]) == 0
    assert not list(tmp_path.glob("*.faa"))

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


@needs_taxonomy
def test_the_artefact_records_real_throughput(tmp_path: Path) -> None:
    """A zero here is what a broken heartbeat looks like after the fact.

    The first version asked the stream for `tell()` with a zero fallback. `GunzipStream` has
    no `tell` — it exposes `read_bytes` — so every progress line printed `0.0 GB` for an hour
    and the artefact recorded no throughput at all. Asserting the fields exist would have
    passed; asserting they are non-zero is what catches it.
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
            "--allow-dirty",
        ]
    )
    payload = json.loads((outdir / "seed-counts-2023_02-uniref100.json").read_text())
    assert payload["decompressed_bytes_read"] > 0
    assert payload["compressed_bytes_read"] > 0
    assert payload["decompressed_bytes_per_second"]


def test_the_heartbeat_counts_what_it_yields() -> None:
    """The progress count comes from the chunks, not from a method the stream may not have."""

    class Stream:
        """Deliberately has no `tell`, exactly like GunzipStream."""

        def __init__(self) -> None:
            self.left = 3

        def read(self, size: int) -> bytes:
            if self.left <= 0:
                return b""
            self.left -= 1
            return b"x" * size

    assert sum(len(c) for c in tool._chunks(Stream(), 0, 0)) == 3 * tool.CHUNK


def test_the_byte_limit_actually_stops_the_read() -> None:
    """The zero fallback silently disabled this, and a one-chunk fixture hid it."""

    class Endless:
        def read(self, size: int) -> bytes:
            return b"x" * size

    produced = sum(len(c) for c in tool._chunks(Endless(), 100, 0))
    assert produced == 100


def test_the_heartbeat_overwrites_one_key_rather_than_accumulating() -> None:
    """The corpus bucket has no DeleteObject, so a key per beat is permanent litter.

    A1.3 left four objects behind that cannot be removed. Overwriting a single key destroys
    only the previous beat, which is all a heartbeat is for.
    """
    import argparse

    puts: list[str] = []

    class FakeS3:
        def put_object(self, **kw: object) -> None:
            puts.append(str(kw["Key"]))

    beat = tool._heartbeat(
        FakeS3(), "bucket", "corpora", argparse.Namespace(tier="uniref100", release="2023_02")
    )
    for n in range(5):
        beat({"clusters": n})
    assert len(set(puts)) == 1, f"heartbeat wrote {len(set(puts))} distinct keys"
    assert "a1-8" in puts[0]


def test_a_failing_heartbeat_does_not_take_the_pass_down() -> None:
    """Losing the diagnosis is bad; losing an hour of corpus reading is worse."""
    import argparse

    class Broken:
        def put_object(self, **kw: object) -> None:
            raise RuntimeError("no")

    beat = tool._heartbeat(
        Broken(), "bucket", "corpora", argparse.Namespace(tier="uniref100", release="2023_02")
    )
    beat({"clusters": 1})  # must not raise


def test_a_local_run_needs_no_heartbeat_client() -> None:
    import argparse

    beat = tool._heartbeat(None, "", "", argparse.Namespace(tier="uniref100", release="2023_02"))
    beat({"clusters": 1})


# --- Per-entry attribution and the manifest's own upload (D-146) -------------------------


@needs_taxonomy
def test_the_pass_attributes_seeded_clusters_to_the_entries_that_claimed_them(
    tmp_path: Path,
) -> None:
    """A pooled count cannot be decomposed afterwards, which is what D-146 ran into."""
    corpus = _mini_corpus(tmp_path / "mini.xml.gz")
    outdir = tmp_path / "out"
    tool.main(
        # fmt: off
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
        # fmt: on
    )
    payload = json.loads((outdir / "seed-counts-2023_02-uniref100.json").read_text())
    exclusive = payload["seeded_by_entry"]["exclusive"]
    named = " ".join(exclusive).lower()
    assert "yersinia pestis" in named
    assert "bacillus anthracis" in named
    assert sum(exclusive.values()) == payload["counts"]["seeded"]


@needs_taxonomy
def test_the_expansion_is_recorded_per_entry_even_where_no_cluster_carries_it() -> None:
    """An entry naming 100,000 taxa and seeding nothing is not the same as naming none."""
    _, prov = tool.load_reading(CAPTURES, MAPPING, toxin_producers=False, alternatives=False)
    assert "expanded_taxa_by_entry" not in prov, "load_reading's contract is unchanged"
    from amazebio.seeds import Taxonomy

    _, counts = tool.load_attribution(
        CAPTURES,
        MAPPING,
        Taxonomy.from_taxdump_zip(TAXDUMP),
        toxin_producers=False,
        alternatives=False,
    )
    assert sum(counts.values()) >= 114_000
    assert max(counts.values()) / sum(counts.values()) > 0.95


def test_the_largest_contributor_is_named_from_the_measurement_not_the_source() -> None:
    """A re-pin that changes which entry dominates must report the new one."""
    from amazebio.seeds import EntryCounts

    counts = EntryCounts()
    for _ in range(90):
        counts.observe(("flu",))
    for _ in range(10):
        counts.observe(("anthrax",))
    top = tool._largest_contributor(100, counts)
    assert top is not None
    assert top["entry"] == "flu"
    assert top["exclusive_clusters"] == 90
    assert top["seeded_without_it"] == 10
    assert top["share_of_seed_set"] == pytest.approx(0.9)


def test_a_shared_cluster_is_not_counted_as_removable_with_one_entry() -> None:
    """`seeded_without_it` must not promise a reduction another entry would keep."""
    from amazebio.seeds import EntryCounts

    counts = EntryCounts()
    counts.observe(("flu",))
    counts.observe(("flu", "newcastle"))
    top = tool._largest_contributor(2, counts)
    assert top is not None
    assert top["exclusive_clusters"] == 1
    assert top["seeded_without_it"] == 1


def test_no_contributor_is_reported_when_nothing_was_attributed() -> None:
    from amazebio.seeds import EntryCounts

    assert tool._largest_contributor(0, EntryCounts()) is None


@needs_taxonomy
def test_the_run_manifest_is_uploaded_with_the_results(tmp_path: Path) -> None:
    """The first pass staged its results and left its provenance on a terminated instance.

    `repro.run` writes the manifest when its block exits, so an upload inside that block has
    no file to send. There is no shell on the instance and nobody can fetch it afterwards, so
    a manifest that does not leave this way does not leave at all — and a result that cannot
    be traced to the code that produced it is not citable.
    """
    corpus = _mini_corpus(tmp_path / "mini.xml.gz")
    outdir = tmp_path / "out"
    uploaded: dict[str, bytes] = {}

    class FakeS3:
        def put_object(self, **kw: Any) -> None:
            uploaded[str(kw["Key"])] = bytes(kw["Body"])

    import argparse

    args = argparse.Namespace(
        release="2023_02",
        tier="uniref100",
        taxdump=TAXDUMP,
        captures=CAPTURES,
        mapping=MAPPING,
        source=str(corpus),
        outdir=outdir,
        limit_bytes=0,
        workers=1,
        batch_bytes=1 << 20,
        upload_results=True,
        allow_dirty=True,
        code_commit="deadbeef",
        progress_seconds=1e9,
        heartbeat_seconds=1e9,
        toxin_producers=False,
        alternatives=False,
    )
    taxa, provenance = tool.load_reading(
        CAPTURES, MAPPING, toxin_producers=False, alternatives=False
    )
    from amazebio.seeds import Taxonomy

    taxonomy = Taxonomy.from_taxdump_zip(TAXDUMP)
    attribution, _ = tool.load_attribution(
        CAPTURES, MAPPING, taxonomy, toxin_producers=False, alternatives=False
    )
    assert (
        tool._execute(
            args,
            FakeS3(),
            "bucket",
            "corpora",
            taxa.expand(taxonomy),
            provenance,
            attribution,
        )
        == 0
    )
    manifest_key = "corpora/results/a1-8/run-select-agent-seeds-uniref100.json"
    assert manifest_key in uploaded, sorted(uploaded)
    manifest = json.loads(uploaded[manifest_key])
    assert manifest["parameters"]["code_commit"] == "deadbeef"
    assert manifest["outputs"], "a manifest with no outputs traces nothing"

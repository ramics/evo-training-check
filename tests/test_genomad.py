"""Tests for reading geNomad's taxonomy output, and for the version provenance.

The parser tests are mostly about one distinction, because getting it wrong inverts A4.2's
finding: a **truncated** lineage (the tool stopped at the rank its markers supported) and a
**wrong** lineage (the tool named a family, confidently, and named the wrong one) are different
errors with different consequences, and the second is the part A4.1's corpus-side ceiling could
not see. A parser that read `unclassified Caudoviricetes` as a taxon name, or that mis-ranked a
short lineage by position, would report under-assignment as misassignment.

`test_installed_version_does_not_trust_the_cli` is here because the real environment misreports:
geNomad 1.1.0 calls `click.version_option()` with no package name and a modern click resolves
`rich-click` instead, so `genomad --version` prints `1.9.8`. A manifest built from that records
fiction (D-085).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amazebio import genomad

HEADER = "seq_name\tn_genes_with_taxonomy\tagreement\ttaxid\tlineage"
HERPES = (
    "Viruses;Duplodnaviria;Heunggongvirae;Peploviricota;Herviviricetes;Herpesvirales;Herpesviridae"
)
CORONA = "Viruses;Riboviria;Orthornavirae;Pisuviricota;Pisoniviricetes;Nidovirales;Coronaviridae"


# --------------------------------------------------------------------------------------
# Lineage parsing
# --------------------------------------------------------------------------------------


def test_full_lineage_fills_every_rank() -> None:
    lineage, anomalies = genomad.parse_lineage(HERPES)
    assert lineage == {
        "realm": "Duplodnaviria",
        "kingdom": "Heunggongvirae",
        "phylum": "Peploviricota",
        "class": "Herviviricetes",
        "order": "Herpesvirales",
        "family": "Herpesviridae",
    }
    assert anomalies == ()


def test_truncated_lineage_is_well_formed_and_fills_only_what_it_names() -> None:
    """The single most important case: this is the escape route the benchmark counts."""
    lineage, anomalies = genomad.parse_lineage("Viruses;Riboviria;Orthornavirae")
    assert lineage == {"realm": "Riboviria", "kingdom": "Orthornavirae"}
    assert "family" not in lineage
    assert anomalies == ()


def test_lineage_to_class_only_has_no_order_or_family() -> None:
    raw = "Viruses;Duplodnaviria;Heunggongvirae;Uroviricota;Caudoviricetes"
    lineage, _ = genomad.parse_lineage(raw)
    assert lineage["class"] == "Caudoviricetes"
    assert "order" not in lineage
    assert "family" not in lineage


def test_unclassified_placeholder_fills_nothing() -> None:
    """Reading the placeholder as a taxon would turn an unlabelled record into a wrong one."""
    raw = (
        "Viruses;Duplodnaviria;Heunggongvirae;Uroviricota;Caudoviricetes;"
        "unclassified Caudoviricetes"
    )
    lineage, anomalies = genomad.parse_lineage(raw)
    assert lineage["class"] == "Caudoviricetes"
    assert "order" not in lineage
    # The placeholder is skipped rather than flagged: it is geNomad working as documented.
    assert anomalies == ()


def test_empty_interior_field_is_skipped_not_shifted() -> None:
    raw = "Viruses;Riboviria;;Pisuviricota"
    lineage, _ = genomad.parse_lineage(raw)
    assert lineage == {"realm": "Riboviria", "phylum": "Pisuviricota"}


def test_suffix_mismatch_is_recorded_rather_than_resolved() -> None:
    """A name at the wrong position means geNomad or our reading is wrong; keep the evidence."""
    raw = "Viruses;Duplodnaviria;Heunggongvirae;Peploviricota;Herviviricetes;Herpesviridae"
    lineage, anomalies = genomad.parse_lineage(raw)
    # Still read positionally, because that is the format's contract...
    assert lineage["order"] == "Herpesviridae"
    # ...but the disagreement is on the record.
    assert any("virales" in a for a in anomalies)


def test_non_viruses_head_is_recorded() -> None:
    lineage, anomalies = genomad.parse_lineage("Bacteria;Pseudomonadota")
    assert any("does not begin with 'Viruses'" in a for a in anomalies)
    assert lineage == {}  # Pseudomonadota lacks a realm suffix, so nothing is claimed
    assert "realm" not in lineage


def test_overlong_lineage_is_recorded_and_truncated_to_the_ladder() -> None:
    raw = HERPES + ";Simplexvirus;Human alphaherpesvirus 1"
    lineage, anomalies = genomad.parse_lineage(raw)
    assert lineage["family"] == "Herpesviridae"
    assert any("ranks below domain" in a for a in anomalies)


def test_empty_lineage() -> None:
    assert genomad.parse_lineage("") == ({}, ())
    assert genomad.parse_lineage("   ") == ({}, ())


def test_domain_only_lineage_fills_nothing() -> None:
    assert genomad.parse_lineage("Viruses") == ({}, ())


# --------------------------------------------------------------------------------------
# The taxonomy file
# --------------------------------------------------------------------------------------


def _write(tmp_path: Path, rows: list[str], header: str = HEADER) -> Path:
    path = tmp_path / "x_taxonomy.tsv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n")
    return path


def test_read_taxonomy_parses_rows(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [f"NC_001806.2\t59\t1.0000\t8973\t{HERPES}", f"NC_045512.2\t6\t1.0000\t2272\t{CORONA}"],
    )
    calls = genomad.read_taxonomy(path)
    assert set(calls) == {"NC_001806.2", "NC_045512.2"}
    assert calls["NC_001806.2"].lineage["family"] == "Herpesviridae"
    assert calls["NC_001806.2"].genes_with_taxonomy == 59
    assert calls["NC_045512.2"].agreement == pytest.approx(1.0)


def test_a_sequence_with_no_row_is_simply_absent(tmp_path: Path) -> None:
    """Absence is the result, not a gap in it.

    `genomad annotate` writes a row only for a sequence with at least one gene carrying marker
    taxonomy. The pilot behind D-087 produced four rows for five inputs and the missing one was
    an influenza A segment — a denylisted family escaping by having nothing said about it.
    """
    path = _write(tmp_path, [f"NC_001806.2\t59\t1.0000\t8973\t{HERPES}"])
    calls = genomad.read_taxonomy(path)
    assert "NC_002016.1" not in calls
    assert calls.get("NC_002016.1") is None


def test_empty_file_reads_as_no_calls(tmp_path: Path) -> None:
    path = tmp_path / "empty_taxonomy.tsv"
    path.write_text("")
    assert genomad.read_taxonomy(path) == {}


def test_header_only_file_reads_as_no_calls(tmp_path: Path) -> None:
    path = tmp_path / "h_taxonomy.tsv"
    path.write_text(HEADER + "\n")
    assert genomad.read_taxonomy(path) == {}


def test_unexpected_header_is_refused(tmp_path: Path) -> None:
    """A changed output format must stop the pass, not be read positionally anyway."""
    path = _write(tmp_path, ["a\t1\t1.0\t1\tViruses"], header="seq\tgenes\tagree\ttax\tlin")
    with pytest.raises(ValueError, match="unexpected taxonomy header"):
        genomad.read_taxonomy(path)


def test_short_row_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, ["NC_001806.2\t59\t1.0"])
    with pytest.raises(ValueError, match="short taxonomy row"):
        genomad.read_taxonomy(path)


def test_unparseable_numbers_do_not_abort_the_row(tmp_path: Path) -> None:
    path = _write(tmp_path, [f"NC_001806.2\tNA\tNA\t8973\t{HERPES}"])
    call = genomad.read_taxonomy(path)["NC_001806.2"]
    assert call.genes_with_taxonomy == 0
    assert call.agreement is None
    assert call.lineage["family"] == "Herpesviridae"


def test_assigned_to_names_the_finest_filled_rank(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            f"full\t10\t1.0\t1\t{HERPES}",
            "short\t2\t1.0\t2\tViruses;Riboviria;Orthornavirae",
            "none\t0\t1.0\t3\tViruses",
        ],
    )
    calls = genomad.read_taxonomy(path)
    assert calls["full"].assigned_to == "family"
    assert calls["short"].assigned_to == "kingdom"
    assert calls["none"].assigned_to is None


def test_anomalies_travel_with_the_call(tmp_path: Path) -> None:
    raw = "Viruses;Duplodnaviria;Heunggongvirae;Peploviricota;Herviviricetes;Herpesviridae"
    path = _write(tmp_path, [f"odd\t5\t1.0\t1\t{raw}"])
    assert genomad.read_taxonomy(path)["odd"].anomalies


# --------------------------------------------------------------------------------------
# Version provenance
# --------------------------------------------------------------------------------------


def test_installed_version_does_not_trust_the_cli(tmp_path: Path) -> None:
    """Read from the distribution's metadata, which is the only place that is truthful here."""
    site = tmp_path / "lib" / "python3.10" / "site-packages"
    site.mkdir(parents=True)
    (site / "genomad-1.1.0.dist-info").mkdir()
    assert genomad.installed_version(tmp_path) == "1.1.0"


def test_installed_version_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no genomad dist-info"):
        genomad.installed_version(tmp_path)


def test_pin_is_the_contemporaneous_pairing() -> None:
    """The pairing is the publisher's own: package 1.1 maps to marker database v1.1."""
    assert genomad.PIN.version == "1.1.0"
    assert genomad.PIN.database_version == "1.1"
    assert len(genomad.PIN.database_sha256) == 64
    assert genomad.PIN.mmseqs2.startswith("13.")


def test_version_evidence_states_that_the_publisher_states_nothing() -> None:
    """The artefact must carry the absence as a fact, not as a missing field."""
    evidence = genomad.VERSION_EVIDENCE
    assert evidence["stated_by_publisher"] is None
    assert evidence["bound"]["newest_possible"] == "1.1.0"
    sources = {entry["source"] for entry in evidence["sources_checked"]}
    # The unretrieved paper is listed, so the claim's scope is visible rather than implied.
    assert any("gkac1037" in s for s in sources)
    assert any("release note" in s for s in sources)


def test_scope_note_names_the_structural_zero() -> None:
    """`not_viral` is zero by construction in this arm, and a reader must not read it as data."""
    assert "not_viral" in genomad.SCOPE_NOTE
    assert "annotate" in genomad.SCOPE_NOTE


def test_lineage_ranks_are_the_ictv_ladder_below_domain() -> None:
    assert genomad.LINEAGE_RANKS == ("realm", "kingdom", "phylum", "class", "order", "family")

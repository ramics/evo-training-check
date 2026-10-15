"""Tests for the VMR ingest.

Two of these tests exist because of specific ways a hand-rolled xlsx reader goes wrong
quietly, and both would corrupt exactly the rows whose lineage is incomplete — which is to
say, the rows a benchmark of under-assignment cares most about. `test_blank_cell_does_not_
shift_later_ranks` injects the failure that positional reading would cause, and
`test_shared_string_runs_are_joined` the one that reading only the first `<t>` would.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from amazebio import ictv

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

HEADINGS = [
    "Sort",
    "Realm",
    "Subrealm",
    "Kingdom",
    "Subkingdom",
    "Phylum",
    "Subphylum",
    "Class",
    "Subclass",
    "Order",
    "Suborder",
    "Family",
    "Subfamily",
    "Genus",
    "Subgenus",
    "Species",
    "Exemplar or additional isolate",
    "Virus name(s)",
    "Virus name abbreviation(s)",
    "Virus isolate designation",
    "Virus GENBANK accession",
    "Genome coverage",
    "Genome composition",
    "Host source",
]


def _letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _workbook(
    rows: list[dict[str, str]],
    *,
    runs: dict[str, list[str]] | None = None,
    headings: list[str] | None = None,
) -> bytes:
    """Build a minimal one-sheet xlsx carrying `rows` keyed by heading.

    `runs` lets a test request that a particular string be stored as several `<t>` runs, the
    way a spreadsheet editor stores partially-styled text.
    """
    runs = runs or {}
    columns = headings if headings is not None else HEADINGS
    strings: list[str] = []
    index_of: dict[str, int] = {}

    def intern(text: str) -> int:
        if text not in index_of:
            index_of[text] = len(strings)
            strings.append(text)
        return index_of[text]

    body = []
    header_cells = []
    for position, heading in enumerate(columns):
        header_cells.append(f'<c r="{_letter(position)}1" t="s"><v>{intern(heading)}</v></c>')
    body.append(f'<row r="1">{"".join(header_cells)}</row>')

    for number, row in enumerate(rows, start=2):
        cells = []
        for position, heading in enumerate(columns):
            value = row.get(heading, "")
            if value == "":
                # The hazard under test: a blank cell is omitted entirely, not emitted empty.
                continue
            cells.append(f'<c r="{_letter(position)}{number}" t="s"><v>{intern(value)}</v></c>')
        body.append(f'<row r="{number}">{"".join(cells)}</row>')

    si_parts = []
    for text in strings:
        if text in runs:
            inner = "".join(f"<t>{part}</t>" for part in runs[text])
            si_parts.append(f"<si>{inner}</si>")
        else:
            si_parts.append(f"<si><t>{text}</t></si>")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f"<workbook {NS} {RNS}><sheets>"
            f'<sheet name="VMRb37" sheetId="1" r:id="rId9"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId9" Target="worksheets/sheet7.xml"/></Relationships>',
        )
        archive.writestr("xl/sharedStrings.xml", f"<sst {NS}>{''.join(si_parts)}</sst>")
        archive.writestr(
            "xl/worksheets/sheet7.xml",
            f"<worksheet {NS}><sheetData>{''.join(body)}</sheetData></worksheet>",
        )
    return buffer.getvalue()


def _write(tmp_path: Path, rows: list[dict[str, str]], **kwargs: object) -> Path:
    path = tmp_path / "vmr.xlsx"
    path.write_bytes(_workbook(rows, **kwargs))  # type: ignore[arg-type]
    return path


# --------------------------------------------------------------------------------------
# Accessions
# --------------------------------------------------------------------------------------


def test_plain_accession() -> None:
    assert ictv.parse_accessions("DQ665917") == ((None, "DQ665917"),)


def test_versioned_and_wgs_accessions() -> None:
    assert ictv.parse_accessions("NC_001806.2") == ((None, "NC_001806.2"),)
    # The WGS contig form has a six-letter prefix; a pattern cut to two letters drops it.
    assert ictv.parse_accessions("JAEILC010000038") == ((None, "JAEILC010000038"),)


def test_labelled_segments_keep_their_labels() -> None:
    parsed = ictv.parse_accessions("DNA-C: EF546812; DNA-M: EF546811")
    assert parsed == (("DNA-C", "EF546812"), ("DNA-M", "EF546811"))


def test_segment_label_is_not_mistaken_for_an_accession() -> None:
    # `DNA-U3` is alphanumeric and would match a loose accession pattern.
    parsed = ictv.parse_accessions("DNA-U3: EF546809")
    assert parsed == (("DNA-U3", "EF546809"),)


def test_unlabelled_multi_segment() -> None:
    parsed = ictv.parse_accessions("HM246720; HM246721; HM246722")
    assert [a for _, a in parsed] == ["HM246720", "HM246721", "HM246722"]
    assert {label for label, _ in parsed} == {None}


def test_missing_whitespace_after_label() -> None:
    # Seen in the real VMR: `DNA-U2:MK039135` with no space.
    assert ictv.parse_accessions("DNA-U2:MK039135") == (("DNA-U2", "MK039135"),)


def test_empty_accession_is_empty_not_an_error() -> None:
    assert ictv.parse_accessions("") == ()
    assert ictv.parse_accessions("   ") == ()


def test_unparseable_token_is_kept_as_an_anomaly() -> None:
    """Not discarded: a silently shorter evaluation set is the failure to avoid."""
    parsed = ictv.parse_accessions("not-an-accession")
    assert parsed == (("?", "not-an-accession"),)


# --------------------------------------------------------------------------------------
# The workbook
# --------------------------------------------------------------------------------------


def _row(**kwargs: str) -> dict[str, str]:
    base = {
        "Realm": "Riboviria",
        "Order": "Picornavirales",
        "Family": "Picornaviridae",
        "Species": "Enterovirus A",
        "Exemplar or additional isolate": "E",
        "Virus GENBANK accession": "NC_001612",
        "Genome coverage": "Complete genome",
        "Host source": "vertebrates",
    }
    base.update(kwargs)
    return base


def test_reads_lineage_and_accession(tmp_path: Path) -> None:
    table = ictv.read_vmr(_write(tmp_path, [_row()]))
    assert len(table.exemplars) == 1
    item = table.exemplars[0]
    assert item.species == "Enterovirus A"
    assert item.rank("family") == "Picornaviridae"
    assert item.rank("order") == "Picornavirales"
    assert item.accessions == ((None, "NC_001612"),)
    assert item.complete is True


def test_blank_cell_does_not_shift_later_ranks(tmp_path: Path) -> None:
    """The failure positional reading would cause, injected deliberately.

    This row leaves Subrealm, Subkingdom, Subphylum, Subclass and Suborder blank, so the
    sheet omits those cells. Read by position, `Family` would pick up whatever cell happens
    to sit fifth from the end — and the lineage of a partially-ranked virus is exactly what
    this benchmark keys on.
    """
    row = _row(Realm="Monodnaviria", Order="", Family="Geminiviridae", Species="Maize streak virus")
    table = ictv.read_vmr(_write(tmp_path, [row]))
    item = table.exemplars[0]
    assert item.rank("family") == "Geminiviridae"
    assert item.rank("realm") == "Monodnaviria"
    assert item.rank("order") == ""
    assert "suborder" not in item.lineage


def test_shared_string_runs_are_joined(tmp_path: Path) -> None:
    """A styled taxon name is stored as several runs; reading one truncates it."""
    row = _row(Family="Orthomyxoviridae")
    path = _write(tmp_path, [row], runs={"Orthomyxoviridae": ["Ortho", "myxo", "viridae"]})
    assert ictv.read_vmr(path).exemplars[0].rank("family") == "Orthomyxoviridae"


def test_sheet_is_resolved_through_relationships(tmp_path: Path) -> None:
    """The fixture's data sheet is `sheet7.xml`, not `sheet1.xml`, on purpose."""
    assert ictv.read_vmr(_write(tmp_path, [_row()])).exemplars


def test_additional_isolates_are_excluded_by_default(tmp_path: Path) -> None:
    rows = [_row(), _row(Species="Enterovirus B", **{"Exemplar or additional isolate": "A"})]
    table = ictv.read_vmr(_write(tmp_path, rows))
    assert len(table.exemplars) == 1
    assert table.all_rows == 2
    assert table.exemplar_rows == 1


def test_additional_isolates_can_be_included(tmp_path: Path) -> None:
    rows = [_row(), _row(Species="Enterovirus B", **{"Exemplar or additional isolate": "A"})]
    table = ictv.read_vmr(_write(tmp_path, rows), exemplars_only=False)
    assert len(table.exemplars) == 2
    assert [e.is_exemplar for e in table.exemplars] == [True, False]


def test_rows_without_accession_are_counted_not_dropped(tmp_path: Path) -> None:
    rows = [_row(), _row(Species="Unsequenced virus", **{"Virus GENBANK accession": ""})]
    table = ictv.read_vmr(_write(tmp_path, rows))
    assert table.without_accession == 1
    assert len(table.exemplars) == 2  # kept, so the artefact can report the count


def test_missing_column_is_refused(tmp_path: Path) -> None:
    renamed = ["Familie" if h == "Family" else h for h in HEADINGS]
    path = tmp_path / "broken.xlsx"
    path.write_bytes(_workbook([_row()], headings=renamed))
    with pytest.raises(ValueError, match="missing expected column"):
        ictv.read_vmr(path)


def test_coverage_wordings_both_count_as_complete(tmp_path: Path) -> None:
    rows = [
        _row(**{"Genome coverage": "Complete genome"}),
        _row(Species="B", **{"Genome coverage": "Complete coding genome"}),
        _row(Species="C", **{"Genome coverage": "Partial genome"}),
        # The real VMR carries this one lower-cased on five rows.
        _row(Species="D", **{"Genome coverage": "partial genome"}),
    ]
    table = ictv.read_vmr(_write(tmp_path, rows))
    assert [e.complete for e in table.exemplars] == [True, True, False, False]


def test_segmented_flag(tmp_path: Path) -> None:
    rows = [
        _row(**{"Virus GENBANK accession": "A: EU623082; B: EU623083"}),
        _row(Species="One segment"),
    ]
    table = ictv.read_vmr(_write(tmp_path, rows))
    assert [e.segmented for e in table.exemplars] == [True, False]


def test_lineage_rank_rejects_a_non_ictv_rank(tmp_path: Path) -> None:
    item = ictv.read_vmr(_write(tmp_path, [_row()])).exemplars[0]
    with pytest.raises(KeyError, match="not an ICTV rank"):
        ictv.lineage_rank(item, "strain")


def test_summarise_counts_sequences_not_rows(tmp_path: Path) -> None:
    rows = [
        _row(**{"Virus GENBANK accession": "A: EU623082; B: EU623083"}),
        _row(Species="Single"),
    ]
    summary = ictv.summarise(ictv.read_vmr(_write(tmp_path, rows)))
    assert summary["exemplars_read"] == 2
    assert summary["sequences"] == 3
    assert summary["segmented"] == 1


def test_by_rank_groups_and_skips_blanks(tmp_path: Path) -> None:
    rows = [_row(), _row(Species="B"), _row(Species="C", Family="")]
    table = ictv.read_vmr(_write(tmp_path, rows))
    grouped = table.by_rank("family")
    assert sorted(grouped) == ["Picornaviridae"]
    assert len(grouped["Picornaviridae"]) == 2


# --------------------------------------------------------------------------------------
# The pin
# --------------------------------------------------------------------------------------


def test_benchmark_release_is_pinned_and_contemporaneous() -> None:
    """The release A4.2 benchmarks against must predate the corpus it is reasoning about.

    A VMR published after IMG/VR v4 would fold taxonomic revision — which is A9.1's
    subject — into this task's measured error, so the pin being earlier than 2022-09-20 is
    a correctness property, not a bookkeeping detail.
    """
    rel = ictv.release(ictv.BENCHMARK_RELEASE)
    assert rel.msl == "MSL37"
    assert rel.published < "2022-09-20"
    assert len(rel.sha256) == 64
    assert rel.url.endswith(rel.filename)


def test_unknown_release_is_refused() -> None:
    with pytest.raises(KeyError, match="no pinned VMR release"):
        ictv.release("MSL99")

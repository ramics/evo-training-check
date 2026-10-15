"""ICTV's Virus Metadata Resource — the ground truth A4.2 benchmarks a tool against.

A taxonomy-based filter can only remove what a taxonomy assignment tool has labelled, so
the filter inherits that tool's errors (DESIGN.md §A4). Measuring those errors needs a
labelled set whose labels do not come from the tool under test, and for viral taxonomy there
is exactly one source that qualifies: the **International Committee on Taxonomy of Viruses**,
which does not predict family membership but *defines* it. Its Virus Metadata Resource (VMR)
publishes, per species, the ratified lineage and the GenBank accession of the isolate chosen
to exemplify it. That pairing — a lineage that is true by construction and a sequence that
can be handed to a classifier — is the whole reason this module exists.

Two things about the VMR shape the benchmark and are worth stating before the code.

**The exemplar flag is the selection criterion, not a quality score.** Each species names one
"exemplar" isolate plus any number of additional isolates. The exemplar is the isolate the
ICTV's own species description is written against, so it is the isolate whose family
assignment is least arguable. Taking only exemplars also makes the set one row per species,
which matters for the error rate: a family with 400 sequenced isolates and one with 3 would
otherwise weight the pooled figure by how fashionable a virus is.

**The accession field is not one accession.** Segmented viruses — which include five of the
nineteen families Evo's denylist names — list one accession per segment, sometimes labelled
(``DNA-C: EF546812; DNA-M: EF546811``) and sometimes not (``HM246720; HM246721``). That is not
a formatting nuisance to flatten away. A filter acts on one record at a time, and a
metagenomic assembly yields segments as separate contigs, so the unit of evaluation has to be
the sequence, not the species. :func:`parse_accessions` therefore keeps every segment and its
label, and the benchmark scores each one as its own record while remembering which species it
came from.

The VMR is published only as an Excel workbook. Rather than take a dependency to read four
columns out of it, :func:`read_vmr` reads the format directly: an ``.xlsx`` is a zip of XML,
and the two parts that matter are the shared-string table and the first worksheet. See
:func:`_cell_text` for the one subtlety that makes a hand-rolled reader safe here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "BENCHMARK_RELEASE",
    "RANKS",
    "RELEASES",
    "Exemplar",
    "VMRRelease",
    "lineage_rank",
    "parse_accessions",
    "read_vmr",
    "release",
]

#: The ICTV's rank ladder, in order, as the VMR's own columns spell it. Written out rather
#: than derived from the sheet so that a release which renames or reorders a column is a
#: loud failure instead of a silently reordered lineage.
RANKS: tuple[str, ...] = (
    "realm",
    "subrealm",
    "kingdom",
    "subkingdom",
    "phylum",
    "subphylum",
    "class",
    "subclass",
    "order",
    "suborder",
    "family",
    "subfamily",
    "genus",
    "subgenus",
    "species",
)

#: VMR column heading -> rank name. The headings are the workbook's own, capitalised as it
#: capitalises them; :func:`read_vmr` matches on these exactly and refuses a sheet that does
#: not carry all of them.
_RANK_COLUMNS: dict[str, str] = {
    "Realm": "realm",
    "Subrealm": "subrealm",
    "Kingdom": "kingdom",
    "Subkingdom": "subkingdom",
    "Phylum": "phylum",
    "Subphylum": "subphylum",
    "Class": "class",
    "Subclass": "subclass",
    "Order": "order",
    "Suborder": "suborder",
    "Family": "family",
    "Subfamily": "subfamily",
    "Genus": "genus",
    "Subgenus": "subgenus",
    "Species": "species",
}

#: The other four columns the benchmark reads, by heading.
_EXEMPLAR_COLUMN = "Exemplar or additional isolate"
_ACCESSION_COLUMN = "Virus GENBANK accession"
_COVERAGE_COLUMN = "Genome coverage"
_HOST_COLUMN = "Host source"

#: The value in :data:`_EXEMPLAR_COLUMN` that marks a species' exemplar isolate.
EXEMPLAR_FLAG = "E"


@dataclass(frozen=True)
class VMRRelease:
    """One pinned VMR release.

    `filename` is the publisher's own, which carries the information its HTTP headers do
    not: every VMR file on the ICTV site reports the same `Last-Modified` (the site was
    migrated and the mtimes went with it), so the release date is recoverable only from the
    name and the MSL it cites.
    """

    filename: str
    msl: str
    published: str
    sha256: str
    bytes: int
    note: str = ""

    @property
    def url(self) -> str:
        return f"https://ictv.global/sites/default/files/VMR/{self.filename}"


#: The VMR releases this audit pins. Only the ones a task actually reads are listed: an
#: unused pin is a maintenance cost with no result attached, and the full published set is
#: recoverable from the ICTV's own VMR page.
RELEASES: dict[str, VMRRelease] = {
    "MSL37.3": VMRRelease(
        filename="VMR_20-190822_MSL37.3.xlsx",
        msl="MSL37",
        published="2022-08-19",
        sha256="66791e9bfea59ff051b5098d67d6a7406f972ee8ab0c759076c5e8b8f059bf32",
        bytes=1_563_522,
        note=(
            "The taxonomy in force when IMG/VR v4 was built. VMR_20 is dated 19 Aug 2022: "
            "three days before geNomad 1.1.0 and the marker database it pairs with, and a "
            "month before the v4 release files (2022-09-20). Revision .3 is the last "
            "correction to that same VMR_20 content, so it renders the taxonomy of the time "
            "most accurately without advancing to a later MSL. Choosing a later release "
            "would fold taxonomic revision into the measured error, which is A9.1's "
            "subject and not this one's."
        ),
    ),
    "MSL37.1": VMRRelease(
        filename="VMR_19-250422_MSL37.xlsx",
        msl="MSL37",
        published="2022-04-25",
        sha256="e8ed871aeb0ef801775385376003939d76d435c4de327974cdc469199c7647b1",
        bytes=1_288_178,
        note=(
            "VMR 19, which geNomad's paper (S-GENOMAD-NATBIOTECH) states its taxonomically "
            "informed markers were annotated from. Same MSL as the benchmark release, four "
            "months earlier. Held as the sensitivity check behind D-092, not as the default: "
            "scoring against the taxonomy the markers were built from measures the tool "
            "against its own reference, while scoring against the taxonomy in force when the "
            "corpus was built measures what the filter inherited. The two agree on every "
            "denylist-scope decision in the evaluation set."
        ),
    ),
}

#: The release A4.2 benchmarks against. Named rather than inlined so a reader of the
#: artefact can see which choice was made without reading the pipeline.
BENCHMARK_RELEASE = "MSL37.3"

#: The release geNomad's own markers were annotated from, per its paper, and therefore the
#: one a purist would score it against. Pinned so the sensitivity check D-092 reports can be
#: re-run rather than taken on trust: the two differ on 4 of 3,149 scored accessions, all of
#: them bacteriophage family renames out of the denylist's scope, and on no order and no
#: in-scope/out-of-scope classification at all.
MARKER_SOURCE_RELEASE = "MSL37.1"


def release(key: str) -> VMRRelease:
    try:
        return RELEASES[key]
    except KeyError:
        raise KeyError(f"no pinned VMR release {key!r}; pinned: {sorted(RELEASES)}") from None


# --------------------------------------------------------------------------------------
# Accessions
# --------------------------------------------------------------------------------------

#: An INSDC nucleotide accession as the VMR writes them. Two shapes occur and both are
#: real: the classic one- or two-letter form (`DQ665917`, `NC_001806`), and the WGS
#: contig form with a longer alphabetic prefix (`JAEILC010000038`). The pattern is
#: deliberately anchored — a loose one matches the segment labels, which are also
#: alphanumeric, and silently turns `DNA-U3` into an accession.
_ACCESSION = re.compile(r"^[A-Z]{1,6}_?\d{5,10}(?:\.\d+)?$")

#: A labelled segment, e.g. `DNA-C: EF546812` or `A: EU623082`. The label is kept because
#: it is the only record of which segment a sequence is, and a per-segment result that
#: cannot name its segment cannot be checked by a reader.
_LABELLED = re.compile(r"^(?P<label>[^:]{1,24}):\s*(?P<accession>\S+)$")


def parse_accessions(field_value: str) -> tuple[tuple[str | None, str], ...]:
    """Split a VMR accession cell into `(segment_label, accession)` pairs.

    Returns an empty tuple for the cells that hold no accession at all — the VMR's own
    "No entry in Genbank" rows, and blanks. Those are not errors and must not be dropped
    silently by a caller either: a species with no retrievable sequence is a species this
    benchmark cannot score, and the count of them belongs in the artefact.

    Unparseable tokens are returned under the label ``"?"`` rather than discarded, so that
    a release which invents a third format shows up as a countable anomaly instead of a
    quietly shorter evaluation set.
    """
    text = (field_value or "").strip()
    if not text:
        return ()
    out: list[tuple[str | None, str]] = []
    for raw in re.split(r"[;,]", text):
        token = raw.strip()
        if not token:
            continue
        label: str | None = None
        match = _LABELLED.match(token)
        if match:
            label = match.group("label").strip()
            token = match.group("accession").strip()
        token = token.strip()
        if _ACCESSION.match(token):
            out.append((label, token))
        else:
            out.append(("?", token))
    return tuple(out)


# --------------------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Exemplar:
    """One VMR row: a ratified lineage and the sequences that exemplify it."""

    species: str
    lineage: Mapping[str, str]
    accessions: tuple[tuple[str | None, str], ...]
    coverage: str
    host_source: str
    is_exemplar: bool
    row: int

    @property
    def segmented(self) -> bool:
        return len(self.accessions) > 1

    @property
    def complete(self) -> bool:
        """Whether the VMR calls this isolate's genome complete.

        Both of the publisher's "complete" wordings count: `Complete genome` and
        `Complete coding genome`. The distinction is about untranslated termini, not about
        whether the coding content a marker-based classifier reads is all there.
        """
        return self.coverage.strip().lower() in ("complete genome", "complete coding genome")

    def rank(self, name: str) -> str:
        return self.lineage.get(name, "")


def lineage_rank(exemplar: Exemplar, rank: str) -> str:
    """The exemplar's name at `rank`, or `""`. Present as a function for call sites that
    map over ranks, so a missing rank never becomes a `KeyError` mid-tally."""
    if rank not in RANKS:
        raise KeyError(f"{rank!r} is not an ICTV rank; known: {RANKS}")
    return exemplar.lineage.get(rank, "")


# --------------------------------------------------------------------------------------
# The workbook
# --------------------------------------------------------------------------------------

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_COLUMN_LETTERS = re.compile(r"^([A-Z]+)")


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """The workbook's shared-string table, flattened.

    A string cell in xlsx usually holds an index into this table rather than text. Each
    entry can be split across several `<t>` runs when part of it is styled differently, so
    the runs are concatenated; reading only the first `<t>` truncates exactly the
    multi-word names this benchmark keys on.
    """
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in root.iter(_NS + "si")]


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    """One cell's text, resolving the three encodings that appear in a VMR sheet."""
    kind = cell.get("t")
    if kind == "s":
        value = cell.find(_NS + "v")
        if value is None or value.text is None:
            return ""
        index = int(value.text)
        # An out-of-range index means the shared-string table and the sheet disagree, which
        # would otherwise surface as a wrong taxon name rather than an error.
        if not 0 <= index < len(shared):
            raise ValueError(f"shared-string index {index} out of range ({len(shared)} entries)")
        return shared[index]
    if kind == "inlineStr":
        inline = cell.find(_NS + "is")
        return "".join(t.text or "" for t in inline.iter(_NS + "t")) if inline is not None else ""
    value = cell.find(_NS + "v")
    return value.text or "" if value is not None else ""


def _rows(archive: zipfile.ZipFile, sheet: str, shared: list[str]) -> Iterator[dict[str, str]]:
    """Yield each sheet row as `{column_letter: text}`.

    Keyed by column letter, not by position: xlsx omits empty cells entirely, so a row with
    a blank Suborder has one fewer `<c>` element than its neighbour and positional reading
    shifts every later rank by one. That failure mode is quiet and would corrupt the
    lineage of exactly the rows whose lineage is incomplete.
    """
    root = ET.fromstring(archive.read(sheet))
    for row in root.iter(_NS + "row"):
        cells: dict[str, str] = {}
        for cell in row.iter(_NS + "c"):
            ref = cell.get("r") or ""
            letters = _COLUMN_LETTERS.match(ref)
            if letters is None:
                continue
            cells[letters.group(1)] = _cell_text(cell, shared)
        yield cells


@dataclass
class VMRTable:
    """A parsed VMR: its rows, and what the parse had to skip."""

    exemplars: list[Exemplar] = field(default_factory=list)
    all_rows: int = 0
    exemplar_rows: int = 0
    without_accession: int = 0
    headings: tuple[str, ...] = ()

    def by_rank(self, rank: str) -> dict[str, list[Exemplar]]:
        out: dict[str, list[Exemplar]] = {}
        for item in self.exemplars:
            name = item.rank(rank)
            if name:
                out.setdefault(name, []).append(item)
        return out


def read_vmr(path: str | Path, *, exemplars_only: bool = True) -> VMRTable:
    """Read a VMR workbook into :class:`Exemplar` rows.

    `exemplars_only` keeps one isolate per species — see the module docstring for why that
    is the default rather than an option exercised occasionally.
    """
    archive = zipfile.ZipFile(Path(path))
    shared = _shared_strings(archive)
    sheet = _first_worksheet(archive)
    rows = _rows(archive, sheet, shared)
    try:
        header = next(rows)
    except StopIteration:
        raise ValueError(f"{path}: first worksheet is empty") from None

    column_of = {text.strip(): letter for letter, text in header.items() if text.strip()}
    required = [*_RANK_COLUMNS, _EXEMPLAR_COLUMN, _ACCESSION_COLUMN, _COVERAGE_COLUMN]
    missing = [name for name in required if name not in column_of]
    if missing:
        raise ValueError(
            f"{path}: VMR sheet is missing expected column(s) {missing}. "
            f"Found: {sorted(column_of)}"
        )

    table = VMRTable(headings=tuple(sorted(column_of)))

    def get(cells: dict[str, str], heading: str) -> str:
        letter = column_of.get(heading)
        return (cells.get(letter, "") if letter else "").strip()

    for index, cells in enumerate(rows, start=2):
        if not any(value.strip() for value in cells.values()):
            continue
        table.all_rows += 1
        is_exemplar = get(cells, _EXEMPLAR_COLUMN) == EXEMPLAR_FLAG
        if is_exemplar:
            table.exemplar_rows += 1
        if exemplars_only and not is_exemplar:
            continue
        accessions = parse_accessions(get(cells, _ACCESSION_COLUMN))
        if not accessions:
            table.without_accession += 1
        lineage = {
            rank: get(cells, heading)
            for heading, rank in _RANK_COLUMNS.items()
            if get(cells, heading)
        }
        table.exemplars.append(
            Exemplar(
                species=get(cells, "Species"),
                lineage=lineage,
                accessions=accessions,
                coverage=get(cells, _COVERAGE_COLUMN),
                host_source=get(cells, _HOST_COLUMN),
                is_exemplar=is_exemplar,
                row=index,
            )
        )
    return table


def _first_worksheet(archive: zipfile.ZipFile) -> str:
    """The path of the workbook's first worksheet.

    Resolved through the workbook relationships rather than assumed to be `sheet1.xml`:
    the VMR's data sheet is named after its MSL (`VMRb37`), and the file ordering inside
    the zip is not part of the format's contract.
    """
    book = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target_of = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.iter("{*}Relationship")  # type: ignore[arg-type]
    }
    for sheet in book.iter(_NS + "sheet"):
        rel_id = sheet.get(rels_ns + "id")
        target = target_of.get(rel_id or "")
        if target:
            return f"xl/{target.lstrip('/')}" if not target.startswith("xl/") else target
    names = [n for n in archive.namelist() if n.startswith("xl/worksheets/")]
    if not names:
        raise ValueError("workbook contains no worksheets")
    return sorted(names)[0]


def summarise(table: VMRTable) -> dict[str, Any]:
    """Counts a reader needs to judge the evaluation set's provenance and bias."""
    coverage: dict[str, int] = {}
    hosts: dict[str, int] = {}
    for item in table.exemplars:
        coverage[item.coverage or "(empty)"] = coverage.get(item.coverage or "(empty)", 0) + 1
        hosts[item.host_source or "(empty)"] = hosts.get(item.host_source or "(empty)", 0) + 1
    return {
        "rows": table.all_rows,
        "exemplar_rows": table.exemplar_rows,
        "exemplars_read": len(table.exemplars),
        "without_accession": table.without_accession,
        "segmented": sum(1 for e in table.exemplars if e.segmented),
        "sequences": sum(len(e.accessions) for e in table.exemplars),
        "coverage": dict(sorted(coverage.items(), key=lambda kv: -kv[1])),
        "host_source": dict(sorted(hosts.items(), key=lambda kv: -kv[1])),
    }

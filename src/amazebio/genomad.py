"""geNomad as the object of study: which version, and how to read what it says.

A4.2 benchmarks geNomad because it is the one taxonomy assignment method in IMG/VR that this
audit can actually run (D-084). This module holds the three things that makes necessary — the
version pins, the output parser, and the honest statement of what the benchmarked step is —
and nothing about statistics, which is `misassignment`'s.

**The version is a bound, not a statement.** The release note pins CheckV to `v1.0.1` in the
same field list and names geNomad with no version at all; the publisher's help page contains no
version string anywhere. So what the audit may claim is a bound derived from dates the
publisher does not control: geNomad 1.0.0 was released 2022-07-30, 1.1.0 on 2022-08-22, and
1.2.0 not until 2022-11-15, while the v4 release files are dated 2022-09-20. The labels were
produced by something at or before 1.1.0. :data:`PIN` is that newest-possible pairing and
:data:`VERSION_EVIDENCE` is the reasoning, carried into the artefact rather than left in a
commit message. See D-085.

**`--version` lies here, and the manifest must not believe it.** geNomad 1.1.0 calls
`click.version_option()` with no package name. A modern click resolves the distribution by
walking the call frame and finds `rich-click` instead, so the CLI prints that package's version
— `1.9.8` in this environment, which is not even a geNomad release number. :func:`installed_
version` reads the installed distribution's own metadata instead. Anything that records
provenance from `genomad --version` records fiction.

**What is benchmarked is the taxonomy step, not virus identification.** The pipeline runs
`genomad annotate`, which calls genes and assigns a lineage from marker-gene consensus. It does
not run geNomad's virus/plasmid classifier. That is the correct scope rather than a shortcut:
the records Evo's denylist acts on are already in IMG/VR, so they have already been called
viral, and the only question left for the filter is what taxon they were assigned to. The
consequence for reporting is explicit — the `not_viral` escape cause is zero by construction
here, and :data:`SCOPE_NOTE` says so, so a reader does not take a zero for a measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "LINEAGE_RANKS",
    "PIN",
    "SCOPE_NOTE",
    "VERSION_EVIDENCE",
    "GenomadPin",
    "TaxonomyCall",
    "installed_version",
    "parse_lineage",
    "read_taxonomy",
]


@dataclass(frozen=True)
class GenomadPin:
    """The code/database pairing the benchmark runs."""

    version: str
    database_version: str
    database_sha256: str
    database_url: str
    mmseqs2: str
    python: str
    numpy: str
    splits: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "genomad": self.version,
            "marker_database": self.database_version,
            "marker_database_sha256": self.database_sha256,
            "marker_database_url": self.database_url,
            "mmseqs2": self.mmseqs2,
            "python": self.python,
            "numpy": self.numpy,
            "mmseqs2_splits": self.splits,
        }


#: What A4.2 runs. The database sha256 is of the published tarball as retrieved, because the
#: publisher ships no checksum of its own — so it attests that the bytes have not changed
#: since acquisition, not that they are the bytes released. Same convention as B2.1's.
PIN = GenomadPin(
    version="1.1.0",
    database_version="1.1",
    database_sha256="462959a4671fe06c12d1d528f8c3c7051aa31e5dfed80ca2d204a59be0f4e025",
    database_url="https://portal.nersc.gov/genomad/__data__/genomad_db_v1.1.tar.gz",
    mmseqs2="13.45111",
    python="3.10",
    numpy="1.23",
    splits=8,
)

#: Why :data:`PIN` is the version it is, in a form the artefact can carry. Each entry is a
#: fact with its source; the conclusion is a bound.
VERSION_EVIDENCE: dict[str, Any] = {
    "stated_by_publisher": None,
    "sources_checked": [
        {
            "source": "IMG/VR v4 release note (README.txt, both releases)",
            "finding": (
                "pins CheckV to v1.0.1 by name in the same field list; names geNomad with no "
                "version"
            ),
        },
        {
            "source": "IMG/VR help page (https://img.jgi.doe.gov/docs/IMG-VR.pdf, 13 pages)",
            "finding": (
                "describes geNomad's role and the four taxonomy approaches; contains no "
                "version string anywhere"
            ),
        },
        {
            "source": "IMG/VR v4 paper (doi:10.1093/nar/gkac1037)",
            "finding": (
                "not retrieved: the publisher returns 403 and PMC serves a proof-of-work "
                "interstitial. The claim is therefore scoped to the two sources above"
            ),
        },
    ],
    "bound": {
        "argument": (
            "geNomad 1.0.0 was released 2022-07-30 and 1.1.0 on 2022-08-22; 1.2.0 did not exist "
            "until 2022-11-15. The v4 release files are dated 2022-09-20, so the labels were "
            "produced by geNomad at or before 1.1.0, or by a pre-release build — geNomad and "
            "IMG/VR come from the same group and the geNomad preprint postdates v4 by a year."
        ),
        "newest_possible": "1.1.0",
        "database_pairing": (
            "The publisher's own releases.txt maps package 1.1 to marker database v1.1, whose "
            "files are dated 2022-08-22."
        ),
    },
    "reading": (
        "The version is a bound derived from release dates, not a statement by the publisher. "
        "An error rate reported against 1.1.0 is the rate for the newest version that could "
        "have produced these labels."
    ),
}

#: What the benchmark covers, stated so a structural zero is not read as a measurement.
SCOPE_NOTE = (
    "The benchmarked step is `genomad annotate`: gene calling plus marker-gene taxonomic "
    "assignment. geNomad's virus/plasmid classifier is not run, and deliberately so — the "
    "records Evo's denylist acts on are already in IMG/VR and have therefore already been "
    "called viral, so the only question left for the filter is which taxon they were assigned. "
    "The `not_viral` escape cause is consequently zero by construction in this arm and must "
    "not be read as evidence that the step never fails that way."
)

#: geNomad writes its lineage as a fixed positional ladder headed by the literal `Viruses`:
#: `Viruses;Duplodnaviria;Heunggongvirae;Peploviricota;Herviviricetes;Herpesvirales;Herpesviridae`.
#: Position 0 is the domain literal and carries no taxon.
LINEAGE_RANKS: tuple[str, ...] = (
    "realm",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
)

#: The ICTV's rank suffixes. Used to *check* the positional read rather than to perform it —
#: the same discipline `conformance.parse_lineage_tag` applies to the released tag, and for the
#: same reason: a positional parser that silently mis-ranks a short lineage would turn a
#: truncation into a misassignment, which is the one distinction this task exists to make.
_RANK_SUFFIX: dict[str, str] = {
    "realm": "viria",
    "kingdom": "virae",
    "phylum": "viricota",
    "class": "viricetes",
    "order": "virales",
    "family": "viridae",
}

_UNCLASSIFIED = re.compile(r"^unclassified\b", re.IGNORECASE)


@dataclass(frozen=True)
class TaxonomyCall:
    """One row of geNomad's `_taxonomy.tsv`, parsed."""

    sequence: str
    genes_with_taxonomy: int
    agreement: float | None
    taxid: str
    raw: str
    lineage: dict[str, str]
    anomalies: tuple[str, ...] = ()

    @property
    def assigned_to(self) -> str | None:
        """The finest rank this call fills, or `None` for a call that fills nothing."""
        for rank in reversed(LINEAGE_RANKS):
            if self.lineage.get(rank):
                return rank
        return None


def parse_lineage(raw: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Parse a geNomad lineage string into `{rank: name}`, plus anything anomalous.

    Three readings worth stating, because each is a way the count could go quietly wrong.

    **A short lineage is a truncation, not a malformation.** geNomad stops at the rank its
    marker consensus supports, so `Viruses;Riboviria;Orthornavirae` is a well-formed call that
    reaches kingdom and no further. That is the single most important case in this benchmark —
    it is the escape route A4.1 measured the corpus-side shadow of — so it must parse cleanly
    and fill only the ranks it names.

    **Position is checked against the ICTV suffix, and a disagreement is recorded rather than
    resolved.** Ranks are read by position because that is the format's contract, but every
    ICTV rank has a mandated suffix, so a mismatch means either geNomad or our reading is
    wrong, and that is not settled by discarding the evidence.

    **A lineage that is not headed `Viruses` yields no ranks at all.** The ladder this parser
    reads is the viral one, so applying it to a row that is not viral would assign a realm to a
    bacterial phylum. Such a row is recorded as an anomaly and trusted for nothing.

    **`unclassified <something>` placeholders fill nothing.** geNomad emits these for ranks it
    cannot resolve; treating the literal string as a taxon name would make every such record a
    confident misassignment instead of an unlabelled one — inverting the finding.
    """
    anomalies: list[str] = []
    lineage: dict[str, str] = {}
    fields = [f.strip() for f in (raw or "").split(";")]
    if not fields or not fields[0]:
        return {}, ()
    if fields[0] != "Viruses":
        # Recorded and then trusted for nothing. geNomad's taxonomy ladder is viral, so a head
        # that is not `Viruses` means the row is not the thing this parser models, and reading
        # its fields against the viral rank ladder anyway would assign a realm to a bacterial
        # phylum. No rank is claimed from such a row.
        anomalies.append(f"lineage does not begin with 'Viruses': {fields[0]!r}")
        return {}, tuple(anomalies)
    body = fields[1:]
    if len(body) > len(LINEAGE_RANKS):
        anomalies.append(f"{len(body)} ranks below domain, expected at most {len(LINEAGE_RANKS)}")
    for index, name in enumerate(body[: len(LINEAGE_RANKS)]):
        if not name:
            continue
        rank = LINEAGE_RANKS[index]
        if _UNCLASSIFIED.match(name):
            continue
        suffix = _RANK_SUFFIX[rank]
        if not name.endswith(suffix):
            anomalies.append(f"{name!r} at position {index} ({rank}) lacks the suffix {suffix!r}")
        lineage[rank] = name
    return lineage, tuple(anomalies)


def read_taxonomy(path: str | Path) -> dict[str, TaxonomyCall]:
    """Read a `*_taxonomy.tsv` into `{sequence_name: TaxonomyCall}`.

    A sequence **absent from this file** has no entry, and the caller must treat that as an
    unclassified record rather than a missing one: `genomad annotate` writes a row only for a
    sequence with at least one gene carrying marker taxonomy, so absence is the result, not a
    gap in it. The five-sequence pilot behind D-087 produced four rows for five inputs, and the
    missing one was an influenza A segment — a denylisted family, escaping by having nothing
    said about it.
    """
    calls: dict[str, TaxonomyCall] = {}
    text = Path(path).read_text()
    lines = text.splitlines()
    if not lines:
        return calls
    header = lines[0].split("\t")
    expected = ["seq_name", "n_genes_with_taxonomy", "agreement", "taxid", "lineage"]
    if header[: len(expected)] != expected:
        raise ValueError(f"{path}: unexpected taxonomy header {header!r}; expected {expected!r}")
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < len(expected):
            raise ValueError(f"{path}: short taxonomy row {line!r}")
        lineage, anomalies = parse_lineage(fields[4])
        try:
            agreement: float | None = float(fields[2])
        except ValueError:
            agreement = None
        try:
            genes = int(fields[1])
        except ValueError:
            genes = 0
        calls[fields[0]] = TaxonomyCall(
            sequence=fields[0],
            genes_with_taxonomy=genes,
            agreement=agreement,
            taxid=fields[3],
            raw=fields[4],
            lineage=lineage,
            anomalies=anomalies,
        )
    return calls


def installed_version(environment_root: str | Path) -> str:
    """The geNomad version from the installed distribution's metadata.

    Not from `genomad --version`, which reports `rich-click`'s version in this environment
    because geNomad 1.1.0 calls `click.version_option()` with no package name (D-085). A
    manifest that records provenance from the CLI records fiction, so the one place the version
    is read is here.
    """
    root = Path(environment_root)
    found = sorted(root.glob("lib/python*/site-packages/genomad-*.dist-info"))
    if not found:
        raise FileNotFoundError(f"no genomad dist-info under {root}")
    name = found[-1].name
    return name.removeprefix("genomad-").removesuffix(".dist-info")

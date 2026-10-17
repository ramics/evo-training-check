"""Integrated elements in surviving bacterial genomes — the instruments A2.4 detects with.

`DESIGN.md` §A2 lists prophage detection as one of five routes by which viral-derived content
survives a taxonomy filter, and A2.4 is the task that measures it. This module holds the three
things that needs and nothing else: the version pins, the output parsers for the two tools, and
the concordance arithmetic. The pipeline that reads the corpus is `tools/detect_proviruses.py`;
the output contract it writes into is `metrics/detections.md`, shared with A2.1.

Four decisions are load-bearing and each is in `tasks/DECISIONS.md`.

**geNomad is pinned here as the audit's instrument, not as A4.2's object of study** (D-112).
`amazebio.genomad` pins 1.1.0 because A4.2 benchmarks the version IMG/VR's own labels came out
of. This module pins 1.12.0 against marker database v1.9, and the two must not be unified:
§A2's opening sentence requires the audit's instruments to be independent of the filter's, and
detecting proviruses with the same 2022 build against the same 2022 markers would make the
audit's blind spot and the filter's blind spot the same blind spot. A2.4 would then report an
absence of prophage that was really an absence of markers — a false null, in the direction
`AGENTS.md` says the pipeline may never be designed to favour.

**These tools say where an element is, never which family it belongs to** (D-113). A provirus
call is an interval in a host contig with a score. The only family-like label geNomad offers is
its marker-consensus taxonomy, which is taxonomy — the input §A2 rules out, and the one A4.2
measured failing to place 36% of the genomes the denylist targets. So nothing in this module
returns a family. Family identity comes from the registries A2.1 pinned, searched over the
proteins inside the interval these tools delineate, at D-076's thresholds unchanged.

**Concordance is a measurement, not a filter** (D-114). VIBRANT is the second tool because its
mechanism is independent — HMM scoring against KEGG, Pfam and VOG with a metabolic-signature
rule, against geNomad's marker consensus plus neural classifier — and because §A2 names it.
:func:`concordance` reports agreement and disagreement **by direction** and never resolves a
disagreement by preferring a tool. Keeping only the calls both tools make would read as rigour
and would be the opposite: it converts instrument disagreement into a quiet reduction in the
headline, in the direction that flatters the filter under audit.

**Every table is read by column name, never by position.** D-090 is the worked lesson: reading
geNomad's lineage as a fixed positional ladder inflated A4.2's headline, because the tool omits
a rank it cannot resolve instead of leaving the field empty. The same failure mode is available
in any of these TSVs the moment a release adds a column, and a provirus parsed from the wrong
columns is a coordinate error that no downstream check would catch.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amazebio.survival import Z_95, Interval

__all__ = [
    "GENOMAD",
    "SCOPE_NOTE",
    "VIBRANT",
    "AgreementTable",
    "ProvirusCall",
    "ProvirusError",
    "ToolPin",
    "cohens_kappa",
    "concordance",
    "overlapping_pairs",
    "read_genomad_proviruses",
    "read_vibrant_proviruses",
    "reciprocal_overlap",
]

#: The reciprocal-overlap fraction at which two calls on the same record are taken to be the
#: same call. Fixed at 0.5 in D-114 **before any call was looked at**, which is the whole point:
#: an agreement threshold chosen once the overlap distribution is in hand is not a criterion,
#: it is a result selected for being reportable.
MIN_RECIPROCAL_OVERLAP = 0.5


#: The score column geNomad 1.12.0 actually writes, with earlier and later names after it.
#: `v_vs_c_score` — virus versus chromosome — is the pinned version's own name for it, read off
#: a real run rather than from the documentation: the first draft of this parser guessed
#: `virus_score` and silently returned `None` for every call, which is the quiet variety of
#: wrong that a score-free table would have carried all the way into A3.2.
_GENOMAD_SCORE_COLUMNS: tuple[str, ...] = (
    "v_vs_c_score",
    "topology_score",
    "virus_score",
    "score",
)


class ProvirusError(RuntimeError):
    """Raised when a provirus table cannot be read as what it claims to be."""


@dataclass(frozen=True)
class ToolPin:
    """One detection tool, with everything a `run.json` has to record about it."""

    tool: str
    version: str
    database_version: str | None = None
    database_url: str | None = None
    #: Of the published archive as retrieved. The publishers ship no checksum of their own, so
    #: this attests that the bytes have not changed since acquisition, not that they are the
    #: bytes released — the same convention `amazebio.genomad.PIN` and B2.1 use.
    database_sha256: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"tool": self.tool, "version": self.version}
        if self.database_version:
            d["database_version"] = self.database_version
        if self.database_url:
            d["database_url"] = self.database_url
        if self.database_sha256:
            d["database_sha256"] = self.database_sha256
        if self.note:
            d["note"] = self.note
        return d


#: A2.4's primary instrument. 1.12.0 rather than 1.13.0, which is newer on bioconda but which
#: the publisher's own `releases.txt` does not yet pair with any marker database; v1.9 with
#: package 1.12 is the newest pairing the publisher attests. The package/database pairing is
#: part of the pin rather than a detail beside it — D-085 records what it cost A4.2 to have to
#: infer one, and there is no reason to manufacture a second inference when an attested pairing
#: is on offer. See D-112.
GENOMAD = ToolPin(
    tool="genomad",
    version="1.12.0",
    database_version="1.9",
    database_url="https://portal.nersc.gov/genomad/__data__/genomad_db_v1.9.tar.gz",
    # Of the published tarball as retrieved 2026-10-17, 842,023,773 bytes. The publisher ships
    # no checksum of its own, so this attests that the bytes have not changed since
    # acquisition, not that they are the bytes released — the same convention
    # `amazebio.genomad.PIN` uses. It is load-bearing rather than decorative: the in-region
    # launcher refuses to detect against a database whose digest does not match, and it caught
    # this field being left as `None` on A2.4's third proving launch.
    database_sha256="47a54faa9584422d6ea1328550d0c78d5fc9ac82ddd1ca9532c1ed365c8e572c",
    note=(
        "The audit's instrument, pinned apart from `amazebio.genomad.PIN`, which is the 1.1.0 "
        "build A4.2 benchmarks as the object of study (D-112). Unlike 1.1.0, this version's "
        "`--version` reports geNomad's own version rather than rich-click's, so the CLI is a "
        "usable provenance source here where D-085 found it was not."
    ),
)

#: The second tool the concordance criterion is measured against (D-114). §A2 names it, and its
#: mechanism is independent of geNomad's in the way the criterion needs. Its databases are the
#: ones `download-db.sh` installs beside the package; VIBRANT ships no version string for them,
#: which is recorded rather than papered over.
VIBRANT = ToolPin(
    tool="vibrant",
    version="1.2.1",
    database_version="KOfam 2019-08-10 + Pfam 32.0 + VOG 94",
    note=(
        "The database versions are not a reading. VIBRANT 1.2.1's own `VIBRANT_setup.py` "
        "hard-codes all three releases by URL — KOfam's 2019-08-10 archive, Pfam 32.0, VOG 94 "
        "— so the pin is read off the package rather than inferred, and any installation the "
        "script produced carries these and no others. The tool exposes no version string for "
        "them at run time, which is why they are recorded here instead: a digest of the "
        "installed profile files travels in the `run.json` beside this."
    ),
)

#: What A2.4's numbers are numbers of, stated so that a bound is not read as a census.
SCOPE_NOTE = (
    "A2.4 reports viral-family survival *inside delineated proviruses* in sampled surviving "
    "bacterial genomes. It is a lower bound twice over and in one direction (D-113, D-115): a "
    "viral-family protein outside any provirus call is not counted, and a genome outside the "
    "sample is not read. A detection is therefore evidence; an absence is not evidence of "
    "absence. The element kind is `prophage` — the kind D-079 reserved for this task to "
    "establish rather than for A2.1 to infer from a profile hit."
)


@dataclass(frozen=True)
class ProvirusCall:
    """One integrated element, as either tool reports it.

    Coordinates are **1-based inclusive**, which is what both tools emit and what
    :func:`reciprocal_overlap` assumes. They are kept as the tool gave them rather than
    normalised to a half-open convention, because a coordinate silently shifted by one is the
    kind of error that survives every downstream check and changes a concordance figure.
    """

    #: The host record the element sits in — the key A2.4 joins on, and the id the sampler
    #: hashes. Not the tool's own name for the excised fragment, which differs between tools
    #: and would make the two tables unjoinable.
    source_record: str
    #: The tool's name for the fragment itself, kept for traceability back to its output.
    fragment: str
    start: int
    end: int
    tool: str
    #: geNomad reports a per-provirus score; VIBRANT does not expose a comparable one, so this
    #: is `None` for VIBRANT calls and must not be defaulted to zero — a missing score and a
    #: score of zero are different claims.
    score: float | None = None

    def __post_init__(self) -> None:
        if self.start < 1:
            raise ProvirusError(
                f"{self.tool} call {self.fragment!r} starts at {self.start}: these tables are "
                "1-based, so a start below 1 means the columns were read wrongly"
            )
        if self.end < self.start:
            raise ProvirusError(
                f"{self.tool} call {self.fragment!r} ends at {self.end} before its start "
                f"{self.start}"
            )

    @property
    def length(self) -> int:
        """Length in bases, inclusive of both endpoints."""
        return self.end - self.start + 1


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------


def _rows(path: str | Path, *, required: Sequence[str], what: str) -> Iterator[dict[str, str]]:
    """Yield a TSV's rows as `{column: value}`, keyed by the header's own names.

    By name and never by position, for the reason D-090 cost A4.2 a headline: a release that
    adds or reorders a column silently re-points a positional read, and a provirus whose
    coordinates came from the wrong columns is an error nothing downstream would catch. A
    missing required column stops the run rather than yielding a row with a hole in it.
    """
    text = Path(path).read_text()
    lines = text.splitlines()
    if not lines:
        raise ProvirusError(f"{path}: empty {what} table — not even a header row")
    header = lines[0].split("\t")
    missing = [c for c in required if c not in header]
    if missing:
        raise ProvirusError(
            f"{path}: {what} table is missing the column(s) {missing!r}; it has {header!r}. "
            "The pinned version's output shape has changed, which invalidates the pin rather "
            "than the parser."
        )
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != len(header):
            raise ProvirusError(
                f"{path}: {what} row has {len(fields)} fields against a {len(header)}-column "
                f"header: {line!r}"
            )
        yield dict(zip(header, fields, strict=True))


def _int(row: dict[str, str], column: str, *, path: str | Path, what: str) -> int:
    raw = row[column].strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ProvirusError(f"{path}: {what} column {column!r} is not an integer: {raw!r}") from exc


def read_genomad_proviruses(path: str | Path) -> list[ProvirusCall]:
    """Read geNomad's `*_provirus.tsv`.

    A host record **absent from this file has no provirus call**, and the caller must read that
    as the measured result rather than as a gap: `find-proviruses` writes a row per detected
    element, so a genome with none is simply not mentioned. That asymmetry is the same one
    `amazebio.genomad.read_taxonomy` documents, and it matters more here — A2.4's denominator is
    the records searched, which the pipeline knows, and never the records this file mentions.
    """
    required = ("seq_name", "source_seq", "start", "end")
    calls: list[ProvirusCall] = []
    for row in _rows(path, required=required, what="geNomad provirus"):
        score: float | None = None
        for column in _GENOMAD_SCORE_COLUMNS:
            if column in row and row[column].strip():
                try:
                    score = float(row[column])
                except ValueError:
                    score = None
                else:
                    break
        calls.append(
            ProvirusCall(
                source_record=row["source_seq"].strip(),
                fragment=row["seq_name"].strip(),
                start=_int(row, "start", path=path, what="geNomad provirus"),
                end=_int(row, "end", path=path, what="geNomad provirus"),
                tool=GENOMAD.tool,
                score=score,
            )
        )
    return calls


def read_vibrant_proviruses(path: str | Path) -> list[ProvirusCall]:
    """Read VIBRANT's `VIBRANT_integrated_prophage_coordinates_*.tsv`.

    VIBRANT names its columns with spaces and units — `nucleotide start` rather than `start` —
    so the required names here look unlike geNomad's on purpose. Normalising them into a shared
    vocabulary inside the parser would hide which tool's table failed to parse, which is the one
    thing a concordance run needs to be able to tell.

    No score is carried. VIBRANT's per-prophage output has no field comparable to geNomad's, and
    inventing a constant to fill the column would make the two tools' scores look commensurable
    when they are not.
    """
    required = ("scaffold", "fragment", "nucleotide start", "nucleotide stop")
    calls: list[ProvirusCall] = []
    for row in _rows(path, required=required, what="VIBRANT prophage"):
        calls.append(
            ProvirusCall(
                source_record=row["scaffold"].strip(),
                fragment=row["fragment"].strip(),
                start=_int(row, "nucleotide start", path=path, what="VIBRANT prophage"),
                end=_int(row, "nucleotide stop", path=path, what="VIBRANT prophage"),
                tool=VIBRANT.tool,
                score=None,
            )
        )
    return calls


# --------------------------------------------------------------------------------------
# Concordance
# --------------------------------------------------------------------------------------


def reciprocal_overlap(a: ProvirusCall, b: ProvirusCall) -> float:
    """Reciprocal overlap of two calls: the *smaller* of the two covered fractions.

    The smaller rather than the larger, and rather than the Jaccard index, because the criterion
    is meant to refuse a short call nested inside a long one. A 2 kb fragment wholly inside a
    40 kb one covers 100% of itself and 5% of the other; calling that agreement would let a tool
    that merely found a fragment of the same element count as confirming its extent.

    Calls on different records never overlap, whatever their coordinates — the records are
    different sequences and the shared coordinate space is an artefact of both starting at 1.
    """
    if a.source_record != b.source_record:
        return 0.0
    shared = min(a.end, b.end) - max(a.start, b.start) + 1
    if shared <= 0:
        return 0.0
    return min(shared / a.length, shared / b.length)


def overlapping_pairs(
    left: Iterable[ProvirusCall],
    right: Iterable[ProvirusCall],
    *,
    min_overlap: float = MIN_RECIPROCAL_OVERLAP,
) -> list[tuple[ProvirusCall, ProvirusCall, float]]:
    """Every (left, right, overlap) pair meeting the criterion, best overlap first.

    Every qualifying pair, not a one-to-one matching. The tools split and merge elements
    differently — a tandem pair of prophages is one call to one tool and two to the other — and
    a matching would have to choose which of those readings to discard. Reporting the pairs
    keeps the split visible, and the record-level 2x2 in :func:`concordance` is what the kappa
    is computed from.
    """
    pairs = [
        (a, b, overlap)
        for a in left
        for b in right
        if (overlap := reciprocal_overlap(a, b)) >= min_overlap
    ]
    pairs.sort(key=lambda p: -p[2])
    return pairs


@dataclass(frozen=True)
class AgreementTable:
    """The record-level 2x2, with its kappa, for one concordance subsample."""

    #: Records both tools call positive.
    both: int
    #: Records only geNomad calls positive.
    genomad_only: int
    #: Records only VIBRANT calls positive.
    vibrant_only: int
    #: Records neither calls positive. Measured, not inferred — it is the cell that makes kappa
    #: meaningful, and it exists only because the denominator is the records *searched*.
    neither: int
    kappa: Interval
    #: Pairs of calls meeting the overlap criterion, and calls on agreed records that did not
    #: pair with anything. The second number is where the tools agree a record carries an
    #: element and disagree about its extent.
    paired_calls: int
    unpaired_calls_on_agreed_records: int

    @property
    def records(self) -> int:
        return self.both + self.genomad_only + self.vibrant_only + self.neither

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "both": self.both,
            "genomad_only": self.genomad_only,
            "vibrant_only": self.vibrant_only,
            "neither": self.neither,
            "kappa": {
                "estimate": self.kappa.estimate,
                "low": self.kappa.low,
                "high": self.kappa.high,
                "method": self.kappa.method,
            },
            "paired_calls": self.paired_calls,
            "unpaired_calls_on_agreed_records": self.unpaired_calls_on_agreed_records,
            "min_reciprocal_overlap": MIN_RECIPROCAL_OVERLAP,
            "reading": (
                "Disagreement is reported by direction and never resolved by preferring a "
                "tool (D-114). The headline comes from geNomad alone; this table measures how "
                "far that headline depends on the instrument."
            ),
        }


def cohens_kappa(both: int, genomad_only: int, vibrant_only: int, neither: int) -> Interval:
    """Cohen's kappa for the 2x2, with a 95% interval.

    Kappa rather than raw agreement because raw agreement is uninformative where one outcome
    dominates, and it will: most sampled genomes are expected to carry no detected provirus, so
    two tools that both say "no" almost always would post a raw agreement near 1 while agreeing
    about nothing that matters.

    The interval is the standard large-sample one. It is an approximation and is named as one in
    `method`, so a reader is not invited to treat it as exact — `AGENTS.md` requires the
    uncertainty to travel with the estimate, not to be exact.
    """
    n = both + genomad_only + vibrant_only + neither
    if n <= 0:
        raise ProvirusError(
            "kappa over an empty concordance subsample is undefined; an empty subsample means "
            "the sampling design was not applied, which is a setup error rather than a result"
        )
    observed = (both + neither) / n
    expected = (
        ((both + genomad_only) * (both + vibrant_only))
        + ((vibrant_only + neither) * (genomad_only + neither))
    ) / (n * n)
    if math.isclose(expected, 1.0):
        # Both tools called every record the same way, so chance agreement is already total and
        # kappa is 0/0. Reported as undefined rather than as 1.0 or 0.0: with no variation there
        # is no agreement beyond chance to measure, and either number would be an assertion the
        # data does not carry.
        return Interval(
            estimate=float("nan"),
            low=float("nan"),
            high=float("nan"),
            method="undefined: chance agreement is total, so kappa is 0/0",
        )
    kappa = (observed - expected) / (1 - expected)
    se = math.sqrt(observed * (1 - observed) / n) / (1 - expected)
    return Interval(
        estimate=kappa,
        low=kappa - Z_95 * se,
        high=kappa + Z_95 * se,
        method=f"cohen_kappa_large_sample_z{Z_95:.6f}",
    )


def concordance(
    records_searched: Iterable[str],
    genomad_calls: Iterable[ProvirusCall],
    vibrant_calls: Iterable[ProvirusCall],
    *,
    min_overlap: float = MIN_RECIPROCAL_OVERLAP,
) -> AgreementTable:
    """Agreement between the two tools over the records both were run on.

    `records_searched` is the denominator and it is required, not derived from the calls. A
    concordance computed over the union of what the tools found would have no `neither` cell,
    and kappa without it is undefined — which is the arithmetic expression of the fact that two
    tools agreeing a genome is clean is a real agreement and has to be counted.

    A record carrying calls that the parser attributes to neither tool stops the run: it means
    the calls and the searched set were assembled from different passes, and every cell of the
    table would then be counting something else.
    """
    searched = list(dict.fromkeys(records_searched))
    searched_set = set(searched)
    if len(searched) != len(searched_set):  # pragma: no cover - dict.fromkeys dedupes
        raise ProvirusError("records_searched contains duplicates")

    by_tool: dict[str, dict[str, list[ProvirusCall]]] = {GENOMAD.tool: {}, VIBRANT.tool: {}}
    for calls, tool in ((genomad_calls, GENOMAD.tool), (vibrant_calls, VIBRANT.tool)):
        for call in calls:
            if call.source_record not in searched_set:
                raise ProvirusError(
                    f"{tool} reports a call on {call.source_record!r}, which is not in the "
                    "searched set. The calls and the denominator come from different passes, "
                    "and a 2x2 assembled from both would count four different things."
                )
            by_tool[tool].setdefault(call.source_record, []).append(call)

    g, v = by_tool[GENOMAD.tool], by_tool[VIBRANT.tool]
    both = sum(1 for r in searched if r in g and r in v)
    genomad_only = sum(1 for r in searched if r in g and r not in v)
    vibrant_only = sum(1 for r in searched if r not in g and r in v)
    neither = len(searched) - both - genomad_only - vibrant_only

    paired = 0
    unpaired = 0
    for record in searched:
        if record not in g or record not in v:
            continue
        pairs = overlapping_pairs(g[record], v[record], min_overlap=min_overlap)
        paired += len(pairs)
        matched = {id(c) for pair in pairs for c in (pair[0], pair[1])}
        unpaired += sum(1 for c in (*g[record], *v[record]) if id(c) not in matched)

    return AgreementTable(
        both=both,
        genomad_only=genomad_only,
        vibrant_only=vibrant_only,
        neither=neither,
        kappa=cohens_kappa(both, genomad_only, vibrant_only, neither),
        paired_calls=paired,
        unpaired_calls_on_agreed_records=unpaired,
    )

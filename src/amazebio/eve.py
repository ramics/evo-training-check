"""A2.3's retroelement arm: consensus queries, the acceptance rule, and the detections — D-186.

D-183 pinned the registry and D-186 replaced its instrument. The profile route it originally
specified costs 4.962e-4 core-seconds per model-residue-megabase, which is 48,040 core-hours
over the 1% band — so the arm searches each family's **consensus** with a seeded aligner
instead, which is what RepeatMasker does and the reason it exists.

Three things follow from that, and they are the whole content of this module:

**The queries are derived from the models already pinned.** Every curated HMM carries a
match-state consensus of its own length, so :func:`consensus_queries` reads the query set out of
the registry D-183 acquired and verified. No second download and no second pin — which also
sidesteps Dfam 4.0 shipping curated *consensus* for the root partition only, where these
families are not.

**The acceptance rule is a conjunction and it is this project's own.** Dfam's `GA` cutoffs are
profile bit scores and do not transfer to an aligner, so reusing them would look like the
publisher's threshold while being an invention. D-186 declares the cut instead:
E-value ≤ 1e-10, alignment ≥ 100 bp, identity ≥ 0.70, fixed before any hit was seen.

**A consensus search is less sensitive than the profile it came from**, and that is the safe
direction for an audit reporting survival: it makes every figure a lower bound, which is what
D-115 requires anyway.

The aligner runs as a subprocess in the tool; everything here is pure and tested, because the
acceptance rule is the part a reviewer will want to check and a subprocess is the part that
cannot be checked in a unit test.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from amazebio.survival import Detection, ElementKind, Route

__all__ = [
    "ACCEPT",
    "DETECTOR",
    "ELEMENT_KIND",
    "MMSEQS_FORMAT",
    "Alignment",
    "EveError",
    "accept",
    "consensus_queries",
    "detections_for",
    "parse_alignments",
    "write_queries",
]


class EveError(RuntimeError):
    """Raised when the arm's inputs or the aligner's output are not what D-186 specified."""


#: The detector name every table and detection carries. Distinct from A2.1's `profile-hmmer`
#: because A3.2 reports by detector and must be able to take the merge apart again.
DETECTOR = "consensus-mmseqs"

#: Assigned from the instrument, not from the component — the one place A2.3 departs from D-079,
#: which leaves exactly this claim to A2.3 and A2.4 rather than forbidding it.
ELEMENT_KIND = ElementKind.ENDOGENOUS_RETROELEMENT

#: The acceptance rule, fixed by D-186 before any hit was inspected. A conjunction: a hit must
#: satisfy all three. Declared here as data so the artefact and the code cannot disagree about
#: what was applied.
ACCEPT: dict[str, float] = {
    "max_evalue": 1e-10,
    "min_alignment_length": 100,
    "min_identity": 0.70,
}

#: The aligner's output columns, in the order the tool asks for them. Named here so the parser
#: and the invocation cannot drift apart — the failure D-090 cost A4.2 a headline was a column
#: taken by position.
MMSEQS_FORMAT = ("query", "target", "fident", "alnlen", "evalue", "bits")


@dataclasses.dataclass(frozen=True, slots=True)
class Alignment:
    """One alignment the aligner reported, before the acceptance rule is applied."""

    family_id: str
    contig: str
    identity: float
    alignment_length: int
    evalue: float
    bits: float


def consensus_queries(
    library: str | Path, keep: Mapping[str, str] | None = None
) -> Iterator[tuple[str, str, str]]:
    """Yield `(accession, name, consensus)` for each model in the pinned library.

    `keep` restricts to a named subset — the ERV-subtype families with a curated threshold — and
    maps accession to display name, which is the same universe the table's denominator uses. A
    model whose accession is not in `keep` is skipped silently; a model in `keep` that the
    library does not hold is the caller's problem to notice, and `write_queries` reports it.

    Streaming: the library is 2.7 GB and the consensus of one model is read at a time.
    """
    from pyhmmer.plan7 import HMMFile

    with HMMFile(str(library)) as handle:
        for hmm in handle:
            accession = hmm.accession
            if isinstance(accession, bytes):
                accession = accession.decode()
            if accession is None:
                raise EveError(
                    "a model in the library carries no accession; the family cannot be cited, "
                    "and a query with no identity would produce an unattributable detection"
                )
            if keep is not None and accession not in keep:
                continue
            consensus = hmm.consensus
            if not consensus:
                raise EveError(
                    f"{accession} carries no consensus sequence, so the query set cannot be "
                    "derived from it; D-186 rests on every curated model having one"
                )
            name = keep[accession] if keep else accession
            yield accession, name, consensus


def write_queries(
    library: str | Path, destination: str | Path, keep: Mapping[str, str]
) -> dict[str, Any]:
    """Write the query FASTA and report what it covers.

    The header is the accession alone. The family's display name is deliberately left out: the
    aligner's `query` column is parsed back into a `family_id`, and a header carrying anything
    else would make that parse depend on how a name was punctuated.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    residues = 0
    with open(destination, "w") as out:
        for accession, _name, consensus in consensus_queries(library, keep):
            out.write(f">{accession}\n{consensus}\n")
            written.append(accession)
            residues += len(consensus)

    missing = sorted(set(keep) - set(written))
    if missing:
        raise EveError(
            f"{len(missing)} families in the universe are not in the library "
            f"(first: {missing[:3]}): the query set would be smaller than the denominator, "
            "which understates survival without saying so"
        )
    return {
        "path": str(destination),
        "queries": len(written),
        "residues": residues,
        "library": str(library),
    }


def parse_alignments(lines: Iterable[str]) -> Iterator[Alignment]:
    """Parse the aligner's tabular output, by column name rather than by position.

    Identity is normalised to a fraction. The aligner reports it as one, but a build that
    reported percent would otherwise pass the 0.70 cut on anything above 0.7% — a silent
    loosening by two orders of magnitude, which is why this is checked rather than trusted.
    """
    index = {name: i for i, name in enumerate(MMSEQS_FORMAT)}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != len(MMSEQS_FORMAT):
            raise EveError(
                f"alignment row has {len(parts)} fields, expected {len(MMSEQS_FORMAT)} "
                f"({', '.join(MMSEQS_FORMAT)}): {line[:120]!r}"
            )
        identity = float(parts[index["fident"]])
        if identity > 1.0:
            if identity > 100.0:
                raise EveError(f"identity {identity} is neither a fraction nor a percentage")
            identity /= 100.0
        yield Alignment(
            family_id=parts[index["query"]],
            contig=parts[index["target"]],
            identity=identity,
            alignment_length=int(parts[index["alnlen"]]),
            evalue=float(parts[index["evalue"]]),
            bits=float(parts[index["bits"]]),
        )


def accept(alignment: Alignment, rule: Mapping[str, float] = ACCEPT) -> bool:
    """True when an alignment satisfies every condition of D-186's rule."""
    return (
        alignment.evalue <= rule["max_evalue"]
        and alignment.alignment_length >= rule["min_alignment_length"]
        and alignment.identity >= rule["min_identity"]
    )


def detections_for(
    alignments: Iterable[Alignment],
    *,
    record_id: str,
    route: Route,
    registry: str,
    registry_version: str,
    rule: Mapping[str, float] = ACCEPT,
) -> list[Detection]:
    """The accepted alignments of one assembly, as one detection per family.

    **One detection per family, not per alignment.** The record is the genome (D-136), and a
    relic is typically present in many degraded copies — so counting alignments would report the
    copy number of an element as if it were the number of families detected, and a genome with
    one family in two thousand copies would outweigh a genome with twenty families. The
    `hits` column of the table is then "families detected in this genome", which is what
    family-level survival is defined over.

    The best alignment per family decides the score. Identity is the score rather than the bit
    score, so that score and threshold are commensurable and a table can be re-cut on the axis
    the rule is declared on; the per-alignment E-value, length and bit score travel in the
    `.jsonl` so a re-cut on any other axis needs no re-search.
    """
    best: dict[str, Alignment] = {}
    for alignment in alignments:
        if not accept(alignment, rule):
            continue
        current = best.get(alignment.family_id)
        if current is None or alignment.identity > current.identity:
            best[alignment.family_id] = alignment

    return [
        Detection(
            family_id=family_id,
            registry=registry,
            registry_version=registry_version,
            record_id=record_id,
            route=route,
            element_kind=ELEMENT_KIND,
            detector=DETECTOR,
            score=alignment.identity,
            threshold=float(rule["min_identity"]),
        )
        for family_id, alignment in sorted(best.items())
    ]

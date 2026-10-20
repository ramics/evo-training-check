"""Joining the two OpenGenome contig tables, and naming every gap — task A7.4, §A7.

Evo 2 states that OpenGenome "was used in its entirety" and that GTDB 220.0 contributed
"all species' reference genomes that had no previously published (release 214.1) genomes
within their species cluster, resulting in 28,174 additional genomes" (D-130). D-213 makes
the contig accession the key that checks it, with a sequence digest settling whatever the
accessions disagree about.

This module is the join and the classification. It holds no I/O: one side arrives as the
accessions of OpenGenome v1 and the other as the contigs of OpenGenome2's four archives,
and what comes back is counts with intervals and **every** discrepancy under a named cause.
§A7 asks for exactly that and for no residual bucket, so `Cause` is a closed set and a
record that fits none of it raises rather than landing in `other`.

**The four causes, and what evidence each needs.**

* `postdates_release` — a contig on the `added` side that v1 does not have. Expected by
  construction: the addition rule selects genomes with no 214.1 representative, so their
  contigs cannot be in a corpus built from 214.1. Decided from the accession alone.
* `representation` — the sequence is on both sides but under different accessions. Needs
  the digest of the v1 record, so it is decidable only once the targeted digest pass has
  run; until then such a record is `undetermined` and says so.
* `deduplication` — a v1 contig absent from OpenGenome2 whose sequence is present there
  under another accession already counted. The same evidence as `representation`, read in
  the other direction: a dropped duplicate rather than a renamed record.
* `content` — present on one side, and its sequence is not on the other at all. The only
  cause that contradicts "used in its entirety", which is why the three above have to be
  ruled out before it is reached rather than after.

`undetermined` is not a fifth cause. It marks a record whose cause is pending evidence, is
counted separately everywhere, and is never summed into the four.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Iterable, Mapping

__all__ = [
    "Cause",
    "Discrepancy",
    "Join",
    "Side",
    "classify",
    "join",
    "wilson",
]

#: z for a two-sided 95% interval, to the digits `metrics/survival.md` fixes. Rounding it
#: further moves the fourth significant figure of a wide interval, which is enough to make
#: this module's rates and the headline's disagree in a table that prints both.
Z = 1.959963984540054


class Side(str, enum.Enum):
    """Which half of Evo 2's claim an OpenGenome2 archive speaks to."""

    REUSED = "reused"
    ADDED = "added"


class Cause(enum.Enum):
    """Why a contig is on one side and not the other. Closed, per §A7."""

    POSTDATES_RELEASE = "postdates_release"
    REPRESENTATION = "representation"
    DEDUPLICATION = "deduplication"
    CONTENT = "content"
    UNDETERMINED = "undetermined"


#: What each cause does and does not license a reader to conclude.
CAUSE_MEANING: Mapping[Cause, str] = {
    Cause.POSTDATES_RELEASE: (
        "on the added side and absent from v1, which the addition rule predicts. It says "
        "nothing about whether the reused side is complete."
    ),
    Cause.REPRESENTATION: (
        "the same residues on both sides under different accessions. The sequence set is "
        "unchanged; the naming is not, and a comparison keyed on accessions alone would "
        "have called this a loss."
    ),
    Cause.DEDUPLICATION: (
        "a v1 record whose residues are still present in OpenGenome2 under an accession "
        "already counted. Material is not missing; a duplicate is."
    ),
    Cause.CONTENT: (
        "present on one side and its residues are not on the other at all. This is the "
        "only cause that bears on 'used in its entirety'. Each record's evidence names "
        "what its residues were looked for in, which is not always the whole of the "
        "other side — D-217."
    ),
    Cause.UNDETERMINED: (
        "the digest needed to separate a renaming from a real absence has not been read "
        "for this record. Counted apart and never folded into the other four."
    ),
}


def wilson(hits: int, total: int, *, z: float = Z) -> tuple[float, float, float]:
    """`(point, low, high)` for a proportion, by the Wilson score interval.

    The same interval `metrics/survival.md` fixes, written out here in the same algebraic
    form rather than imported from `survival`, so that a test can check the two against
    each other to the last digit instead of one standing in for the other.
    """
    if total <= 0:
        raise ValueError("a rate over no records is not a rate")
    if not 0 <= hits <= total:
        raise ValueError(f"hits {hits} outside 0..{total}")
    n = float(total)
    centre = (hits + z * z / 2) / (n + z * z)
    half = (z / (n + z * z)) * math.sqrt(hits * (n - hits) / n + z * z / 4)
    return hits / total, max(0.0, centre - half), min(1.0, centre + half)


@dataclasses.dataclass(frozen=True, slots=True)
class Discrepancy:
    """One contig present on one side and not the other, with its cause."""

    accession: str
    present_in: str
    cause: Cause
    evidence: str


@dataclasses.dataclass(frozen=True, slots=True)
class Join:
    """What the two tables share and where they part, before any cause is assigned."""

    v1_accessions: int
    reused_accessions: int
    added_accessions: int
    shared_with_reused: int
    only_v1: tuple[str, ...]
    only_reused: tuple[str, ...]
    added_also_in_v1: tuple[str, ...]

    @property
    def reused_coverage(self) -> tuple[float, float, float]:
        """How much of v1 the reused subtree carries, with its interval."""
        return wilson(self.shared_with_reused, self.v1_accessions)

    @property
    def claims_entirety(self) -> bool:
        """Whether "used in its entirety" holds on accessions alone, before causes."""
        return not self.only_v1


def join(
    v1: Iterable[str],
    og2: Iterable[tuple[str, Side]],
) -> Join:
    """Join the two accession sets, keeping the two OpenGenome2 sides apart.

    Args:
        v1: every distinct contig accession in OpenGenome v1's GTDB tier.
        og2: `(accession, side)` for every contig of OpenGenome2's GTDB subtree.

    The sides are kept apart because they answer different questions: the reused side
    tests "in its entirety" and the added side tests the 28,174 figure. Pooling them
    would let material added in 220.0 cover a gap in the reuse, which is the one way this
    comparison could flatter the claim.
    """
    left = set(v1)
    reused: set[str] = set()
    added: set[str] = set()
    for accession, side in og2:
        (reused if side is Side.REUSED else added).add(accession)

    return Join(
        v1_accessions=len(left),
        reused_accessions=len(reused),
        added_accessions=len(added),
        shared_with_reused=len(left & reused),
        only_v1=tuple(sorted(left - reused - added)),
        only_reused=tuple(sorted(reused - left)),
        added_also_in_v1=tuple(sorted(added & left)),
    )


#: What `v1_digests` was read over, when it was read over all of OpenGenome v1.
FULL_SCOPE = "v1"


def classify(
    result: Join,
    *,
    og2_digests: Mapping[str, str],
    v1_digests: Mapping[str, str],
    v1_scope: str = FULL_SCOPE,
) -> tuple[Discrepancy, ...]:
    """Give every discrepancy a cause, or mark it as waiting on evidence.

    Args:
        result: the accession join.
        og2_digests: accession -> sha256 for OpenGenome2's contigs. The in-region pass
            produces this for every contig it reads.
        v1_digests: accession -> sha256 for whichever v1 records have been digested. A
            record missing here is `undetermined`, not absent — the distinction `A7.4`
            rests on, since a missing digest and a missing sequence look the same to a
            join and mean opposite things.
        v1_scope: what `v1_digests` was read over, in words. It travels into the evidence
            of every `content` call made against it, because "these residues are not in
            v1" and "these residues are not in the 158 v1 contigs of the same WGS
            project" are different claims and only one of them was checked. D-217.

    Raises:
        ValueError: if a discrepancy would fall outside the closed set of causes.
    """
    og2_by_digest: dict[str, str] = {}
    for accession, digest in og2_digests.items():
        og2_by_digest.setdefault(digest, accession)
    v1_by_digest: dict[str, str] = {}
    for accession, digest in v1_digests.items():
        v1_by_digest.setdefault(digest, accession)

    out: list[Discrepancy] = []

    for accession in result.only_v1:
        digest = v1_digests.get(accession)
        if digest is None:
            out.append(
                Discrepancy(accession, "v1", Cause.UNDETERMINED, "no digest read for this record")
            )
        elif digest in og2_by_digest:
            twin = og2_by_digest[digest]
            cause = Cause.DEDUPLICATION if twin != accession else Cause.REPRESENTATION
            out.append(Discrepancy(accession, "v1", cause, f"same residues as {twin}"))
        else:
            out.append(Discrepancy(accession, "v1", Cause.CONTENT, "these residues are not in og2"))

    for accession in result.only_reused:
        digest = og2_digests.get(accession)
        if digest is None:
            raise ValueError(
                f"{accession} is in the reused side's accessions but has no digest. The "
                "in-region pass writes a digest for every contig it reads, so a gap here "
                "is a truncated table rather than a finding."
            )
        twin = v1_by_digest.get(digest)
        if twin is not None:
            out.append(
                Discrepancy(accession, "og2", Cause.REPRESENTATION, f"same residues as {twin}")
            )
        elif not v1_digests:
            out.append(Discrepancy(accession, "og2", Cause.UNDETERMINED, "no v1 digests read yet"))
        else:
            out.append(
                Discrepancy(
                    accession, "og2", Cause.CONTENT, f"these residues are not in {v1_scope}"
                )
            )

    for accession in result.added_also_in_v1:
        out.append(
            Discrepancy(
                accession,
                "og2-added",
                Cause.CONTENT,
                "on the added side although v1 already carried it, which the stated "
                "selection rule does not predict",
            )
        )

    expected = len(result.only_v1) + len(result.only_reused) + len(result.added_also_in_v1)
    if len(out) != expected:  # pragma: no cover - the loops above are exhaustive
        raise ValueError(f"{expected} discrepancies went in and {len(out)} came out")
    return tuple(out)


def tally(discrepancies: Iterable[Discrepancy]) -> dict[str, int]:
    """How many of each cause, with every cause present even at zero.

    A cause missing from a report reads as a cause nobody looked for, so the zeroes are
    written down rather than left out.
    """
    counts = {cause.value: 0 for cause in Cause}
    for item in discrepancies:
        counts[item.cause.value] += 1
    return counts

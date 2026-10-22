"""How often each pre-registered viral family also occurs outside viruses — task A4.5.

**The question this answers, and the one it does not.** Every Pfam survival figure in Phase A
counts *families*: a family is detected when a profile from the pinned viral subset matches a
record in the surviving corpus. That licenses the sentence "a member of this protein family is
present". It does not license "viral material is present", because nothing in the search asks
whether the family occurs only in viruses. The family set was selected by Pfam's own
family-level naming (`profiles.select_viral_families`, D-075), which is a statement about what
the family is *named for*, not a measurement of where its members live.

This module measures where they live, against curated data: for each family in the pinned
universe, how many entries of the **reviewed (curated) section of UniProtKB** carry it, split
by whether the entry's own organism lineage is viral. A family with reviewed occurrences and
none of them outside viruses is, at this instrument's resolution, viral-only. A family with
occurrences in cellular organisms is shared, and a detection of it cannot by itself be read as
viral material.

**Three things it is not, stated because each would be an easy misreading.**

* **It is not a correction to any survival figure.** The headline counts stay as published.
  What the measurement does is tell a reader which of two sentences those counts support. No
  number here may be subtracted from a survival count to produce a "real" one.
* **A non-viral occurrence is not proof of independent cellular ancestry.** Host genomes carry
  integrated viral material, and a curated entry for such a protein is annotated to the host
  organism. So "occurs in a cellular proteome" and "is a cellular protein" are different
  claims, and the second does not follow. :func:`endogenous_flag` picks out the subset the
  curators themselves label that way, which bounds the confusion from below without resolving
  it.
* **Reviewed UniProtKB is curated, and it is not a census.** A family absent from it is absent
  from *this* instrument, which is a statement about curation effort, not about biology. Those
  families are reported as unmeasurable in their own class and never folded into either of the
  other two — the D-245 lesson, which is that a denominator assembled out of two different
  kinds of thing is not a denominator.

**Why the reviewed section rather than reference proteomes.** The question asks about curated
material. Reviewed UniProtKB is the curated section of the knowledgebase, it is one file with a
publisher digest, and its Pfam cross-references are the publisher's own join rather than a
threshold this project chose. Reference proteomes would answer a related question — occurrence
per organism rather than per curated entry — and would bring in a second selection step
(which proteomes are reference) that this measurement does not need.

**The version skew, which is measured rather than assumed.** The family universe is pinned to
Pfam 38.2. The reviewed section's Pfam cross-references were computed by the publisher against
whatever Pfam release that UniProtKB release was built on, which is not necessarily 38.2. A
family that 38.2 holds and that release did not would show zero occurrences and read as
viral-only — an error in the direction that flatters the claim. So every family with no
occurrence at all lands in the `unmeasurable` class rather than in `viral_only`, and the size
of that class is reported as the instrument's coverage of the universe.
"""

from __future__ import annotations

import dataclasses
import gzip
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

__all__ = [
    "ENDOGENOUS_MARKERS",
    "HOST_SUBSTRING_WORDS",
    "FamilyBackground",
    "ReviewedEntry",
    "admitting_words",
    "classify",
    "endogenous_flag",
    "iter_entries",
    "measure",
    "summarise",
]

#: The flat-file cross-reference line this measurement reads.
#:
#: Anchored at the line start: `Pfam` also appears inside free text on `CC` lines, and an
#: unanchored match would count a comment as an annotation.
_PFAM_DR = re.compile(rb"^DR   Pfam; (PF\d{5});")

#: The organism-lineage line. The first element of the lineage is the superkingdom-level term,
#: and `Viruses` there is UniProt's own viral annotation — the same annotation ESM3's denylist
#: clause (a) reads (`amazebio.seeds`). Nothing here re-derives it from a taxonomy tool.
_OC = re.compile(rb"^OC   (.+)$")

_OX = re.compile(rb"^OX   NCBI_TaxID=(\d+)")

_KW = re.compile(rb"^KW   (.+)$")

#: Curator phrases that say a cellular entry's protein is integrated viral material.
#:
#: Read from `KW` and `DE` lines, which are the curators' own words. Deliberately short and
#: literal: this bounds the endogenous share from below, and a looser rule would start
#: deciding for the curators which proteins are viral in origin — which is the very judgement
#: this measurement exists to avoid making.
ENDOGENOUS_MARKERS: tuple[bytes, ...] = (
    b"endogenous retrovirus",
    b"endogenous viral element",
    b"provirus",
    b"proviral",
    b"transposable element",
)


@dataclasses.dataclass(frozen=True, slots=True)
class ReviewedEntry:
    """One reviewed UniProtKB entry, reduced to what this measurement reads."""

    accession: str
    #: True when the entry's own organism lineage begins `Viruses`.
    viral: bool
    taxid: str | None
    #: Pfam accessions cross-referenced on this entry, in file order, deduplicated.
    families: tuple[str, ...]
    #: True when the curators' own words mark this as integrated viral material.
    endogenous: bool


def endogenous_flag(text: bytes) -> bool:
    """Whether a curator phrase on this entry says the protein is integrated viral material."""
    lowered = text.lower()
    return any(marker in lowered for marker in ENDOGENOUS_MARKERS)


def iter_entries(path: str | Path) -> Iterator[ReviewedEntry]:
    """Stream the reviewed section, yielding one :class:`ReviewedEntry` per record.

    The file is read once, forward, as bytes. Per-entry state is reset on the `//` terminator
    rather than on `ID`, so a record whose header this parser does not recognise cannot leak
    its families into the next one.
    """
    accession: str | None = None
    viral = False
    taxid: str | None = None
    families: list[str] = []
    seen: set[str] = set()
    descriptive: list[bytes] = []
    lineage_seen = False

    with gzip.open(path, "rb") as handle:
        for line in handle:
            if line.startswith(b"//"):
                if accession is not None:
                    yield ReviewedEntry(
                        accession=accession,
                        viral=viral,
                        taxid=taxid,
                        families=tuple(families),
                        endogenous=endogenous_flag(b" ".join(descriptive)),
                    )
                accession, viral, taxid, lineage_seen = None, False, None, False
                families, seen, descriptive = [], set(), []
                continue
            if line.startswith(b"AC   ") and accession is None:
                accession = line[5:].split(b";")[0].strip().decode("ascii")
            elif line.startswith(b"OC   "):
                if not lineage_seen:
                    first = _OC.match(line)
                    if first is not None:
                        viral = first.group(1).split(b";")[0].strip() == b"Viruses"
                    lineage_seen = True
            elif line.startswith(b"OX   "):
                found = _OX.match(line)
                if found is not None:
                    taxid = found.group(1).decode("ascii")
            elif line.startswith(b"DR   Pfam; "):
                found = _PFAM_DR.match(line)
                if found is not None:
                    family = found.group(1).decode("ascii")
                    if family not in seen:
                        seen.add(family)
                        families.append(family)
            elif line.startswith(b"DE   ") or line.startswith(b"KW   "):
                descriptive.append(line[5:].strip())

    if accession is not None:  # a final record with no terminator
        yield ReviewedEntry(
            accession=accession,
            viral=viral,
            taxid=taxid,
            families=tuple(families),
            endogenous=endogenous_flag(b" ".join(descriptive)),
        )


@dataclasses.dataclass(slots=True)
class FamilyBackground:
    """One family's occurrence in the reviewed section, split by the entry's own lineage."""

    accession: str
    reviewed_viral: int = 0
    reviewed_non_viral: int = 0
    #: Of `reviewed_non_viral`, the entries the curators mark as integrated viral material.
    non_viral_endogenous: int = 0
    #: Distinct organisms behind `reviewed_non_viral`. Breadth, not weight: one over-curated
    #: organism can supply many entries, and a family in one host is not a family in cellular
    #: life generally.
    non_viral_taxa: set[str] = dataclasses.field(default_factory=set)

    @property
    def reviewed_total(self) -> int:
        return self.reviewed_viral + self.reviewed_non_viral

    @property
    def non_viral_fraction(self) -> float | None:
        """Share of this family's reviewed occurrences that sit outside viruses, or None."""
        if self.reviewed_total == 0:
            return None
        return self.reviewed_non_viral / self.reviewed_total

    def row(self) -> dict[str, object]:
        return {
            "accession": self.accession,
            "reviewed_total": self.reviewed_total,
            "reviewed_viral": self.reviewed_viral,
            "reviewed_non_viral": self.reviewed_non_viral,
            "non_viral_endogenous": self.non_viral_endogenous,
            "non_viral_taxa": len(self.non_viral_taxa),
            "non_viral_fraction": self.non_viral_fraction,
            "class": classify(self),
        }


#: Whole words that contain a selection keyword as a substring while naming nothing viral.
#:
#: `macrophage` is the one the data found: the selection rule in `amazebio.profiles` matches
#: `phage` with no word boundary, so seven cellular host proteins are in the pinned universe.
#: Listed here because a reader has to be able to check the claim against the rule rather than
#: take it from prose, and because the list is the thing to extend if another is found.
HOST_SUBSTRING_WORDS: tuple[str, ...] = ("macrophage",)


def admitting_words(text: str, keyword_re: re.Pattern[str]) -> tuple[str, ...]:
    """The whole words in `text` that a selection keyword matched inside, lowercased.

    The selection rule asks only whether a keyword occurs. This asks what it occurred *in*,
    which is what separates `bacteriophage` from `macrophage`. Reported per family in the
    artefact so that the denominator's composition is checkable rather than asserted: a family
    admitted only by a word on :data:`HOST_SUBSTRING_WORDS` names no viral entity.

    The denominator is **not** corrected from this. It was pre-registered before anything was
    searched and every published survival figure rests on it; a cellular family in it
    contributes a near-certain zero and so pushes the survival fraction down, which is the
    conservative direction. Measured and reported, like D-083's blind spot in the other
    direction.
    """
    found: set[str] = set()
    for match in keyword_re.finditer(text):
        start, end = match.start(), match.end()
        while start > 0 and text[start - 1].isalpha():
            start -= 1
        while end < len(text) and text[end].isalpha():
            end += 1
        found.add(text[start:end].lower())
    return tuple(sorted(found))


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def classify(background: FamilyBackground) -> str:
    """One of `unmeasurable`, `viral_only`, `shared` — in that order of precedence.

    `unmeasurable` first, deliberately. A family with no reviewed occurrence at all has not
    been measured, and calling it viral-only would turn an absence of curation into evidence
    for the claim under test.
    """
    if background.reviewed_total == 0:
        return "unmeasurable"
    if background.reviewed_non_viral == 0:
        return "viral_only"
    return "shared"


def measure(
    universe: Iterable[str], entries: Iterable[ReviewedEntry]
) -> dict[str, FamilyBackground]:
    """Accumulate the per-family background over one forward pass of the reviewed section.

    `universe` is the pinned family set; families outside it are ignored rather than counted,
    so the table's rows and the survival figures' denominator are the same set of objects.
    """
    table = {accession: FamilyBackground(accession=accession) for accession in universe}
    for entry in entries:
        for family in entry.families:
            found = table.get(family)
            if found is None:
                continue
            if entry.viral:
                found.reviewed_viral += 1
                continue
            found.reviewed_non_viral += 1
            if entry.endogenous:
                found.non_viral_endogenous += 1
            if entry.taxid is not None:
                found.non_viral_taxa.add(entry.taxid)
    return table


def summarise(table: dict[str, FamilyBackground]) -> dict[str, object]:
    """Class counts over the whole pinned universe, plus the shared families' shape."""
    classes: dict[str, int] = {"unmeasurable": 0, "viral_only": 0, "shared": 0}
    for background in table.values():
        classes[classify(background)] += 1
    shared = [b for b in table.values() if classify(b) == "shared"]
    return {
        "families": len(table),
        "classes": classes,
        # Shared families whose every non-viral occurrence the curators themselves mark as
        # integrated viral material. For these the sharing is the host genome carrying the
        # element, not the family having cellular members, so they are reported apart.
        "shared_endogenous_only": sum(
            1 for b in shared if b.non_viral_endogenous == b.reviewed_non_viral
        ),
        "shared_taxa_median": _median([len(b.non_viral_taxa) for b in shared]),
        "measured": classes["viral_only"] + classes["shared"],
    }

"""The pinned Dfam release A2.3's retroelement arm searches with, and its family universe.

`DESIGN.md` §A2 names Dfam as the registry for endogenous-element detection in host genomes.
D-183 pins which part of it, how families are selected, and what a hit has to beat — all three
fixed before anything was searched. This module is the machine-readable half of that entry.

Three things about the registry shape the code more than its contents do:

**It is a database, not a profile library.** Dfam ships partitioned HDF5, so the profiles have to
be exported by the publisher's own reader (`famdb`, pinned at the version Dfam 4.0's README
attests). This module therefore parses the reader's *output* — HMMER3 text — rather than the
database. That keeps the detection pass independent of the reader: the export happens once, and
what every later run reads is a profile file and this module's selection of it.

**The profiles are nucleotide HMMs.** So `pyhmmer.hmmer.nhmmer` searches them directly against
genomic DNA, with no gene calling and no six-frame translation. That is the right instrument for
a degraded relic no gene caller will call, and it is why no second search engine is pinned.

**Not every family carries a threshold this project may use.** Dfam's general `GA` cutoff is the
threshold D-183 fixed, on the same principle as A2.1's D-076. 8.9% of the LTR class has none, and
those families are excluded from the universe and named rather than given an invented cut. The
per-species `TH` lines are deliberately *not* read: they are a better cutoff for one named
species and unusable as a fixed universe, because a per-species cut makes the denominator differ
from genome to genome.

Parsing is streaming throughout. The curated LTR export is about 3 GB of HMM text, so nothing
here holds a whole file, and :func:`iter_models` yields one record per model while reading lines.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Iterator
from typing import Any

__all__ = [
    "ERV_SUBTYPES",
    "FILES",
    "LTR_TYPE",
    "RELEASE",
    "DfamError",
    "FamilyModel",
    "PinnedFile",
    "classify",
    "is_erv",
    "iter_models",
    "universe",
]


class DfamError(RuntimeError):
    """Raised when the export is not the pinned release's curated HMM component."""


@dataclasses.dataclass(frozen=True, slots=True)
class PinnedFile:
    """One file of the release, with the digest the publisher serves beside it."""

    name: str
    md5: str
    gz_bytes: int
    partition: str
    role: str

    @property
    def url(self) -> str:
        return f"{RELEASE_BASE}/{self.name}"


#: The release D-183 pinned. Dated from the database's own metadata rather than from when it was
#: fetched, so the pin names a release rather than a download.
RELEASE = "4.0"
RELEASE_DATE = "2026-05-22"
RELEASE_BASE = "https://www.dfam.org/releases/Dfam_4.0/families/FamDB"

#: The reader version the publisher attests for this format, quoted in D-183 from the release's
#: own `FamDB/README.txt`. The previous release is format 2.0.0 and this reader refuses it, so the
#: tool and the release are one pin.
FAMDB_VERSION = "3.0.0"

#: Exactly the files A2.3 acquires: the required root metadata and the curated HMM component.
#: The uncurated component is rejected in D-183 — 10-18 GB per partition, no curated thresholds,
#: and a de novo family is not an independent authority on what a retroelement is.
FILES: tuple[PinnedFile, ...] = (
    PinnedFile(
        name="dfam40.0.h5.gz",
        md5="234d177775f1bf3445b1fe146bc6e65e",
        gz_bytes=60_708_386,
        partition="root",
        role="release and partition metadata; required by the reader",
    ),
    PinnedFile(
        name="dfam40.curated.hmm.0.h5.gz",
        md5="c2e0f71f98dd19f0b493f5aa690f5c60",
        gz_bytes=51_796_624,
        partition="root",
        role="curated HMMs, root partition (688 families)",
    ),
    PinnedFile(
        name="dfam40.curated.hmm.1.h5.gz",
        md5="825aaef61fd0329778c34efb545c0356",
        gz_bytes=2_015_629_808,
        partition="Bilateria",
        role="curated HMMs, Bilateria partition (29,933 families)",
    ),
)

#: The Dfam Type the arm's universe is drawn from.
LTR_TYPE = "LTR"

#: The subtypes D-183 makes the arm's headline: integrated retroviruses rather than LTR
#: retrotransposons generally. Counted before any search — 5,565 of the 8,593 curated LTR-class
#: models in the Bilateria partition.
ERV_SUBTYPES = frozenset({"ERV", "ERV1", "ERVK", "ERVL", "ERVL-MaLR", "ERV-Foamy"})

#: What the counts above were measured on, so a re-export that disagrees is visible rather than
#: quietly becoming the new denominator. Checked by `universe`.
EXPECTED_LTR_MODELS = 8593
EXPECTED_WITHOUT_THRESHOLD = 762

#: The ERV subtypes' two counts, which are **not** the same number and must not be conflated.
#: `IN_CLASS` is how many ERV-subtype models the class holds; `SEARCHABLE` is how many of those
#: carry a curated threshold and are therefore actually searched. D-183 recorded only the first
#: and called it the arm's headline, which D-185 corrects: 145 ERV-subtype models have no general
#: GA cutoff, so the searched universe is the smaller figure. Both are reported, because the
#: difference between them is the arm's blind spot restricted to the families it cares about.
EXPECTED_ERV_IN_CLASS = 5565
EXPECTED_ERV_SEARCHABLE = 5420


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyModel:
    """One Dfam family as the export states it.

    `threshold` is the general `GA` cutoff, or None where the family has none — which is a
    property to report rather than a gap to fill (D-183).
    """

    accession: str
    name: str
    type: str
    subtype: str | None
    length: int
    threshold: float | None

    @property
    def is_erv(self) -> bool:
        return is_erv(self.subtype)

    @property
    def classification(self) -> str:
        return f"{self.type}/{self.subtype}" if self.subtype else self.type

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.accession,
            "name": self.name,
            "type": self.type,
            "subtype": self.subtype,
            "classification": self.classification,
            "model_length": self.length,
            "threshold": self.threshold,
            "is_erv": self.is_erv,
        }


def classify(name: str) -> tuple[str, str | None]:
    """Split an exported model name into its Dfam type and subtype.

    The export is taken with the reader's `--include-class-in-name`, so a name reads
    `HERV16#LTR/ERVL` — the family name, `#`, then the RepeatMasker-style classification. A name
    with no `#` has no classification and is returned as such rather than guessed at.

    Taken from the class string the export carries rather than through the reader's own `--class`
    filter, for the reason D-075 derived Pfam's viral subset in this project's code and D-166
    re-derived A2.2's fold universe: a selection that is the audit's own is one a reviewer can
    check, and a flag's semantics are not.
    """
    _, _, classification = name.partition("#")
    if not classification:
        return "", None
    kind, _, subtype = classification.partition("/")
    return kind, subtype or None


def is_erv(subtype: str | None) -> bool:
    """True for the subtypes D-183 counts as integrated retroviruses."""
    return subtype in ERV_SUBTYPES


def iter_models(lines: Iterable[str]) -> Iterator[FamilyModel]:
    """Yield one :class:`FamilyModel` per model in an HMMER3 text export.

    Streaming, because the curated LTR export is about 3 GB.

    Only the general `GA` line is read as a threshold. A `TH` line carries a per-species cutoff
    and is skipped — reading one as the family's threshold would silently make the cut depend on
    which species happened to be listed first, which is the failure mode D-183 rejects
    per-species thresholds to avoid.
    """
    name: str | None = None
    accession: str | None = None
    length: int | None = None
    threshold: float | None = None

    def flush() -> Iterator[FamilyModel]:
        if name is None:
            return
        if accession is None or length is None:
            raise DfamError(
                f"model {name!r} has no {'ACC' if accession is None else 'LENG'} line; the export "
                "is not a complete HMMER3 file and a family without an accession cannot be cited"
            )
        kind, subtype = classify(name)
        yield FamilyModel(
            accession=accession,
            name=name.partition("#")[0],
            type=kind,
            subtype=subtype,
            length=length,
            threshold=threshold,
        )

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("//"):
            yield from flush()
            name = accession = length = threshold = None
            continue
        if line.startswith("NAME "):
            name = line[5:].strip()
        elif line.startswith("ACC "):
            accession = line[4:].strip()
        elif line.startswith("LENG "):
            length = int(line[5:].strip())
        elif line.startswith("GA "):
            # `GA    30.15;` — one value, semicolon-terminated. Nucleotide models carry a single
            # score where a protein model would carry sequence and domain cutoffs.
            threshold = float(line[3:].strip().rstrip(";").split()[0])
    yield from flush()


def universe(models: Iterable[FamilyModel], *, strict: bool = True) -> dict[str, Any]:
    """Partition an export into the arm's searchable universe and its declared exclusions.

    Returns the registry artefact's contents: the families that will be searched, the families
    excluded for want of a curated threshold (by accession, per D-183), and the subtype
    composition both counts rest on.

    `strict` re-checks the three counts D-183 recorded. A re-export that disagrees is a changed
    denominator, and a changed denominator that nothing notices is how a figure stops meaning
    what its entry says it means — the failure D-074 recorded. Pass `strict=False` only to
    measure a deliberately different selection.
    """
    ltr = [m for m in models if m.type == LTR_TYPE]
    searchable = [m for m in ltr if m.threshold is not None]
    excluded = [m for m in ltr if m.threshold is None]
    erv_in_class = [m for m in ltr if m.is_erv]
    erv = [m for m in searchable if m.is_erv]

    composition: dict[str, int] = {}
    for model in ltr:
        composition[model.classification] = composition.get(model.classification, 0) + 1

    if strict:
        problems = []
        if len(ltr) != EXPECTED_LTR_MODELS:
            problems.append(f"{len(ltr)} LTR-class models, D-183 measured {EXPECTED_LTR_MODELS}")
        if len(excluded) != EXPECTED_WITHOUT_THRESHOLD:
            problems.append(
                f"{len(excluded)} without a general threshold, D-183 measured "
                f"{EXPECTED_WITHOUT_THRESHOLD}"
            )
        if len(erv_in_class) != EXPECTED_ERV_IN_CLASS:
            problems.append(
                f"{len(erv_in_class)} ERV-subtype models in the class, D-183 measured "
                f"{EXPECTED_ERV_IN_CLASS}"
            )
        if len(erv) != EXPECTED_ERV_SEARCHABLE:
            problems.append(
                f"{len(erv)} searchable ERV-subtype models, D-185 measured "
                f"{EXPECTED_ERV_SEARCHABLE}"
            )
        if problems:
            raise DfamError(
                "the export does not match the universe D-183 pinned: "
                + "; ".join(problems)
                + ". The denominator has changed, so the figures this registry produces would "
                "not mean what that entry says they mean."
            )

    return {
        "registry": "dfam-curated-ltr",
        "registry_version": RELEASE,
        "release_date": RELEASE_DATE,
        "famdb_version": FAMDB_VERSION,
        "decision_ref": "D-183",
        "ltr_models": len(ltr),
        "searchable": len(searchable),
        # Two ERV counts, never one. `erv_models` is what is searched; `erv_models_in_class` is
        # what the class holds. Their difference is the blind spot restricted to the families the
        # arm cares about, and reporting only the larger one would overstate the search (D-185).
        "erv_models": len(erv),
        "erv_models_in_class": len(erv_in_class),
        "erv_excluded_no_threshold": len(erv_in_class) - len(erv),
        "excluded_no_threshold": len(excluded),
        "excluded_accessions": sorted(m.accession for m in excluded),
        "composition": dict(sorted(composition.items(), key=lambda kv: (-kv[1], kv[0]))),
        "erv_subtypes": sorted(ERV_SUBTYPES),
        "threshold_policy": (
            "Dfam's own general GA cutoff, per model. A family with no general GA is excluded "
            "from the universe and named, never given a threshold this project invented (D-183)."
        ),
        "denominator": {
            "authority": (
                "Dfam 4.0's curated HMM component, selected to Type LTR by this project's own "
                "rule over the export's class string (D-183)."
            ),
            "restriction": (
                "Never quote this as 'the fraction of retroelement families': the universe is "
                "the curated component only, excludes the 762 LTR-class families with no curated "
                "threshold, and spans LTR retrotransposons as well as integrated retroviruses. "
                "Quote the ERV subtypes and the other LTR subtypes separately, each naming its "
                "own count."
            ),
            "comparable_across_registries": False,
        },
    }

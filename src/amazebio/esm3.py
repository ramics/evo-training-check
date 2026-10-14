"""What ESM3-open states about its training data, and what a proxy can pin.

Why this exists in this shape
-----------------------------

A1.5 expected the §A0 under-specification finding to be that ESM3 names its source
databases without versions. That expectation came from the filter appendix, which
writes the corpus as "the full set of training databases, (including PDB, UniRef,
MGnify, and JGI)" — four bare names. It is wrong, and the correction is the first
result here: the pretraining-data appendix and Table S3 state a release for every
component, and for the two largest sequence components they are exact, retrievable
releases (DECISIONS.md D-032).

So the under-specification sits elsewhere, and this module is where it is recorded
rather than guessed at:

* **UniRef's tier is unstated.** "UniRef release 2023 02" names a release, not which
  of its three tiers was parsed; the release holds 60.5M, 170.7M and 351.0M clusters
  depending on the answer. The clustering columns of Table S3 do not settle it,
  because they report ESM3's own mmseqs clustering rather than UniRef's tiers.
* **The counts do not reconcile.** Table S3's post-filter figures fall short of the
  publishers' own release-note counts by more, in each of two components separately,
  than the filter is reported to have removed in total. :func:`reconcile` is that
  arithmetic; nothing here resolves it, because published text cannot.
* **JGI's pin is a date, and the two statements of it differ by a day.** The prose
  says July 31st 2023 and Table S3 says July 30th 2023. Either way IMG/M serves no
  dated snapshot, so this component is the one that cannot be pinned at all.

Every figure below is transcribed from the preprint with its locator, so a reader can
check the transcription against the source rather than trusting this file. The
publishers' counts are transcribed from release notes stored under
`policies/captures/`, whose checksums `tools/policies.py` verifies.

What this module deliberately does not do
-----------------------------------------

It computes no in-scope/out-of-scope share. That is A4.3's result, and A4.3 fixes its
share metrics with A3.1 first; a share computed here would pre-empt both. The table is
the input to that, not the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOURCE = "S-ESM3-PREPRINT"

# The filter appendix's scope list. Quoted in policies/esm3-open.md §2; the word
# "including" is why `in_filter_scope` is a tri-state and not a boolean.
FILTER_SCOPE_NAMED = ("PDB", "UniRef", "MGnify", "JGI")

# "This filter removes a total of 10.6M sequences across all training sets."
# [S-ESM3-PREPRINT, Appendix A.6.1, p67]
STATED_TOTAL_REMOVED = 10_600_000

# Table S3's caption, which is what makes the reconciliation in `reconcile` legitimate:
# the per-component counts are post-filter, so a shortfall against the publisher's own
# count is a quantity the filter could in principle explain.
# "Numbers are derived after dataset filtering." [S-ESM3-PREPRINT, Table S3, p40]
STATED_COUNTS_ARE_POST_FILTER = True

# Table S3 reports counts to the nearest million ("156M"), so every gap computed
# against an exact publisher count carries this much slack before it means anything.
STATED_COUNT_PRECISION = 1_000_000


@dataclass(frozen=True)
class Component:
    """One component of ESM3's stated pretraining corpus.

    Fields are transcriptions, not judgements, except `retrievability` and `proxy`,
    which are this task's calls and are argued in `policies/esm3-open.md`.
    """

    name: str
    track: str  # "sequence" | "structure"
    stated_release: str  # verbatim as the paper states it
    locator: str  # where in S-ESM3-PREPRINT that statement sits
    in_filter_scope: bool | None  # None: not addressed either way by the scope list
    # Table S3, p40. `None` where the table gives none.
    clustering_level: str | None
    clustering_count: int | None
    expansion_level: str | None
    expansion_count: int | None
    tokens_b: float | None
    # Table S4, p40.
    unique_samples_m: float | None
    unique_tokens_m: int | None
    # This task's verdict on whether the stated release can be obtained as stated.
    #   "pinned"          — the exact stated release is served with a published checksum
    #   "substituted"     — obtainable, but not at the stated granularity; proxy differs
    #   "not-reproducible"— no snapshot corresponding to the stated pin exists
    retrievability: str
    proxy: str | None
    note: str


COMPONENTS: tuple[Component, ...] = (
    Component(
        name="UniRef",
        track="sequence",
        stated_release="2023_02",
        locator="Appendix A.2.1.1, p37; Table S3, p40",
        in_filter_scope=True,
        clustering_level="70%",
        clustering_count=83_000_000,
        expansion_level="90%",
        expansion_count=156_000_000,
        tokens_b=54.6,
        unique_samples_m=133.0,
        unique_tokens_m=40_177,
        retrievability="pinned",
        proxy="UniRef 2023_02 as published, whole archive, md5 verified in stream",
        note=(
            "The release is exact and still served, with a published md5 over the whole "
            "211,819,312,677-byte archive. The tier is not stated: 'the official UniRef "
            "website' serves UniRef50, UniRef90 and UniRef100, and parsing any one of them "
            "is consistent with the sentence. Staging the archive rather than a tier is what "
            "makes the proxy independent of that unresolved question."
        ),
    ),
    Component(
        name="MGnify",
        track="sequence",
        stated_release="2023_02 (MGnify90)",
        locator="Appendix A.2.1.1, p37; Table S3, p40",
        in_filter_scope=True,
        clustering_level="70%",
        clustering_count=372_000_000,
        expansion_level="90%",
        expansion_count=621_000_000,
        tokens_b=105.5,
        unique_samples_m=406.0,
        unique_tokens_m=65_780,
        retrievability="pinned",
        proxy="MGnify protein database 2023_02, cluster representatives, md5 per file",
        note=(
            "'MGnify90' names the release's 90%-clustered product, which the release serves "
            "as one 83,473,342,442-byte mgy_clusters.fa.gz with a published md5. The full "
            "protein set behind it is 30 further files and 362 GB. Which of the two was "
            "parsed is not stated, and the counts do not settle it either: see `reconcile`. "
            "This is also the component with no taxonomic annotation at all, which is why an "
            "alignment-based filter is the only kind that could reach it."
        ),
    ),
    Component(
        name="JGI",
        track="sequence",
        stated_release="all non-restricted studies available in JGI on July 31st, 2023",
        locator="Appendix A.2.1.1, p37; Table S3, p40",
        in_filter_scope=True,
        clustering_level="70%",
        clustering_count=2_029_000_000,
        expansion_level=None,
        expansion_count=None,
        tokens_b=256.0,
        unique_samples_m=2_039.0,
        unique_tokens_m=265_070,
        retrievability="not-reproducible",
        proxy=None,
        note=(
            "The largest sequence component — a third of all unique training tokens — and the "
            "one that cannot be pinned. The cited system is IMG/M v.7, which serves no dated "
            "snapshot and no checksummed release, and 'non-restricted' is a per-study access "
            "state that changes over time, so even the same date queried later need not return "
            "the same set. Table S3 states the date as July 30th where the prose says July "
            "31st. No proxy is proposed: a different metagenomic collection would not be this "
            "component, and substituting one would misrepresent the audit's coverage."
        ),
    ),
    Component(
        name="OAS",
        track="sequence",
        stated_release="all sequences available on July 30th, 2023",
        locator="Appendix A.2.1.1, p37; Table S3, p40",
        in_filter_scope=None,
        clustering_level="95%",
        clustering_count=1_192_000_000,
        expansion_level=None,
        expansion_count=None,
        tokens_b=132.0,
        unique_samples_m=203.0,
        unique_tokens_m=22_363,
        retrievability="not-reproducible",
        proxy=None,
        note=(
            "Antibody sequences. Not named in the filter's scope list, and the prose states no "
            "date where Table S3 gives one. OAS is served as a per-study download set that "
            "grows; there is no dated snapshot."
        ),
    ),
    Component(
        name="PDB",
        track="structure",
        stated_release="all chains available on RCSB prior to May, 1st, 2020",
        locator="Appendix A.2.1.5, p38; Table S3, p40",
        in_filter_scope=True,
        clustering_level=None,
        clustering_count=203_000,
        expansion_level=None,
        expansion_count=None,
        tokens_b=0.054,
        unique_samples_m=0.2,
        unique_tokens_m=55,
        retrievability="substituted",
        proxy="RCSB chains by deposition date, X-ray, resolution cutoff applied as stated",
        note=(
            "The only component whose pin is a reproducible query rather than a release: "
            "deposition dates do not change. Two caveats keep it a substitution rather than a "
            "pin. Table S3's row states the date filter alone, where the prose adds X-ray "
            "crystallography and a 9 angstrom resolution cutoff — the table's wording would "
            "select a larger set. And entries obsoleted since 2020 are no longer served, so "
            "the set reconstructed today is a subset of the set available then."
        ),
    ),
    Component(
        name="PDB Clustered",
        track="structure",
        stated_release="all chains available on RCSB prior to May, 1st, 2020",
        locator="Table S3, p40",
        in_filter_scope=True,
        clustering_level="70%",
        clustering_count=46_000,
        expansion_level="100%",
        expansion_count=100_000,
        tokens_b=0.027,
        unique_samples_m=None,
        unique_tokens_m=None,
        retrievability="substituted",
        proxy="derived from the PDB component by clustering",
        note=(
            "A second Table S3 row over the same source data, clustered. Table S4 does not "
            "break it out separately, so its unique-sample figures are absent rather than zero."
        ),
    ),
    Component(
        name="AlphaFoldDB",
        track="structure",
        stated_release="v4",
        locator="Appendix A.2.1.5, p38; Table S3, p40",
        in_filter_scope=None,
        clustering_level="70%",
        clustering_count=36_000_000,
        expansion_level="90%",
        expansion_count=69_000_000,
        tokens_b=40.5,
        unique_samples_m=68.0,
        unique_tokens_m=20_510,
        retrievability="substituted",
        proxy=None,
        note=(
            "Stated exactly, as v4, and not named in the filter's scope list. Predicted "
            "structures of UniProt sequences: whatever the filter did or did not do here, the "
            "underlying sequences are UniProt's, so a viral sequence excluded from the UniRef "
            "component could re-enter through this one. Whether it was filtered is unstated."
        ),
    ),
    Component(
        name="ESMAtlas",
        track="structure",
        stated_release="v0, v2023_02",
        locator="Appendix A.2.1.5, p38; Table S3, p40",
        in_filter_scope=None,
        clustering_level="70%",
        clustering_count=87_000_000,
        expansion_level="90%",
        expansion_count=179_000_000,
        tokens_b=23.5,
        unique_samples_m=168.0,
        unique_tokens_m=38_674,
        retrievability="substituted",
        proxy=None,
        note=(
            "Stated exactly, and not named in the filter's scope list. Predicted structures of "
            "MGnify metagenomic sequences, so the same re-entry question as AlphaFoldDB applies, "
            "over the component that carries no taxonomic annotation."
        ),
    ),
)

# Table S4's inverse-folding rows, kept apart from COMPONENTS because they are not
# databases: they are sequences this pipeline generated from structures. They matter to
# the audit out of proportion to their size, and the reason is in `policies/esm3-open.md`
# §8 — a generated sequence is in no database, so an MMseqs query against the training
# databases cannot reach it.
INVERSE_FOLDED = (
    {"name": "AFDB inverse folded", "unique_samples_m": 111.0, "unique_tokens_m": 33_300},
    {"name": "ESMAtlas inverse folded", "unique_samples_m": 251.0, "unique_tokens_m": 57_730},
)

# Table S4's own totals, transcribed so a consistency check is possible without
# re-deriving them.
STATED_TOTALS = {
    "sequence_samples_m": 3_143.0,
    "sequence_tokens_m": 484_441,
    "structure_samples_m": 236.0,
    "structure_tokens_m": 177_710,
    "annotation_samples_m": 539.0,
    "annotation_tokens_m": 105_957,
    "total_unique_training_tokens_m": 768_109,
}


# --------------------------------------------------------------------------- #
# What the publishers say about the same releases
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PublisherCount:
    """A count of a release taken from the publisher's own release note.

    `same_granularity_as` is what makes a comparison legitimate. ESM3's Table S3 reports
    counts at its own clustering levels, so only a publisher count of the *same*
    granularity can be subtracted from one: UniRef90's cluster count is comparable with a
    stated "90%" count, UniRef100's is not, and reading the difference between 156M and
    UniRef100's 351M as a filter's work would be arithmetic with no claim behind it.
    Non-comparable counts are kept, because the spread between them is what the unstated
    tier costs a reconstruction, but they carry no verdict.
    """

    component: str
    level: str  # the granularity this count is of
    count: int
    source: str  # capture under policies/captures/
    same_granularity_as: str | None = None  # a Component.expansion_level, if any
    note: str = ""


PUBLISHER_COUNTS: tuple[PublisherCount, ...] = (
    PublisherCount(
        "UniRef",
        "UniRef50",
        60_479_070,
        "policies/captures/uniref-2023_02-uniref50.release_note",
    ),
    PublisherCount(
        "UniRef",
        "UniRef90",
        170_669_877,
        "policies/captures/uniref-2023_02-uniref90.release_note",
        same_granularity_as="90%",
        note="UniRef's own 90% tier, the one reading of 'UniRef release 2023 02' under "
        "which Table S3's 90% column is a published count rather than ESM3's own.",
    ),
    PublisherCount(
        "UniRef",
        "UniRef100",
        350_950_053,
        "policies/captures/uniref-2023_02-uniref100.release_note",
    ),
    PublisherCount(
        "MGnify",
        "all sequences",
        2_973_257_435,
        "policies/captures/mgnify-2023_02-README.txt",
    ),
    PublisherCount(
        "MGnify",
        "90% clusters",
        729_215_663,
        "policies/captures/mgnify-2023_02-README.txt",
        same_granularity_as="90%",
        note="MMseqs/linclust at 90% coverage and 90% identity, per the release README. "
        "Not the same algorithm or coverage mode as the mmseqs2 flags ESM3 states, which "
        "is why this comparison bounds the gap rather than explaining it.",
    ),
)


# --------------------------------------------------------------------------- #
# Pins for what a proxy would stage
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FilePin:
    """One file of a staged component, with the verification its publisher publishes."""

    name: str
    url: str
    bytes: int
    md5: str


# The UniRef side of the proxy is the same archive shape A1.3 staged for ESM-2, one
# release later, so `amazebio.uniref` stages it unchanged: see UNIREF_2023_02 there.
# Repeated here only as the pin a manifest records.
UNIREF_2023_02_ARCHIVE = FilePin(
    name="uniref2023_02.tar.gz",
    url=(
        "https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/"
        "release-2023_02/uniref/uniref2023_02.tar.gz"
    ),
    bytes=211_819_312_677,
    md5="353681f464572bb199fa032f714d4669",
)

MGNIFY_2023_02_BASE = "https://ftp.ebi.ac.uk/pub/databases/metagenomics/peptide_database/2023_02"

# The 90%-clustered product, which is what "MGnify90" names. Its md5 is the publisher's,
# transcribed from the stored md5sum.txt capture; the size is from the server.
MGNIFY_2023_02_CLUSTERS = FilePin(
    name="mgy_clusters.fa.gz",
    url=f"{MGNIFY_2023_02_BASE}/mgy_clusters.fa.gz",
    bytes=83_473_342_442,
    md5="332d36d2a943bdb769237a03e050ed03",
)

# The full protein set, 30 files, pinned by the same published md5sum.txt. Listed rather
# than fetched so a staging run can be costed before it is authorised.
MGNIFY_2023_02_MANIFEST = "policies/captures/mgnify-2023_02-md5sum.txt"
MGNIFY_2023_02_PROTEINS_BYTES = 361_962_755_462
MGNIFY_2023_02_PROTEINS_FILES = 30


def reconcile() -> list[dict[str, Any]]:
    """Set Table S3's post-filter counts against the publishers' own counts.

    Returned as rows rather than a verdict, and only rows of matching granularity carry
    one. Where `comparable` is True the two numbers count the same kind of thing, so the
    difference is a real shortfall in a stated corpus against the release it names.
    Where it is False the row is context: the spread across UniRef's three tiers is what
    the unstated tier costs, not a quantity anything removed.

    `exceeds_stated_removal` is the finding. Where it is True, that one component's
    shortfall is larger than the 10.6M the filter is reported to have removed across
    every component together, so the filter cannot account for it — and since published
    text does not say whether the remainder is ESM3's own re-clustering or removal the
    filter description omits, the reported 10.6M cannot be used to validate a
    reconstruction.
    """
    rows: list[dict[str, Any]] = []
    for comp in COMPONENTS:
        if comp.expansion_count is None:
            continue
        for pub in PUBLISHER_COUNTS:
            if pub.component != comp.name:
                continue
            comparable = pub.same_granularity_as == comp.expansion_level
            gap = pub.count - comp.expansion_count
            rows.append(
                {
                    "component": comp.name,
                    "stated_level": comp.expansion_level,
                    "stated_count": comp.expansion_count,
                    "publisher_level": pub.level,
                    "publisher_count": pub.count,
                    "comparable": comparable,
                    "gap": gap if comparable else None,
                    "gap_fraction": gap / pub.count if comparable else None,
                    "exceeds_stated_removal": (
                        gap - STATED_COUNT_PRECISION > STATED_TOTAL_REMOVED if comparable else None
                    ),
                    "publisher_source": pub.source,
                    "note": pub.note,
                }
            )
    return rows


def unstated() -> list[dict[str, str]]:
    """The §A0 findings: what a reconstruction has to choose because nobody stated it.

    One entry per thing a reconstruction cannot read off the source. `consequence` says
    what goes wrong downstream if it is guessed silently, because that is the part a
    write-up needs and the part that is lost if these are left as prose.
    """
    return [
        {
            "id": "esm3-uniref-tier",
            "finding": (
                "Which UniRef tier was parsed is not stated. The release holds three, at "
                "60,479,070, 170,669,877 and 350,950,053 clusters."
            ),
            "evidence": "Appendix A.2.1.1, p37",
            "consequence": (
                "The corpus denominator differs by 5.8x across the three readings, so any "
                "survival rate expressed as a fraction of 'the UniRef component' is "
                "undefined until the tier is chosen and stated."
            ),
        },
        {
            "id": "esm3-mgnify-granularity",
            "finding": (
                "'MGnify90' is the release's 90%-clustered product by name, but Table S3 "
                "reports its own 70% and 90% clustering levels over it, which the release "
                "does not provide. Whether the clustered product or the full 2,973,257,435 "
                "sequences behind it was parsed is not stated."
            ),
            "evidence": "Appendix A.2.1.1, p37; Table S3, p40",
            "consequence": (
                "A 4.1x difference in the component's size, and it decides whether staging "
                "needs 83 GB or 362 GB."
            ),
        },
        {
            "id": "esm3-counts-do-not-reconcile",
            "finding": (
                "Table S3's post-filter counts fall short of the publishers' release-note "
                "counts by 14.7M clusters for UniRef and 108.2M for MGnify, against a filter "
                "reported to remove 10.6M sequences across every component together."
            ),
            "evidence": "Table S3, p40; Appendix A.6.1, p67",
            "consequence": (
                "The gap is either ESM3's own re-clustering or removal the filter description "
                "does not cover, and published text does not distinguish them. So the "
                "reported 10.6M cannot be used to validate a reconstruction, which "
                "policies/corpora.md section 5 had proposed as the nearest available "
                "substitute for a conformance re-execution."
            ),
        },
        {
            "id": "esm3-jgi-unpinnable",
            "finding": (
                "JGI is pinned by a date, stated as July 31st 2023 in prose and July 30th "
                "2023 in Table S3, over 'non-restricted studies' — a per-study access state "
                "that changes. IMG/M serves no dated snapshot."
            ),
            "evidence": "Appendix A.2.1.1, p37; Table S3, p40",
            "consequence": (
                "A third of all unique training tokens is unreconstructible, and every ESM3 "
                "coverage figure is a fraction of the components that could be staged, not "
                "of the corpus."
            ),
        },
        {
            "id": "esm3-filter-scope-list-not-exhaustive",
            "finding": (
                "The filter's scope is 'the full set of training databases, (including PDB, "
                "UniRef, MGnify, and JGI)'. OAS, AlphaFoldDB and ESMAtlas are training "
                "databases that the list does not name, and together they are 439M of the "
                "3,379M unique samples in Table S4."
            ),
            "evidence": "Appendix A.6.1, p67; Table S4, p40",
            "consequence": (
                "Whether those components were filtered is unstated, so A4.3 must report them "
                "as not addressed rather than as in or out of scope."
            ),
        },
        {
            "id": "esm3-inverse-folded-sequences",
            "finding": (
                "362M of the sequences ESM3 trained on were generated by an inverse-folding "
                "model from PDB, AlphaFoldDB and ESMAtlas structures, not drawn from any "
                "database. The filter is described as an MMseqs query against the training "
                "databases."
            ),
            "evidence": "Appendix A.2.1.3, p38; Table S4, p40",
            "consequence": (
                "A generated sequence is in no database, so a query against the databases "
                "cannot remove it. Whether the generated set was filtered, or the structures "
                "it was generated from were, is unstated."
            ),
        },
    ]


def scope_table() -> list[dict[str, Any]]:
    """COMPONENTS as rows, for the artefact A4.3 consumes. No shares: see module docstring."""
    return [
        {
            "component": c.name,
            "track": c.track,
            "stated_release": c.stated_release,
            "locator": c.locator,
            "in_filter_scope": c.in_filter_scope,
            "clustering_level": c.clustering_level,
            "clustering_count": c.clustering_count,
            "expansion_level": c.expansion_level,
            "expansion_count": c.expansion_count,
            "tokens_b": c.tokens_b,
            "unique_samples_m": c.unique_samples_m,
            "unique_tokens_m": c.unique_tokens_m,
            "retrievability": c.retrievability,
            "proxy": c.proxy,
            "note": c.note,
        }
        for c in COMPONENTS
    ]

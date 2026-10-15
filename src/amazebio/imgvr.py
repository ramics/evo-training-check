"""The IMG/VR releases, and which one "IMG/VR v4" names.

This is task A1.7: acquiring the **input** side of the only published exclusion procedure in
this audit. A1.2 staged both Evo releases, which are the filter's output; A7.1 then re-executed
the published predicates against that output and could reach three of six rules, because the
other three read IMG/VR metadata that does not travel with either release (D-047, D-049).

Two facts about the publisher's distribution shape everything here, and the second is a finding.

**The inventory is public; the bytes are not.** JGI's data portal serves a complete file listing
for the IMG/VR dataset — every file, its size, its release date, and *the publisher's own
md5sum* — without authentication. Downloading any of those files returns HTTP 401,
`{"detail":"Authentication credentials were not provided."}`. So the pin can be established
before the data is in hand, which is why :data:`RELEASES` carries checksums for files this
project has never held: when a credential exists, staging verifies against a figure recorded
before anyone went looking for it. That is a stronger pin than one taken at download time, and
it is the A1.3 standard (D-026, D-027) rather than the weaker self-attestation D-040 had to
settle for.

**"IMG/VR v4" names two releases, not one.** Evo 1's data availability section cites "the IMG/VR
v4 database (Camargo et al., 2023)" and nothing more specific. The publisher ships IMG/VR in
folders identified by release date, and *two* of them answer to v4: **2022-09-20** and
**2022-12-20**. They are not alternative copies of one thing. Comparing the publisher's md5sums:

* the nucleotide sets are **byte-identical**, in both the full and high-confidence variants;
* the host-information tables are **byte-identical**;
* the sequence-information tables **differ**, in both variants;
* the protein sets and the READMEs differ.

The sequence-information table is where the confidence label and the vOTU assignment live. So
the two releases agree on exactly what Evo 1's host-count rule reads and on the sequences
themselves, and disagree on exactly what its high-confidence gate and its vOTU representative
read — two of the three rules A7.1 could not run. Which release is cited therefore cannot be
treated as a detail, and the citation does not resolve it. See DECISIONS.md D-052.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterable, Sequence

__all__ = [
    "DOWNLOAD_BASE",
    "EUKARYOTIC_DOMAINS",
    "FILE_ROLES",
    "HOST_COLUMNS",
    "PROKARYOTIC_DOMAINS",
    "RELEASES",
    "SEQ_COLUMNS",
    "V4_CANDIDATES",
    "Release",
    "ReleaseFile",
    "UvigNotPackable",
    "collision_free",
    "conformance_inputs",
    "differs_between",
    "download_request",
    "host_class",
    "host_domain",
    "release_on",
    "split_uvig",
    "uvig_fallback_key",
    "uvig_join_key",
    "uvig_key",
    "votu_id",
]


#: What each published file is for, in this audit's terms. The roles are the point: a
#: conformance re-execution of Evo 1's procedure needs metadata and not sequence, and naming
#: that here keeps a 48 GB nucleotide download from being staged because it was in the folder.
FILE_ROLES = {
    "sequence_information": (
        "Per-sequence characteristics: the confidence label Evo 1's first rule gates on, the "
        "vOTU assignment its second rule deduplicates by, and the taxonomic affiliation. The "
        "single most important file in this release for Phase A."
    ),
    "host_information": (
        "Predicted host per sequence. What the prokaryotic-host count rule reads, and the only "
        "source for it: no host assignment travels with either Evo release."
    ),
    "nucleotides": (
        "Viral genome and contig sequence. Not needed for any conformance check — those are "
        "set operations over accessions and metadata. Staged only if a later task needs the "
        "sequence itself."
    ),
    "proteins": "Predicted protein sequence. No Phase A task reads it.",
    "readme": "The publisher's own release note. Establishes what the release is.",
}


@dataclasses.dataclass(frozen=True)
class ReleaseFile:
    """One published file, pinned by the publisher's own md5 before we hold the bytes."""

    name: str
    role: str
    bytes: int
    md5: str
    #: True for the variant JGI pre-filters to high-confidence records. Evo 1's first rule
    #: *selects* high-confidence records, so auditing that rule needs the unfiltered variant:
    #: the high-confidence file cannot show a record the gate should have removed, because
    #: every record in it passes the gate by construction.
    high_confidence: bool
    #: The publisher's analysis directory, which is how a file is addressed in their portal.
    directory: str


@dataclasses.dataclass(frozen=True)
class Release:
    """One dated IMG/VR release."""

    date: str
    version: str
    files: tuple[ReleaseFile, ...]
    note: str = ""

    def by_role(self, role: str, *, high_confidence: bool | None = None) -> tuple[ReleaseFile, ...]:
        return tuple(
            f
            for f in self.files
            if f.role == role and (high_confidence is None or f.high_confidence == high_confidence)
        )

    @property
    def total_bytes(self) -> int:
        return sum(f.bytes for f in self.files)


def _f(name: str, role: str, b: int, md5: str, hc: bool, d: str) -> ReleaseFile:
    return ReleaseFile(name=name, role=role, bytes=b, md5=md5, high_confidence=hc, directory=d)


#: The two releases that answer to "IMG/VR v4", as published. Checksums, sizes and dates are
#: the publisher's own, read from JGI's public file listing on 2026-10-15 and captured at
#: `policies/captures/jgi-imgvr-inventory.json`. Earlier IMG/VR releases (v1 2018-01-24, v2
#: 2018-09-13, v3 2020-09-11 and 2020-10-12) are in that capture and deliberately not pinned
#: here: no source in this audit cites them.
RELEASES = {
    "2022-09-20": Release(
        date="2022-09-20",
        version="v4",
        note=(
            "v4 proper: its own README reads '### IMG/VR database v4 release Oct. 2022 ###', "
            "three months before the v4 paper's issue date. This is the release Evo 1's "
            "citation names on the publisher's own naming. Its sequence-information table "
            "differs from the December one, and the December one says why (D-063)."
        ),
        files=(
            _f(
                "IMGVR_all_Host_information.tsv",
                "host_information",
                696_380_987,
                "3486513594a81fd00e276e37803994e0",
                False,
                "AUTO-420894",
            ),
            _f(
                "IMGVR_all_Sequence_information.tsv",
                "sequence_information",
                5_047_197_400,
                "2d088a49561248e199843f73222c5a94",
                False,
                "AUTO-420894",
            ),
            _f(
                "IMGVR_all_nucleotides.fna.gz",
                "nucleotides",
                48_319_030_883,
                "e37e6a541e10a75a88577763f75fc9cd",
                False,
                "AUTO-420894",
            ),
            _f(
                "IMGVR_all_proteins.faa.gz",
                "proteins",
                31_527_214_055,
                "4ad51e8940d2e4174bda17a0809f8f44",
                False,
                "AUTO-420894",
            ),
            _f(
                "README.txt",
                "readme",
                4_063,
                "de00c84dbd84612e382532b6523ab77b",
                False,
                "AUTO-420894",
            ),
            _f(
                "IMGVR_all_Host_information-high_confidence.tsv",
                "host_information",
                289_219_376,
                "71b54d0f5c186d813f058bf0379dfd24",
                True,
                "AUTO-420906",
            ),
            _f(
                "IMGVR_all_Sequence_information-high_confidence.tsv",
                "sequence_information",
                1_888_622_388,
                "a2eedc151e557a78a327d6bf9a95bd25",
                True,
                "AUTO-420906",
            ),
            _f(
                "IMGVR_all_nucleotides-high_confidence.fna.gz",
                "nucleotides",
                24_792_200_438,
                "83301c9c6dfefea3305a53ee2a41bac3",
                True,
                "AUTO-420906",
            ),
            _f(
                "IMGVR_all_proteins-high_confidence.faa.gz",
                "proteins",
                16_474_572_352,
                "c04b4c385386741d5c7cdbfa23e9af9d",
                True,
                "AUTO-420906",
            ),
            _f(
                "README-high_confidence.txt",
                "readme",
                4_804,
                "823d65f8c9c6ff07f772228e685e55dd",
                True,
                "AUTO-420906",
            ),
        ),
    ),
    "2022-12-20": Release(
        date="2022-12-20",
        version="v4.1",
        note=(
            "Not a second v4 but an erratum of it. Its README reads '### IMG/VR database v4.1 "
            "release Dec. 2022 ###' and states that v4.1 'includes the same sequences as "
            "IMG/VR v4, but fixes issues with two files (IMGVR_all_proteins.faa and "
            "IMGVR_all_Sequence_information.tsv) in which a few sequences/rows were "
            "incorrect', everything else being identical. That is exactly the difference set "
            "D-052 derived from the md5sums alone, confirmed independently by the publisher "
            "(D-063)."
        ),
        files=(
            _f(
                "IMGVR_all_Host_information.tsv",
                "host_information",
                696_380_987,
                "3486513594a81fd00e276e37803994e0",
                False,
                "AUTO-444368",
            ),
            _f(
                "IMGVR_all_Sequence_information.tsv",
                "sequence_information",
                5_047_197_637,
                "658ce076cd26729892552ed5876ad17c",
                False,
                "AUTO-444368",
            ),
            _f(
                "IMGVR_all_nucleotides.fna.gz",
                "nucleotides",
                48_319_030_883,
                "e37e6a541e10a75a88577763f75fc9cd",
                False,
                "AUTO-444368",
            ),
            _f(
                "IMGVR_all_proteins.faa.gz",
                "proteins",
                31_477_831_962,
                "fff611fc3983ce2ce8e9f9a4d671ae0e",
                False,
                "AUTO-444368",
            ),
            _f(
                "README.txt",
                "readme",
                4_332,
                "ba749fd171bbf5821dcddeeff3db343b",
                False,
                "AUTO-444368",
            ),
            _f(
                "IMGVR_all_Host_information-high_confidence.tsv",
                "host_information",
                289_219_376,
                "71b54d0f5c186d813f058bf0379dfd24",
                True,
                "AUTO-444369",
            ),
            _f(
                "IMGVR_all_Sequence_information-high_confidence.tsv",
                "sequence_information",
                1_888_622_625,
                "3c516db128082fa29dc2c2f60520da1b",
                True,
                "AUTO-444369",
            ),
            _f(
                "IMGVR_all_nucleotides-high_confidence.fna.gz",
                "nucleotides",
                24_792_200_438,
                "83301c9c6dfefea3305a53ee2a41bac3",
                True,
                "AUTO-444369",
            ),
            _f(
                "IMGVR_all_proteins-high_confidence.faa.gz",
                "proteins",
                16_148_816_357,
                "19e266b87ec7ca96fe586aed172438fe",
                True,
                "AUTO-444369",
            ),
            _f(
                "README-high_confidence.txt",
                "readme",
                4_590,
                "7097befc3787e4f78858ba8f6ff7e4c0",
                True,
                "AUTO-444369",
            ),
        ),
    ),
}

#: Both releases Evo 1's citation could mean, in publication order.
V4_CANDIDATES = ("2022-09-20", "2022-12-20")


def release_on(date: str) -> Release:
    try:
        return RELEASES[date]
    except KeyError:
        raise KeyError(
            f"no pinned IMG/VR release dated {date!r}; pinned: {sorted(RELEASES)}. Earlier "
            "releases are in the inventory capture but no source in this audit cites them."
        ) from None


def differs_between(a: str, b: str) -> dict[str, bool]:
    """Which published files differ between two releases, by name. True means they differ.

    This is the function behind D-052, and it is here rather than in a write-up because the
    claim it supports — that the two v4 releases agree on sequence and host data and disagree
    on the confidence and vOTU metadata — decides whether A7.2 has to run both.
    """
    ra, rb = release_on(a), release_on(b)
    fa = {f.name: f.md5 for f in ra.files}
    fb = {f.name: f.md5 for f in rb.files}
    return {name: fa.get(name) != fb.get(name) for name in sorted(set(fa) | set(fb))}


#: Where a single file is fetched from, by its JAMO id. Read from the publisher's own download
#: API spec (`files-download.jgi.doe.gov/apidoc/?format=openapi`, version 202610.92006.17) and
#: not from the portal's search host, because the two are different services and only this one
#: serves a single file by id.
DOWNLOAD_BASE = "https://files-download.jgi.doe.gov/download_files/"


def download_request(
    file_ids: Sequence[str], *, organism_id: str, top_hit: str
) -> tuple[str, dict[str, object]]:
    """The URL and JSON body that actually return bytes, for files named by listing `_id`.

    `POST /download_files/` with `{"ids": {<organism_id>: {"file_ids": [...], "top_hit": ...}}}`.
    The response is a single `application/zip` stream holding every requested file under a
    per-release directory, plus a `Download_<n>_File_Manifest.csv` carrying the publisher's own
    md5 and size for each. It is recorded here rather than inlined in the staging tool because
    two earlier passes had the endpoint wrong in ways that were invisible without a credential:

    * `files.jgi.doe.gov/filedownload/?_id=<id>` — the first version — answers `401` to *any*
      method and its `Allow` header reads `POST, OPTIONS`, so the 401 that pass read as proof the
      endpoint was live proved only that (D-060).
    * `files-download.jgi.doe.gov/download_files/<id>/` is the publisher's documented single-file
      read and is what D-060 corrected to. Authenticated, it answers `404` for every IMG/VR file
      tried, small and large alike, as nginx HTML rather than the API's own JSON — so the request
      is authenticated and routed and the file is still not served that way. Unauthenticated the
      same URL answers `401` with `Allow: GET, HEAD, OPTIONS`, which is why no measurement before
      a credential existed could distinguish the two (D-062).

    `top_hit` is the `_id` **string** of the organism's top-hit file, not the object the search
    response nests there; passing the object returns HTTP 500. Verified end to end against the
    live API on 2026-10-15: the two 2022-09-20 READMEs came back inside the zip at the exact
    sizes and md5s pinned in `RELEASES`.
    """
    return DOWNLOAD_BASE, {"ids": {organism_id: {"file_ids": list(file_ids), "top_hit": top_hit}}}


def conformance_inputs(date: str) -> tuple[ReleaseFile, ...]:
    """The files A7.2's conformance re-execution actually needs from a release.

    Metadata only, and both confidence variants of the sequence information. The unfiltered
    variant is not optional: Evo 1's first rule keeps records labelled high-confidence, so
    auditing it requires records that are *not* so labelled, and the pre-filtered file cannot
    contain one. 7.9 GB rather than the 128.7 GB the release holds in full — the nucleotides
    and proteins answer no conformance question, because every check here is a set operation
    over accessions and metadata.
    """
    rel = release_on(date)
    return tuple(
        f for f in rel.files if f.role in ("sequence_information", "host_information", "readme")
    )


# --------------------------------------------------------------------------------------
# Reading the metadata tables
# --------------------------------------------------------------------------------------

#: The columns of `IMGVR_all_Sequence_information.tsv` A7.2 reads, by header text rather than
#: by index. The index is stable across both releases today; a header lookup costs nothing and
#: survives a re-cut, which matters because v4.1 is an erratum of this very file (D-063).
#:
#: `Taxonomic classification` is the load-bearing one, and not only because the taxonomy rules
#: read it: its value is formatted exactly as the inline lineage tag Evo 1's release carries
#: (`r__...;k__...;p__...;c__...;o__...;f__...;g__...;s__...`, eight `;`-separated fields). That
#: identity is what makes Evo 1's accession-less release joinable to its own input at all — not
#: per record, which no field permits, but per lineage, which is the unit the taxonomy rules
#: act on anyway.
SEQ_COLUMNS = {
    "uvig": "UVIG",
    "votu": "vOTU",
    "confidence": "Confidence",
    "classification": "Taxonomic classification",
    "host": "Host taxonomy prediction",
}

#: The columns of `IMGVR_all_Host_information.tsv`. One row per host *prediction*, so a UViG
#: appears as many times as it has predictions — which is why the host rule's counting unit has
#: to be declared rather than assumed (D-058).
HOST_COLUMNS = {
    "uvig": "UVIG",
    "method": "Prediction method",
    "host": "Host taxonomy prediction",
}

#: Host domains that make a host prokaryotic, in the sense Evo 1's published rule uses the word.
#: Both are named in the publisher's own `d__` vocabulary. Nothing here is inferred from a
#: secondary source: the rule says "prokaryotic host" and these are the two prokaryotic domains.
PROKARYOTIC_DOMAINS = frozenset({"Bacteria", "Archaea"})

#: And the domain that makes it eukaryotic, which only the charitable and strict readings act on.
EUKARYOTIC_DOMAINS = frozenset({"Eukaryota"})


def host_domain(value: str) -> str:
    """The domain rank of a host prediction, or a label for its absence.

    The field is a semicolon-joined lineage beginning at `d__`. An empty field and a field of
    bare separators both mean no prediction, and they are counted apart from each other because
    which one the publisher emits is itself under-specified.

    This is the canonical implementation; `tools/imgvr_composition.py` carries its own copy from
    A1.7 and `tests/test_imgvr.py` asserts the two agree, so a change to either is caught rather
    than silently splitting the semantics of the word "host" across two passes.
    """
    v = value.strip()
    if not v:
        return "(empty)"
    if not v.strip(";"):
        return "(separators only)"
    first = v.split(";")[0].strip()
    if not first.startswith("d__"):
        return f"(unparsed: {first[:24]})"
    return first[3:] or "(empty d__)"


def host_class(value: str) -> str | None:
    """The host *class* a prediction falls in — the vocabulary the published rules are written
    against — or `None` when there is no usable prediction.

    `prokaryotic` and `eukaryotic` are the two classes the three readings of Evo's policy name
    (`policies/specs/evo1-*.yaml`). A domain the publisher emits that is neither is returned as
    `other`, rather than being folded into one of the two: a host assignment this audit cannot
    classify is not the same thing as an absent one, and the strict reading's exclusivity test
    turns on exactly that difference.
    """
    domain = host_domain(value)
    if domain.startswith("("):
        return None
    if domain in PROKARYOTIC_DOMAINS:
        return "prokaryotic"
    if domain in EUKARYOTIC_DOMAINS:
        return "eukaryotic"
    return "other"


class UvigNotPackable(ValueError):
    """An IMG/VR accession whose middle field is not numeric, and so does not pack.

    Its own exception class because the caller's correct response is not to discard the record.
    IMG/VR carries two accession shapes: `IMGVR_UViG_<taxon_oid>_<n>`, where the middle field is
    a numeric IMG taxon object id, and `IMGVR_UViG_GVMAG-<M|S>-<oid>-<n>_<m>`, where it is a
    giant-virus metagenome-assembled genome identifier carrying letters and hyphens. The second
    is a small fraction of the database and is exactly the fraction an audit of a
    eukaryote-infecting-virus filter cannot afford to lose: giant viruses infect eukaryotes.

    So a packed-integer join must carry these records under identifiers of their own rather than
    skipping the ones that will not fit the packing. Raising a distinct type is what lets a
    caller do that without catching the same `ValueError` that a genuinely malformed accession
    raises.
    """


def split_uvig(uvig: str) -> tuple[str, int]:
    """`IMGVR_UViG_<middle>_<n>` -> `(middle, n)`, whatever shape the middle field has.

    Raises `ValueError` on anything that is not an IMG/VR UViG accession at all. The suffix is
    required to be numeric because both published shapes have one and because it is what
    distinguishes the several UViGs cut from a single assembly.
    """
    v = uvig.strip()
    if not v.startswith("IMGVR_UViG_"):
        raise ValueError(f"not an IMG/VR UViG accession: {uvig!r}")
    middle, _, n = v[len("IMGVR_UViG_") :].rpartition("_")
    if not middle or not n.isdigit():
        raise ValueError(f"not an IMG/VR UViG accession: {uvig!r}")
    return middle, int(n)


def uvig_key(uvig: str) -> int:
    """Pack an `IMGVR_UViG_<taxon_oid>_<n>` accession into one integer.

    15.7 million accessions are joined twice in this task — once against the host table, once
    against Evo 2's released FASTA — and a dict of 15.7 million 28-character strings does not
    fit the budget this pass runs in. For the numeric shape the two fields are the whole
    identity of the accession, so they pack losslessly into `taxon_oid * 10**7 + n`, and the
    pair sorts the same way the string does.

    Raises :class:`UvigNotPackable` for the GVMAG shape, which has no numeric middle field, and
    plain `ValueError` for anything that is not an IMG/VR accession. A silent fallback would be
    the dangerous option in either case: an accession that does not pack is a record that would
    drop out of a join, and a join that quietly loses records produces a conformance number that
    is wrong in the direction of looking clean.
    """
    middle, n = split_uvig(uvig)
    if not middle.isdigit():
        raise UvigNotPackable(f"non-numeric taxon field in UViG accession: {uvig!r}")
    if n >= 10**7:
        raise ValueError(f"UViG suffix wider than the packing allows: {uvig!r}")
    return int(middle) * 10**7 + n


def votu_id(votu: str) -> int:
    """The integer of a `vOTU_<n>` identifier.

    Same reason as :func:`uvig_key`: 8.6 million vOTU strings are grouped in memory, and the
    integer is the identifier. Raises rather than falling back, for the same reason.
    """
    v = votu.strip()
    prefix, _, n = v.partition("_")
    if prefix != "vOTU" or not n.isdigit():
        raise ValueError(f"not a vOTU identifier: {votu!r}")
    return int(n)


def uvig_fallback_key(uvig: str) -> int:
    """A stable integer for an accession :func:`uvig_key` cannot pack.

    The GVMAG shape has no numeric field to pack, and the two sides of every join in A7.2 are
    computed by different passes at different times — so the identifier has to be a function of
    the accession string alone, with no vocabulary shared between them. A truncated BLAKE2b
    digest is that function.

    Returned negative, which keeps it disjoint from every packed key by construction:
    :func:`uvig_key` returns `taxon_oid * 10**7 + n`, which is non-negative. The digest is
    narrowed to 63 bits before negating so the result is a valid `int64` on any platform.

    A hash is not an injection, so a caller joining on these must check for collisions rather
    than assume them away: the non-packable accessions are a small vocabulary, so comparing the
    number of distinct keys against the number of distinct accession strings is cheap and exact.
    :func:`collision_free` is that check, and both A7.2 passes run it.
    """
    digest = hashlib.blake2b(uvig.strip().encode("utf-8"), digest_size=8).digest()
    return -(int.from_bytes(digest, "big") >> 1) - 1


def uvig_join_key(uvig: str) -> int:
    """The join key for any IMG/VR accession: packed where it packs, hashed where it does not.

    Raises `ValueError` only for something that is not an IMG/VR UViG accession at all, which is
    a malformed row rather than a second accession shape.
    """
    try:
        return uvig_key(uvig)
    except UvigNotPackable:
        return uvig_fallback_key(uvig)


def collision_free(accessions: Iterable[str]) -> tuple[bool, int, int]:
    """Whether :func:`uvig_join_key` is injective on `accessions`.

    Returns `(verdict, n_distinct_accessions, n_distinct_keys)`. A false verdict means two
    different accessions share a key and any join over them silently merges two records; it is
    reported with both counts rather than as a bare flag, because the size of the gap is the
    size of the problem.
    """
    seen = set(a.strip() for a in accessions)
    keys = {uvig_join_key(a) for a in seen}
    return len(seen) == len(keys), len(seen), len(keys)

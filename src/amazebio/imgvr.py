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

__all__ = [
    "FILE_ROLES",
    "RELEASES",
    "V4_CANDIDATES",
    "Release",
    "ReleaseFile",
    "conformance_inputs",
    "differs_between",
    "release_on",
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
            "The first release answering to v4, three months before the v4 paper's issue date. "
            "Its sequence-information table differs from the December one."
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
        version="v4",
        note=(
            "The second release answering to v4, the month the v4 paper issued. Identical "
            "nucleotides and host information to September; different sequence information "
            "and proteins."
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

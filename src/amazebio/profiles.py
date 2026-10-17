"""Pinned profile registries and the thresholds they are searched at — task A2.1.

`DESIGN.md` §A2 names two profile resources: Pfam's viral clans, and RVDB, "which exists for
exactly this purpose". This module pins both, decides what a hit is, and does nothing else —
the search itself is `amazebio.detect` and the pipeline is `tools/detect_profiles.py`.

Three things here are decisions rather than code, and each has a `tasks/DECISIONS.md` entry.

**"Pfam viral clans" does not denote a usable set, and the gap is measurable** (D-075). A Pfam
clan is a structural superfamily, so clans mix viral and cellular families freely: `CL0055`
(Nucleoplasmin) holds seven viral capsid families beside the cellular nucleoplasmins, and
`CL0063` (NADP_Rossmann) holds two reovirus methyltransferase domains inside one of the largest
cellular clans in the database. Reading the phrase at clan level — every family in every clan
containing a viral family — selects 6,614 of Pfam 38.2's 30,134 families, 6,075 of which are not
themselves viral, and *still* misses the 1,127 viral families that belong to no clan at all. It
is both four times too large and materially incomplete. So selection here is at family level
(:func:`select_viral_families`), the clan travels as metadata, and the selected set ships as an
artefact so a reviewer can check the membership rather than trust it.

**Thresholds are bit-score thresholds, or E-values against a pinned database size** (D-076).
An E-value depends on how many sequences were searched, so the same profile at "E ≤ 1e-5" means
a different bit score on a sample than on a full corpus, and the audit's own headline would move
with the amount of corpus it happened to read. Pfam carries curated per-model gathering cutoffs
for all 30,134 families and those are used as published — this project does not get to pick its
own threshold for somebody else's curated database. RVDB-prot's profiles are built
automatically and carry no curated cutoff, so they are searched at E ≤ 1e-5 with `Z` pinned to
:data:`PINNED_Z`, which makes the E-value a fixed per-model bit score and therefore comparable
across every manifest and every sample size.

**Registries are never pooled** (`metrics/survival.md`, D-022). The headline is reported once
per registry because the two have incompatible membership criteria — RVDB's is published by its
authors and Pfam's is this project's reading — and a pooled denominator would hide which is
which. :class:`Registry` carries its version into every detection for that reason.
"""

from __future__ import annotations

import contextlib
import dataclasses
import gzip
import hashlib
import lzma
import re
from collections.abc import Iterator
from pathlib import Path

__all__ = [
    "MIN_MODEL_COVERAGE",
    "PFAM_38_2",
    "PINNED_DOM_Z",
    "PINNED_E_VALUE",
    "PINNED_Z",
    "REGISTRIES",
    "RVDB_PROT_32_0",
    "VIRAL_KEYWORDS",
    "FamilyLabel",
    "FamilyMeta",
    "ProfileError",
    "ProfileHeader",
    "Registry",
    "RegistryFile",
    "clan_name_additions",
    "clan_names",
    "iter_family_meta",
    "iter_profile_headers",
    "md5_of",
    "open_profiles",
    "registry",
    "rvdb_labels",
    "select_viral_families",
]


class ProfileError(RuntimeError):
    """Raised when a registry is not what its publisher says it is, or a threshold is unsound."""


# --------------------------------------------------------------------------------------
# Thresholds — fixed here, before any corpus was searched. See D-076.
# --------------------------------------------------------------------------------------

#: Target-sequence count the E-values are computed against, for registries with no curated
#: cutoff. Pinned so that a threshold means one bit score everywhere: `hmmsearch` scales the
#: E-value by the number of targets, so leaving `Z` to the search would make the threshold a
#: function of how much corpus a run happened to read. One million is within an order of
#: magnitude of the translated gene count of a single staged source, which keeps the reported
#: E-values readable as E-values rather than as a rescaled bit score.
PINNED_Z = 1_000_000

#: Domain-count equivalent of :data:`PINNED_Z`, pinned for the same reason.
PINNED_DOM_Z = 1_000_000

#: Sequence E-value a hit must beat where the registry publishes no curated cutoff.
PINNED_E_VALUE = 1e-5

#: Fraction of the profile that must be covered by the hit's envelope. A profile search over
#: called genes finds short partial matches in abundance, and a 20-residue slice of a 400-residue
#: capsid model is not a surviving homolog of that family in any sense §A3 reports. Applies to
#: both registries, including Pfam's gathering cutoffs: Pfam curates its cutoffs for annotating
#: domains in proteins, which is a different question from whether a family survived a filter.
MIN_MODEL_COVERAGE = 0.5


# --------------------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class RegistryFile:
    """One file of a registry release, with the checksum its publisher states for it.

    `md5` is the publisher's value, transcribed from the source named in `md5_source` — never
    computed from a downloaded copy. A checksum taken from the bytes you already have verifies
    nothing; `AGENTS.md` requires pinned inputs, and the pin is the publisher's digest.
    """

    name: str
    url: str
    size: int
    md5: str
    md5_source: str
    #: Uncompressed size, where the publisher states it. None where they do not.
    uncompressed_size: int | None = None
    #: Publisher's digest of the uncompressed file, where stated.
    uncompressed_md5: str | None = None

    @property
    def local_name(self) -> str:
        return self.name


@dataclasses.dataclass(frozen=True, slots=True)
class Registry:
    """A pinned profile release: what it is, where it came from, and how many profiles it has.

    `profile_count` is the publisher's stated count where they state one. `tools/stage_profiles.py`
    counts the staged file independently and records stated-versus-counted, because
    `AGENTS.md` asks for exactly that gap to be visible rather than assumed away.
    """

    id: str
    version: str
    publisher: str
    release_date: str
    #: Where the version and the digests were read from. A primary source, per `AGENTS.md`.
    source: str
    files: tuple[RegistryFile, ...]
    #: Profiles the publisher states the release contains, or None where they state none.
    profile_count: int | None
    #: How membership of this registry is defined, and by whom. Carried into the write-up:
    #: the two registries answer "is this family viral" by different authorities.
    membership: str
    #: True when every profile carries a curated per-model cutoff to search at.
    curated_cutoffs: bool
    notes: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """`<id>/<version>`, as it appears in artefact paths and in every detection."""
        return f"{self.id}/{self.version}"

    def file(self, name: str) -> RegistryFile:
        for f in self.files:
            if f.name == name:
                return f
        raise ProfileError(f"{self.key}: no file named {name!r}")

    def staged_dir(self, root: str | Path = "data/profiles") -> Path:
        return Path(root) / self.id / self.version


#: Pfam 38.2. The release is pinned by its versioned directory rather than `current_release`,
#: which is a moving pointer: a result that regenerates only until EBI publishes 38.3 does not
#: regenerate. Digests are the publisher's own `md5_checksums`.
PFAM_38_2 = Registry(
    id="pfam",
    version="38.2",
    publisher="EMBL-EBI",
    release_date="2026-01-22",
    source="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/relnotes.txt",
    files=(
        RegistryFile(
            name="Pfam-A.hmm.gz",
            url="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/Pfam-A.hmm.gz",
            size=418160514,
            md5="7ab3c4e215d0daaea3004e37c4e24f8a",
            md5_source="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/md5_checksums",
        ),
        RegistryFile(
            name="Pfam-A.hmm.dat.gz",
            url="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/Pfam-A.hmm.dat.gz",
            size=782046,
            md5="aab364689372b1846e8e880976e7f750",
            md5_source="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/md5_checksums",
        ),
        RegistryFile(
            name="Pfam-A.clans.tsv.gz",
            url="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/Pfam-A.clans.tsv.gz",
            size=553777,
            md5="a70eeffcd8105ff094ea5834456d8bab",
            md5_source="https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/md5_checksums",
        ),
    ),
    # Pfam states its family count in the release notes; the viral subset is this project's
    # selection and is counted, not stated. The stated total is checked by the stager.
    profile_count=None,
    membership=(
        "this project's reading: Pfam families whose own ID or description names a viral "
        "entity (select_viral_families). Pfam itself publishes no viral flag, and the clans "
        "DESIGN.md §A2 refers to are structural superfamilies that mix viral with cellular "
        "families — see D-075 for the measured consequence of reading the phrase at clan level."
    ),
    curated_cutoffs=True,
    notes=(
        "Every family in 38.2 carries a GA gathering cutoff, so the whole registry can be "
        "searched at its curated thresholds with nothing left to this project's judgement.",
        "13,933 of 30,134 families belong to a clan at all, which is why clan-level selection "
        "is incomplete as well as over-broad.",
    ),
)

#: RVDB-prot 32.0. Digests, counts and the build's own tool versions come from the release's
#: metadata file, which is the publisher stating them rather than this project inferring them.
RVDB_PROT_32_0 = Registry(
    id="rvdb-prot",
    version="32.0",
    publisher="Bioinformatics Hub, Institut Pasteur",
    release_date="2026-07",
    source="https://rvdb-prot.pasteur.fr/files/U-RVDBv32.0-prot-metadata.yaml",
    files=(
        RegistryFile(
            name="U-RVDBv32.0-prot.hmm.xz",
            url="https://rvdb-prot.pasteur.fr/files/U-RVDBv32.0-prot.hmm.xz",
            size=266598820,
            md5="d21c42648369ccaf30188633536d08e9",
            md5_source="U-RVDBv32.0-prot-metadata.yaml: files.hmm_profiles.md5_checksum_compressed",
            uncompressed_size=2715363745,
            uncompressed_md5="7e6d213a9a55739af1cf1d498e58647c",
        ),
        RegistryFile(
            name="U-RVDBv32.0-prot-hmm.sqlite.xz",
            url="https://rvdb-prot.pasteur.fr/files/U-RVDBv32.0-prot-hmm.sqlite.xz",
            size=6283684,
            md5="4179c579c38fb2d2c5c0af967bcface7",
            md5_source=(
                "U-RVDBv32.0-prot-metadata.yaml: "
                "files.annotations_sqlite.md5_checksum_compressed"
            ),
            uncompressed_size=24489984,
            uncompressed_md5="a95a0d3ab084f7a49e15170d777ed262",
        ),
        RegistryFile(
            name="U-RVDBv32.0-prot-metadata.yaml",
            url="https://rvdb-prot.pasteur.fr/files/U-RVDBv32.0-prot-metadata.yaml",
            # The metadata file states digests for every other file and none for itself, so it
            # is pinned by the version it declares rather than by a digest. Recorded as the one
            # unpinned input rather than quietly checksummed against our own copy.
            size=0,
            md5="",
            md5_source="unpinned: the metadata file states no digest for itself",
        ),
    ),
    profile_count=13679,
    membership=(
        "the publisher's: profiles built from clustered protein sequences translated from the "
        "nucleotide RVDB, a database curated for virus detection. Membership is defined by "
        "RVDB's own curation, not by this project."
    ),
    curated_cutoffs=False,
    notes=(
        "Built with HMMER 3.3.1 per the release metadata; searched here with the HMMER pyhmmer "
        "vendors. Profile format is version-stable, so this is recorded rather than reconciled.",
        "The publisher's disclaimer states the database is for academic and research use and is "
        "not a regulatory standard. Quoted in the write-up beside any number drawn from it.",
        "No curated per-model cutoffs, so searched at PINNED_E_VALUE against PINNED_Z (D-076).",
    ),
)

#: Every registry A2.1 searches, by id.
REGISTRIES = {r.id: r for r in (PFAM_38_2, RVDB_PROT_32_0)}


def registry(id_: str) -> Registry:
    try:
        return REGISTRIES[id_]
    except KeyError:
        raise ProfileError(
            f"unknown registry {id_!r}; pinned registries are {sorted(REGISTRIES)}"
        ) from None


# --------------------------------------------------------------------------------------
# Pfam family metadata and the viral selection
# --------------------------------------------------------------------------------------

#: The selection vocabulary, frozen before the corpus was searched (D-075).
#:
#: Each term names a viral entity or a structure only viruses build, and the list is deliberately
#: short: a longer one would pull in families named for a host process viruses happen to use.
#: `integrase` and `transposase` are absent for that reason — they are mobile-element machinery
#: shared with transposons and the audit must not count a bacterial transposase as viral content.
#: Terms are matched case-insensitively against the family's Pfam ID and description, and the
#: selected set ships as an artefact so the selection is reviewable per family rather than
#: per keyword.
VIRAL_KEYWORDS: tuple[str, ...] = (
    "virus",
    "viral",
    "virion",
    "phage",
    "capsid",
    "nucleocapsid",
    "coat protein",
    "tail fibre",
    "tail fiber",
    "baseplate",
    "portal protein",
    "terminase",
    "rna-dependent rna polymerase",
    "rdrp",
    "reverse transcriptase",
)

_KEYWORD_RE = re.compile("|".join(re.escape(k) for k in VIRAL_KEYWORDS), re.IGNORECASE)

_GF = re.compile(r"#=GF (\w\w)\s+(.*)")


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyMeta:
    """One Pfam family as `Pfam-A.hmm.dat` states it."""

    accession: str
    name: str
    description: str
    #: Gathering cutoffs: (sequence, domain). Pfam states both.
    gathering: tuple[float, float] | None
    model_length: int | None
    clan: str | None
    entry_type: str | None
    #: Which rule put this family in the universe, set by :func:`select_viral_families`.
    selected_by: str = ""

    @property
    def is_viral(self) -> bool:
        """True when the family's own name or description names a viral entity. See D-075."""
        return bool(_KEYWORD_RE.search(f"{self.name} {self.description}"))


def iter_family_meta(dat_path: str | Path) -> Iterator[FamilyMeta]:
    """Stream `Pfam-A.hmm.dat.gz` as :class:`FamilyMeta`.

    Read from the `.dat` file rather than from the 1.6 GB `Pfam-A.hmm` because the selection
    needs names, clans and cutoffs and nothing else: parsing a gigabyte of model parameters to
    read the headers would make the selection step cost more than the search.
    """
    path = Path(dat_path)
    opener = gzip.open if path.suffix == ".gz" else open
    current: dict[str, str] = {}
    with opener(path, "rt") as handle:  # type: ignore[operator]
        for line in handle:
            line = line.rstrip("\n")
            if line == "//":
                if current:
                    yield _family_from(current)
                current = {}
                continue
            match = _GF.match(line)
            if match:
                current[match.group(1)] = match.group(2).strip()
    if current:
        yield _family_from(current)


def _family_from(fields: dict[str, str]) -> FamilyMeta:
    accession = fields.get("AC", "")
    if not accession:
        raise ProfileError(f"Pfam .dat record without an accession: {fields!r}")
    gathering: tuple[float, float] | None = None
    if "GA" in fields:
        parts = [p.strip() for p in fields["GA"].rstrip(";").split(";") if p.strip()]
        if len(parts) != 2:
            raise ProfileError(f"{accession}: GA line {fields['GA']!r} is not two cutoffs")
        gathering = (float(parts[0]), float(parts[1]))
    length = int(fields["ML"]) if "ML" in fields else None
    return FamilyMeta(
        # Versioned accessions (PF26733.1) are stripped to the stable accession, which is what
        # survival counts are keyed on: a family universe keyed on the point release would change
        # denominator whenever Pfam bumps a single alignment.
        accession=accession.split(".")[0],
        name=fields.get("ID", ""),
        description=fields.get("DE", ""),
        gathering=gathering,
        model_length=length,
        clan=fields.get("CL"),
        entry_type=fields.get("TP"),
    )


def clan_names(clans_path: str | Path) -> dict[str, str]:
    """Clan accession to clan ID, from `Pfam-A.clans.tsv`.

    The clan's own *name* is used by :func:`select_viral_families` and is a far narrower signal
    than clan membership: `CL0156` is called `Nucleocapsid` and holds nothing but viral
    nucleocapsids, while `CL0055` is called `Nucleoplasmin` and holds viral capsids beside
    cellular families. Reading the name keeps the first and rejects the second, which is the
    distinction D-075 and D-083 turn on.
    """
    path = Path(clans_path)
    opener = gzip.open if path.suffix == ".gz" else open
    names: dict[str, str] = {}
    with opener(path, "rt") as handle:  # type: ignore[operator]
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) >= 3 and fields[1]:
                names[fields[1]] = fields[2]
    return names


def select_viral_families(dat_path: str | Path) -> dict[str, FamilyMeta]:
    """The Pfam viral family universe: accession to metadata, for families naming a viral entity.

    One rule, applied to the family's own ID and description: this is the denominator of every
    Pfam-registry survival figure, and a denominator assembled from two rules of different
    reliability cannot be defended family by family.

    The rule has a known blind spot and it is pinned by a test rather than left to be
    rediscovered: a family named for a virus *taxon* carries no word from the vocabulary at all.
    `Ebola_NP`, `Rhabdo_ncap` and `Paramyxo_ncap` are outside this universe for that reason.
    :func:`clan_name_additions` measures the gap, D-083 records why it is reported rather than
    closed, and RVDB-prot — whose membership is its publisher's, not ours — is the registry that
    covers it.

    :func:`amazebio.survival.family_survival` reads its denominator from the universe it is
    given and cannot tell a pinned zero from a missing key, so a universe that drifted between
    runs would move the headline silently. Hence: derived once from the pinned release, shipped
    as an artefact, and keyed on the stable accession.
    """
    selected = {
        m.accession: dataclasses.replace(m, selected_by="family-name")
        for m in iter_family_meta(dat_path)
        if m.is_viral
    }
    if not selected:
        raise ProfileError(
            f"no viral families selected from {dat_path}: an empty family universe means the "
            "release was not staged correctly, which is a setup error rather than a result"
        )
    missing = sorted(a for a, m in selected.items() if m.gathering is None)
    if missing:
        raise ProfileError(
            f"{len(missing)} selected families carry no gathering cutoff "
            f"(first: {missing[:3]}); searching those would need a threshold this project "
            "invented, which D-076 does not permit for a curated registry"
        )
    return selected


def clan_name_additions(
    dat_path: str | Path, clans_path: str | Path
) -> dict[str, tuple[FamilyMeta, str]]:
    """Families a second rule would add: those whose *clan's* name names a viral entity.

    Measured and reported, not used (D-083). It is the narrowest widening available — the
    clan's own name rather than its membership — and it is still contaminated: `CL0511` is
    called `Retroviral_zf` and holds cellular zinc fingers (`CLIP1_ZNF`), `CL0504` is called
    `Phage_barrel` and holds `Alg8_N`. A universe is a denominator, so a cellular family inside
    it adds a guaranteed zero and pushes the headline down; that is the safe direction but it is
    still wrong, and the per-family artefact is what lets a reviewer re-cut either way.
    """
    clans = clan_names(clans_path)
    viral_clans = {acc: name for acc, name in clans.items() if _KEYWORD_RE.search(name)}
    return {
        m.accession: (m, viral_clans[m.clan])
        for m in iter_family_meta(dat_path)
        if not m.is_viral and m.clan in viral_clans
    }


# --------------------------------------------------------------------------------------
# Staged files
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ProfileHeader:
    """What a profile's header says about itself: name, length, cutoffs, calibration.

    Enough to build a family universe and a per-model threshold without loading the models.
    Reading the headers is a text scan of the decompressing stream; loading 13,679 profiles to
    read 13,679 names would cost gigabytes of memory for what is on the first few lines of each.
    """

    name: str
    accession: str | None
    length: int | None
    #: Calibrated Forward tail: (tau, lambda). HMMER's sequence E-value is
    #: `Z · exp(-lambda · (score - tau))`, which is what makes a per-model bit-score threshold
    #: derivable from an E-value and a pinned `Z` (D-076).
    forward: tuple[float, float] | None
    #: Curated gathering cutoffs, (sequence, domain), where the publisher curates them.
    gathering: tuple[float, float] | None

    def bit_threshold(self, *, e_value: float = PINNED_E_VALUE, z: int = PINNED_Z) -> float:
        """The bit score equivalent to `e_value` against a database of `z` sequences.

        Raises:
            ProfileError: if the profile carries no Forward calibration. An uncalibrated model
                has no E-value to invert, and guessing a bit score for it would put a threshold
                this project invented inside a registry it did not curate.
        """
        if self.forward is None:
            raise ProfileError(
                f"{self.name}: no calibrated Forward tail, so no bit score corresponds to "
                f"E <= {e_value}. The profile cannot be searched at a declared threshold."
            )
        import math

        tau, lam = self.forward
        return tau + math.log(z / e_value) / lam


def iter_profile_headers(path: str | Path) -> Iterator[ProfileHeader]:
    """Stream a staged HMM file's profile headers."""
    name: str | None = None
    accession: str | None = None
    length: int | None = None
    forward: tuple[float, float] | None = None
    gathering: tuple[float, float] | None = None
    seen = False

    with open_profiles(path) as handle:
        for raw in handle:
            line = raw.decode("ascii", "replace").rstrip()
            if line.startswith("HMMER3"):
                if seen and name:
                    yield ProfileHeader(name, accession, length, forward, gathering)
                name, accession, length, forward, gathering = None, None, None, None, None
                seen = True
                continue
            if line.startswith("NAME "):
                name = line.split(maxsplit=1)[1].strip()
            elif line.startswith("ACC "):
                accession = line.split(maxsplit=1)[1].strip()
            elif line.startswith("LENG "):
                length = int(line.split()[1])
            elif line.startswith("GA "):
                parts = [p.strip() for p in line[3:].replace(";", " ").split()]
                gathering = (float(parts[0]), float(parts[1]))
            elif line.startswith("STATS LOCAL FORWARD"):
                parts = line.split()
                forward = (float(parts[3]), float(parts[4]))
            elif line.startswith("HMM "):
                # The model matrix starts here; nothing further in this record is a header.
                if name:
                    yield ProfileHeader(name, accession, length, forward, gathering)
                name, accession, length, forward, gathering = None, None, None, None, None
    if name:
        yield ProfileHeader(name, accession, length, forward, gathering)


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyLabel:
    """A readable label for one RVDB family, derived from the release's own annotations.

    RVDB names its families `FAM004230` and assigns no descriptive name: the annotation database
    holds keyword frequencies and taxon ids, not titles. So a label is *derived*, and the
    distinction matters enough to keep in the type — `family_id` is the identity the counts are
    keyed on and the only thing a figure may cite as the family; `label` is for a reader, and it
    is this project's summary of the publisher's keyword frequencies (D-097).
    """

    family_id: str
    label: str
    keywords: tuple[str, ...]
    reference_keywords: tuple[str, ...]
    lca_taxid: int | None
    sequences: int | None
    model_length: int | None


def rvdb_labels(sqlite_path: str | Path, *, top: int = 4) -> dict[str, FamilyLabel]:
    """Derive a readable label per RVDB family from the pinned annotation database.

    The label is the family's `top` most frequent sequence-name keywords, in frequency order,
    which reads as a rough function: `FAM004230` becomes "virus protease hypothetical protein".
    Reference-derived keywords travel beside it rather than inside it — they describe the domain
    literature rather than the sequences, and mixing the two would make the label look like a
    curated title, which it is not.

    `sqlite_path` may be the `.xz` as staged; it is decompressed to a temporary file because
    SQLite needs a seekable file rather than a stream.
    """
    import sqlite3
    import tempfile

    path = Path(sqlite_path)
    with contextlib.ExitStack() as stack:
        if path.suffix == ".xz":
            tmp = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".sqlite"))
            with lzma.open(path, "rb") as compressed:
                while block := compressed.read(8 << 20):
                    tmp.write(block)
            tmp.flush()
            db_path = tmp.name
        else:
            db_path = str(path)
        connection = stack.enter_context(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True))

        def keywords_of(table: str) -> dict[int, list[str]]:
            out: dict[int, list[str]] = {}
            rows = connection.execute(
                f"SELECT f.famId, k.str FROM {table} f "
                "JOIN keyword k ON k.id = f.kwId ORDER BY f.famId, f.freq DESC"
            )
            for fam_id, word in rows:
                out.setdefault(fam_id, []).append(word)
            return out

        by_sequence = keywords_of("fam_kw_seqnames")
        by_reference = keywords_of("fam_kw_ref")
        labels: dict[str, FamilyLabel] = {}
        for fam_id, size, nbseq, taxid in connection.execute(
            "SELECT id, size, nbseq, LCAtaxid FROM family"
        ):
            words = tuple(by_sequence.get(fam_id, ()))
            family_id = f"FAM{fam_id:06d}"
            labels[family_id] = FamilyLabel(
                family_id=family_id,
                label=" ".join(words[:top]) or "(no keywords in the release's annotations)",
                keywords=words[:12],
                reference_keywords=tuple(by_reference.get(fam_id, ()))[:8],
                lca_taxid=taxid,
                sequences=nbseq,
                model_length=size,
            )
    if not labels:
        raise ProfileError(
            f"no family annotations read from {sqlite_path}: an empty label set means the "
            "annotation database was not staged correctly"
        )
    return labels


def md5_of(path: str | Path, *, chunk: int = 8 << 20) -> str:
    """MD5 of a file, streamed. The registries are gigabytes; nothing is read whole."""
    # MD5 because the publisher's digests are MD5; the choice of algorithm is theirs, not ours.
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def open_profiles(path: str | Path):
    """Open a staged profile file, transparently handling `.gz` and `.xz`.

    Returns a binary handle. The HMM files stay compressed on disk — 1.6 GB and 2.7 GB
    uncompressed against a session container's disk allowance is not a trade worth making when
    `pyhmmer` reads a decompressing stream perfectly well.
    """
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    if path.suffix == ".xz":
        return lzma.open(path, "rb")
    return open(path, "rb")

"""The pinned fold universe A2.2 searches for, enumerated at ECOD's family level — task A2.2.

`DESIGN.md` §A2 names three virus-characteristic folds in prose — jelly-roll capsid, viral
RdRp, class I fusion glycoprotein — and names no identifier for any of them. This module turns
those three phrases into an auditable denominator: a list of ECOD family identifiers per fold,
and the representative domains whose structures become the search target. The search itself is
`tools/detect_folds.py`; the detection schema is `amazebio.detect`.

Four things here are decisions rather than code, and each has a decision-log entry
(`docs/working-record.md`).

**Selection is by enumerated family identifier, never by regex over names** (D-166). Names are
how the lists below were built and must not be the mechanism that applies them. The measurement
that forces this: the family name `GP41` matches HIV's envelope glycoprotein, a phage tail
protein (`E217_GP41`) and a Wiskott-Aldrich protein alike, and `Hemagglutinin` spans both the
jelly-roll receptor-binding head and the HA2 fusion stalk — different folds doing different
jobs. Searching the literal phrase "RNA-dependent RNA polymerase" in ECOD's names returns 81
birnavirus subdomains and misses every canonical RdRp family, because those are named for Pfam.

**Selection is at the family level and not one level up** (D-166, corrected by D-169). ECOD's
`jelly-roll` X-group holds 15,906 Concanavalin A-like lectins and 9,881 galactose-binding
domains beside the viral capsids, and viral RdRp sits under topologies named for adenylyl
cyclases and reverse transcriptases. D-166 established that and then, for the capsid fold only,
selected one level up anyway — at the H-group `Nucleoplasmin-like/VP (viral coat and capsid
proteins)`. That group is "nucleoplasmin-*like*": it carries 867 plainly cellular domains
(nucleoplasmin itself, peptide-N-glycanase, Cu(2+) monooxygenase, TGF-beta propeptide) and 12 of
its 119 curated representatives are cellular. D-169 applies the family-level rule consistently,
so :data:`JELLY_ROLL_CAPSID` enumerates the 64 demonstrably viral families of that H-group and
excludes both the cellular ones and ECOD's two unnamed families, one of which contains a
cellular enzyme (`e1pgsA1`, peptide-N-glycanase).

**Host polymerases that share the viral RdRp fold are excluded deliberately** (D-166). The
eukaryotic RNAi polymerase families — ECOD's `RNAi polymerase helical domain`, `RNAi polymerase
N-terminal domain` and the `double psi` RdRP family, 269 domains between them — have the fold
and are not viral-derived content. Counting one as a surviving viral homolog would be a false
positive of exactly the kind this audit exists to avoid, and it is the same call A2.1 made
excluding integrase and transposase from its viral family set.

**One of the three folds is this project's own construction, and ships labelled so** (D-166).
"Class I fusion glycoprotein" is a virology category, not a structural group: influenza HA2, HIV
gp41, coronavirus S2 and the paramyxovirus F proteins sit in unrelated ECOD branches and **no
single node means the class**. :data:`CLASS_I_FUSION` is assembled here rather than borrowed,
which makes it the weakest of the three and the structural coverage gap A2.2's Done-when
criterion asks to be documented. The capsid and RdRp sets borrow a curator's grouping and say
which one.

**A reference structure is a curated representative, not every domain** (D-166). Fold search is
the point, so ECOD's `manual_rep` domains are the right reference, and it keeps the reference
side small — 141 structures against 26,102 classified domains in the three folds.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

__all__ = [
    "CLASS_I_FUSION",
    "ECOD_V295_2",
    "EXCLUDED_CELLULAR_CAPSID",
    "EXCLUDED_HOST_RNAI",
    "FOLDS",
    "JELLY_ROLL_CAPSID",
    "PROSTT5",
    "SEARCH_GEOMETRY",
    "VIRAL_RDRP",
    "EcodRelease",
    "Fold",
    "FoldError",
    "ReferenceDomain",
    "fold_for_family",
    "iter_domains",
    "params_fingerprint",
    "reference_domains",
    "sha256_of",
]


class FoldError(RuntimeError):
    """Raised when the fold universe would be built from something it cannot support."""


#: The search geometry A2.2 runs under, and the only things that change what a shard's scores
#: mean. Lives here rather than in the tool because the launcher has to derive the same
#: fingerprint to place shards where a later launch will look for them — two definitions of this
#: would mean two prefixes and a pass that silently never resumes.
#:
#: The threshold is deliberately absent: shards are stored above a floor far below any declared
#: cut, so re-cutting at the declared value or either bracket does not invalidate them.
SEARCH_GEOMETRY = {
    "cov_mode": 1,
    "min_target_coverage": 0.5,
    "floor_bits": 15.0,
    "exhaustive_search": True,
    "seed": 20261015,
}


def params_fingerprint(reference_sha256: str) -> str:
    """A short digest of the reference set plus :data:`SEARCH_GEOMETRY`."""
    body = json.dumps({"reference_sha256": reference_sha256, **SEARCH_GEOMETRY}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


@dataclasses.dataclass(frozen=True)
class StagedWeights:
    """The pinned ProstT5 weights foldseek predicts 3Di with, and where they are staged.

    Pinned rather than downloaded per run for two reasons, one of which stopped a launch.
    `foldseek databases ProstT5` fetches from a third-party host that returned `status=429` to
    all three attempts from an instance on 2026-10-19, fifteen minutes after the identical file
    downloaded cleanly in the session container. And the published command names no digest at
    all, which makes the weights an unpinned input on the critical path — D-171's threshold was
    measured with *these* bytes, so an instance fetching a different build under the same name
    would apply a threshold measured on one instrument to another, and nothing would notice.

    `key` is derived from `sha256` so that a different build cannot land where this one is
    expected: the corpus bucket has no `DeleteObject`, so a key is a promise.
    """

    name: str
    sha256: str
    bytes: int
    upstream: str
    publisher: str

    @property
    def key(self) -> str:
        return f"corpora/models/prostt5/{self.sha256[:12]}/{self.name}"


#: Staged 2026-10-19 and verified by size on landing (D-173).
PROSTT5 = StagedWeights(
    name="prostt5-f16.gguf",
    sha256="b072042c7d5b2c7425ed6cfdbc85d2cbd62b42470d0fc1afc7c2524c1bb70207",
    bytes=2417458816,
    upstream="https://foldseek.steineggerlab.workers.dev/prostt5-f16-gguf.tar.gz",
    publisher="https://huggingface.co/Rostlab/ProstT5",
)


# --------------------------------------------------------------------------------------
# The pinned registry
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class EcodRelease:
    """A pinned ECOD domain list.

    `url` is the publisher's *moving* pointer — ECOD serves the current release as
    `ecod.latest.domains.txt` and does not keep a per-version filename for it, which the
    distribution listing confirms: it stops at `develop292` while `latest` is v295.2. So the pin
    cannot be the URL. It is `version` plus `sha256`, both checked against the file on disk, and
    `generated` is the publisher's own timestamp from the file header.
    """

    version: str
    generated: str
    url: str
    sha256: str
    classified_domains: int


#: The release D-166 pinned, re-verified here: the downloaded file's header states v295.2 and
#: generated 2026-08-27, and it holds 2,943,252 classified domain rows. D-166 recorded
#: 2,943,253, which is that count plus the header's own column line.
ECOD_V295_2 = EcodRelease(
    version="v295.2",
    generated="2026-08-27 10:39:43",
    url="http://prodata.swmed.edu/ecod/distributions/ecod.latest.domains.txt",
    sha256="cd3abc43f6e6fa3671e7c32bee4eaa201093dc28f71cb170e0d6340a5d27afe8",
    classified_domains=2943252,
)


# --------------------------------------------------------------------------------------
# Fold 1 — jelly-roll capsid. Borrowed grouping, cellular families removed.
# --------------------------------------------------------------------------------------

#: The viral families of ECOD's `Nucleoplasmin-like/VP (viral coat and capsid proteins)` H-group
#: (X-group `jelly-roll`). 64 families, 15,158 domains, 97 curated representatives.
JELLY_ROLL_CAPSID = (
    "10.2.1.1",  # Rhv
    "10.2.1.2",  # picornavirus capsid protein / Picornavirus coat protein (VP4)
    "10.2.1.4",  # Late_protein_L1
    "10.2.1.6",  # Polyoma_coat
    "10.2.1.7",  # Viral_coat
    "10.2.1.8",  # Polyhedrin
    "10.2.1.9",  # Parvo_coat
    "10.2.1.10",  # Cucumo_coat
    "10.2.1.11",  # Gemini_coat
    "10.2.1.12",  # Luteo_coat
    "10.2.1.13",  # Calici_coat
    "10.2.1.14",  # Calicivirus coat protein / Calicivirus coat protein C-terminal
    "10.2.1.15",  # Tymo_coat
    "10.2.1.16",  # Parvo_NS1
    "10.2.1.17",  # Adeno_hexon
    "10.2.1.19",  # Bromo_coat
    "10.2.1.20",  # Birna_VP2
    "10.2.1.21",  # Ilar_coat
    "10.2.1.22",  # Peptidase_A6 — nodavirus capsid protease domain
    "10.2.1.23",  # Pico_P1A
    "10.2.1.24",  # Como_LCP
    "10.2.1.25",  # Como_SCP
    "10.2.1.26",  # Phage_F
    "10.2.1.27",  # Phage_G
    "10.2.1.28",  # Denso_VP4
    "10.2.1.29",  # Circo_capsid
    "10.2.1.32",  # Astro_capsid_N
    "10.2.1.33",  # Pox_Rif
    "10.2.1.34",  # Nepo_coat
    "10.2.1.35",  # Peptidase_A21 — pararetroviral capsid protease domain
    "10.2.1.36",  # Adeno_hexon_C
    "10.2.1.37",  # Nepo_coat_C
    "10.2.1.38",  # Nepo_coat_N
    "10.2.1.40",  # TNV_CP
    "10.2.1.41",  # Capsid_NCLDV
    "10.2.1.42",  # Potex_coat
    "10.2.1.43",  # Calici_coat_C
    "10.2.1.44",  # CRPV_capsid
    "10.2.1.45",  # Phage_Capsid_P3
    "10.2.1.49",  # Capsid-VNN
    "10.2.1.50",  # Protein of unknown function (DUF3724) / Picornavirus coat protein
    "10.2.1.51",  # HAV_VP
    "10.2.1.53",  # IHHNV_capsid
    "10.2.1.54",  # Capsid_N
    "10.2.1.56",  # P2_N
    "10.2.1.57",  # Bbp16
    "10.2.1.58",  # Gp10-like
    "10.2.1.59",  # STIV_turret_3rd
    "10.2.1.60",  # STIV_penton_2nd
    "10.2.1.61",  # Sputnik_MCP_1st
    "10.2.1.62",  # VP16-like
    "10.2.1.63",  # MCP_V20_C
    "10.2.1.64",  # Phage_spike_P1
    "10.2.1.65",  # VP17_central_barrel
    "10.2.1.66",  # STIV-like_capsid
    "10.2.1.67",  # Spike_JR1
    "10.2.1.68",  # Spike_JR2
    "10.2.1.69",  # Rhv_5
    "10.2.1.80",  # P2_C
    "10.2.1.81",  # MP — viral movement protein
    "10.2.1.87",  # P3_C
    "10.2.1.88",  # Rhv, Calici_coat
    "10.2.1.90",  # Adeno_hexon, Adeno_hexon_C
    "10.2.1.103",  # Vp24_capsid
)

#: Families of the same H-group that are *not* viral capsids and are excluded (D-169). Recorded
#: by identifier rather than merely omitted, because what a denominator leaves out is as much a
#: part of the membership rule as what it admits — and because the exclusion is a correction to
#: a recorded decision, so a reader must be able to check it. 867 domains, 12 representatives.
EXCLUDED_CELLULAR_CAPSID = (
    "10.2.1.5",  # TGFb_propeptide
    "10.2.1.18",  # Cu2_monooxygen
    "10.2.1.30",  # SP2
    "10.2.1.31",  # Nucleoplasmin — the cellular protein the H-group is named "like"
    "10.2.1.39",  # Cu2_monoox_C
    "10.2.1.46",  # N-glycanase_N
    "10.2.1.47",  # N-glycanase_C
    "10.2.1.48",  # DUF2961
    "10.2.1.55",  # NPL
    "10.2.1.70",  # SURNod19
    "10.2.1.72",  # PNGaseA
    "10.2.1.74",  # WAK
    "10.2.1.75",  # CBM96
    "10.2.1.82",  # C-JID
    "10.2.1.83",  # GUB_WAK_bind
    "10.2.1.84",  # Seipin
    "10.2.1.85",  # Rv1352
    "10.2.1.86",  # But2
    "10.2.1.89",  # GH172_dom
    "10.2.1.92",  # WAK, GUB_WAK_bind
    "10.2.1.95",  # DUF4360
    "10.2.1.96",  # GH172_1st
    "10.2.1.97",  # TGF_beta
    "10.2.1.100",  # DUF7154
    "10.2.1.104",  # Disaggr_repeat
)

#: ECOD's two unnamed families in that H-group, also excluded (D-169). An unnamed family is
#: domains ECOD placed in the group without assigning them a family, so its membership cannot be
#: stated — and `10.2.1.0` demonstrably holds a cellular enzyme (`e1pgsA1`, peptide-N-glycanase,
#: PDB 1pgs), which is what settles it. 665 domains, 10 representatives.
EXCLUDED_UNNAMED_CAPSID = ("10.2.1.0", "10.2.1.52")


# --------------------------------------------------------------------------------------
# Fold 2 — viral RdRp. Borrowed families, assembled across topologies, host set removed.
# --------------------------------------------------------------------------------------

#: Viral RNA-dependent RNA polymerase families. 27 families, 2,583 domains, 30 representatives.
#:
#: RdRp is multidomain and ECOD classifies its palm and its helical bundle ("thumb") apart, under
#: two topologies named for unrelated enzymes — `Adenylyl and guanylyl cyclase catalytic
#: domain-like` (the 304.48.* ids) and `helical bundle domain in reverse transcriptase-like
#: polymerases` (the 4967.1.1.* ids). Both halves are listed: a corpus protein carrying either is
#: carrying viral RdRp fold, and selecting only one would halve the fold's sensitivity.
#:
#: D-166's prose named six families by way of example (`RdRP_1`, `RdRP_3`, `RdRP`,
#: `Birna_RdRp_palm`, `Birna_RdRp_C`, `CoV_RPol_N`) and its artefact was never shipped, so the
#: list below is re-derived (D-169). Those six names alone select 1,441 domains and 18
#: representatives and miss influenza PB1, flavivirus NS5, the mononegavirus and bunyavirus L
#: polymerases and the coronavirus thumb — all canonical viral RdRps. The re-derivation lands at
#: 30 representatives against D-166's recorded 31.
VIRAL_RDRP = (
    "142.2.1.1",  # Birna_RdRp_C
    "304.48.1.7",  # Flu_PB1 — influenza polymerase
    "304.48.1.8",  # RdRP_1
    "304.48.1.9",  # RdRP_1, CoV_RPol_N — coronavirus nsp12
    "304.48.1.12",  # Mononeg_RNA_pol
    "304.48.1.13",  # Flavi_NS5
    "304.48.1.15",  # RdRP_3
    "304.48.1.16",  # RdRP_4
    "304.48.1.18",  # RNA_replicase_B
    "304.48.1.19",  # Bunya_RdRp
    "304.48.1.23",  # RdRP_5
    "304.48.1.29",  # vRNAP_dom
    "304.48.1.30",  # CPV_RdRP_pol_dom
    "304.48.1.43",  # Mitovir_RNA_pol
    "304.48.2.1",  # Birna_RdRp_palm
    "304.48.2.2",  # Permu_RdRp_palm
    "4967.1.1.1",  # Flu_PB1 (thumb)
    "4967.1.1.2",  # RdRP_1 (thumb)
    "4967.1.1.3",  # Mononeg_RNA_pol (thumb)
    "4967.1.1.5",  # RdRP_3 (thumb)
    "4967.1.1.7",  # RNA_replicase_B (thumb)
    "4967.1.1.8",  # Bunyavirus L, thumb ring domain
    "4967.1.1.10",  # RdRP_5 (thumb)
    "4967.1.1.14",  # Flavi_NS5_thumb
    "4967.1.1.15",  # Birna_VP1_thumb
    "4967.1.1.17",  # Permu_RdRp_thumb
    "4967.1.1.32",  # Bunya_RdRp (thumb)
)

#: Host polymerase families sharing the RdRp fold, excluded deliberately (D-166). 269 domains.
#: A eukaryotic RNAi polymerase is not viral-derived content; see the module docstring.
EXCLUDED_HOST_RNAI = (
    "1.1.2.11",  # RdRP, under topology `double psi` — the eukaryotic RDR family
    "3588.1.1.1",  # RdRP, RNAi polymerase helical domain
    "3588.1.1.2",  # RdRP, RdRP_head
    "3588.1.1.3",  # RdRP_head
    "3589.1.1.1",  # RdRP, RNAi polymerase N-terminal domain
)


# --------------------------------------------------------------------------------------
# Fold 3 — class I fusion glycoprotein. This project's own construction.
# --------------------------------------------------------------------------------------

#: Class I viral fusion glycoprotein families. 15 families, 7,361 domains, 14 representatives.
#:
#: Assembled here, not borrowed: the members sit in five unrelated ECOD branches and no node
#: means the class. The branch names are the reason family-level selection is not optional — the
#: `MPER trimer` topology that carries HIV gp41 (`3567.1.1.2`) also carries bZIP transcription
#: factors, GATA domains, syntaxin, fungal rhodopsin, mitochondrial carriers and a phage
#: fibritin trimerization domain, several hundred cellular families in all.
#:
#: D-166 recorded 9,606 domains and 16 representatives; its list was never shipped and this
#: re-derivation lands at 7,361 and 14 (D-169). The gap is not padded: approaching D-166's figure
#: needs either the coronavirus S1 beta domain (receptor binding, not fusion) or ECOD's unnamed
#: families in the `MPER trimer` topology, and neither is a class I fusion glycoprotein.
CLASS_I_FUSION = (
    "11.40.1.0",  # Immunoglobulin-like domain in paramyxovirus F (unnamed family)
    "11.40.1.1",  # Fusion_gly — paramyxovirus F, Ig-like domain
    "1042.1.1.0",  # S2 subunit of coronavirus spike (unnamed family)
    "1042.1.1.1",  # CoV_S2
    "1042.1.1.12",  # CoV_S2, CoV_S1_C
    "3362.1.1.1",  # Fusion_gly — fusion glycoprotein F2
    "3567.1.1.2",  # GP41 — HIV-1 envelope, MPER trimer
    "3567.1.1.188",  # Ebola-like_HR1-HR2
    "3847.1.1.0",  # Hemagglutinin HA2 chain (unnamed family)
    "3847.1.1.1",  # Hemagglutinin — influenza HA2
    "3847.1.1.2",  # Hema_stalk
    "5093.1.1.0",  # Paramyxovirus F ectodomain head and neck (unnamed family)
    "5093.1.1.1",  # Fusion_gly — paramyxovirus F ectodomain
    "5093.1.1.2",  # Baculo_F
    "5093.1.1.4",  # Fusion_gly, Fibritin_C
)


# --------------------------------------------------------------------------------------
# The universe
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Fold:
    """One of §A2's three folds, as a membership rule over ECOD families.

    `curation` is load-bearing in the write-up rather than in the code: it records whether the
    grouping is a curator's or this project's, which is what decides how strongly a detection in
    this fold may be worded.
    """

    fold_id: str
    name: str
    families: tuple[str, ...]
    curation: str
    note: str

    def __post_init__(self) -> None:
        if len(set(self.families)) != len(self.families):
            raise FoldError(f"{self.fold_id}: duplicate family identifier")


FOLDS: tuple[Fold, ...] = (
    Fold(
        fold_id="jelly_roll_capsid",
        name="Jelly-roll viral capsid",
        families=JELLY_ROLL_CAPSID,
        curation="borrowed_grouping_cellular_families_removed",
        note=(
            "ECOD's Nucleoplasmin-like/VP H-group under X-group jelly-roll, restricted to its "
            "demonstrably viral families. 25 cellular families and 2 unnamed families are "
            "excluded by identifier (D-169)."
        ),
    ),
    Fold(
        fold_id="viral_rdrp",
        name="Viral RNA-dependent RNA polymerase",
        families=VIRAL_RDRP,
        curation="borrowed_families_assembled_across_topologies",
        note=(
            "Palm and helical-bundle halves are classified under two topologies named for "
            "unrelated enzymes; both are listed. Host RNAi polymerase families sharing the fold "
            "are excluded by identifier (D-166)."
        ),
    ),
    Fold(
        fold_id="class_i_fusion",
        name="Class I viral fusion glycoprotein",
        families=CLASS_I_FUSION,
        curation="this_project",
        note=(
            "No single ECOD node means this class; the set is assembled here across five "
            "unrelated branches. The weakest of the three folds, and the structural coverage "
            "gap A2.2 reports as a limitation (D-166)."
        ),
    ),
)


def fold_for_family(family_id: str) -> Fold | None:
    """Which fold a family belongs to, or `None`.

    Exact identifier match, never a prefix: `10.2.1.1` and `10.2.1.10` are different families and
    a prefix test would conflate them.
    """
    for fold in FOLDS:
        if family_id in fold.families:
            return fold
    return None


# --------------------------------------------------------------------------------------
# Reading the release
# --------------------------------------------------------------------------------------

#: The columns `iter_domains` requires. ECOD's header is read rather than assumed: the column
#: order has changed between releases, and a positional read would silently mis-assign.
REQUIRED_COLUMNS = (
    "uid",
    "ecod_domain_id",
    "manual_rep",
    "f_id",
    "pdb",
    "chain",
    "pdb_range",
    "seqid_range",
    "x_name",
    "h_name",
    "t_name",
    "f_name",
    "valid_structure",
)


@dataclasses.dataclass(frozen=True)
class ReferenceDomain:
    """One ECOD representative domain, and where to cut it out of its PDB entry."""

    uid: str
    domain_id: str
    fold_id: str
    family_id: str
    family_name: str
    t_name: str
    pdb: str
    chain: str
    pdb_range: str

    @property
    def filename(self) -> str:
        """The reference structure's name in the foldseek database.

        The ECOD domain id alone, which is unique within a release and is what a detection
        reports. Not the PDB id: several representatives can come from one entry.
        """
        return f"{self.domain_id}.cif"


def sha256_of(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def iter_domains(path: Path) -> Iterator[dict[str, str]]:
    """Stream ECOD's domain list as dicts keyed by its own header names.

    The file is 663 MB and is never held in memory. Comment lines are skipped and the first
    non-comment line is the header.
    """
    header: list[str] | None = None
    with path.open() as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if header is None:
                header = fields
                missing = [c for c in REQUIRED_COLUMNS if c not in header]
                if missing:
                    raise FoldError(f"{path}: ECOD header is missing {missing}")
                continue
            yield dict(zip(header, fields, strict=False))


def reference_domains(
    path: Path, *, release: EcodRelease = ECOD_V295_2, verify: bool = True
) -> list[ReferenceDomain]:
    """The reference set: every curated representative of every family in :data:`FOLDS`.

    A representative is kept only when ECOD marks it `manual_rep`, marks its structure valid, and
    names a PDB entry — the three things that have to hold for the structure to be fetchable and
    cuttable. A representative failing any of them is dropped here rather than failing later as a
    download error, and the count is reported so the drop is visible.
    """
    if verify:
        actual = sha256_of(path)
        if actual != release.sha256:
            raise FoldError(
                f"{path}: sha256 is {actual}, expected {release.sha256} for {release.version}"
            )
    out: list[ReferenceDomain] = []
    for row in iter_domains(path):
        fold = fold_for_family(row["f_id"])
        if fold is None:
            continue
        if row["manual_rep"] != "True" or row["valid_structure"] != "True":
            continue
        if not row["pdb"].strip() or not row["pdb_range"].strip():
            continue
        out.append(
            ReferenceDomain(
                uid=row["uid"],
                domain_id=row["ecod_domain_id"],
                fold_id=fold.fold_id,
                family_id=row["f_id"],
                family_name=row["f_name"],
                t_name=row["t_name"],
                pdb=row["pdb"].strip().lower(),
                chain=row["chain"].strip(),
                pdb_range=row["pdb_range"].strip(),
            )
        )
    if not out:
        raise FoldError(f"{path}: no reference domains selected — the family lists cannot be empty")
    return out

"""The profile search itself, shared by every A2 detector that needs a family name.

Factored out of `tools/detect_profiles.py` for A2.4 (D-113) and otherwise unchanged: same
gathering cutoffs, same pinned `Z` and E-value, same model-coverage floor, same record naming.
A2.1's numbers do not move because of this file, and the tests that pin them did not change.

The split is between *finding* a viral family and *locating* the element it sits in, and the
two A2 detectors that need both take them from different places:

- **A2.1** calls genes across sampled surviving records and searches all of them. A hit says a
  viral family is present; D-079 is explicit that it says nothing about what kind of element
  carries it.
- **A2.4** takes the proteins geNomad already called *inside a delineated provirus* and searches
  only those. The element kind is `prophage` because the provirus finder said so, and the family
  comes from here — which is the whole of D-113: localisation and identity from different
  instruments, so that neither the audit's family axis nor its element kinds rest on the
  taxonomy the filter itself used.

Both paths end in :func:`search` against the same registries at the same thresholds, which is
what lets A3.2 join the two tables instead of reconciling them.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from amazebio.profiles import (
    MIN_MODEL_COVERAGE,
    PINNED_DOM_Z,
    PINNED_E_VALUE,
    PINNED_Z,
    ProfileError,
    Registry,
    iter_profile_headers,
    open_profiles,
    select_viral_families,
)

__all__ = [
    "RegistryView",
    "best_domain",
    "best_domain_region",
    "best_model_coverage",
    "call_genes",
    "consensus_identity",
    "family_universe",
    "hmm_path",
    "proteins_from_fasta",
    "search",
    "text_of",
]


class RegistryView:
    """One registry resolved for searching: its universe, its thresholds, and what to search.

    Three keyings have to be kept straight and conflating them is the easy mistake. A *profile
    name* is what the HMM file calls a model and what a hit comes back under. A *family id* is
    what the survival counts are keyed on — Pfam's stable accession, RVDB's family name. And
    `restrict_to` is the set of profile names to search at all: Pfam is cut to the viral
    selection (D-075), while RVDB-prot is searched whole because its publisher's curation *is*
    the membership criterion.
    """

    def __init__(
        self,
        *,
        universe: dict[str, str],
        thresholds: dict[str, float],
        family_of_profile: dict[str, str],
        restrict_to: set[str] | None,
    ) -> None:
        self.universe = universe
        self.thresholds = thresholds
        self.family_of_profile = family_of_profile
        self.restrict_to = restrict_to

    def thresholds_by_family(self) -> dict[str, float]:
        return {self.family_of_profile[n]: t for n, t in self.thresholds.items()}


def family_universe(reg: Registry, data_root: Path) -> RegistryView:
    """Resolve one pinned registry into the view the search and the tables need."""
    if reg.id == "pfam":
        selected = select_viral_families(reg.staged_dir(data_root) / "Pfam-A.hmm.dat.gz")
        return RegistryView(
            universe={a: m.name for a, m in selected.items()},
            # Pfam's own curated per-model gathering cutoff, sequence half. Used as published.
            thresholds={m.name: m.gathering[0] for m in selected.values() if m.gathering},
            family_of_profile={m.name: a for a, m in selected.items()},
            restrict_to={m.name for m in selected.values()},
        )

    path = reg.staged_dir(data_root) / reg.files[0].local_name
    universe: dict[str, str] = {}
    thresholds: dict[str, float] = {}
    for header in iter_profile_headers(path):
        universe[header.name] = header.accession or header.name
        thresholds[header.name] = header.bit_threshold(e_value=PINNED_E_VALUE, z=PINNED_Z)
    if reg.profile_count is not None and len(universe) != reg.profile_count:
        raise ProfileError(
            f"{reg.key}: {len(universe)} profiles read, publisher states {reg.profile_count}. "
            "The family universe is the denominator of every figure from this registry, so a "
            "disagreement about its size voids them all."
        )
    return RegistryView(
        universe=universe,
        thresholds=thresholds,
        family_of_profile={n: n for n in universe},
        restrict_to=None,
    )


def hmm_path(reg: Registry, data_root: Path) -> Path:
    """Where a pinned registry's profile file lives under the data root."""
    name = "Pfam-A.hmm.gz" if reg.id == "pfam" else reg.files[0].local_name
    return reg.staged_dir(data_root) / name


def text_of(value: Any) -> str:
    """A pyhmmer name as text. The library returns `bytes` in some versions and `str` in others."""
    return value.decode() if isinstance(value, bytes) else str(value)


def _name(hmm: Any) -> str:
    return text_of(hmm.name)


def best_domain(hit: Any) -> Any | None:
    """The hit's included domain covering the most columns of the model, or `None`.

    One function so that every statistic reported about "the matched region" is a statistic of
    the *same* region. :func:`best_model_coverage` and :func:`best_domain_region` each used to
    scan the domains themselves and agreed only because both maximise aligned model columns —
    one of them divided by a constant. A7.5 reports coverage, coordinates and identity to the
    consensus side by side as properties of one region, which is a claim a reader cannot check
    and three independent scans could quietly break (the shape of D-246).

    Ties go to the first such domain, which is HMMER's own order.
    """
    best: tuple[int, Any] | None = None
    for domain in hit.domains:
        if domain.included is False:
            continue
        alignment = domain.alignment
        covered = int(alignment.hmm_to - alignment.hmm_from + 1)
        if best is None or covered > best[0]:
            best = (covered, domain)
    return None if best is None else best[1]


def best_model_coverage(hit: Any, model_length: int) -> float:
    """Fraction of the model covered by the hit's best-covering domain.

    Per domain rather than summed across domains: a family detected because four unrelated
    fragments of its model matched in different places is not the same claim as a family
    detected because one region matched most of the model, and A2.1 reports the stronger one.
    """
    if not model_length:
        return 0.0
    domain = best_domain(hit)
    if domain is None:
        return 0.0
    alignment = domain.alignment
    return (alignment.hmm_to - alignment.hmm_from + 1) / model_length


def consensus_identity(domain: Any) -> float | None:
    """Fraction of the region's match-state columns where the target residue *is* the consensus.

    Defined once, here, and fixed before any row was read (A7.5). Over the alignment of one
    domain, a column counts in the denominator when the model's consensus line carries a
    match-state residue — a letter, rather than the `.` HMMER writes where the target has
    inserted relative to the model — and in the numerator when the target's residue at that
    column is the same letter, case-folded. A gap on the target side (`-`) counts in the
    denominator and not the numerator.

    Case-folded because HMMER writes the consensus in upper case at the most conserved positions
    and lower case elsewhere: that is an emphasis on the model's own confidence and not a
    different residue.

    `alignment.identity_sequence` is deliberately not used — it marks positive-scoring
    substitutions as well as identities, so it answers a different question.

    **What the number is not.** It is identity to a consensus string, which summarises a family's
    model; it is not identity to any sequence that exists, not identity to any member of the
    family, and not a measure of resemblance to any named organism. The detection claim remains
    the bit score against the curated threshold. `None` where the region has no match-state
    column at all, which is a degenerate alignment rather than an identity of zero.
    """
    alignment = domain.alignment
    consensus = str(alignment.hmm_sequence)
    target = str(alignment.target_sequence)
    columns = 0
    same = 0
    for model_residue, target_residue in zip(consensus, target, strict=False):
        if not model_residue.isalpha():
            continue
        columns += 1
        if target_residue.isalpha() and target_residue.upper() == model_residue.upper():
            same += 1
    return None if not columns else same / columns


def best_domain_region(hit: Any) -> tuple[int, int] | None:
    """The hit's best-covering domain as 1-based inclusive coordinates on the protein.

    The same domain :func:`best_model_coverage` measures, reported as the region of the
    *target* it occupies. A2.1 itself has no use for this — a detection is a record, not a
    span — but A3.4 does: its diversity bins are built from Pfam's seed alignment, whose
    members are aligned regions and not whole proteins, so comparing a called gene against
    them compares a protein with a domain. The region is what makes the two sides the same
    kind of object (D-241).
    """
    domain = best_domain(hit)
    if domain is None:
        return None
    alignment = domain.alignment
    return int(alignment.target_from), int(alignment.target_to)


def call_genes(records: list[Any]) -> tuple[list[Any], dict[str, int]]:
    """Call genes on sampled nucleotide records; returns digital protein sequences and counts.

    Metagenomic mode (D-077). Records whose genes cannot be called are counted rather than
    absorbed into "no hit": that population is a limit of the method and has to be visible.
    """
    import pyrodigal
    from pyhmmer.easel import Alphabet, TextSequence

    amino = Alphabet.amino()
    finder = pyrodigal.GeneFinder(meta=True)
    proteins: list[Any] = []
    stats = Counter({"records": 0, "records_without_genes": 0, "genes": 0, "residues": 0})
    for sampled in records:
        stats["records"] += 1
        genes = finder.find_genes(sampled.sequence)
        if not len(genes):
            stats["records_without_genes"] += 1
            continue
        for i, gene in enumerate(genes):
            protein = gene.translate().rstrip("*")
            if not protein:
                continue
            stats["genes"] += 1
            stats["residues"] += len(protein)
            # The gene index travels in the name so a hit can be placed back on its record
            # without the artefact carrying any sequence.
            name = f"{sampled.id}|gene{i}".encode()
            proteins.append(TextSequence(name=name, sequence=protein).digitize(amino))
    return proteins, dict(stats)


def proteins_from_fasta(entries: Any, *, record_of: Any) -> tuple[list[Any], dict[str, int]]:
    """Digitize already-called proteins, naming each one for the record it is to be counted on.

    A2.4's path into :func:`search`. geNomad has already called the genes inside each delineated
    provirus and written them out, so calling them again with a different gene finder would
    search a different set of proteins than the one the provirus boundaries were drawn around.

    `entries` yields `(name, protein_sequence)`; `record_of` maps the tool's protein name to the
    **host record** the hit must be counted on. That mapping is the caller's because only the
    caller knows which provirus came from which genome, and getting it wrong would attribute a
    prophage's families to the wrong bacterium — an error the artefact gives no way to spot.

    A protein the mapping cannot place stops nothing and is counted in `proteins_unplaced`:
    silently dropping it would shrink the searched set without shrinking the denominator.
    """
    from pyhmmer.easel import Alphabet, TextSequence

    amino = Alphabet.amino()
    proteins: list[Any] = []
    stats = Counter({"records": 0, "genes": 0, "residues": 0, "proteins_unplaced": 0})
    seen: set[str] = set()
    for i, (name, sequence) in enumerate(entries):
        protein = str(sequence).rstrip("*")
        if not protein:
            continue
        record_id = record_of(name)
        if not record_id:
            stats["proteins_unplaced"] += 1
            continue
        if record_id not in seen:
            seen.add(record_id)
            stats["records"] += 1
        stats["genes"] += 1
        stats["residues"] += len(protein)
        tagged = f"{record_id}|gene{i}".encode()
        proteins.append(TextSequence(name=tagged, sequence=protein).digitize(amino))
    return proteins, dict(stats)


def search(
    reg: Registry,
    proteins: list[Any],
    *,
    restrict_to: set[str] | None,
    hmm_file: Path,
    cpus: int = 3,
    with_identity: bool = False,
) -> list[dict[str, Any]]:
    """Search one registry over called proteins, returning accepted hit rows.

    Pfam is searched at its own gathering cutoffs; RVDB at the pinned E-value against the pinned
    `Z`, which is the same thing as the per-model bit score `bit_threshold` derives (D-076).
    Both are then held to :data:`MIN_MODEL_COVERAGE` of the model's length, measured on the
    best-covering domain of the hit.

    `with_identity` adds `identity`, `hmm_from` and `hmm_to` — the matched region on the model
    side, and its identity to the model's consensus (:func:`consensus_identity`). Off by default
    so that A2.1's and A2.4's rows are what they have always been: those tables are published
    and digest-pinned, and a column appearing in them is a change to an artefact rather than to
    a tool. A7.5 is the caller that asks for them.
    """
    import pyhmmer
    from pyhmmer.easel import Alphabet, DigitalSequenceBlock

    amino = Alphabet.amino()
    block = DigitalSequenceBlock(amino, proteins)
    accepted: list[dict[str, Any]] = []
    options: dict[str, Any] = (
        {"bit_cutoffs": "gathering"}
        if reg.curated_cutoffs
        else {"Z": PINNED_Z, "domZ": PINNED_DOM_Z, "E": PINNED_E_VALUE}
    )

    with open_profiles(hmm_file) as handle, pyhmmer.plan7.HMMFile(handle) as hmms:
        models = hmms if restrict_to is None else (h for h in hmms if _name(h) in restrict_to)
        for top in pyhmmer.hmmsearch(models, block, cpus=cpus, **options):
            query_name = text_of(top.query.name)
            query_length = top.query.M
            for hit in top:
                if hit.included is False:
                    continue
                domain = best_domain(hit)
                coverage = best_model_coverage(hit, query_length)
                if coverage < MIN_MODEL_COVERAGE:
                    continue
                record_id, _, gene = text_of(hit.name).partition("|")
                region = best_domain_region(hit)
                row = {
                    "profile": query_name,
                    "model_length": query_length,
                    "record_id": record_id,
                    "gene": gene,
                    "score": float(hit.score),
                    "evalue": float(hit.evalue),
                    "coverage": coverage,
                    # On the protein, 1-based inclusive; the region A3.4 places rather than
                    # the whole gene (D-241). No artefact of A2.1's own carries it.
                    "target_from": None if region is None else region[0],
                    "target_to": None if region is None else region[1],
                }
                if with_identity:
                    alignment = None if domain is None else domain.alignment
                    row["identity"] = None if domain is None else consensus_identity(domain)
                    row["hmm_from"] = None if alignment is None else int(alignment.hmm_from)
                    row["hmm_to"] = None if alignment is None else int(alignment.hmm_to)
                accepted.append(row)
    return accepted

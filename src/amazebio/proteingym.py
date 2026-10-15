"""The benchmark DMS assay collection — task B2.1.

`DESIGN.md` §B2 pins the benchmark at ProteinGym v1.3 and says to use its standard splits and
its standard rank correlation "so results are comparable to the published leaderboard". This
module is the ingest: the release pin, the assay schema with taxon labels carried through, and
the metric.

Three things here are decisions rather than mechanics, and each is recorded in DECISIONS.md
rather than left for a reader to infer:

**There is no train/test split to honour in the zero-shot setting.** The benchmark's published
CV folds belong to its *supervised* benchmark, and `DESIGN.md` §4 restricts this project to
zero-shot scoring, so no fold file is used. What "standard split" means here is the published
variant list per assay, taken as given: every variant the maintainers ship for an assay is
scored, none is filtered, and the assay is the unit of analysis. Dropping variants — even
plausibly, say multi-mutants — would silently redefine the benchmark and break exactly the
comparability §B2 asks for.

**The metric is Spearman's rank correlation with ties averaged**, implemented here in the
standard library rather than by adding a dependency. Not inventing a metric: it is the same
definition, and :func:`spearman` is validated against the maintainers' own published per-assay
values for all 217 assays, which is a stronger check than any unit test could be. The
alternative — adding scipy to the lockfile for one function — is weighed in DECISIONS.md.

**The leaderboard's headline average is not the mean of the per-assay values** and this module
does not reproduce it. The maintainers state that their aggregation corrects for biases (assays
per protein family, functional groupings), so the aggregate is a weighted quantity whose
weighting is theirs. Reproducing a published *per-assay* number is therefore the honest ingest
check, and `tools/proteingym_check.py` does it for every assay rather than the one §B2 asks
for. Any pooled figure this project publishes must be its own, computed per `metrics/` and
reported per-assay first, which `AGENTS.md` requires anyway.
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import hashlib
import io
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from enum import Enum
from pathlib import Path

__all__ = [
    "RELEASE",
    "Assay",
    "ProteinGymError",
    "Release",
    "Taxon",
    "load_assay",
    "load_model_scores",
    "load_reference",
    "spearman",
    "verify_release",
]


class ProteinGymError(RuntimeError):
    """Raised when the ingest cannot stand behind what it loaded."""


class Taxon(Enum):
    """The taxon labels the benchmark ships, verbatim.

    Carried through into the analysis schema because §B5 reports by homology class and taxon,
    and because the virus/phage contrast is the whole point of the Evo arm. The labels are the
    maintainers' own and are not re-derived: `HUMAN` is a separate label from `EUKARYOTE` in
    their reference file, which is a curation choice this project inherits rather than fixes.
    """

    VIRUS = "Virus"
    PROKARYOTE = "Prokaryote"
    HUMAN = "Human"
    EUKARYOTE = "Eukaryote"


@dataclasses.dataclass(frozen=True)
class Release:
    """A pinned benchmark release: version, where each file came from, and its checksum."""

    version: str
    base_url: str
    files: Mapping[str, str]
    reference_file: str
    # Files that exist only in the maintainers' git repository, which carries no tag for this
    # version. Their URL therefore names no version and the hash is the whole pin — kept apart
    # from `files` so that asymmetry stays visible instead of reading as a version pin.
    unversioned: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def url(self, filename: str) -> str:
        return f"{self.base_url}/{filename}"


# The version `DESIGN.md` §B2 names, and the one the maintainers' own documentation calls
# latest. `files` maps the archive name to its SHA-256 as measured on acquisition — the
# publisher does not publish checksums for these archives, which is itself worth knowing: the
# pin is ours, so a silent re-cut of a release would be invisible to anyone who did not record
# one. Stated-versus-actual sizes are in artifacts/b2-1/release.json; the documented sizes are
# approximate and in one case off by more than an order of magnitude.
RELEASE = Release(
    version="v1.3",
    base_url="https://marks.hms.harvard.edu/proteingym/ProteinGym_v1.3",
    files={
        "DMS_ProteinGym_substitutions.zip": (
            "3a83766254ac9ac9984ec25cb73c6e010ea4418f5e35f143933e6b6e6473b921"
        ),
        "zero_shot_substitutions_scores.zip": (
            "3fd7cdb5e78f1d43cabfabfeb6578c252b63af23ba2ab44db0094dc3a42de36d"
        ),
    },
    reference_file="DMS_substitutions.csv",
    unversioned={
        "DMS_substitutions.csv": (
            "a8f498011532a74aa9fe556a50555a75e928c5837d19c06a87592ae04049b308"
        ),
        "DMS_substitutions_Spearman_DMS_level.csv": (
            "f432423b87f79ac9778dfac86e3d95be041d246bc618dc0a406b35b0b7466437"
        ),
        "Summary_performance_DMS_substitutions_Spearman.csv": (
            "ee61a7c09efbfbd8d9a6c9355092c798032a578fa58c6f6256b5da8778555fd4"
        ),
    },
)


@dataclasses.dataclass(frozen=True)
class Assay:
    """One DMS assay, as the benchmark's reference file describes it.

    Only the fields this project uses are lifted; the reference file carries 46 columns and
    copying all of them into a dataclass would invite treating the copy as the source. The
    file itself stays the source of truth and is checksummed.

    Attributes:
        dms_id: the benchmark's stable assay id, e.g. `BLAT_ECOLX_Stiffler_2015`.
        uniprot_id: the benchmark's protein identifier.
        taxon: the shipped taxon label.
        source_organism: free text, as shipped.
        filename: the per-assay CSV inside the substitutions archive.
        seq_len: target sequence length.
        n_singles: single-substitution variant count.
        n_multiples: multi-substitution variant count, 0 for most assays.
        selection_assay: what was measured, as shipped (e.g. `Viral replication`).
        selection_type: the coarse readout class (e.g. `Growth`, `Stability`).
        msa_depth_category: the maintainers' Low/Medium/High MSA-depth bin. B3.4's covariate
            is computed independently; this is the published bin, kept for comparability.
        doi: the assay's publication DOI, for B2.4's provenance register.
        year: publication year.
    """

    dms_id: str
    uniprot_id: str
    taxon: Taxon
    source_organism: str
    filename: str
    seq_len: int
    n_singles: int
    n_multiples: int
    selection_assay: str
    selection_type: str
    msa_depth_category: str
    doi: str
    year: str

    @property
    def n_variants(self) -> int:
        return self.n_singles + self.n_multiples

    @property
    def is_viral(self) -> bool:
        return self.taxon is Taxon.VIRUS

    def to_dict(self) -> dict[str, object]:
        d = dataclasses.asdict(self)
        d["taxon"] = self.taxon.value
        d["n_variants"] = self.n_variants
        return d


def _int(row: Mapping[str, str], key: str) -> int:
    raw = (row.get(key) or "").strip()
    try:
        return int(float(raw))
    except ValueError as exc:
        raise ProteinGymError(f"{row.get('DMS_id')}: {key}={raw!r} is not a number") from exc


def load_reference(path: str | Path) -> tuple[Assay, ...]:
    """Load the benchmark's assay reference file.

    Raises:
        ProteinGymError: on an unknown taxon label. Deliberately strict: a new label would mean
            the release changed under a pin, and silently mapping it to "other" would hide that
            from every downstream analysis that reports by taxon.
    """
    assays: list[Assay] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("taxon") or "").strip()
            try:
                taxon = Taxon(label)
            except ValueError as exc:
                raise ProteinGymError(
                    f"{row.get('DMS_id')}: unknown taxon label {label!r}. The pinned release "
                    f"ships {[t.value for t in Taxon]}; a new one means the release moved."
                ) from exc
            assays.append(
                Assay(
                    dms_id=row["DMS_id"],
                    uniprot_id=row["UniProt_ID"],
                    taxon=taxon,
                    source_organism=row.get("source_organism", ""),
                    filename=row["DMS_filename"],
                    seq_len=_int(row, "seq_len"),
                    n_singles=_int(row, "DMS_number_single_mutants"),
                    n_multiples=_int(row, "DMS_number_multiple_mutants"),
                    selection_assay=row.get("selection_assay", ""),
                    selection_type=row.get("selection_type", ""),
                    msa_depth_category=row.get("MSA_Neff_L_category", ""),
                    doi=row.get("jo", ""),
                    year=row.get("year", ""),
                )
            )
    if not assays:
        raise ProteinGymError(f"{path}: no assays found")
    return tuple(assays)


@contextlib.contextmanager
def _open_csv_member(archive: str | Path, member: str) -> Iterator[csv.DictReader]:
    """Stream one CSV member of a zip archive.

    Streamed rather than read whole because it has to be: the largest member of the score
    archive is 1.15 GB uncompressed, and materialising it as a list of dicts peaked at over
    5 GB of resident memory — enough to fail on the instance sizes this account can launch.
    Both callers make a single pass, so nothing is lost by handing back a reader.
    """
    with zipfile.ZipFile(archive) as z:
        try:
            handle = z.open(member)
        except KeyError as exc:
            raise ProteinGymError(f"{member!r} is not in {archive}") from exc
        with handle as fh:
            yield csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))


def load_assay(archive: str | Path, assay: Assay) -> dict[str, float]:
    """Measured DMS scores for one assay, keyed by the benchmark's own mutant string.

    The whole published variant list, unfiltered — see this module's docstring on what
    "standard split" means in the zero-shot setting.
    """
    member = f"DMS_ProteinGym_substitutions/{assay.filename}"
    out: dict[str, float] = {}
    with _open_csv_member(archive, member) as reader:
        for row in reader:
            try:
                out[row["mutant"]] = float(row["DMS_score"])
            except (KeyError, ValueError) as exc:
                raise ProteinGymError(f"{assay.dms_id}: bad row {row!r}") from exc
    if not out:
        raise ProteinGymError(f"{assay.dms_id}: no variants in {member}")
    return out


def load_model_scores(
    archive: str | Path, assay: Assay, model_column: str, *, member: str | None = None
) -> dict[str, float]:
    """Published per-variant scores for one model on one assay.

    The score archive holds one CSV per assay with a column per model, so the model is a column
    name rather than a file. Rows whose score is empty or non-numeric are skipped and counted
    by the caller: a model that failed on some variants is a fact about the published scores,
    not a reason to fail the ingest.
    """
    # The score archive stores its CSVs at the root, while the assay archive nests them under
    # a directory. Not symmetrical, and not worth normalising away: the member path is what it
    # is in each release, and hard-coding the wrong one fails loudly rather than silently.
    member = member or assay.filename
    out: dict[str, float] = {}
    with _open_csv_member(archive, member) as reader:
        for row in reader:
            if model_column not in row:
                raise ProteinGymError(
                    f"{assay.dms_id}: no column {model_column!r} in {member}. "
                    f"Available: {sorted(row)[:8]}..."
                )
            raw = (row.get(model_column) or "").strip()
            if not raw:
                continue
            try:
                out[row["mutant"]] = float(raw)
            except ValueError:
                continue
    return out


def _ranks(values: Sequence[float]) -> list[float]:
    """Ranks with ties averaged — the `scipy.stats.rankdata` "average" convention."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman's rank correlation, ties averaged.

    Pearson's correlation of the average ranks, which is the definition `scipy.stats.spearmanr`
    implements and the one the benchmark's own scripts call. Validated against the maintainers'
    published per-assay values for every assay in the release by `tools/proteingym_check.py` —
    that comparison, not this docstring, is the evidence that it is the same metric.

    Raises:
        ProteinGymError: on length mismatch, fewer than two points, or a constant input. A
            constant input has no defined rank correlation, and returning 0.0 for it would
            quietly turn a degenerate assay into a real-looking null.
    """
    if len(x) != len(y):
        raise ProteinGymError(f"length mismatch: {len(x)} vs {len(y)}")
    n = len(x)
    if n < 2:
        raise ProteinGymError(f"need at least two points, got {n}")

    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    dx = [a - mx for a in rx]
    dy = [b - my for b in ry]
    sxx = sum(a * a for a in dx)
    syy = sum(b * b for b in dy)
    if sxx == 0 or syy == 0:
        raise ProteinGymError("an input is constant, so rank correlation is undefined")
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / (sxx * syy) ** 0.5


def paired(
    measured: Mapping[str, float], predicted: Mapping[str, float]
) -> tuple[list[float], list[float], int]:
    """Align two score maps on their shared mutants.

    Returns the measured values, the predicted values and the number of measured variants that
    the model has no score for. The join is on the benchmark's own mutant string, never on row
    order: the score archive's row order is not guaranteed to match the assay file's, and a
    positional join would produce a plausible-looking correlation from mismatched pairs. That
    is the ingest failure this function exists to make impossible.
    """
    shared = [m for m in measured if m in predicted]
    return (
        [measured[m] for m in shared],
        [predicted[m] for m in shared],
        len(measured) - len(shared),
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release(directory: str | Path, release: Release = RELEASE) -> dict[str, str]:
    """Check staged archives against the release's recorded checksums.

    An archive with no recorded checksum is reported as `unpinned` rather than passing. The
    publisher ships no checksums of its own, so an unrecorded file is one nobody can show has
    not changed — `AGENTS.md` treats that as not yet a result.
    """
    directory = Path(directory)
    out: dict[str, str] = {}
    for name, expected in {**release.files, **release.unversioned}.items():
        path = directory / name
        if not path.exists():
            out[name] = "missing"
        elif not expected:
            out[name] = "unpinned"
        else:
            out[name] = "ok" if sha256_file(path) == expected else "CHECKSUM MISMATCH"
    return out


def by_taxon(assays: Iterable[Assay]) -> dict[str, int]:
    counts: dict[str, int] = {t.value: 0 for t in Taxon}
    for a in assays:
        counts[a.taxon.value] += 1
    return counts

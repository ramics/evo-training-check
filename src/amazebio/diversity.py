"""M3's diversity bins — task A3.4, `metrics/survival.md` §4 M3.

M3 asks, for each surviving family, how much of that family's known diversity the surviving
sequence covers. The denominator is the family's **bins**: its reference members clustered at
50% amino-acid identity over 80% of the shorter sequence. Both numbers are frozen and are not
parameters of this module.

**Where the members come from, and what that costs.** D-205 fixes them as Pfam's curated seed
alignment, `Pfam-A.seed.gz` of the pinned 38.2 release, after the project owner chose it over
the 24 GB full alignment. The seed is small: across the 1,719 viral families it holds 34,482
members, a median of six per family, and 174 families have exactly one. A family with four
bins and two of them covered reports 0.5 with a 95% interval of roughly [0.15, 0.85]. That is
not a defect of this code and it is not hidden by it — `metrics/survival.md` §6 says an
interval spanning the interesting range is reported as uninformative, and for most families
this is what M3 from the seed will be.

**The one reading this module makes.** M3 says "80% of the shorter sequence" and MMseqs2 has
no coverage mode for the shorter sequence: its modes are query, target, both, and two length
ratios. This uses `--cov-mode 0`, coverage of **both**, which is strictly harder to satisfy
than covering the shorter one alone. Erring that way splits bins more finely, which lowers
`coverage(f)` and therefore understates how much of a family survived — the direction that
cannot flatter the audit's own finding. D-206 records it.

**Clustering is per family, not global.** The specification says to cluster the family's
members, and a global pass could merge two of a family's members through a bridging sequence
from another family. 1,719 families of a few members each is a cheap price for not having to
argue about that.
"""

from __future__ import annotations

import dataclasses
import gzip
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from amazebio.survival import Interval, wilson_interval

__all__ = [
    "COVERAGE",
    "COV_MODE",
    "IDENTITY",
    "DiversityError",
    "FamilyBins",
    "SeedFamily",
    "cluster_members",
    "coverage_of",
    "iter_seed_families",
    "temporary_workdir",
]

#: Frozen by `metrics/survival.md` §4 M3. Not parameters.
IDENTITY = 0.50
COVERAGE = 0.80

#: The reading, not the specification: MMseqs2 offers no "shorter sequence" coverage mode, and
#: mode 0 — both sequences — is the strictly harder one. D-206.
COV_MODE = 0

#: Gap characters Stockholm uses. `.` is an insertion column, `-` a deletion.
_GAPS = str.maketrans("", "", ".-~")


class DiversityError(RuntimeError):
    """A refusal: the bins cannot be computed as specified."""


@dataclasses.dataclass(frozen=True, slots=True)
class SeedFamily:
    """One family's seed members, ungapped, in the order the alignment lists them."""

    accession: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.accession:
            raise DiversityError("a seed record with no accession")
        if not self.members:
            raise DiversityError(f"{self.accession}: a seed alignment with no members")


def iter_seed_families(path: str | Path) -> Iterator[SeedFamily]:
    """Parse a gzipped Stockholm multi-alignment into one record per family.

    Rows are accumulated by sequence name rather than taken line by line, because Stockholm
    permits an interleaved alignment and reading one block as the whole sequence would
    truncate every member silently. The accession is taken without its version suffix, which
    is what every other artefact in this project keys on.
    """
    path = Path(path)
    accession: str | None = None
    rows: dict[str, list[str]] = {}
    order: list[str] = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="latin-1") as handle:  # type: ignore[operator]
        for line in handle:
            if line.startswith("#=GF AC"):
                accession = line.split()[2].split(".")[0]
            elif line.startswith("//"):
                if accession is not None:
                    yield SeedFamily(
                        accession=accession,
                        members=tuple("".join(rows[n]).translate(_GAPS).upper() for n in order),
                    )
                accession, rows, order = None, {}, []
            elif line.startswith("#") or not line.strip():
                continue
            else:
                name, _, sequence = line.rstrip("\n").partition(" ")
                if not sequence.strip():
                    continue
                if name not in rows:
                    rows[name] = []
                    order.append(name)
                rows[name].append(sequence.strip())
    if accession is not None:  # pragma: no cover - a file with no terminating `//`
        raise DiversityError(f"{path}: the record for {accession} has no closing '//'")


def cluster_members(
    members: Sequence[str],
    *,
    workdir: Path,
    mmseqs: str = "mmseqs",
    identity: float = IDENTITY,
    coverage: float = COVERAGE,
    cov_mode: int = COV_MODE,
) -> tuple[int, ...]:
    """Cluster one family's members; return each member's bin index, in input order.

    Single-threaded on purpose. MMseqs2's greedy set-cover can break ties differently across
    thread counts, and a denominator that moves with the machine is not a pinned denominator.
    """
    if not members:
        raise DiversityError("clustering an empty family")
    if len(members) == 1:
        return (0,)
    workdir.mkdir(parents=True, exist_ok=True)
    fasta = workdir / "members.faa"
    fasta.write_text("".join(f">m{i}\n{s}\n" for i, s in enumerate(members)))
    out = workdir / "clu"
    argv = [
        mmseqs,
        "easy-cluster",
        str(fasta),
        str(out),
        str(workdir / "tmp"),
        "--min-seq-id",
        f"{identity:g}",
        "-c",
        f"{coverage:g}",
        "--cov-mode",
        str(cov_mode),
        "--threads",
        "1",
        "-v",
        "1",
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise DiversityError(
            f"mmseqs easy-cluster exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()[:400]}"
        )
    table = out.with_name(out.name + "_cluster.tsv")
    if not table.exists():
        raise DiversityError(f"mmseqs produced no cluster table at {table}")

    bin_of: dict[str, int] = {}
    representatives: dict[str, int] = {}
    for line in table.read_text().splitlines():
        if not line.strip():
            continue
        rep, _, member = line.partition("\t")
        index = representatives.setdefault(rep, len(representatives))
        bin_of[member] = index
    missing = [i for i in range(len(members)) if f"m{i}" not in bin_of]
    if missing:
        raise DiversityError(
            f"mmseqs placed {len(missing)} of {len(members)} members in no cluster "
            f"(first: m{missing[0]}); a member in no bin would shrink the denominator"
        )
    return tuple(bin_of[f"m{i}"] for i in range(len(members)))


@dataclasses.dataclass(frozen=True, slots=True)
class FamilyBins:
    """One family's diversity denominator, and what a coverage over it can say."""

    accession: str
    members: int
    assignment: tuple[int, ...]

    @property
    def bins(self) -> int:
        return len(set(self.assignment))

    def coverage(self, bins_hit: int) -> Interval:
        if not 0 <= bins_hit <= self.bins:
            raise DiversityError(
                f"{self.accession}: {bins_hit} bins covered of {self.bins}; a coverage outside "
                "its own denominator is an upstream join error, not a result"
            )
        return wilson_interval(bins_hit, self.bins)

    @property
    def widest_interval(self) -> float:
        """How wide a 95% interval over this denominator can be, at its worst.

        Computed before any detection is placed, because it is a property of the family's
        seed size alone and it is what decides whether this family's M3 can say anything.
        The worst case is the middle of the range, so it is evaluated at half the bins.
        """
        interval = wilson_interval(self.bins // 2, self.bins)
        return interval.high - interval.low

    def to_dict(self) -> dict[str, object]:
        return {
            "accession": self.accession,
            "members": self.members,
            "bins": self.bins,
            "widest_interval": self.widest_interval,
        }


def coverage_of(bins: Mapping[str, FamilyBins], hits: Mapping[str, int]) -> dict[str, Interval]:
    """`coverage(f)` for every family with a denominator, from a bins-hit count per family.

    A family in `hits` with no denominator is refused rather than skipped: it means the
    detection table and the registry release disagree about what families exist, and a
    coverage distribution quietly missing those families would be a distribution over a
    different universe.
    """
    unknown = sorted(set(hits) - set(bins))
    if unknown:
        raise DiversityError(
            f"{len(unknown)} families carry detections and no seed denominator "
            f"(first: {unknown[:5]}); the detection table and the registry release disagree"
        )
    return {acc: bins[acc].coverage(hits.get(acc, 0)) for acc in sorted(hits)}


def temporary_workdir() -> tempfile.TemporaryDirectory[str]:
    """A scratch directory for one family's clustering. Caller closes it."""
    return tempfile.TemporaryDirectory(prefix="amazebio-bins-")

#!/usr/bin/env python3
"""Place each surviving detection in its family's diversity bins — task A3.4, §A3, M3.

    pixi run -e dev python tools/diversity_coverage.py \
        --bins artifacts/a3-4/bins-pfam-38.2.json \
        --seed <Pfam-A.seed.gz> \
        --proteins <scratch>/a3-4-hits/pfam \
        --label evo1-strict-opengenome

The other half of A3.4. `tools/diversity_bins.py` built the denominator — each family's seed
members clustered into bins, and which member sits in which. This places the numerator:
`coverage(f) = |bins with at least one surviving detection| / |bins(f)|`, with a 95% Wilson
interval over bins (`metrics/survival.md` §4 M3).

The detections come in as one FASTA per family, retained by `detect_profiles.py
--retain-hit-proteins` during the search that found them. They are corpus residues: they are
read from ephemeral scratch and nothing of them reaches an artefact (D-103). What this tool
publishes is bin indices and counts.

**Per family, never pooled.** The corpus-level summary is the distribution of `coverage(f)` —
median and IQR across families with a detection — because a single pooled coverage at this
sample size is the fragility `DESIGN.md` §B5 warns about. A family whose interval spans the
interesting range is marked uninformative rather than quoted as a point estimate (§6), and the
count of families with no detection at all is reported beside the distribution so that a null
is not missing data.

**A detection that meets no bin is reported, not dropped.** The protein hit the family's
profile, so it is a detection of that family; failing to reach 50% identity over 80% coverage
against any seed member means the surviving sequence is more diverged than the seed's own
spread, which is a finding about the family rather than a join error. Those are counted
separately and excluded from the numerator, which understates coverage rather than inflating
it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import diversity, objectstore, repro

TASK = "A3.4"

#: The publisher's own digest for the pinned release, from Pfam 38.2's `md5_checksums`.
SEED_MD5 = "7a37e1237d5d20c35b236c9f5a9ac797"

#: An interval wider than this spans the interesting range; `metrics/survival.md` §6 says such a
#: family is reported as uninformative rather than quoted as a point estimate.
UNINFORMATIVE_WIDTH = 0.5


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def members_digest(members: Any) -> str:
    """The same digest `tools/diversity_bins.py` published, recomputed from this parse."""
    digest = hashlib.blake2b(digest_size=16)
    for member in members:
        digest.update(member.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def read_detections(path: Path) -> tuple[tuple[str, str], ...]:
    """One family's retained hit proteins, as (name, sequence). Scratch only (D-103)."""
    out: list[tuple[str, str]] = []
    name: str | None = None
    chunks: list[str] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if name is not None:
                out.append((name, "".join(chunks)))
            name, chunks = line[1:].strip(), []
        elif line.strip():
            chunks.append(line.strip())
    if name is not None:
        out.append((name, "".join(chunks)))
    return tuple(out)


def read_detection_table(path: Path) -> dict[str, set[str]]:
    """The published detections, as record ids per family.

    The retention directory holds every protein that hit, which is not the same set as the
    detections A2.1 published: a reading removes records from the surviving corpus, and a
    protein from a removed record is not a surviving detection. Placing it would raise
    coverage on evidence the table does not contain, so the table is what decides.
    """
    out: dict[str, set[str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out.setdefault(row["family_id"], set()).add(row["record_id"])
    return out


def _place(
    item: tuple[str, tuple[str, ...], tuple[int, ...], str, frozenset[str]],
) -> dict[str, Any]:
    """One family: place its detections and report which bins they reached."""
    accession, members, assignment, proteins_path, surviving = item
    retained = read_detections(Path(proteins_path))
    detections = tuple(
        (name, sequence) for name, sequence in retained if name.partition("|")[0] in surviving
    )
    not_in_table = len(retained) - len(detections)
    with tempfile.TemporaryDirectory(prefix="amazebio-place-") as scratch:
        placed = diversity.bins_hit_by(
            members,
            assignment,
            [sequence for _, sequence in detections],
            workdir=Path(scratch),
        )
    hit: set[int] = set()
    unplaced = 0
    for bins in placed:
        if bins:
            hit |= set(bins)
        else:
            unplaced += 1
    return {
        "accession": accession,
        "detections": len(detections),
        "detections_meeting_no_bin": unplaced,
        "proteins_not_in_the_table": not_in_table,
        "bins_hit": sorted(hit),
    }


def load_bins(path: Path) -> dict[str, dict[str, Any]]:
    doc = json.loads(path.read_text())
    entries = {entry["accession"]: entry for entry in doc["per_family"]}
    missing = [a for a, e in entries.items() if "assignment" not in e]
    if missing:
        raise SystemExit(
            f"{path}: {len(missing)} families carry a bin count and no assignment (first: "
            f"{missing[:3]}). A coverage needs to know which member sits in which bin, not "
            "only how many bins there are; re-run tools/diversity_bins.py."
        )
    return entries


def prepare(
    bins: dict[str, dict[str, Any]],
    seed: Path,
    proteins: Path,
    table: dict[str, set[str]],
) -> list[tuple[str, tuple[str, ...], tuple[int, ...], str, frozenset[str]]]:
    """Pair each family's retained detections with its members and bin assignment.

    The seed is re-read for the member sequences the assignment is positional over, and the
    digest published beside the assignment is recomputed here: a parse that recovered the same
    members in a different order would place every detection against the wrong bins and no
    figure downstream would look wrong.
    """
    available = {p.stem: p for p in sorted(proteins.glob("*.faa")) if p.stem in table}
    absent = sorted(set(table) - {p.stem for p in proteins.glob("*.faa")})
    if absent:
        raise SystemExit(
            f"{len(absent)} families carry published detections and no retained protein "
            f"(first: {absent[:5]}); the retention pass did not cover the band the table was "
            "assembled from, and a coverage over the rest would be a metric over a smaller "
            "set of families than it claims"
        )
    unknown = sorted(set(available) - set(bins))
    if unknown:
        raise SystemExit(
            f"{len(unknown)} families have retained detections and no seed denominator "
            f"(first: {unknown[:5]}); the detection pass and the registry release disagree "
            "about what families exist, which would make the distribution one over a "
            "different universe"
        )
    items = []
    for family in diversity.iter_seed_families(seed):
        path = available.get(family.accession)
        if path is None:
            continue
        entry = bins[family.accession]
        if members_digest(family.members) != entry["members_digest"]:
            raise SystemExit(
                f"{family.accession}: this parse of {seed.name} does not reproduce the members "
                "the bin assignment was built over. The assignment is positional, so placing "
                "against a different list would be silently wrong; refusing."
            )
        items.append(
            (
                family.accession,
                family.members,
                tuple(entry["assignment"]),
                str(path),
                frozenset(table[family.accession]),
            )
        )
    found = {i[0] for i in items}
    unread = sorted(set(available) - found)
    if unread:
        raise SystemExit(
            f"{len(unread)} families with detections were not found in {seed.name} "
            f"(first: {unread[:5]}); the denominator and the seed release disagree"
        )
    return items


def build(
    bins: dict[str, dict[str, Any]],
    items: list[tuple[str, tuple[str, ...], tuple[int, ...], str, frozenset[str]]],
    *,
    label: str,
    workers: int,
) -> dict[str, Any]:
    started = time.time()
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n, row in enumerate(pool.map(_place, items), start=1):
            rows.append(row)
            if n % 50 == 0 or n == len(items):
                rate = n / max(time.time() - started, 1e-9)
                print(
                    f"  {n}/{len(items)} families, {rate:.2f}/s, "
                    f"{(len(items) - n) / max(rate, 1e-9) / 60:.0f} min left",
                    flush=True,
                )

    per_family = []
    for row in sorted(rows, key=lambda r: r["accession"]):
        family = diversity.FamilyBins(
            accession=row["accession"],
            members=bins[row["accession"]]["members"],
            assignment=tuple(bins[row["accession"]]["assignment"]),
        )
        interval = family.coverage(len(row["bins_hit"]))
        width = interval.high - interval.low
        per_family.append(
            {
                **row,
                "bins": family.bins,
                "coverage": round(interval.estimate, 4),
                "ci_low": round(interval.low, 4),
                "ci_high": round(interval.high, 4),
                "interval_width": round(width, 4),
                "uninformative": width > UNINFORMATIVE_WIDTH,
            }
        )

    covered = [r["coverage"] for r in per_family]
    informative = [r["coverage"] for r in per_family if not r["uninformative"]]
    return {
        "task": TASK,
        "design_ref": "§A3",
        "metric": "M3",
        "decisions": ["D-195", "D-205", "D-206", "D-239", "D-240"],
        "label": label,
        "registry": {"id": "pfam", "version": "38.2"},
        "parameters": {
            "identity": diversity.IDENTITY,
            "coverage": diversity.COVERAGE,
            "cov_mode": diversity.COV_MODE,
            "uninformative_interval_width": UNINFORMATIVE_WIDTH,
        },
        "families_in_universe": len(bins),
        "families_with_a_detection": len(per_family),
        "families_with_no_detection": len(bins) - len(per_family),
        "detections_placed": sum(r["detections"] for r in per_family),
        "detections_meeting_no_bin": sum(r["detections_meeting_no_bin"] for r in per_family),
        "proteins_not_in_the_table": sum(r["proteins_not_in_the_table"] for r in per_family),
        "distribution": _distribution(covered),
        "distribution_informative_only": _distribution(informative),
        "families_uninformative": sum(1 for r in per_family if r["uninformative"]),
        "per_family": per_family,
    }


def _distribution(values: list[float]) -> dict[str, Any]:
    """Median and IQR, never a pooled coverage (`metrics/survival.md` §4 M3)."""
    if not values:
        return {"families": 0, "median": None, "q1": None, "q3": None}
    ordered = sorted(values)
    if len(ordered) < 4:
        q1 = q3 = None
    else:
        q1, _, q3 = statistics.quantiles(ordered, n=4)
    return {
        "families": len(ordered),
        "median": round(statistics.median(ordered), 4),
        "q1": None if q1 is None else round(q1, 4),
        "q3": None if q3 is None else round(q3, 4),
        "min": ordered[0],
        "max": ordered[-1],
    }


def summarise(doc: dict[str, Any]) -> str:
    dist, info = doc["distribution"], doc["distribution_informative_only"]

    def band(d: dict[str, Any]) -> str:
        if not d["families"]:
            return "no families"
        iqr = "IQR undefined" if d["q1"] is None else f"IQR {d['q1']:.3f}-{d['q3']:.3f}"
        return f"median {d['median']:.3f}, {iqr}, over {d['families']:,} families"

    return "\n".join(
        [
            f"M3 diversity coverage — {doc['label']}, pfam/38.2",
            "",
            f"{doc['families_with_a_detection']:,} of {doc['families_in_universe']:,} families "
            f"carry a detection; {doc['families_with_no_detection']:,} carry none and are not in "
            "the distribution below (they are in M1's denominator, where the null is visible).",
            "",
            f"coverage(f) across families with a detection: {band(dist)}",
            f"  of those, {doc['families_uninformative']:,} have an interval wider than "
            f"{doc['parameters']['uninformative_interval_width']} and are uninformative by "
            "metrics/survival.md §6",
            f"  informative families only: {band(info)}",
            "",
            f"{doc['detections_placed']:,} detections placed, of which "
            f"{doc['detections_meeting_no_bin']:,} met no bin at the clustering threshold and "
            "are excluded from the numerator — the surviving sequence is further from every "
            "seed member than the seed members are from each other, which lowers coverage "
            "rather than raising it.",
            "",
            "No pooled coverage figure is reported: the corpus-level summary is this "
            "distribution (metrics/survival.md §4 M3).",
        ]
    )


def durable_destination(limit: int | None) -> tuple[str | None, str | None]:
    """Where this run publishes, and why it does not (D-232)."""
    if limit is not None:
        return None, f"--limit {limit}: part of the family set, not the metric"
    return objectstore.durable_results("a3-4"), None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--bins", type=Path, required=True, help="bins-pfam-38.2.json")
    ap.add_argument("--seed", type=Path, required=True, help="Pfam-A.seed.gz, pinned release")
    ap.add_argument(
        "--proteins",
        type=Path,
        required=True,
        help="retained hit proteins, one FASTA per family, in ephemeral scratch (D-103)",
    )
    ap.add_argument(
        "--detections",
        type=Path,
        required=True,
        help="A2.1's published detections for this release, as JSONL. Only the records it "
        "names are placed: a protein that hit but whose record a reading removes is not a "
        "surviving detection.",
    )
    ap.add_argument("--label", required=True, help="which reading and release these came from")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a3-4"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None, help="first N families; for a probe")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    digest = _md5(args.seed)
    if digest != SEED_MD5:
        raise SystemExit(
            f"{args.seed}: md5 {digest} does not match the publisher's {SEED_MD5}. The members "
            "the bins were built over come from the pinned release, so this is a refusal."
        )

    bins = load_bins(args.bins)
    table = read_detection_table(args.detections)
    items = prepare(bins, args.seed, args.proteins, table)
    if not items:
        raise SystemExit(
            f"{args.proteins} holds no family FASTA. Run the detection pass with "
            "--retain-hit-proteins; a coverage over nothing is not a null, it is a missing input."
        )
    items = items[: args.limit]
    print(f"{len(items)} families with detections, of {len(bins)} in the universe")

    durable, exempt = durable_destination(args.limit)
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = f"coverage-pfam-38.2-{args.label}"
    try:
        with repro.run(
            TASK,
            seed=None,  # placement is deterministic at one thread; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-{stem}.json",
            durable=durable,
            durable_exempt=exempt,
        ) as manifest:
            manifest.parameter("identity", diversity.IDENTITY)
            manifest.parameter("coverage", diversity.COVERAGE)
            manifest.parameter("cov_mode", diversity.COV_MODE)
            manifest.parameter("label", args.label)
            manifest.parameter("limit", args.limit)
            manifest.parameter("decisions", ["D-195", "D-205", "D-206", "D-239", "D-240"])
            manifest.input_file(args.seed, role="pfam seed alignment")
            manifest.input_file(args.bins, role="diversity bins")
            manifest.input_file(args.detections, role="published detections")
            doc = build(bins, items, label=args.label, workers=args.workers)
            (args.outdir / f"{stem}.json").write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n"
            )
            (args.outdir / f"{stem}.md").write_text(summarise(doc) + "\n")
            manifest.output_file(args.outdir / f"{stem}.json", role="coverage")
            manifest.output_file(args.outdir / f"{stem}.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print()
    print(summarise(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

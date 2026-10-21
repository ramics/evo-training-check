#!/usr/bin/env python3
"""Place the surviving detections into M3's diversity bins — task A3.4, §A3, D-239.

    pixi run -e dev python tools/place_detections.py \
        --hit-proteins "$AMAZEBIO_SCRATCH/a3-4-hits/pfam" \
        --detections artifacts/a2-1/detections-pfam-evo1-literal-opengenome.jsonl \
        --seed data/profiles/pfam/38.2/Pfam-A.seed.gz \
        --dat data/profiles/pfam/38.2/Pfam-A.hmm.dat.gz \
        --bins artifacts/a3-4/bins-pfam-38.2.json

`tools/diversity_bins.py` built the denominator: each viral Pfam family's seed members clustered
at the frozen 50% identity over 80% coverage. This is the numerator. For every family with a
surviving detection it asks which of that family's bins the detection reaches, under the rule
D-239 fixed before any coverage figure existed — the same frozen criterion the members were
grouped by, searched against every member rather than a representative, one detection counting
for every bin it meets, and a detection that meets none counted apart as surviving sequence the
family's seed diversity does not represent.

**Where the residues come from.** No A2 artefact carries sequence (D-195, D-103), so
`detect_profiles.py --emit-hit-proteins` writes the hitting genes' residues to ephemeral scratch
as its search passes over them, and this tool reads that. The alternative was a second 35 GB
corpus pass to re-derive residues the first pass already held. What it writes is each hit's
matched domain region rather than the whole gene, because the members are aligned regions and
the criterion requires 80% coverage of both sides: comparing a protein with a domain measures
the length difference and nothing else (D-241).

**The corpus summary is a distribution, never a pooled figure** (`metrics/survival.md` §4 M3).
A pooled coverage would average a family with 421 bins against a family with one, and the
finding here is in the shape of the distribution: most families' seed alignments are too small
for an informative interval at any corpus depth, which is a property of the registry rather
than of the filter under audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import diversity, objectstore, profiles, repro
from amazebio.survival import wilson_interval

TASK = "A3.4"

#: The publisher's own digest for the pinned release, as `tools/diversity_bins.py` pins it. The
#: denominator has to come from the same bytes the bins were built from, or the join is between
#: two different universes.
SEED_MD5 = "7a37e1237d5d20c35b236c9f5a9ac797"

#: `metrics/survival.md` §6: a family whose 95% interval at half coverage spans more than half
#: the range cannot say anything about coverage, whatever the detections are.
INFORMATIVE_WIDTH = 0.5


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def read_detection_records(path: Path) -> dict[str, set[str]]:
    """Family -> the record ids carrying a detection of it, from one reading's hit rows."""
    by_family: dict[str, set[str]] = {}
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            by_family.setdefault(row["family_id"], set()).add(row["record_id"])
    return by_family


def read_hit_proteins(directory: Path, accession: str, records: set[str]) -> dict[str, str]:
    """The residues of this family's hit genes, restricted to one reading's surviving records.

    The scratch FASTA is written by a search that is shared across the three readings — they
    differ in what they remove, not in the residues — so the reading's own record set is what
    selects from it. A gene whose record this reading removes is not a detection of this
    reading and is dropped here rather than counted.
    """
    path = directory / f"{accession}.faa"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    name: str | None = None
    with path.open() as handle:
        for raw in handle:
            if raw.startswith(">"):
                name = raw[1:].strip()
                continue
            if name is None:
                continue
            if name.partition("|")[0] in records:
                out[name] = raw.strip()
            name = None
    return out


def _place(item: tuple[str, tuple[str, ...], dict[str, str], int]) -> dict[str, Any]:
    """One family: rebuild its bins, then place its detections into them.

    The bins are rebuilt rather than read, because the published bins artefact carries each
    family's bin *count* and not which member sits in which bin. The clustering is deterministic
    at one thread (D-206), so the rebuild is checked against that published count and a
    disagreement is a refusal: a denominator that moved since the bins were published would make
    every coverage figure here incomparable with the one it is reported beside.
    """
    accession, members, detections, expected_bins = item
    with tempfile.TemporaryDirectory(prefix="amazebio-place-") as scratch:
        workdir = Path(scratch)
        assignment = diversity.cluster_members(members, workdir=workdir / "cluster")
        bins = len(set(assignment))
        if bins != expected_bins:
            raise diversity.DiversityError(
                f"{accession}: rebuilt {bins} bins where the published artefact has "
                f"{expected_bins}; the denominator is not reproducing and nothing placed in it "
                "can be reported beside the published bin counts"
            )
        placement = diversity.place_detections(
            members,
            detections,
            assignment,
            accession=accession,
            workdir=workdir / "search",
        )
    interval = wilson_interval(len(placement.bins_hit), bins)
    return {
        "accession": accession,
        "members": len(members),
        "bins": bins,
        "bins_hit": len(placement.bins_hit),
        "coverage": len(placement.bins_hit) / bins,
        "ci_low": interval.low,
        "ci_high": interval.high,
        "detections": placement.detections,
        "detections_placed": placement.placed,
        "detections_unplaced": placement.unplaced,
    }


def build(
    *,
    hit_proteins: Path,
    detections_path: Path,
    seed: Path,
    dat: Path,
    bins_doc: dict[str, Any],
    workers: int,
    limit: int | None,
) -> dict[str, Any]:
    published = {row["accession"]: row for row in bins_doc["per_family"]}
    viral = profiles.select_viral_families(dat)
    members_of = {
        f.accession: f.members for f in diversity.iter_seed_families(seed) if f.accession in viral
    }
    by_family = read_detection_records(detections_path)
    unknown = sorted(set(by_family) - set(published))
    if unknown:
        raise SystemExit(
            f"{len(unknown)} families carry detections and have no published bins "
            f"(first: {unknown[:5]}); the detection table and the bins artefact disagree about "
            "what families exist, and a coverage distribution missing those families would be a "
            "distribution over a different universe"
        )

    items = [
        (
            accession,
            members_of[accession],
            read_hit_proteins(hit_proteins, accession, records),
            published[accession]["bins"],
        )
        for accession, records in sorted(by_family.items())
    ][:limit]
    without_residues = [a for a, _, d, _ in items if not d]
    if without_residues:
        raise SystemExit(
            f"{len(without_residues)} of {len(items)} families with detections have no residues "
            f"in {hit_proteins} (first: {without_residues[:5]}). The search that wrote that "
            "directory covered different records than this detection table does; placing a "
            "subset would understate coverage silently. Re-run the search for this release and "
            "band with --emit-hit-proteins."
        )
    print(
        f"{len(items):,} families with detections, "
        f"{sum(len(d) for _, _, d, _ in items):,} hit genes to place",
        flush=True,
    )

    started = time.time()
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n, row in enumerate(pool.map(_place, items), start=1):
            rows.append(row)
            if n % 50 == 0 or n == len(items):
                rate = n / max(time.time() - started, 1e-9)
                print(
                    f"  {n}/{len(items)} families, {rate:.1f}/s, "
                    f"{(len(items) - n) / max(rate, 1e-9) / 60:.0f} min left",
                    flush=True,
                )

    informative = [
        row for row in rows if published[row["accession"]]["widest_interval"] <= INFORMATIVE_WIDTH
    ]
    totals = Counter()
    for row in rows:
        totals["detections"] += row["detections"]
        totals["placed"] += row["detections_placed"]
        totals["unplaced"] += row["detections_unplaced"]

    return {
        "task": TASK,
        "design_ref": "§A3",
        "metric": "M3",
        "decisions": ["D-195", "D-205", "D-206", "D-239", "D-240", "D-241"],
        "detections_from": detections_path.name,
        "bins_from": {"seed_md5": bins_doc["seed_md5"], "families": bins_doc["families"]},
        "registry": bins_doc["registry"],
        "estimate_kind": "lower_bound",
        "parameters": {
            "identity": diversity.IDENTITY,
            "coverage": diversity.COVERAGE,
            "cov_mode": diversity.COV_MODE,
            "search_evalue": diversity.SEARCH_EVALUE,
            "search_sensitivity": diversity.SEARCH_SENSITIVITY,
            "placement_rule": (
                "a detection joins a bin when it meets the same frozen criterion against any "
                "member of that bin; it may join several and each counts; one that joins no bin "
                "is reported apart (D-239)"
            ),
            "informative_interval_width": INFORMATIVE_WIDTH,
        },
        "families_with_detections": len(rows),
        "families_in_universe": bins_doc["families"],
        "detections": dict(totals),
        "coverage_distribution": _distribution([row["coverage"] for row in rows]),
        "coverage_distribution_informative": _distribution(
            [row["coverage"] for row in informative]
        ),
        "informative_families": len(informative),
        "per_family": sorted(rows, key=lambda row: row["accession"]),
        "reading_this_table": (
            "`coverage` is the share of a family's diversity bins holding at least one surviving "
            "detection. The corpus figure is the distribution of those shares and never a pooled "
            "coverage: the families run from one bin to 421 and pooling would weight them as if "
            "they were one measurement. `estimate_kind` is `lower_bound` on two counts — the "
            "detections come from a sampled search, so a bin with no detection may hold surviving "
            "material nothing read, and the bins come from Pfam's seed alignment, which is a "
            "sample of each family's diversity rather than all of it. Families whose interval at "
            "half coverage spans more than half the range are reported in the distribution and "
            "again in `coverage_distribution_informative` without them, because their coverage "
            "cannot be distinguished from chance whatever it reads (metrics/survival.md §6)."
        ),
    }


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"families": 0}
    ordered = sorted(values)
    quartiles = statistics.quantiles(ordered, n=4) if len(ordered) > 1 else [ordered[0]] * 3
    return {
        "families": len(ordered),
        "median": round(statistics.median(ordered), 4),
        "q1": round(quartiles[0], 4),
        "q3": round(quartiles[2], 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
        "families_at_full_coverage": sum(1 for v in ordered if v >= 1.0),
        "families_at_zero": sum(1 for v in ordered if v == 0.0),
    }


def summarise(doc: dict[str, Any]) -> str:
    whole, informative = doc["coverage_distribution"], doc["coverage_distribution_informative"]
    detections = doc["detections"]
    lines = [
        f"M3 from {doc['detections_from']}",
        "",
        f"{doc['families_with_detections']:,} of {doc['families_in_universe']:,} families carry "
        f"a surviving detection; {detections['detections']:,} hit genes placed",
        f"  {detections['placed']:,} met a bin, {detections['unplaced']:,} met none "
        f"({detections['unplaced'] / max(detections['detections'], 1):.1%}) — surviving sequence "
        "the family's seed diversity does not represent",
        "",
        "coverage(f), all families with a detection:",
        f"  median {whole['median']:.3f}, IQR {whole['q1']:.3f}-{whole['q3']:.3f}",
        f"  {whole['families_at_full_coverage']:,} families cover every bin, "
        f"{whole['families_at_zero']:,} cover none",
        "",
        f"coverage(f), the {informative.get('families', 0):,} families whose interval can say "
        "something:",
    ]
    if informative.get("families"):
        lines += [
            f"  median {informative['median']:.3f}, IQR "
            f"{informative['q1']:.3f}-{informative['q3']:.3f}",
            f"  {informative['families_at_full_coverage']:,} cover every bin, "
            f"{informative['families_at_zero']:,} cover none",
        ]
    lines += [
        "",
        "A lower bound twice over: the detections come from a sampled search, and the bins come "
        "from a seed alignment that samples each family's diversity.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--hit-proteins", type=Path, required=True, help="scratch FASTA per family")
    ap.add_argument("--detections", type=Path, required=True, help="one reading's hit rows")
    ap.add_argument("--seed", type=Path, required=True, help="Pfam-A.seed.gz, pinned release")
    ap.add_argument("--dat", type=Path, required=True, help="Pfam-A.hmm.dat.gz, same release")
    ap.add_argument("--bins", type=Path, required=True, help="bins-pfam-38.2.json")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a3-4"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N families; for a probe")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    digest = _md5(args.seed)
    if digest != SEED_MD5:
        raise SystemExit(
            f"{args.seed}: md5 {digest} does not match the publisher's {SEED_MD5}. The members "
            "must be the bytes the bins were built from, so this is a refusal."
        )
    bins_doc = json.loads(args.bins.read_text())
    if bins_doc.get("seed_md5") != SEED_MD5:
        raise SystemExit(
            f"{args.bins} was built from seed md5 {bins_doc.get('seed_md5')}, not {SEED_MD5}"
        )

    stem = args.detections.name.removeprefix("detections-").removesuffix(".jsonl")
    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=None,  # clustering and search are deterministic at one thread
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-coverage-{stem}.json",
            durable=objectstore.durable_results("a3-4"),
        ) as manifest:
            manifest.parameter("identity", diversity.IDENTITY)
            manifest.parameter("coverage", diversity.COVERAGE)
            manifest.parameter("cov_mode", diversity.COV_MODE)
            manifest.parameter("search_evalue", diversity.SEARCH_EVALUE)
            manifest.parameter("search_sensitivity", diversity.SEARCH_SENSITIVITY)
            manifest.parameter("decisions", ["D-195", "D-205", "D-206", "D-239", "D-240", "D-241"])
            manifest.parameter("limit", args.limit)
            manifest.input_file(args.seed, role="pfam seed alignment")
            manifest.input_file(args.dat, role="pfam family metadata")
            manifest.input_file(args.bins, role="diversity bins")
            manifest.input_file(args.detections, role="detections")
            doc = build(
                hit_proteins=args.hit_proteins,
                detections_path=args.detections,
                seed=args.seed,
                dat=args.dat,
                bins_doc=bins_doc,
                workers=args.workers,
                limit=args.limit,
            )
            out = args.outdir / f"coverage-{stem}.json"
            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            (args.outdir / f"coverage-{stem}.md").write_text(summarise(doc) + "\n")
            manifest.output_file(out, role="m3 coverage")
            manifest.output_file(args.outdir / f"coverage-{stem}.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

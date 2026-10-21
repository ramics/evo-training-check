#!/usr/bin/env python3
"""Build M3's diversity denominator from Pfam's seed alignment — task A3.4, §A3.

    pixi run -e dev python tools/diversity_bins.py --seed <Pfam-A.seed.gz> --dat <Pfam-A.hmm.dat.gz>

One bin set per viral Pfam family: its seed members clustered at the frozen 50% identity over
80% coverage (`metrics/survival.md` §4 M3). D-205 fixes the seed alignment as the member
source and D-206 records the one reading this needs — MMseqs2 has no coverage mode for "the
shorter sequence", so both sequences are required to be covered, which splits bins more finely
and therefore understates coverage rather than flattering it.

This is the cheap half of A3.4. The other half — placing each surviving detection into a bin —
needs the surviving sequence, which no A2 artefact carries (D-195), so it is a corpus pass
with its own declared depth and is not run here. What this half hands it is `per_family`:
each family's bin assignment, positional over the seed members, with a digest of those
members so the placement pass can prove it re-read the same list in the same order.

**Per family, not globally.** A global clustering of all 34,482 members takes 18 seconds
against about 70 minutes for 1,545 separate runs, and the specification says to cluster the
family's members. The shortcut was measured rather than assumed: on a seeded sample of 120
families it agreed exactly on 111, and the nine differences ran in both directions by one to
four bins on the largest families — greedy set-cover breaking ties against a different
candidate pool, not cross-family merging. Small, but it is a different operation from the one
the frozen metric names, so the slow one is what runs and the comparison is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import diversity, objectstore, profiles, repro

TASK = "A3.4"

#: The publisher's own digest for the pinned release, from Pfam 38.2's `md5_checksums`.
SEED_MD5 = "7a37e1237d5d20c35b236c9f5a9ac797"


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def members_digest(members: Sequence[str]) -> str:
    """A digest of one family's members, in the order the seed alignment lists them.

    The bin assignment is positional: entry `i` is the bin of member `i`. Anything that
    re-reads the seed to recover the sequences has to land on the same list in the same
    order, so the digest travels with the assignment and the placement pass refuses a
    parse that does not reproduce it.
    """
    digest = hashlib.blake2b(digest_size=16)
    for member in members:
        digest.update(member.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _bins(item: tuple[str, tuple[str, ...]]) -> tuple[str, int, tuple[int, ...], str]:
    accession, members = item
    with tempfile.TemporaryDirectory(prefix="amazebio-bins-") as scratch:
        assignment = diversity.cluster_members(members, workdir=Path(scratch))
    return accession, len(members), assignment, members_digest(members)


def family_entry(family: diversity.FamilyBins, digest: str) -> dict[str, Any]:
    """One family's published record: its counts, its bin assignment and its members' digest."""
    return {**family.to_dict(), "assignment": list(family.assignment), "members_digest": digest}


def build(seed: Path, dat: Path, *, workers: int, limit: int | None = None) -> dict[str, Any]:
    viral = profiles.select_viral_families(dat)
    families = {
        f.accession: f.members for f in diversity.iter_seed_families(seed) if f.accession in viral
    }
    missing = sorted(set(viral) - set(families))
    if missing:
        raise SystemExit(
            f"{len(missing)} viral families have no seed record (first: {missing[:5]}); the "
            "universe and the seed release disagree, which would shrink the denominator"
        )
    items = sorted(families.items())[:limit]
    print(f"{len(items)} viral families, {sum(len(m) for _, m in items):,} seed members")

    started = time.time()
    out: dict[str, diversity.FamilyBins] = {}
    digests: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n, (accession, members, assignment, digest) in enumerate(
            pool.map(_bins, items), start=1
        ):
            out[accession] = diversity.FamilyBins(
                accession=accession, members=members, assignment=assignment
            )
            digests[accession] = digest
            if n % 100 == 0 or n == len(items):
                rate = n / max(time.time() - started, 1e-9)
                print(
                    f"  {n}/{len(items)} families, {rate:.1f}/s, "
                    f"{(len(items) - n) / max(rate, 1e-9) / 60:.0f} min left",
                    flush=True,
                )

    counts = [b.bins for b in out.values()]
    widths = [b.widest_interval for b in out.values()]
    return {
        "task": TASK,
        "design_ref": "§A3",
        "decisions": ["D-195", "D-205", "D-206"],
        "registry": {"id": "pfam", "version": "38.2", "members_from": "Pfam-A.seed.gz"},
        "seed_md5": SEED_MD5,
        "parameters": {
            "identity": diversity.IDENTITY,
            "coverage": diversity.COVERAGE,
            "cov_mode": diversity.COV_MODE,
            "cov_mode_note": (
                "MMseqs2 has no coverage mode for the shorter sequence; mode 0 requires both "
                "and is strictly harder, so bins split more finely and coverage is understated "
                "rather than overstated (D-206)"
            ),
            "threads_per_family": 1,
            "clustered": "per family",
        },
        "families": len(out),
        "members": sum(b.members for b in out.values()),
        "bins_total": sum(counts),
        "bins": {
            "median": statistics.median(counts),
            "mean": round(statistics.mean(counts), 2),
            "min": min(counts),
            "max": max(counts),
            "families_with_one_bin": sum(1 for c in counts if c == 1),
            "families_under_five_bins": sum(1 for c in counts if c < 5),
        },
        "interval_width_at_half_coverage": {
            "median": round(statistics.median(widths), 4),
            "families_wider_than_half_the_range": sum(1 for w in widths if w > 0.5),
        },
        "per_family": [
            family_entry(b, digests[b.accession])
            for b in sorted(out.values(), key=lambda b: b.accession)
        ],
    }


def summarise(doc: dict[str, Any]) -> str:
    bins, widths = doc["bins"], doc["interval_width_at_half_coverage"]
    return "\n".join(
        [
            f"{doc['families']:,} viral Pfam families, {doc['members']:,} seed members, "
            f"{doc['bins_total']:,} bins",
            "",
            f"bins per family: median {bins['median']}, mean {bins['mean']}, " f"max {bins['max']}",
            f"  {bins['families_with_one_bin']:,} families have one bin "
            f"({bins['families_with_one_bin'] / doc['families']:.1%})",
            f"  {bins['families_under_five_bins']:,} have fewer than five "
            f"({bins['families_under_five_bins'] / doc['families']:.1%})",
            "",
            "what a coverage of one half could say, as a 95% interval width:",
            f"  median {widths['median']:.3f}",
            f"  {widths['families_wider_than_half_the_range']:,} families "
            f"({widths['families_wider_than_half_the_range'] / doc['families']:.1%}) have an "
            "interval wider than half the range, so their M3 is uninformative by "
            "metrics/survival.md §6 whatever the detections turn out to be",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--seed", type=Path, required=True, help="Pfam-A.seed.gz, pinned release")
    ap.add_argument("--dat", type=Path, required=True, help="Pfam-A.hmm.dat.gz, same release")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a3-4"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N families; for a probe")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    digest = _md5(args.seed)
    if digest != SEED_MD5:
        raise SystemExit(
            f"{args.seed}: md5 {digest} does not match the publisher's {SEED_MD5}. The "
            "denominator must come from the pinned release, so this is a refusal, not a warning."
        )

    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=None,  # clustering is deterministic at one thread; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-bins.json",
            durable=objectstore.durable_results("a3-4"),
        ) as manifest:
            manifest.parameter("identity", diversity.IDENTITY)
            manifest.parameter("coverage", diversity.COVERAGE)
            manifest.parameter("cov_mode", diversity.COV_MODE)
            manifest.parameter("members_from", "Pfam-A.seed.gz")
            manifest.parameter("decisions", ["D-195", "D-205", "D-206"])
            manifest.parameter("limit", args.limit)
            manifest.input_file(args.seed, role="pfam seed alignment")
            manifest.input_file(args.dat, role="pfam family metadata")
            doc = build(args.seed, args.dat, workers=args.workers, limit=args.limit)
            (args.outdir / "bins-pfam-38.2.json").write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n"
            )
            (args.outdir / "bins-pfam-38.2.md").write_text(summarise(doc) + "\n")
            manifest.output_file(args.outdir / "bins-pfam-38.2.json", role="bins")
            manifest.output_file(args.outdir / "bins-pfam-38.2.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

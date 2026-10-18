#!/usr/bin/env python3
"""Join the exposure pass to band 1 and report the two-tier curve — A1.6, D-158 and D-160.

Three inputs meet here, and each answers a different part of D-158:

* **The exposure rows**, one file per tier, from `tools/seed_exclusivity.py`: a verdict per
  viral UniRef100 cluster at that tier's identity.
* **The seed set**, from the staged `viral-seeds.faa`. Band 1's sample is the hash rule
  `bucket_of(id, 100) == 0` rather than a stored list, so the realised sample regenerates
  from this file alone — which is the only reason D-158's first denominator survived band 1
  keeping no identifier (D-160).
* **The seed-hit sidecars**, one per cell from the re-run: which seeds produced a counted
  record under that cell's reading. D-158's second denominator, and the one band 1 as
  originally run could not supply.

**No blended number is produced, by construction.** D-158 fixes the two tiers as a two-point
curve with no interpolation and no chosen cut, so this writes them side by side and offers no
field that combines them. If a later reader wants one number they have to decide on a
threshold themselves, in the open, which is the whole point.

**Nothing identifier-bearing is written to the report.** Counts and shares only, per D-125 as
amended by D-126; the ids stay in the staged disclosure package they came from.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import exclusivity, repro, seeds

#: `>UniRef100_X` at the start of a FASTA header. `write_fasta` emits a bare cluster id
#: because MMseqs2 keys on the first whitespace-delimited token, so there is nothing after it.
_HEADER = re.compile(rb">(\S+)")

#: A seed-hit sidecar row: the coverage reading, then the query id.
_HIT_ROW = re.compile(r"^(\d+)\t(\S+)$")


def _open(path: Path):  # type: ignore[no-untyped-def]
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def iter_seed_ids(fasta: Path) -> Iterator[str]:
    """Cluster ids from a seed FASTA, header lines only.

    Streamed rather than read, because the staged seed set is 1.25 GB of which the ids are a
    few tens of megabytes; holding the sequences to count the headers would be a gigabyte of
    resident memory for no purpose.
    """
    with _open(fasta) as handle:
        for line in handle:
            if line.startswith(b">"):
                m = _HEADER.match(line)
                if m is not None:
                    yield m.group(1).decode("ascii", "replace")


def read_verdicts(rows: Path) -> dict[str, str]:
    """The verdict per cluster from one tier's rows, strongest claim kept.

    A cluster can appear more than once — it is reached through every viral member it has —
    so this folds with the same precedence `Tally` uses rather than letting the last row win.
    """
    tally = exclusivity.Tally(name="rows", tier=rows.name)
    with _open(rows) as handle:
        for line in handle:
            ident, _, verdict = line.decode().rstrip("\n").partition("\t")
            if verdict:
                tally.observe(ident, verdict)
    return tally.verdicts


def read_seed_hits(path: Path) -> dict[int, set[str]]:
    """Per reading, the seeds that produced a counted record in one cell."""
    out: dict[int, set[str]] = {}
    with _open(path) as handle:
        for raw in handle:
            m = _HIT_ROW.match(raw.decode().rstrip("\n"))
            if m is None:
                continue
            out.setdefault(int(m.group(1)), set()).add(m.group(2))
    return out


def summarise(
    tier: str,
    verdicts: dict[str, str],
    sampled: set[str],
    cells: dict[str, dict[int, set[str]]],
) -> dict[str, object]:
    """Both of D-158's denominators for one tier.

    The seed set is the denominator in both cases, never the rows: a seed the pass emitted no
    row for is `UNDETERMINED` and stays in the denominator. Dropping it would shrink the
    denominator and flatter the share, which is the error the two-denominator rule exists to
    catch.
    """
    tally = exclusivity.Tally(name="all-sampled", tier=tier, verdicts=dict(verdicts))
    out: dict[str, object] = {
        "tier": tier,
        "all_sampled_seeds": tally.summarise(sampled),
        "seeds_with_hits": [],
    }
    per_cell: list[dict[str, object]] = []
    for slug in sorted(cells):
        for mode in sorted(cells[slug]):
            hit = cells[slug][mode]
            stray = hit - sampled
            if stray:
                raise SystemExit(
                    f"cell {slug} reading {mode} names {len(stray):,} seeds that are not in "
                    f"the realised sample (e.g. {sorted(stray)[0]}). The sidecar and the seed "
                    "denominator describe different bands; joining them would report a share "
                    "over a denominator it was not measured against."
                )
            row = exclusivity.Tally(
                name=f"{slug}/mode{mode}", tier=tier, verdicts=dict(verdicts)
            ).summarise(hit)
            row["cell"] = slug
            row["reading"] = mode
            per_cell.append(row)
    out["seeds_with_hits"] = per_cell
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--rows",
        action="append",
        required=True,
        metavar="TIER=PATH",
        help="one tier's exposure rows, e.g. uniref90=artifacts/a1-6/exclusivity-rows-"
        "2023_02-uniref90.tsv.gz. Repeat per tier; the tiers are reported separately and "
        "never combined (D-158)",
    )
    ap.add_argument("--seed-fasta", required=True, type=Path)
    ap.add_argument(
        "--seed-denominator",
        type=int,
        default=100,
        help="the band whose sample this reports over; 100 is band 1 (default: %(default)s)",
    )
    ap.add_argument(
        "--seed-hits",
        action="append",
        default=[],
        type=Path,
        help="a cell's seed-hit sidecar from the band re-run. Repeat per cell; without any, "
        "only the first denominator is reported and the report says so",
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-6"))
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--code-commit")
    args = ap.parse_args(argv)

    pairs: dict[str, Path] = {}
    for spec in args.rows:
        tier, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--rows wants TIER=PATH, got {spec!r}")
        pairs[tier] = Path(path)

    args.outdir.mkdir(parents=True, exist_ok=True)
    out = args.outdir / f"exposure-q{args.seed_denominator}.json"

    print(f"reading the seed set from {args.seed_fasta}", flush=True)
    all_seeds = 0
    sampled: set[str] = set()
    for ident in iter_seed_ids(args.seed_fasta):
        all_seeds += 1
        if seeds.bucket_of(ident, args.seed_denominator) == 0:
            sampled.add(ident)
    print(f"  {all_seeds:,} seeds, {len(sampled):,} in the 1/{args.seed_denominator} sample")

    cells: dict[str, dict[int, set[str]]] = {}
    for path in args.seed_hits:
        slug = path.name.replace("seed-hits-", "").replace(".tsv.gz", "")
        cells[slug] = read_seed_hits(path)
        print(
            f"  cell {slug}: "
            + ", ".join(f"mode {m} {len(v):,}" for m, v in sorted(cells[slug].items()))
        )

    with repro.run(
        "A1.6",
        seed=None,
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-exposure-q{args.seed_denominator}.json",
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("decisions", ["D-158", "D-160"])
        manifest.parameter("seed_denominator", args.seed_denominator)
        manifest.parameter("seeds_total", all_seeds)
        manifest.parameter("seeds_sampled", len(sampled))
        manifest.input_file(args.seed_fasta, role="viral-seed-set")
        for path in args.seed_hits:
            manifest.input_file(path, role="seed-hits")

        report: dict[str, object] = {
            "decisions": ["D-158", "D-160"],
            "seed_denominator": args.seed_denominator,
            "seeds_total": all_seeds,
            "seeds_sampled": len(sampled),
            "tiers": {},
            "reported_denominators": (
                ["all_sampled_seeds", "seeds_with_hits"]
                if args.seed_hits
                else ["all_sampled_seeds"]
            ),
        }
        for tier, path in sorted(pairs.items()):
            print(f"joining {tier} from {path}", flush=True)
            verdicts = read_verdicts(path)
            manifest.input_file(path, role=f"exposure-rows-{tier}")
            summary = summarise(tier, verdicts, sampled, cells)
            report["tiers"][tier] = summary  # type: ignore[index]
            row = summary["all_sampled_seeds"]
            assert isinstance(row, dict)
            share = row["non_exclusive_share"]
            und = row["undetermined_share"]
            print(
                f"  {tier}: {row['counts'][exclusivity.NON_EXCLUSIVE]:,} of "
                f"{row['seeds']:,} sampled seeds have a non-viral member "
                f"({0.0 if share is None else share:.2%}); "
                f"undetermined {0.0 if und is None else und:.2%}",
                flush=True,
            )

        if not args.seed_hits:
            manifest.note(
                "No seed-hit sidecars were given, so only D-158's first denominator is "
                "reported. The second needs the band re-run of D-160; a report without it "
                "is not the full specification and says so in reported_denominators."
            )
        manifest.note(
            "The two tiers are a two-point curve and are deliberately not combined: no "
            "blended share, no interpolation, no chosen cut (D-158). Cluster co-membership "
            "is a proxy for ESM3-open's clause (b) at two fixed identities, not an execution "
            "of it, and it bounds a figure's exposure to the dropped clause rather than "
            "correcting the figure."
        )
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        manifest.output_file(out, role="exposure-report")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare the two registries at the sampling rate they share — task A3.2, D-247.

    pixi run -e dev python tools/equal_rate_pair.py

A3.2's headline reports each registry at the depth it was searched, and the two depths differ by
ten (D-247). That makes the headline figures useless for the one question a reader asks first:
does the protein registry survive less than the nucleotide one, or was it simply sampled less?

The comparison that answers it needs no new compute, because both registries were searched at the
same pre-registered rates before either was deepened. This tool assembles that pair from pins and
publishes it, so the write-up can cite a regenerated figure.

**It holds one detector on both sides, and that is the whole point.** The headline merges the
profile search with A2.4's provirus route, which sampled at 0.0025 on both releases — a third
rate again. A pairing that takes the profile search on one side and the merged headline on the
other is not an equal-rate comparison, however close the numbers look. That mistake was made and
corrected on 2026-10-21; this tool exists so it cannot be made silently again, and it publishes
the merged counts beside the single-detector ones with the difference stated rather than leaving
two counts in circulation for the same registry.

The nucleotide registry's shallow counts come from the published band parts rather than from its
current tables, because its tables now hold the deepened pass. The shallow band is the first
band of that pass and the sample is nested in its rate (D-078), so the band part *is* the shallow
measurement, and its rows carry the accessions that prove which corpus they came from (D-245).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, repro
from amazebio.survival import wilson_interval

TASK = "A3.2"

#: The shallow band of the deepened nucleotide pass, per release, and the rate it covers.
NUCLEOTIDE_PARTS: tuple[tuple[str, str, float], ...] = (
    ("opengenome", "a2-1/parts/part-opengenome-0-1.json", 0.002),
    ("opengenome2", "a2-1/parts/part-opengenome2-0-1.json", 0.001),
)

#: The protein registry's tables, which were never deepened and so are already at these rates.
PROTEIN_TABLES: tuple[tuple[str, str, float], ...] = (
    ("opengenome", "a2-1/detections-rvdb-prot-evo1-literal-opengenome.json", 0.002),
    ("opengenome2", "a2-1/detections-rvdb-prot-evo1-literal-opengenome2.json", 0.001),
)

#: The merged headline's protein rows, quoted for contrast, not for the comparison.
HEADLINE = "a3-2/headline.json"

POLICY = "evo1-literal"
PART_TABLE = f"{POLICY}|pfam"
PREFIX = "corpora/results/"


def fetch(cache: Path, key: str, *, client: Any) -> dict[str, Any]:
    dest = cache / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        client.download_file(objectstore.CORPORA_BUCKET, PREFIX + key, str(dest))
    return json.loads(dest.read_text())


def families_in_part(part: dict[str, Any], release: str) -> tuple[int, dict[str, int]]:
    """Distinct families in the part's table, with the rows counted by accession prefix.

    The prefix count is the check D-245 earned: a part belongs to one release, and its rows have
    to carry that release's own accessions. A row from the other release here would be the same
    fault in a different place.
    """
    if part.get("release") != release:
        raise SystemExit(f"part names release {part.get('release')!r}, expected {release!r}")
    rows = part["tables"][PART_TABLE]
    families = {row["family_id"] for row in rows}
    prefixes: dict[str, int] = {}
    for row in rows:
        record = row["record_id"]
        head = record.split(":")[0] if ":" in record else record.split("_")[0]
        prefixes[head] = prefixes.get(head, 0) + 1
    return len(families), prefixes


def build(*, cache: Path, client: Any, manifest: repro.RunManifest) -> dict[str, Any]:
    nucleotide: dict[str, dict[str, Any]] = {}
    for release, key, rate in NUCLEOTIDE_PARTS:
        part = fetch(cache, key, client=client)
        families, prefixes = families_in_part(part, release)
        rates = {
            source["sample_rate"]
            for source in part["sources"]
            if source.get("searched") and source.get("sample_rate") is not None
        }
        if rates != {rate}:
            raise SystemExit(f"{key}: searched sources report rates {sorted(rates)}, not {rate}")
        manifest.parameter(f"nucleotide_rows_{release}", sum(prefixes.values()))
        nucleotide[release] = {
            "families_with_a_hit": families,
            "rate": rate,
            "rows": sum(prefixes.values()),
            "rows_by_accession_prefix": prefixes,
            "from": f"s3://{objectstore.CORPORA_BUCKET}/{PREFIX}{key}",
        }

    protein: dict[str, dict[str, Any]] = {}
    for release, key, rate in PROTEIN_TABLES:
        table = fetch(cache, key, client=client)
        if table["sample"]["rate"] != rate:
            raise SystemExit(f"{key}: table reports rate {table['sample']['rate']}, not {rate}")
        protein[release] = {
            "families_with_a_hit": table["survival"]["families_with_a_hit"],
            "families_in_universe": table["survival"]["families_in_universe"],
            "rate": rate,
            "from": f"s3://{objectstore.CORPORA_BUCKET}/{PREFIX}{key}",
        }

    headline = fetch(cache, HEADLINE, client=client)
    merged = {}
    for group in headline["groups"]:
        if group.get("universe", "").startswith("rvdb-prot") and group.get("policy_id") == POLICY:
            merged[group["release"]] = {
                "families_with_a_hit": group["m1_families_with_a_hit"],
                "detectors": sorted(d["detector"] for d in group["detectors"]),
            }

    universe = {"nucleotide": 1719, "protein": protein["opengenome"]["families_in_universe"]}
    pairs = []
    for release, _key, rate in PROTEIN_TABLES:
        n, p = nucleotide[release]["families_with_a_hit"], protein[release]["families_with_a_hit"]
        pairs.append(
            {
                "release": release,
                "rate": rate,
                "nucleotide": {
                    "registry": "pfam/38.2 viral",
                    "families_with_a_hit": n,
                    "families_in_universe": universe["nucleotide"],
                    **_fraction(n, universe["nucleotide"]),
                },
                "protein": {
                    "registry": "rvdb-prot/32.0",
                    "families_with_a_hit": p,
                    "families_in_universe": universe["protein"],
                    **_fraction(p, universe["protein"]),
                },
            }
        )

    return {
        "task": TASK,
        "design_ref": "§A3",
        "decisions": ["D-078", "D-161", "D-245", "D-246", "D-247"],
        "detector": "profile-hmmer",
        "policy_id": POLICY,
        "estimate_kind": "lower_bound",
        "pairs": pairs,
        "sources": {"nucleotide": nucleotide, "protein": protein},
        "merged_headline_protein_for_contrast": merged,
        "reading_this_table": (
            "Both sides are the profile search alone, at the rate named on each row, so the "
            "difference between the two registries is not a difference in how deeply they were "
            "read. What it is not evidence of: that one registry's families are more or less "
            "likely to survive a filter than the other's. The two universes define a family "
            "differently and their denominators differ by a factor of eight (D-161), so this "
            "pair establishes only that the gap between them survives equal sampling. "
            "`merged_headline_protein_for_contrast` holds A3.2's own protein figures, which are "
            "larger because they merge the provirus route in at a rate of 0.0025 — right for the "
            "headline and wrong for this comparison, which is why both appear here."
        ),
    }


def _fraction(hits: int, universe: int) -> dict[str, Any]:
    interval = wilson_interval(hits, universe)
    low, high = interval.low, interval.high
    return {
        "fraction": round(hits / universe, 6),
        "ci_low": round(low, 6),
        "ci_high": round(high, 6),
    }


def summarise(doc: dict[str, Any]) -> str:
    lines = [
        "The two registries at the sampling rate they share — profile search only",
        "",
        "| release | rate | nucleotide (of 1,719) | protein (of 13,679) |",
        "|---|---|---|---|",
    ]
    for pair in doc["pairs"]:
        n, p = pair["nucleotide"], pair["protein"]
        lines.append(
            f"| `{pair['release']}` | {pair['rate']} | "
            f"{n['families_with_a_hit']:,} = {n['fraction']:.2%} "
            f"[{n['ci_low']:.2%}, {n['ci_high']:.2%}] | "
            f"{p['families_with_a_hit']:,} = {p['fraction']:.2%} "
            f"[{p['ci_low']:.2%}, {p['ci_high']:.2%}] |"
        )
    merged = doc["merged_headline_protein_for_contrast"]
    lines += [
        "",
        "A3.2's headline protein figures, for contrast rather than for the comparison: "
        + ", ".join(f"{rel} {v['families_with_a_hit']:,}" for rel, v in sorted(merged.items()))
        + " — larger because they merge the provirus route at a rate of 0.0025.",
        "",
        "Both sides are lower bounds, and the two universes are not comparable as universes "
        "(D-161). What equal sampling establishes is that the gap between them is not an "
        "artefact of depth.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a3-2"))
    ap.add_argument("--cache", type=Path, default=Path("artifacts/a3-2/inputs"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    args.outdir.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    client = objectstore.client()
    try:
        with repro.run(
            TASK,
            seed=None,
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-equal-rate-pair.json",
            durable=objectstore.durable_results("a3-2"),
        ) as manifest:
            manifest.parameter("policy_id", POLICY)
            manifest.parameter("detector", "profile-hmmer")
            manifest.parameter("decisions", ["D-078", "D-161", "D-245", "D-246", "D-247"])
            manifest.parameter(
                "reads",
                [PREFIX + key for _release, key, _rate in NUCLEOTIDE_PARTS + PROTEIN_TABLES]
                + [PREFIX + HEADLINE],
            )
            doc = build(cache=args.cache, client=client, manifest=manifest)
            out = args.outdir / "equal-rate-pair.json"
            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            (args.outdir / "equal-rate-pair.md").write_text(summarise(doc) + "\n")
            manifest.output_file(out, role="equal-rate comparison")
            manifest.output_file(args.outdir / "equal-rate-pair.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

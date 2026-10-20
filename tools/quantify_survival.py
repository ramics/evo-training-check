#!/usr/bin/env python3
"""Merge the A2 detection tables into the headline survival quantification — task A3.2.

Reads every A2 detection table out of the durable result store, groups them by policy reading,
release and registry universe, and emits M1 (family-level survival) and M2 (surviving sequence
count per family) overall and per survival route. `metrics/survival.md` is the specification;
`amazebio.quantify` is the implementation and the module docstring states the de-duplication
rules this tool relies on.

    pixi run -e dev python tools/quantify_survival.py --show

Nothing here samples, searches or thresholds: every input is an artefact some A2 task already
produced, so the run is deterministic apart from M2's bootstrap, which is seeded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from amazebio import objectstore
from amazebio.quantify import (
    BOOTSTRAP_RESAMPLES,
    MergeError,
    group_tables,
    load_table,
    merge_group,
    quantify,
)
from amazebio.repro import ReproError, run

#: The detection tables this merge consumes, by result-store prefix and filename stem.
#:
#: A2.5 contributes its *assembled* segmented table and not its four bands: the bands are
#: partial reads of one pass and the assembly is what A2.5 published as the result. Its
#: `sweep-*` tables are the label-side arm — a checklist over taxonomic categories with no
#: family universe at all — so they carry no M1 and are listed in the output as present and
#: not merged, rather than dropped where nobody would notice.
TABLE_SOURCES: tuple[tuple[str, str], ...] = (
    ("a2-1", "detections-"),
    ("a2-3", "detections-"),
    ("a2-4", "detections-"),
    ("a2-5", "segmented-assembled"),
)

#: Detectors that produced no table in the durable store, with why. Named in the output
#: because a headline assembled from four detectors where §A2 specifies five is a fact about
#: the result, not a detail of the run.
DETECTORS_ABSENT: tuple[dict[str, str], ...] = (
    {
        "task": "A2.2",
        "detector": "structure-foldseek",
        "why": (
            "A2.2 ships without a searched corpus: the structural route's cost was measured at "
            "a multiple of the budget and recorded as the finding instead (D-179, D-180). Its "
            "seven per-manifest tables are all estimate_kind not_searched, so the structural "
            "route contributes no detections to any group and no family survives by it here."
        ),
    },
)

#: A2 artefacts that exist, are not merged, and are named here so that is visible. An arm left
#: out of a headline without a line saying so is indistinguishable from an arm nobody ran.
TABLES_NOT_MERGED: tuple[dict[str, str], ...] = (
    {
        "tables": "a2-5/sweep-*",
        "why": (
            "A2.5's label-side arm is a checklist over taxonomic categories, with no family "
            "registry and so no denominator M1 is defined over. Its result — zero against the "
            "same records where the sequence-side arm found seven families — is the "
            "methodological finding D-193 records, and it is reported there rather than "
            "folded into a survival fraction it has no universe for."
        ),
    },
    {
        "tables": "a2-5/segmented-*-band*",
        "why": (
            "The four bands are partial reads of one pass; `segmented-assembled` is the "
            "assembly A2.5 published and is what this merge consumes. Reading both would "
            "count the same records twice."
        ),
    },
    {
        "tables": "a2-4/band1-run1-*",
        "why": "A2.4's superseded first band, kept only because the result bucket has no delete.",
    },
)

RESULT_PREFIX = "corpora/results/"


def fetch_tables(cache: Path, *, client: Any = None) -> list[tuple[str, dict[str, Any]]]:
    """Download every consumed detection table into `cache`, returning (key, document)."""
    client = client or objectstore.client()
    paginator = client.get_paginator("list_objects_v2")
    found: list[str] = []
    for prefix, stem in TABLE_SOURCES:
        for page in paginator.paginate(
            Bucket=objectstore.CORPORA_BUCKET, Prefix=RESULT_PREFIX + prefix
        ):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key.rsplit("/", 1)[-1]
                # `band1-run1-...` is A2.4's superseded first band, kept in the store because
                # the bucket has no delete. Reading it alongside the final tables would merge
                # one pass with its own rerun.
                if "/band1-run1" in key or not name.startswith(stem) or not name.endswith(".json"):
                    continue
                if name in {"detections-index.json", "index.json", "index-all.json"}:
                    continue
                found.append(key)

    out: list[tuple[str, dict[str, Any]]] = []
    for key in sorted(found):
        dest = cache / key[len(RESULT_PREFIX) :]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            client.download_file(objectstore.CORPORA_BUCKET, key, str(dest))
        out.append((f"s3://{objectstore.CORPORA_BUCKET}/{key}", json.loads(dest.read_text())))
    return out


def build(tables: list[tuple[str, dict[str, Any]]], *, seed: int, resamples: int) -> dict[str, Any]:
    """Group, merge and quantify. Raises MergeError on anything that cannot be merged honestly."""
    loaded = [load_table(doc, source=src) for src, doc in tables]
    groups = []
    for key, members in sorted(group_tables(loaded).items(), key=lambda kv: kv[0].slug):
        groups.append(quantify(merge_group(key, members), seed=seed, resamples=resamples).document)

    universes = sorted({(g["universe"], g["families_in_universe"]) for g in groups})
    return {
        "task": "A3.2",
        "specification": "metrics/survival.md",
        "seed": seed,
        "bootstrap_resamples": resamples,
        "groups": groups,
        "universes": [{"universe": u, "families": n} for u, n in universes],
        "detectors_absent": list(DETECTORS_ABSENT),
        "tables_not_merged": list(TABLES_NOT_MERGED),
        "metrics_not_computed_here": [
            {
                "metric": "M3 diversity coverage",
                "why": (
                    "M3 asks which of a family's diversity bins the surviving sequence covers, "
                    "which needs each detection placed against its family's clustered members. "
                    "The A2 detection records carry a record id, a score and a route and no "
                    "sequence or alignment, so M3 cannot be computed from these artefacts at "
                    "any depth. It is task A3.4, split out rather than approximated (D-195)."
                ),
            },
        ],
        "reading_this_file": [
            "One group is one policy reading, one release and one registry universe. Universes "
            "are never pooled: Pfam's is this project's derived viral subset, RVDB-prot's is "
            "the publisher's clustering of the whole known virosphere, and D-190's segmented "
            "selection is RVDB-prot cut to 1,285 families (D-022, D-161).",
            "Per-route figures do not sum to the overall figure. A family can survive by more "
            "than one route.",
            "Counts are summed across detectors, which is sound only because the detectors read "
            "disjoint corpus components; the merge verifies that from each table's sources[] "
            "and refuses the group otherwise.",
        ],
    }


def summarise(doc: dict[str, Any]) -> str:
    lines = [
        "# A3.2 — survival quantification by route",
        "",
        f"Specification: `{doc['specification']}` (frozen, D-022). "
        f"Seed {doc['seed']}, {doc['bootstrap_resamples']:,} bootstrap resamples.",
        "",
        "Universes are never pooled and per-route figures never summed. M1 is the fraction of "
        "the pinned family universe with at least one surviving homolog.",
        "",
        "| universe | reading | release | kind | families | M1 | 95% CI |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in doc["groups"]:
        if g["m1_fraction"] is None:
            # Withheld, not zero. See `_unsearched_document`: printing 0.0000 here would be
            # the audit's strongest claim made from nothing searched.
            lines.append(
                f"| {g['universe']} | {g['policy_id']} | {g['release']} | {g['estimate_kind']} | "
                f"—/{g['families_in_universe']} | withheld | not evidence of absence |"
            )
            continue
        lines.append(
            f"| {g['universe']} | {g['policy_id']} | {g['release']} | {g['estimate_kind']} | "
            f"{g['m1_families_with_a_hit']}/{g['families_in_universe']} | "
            f"{g['m1_fraction']:.4f} | [{g['m1_ci_low']:.4f}, {g['m1_ci_high']:.4f}] |"
        )
    lines += [
        "",
        "## By route",
        "",
        "| universe | reading | release | route | M1 | 95% CI | max n_f |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in doc["groups"]:
        for route, r in sorted(g["routes"].items()):
            lines.append(
                f"| {g['universe']} | {g['policy_id']} | {g['release']} | {route} | "
                f"{r['m1_fraction']:.4f} | [{r['m1_ci_low']:.4f}, {r['m1_ci_high']:.4f}] | "
                f"{r['m2']['maximum']} |"
            )
    lines += ["", "## Not in these numbers", ""]
    for d in doc["detectors_absent"]:
        lines.append(f"- **{d['task']} ({d['detector']})** — {d['why']}")
    for t in doc["tables_not_merged"]:
        lines.append(f"- **`{t['tables']}`** — {t['why']}")
    for m in doc["metrics_not_computed_here"]:
        lines.append(f"- **{m['metric']}** — {m['why']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default="artifacts/a3-2")
    ap.add_argument(
        "--cache", default="artifacts/a3-2/inputs", help="where the A2 tables are downloaded"
    )
    ap.add_argument("--seed", type=int, default=20261020, help="seed for M2's bootstrap")
    ap.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    try:
        with run(
            "A3.2",
            seed=args.seed,
            outdir=outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-quantify.json",
            durable=objectstore.durable_results("a3-2"),
        ) as m:
            m.parameter("bootstrap_resamples", args.resamples)
            m.parameter("table_sources", [f"{p}/{s}*" for p, s in TABLE_SOURCES])
            tables = fetch_tables(cache)
            if not tables:
                print("refused: no A2 detection tables found in the result store", file=sys.stderr)
                return 2
            for src, _ in tables:
                m.input_url(src, role="a2-detection-table")

            doc = build(tables, seed=args.seed, resamples=args.resamples)

            out = outdir / "headline.json"
            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            m.output_file(out, role="headline-quantification")

            md = outdir / "headline.md"
            md.write_text(summarise(doc))
            m.output_file(md, role="summary")

            m.note(
                f"{len(doc['groups'])} groups over {len(doc['universes'])} registry universes, "
                f"from {len(tables)} A2 detection tables. M3 is not computed here (D-195)."
            )
    except MergeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.show:
        print((outdir / "headline.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

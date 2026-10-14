#!/usr/bin/env python3
"""Emit ESM3-open's stated corpus composition, and what reconciles against it — A1.5.

This produces the machine-readable artefact the ESM3 parts of A4.3 and the Phase A
write-up read, so no number in prose is a value somebody retyped: `AGENTS.md` requires
every figure in a write-up to trace to an artefact a pipeline produced.

It needs no corpus and no network. Everything it writes is either transcribed from the
preprint with a locator, or arithmetic over those transcriptions and the publishers'
own release notes — the three parts of A1.5 that do not depend on the staging scope
question. Run it before staging, not after: the reconciliation is what decides whether
the reported 10.6M removal can validate a reconstruction at all.

    python3 tools/esm3_composition.py                 # artifacts/a1-5/composition.json
    python3 tools/esm3_composition.py --print         # and to stdout, for reading
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import esm3
from amazebio.repro import ReproError, run

OUTDIR = Path("artifacts/a1-5")


def build() -> dict[str, object]:
    components = esm3.scope_table()
    reconciliation = esm3.reconcile()
    return {
        "task": "A1.5",
        "model": "ESM3-open (esm3-sm-open-v1)",
        "source": esm3.SOURCE,
        "verdict": "proxy only",
        "components": components,
        "inverse_folded": list(esm3.INVERSE_FOLDED),
        "stated_totals": esm3.STATED_TOTALS,
        "publisher_counts": [
            {
                "component": p.component,
                "level": p.level,
                "count": p.count,
                "source": p.source,
                "note": p.note,
            }
            for p in esm3.PUBLISHER_COUNTS
        ],
        "reconciliation": reconciliation,
        "under_specification": esm3.unstated(),
        "summary": {
            "components_stated": len(components),
            "components_pinnable": sum(1 for c in components if c["retrievability"] == "pinned"),
            "components_not_reproducible": sum(
                1 for c in components if c["retrievability"] == "not-reproducible"
            ),
            "filter_scope_named": list(esm3.FILTER_SCOPE_NAMED),
            "components_scope_unaddressed": [
                c["component"] for c in components if c["in_filter_scope"] is None
            ],
            "stated_total_removed": esm3.STATED_TOTAL_REMOVED,
            "reconciliation_rows_exceeding_stated_removal": sum(
                1 for r in reconciliation if r["exceeds_stated_removal"] is True
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument("--print", action="store_true", help="also write the table to stdout")
    ap.add_argument(
        "--allow-dirty", action="store_true", help="iteration only, never for a cited run"
    )
    args = ap.parse_args(argv)

    try:
        return _execute(args)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(args: argparse.Namespace) -> int:
    out = args.outdir / "composition.json"
    with run(
        "A1.5",
        seed=None,
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-composition.json",
    ) as manifest:
        # Declared before anything is written, per the repro contract. These are the
        # published quantities the arithmetic rests on; naming them here means a later
        # run that used different ones is visibly a different run.
        manifest.parameter("source", esm3.SOURCE)
        manifest.parameter("stated_total_removed", esm3.STATED_TOTAL_REMOVED)
        manifest.parameter("stated_count_precision", esm3.STATED_COUNT_PRECISION)
        manifest.parameter("stated_counts_are_post_filter", esm3.STATED_COUNTS_ARE_POST_FILTER)
        manifest.parameter("filter_scope_named", list(esm3.FILTER_SCOPE_NAMED))

        # The captures the publisher counts are transcribed from. Checksummed here, so
        # the artefact records which bytes the counts came from rather than asserting
        # them; tools/policies.py separately checks these against sources.json.
        for capture in sorted({p.source for p in esm3.PUBLISHER_COUNTS}):
            manifest.input_file(capture, role="publisher release note")
        manifest.input_file("pdfs/2024.07.01.600583v2.full.pdf", role="S-ESM3-PREPRINT")

        report = build()
        out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n")
        manifest.output_file(out, role="composition table")

        for row in report["reconciliation"]:  # type: ignore[union-attr]
            if row["exceeds_stated_removal"] is True:
                manifest.note(
                    f"{row['component']}: stated {row['stated_level']} count is "
                    f"{row['gap']:,} short of the publisher's {row['publisher_level']} "
                    f"count, against a stated total removal of "
                    f"{esm3.STATED_TOTAL_REMOVED:,} across every component"
                )

    if args.print:
        _render(report)
    print(f"wrote {out}")
    return 0


def _render(report: dict[str, object]) -> None:
    print()
    print(
        f"{'component':<16}{'track':<11}{'release':<22}{'scope':<8}"
        f"{'tokens(B)':>10}  retrievability"
    )
    for c in report["components"]:  # type: ignore[union-attr]
        scope = {True: "named", False: "no", None: "unaddr"}[c["in_filter_scope"]]
        release = c["stated_release"]
        if len(release) > 20:
            release = release[:19] + "…"
        tokens = "-" if c["tokens_b"] is None else f"{c['tokens_b']:.3f}".rstrip("0").rstrip(".")
        print(
            f"{c['component']:<16}{c['track']:<11}{release:<22}{scope:<8}"
            f"{tokens:>10}  {c['retrievability']}"
        )
    print()
    for r in report["reconciliation"]:  # type: ignore[union-attr]
        if not r["comparable"]:
            print(
                f"{r['component']:<10} stated {r['stated_level']:>4} {r['stated_count']:>13,}"
                f"  vs {r['publisher_level']:<14} {r['publisher_count']:>13,}"
                f"  {'(different granularity, no gap)':>36}"
            )
            continue
        flag = "  <-- exceeds stated removal" if r["exceeds_stated_removal"] else ""
        print(
            f"{r['component']:<10} stated {r['stated_level']:>4} {r['stated_count']:>13,}"
            f"  vs {r['publisher_level']:<14} {r['publisher_count']:>13,}"
            f"  gap {r['gap']:>13,} ({r['gap_fraction']:+.1%}){flag}"
        )
    print()
    for f in report["under_specification"]:  # type: ignore[union-attr]
        print(f"- [{f['id']}] {f['finding']}")


if __name__ == "__main__":
    sys.exit(main())

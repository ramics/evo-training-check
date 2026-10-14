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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import esm3
from amazebio.repro import ReproError, run

OUTDIR = Path("artifacts/a1-5")


def _manifests(staging_dir: Path) -> list[dict[str, Any]]:
    """Every run manifest in a staging directory, newest last."""
    found = []
    for name in sorted(staging_dir.glob("run*.json")):
        try:
            found.append(json.loads(name.read_text()) | {"_path": str(name)})
        except (OSError, json.JSONDecodeError):
            continue
    return found


def load_staged(staging_dir: Path) -> dict[str, dict[str, Any]]:
    """Read what the staging passes actually produced, from their own manifests.

    Deliberately reads the manifests rather than the bucket. A manifest records the
    checksum each object was verified against and the commit that produced it; a
    listing would show only that something is there, which is not the claim.

    A component appears only if a manifest shows at least one verified object for it.
    A run that was stopped early, or whose checksum did not match, leaves the component
    unstaged here — which is the honest reading, and is why `--staging-dir` cannot turn
    a smoke test into a staged corpus.
    """
    staged: dict[str, dict[str, Any]] = {}
    for manifest in _manifests(staging_dir):
        if manifest.get("task") != "A1.5":
            continue
        params = manifest.get("parameters", {})
        release = params.get("release")
        md5_verified = any(
            entry.get("checksum_type") == "md5" and entry.get("verified")
            for entry in manifest.get("inputs", [])
        )
        objects = [
            {
                "uri": out.get("uri"),
                "bytes": out.get("bytes"),
                "sha256": out.get("sha256"),
                "role": out.get("role"),
                "member": out.get("member"),
            }
            for out in manifest.get("outputs", [])
            if str(out.get("role", "")).startswith(("corpus:", "staged corpus"))
            and out.get("uri")
            and not out.get("partial")
        ]
        if not objects or not md5_verified:
            continue

        if any(str(o["role"]).startswith("corpus:") for o in objects):
            tiers = sorted({str(o["role"]).split(":", 1)[1] for o in objects})
            staged["UniRef"] = {
                "release": release,
                "granularity": ", ".join(tiers)
                + " — all three, because the stated release does not name a tier",
                "objects": objects,
                "manifest": manifest["_path"],
            }
        else:
            staged["MGnify"] = {
                "release": release,
                "granularity": "the 90%-clustered product, which is what MGnify90 names; "
                "the full protein set behind it is not staged (D-033)",
                "objects": objects,
                "manifest": manifest["_path"],
            }
    return staged


def load_counts(counts_dir: Path) -> list[dict[str, Any]]:
    """Per-tier cluster counts from the in-region counting runs, if they are here.

    The archive md5 shows the released bytes arrived; it cannot show the tar walk split
    them into the right tiers, because a mis-walked archive still hashes correctly. So
    each staged tier is counted against the cluster total its own release note states,
    and that is the check this reads. Rows are per tier, carrying whether the count
    agreed, because a verification nobody can see is not one.
    """
    rows: list[dict[str, Any]] = []
    for path in sorted(counts_dir.glob("composition-*.json")):
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        # `tiers_counted` was added after A1.3's runs and after A1.5's own counting pass,
        # so fall back to the rows that carry a verdict. Older reports stay readable.
        composition_rows = report.get("composition", [])
        counted = report.get("tiers_counted")
        if counted is None:
            counted = [r["tier"] for r in composition_rows if r.get("agrees") is not None]
        for tier in counted:
            row = next((r for r in composition_rows if r.get("tier") == tier), None)
            if row is None:
                continue
            rows.append(
                {
                    "tier": tier,
                    "counted_clusters": row.get("counted_clusters"),
                    "stated_clusters": row.get("stated_clusters"),
                    "agrees": row.get("agrees"),
                    "delta": row.get("delta"),
                    "source": str(path),
                }
            )
    return sorted(rows, key=lambda r: r["tier"])


def build(
    staged: dict[str, dict[str, Any]] | None = None,
    counts: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
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
        "stated_vs_used": esm3.stated_vs_used(staged),
        "staged_tier_counts": counts or [],
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
            "components_staged": sorted(staged or {}),
            "staged_tiers_counted_and_agreeing": sorted(
                c["tier"] for c in (counts or []) if c["agrees"]
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
        "--staging-dir",
        type=Path,
        default=None,
        help="read the staging manifests here and record stated-versus-used per "
        "component (default: --outdir)",
    )
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

        staging_dir = args.staging_dir or args.outdir
        staged = load_staged(staging_dir) if staging_dir.exists() else {}
        for name, used in sorted(staged.items()):
            manifest.input_file(used["manifest"], role=f"staging manifest: {name}")
        counts = load_counts(staging_dir / "counts")
        for row in counts:
            manifest.input_file(row["source"], role=f"cluster count: {row['tier']}")
        report = build(staged, counts)
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

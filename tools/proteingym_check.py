#!/usr/bin/env python3
"""Reproduce the benchmark's published per-assay numbers — task B2.1's ingest check.

    python3 tools/proteingym_check.py                    # every assay, default model
    python3 tools/proteingym_check.py --model "ESM2 (3B)"
    python3 tools/proteingym_check.py --print            # write no artefact

§B2 asks for one published leaderboard number reproduced end to end as a sanity check. This
does every assay in the release instead, because the extra cost is seconds and the stronger
claim is worth having: if our Spearman matches the maintainers' published value on all 217
assays, then the ingest — the variant list, the join, the metric, the tie handling — agrees
with theirs, and `amazebio.proteingym.spearman` is demonstrably the same metric rather than
merely a function with the same name.

What this does **not** reproduce is the leaderboard's headline average. The maintainers state
their aggregation corrects for biases (assays per protein family, functional groupings), so
that number is a weighted quantity whose weighting is theirs, and the arithmetic mean of the
per-assay values is not it. Reproducing a per-assay number is the real check; a pooled figure
this project publishes has to be its own, reported per-assay first per `AGENTS.md`.

The published values are rounded to three decimals, so agreement is judged at that precision
and the largest raw deviation is reported alongside, rather than asserting an exact match the
published file cannot support.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio.proteingym import (
    RELEASE,
    ProteinGymError,
    load_assay,
    load_model_scores,
    load_reference,
    paired,
    spearman,
)
from amazebio.repro import run

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "proteingym" / RELEASE.version
OUTDIR = REPO / "artifacts" / "b2-1" / "leaderboard-check"

# The leaderboard CSV and the score archive name the same model differently, so the mapping is
# explicit rather than guessed by string munging — a near-miss would silently score the wrong
# model and still produce plausible correlations. Only the Phase B checkpoints and the
# non-neural baseline are listed; extend deliberately.
MODEL_COLUMNS = {
    "ESM2 (650M)": "ESM2_650M",
    "ESM2 (3B)": "ESM2_3B",
    "ESM3 open (1.4B)": "ESM3",
    "ESM-C (600M)": "ESMC-600M",
    "ESM-C (300M)": "ESMC-300M",
    # The leaderboard writes a hyphen, the score archive an underscore. Verified against
    # the staged archive by tests/test_proteingym.py rather than assumed.
    "Site-Independent": "Site_Independent",
}

# Three decimals is the precision the published file carries, so the largest deviation that
# rounding alone can produce is exactly 0.0005. Comparing at exactly that bound would call a
# value differing by 0.00050000001 a disagreement, which is a float artefact rather than a
# finding — hence the epsilon.
TOLERANCE = 0.0005
EPSILON = 1e-9


def check_model(published_name: str) -> dict:
    score_column = MODEL_COLUMNS[published_name]
    assays = load_reference(DATA / RELEASE.reference_file)
    subs = DATA / "DMS_ProteinGym_substitutions.zip"
    scores = DATA / "zero_shot_substitutions_scores.zip"

    published: dict[str, str] = {}
    with (DATA / "DMS_substitutions_Spearman_DMS_level.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            published[row["DMS ID"]] = row[published_name]

    rows = []
    for assay in assays:
        measured = load_assay(subs, assay)
        predicted = load_model_scores(scores, assay, score_column)
        x, y, unscored = paired(measured, predicted)
        try:
            rho = spearman(x, y)
        except ProteinGymError as exc:
            rows.append({"dms_id": assay.dms_id, "error": str(exc)})
            continue
        want = published.get(assay.dms_id, "")
        entry = {
            "dms_id": assay.dms_id,
            "taxon": assay.taxon.value,
            "n_variants": len(x),
            "n_measured": len(measured),
            "n_unscored": unscored,
            "recomputed": round(rho, 6),
            "published": float(want) if want not in ("", "NA") else None,
        }
        if entry["published"] is not None:
            entry["deviation"] = round(abs(rho - entry["published"]), 6)
            entry["agrees"] = entry["deviation"] <= TOLERANCE + EPSILON
        rows.append(entry)

    errored = [r for r in rows if "error" in r]
    missing_published = [r for r in rows if "error" not in r and r.get("published") is None]
    compared = [r for r in rows if r.get("published") is not None]
    agree = [r for r in compared if r["agrees"]]
    worst = max(compared, key=lambda r: r["deviation"], default=None)
    return {
        "model_published_name": published_name,
        "model_score_column": score_column,
        "assays": len(rows),
        "compared": len(compared),
        "errored": errored,
        "no_published_value": [r["dms_id"] for r in missing_published],
        "agree_at_3dp": len(agree),
        "disagree": [r for r in compared if not r["agrees"]],
        "max_deviation": worst["deviation"] if worst else None,
        "worst_assay": worst["dms_id"] if worst else None,
        "mean_deviation": (
            round(sum(r["deviation"] for r in compared) / len(compared), 6) if compared else None
        ),
        "total_variants_scored": sum(r.get("n_variants", 0) for r in rows),
        "assays_with_unscored_variants": sum(1 for r in rows if r.get("n_unscored")),
        "per_assay": rows,
    }


def exit_code(result: dict) -> int:
    """Non-zero if anything is unaccounted for, on either path.

    A disagreement, an assay whose metric raised, and an assay with no published value to
    compare against are all reasons the ingest is not validated. Returning 0 for the last two
    would let a silent drop read as a clean run.
    """
    unaccounted = result["disagree"] or result["errored"] or result["no_published_value"]
    return 1 if unaccounted else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ESM2 (650M)", choices=sorted(MODEL_COLUMNS))
    ap.add_argument("--print", dest="print_only", action="store_true", help="write no artefact")
    ap.add_argument(
        "--allow-dirty", action="store_true", help="local iteration only; never for a citation"
    )
    args = ap.parse_args()

    def report(result: dict) -> None:
        print(f"model:     {result['model_published_name']} -> {result['model_score_column']}")
        print(f"assays:    {result['assays']} ({result['compared']} with a published value)")
        print(f"agree:     {result['agree_at_3dp']}/{result['compared']} at 3 decimals")
        print(
            f"deviation: max {result['max_deviation']} ({result['worst_assay']}), "
            f"mean {result['mean_deviation']}"
        )
        print(f"variants:  {result['total_variants_scored']:,} scored")
        if result["errored"]:
            print(f"\nerrored ({len(result['errored'])}): the metric could not be computed")
            for r in result["errored"][:10]:
                print(f"  {r['dms_id']:44} {r['error']}")
        if result["no_published_value"]:
            print(
                f"\nno published value ({len(result['no_published_value'])}): "
                f"{', '.join(result['no_published_value'][:6])}"
            )
        if result["disagree"]:
            print(f"\ndisagreements ({len(result['disagree'])}):")
            for r in result["disagree"][:10]:
                print(
                    f"  {r['dms_id']:44} ours {r['recomputed']:+.4f} "
                    f"theirs {r['published']:+.4f}  d={r['deviation']:.4f}"
                )

    if args.print_only:
        result = check_model(args.model)
        report(result)
        return exit_code(result)

    with run("B2.1", outdir=OUTDIR, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("version", RELEASE.version)
        m.parameter("model", args.model)
        m.parameter("tolerance", TOLERANCE)
        m.parameter("metric", "spearman, ties averaged")
        m.input_file(DATA / RELEASE.reference_file, role="assay reference")
        m.input_file(DATA / "DMS_substitutions_Spearman_DMS_level.csv", role="published per-assay")
        m.input_file(DATA / "DMS_ProteinGym_substitutions.zip", role="measured DMS scores")
        m.input_file(DATA / "zero_shot_substitutions_scores.zip", role="published model scores")
        m.note(
            "Reproduces the published per-assay Spearman for every assay, not the one §B2 "
            "asks for. The leaderboard's headline average is deliberately not reproduced: the "
            "maintainers state their aggregation corrects for biases, so it is not the mean of "
            "these values."
        )
        result = check_model(args.model)
        path = OUTDIR / f"check-{result['model_score_column']}.json"
        path.write_text(json.dumps(result, indent=1) + "\n")
        m.output_file(path, role="per-assay reproduction of published values")

    report(result)
    print(f"wrote {path.relative_to(REPO)}")
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect B1.2's per-checkpoint score artefacts into one reference-check table.

The harness writes one artefact per checkpoint per assay. What B1.2's Done-when asks for is a
statement across them — every in-scope model scored through one interface, determinism
verified, and the published reference reproduced *where one exists*. That last clause is the
reason this tool exists rather than a hand-written table: "where one exists" is a fact about
each checkpoint that has to be read from the artefacts, and a table typed from them would be
the pasted values `AGENTS.md` forbids.

It reads what is on disk and says what is missing. A checkpoint named in the roster with no
artefact is reported as not run, with the reason the roster gives, rather than omitted — a
model quietly absent from a comparison is the failure this table is for. The same goes for a
run with no reference block: ESM3-open's first pass had none, which read as "ProteinGym does
not publish this model" when in fact it does and the run was invoked without `--published`.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B1.2"
SEED = 20261020
CANONICAL_OUT = REPO / "artifacts" / "b1-2"

#: Every checkpoint B1.2 is answerable for, and what to say about one with no artefact. The
#: roster is here rather than derived from the files present, because deriving it would make a
#: model that was never run indistinguishable from one that is not in scope.
ROSTER: dict[str, dict[str, str]] = {
    "esm2_t33_650M_UR50D": {"level": "protein", "role": "positive control"},
    "esm2_t36_3B_UR50D": {"level": "protein", "role": "positive control"},
    "ESMC-600M": {"level": "protein", "role": "second positive control"},
    "esm3-sm-open-v1": {"level": "protein", "role": "test condition"},
    "evo2_7b": {
        "level": "nucleotide",
        "role": "test condition",
        "not_run": (
            "the nucleotide arm needs a published coding sequence for the assay's target and "
            "ProteinGym publishes protein sequences. Reported as not run rather than scored "
            "against a back-translation, which would be a sequence nobody published"
        ),
    },
}


def durable_for(out: Path) -> str | None:
    """The durable prefix, **or None for a run that is not the deliverable** (D-224)."""
    if out.resolve() == CANONICAL_OUT.resolve():
        return objectstore.durable_results("b1-2")
    print(f"not publishing: --out {out} is not {CANONICAL_OUT}", file=sys.stderr)
    return None


def load(outdir: Path) -> dict[str, list[dict[str, Any]]]:
    """Every score artefact in `outdir`, grouped by checkpoint."""
    by_checkpoint: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(outdir.glob("scores-*.json")):
        doc = json.loads(path.read_text())
        by_checkpoint.setdefault(doc["checkpoint"], []).append(doc)
    return by_checkpoint


def summarise_one(doc: dict[str, Any]) -> dict[str, Any]:
    """One checkpoint-assay pair, reduced to what the Done-when asks about."""
    ref = doc.get("reference_check") or {}
    compared = bool(ref.get("compared"))
    out: dict[str, Any] = {
        "assay": doc["assay"],
        "variants_scored": doc["variants_scored"],
        "bitwise_identical_on_rescore": doc["determinism"]["bitwise_identical"],
        "variants_rescored": doc["determinism"]["variants_rescored"],
        "reference_compared": compared,
    }
    if compared:
        ours = ref["ours_vs_published"]
        diff = ref["difference_vs_truth"]
        # The verdict is `reference.ReferenceCheck`'s, read rather than recomputed. A boolean
        # derived here would be a second, coarser standard beside the authoritative one — and
        # a coarser one, because it would collapse `undetermined` (the interval straddles the
        # floor, so neither answer is established) into the same bucket as `diverges`.
        out |= {
            "published_column": doc.get("published_column"),
            "spearman_ours_vs_published": ours["estimate"],
            "spearman_ours_vs_published_interval": [ours["low"], ours["high"]],
            "agreement_floor": ref["agreement_floor"],
            "difference_vs_truth": diff["estimate"],
            "difference_vs_truth_interval": [diff["low"], diff["high"]],
            "difference_straddles_zero": diff["low"] <= 0 <= diff["high"],
            "verdict": ref.get("verdict"),
        }
    else:
        out["no_reference_because"] = ref.get("why_not", "not stated by the run")
    return out


def summarise(by_checkpoint: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for name, meta in ROSTER.items():
        docs = by_checkpoint.get(name, [])
        if not docs:
            rows.append(
                {
                    "checkpoint": name,
                    **meta,
                    "run": False,
                    "not_run": meta.get("not_run", "no artefact on disk and no reason recorded"),
                }
            )
            continue
        rows.append(
            {
                "checkpoint": name,
                "level": meta["level"],
                "role": meta["role"],
                "run": True,
                "runs": [summarise_one(d) for d in sorted(docs, key=lambda d: d["assay"])],
            }
        )

    scored = [r for r in rows if r["run"]]
    compared = [x for r in scored for x in r["runs"] if x["reference_compared"]]
    assays = sorted({x["assay"] for r in scored for x in r["runs"]})
    return {
        "task": TASK,
        "design_ref": "§B1",
        "checkpoints": rows,
        "done_when": {
            "common_test_set": {
                "assays_every_scored_checkpoint_covers": [
                    a
                    for a in assays
                    if all(any(x["assay"] == a for x in r["runs"]) for r in scored)
                ],
                "checkpoints_scored": len(scored),
                "checkpoints_in_roster": len(ROSTER),
                "not_run": [r["checkpoint"] for r in rows if not r["run"]],
            },
            "determinism": {
                "runs_checked": sum(len(r["runs"]) for r in scored),
                # None, not True, when nothing was checked. `all([])` is True and a Done-when
                # field reading True because there was nothing to test is how a gap gets
                # signed off.
                "all_bitwise_identical": (
                    all(x["bitwise_identical_on_rescore"] for r in scored for x in r["runs"])
                    if any(r["runs"] for r in scored)
                    else None
                ),
            },
            "reference_reproduced_where_one_exists": {
                "runs_with_a_published_reference": len(compared),
                "verdicts": dict(
                    sorted(collections.Counter(x["verdict"] for x in compared).items())
                ),
                "all_reproduced": (
                    all(x["verdict"] == "reproduced" for x in compared) if compared else None
                ),
                "lowest_agreement": min(
                    (x["spearman_ours_vs_published"] for x in compared), default=None
                ),
                "runs_without_one": [
                    {"checkpoint": r["checkpoint"], "why": x["no_reference_because"]}
                    for r in scored
                    for x in r["runs"]
                    if not x["reference_compared"]
                ],
            },
        },
    }


def markdown(report: dict[str, Any]) -> str:
    dw = report["done_when"]
    refs = dw["reference_reproduced_where_one_exists"]
    lines = [
        "# B1.2 — the scoring harness, checked against published references",
        "",
        "Generated by `tools/scoring_summary.py`. Do not hand-edit.",
        "",
        "## Reference check",
        "",
        "| checkpoint | role | assay | n | deterministic | vs published | 95% interval | verdict |",
        "|---|---|---|---:|---|---:|---|---|",
    ]
    for row in report["checkpoints"]:
        if not row["run"]:
            lines.append(f"| `{row['checkpoint']}` | {row['role']} | — | — | — | not run | — | — |")
            continue
        for r in row["runs"]:
            det = "yes" if r["bitwise_identical_on_rescore"] else "**no**"
            if r["reference_compared"]:
                lo, hi = r["spearman_ours_vs_published_interval"]
                vs = f"{r['spearman_ours_vs_published']:.4f}"
                iv = f"{lo:.4f} to {hi:.4f}"
                floor = r["verdict"]
            else:
                vs, iv, floor = "no reference", "—", "—"
            lines.append(
                f"| `{row['checkpoint']}` | {row['role']} | `{r['assay']}` | "
                f"{r['variants_scored']} | {det} | {vs} | {iv} | {floor} |"
            )

    lines += ["", "## Where there is no published reference", ""]
    for item in dw["reference_reproduced_where_one_exists"]["runs_without_one"]:
        lines.append(f"- `{item['checkpoint']}`: {item['why']}")
    for row in report["checkpoints"]:
        if not row["run"]:
            lines.append(f"- `{row['checkpoint']}`: {row['not_run']}")
    lines += [
        "",
        "## Against the Done-when",
        "",
        f"- Common test set: {dw['common_test_set']['checkpoints_scored']} of "
        f"{dw['common_test_set']['checkpoints_in_roster']} roster checkpoints scored, over "
        f"{len(dw['common_test_set']['assays_every_scored_checkpoint_covers'])} assay(s) every "
        "one of them covers.",
        f"- Determinism: {dw['determinism']['runs_checked']} run(s) rescored, all bitwise "
        f"identical: {dw['determinism']['all_bitwise_identical']}.",
        f"- References: {refs['runs_with_a_published_reference']} run(s) had one; "
        f"verdicts {refs['verdicts']}, all reproduced: {refs['all_reproduced']}.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=CANONICAL_OUT, type=Path)
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    out: Path = args.out
    by_checkpoint = load(out)
    report = summarise(by_checkpoint)
    destination = durable_for(out)
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-reference-check.json",
        durable=destination,
        durable_exempt=None if destination else "rehearsal: --out is not the canonical directory",
    ) as m:
        for path in sorted(out.glob("scores-*.json")):
            m.input_file(path, role="scores")
        m.parameter("roster", sorted(ROSTER))
        path = out / "reference-check.json"
        path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(path, role="reference-check")
        md = out / "reference-check.md"
        md.write_text(markdown(report) + "\n")
        m.output_file(md, role="reference-check-markdown")

    print(json.dumps(report["done_when"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

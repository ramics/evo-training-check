"""Compute B3.4's alignment-depth covariate for every assay target.

`DESIGN.md` §B3 names one confounder and gives it one line: "compute Neff per target and
include as covariate. Without it, 'viral proteins are hard' and 'viral proteins were excluded'
are not separable." That sentence decides whether Phase B can make its central distinction, so
the statistic behind it is pinned in D-231 before any depth was computed and `amazebio.neff`
implements exactly that definition.

What this does: read the assay register, resolve each assay's target to the alignment its
maintainers distribute for it, compute Neff on that alignment under the threshold those same
maintainers reweighted at, and set the result beside their own published figure. The published
figure is the check, not the source — it is computed on their filtered alignment rather than on
the one they distribute, so a gap is expected and is reported rather than reconciled away.

Both readings of the identity boundary are computed, per D-231. The inclusive one is the
headline; where the strict one differs, the difference is in the artefact.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import neff, objectstore
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B3.4"
SEED = 20261020
CANONICAL_OUT = REPO / "artifacts" / "b3-4"

#: B2.4's register, the pinned list of assays Phase B analyses. Read as a file rather than
#: re-derived, so a target that is in the analysis is a target that has a depth.
REGISTER = REPO / "assays" / "register.json"

#: The staged alignments and the map from assay to alignment, written by `stage_assay_msas.py`.
STAGED = REPO / "data" / "proteingym" / "v1.3"
INPUTS = STAGED / "baseline-inputs.json"

#: The maintainers' own reference table. Three columns are read from it and all three are
#: inputs rather than results: the alignment each assay belongs to, the threshold that
#: alignment was reweighted at, and the depth they published for it.
REFERENCE = STAGED / "DMS_substitutions.csv"

#: The column carrying the reweighting threshold, as a distance: neighbours are pairs above
#: 1 - theta identity. The filenames carry the same number the other way round
#: (`theta0.99` for `MSA_theta` 0.01), which is the detail that makes a careless reading
#: compute a completely different statistic.
THETA_COLUMN = "MSA_theta"
PUBLISHED_NEFF = "MSA_N_eff"
PUBLISHED_NEFF_L = "MSA_Neff_L"


def canonical_out() -> Path:
    return CANONICAL_OUT


def durable_for(out: Path) -> str | None:
    """The durable prefix, **or None for a run that is not the deliverable** (D-224)."""
    if out.resolve() == canonical_out().resolve():
        return objectstore.durable_results("b3-4")
    print(
        f"not publishing: --out {out} is not {canonical_out()}, so this run is a rehearsal",
        file=sys.stderr,
    )
    return None


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------


def read_alignment(path: Path) -> list[str]:
    """The match columns of every row of a gzipped a2m alignment."""
    rows: list[str] = []
    current: list[str] = []
    with gzip.open(path, "rt") as handle:
        for line in handle:
            if line.startswith(">"):
                if current:
                    rows.append(neff.match_columns("".join(current)))
                    current = []
            else:
                current.append(line.strip())
    if current:
        rows.append(neff.match_columns("".join(current)))
    if not rows:
        raise neff.DepthError(f"{path.name} holds no sequences")
    return rows


def staged_paths(inputs: dict[str, Any]) -> dict[str, Path]:
    """Where each alignment is on disk, with its staged digest confirmed.

    The digest is checked here rather than trusted because the covariate is mandatory for
    every assay in B5: a silently replaced alignment would move a target's depth without
    moving anything a reader could see.
    """
    out: dict[str, Path] = {}
    for record in inputs["alignments"]:
        path = REPO / record["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise neff.DepthError(
                f"{path.name} hashes to {digest[:12]} but was staged as "
                f"{record['sha256'][:12]}; it is not the pinned alignment"
            )
        out[record["name"]] = path
    return out


def reference_rows(path: Path, wanted: set[str]) -> dict[str, dict[str, str]]:
    with path.open(newline="") as handle:
        rows = {r["DMS_id"]: r for r in csv.DictReader(handle) if r["DMS_id"] in wanted}
    missing = sorted(wanted - set(rows))
    if missing:
        raise neff.DepthError(f"the reference table has no row for {', '.join(missing)}")
    return rows


def thresholds(rows: dict[str, dict[str, str]], alignment_for: dict[str, str]) -> dict[str, float]:
    """One reweighting threshold per alignment, refusing a disagreement rather than averaging.

    Several assays can share a target and therefore an alignment. They should carry the same
    threshold; if they ever did not, one of the two numbers would be wrong and picking either
    silently would bury it.
    """
    out: dict[str, float] = {}
    for dms_id, alignment in alignment_for.items():
        row = rows.get(dms_id)
        if row is None:
            continue
        value = 1.0 - float(row[THETA_COLUMN])
        if alignment in out and abs(out[alignment] - value) > 1e-12:
            raise neff.DepthError(
                f"{alignment} is reweighted at {out[alignment]} for one assay and {value} for "
                f"{dms_id}; one alignment cannot have two thresholds"
            )
        out[alignment] = value
    return out


# --------------------------------------------------------------------------------------
# The covariate
# --------------------------------------------------------------------------------------


def published(row: dict[str, str]) -> dict[str, float | None]:
    def number(key: str) -> float | None:
        raw = (row.get(key) or "").strip()
        try:
            return float(raw)
        except ValueError:
            return None

    return {"neff": number(PUBLISHED_NEFF), "neff_per_residue": number(PUBLISHED_NEFF_L)}


def agreement(ours: float, theirs: float | None) -> dict[str, Any]:
    """How our depth sits against the maintainers' own, as a ratio with no verdict attached.

    A verdict would need a tolerance, and there is no principled one: their figure is computed
    on a filtered alignment and ours on the distributed one, so the two measure slightly
    different populations by construction. The ratio is the honest statement.
    """
    if theirs is None or theirs <= 0:
        return {"published": None, "ratio": None, "note": "no published depth for this target"}
    return {"published": theirs, "ratio": round(ours / theirs, 4), "note": None}


def depth_table(
    register: dict[str, Any],
    alignment_for: dict[str, str],
    reference: dict[str, dict[str, str]],
    path_for: dict[str, Path],
    *,
    seed: int,
    only: str | None = None,
) -> dict[str, Any]:
    per_alignment = thresholds(reference, alignment_for)
    assays = [a["dms_id"] for a in register["assays"]]
    needed = sorted({alignment_for[a] for a in assays if a in alignment_for})
    if only:
        needed = [n for n in needed if only in n]

    alignments: dict[str, Any] = {}
    for name in needed:
        path = path_for[name]
        rows = read_alignment(path)
        threshold = per_alignment[name]
        readings = {
            reading: neff.depth(rows, threshold, inclusive=reading == "inclusive", seed=seed)
            for reading in ("inclusive", "strict")
        }
        head = readings["inclusive"]
        alignments[name] = {
            "threshold": threshold,
            "readings": {k: v.as_dict() for k, v in readings.items()},
            "neff": head.neff,
            "neff_per_column": head.neff_per_column,
            "readings_agree": readings["inclusive"].floor == readings["strict"].floor,
        }
        print(
            f"{name[:46]:48s} N={head.sequences:>7d} L={head.columns:>4d} "
            f"{head.method:10s} Neff={head.neff:,.0f}",
            flush=True,
        )

    targets = []
    for dms_id in assays:
        name = alignment_for.get(dms_id)
        if name is None or name not in alignments:
            targets.append(
                {
                    "dms_id": dms_id,
                    "alignment": name,
                    "depth": None,
                    "why": "no alignment is distributed for this target"
                    if name is None
                    else "this run covered only part of the alignment set",
                }
            )
            continue
        block = alignments[name]
        targets.append(
            {
                "dms_id": dms_id,
                "alignment": name,
                "depth": block["neff"],
                "depth_per_column": block["neff_per_column"],
                "method": block["readings"]["inclusive"]["method"],
                "interval": block["readings"]["inclusive"]["interval"],
                "strict_reading": block["readings"]["strict"]["neff"],
                "against_published": agreement(block["neff"], published(reference[dms_id])["neff"]),
            }
        )
    return {"alignments": alignments, "targets": targets}


def sanity(table: dict[str, Any]) -> dict[str, Any]:
    """Does the statistic behave sensibly across the target range, as the task's Steps ask.

    Three things are checked and all three are reported rather than asserted: that every
    target has a depth, that depth never exceeds the alignment's own sequence count, and that
    deeper alignments do come out deeper — a statistic that did not track sequence count at all
    would be measuring something other than depth.
    """
    with_depth = [t for t in table["targets"] if t["depth"] is not None]
    blocks = list(table["alignments"].values())
    overruns = [
        name
        for name, b in table["alignments"].items()
        if b["neff"] > b["readings"]["inclusive"]["sequences"] + 1e-6
    ]
    sizes = [b["readings"]["inclusive"]["sequences"] for b in blocks]
    neffs = [b["neff"] for b in blocks]
    correlation = (
        statistics.correlation(
            [float(s) for s in sizes], [float(n) for n in neffs], method="ranked"
        )
        if len(blocks) > 2
        else None
    )
    return {
        "targets": len(table["targets"]),
        "targets_with_depth": len(with_depth),
        "targets_without_depth": [t["dms_id"] for t in table["targets"] if t["depth"] is None],
        "alignments": len(blocks),
        "depth_exceeding_sequence_count": overruns,
        "rank_correlation_with_sequence_count": None
        if correlation is None
        else round(correlation, 4),
        "readings_that_differ": [
            name for name, b in table["alignments"].items() if not b["readings_agree"]
        ],
        "methods": {
            method: sum(1 for b in blocks if b["readings"]["inclusive"]["method"] == method)
            for method in ("duplicates", "exact", "sampled")
        },
    }


def check(report: dict[str, Any]) -> list[str]:
    """What would make this covariate unusable for B5. Empty means usable."""
    problems = []
    s = report["sanity"]
    if s["targets"] == 0:
        problems.append("no targets")
    if s["targets_without_depth"]:
        problems.append(
            "no depth for " + ", ".join(s["targets_without_depth"]) + "; §B3 makes the "
            "covariate mandatory, so an assay without one cannot enter the model"
        )
    if s["depth_exceeding_sequence_count"]:
        problems.append(
            "depth above the sequence count for "
            + ", ".join(s["depth_exceeding_sequence_count"])
            + "; the weights do not sum to what they must"
        )
    for name, block in report["table"]["alignments"].items():
        head = block["readings"]["inclusive"]
        if head["method"] == "sampled" and head["interval"] is None:
            problems.append(f"{name} was estimated and carries no interval")
    return problems


def markdown(report: dict[str, Any]) -> str:
    s = report["sanity"]
    lines = [
        "# B3.4 — alignment depth, the mandatory covariate",
        "",
        f"Depth for {s['targets_with_depth']} of {s['targets']} assay targets, over "
        f"{s['alignments']} distinct alignments. The statistic is Neff as D-231 pins it: the "
        "sum of sequence weights, at the threshold each alignment's own maintainers "
        "reweighted it at.",
        "",
        "| assay | sequences | columns | Neff | Neff per column | how | against published |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for t in report["table"]["targets"]:
        if t["depth"] is None:
            lines.append(f"| `{t['dms_id']}` | — | — | — | — | {t['why']} | — |")
            continue
        block = report["table"]["alignments"][t["alignment"]]["readings"]["inclusive"]
        ratio = t["against_published"]["ratio"]
        lines.append(
            f"| `{t['dms_id']}` | {block['sequences']:,} | {block['columns']:,} | "
            f"{t['depth']:,.0f} | {t['depth_per_column']:.3f} | {block['method']} | "
            f"{'—' if ratio is None else f'{ratio:.2f}x'} |"
        )
    lines += [
        "",
        "The last column is our depth over the figure the maintainers publish for the same "
        "target. It is a check and not a target: theirs is computed on the alignment after "
        "their coverage filters and ours on the alignment as distributed, so the two count "
        "slightly different populations and a ratio near one is reassurance rather than proof.",
        "",
        f"Both readings of the identity boundary were computed. They give the same neighbour "
        f"floor for every alignment but {len(s['readings_that_differ'])} of "
        f"{s['alignments']}"
        + (
            ": " + ", ".join(f"`{n}`" for n in s["readings_that_differ"])
            if s["readings_that_differ"]
            else ""
        )
        + ".",
        "",
        f"Methods: {s['methods']['duplicates']} alignments where the threshold admits only an "
        f"identical row as a neighbour, {s['methods']['exact']} compared against themselves in "
        f"full, {s['methods']['sampled']} estimated from sampled rows with a bootstrap "
        "interval.",
    ]
    if report["problems"]:
        lines += ["", "**Unusable as it stands:**", ""] + [f"- {p}" for p in report["problems"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=CANONICAL_OUT, type=Path)
    parser.add_argument("--register", default=REGISTER, type=Path)
    parser.add_argument("--inputs", default=INPUTS, type=Path)
    parser.add_argument("--reference", default=REFERENCE, type=Path)
    parser.add_argument(
        "--only",
        default=None,
        help="substring of an alignment filename; a rehearsal that refuses to publish",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the committed artefact and exit; what CI runs",
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    if args.check:
        path = canonical_out() / "depth.json"
        if not path.exists():
            print(f"no depth artefact at {path}", file=sys.stderr)
            return 1
        problems = check(json.loads(path.read_text()))
        for problem in problems:
            print(f"problem: {problem}", file=sys.stderr)
        print(f"checked {path.name}: {len(problems)} problems")
        return 1 if problems else 0

    register = json.loads(args.register.read_text())
    inputs = json.loads(args.inputs.read_text())
    alignment_for = inputs["alignment_for_assay"]
    reference = reference_rows(args.reference, {a["dms_id"] for a in register["assays"]})
    path_for = staged_paths(inputs)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    destination = None if args.only else durable_for(out)
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-depth.json",
        durable=destination,
        durable_exempt=None if destination else "a rehearsal over part of the alignment set",
    ) as m:
        m.input_file(args.register, role="assay register")
        m.input_file(args.inputs, role="staged alignment map")
        m.input_file(args.reference, role="maintainers' reference table")
        m.parameter("decision_ref", "D-231")
        m.parameter("exact_budget", neff.EXACT_BUDGET)
        m.parameter("sample_rows", neff.SAMPLE_ROWS)
        m.parameter("bootstrap_resamples", neff.BOOTSTRAP)
        m.parameter("only", args.only)
        table = depth_table(register, alignment_for, reference, path_for, seed=SEED, only=args.only)
        report = {
            "task": TASK,
            "design_ref": "§B3 confounder",
            "decision_ref": "D-231",
            "table": table,
            "sanity": sanity(table),
        }
        report["problems"] = check(report)
        path = out / "depth.json"
        path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(path, role="depth")
        md = out / "depth.md"
        md.write_text(markdown(report) + "\n")
        m.output_file(md, role="depth-markdown")

    print(json.dumps(report["sanity"], indent=1))
    return 1 if report["problems"] and not args.only else 0


if __name__ == "__main__":
    raise SystemExit(main())

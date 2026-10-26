"""Assemble the §B3 homology axis into `metrics/homology.md` rows — B3.1, B3.2, B3.3.

Cheap and re-runnable, which is why it is not part of `tools/homology_pass.py`: the pass reads
a corpus for hours, this turns what it wrote into the artefact B3.5 and B5 read, and a change
to the schema costs seconds rather than another pass.

Three things it does beyond reshaping.

**It fills every cell of the grid, including the ones nothing searched.** `homology.check_complete`
refuses a table missing a target x manifest x measure, so "scores computed for all targets
against all manifests" is a property the artefact has rather than a claim its write-up makes.
The cells that were not searched carry `kind: not_searched` and the reason — the ESM3 proxy
manifest, whose records are every one `undetermined` so there is no surviving set to search
(A1.4), and the whole of the `structural` measure (D-167, D-180).

**It checks B3.2's presence verdicts against A2.1's.** An annotated domain family that is also
in A2.1's viral family selection was searched twice by different pipelines over the same
manifests at different depths. A2.1's detected set is a census over a sample and this pass is
over the surviving records, so the directional expectation is stated and checked rather than
assumed: a family A2.1 detected must be present here. The reverse is not required — this pass
reads more records — and a violation is a finding, not a rounding error. That is D-250's lesson
applied before anyone depends on the number.

**It never writes a zero for an absent hit.** `amazebio.homology.Row` refuses it; this tool
only has to not reach for one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import homology, objectstore, profiles
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B3.1/B3.2/B3.3"
SEED = 20261026
TARGETS = REPO / "artifacts" / "b3-targets" / "targets.json"
PASS_DIR = REPO / "artifacts" / "b3-pass"
CANONICAL_OUT = REPO / "artifacts" / "b3-homology"

#: Every A1.4 manifest, as its index lists them. The grid is this list times the targets times
#: the three measures, and a cell outside it is as much an error as a cell missing from it.
MANIFESTS: tuple[tuple[str, str], ...] = (
    ("evo1-literal", "opengenome"),
    ("evo1-charitable", "opengenome"),
    ("evo1-strict", "opengenome"),
    ("evo1-literal", "opengenome2"),
    ("evo1-charitable", "opengenome2"),
    ("evo1-strict", "opengenome2"),
    ("esm3-open-literal", "esm3-proxy"),
)

NOT_ENUMERATED = (
    "A1.4's manifest for this model enumerates no surviving record: every in-scope record is "
    "`undetermined`, because the published filter states no identity threshold for the rule "
    "that would decide it. There is no surviving set to search, and A1.6's enumeration of one "
    "is unfinished."
)

STRUCTURAL_UNAVAILABLE = (
    "The measure §B3 names is a TM-score to the nearest surviving structure, and A2.2 "
    "established it cannot be computed over these corpora: a structural-alphabet database "
    "predicted from sequence carries no C-alpha coordinates, and the tool refuses TM-score "
    "and LDDT output outright (D-167). The coordinate-free bit score that remains was priced "
    "at 70+ instance-hours for one manifest and declined (D-180). No manifest has been "
    "searched for this measure."
)


def load_pass(release: str) -> dict[str, Any] | None:
    path = PASS_DIR / release / f"best-{release}.json"
    return json.loads(path.read_text()) if path.exists() else None


def a2_1_detected(client: Any, policy: str, release: str) -> set[str] | None:
    """The Pfam families A2.1 detected on this manifest, for the cross-check."""
    key = f"corpora/results/a2-1/detections-pfam-{policy}-{release}.json"
    try:
        body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=key)["Body"].read()
    except Exception:
        return None
    payload = json.loads(body)
    rows = payload.get("families") or payload.get("rows") or []
    out = set()
    for row in rows:
        accession = row.get("family") or row.get("family_id") or row.get("accession")
        hits = row.get("hits") or row.get("records") or 0
        if accession and hits:
            out.add(accession)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=CANONICAL_OUT)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--no-durable",
        action="store_true",
        help="smoke runs only; the result is not citable and is not published",
    )
    parser.add_argument("--no-crosscheck", action="store_true", help="skip the A2.1 join")
    args = parser.parse_args(argv)

    if not TARGETS.exists():
        raise SystemExit(f"{TARGETS} is missing; run tools/homology_targets.py first")
    payload = json.loads(TARGETS.read_text())
    passes = {r: load_pass(r) for r in ("opengenome", "opengenome2")}

    targets = [
        homology.Target(
            dms_id=e["dms_id"],
            uniprot_id=e["uniprot_id"],
            length=e["target_length"],
            alignment=e["alignment"],
        )
        for e in payload["targets"]
    ]
    by_id = {e["dms_id"]: e for e in payload["targets"]}

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    with run(
        task=TASK,
        seed=SEED,
        outdir=out,
        manifest_name="run-homology.json",
        allow_dirty=args.allow_dirty,
        durable=None if args.no_durable else objectstore.durable_results("b3-homology"),
        durable_exempt=(
            "smoke run: --no-durable, so this output is scratch and is not cited"
            if args.no_durable
            else None
        ),
    ) as ctx:
        ctx.parameter("manifests", ["/".join(m) for m in MANIFESTS])
        ctx.parameter("measures", list(homology.MEASURES))
        ctx.parameter("primary_measure", "structural")
        ctx.parameter("min_model_coverage", profiles.MIN_MODEL_COVERAGE)
        ctx.parameter("pinned_e_value", homology.PINNED_E_VALUE)
        ctx.parameter("pinned_z", homology.PINNED_Z)
        ctx.input_file(TARGETS, role="target side of the axis")
        for release, data in passes.items():
            path = PASS_DIR / release / f"best-{release}.json"
            if data is not None:
                ctx.input_file(path, role=f"{release} corpus pass")

        rows: list[homology.Row] = []
        for policy, release in MANIFESTS:
            data = passes.get(release)
            for target in targets:
                entry = by_id[target.dms_id]
                if data is None:
                    for measure in ("sequence_profile", "domain_presence"):
                        rows.append(
                            homology.Row.without_score(
                                target,
                                policy=policy,
                                release=release,
                                measure=measure,
                                kind="not_searched",
                                reason=NOT_ENUMERATED,
                                searched_fraction=1.0,
                                params={"manifest": f"{policy}/{release}"},
                            )
                        )
                else:
                    fraction = data["searched_fraction"] or 1.0
                    shared = {
                        "manifest": f"{policy}/{release}",
                        "component": data["component"],
                        "selection": data["selection"],
                        "records_searched": data["records_searched"],
                        "manifest_records": data["manifest_records"],
                        "readings_sharing_this_pass": data["readings"],
                        "min_model_coverage": profiles.MIN_MODEL_COVERAGE,
                    }
                    rows.append(
                        _sequence_profile_row(
                            target, entry, data, policy, release, fraction, shared
                        )
                    )
                    rows.append(
                        _domain_presence_row(target, entry, data, policy, release, fraction, shared)
                    )
                rows.append(
                    homology.Row.without_score(
                        target,
                        policy=policy,
                        release=release,
                        measure="structural",
                        kind="not_searched",
                        reason=STRUCTURAL_UNAVAILABLE,
                        searched_fraction=1.0,
                        params={"manifest": f"{policy}/{release}", "role": "primary"},
                    )
                )

        homology.check_complete(rows, targets=targets, manifests=MANIFESTS)

        crosscheck = None
        if not args.no_crosscheck:
            crosscheck = _crosscheck(objectstore.client(), payload, passes)

        jsonl = out / "homology.jsonl"
        with jsonl.open("w") as sink:
            for row in rows:
                sink.write(json.dumps(row.to_dict(), sort_keys=True) + "\n")
        summary = _summary(rows, payload, passes, crosscheck)
        (out / "homology.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        (out / "homology.md").write_text(_markdown(summary, rows))
        ctx.output_file(jsonl, role="one row per target x manifest x measure")
        ctx.output_file(out / "homology.json", role="the axis summary")
        ctx.output_file(out / "homology.md", role="the axis, for a person")

    print(
        f"{len(rows)} rows over {len(targets)} targets x {len(MANIFESTS)} manifests x "
        f"{len(homology.MEASURES)} measures; "
        + ", ".join(f"{k}={v}" for k, v in sorted(summary["kinds"].items()))
    )
    return 0


def _sequence_profile_row(
    target: homology.Target,
    entry: dict[str, Any],
    data: dict[str, Any],
    policy: str,
    release: str,
    fraction: float,
    shared: dict[str, Any],
) -> homology.Row:
    params = {**shared, "cut": "pinned E-value against pinned Z", "profile": None}
    if not entry["profile"]:
        return homology.Row.without_score(
            target,
            policy=policy,
            release=release,
            measure="sequence_profile",
            kind="unanswerable",
            reason=entry["profile_absent_because"] or "no profile for this target",
            searched_fraction=fraction,
            params=params,
        )
    name = Path(entry["profile"]["profile"]).stem
    params = {
        **params,
        "profile": entry["profile"]["profile"],
        "profile_length": entry["profile"]["profile_length"],
    }
    hit = data["sequence_profile_best"].get(name)
    if hit is None:
        return homology.Row.without_score(
            target,
            policy=policy,
            release=release,
            measure="sequence_profile",
            kind="absent",
            reason=(
                "searched, and no hit met the pinned cut at the model-coverage floor. A "
                "censored observation at the cut, never a zero (metrics/homology.md)"
            ),
            searched_fraction=fraction,
            params=params,
        )
    return homology.Row.measured(
        target,
        policy=policy,
        release=release,
        measure="sequence_profile",
        score=hit["bits"],
        searched_fraction=fraction,
        params=params,
        evidence={
            "record": hit["record"],
            "model_coverage": hit["model_coverage"],
            "target_region": hit["target_region"],
            "model_length": hit["model_length"],
            "hits": hit["hits"],
            "second_best_bits": hit["second_best_bits"],
        },
    )


def _domain_presence_row(
    target: homology.Target,
    entry: dict[str, Any],
    data: dict[str, Any],
    policy: str,
    release: str,
    fraction: float,
    shared: dict[str, Any],
) -> homology.Row:
    families = entry["domain_families"]
    params = {**shared, "cut": "pfam gathering cutoffs", "annotated_families": len(families)}
    if not families:
        return homology.Row.without_score(
            target,
            policy=policy,
            release=release,
            measure="domain_presence",
            kind="unanswerable",
            reason=(
                "no Pfam family is annotated on this target at the pin's gathering cutoffs "
                "and the model-coverage floor, so nothing was looked for"
            ),
            searched_fraction=fraction,
            params=params,
        )
    best = data["domain_presence_best"]
    verdicts = []
    for family in families:
        hit = best.get(family["accession"])
        verdicts.append(
            {
                "accession": family["accession"],
                "family": family["family"],
                "instances_on_target": family["instances"],
                "present": hit is not None,
                "best_bits": hit["bits"] if hit else None,
                "record": hit["record"] if hit else None,
                "hits": hit["hits"] if hit else 0,
            }
        )
    present = sum(1 for v in verdicts if v["present"])
    evidence = {"families": verdicts, "annotated_families": len(families)}
    if not present:
        return homology.Row.without_score(
            target,
            policy=policy,
            release=release,
            measure="domain_presence",
            kind="absent",
            reason=(
                "searched, and none of this target's annotated families met Pfam's gathering "
                "cutoff at the model-coverage floor in the surviving records"
            ),
            searched_fraction=fraction,
            params=params,
            evidence=evidence,
        )
    return homology.Row.measured(
        target,
        policy=policy,
        release=release,
        measure="domain_presence",
        score=float(present),
        searched_fraction=fraction,
        params=params,
        evidence=evidence,
        normalise_over=len(families),
    )


def _crosscheck(
    client: Any, payload: dict[str, Any], passes: dict[str, dict[str, Any] | None]
) -> dict[str, Any]:
    """A2.1 detected these families; this pass must find them present. One direction only."""
    annotated = {f["accession"] for e in payload["targets"] for f in e["domain_families"]}
    out: dict[str, Any] = {
        "what_this_is": (
            "Annotated families that A2.1 also searched. A2.1's sample is a subset of the records "
            "this pass reads, so a family A2.1 detected must be present here; the reverse is not "
            "required and a disagreement in that direction is expected, not a fault."
        ),
        "manifests": {},
    }
    for policy, release in MANIFESTS:
        data = passes.get(release)
        if data is None:
            continue
        detected = a2_1_detected(client, policy, release)
        if detected is None:
            out["manifests"][f"{policy}/{release}"] = {"a2_1_table": "not readable"}
            continue
        shared = annotated & detected
        present = set(data["domain_presence_best"])
        out["manifests"][f"{policy}/{release}"] = {
            "annotated_families": len(annotated),
            "also_in_a2_1_detected": len(shared),
            "of_those_present_here": len(shared & present),
            "a2_1_detected_but_absent_here": sorted(shared - present),
            "present_here_but_not_in_a2_1_detected": len(present - detected),
            "holds": not (shared - present),
        }
    return out


def _summary(
    rows: list[homology.Row],
    payload: dict[str, Any],
    passes: dict[str, dict[str, Any] | None],
    crosscheck: dict[str, Any] | None,
) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    by_measure: dict[str, dict[str, int]] = {}
    for row in rows:
        kinds[row.kind] = kinds.get(row.kind, 0) + 1
        by_measure.setdefault(row.measure, {})
        by_measure[row.measure][row.kind] = by_measure[row.measure].get(row.kind, 0) + 1
    return {
        "task": TASK,
        "what_this_is": (
            "§B3's homology axis: one row per assay target x A1.4 manifest x measure, in the "
            "shape metrics/homology.md specifies. The primary measure is `structural` and no "
            "manifest could be searched for it; see the row reasons."
        ),
        "contract": "metrics/homology.md",
        "manifests": ["/".join(m) for m in MANIFESTS],
        "targets": len(payload["targets"]),
        "rows": len(rows),
        "kinds": kinds,
        "by_measure": by_measure,
        "passes": {
            release: None
            if data is None
            else {
                "component": data["component"],
                "selection": data["selection"],
                "records_searched": data["records_searched"],
                "manifest_records": data["manifest_records"],
                "searched_fraction": data["searched_fraction"],
                "complete": data["complete"],
                "genes": data["gene_calling"]["genes"],
                "residues": data["gene_calling"]["residues"],
                "elapsed_seconds": data["elapsed_seconds"],
            }
            for release, data in passes.items()
        },
        "crosscheck_against_a2_1": crosscheck,
    }


def _markdown(summary: dict[str, Any], rows: list[homology.Row]) -> str:
    lines = [
        "# The homology axis — B3.1, B3.2, B3.3",
        "",
        "Generated by `tools/homology_rows.py`. The contract is `metrics/homology.md`; the",
        "per-row artefact is `homology.jsonl`. Nothing here is pooled across assays.",
        "",
        f"{summary['rows']} rows: {summary['targets']} targets x "
        f"{len(summary['manifests'])} manifests x 3 measures.",
        "",
        "## Kinds, per measure",
        "",
        "| measure | measured | absent | not_searched | unanswerable |",
        "|---|---|---|---|---|",
    ]
    for measure in homology.MEASURES:
        counts = summary["by_measure"].get(measure, {})
        lines.append(
            f"| `{measure}` | {counts.get('measured', 0)} | {counts.get('absent', 0)} | "
            f"{counts.get('not_searched', 0)} | {counts.get('unanswerable', 0)} |"
        )
    lines += [
        "",
        "`structural` is §B3's pre-registered **primary** measure and carries no searched",
        "manifest. The reason travels in every one of its rows.",
        "",
        "## The passes",
        "",
        "| release | component | selection | records searched | of manifest | genes | residues |",
        "|---|---|---|---|---|---|---|",
    ]
    for release, info in sorted(summary["passes"].items()):
        if info is None:
            lines.append(f"| {release} | — | not searched | — | — | — | — |")
            continue
        lines.append(
            f"| {release} | {info['component']} | {info['selection']} | "
            f"{info['records_searched']:,} | {info['manifest_records']:,} | "
            f"{info['genes']:,} | {info['residues']:,} |"
        )
    measured = [r for r in rows if r.kind == "measured" and r.measure == "sequence_profile"]
    if measured:
        measured.sort(key=lambda r: -(r.normalised or 0))
        lines += [
            "",
            "## Sequence-profile homology, strongest first",
            "",
            "Bits per residue of the query, with the raw bit score beside it. Per assay, never",
            "pooled; a row from a prefix pass is a floor.",
            "",
            "| assay | manifest | bits | bits/residue | record coverage of model |",
            "|---|---|---|---|---|",
        ]
        for row in measured[:40]:
            lines.append(
                f"| `{row.dms_id}` | {row.policy}/{row.release} | {row.score:,.1f} | "
                f"{row.normalised:.4f} | {row.evidence.get('model_coverage')} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

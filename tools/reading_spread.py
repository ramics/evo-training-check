#!/usr/bin/env python3
"""Measure how far apart the three readings of each published filter are — task A0.4, §A0.

    pixi run -e dev python tools/reading_spread.py

Reads A1.4's per-reading manifests and removed sets and A3.2's headline groups, both from the
durable result store, and reports the spread in four places: the exclusion sets record by
record, the headline metrics, declared scope, and which rules the release leaves undecidable.

It recomputes nothing. A1.4 decided what each reading removes and A3.2 decided what that does
to the metrics; measuring the spread with a third implementation of either would be measuring
this tool's agreement with them, not the readings' agreement with each other.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, repro, spread

TASK = "A0.4"

#: What each verdict word is licensed to mean. `agree_on_the_corpus` is the one that matters:
#: readings can only be told apart by a corpus that carries the fields their rules read, so
#: agreement over a corpus that carries none of them is a fact about the corpus.
_GLOSS = {
    "agree": (
        "the readings remove the same records and report the same metrics, and every rule "
        "that separates them was decidable against the release."
    ),
    "agree_on_the_corpus": (
        "the readings remove the same records and report the same metrics, but at least one "
        "rule they word differently is one this release cannot decide. The agreement is a "
        "property of the released corpus as much as of the policy, and it is not evidence "
        "that the policy is unambiguous."
    ),
    "readings_disagree": (
        "the readings remove different records, so the published policy does not determine "
        "an exclusion set."
    ),
    "not_measurable": "fewer than two readings have been executed.",
}

#: Where the inputs live. Both are their task's durable result prefix, so this tool reads what
#: a reader of the paper would be pointed at rather than a local cache (`metrics/manifests.md`).
MANIFESTS = objectstore.durable_results("a1-4")
HEADLINE = objectstore.durable_results("a3-2") + "/headline.json"


def _get(client: Any, uri: str) -> Any:
    bucket, key = objectstore.split_uri(uri)
    return json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())


def _removed_ids(client: Any, prefix: str, name: str) -> list[str]:
    bucket, key = objectstore.split_uri(f"{prefix}/{name}")
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    return [json.loads(line)["record_id"] for line in body.splitlines() if line.strip()]


def load(client: Any) -> tuple[list[spread.PolicyManifest], list[dict[str, Any]], dict[str, str]]:
    index = _get(client, f"{MANIFESTS}/index.json")
    manifests: list[spread.PolicyManifest] = []
    for entry in index["manifests"]:
        doc = _get(client, f"{MANIFESTS}/{entry['manifest']}")
        declared = (doc.get("removed") or {}).get("file")
        removed: list[str] | None = []
        if declared:
            removed = _removed_ids(client, MANIFESTS, declared)
        elif entry.get("removed_records"):
            raise SystemExit(
                f"{entry['manifest']} declares {entry['removed_records']} removed records and "
                "names no file; the exclusion sets cannot be compared without it"
            )
        manifests.append(spread.PolicyManifest.from_document(doc, removed=removed))
    headline = _get(client, HEADLINE)
    return manifests, list(headline["groups"]), dict(index.get("deferred") or {})


def measure(
    manifests: list[spread.PolicyManifest],
    groups: list[dict[str, Any]],
    deferred: dict[str, str],
) -> dict[str, Any]:
    pairs = spread.pair_spreads(manifests)
    cells = spread.metric_cells(groups)
    components = spread.component_spreads(manifests)
    models = sorted({m.model for m in manifests})
    verdicts = []
    for model in models:
        mine = [m for m in manifests if m.model == model]
        verdicts.append(
            spread.verdict_for(
                model,
                manifests,
                cells,
                components,
                not_executed={
                    k: v
                    for k, v in deferred.items()
                    if _stem(k) in {_stem(m.policy_id) for m in mine}
                },
            )
        )
    return {
        "task": TASK,
        "design_ref": "§A0",
        "inputs": {"manifests": MANIFESTS, "headline": HEADLINE},
        "readings_executed": sorted({m.policy_id for m in manifests}),
        "readings_not_executed": deferred,
        "exclusion_sets": [p.to_dict() for p in pairs],
        "metrics": [c.to_dict() for c in cells],
        "components": [c.to_dict() for c in components if c.verdict_differs or c.disputed_rules],
        "verdicts": [v.to_dict() for v in verdicts],
    }


def _stem(policy_id: str) -> str:
    """`evo1-literal` -> `evo1`. A policy id is its model's stem plus its reading."""
    return policy_id.rsplit("-", 1)[0]


def summarise(doc: dict[str, Any]) -> str:
    lines = ["# A0.4 — the spread between readings", ""]
    for verdict in doc["verdicts"]:
        lines += [f"## {verdict['model']}", ""]
        executed = len(verdict["readings_compared"])
        total = executed + len(verdict["readings_not_executed"])
        if verdict["reproducible"] == "not_measurable":
            lines += [
                f"**Not measurable.** {executed} of this policy's {total} readings has been "
                "executed against a corpus, so there is no second exclusion set to compare "
                "it with.",
                "",
            ]
            for policy, why in verdict["readings_not_executed"].items():
                lines.append(f"- `{policy}` was not executed: {why}")
            lines.append("")
            continue
        lines += [
            f"Readings compared: {', '.join(f'`{r}`' for r in verdict['readings_compared'])}.",
            "",
            f"- exclusion sets identical: **{verdict['removals_identical']}**",
            f"- headline metrics identical: **{verdict['metrics_identical']}**",
            f"- declared scope differs between readings: **{verdict['scope_differs']}**",
            "",
            f"Verdict: **{verdict['reproducible']}**. " + _GLOSS[str(verdict["reproducible"])],
            "",
        ]
        if verdict["rules_disputed_but_undecidable"]:
            lines += [
                "Rules the readings word differently and the release cannot decide: "
                + ", ".join(f"`{r}`" for r in verdict["rules_disputed_but_undecidable"]),
                "",
            ]

    lines += ["## Exclusion sets, record by record", ""]
    for pair in doc["exclusion_sets"]:
        empty = pair["shared"] == 0 and pair["symmetric_difference"] == 0
        lines.append(
            f"- {pair['release']}: `{pair['left']}` vs `{pair['right']}` — "
            f"{pair['shared']:,} shared, {pair['symmetric_difference']:,} differing, "
            f"Jaccard {pair['jaccard']:.4f}"
            + (
                " — both readings remove nothing, so this is agreement over an empty set"
                if empty
                else ""
            )
        )

    lines += ["", "## Headline metrics, per registry and release", ""]
    for cell in doc["metrics"]:
        values = ", ".join(f"{v:.6f}" for v in sorted(set(cell["m1"].values())))
        lines.append(
            f"- {cell['release']} / {cell['universe']}: M1 {values} across "
            f"{len(cell['readings'])} readings (span {cell['m1_span']:.6f}); "
            f"M2 identical: {cell['m2_identical']}; routes identical: {cell['routes_identical']}"
        )

    lines += ["", "## Where the readings do diverge", ""]
    if not doc["components"]:
        lines.append("Nowhere: no component's verdict or decidability differs between readings.")
    for component in doc["components"]:
        verdicts = ", ".join(f"`{k}`→{v}" for k, v in sorted(component["verdicts"].items()))
        lines.append(f"- {component['release']} / {component['component']}: {verdicts}")
        if component["disputed_rules"]:
            lines.append(
                "  - disputed and undecidable here: "
                + ", ".join(f"`{r}`" for r in component["disputed_rules"])
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a0-4"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=None,  # a comparison of two stored artefacts; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-spread.json",
            durable=objectstore.durable_results("a0-4"),
        ) as manifest:
            manifest.parameter("manifests", MANIFESTS)
            manifest.parameter("headline", HEADLINE)
            client = objectstore.client()
            manifests, groups, deferred = load(client)
            doc = measure(manifests, groups, deferred)
            (args.outdir / "spread.json").write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n"
            )
            (args.outdir / "spread.md").write_text(summarise(doc))
            manifest.output_file(args.outdir / "spread.json", role="spread")
            manifest.output_file(args.outdir / "spread.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(summarise(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

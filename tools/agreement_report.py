#!/usr/bin/env python3
"""Put A8.1's two tiers side by side — DESIGN.md §A8.

    pixi run -e dev python tools/agreement_report.py artifacts/a8-1/agreement-*.json

`tools/filter_agreement.py` runs one tier per pass, because each is a forward read of a
staged object and the instance runs them in sequence. Neither pass can produce §A8's actual
deliverable, which is the comparison: UniRef90 is the similarity predicate at 90% identity
and UniRef50 is the same predicate at 50%, so the pair is the threshold sweep and a single
tier is one point on it. This reads both artefacts and writes the table.

Separate from the pass on purpose. The pass runs on an instance that cannot be inspected and
gets one shot at its `UserData`; a rendering step that runs here can be corrected without
buying another launch, and it reads published artefacts rather than the corpus, so it is
reproducible from them alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import agreement, objectstore, repro

TASK = "A8.1"

#: The cells, in the order the table lists them, with the sentence each one means. The words
#: are the deliverable as much as the numbers: "neither" and "out of scope" are both zeros in
#: a naive table and they mean opposite things.
CELL_MEANING = (
    (agreement.CELL_BOTH, "both filters remove it"),
    (agreement.CELL_NEITHER, "neither removes it, the taxon rules having judged it"),
    (agreement.CELL_SIMILARITY_ONLY, "only the similarity filter removes it"),
    (agreement.CELL_LABEL_ONLY, "only the taxon rules remove it"),
    (
        agreement.CELL_OUT_OF_SCOPE_REMOVED,
        "not viral, so the taxon rules never see it — and removed by similarity anyway",
    ),
    (agreement.CELL_OUT_OF_SCOPE, "not viral, and nothing removes it"),
)


def load(paths: list[Path]) -> list[dict[str, Any]]:
    docs = [json.loads(p.read_text()) for p in paths]
    releases = {d["release"] for d in docs}
    if len(releases) != 1:
        raise SystemExit(f"these artefacts are of different releases ({sorted(releases)})")
    if len({d["tier"] for d in docs}) != len(docs):
        raise SystemExit("two artefacts of the same tier; the comparison would double-count")
    if any(d["bounded"] for d in docs):
        raise SystemExit(
            "one of these passes stopped at --limit-bytes. UniRef is ordered by accession, "
            "so it read a prefix rather than a sample and its shares estimate nothing"
        )
    return sorted(docs, key=lambda d: -d["identity"])


def render(docs: list[dict[str, Any]]) -> str:
    first = docs[0]
    lines = [
        "# A8.1 — do the two filters mean the same thing by viral?",
        "",
        f"Release {first['release']}. Evo's taxon rules, as all three of its readings carry "
        f"them, against ESM3-open's similarity rule read as co-membership of the publisher's "
        f"own cluster. One column per identity.",
        "",
        "## The cross-tab",
        "",
        "| records | " + " | ".join(f"{d['identity']:.0%}" for d in docs) + " | meaning |",
        "|---|" + "---|" * len(docs) + "---|",
    ]
    for cell, meaning in CELL_MEANING:
        cols = " | ".join(f"{d['counts']['cells'][cell]:,}" for d in docs)
        lines.append(f"| `{cell}` | {cols} | {meaning} |")
    judged = " | ".join(f"{d['counts']['judged_members']:,}" for d in docs)
    agreed = " | ".join(
        f"{d['counts']['agreement']:.4f}" if d["counts"]["agreement"] is not None else "—"
        for d in docs
    )
    lines += [
        f"| **judged** | {judged} | records the taxon rules were in a position to judge |",
        f"| **agreement** | {agreed} | of those, the share both filters treat alike |",
        "",
        "## What the disagreement is made of",
        "",
        "`label_only` is empty, and it is empty before the pass rather than as a result of "
        "it: every record the taxon rules remove is viral by NCBI taxonomy, every "
        "viral-annotated record is a seed under the reading in force, and a seed's own "
        "cluster contains it. The disagreement is one-sided, so what matters is its size and "
        "what kind of sequence is in it.",
        "",
        "| kind | " + " | ".join(f"{d['identity']:.0%}" for d in docs) + " |",
        "|---|" + "---|" * len(docs) + "",
    ]
    for kind in agreement.KINDS:
        cols = " | ".join(
            f"{d['counts']['kind_by_cell'][agreement.CELL_SIMILARITY_ONLY][kind]:,}" for d in docs
        )
        lines.append(f"| {kind} (similarity only) | {cols} |")
    for kind in (agreement.KIND_CELLULAR, agreement.KIND_UNPLACED):
        cols = " | ".join(
            f"{d['counts']['kind_by_cell'][agreement.CELL_OUT_OF_SCOPE_REMOVED][kind]:,}"
            for d in docs
        )
        lines.append(f"| {kind} (out of scope, removed) | {cols} |")

    lines += [
        "",
        "## What could not be run, and what had to be read rather than executed",
        "",
        "Only Evo's taxon rules run on a protein corpus. These rules read IMG/VR metadata "
        "that a protein record does not carry, and were not executed:",
        "",
    ]
    for rule, kind in first["rules_not_runnable"]:
        lines.append(f"- `{rule}` (`{kind}`)")
    lines += [
        "",
        "Two of the rules' own names do not resolve against the pinned taxonomy as written:",
        "",
    ]
    for name, how, _ in first["name_resolution"]:
        if how != "scientific name":
            lines.append(f"- **{name}** — {how}.")
    loose = " and ".join(
        f"{d['counts']['loose_only_members']:,} at {d['identity']:.0%}" for d in docs
    )
    lines += [
        "",
        f"Taken as written those rules remove nothing. A reading that resolved the names "
        f"loosely would reach {loose} further records, which is reported here and is not in "
        f"the table above.",
        "",
        "## The confound",
        "",
        first["confound"],
        "",
        "The similarity side is the publisher's own clustering at two identities, not an "
        "alignment against the whole of UniProt and not ESM3-open's own threshold, which is "
        "unpublished. A1.6's banded curve sweeps our stated range; this sweeps theirs.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("artefacts", nargs="+", type=Path, help="one agreement-*.json per tier")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a8-1"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    docs = load(args.artefacts)
    args.outdir.mkdir(parents=True, exist_ok=True)
    out = args.outdir / "agreement.md"
    try:
        with repro.run(
            TASK,
            seed=None,
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-agreement-report.json",
            durable=objectstore.durable_results("a8-1"),
        ) as manifest:
            manifest.parameter("tiers", [d["tier"] for d in docs])
            manifest.parameter("identities", [d["identity"] for d in docs])
            for path in args.artefacts:
                manifest.input_file(path, role="tier agreement")
            out.write_text(render(docs) + "\n")
            manifest.output_file(out, role="report")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

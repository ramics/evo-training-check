#!/usr/bin/env python3
"""Which detected records belong to a hazard family *by biology* — the second instrument.

    pixi run -e dev python tools/hazard_record_membership.py --outdir artifacts/c5-1

X1.8 and X1.9 answer "does this record carry a Pfam family whose **name** refers to a group the
published filter denylists" and get 319 records. D-261 found that count is an upper bound: 81 of
the 82 records surviving into Evo 2's training data reached a denylisted group through
`matched_on: identifier` — the Pfam identifier, on families Pfam's own descriptions call
"protein-**like**" and "VLTF3 **like**".

This tool asks the same question through an instrument that reads no family name:

    does the record's detected family appear in the hazard family set that
    `tools/hazard_family_set.py` builds by cross-reference from the listed taxa?

The two instruments share the group list and nothing else — no matching rule, no Pfam metadata,
and on this side no family name is ever compared to anything. Where they disagree, the
disagreement is the result.

**The classification is fixed here, before the join is run, and it introduces no threshold of
this project's own.** Every detection in the input already clears Pfam's curated gathering
cutoff; that is what makes it a detection, and inventing a second cutoff on top would be this
project choosing which hits count after seeing them. So records are placed by two properties
that are measurements rather than choices:

* **`nominated`** — the detected family is in the hazard set, i.e. some reviewed UniProtKB entry
  of a listed taxon cross-references it. A published fact about a curated database.
* **`exclusivity`** — the fraction of that family's reviewed entries contributed by the listed
  taxa. `1.0` means the family *is* the listed biology; below 1.0 means the family also holds
  entries from taxa the list does not name, so a detection on it is evidence of the family and
  not yet evidence of the taxon.

giving three classes, in decreasing strength:

* `hazard_family_exclusive` — nominated, and every reviewed entry of the family comes from the
  listed taxa.
* `hazard_family_shared` — nominated, but the family also holds entries from taxa the list does
  not name; `exclusivity` says how much.
* `not_nominated` — the family has reviewed entries, and none of them is from a listed taxon,
  so the name axis's claim for that record is vocabulary only.
A family that only stratum **T** nominates carries no exclusivity — the measure is a property of
the taxon nomination, and a regulation naming a protein names no taxon — so such a family falls
to `hazard_family_shared`, which understates it. That is conservative and it does not arise in
this result: none of the detected records carries a toxin-stratum family. A record that did would
need its own reading, not this rule.

* `unnominatable` — the family has **no reviewed entries at all**, so no taxon could nominate it
  and this instrument cannot speak to the record either way. A4.5 already calls such a family
  `unmeasurable`; keeping it apart from `not_nominated` matters because "the listed taxa do not
  carry this family" and "nobody has curated a protein into this family" are different findings,
  and only the first is evidence against the name axis.

A record carrying several families takes its strongest class, and every family it carries is
listed, because a record is not summarised by its best hit.

**No cut-off is applied to hit strength, and it is reported per record.** `score / threshold`,
identity and model coverage come from A7.5's published region metrics, which exist for the
IMG/VR records. They travel with every row so a reader can see that a nominated, exclusive
family can still be reached by a distant homolog — the distinction D-261 is about. Pooling them
into a verdict would hide exactly that.

**What this does not settle.** Training-corpus membership. D-262's sequence join produced the
accession list that would say which of these records survive into what Evo 2 was trained on, and
that list was scratch and is gone with its container. The records present in the training data
are a *subset* of the records here, so a record this tool places as `not_nominated` cannot
become a hazard-family record by being in the training set; but the per-record training column
needs the join rebuilt and is absent rather than guessed.

Reads only published tables. No sequence, no residues (D-103), seconds to run.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, repro

TASK = "C5.1"

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_OUT = ROOT / "artifacts" / "c5-1"

#: The name axis's per-record table (X1.9) and A7.5's region metrics, both published.
RECORDS_KEY = "corpora/results/x1-9/denylist-named-family-records.tsv"
REGIONS_KEY = "corpora/results/a7-5/regions-denylist-named-family-records-imgvr-pfam-38.2.tsv"

#: The hazard family set this run joins against, built by the companion tool.
FAMILY_SET = "hazard-family-set.json"

#: A4.5's background table, for the reviewed-entry total of a family no listed taxon nominated.
BACKGROUND = ROOT / "artifacts" / "a4-5" / "background-pfam-38.2.json"

CLASSES = (
    "hazard_family_exclusive",
    "hazard_family_shared",
    "not_nominated",
    "unnominatable",
)


def durable_for(out: Path, *, allow_dirty: bool) -> str | None:
    """The durable destination, or None for a run that must not publish (D-193, D-224, D-265).

    Two conditions, and both are refusals rather than warnings. `--out` must be the canonical
    directory, because `repro.run`'s `durable` is derived from the task id and cannot see where
    the run was told to write. And `--allow-dirty` must not be set: that flag exists for local
    iteration, and combining it with the canonical directory publishes an artefact whose
    manifest names the last *commit* rather than the code that produced it — permanently, in a
    bucket with no `DeleteObject`. That happened on 2026-10-27 and the stray
    `by-commit/02b1a45.../` twin cannot be removed.
    """
    if allow_dirty:
        print(
            "not publishing: --allow-dirty is set, so this run's provenance would name a commit "
            "that does not contain the code that produced it",
            file=sys.stderr,
        )
        return None
    if out.resolve() == CANONICAL_OUT.resolve():
        return objectstore.durable_results("c5-1")
    print(
        f"not publishing: --out {out} is not {CANONICAL_OUT}, so this run is a probe",
        file=sys.stderr,
    )
    return None


def fetch(client: Any, key: str, dest: Path) -> Path:
    body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=key)["Body"].read()
    dest.write_bytes(body)
    return dest


#: A Pfam accession, for the delimiter guard below.
PFAM_ACCESSION = re.compile(r"^PF\d{5}$")


def split_families(cell: str, record_id: str) -> list[str]:
    """The record's families, with the delimiter checked rather than assumed.

    X1.9's table separates multi-family cells with `|`. Reading it as comma-separated does not
    fail: it yields one token per cell, that token matches no family in the hazard set, and
    every multi-family record silently classifies as carrying no hazard family — which is the
    direction that flatters the safeguard, and is what this guard caught in its own first run.
    So each token has to look like a Pfam accession or the run refuses.
    """
    fams = [f.strip() for f in cell.split("|") if f.strip()]
    bad = [f for f in fams if not PFAM_ACCESSION.match(f)]
    if bad:
        raise SystemExit(
            f"{record_id}: {bad} in `pfam_families` does not look like a Pfam accession. The "
            f"cell is {cell!r}. Either the table's delimiter has changed or the column has "
            "moved; both would classify records silently and wrongly, so this refuses."
        )
    return fams


def classify(
    families: list[str],
    hazard: dict[str, dict[str, Any]],
    background: dict[str, dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """The record's class and the per-family detail behind it.

    `background` supplies the reviewed-entry total for a family the listed taxa did *not*
    nominate, which is what separates `not_nominated` from `unnominatable`.
    """
    detail: list[dict[str, Any]] = []
    for fam in families:
        h = hazard.get(fam)
        if h is None:
            meta = background.get(fam)
            detail.append(
                {
                    "family": fam,
                    "nominated": False,
                    "name": meta["name"] if meta else None,
                    "specificity": meta["class"] if meta else None,
                    "reviewed_total": meta["reviewed_total"] if meta else None,
                }
            )
            continue
        excl = h["exclusivity"]
        detail.append(
            {
                "family": fam,
                "nominated": True,
                "name": h["name"],
                "exclusivity": excl,
                "specificity": h["specificity"],
                "viral_selection": h["viral_selection"],
                "nominating_entries": h["nominating_entries"],
                "reviewed_total": h["reviewed_total"],
                "nominated_by_taxa": h["nominated_by_taxa"],
            }
        )
    if any(d.get("nominated") and d.get("exclusivity") == 1.0 for d in detail):
        return "hazard_family_exclusive", detail
    if any(d.get("nominated") for d in detail):
        return "hazard_family_shared", detail
    if all(d.get("reviewed_total") == 0 for d in detail):
        return "unnominatable", detail
    return "not_nominated", detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(CANONICAL_OUT))
    ap.add_argument(
        "--family-set",
        default=None,
        help=f"the hazard family set JSON; defaults to <outdir>/{FAMILY_SET}",
    )
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    durable = durable_for(out, allow_dirty=args.allow_dirty)
    fset = Path(args.family_set) if args.family_set else out / FAMILY_SET

    with repro.run(
        TASK,
        outdir=out,
        allow_dirty=args.allow_dirty,
        manifest_name="run-hazard-record-membership.json",
        durable=durable,
        durable_exempt=(
            None
            if durable
            else "not the deliverable: a probe directory, or a dirty tree under --allow-dirty"
        ),
    ) as m:
        m.note(
            "Which detected records carry a family the listed taxa nominate by cross-reference. "
            "The second instrument for X1.8's name-matched count; no family name is read here."
        )
        payload = json.loads(m.input_file(fset, role="hazard-family-set").read_text())
        hazard = {f["accession"]: f for f in payload["per_family"]}
        background = {
            f["accession"]: f
            for f in json.loads(m.input_file(BACKGROUND, role="specificity").read_text())[
                "per_family"
            ]
        }

        client = objectstore.client()
        recs = csv.DictReader(
            m.input_file(
                fetch(client, RECORDS_KEY, out / "in-denylist-named-family-records.tsv"),
                role="name-axis-records",
            )
            .read_text()
            .splitlines(),
            delimiter="\t",
        )
        rows = list(recs)

        regions: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for r in csv.DictReader(
            m.input_file(fetch(client, REGIONS_KEY, out / "in-a7-5-regions.tsv"), role="regions")
            .read_text()
            .splitlines(),
            delimiter="\t",
        ):
            regions[(r["record_id"], r["accession"])].append(r)

        results: list[dict[str, Any]] = []
        for r in rows:
            fams = split_families(r["pfam_families"], r["record_id"])
            cls, detail = classify(fams, hazard, background)
            strengths = []
            for d in detail:
                for reg in regions.get((r["record_id"], d["family"]), ()):
                    thr = float(reg["threshold"])
                    strengths.append(
                        {
                            "family": d["family"],
                            "score": float(reg["score"]),
                            "threshold": thr,
                            "score_over_threshold": round(float(reg["score"]) / thr, 3)
                            if thr
                            else None,
                            "identity": float(reg["identity"]),
                            "model_coverage": float(reg["model_coverage"]),
                        }
                    )
            results.append(
                {
                    "record_id": r["record_id"],
                    "component": r["component"],
                    "pfam_families": fams,
                    "name_axis_groups": [g for g in r["denylisted_groups_named"].split("|") if g],
                    "label_rule_outcome": r["label_rule_outcome"],
                    "biology_class": cls,
                    "families": detail,
                    "region_metrics": strengths,
                }
            )

        by_class = {c: [x for x in results if x["biology_class"] == c] for c in CLASSES}

        def ratios(items: list[dict[str, Any]]) -> dict[str, Any]:
            vals = [
                s["score_over_threshold"]
                for x in items
                for s in x["region_metrics"]
                if s["score_over_threshold"] is not None
            ]
            if not vals:
                return {"n": 0}
            return {
                "n": len(vals),
                "median": round(statistics.median(vals), 3),
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "at_or_above_10x": sum(1 for v in vals if v >= 10),
            }

        summary = {
            "records": len(results),
            "by_class": {c: len(by_class[c]) for c in CLASSES},
            "removed_by_published_rule": {
                c: sum(1 for x in by_class[c] if x["label_rule_outcome"] == "removed")
                for c in CLASSES
            },
            "score_over_threshold": {c: ratios(by_class[c]) for c in CLASSES},
            "name_axis_records": len(results),
            "agreement_with_name_axis": {
                "name_axis_says_denylisted": len(results),
                "biology_agrees_nominated": len(results) - len(by_class["not_nominated"]),
                "biology_agrees_exclusive": len(by_class["hazard_family_exclusive"]),
                "biology_disagrees": len(by_class["not_nominated"]),
            },
        }

        doc = {
            "task": TASK,
            "design_ref": "metrics/costcurve.md §3, DESIGN.md §C5, §7",
            "question": (
                "Of the records the audit detected in Evo 2's released viral component, which "
                "carry a Pfam family that the published hazard list's own taxa nominate by "
                "database cross-reference?"
            ),
            "instrument": (
                "hazard family set built by taxon -> reviewed UniProtKB entry -> Pfam "
                "cross-reference. No Pfam family name is read on this side."
            ),
            "independent_of": (
                "X1.8/X1.9's name axis, which matches Pfam identifiers and descriptions against "
                "the same group list. Shared input: the 19 families and 12 orders the published "
                "rules name. Nothing else."
            ),
            "classification_fixed_before_run": {
                "classes": list(CLASSES),
                "rule": (
                    "exclusivity == 1.0 -> hazard_family_exclusive; nominated at all -> "
                    "hazard_family_shared; otherwise not_nominated. A record takes its "
                    "strongest class and lists every family it carries."
                ),
                "no_strength_cutoff": (
                    "Every detection already clears Pfam's curated gathering cutoff. No second "
                    "cutoff is applied; score/threshold, identity and coverage are reported per "
                    "record instead."
                ),
            },
            "does_not_claim": [
                "That a record in any class is dangerous. The strongest class says the record "
                "carries a family whose reviewed membership is wholly from the listed taxa; it "
                "does not say the record is a member of those taxa, and the region metrics show "
                "several are reached by distant homology.",
                "Training-corpus membership. D-262's accession list is gone with its container, "
                "so the column that would say which of these survive into Evo 2's training data "
                "is absent rather than estimated. Those records are a subset of these.",
            ],
            "summary": summary,
            "per_record": results,
        }

        jp = out / "hazard-record-membership.json"
        jp.write_text(json.dumps(doc, indent=2) + "\n")
        m.output_file(jp, role="record-membership")

        tp = out / "hazard-record-membership.tsv"
        cols = (
            "record_id",
            "component",
            "biology_class",
            "label_rule_outcome",
            "pfam_families",
            "max_exclusivity",
            "max_score_over_threshold",
            "name_axis_groups",
        )
        with tp.open("w") as fh:
            fh.write("\t".join(cols) + "\n")
            for x in results:
                ex = [d["exclusivity"] for d in x["families"] if d.get("exclusivity") is not None]
                sr = [
                    s["score_over_threshold"]
                    for s in x["region_metrics"]
                    if s["score_over_threshold"] is not None
                ]
                fh.write(
                    "\t".join(
                        (
                            x["record_id"],
                            x["component"],
                            x["biology_class"],
                            x["label_rule_outcome"],
                            ",".join(x["pfam_families"]),
                            str(max(ex)) if ex else "",
                            str(max(sr)) if sr else "",
                            "|".join(x["name_axis_groups"]),
                        )
                    )
                    + "\n"
                )
        m.output_file(tp, role="record-membership-tsv")

        print(json.dumps(summary, indent=2))
        print(f"wrote {jp}")
        print(f"wrote {tp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

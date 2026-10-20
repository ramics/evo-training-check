#!/usr/bin/env python3
"""Which taxa the denylist rules account for in Evo 2's release, for A7.3.

A7.2 reported Evo 2's forward mismatch split four ways by rule: 217,078 records the
prokaryotic-host rule removes, 23,523 the unspecificity rule removes, 21,867 from
denylisted orders, and 2,102 from the 19 denylisted families. A7.3 has to publish the
last two at the taxon the rule names, because those are the rules whose subject §4's
reporting limits actually govern.

**The order of the chain is what makes this a derivation rather than a count.** Counting
released records whose family is on the denylist gives 4,706, not 2,102 — because the
host rule fires first and 2,604 of those records are already gone by the time the family
rule is reached. The difference is not a rounding error; it is more than the figure
itself. A breakdown computed independently of the chain would be wrong by 124%, which is
why this imports A7.2's re-execution rather than re-deriving the rules from the spec, and
why `DESIGN.md`'s disclosure standard asks a developer to publish the order of an
order-dependent step at all.

**On §4's reporting limits.** Results go out by homology class, fold family and survival
route, and no ranking of which model is most capable for which pathogen is published. A
table of how many records of each virus family a published denylist accounts for in a
published corpus is neither: the families are names on the developer's own list, the
counts are of records in a released artefact, and nothing here is a capability
measurement. The write-up says that rather than leaving a reader to wonder why the table
stops where it does.

    python3 tools/evo2_denylist_detail.py
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
from pathlib import Path
from typing import Any

from amazebio import conformance as cf
from amazebio import objectstore
from amazebio.policyspec import Outcome
from amazebio.repro import run

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("conformance_close", _HERE / "conformance_close.py")
assert _spec and _spec.loader
close = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(close)

#: The two rules this pass breaks down, and the rank each one names.
RULE_RANK = {
    "remove-denylisted-families": "f",
    "remove-denylisted-orders": "o",
}


def ranks_of(classification: str) -> dict[str, str]:
    """Split an IMG/VR lineage string into its rank letters.

    IMG/VR writes the lineage as eight `rank__name` fields joined by semicolons, with
    unassigned ranks left empty. An empty field is an absent assignment, not an empty name,
    so it is dropped rather than recorded as `""` — a record with no family is not a record
    in a family called nothing.
    """
    out: dict[str, str] = {}
    for part in classification.split(";"):
        if "__" in part:
            rank, name = part.split("__", 1)
            if name:
                out[rank] = name
    return out


def breakdown(scan: dict[str, Any], run_: dict[str, Any], totals: dict[str, Any]) -> dict[str, Any]:
    """Attribute each removed released record to the rule that removes it, then to its taxon.

    The attribution is the chain's own: a record is counted against the first rule that
    removes it, exactly as `evo2_arm` counts it, so the per-taxon totals sum to the per-rule
    totals A7.2 published.
    """
    evo2 = scan["evo2"]
    released = evo2["released_by_classification"]
    released_hc = evo2["released_hc_by_classification"]

    per_rule: dict[str, collections.Counter] = {r: collections.Counter() for r in RULE_RANK}
    unnamed: dict[str, int] = {r: 0 for r in RULE_RANK}
    by_rule_total: collections.Counter = collections.Counter()

    for classification, n in released.items():
        row = run_["verdicts"].get(classification)
        if row is None:
            continue
        n_hc = released_hc.get(classification, 0)
        for group, count in (("hc", n_hc), ("non_hc", n - n_hc)):
            if not count:
                continue
            verdict = row[group]
            if verdict["outcome"] is Outcome.RETAINED:
                continue
            rule = verdict["rule_id"] or "(no rule)"
            by_rule_total[rule] += count
            if rule not in RULE_RANK:
                continue
            name = ranks_of(classification).get(RULE_RANK[rule])
            if name is None:
                unnamed[rule] += count
            else:
                per_rule[rule][name] += count

    # A record removed by the family rule must carry a family; if one does not, the rule and
    # the attribution disagree and that is a defect in this pass rather than a finding about
    # the release. Caught here rather than published as a silent zero.
    for rule, missing in unnamed.items():
        if missing:
            raise SystemExit(
                f"{missing} records attributed to {rule} carry no name at rank "
                f"{RULE_RANK[rule]!r}; the attribution and the rule disagree"
            )

    naive = _naive_counts(released)
    return {
        "by_rule_totals": dict(sorted(by_rule_total.items())),
        "rules": {
            rule: {
                "rank": RULE_RANK[rule],
                "records": int(per_rule[rule].total()),
                "distinct_taxa": len(per_rule[rule]),
                "by_taxon": dict(per_rule[rule].most_common()),
                "naive_records_ignoring_chain_order": naive[rule],
                "records_the_chain_removes_earlier": naive[rule] - int(per_rule[rule].total()),
            }
            for rule in RULE_RANK
        },
        "note_on_order": (
            "Counted against the first rule in the published chain that removes the record. "
            "Counting membership of the denylist alone, ignoring the order, gives a larger "
            "figure for both rules, because the host rule fires first; the difference is "
            "reported beside each total rather than left for a reader to rediscover."
        ),
        "note_on_reporting_limits": (
            "DESIGN.md §4 bars a published ranking of which model is most capable for which "
            "pathogen. This is not one: the taxa are names on the developer's own published "
            "denylist and the counts are of records in a released corpus. No capability is "
            "measured here and none may be inferred from these counts."
        ),
    }


def _naive_counts(released: dict[str, int]) -> dict[str, int]:
    """What a breakdown that ignored the chain's order would have reported.

    Published so the order-dependence is visible as a number rather than as a caution.
    """
    policies = close.load_policy_dir(close.SPECS)
    literal = next(
        p
        for p in policies.values()
        if p.id.startswith(close.POLICY_PREFIX) and p.reading == "literal"
    )
    names = {}
    for rule in literal.rules:
        if rule.id in RULE_RANK:
            names[rule.id] = set(rule.params["names"])
    out = {}
    for rule_id, allowed in names.items():
        rank = RULE_RANK[rule_id]
        out[rule_id] = sum(n for c, n in released.items() if ranks_of(c).get(rank) in allowed)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--input-scan",
        default="artifacts/a7-2/2022-12-20/input-scan-2022-12-20.json",
        help="the IMG/VR input scan, local or s3://. Default is v4.1, the release A7.2 "
        "identified as the procedure's input (D-071).",
    )
    ap.add_argument("--outdir", default="artifacts/a7-3")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    with run(
        "A7.3",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-denylist-detail.json",
        durable=objectstore.durable_results("a7-3"),
    ) as m:
        scan = close._load(args.input_scan, outdir)
        if args.input_scan.startswith("s3://"):
            m.input_url(args.input_scan, role="input-scan", verified=False)
        else:
            m.input_file(Path(args.input_scan), role="input-scan")
        for spec in sorted(close.SPECS.glob(f"{close.POLICY_PREFIX}*.yaml")):
            m.input_file(spec, role="policy-spec")
        m.parameter("primary_host_unit", cf.PRIMARY_HOST_UNIT.value)
        m.parameter("rules_broken_down", sorted(RULE_RANK))
        m.note(
            "Attribution follows the published chain's order; a count of denylist membership "
            "alone is reported beside it and is larger."
        )

        policies = {
            k: v
            for k, v in close.load_policy_dir(close.SPECS).items()
            if k.startswith(close.POLICY_PREFIX)
        }
        release_key = close.INPUT_RELEASE[scan["release"]]
        per_reading = {}
        for policy in sorted(policies.values(), key=lambda p: p.reading):
            run_ = close.re_execute(
                policy, scan, release_key=release_key, unit=cf.PRIMARY_HOST_UNIT
            )
            totals = close.record_level_totals(run_)
            per_reading[policy.reading] = breakdown(scan, run_, totals)

        report = {
            "task": "A7.3",
            "input_release": scan["release"],
            "input_version": scan["version"],
            "per_reading": per_reading,
        }
        out = outdir / "denylist-detail.json"
        out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(out, role="denylist-detail")

    lit = report["per_reading"]["literal"]["rules"]
    for rule, row in lit.items():
        print(f"\n{rule}: {row['records']:,} records across {row['distinct_taxa']} taxa")
        print(
            f"  (denylist membership alone: {row['naive_records_ignoring_chain_order']:,}; "
            f"{row['records_the_chain_removes_earlier']:,} removed by an earlier rule)"
        )
        for taxon, n in list(row["by_taxon"].items())[:25]:
            print(f"   {n:>7,}  {taxon}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

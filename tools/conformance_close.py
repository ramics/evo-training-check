#!/usr/bin/env python3
"""Close A7.2's conformance gaps: both directions, both Evo releases, all three readings.

A7.1 re-executed three of Evo 1's six published rules against Evo 1's released viral component
and reported the other three as not checkable, because the release carries none of the metadata
they read (D-047). A1.7 staged what they read. This runs the whole procedure against its own
input and compares the result with what each developer actually released — forward and converse,
for Evo 1 and for Evo 2, under each of the three readings, which are distinguishable for the
first time here.

It touches no corpus. Everything comes from two reduced artefacts — the input scan
(`tools/imgvr_conformance_scan.py`) and A7.1's release scan — so the headline numbers recompute
in a second and A3.3's second implementation can check them against the same intermediates.

Five things it will not do, each of which would produce a number that reads better than it is.

**It does not report a single mismatch rate.** Forward failures (a record released that the rule
removes) and converse failures (a record removed that the rule retains) say opposite things
about a filter, and the interesting part of this audit is which direction the filter errs in. A
combined rate would hide exactly that.

**It does not report the vOTU rule at record level.** The rule keeps one representative per
vOTU; no input order is published, so which record survives is undetermined (D-017) and a
record-level diff of it would measure our sort order. It is compared at vOTU level, with the
unit named beside every number, and the retained total the published chain implies is reported
as an **interval** rather than a point.

**It does not read a per-record host field.** The host rule counts findings for a taxonomic
*classification* and joins them back to the record (D-058), which is the one unit error that
would otherwise produce a confident wrong number here. The unit was declared before the pass
that computed it, and the other two readings of "found ... at least twice" travel with it.

**It does not revise a spec to fit the data.** Fitting a predicate to the data it audits is the
one move a conformance audit may not make (D-051). A rule that looks wrong is a finding.

**It does not merge the two Evo releases.** The audited *procedure* is Evo 1's, restated by
reference in Evo 2; the audited *outputs* are two different artefacts and are reported as two
(D-019).

    python3 tools/conformance_close.py            # both IMG/VR releases, from local artefacts
    python3 tools/conformance_close.py --input-scan artifacts/a7-2/<date>/input-scan-<date>.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import conformance as cf
from amazebio.policyspec import Outcome, Policy, Record, load_policy_dir
from amazebio.policyspec import evaluate as evaluate_policy
from amazebio.repro import run

SPECS = Path(__file__).resolve().parent.parent / "policies" / "specs"
POLICY_PREFIX = "evo1-"

#: Which `RELEASE_INPUTS` key each staged IMG/VR release answers to. The two are not
#: interchangeable at row level even though every aggregate A1.7 counted is identical: v4.1 is
#: an in-place erratum of v4's sequence-information table, which is the table every rule here
#: reads (D-063, D-064).
INPUT_RELEASE = {"2022-09-20": "imgvr-v4", "2022-12-20": "imgvr-v4.1"}

#: Evo 1's own count of the IMG/VR component of its corpus, Table S3 p43 (D-055). The one
#: published quantity the re-executed chain can be checked against end to end.
EVO1_TABLE_S3_RECORDS = 2_653_046

#: And the share of those records Evo 1's own Figure S1B puts at host kingdom *Unknown*
#: (2,374,733 of 2,653,046). The check D-058 sets for this task: a host rule read at the wrong
#: unit cannot reproduce it.
EVO1_UNKNOWN_HOST_RECORDS = 2_374_733

#: The host classes a record can carry, for the composition checks. `none` is a class here and
#: not an absence: it is the population the classification-level reading of the host rule exists
#: to account for, and 89.5% of Evo 1's retained records sit in it.
HOST_CLASSES = ("prokaryotic", "eukaryotic", "other", "none")


# --------------------------------------------------------------------------------------
# Re-executing one reading over the input
# --------------------------------------------------------------------------------------


def _non_hc_label(scan: dict[str, Any]) -> str:
    """The confidence label standing in for "not high-confidence" in the `why` strings.

    Every label that is not `High-confidence` fails the published gate identically, so the
    records are grouped rather than evaluated one label at a time. The most common of them is
    named in the output so a reader can see which label the group is mostly made of.
    """
    other = {k: v for k, v in scan.get("confidence", {}).items() if k != "High-confidence"}
    return max(other, key=lambda k: other[k]) if other else "(no label)"


def re_execute(
    policy: Policy, scan: dict[str, Any], *, release_key: str, unit: cf.HostUnit
) -> dict[str, Any]:
    """Run one reading's record-level rules over every classification in the input.

    Returns the per-classification verdicts and the rule that produced each. Two pseudo-records
    per classification, not one per record: every record-level rule in these procedures is a
    function of the taxonomic classification and the confidence label alone — the host rule
    included, since its count is built over the classification (D-058) — so a verdict per
    (classification, high-confidence?) pair is exact and not a summary. 15.7 million evaluations
    reduce to a few thousand with no loss.
    """
    restriction = cf.restrict(policy, release=release_key)
    non_hc = _non_hc_label(scan)
    verdicts: dict[str, dict[str, Any]] = {}
    for classification, info in scan["by_classification"].items():
        tag = cf.parse_lineage_tag(classification)
        findings = info.get("host_findings", {})
        host_occurrences = {
            host_class: findings.get(host_class, {}).get(unit.value, 0)
            for host_class in ("prokaryotic", "eukaryotic", "other")
        }
        host_occurrences = {k: v for k, v in host_occurrences.items() if v}
        row: dict[str, Any] = {"tag": tag, "info": info}
        for group, label in (("hc", "High-confidence"), ("non_hc", non_hc)):
            record = Record(
                id=f"{group}:{classification}",
                component="IMG/VR",
                attributes={"confidence": label},
                taxonomy=dict(tag.taxonomy),
                host_occurrences=dict(host_occurrences),
            )
            decision = evaluate_policy(restriction.policy, [record])[0]
            rule = next((r for r in restriction.kept if r.id == decision.rule_id), None)
            row[group] = {
                "outcome": decision.outcome,
                "rule_id": decision.rule_id,
                "why": decision.why,
                "cause": (
                    cf.classify(decision, record, tag=tag, rule=rule).value
                    if rule is not None and decision.outcome is Outcome.REMOVED
                    else None
                ),
            }
        verdicts[classification] = row
    return {
        "restriction": restriction,
        "coverage": cf.Coverage.of(restriction, policy),
        "verdicts": verdicts,
        "non_hc_label": non_hc,
    }


def record_level_totals(run_: dict[str, Any]) -> dict[str, Any]:
    """What the dedup-free record-level chain does to the whole input.

    "Dedup-free" is load-bearing and stated wherever these numbers appear: the vOTU rule is held
    out of this chain, so every record is put to the remaining rules rather than only the
    representatives. The retained count here is therefore **not** the published procedure's
    output size — :func:`votu_interval` is what computes that.
    """
    removed_by_rule: collections.Counter = collections.Counter()
    removed_by_cause: collections.Counter = collections.Counter()
    retained = 0
    retained_hc = 0
    passing: dict[str, bool] = {}
    for classification, row in run_["verdicts"].items():
        info = row["info"]
        n_hc = info["records_hc"]
        n_non_hc = info["records"] - n_hc
        passing[classification] = row["hc"]["outcome"] is Outcome.RETAINED
        for group, n in (("hc", n_hc), ("non_hc", n_non_hc)):
            if not n:
                continue
            verdict = row[group]
            if verdict["outcome"] is Outcome.RETAINED:
                retained += n
                if group == "hc":
                    retained_hc += n
            else:
                removed_by_rule[verdict["rule_id"] or "(no rule)"] += n
                removed_by_cause[verdict["cause"] or "(not a failure)"] += n
    return {
        "records_examined": sum(r["info"]["records"] for r in run_["verdicts"].values()),
        "records_removed": sum(removed_by_rule.values()),
        "records_retained_dedup_free": retained,
        "records_retained_dedup_free_high_confidence": retained_hc,
        "removed_by_rule": dict(sorted(removed_by_rule.items())),
        "classifications_total": len(run_["verdicts"]),
        "classifications_surviving": sum(1 for v in passing.values() if v),
        "passing": passing,
        "note": (
            "A dedup-free chain: the vOTU rule is held out and every record is put to the "
            "remaining rules. `records_retained_dedup_free` is therefore not the published "
            "procedure's output size — see the vOTU interval."
        ),
    }


def votu_interval(scan: dict[str, Any], passing: dict[str, bool]) -> dict[str, Any]:
    """The number of records the published chain retains, as the interval it actually is.

    The published order keeps high-confidence records, then one representative per vOTU, then
    applies the host and taxonomy rules. So one surviving vOTU is one retained record, and
    whether a vOTU survives depends on which of its records was chosen — a choice no published
    source determines. Where every high-confidence record of a vOTU carries the same
    classification the choice does not matter; where they do not, it does, and those vOTUs are
    the width of the interval.
    """
    structure = scan["votu_structure"]
    single = {
        c: info["votus_owned_outright"]
        for c, info in scan["by_classification"].items()
        if info["votus_owned_outright"]
    }
    mixed = [(tuple(sig["classifications"]), sig["votus"]) for sig in structure["mixed_signatures"]]
    lower, upper = cf.votu_bounds(single, mixed, passing)
    straddling = sum(
        n
        for sig, n in mixed
        if any(passing.get(c, False) for c in sig) and not all(passing.get(c, False) for c in sig)
    )
    return {
        "unit": "record (one per surviving vOTU)",
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "high_confidence_votus": structure["high_confidence_votus"],
        "votus_straddling_the_predicate": straddling,
        "why_an_interval": (
            "The vOTU representative is chosen by an input order no published source states "
            "(D-017), so the retained count is bounded rather than determined. The width is "
            f"the {straddling:,} vOTUs whose high-confidence records disagree about taxonomy in "
            "a way the rules act on."
        ),
    }


# --------------------------------------------------------------------------------------
# The two comparisons
# --------------------------------------------------------------------------------------


def per_classification_bounds(
    scan: dict[str, Any], passing: dict[str, bool]
) -> dict[str, tuple[int, int]]:
    """Predicted surviving records per classification, as `(lower, upper)`.

    A classification owns a vOTU outright when every high-confidence record of that vOTU carries
    it, and those vOTUs are certain to be represented by it. A mixed vOTU might be represented
    by any of its classifications, so it raises the upper bound of each one that passes without
    raising any lower bound.
    """
    bounds: dict[str, tuple[int, int]] = {}
    for c, info in scan["by_classification"].items():
        if not passing.get(c, False):
            bounds[c] = (0, 0)
            continue
        own = info["votus_owned_outright"]
        extra = sum(
            sig["votus"]
            for sig in scan["votu_structure"]["mixed_signatures"]
            if c in sig["classifications"]
        )
        bounds[c] = (own, own + extra)
    return bounds


def _votu_rule_id(run_: dict[str, Any]) -> str | None:
    """The id of the deduplication rule held out of the record-level chain, if there is one."""
    deferred = run_["restriction"].deferred
    return deferred[0][0].id if deferred else None


def evo1_arm(
    scan: dict[str, Any], run_: dict[str, Any], totals: dict[str, Any], released: dict[str, int]
) -> dict[str, Any]:
    """Compare the re-executed chain against Evo 1's own released component, per lineage.

    Evo 1's release carries a lineage tag and no accession, so its records cannot be identified
    individually and the comparison is per lineage — the unit the taxonomy rules act on anyway,
    and a join key rather than a coincidence because the released tag is formatted exactly as
    IMG/VR's own classification column.

    Both directions, separately, and both against the bound that favours the developer: a
    forward failure is a released record in excess of the **most** the rule could have retained,
    and a converse failure is a shortfall against the **least** it could have retained. Anything
    inside the interval is consistent with the published procedure under some input order and is
    not counted against it.
    """
    bounds = per_classification_bounds(scan, totals["passing"])
    forward: list[dict[str, Any]] = []
    converse: list[dict[str, Any]] = []
    absent: list[dict[str, Any]] = []
    by_rule: collections.Counter = collections.Counter()
    by_cause: collections.Counter = collections.Counter()
    for tag, n_released in sorted(released.items(), key=lambda kv: -kv[1]):
        if tag not in bounds:
            # A lineage in the release that the staged input does not contain at all. Not a
            # rule failure: either the record entered after the filter ran, or the release was
            # built from a different IMG/VR cut. Reported as its own category rather than being
            # counted as over-retention, which is what it would look like otherwise.
            absent.append({"lineage_tag": tag, "released_records": n_released})
            continue
        lower, upper = bounds[tag]
        verdict = run_["verdicts"][tag]["hc"]
        removed = verdict["outcome"] is not Outcome.RETAINED
        if n_released > upper:
            # Two different failures reach this branch and they must not be added together.
            # Where a record-level rule removes the lineage outright, `upper` is zero and every
            # released record under it is that rule's failure. Where the lineage survives the
            # record-level rules, the excess is over the number of *vOTUs* that lineage could
            # represent — so it is the deduplication rule that was not applied, and attributing
            # it to anything else would name the wrong rule in a write-up that names labs.
            excess = n_released - upper
            rule = verdict["rule_id"] if removed else _votu_rule_id(run_)
            cause = verdict["cause"] if removed else cf.Cause.UNEXPLAINED.value
            why = (
                verdict["why"]
                if removed
                else (
                    f"lineage survives the record-level rules, and {n_released:,} records were "
                    f"released against at most {upper:,} vOTUs it could represent: more than "
                    "one record per vOTU survived"
                )
            )
            by_rule[rule or "(no rule)"] += excess
            by_cause[cause or "(not a failure)"] += excess
            forward.append(
                {
                    "lineage_tag": tag,
                    "released_records": n_released,
                    "predicted_upper": upper,
                    "excess": excess,
                    "attributed_to": "record-level rule" if removed else "vOTU rule",
                    "rule": rule,
                    "cause": cause,
                    "why": why,
                }
            )
        elif n_released < lower:
            converse.append(
                {
                    "lineage_tag": tag,
                    "released_records": n_released,
                    "predicted_lower": lower,
                    "shortfall": lower - n_released,
                }
            )
    # Lineages the chain retains that the release does not carry at all: the converse direction's
    # other half, and the one a tag-level comparison can see most clearly.
    missing = [
        {"lineage_tag": c, "predicted_lower": lo, "predicted_upper": up}
        for c, (lo, up) in sorted(bounds.items(), key=lambda kv: -kv[1][0])
        if lo > 0 and c not in released
    ]
    return {
        "comparison_key": cf.COMPARISON_KEYS["opengenome-stage2"],
        "comparison_unit": "lineage",
        "released_records": sum(released.values()),
        "released_lineages": len(released),
        "forward": {
            "direction": "released records the published rule removes",
            "records": sum(f["excess"] for f in forward),
            "lineages": len(forward),
            "records_removed_by_a_record_level_rule": sum(
                f["excess"] for f in forward if f["attributed_to"] == "record-level rule"
            ),
            "records_in_excess_of_the_votu_bound": sum(
                f["excess"] for f in forward if f["attributed_to"] == "vOTU rule"
            ),
            "why_split": (
                "A lineage a record-level rule removes outright, and a lineage that survives "
                "those rules but was released in more copies than it has vOTUs to represent, "
                "are failures of different rules. Summing them would name the wrong rule."
            ),
            "by_rule": dict(sorted(by_rule.items())),
            "by_cause": dict(sorted(by_cause.items())),
            "detail": sorted(forward, key=lambda f: -f["excess"])[:200],
        },
        "converse": {
            "direction": "records the published rule retains that the release does not carry",
            "shortfall_in_released_lineages": sum(c["shortfall"] for c in converse),
            "lineages_short": len(converse),
            "lineages_absent_entirely": len(missing),
            "records_in_lineages_absent_entirely": sum(m["predicted_lower"] for m in missing),
            "detail_short": converse[:200],
            "detail_absent": missing[:200],
        },
        "released_lineages_absent_from_the_input": {
            "lineages": len(absent),
            "records": sum(a["released_records"] for a in absent),
            "detail": absent[:200],
            "note": (
                "Lineages the release carries that the staged IMG/VR release does not. Not "
                "counted in either direction: a record that postdates the filter, or a corpus "
                "built from another cut, is not a rule the filter failed to apply. The cause "
                "`postdates_filter` exists for this and remains unassignable per record, "
                "because neither release publishes a per-record provenance date."
            ),
        },
    }


def evo2_arm(scan: dict[str, Any], run_: dict[str, Any], totals: dict[str, Any]) -> dict[str, Any]:
    """Compare the re-executed chain against Evo 2's released component, per record.

    Evo 2's release carries the IMG/VR accession and no lineage — the exact inverse of Evo 1's
    (D-049) — so with the input in hand this arm is a record-level set difference and not an
    aggregate comparison. The forward direction is exact. The converse is reported at vOTU level
    and not at record level, and the reason is structural rather than a shortcut: the chain
    retains one record per surviving vOTU and which one is undetermined, so a record present in
    the input and absent from the release is only a failure if its whole vOTU is missing.
    """
    evo2 = scan.get("evo2")
    if not evo2:
        return {
            "run": False,
            "why": (
                "No accession inventory for Evo 2's released component was supplied to the "
                "input scan, so this arm did not run. It is a missing arm, not a null result."
            ),
        }
    released = evo2["released_by_classification"]
    released_hc = evo2["released_hc_by_classification"]
    forward: list[dict[str, Any]] = []
    by_rule: collections.Counter = collections.Counter()
    by_cause: collections.Counter = collections.Counter()
    for classification, n in sorted(released.items(), key=lambda kv: -kv[1]):
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
            by_rule[verdict["rule_id"] or "(no rule)"] += count
            by_cause[verdict["cause"] or "(not a failure)"] += count
            forward.append(
                {
                    "classification": classification,
                    "released_records": count,
                    "group": group,
                    "rule": verdict["rule_id"],
                    "cause": verdict["cause"],
                    "why": verdict["why"],
                }
            )

    # The vOTU rule, at vOTU level and nowhere else. Restricted to the vOTUs the chain predicts
    # should survive, which is the population the rule makes its claim about.
    histogram: collections.Counter = collections.Counter()
    for classification, hist in evo2["votu_released_histogram_single"].items():
        if not totals["passing"].get(classification, False):
            continue
        for n, votus in hist.items():
            histogram[int(n)] += votus
    comparison = cf.votu_comparison(histogram)
    mixed_excluded = sum(evo2["votu_released_histogram_mixed"].values())

    return {
        "run": True,
        "comparison_key": cf.COMPARISON_KEYS["opengenome2-imgvr"],
        "provenance": (
            "The audited procedure is Evo 1's, restated by reference in Evo 2 ('As previously "
            "described'); the audited output is Evo 2's own release. Two artefacts, not one "
            "(D-019)."
        ),
        "released_accessions": evo2["released_accessions"],
        "released_accessions_joined_to_the_input": evo2["released_accessions_found_in_imgvr"],
        "released_accessions_absent_from_the_input": evo2["released_accessions_absent_from_imgvr"],
        "forward": {
            "direction": "released records the published rule removes",
            "unit": "record",
            "records": int(by_rule.total()),
            "by_rule": dict(sorted(by_rule.items())),
            "by_cause": dict(sorted(by_cause.items())),
            "detail": forward[:200],
        },
        "converse": {
            "direction": "vOTUs the published rule retains that contributed no released record",
            "unit": "vOTU",
            "votus": comparison.none,
            "why_not_per_record": (
                "The chain retains one record per surviving vOTU and which record is "
                "undetermined (D-017), so an input record absent from the release is a failure "
                "only if its whole vOTU is absent. Counted at vOTU level for that reason, and "
                "never reported as a record-level rate."
            ),
        },
        "votu_level": {
            "unit": comparison.unit,
            "predicted_surviving_votus_compared": comparison.considered,
            "contributed_exactly_one": comparison.exactly_one,
            "contributed_none": comparison.none,
            "contributed_more_than_one": comparison.more_than_one,
            "released_records_in_those": comparison.released_records_in_multi,
            "rate_at_votu_level": comparison.conformance_rate,
            "histogram": comparison.histogram,
            "mixed_classification_votus_excluded": mixed_excluded,
            "verdict": comparison.verdict,
        },
        "released_host_classes": evo2.get("released_host_classes", {}),
    }


# --------------------------------------------------------------------------------------
# The checks this task inherited, and the spread §A7 asks for
# --------------------------------------------------------------------------------------


def published_checks(
    scan: dict[str, Any], interval: dict[str, Any], evo2: dict[str, Any], totals: dict[str, Any]
) -> dict[str, Any]:
    """The two numbers A7.2 was handed as checks rather than as results.

    D-064 predicted the chain would land near Evo 1's own 2,653,046 from the aggregates alone
    and recorded it as falsifiable. D-058 set the harder one: a host rule read at the wrong unit
    cannot put 89.5% of the retained records at an unknown host kingdom.
    """
    lower, upper = interval["lower"], interval["upper"]
    unknown_share_estimate = None
    survivors = sum(
        info["records"]
        for c, info in scan["by_classification"].items()
        if totals["passing"].get(c, False)
    )
    no_host = sum(
        info.get("seq_column_host", {}).get("none", 0)
        for c, info in scan["by_classification"].items()
        if totals["passing"].get(c, False)
    )
    if survivors:
        unknown_share_estimate = no_host / survivors
    exact = None
    released_hosts = evo2.get("released_host_classes") or {}
    if released_hosts:
        total = sum(released_hosts.values())
        exact = {
            "release": "opengenome2-imgvr",
            "records": total,
            "by_host_class": released_hosts,
            "share_without_a_host_prediction": (
                released_hosts.get("none", 0) / total if total else None
            ),
        }
    return {
        "d064_retained_count": {
            "published": EVO1_TABLE_S3_RECORDS,
            "published_source": "S-EVO1-PREPRINT Table S3, p43 (D-055)",
            "re_executed_interval": [lower, upper],
            "published_count_inside_the_interval": lower <= EVO1_TABLE_S3_RECORDS <= upper,
            "distance_to_interval": (
                0
                if lower <= EVO1_TABLE_S3_RECORDS <= upper
                else min(abs(EVO1_TABLE_S3_RECORDS - lower), abs(EVO1_TABLE_S3_RECORDS - upper))
            ),
            "d064_prediction": (
                "A1.7 predicted from aggregates alone that the high-confidence gate leaves "
                "5,576,197 records over 2,917,521 distinct vOTUs, and that a prokaryotic-host "
                "requirement would take that the further 9.1% down to Evo 1's own 2,653,046. "
                "This is the computation over joined records that D-064 recorded as falsifiable."
            ),
        },
        "d058_host_kingdom_unknown": {
            "published": EVO1_UNKNOWN_HOST_RECORDS,
            "published_of": EVO1_TABLE_S3_RECORDS,
            "published_share": EVO1_UNKNOWN_HOST_RECORDS / EVO1_TABLE_S3_RECORDS,
            "published_source": "S-EVO1-PREPRINT Figure S1B, p41 (D-058); read off a raster",
            "re_executed_share_estimate": unknown_share_estimate,
            "estimate_is_over": (
                "records of surviving classifications, not surviving records: the vOTU "
                "representative is undetermined, so the share is exact only under the "
                "assumption that which record represents a vOTU is independent of whether it "
                "carries a host prediction. Stated as an estimate for that reason."
            ),
            "exact_on_evo2": exact,
            "why_it_is_a_check": (
                "A per-record reading of the host rule cannot retain a record with no host "
                "annotation at all, so it cannot produce this share. Reproducing it is what "
                "confirms the classification-level unit; failing to would mean the unit is "
                "wrong whatever else reproduces."
            ),
        },
    }


def reading_spread(per_reading: dict[str, Any]) -> dict[str, Any]:
    """The spread across readings §A7 says matters as much as any single number.

    A7.1 could only report that it was unmeasurable: every rule the three readings differ over
    reads an input the release does not carry, so they re-executed an identical pipeline
    (D-047). With the input in hand they differ, and this is the first point at which the number
    exists.
    """

    def spread(path: Any) -> dict[str, Any]:
        values = {reading: path(block) for reading, block in per_reading.items()}
        numeric = [v for v in values.values() if v is not None]
        return {
            "per_reading": values,
            "min": min(numeric) if numeric else None,
            "max": max(numeric) if numeric else None,
            "spread": (max(numeric) - min(numeric)) if numeric else None,
        }

    return {
        "measurable": True,
        "why_it_is_measurable_here": (
            "The readings differ over the host rule — the literal reading's prokaryotic count, "
            "the charitable reading's additional one-strike eukaryotic-host rule, the strict "
            "reading's exclusivity requirement — and over scope. Every one of those reads host "
            "occurrences, which the release does not carry and the input does. A7.1 reported "
            "the spread as unmeasurable against the release; that was a property of the "
            "release (D-047), and this is the number it was standing in for."
        ),
        "records_removed_record_level": spread(lambda b: b["record_level"]["records_removed"]),
        "classifications_surviving": spread(
            lambda b: b["record_level"]["classifications_surviving"]
        ),
        "retained_lower_bound": spread(lambda b: b["votu_interval"]["lower"]),
        "retained_upper_bound": spread(lambda b: b["votu_interval"]["upper"]),
        "evo1_forward_records": spread(lambda b: b["evo1"]["forward"]["records"]),
        "evo2_forward_records": spread(
            lambda b: b["evo2"]["forward"]["records"] if b["evo2"]["run"] else None
        ),
    }


def host_unit_sensitivity(
    policies: dict[str, Policy], scan: dict[str, Any], *, release_key: str
) -> dict[str, Any]:
    """What the choice of counting unit costs, under each reading.

    The unit was declared before any of this was computed (`conformance.PRIMARY_HOST_UNIT`), so
    this is a sensitivity and not a selection. It is reported because the choice is ours: a
    reader is entitled to see how much of the headline rests on it.
    """
    out: dict[str, Any] = {}
    for unit in cf.HostUnit:
        per_reading = {}
        for policy in policies.values():
            run_ = re_execute(policy, scan, release_key=release_key, unit=unit)
            totals = record_level_totals(run_)
            interval = votu_interval(scan, totals["passing"])
            per_reading[policy.reading] = {
                "records_removed": totals["records_removed"],
                "classifications_surviving": totals["classifications_surviving"],
                "retained_lower": interval["lower"],
                "retained_upper": interval["upper"],
            }
        out[unit.value] = {
            "definition": cf.HOST_UNITS[unit],
            "primary": unit is cf.PRIMARY_HOST_UNIT,
            "per_reading": per_reading,
        }
    return out


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def analyse(scan: dict[str, Any], released: dict[str, int]) -> dict[str, Any]:
    policies = {k: v for k, v in load_policy_dir(SPECS).items() if k.startswith(POLICY_PREFIX)}
    if not policies:
        raise SystemExit(f"no policies matching {POLICY_PREFIX!r} in {SPECS}")
    release_key = INPUT_RELEASE[scan["release"]]

    per_reading: dict[str, Any] = {}
    for policy in sorted(policies.values(), key=lambda p: p.reading):
        run_ = re_execute(policy, scan, release_key=release_key, unit=cf.PRIMARY_HOST_UNIT)
        totals = record_level_totals(run_)
        interval = votu_interval(scan, totals["passing"])
        coverage = run_["coverage"]
        evo2 = evo2_arm(scan, run_, totals)
        per_reading[policy.reading] = {
            "policy_id": policy.id,
            "rule_coverage_record_level": coverage.rule_coverage,
            "rule_coverage_with_own_unit": coverage.unit_coverage,
            "rules_re_executed": list(coverage.kept_rules),
            "rules_compared_at_their_own_unit": [
                {"rule": r, "why": why} for r, why in coverage.deferred_rules
            ],
            "rules_not_checkable": [{"rule": r, "needs": why} for r, why in coverage.dropped_rules],
            "record_level": {k: v for k, v in totals.items() if k != "passing"},
            "votu_interval": interval,
            "evo1": evo1_arm(scan, run_, totals, released),
            "evo2": evo2,
            "published_checks": published_checks(scan, interval, evo2, totals),
            "non_high_confidence_label": run_["non_hc_label"],
        }

    return {
        "task": "A7.2",
        "input_release": scan["release"],
        "input_version": scan["version"],
        "input_release_key": release_key,
        "input_records": scan["records"],
        "input_scan_was_partial": scan.get("partial", False),
        "host_unit": {
            "primary": cf.PRIMARY_HOST_UNIT.value,
            "definitions": {u.value: t for u, t in cf.HOST_UNITS.items()},
            "declared_before_computation": True,
            "sensitivity": host_unit_sensitivity(policies, scan, release_key=release_key),
        },
        "directions_reported_separately": (
            "Forward and converse are never summed. An over-broad filter and a leaky one are "
            "different findings, and which direction a filter errs in is the interesting part."
        ),
        "per_reading": per_reading,
        "reading_spread": reading_spread(per_reading),
        "causes": {c.value: text for c, text in cf.CAUSES.items()},
        "accession_shapes": scan.get("accession_shapes"),
        "provenance": {
            "input_is_the_real_input": (
                "The publisher's own files at the publisher's own checksums, pinned from a "
                "public inventory before this project held any bytes (A1.7, D-064). Not a proxy."
            ),
            "which_v4": (
                "Evo 1 cites 'IMG/VR v4'; the publisher names one release v4 and the other "
                "v4.1, and Evo 1's corpus build date is unstated, so which one the procedure "
                "ran on is not determinable from Evo 1's words (D-052, D-063). Both are staged "
                "and both are run; every number here names the one it came from."
            ),
            "weaker_end_governs": (
                "A conformance claim is only as strong as the weaker of its two ends. The "
                "input end is verified (A1.7); the output end is each developer's own release "
                "(A1.1, D-017), so no proxy substitution arises on either side — but the "
                "v4/v4.1 ambiguity above is a row-level qualification on every row-level count."
            ),
        },
    }


def summarise(result: dict[str, Any]) -> str:
    head = result["per_reading"]["literal"]
    interval = head["votu_interval"]
    checks = head["published_checks"]
    evo1, evo2 = head["evo1"], head["evo2"]
    spread = result["reading_spread"]
    lines = [
        f"# A7.2 — the published filter re-executed against its own input "
        f"({result['input_release']}, {result['input_version']})",
        "",
        f"Input: {result['input_records']:,} IMG/VR records · "
        f"record-level rule coverage {head['rule_coverage_record_level']} "
        f"({head['rule_coverage_with_own_unit']} counting the vOTU rule at its own unit) · "
        f"host counting unit `{result['host_unit']['primary']}`",
        "",
    ]
    if result["input_scan_was_partial"]:
        lines += [
            "> **NOT A RESULT.** The input scan behind these numbers is marked partial: it "
            "covered a bounded number of rows per shard. Re-run it without `--max-rows` before "
            "citing anything here.",
            "",
        ]
    lines += [
        "## What closed, and what cannot",
        "",
        f"A7.1 reached three of Evo 1's six published rules against Evo 1's release. With the "
        f"filter's input in hand that becomes **{head['rule_coverage_record_level']} at record "
        "level**, and the three rules it could not run are now run:",
        "",
    ]
    for rule in head["rules_re_executed"]:
        lines.append(f"- re-executed per record: `{rule}`")
    for item in head["rules_compared_at_their_own_unit"]:
        lines.append(
            f"- compared at its own unit, never per record: `{item['rule']}` — {item['why']}"
        )
    for item in head["rules_not_checkable"]:
        lines.append(f"- **still not checkable**: `{item['rule']}` — needs `{item['needs']}`")
    lines += [
        "",
        "The coverage moved because the declaration of what the audited artefact carries "
        "changed, not because any rule was hand-picked back in: `RELEASE_INPUTS` gained the "
        "input's own inventory and `restrict` did the rest (D-047).",
        "",
        "## How many records the published procedure keeps, as an interval",
        "",
        f"**{interval['lower']:,} to {interval['upper']:,} records**, one per surviving vOTU, "
        f"out of {interval['high_confidence_votus']:,} high-confidence vOTUs. "
        f"{interval['why_an_interval']}",
        "",
        f"Evo 1 publishes {checks['d064_retained_count']['published']:,} for the same component "
        f"({checks['d064_retained_count']['published_source']}). That is "
        + (
            "**inside** the interval the published procedure determines."
            if checks["d064_retained_count"]["published_count_inside_the_interval"]
            else f"**outside** it, by "
            f"{checks['d064_retained_count']['distance_to_interval']:,} records."
        ),
        "",
        "## The host rule's counting unit",
        "",
        "The rule keeps sequences \"whose assigned taxonomic classification was found within a "
        "prokaryotic host at least twice\". The subject of the count is the classification and "
        "not the record — the developers' own Figure S1B puts 89.5% of their retained records "
        "at an unknown host kingdom, which a per-record reading cannot produce (D-058). What "
        "one *finding* is, the published sentence does not say, so three readings are computed "
        f"and `{result['host_unit']['primary']}` was declared primary before any of them was:",
        "",
        "| unit | records removed (literal reading) | retained interval |",
        "|---|---|---|",
    ]
    for unit, block in result["host_unit"]["sensitivity"].items():
        lit = block["per_reading"]["literal"]
        mark = " **(primary)**" if block["primary"] else ""
        lines.append(
            f"| `{unit}`{mark} | {lit['records_removed']:,} | "
            f"{lit['retained_lower']:,} to {lit['retained_upper']:,} |"
        )
    d058 = checks["d058_host_kingdom_unknown"]
    lines += [
        "",
        f"D-058's check: Evo 1 puts {d058['published']:,} of {d058['published_of']:,} retained "
        f"records ({d058['published_share']:.1%}) at an unknown host kingdom. Re-executed, the "
        "share of surviving classifications' records carrying no host prediction is "
        + (
            f"**{d058['re_executed_share_estimate']:.1%}**"
            if d058["re_executed_share_estimate"] is not None
            else "not computable"
        )
        + f". {d058['estimate_is_over']}",
        "",
    ]
    if d058["exact_on_evo2"]:
        ex = d058["exact_on_evo2"]
        lines += [
            f"On Evo 2's release the same quantity is **exact**, because its records carry "
            f"accessions: {ex['records']:,} released records joined to the input, "
            f"{ex['share_without_a_host_prediction']:.1%} of them with no host prediction of "
            "their own. Evo 1's release carries no accession, so this is the only exact "
            "measurement of the phenomenon available.",
            "",
        ]
    lines += [
        "## Forward and converse, reported apart",
        "",
        "### Evo 1's release, compared per lineage",
        "",
        f"Evo 1's release carries a lineage and no accession, so its records cannot be "
        f"identified individually; the comparison is per lineage, over "
        f"{evo1['released_records']:,} released records in {evo1['released_lineages']:,} "
        "lineages. Each direction is scored against the bound that favours the developer.",
        "",
        f"- **forward** — released records the published rules remove: "
        f"**{evo1['forward']['records']:,}** across {evo1['forward']['lineages']:,} lineages, "
        "counted as the excess over the most the procedure could have retained, and split by "
        f"which rule the excess belongs to: "
        f"{evo1['forward']['records_removed_by_a_record_level_rule']:,} to a record-level rule, "
        f"{evo1['forward']['records_in_excess_of_the_votu_bound']:,} to the deduplication rule "
        "(a lineage released in more copies than it has vOTUs to represent).",
        f"- **converse** — records the rule retains that the release does not carry: "
        f"{evo1['converse']['shortfall_in_released_lineages']:,} short in "
        f"{evo1['converse']['lineages_short']:,} lineages it does carry, plus "
        f"{evo1['converse']['records_in_lineages_absent_entirely']:,} in "
        f"{evo1['converse']['lineages_absent_entirely']:,} lineages it carries none of.",
        f"- released lineages the staged input does not contain at all: "
        f"{evo1['released_lineages_absent_from_the_input']['lineages']:,} lineages, "
        f"{evo1['released_lineages_absent_from_the_input']['records']:,} records — counted in "
        "neither direction.",
        "",
    ]
    if evo1["forward"]["detail"]:
        lines += [
            "| excess records | attributed to | rule | cause | lineage |",
            "|---|---|---|---|---|",
        ]
        for f in evo1["forward"]["detail"][:15]:
            lines.append(
                f"| {f['excess']:,} | {f['attributed_to']} | `{f['rule']}` | "
                f"`{f['cause']}` | `{f['lineage_tag']}` |"
            )
        lines.append("")
    lines += [
        "### Evo 2's release, compared per record",
        "",
    ]
    if not evo2["run"]:
        lines += [evo2["why"], ""]
    else:
        votu = evo2["votu_level"]
        lines += [
            evo2["provenance"],
            "",
            f"{evo2['released_accessions']:,} released accessions, of which "
            f"{evo2['released_accessions_joined_to_the_input']:,} join to the staged input and "
            f"{evo2['released_accessions_absent_from_the_input']:,} do not.",
            "",
            f"- **forward** — released records the published rule removes: "
            f"**{evo2['forward']['records']:,}**, exactly, per record.",
            f"- **converse** — vOTUs the rule retains that contributed no released record: "
            f"{evo2['converse']['votus']:,}. {evo2['converse']['why_not_per_record']}",
            "",
            "#### The vOTU rule, at vOTU level",
            "",
            votu["verdict"],
            "",
            "| released records per vOTU | vOTUs |",
            "|---|---|",
        ]
        for n, v in votu["histogram"].items():
            lines.append(f"| {n} | {v:,} |")
        lines += [
            "",
            f"Unit: **{votu['unit']}**. This is not a record-level conformance rate and must "
            f"not be quoted as one. {votu['mixed_classification_votus_excluded']:,} vOTUs whose "
            "high-confidence records disagree about taxonomy are excluded from this comparison, "
            "because whether the chain retains them depends on the undetermined representative.",
            "",
        ]
    lines += [
        "## The spread across readings",
        "",
        spread["why_it_is_measurable_here"],
        "",
        "| quantity | literal | charitable | strict | spread |",
        "|---|---|---|---|---|",
    ]
    for label, key in (
        ("records removed (record level)", "records_removed_record_level"),
        ("classifications surviving", "classifications_surviving"),
        ("retained, lower bound", "retained_lower_bound"),
        ("retained, upper bound", "retained_upper_bound"),
        ("Evo 1 forward failures", "evo1_forward_records"),
        ("Evo 2 forward failures", "evo2_forward_records"),
    ):
        block = spread[key]
        row = block["per_reading"]

        def fmt(v: Any) -> str:
            return f"{v:,}" if isinstance(v, int) else "—"

        lines.append(
            f"| {label} | {fmt(row.get('literal'))} | {fmt(row.get('charitable'))} | "
            f"{fmt(row.get('strict'))} | {fmt(block['spread'])} |"
        )
    lines += [
        "",
        "## Causes",
        "",
        "Assigned from the taxonomy frozen in `amazebio.conformance.CAUSES` before any of this "
        "was counted. No cause was added after the numbers were in view.",
        "",
    ]
    for cause, text in result["causes"].items():
        lines.append(f"- **`{cause}`** — {text}")
    shapes = result.get("accession_shapes") or {}
    lines += [
        "",
        "## Provenance, and the qualification on every row-level count",
        "",
        result["provenance"]["input_is_the_real_input"],
        "",
        result["provenance"]["which_v4"],
        "",
        result["provenance"]["weaker_end_governs"],
        "",
    ]
    if shapes:
        lines += [
            f"IMG/VR ships two accession shapes. {shapes['non_packable_accessions']:,} records "
            "carry the giant-virus MAG form, which does not pack into the integer key the joins "
            "use and is carried under a verified-injective hash instead. They are the records a "
            "eukaryote-virus filter is judged on, so losing them from a join would have been the "
            "worst available place to lose records.",
            "",
        ]
    lines += [
        "Headline numbers here are not cleared for external circulation until A3.3 has "
        "reproduced them by a second method and X3.1's disclosure window has been honoured.",
        "",
    ]
    return "\n".join(lines)


def _load(path: str, outdir: Path) -> dict[str, Any]:
    """Read an artefact from a local path or straight out of the store."""
    if path.startswith("s3://"):
        from amazebio import objectstore

        bucket, key = objectstore.split_uri(path)
        body = objectstore.client().get_object(Bucket=bucket, Key=key)["Body"].read()
        local = outdir / Path(key).name
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(body)
        return json.loads(body)
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"no artefact at {p}")
    return json.loads(p.read_text())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--input-scan",
        action="append",
        default=None,
        help="input scan artefact, local or s3://; repeatable. Default: both staged releases.",
    )
    ap.add_argument(
        "--release-scan",
        default="artifacts/a7-1/opengenome-stage2/scan-opengenome-stage2.json",
        help="A7.1's scan of Evo 1's released component, local or s3://",
    )
    ap.add_argument("--outdir", default="artifacts/a7-2")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    scans = args.input_scan or [
        f"artifacts/a7-2/{date}/input-scan-{date}.json" for date in INPUT_RELEASE
    ]

    with run(
        "A7.2",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-close.json",
    ) as m:
        m.parameter("policy_prefix", POLICY_PREFIX)
        m.parameter("primary_host_unit", cf.PRIMARY_HOST_UNIT.value)
        m.parameter("evo1_table_s3_records", EVO1_TABLE_S3_RECORDS)
        m.parameter("evo1_unknown_host_records", EVO1_UNKNOWN_HOST_RECORDS)
        m.note(
            "Forward and converse are reported separately and never summed; the vOTU rule is "
            "compared at vOTU level only."
        )
        release_scan = _load(args.release_scan, outdir)
        if args.release_scan.startswith("s3://"):
            m.input_url(args.release_scan, role="release-scan", verified=False)
        else:
            m.input_file(Path(args.release_scan), role="release-scan")
        for spec in sorted(SPECS.glob(f"{POLICY_PREFIX}*.yaml")):
            m.input_file(spec, role="policy-spec")

        released = release_scan["tag_counts"]
        per_input: dict[str, Any] = {}
        for path in scans:
            scan = _load(path, outdir)
            if not path.startswith("s3://"):
                m.input_file(Path(path), role="input-scan")
            else:
                m.input_url(path, role="input-scan", verified=False)
            result = analyse(scan, released)
            per_input[scan["release"]] = result
            sub = outdir / scan["release"]
            sub.mkdir(parents=True, exist_ok=True)
            out = sub / f"close-{scan['release']}.json"
            out.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
            m.output_file(out, role="conformance-close")
            md = sub / f"close-{scan['release']}.md"
            md.write_text(summarise(result))
            m.output_file(md, role="summary")
            print(md.read_text())
            head = result["per_reading"]["literal"]
            m.note(
                f"{scan['release']}: coverage {head['rule_coverage_record_level']} at record "
                f"level; retained interval {head['votu_interval']['lower']:,} to "
                f"{head['votu_interval']['upper']:,}; Evo 1 forward "
                f"{head['evo1']['forward']['records']:,}; Evo 2 forward "
                f"{head['evo2']['forward']['records'] if head['evo2']['run'] else 'not run'}."
            )

        if len(per_input) > 1:
            cross = cross_release(per_input)
            out = outdir / "close-v4-vs-v41.json"
            out.write_text(json.dumps(cross, indent=2, sort_keys=True) + "\n")
            m.output_file(out, role="release-comparison")
            print(json.dumps(cross, indent=2, sort_keys=True))
    return 0


def cross_release(per_input: dict[str, Any]) -> dict[str, Any]:
    """Whether the v4/v4.1 ambiguity changes any conformance number.

    A1.7 found every aggregate identical between the two releases while their md5s differ,
    because v4.1 corrects a few rows of the sequence-information table in place (D-063, D-064).
    Every count in A7.2 is row-level, so the ambiguity is material here in a way it was not
    there — and the only honest way to say whether it mattered is to run both and diff.
    """
    dates = sorted(per_input)
    out: dict[str, Any] = {
        "releases": dates,
        "why": (
            "Evo 1 cites 'IMG/VR v4' and the publisher ships a v4 and a v4.1 erratum; which "
            "one the procedure ran on is not determinable from Evo 1's words (D-052, D-063). "
            "A1.7 staged both for that reason and found every aggregate identical. A7.2's "
            "counts are row-level, so this is where the ambiguity either bites or does not."
        ),
        "per_reading": {},
    }
    readings = per_input[dates[0]]["per_reading"]
    for reading in readings:
        blocks = [per_input[d]["per_reading"][reading] for d in dates]
        out["per_reading"][reading] = {
            "records_removed": [b["record_level"]["records_removed"] for b in blocks],
            "retained_lower": [b["votu_interval"]["lower"] for b in blocks],
            "retained_upper": [b["votu_interval"]["upper"] for b in blocks],
            "evo1_forward": [b["evo1"]["forward"]["records"] for b in blocks],
            "evo2_forward": [
                b["evo2"]["forward"]["records"] if b["evo2"]["run"] else None for b in blocks
            ],
        }
    identical = all(
        len(set(v)) == 1
        for block in out["per_reading"].values()
        for v in block.values()
        if None not in v
    )
    out["identical_across_releases"] = identical
    out["verdict"] = (
        "Every conformance number is identical across v4 and v4.1, so the ambiguity in Evo 1's "
        "citation is immaterial to this result. Both are still reported."
        if identical
        else "The two releases give different conformance numbers. Every claim must name the "
        "release it came from, and neither can stand for 'IMG/VR v4'."
    )
    return out


if __name__ == "__main__":
    raise SystemExit(main())

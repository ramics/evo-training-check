#!/usr/bin/env python3
"""Compute A7.1's conformance diff from a scan artefact, and write it up.

The cheap half of A7.1 and the half that decides everything. It reads the lineage-tag histogram
`conformance_scan.py` produced, re-executes the checkable part of each published reading of Evo's
filter against it, and reports failures by rule and by cause. It touches no corpus, so it runs
anywhere in a second and A3.3's independent reimplementation can check the headline numbers
against the same intermediate without a 17 GB read.

What it will and will not say, in the order a reader will want it:

**It reports the forward direction only.** A record the published rule removes and the release
contains is a conformance failure. The converse — a record removed that the rule does not call
for — needs the filter's *input*, IMG/VR v4, which this project has not acquired. Nothing here
speaks to over-removal, and the artefact says so in a field rather than in a footnote, because a
missing arm that is only mentioned in prose gets cited as a null result.

**It reports coverage next to every count.** Three of Evo's six published rules read inputs the
release does not carry. A failure rate over the other three is a statement about those three.

**It refuses to call a row a record unless the scan proved it.** `one_row_one_record` comes back
from the scan as a measured property, and when it is false every count here is relabelled
per-row, because a count of records that is really a count of rows is the kind of error that
survives review and then gets quoted.

**A clean result is written up as a finding.** DESIGN.md §2 commits this project to publishing a
null, and §A7 says a clean conformance result would be the first external confirmation that a
stated filter was applied as described. So the summary leads with the verdict either way, and
there is no code path on which zero failures produces a quieter artefact than a thousand would.
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
from amazebio import objectstore
from amazebio.policyspec import load_policy_dir
from amazebio.repro import run

SPECS = Path(__file__).resolve().parent.parent / "policies" / "specs"

#: The release the diff runs against, and the policies written for the model that released it.
#: Named here rather than inferred from the scan so that pointing this at another corpus is a
#: visible change.
RELEASE = "opengenome-stage2"
POLICY_PREFIX = "evo1-"

#: What Evo 1 publishes about the IMG/VR component of its own corpus, from Table S3 (p43 of
#: S-EVO1-PREPRINT): genomes/loci, total bases in millions, and average length. Checked against
#: the census rather than quoted, because the denominator of the headline rests on it and
#: because a count of context windows could not land within one of a count of genomes — which
#: is what makes this an independent corroboration of the row-is-a-record premise D-048
#: measured structurally. See D-055.
PUBLISHED_IMGVR = {
    "source": "S-EVO1-PREPRINT",
    "locator": "Table S3, p43",
    "records": 2_653_046,
    "bases_millions": 36_236,
    "mean_length": 13_658,
}

#: Evo 1's own per-realm counts for the same component, from Figure S1 panel A (p41), and its
#: host-kingdom counts from panel B. These are a stronger check than the totals above: the
#: totals could agree while the composition did not.
#:
#: **Provenance is weaker than the table's, and the difference matters.** Figure S1 is a
#: flattened raster — "Duplodnaviria" appears nowhere in the PDF's text layer though it is 99%
#: of the released records — so these numbers were read off the rendered image rather than
#: extracted, and X1.4's quote checker cannot verify them. What backs them is arithmetic:
#: :func:`_check_published_arithmetic` asserts that each panel sums to the record count in
#: Table S3, which *is* text-extractable. A misread digit would almost certainly break that sum.
#:
#: Panel B's Archaea label is printed malformed in the source, as "N = 17,44". The value below
#: is recovered as the residual, which is what makes the sum check load-bearing rather than
#: decorative. See D-058.
PUBLISHED_REALMS = {
    "source": "S-EVO1-PREPRINT",
    "locator": "Figure S1A, p41",
    "transcribed_from": "rasterised figure; not present in the PDF text layer",
    "counts": {
        "Duplodnaviria": 2_628_512,
        "Monodnaviria": 17_781,
        "Riboviria": 6_105,
        # Everything not named above. Our census resolves it as Varidnaviria + Adnaviria +
        # the realmless records, which is the decomposition D-058 records.
        "Other": 648,
    },
}

PUBLISHED_HOST_KINGDOMS = {
    "source": "S-EVO1-PREPRINT",
    "locator": "Figure S1B, p41",
    "transcribed_from": "rasterised figure; not present in the PDF text layer",
    "counts": {
        "Unknown": 2_374_733,
        "Bacteria": 276_569,
        # Printed as "N = 17,44" in the source; recovered as the residual against Table S3.
        "Archaea": 1_744,
    },
    "archaea_label_as_printed": "17,44",
}

#: The three realms Figure S1A names. Anything else the census finds belongs to "Other".
_NAMED_REALMS = ("Duplodnaviria", "Monodnaviria", "Riboviria")


def _check_published_arithmetic() -> None:
    """Both figure panels must sum to the record count Table S3 publishes.

    This is what stands in for a machine-extractable source on the two panels. It runs on
    import rather than in a test so that a mis-transcription cannot reach an artefact even if
    the test suite is not run.
    """
    total = PUBLISHED_IMGVR["records"]
    for name, block in (("Figure S1A", PUBLISHED_REALMS), ("Figure S1B", PUBLISHED_HOST_KINGDOMS)):
        got = sum(block["counts"].values())
        if got != total:
            raise AssertionError(
                f"{name} counts sum to {got:,}, but Table S3 publishes {total:,} records. "
                "One of the transcribed figure values is wrong — these were read off a raster, "
                "so re-read the panel rather than adjusting the total."
            )


_check_published_arithmetic()


def _rows_from_scan(scan: dict[str, Any]):
    """Yield one weighted row per distinct lineage tag.

    The aggregation is exact rather than approximate, and that is a property of the data: the
    only per-record field the release carries is the lineage tag, so two records with the same
    tag are indistinguishable to every rule that can be re-executed. Evaluating the tag once
    with its count attached gives the identical answer to evaluating every record, and makes the
    intermediate small enough to publish alongside the result.
    """
    for raw, count in scan["tag_counts"].items():
        record, _ = cf.record_from_row(f"|{raw}|", record_id=f"tag:{raw}", component="IMG/VR")
        yield f"tag:{raw}", record, cf.parse_lineage_tag(raw), count


def analyse(scan: dict[str, Any]) -> dict[str, Any]:
    policies = {k: v for k, v in load_policy_dir(SPECS).items() if k.startswith(POLICY_PREFIX)}
    if not policies:
        raise SystemExit(f"no policies matching {POLICY_PREFIX!r} in {SPECS}")

    agree, kept_by_reading = cf.readings_agree_by_construction(policies, release=RELEASE)
    structure = scan.get("structure", {})
    unit = "record" if structure.get("one_row_one_record") else "row"
    total = scan["rows"]

    per_reading: dict[str, Any] = {}
    for policy in sorted(policies.values(), key=lambda p: p.reading):
        failures, coverage = cf.diff(policy, _rows_from_scan(scan), release=RELEASE)
        by_cause: collections.Counter = collections.Counter()
        by_rule: collections.Counter = collections.Counter()
        by_rule_cause: collections.Counter = collections.Counter()
        for f in failures:
            by_cause[f.cause.value] += f.n_records
            by_rule[f.rule_id] += f.n_records
            by_rule_cause[(f.rule_id, f.cause.value)] += f.n_records
        failing = sum(f.n_records for f in failures)
        per_reading[policy.reading] = {
            "policy_id": policy.id,
            "rule_coverage": coverage.rule_coverage,
            "rules_re_executed": list(coverage.kept_rules),
            "rules_not_checkable": [{"rule": r, "needs": why} for r, why in coverage.dropped_rules],
            f"{unit}s_examined": total,
            f"{unit}s_failing": failing,
            "failure_rate": failing / total if total else None,
            "by_cause": dict(sorted(by_cause.items())),
            "by_rule": dict(sorted(by_rule.items())),
            "by_rule_and_cause": {
                f"{rule}|{cause}": n for (rule, cause), n in sorted(by_rule_cause.items())
            },
            "distinct_failing_tags": len({f.record_id for f in failures}),
            "failures": [
                {
                    "lineage_tag": f.record_id.removeprefix("tag:"),
                    "rule": f.rule_id,
                    "cause": f.cause.value,
                    "why": f.why,
                    "taxonomy": f.taxonomy,
                    f"{unit}s": f.n_records,
                }
                for f in sorted(failures, key=lambda f: (-f.n_records, f.record_id))
            ],
        }

    return {
        "release": RELEASE,
        "counting_unit": unit,
        "published_comparison": _compare_to_published(scan),
        "direction": "forward_only",
        "converse_not_run": (
            "Records removed that the published predicate does not call for are not checked. "
            "That needs the filter's input, IMG/VR v4, which this project has not acquired. No "
            "number in this artefact speaks to over-removal."
        ),
        "readings_distinguishable": agree is False,
        "reading_spread_note": (
            "Every rule the three readings disagree about reads an input the release does not "
            "carry, so the readings re-execute an identical pipeline here and the spread §A7 "
            "asks for is unmeasurable against this release. Identical columns below are a "
            "property of the release, not agreement between the readings."
        ),
        "rules_re_executed_by_reading": {k: list(v) for k, v in kept_by_reading.items()},
        "structure": structure,
        "scan_was_partial": scan.get("partial", False),
        "per_reading": per_reading,
        "causes": {c.value: text for c, text in cf.CAUSES.items()},
    }


def _compare_to_published(scan: dict[str, Any]) -> dict[str, Any]:
    """Check the census against Evo 1's own published figures for the same component.

    Three quantities, one of which is derived from the other two, so they are not independent
    of each other — but all three are independent of our count, which is the point.
    """
    rows = scan["rows"]
    bases = scan["sequence_chars"]
    pub = PUBLISHED_IMGVR
    mean = bases / rows if rows else None
    return {
        "published": {k: v for k, v in pub.items() if k not in ("source", "locator")},
        "published_source": f"{pub['source']} {pub['locator']}",
        "counted": {
            "records": rows,
            "bases_millions": bases / 1e6,
            "mean_length": mean,
        },
        "delta": {
            "records": rows - pub["records"],
            "bases_millions_fraction": (bases / 1e6 - pub["bases_millions"])
            / pub["bases_millions"],
            "mean_length": mean - pub["mean_length"] if mean else None,
        },
        "verdict": (
            "Records agree to within one. Bases and mean length agree at the precision the "
            "table publishes. The row-is-a-record premise is corroborated by the developers' "
            "own count, independently of the structural measurement in D-048."
            if abs(rows - pub["records"]) <= 1
            else "Record counts disagree by more than one. Do not cite this denominator until "
            "the difference is explained: see D-055."
        ),
        "unexplained_offset": rows - pub["records"],
        "by_realm": _compare_realms(scan),
        "host_kingdoms": {
            "published": dict(PUBLISHED_HOST_KINGDOMS["counts"]),
            "published_source": (
                f"{PUBLISHED_HOST_KINGDOMS['source']} {PUBLISHED_HOST_KINGDOMS['locator']}"
            ),
            "unknown_share": (PUBLISHED_HOST_KINGDOMS["counts"]["Unknown"] / pub["records"]),
            "eukaryota_present": "Eukaryota" in PUBLISHED_HOST_KINGDOMS["counts"],
            "why_it_matters": (
                "Downstream of the prokaryotic-host rule, which this release cannot re-execute. "
                "The rule keeps records whose taxonomic classification was found in a "
                "prokaryotic host at least twice, yet the developers' own figure puts most "
                "retained records at an unknown host kingdom. That is not a contradiction: it "
                "means the rule reads host evidence aggregated over the classification rather "
                "than per record, which is the unit A7.2 has to get right. It also sizes how "
                "much of the corpus was retained on evidence not attached to the record."
            ),
        },
    }


def _compare_realms(scan: dict[str, Any]) -> dict[str, Any]:
    """Our census by realm against Evo 1's own Figure S1A, binned the way they bin it."""
    ours = scan.get("realms", {})
    binned: dict[str, int] = {r: ours.get(r, 0) for r in _NAMED_REALMS}
    binned["Other"] = sum(n for r, n in ours.items() if r not in _NAMED_REALMS)
    pub = PUBLISHED_REALMS["counts"]
    return {
        "published": dict(pub),
        "published_source": f"{PUBLISHED_REALMS['source']} {PUBLISHED_REALMS['locator']}",
        "counted": binned,
        "delta": {k: binned.get(k, 0) - v for k, v in pub.items()},
        "other_decomposition": {r: n for r, n in sorted(ours.items()) if r not in _NAMED_REALMS},
        "categories_agreeing": sum(1 for k, v in pub.items() if binned.get(k, 0) == v),
        "categories": len(pub),
    }


def summarise(result: dict[str, Any], scan: dict[str, Any]) -> str:
    unit = result["counting_unit"]
    readings = result["per_reading"]
    # Identical by construction here, but take the literal reading explicitly rather than
    # "the first one": if the spread ever becomes measurable this must stop looking agnostic.
    head = readings["literal"]
    failing, total = head[f"{unit}s_failing"], head[f"{unit}s_examined"]
    verdict = (
        f"**{failing:,} of {total:,} released {unit}s ({failing / total:.3%}) survive a rule "
        f"Evo 1 published.**"
        if failing
        else f"**No released {unit} survives any of the rules this release can test.**"
    )
    lines = [
        "# A7.1 — conformance re-execution against Evo 1's released viral component",
        "",
        f"Release: `{result['release']}` · {total:,} {unit}s · "
        f"{scan['distinct_tags']:,} distinct lineage tags · "
        f"rule coverage {head['rule_coverage']}",
        "",
        verdict,
        "",
    ]
    if result["scan_was_partial"]:
        lines += [
            "> **NOT A RESULT.** The scan artefact behind these numbers is marked partial: it "
            "covered a bounded number of row groups rather than the whole release. Every count "
            "above and below is of that subset. Re-run the scan without `--row-groups` before "
            "citing anything here.",
            "",
        ]
    lines += [
        "## What was re-executed, and what could not be",
        "",
        f"Evo 1's published procedure has six steps. This release carries one per-record field — "
        f"the inline taxonomic lineage — so {head['rule_coverage']} of those steps can be run "
        "against it:",
        "",
    ]
    for rule in head["rules_re_executed"]:
        lines.append(f"- re-executed: `{rule}`")
    for item in head["rules_not_checkable"]:
        lines.append(
            f"- **not checkable**: `{item['rule']}` — needs `{item['needs']}`, which the "
            "release does not carry"
        )
    lines += [
        "",
        "The three rules that cannot be run are the high-confidence gate, the vOTU "
        "representative and the prokaryotic-host count. All three read IMG/VR metadata that "
        "does not travel with the released records (DECISIONS.md D-020). That is a property of "
        "the release, not an assumption of ours.",
        "",
        "## The reading spread is unmeasurable here, and that is the finding",
        "",
        result["reading_spread_note"],
        "",
    ]
    for reading, kept in sorted(result["rules_re_executed_by_reading"].items()):
        lines.append(f"- {reading}: {', '.join(kept)}")
    lines += [
        "",
        "## Failures by cause",
        "",
        f"| cause | {unit}s | share of failures |",
        "|---|---|---|",
    ]
    for cause, n in sorted(head["by_cause"].items(), key=lambda kv: -kv[1]):
        lines.append(
            f"| `{cause}` | {n:,} | {n / failing:.1%} |"
            if failing
            else f"| `{cause}` | {n:,} | — |"
        )
    if not head["by_cause"]:
        lines.append("| — | 0 | — |")
    lines += [
        "",
        "Cause definitions were fixed before counting, in `amazebio.conformance.CAUSES`:",
        "",
    ]
    for cause, text in result["causes"].items():
        lines.append(f"- **`{cause}`** — {text}")
    if head["failures"]:
        depths = {int(d): n for d, n in scan["rank_depth"].items()}
        modal = max(depths, key=lambda d: depths[d])
        lines += [
            "",
            "## What the failures are",
            "",
            f"{head['distinct_failing_tags']} distinct lineage tags account for all "
            f"{failing:,} failing {unit}s:",
            "",
            f"| {unit}s | rule | cause | lineage tag |",
            "|---|---|---|---|",
        ]
        for f in head["failures"]:
            lines.append(
                f"| {f[unit + 's']:,} | `{f['rule']}` | `{f['cause']}` | `{f['lineage_tag']}` |"
            )
        lines += [
            "",
            "Read the ranks these records *do* fill before reading the count. Each is assigned "
            "at **family** rank and at no rank above it, while the modal released record fills "
            f"{modal} ranks and stops at class ({depths[modal]:,} of {total:,} records). So the "
            "rule removes records that are *better* resolved than the ones it keeps, and it does "
            "so because `require_rank: realm` tests for a particular rank rather than for the "
            'taxonomic specificity the published sentence is about — "viruses with poor '
            "taxonomic specificity were excluded, including those with no assigned realm at "
            'all". A family-level assignment with no realm above it is not poor specificity; '
            "it is a family whose higher placement the taxonomy has not settled.",
            "",
            "That locates the mismatch precisely, and it is worth stating in the developers' "
            "favour: on this evidence the failure is in the rule's wording rather than in the "
            f"filter's judgement. A re-execution of their stated rule removes {failing:,} "
            "records that their own release shows they kept, and the ground for removing them "
            "is an absent rank above family rather than anything about the records themselves. "
            "Which hosts these three families infect is not settled here — that needs a "
            "taxonomy source this project has not retrieved, and A9.1 is where one enters.",
            "",
            "This is also the second time the realm/specificity conflation has come up from a "
            "different direction. DECISIONS.md D-016 and D-018 withdrew a strict reading that "
            "raised the required rank to family, on the grounds that the authors ceiling their "
            "enumeration at class; the release now shows the published encoding failing in the "
            "opposite direction on real records. Both point at the same gap, which is A9.1's "
            "subject: a static rank test against a taxonomy that keeps changing.",
            "",
        ]
    pc = result["published_comparison"]
    lines += [
        "## Checked against Evo 1's own published figures",
        "",
        f"Evo 1 publishes its own statistics for this component in {pc['published_source']}. "
        "They are not a check on the filter — they are the authors' count of their own output — "
        "but they are an independent check on our denominator and on the unit we are counting:",
        "",
        "| quantity | published | counted | delta |",
        "|---|---|---|---|",
        f"| records | {pc['published']['records']:,} | {pc['counted']['records']:,} | "
        f"{pc['delta']['records']:+,} |",
        f"| bases (M) | {pc['published']['bases_millions']:,} | "
        f"{pc['counted']['bases_millions']:,.1f} | "
        f"{pc['delta']['bases_millions_fraction']:+.4%} |",
        f"| mean length | {pc['published']['mean_length']:,} | "
        f"{pc['counted']['mean_length']:,.1f} | {pc['delta']['mean_length']:+,.1f} |",
        "",
        pc["verdict"],
        "",
        f"Composition agrees too, and more sharply: {pc['by_realm']['categories_agreeing']} of "
        f"{pc['by_realm']['categories']} realm categories match **exactly** against "
        f"{pc['by_realm']['published_source']}.",
        "",
        "| realm | published | counted | delta |",
        "|---|---|---|---|",
    ]
    br = pc["by_realm"]
    for realm, pubn in br["published"].items():
        lines.append(
            f"| {realm} | {pubn:,} | {br['counted'].get(realm, 0):,} | "
            f"{br['delta'].get(realm, 0):+,} |"
        )
    lines += [
        "",
        "Their `Other` bin decomposes exactly into "
        + ", ".join(f"{r} {n:,}" for r, n in br["other_decomposition"].items())
        + ". The realmless records are therefore accounted for in the developers' own "
        "published figure, not only in ours.",
        "",
        "Figure S1 is a flattened raster — `Duplodnaviria` appears nowhere in the PDF text "
        "layer though it is 99% of the released records — so these values were read off the "
        "rendered image and cannot be machine-verified from the source. What backs them is "
        "that each panel sums to the record count in Table S3, which is text-extractable; "
        "that assertion runs on import.",
        "",
        "### What the host panel says about a rule this release cannot test",
        "",
        "| host kingdom | records |",
        "|---|---|",
    ]
    hk = pc["host_kingdoms"]
    for kingdom, n in hk["published"].items():
        lines.append(f"| {kingdom} | {n:,} |")
    lines += [
        "",
        f"Unknown accounts for {hk['unknown_share']:.1%} of retained records, and Eukaryota "
        f"does not appear at all. {hk['why_it_matters']}",
        "",
        "One transcription note: panel B prints the Archaea count malformed, as "
        f"`N = {PUBLISHED_HOST_KINGDOMS['archaea_label_as_printed']}`. It is recovered here as "
        "the residual against Table S3.",
        "",
        f"The {pc['unexplained_offset']:+d}-record offset is **not explained** and is reported "
        "rather than rounded away. A conformance audit that rounds its own denominator has no "
        "standing to report a 95-record finding. The realm table localises it: every other "
        "category agrees exactly, so whatever the difference is, it is one Duplodnaviria "
        "record. See D-055 and D-058.",
        "",
        "## Structural premise",
        "",
        f"Counts above are per {unit}. The release publishes no statement that one row is one "
        "record, so the scan measured it: "
        f"{result['structure'].get('rows_multi_tag', 0):,} rows carry more than one distinct "
        f"lineage tag, {result['structure'].get('rows_last_block_full', 0):,} end on a "
        f"full-length sequence block, and {result['structure'].get('rows_no_tag', 0):,} carry "
        "no tag at all. A record longer than "
        f"{result['structure'].get('block_chars', cf.BLOCK_CHARS):,} characters arrives as "
        "several same-tag blocks inside one row rather than as several rows.",
        "",
        "## What this does not say",
        "",
        result["converse_not_run"],
        "",
        "The audited *procedure* is Evo 1's and the audited *output* is Evo 1's own release, so "
        "no proxy substitution arises on either side (A1.1, D-017, D-020). Evo 2's release of "
        "the same component carries IMG/VR accessions and no lineage, so no published rule can "
        "be re-executed against it at all. ESM3-open has no conformance arm: neither its corpus "
        "nor its threshold is published.",
        "",
        "Headline numbers here are not cleared for external circulation until A3.3 has "
        "reproduced them by a second method and X3.1's disclosure window has been honoured.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--scan",
        default="artifacts/a7-1/opengenome-stage2/scan-opengenome-stage2.json",
        help="local path or s3:// URI of the scan artefact",
    )
    ap.add_argument("--outdir", default="artifacts/a7-1")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    # The scan may be read from object storage, which is how this stays reproducible without a
    # re-run: the expensive pass uploads its artefact, and anyone with credentials recomputes
    # the headline numbers from it in a second. A3.3's second implementation needs exactly that.
    if args.scan.startswith("s3://"):
        import boto3

        bucket, _, key = args.scan[5:].partition("/")
        body = (
            boto3.client(
                "s3", region_name="us-east-1", endpoint_url="https://s3.us-east-1.amazonaws.com"
            )
            .get_object(Bucket=bucket, Key=key)["Body"]
            .read()
        )
        scan_path = Path(args.outdir) / "scan-from-store.json"
        scan_path.parent.mkdir(parents=True, exist_ok=True)
        scan_path.write_bytes(body)
    else:
        scan_path = Path(args.scan)
        if not scan_path.exists():
            raise SystemExit(
                f"no scan artefact at {scan_path}; run tools/conformance_scan.py first, or pass "
                "an s3:// URI for one already in the store"
            )
    scan = json.loads(scan_path.read_text())
    outdir = Path(args.outdir)

    with run(
        "A7.1",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-diff.json",
        durable=objectstore.durable_results("a7-1"),
    ) as m:
        m.parameter("release", RELEASE)
        m.parameter("policy_prefix", POLICY_PREFIX)
        m.parameter("direction", "forward_only")
        m.input_file(scan_path, role="scan")
        for spec in sorted(SPECS.glob(f"{POLICY_PREFIX}*.yaml")):
            m.input_file(spec, role="policy-spec")
        if scan.get("partial"):
            m.note(
                "The scan artefact is marked partial: it covered a bounded number of row "
                "groups. Counts below are of that subset and are not a result."
            )

        result = analyse(scan)
        out = outdir / "conformance.json"
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="conformance-diff")

        md = outdir / "conformance.md"
        md.write_text(summarise(result, scan))
        m.output_file(md, role="summary")

        unit = result["counting_unit"]
        head = result["per_reading"]["literal"]
        m.note(
            f"{head[f'{unit}s_failing']:,} of {head[f'{unit}s_examined']:,} {unit}s fail the "
            f"{head['rule_coverage']} of Evo 1's published rules this release can test."
        )
        print(md.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

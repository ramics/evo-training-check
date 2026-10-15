#!/usr/bin/env python3
"""Measure what taxonomy has not labelled, and the ceiling that puts on the filter — A4.1.

`DESIGN.md` §A4: a taxonomy-based filter can only act on sequence taxonomy has labelled, so
what share of the corpus is outside its reach in principle? This pass answers it against the
corpus's own annotation fields, per component, and expresses each published rule's reach as a
ceiling. `amazebio.unfilterable` holds the definitions; this reads the bytes.

**What it reads, and why those.**

*The filter's input*, primarily: both staged IMG/VR releases, streamed in byte shards. Five
fields per record — the taxonomic classification, the host prediction, the confidence label, the
vOTU and the classification method — which between them are every field any published Evo rule
reads (`amazebio.policyspec.RULE_INPUTS`). This is a fresh pass over the publisher's tables
rather than a re-reading of A7.2's scan, because a ceiling is a claim about the input population
and A4.1 should be able to state it from the primary file.

*The released corpora*, from the pinned scans A7.1 and A7.2 already published to object storage.
Those two passes read 28 GB of Parquet and gzipped FASTA to produce the lineage histograms this
needs, the histograms are complete partitions of their components, and re-reading the same bytes
to recompute the same tallies would buy nothing a cross-check does not already give (D-082). The
sums are verified against each scan's own independently counted record total before use.

**What it deliberately does not measure.** Components the filter was never applied to get a row
and no fill: their share of the corpus is A4.3's, and "unlabelled" and "out of policy scope" are
different findings with different remedies. ESM3-open's rule reads a similarity threshold rather
than a taxonomy, so no taxonomic ceiling binds it and none is reported.

    python3 tools/unfilterable.py                      # artifacts/a4-1/
    python3 tools/unfilterable.py --release 2022-12-20 # one IMG/VR release
    python3 tools/unfilterable.py --print              # and to stdout, for reading
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import imgvr, objectstore, policyspec, scope, unfilterable
from amazebio.repro import run

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "policies" / "specs"
OUTDIR = Path("artifacts/a4-1")

#: The pinned scans of the two *released* corpora, by the component they describe. Each carries
#: a classification histogram and its own independently counted record total, and the totals are
#: what makes the histogram safe to reuse: a partition that sums to the component's record count
#: cannot be missing a record (D-082).
RELEASED_SCANS = {
    "opengenome/stage2": {
        "key": "results/a7-1/scan-opengenome-stage2.json",
        "histogram": "tag_counts",
        "total": "rows",
        "corpus": "opengenome",
        "label": "Evo 1 released viral component",
        "task": "A7.1",
    },
    "opengenome2/imgvr": {
        "key": "results/a7-2/evo2-accessions.json",
        "histogram": None,  # the release carries no lineage at all; see `_evo2_row`.
        "total": "headers",
        "corpus": "opengenome2",
        "label": "Evo 2 released viral component",
        "task": "A7.2",
    },
}

#: Where the labels Evo 2's release does not carry can be recovered from: A7.2 joined every
#: released accession back to IMG/VR and kept the classification histogram of the join.
EVO2_JOIN_SCAN = "results/a7-2/input-scan-2022-12-20.json"

#: The blank-field label this pass emits, following `imgvr.host_domain`'s convention that a
#: parenthesised label is an absence. `amazebio.unfilterable.absence_reason` reads that
#: convention, so the two must agree and neither may invent a third spelling.
EMPTY = "(empty)"

#: The one confidence value Evo 1's first published rule keeps, quoted from the spec it is
#: declared in rather than spelled again here: `keep-high-confidence` names it, and the
#: population every later rule sees is what that rule kept.
HIGH_CONFIDENCE = "High-confidence"


# --------------------------------------------------------------------------------------
# The primary pass over the filter's input
# --------------------------------------------------------------------------------------


def _scan_shard(bucket: str, key: str, start: int, end: int, header: list[str]) -> dict[str, Any]:
    """Tally one byte shard of a sequence-information table. Runs in a subprocess.

    Returns counters rather than rows: every figure A4.1 reports is a count over a small
    vocabulary — 6,221 distinct classifications in the whole of v4.1 — so nothing here needs the
    per-record arrays A7.2's scan had to ship back for its joins.
    """
    idx = {role: header.index(name) for role, name in imgvr.SEQ_COLUMNS.items()}
    method_col = header.index("Taxonomic classification method")
    width = len(header)
    classes: collections.Counter = collections.Counter()
    hosts: collections.Counter = collections.Counter()
    confidence: collections.Counter = collections.Counter()
    votu: collections.Counter = collections.Counter()
    method: collections.Counter = collections.Counter()
    # The same two tallies again over the high-confidence subset, because Evo's confidence gate
    # runs *first* and the denylists only ever see what it kept. A ceiling measured over the
    # whole table answers a question about the database; the denylist's own ceiling is over the
    # population it was handed, and the two differ.
    classes_hc: collections.Counter = collections.Counter()
    hosts_hc: collections.Counter = collections.Counter()
    votu_hc: collections.Counter = collections.Counter()
    method_hc: collections.Counter = collections.Counter()
    rows = 0
    rows_hc = 0
    malformed = 0
    client = objectstore.client()
    for line in objectstore.shard_lines(client, bucket, key, start, end, skip_header=(start == 0)):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != width:
            # Counted, never dropped silently: a row the publisher emitted that does not fit its
            # own header is what D-063's erratum note leads one to expect, and a row this pass
            # cannot read is a record whose labelling it cannot claim either way.
            malformed += 1
            continue
        rows += 1
        classification = fields[idx["classification"]].strip()
        domain = imgvr.host_domain(fields[idx["host"]])
        conf = fields[idx["confidence"]].strip()
        votu_value = fields[idx["votu"]].strip() or EMPTY
        classes[classification] += 1
        hosts[domain] += 1
        confidence[conf or EMPTY] += 1
        votu[votu_value] += 1
        classification_method = fields[method_col].strip() or EMPTY
        method[classification_method] += 1
        if conf == HIGH_CONFIDENCE:
            rows_hc += 1
            classes_hc[classification] += 1
            hosts_hc[domain] += 1
            votu_hc[votu_value] += 1
            method_hc[classification_method] += 1
    return {
        "classes": dict(classes),
        "classes_hc": dict(classes_hc),
        "hosts": dict(hosts),
        "hosts_hc": dict(hosts_hc),
        "confidence": dict(confidence),
        # Presence only. The vOTU vocabulary is 8.6 million values and the rule that reads it
        # deduplicates by identity, which A7.2 measured; what a ceiling needs is whether the
        # field is there at all.
        "votu": {EMPTY: votu.get(EMPTY, 0), "assigned": sum(votu.values()) - votu.get(EMPTY, 0)},
        "votu_hc": {
            EMPTY: votu_hc.get(EMPTY, 0),
            "assigned": sum(votu_hc.values()) - votu_hc.get(EMPTY, 0),
        },
        "method": dict(method),
        "method_hc": dict(method_hc),
        "rows": rows,
        "rows_hc": rows_hc,
        "malformed": malformed,
    }


def _merge(shards: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"rows": 0, "rows_hc": 0, "malformed": 0}
    fields = (
        "classes",
        "classes_hc",
        "hosts",
        "hosts_hc",
        "confidence",
        "votu",
        "votu_hc",
        "method",
        "method_hc",
    )
    for field in fields:
        merged: collections.Counter = collections.Counter()
        for shard in shards:
            merged.update(shard[field])
        out[field] = dict(merged)
    for shard in shards:
        out["rows"] += shard["rows"]
        out["rows_hc"] += shard["rows_hc"]
        out["malformed"] += shard["malformed"]
    return out


def scan_release(bucket: str, prefix: str, date: str, *, workers: int, progress: float) -> dict:
    """The five annotation fields of one IMG/VR release's sequence-information table."""
    client = objectstore.client()
    files = [f for f in imgvr.conformance_inputs(date) if f.role == "sequence_information"]
    (f,) = [x for x in files if not x.high_confidence]
    key = f"{prefix}/imgvr/{date}/{f.name}" if prefix else f"imgvr/{date}/{f.name}"
    size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if size != f.bytes:
        raise SystemExit(
            f"{key}: staged object is {size:,} bytes, the publisher's pin says {f.bytes:,}. "
            "Refusing to measure an object that is not the pinned one."
        )
    header = _read_header(client, bucket, key)
    shards = objectstore.byte_shards(size, max(workers * 8, 1))
    print(f"[a4-1] {date}: {len(shards)} shards over {len(header)} columns", flush=True)
    done: list[dict[str, Any]] = []
    started = last = time.time()
    with ProcessPoolExecutor(max_workers=min(workers, len(shards))) as pool:
        futures = [pool.submit(_scan_shard, bucket, key, s, e, header) for s, e in shards]
        for fut in as_completed(futures):
            done.append(fut.result())
            if time.time() - last >= progress:
                last = time.time()
                print(
                    f"[a4-1] {date}: {len(done)}/{len(shards)} shards  "
                    f"{time.time() - started:,.0f}s",
                    flush=True,
                )
    print(f"[a4-1] {date}: done in {time.time() - started:,.0f}s", flush=True)
    merged = _merge(done)
    merged["file"] = {"name": f.name, "key": key, "bytes": f.bytes, "md5": f.md5}
    merged["seconds"] = round(time.time() - started, 1)
    return merged


def _boto3_version() -> str:
    """The one third-party library every byte of this measurement passes through."""
    import boto3

    return str(boto3.__version__)


def _read_header(client: Any, bucket: str, key: str) -> list[str]:
    body = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-65535")["Body"].read()
    return body.split(b"\n", 1)[0].decode("utf-8").rstrip("\r").split("\t")


# --------------------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------------------


def _fills(scanned: dict[str, Any], *, high_confidence: bool = False) -> dict[str, Any]:
    """The labelling of one scanned release: ranks, and one fill per non-taxonomic field.

    `high_confidence` measures the subset Evo's first rule keeps instead of the whole table.
    Both are reported, because they answer different questions: the full table is what the
    database holds, and the high-confidence subset is what every rule after the gate was
    handed. Each is checked against its own independently counted row total.
    """
    suffix = "_hc" if high_confidence else ""
    counted = scanned["rows_hc" if high_confidence else "rows"]
    ranks = unfilterable.rank_fill(scanned["classes" + suffix])
    if ranks.total != counted:
        raise SystemExit(
            f"classification histogram sums to {ranks.total:,} and the pass counted "
            f"{counted:,} rows. A histogram that is not a partition cannot carry a share."
        )
    host = unfilterable.host_fill(scanned["hosts" + suffix])
    confidence = {HIGH_CONFIDENCE: counted} if high_confidence else scanned["confidence"]
    attributes = {
        "confidence": unfilterable.field_fill("Confidence", confidence),
        "vOTU": unfilterable.field_fill("vOTU", scanned["votu" + suffix]),
    }
    method = unfilterable.field_fill("Taxonomic classification method", scanned["method" + suffix])
    # Every fill must be a fill *of this population*. Without this, a field tallied over the
    # whole table and reported beside a subset reads as a present count larger than the
    # population it describes — which happened, and is exactly the kind of number a reviewer
    # finds first.
    for fill in (host, method, *attributes.values()):
        if fill.total != counted:
            raise SystemExit(
                f"{fill.field!r} was tallied over {fill.total:,} records and this population "
                f"holds {counted:,}. A fill must be measured over the population it is "
                "reported beside."
            )
    return {"ranks": ranks, "host": host, "attributes": attributes, "method": method}


#: The two populations each release is measured over. The second is not a corpus component: it
#: is the output of the filter's own first rule, and it is here because the rules that name a
#: hazard run after it. Reporting only the first invites the obvious objection and does not
#: answer it; reporting only the second would measure a population the publisher never shipped.
POPULATIONS = (
    ("all records", False, "the filter's input"),
    (
        "high-confidence subset",
        True,
        "the filter's input, after its own confidence gate",
    ),
)


def input_rows(scans: dict[str, dict[str, Any]], policies: dict[str, policyspec.Policy]) -> list:
    """One row per IMG/VR release and population: what every Evo rule is actually applied to."""
    rows = []
    for date, scanned in sorted(scans.items()):
        for population, hc, role in POPULATIONS:
            rows += _rows_for(date, scanned, policies, population=population, hc=hc, role=role)
    return rows


def _rows_for(
    date: str,
    scanned: dict[str, Any],
    policies: dict[str, policyspec.Policy],
    *,
    population: str,
    hc: bool,
    role: str,
) -> list[dict[str, Any]]:
    rows = []
    fills = _fills(scanned, high_confidence=hc)
    release = imgvr.release_on(date)
    for pid in sorted(policies):
        policy = policies[pid]
        cell = scope.classify(policy, "imgvr", family="evo")
        rows.append(
            unfilterable.ComponentFill(
                component=f"imgvr/{date}",
                corpus=f"IMG/VR {release.version}",
                role=role,
                scope_state=cell.state,
                labelling=unfilterable.LABELLED,
                ranks=fills["ranks"],
                fields=(
                    fills["host"],
                    fills["attributes"]["confidence"],
                    fills["attributes"]["vOTU"],
                    fills["method"],
                ),
                ceilings=unfilterable.policy_ceilings(
                    policy,
                    ranks=fills["ranks"],
                    host=fills["host"],
                    attributes=fills["attributes"],
                ),
                note=(
                    f"{policy.model}, {policy.reading} reading, over {population}. "
                    f"Measured from {scanned['file']['name']}, md5 "
                    f"{scanned['file']['md5']}, {scanned['malformed']} malformed rows."
                ),
            ).to_dict()
            | {
                "policy_id": pid,
                "reading": policy.reading,
                "release": date,
                "population": population,
            }
        )
    return rows


def released_rows(client: Any, bucket: str, prefix: str) -> list[dict[str, Any]]:
    """One row per released viral component, from the pinned scan that already counted it."""
    rows: list[dict[str, Any]] = []
    for component, meta in sorted(RELEASED_SCANS.items()):
        key = f"{prefix}/{meta['key']}" if prefix else meta["key"]
        doc = json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
        total = int(doc[str(meta["total"])])
        if meta["histogram"] is None:
            rows.append(_evo2_row(client, bucket, prefix, component, meta, doc, total))
            continue
        histogram = doc[str(meta["histogram"])]
        ranks = unfilterable.rank_fill(histogram)
        if ranks.total != total:
            raise SystemExit(
                f"{key}: histogram sums to {ranks.total:,}, scan counted {total:,} records. "
                "A4.1 will not take a share from a histogram that is not a partition."
            )
        rows.append(
            unfilterable.ComponentFill(
                component=component,
                corpus=str(meta["corpus"]),
                role="the filter's released output",
                scope_state=scope.IN_SCOPE,
                labelling=unfilterable.LABELLED,
                ranks=ranks,
                note=(
                    f"Lineage histogram from {meta['task']}'s pinned scan `{meta['key']}`, "
                    f"verified as a partition of its own count of {total:,} records (D-082). "
                    "Post-filter: a ceiling on what the filter could reach is a claim about "
                    "its input, and this row is here to be compared with one, not to carry one."
                ),
            ).to_dict()
            | {"source_scan": meta["key"], "task": meta["task"]}
        )
    return rows


def _evo2_row(
    client: Any,
    bucket: str,
    prefix: str,
    component: str,
    meta: dict[str, Any],
    doc: dict[str, Any],
    total: int,
) -> dict[str, Any]:
    """Evo 2's released viral component: no annotation field at all, and labels recoverable.

    The distinction `NOT_ANNOTATED` exists for exactly this row. 2,957,495 FASTA headers carry
    an IMG/VR accession and no lineage, so the *release* says nothing taxonomic — but every one
    of its distinct accessions resolves in IMG/VR, so the labels exist and the component is not
    unclassified. Calling it 100% unclassified would be the easiest wrong number in this task.
    """
    join_key = f"{prefix}/{EVO2_JOIN_SCAN}" if prefix else EVO2_JOIN_SCAN
    join = json.loads(client.get_object(Bucket=bucket, Key=join_key)["Body"].read())
    recovered = unfilterable.rank_fill(join["evo2"]["released_by_classification"])
    found = int(join["evo2"]["released_accessions_found_in_imgvr"])
    absent = int(join["evo2"]["released_accessions_absent_from_imgvr"])
    if recovered.total != found:
        raise SystemExit(
            f"{join_key}: the recovered histogram sums to {recovered.total:,} and the join "
            f"matched {found:,} accessions. Refusing to report a share over a partial join."
        )
    return unfilterable.ComponentFill(
        component=component,
        corpus=str(meta["corpus"]),
        role="the filter's released output",
        scope_state=scope.IN_SCOPE,
        labelling=unfilterable.NOT_ANNOTATED,
        ranks=recovered,
        note=(
            f"The release carries no taxonomic field: {total:,} FASTA headers, "
            f"`carries_lineage` false in {meta['task']}'s pinned scan. The ranks reported here "
            f"are *recovered* by {meta['task']}'s join of {found:,} distinct released "
            f"accessions back to IMG/VR v4.1, with {absent} absent from it (D-073). So this "
            "component is unannotated rather than unclassified, and the two are not the same "
            "finding: nothing about the labels was lost, only the release's record of them."
        ),
    ).to_dict() | {
        "source_scan": meta["key"],
        "task": meta["task"],
        "release_headers": total,
        "distinct_accessions_joined": found,
        "accessions_absent_from_imgvr": absent,
    }


def _why_no_ceiling(labelling: str) -> str:
    """The sentence each no-ceiling row carries, by the reason there is no ceiling."""
    if labelling == unfilterable.NOT_TAXONOMY_DEPENDENT:
        return (
            ". No labelling ceiling is reported: this policy's rules read a similarity "
            "threshold rather than a taxonomy, so taxonomic coverage does not bound them."
        )
    if labelling == unfilterable.NOT_MEASURED:
        return (
            ". Reached by this reading's scope and by none of its rules, so there is no rule "
            "here for a labelling ceiling to bound."
        )
    return (
        ". Its share of the corpus is A4.3's figure, not re-derived here; what matters for "
        "A4.1 is that it is a scope finding and not a labelling one."
    )


def out_of_scope_rows(policies: dict[str, policyspec.Policy]) -> list[dict[str, Any]]:
    """Every other component each policy declares a view on, with no fill and no ceiling.

    The task's fourth step in as many words: unlabelled apart from labelled-but-out-of-scope.
    The component names come from `scope.COMPONENT_LABELS`, which is the repo's one declared
    join between a spec's vocabulary and a composition's, so this enumerates the same components
    A4.3 does without re-deriving its shares — which stay A4.3's number to quote.
    """
    rows: list[dict[str, Any]] = []
    for pid in sorted(policies):
        policy = policies[pid]
        family = "evo" if pid.startswith("evo") else "esm3"
        for label, names in sorted(scope.COMPONENT_LABELS[family].items()):
            if family == "evo" and label == "IMG/VR":
                continue  # measured above, from the primary table
            cell = scope.classify(policy, names[0], family=family)
            taxonomic = any(
                policyspec.RULE_INPUTS[rule.kind] == "taxonomy" for rule in policy.rules
            )
            if not taxonomic:
                labelling = unfilterable.NOT_TAXONOMY_DEPENDENT
            elif cell.never_a_candidate:
                labelling = unfilterable.OUT_OF_POLICY_SCOPE
            else:
                # A wildcard-scope reading reaches this component and no rule of it does, so
                # there is nothing here for a labelling ceiling to bound. Saying "out of scope"
                # would contradict the scope table (D-014); saying nothing would lose the row.
                labelling = unfilterable.NOT_MEASURED
            rows.append(
                unfilterable.ComponentFill(
                    component=label,
                    corpus=policy.model,
                    role="other component of the same corpus",
                    scope_state=cell.state,
                    labelling=labelling,
                    note=(cell.why + _why_no_ceiling(labelling)),
                ).to_dict()
                | {"policy_id": pid, "reading": policy.reading}
            )
    return rows


# --------------------------------------------------------------------------------------
# The ceiling, and the caveat it needs
# --------------------------------------------------------------------------------------


def ceiling_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The headline: the lowest discriminating share among each reading's taxonomy rules.

    Lowest rather than mean. The question is what the filter can tell apart, and a procedure is
    as blind as its blindest discriminating step: a denylist that can see 6% of the records does
    not become more capable because a realm-level rule beside it can see 97%.
    """
    out = []
    for row in rows:
        taxonomy = [
            c
            for c in row["ceilings"]
            if c["channel"] == "taxonomy" and c["fires_on"] != "label_absent" and c["binds"]
        ]
        if not taxonomy:
            continue
        binding = min(taxonomy, key=lambda c: (c["discriminating_share"] or 0.0))
        out.append(
            {
                "component": row["component"],
                "population": row["population"],
                "policy_id": row["policy_id"],
                "reading": row["reading"],
                "records": row["ranks"]["total"],
                "binding_rule": binding["rule"],
                "binding_rank": binding["key"],
                "ceiling": binding["discriminating_share"],
                "records_the_rule_can_read": binding["discriminating"],
                "rules_summarised": [c["rule"] for c in taxonomy],
            }
        )
    return out


def backstop(scans: dict[str, dict[str, Any]], policies: dict[str, policyspec.Policy]) -> list:
    """How much of the under-labelled population a shallowness rule removes anyway.

    The caveat without which the ceiling overstates the case. Evo 1's unspecificity rule removes
    records with no realm and those "only assigned up to the level of" eight named taxa, so a
    share of the records the family denylist cannot see are removed by a rule that reads their
    shallowness instead. This counts them. It is not a survival figure — that is A3.2's, over a
    population this pass does not compute.
    """
    out = []
    for date, scanned in sorted(scans.items()):
        histogram = scanned["classes"]
        total = scanned["rows"]
        for pid in sorted(policies):
            policy = policies[pid]
            for rule in policy.rules:
                if rule.kind != "remove_if_unspecific":
                    continue
                stop = rule.params.get("stop_taxa") or []
                if isinstance(stop, policyspec.Unspecified):
                    continue
                terminal = unfilterable.terminal_taxa(histogram, stop)
                no_realm = unfilterable.rank_fill(histogram).unlabelled("realm")
                caught = sum(terminal.values()) + no_realm
                out.append(
                    {
                        "release": date,
                        "policy_id": pid,
                        "rule": rule.id,
                        "records": total,
                        "no_realm": no_realm,
                        "terminal_in_stop_taxa": terminal,
                        "removed_for_shallowness": caught,
                        "share": caught / total if total else None,
                    }
                )
    return out


def caveats() -> list[dict[str, str]]:
    """What a figure from this artefact may not be used to say.

    Carried in the artefact rather than only in the write-up, so a number cannot be quoted out
    of it without them (the pattern A4.3 established).
    """
    return [
        {
            "id": "ceiling-is-not-survival",
            "text": (
                "A ceiling is what a rule could discriminate on, not what survived. The two "
                "differ because rules compose: a record the family denylist cannot see may be "
                "removed by the confidence gate, the vOTU deduplication or the unspecificity "
                "rule before the denylist would have run. What survived is A3.2's, by route."
            ),
        },
        {
            "id": "absence-fires-rules-too",
            "text": (
                "Evo's pipeline is mostly keep-listing, so absence of a label is itself grounds "
                "for removal. Every rule here therefore carries two shares: decidable, which is "
                "1.0 for a rule that fires on absence, and discriminating, which is the ceiling. "
                "Quoting the ceiling as the share of the corpus the filter 'cannot touch' would "
                "be wrong in the filter's favour and in its disfavour at once."
            ),
        },
        {
            "id": "unlabelled-is-not-out-of-scope",
            "text": (
                "Unlabelled is a limit of taxonomy and out-of-scope is a limit of the policy. "
                "The remedies differ — better annotation against wider scope — so the two are "
                "separate columns here and must not be summed. The out-of-scope shares are "
                "A4.3's."
            ),
        },
        {
            "id": "not-annotated-is-not-unclassified",
            "text": (
                "Evo 2's released viral component carries no lineage field at all, and every "
                "one of its distinct accessions resolves in IMG/VR. It is unannotated, not "
                "unclassified; its ranks here are recovered by join (D-073)."
            ),
        },
        {
            "id": "esm3-reads-no-taxonomy",
            "text": (
                "ESM3-open's published rule is a sequence-identity threshold against a seed "
                "set, so no taxonomic labelling ceiling binds it. The rows for its components "
                "say that rather than reporting a zero, which would read as a finding."
            ),
        },
        {
            "id": "released-histograms-are-reused",
            "text": (
                "The two released-corpus rows are computed from A7.1's and A7.2's pinned scans "
                "rather than from a fresh pass over 28 GB. Each histogram is verified to sum to "
                "that scan's own independently counted record total before a share is taken "
                "from it (D-082)."
            ),
        },
    ]


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def build(bucket: str, prefix: str, dates: list[str], *, workers: int, progress: float) -> dict:
    client = objectstore.client()
    policies = policyspec.load_policy_dir(SPECS)
    evo = {k: v for k, v in policies.items() if k.startswith("evo")}
    scans = {
        date: scan_release(bucket, prefix, date, workers=workers, progress=progress)
        for date in dates
    }
    rows = input_rows(scans, evo)
    return {
        "task": "A4.1",
        "definition": {
            "labelled_at_rank": (
                "A record is labelled at rank r when its own classification field assigns a "
                "name to r. Measured per rank, not per record: a lineage can fill four ranks of "
                "eight, and a rule keyed on family cannot see it while a rule keyed on realm can."
            ),
            "unclassified": (
                "A record filling no rank at all. Reported apart from the per-rank shares "
                "because it is the only figure that needs no rank named with it."
            ),
            "absent_field": (
                "A non-taxonomic field counts as absent when it is empty, bare separators, or "
                "content this audit cannot parse — each under its own reason, never pooled."
            ),
            "ceiling": (
                "The discriminating share: records where a rule's own criterion can be "
                "evaluated against a label that is present. A rule firing on absence is "
                "decidable everywhere and discriminates nowhere, and both are reported."
            ),
            "states": {
                unfilterable.LABELLED: "the component carries the field and it is filled",
                unfilterable.ABSENT: "the component carries the field and it is empty",
                unfilterable.NOT_ANNOTATED: "the component carries no such field",
                unfilterable.OUT_OF_POLICY_SCOPE: "the filter was never applied here (A4.3)",
                unfilterable.NOT_TAXONOMY_DEPENDENT: "the policy's rules read no taxonomy",
            },
        },
        "components": rows + released_rows(client, bucket, prefix) + out_of_scope_rows(policies),
        "ceiling": ceiling_summary(rows),
        "shallowness_backstop": backstop(scans, evo),
        "scans": {
            date: {
                "file": s["file"],
                "rows": s["rows"],
                "malformed_rows": s["malformed"],
                "seconds": s["seconds"],
                "classification_method": s["method"],
            }
            for date, s in sorted(scans.items())
        },
        "caveats": caveats(),
    }


def summarise(doc: dict[str, Any]) -> str:
    lines: list[str] = ["# A4.1 — the unfilterable fraction", ""]
    lines += ["## Labelling, per rank, of the filter's input", ""]
    seen = set()
    for row in doc["components"]:
        if row["ranks"] is None or not row.get("population"):
            continue
        name = (row["component"], row["population"])
        if name in seen:
            continue
        seen.add(name)
        r = row["ranks"]
        lines += [
            f"**{row['component']}**, {row['population']} — {r['total']:,} records, "
            f"{r['unclassified_records']:,} ({r['unclassified_share']:.2%}) filling no rank.",
            "",
            "| rank | labelled | share |",
            "|---|---|---|",
        ]
        for rank, cell in r["per_rank"].items():
            lines.append(f"| {rank} | {cell['labelled']:,} | {cell['labelled_share']:.2%} |")
        lines.append("")
    lines += [
        "## The ceiling, per reading",
        "",
        "| component | population | reading | binding rule | rank | ceiling |",
        "|---|---|---|---|---|---|",
    ]
    for c in doc["ceiling"]:
        lines.append(
            f"| {c['component']} | {c['population']} | {c['reading']} | `{c['binding_rule']}` | "
            f"{c['binding_rank']} | {c['ceiling']:.2%} |"
        )
    lines += ["", "## Released components", ""]
    for row in doc["components"]:
        if row["role"] != "the filter's released output":
            continue
        r = row["ranks"]
        lines.append(
            f"- **{row['component']}** ({row['labelling']}): {r['total']:,} records, family "
            f"labelled on {r['per_rank']['family']['labelled_share']:.2%}."
        )
    lines += ["", "## Caveats", ""]
    lines += [f"- **{c['id']}** — {c['text']}" for c in doc["caveats"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", choices=sorted(imgvr.RELEASES), action="append")
    ap.add_argument("--s3-uri", default=None)
    ap.add_argument("--outdir", default=str(OUTDIR))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--progress-seconds", type=float, default=30.0)
    ap.add_argument("--print", dest="show", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    import os

    uri = args.s3_uri or os.environ.get("AMAZEBIO_S3_URI")
    if not uri or not uri.startswith("s3://"):
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI, as s3://bucket/prefix")
    bucket, prefix = objectstore.split_uri(uri)
    dates = args.release or sorted(imgvr.RELEASES)
    outdir = Path(args.outdir)

    with run("A4.1", seed=None, outdir=outdir, allow_dirty=args.allow_dirty) as m:
        m.parameter("releases", dates)
        m.parameter("source", uri)
        m.parameter("workers", args.workers)
        m.parameter("boto3_version", _boto3_version())
        m.note(
            "The ceiling is the discriminating share: where a rule's criterion can be evaluated "
            "against a label that is present. A rule firing on an absent label is decidable "
            "everywhere and discriminates nowhere, and both shares are reported per rule."
        )
        m.note(
            "Released-corpus rows reuse A7.1's and A7.2's pinned scans, each verified as a "
            "partition of that scan's own record count before a share is taken (D-082)."
        )
        for date in dates:
            f = next(
                x
                for x in imgvr.conformance_inputs(date)
                if x.role == "sequence_information" and not x.high_confidence
            )
            key = f"{prefix}/imgvr/{date}/{f.name}" if prefix else f"imgvr/{date}/{f.name}"
            m.input_url(
                f"s3://{bucket}/{key}",
                role=f"sequence_information/{date}",
                bytes=f.bytes,
                checksum=f.md5,
                checksum_type="md5",
                verified=False,
            )
        for meta in RELEASED_SCANS.values():
            key = f"{prefix}/{meta['key']}" if prefix else str(meta["key"])
            m.input_url(f"s3://{bucket}/{key}", role=f"scan/{meta['task']}", verified=False)

        doc = build(bucket, prefix, dates, workers=args.workers, progress=args.progress_seconds)
        outdir.mkdir(parents=True, exist_ok=True)
        out = outdir / "unfilterable.json"
        out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="unfilterable")
        md = outdir / "unfilterable.md"
        md.write_text(summarise(doc))
        m.output_file(md, role="summary")

    if args.show:
        sys.stdout.write(summarise(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

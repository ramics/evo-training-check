#!/usr/bin/env python3
"""Which detected Evo 2 records carry a label naming a denylisted group — X1.9, §7.

    pixi run -e dev python tools/denylist_label_records.py --outdir artifacts/x1-9

X1.8 pinned the label arm's three references and regenerated its family table. It deliberately
did **not** regenerate the per-record table: that needs a pass over the 1.9 GB staged label
table, and the session was told not to start one. So the per-record figures stayed as a
hand-built copy, produced once from inputs named in prose — which `AGENTS.md` says is not a
result yet. This is that pass, as its own task rather than as a widening of either A7.5 (which
consumes the record list) or X1.8 (which is done).

**The join, in one sentence.** Of the records the audit detected in Evo 2's released viral
component, which ones does IMG/VR's own metadata label as belonging to one of the nineteen virus
families the published filter names for removal?

Three inputs, all pinned, none of them a corpus of sequence:

* **The detected records.** A2.1's published per-hit tables for Pfam on `opengenome2`, read by
  key. All three readings of the filter are read and required to agree on the record set: on
  this component every taxonomy rule is unresolvable, so the three *must* agree, and a
  disagreement would mean one of the tables is not what it says it is.
* **The labels.** `IMGVR_all_Sequence_information-high_confidence.tsv` for the 2022-09-20
  release, staged in object storage, verified against **the publisher's own md5** — recorded in
  `policies/sources.json` as `S-IMGVR-V4-SEQINFO-2022-09-20` — as it streams. The digest comes
  from that entry rather than from a literal here, so there is one place to keep in step.
* **The nineteen groups.** The `remove-denylisted-families` rule of
  `policies/specs/evo1-literal.yaml`, this project's machine-verified transcription of the
  published procedure. The rule is not reimplemented: it is *executed*, through
  `policyspec.decide`, which is the same code path A1.4's corpus-scale evaluator uses. A record
  is a denylisted-label record when the published rule, given that record's label, removes it.

**What the table is and is not.** A row says IMG/VR labelled this record as a member of a family
the filter's own policy names, and the audit detected a viral protein family on it. It does not
say the record is dangerous, and it does not say the label is right: `Taxonomic classification
method` travels with every row so a reader can see which rows rest on a geNomad prediction
rather than on a reference match. Two ceilings travel with the count and are in the output:
only a small minority of IMG/VR records carry a family label at all, so this is a floor over
that window and never a census; and the label table covers the high-confidence subset, so a
detected record absent from it is unlabelled here rather than unlabelled in IMG/VR.

No sequence is read and no residues are written (D-103). The pass is ~1.9 GB of in-region
reading, which is free inside `us-east-1` and metered outside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, objectstore, policyspec, repro
from amazebio.conformance import RANKS, parse_lineage_tag

TASK = "X1.9"
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "artifacts" / "x1-9"

#: The source register entry whose md5 the staged label table is checked against, and where the
#: table is held. Both are read from the entry rather than written out here.
SOURCE_ID = "S-IMGVR-V4-SEQINFO-2022-09-20"
SOURCES = REPO / "policies" / "sources.json"

#: The spec whose rule names the groups, and the rule's id. The rule is executed, not restated.
SPEC = REPO / "policies" / "specs" / "evo1-literal.yaml"
RULE = "remove-denylisted-families"

#: The published per-hit tables the detected record set comes from. One per reading of the
#: filter, all three required to agree: on this component every taxonomy rule is unresolvable,
#: so nothing is removed under any reading and the three record sets are the same set.
READINGS = ("evo1-literal", "evo1-strict", "evo1-charitable")
RELEASE = "opengenome2"
COMPONENT = "IMG/VR"


def detections_key(reading: str) -> str:
    return f"corpora/results/a2-1/detections-pfam-{reading}-{RELEASE}.jsonl"


#: Columns of the label table this reads, by header name rather than by position: the file has
#: nineteen columns and one of its headers contains a comma and a parenthesis, so a positional
#: read would be a silent dependency on column order.
UVIG = "UVIG"
LINEAGE = "Taxonomic classification"
METHOD = "Taxonomic classification method"

COLUMNS = ("record_id", "denylisted_family", "rule_outcome", "label_method", "taxonomy")


class Refusal(SystemExit):
    """Exit with a reason. Every refusal here is a disagreement between two pinned inputs."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"refused: {reason}")


# --------------------------------------------------------------------------------------
# The three inputs
# --------------------------------------------------------------------------------------


def source_entry() -> dict[str, Any]:
    """The register's entry for the label table: its publisher digest and where it is held."""
    register = json.loads(SOURCES.read_text())
    entries = [s for s in register["sources"] if s.get("id") == SOURCE_ID]
    if len(entries) != 1:
        raise Refusal(
            f"{SOURCES} holds {len(entries)} entries for {SOURCE_ID}; the digest this pass "
            "verifies against has no other source"
        )
    entry = entries[0]
    for field in ("md5", "held_at"):
        if not entry.get(field):
            raise Refusal(f"{SOURCE_ID} states no {field}, so the staged table cannot be pinned")
    return entry


def denylist_rule() -> policyspec.Rule:
    """The published procedure's own denylist rule, as an executable predicate."""
    policy = policyspec.load_policy(SPEC)
    for rule in policy.rules:
        if rule.id == RULE:
            if rule.kind != "remove_if_taxon_in" or rule.params.get("rank") != "family":
                raise Refusal(
                    f"{SPEC}: {RULE} is {rule.kind!r} at rank {rule.params.get('rank')!r}, not a "
                    "family-rank taxon rule. This pass joins on the family label and cannot "
                    "execute another shape of rule."
                )
            return rule
    raise Refusal(f"{SPEC}: no rule {RULE!r}. The group list has no other source.")


def detected_records(client: Any) -> tuple[set[str], list[dict[str, Any]]]:
    """The detected Evo 2 record set, and the published tables it was read from.

    Each reading's table is read whole and its digest recorded. The three sets must be equal:
    every taxonomy rule is unresolvable against this component (A1.4's finding), so the readings
    cannot differ here, and if they do then one table is not the table it claims to be.
    """
    sets: dict[str, set[str]] = {}
    tables: list[dict[str, Any]] = []
    for reading in READINGS:
        key = detections_key(reading)
        body = client.get_object(Bucket=corpora.BUCKET, Key=key)["Body"].read()
        ids = {json.loads(line)["record_id"] for line in body.decode().splitlines() if line.strip()}
        sets[reading] = ids
        tables.append(
            {
                "key": key,
                "sha256": hashlib.sha256(body).hexdigest(),
                "records": len(ids),
                "reading": reading,
            }
        )
    first = sets[READINGS[0]]
    disagreeing = [r for r, ids in sets.items() if ids != first]
    if disagreeing:
        raise Refusal(
            f"the three readings disagree about which records carry a detection on {RELEASE} "
            f"({', '.join(disagreeing)} differ from {READINGS[0]}). Every taxonomy rule is "
            "unresolvable against this component, so they cannot differ; one of these tables is "
            "not what it says it is."
        )
    return first, tables


# --------------------------------------------------------------------------------------
# The pass
# --------------------------------------------------------------------------------------


def stream_labels(
    client: Any,
    *,
    entry: dict[str, Any],
    wanted: set[str],
    progress_every: int = 400 << 20,
) -> tuple[dict[str, tuple[str, str]], dict[str, Any]]:
    """`{record_id: (lineage, method)}` for the wanted records, and the pass's own counts.

    The whole object is read because its md5 is the pin and a digest over part of a file pins
    nothing. There is no index into it either, so one sequential pass is the floor.
    """
    bucket, key = objectstore.split_uri(entry["held_at"])
    live = int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
    if entry.get("bytes") and live != int(entry["bytes"]):
        raise Refusal(
            f"{key}: staged object is {live} bytes, {SOURCE_ID} says {entry['bytes']}. A staged "
            "object of a different length is a different release."
        )
    obj = corpora.RangedObject(client, bucket=bucket, key=key, size=live)
    reader = obj.buffered()

    digest = hashlib.md5(usedforsecurity=False)
    found: dict[str, tuple[str, str]] = {}
    header: list[str] | None = None
    columns: dict[str, int] = {}
    rows = 0
    tail = b""
    read = 0
    announced = 0
    started = time.time()
    while True:
        block = reader.read(1 << 22)
        if not block:
            break
        digest.update(block)
        read += len(block)
        data = tail + block
        lines = data.split(b"\n")
        tail = lines.pop()
        for raw in lines:
            if not raw:
                continue
            fields = raw.decode("utf-8", "replace").rstrip("\r").split("\t")
            if header is None:
                header = fields
                for name in (UVIG, LINEAGE, METHOD):
                    if name not in header:
                        raise Refusal(
                            f"{key}: the table has no {name!r} column (it has "
                            f"{len(header)}: {header[:3]}…). The columns are read by name "
                            "because a positional read is a silent dependency on their order."
                        )
                columns = {name: header.index(name) for name in (UVIG, LINEAGE, METHOD)}
                continue
            rows += 1
            record_id = fields[columns[UVIG]]
            if record_id in wanted:
                found[record_id] = (
                    fields[columns[LINEAGE]] if columns[LINEAGE] < len(fields) else "",
                    fields[columns[METHOD]] if columns[METHOD] < len(fields) else "",
                )
        if read - announced >= progress_every:
            announced = read
            print(
                f"  {read / 1e9:.2f}/{live / 1e9:.2f} GB, {rows:,} rows, "
                f"{len(found):,}/{len(wanted):,} wanted found, "
                f"{(time.time() - started) / 60:.1f} min",
                flush=True,
            )
    if tail.strip() and header is not None:
        fields = tail.decode("utf-8", "replace").rstrip("\r").split("\t")
        rows += 1
        if fields[columns[UVIG]] in wanted:
            found[fields[columns[UVIG]]] = (
                fields[columns[LINEAGE]] if columns[LINEAGE] < len(fields) else "",
                fields[columns[METHOD]] if columns[METHOD] < len(fields) else "",
            )

    md5 = digest.hexdigest()
    if md5 != entry["md5"]:
        raise Refusal(
            f"{key}: md5 {md5} is not the publisher's {entry['md5']} for {SOURCE_ID}. Every "
            "label in this table would be relative to a release nobody pinned."
        )
    return found, {
        "bytes_read": read,
        "object_bytes": live,
        "md5_verified": True,
        "rows": rows,
        "seconds": round(time.time() - started, 1),
    }


def build(client: Any) -> dict[str, Any]:
    entry = source_entry()
    rule = denylist_rule()
    groups = list(rule.params["names"])
    detected, tables = detected_records(client)
    print(f"{len(detected):,} detected records on {RELEASE}; reading the label table", flush=True)

    labels, pass_counts = stream_labels(client, entry=entry, wanted=detected)

    rows: list[dict[str, Any]] = []
    labelled_at_family = 0
    for record_id in sorted(labels):
        lineage, method = labels[record_id]
        tag = parse_lineage_tag(lineage)
        if tag.taxonomy.get("family"):
            labelled_at_family += 1
        record = policyspec.Record(id=record_id, component=COMPONENT, taxonomy=dict(tag.taxonomy))
        # The published rule, executed rather than restated: a denylisted-label record is one
        # this rule removes when it is given that record's own label.
        decision = policyspec.decide(rule, record, kept_values={})
        if decision is None or decision.outcome is not policyspec.Outcome.REMOVED:
            continue
        rows.append(
            {
                "record_id": record_id,
                "denylisted_family": tag.taxonomy.get("family", ""),
                "rule_outcome": decision.outcome.value,
                "label_method": method,
                "taxonomy": lineage,
            }
        )

    per_family: dict[str, int] = {}
    for row in rows:
        per_family[row["denylisted_family"]] = per_family.get(row["denylisted_family"], 0) + 1
    by_method: dict[str, int] = {}
    for row in rows:
        by_method[row["label_method"] or "(none stated)"] = (
            by_method.get(row["label_method"] or "(none stated)", 0) + 1
        )

    return {
        "rows": rows,
        "summary": {
            "task": TASK,
            "design_ref": "§7",
            "question": (
                "Of the records the audit detected in Evo 2's released viral component, which "
                "does IMG/VR's own metadata label as belonging to one of the nineteen virus "
                "families the published filter names for removal?"
            ),
            "release": RELEASE,
            "component": COMPONENT,
            "rule": {
                "spec": str(SPEC.relative_to(REPO)),
                "rule": RULE,
                "kind": rule.kind,
                "rank": rule.params.get("rank"),
                "groups": groups,
                "executed_not_restated": (
                    "the groups and the predicate both come from the spec and are applied "
                    "through policyspec.decide, the same code path the corpus-scale evaluator "
                    "uses; this tool implements no matching rule of its own"
                ),
            },
            "label_table": {
                "source": SOURCE_ID,
                "held_at": entry["held_at"],
                "md5": entry["md5"],
                "md5_source": entry.get("md5_source"),
                "revision": entry.get("revision"),
                **pass_counts,
            },
            "detection_tables": tables,
            "counts": {
                "detected_records": len(detected),
                "found_in_label_table": len(labels),
                "absent_from_label_table": len(detected) - len(labels),
                "labelled_at_family_rank": labelled_at_family,
                "denylisted_label_records": len(rows),
            },
            "per_family": dict(sorted(per_family.items())),
            "by_label_method": dict(sorted(by_method.items())),
            "ranks_read": list(RANKS),
            "estimate_kind": "lower_bound",
            "reading_this_table": (
                "A row says two things and no more: IMG/VR's metadata labels this record as a "
                "member of a family the published filter names for removal, and the audit "
                "detected a viral protein family on it. It does not say the record is "
                "dangerous, and it does not say the label is correct — `label_method` is "
                "carried so a reader can see which rows rest on a geNomad prediction rather "
                "than on a reference match. The count is a floor three times over: the "
                "detections come from a sampled search, only a minority of IMG/VR records carry "
                "a family label at all, and the label table covers the high-confidence subset, "
                "so a detected record counted in `absent_from_label_table` is unlabelled *here* "
                "rather than unlabelled in IMG/VR. No sequence was read and no residues are in "
                "this table (D-103); the record identifiers keep it internal until X3.1."
            ),
        },
    }


def write_table(path: Path, rows: list[dict[str, Any]]) -> Path:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(str(row[c]) for c in COLUMNS))
    path.write_text("\n".join(lines) + "\n")
    return path


def summarise(doc: dict[str, Any]) -> str:
    s = doc["summary"]
    counts = s["counts"]
    lines = [
        f"X1.9 denylisted-label records — {s['release']} {s['component']}",
        "",
        f"{counts['detected_records']:,} detected records; "
        f"{counts['found_in_label_table']:,} are in the pinned label table "
        f"({counts['absent_from_label_table']:,} are not, and are unlabelled here rather than "
        "in IMG/VR)",
        f"{counts['labelled_at_family_rank']:,} of those carry a family label at all",
        f"**{counts['denylisted_label_records']:,} carry a label the published rule removes**",
        "",
        "per family:",
    ]
    lines += [f"  {family:24s} {n:5d}" for family, n in s["per_family"].items()]
    lines += [
        "",
        "by label method:",
        *(f"  {method:34s} {n:5d}" for method, n in s["by_label_method"].items()),
        "",
        "A floor, not a census: the detections are sampled, most IMG/VR records carry no family "
        "label, and the label table is the high-confidence subset. The rule is the published "
        "one, executed from the spec rather than restated here.",
        "Internal under X3.1: the table carries record identifiers.",
    ]
    return "\n".join(lines)


def durable_for(out: Path) -> str | None:
    """The durable prefix, or None for a run that is not this task's deliverable.

    Same guard as every other publishing tool here, and for the same two permanent incidents
    (D-193, then D-224): `repro.run`'s prefix follows from the task id and cannot see where the
    run was told to write, and the bucket has no `s3:DeleteObject`.
    """
    if out.resolve() != OUTDIR.resolve():
        return None
    return objectstore.durable_results("x1-9")


def main(argv: list[str] | None = None, *, client: Any = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument("--replace-durable", default=None, help="why replacing a published output")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    handle = client if client is not None else objectstore.client()
    durable = durable_for(args.outdir)
    exempt = None if durable else f"not the deliverable: --outdir {args.outdir} is not {OUTDIR}"
    if exempt:
        print(f"not publishing: {exempt}; this run writes locally only", flush=True)
    args.outdir.mkdir(parents=True, exist_ok=True)

    doc: dict[str, Any] | None = None
    try:
        with repro.run(
            TASK,
            seed=None,  # a join and a predicate; no RNG
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-denylist-label-records.json",
            durable=durable,
            durable_exempt=exempt,
            replace_durable=args.replace_durable,
            uploader=client,
        ) as manifest:
            manifest.parameter("groups_from", f"{SPEC.relative_to(REPO)}:{RULE}")
            manifest.parameter("rule_executed_through", "policyspec.decide")
            manifest.parameter("readings_required_to_agree", list(READINGS))
            manifest.parameter("label_source", SOURCE_ID)
            manifest.parameter("release", RELEASE)
            manifest.input_file(SPEC, role="denylisted group names")
            manifest.input_file(SOURCES, role="source register")
            doc = build(handle)
            table = write_table(args.outdir / "denylisted-label-records.tsv", doc["rows"])
            summary_json = args.outdir / "denylisted-label-records.json"
            summary_json.write_text(json.dumps(doc["summary"], indent=2, sort_keys=True) + "\n")
            summary_md = args.outdir / "denylisted-label-records.md"
            summary_md.write_text(summarise(doc) + "\n")
            manifest.output_file(table, role="denylisted-label records")
            manifest.output_file(summary_json, role="summary with provenance")
            manifest.output_file(summary_md, role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

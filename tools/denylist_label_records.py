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
  release, staged in object storage, verified against **the publisher's own md5** as it streams.
  That digest is read out of the publisher's captured file listing
  (`policies/captures/jgi-imgvr-inventory.json`, `S-IMGVR-JGI-INVENTORY`) by release date and
  file name, so the pin comes from the publisher rather than from a transcription of them —
  which also tells the two releases answering to "IMG/VR v4" apart, since they differ in this
  file by 237 bytes (D-052, D-054).
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

#: Where the label table's pin comes from: **the publisher's own file listing**, captured in the
#: evidence store as `S-IMGVR-JGI-INVENTORY`. Their listing states every IMG/VR file's release
#: date, size and md5sum, so the pin is read from the publisher rather than transcribed — which
#: is `amazebio.profiles.RegistryFile`'s rule (a checksum of bytes you already hold verifies
#: nothing) applied one register over.
INVENTORY = REPO / "policies" / "captures" / "jgi-imgvr-inventory.json"
SOURCE_ID = "S-IMGVR-JGI-INVENTORY"

#: The release joined against, and the file within it. Two releases answer to "IMG/VR v4" and
#: they differ by 237 bytes in this very file; D-052 and D-054 record why this is the one. The
#: date is part of the pin rather than a default, and the size check tells the two apart.
LABEL_RELEASE = "2022-09-20"
LABEL_FILE = "IMGVR_all_Sequence_information-high_confidence.tsv"


#: Where the staged copy of a published IMG/VR file lives, derived from the release and the
#: file name rather than written out as a literal key in a second place.
def label_table_key(release: str, file_name: str) -> str:
    return f"corpora/imgvr/{release}/{file_name}"


#: The spec whose rule names the groups, and the rule's id. The rule is executed, not restated.
SPEC = REPO / "policies" / "specs" / "evo1-literal.yaml"
RULE = "remove-denylisted-families"

#: The published per-hit tables the detected record set comes from. One per reading of the
#: filter, all three required to agree: on this component every taxonomy rule is unresolvable,
#: so nothing is removed under any reading and the three record sets are the same set.
READINGS = ("evo1-literal", "evo1-strict", "evo1-charitable")

#: Per-record hit lists come from one reading, named rather than left implicit. D-247.
HIT_READING = "evo1-literal"
RELEASE = "opengenome2"
COMPONENT = "IMG/VR"

#: A detected record's component, from the prefix the publisher gives its accessions. A2.1's
#: per-hit rows carry no component field — the record id *is* the FASTA header — and this
#: release has two components that both reach the search, so the prefix is the only signal and
#: it is declared rather than pattern-matched: an unknown prefix is a refusal, because silently
#: filing a plasmid record under IMG/VR would join it against a table that cannot contain it.
COMPONENT_OF_PREFIX = {"IMGVR": "IMG/VR", "IMGPR": "IMG/PR"}


def component_of(record_id: str) -> str:
    prefix = record_id.split("_", 1)[0]
    component = COMPONENT_OF_PREFIX.get(prefix)
    if component is None:
        raise Refusal(
            f"{record_id}: accession prefix {prefix!r} belongs to no declared component of "
            f"{RELEASE} ({', '.join(sorted(COMPONENT_OF_PREFIX))}). A record filed under the "
            "wrong component is joined against a table that cannot contain it."
        )
    return component


def detections_key(reading: str) -> str:
    return f"corpora/results/a2-1/detections-pfam-{reading}-{RELEASE}.jsonl"


#: Columns of the label table this reads, by header name rather than by position: the file has
#: nineteen columns and one of its headers contains a comma and a parenthesis, so a positional
#: read would be a silent dependency on column order.
UVIG = "UVIG"
LINEAGE = "Taxonomic classification"
METHOD = "Taxonomic classification method"

COLUMNS = (
    "record_id",
    "component",
    "pfam_families",
    "denylisted_groups_named",
    "in_label_table",
    "label_family",
    "label_method",
    "label_rule_outcome",
    "taxonomy",
)


class Refusal(SystemExit):
    """Exit with a reason. Every refusal here is a disagreement between two pinned inputs."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"refused: {reason}")


# --------------------------------------------------------------------------------------
# The three inputs
# --------------------------------------------------------------------------------------


def label_table_pin() -> dict[str, Any]:
    """The publisher's own md5 and size for the label table, and where the staged copy is.

    Read out of their captured file listing by release date *and* file name, and refused unless
    that selects exactly one file: the listing holds forty-two files across ten dated releases,
    and two of those releases carry this same file name with different bytes.
    """
    listing = json.loads(INVENTORY.read_text())
    files = [
        f
        for f in listing["files"]
        if f.get("file_name") == LABEL_FILE and f.get("added_date") == LABEL_RELEASE
    ]
    if len(files) != 1:
        raise Refusal(
            f"{INVENTORY} lists {len(files)} files named {LABEL_FILE!r} for release "
            f"{LABEL_RELEASE}; the publisher's digest for this pass has no other source"
        )
    entry = files[0]
    for field in ("md5sum", "file_size"):
        if not entry.get(field):
            raise Refusal(f"{SOURCE_ID} states no {field} for {LABEL_FILE}, so it cannot be pinned")
    return {
        "source": SOURCE_ID,
        "capture": str(INVENTORY.relative_to(REPO)),
        "retrieved": listing.get("retrieved"),
        "release": LABEL_RELEASE,
        "file_name": LABEL_FILE,
        "md5": entry["md5sum"],
        "md5_source": f"{SOURCE_ID}: the publisher's own file listing, {LABEL_RELEASE}",
        "bytes": int(entry["file_size"]),
        "held_at": f"s3://{corpora.BUCKET}/{label_table_key(LABEL_RELEASE, LABEL_FILE)}",
    }


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


#: X1.8's published table of detected families whose Pfam name refers to a denylisted group:
#: the family axis of the hazard check, read by key with its digest recorded. Produced by
#: `tools/denylist_named_families.py`, whose matching rule and its two readings are that task's.
NAMED_FAMILIES_KEY = "corpora/results/x1-8/denylist-named-families.tsv"


def denylist_named_families(client: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """`{pfam accession: the denylisted group(s) its name refers to}`, from X1.8's table."""
    body = client.get_object(Bucket=corpora.BUCKET, Key=NAMED_FAMILIES_KEY)["Body"].read()
    lines = body.decode().splitlines()
    if not lines:
        raise Refusal(f"{NAMED_FAMILIES_KEY} is empty; the family axis has no other source")
    header = lines[0].split("\t")
    for column in ("accession", "denylisted_group"):
        if column not in header:
            raise Refusal(
                f"{NAMED_FAMILIES_KEY} has no {column!r} column (it has {header}); this table is "
                "X1.8's and its shape is what the join reads"
            )
    acc, grp = header.index("accession"), header.index("denylisted_group")
    families = {row.split("\t")[acc]: row.split("\t")[grp] for row in lines[1:] if row.strip()}
    return families, {
        "key": NAMED_FAMILIES_KEY,
        "sha256": hashlib.sha256(body).hexdigest(),
        "families": len(families),
    }


def detected_records(
    client: Any, named_families: dict[str, str]
) -> tuple[set[str], dict[str, list[str]], list[dict[str, Any]]]:
    """The detected record set, the hits in denylist-named families, and the tables read.

    Each reading's table is read whole and its digest recorded. The three sets must be equal:
    every taxonomy rule is unresolvable against this component (A1.4's finding), so the readings
    cannot differ here, and if they do then one table is not the table it claims to be.

    Hits are counted from the literal reading, named in :data:`HIT_READING`: the detected *set*
    is the agreement of all three, while a per-record hit list is a measurement of one table, and
    mixing readings in one column would make it a sum over three overlapping corpora (D-247).
    """
    sets: dict[str, set[str]] = {}
    tables: list[dict[str, Any]] = []
    hits: dict[str, list[str]] = {}
    for reading in READINGS:
        key = detections_key(reading)
        body = client.get_object(Bucket=corpora.BUCKET, Key=key)["Body"].read()
        ids: set[str] = set()
        for line in body.decode().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            ids.add(row["record_id"])
            if reading == HIT_READING and row["family_id"] in named_families:
                hits.setdefault(row["record_id"], []).append(row["family_id"])
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
    return first, {r: sorted(set(f)) for r, f in hits.items()}, tables


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
            f"{key}: staged object is {live} bytes, the publisher's listing says "
            f"{entry['bytes']} for the {entry['release']} release. A staged object of a "
            "different length is a different release, and two of them carry this file name."
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
            f"{key}: md5 {md5} is not the publisher's {entry['md5']} ({SOURCE_ID}). Every "
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
    entry = label_table_pin()
    rule = denylist_rule()
    groups = list(rule.params["names"])
    named_families, family_table = denylist_named_families(client)
    detected, hits, tables = detected_records(client, named_families)
    print(
        f"{len(detected):,} detected records on {RELEASE}, {len(hits):,} of them carrying a hit "
        f"in one of {family_table['families']} denylist-named families; reading the label table",
        flush=True,
    )

    labels, pass_counts = stream_labels(client, entry=entry, wanted=detected)

    def label_outcome(lineage: str) -> tuple[str, str | None]:
        """The record's family label, and what the published rule does when given it."""
        tag = parse_lineage_tag(lineage)
        record = policyspec.Record(id="", component=COMPONENT, taxonomy=dict(tag.taxonomy))
        # The published rule, executed rather than restated: the record is one the filter's own
        # denylist removes when it is handed that record's own label.
        decision = policyspec.decide(rule, record, kept_values={})
        return tag.taxonomy.get("family", ""), None if decision is None else decision.outcome.value

    # The per-record table: one row per detected record carrying a hit in a denylist-named
    # family, which is the axis the hazard check's per-record work is on. The label is attached
    # where the table has one and its absence is a column rather than a dropped row.
    rows: list[dict[str, Any]] = []
    for record_id in sorted(hits):
        families = hits[record_id]
        lineage, method = labels.get(record_id, ("", ""))
        family, outcome = label_outcome(lineage) if lineage else ("", None)
        rows.append(
            {
                "record_id": record_id,
                "component": component_of(record_id),
                "pfam_families": "|".join(families),
                "denylisted_groups_named": "|".join(
                    sorted({g for f in families for g in named_families[f].split("|")})
                ),
                "in_label_table": record_id in labels,
                "label_family": family,
                "label_method": method,
                "label_rule_outcome": outcome or "",
                "taxonomy": lineage,
            }
        )

    # The other axis, over every detected record rather than only these: which records the
    # published denylist rule removes on the strength of IMG/VR's own label. It costs nothing
    # extra — the same pass already read every label — and it is the figure the label arm of the
    # hazard check reports, so the two axes are never mistaken for one number.
    label_removed: list[str] = []
    labelled_at_family = 0
    for record_id, (lineage, _) in labels.items():
        family, outcome = label_outcome(lineage)
        if family:
            labelled_at_family += 1
        if outcome == policyspec.Outcome.REMOVED.value:
            label_removed.append(record_id)

    # The label table is IMG/VR's, so a plasmid record missing from it is not a record the
    # high-confidence subset left out — it is a record the table was never about. Counting the
    # two together would read as a gap in IMG/VR's labelling that is nothing of the kind.
    by_component: dict[str, int] = {}
    for record_id in detected:
        key = component_of(record_id)
        by_component[key] = by_component.get(key, 0) + 1
    absent = sorted(detected - set(labels))
    absent_by_component: dict[str, int] = {}
    for record_id in absent:
        key = component_of(record_id)
        absent_by_component[key] = absent_by_component.get(key, 0) + 1

    def tally(key: Any, over: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in over:
            out[key(row)] = out.get(key(row), 0) + 1
        return dict(sorted(out.items()))

    labelled_rows = [r for r in rows if r["in_label_table"]]
    return {
        "rows": rows,
        "summary": {
            "task": TASK,
            "design_ref": "§7",
            "question": (
                "For each record the audit detected in Evo 2's released viral component on a "
                "Pfam family whose name refers to a group the published filter names for "
                "removal: what does IMG/VR's own metadata label that record as, and would the "
                "published rule have removed it on the strength of that label?"
            ),
            "release": RELEASE,
            "component": COMPONENT,
            "two_axes": (
                "A family-named row and a denylisted label are different claims and this table "
                "keeps them apart. `records_with_denylist_named_family_hit` counts records by "
                "the name of the family detected on them, which is a property of Pfam's "
                "curation; `records_the_label_rule_removes` counts records by their own IMG/VR "
                "label, over every detected record. Neither is a subset of the other and "
                "neither is the sum."
            ),
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
            "family_axis_from": family_table,
            "hit_reading": HIT_READING,
            "label_table": {
                "source": SOURCE_ID,
                "capture": entry["capture"],
                "held_at": entry["held_at"],
                "md5": entry["md5"],
                "md5_source": entry["md5_source"],
                "release": entry["release"],
                "listing_retrieved": entry["retrieved"],
                **pass_counts,
            },
            "detection_tables": tables,
            "detected_by_component": dict(sorted(by_component.items())),
            "absent_from_label_table_by_component": dict(sorted(absent_by_component.items())),
            "counts": {
                "detected_records": len(detected),
                "found_in_label_table": len(labels),
                "absent_from_label_table": len(detected) - len(labels),
                "labelled_at_family_rank": labelled_at_family,
                "records_with_denylist_named_family_hit": len(rows),
                "of_those_in_label_table": len(labelled_rows),
                "of_those_with_a_family_label": sum(1 for r in labelled_rows if r["label_family"]),
                "of_those_the_label_rule_removes": sum(
                    1 for r in labelled_rows if r["label_rule_outcome"] == "removed"
                ),
                "records_the_label_rule_removes": len(label_removed),
                "family_axis_by_component": {
                    component: sum(1 for r in rows if r["component"] == component)
                    for component in sorted({r["component"] for r in rows})
                },
            },
            "per_group_named": tally(lambda r: r["denylisted_groups_named"], rows),
            "per_label_family": tally(
                lambda r: r["label_family"] or "(no family label)", labelled_rows
            ),
            "by_label_method": tally(lambda r: r["label_method"] or "(none stated)", labelled_rows),
            "ranks_read": list(RANKS),
            "estimate_kind": "lower_bound",
            "reading_this_table": (
                "One row is one detected record whose detected Pfam family *name* refers to a "
                "group the published filter denylists. That is a property of Pfam's curation, "
                "not of the record: a row leaves open whether the record belongs to that group "
                "or carries a distant homolog, which is what the label columns are for and why "
                "`label_method` travels with every row — a label resting on a geNomad "
                "prediction is weaker evidence than one resting on a reference match. "
                "`label_rule_outcome` is the published denylist rule executed against that "
                "record's own label, so `removed` means the filter would have excluded the "
                "record had it been able to read the label, and an empty value means the label "
                "says nothing the rule reads. A record with `in_label_table` false is "
                "unlabelled *in this table* rather than in IMG/VR: the table covers the "
                "high-confidence subset. The counts are a floor — the detections come from a "
                "sampled search and most IMG/VR records carry no family label at all. No "
                "sequence was read and no residues are here (D-103); the record identifiers "
                "keep this table internal until X3.1."
            ),
        },
    }


def write_tables(outdir: Path, stem: str, rows: list[dict[str, Any]]) -> list[Path]:
    """The per-record table, and one table per component.

    Split because the consumer of this list reads **one** staged object: A7.5's pass streams
    Evo 2's viral component, so handing it a list with five plasmid records in it would report
    those five as missing from a corpus they were never in. A published table per component
    means the next pass is given an artefact with a digest rather than the output of somebody's
    ad-hoc filter.
    """
    written = [_write_rows(outdir / f"{stem}.tsv", rows)]
    for component in sorted({r["component"] for r in rows}):
        slug = component.lower().replace("/", "").replace(" ", "-")
        written.append(
            _write_rows(
                outdir / f"{stem}-{slug}.tsv",
                [r for r in rows if r["component"] == component],
            )
        )
    return written


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> Path:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(str(row[c]) for c in COLUMNS))
    path.write_text("\n".join(lines) + "\n")
    return path


def summarise(doc: dict[str, Any]) -> str:
    s = doc["summary"]
    c = s["counts"]
    lines = [
        f"X1.9 per-record label table — {s['release']} {s['component']}",
        "",
        f"{c['detected_records']:,} detected records; {c['found_in_label_table']:,} are in the "
        f"pinned label table ({c['absent_from_label_table']:,} are not, and are unlabelled here "
        "rather than in IMG/VR)",
        f"{c['labelled_at_family_rank']:,} of those carry a family label at all",
        "  detected by component: "
        + ", ".join(f"{k} {v:,}" for k, v in s["detected_by_component"].items()),
        "  absent from the label table by component: "
        + ", ".join(f"{k} {v:,}" for k, v in s["absent_from_label_table_by_component"].items())
        + " — the table is IMG/VR's, so a plasmid record was never in it",
        "",
        "the family axis — records whose detected Pfam family is named for a denylisted group:",
        "  by component: "
        + ", ".join(f"{k} {v:,}" for k, v in c["family_axis_by_component"].items()),
        f"  **{c['records_with_denylist_named_family_hit']:,} records**, "
        f"{c['of_those_in_label_table']:,} of them in the label table, "
        f"{c['of_those_with_a_family_label']:,} carrying a family label, "
        f"{c['of_those_the_label_rule_removes']:,} the published rule would remove",
        "",
        "the label axis — every detected record the published denylist rule removes on its own "
        "label:",
        f"  **{c['records_the_label_rule_removes']:,} records**",
        "",
        "Different claims, never one number: the first counts by the name of the family "
        "detected, which is a property of Pfam's curation; the second counts by the record's "
        "own IMG/VR label. Neither contains the other.",
        "",
        "per denylisted group named by the detected family:",
        *(f"  {group:34s} {n:5d}" for group, n in s["per_group_named"].items()),
        "",
        "label method, for the family-axis records that carry a label:",
        *(f"  {method:38s} {n:5d}" for method, n in s["by_label_method"].items()),
        "",
        "A floor: the detections are sampled, most IMG/VR records carry no family label, and the "
        "label table is the high-confidence subset. The rule is the published one, executed from "
        "the spec rather than restated here.",
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
            manifest_name="run-denylist-named-family-records.json",
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
            manifest.input_file(INVENTORY, role="publisher file listing (the label pin)")
            doc = build(handle)
            stem = "denylist-named-family-records"
            for table in write_tables(args.outdir, stem, doc["rows"]):
                manifest.output_file(
                    table,
                    role=(
                        "per-record label table"
                        if table.name == f"{stem}.tsv"
                        else f"per-record label table, {table.stem.removeprefix(stem + '-')} only"
                    ),
                )
            summary_json = args.outdir / f"{stem}.json"
            summary_json.write_text(json.dumps(doc["summary"], indent=2, sort_keys=True) + "\n")
            summary_md = args.outdir / f"{stem}.md"
            summary_md.write_text(summarise(doc) + "\n")
            manifest.output_file(summary_json, role="summary with provenance")
            manifest.output_file(summary_md, role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regenerate the per-record table: detected records whose own label is on the denylist.

    pixi run -e dev python tools/denylisted_label_records.py --outdir artifacts/x1-8/records

The companion of `tools/denylist_named_families.py`. That one asks which detected *families*
carry a name referring to a group the published filter denylists; this one asks which detected
*records* carry a taxonomic label that is literally one of the denylisted taxa, which is a
different question with a different answer — two groups name no detected family and do label
detected records.

Three pinned references, and one of them is verified end to end here:

* The A2.1 per-hit table for the literal reading of the filter over Evo 2's released corpus.
  It names the record behind every hit, which is what makes the join possible at all. **Only
  Evo 2's.** Evo 1's released viral component carries no source accession — its per-hit records
  are `stage2:train…` training identifiers — so no label statement can be made about an Evo 1
  record, and this tool refuses a release whose identifiers do not resolve.
* `S-IMGVR-V4-SEQINFO-2022-09-20`, streamed from object storage rather than downloaded: the
  session's writable disk is smaller than the file. The md5 of the whole stream is computed as
  it passes and compared with the publisher's, so the figures rest on the publisher's digest
  and not on the staging having gone well.
* `S-ICTV-VMR-MSL37-3` for the host column, verified against its sha256 before it is read.

The denylisted family and order names come from `policies/specs/evo1-literal.yaml`, as they do
everywhere else in this project.

**What a row is, and is not.** A row says that a record the audit detected carries, in IMG/VR's
own metadata, a label naming a taxon the filter's own policy names for removal. The label comes
from the source database by way of the accession the release carries, not from anything in the
release. Whether that constitutes a conformance failure of the published procedure is A7.1's and
A7.2's question, decided against the three readings, and this table does not assert it.

**The ceiling is the first thing to read.** Only a small minority of IMG/VR records carry a
family label at all, so a count here is a floor over that window: a record not on this list is
one whose label does not say, never one that is known not to be a member. The summary records
the window it was measured over rather than leaving it to prose.

**Host comes from a pinned source rather than from judgement**, and its vocabulary stops above
the question anyone wants to ask: the VMR's finest `Host source` value is `vertebrates` and it
never says `human`. A species named after the pin is absent from the VMR rather than hostless,
which is a third state and is reported as one.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import denylist_named_families as families

from amazebio import ictv, objectstore, profiles, repro

TASK = "X1.8"

#: The release this question can be asked of, and the reading of the filter whose per-hit table
#: is read. Both are named rather than defaulted: see the module docstring on Evo 1.
RELEASE = "opengenome2"
POLICY = "evo1-literal"

#: The label table. `S-IMGVR-V4-SEQINFO-2022-09-20` in `policies/sources.json`.
LABELS_KEY = "corpora/imgvr/2022-09-20/IMGVR_all_Sequence_information-high_confidence.tsv"

#: The ICTV release whose `Host source` column the host column comes from.
VMR_RELEASE = "MSL37.3"

#: Columns of the label table this tool reads, by header text. Reading by text rather than by
#: position is A7.2's convention: the two IMG/VR v4 releases do not share a column order.
UVIG = "UVIG"
VOTU = "vOTU"
LINEAGE = "Taxonomic classification"
HOST_PREDICTION = "Host taxonomy prediction"

#: The lineage field's rank prefixes, in the order the publisher writes them.
RANK_PREFIXES = {
    "r__": "realm",
    "k__": "kingdom",
    "p__": "phylum",
    "c__": "class",
    "o__": "order",
    "f__": "family",
    "g__": "genus",
    "s__": "species",
}

COLUMNS = (
    "record_id",
    "vOTU",
    "denylisted_family",
    "denylisted_order",
    "realm",
    "class",
    "order",
    "family",
    "genus",
    "species",
    "vmr_host_source",
    "imgvr_host_prediction",
    "detected_families",
    "detected_family_names",
)


def rule_names(rule: str, rank: str, expected: int) -> list[str]:
    """One `remove_if_taxon_in` rule's taxon names, from the spec."""
    policy = families.policyspec.load_policy(families.SPEC)
    for item in policy.rules:
        if item.id == rule:
            if item.params.get("rank") != rank:
                raise SystemExit(
                    f"{families.SPEC}: {rule} names rank {item.params.get('rank')!r}, not "
                    f"{rank!r}; the label join compares that rank's column."
                )
            names = list(item.params["names"])
            if len(names) != expected or len(set(names)) != len(names):
                raise SystemExit(
                    f"{families.SPEC}: {rule} names {len(names)} taxa, expected {expected} "
                    "distinct. The published procedure states the count and the list is quoted "
                    "from it."
                )
            return names
    raise SystemExit(f"{families.SPEC}: no rule {rule!r}.")


def detections(
    client: Any, universe: dict[str, profiles.FamilyMeta]
) -> tuple[dict[str, set[str]], list[str]]:
    """IMG/VR record id to the families that detected it, and the plasmid records set aside."""
    key = f"corpora/results/a2-1/detections-pfam-{POLICY}-{RELEASE}.jsonl"
    hits: dict[str, set[str]] = {}
    body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=key)["Body"]
    tail = b""
    for chunk in body.iter_chunks(1 << 22):
        lines = (tail + chunk).split(b"\n")
        tail = lines.pop()
        for line in lines:
            if not line.strip():
                continue
            hit = json.loads(line)
            if hit["family_id"] not in universe:
                raise SystemExit(
                    f"{key}: hit on {hit['family_id']}, which is not in the pinned universe. "
                    "The per-hit table and the family pin describe different selections."
                )
            hits.setdefault(hit["record_id"], set()).add(hit["family_id"])
    if tail.strip():
        hit = json.loads(tail)
        hits.setdefault(hit["record_id"], set()).add(hit["family_id"])

    #: Three kinds of record id, and only one of them has a label to look up.
    #:
    #: * `IMGVR_…` — a record of the component the filter's rules were described as applied to.
    #:   This table is about those.
    #: * `IMGPR_…` — a plasmid record. IMG/PR is in the corpus and out of the published policy's
    #:   scope by its own words, and it has no viral taxonomy to join against, so these are
    #:   counted and set aside rather than silently dropped.
    #: * anything else — an identifier that resolves to nothing, which is the whole of Evo 1's
    #:   released viral component (`stage2:train…`). A label statement about such a record is
    #:   impossible, and a tool that quietly skipped them would report a floor as a count.
    plasmids = sorted(r for r in hits if r.startswith("IMGPR_"))
    unresolvable = sorted(
        r for r in hits if not r.startswith("IMGVR_") and not r.startswith("IMGPR_")
    )
    if unresolvable:
        raise SystemExit(
            f"{key}: {len(unresolvable)} of {len(hits)} record ids resolve to no source record "
            f"(first: {unresolvable[0]!r}). No label statement can be made about them, so this "
            "table cannot be built from this release. Evo 1's released viral component is the "
            "whole of this class, which is why this tool reads one release."
        )
    for record in plasmids:
        del hits[record]
    return hits, plasmids


def stream_labels(
    client: Any, detected: set[str], seen: dict[str, str]
) -> Iterator[dict[str, str]]:
    """Rows of the label table for detected records, with the stream's md5 verified at the end.

    The file is 1.9 GB and the session's writable disk is smaller, so it is never stored. The
    digest is computed over the bytes as they pass and left in `seen['md5']`: a figure read
    from a stream nobody checked would rest on the staging having gone well rather than on the
    publisher's digest.
    """
    digest = hashlib.md5(usedforsecurity=False)
    body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=LABELS_KEY)["Body"]
    header: list[str] | None = None
    tail = b""

    def row(raw: bytes) -> dict[str, str] | None:
        nonlocal header
        fields = raw.decode("utf8", "replace").rstrip("\r").split("\t")
        if header is None:
            header = fields
            missing = [c for c in (UVIG, VOTU, LINEAGE, HOST_PREDICTION) if c not in header]
            if missing:
                raise SystemExit(f"{LABELS_KEY}: header is missing column(s) {missing}.")
            return None
        if fields[0] not in detected:
            return None
        # A row whose trailing columns are empty may be written short. Padding keeps the
        # column names aligned with the values; a row *longer* than the header is a different
        # file than the one the header describes and is a refusal.
        if len(fields) > len(header):
            raise SystemExit(
                f"{LABELS_KEY}: {fields[0]} has {len(fields)} fields over a {len(header)}-column "
                "header. The header and the rows do not describe the same table."
            )
        fields += [""] * (len(header) - len(fields))
        return dict(zip(header, fields, strict=True))

    for chunk in body.iter_chunks(1 << 22):
        digest.update(chunk)
        lines = (tail + chunk).split(b"\n")
        tail = lines.pop()
        for raw in lines:
            if not raw:
                continue
            parsed = row(raw)
            if parsed is not None:
                yield parsed
    if tail:
        parsed = row(tail)
        if parsed is not None:
            yield parsed
    seen["md5"] = digest.hexdigest()
    pinned = next(
        entry
        for entry in json.loads((Path("policies") / "sources.json").read_text())["sources"]
        if entry["id"] == "S-IMGVR-V4-SEQINFO-2022-09-20"
    )
    if digest.hexdigest() != pinned["md5"]:
        raise SystemExit(
            f"{LABELS_KEY}: the staged bytes hash to md5 {digest.hexdigest()}, and the "
            f"publisher states {pinned['md5']} for this release. Every label figure is "
            "relative to that file, so this is a refusal and not a warning."
        )


def ranks(lineage: str) -> dict[str, str]:
    """The publisher's `r__…;k__…;…` lineage field, split by rank."""
    out = {name: "" for name in RANK_PREFIXES.values()}
    for part in lineage.split(";"):
        part = part.strip()
        for prefix, rank in RANK_PREFIXES.items():
            if part.startswith(prefix):
                out[rank] = part[len(prefix) :].strip()
    return out


def build(client: Any, dat: Path, vmr_path: Path) -> dict[str, Any]:
    universe = profiles.select_viral_families(dat)
    denylisted_families = rule_names("remove-denylisted-families", "family", 19)
    denylisted_orders = rule_names("remove-denylisted-orders", "order", 12)

    hits, plasmids = detections(client, universe)
    vmr = ictv.read_vmr(vmr_path)
    host_of = {item.species: item.host_source for item in vmr.exemplars}

    rows: list[dict[str, Any]] = []
    joined = 0
    with_family_label = 0
    with_order_label = 0
    seen: dict[str, str] = {}
    for record in stream_labels(client, set(hits), seen):
        joined += 1
        lineage = ranks(record[LINEAGE])
        if lineage["family"]:
            with_family_label += 1
        if lineage["order"]:
            with_order_label += 1
        family_hit = lineage["family"] if lineage["family"] in denylisted_families else ""
        order_hit = lineage["order"] if lineage["order"] in denylisted_orders else ""
        if not family_hit and not order_hit:
            continue
        detected_families = sorted(hits[record[UVIG]])
        rows.append(
            {
                "record_id": record[UVIG],
                "vOTU": record[VOTU],
                "denylisted_family": family_hit,
                "denylisted_order": order_hit,
                "realm": lineage["realm"],
                "class": lineage["class"],
                "order": lineage["order"],
                "family": lineage["family"],
                "genus": lineage["genus"],
                "species": lineage["species"],
                # Three states, kept distinct in the row and not only in the summary: a host,
                # no species label to ask about, and a species the pinned release does not
                # contain. The last is taxonomic churn after the pin, not a hostless virus.
                "vmr_host_source": (
                    host_of.get(lineage["species"], f"species-not-in-{VMR_RELEASE}")
                    if lineage["species"]
                    else ""
                ),
                "imgvr_host_prediction": record[HOST_PREDICTION],
                "detected_families": ";".join(detected_families),
                "detected_family_names": ";".join(
                    universe[accession].name for accession in detected_families
                ),
            }
        )

    if joined != len(hits):
        raise SystemExit(
            f"{LABELS_KEY}: {joined} of {len(hits)} detected records joined. A record that "
            "does not join is not an unlabelled record, it is an accession the pinned release "
            "does not contain, which would mean the hits and the labels are different releases."
        )

    absent = f"species-not-in-{VMR_RELEASE}"
    species_absent = sum(1 for r in rows if r["vmr_host_source"] == absent)
    summary = {
        "task": TASK,
        "question": (
            "Which records that the audit detected in the released corpus carry a taxonomic "
            "label naming a taxon the published filter's own policy names for removal?"
        ),
        "release": RELEASE,
        "policy_reading": POLICY,
        "route": "profile-hmmer",
        "route_note": (
            "A2.4 publishes no per-hit table, so the provirus route is out of scope here: no "
            "record behind a provirus hit can be looked up at all."
        ),
        "detected_records": len(hits),
        "plasmid_records_set_aside": len(plasmids),
        "joined_to_labels": joined,
        "label_ceiling": {
            "records_with_a_family_label": with_family_label,
            "records_with_an_order_label": with_order_label,
            "family_label_fraction": round(with_family_label / joined, 6),
            "order_label_fraction": round(with_order_label / joined, 6),
            "note": (
                "A negative result below means 'not labelled', never 'not present'. Every count "
                "is a floor over this window, and the window is itself a sample of the corpus."
            ),
        },
        "rows": len(rows),
        "with_denylisted_family_label": sum(1 for r in rows if r["denylisted_family"]),
        "with_denylisted_order_label": sum(1 for r in rows if r["denylisted_order"]),
        "with_both": sum(1 for r in rows if r["denylisted_family"] and r["denylisted_order"]),
        "per_denylisted_family": dict(
            Counter(r["denylisted_family"] for r in rows if r["denylisted_family"]).most_common()
        ),
        "per_denylisted_order": dict(
            Counter(r["denylisted_order"] for r in rows if r["denylisted_order"]).most_common()
        ),
        "host": {
            "source": f"ICTV VMR {VMR_RELEASE}, 'Host source' column",
            "rows_with_a_host": sum(
                1 for r in rows if r["vmr_host_source"] and r["vmr_host_source"] != absent
            ),
            "rows_with_no_species_label": sum(1 for r in rows if not r["species"]),
            "rows_whose_species_is_absent_from_the_vmr": species_absent,
            "note": (
                "The column's finest value is 'vertebrates' and it never says 'human', so no "
                "count here supports a sentence about human pathogens. A species absent from "
                "the pin is a third state, not a hostless record."
            ),
        },
        "does_not_claim": [
            "that a labelled record is a conformance failure of the published procedure: the "
            "label is the source database's, reached by accession, and A7.1 and A7.2 own that "
            "question against the three readings",
            "that these are all such records: the label ceiling above bounds every count",
        ],
        "sources": {
            "labels": {
                "key": LABELS_KEY,
                "md5": seen["md5"],
                "verified_against": "the publisher's own md5, over the whole stream",
            },
            "detections": f"corpora/results/a2-1/detections-pfam-{POLICY}-{RELEASE}.jsonl",
            "vmr": str(vmr_path),
            "pfam_dat": str(dat),
        },
    }
    return {"rows": rows, "summary": summary}


def write(built: dict[str, Any], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    tsv = outdir / "denylisted-label-records.tsv"
    with open(tsv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in sorted(built["rows"], key=lambda r: r["record_id"]):
            writer.writerow(row)
    summary = outdir / "denylisted-label-records.json"
    summary.write_text(json.dumps(built["summary"], indent=2, sort_keys=True) + "\n")
    return [tsv, summary]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, default=Path("data/profiles/Pfam-A.hmm.dat.gz"))
    parser.add_argument("--vmr", type=Path, default=None, help="default: the MSL37.3 pin's path")
    parser.add_argument("--outdir", type=Path, default=Path("artifacts/x1-8/records"))
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    release = ictv.RELEASES[VMR_RELEASE]
    vmr_path = args.vmr or Path("data/ictv") / release.filename
    digest = hashlib.sha256(vmr_path.read_bytes()).hexdigest()
    if digest != release.sha256:
        raise SystemExit(
            f"{vmr_path}: sha256 {digest} is not the pinned {release.sha256} for "
            f"{release.url}. Re-stage it; every host statement is relative to that release."
        )
    pfam = {f.name: f for f in profiles.registry("pfam").files}[families.PFAM_DAT]
    pfam_digest = hashlib.md5(args.dat.read_bytes(), usedforsecurity=False).hexdigest()
    if pfam_digest != pfam.md5:
        raise SystemExit(f"{args.dat}: md5 {pfam_digest} is not the publisher's {pfam.md5}.")

    with repro.run(
        TASK,
        outdir=args.outdir,
        manifest_name="run-label-records.json",
        allow_dirty=args.allow_dirty,
        durable=objectstore.durable_results("x1-8/records"),
    ) as manifest:
        manifest.parameter("release", RELEASE)
        manifest.parameter("policy_reading", POLICY)
        manifest.parameter("route", "profile-hmmer")
        manifest.parameter("labels_key", LABELS_KEY)
        manifest.parameter("vmr_release", VMR_RELEASE)
        manifest.input_file(args.dat, role="pfam family metadata")
        manifest.input_file(vmr_path, role="ictv vmr")
        manifest.input_file(families.SPEC, role="denylisted taxon names")
        built = build(objectstore.client(), args.dat, vmr_path)
        for path in write(built, args.outdir):
            manifest.output_file(path, role="denylisted-label record table")

    summary = built["summary"]
    print(
        f"{summary['joined_to_labels']} detected records joined; "
        f"{summary['label_ceiling']['records_with_a_family_label']} carry a family label "
        f"({summary['label_ceiling']['family_label_fraction'] * 100:.2f}%)"
    )
    print(
        f"rows {summary['rows']}: family label {summary['with_denylisted_family_label']}, "
        f"order label {summary['with_denylisted_order_label']}, "
        f"both {summary['with_both']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

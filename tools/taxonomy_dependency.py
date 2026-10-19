#!/usr/bin/env python3
"""A4.2 step 1 — which taxonomy assignment tool the filter actually depends on, and how much.

DESIGN.md §A4 says to benchmark "the taxonomy assignment tools the filter relies on". That
phrasing hides a question of fact that has to be settled before any error rate means
anything: *which* tool, on *which* records. A benchmark of a tool that assigned 2% of the
labels the denylist reads would be a precise answer to nothing.

On this corpus the question has a published answer. IMG/VR carries a
`Taxonomic classification method` field per record, and the publisher's own help page names
the four approaches it can hold:

    Taxonomic assignment of IMG/VR UViGs is based on (i) clustering with RefSeq virus
    genomes; (ii) geNomad's marker-based taxonomic assignment; (iii) similarity to viral
    proteins in NCBI NR; (iv) vOTU consensus.

So this pass cross-tabulates that field against the thing that matters — whether the record
is labelled at the ranks Evo's denylist reads — over the population the denylist is actually
handed, which is what survives the confidence gate that runs before it (A4.1, D-081).

It also records two things the benchmark downstream needs and cannot invent:

* **The length distribution of the records the rules decide on.** A4.2's evaluation set is
  built from complete reference genomes, because that is where trustworthy ground truth
  exists; the corpus is mostly assembly fragments. The strata the benchmark reports its
  error rate over are taken from this distribution rather than chosen for roundness.
* **The share of records flagged `Reference`.** The release note says sequences from NCBI
  RefSeq are flagged that way in `MIUViG quality`. Those would carry ground truth inside the
  corpus itself, which would be a better evaluation set than any external one, so their
  count decides whether that option exists.

Reads the sequence-information table out of object storage in byte shards, as A4.1 and A7.2
do; emits counts only, never sequence.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import conformance, imgvr, objectstore, policyspec
from amazebio.misassignment import Denylist
from amazebio.repro import run

TASK = "A4.2"
SEED = 20261015

#: The blank-field label, following `unfilterable`'s convention so the two artefacts can be
#: read side by side without a translation table.
EMPTY = "(empty)"

#: The `MIUViG quality` value the release note gives to sequences taken from NCBI RefSeq.
REFERENCE = "Reference"

#: The confidence value Evo 1's first rule keeps. Every later rule only ever sees what it
#: kept, so a share of "the records the denylist decides on" is a share of this subset.
HIGH_CONFIDENCE = "High-confidence"

#: The publisher's own description of each method value, from the IMG/VR help page. Stored
#: so the artefact can state what a method *is* rather than only its name — a reader should
#: not have to know that "NR (doi:...)" means protein similarity to NCBI NR.
METHOD_MEANING: dict[str, str] = {
    "geNomad": "geNomad's marker-based taxonomic assignment (help page, approach ii)",
    "vOTU with RefSeq genome": (
        "clustering with RefSeq virus genomes: the UViG shares a vOTU with a reference and "
        "takes the reference's taxonomy (help page, approach i)"
    ),
    "vOTU consensus": "consensus of the other members of the UViG's vOTU (help page, approach iv)",
    "NR (doi:10.5281/zenodo.6574914)": (
        "similarity to viral proteins in NCBI NR (help page, approach iii)"
    ),
    EMPTY: "no method recorded; these are the records that carry no classification at all",
}

#: Length strata, in bases. The edges are the ones IMG/VR's own documentation and the
#: MIUViG convention make meaningful rather than arbitrary round numbers: 10 kb is where
#: viral contig callers are conventionally trusted, and the top edge separates the complete
#: genomes from the fragments that dominate the corpus.
LENGTH_EDGES: tuple[int, ...] = (0, 2_500, 5_000, 10_000, 20_000, 40_000, 80_000, 200_000)


def _stratum(length: int) -> str:
    for index in range(len(LENGTH_EDGES) - 1, -1, -1):
        if length >= LENGTH_EDGES[index]:
            high = LENGTH_EDGES[index + 1] if index + 1 < len(LENGTH_EDGES) else None
            return f"{LENGTH_EDGES[index]}-{high if high else 'inf'}"
    return "unknown"


def _rank_depth(classification: str) -> dict[str, str]:
    """The lineage tag parsed to `{rank: name}`.

    Delegates to `conformance.parse_lineage_tag`, which A7.1 wrote against the released
    format and D-057 made the single parser for it. IMG/VR's `Taxonomic classification`
    column is formatted identically to the inline tag Evo 1's release carries (D-057), so
    re-deriving the split here would be the cross-declaration that decision forbids.
    """
    return conformance.parse_lineage_tag(classification).taxonomy


def _scan_shard(
    bucket: str,
    key: str,
    start: int,
    end: int,
    header: list[str],
    families: frozenset[str],
    orders: frozenset[str],
) -> dict[str, Any]:
    """Tally one byte shard. Runs in a subprocess; returns counters, never rows."""
    idx = {role: header.index(name) for role, name in imgvr.SEQ_COLUMNS.items()}
    method_col = header.index("Taxonomic classification method")
    quality_col = header.index("MIUViG quality")
    length_col = header.index("Length")
    width = len(header)

    counters: dict[str, collections.Counter] = {
        name: collections.Counter()
        for name in (
            "method",
            "method_hc",
            "quality",
            "quality_hc",
            "length",
            "length_hc",
            "method_by_family_labelled",
            "method_by_order_labelled",
            "method_of_denylisted",
            "method_of_denylisted_hc",
            "family_labelled_by_method_hc",
            # Reference-flagged records cross-tabbed by assigning method. The release note
            # says sequences from NCBI RefSeq carry `Reference` in `MIUViG quality`, and
            # for those the ratified lineage is recoverable from the accession. A Reference
            # record whose label came from *looking the reference up* tests nothing — the
            # label and the ground truth are the same fact. One labelled by a predictor
            # is a gold-standard case: a real corpus record, with ground truth, scored by
            # the tool under test. Which of the two the corpus holds decides whether an
            # internal benchmark exists at all, so it is counted rather than assumed.
            "method_of_reference",
            "reference_family_labelled",
        )
    }
    rows = rows_hc = malformed = 0
    denylisted = denylisted_hc = 0
    client = objectstore.client()
    for line in objectstore.shard_lines(client, bucket, key, start, end, skip_header=(start == 0)):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != width:
            malformed += 1
            continue
        rows += 1
        method = fields[method_col].strip() or EMPTY
        quality = fields[quality_col].strip() or EMPTY
        conf = fields[idx["confidence"]].strip()
        high = conf == HIGH_CONFIDENCE
        try:
            length = int(fields[length_col].strip())
        except ValueError:
            length = -1
        lineage = _rank_depth(fields[idx["classification"]].strip())
        family = lineage.get("family", "")
        order = lineage.get("order", "")
        hit = (family and family in families) or (order and order in orders)

        counters["method"][method] += 1
        counters["quality"][quality] += 1
        if quality == REFERENCE:
            counters["method_of_reference"][method] += 1
            counters["reference_family_labelled"][
                f"{method}|{'labelled' if family else 'absent'}"
            ] += 1
        counters["length"][_stratum(length) if length >= 0 else "unparseable"] += 1
        if family:
            counters["method_by_family_labelled"][method] += 1
        if order:
            counters["method_by_order_labelled"][method] += 1
        if hit:
            denylisted += 1
            counters["method_of_denylisted"][method] += 1
        if high:
            rows_hc += 1
            counters["method_hc"][method] += 1
            counters["quality_hc"][quality] += 1
            counters["length_hc"][_stratum(length) if length >= 0 else "unparseable"] += 1
            counters["family_labelled_by_method_hc"][
                f"{method}|{'labelled' if family else 'absent'}"
            ] += 1
            if hit:
                denylisted_hc += 1
                counters["method_of_denylisted_hc"][method] += 1

    out: dict[str, Any] = {name: dict(c) for name, c in counters.items()}
    out.update(
        rows=rows,
        rows_hc=rows_hc,
        malformed=malformed,
        denylisted=denylisted,
        denylisted_hc=denylisted_hc,
    )
    return out


def _merge(shards: list[dict[str, Any]]) -> dict[str, Any]:
    scalar = ("rows", "rows_hc", "malformed", "denylisted", "denylisted_hc")
    out: dict[str, Any] = dict.fromkeys(scalar, 0)
    names = [k for k in shards[0] if k not in scalar]
    for name in names:
        merged: collections.Counter = collections.Counter()
        for shard in shards:
            merged.update(shard[name])
        out[name] = dict(merged)
    for shard in shards:
        for key in scalar:
            out[key] += shard[key]
    return out


def scan(bucket: str, prefix: str, date: str, *, workers: int, denylist: Denylist) -> dict:
    client = objectstore.client()
    rel = imgvr.release_on(date)
    name = next(
        f.name for f in rel.files if f.role == "sequence_information" and not f.high_confidence
    )
    key = f"{prefix}/imgvr/{date}/{name}"
    size = objectstore.S3RandomRead(client, bucket, key).size
    header = next(objectstore.shard_lines(client, bucket, key, 0, 8192)).split("\t")
    shards = objectstore.byte_shards(size, workers * 8)
    results: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _scan_shard,
                bucket,
                key,
                start,
                end,
                header,
                denylist.families,
                denylist.orders,
            )
            for start, end in shards
        ]
        for done in concurrent.futures.as_completed(futures):
            results.append(done.result())
    merged = _merge(results)
    merged["key"] = key
    merged["bytes"] = size
    merged["release"] = date
    merged["version"] = rel.version
    return merged


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def report(scanned: dict[str, Any], denylist: Denylist) -> dict[str, Any]:
    rows = scanned["rows"]
    rows_hc = scanned["rows_hc"]
    method = scanned["method"]
    method_hc = scanned["method_hc"]

    def with_shares(counts: dict[str, int], whole: int) -> dict[str, Any]:
        return {
            name: {
                "records": value,
                "share": _share(value, whole),
                "meaning": METHOD_MEANING.get(name, "not described by the publisher"),
            }
            for name, value in sorted(counts.items(), key=lambda kv: -kv[1])
        }

    denylisted_methods = scanned["method_of_denylisted"]
    genomad_of_denylisted = denylisted_methods.get("geNomad", 0)

    return {
        "task": TASK,
        "question": (
            "Which taxonomy assignment tool do the denylist rules depend on, and over what "
            "share of the records they decide?"
        ),
        "release": {
            "release": scanned["release"],
            "version": scanned["version"],
            "key": scanned["key"],
            "bytes": scanned["bytes"],
            "records": rows,
            "records_high_confidence": rows_hc,
            "malformed_rows": scanned["malformed"],
        },
        "denylist": {
            "policy": denylist.policy,
            "families": sorted(denylist.families),
            "orders": sorted(denylist.orders),
        },
        "method_mix": {
            "all_records": with_shares(method, rows),
            "after_confidence_gate": with_shares(method_hc, rows_hc),
            "of_records_labelled_at_family": with_shares(
                scanned["method_by_family_labelled"],
                sum(scanned["method_by_family_labelled"].values()),
            ),
            "of_records_labelled_at_order": with_shares(
                scanned["method_by_order_labelled"],
                sum(scanned["method_by_order_labelled"].values()),
            ),
        },
        "denylisted_records": {
            "records": scanned["denylisted"],
            "records_after_confidence_gate": scanned["denylisted_hc"],
            "share_of_release": _share(scanned["denylisted"], rows),
            "by_method": with_shares(denylisted_methods, scanned["denylisted"]),
            "by_method_after_gate": with_shares(
                scanned["method_of_denylisted_hc"], scanned["denylisted_hc"]
            ),
            "genomad_share": _share(genomad_of_denylisted, scanned["denylisted"]),
            "reading": (
                "This is the share of the denylist's own hits that rest on the tool A4.2 "
                "benchmarks. It is the number that makes the benchmark load-bearing: an "
                "error rate for geNomad propagates into the filter in proportion to it."
            ),
        },
        "quality": {
            "all_records": scanned["quality"],
            "after_confidence_gate": scanned["quality_hc"],
            "reference_flagged": scanned["quality"].get(REFERENCE, 0),
            "reference_by_method": with_shares(
                scanned["method_of_reference"], scanned["quality"].get(REFERENCE, 0)
            ),
            "reference_family_labelled": scanned["reference_family_labelled"],
            "reading": (
                "The release note says sequences from NCBI RefSeq are flagged 'Reference' in "
                "this field, so for those records the ratified lineage is recoverable from the "
                "accession. Whether that makes an internal benchmark possible depends on "
                "`reference_by_method`: a Reference record labelled by looking its own "
                "reference up tests nothing, because the label and the ground truth are one "
                "fact, while a Reference record labelled by a predictor is a real corpus "
                "record with trustworthy ground truth scored by the tool under test."
            ),
        },
        "length_distribution": {
            "edges": list(LENGTH_EDGES),
            "all_records": scanned["length"],
            "after_confidence_gate": scanned["length_hc"],
            "reading": (
                "The strata A4.2 reports its error rate over are taken from here. The "
                "evaluation set is built from complete reference genomes because that is "
                "where ground truth exists; this distribution is what the result has to be "
                "carried onto."
            ),
        },
        "family_label_by_method": scanned["family_labelled_by_method_hc"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI", ""))
    parser.add_argument("--release", default="2022-12-20")
    parser.add_argument("--policy", default="policies/specs/evo1-literal.yaml")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4)))
    parser.add_argument("--outdir", default="artifacts/a4-2")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    if not args.s3_uri.startswith("s3://"):
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI, as s3://bucket/prefix")
    bucket, prefix = objectstore.split_uri(args.s3_uri)

    policy = policyspec.load_policy(args.policy)
    denylist = Denylist.from_policy(policy, name=Path(args.policy).stem)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    with run(
        TASK,
        seed=SEED,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        # Distinct per step: three A4.2 pipelines write to this directory, and a shared
        # `run.json` means the last one silently erases the others' provenance. A1.5 hit this.
        manifest_name="run-dependency.json",
        durable=objectstore.durable_results("a4-2"),
    ) as manifest:
        manifest.parameter("release", args.release)
        manifest.parameter("policy", args.policy)
        manifest.parameter("length_edges", list(LENGTH_EDGES))
        manifest.parameter("high_confidence_value", HIGH_CONFIDENCE)
        manifest.input_file(args.policy, role="policy-spec")

        scanned = scan(bucket, prefix, args.release, workers=args.workers, denylist=denylist)
        manifest.input_url(
            f"s3://{bucket}/{scanned['key']}", role="imgvr/sequence_information", verified=False
        )
        built = report(scanned, denylist)
        path = outdir / "dependency.json"
        path.write_text(json.dumps(built, indent=1, sort_keys=False) + "\n")
        manifest.output_file(path, role="dependency")

    genomad = built["denylisted_records"]["genomad_share"]
    print(f"records: {built['release']['records']:,}")
    print(f"denylist hits: {built['denylisted_records']['records']:,}")
    print(f"of which geNomad-assigned: {genomad:.4%}" if genomad is not None else "no hits")
    print(f"Reference-flagged: {built['quality']['reference_flagged']:,}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

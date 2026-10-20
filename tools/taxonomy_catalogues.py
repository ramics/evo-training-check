#!/usr/bin/env python3
"""A4.4 — can the imported taxonomy catalogues the denylist depends on be benchmarked at all?

A4.2 benchmarked geNomad because geNomad is a tool this audit can run. Its dependency pass
then found that geNomad assigns a minority of the records Evo 1's denylist removes, and that
the largest single share comes from **RVMT** — a published metatranscriptome catalogue whose
taxonomy IMG/VR imported. D-091 says Phase A does not publish a leakage figure covering a
minority of the filter's hazard-relevant removals, so the remainder has to be measured or the
reason it cannot be has to be established from primary sources. This pass settles which.

A benchmark needs ground truth that is **independent of the thing being measured**. Inside
this corpus there is exactly one candidate: `MIUViG quality: Reference`, which the release
note gives to sequences taken from NCBI RefSeq and for which the ratified lineage is
recoverable from the accession. So for each assigning method the question is concrete and
countable: among the records the denylist actually removes, how many did that method label
*and* carry independent ground truth? A method with none cannot be scored here at any depth,
and establishing that is the result.

The pass also re-derives A4.2's headline counts from the same release, which is a free check
that the two tools read the corpus the same way.

    pixi run -e dev python tools/taxonomy_catalogues.py --s3-uri s3://$BUCKET/corpora
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import conformance, ictv, imgvr, objectstore, policyspec
from amazebio.misassignment import Denylist, rate
from amazebio.repro import ReproError, run

TASK = "A4.4"
SEED = 20261020

EMPTY = "(empty)"
REFERENCE = "Reference"
HIGH_CONFIDENCE = "High-confidence"

#: The VMR release the ratified-name check reads. The same one A4.2 benchmarks against, so
#: "ratified" means the same thing in both artefacts — a different MSL here would fold
#: taxonomic revision into the comparison, which is A9.1's subject and not this one's.
VMR_RELEASE = ictv.BENCHMARK_RELEASE

#: What each catalogue is, and what its own publisher says about how it assigned taxonomy.
#: Quoted rather than paraphrased where the wording carries the limit, because the
#: publisher's own hedge is the evidence this task reports in place of a number.
CATALOGUES: dict[str, dict[str, str]] = {
    "geNomad": {
        "what": "geNomad's marker-based taxonomic assignment (IMG/VR help page, approach ii)",
        "assigned_how": (
            "A classifier this audit can run, with a pinned version and a downloadable "
            "database. Its taxonomically informed markers were annotated from ICTV VMR 19 "
            "(S-GENOMAD-NATBIOTECH)."
        ),
        "benchmarkable": "yes — A4.2 scores it by direction with exact intervals",
    },
    "RVMT (doi:10.1101/2022.02.15.480533)": {
        "what": (
            "The RNA Virus MetaTranscriptomes catalogue (Neri et al. 2022, S-RVMT-CELL). "
            "IMG/VR imported its taxonomy; the method field cites it by its preprint doi."
        ),
        "assigned_how": (
            "Not a classifier. Of the catalogue's own contig set, 2,765 took ICTV labels by "
            "MEGA-BLAST against VMR MSL36 at identity >=98% and coverage >=95% both ways, and "
            "a further 6,878 took labels from NCBI NR. Every other label was *erected*: an "
            "approximate-maximum-likelihood RdRp tree, taxa propagated from the last common "
            "ancestor of labelled leaves, clades outside existing taxa dissected at a "
            "depth threshold and named as new taxa. Individual contigs were then affiliated "
            "to clusters through four similarity levels A-D."
        ),
        "publisher_hedge": (
            "The authors state only that they 'estimate that the majority contigs affiliated "
            "in this manner, would roughly share the same taxonomic ranks down to genus "
            "level'. No accuracy, no error rate, no interval. They also record that the "
            "assumption their procedure rests on — that existing taxonomy is non-contradictory "
            "with respect to the tree — 'is violated in multiple places', resolved mostly by "
            "stripping the conflicting labels."
        ),
        "benchmarkable": "to be established by this pass",
    },
    "NR (doi:10.5281/zenodo.6574914)": {
        "what": "similarity to viral proteins in NCBI NR (IMG/VR help page, approach iii)",
        "assigned_how": (
            "IMG/VR's own similarity search against a pinned NR subset. The database is "
            "pinned by doi; the search is the publisher's and is not re-runnable here."
        ),
        "benchmarkable": "to be established by this pass",
    },
    "vOTU consensus": {
        "what": "consensus of the other members of the UViG's vOTU (help page, approach iv)",
        "assigned_how": (
            "Inherited rather than assigned: the label comes from whatever labelled the "
            "other members of the cluster, so its error is theirs plus the clustering's."
        ),
        "benchmarkable": "to be established by this pass",
    },
    "vOTU with RefSeq genome": {
        "what": "clustering with RefSeq virus genomes (help page, approach i)",
        "assigned_how": (
            "The UViG shares a vOTU with a reference and takes the reference's taxonomy."
        ),
        "benchmarkable": "to be established by this pass",
    },
    "RefSeq": {
        "what": "not described by the publisher",
        "assigned_how": (
            "Undocumented. The release note says RefSeq-derived sequences carry `Reference` "
            "in MIUViG quality, so for these the label and any ground truth drawn from the "
            "same accession are one fact, not two."
        ),
        "benchmarkable": "circular by construction — see `assigned_how`",
    },
    "GVMAG (doi:10.1038/s41586-020-1957-x)": {
        "what": "giant virus metagenome-assembled genomes (Schulz et al. 2020)",
        "assigned_how": "Imported from the GVMAG study; not described by IMG/VR.",
        "benchmarkable": "to be established by this pass",
    },
    EMPTY: {
        "what": "no method recorded; these records carry no classification at all",
        "assigned_how": "n/a — nothing was assigned, so the denylist cannot read them.",
        "benchmarkable": "n/a",
    },
}


def _lineage(classification: str) -> dict[str, str]:
    """The lineage tag parsed to `{rank: name}`, through A7.1's single parser (D-057)."""
    return conformance.parse_lineage_tag(classification).taxonomy


def tally_rows(
    lines: Iterable[str],
    header: list[str],
    families: frozenset[str],
    orders: frozenset[str],
    ratified: frozenset[str],
) -> dict[str, Any]:
    """Tally a stream of release rows into counters.

    Separated from the shard reader so the counting rules can be tested against rows written
    by hand rather than only against a 5 GB object nothing can assert about cheaply.
    """
    idx = {role: header.index(name) for role, name in imgvr.SEQ_COLUMNS.items()}
    method_col = header.index("Taxonomic classification method")
    quality_col = header.index("MIUViG quality")
    width = len(header)

    names = (
        # Over the records the denylist removes, pre- and post-gate.
        "hits_by_method",
        "hits_by_method_hc",
        # The only independent ground truth inside the corpus, over those same records.
        "hits_reference_by_method",
        "hits_reference_by_method_hc",
        # Which rank the removal turned on. A removal on `order` is a coarser claim than one
        # on `family` and the two are not interchangeable evidence.
        "hits_rank_by_method",
        # The denylisted taxon each hit carries, per method: the parts list of what is being
        # removed on each catalogue's word.
        "hits_taxon_by_method",
        # Does the record's lineage carry any name the pinned VMR does not ratify? If a
        # catalogue's novel taxa reached IMG/VR, they show up here.
        "unratified_lineage_by_method",
        "method_all",
    )
    counters: dict[str, collections.Counter] = {n: collections.Counter() for n in names}
    rows = rows_hc = malformed = hits = hits_hc = 0
    for line in lines:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != width:
            malformed += 1
            continue
        rows += 1
        method = fields[method_col].strip() or EMPTY
        quality = fields[quality_col].strip() or EMPTY
        high = fields[idx["confidence"]].strip() == HIGH_CONFIDENCE
        counters["method_all"][method] += 1
        if high:
            rows_hc += 1

        lineage = _lineage(fields[idx["classification"]].strip())
        family = lineage.get("family", "")
        order = lineage.get("order", "")
        by_family = bool(family) and family in families
        by_order = bool(order) and order in orders
        if not (by_family or by_order):
            continue

        hits += 1
        counters["hits_by_method"][method] += 1
        counters["hits_rank_by_method"][
            f"{method}|{'family' if by_family else ''}{'+' if by_family and by_order else ''}"
            f"{'order' if by_order else ''}"
        ] += 1
        counters["hits_taxon_by_method"][f"{method}|{family if by_family else order}"] += 1
        if quality == REFERENCE:
            counters["hits_reference_by_method"][method] += 1
        if any(name and name not in ratified for name in lineage.values()):
            counters["unratified_lineage_by_method"][method] += 1
        if high:
            hits_hc += 1
            counters["hits_by_method_hc"][method] += 1
            if quality == REFERENCE:
                counters["hits_reference_by_method_hc"][method] += 1

    out: dict[str, Any] = {n: dict(c) for n, c in counters.items()}
    out.update(rows=rows, rows_hc=rows_hc, malformed=malformed, hits=hits, hits_hc=hits_hc)
    return out


def _scan_shard(
    bucket: str,
    key: str,
    start: int,
    end: int,
    header: list[str],
    families: frozenset[str],
    orders: frozenset[str],
    ratified: frozenset[str],
) -> dict[str, Any]:
    """Tally one byte shard. Runs in a subprocess; returns counters, never rows."""
    client = objectstore.client()
    lines = objectstore.shard_lines(client, bucket, key, start, end, skip_header=(start == 0))
    return tally_rows(lines, header, families, orders, ratified)


def _merge(shards: list[dict[str, Any]]) -> dict[str, Any]:
    scalar = ("rows", "rows_hc", "malformed", "hits", "hits_hc")
    out: dict[str, Any] = dict.fromkeys(scalar, 0)
    for shard in shards:
        for name in scalar:
            out[name] += shard[name]
        for name, counts in shard.items():
            if name in scalar:
                continue
            merged = out.setdefault(name, {})
            for key, value in counts.items():
                merged[key] = merged.get(key, 0) + value
    return out


def ratified_names(path: str | Path) -> frozenset[str]:
    """Every taxon name the pinned VMR ratifies, at every rank."""
    table = ictv.read_vmr(path)
    return frozenset(name for rank in ictv.RANKS for name in table.by_rank(rank) if name)


def scan(
    bucket: str,
    prefix: str,
    date: str,
    *,
    workers: int,
    denylist: Denylist,
    ratified: frozenset[str],
) -> dict[str, Any]:
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
                ratified,
            )
            for start, end in shards
        ]
        for done in concurrent.futures.as_completed(futures):
            results.append(done.result())
    merged = _merge(results)
    merged.update(key=key, bytes=size, release=date, version=rel.version)
    return merged


def _split(counts: dict[str, int], method: str) -> dict[str, int]:
    """The `method|value` counters, filtered to one method and stripped of the prefix."""
    return {
        key.split("|", 1)[1]: n
        for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if key.split("|", 1)[0] == method
    }


def report(scanned: dict[str, Any], denylist: Denylist, *, vmr: ictv.VMRRelease) -> dict[str, Any]:
    hits = scanned["hits"]
    hits_hc = scanned["hits_hc"]
    by_method = scanned["hits_by_method"]
    by_method_hc = scanned["hits_by_method_hc"]
    reference = scanned["hits_reference_by_method"]

    methods: list[dict[str, Any]] = []
    for method in sorted(by_method, key=lambda m: -by_method[m]):
        n = by_method[method]
        n_hc = by_method_hc.get(method, 0)
        n_ref = reference.get(method, 0)
        meta = CATALOGUES.get(method, {"what": "not described by the publisher"})
        taxa = _split(scanned["hits_taxon_by_method"], method)
        row: dict[str, Any] = {
            "method": method,
            "what": meta.get("what"),
            "assigned_how": meta.get("assigned_how"),
            "publisher_hedge": meta.get("publisher_hedge"),
            "hits": n,
            "share_of_hits": n / hits if hits else None,
            "hits_after_confidence_gate": n_hc,
            "share_of_hits_after_gate": n_hc / hits_hc if hits_hc else None,
            "removed_on_rank": _split(scanned["hits_rank_by_method"], method),
            "records_with_an_unratified_name_in_lineage": scanned[
                "unratified_lineage_by_method"
            ].get(method, 0),
            "denylisted_taxa": dict(list(taxa.items())[:25]),
            "distinct_denylisted_taxa": len(taxa),
            "independent_ground_truth_in_corpus": {
                "reference_flagged_hits": n_ref,
                "reference_flagged_hits_after_gate": scanned["hits_reference_by_method_hc"].get(
                    method, 0
                ),
            },
        }
        if method == "RefSeq":
            row["benchmarkable"] = "no"
            row["why"] = (
                "Circular. The release note says RefSeq-derived records carry `Reference`, so "
                "the label and any ground truth read off the same accession are one fact. "
                "Scoring it would measure a lookup against itself."
            )
        elif n_ref == 0:
            row["benchmarkable"] = "no"
            row["why"] = (
                f"No record this method labelled and the denylist removes carries independent "
                f"ground truth: {n:,} hits, none flagged `Reference`. The corpus holds no "
                "non-circular evaluation set for it at any depth, so the gap is a bound on "
                "this audit and not a measurement of the filter."
            )
        else:
            bound = rate(f"{method} reference-flagged share", n_ref, n)
            row["benchmarkable"] = "only at a depth that cannot carry a rate"
            row["why"] = (
                f"{n_ref} of {n:,} hits carry independent ground truth "
                f"({bound.point:.4%}, 95% CI [{bound.lower:.4%}, {bound.upper:.4%}]). An error "
                "rate over that many records has an interval spanning most of the range, and "
                "D-091 asks for a figure that covers the removals, not one that is precise "
                "about a handful of them."
            )
        methods.append(row)

    measured = sum(m["hits"] for m in methods if m["method"] == "geNomad")
    measured_hc = sum(m["hits_after_confidence_gate"] for m in methods if m["method"] == "geNomad")
    return {
        "task": TASK,
        "question": (
            "Of the records Evo 1's denylist removes, what share has a measured taxonomy error "
            "rate, and for the rest, why can one not be measured?"
        ),
        "release": {
            "release": scanned["release"],
            "version": scanned["version"],
            "key": scanned["key"],
            "bytes": scanned["bytes"],
            "records": scanned["rows"],
            "records_high_confidence": scanned["rows_hc"],
            "malformed_rows": scanned["malformed"],
        },
        "ratified_against": {
            "release": vmr.msl,
            "file": vmr.filename,
            "sha256": vmr.sha256,
            "published": vmr.published,
        },
        "denylist": {
            "policy": denylist.policy,
            "families": sorted(denylist.families),
            "orders": sorted(denylist.orders),
        },
        "denylisted_records": {
            "records": hits,
            "records_after_confidence_gate": hits_hc,
        },
        "methods": methods,
        "coverage": {
            "measured_methods": ["geNomad"],
            "hits_with_a_measured_error_rate": measured,
            "share_of_hits": measured / hits if hits else None,
            "hits_with_a_measured_error_rate_after_gate": measured_hc,
            "share_of_hits_after_gate": measured_hc / hits_hc if hits_hc else None,
            "reading_this": (
                "The confidence gate runs before the denylist (A4.1, D-081), so the share "
                "after the gate is the share of the removals the filter actually makes. It is "
                "the figure D-091's commitment should be read against."
            ),
        },
    }


def summarise(doc: dict[str, Any]) -> str:
    cov = doc["coverage"]
    d = doc["denylisted_records"]
    lines = [
        "# A4.4 — the taxonomy catalogues the denylist depends on",
        "",
        f"IMG/VR {doc['release']['version']} ({doc['release']['release']}), "
        f"{doc['release']['records']:,} records. Denylist: `{doc['denylist']['policy']}`.",
        f"Ratified names checked against ICTV {doc['ratified_against']['release']} "
        f"({doc['ratified_against']['file']}).",
        "",
        f"The denylist removes **{d['records']:,}** records, "
        f"**{d['records_after_confidence_gate']:,}** of them after the confidence gate that "
        "runs before it. The gated figure is the one the filter actually acts on.",
        "",
        "| catalogue | hits | share | after gate | share | ground truth | benchmarkable |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in doc["methods"]:
        gt = m["independent_ground_truth_in_corpus"]["reference_flagged_hits"]
        lines.append(
            f"| {m['method']} | {m['hits']:,} | {m['share_of_hits']:.2%} | "
            f"{m['hits_after_confidence_gate']:,} | {m['share_of_hits_after_gate']:.2%} | "
            f"{gt:,} | {m['benchmarkable']} |"
        )
    lines += [
        "",
        f"**Coverage.** A measured error rate exists for {cov['share_of_hits']:.2%} of the "
        f"removals before the gate and **{cov['share_of_hits_after_gate']:.2%}** after it.",
        "",
        "## Why the rest cannot be measured",
        "",
    ]
    for m in doc["methods"]:
        if m["benchmarkable"] == "yes — A4.2 scores it by direction with exact intervals":
            continue
        lines.append(f"**{m['method']}** — {m['why']}")
        if m.get("publisher_hedge"):
            lines.append("")
            lines.append(f"> {m['publisher_hedge']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI", ""))
    parser.add_argument("--release", default="2022-12-20")
    parser.add_argument("--policy", default="policies/specs/evo1-literal.yaml")
    parser.add_argument("--vmr", required=True, help="the pinned VMR workbook, verified by digest")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4)))
    parser.add_argument("--outdir", default="artifacts/a4-4")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)

    if not args.s3_uri.startswith("s3://"):
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI, as s3://bucket/prefix")
    bucket, prefix = objectstore.split_uri(args.s3_uri)

    vmr = ictv.release(VMR_RELEASE)
    policy = policyspec.load_policy(args.policy)
    denylist = Denylist.from_policy(policy, name=Path(args.policy).stem)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        with run(
            TASK,
            seed=SEED,
            outdir=outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-catalogues.json",
            durable=objectstore.durable_results("a4-4"),
        ) as manifest:
            manifest.parameter("release", args.release)
            manifest.parameter("policy", args.policy)
            manifest.parameter("vmr_release", VMR_RELEASE)
            manifest.parameter("high_confidence_value", HIGH_CONFIDENCE)
            manifest.parameter("reference_quality_value", REFERENCE)
            manifest.input_file(args.policy, role="policy-spec")
            manifest.input_file(args.vmr, role="ictv-vmr")

            ratified = ratified_names(args.vmr)
            manifest.parameter("ratified_names", len(ratified))
            scanned = scan(
                bucket,
                prefix,
                args.release,
                workers=args.workers,
                denylist=denylist,
                ratified=ratified,
            )
            manifest.input_url(
                f"s3://{bucket}/{scanned['key']}",
                role="imgvr/sequence_information",
                verified=False,
            )
            built = report(scanned, denylist, vmr=vmr)

            path = outdir / "catalogues.json"
            path.write_text(json.dumps(built, indent=1, sort_keys=False) + "\n")
            manifest.output_file(path, role="catalogues")

            md = outdir / "catalogues.md"
            md.write_text(summarise(built))
            manifest.output_file(md, role="summary")

            cov = built["coverage"]
            manifest.note(
                f"A measured error rate covers {cov['share_of_hits_after_gate']:.2%} of the "
                "removals the denylist actually makes. The rest is bounded by what the "
                "importing catalogues published about themselves."
            )
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.show:
        print((outdir / "catalogues.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

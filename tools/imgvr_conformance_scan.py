#!/usr/bin/env python3
"""Reduce a staged IMG/VR release to the sufficient statistic A7.2's conformance diff needs.

The expensive half of A7.2, and — like A7.1's scan — deliberately the half that decides nothing.
It reads 5.7 GB of metadata per release and emits a few megabytes: per taxonomic
classification, how many records carry it, how many are high-confidence, and how many host
findings it has under each of the three countable readings of "found within a prokaryotic host
at least twice". The diff then re-executes each published reading of the policy against that
artefact in a second, which is what makes the headline numbers reproducible from a published
intermediate rather than from a re-run of this pass, and what lets A3.3's second implementation
check them without touching a corpus.

**Why the classification is the key.** Every record-level rule the published procedure contains
is a function of the taxonomic classification and the confidence label alone — including the
host rule, whose count is built over the classification and joined back to the record (D-058).
So a table of counts keyed by (classification, confidence) carries everything the rules can
read, exactly, and losing the per-record detail loses nothing a predicate could have acted on.
That is what makes a small artefact an honest one here rather than a summary.

**The vOTU rule does not reduce that way, and is not made to.** It keeps one representative per
vOTU, and which record that is depends on an input order nobody published (D-017). So this pass
emits the vOTU structure instead of a vOTU verdict: for each vOTU, which classifications its
high-confidence records carry, aggregated into the classifications that own a vOTU outright and
the signatures of the ones that do not. `amazebio.conformance.votu_bounds` turns that into the
interval the published chain actually determines, and `votu_comparison` compares it at vOTU
level against what was released. Neither is a record-level conformance rate and the artefact
never calls them one.

**No sequence is read.** The nucleotide and protein sets are not staged and answer no
conformance question (D-053). This pass reads two TSVs of metadata and holds no base.

    python3 tools/imgvr_conformance_scan.py --release 2022-09-20
    python3 tools/imgvr_conformance_scan.py --release 2022-09-20 --evo2-accessions a.npy
    python3 tools/imgvr_conformance_scan.py --release 2022-09-20 --max-rows 200000  # smoke
"""

from __future__ import annotations

import argparse
import array
import collections
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import conformance as cf
from amazebio import imgvr, objectstore
from amazebio.repro import run

#: Host classes, in the order their columns appear in the per-classification count matrix.
#: `None` — no usable prediction — is counted as its own column rather than omitted: a record
#: with no host assignment is the population the host rule's classification-level reading exists
#: to explain, and D-058 puts 89.5% of Evo 1's retained records in it.
HOST_CLASSES = ("prokaryotic", "eukaryotic", "other", "none")

#: Columns of the per-classification matrix each worker returns.
COLS = (
    "records",
    "records_hc",
    *(f"seqcol_{c}" for c in HOST_CLASSES),
    *(f"seqcol_hc_{c}" for c in HOST_CLASSES),
)

#: How many distinct taxonomic classifications the pass will carry before it stops. A tripwire,
#: not a budget: the classification is a controlled vocabulary of viral lineages, and blowing
#: through this means the column is not what it was read to be and the artefact should not be
#: emitted until somebody has looked.
MAX_DISTINCT_CLASSIFICATIONS = 200_000

#: And how many distinct mixed-classification vOTU signatures. Same logic. A vOTU whose
#: high-confidence records disagree about taxonomy is the interesting minority; if it turns out
#: to be the majority, the vOTU interval will be wide and that is a finding to state rather than
#: a histogram to emit.
MAX_MIXED_SIGNATURES = 200_000


def _np() -> Any:
    import numpy as np

    return np


# --------------------------------------------------------------------------------------
# The sequence-information pass
# --------------------------------------------------------------------------------------


def _scan_seq_shard(
    bucket: str, key: str, start: int, end: int, header: list[str], max_rows: int | None
) -> dict[str, Any]:
    """Reduce one byte shard of the sequence-information table. Runs in a subprocess.

    Returns arrays rather than a parse: the vOTU grouping and both joins are global operations
    the parent has to do once over the whole release, and shipping five narrow columns back is
    cheaper than shipping the strings they were read from.
    """
    np = _np()
    idx = {role: header.index(name) for role, name in imgvr.SEQ_COLUMNS.items()}
    width = len(header)
    classes: dict[str, int] = {}
    # One typed array per column rather than a list of tuples. At a million rows a shard the
    # tuple overhead is the difference between a pass that fits in this container and one that
    # does not, and four shards run at once.
    col_uvig = array.array("q")
    col_votu = array.array("i")
    col_cid = array.array("i")
    col_hc = array.array("b")
    col_hclass = array.array("b")
    n_rows = 0
    malformed = 0
    bad_accessions: collections.Counter = collections.Counter()
    # The accessions that do not pack, kept as strings. A small vocabulary — the GVMAG shape is
    # a fraction of a percent of the database — and the parent checks that hashing them into
    # join keys lost nothing.
    fallback: set[str] = set()
    confidence: collections.Counter = collections.Counter()
    host_domains: collections.Counter = collections.Counter()

    client = objectstore.client()
    for line in objectstore.shard_lines(client, bucket, key, start, end, skip_header=(start == 0)):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != width:
            # Counted, never dropped silently: a row the publisher emitted that does not fit
            # its own header is exactly what D-063's erratum note leads one to expect.
            malformed += 1
            continue
        conf = fields[idx["confidence"]].strip()
        confidence[conf] += 1
        host_field = fields[idx["host"]]
        host_domains[imgvr.host_domain(host_field)] += 1
        classification = fields[idx["classification"]].strip()
        cid = classes.setdefault(classification, len(classes))
        raw_uvig = fields[idx["uvig"]].strip()
        try:
            uvig = imgvr.uvig_join_key(raw_uvig)
            votu = imgvr.votu_id(fields[idx["votu"]])
        except ValueError:
            # Not a second accession shape but a row whose identifiers this audit cannot read at
            # all. Counted with an example and excluded from the arrays; the parent reports the
            # count beside every number the pass produces, because a record missing from a join
            # is a record missing from the converse direction.
            bad_accessions[raw_uvig[:64]] += 1
            continue
        if uvig < 0:
            fallback.add(raw_uvig)
        col_uvig.append(uvig)
        col_votu.append(votu)
        col_cid.append(cid)
        col_hc.append(1 if conf == "High-confidence" else 0)
        col_hclass.append(HOST_CLASSES.index(imgvr.host_class(host_field) or "none"))
        n_rows += 1
        if max_rows is not None and n_rows >= max_rows:
            break

    return {
        "classes": [c for c, _ in sorted(classes.items(), key=lambda kv: kv[1])],
        "uvig": np.frombuffer(col_uvig, dtype=np.int64).copy(),
        "votu": np.frombuffer(col_votu, dtype=np.int32).copy(),
        "cid": np.frombuffer(col_cid, dtype=np.int32).copy(),
        "hc": np.frombuffer(col_hc, dtype=np.int8).copy(),
        "hclass": np.frombuffer(col_hclass, dtype=np.int8).copy(),
        "malformed": malformed,
        "bad_accessions": dict(bad_accessions),
        "fallback": sorted(fallback),
        "confidence": dict(confidence),
        "host_domains": dict(host_domains),
    }


def _scan_host_shard(
    bucket: str, key: str, start: int, end: int, header: list[str]
) -> dict[str, Any]:
    """Reduce one byte shard of the host-information table. Runs in a subprocess."""
    np = _np()
    idx = {role: header.index(name) for role, name in imgvr.HOST_COLUMNS.items()}
    width = len(header)
    taxa: dict[str, int] = {}
    col_uvig = array.array("q")
    col_hclass = array.array("b")
    col_tid = array.array("i")
    n_rows = 0
    malformed = 0
    bad_accessions: collections.Counter = collections.Counter()
    fallback: set[str] = set()
    methods: collections.Counter = collections.Counter()

    client = objectstore.client()
    for line in objectstore.shard_lines(client, bucket, key, start, end, skip_header=(start == 0)):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != width:
            malformed += 1
            continue
        methods[fields[idx["method"]].strip()] += 1
        host_field = fields[idx["host"]]
        hclass = imgvr.host_class(host_field)
        taxon = host_field.strip()
        tid = taxa.setdefault(taxon, len(taxa))
        raw_uvig = fields[idx["uvig"]].strip()
        try:
            uvig = imgvr.uvig_join_key(raw_uvig)
        except ValueError:
            bad_accessions[raw_uvig[:64]] += 1
            continue
        if uvig < 0:
            fallback.add(raw_uvig)
        col_uvig.append(uvig)
        col_hclass.append(HOST_CLASSES.index(hclass or "none"))
        col_tid.append(tid)
        n_rows += 1

    return {
        "taxa": [t for t, _ in sorted(taxa.items(), key=lambda kv: kv[1])],
        "uvig": np.frombuffer(col_uvig, dtype=np.int64).copy(),
        "hclass": np.frombuffer(col_hclass, dtype=np.int8).copy(),
        "tid": np.frombuffer(col_tid, dtype=np.int32).copy(),
        "malformed": malformed,
        "bad_accessions": dict(bad_accessions),
        "fallback": sorted(fallback),
        "methods": dict(methods),
        "rows": n_rows + malformed,
    }


def _read_header(client: Any, bucket: str, key: str) -> list[str]:
    """The first line of a staged TSV, read as one small range request."""
    body = client.get_object(Bucket=bucket, Key=key, Range="bytes=0-65535")["Body"].read()
    line = body.split(b"\n", 1)[0]
    return line.decode("utf-8").rstrip("\r").split("\t")


def _shards(client: Any, bucket: str, key: str, workers: int) -> list[tuple[int, int]]:
    size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    # Eight shards per worker: progress prints before the first worker finishes its share,
    # and each shard's typed columns stay small enough that four at once fit in memory.
    return objectstore.byte_shards(size, max(workers * 8, 1))


def _run_shards(fn: Any, bucket: str, key: str, args: Any, extra: tuple, label: str) -> list[dict]:
    client = objectstore.client()
    header = _read_header(client, bucket, key)
    shards = _shards(client, bucket, key, args.workers)
    print(f"[imgvr] {label}: {len(shards)} shards over {len(header)} columns", flush=True)
    out: list[dict] = []
    started = last = time.time()
    with ProcessPoolExecutor(max_workers=min(args.workers, len(shards))) as pool:
        futures = {pool.submit(fn, bucket, key, s, e, header, *extra): (s, e) for s, e in shards}
        for fut in as_completed(futures):
            out.append(fut.result())
            if time.time() - last >= args.progress_seconds:
                last = time.time()
                print(
                    f"[imgvr] {label}: {len(out)}/{len(shards)} shards  "
                    f"{time.time() - started:,.0f}s",
                    flush=True,
                )
    print(f"[imgvr] {label}: done in {time.time() - started:,.0f}s", flush=True)
    return out


# --------------------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------------------


def _merge_vocabulary(shards: list[dict], field: str) -> tuple[list[str], list[Any]]:
    """One global vocabulary, and a per-shard local->global id map."""
    np = _np()
    vocab: dict[str, int] = {}
    maps = []
    for shard in shards:
        maps.append(
            np.array([vocab.setdefault(v, len(vocab)) for v in shard[field]], dtype=np.int64)
        )
    return [v for v, _ in sorted(vocab.items(), key=lambda kv: kv[1])], maps


def _accession_shapes(shards: list[dict]) -> dict[str, Any]:
    """What the accessions in one pass looked like, and whether the join key kept them apart.

    IMG/VR ships two accession shapes and the second one matters more than its size suggests:
    `IMGVR_UViG_GVMAG-<M|S>-<oid>-<n>_<m>` identifies a giant-virus metagenome-assembled
    genome, and giant viruses infect eukaryotes — the very population a filter aimed at
    eukaryote-infecting viruses is judged on. An earlier draft of this pass packed only the
    numeric shape and dropped the rest from both joins, which would have removed those records
    from the converse direction silently. They are carried under hashed keys instead, and the
    hash is verified injective here rather than assumed to be.
    """
    fallback = sorted({a for s in shards for a in s["fallback"]})
    bad: collections.Counter = sum(
        (collections.Counter(s["bad_accessions"]) for s in shards), collections.Counter()
    )
    ok, n_accessions, n_keys = imgvr.collision_free(fallback)
    if not ok:
        raise RuntimeError(
            f"the join key is not injective on the {n_accessions:,} non-packable accessions: "
            f"{n_keys:,} distinct keys. Two records would merge in every join; fix the "
            "encoding before emitting an artefact."
        )
    return {
        "packed": True,
        "non_packable_accessions": n_accessions,
        "non_packable_examples": fallback[:20],
        "join_key_injective_on_non_packable": ok,
        "unreadable_accessions": int(sum(bad.values())),
        "unreadable_examples": dict(bad.most_common(20)),
    }


def merge(seq_shards: list[dict], host_shards: list[dict], evo2_keys: Any | None) -> dict[str, Any]:
    """Assemble the per-classification sufficient statistic from the shard results."""
    np = _np()

    classifications, cmaps = _merge_vocabulary(seq_shards, "classes")
    n_class = len(classifications)
    if n_class > MAX_DISTINCT_CLASSIFICATIONS:
        raise RuntimeError(
            f"{n_class:,} distinct taxonomic classifications, over the "
            f"{MAX_DISTINCT_CLASSIFICATIONS:,} tripwire. The column is not the controlled "
            "vocabulary it was read to be; characterise it before emitting an artefact."
        )

    uvig = np.concatenate([s["uvig"] for s in seq_shards])
    votu = np.concatenate([s["votu"] for s in seq_shards])
    cid = np.concatenate([cmaps[i][s["cid"]] for i, s in enumerate(seq_shards)]).astype(np.int64)
    hc = np.concatenate([s["hc"] for s in seq_shards]).astype(bool)
    hclass = np.concatenate([s["hclass"] for s in seq_shards]).astype(np.int64)

    records = len(uvig)
    counts = {
        "records": np.bincount(cid, minlength=n_class),
        "records_hc": np.bincount(cid[hc], minlength=n_class),
    }
    for i, name in enumerate(HOST_CLASSES):
        sel = hclass == i
        counts[f"seqcol_{name}"] = np.bincount(cid[sel], minlength=n_class)

    # ---- the host table, joined back by accession -------------------------------------
    order = np.argsort(uvig, kind="stable")
    sorted_uvig = uvig[order]
    duplicate_accessions = int(records - len(np.unique(sorted_uvig)))

    host_taxa, tmaps = _merge_vocabulary(host_shards, "taxa")
    host_rows_by_class: dict[str, Any] = {}
    host_taxa_by_class: dict[str, Any] = {}
    host_records_by_class: dict[str, Any] = {}
    host_unmatched = 0
    if host_shards:
        h_uvig = np.concatenate([s["uvig"] for s in host_shards])
        h_class = np.concatenate([s["hclass"] for s in host_shards]).astype(np.int64)
        h_tid = np.concatenate([tmaps[i][s["tid"]] for i, s in enumerate(host_shards)])
        pos = np.searchsorted(sorted_uvig, h_uvig)
        pos_clipped = np.clip(pos, 0, max(len(sorted_uvig) - 1, 0))
        matched = (len(sorted_uvig) > 0) & (sorted_uvig[pos_clipped] == h_uvig)
        host_unmatched = int((~matched).sum())
        h_cid = np.where(matched, cid[order[pos_clipped]], -1)
        for i, name in enumerate(HOST_CLASSES):
            sel = matched & (h_class == i)
            host_rows_by_class[name] = np.bincount(h_cid[sel], minlength=n_class)
            # Distinct host taxa per classification, and distinct records per classification:
            # both are counts of unique pairs, which is what makes them different readings of
            # the same sentence rather than the same number twice.
            pairs = np.unique(np.stack([h_cid[sel], h_tid[sel]], axis=1), axis=0)
            host_taxa_by_class[name] = (
                np.bincount(pairs[:, 0], minlength=n_class)
                if len(pairs)
                else np.zeros(n_class, dtype=np.int64)
            )
            rec_pairs = np.unique(np.stack([h_cid[sel], h_uvig[sel]], axis=1), axis=0)
            host_records_by_class[name] = (
                np.bincount(rec_pairs[:, 0], minlength=n_class)
                if len(rec_pairs)
                else np.zeros(n_class, dtype=np.int64)
            )

    # ---- the vOTU structure over high-confidence records ------------------------------
    hv, hcid = votu[hc].astype(np.int64), cid[hc]
    pairs = np.unique(np.stack([hv, hcid], axis=1), axis=0)
    votus_hc = np.unique(hv)
    per_votu = np.bincount(np.searchsorted(votus_hc, pairs[:, 0]), minlength=len(votus_hc))
    single_mask = per_votu == 1
    single_votus = votus_hc[single_mask]
    single_pairs = pairs[np.isin(pairs[:, 0], single_votus)]
    votu_single = np.bincount(single_pairs[:, 1], minlength=n_class)

    mixed_votus = votus_hc[~single_mask]
    mixed_signatures: collections.Counter = collections.Counter()
    if len(mixed_votus):
        mixed_pairs = pairs[np.isin(pairs[:, 0], mixed_votus)]
        by_votu: dict[int, list[int]] = collections.defaultdict(list)
        for v, c in mixed_pairs:
            by_votu[int(v)].append(int(c))
        for sig in by_votu.values():
            mixed_signatures[tuple(sorted(sig))] += 1
    if len(mixed_signatures) > MAX_MIXED_SIGNATURES:
        raise RuntimeError(
            f"{len(mixed_signatures):,} distinct mixed-classification vOTU signatures, over "
            f"the {MAX_MIXED_SIGNATURES:,} tripwire. Report the structure in prose rather than "
            "emitting a histogram this size."
        )

    # ---- Evo 2's released accessions, joined record by record -------------------------
    evo2: dict[str, Any] | None = None
    if evo2_keys is not None:
        released = np.isin(uvig, evo2_keys)
        in_imgvr = np.isin(evo2_keys, uvig)
        released_by_class = np.bincount(cid[released], minlength=n_class)
        released_hc_by_class = np.bincount(cid[released & hc], minlength=n_class)
        # Released records per vOTU, over vOTUs that have at least one high-confidence record:
        # the unit the vOTU rule claims, and the only unit at which it can be checked.
        rel_per_votu = np.bincount(
            np.searchsorted(votus_hc, votu[released & np.isin(votu, votus_hc)]),
            minlength=len(votus_hc),
        )
        single_class_of = np.full(len(votus_hc), -1, dtype=np.int64)
        # `pairs` comes back from np.unique lexicographically sorted, and votus_hc is sorted,
        # so the single-classification pairs already line up with votus_hc[single_mask].
        single_class_of[single_mask] = single_pairs[:, 1]
        hist_single: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
        for c, n in zip(single_class_of[single_mask], rel_per_votu[single_mask], strict=True):
            hist_single[int(c)][int(n)] += 1
        hist_mixed: collections.Counter = collections.Counter()
        for n in rel_per_votu[~single_mask]:
            hist_mixed[int(n)] += 1
        # The host class of each released record, exactly. Evo 1's own Figure S1B puts 89.5% of
        # its retained records at an unknown host kingdom, which is what forced the host rule's
        # unit to be the classification rather than the record (D-058). Evo 1's release carries
        # no accession, so that distribution cannot be recomputed for it; Evo 2's can, and it is
        # the only exact check of the same phenomenon available anywhere in this audit.
        released_host = {
            name: int((released & (hclass == i)).sum()) for i, name in enumerate(HOST_CLASSES)
        }
        evo2 = {
            "released_host_classes": released_host,
            "released_records_joined": int(released.sum()),
            "released_accessions": int(len(evo2_keys)),
            "released_accessions_found_in_imgvr": int(in_imgvr.sum()),
            "released_accessions_absent_from_imgvr": int((~in_imgvr).sum()),
            "released_by_classification": released_by_class,
            "released_hc_by_classification": released_hc_by_class,
            # Keyed by the classification itself, not by its index in this pass's vocabulary:
            # the diff joins these against rule verdicts keyed by classification, and an index
            # would silently match nothing and report a clean vOTU comparison.
            "votu_released_histogram_single": {
                classifications[c]: {str(k): v for k, v in sorted(h.items())}
                for c, h in hist_single.items()
            },
            "votu_released_histogram_mixed": {str(k): v for k, v in sorted(hist_mixed.items())},
        }

    def per_class(name: str, vec: Any) -> dict[str, int]:
        return {classifications[i]: int(vec[i]) for i in range(n_class) if vec[i]}

    doc: dict[str, Any] = {
        "records": records,
        "distinct_classifications": n_class,
        "distinct_votus": int(len(np.unique(votu))),
        "distinct_votus_high_confidence": int(len(votus_hc)),
        "records_high_confidence": int(hc.sum()),
        "duplicate_accessions": duplicate_accessions,
        "malformed_rows": sum(s["malformed"] for s in seq_shards),
        "accession_shapes": _accession_shapes(seq_shards),
        "confidence": dict(
            sum((collections.Counter(s["confidence"]) for s in seq_shards), collections.Counter())
        ),
        "host_domains": dict(
            sum((collections.Counter(s["host_domains"]) for s in seq_shards), collections.Counter())
        ),
        "host_table": {
            "rows": sum(s["rows"] for s in host_shards),
            "malformed_rows": sum(s["malformed"] for s in host_shards),
            "accession_shapes": _accession_shapes(host_shards),
            "rows_not_matching_a_sequence_record": host_unmatched,
            "distinct_host_taxa": len(host_taxa),
            "methods": dict(
                sum(
                    (collections.Counter(s["methods"]) for s in host_shards),
                    collections.Counter(),
                )
            ),
        },
        "by_classification": {
            classifications[i]: {
                "records": int(counts["records"][i]),
                "records_hc": int(counts["records_hc"][i]),
                "seq_column_host": {
                    name: int(counts[f"seqcol_{name}"][i])
                    for name in HOST_CLASSES
                    if counts[f"seqcol_{name}"][i]
                },
                "host_findings": {
                    name: {
                        cf.HostUnit.RECORDS.value: int(host_records_by_class[name][i])
                        if host_records_by_class
                        else 0,
                        cf.HostUnit.HOST_ROWS.value: int(host_rows_by_class[name][i])
                        if host_rows_by_class
                        else 0,
                        cf.HostUnit.HOST_TAXA.value: int(host_taxa_by_class[name][i])
                        if host_taxa_by_class
                        else 0,
                    }
                    for name in HOST_CLASSES
                    if host_rows_by_class and host_rows_by_class[name][i]
                },
                "votus_owned_outright": int(votu_single[i]),
            }
            for i in range(n_class)
        },
        "votu_structure": {
            "high_confidence_votus": int(len(votus_hc)),
            "votus_with_one_classification": int(single_mask.sum()),
            "votus_with_several_classifications": int((~single_mask).sum()),
            "mixed_signatures": [
                {"classifications": [classifications[c] for c in sig], "votus": n}
                for sig, n in sorted(mixed_signatures.items(), key=lambda kv: -kv[1])
            ],
            "why_it_is_emitted_as_structure": (
                "The vOTU rule keeps one representative per vOTU and no published source states "
                "the input order, so which record survives is undetermined (D-017). What is "
                "determined is the count per vOTU, and the interval the retained total can lie "
                "in given which classifications survive the later rules. A vOTU whose "
                "high-confidence records carry one classification contributes to that interval "
                "without widening it; the signatures above are the ones that widen it."
            ),
        },
        "host_unit_readings": {u.value: text for u, text in cf.HOST_UNITS.items()},
        "primary_host_unit": cf.PRIMARY_HOST_UNIT.value,
    }
    if evo2 is not None:
        doc["evo2"] = {
            k: (per_class(k, v) if k.startswith("released") and hasattr(v, "shape") else v)
            for k, v in evo2.items()
        }
    return doc


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", choices=sorted(imgvr.RELEASES), required=True)
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--outdir", default=None, help="default: artifacts/a7-2/<release>")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--progress-seconds", type=float, default=30.0)
    ap.add_argument(
        "--evo2-accessions",
        default=None,
        help="path to the packed accession inventory of Evo 2's released IMG/VR component, "
        "from tools/evo2_accessions.py. Without it the Evo 2 arm is not run.",
    )
    ap.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="stop each shard after N rows — a smoke run, never a result; the artefact "
        "records that it was partial",
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, prefix = objectstore.split_uri(args.s3_uri)
    outdir = Path(args.outdir or f"artifacts/a7-2/{args.release}")
    release = imgvr.release_on(args.release)

    seq = next(
        f for f in release.files if f.role == "sequence_information" and not f.high_confidence
    )
    host = next(f for f in release.files if f.role == "host_information" and not f.high_confidence)
    keys = {
        "sequence_information": f"{prefix}/imgvr/{args.release}/{seq.name}",
        "host_information": f"{prefix}/imgvr/{args.release}/{host.name}",
    }

    evo2_keys = None
    if args.evo2_accessions:
        np = _np()
        evo2_keys = np.load(args.evo2_accessions)

    with run(
        "A7.2",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-input-scan-{args.release}.json",
    ) as m:
        m.parameter("release", args.release)
        m.parameter("version", release.version)
        m.parameter("primary_host_unit", cf.PRIMARY_HOST_UNIT.value)
        m.parameter("host_classes", list(HOST_CLASSES))
        m.parameter("workers", args.workers)
        m.parameter("max_rows", args.max_rows)
        m.parameter("evo2_arm", bool(args.evo2_accessions))
        m.note(
            "Metadata only. No nucleotide or protein file is read and no base enters the "
            "artefact (D-053)."
        )
        m.note(
            "The counting unit of the host rule is declared before the pass rather than chosen "
            f"after it: {cf.PRIMARY_HOST_UNIT.value} is primary, the other two readings travel "
            "with it as a sensitivity. See D-058 for why the unit is the classification and not "
            "the record."
        )
        for role, key in keys.items():
            f = seq if role == "sequence_information" else host
            m.input_url(
                f"s3://{bucket}/{key}",
                role=role,
                bytes=f.bytes,
                checksum=f.md5,
                checksum_type="md5",
                verified=False,
            )
        if args.evo2_accessions:
            m.input_file(Path(args.evo2_accessions), role="evo2-accession-inventory")

        seq_shards = _run_shards(
            _scan_seq_shard,
            bucket,
            keys["sequence_information"],
            args,
            (args.max_rows,),
            "sequence_information",
        )
        host_shards = _run_shards(
            _scan_host_shard, bucket, keys["host_information"], args, (), "host_information"
        )
        doc = merge(seq_shards, host_shards, evo2_keys)
        doc["release"] = args.release
        doc["version"] = release.version
        doc["partial"] = bool(args.max_rows)
        doc["files"] = {
            role: {"key": key, "md5": (seq if "sequence" in role else host).md5}
            for role, key in keys.items()
        }

        out = outdir / f"input-scan-{args.release}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="input-scan")
        print(
            f"[imgvr] {doc['records']:,} records, {doc['distinct_classifications']:,} "
            f"classifications, {doc['distinct_votus_high_confidence']:,} high-confidence vOTUs "
            f"-> {out}",
            flush=True,
        )
        m.note(
            f"{doc['records']:,} records reduced to {doc['distinct_classifications']:,} "
            "taxonomic classifications, which is the sufficient statistic for every "
            "record-level rule in the published procedure."
        )

        if args.upload_results:
            client = objectstore.client()
            key = f"{prefix}/results/a7-2/input-scan-{args.release}.json"
            payload = out.read_bytes()
            client.put_object(Bucket=bucket, Key=key, Body=payload)
            m.output_object(f"s3://{bucket}/{key}", bytes=len(payload), role="input-scan")
            manifest = outdir / f"run-input-scan-{args.release}.json"
            m.write(manifest)
            client.put_object(
                Bucket=bucket,
                Key=key.replace("input-scan-", "run-input-scan-"),
                Body=manifest.read_bytes(),
            )
            print(f"[imgvr] uploaded s3://{bucket}/{key}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

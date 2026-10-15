#!/usr/bin/env python3
"""Inventory the accessions in Evo 2's released IMG/VR component — the join key A7.2 needs.

Evo 2's release of the viral component is the exact inverse of Evo 1's: its FASTA headers carry
the IMG/VR accession and no taxonomic lineage, where Evo 1's rows carry a lineage and no
accession (D-049). So no published rule can be re-executed against Evo 2's release on its own,
and A7.1 established that from a bounded 2,000-header read and stopped there, because nothing
then consumed the inventory.

With IMG/VR v4 staged (A1.7), the accession becomes a record-level join key and both directions
of the conformance check open for Evo 2 — which is what this pass exists to supply. Note what is
being audited and what is being compared: the *procedure* is Evo 1's, restated by reference in
Evo 2 ("As previously described"), and the *output* is Evo 2's own release. Those are two
different artefacts and the write-up says so rather than writing "OpenGenome" as though they
were one (D-019).

Two things about the shape of the work.

**One gzip stream is one thread, however large the machine.** A gzip member cannot be
decompressed in parallel, so there is no parallelism to buy here and the honest instance size
is none — AGENTS.md's test, applied and failed the same way A7.1 applied it for its own pass
(D-050). The pass runs in the session container at the speed of one core and the outbound proxy.

**The output is packed integers, not JSON.** 2.6 million accessions as JSON text would be a
50 MB artefact nobody can diff; `amazebio.imgvr.uvig_key` packs each losslessly into one
integer, and the inventory ships as a sorted `.npy` beside a small JSON report of what it
contains. The sort is what makes the join a `searchsorted` rather than a hash of millions of
strings.

    python3 tools/evo2_accessions.py                      # artifacts/a7-2/evo2
    python3 tools/evo2_accessions.py --max-headers 50000  # smoke run, never a result
"""

from __future__ import annotations

import argparse
import array
import collections
import gzip
import io
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import imgvr, objectstore
from amazebio import opengenome as og
from amazebio.repro import run

#: The staged object, pinned by the release revision in `amazebio.opengenome`. The same key
#: A7.1's scan reads, and for the same reason: the corpus bucket withholds `s3:DeleteObject`,
#: so a key names one immutable artefact.
RELEASE_KEY = f"opengenome2/{og.OG2.revision}/fasta/plasmids_phage/imgvr.fasta.gz"


def scan(bucket: str, key: str, *, progress: float, max_headers: int | None) -> dict:
    """Read every header, pack every accession, and measure what did not pack."""
    import numpy as np

    client = objectstore.client()
    reader = objectstore.S3RandomRead(client, bucket, key)
    body = io.BufferedReader(reader, buffer_size=1 << 23)
    keys = array.array("q")
    headers = 0
    fallback: set[str] = set()
    unparsable: collections.Counter = collections.Counter()
    sample: list[str] = []
    seq_chars = 0
    started = last = time.time()
    with gzip.GzipFile(fileobj=body) as gz:
        for raw in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if not raw.startswith(">"):
                seq_chars += len(raw.strip())
                continue
            headers += 1
            head = raw[1:].strip()
            if len(sample) < 20:
                sample.append(head)
            first = head.split()[0] if head.split() else ""
            try:
                key = imgvr.uvig_join_key(first)
            except ValueError:
                # Kept as an example rather than a count alone: a header this audit cannot read
                # as an accession is a released record that cannot be joined, and which records
                # those are decides whether the join is complete or merely large.
                unparsable[first[:64]] += 1
            else:
                keys.append(key)
                if key < 0:
                    # The GVMAG accession shape, which does not pack and is carried under a
                    # hashed key instead. Collected so the hash can be checked injective: these
                    # are giant-virus genomes, so losing them would lose exactly the records a
                    # eukaryote-virus filter is judged on.
                    fallback.add(first)
            if progress and time.time() - last >= progress:
                last = time.time()
                print(
                    f"[evo2] {headers:,} headers  {len(keys):,} packed  "
                    f"{time.time() - started:,.0f}s",
                    flush=True,
                )
            if max_headers is not None and headers >= max_headers:
                break

    packed = np.frombuffer(keys, dtype=np.int64).copy()
    unique = np.unique(packed)
    ok, n_accessions, n_keys = imgvr.collision_free(sorted(fallback))
    if not ok:
        raise RuntimeError(
            f"the join key is not injective on the {n_accessions:,} non-packable released "
            f"accessions: {n_keys:,} distinct keys. Fix the encoding before emitting an "
            "inventory two passes will join on."
        )
    return {
        "non_packable_accessions": n_accessions,
        "non_packable_examples": sorted(fallback)[:20],
        "join_key_injective_on_non_packable": ok,
        "headers": headers,
        "accessions_packed": int(len(packed)),
        "distinct_accessions": int(len(unique)),
        "duplicate_accessions": int(len(packed) - len(unique)),
        "unparsable_headers": int(sum(unparsable.values())),
        "unparsable_examples": dict(unparsable.most_common(20)),
        "header_sample": sample,
        "sequence_chars": seq_chars,
        "carries_lineage": any("__" in h for h in sample),
        "_keys": unique,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--outdir", default="artifacts/a7-2/evo2")
    ap.add_argument("--progress-seconds", type=float, default=60.0)
    ap.add_argument(
        "--max-headers",
        type=int,
        default=None,
        help="stop after N headers — a smoke run, never a result; the artefact records that "
        "it was partial",
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, prefix = objectstore.split_uri(args.s3_uri)
    key = f"{prefix}/{RELEASE_KEY}" if prefix else RELEASE_KEY
    outdir = Path(args.outdir)

    import numpy as np

    with run(
        "A7.2",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-evo2-accessions.json",
    ) as m:
        m.parameter("release", "opengenome2-imgvr")
        m.parameter("revision", og.OG2.revision)
        m.parameter("max_headers", args.max_headers)
        m.note(
            "Headers only. Every sequence line is measured and dropped, so no base enters the "
            "artefact — the commitment in D-020, kept the same way A7.1's scan keeps it."
        )
        m.note(
            "One gzip stream is one thread, so there is no parallelism to buy and no instance "
            "worth launching: AGENTS.md's EC2 test applied and failed, as in D-050."
        )
        client = objectstore.client()
        head = client.head_object(Bucket=bucket, Key=key)
        m.input_url(
            f"s3://{bucket}/{key}",
            role="released-corpus",
            bytes=head["ContentLength"],
            verified=False,
        )

        result = scan(
            bucket, key, progress=args.progress_seconds, max_headers=args.max_headers
        )
        keys = result.pop("_keys")
        result["release"] = "opengenome2-imgvr"
        result["partial"] = bool(args.max_headers)

        outdir.mkdir(parents=True, exist_ok=True)
        npy = outdir / "evo2-imgvr-accessions.npy"
        np.save(npy, keys)
        m.output_file(npy, role="accession-inventory")
        out = outdir / "evo2-accessions.json"
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="accession-report")
        m.note(
            f"{result['headers']:,} headers, {result['distinct_accessions']:,} distinct "
            f"accessions, {result['unparsable_headers']:,} headers that do not pack."
        )
        print(
            f"[evo2] {result['headers']:,} headers -> {result['distinct_accessions']:,} "
            f"distinct accessions; wrote {npy} and {out}",
            flush=True,
        )

        if args.upload_results:
            for path, role in ((npy, "accession-inventory"), (out, "accession-report")):
                k = f"{prefix}/results/a7-2/{path.name}" if prefix else f"results/a7-2/{path.name}"
                payload = path.read_bytes()
                client.put_object(Bucket=bucket, Key=k, Body=payload)
                m.output_object(f"s3://{bucket}/{k}", bytes=len(payload), role=role)
                print(f"[evo2] uploaded s3://{bucket}/{k}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Measure how much of the viral seed set has cellular homologues — task A1.6, D-158.

D-156 settled that ESM3-open's clause (b) — "align almost exclusively to other viral
sequences in UniProt" — is not to be implemented: the strict reading deliberately drops it,
so the annotation-only seed set is that reading's own, and quantifying "almost exclusively"
would invent the number D-015 declined. D-158 fixes what is still measurable without
inventing anything: for each seed, whether the publisher's own cluster containing it holds a
non-viral member, at 90% and at 50% identity, reported as a two-point curve.

`amazebio.exclusivity` holds the reading and what it does *not* claim. The short form: this
bounds how much of a survival figure is exposed to the dropped clause. It is not clause (b),
it does not correct the figure, and it says nothing about whether a matched corpus record is
viral material or host protein that resembles it.

One tier per run. The two tiers are independent forward reads and each wants the whole
worker pool, so running them in one process would halve nothing and complicate the resume;
the launcher invokes this once per tier.

Reads 63 GB for the 90 tier and 30 GB for the 50, so it is meant to run in us-east-1 where
that transfer is free. `--source` accepts a local path, which is how the path is tested end
to end before an instance is paid for.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import exclusivity, repro, seeds, uniref

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"
CHUNK = 8 << 20

#: Tiers this pass can read. UniRef100 is excluded deliberately: it is the tier the seed set
#: was built *from*, so its clusters are the seeds themselves and the question is vacuous
#: there. It also carries no `UniRef100 ID` property to join on.
TIERS = ("uniref90", "uniref50")


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def _make_heartbeat(client: Any, bucket: str, prefix: str, name: str, commit: str | None) -> Any:
    """Publish progress to object storage on an interval, best-effort.

    `AGENTS.md`: a running instance cannot be inspected here — no shell, no SSM, no inbound
    connection — and a quiet console cannot be told apart from a dead process. Two runs died
    31 seconds in and looked exactly like a long pass. So a step with no heartbeat is a step
    whose silence means nothing at all.

    Its own key, overwritten each time, because a heartbeat is not a deliverable. A failure
    to publish one must never fail the run it reports on.

    There is a second copy of this in `tools/esm3_calibrate.py`. Deliberately not shared yet:
    that tool has runs in flight whose behaviour this task has no business changing.
    """
    key = f"{prefix}/heartbeat/{name}.json"
    started = time.time()

    def beat(read: int, elapsed: float, **extra: Any) -> None:
        body = {
            "name": name,
            "code_commit": commit,
            "started_epoch": round(started, 1),
            "now_epoch": round(time.time(), 1),
            "decompressed_bytes": read,
            "elapsed_seconds": round(elapsed, 1),
            "bytes_per_second": round(read / elapsed) if elapsed else None,
            **extra,
        }
        try:
            client.put_object(
                Bucket=bucket, Key=key, Body=json.dumps(body, sort_keys=True).encode()
            )
        except Exception as exc:  # A failed heartbeat must never fail the run it reports on.
            print(f"    heartbeat failed: {type(exc).__name__}", flush=True)

    return beat


def _chunks(
    stream: Any,
    limit: int,
    progress_seconds: float,
    heartbeat: Any = None,
    heartbeat_seconds: float = 300.0,
) -> Any:
    """Yield decompressed chunks, reporting progress to stdout and object storage."""
    read = 0
    started = time.monotonic()
    last = started
    last_beat = started
    while True:
        if limit and read >= limit:
            print(f"    stopping at --limit-bytes {human(limit)}", flush=True)
            return
        want = CHUNK if not limit else min(CHUNK, limit - read)
        chunk = stream.read(want)
        if not chunk:
            return
        read += len(chunk)
        now = time.monotonic()
        if progress_seconds and now - last >= progress_seconds:
            rate = read / max(now - started, 1e-9)
            print(f"    {human(read)} decompressed, {human(rate)}/s", flush=True)
            last = now
        if heartbeat is not None and now - last_beat >= heartbeat_seconds:
            heartbeat(read, now - started)
            last_beat = now
        yield chunk


def _open_tier(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> tuple[Any, str]:
    if args.source:
        return open(args.source, "rb"), str(args.source)
    rel = uniref.RELEASES[args.release]
    key = f"{prefix}/uniref/{rel.release}/{args.tier}.tar/{args.tier}.xml.gz"
    reader = uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {human(pos)}: {type(exc).__name__}", flush=True
        ),
    )
    return reader, f"s3://{bucket}/{key}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", choices=sorted(uniref.RELEASES), default="2023_02")
    ap.add_argument("--tier", choices=TIERS, required=True)
    ap.add_argument(
        "--taxdump",
        required=True,
        type=Path,
        help=f"dated NCBI taxonomy zip; pinned release is {seeds.TAXDUMP_2023_04.date}",
    )
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--source", help="local .xml.gz to read instead of S3 — for testing")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-6"))
    ap.add_argument(
        "--limit-bytes",
        type=int,
        default=0,
        help="stop after this many decompressed bytes. A bounded run cannot estimate the "
        "tier's share — UniRef is ordered by accession, so a prefix is not a sample — and "
        "the artefact is marked accordingly",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 4) - 1),
        help="processes parsing entries. Decompression stays here because a gzip stream "
        "cannot be split, and at a measured 218 MB/s it is not the bottleneck anyway "
        "(default: %(default)s)",
    )
    ap.add_argument("--batch-bytes", type=int, default=8 << 20)
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    ap.add_argument("--heartbeat-seconds", type=float, default=300.0)
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        help="the commit this code came from. An instance has no checkout, so a manifest "
        "that omits it cannot be traced to the code that produced the numbers",
    )
    args = ap.parse_args(argv)

    client = None
    bucket = prefix = ""
    if not args.source or args.upload_results:
        if not args.s3_uri:
            raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI (or --source without upload)")
        bucket, _, prefix = args.s3_uri[5:].partition("/")
        prefix = prefix.strip("/")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT,
            config=Config(retries={"max_attempts": 10, "mode": "standard"}),
        )

    try:
        return _execute(args, client, bucket, prefix)
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.release}-{args.tier}"
    rows_path = args.outdir / f"exclusivity-rows-{stem}.tsv.gz"
    counts_path = args.outdir / f"exclusivity-counts-{stem}.json"

    print(f"loading taxonomy from {args.taxdump}", flush=True)
    taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
    viral = frozenset(taxonomy.descendants(seeds.VIRAL_ROOT))
    print(f"  {len(taxonomy.parent):,} taxa, {len(viral):,} viral", flush=True)

    with repro.run(
        "A1.6",
        seed=None,  # one forward read of a pinned object: nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-exclusivity-{args.tier}.json",
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("decision", "D-158")
        manifest.parameter("release", args.release)
        manifest.parameter("tier", args.tier)
        manifest.parameter("viral_root", seeds.VIRAL_ROOT)
        manifest.parameter("taxdump_pin", seeds.TAXDUMP_2023_04.date)
        manifest.parameter("viral_taxa", len(viral))
        manifest.parameter("workers", args.workers)
        manifest.parameter("limit_bytes", args.limit_bytes)
        manifest.input_file(args.taxdump, role="taxonomy")
        manifest.note(
            "Cluster co-membership at a fixed identity is a proxy for ESM3-open's clause "
            "(b), not an execution of it: the clause conditions on alignment against the "
            "whole of UniProt. This bounds the exposure of a survival figure to the dropped "
            "clause and does not correct that figure (D-156, D-158)."
        )

        reader, label = _open_tier(args, client, bucket, prefix)
        print(f"reading {label}", flush=True)
        if args.source:
            manifest.input_file(args.source, role="tier")
        else:
            manifest.parameter("tier_object", label)

        heartbeat = None
        if client is not None and not args.source:
            heartbeat = _make_heartbeat(
                client, bucket, prefix, f"a1-6-exclusivity-{args.tier}", args.code_commit
            )

        counts = exclusivity.ExclusivityCounts()
        config = exclusivity.ExclusivityConfig(denylist_taxids=viral)
        stream = uniref.GunzipStream(reader)
        started = time.monotonic()
        emitted = 0
        with gzip.open(rows_path, "wb") as rows:
            for batch in seeds.scan_parallel(
                _chunks(
                    stream,
                    args.limit_bytes,
                    args.progress_seconds,
                    heartbeat,
                    args.heartbeat_seconds,
                ),
                config,
                workers=args.workers,
                batch_bytes=args.batch_bytes,
            ):
                counts.merge(batch.counts)
                for uniref100_id, verdict in batch.rows:
                    rows.write(f"{uniref100_id}\t{verdict}\n".encode())
                    emitted += 1
        elapsed = time.monotonic() - started

        # `GunzipStream` exposes these as attributes, not as `tell()` — a `tell` lookup
        # silently yields 0, which is how this field reads as "nothing was read" on a pass
        # that read the whole tier. `tools/count_clusters.py` is the precedent that proves
        # the names.
        compressed = getattr(stream, "compressed_bytes", 0)
        decompressed = getattr(stream, "read_bytes", 0)
        payload = {
            "decision": "D-158",
            "release": args.release,
            "tier": args.tier,
            "bounded": bool(args.limit_bytes),
            "rows_emitted": emitted,
            "counts": counts.to_dict(),
            "compressed_bytes_read": compressed,
            "decompressed_bytes_read": decompressed,
            "elapsed_seconds": round(elapsed, 1),
            "decompressed_bytes_per_second": (round(decompressed / elapsed) if elapsed else None),
            "taxdump": {
                "date": seeds.TAXDUMP_2023_04.date,
                "sha256": seeds.TAXDUMP_2023_04.sha256,
            },
        }
        counts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

        manifest.output_file(rows_path, role="exclusivity-rows")
        manifest.output_file(counts_path, role="exclusivity-counts")
        if args.limit_bytes:
            manifest.note(
                "BOUNDED RUN: stopped at --limit-bytes. UniRef is ordered by accession, so "
                "this read a prefix rather than a sample and no share here estimates the "
                "tier's."
            )
        if hasattr(reader, "close"):
            reader.close()

        d = counts.to_dict()
        print(
            f"\n{d['clusters']:,} clusters, {d['viral_covering']:,} covering a viral member, "
            f"{d['non_exclusive']:,} of those non-exclusive "
            f"({100 * (d['non_exclusive_share'] or 0):.2f}%)",
            flush=True,
        )
        print(f"  wholly unplaced clusters: {d['unplaced_clusters']:,}")
        print(f"  rows emitted: {emitted:,}  ->  {rows_path}")

    # Uploads happen after the run block: `run.json` is written by the manifest's exit
    # handler, so an upload inside the block would miss it.
    if args.upload_results and client is not None:
        for path, role in (
            (rows_path, "rows"),
            (counts_path, "counts"),
            (args.outdir / f"run-exclusivity-{args.tier}.json", "manifest"),
        ):
            if not path.exists():
                print(f"not uploaded (absent): {path}")
                continue
            # The commit is in the key because this bucket has no DeleteObject, so an
            # overwrite destroys the earlier object irreversibly (D-126's reasoning).
            tag = args.code_commit or "nocommit"
            key = f"{prefix}/results/a1-6/exclusivity/{args.release}/{args.tier}/{role}-{tag}"
            key += ".tsv.gz" if role == "rows" else ".json"
            client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
            print(f"uploaded s3://{bucket}/{key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

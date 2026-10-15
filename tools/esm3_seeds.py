#!/usr/bin/env python3
"""Build ESM3-open's viral denylist seed set from a staged UniRef tier — task A1.6.

ESM3-open's filter is similarity-based, so re-executing it needs the two denylists it
queries against, and neither is published as a set. This builds the viral one: the
clusters of a staged UniRef release that carry at least one member UniProt annotates as
viral. `amazebio.seeds` holds the reading this implements, including what it costs and in
which direction — read that docstring before trusting a number out of here.

The pass is one forward read of a `.xml.gz` object. It is in-region work by the test in
AGENTS.md: UniRef100 2023_02 is 118.68 GB of staged object and reading it from outside
`us-east-1` is metered, which the measured 42.5 MB/s out of the bucket turns into about
forty-five minutes and roughly eleven dollars of egress for that tier alone. Inside the
region it is free. `--source` runs the identical path over a local file, which is how the
parser is exercised before anything launches.

A gzip stream cannot be decompressed in parallel, so one tier is one process however many
cores the machine has. Parallelism here is one process per tier and no more.

Provenance: `--code-commit` exists because an instance has no git checkout, so
`amazebio.repro` cannot discover the commit and a manifest written there would be
untraceable. Pass it from the launcher.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import repro, seeds, uniref
from amazebio.repro import ReproError

S3_REGION = "us-east-1"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
CHUNK = 8 << 20


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000:
            return f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} PB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--release",
        choices=sorted(uniref.RELEASES),
        default="2023_02",
        help="which staged release to read (default: %(default)s, ESM3's stated release)",
    )
    ap.add_argument(
        "--tier",
        default="uniref100",
        choices=["uniref50", "uniref90", "uniref100"],
        help="UniRef100 is the only tier that covers every UniProtKB entry, which is "
        "what 'annotated as viral in UniProt' is a statement about (default: %(default)s)",
    )
    ap.add_argument(
        "--taxdump",
        required=True,
        type=Path,
        help=f"dated NCBI taxonomy zip; pinned release is {seeds.TAXDUMP_2023_04.date}",
    )
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument(
        "--source", help="local .xml.gz to read instead of S3 — exercises the identical path"
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-6"))
    ap.add_argument(
        "--limit-bytes",
        type=int,
        default=0,
        help="stop after this many DECOMPRESSED bytes. A bounded run measures throughput "
        "and exercises the path; it does not produce a seed set, and the artefact says so. "
        "Note what it also cannot do: UniRef is ordered by accession, so a prefix is not a "
        "sample of it and no share measured from one estimates the share of the tier.",
    )
    ap.add_argument(
        "--upload-results",
        action="store_true",
        help="put the seed set and manifest back in S3, so a run on a machine nobody "
        "can log into still reports its result",
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        help="the commit this code came from. An instance has no checkout and cannot "
        "discover it; a manifest without it cannot be traced to the code behind the numbers.",
    )
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    args = ap.parse_args(argv)

    client = None
    bucket = prefix = ""
    if not args.source:
        if not args.s3_uri:
            raise SystemExit("need --s3-uri, $AMAZEBIO_S3_URI, or --source")
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
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _open_tier(args: argparse.Namespace, client: Any, bucket: str, prefix: str):
    """Return (reader, label). The reader is forward-only with .read(n)."""
    if args.source:
        return open(args.source, "rb"), args.source
    key = f"{prefix}/uniref/{args.release}/{args.tier}.tar/{args.tier}.xml.gz"
    reader = uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {human(pos)}: {type(exc).__name__}", flush=True
        ),
    )
    return reader, f"s3://{bucket}/{key}"


def _chunks(stream: Any, limit: int, progress_seconds: float) -> Any:
    """Yield decompressed chunks, reporting progress and honouring a byte limit.

    Progress goes to stdout because that is the only channel back from an instance:
    there is no shell, and the serial console is read with `ec2:GetConsoleOutput`.
    """
    read = 0
    last = time.monotonic()
    started = last
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
        yield chunk


def _execute(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    fasta_path = args.outdir / f"viral-seeds-{args.release}-{args.tier}.faa"
    counts_path = args.outdir / f"seed-counts-{args.release}-{args.tier}.json"

    print(f"loading taxonomy from {args.taxdump}", flush=True)
    taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
    viral = taxonomy.descendants(seeds.VIRAL_ROOT)
    print(f"  {len(taxonomy.parent):,} taxa, {len(viral):,} viral", flush=True)

    with repro.run(
        "A1.6",
        seed=None,  # one forward read of a pinned object: nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-seeds-{args.tier}.json",
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("release", args.release)
        manifest.parameter("tier", args.tier)
        manifest.parameter("viral_root", seeds.VIRAL_ROOT)
        manifest.parameter("limit_bytes", args.limit_bytes)
        manifest.parameter("taxdump_pin", seeds.TAXDUMP_2023_04.date)
        manifest.parameter("taxa", len(taxonomy.parent))
        manifest.parameter("viral_taxa", len(viral))
        manifest.input_file(args.taxdump, role="taxonomy")

        reader, label = _open_tier(args, client, bucket, prefix)
        print(f"reading {label}", flush=True)
        if args.source:
            manifest.input_file(args.source, role="corpus")
        else:
            manifest.parameter("corpus_object", label)

        counts = seeds.SeedCounts()
        started = time.monotonic()
        stream = uniref.GunzipStream(reader)
        with open(fasta_path, "wb") as fasta:
            for entry in seeds.iter_entries(
                _chunks(stream, args.limit_bytes, args.progress_seconds)
            ):
                if counts.observe(entry, viral):
                    seeds.write_fasta(fasta, entry.cluster_id, entry.sequence)
        elapsed = time.monotonic() - started

        compressed = getattr(reader, "tell", lambda: 0)() or 0
        decompressed = getattr(stream, "tell", lambda: 0)() or 0
        payload = {
            "release": args.release,
            "tier": args.tier,
            "bounded": bool(args.limit_bytes),
            "compressed_bytes_read": compressed,
            "decompressed_bytes_read": decompressed,
            "elapsed_seconds": round(elapsed, 1),
            "compressed_bytes_per_second": (round(compressed / elapsed) if elapsed else None),
            "decompressed_bytes_per_second": (round(decompressed / elapsed) if elapsed else None),
            "taxdump": {
                "date": seeds.TAXDUMP_2023_04.date,
                "sha256": seeds.TAXDUMP_2023_04.sha256,
            },
            "counts": counts.to_dict(),
        }
        counts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

        manifest.output_file(fasta_path, role="viral-seed-set")
        manifest.output_file(counts_path, role="seed-counts")
        manifest.tool("mmseqs", ["mmseqs", "version"])
        if args.limit_bytes:
            manifest.note(
                "BOUNDED RUN: stopped at --limit-bytes, so the seed set is a prefix of "
                "the tier and not the seed set. Throughput is measurable from it; "
                "counts are not a result."
            )

        print(
            f"\n{counts.clusters:,} clusters, {counts.viral_seeded:,} viral-seeded "
            f"({100 * (counts.viral_seeded / counts.clusters if counts.clusters else 0):.2f}%)"
            f" in {elapsed:.0f}s",
            flush=True,
        )
        print(
            f"  representative not viral: {counts.representative_not_viral:,}"
            f"   mixed members: {counts.mixed:,}",
            flush=True,
        )

        if args.upload_results and client is not None:
            for path, role in ((fasta_path, "viral-seed-set"), (counts_path, "seed-counts")):
                key = f"{prefix}/results/a1-6/{path.name}"
                client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
                manifest.output_object(f"s3://{bucket}/{key}", bytes=path.stat().st_size, role=role)
                print(f"  uploaded s3://{bucket}/{key}", flush=True)

    if args.upload_results and client is not None:
        name = f"run-seeds-{args.tier}.json"
        local = args.outdir / name
        key = f"{prefix}/results/a1-6/{name}"
        client.put_object(Bucket=bucket, Key=key, Body=local.read_bytes())
        print(f"  uploaded s3://{bucket}/{key}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

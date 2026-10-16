#!/usr/bin/env python3
"""Price ESM3-open's alignment pass by measuring it in region — task A1.6.

A1.6's file instructs that the alignment pass be priced before anything launches, and
D-094 records why the price could not be settled in the session container: extrapolating
from a slice at 1/88,000 of the full target spans roughly 200 to 33,000 core-hours,
because how MMseqs2's prefilter divides its cost between query batching and target
scanning does not show up at that size. This measures the scaling directly, over target
shards spanning an order of magnitude, and writes the fit inputs out so the full pass can
be priced from numbers rather than from a guess.

It does two things in one pass over the staged tier, because a second pass over 118 GB
costs an hour for nothing:

1. **The viral seed set**, whole — every cluster with a viral member. This is not
   calibration output, it is A1.6's actual deliverable, and it is what makes the query
   side of the timing the real query side rather than a sample of it. It also gives the
   one comparison that works: ESM3 states the viral denylist is roughly 4M sequences.

2. **A hash-partitioned sample of the corpus**, as `--buckets` equal shards. Sampling by
   a deterministic hash of the cluster id rather than by taking a prefix is the whole
   point: UniRef is ordered by accession, so a prefix is not a sample of it and hit rates
   measured from one mean nothing. Hash partitioning also makes the shards *nested* —
   buckets 1..k is a valid sample at k times the rate — which is what lets one pass
   produce a scaling curve instead of a single point. This follows D-078's precedent.

Then it times `mmseqs search` with the seed set as query against buckets 1..k for each k,
at both readings: the charitable 0.70 identity threshold, and the strict reading's
sensitivity floor on the smaller shards only, since that end is 10 to 50 times the cost.
Orientation is seeds-as-query because D-094 measured the alternative at eight times
slower before abandoning it.

Nothing here decides a threshold or a parameter — D-015 fixed the readings and D-093 the
aligner. This measures what running them costs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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

#: Fixed before any output exists, as the non-negotiables require. The charitable reading's
#: 0.70 comes from D-015; coverage mode and coverage match what ESM3 states for its own
#: clustering, which is the only parameter guidance the source gives at all. The strict
#: reading removes on any detected hit, so it runs at MMseqs2's maximum sensitivity and
#: sets no identity floor.
CHARITABLE = ("--min-seq-id", "0.70", "-c", "0.8", "--cov-mode", "1")
STRICT = ("-c", "0.8", "--cov-mode", "1", "-s", "7.5")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1000:
            return f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} PB"


#: Lives in the library because the worker processes need it too, and a sampling rule that
#: differed between the parent and a worker would put the same cluster in two shards.
bucket_of = seeds.bucket_of


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", default="2023_02", choices=sorted(uniref.RELEASES))
    ap.add_argument("--tier", default="uniref100", choices=["uniref50", "uniref90", "uniref100"])
    ap.add_argument("--taxdump", required=True, type=Path)
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--source", help="local .xml.gz instead of S3 — exercises the same path")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-6"))
    ap.add_argument("--workdir", type=Path, default=Path("work"))
    ap.add_argument(
        "--sample-rate",
        type=int,
        default=50,
        help="keep 1 cluster in this many for the target sample (default: %(default)s, "
        "which over UniRef100 is about 2 G residues)",
    )
    ap.add_argument(
        "--buckets",
        type=int,
        default=8,
        help="equal hash-partitioned shards of the sample; buckets 1..k is itself a "
        "valid sample, which is what makes the scaling curve one pass (default: %(default)s)",
    )
    ap.add_argument(
        "--strict-buckets",
        type=int,
        default=2,
        help="how many shards to also time at the strict reading's sensitivity floor; "
        "that end costs 10-50x the charitable one, so it is measured small (default: %(default)s)",
    )
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 4) - 1),
        help="processes parsing entries. Decompression stays in this process because a "
        "gzip stream cannot be split, and measured it runs at 218 MB/s against the "
        "43.6 MB/s the whole pass managed single-threaded: the parsing is the bottleneck, "
        "not the decompression, and the parsing is what this spreads. One worker keeps "
        "the serial path (default: %(default)s)",
    )
    ap.add_argument(
        "--batch-bytes",
        type=int,
        default=8 << 20,
        help="entry bytes per unit of work handed to a worker (default: %(default)s)",
    )
    ap.add_argument(
        "--limit-bytes",
        type=int,
        default=0,
        help="stop the corpus pass after this many decompressed bytes. For exercising "
        "the path; the seed set it produces is a prefix and not a seed set.",
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--code-commit")
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    ap.add_argument(
        "--skip-search",
        action="store_true",
        help="build the seed set and shards and stop, for checking the pass without paying "
        "for the timing",
    )
    ap.add_argument(
        "--search-budget-seconds",
        type=float,
        default=0.0,
        help="stop starting new searches once this much time has gone into them. The "
        "shards are timed smallest first, so a budget trades the largest point of the "
        "curve for a guarantee the run ends and reports. 0 means no budget, which is "
        "only safe where something else bounds the run.",
    )
    args = ap.parse_args(argv)

    if args.buckets < 1:
        raise SystemExit("--buckets must be at least 1")
    if args.strict_buckets > args.buckets:
        raise SystemExit("--strict-buckets cannot exceed --buckets")

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

    if shutil.which("mmseqs") is None and not args.skip_search:
        raise SystemExit("mmseqs is not on PATH; the timing cannot run")

    try:
        return _execute(args, client, bucket, prefix)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _reader(args: argparse.Namespace, client: Any, bucket: str, prefix: str):
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
    read = 0
    started = last = time.monotonic()
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
            print(
                f"    {human(read)} decompressed, {human(read / max(now - started, 1e-9))}/s",
                flush=True,
            )
            last = now
        yield chunk


def _mmseqs(*argv: str) -> float:
    """Run one mmseqs command, returning wall seconds. Output goes to the console."""
    started = time.monotonic()
    proc = subprocess.run(["mmseqs", *argv], capture_output=True, text=True)
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(f"mmseqs {argv[0]} failed ({proc.returncode}): {' / '.join(tail)}")
    return elapsed


def _execute(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    work = args.workdir
    work.mkdir(parents=True, exist_ok=True)
    seed_fasta = work / "viral-seeds.faa"
    shard_paths = [work / f"shard-{i:02d}.faa" for i in range(args.buckets)]
    timing_path = args.outdir / "calibration.json"

    print(f"loading taxonomy from {args.taxdump}", flush=True)
    taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
    viral = taxonomy.descendants(seeds.VIRAL_ROOT)
    print(f"  {len(taxonomy.parent):,} taxa, {len(viral):,} viral", flush=True)

    with repro.run(
        "A1.6",
        seed=None,  # the sample is a hash of the cluster id, not an RNG draw
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-calibration.json",
    ) as manifest:
        for name, value in (
            ("code_commit", args.code_commit),
            ("release", args.release),
            ("tier", args.tier),
            ("sample_rate", args.sample_rate),
            ("buckets", args.buckets),
            ("strict_buckets", args.strict_buckets),
            ("threads", args.threads),
            ("workers", args.workers),
            ("batch_bytes", args.batch_bytes),
            ("limit_bytes", args.limit_bytes),
            ("charitable_params", " ".join(CHARITABLE)),
            ("strict_params", " ".join(STRICT)),
            ("taxdump_pin", seeds.TAXDUMP_2023_04.date),
        ):
            if value is not None:
                manifest.parameter(name, value)
        manifest.input_file(args.taxdump, role="taxonomy")

        reader, label = _reader(args, client, bucket, prefix)
        print(f"reading {label}", flush=True)
        if args.source:
            manifest.input_file(args.source, role="corpus")
        else:
            manifest.parameter("corpus_object", label)

        counts = seeds.SeedCounts()
        shard_counts = [0] * args.buckets
        shard_residues = [0] * args.buckets
        started = time.monotonic()
        stream = uniref.GunzipStream(reader)
        handles = [p.open("wb") for p in shard_paths]
        # The sample and the seed set are independent: a viral cluster can be in both, and
        # must be, or the target would be missing exactly the records the filter is
        # supposed to remove.
        config = seeds.ScanConfig(
            viral=frozenset(viral), sample_rate=args.sample_rate, buckets=args.buckets
        )
        try:
            with seed_fasta.open("wb") as seedfh:
                for batch in seeds.scan_parallel(
                    _chunks(stream, args.limit_bytes, args.progress_seconds),
                    config,
                    workers=args.workers,
                    batch_bytes=args.batch_bytes,
                ):
                    counts.merge(batch.counts)
                    for cluster_id, sequence in batch.seeds:
                        seeds.write_fasta(seedfh, cluster_id, sequence)
                    for shard, cluster_id, sequence in batch.samples:
                        seeds.write_fasta(handles[shard], cluster_id, sequence)
                        shard_counts[shard] += 1
                        shard_residues[shard] += len(sequence)
        finally:
            for handle in handles:
                handle.close()
        corpus_seconds = time.monotonic() - started

        print(
            f"\ncorpus pass: {counts.clusters:,} clusters in {corpus_seconds:.0f}s"
            f"  ({counts.viral_seeded:,} viral-seeded)",
            flush=True,
        )
        print(
            f"  sample: {sum(shard_counts):,} clusters, "
            f"{sum(shard_residues) / 1e9:.3f} G residues across {args.buckets} shards",
            flush=True,
        )

        payload: dict[str, Any] = {
            "release": args.release,
            "tier": args.tier,
            "bounded": bool(args.limit_bytes),
            "threads": args.threads,
            "corpus_pass_seconds": round(corpus_seconds, 1),
            "compressed_bytes_read": getattr(reader, "tell", lambda: 0)() or 0,
            "decompressed_bytes_read": getattr(stream, "tell", lambda: 0)() or 0,
            "seed_counts": counts.to_dict(),
            "sample": {
                "rate": args.sample_rate,
                "buckets": args.buckets,
                "clusters_per_bucket": shard_counts,
                "residues_per_bucket": shard_residues,
            },
            "searches": [],
        }

        def upload(path: Path, role: str) -> None:
            if not (args.upload_results and client is not None):
                return
            key = f"{prefix}/results/a1-6/{path.name}"
            client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
            manifest.output_object(f"s3://{bucket}/{key}", bytes=path.stat().st_size, role=role)
            print(f"  uploaded s3://{bucket}/{key}", flush=True)

        def publish() -> None:
            """Write the timing artefact, and upload it if asked.

            Called after every measurement rather than once at the end. There is no shell
            on the instance and no way to retrieve a partial result from it, so a run that
            is cut short — by a budget, a timeout, or the launcher's own terminate — has to
            have already reported everything it measured. A1.3 learned the general version
            of this the hard way; this is the specific one.
            """
            timing_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            if args.upload_results and client is not None:
                key = f"{prefix}/results/a1-6/{timing_path.name}"
                client.put_object(Bucket=bucket, Key=key, Body=timing_path.read_bytes())

        # The seed set goes up *now*, before the searches, because it is the deliverable
        # and they are the measurement. On 2026-10-15 the searches were cut short and took
        # an already-finished 53-minute corpus pass with them, purely because the upload
        # sat after them in this function. Deliverables ship when they exist.
        publish()
        upload(seed_fasta, "viral-seed-set")

        if not args.skip_search:
            _time_searches(
                args,
                work,
                seed_fasta,
                shard_paths,
                shard_residues,
                counts,
                payload["searches"],
                publish,
            )

        timing_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        manifest.output_file(timing_path, role="calibration")
        manifest.output_file(seed_fasta, role="viral-seed-set")
        manifest.tool("mmseqs", ["mmseqs", "version"])
        if args.limit_bytes:
            manifest.note(
                "BOUNDED RUN: the corpus pass stopped at --limit-bytes, so the seed set is a "
                "prefix of the tier and not the seed set, and no share here estimates the "
                "tier's share. The timings are still timings."
            )

        upload(timing_path, "calibration")

    if args.upload_results and client is not None:
        local = args.outdir / "run-calibration.json"
        key = f"{prefix}/results/a1-6/run-calibration.json"
        client.put_object(Bucket=bucket, Key=key, Body=local.read_bytes())
        print(f"  uploaded s3://{bucket}/{key}", flush=True)
    return 0


def _time_searches(
    args: argparse.Namespace,
    work: Path,
    seed_fasta: Path,
    shard_paths: list[Path],
    shard_residues: list[int],
    counts: seeds.SeedCounts,
    results: list[dict[str, Any]],
    publish: Any,
) -> list[dict[str, Any]]:
    """Time the charitable reading over nested shards, and the strict one over the small ones.

    Shards are timed smallest first and every measurement is published as it lands, so a
    run cut short still reports the curve it got. `--search-budget-seconds` trades the
    largest point for the guarantee that the run ends.
    """
    db = work / "db"
    db.mkdir(exist_ok=True)
    tmp = work / "tmp"
    spent = 0.0

    print("\nbuilding the query database", flush=True)
    query_seconds = _mmseqs("createdb", str(seed_fasta), str(db / "Q"))
    print(f"  createdb(query) {query_seconds:.1f}s", flush=True)

    cumulative = work / "cumulative.faa"
    if cumulative.exists():
        cumulative.unlink()

    for k in range(1, args.buckets + 1):
        with cumulative.open("ab") as out, shard_paths[k - 1].open("rb") as src:
            shutil.copyfileobj(src, out)
        residues = sum(shard_residues[:k])
        if residues == 0:
            print(f"  shards 1..{k}: empty, skipped", flush=True)
            continue
        target = db / f"T{k}"
        build = _mmseqs("createdb", str(cumulative), str(target))

        for reading, params in (("charitable", CHARITABLE), ("strict", STRICT)):
            if reading == "strict" and k > args.strict_buckets:
                continue
            if args.search_budget_seconds and spent >= args.search_budget_seconds:
                print(
                    f"  budget of {args.search_budget_seconds:.0f}s spent; "
                    f"stopping before shards 1..{k} {reading}",
                    flush=True,
                )
                results.append(
                    {
                        "shards": k,
                        "reading": reading,
                        "residues": residues,
                        "skipped": "search budget exhausted",
                    }
                )
                publish()
                return results
            out_db = db / f"R-{reading}-{k}"
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)
            try:
                elapsed = _mmseqs(
                    "search",
                    str(db / "Q"),
                    str(target),
                    str(out_db),
                    str(tmp),
                    *params,
                    "--threads",
                    str(args.threads),
                )
            except RuntimeError as exc:
                # A failure on one shard is a datum, not the end of the run: the smaller
                # shards already measured are what the fit needs, and losing them to an
                # exception on the largest would waste the whole instance.
                print(f"  shards 1..{k} {reading}: FAILED {exc}", flush=True)
                results.append(
                    {"shards": k, "reading": reading, "residues": residues, "error": str(exc)}
                )
                publish()
                continue
            spent += elapsed
            hits = _hit_count(db / "Q", target, out_db, work)
            core_seconds = elapsed * args.threads
            print(
                f"  shards 1..{k} {reading}: {elapsed:.1f}s wall, "
                f"{core_seconds:.0f} core-s over {residues / 1e9:.3f} G residues, {hits:,} hits",
                flush=True,
            )
            results.append(
                {
                    "shards": k,
                    "reading": reading,
                    "residues": residues,
                    "createdb_seconds": round(build, 1),
                    "search_wall_seconds": round(elapsed, 1),
                    "search_core_seconds": round(core_seconds, 1),
                    "query_residues": counts.viral_residues,
                    "query_sequences": counts.viral_seeded,
                    "hit_rows": hits,
                }
            )
            publish()
    return results


def _hit_count(query: Path, target: Path, result: Path, work: Path) -> int:
    """How many alignment rows the search produced. Zero is a result, not a failure."""
    tsv = work / "hits.tsv"
    try:
        _mmseqs("convertalis", str(query), str(target), str(result), str(tsv))
    except RuntimeError:
        return -1
    if not tsv.exists():
        return -1
    with tsv.open("rb") as handle:
        return sum(1 for _ in handle)


if __name__ == "__main__":
    raise SystemExit(main())

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

from amazebio import repro, seeds, similarity, uniref
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

#: One artefact name per mode, because the corpus bucket has no DeleteObject: a second mode
#: writing to the first's key would overwrite a preserved grid permanently.
ARTEFACT_NAMES = {"curve": "calibration.json", "caps": "cap-measurement.json"}


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
        "--query-fractions",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[1000, 100, 10, 1],
        help="denominators for the query-size sweep: 1000 means a 1-in-1000 subsample of "
        "the seed set, 1 means all of it. Swept because the first in-region run showed "
        "the query side dominates (default: %(default)s)",
    )
    ap.add_argument(
        "--shard-points",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[1, 2, 4, 8],
        help="which cumulative shard counts to time, rather than every one (default: %(default)s)",
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
    ap.add_argument(
        "--measure",
        choices=("curve", "caps"),
        default="curve",
        help="`curve` times the cost model's grid, which is what D-104 was fitted on. "
        "`caps` measures the two items D-105 and D-109 left open: what the hit cap costs "
        "where it binds, and what relaxing coverage costs to buy the three readings from "
        "one search (default: %(default)s)",
    )
    ap.add_argument(
        "--artefact-name",
        default="",
        help="result filename, which is also its S3 key. Defaults per --measure, and the "
        "default is never shared between modes: the corpus bucket has no DeleteObject, so "
        "writing one mode's artefact over another's preserved grid cannot be undone",
    )
    ap.add_argument(
        "--cap-query-denominator",
        type=int,
        default=100,
        help="query subsample for the cap measurement. Hits per seed is a per-seed "
        "property, so subsampling the query does not bias it — it only makes the "
        "measurement affordable (default: %(default)s)",
    )
    ap.add_argument(
        "--cap-shard-points",
        type=lambda s: [int(x) for x in s.split(",")],
        default=[1, 2, 4],
        help="cumulative shard counts the cap measurement runs at. More than one because "
        "the question is whether hits per seed grows linearly in target size, which is "
        "what decides whether the cap binds at the pass's scale (default: %(default)s)",
    )
    ap.add_argument(
        "--cap-fractions",
        type=lambda s: [float(x) for x in s.split(",")],
        default=[0.5, 0.2],
        help="caps to also run, as fractions of the maximum hits per seed the slack run "
        "observed. These are the caps that bind at this scale; the published cap stays "
        "D-105's 100,000 (default: %(default)s)",
    )
    args = ap.parse_args(argv)

    if args.buckets < 1:
        raise SystemExit("--buckets must be at least 1")
    if args.measure == "caps" and max(args.cap_shard_points) > args.buckets:
        raise SystemExit("--cap-shard-points cannot exceed --buckets")
    if any(not 0 < f <= 1 for f in args.cap_fractions):
        raise SystemExit("--cap-fractions are fractions of the observed maximum, in (0, 1]")
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
    timing_path = args.outdir / (args.artefact_name or ARTEFACT_NAMES[args.measure])

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
            ("query_fractions", ",".join(str(x) for x in args.query_fractions)),
            ("shard_points", ",".join(str(x) for x in args.shard_points)),
            ("threads", args.threads),
            ("workers", args.workers),
            ("batch_bytes", args.batch_bytes),
            ("limit_bytes", args.limit_bytes),
            ("measure", args.measure),
            ("cap_query_denominator", args.cap_query_denominator),
            ("cap_shard_points", ",".join(str(x) for x in args.cap_shard_points)),
            ("cap_fractions", ",".join(str(x) for x in args.cap_fractions)),
            ("published_hit_cap", similarity.HIT_CAP),
            ("coverage", similarity.COVERAGE),
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
            "measure": args.measure,
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
            if args.measure == "caps":
                _measure_caps(args, work, seed_fasta, shard_paths, shard_residues, payload, publish)
            else:
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


def _subsample_fasta(src: Path, dst: Path, denom: int) -> tuple[int, int]:
    """Keep one FASTA record in `denom`, chosen by a stable hash of the identifier.

    The query side has to be swept, not held fixed. The first in-region run searched the
    whole 3,159,223-sequence seed set against one 334 M-residue shard and had not finished
    after 61 minutes, which says the query side dominates and says nothing about by how
    much. One target-size curve at fixed query size cannot separate the two; a grid can.

    Hash rather than head: the seed set comes out in corpus order, so its first n records
    are the low-accession end of UniProt rather than a sample of viral protein space.
    """
    kept = residues = 0
    with src.open("rb") as handle, dst.open("wb") as out:
        emit = False
        for line in handle:
            if line.startswith(b">"):
                ident = line[1:].split()[0].decode("ascii", "replace")
                emit = denom <= 1 or seeds.bucket_of(ident, denom) == 0
                if emit:
                    kept += 1
            if emit:
                out.write(line)
                if not line.startswith(b">"):
                    residues += len(line.strip())
    return kept, residues


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
    """Time a grid of query size against target size, cheapest corner first.

    Both axes move because the first run established that holding the query at its full
    3.16M sequences makes even a small target unaffordable, so a single-axis curve would
    have measured one expensive point and nothing else. Sweeping both gives the two
    coefficients the extrapolation actually needs: cost per residue of target, and cost
    per sequence of query.

    Order is sparsest query first and smallest target first, so `--search-budget-seconds`
    spends the budget on the cheap, numerous points that constrain the fit and drops the
    one expensive corner — which is the corner that killed the previous run.
    """
    db = work / "db"
    db.mkdir(exist_ok=True)
    tmp = work / "tmp"
    spent = 0.0

    # Target databases, built once and shared across every query size.
    targets: list[tuple[int, int, Path]] = []
    cumulative = work / "cumulative.faa"
    if cumulative.exists():
        cumulative.unlink()
    wanted = sorted({min(k, args.buckets) for k in args.shard_points})
    for k in range(1, args.buckets + 1):
        with cumulative.open("ab") as out, shard_paths[k - 1].open("rb") as src:
            shutil.copyfileobj(src, out)
        if k not in wanted:
            continue
        residues = sum(shard_residues[:k])
        if residues == 0:
            print(f"  shards 1..{k}: empty, skipped", flush=True)
            continue
        target = db / f"T{k}"
        build = _mmseqs("createdb", str(cumulative), str(target))
        print(
            f"  createdb(target 1..{k}) {build:.1f}s, {residues / 1e6:.0f} M residues", flush=True
        )
        targets.append((k, residues, target))

    for denom in sorted(args.query_fractions, reverse=True):
        qpath = work / f"query-{denom}.faa"
        qseqs, qres = _subsample_fasta(seed_fasta, qpath, denom)
        if qseqs == 0:
            print(f"  query 1/{denom}: empty, skipped", flush=True)
            continue
        qdb = db / f"Q{denom}"
        _mmseqs("createdb", str(qpath), str(qdb))
        print(f"\n  query 1/{denom}: {qseqs:,} sequences, {qres / 1e6:.0f} M residues", flush=True)

        for k, residues, target in targets:
            for reading, params in (("charitable", CHARITABLE), ("strict", STRICT)):
                if reading == "strict" and k > args.strict_buckets:
                    continue
                point = {
                    "shards": k,
                    "reading": reading,
                    "residues": residues,
                    "query_denominator": denom,
                    "query_sequences": qseqs,
                    "query_residues": qres,
                }
                if args.search_budget_seconds and spent >= args.search_budget_seconds:
                    print(
                        f"  budget of {args.search_budget_seconds:.0f}s spent; stopping "
                        f"before query 1/{denom} x shards 1..{k} {reading}",
                        flush=True,
                    )
                    results.append({**point, "skipped": "search budget exhausted"})
                    publish()
                    return results
                out_db = db / f"R-{reading}-{denom}-{k}"
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True, exist_ok=True)
                try:
                    elapsed = _mmseqs(
                        "search",
                        str(qdb),
                        str(target),
                        str(out_db),
                        str(tmp),
                        *params,
                        "--threads",
                        str(args.threads),
                    )
                except RuntimeError as exc:
                    # A failure at one grid point is a datum. Losing the points already
                    # measured to an exception at a later one would waste the instance.
                    print(f"  query 1/{denom} x 1..{k} {reading}: FAILED {exc}", flush=True)
                    results.append({**point, "error": str(exc)})
                    publish()
                    continue
                spent += elapsed
                hits = _hit_count(qdb, target, out_db, work)
                core_seconds = elapsed * args.threads
                print(
                    f"  query 1/{denom} x shards 1..{k} {reading}: {elapsed:.1f}s wall, "
                    f"{core_seconds:.0f} core-s, {residues / 1e6:.0f} M target residues, "
                    f"{hits:,} hits",
                    flush=True,
                )
                results.append(
                    {
                        **point,
                        "search_wall_seconds": round(elapsed, 1),
                        "search_core_seconds": round(core_seconds, 1),
                        "hit_rows": hits,
                    }
                )
                publish()
    return results


#: The cap measurement holds sensitivity at D-105's fixed value rather than sweeping it.
#: The two questions here are about the cap and about coverage, and entangling them with the
#: one axis D-109 is already paying to sweep would make neither answer clean.
CAP_SENSITIVITY = 5.7


def _build_targets(
    args: argparse.Namespace,
    work: Path,
    db: Path,
    shard_paths: list[Path],
    shard_residues: list[int],
    points: list[int],
) -> list[tuple[int, int, Path]]:
    """Cumulative target databases at the requested shard counts.

    Shards 1..k of a hash partition is itself a hash sample, which is what makes a size
    sweep one corpus pass rather than k of them.
    """
    targets: list[tuple[int, int, Path]] = []
    cumulative = work / "cap-cumulative.faa"
    if cumulative.exists():
        cumulative.unlink()
    wanted = sorted({min(k, args.buckets) for k in points})
    for k in range(1, max(wanted) + 1):
        with cumulative.open("ab") as out, shard_paths[k - 1].open("rb") as src:
            shutil.copyfileobj(src, out)
        if k not in wanted:
            continue
        residues = sum(shard_residues[:k])
        if residues == 0:
            print(f"  shards 1..{k}: empty, skipped", flush=True)
            continue
        target = db / f"CT{k}"
        build = _mmseqs("createdb", str(cumulative), str(target))
        print(
            f"  createdb(target 1..{k}) {build:.1f}s, {residues / 1e6:.0f} M residues", flush=True
        )
        targets.append((k, residues, target))
    return targets


def _cap_cell(
    args: argparse.Namespace,
    work: Path,
    db: Path,
    qdb: Path,
    target: Path,
    *,
    cap: int,
    coverage_mode: int | None,
    label: str,
) -> tuple[float, int, similarity.RecordLedger, similarity.Saturation]:
    """One search, read back through the instrument the pass itself will use.

    Reading the hit table through `similarity` rather than counting lines is the point: the
    distinct-record counts per coverage reading are what decide whether the post-filter buys
    the three readings, and they cannot be recovered from a row count.
    """
    out_db = db / f"R-{label}"
    tmp = work / "tmp"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    params = similarity.search_argv(
        sensitivity=CAP_SENSITIVITY, cap=cap, coverage_mode=coverage_mode
    )
    elapsed = _mmseqs(
        "search",
        str(qdb),
        str(target),
        str(out_db),
        str(tmp),
        *params,
        "--threads",
        str(args.threads),
    )
    tsv = work / f"cap-hits-{label}.tsv"
    _mmseqs(
        "convertalis",
        str(qdb),
        str(target),
        str(out_db),
        str(tsv),
        "--format-output",
        similarity.CONVERTALIS_FORMAT,
    )
    ledger = similarity.RecordLedger()
    guard = similarity.Saturation(cap=cap)
    rows = 0
    with tsv.open() as handle:
        for row in similarity.parse_hits(handle):
            rows += 1
            ledger.observe(row)
            guard.observe(row.query)
    tsv.unlink(missing_ok=True)
    return elapsed, rows, ledger, guard


def _measure_caps(
    args: argparse.Namespace,
    work: Path,
    seed_fasta: Path,
    shard_paths: list[Path],
    shard_residues: list[int],
    payload: dict[str, Any],
    publish: Any,
) -> None:
    """Measure the two things D-105 and D-109 left open, in the one run where they interact.

    **The hit cap, where it binds.** D-105 measured raising 300 to 5,000 at a scale where the
    cap did not bind — 1.62x for 0.21% more records — which prices the wrong thing: a slack
    cap costs what it costs. What matters is the cap that truncates, because truncation is
    worst for the records matching the most seeds, which are the most viral-like ones. So the
    slack run reports the maximum hits per seed at each target size, and the binding runs are
    caps set as fractions of *that*. Hits per seed against target size is also what says
    whether 100,000 binds at the pass's scale, by extrapolation rather than by assertion.

    **Relaxed coverage.** D-109 buys the three coverage readings from one relaxed search and
    flagged the risk honestly: relaxing admits more rows, so it costs more and makes the cap
    likelier to bind. Running both coverage settings here prices that, and the two questions
    share a run because the interaction is the thing — a relaxed search with a binding cap is
    the cell where the design could fail.

    The fallback is already decided. If relaxed costs more than three separate `--cov-mode`
    cells, three cells is the design and D-109 is superseded; this run is what picks.
    """
    db = work / "db"
    db.mkdir(exist_ok=True)
    spent = 0.0
    cells: list[dict[str, Any]] = payload["searches"]

    qpath = work / "cap-query.faa"
    qseqs, qres = _subsample_fasta(seed_fasta, qpath, args.cap_query_denominator)
    if qseqs == 0:
        print("  cap measurement: query subsample is empty, nothing to measure", flush=True)
        return
    qdb = db / "QCAP"
    _mmseqs("createdb", str(qpath), str(qdb))
    print(
        f"\ncap measurement: query 1/{args.cap_query_denominator} = {qseqs:,} seeds, "
        f"{qres / 1e6:.0f} M residues",
        flush=True,
    )
    payload["cap_query"] = {
        "denominator": args.cap_query_denominator,
        "sequences": qseqs,
        "residues": qres,
        "sensitivity": CAP_SENSITIVITY,
    }

    targets = _build_targets(args, work, db, shard_paths, shard_residues, args.cap_shard_points)

    for k, residues, target in targets:
        # Relaxed first. It is the design under test, and if the budget runs out after one
        # coverage setting the useful half is the one that was not already decided.
        for coverage_mode in (None, 1):
            name = "relaxed" if coverage_mode is None else f"covmode{coverage_mode}"
            base = {
                "measurement": "hit-cap",
                "reading": name,
                "shards": k,
                "residues": residues,
                "query_sequences": qseqs,
                "coverage_mode": coverage_mode,
            }
            if args.search_budget_seconds and spent >= args.search_budget_seconds:
                print(
                    f"  budget of {args.search_budget_seconds:.0f}s spent; stopping before "
                    f"{name} x shards 1..{k}",
                    flush=True,
                )
                cells.append({**base, "skipped": "search budget exhausted"})
                publish()
                return

            try:
                elapsed, rows, ledger, guard = _cap_cell(
                    args,
                    work,
                    db,
                    qdb,
                    target,
                    cap=similarity.HIT_CAP,
                    coverage_mode=coverage_mode,
                    label=f"{name}-{k}-slack",
                )
            except RuntimeError as exc:
                print(f"  {name} x 1..{k} slack: FAILED {exc}", flush=True)
                cells.append({**base, "cap": similarity.HIT_CAP, "error": str(exc)})
                publish()
                continue
            spent += elapsed
            slack_records = {m: len(ledger.records(m)) for m in similarity.COVERAGE_READINGS}
            cells.append(
                {
                    **base,
                    "cap": similarity.HIT_CAP,
                    "binding": guard.saturated,
                    "search_wall_seconds": round(elapsed, 1),
                    "search_core_seconds": round(elapsed * args.threads, 1),
                    "hit_rows": rows,
                    "records_by_reading": {str(m): n for m, n in slack_records.items()},
                    "bands_by_reading": {
                        str(m): ledger.counts_by_band(m) for m in similarity.COVERAGE_READINGS
                    },
                    "saturation": guard.to_dict(),
                }
            )
            print(
                f"  {name} x 1..{k} cap {similarity.HIT_CAP}: {elapsed:.1f}s wall, {rows:,} rows, "
                f"max {guard.max_hits:,} hits/seed, records {slack_records}",
                flush=True,
            )
            publish()

            # The caps that bind are defined by what this scale actually produced, so they
            # are derived here rather than guessed before the run. The published cap is
            # unchanged by anything measured here: D-105 fixed it, and this prices it.
            reference = ledger.records(1)
            for fraction in args.cap_fractions:
                cap = max(1, int(guard.max_hits * fraction))
                if cap >= guard.max_hits:
                    continue
                if args.search_budget_seconds and spent >= args.search_budget_seconds:
                    cells.append({**base, "cap": cap, "skipped": "search budget exhausted"})
                    publish()
                    return
                try:
                    elapsed, rows, ledger_c, guard_c = _cap_cell(
                        args,
                        work,
                        db,
                        qdb,
                        target,
                        cap=cap,
                        coverage_mode=coverage_mode,
                        label=f"{name}-{k}-cap{cap}",
                    )
                except RuntimeError as exc:
                    print(f"  {name} x 1..{k} cap {cap}: FAILED {exc}", flush=True)
                    cells.append({**base, "cap": cap, "error": str(exc)})
                    publish()
                    continue
                spent += elapsed
                found = ledger_c.records(1)
                lost = len(reference - found)
                cells.append(
                    {
                        **base,
                        "cap": cap,
                        "cap_fraction_of_observed_max": fraction,
                        "binding": guard_c.saturated,
                        "search_wall_seconds": round(elapsed, 1),
                        "search_core_seconds": round(elapsed * args.threads, 1),
                        "hit_rows": rows,
                        "records_by_reading": {
                            str(m): len(ledger_c.records(m)) for m in similarity.COVERAGE_READINGS
                        },
                        "records_lost_vs_slack": lost,
                        "record_loss_fraction": (lost / len(reference)) if reference else None,
                        "saturation": guard_c.to_dict(),
                    }
                )
                print(
                    f"  {name} x 1..{k} cap {cap}: {elapsed:.1f}s wall, {rows:,} rows, "
                    f"lost {lost:,} of {len(reference):,} records",
                    flush=True,
                )
                publish()

    payload["cap_summary"] = _cap_summary(cells)
    publish()


def _cap_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """The two numbers the run exists to produce, derived from the cells.

    Derived here rather than in a notebook so the instance reports a conclusion even if
    nothing downstream ever reads the cells: there is no shell on it, and a run whose
    arithmetic waits until it is home is a run that can come home without it.
    """
    slack = [c for c in cells if c.get("cap") == similarity.HIT_CAP and "search_wall_seconds" in c]
    by_shards: dict[int, dict[str, dict[str, Any]]] = {}
    for cell in slack:
        by_shards.setdefault(cell["shards"], {})[cell["reading"]] = cell

    coverage_cost: list[dict[str, Any]] = []
    for shards, readings in sorted(by_shards.items()):
        relaxed, filtered = readings.get("relaxed"), readings.get("covmode1")
        if not (relaxed and filtered):
            continue
        ratio = relaxed["search_wall_seconds"] / filtered["search_wall_seconds"]
        coverage_cost.append(
            {
                "shards": shards,
                "residues": relaxed["residues"],
                "relaxed_wall_seconds": relaxed["search_wall_seconds"],
                "filtered_wall_seconds": filtered["search_wall_seconds"],
                "cost_ratio": round(ratio, 3),
                # Three separate --cov-mode searches is the fallback D-109 names, so the
                # relaxed search is only worth it below 3x. Stated as the comparison rather
                # than as a verdict, because the verdict is a decision entry's job.
                "cheaper_than_three_cells": ratio < len(similarity.COVERAGE_READINGS),
                "row_ratio": round(relaxed["hit_rows"] / max(1, filtered["hit_rows"]), 3),
            }
        )

    hits_per_seed = [
        {
            "shards": c["shards"],
            "residues": c["residues"],
            "reading": c["reading"],
            "max_hits_per_seed": c["saturation"]["max_hits_per_query"],
            "max_hits_per_seed_per_g_residue": round(
                c["saturation"]["max_hits_per_query"] / (c["residues"] / 1e9), 1
            )
            if c["residues"]
            else None,
        }
        for c in slack
    ]
    return {
        "coverage_cost": coverage_cost,
        "hits_per_seed": hits_per_seed,
        "published_cap": similarity.HIT_CAP,
        "note": (
            "max_hits_per_seed_per_g_residue extrapolates linearly to the pass's target size "
            "and is what says whether the published cap binds there. The caps run below the "
            "observed maximum price truncation at this scale; they do not change the "
            "published cap, which D-105 fixed."
        ),
    }


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

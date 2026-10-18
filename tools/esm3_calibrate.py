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

from amazebio import repro, seeds, shardstore, similarity, uniref
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
ARTEFACT_NAMES = {
    "curve": "calibration.json",
    "caps": "cap-measurement.json",
    "band": "band.json",
}

#: Progress keys, one per mode for the same reason the artefacts are. Separate from the
#: artefact because a heartbeat is not a deliverable, and small because it is overwritten
#: every few minutes in a bucket that cannot delete anything.
HEARTBEAT_NAMES = {
    "curve": "progress-curve.json",
    "caps": "progress-caps.json",
    "band": "progress-band.json",
}


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
        "--stage-sample",
        action="store_true",
        help="after the corpus pass, stage the sample — shards, seed set and a checksummed "
        "manifest — so later runs skip the pass. Refuses rather than overwriting: the "
        "corpus bucket has no DeleteObject",
    )
    ap.add_argument(
        "--sample-from",
        metavar="S3_URI",
        help="s3:// uri of a staged sample's manifest. Loads and verifies it instead of "
        "running the corpus pass, which costs about 52 minutes whatever the sample rate "
        "(D-122, D-123)",
    )
    ap.add_argument(
        "--stage-sidecars-only",
        action="store_true",
        help="upload just the strata sidecars into an existing sample's prefix, leaving its "
        "shards, seed set and manifest untouched. For the sample staged before the sidecars "
        "existed (D-142), so later bands do not each rebuild them",
    )
    ap.add_argument(
        "--resume-band-from",
        metavar="S3_URI",
        help="a band.json an earlier run published. Its cells for this same band and shard "
        "are reused rather than recomputed, and carried into the combined result — without "
        "it a re-run rebuys every completed cell and then overwrites them with the new one",
    )
    ap.add_argument(
        "--verify-sample-against",
        metavar="S3_URI",
        help="after the corpus pass, check the rebuilt shards are byte-identical to this "
        "staged manifest. The staged 2.5% sample carries no strata sidecars (D-142), so "
        "building them needs the pass re-run; this is what makes a band over the rebuilt "
        "shards a result about the staged sample rather than about a lookalike",
    )
    ap.add_argument(
        "--seeds-uri",
        help="score this seed set instead of the viral one, with its .taxids.tsv sidecar "
        "taken from the same prefix. The shards and their strata still come from the "
        "corpus pass or the staged sample; only the query changes (D-159)",
    )
    ap.add_argument(
        "--band-denominator",
        type=int,
        default=100,
        help="the seed band to run: 1/N of the seed set by hash. 100 is D-134's band 1, "
        "which re-runs the cap measurement's own query set; 1 is the whole set (default: "
        "%(default)s)",
    )
    ap.add_argument(
        "--band-shard",
        type=int,
        default=0,
        help="which staged shard the band searches. D-128 runs one shard, not eight "
        "(default: %(default)s)",
    )
    ap.add_argument(
        "--measure",
        choices=("curve", "caps", "band"),
        default="curve",
        help="`curve` times the cost model's grid, which is what D-104 was fitted on. "
        "`caps` measures the two items D-105 and D-109 left open: what the hit cap costs "
        "where it binds, and what relaxing coverage costs to buy the three readings from "
        "one search. `band` is the pass itself — one seed band's six cells over one shard, "
        "reporting rates with intervals (default: %(default)s)",
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
    if args.stage_sample and args.stage_sidecars_only:
        raise SystemExit(
            "--stage-sample stages the whole sample; --stage-sidecars-only adds sidecars to "
            "one already staged. Pick one."
        )
    if args.stage_sample and args.sample_from:
        raise SystemExit("--stage-sample builds a sample; --sample-from loads one. Pick one.")
    if args.sample_from and not args.sample_from.startswith("s3://"):
        raise SystemExit("--sample-from takes an s3:// uri pointing at a staged manifest")
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
            config=Config(
                retries={"max_attempts": 10, "mode": "standard"},
                # Without these a stalled call waits on botocore's defaults and a hung one
                # never returns at all; 2026-10-17 lost a run to 25 minutes of silence in a
                # step that should take under a minute.
                connect_timeout=15,
                read_timeout=120,
            ),
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


def _chunks(stream: Any, limit: int, progress_seconds: float, heartbeat: Any = None) -> Any:
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
            elapsed = now - started
            print(
                f"    {human(read)} decompressed, {human(read / max(elapsed, 1e-9))}/s",
                flush=True,
            )
            if heartbeat is not None:
                heartbeat(read, elapsed)
            last = now
        yield chunk


def _make_heartbeat(client: Any, bucket: str, prefix: str, name: str, commit: str | None) -> Any:
    """Write a few hundred bytes to S3 saying how far the corpus pass has got.

    Measured need, 2026-10-16: an instance ran 95 minutes on a pass due in 53 with no way to
    tell work from a wedge. The console froze at the boot line — `GetConsoleOutput` is
    best-effort and stopped there — and in this account `cloudwatch:GetMetricStatistics` and
    `ec2:GetConsoleScreenshot` are both denied, as are SSH and SSM by policy. So every channel
    was closed except S3, and the pass published nothing until it finished: the only signal
    arrived after the thing it would have reported on.

    A heartbeat closes that. It is its own key rather than part of the result artefact,
    because the result is a deliverable and a progress file is not, and because the corpus
    bucket has no `DeleteObject` — overwriting one small key repeatedly is the cheapest thing
    to leave behind. `None` when there is no client, so a local run is unaffected.
    """
    if client is None:
        return None
    key = f"{prefix}/results/a1-6/{name}"

    def beat(read: int, elapsed: float) -> None:
        body = {
            "decompressed_bytes": read,
            "elapsed_seconds": round(elapsed, 1),
            "bytes_per_second": round(read / max(elapsed, 1e-9)),
            "stage": "corpus-pass",
            "code_commit": commit,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            client.put_object(
                Bucket=bucket, Key=key, Body=json.dumps(body, sort_keys=True).encode()
            )
        except Exception as exc:  # A failed heartbeat must never fail the run it reports on.
            print(f"    heartbeat failed: {type(exc).__name__}", flush=True)

    return beat


def _mmseqs(*argv: str) -> float:
    """Run one mmseqs command, returning wall seconds. Output goes to the console."""
    started = time.monotonic()
    proc = subprocess.run(["mmseqs", *argv], capture_output=True, text=True)
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(f"mmseqs {argv[0]} failed ({proc.returncode}): {' / '.join(tail)}")
    return elapsed


def _sort_by_target(tsv: Path, work: Path, memory: str = "1G") -> Path:
    """Sort a hit table by its target column, so it can be aggregated in constant memory.

    `LC_ALL=C` is not cosmetic. `similarity.TargetStream` verifies order with Python string
    comparison, which is codepoint order, while `sort` under a UTF-8 locale uses collation
    that ignores case and punctuation differently — so a locale-sorted file is *not* sorted by
    the comparison the aggregator checks, and the run would die claiming its own sorted input
    was unsorted. Byte order on both sides, or neither.

    Sorting is the trade `TargetStream` exists to make: bounded disk and a bounded `-S` budget
    instead of a dictionary whose size is the result the pass is trying to measure.
    """
    out = tsv.with_name(tsv.stem + ".by-target.tsv")
    subprocess.run(
        ["sort", "-t", "\t", "-k", "2,2", "-S", memory, "-T", str(work), "-o", str(out), str(tsv)],
        check=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    return out


def _stream_hit_rows(path: Path) -> Any:
    """Parse a hit table row by row, holding one row at a time."""
    with path.open() as handle:
        yield from similarity.parse_hits(handle)


def _put_large(client: Any, bucket: str, key: str, path: Path) -> None:
    """Upload one file, by managed transfer where the client offers one.

    `put_object(Body=path.read_bytes())` reads the whole file into memory and sends it as a
    single request, which for a 450 MB shard means one long-running call that a read timeout
    can strand and a retry must restart from zero. `upload_file` chunks it, retries parts and
    streams from disk. The fallback keeps the local stand-ins and tests working, where the
    files are bytes rather than gigabytes.
    """
    started = time.monotonic()
    size = path.stat().st_size
    if hasattr(client, "upload_file"):
        client.upload_file(str(path), bucket, key)
    else:
        client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
    elapsed = max(time.monotonic() - started, 1e-9)
    print(
        f"  staged {key}  ({size:,} bytes, {elapsed:.0f}s, {size / elapsed / 1e6:.0f} MB/s)",
        flush=True,
    )


def _progress(
    client: Any, bucket: str, prefix: str, args: argparse.Namespace, **fields: Any
) -> None:
    """Write a progress object for any stage, not just the corpus pass.

    The corpus pass got a heartbeat this morning because an unobservable hour cost a day. The
    staging step was written after that and got none, and then hung — so the same blindness
    returned in the code added to cure it. Every step that can take minutes reports.
    """
    if client is None:
        return
    key = f"{prefix}/results/a1-6/{HEARTBEAT_NAMES[args.measure]}"
    body = {
        "code_commit": args.code_commit,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **fields,
    }
    try:
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(body, sort_keys=True).encode())
    except Exception as exc:  # Never fail the run for the sake of reporting on it.
        print(f"    progress write failed: {type(exc).__name__}", flush=True)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    bucket, _, key = uri[5:].partition("/")
    return bucket, key


def _load_staged_sample(
    args: argparse.Namespace,
    client: Any,
    work: Path,
    seed_fasta: Path,
    shard_paths: list[Path],
) -> tuple[seeds.SeedCounts, list[int], list[int], shardstore.ShardManifest]:
    """Fetch a staged sample, verify every object, and skip the corpus pass.

    The pass costs about 52 minutes whatever the sample rate (D-123) and is currently paid on
    every launch, while the broad arm's sweep is dozens of launches (D-122). This is the other
    half of that fix: the sample is built once and verified on every load.

    Verification is not optional and not sampled. The corpus bucket has no `DeleteObject`, so
    a bad staged shard can only be superseded, never removed — checking every digest on load is
    the only thing standing between that and a published number.
    """
    if client is None:
        raise SystemExit("--sample-from needs S3; it cannot be combined with --source")
    bucket, key = _parse_s3_uri(args.sample_from)
    print(f"loading staged sample from {args.sample_from}", flush=True)
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    staged = shardstore.ShardManifest.from_json(body)
    staged.check_self_consistent()

    if staged.release != args.release or staged.tier != args.tier:
        raise SystemExit(
            f"staged sample is {staged.tier} {staged.release}, this run asked for "
            f"{args.tier} {args.release}"
        )
    if staged.buckets != args.buckets:
        raise SystemExit(
            f"staged sample has {staged.buckets} shards and this run is configured for "
            f"{args.buckets}. Shards 1..k is only a valid sample at k times the rate if the "
            f"partition matches, so this is refused rather than reinterpreted."
        )
    if staged.sample_rate != args.sample_rate:
        print(
            f"  note: staged at rate {staged.sample_rate}, run configured for "
            f"{args.sample_rate}; the staged rate is what the sample is",
            flush=True,
        )
        args.sample_rate = staged.sample_rate

    local: dict[str, Path] = {}
    # The sidecars land beside the file they describe, keyed by name rather than by index:
    # they are the strata for the shard FASTAs and the seed set, and `write_taxid_row` named
    # them `<stem>.taxids.tsv` (D-142). A sample staged before they existed lists none, and
    # that sample still owes a corpus pass to produce them.
    sidecar_dests = {
        f"{dest.stem}.taxids.tsv": dest.with_suffix(".taxids.tsv")
        for dest in (seed_fasta, *shard_paths)
    }
    sidecar_pairs = []
    for obj in staged.sidecars or ():
        dest = sidecar_dests.get(obj.key.rsplit("/", 1)[-1])
        if dest is None:
            raise SystemExit(
                f"staged sidecar {obj.key!r} does not match any shard or the seed set; the "
                "strata and the records they describe have to be the same files"
            )
        sidecar_pairs.append((obj, dest))
    for obj, dest in [
        (staged.seed_fasta, seed_fasta),
        *[(sh, shard_paths[sh.index]) for sh in staged.shards],
        *sidecar_pairs,
    ]:
        client.download_file(bucket, obj.key, str(dest))
        local[obj.key] = dest
        print(f"  fetched {obj.key} ({obj.bytes:,} bytes)", flush=True)
    shardstore.verify_all(staged, local)
    print(f"  verified {len(local)} objects against their staged digests", flush=True)

    counts = seeds.SeedCounts()
    if staged.seed_counts:
        for name in (
            "clusters",
            "residues",
            "seeded",
            "seeded_residues",
            "representative_not_seeded",
            "mixed",
        ):
            value = staged.seed_counts.get(name)
            if value is not None:
                setattr(counts, name, value)
    else:
        # Only the denominators were carried. Set those and leave the rest at zero rather
        # than inventing them — but say so, because a zero that reads as a measurement is
        # the failure this branch exists to avoid.
        counts.clusters = staged.corpus_clusters
        counts.seeded = staged.viral_seeded_clusters
        print(
            "  note: this manifest carries only the denominators, so the "
            "representative-versus-member counts are absent rather than zero",
            flush=True,
        )
    return (
        counts,
        [sh.clusters for sh in staged.shards],
        [sh.residues for sh in staged.shards],
        staged,
    )


def _stage_sample(
    args: argparse.Namespace,
    client: Any,
    bucket: str,
    prefix: str,
    seed_fasta: Path,
    shard_paths: list[Path],
    counts: seeds.SeedCounts,
    shard_counts: list[int],
    shard_residues: list[int],
    sidecar_paths: list[Path] | None = None,
) -> str | None:
    """Stage the sample so no later run pays for the corpus pass again.

    Refuses on a key that already exists. In a bucket with no `DeleteObject` an overwrite is
    not a replacement but the irreversible loss of the earlier object, and `AGENTS.md` records
    what that already cost once.
    """
    if client is None:
        print("  --stage-sample needs S3; nothing staged", flush=True)
        return None
    # Under the run's prefix, not at the bucket root. Measured the hard way on 2026-10-17:
    # `sample_prefix` returns a path relative to the project prefix, and staging used it as an
    # absolute key, which would have written several gigabytes outside `corpora/` — permanently,
    # in a bucket with no DeleteObject.
    sample_root = f"{prefix}/{shardstore.sample_prefix(args.release, args.tier, args.sample_rate)}"
    if args.stage_sidecars_only:
        # The sample was staged before the sidecars existed (D-142). Its shards and seed set
        # are already there and must not be rewritten, so only the sidecars go up — and the
        # manifest is left alone, since this run cannot prove anything about objects it did
        # not produce. Without this every later band pays the 52-minute pass again purely to
        # rebuild them, and D-134's band 2 is six launches.
        plan = shardstore.plan_uploads(sample_root, [], seed_fasta, sidecar_paths)[1:]
    else:
        plan = shardstore.plan_uploads(sample_root, shard_paths, seed_fasta, sidecar_paths)
    manifest_key = f"{sample_root}/{shardstore.MANIFEST_NAME}"

    present = shardstore.existing_keys(client, bucket, sample_root + "/")
    wanted = {k for _, k in plan}
    if not args.stage_sidecars_only:
        wanted |= {manifest_key}
    clashes = sorted(wanted & present)
    if clashes:
        raise SystemExit(
            "refusing to stage over existing objects — this bucket has no DeleteObject, so "
            f"an overwrite destroys the earlier object irreversibly: {clashes[:4]}"
        )

    total = len(plan)
    print(f"  staging {total} objects under s3://{bucket}/{sample_root}/", flush=True)

    if args.stage_sidecars_only:
        for path, key in plan:
            _put_large(client, bucket, key, path)
        _progress(client, bucket, prefix, args, stage="staging", done=total, total=total)
        print(
            f"  staged {total} sidecars; the sample's own objects were left untouched",
            flush=True,
        )
        return f"s3://{bucket}/{manifest_key}"

    staged_shards = []
    shard_plan = plan[1 : 1 + len(shard_paths)]
    sidecar_plan = plan[1 + len(shard_paths) :]
    for (path, key), index in zip(shard_plan, range(len(shard_paths)), strict=True):
        _put_large(client, bucket, key, path)
        staged_shards.append(
            shardstore.describe_shard(
                path, key, index=index, clusters=shard_counts[index], residues=shard_residues[index]
            )
        )
        _progress(client, bucket, prefix, args, stage="staging", done=index + 1, total=total)
    seed_path, seed_key = plan[0]
    _put_large(client, bucket, seed_key, seed_path)
    staged_sidecars = []
    for path, key in sidecar_plan:
        _put_large(client, bucket, key, path)
        staged_sidecars.append(shardstore.describe(path, key))
    _progress(client, bucket, prefix, args, stage="staging", done=total, total=total)

    staged = shardstore.ShardManifest(
        release=args.release,
        tier=args.tier,
        sample_rate=args.sample_rate,
        buckets=args.buckets,
        corpus_clusters=counts.clusters,
        viral_seeded_clusters=counts.seeded,
        seed_fasta=shardstore.describe(seed_path, seed_key),
        shards=staged_shards,
        sidecars=staged_sidecars or None,
        seed_counts={k: v for k, v in counts.to_dict().items() if isinstance(v, int)},
        code_commit=args.code_commit,
        taxdump_pin=seeds.TAXDUMP_2023_04.date,
    )
    staged.check_self_consistent()
    client.put_object(Bucket=bucket, Key=manifest_key, Body=staged.to_json().encode())
    uri = f"s3://{bucket}/{manifest_key}"
    print(f"  staged manifest {uri}", flush=True)
    return uri


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

        if args.resume_band_from:
            name = args.artefact_name or ARTEFACT_NAMES["band"]
            destination = f"{prefix}/results/a1-6/{name}"
            src_bucket, src_key = _parse_s3_uri(args.resume_band_from)
            if src_key == destination and src_bucket == bucket:
                raise SystemExit(
                    f"--resume-band-from reads {args.resume_band_from} and this run would "
                    f"write the same key. The first publish happens before the band stage, "
                    "so the cells being resumed would be destroyed before they were read — "
                    "and this bucket has no DeleteObject. Pass --artefact-name to write "
                    "somewhere else."
                )
        if args.verify_sample_against and args.sample_from:
            raise SystemExit(
                "--sample-from loads a staged sample and already verifies it; "
                "--verify-sample-against checks one this run rebuilds. Pick one."
            )
        # Read before the corpus pass, because the first `publish()` lands before the band
        # stage does and would otherwise rewrite the very object being resumed from. The
        # same-key case is refused above; this ordering covers the rest.
        prior: list[dict[str, Any]] | None = None
        if args.resume_band_from:
            if client is None:
                raise SystemExit("--resume-band-from needs S3")
            rbucket, rkey = _parse_s3_uri(args.resume_band_from)
            rbody = client.get_object(Bucket=rbucket, Key=rkey)["Body"].read()
            prior = json.loads(rbody).get("band", {}).get("cells") or []
            print(f"loaded {len(prior)} published cells from {args.resume_band_from}", flush=True)
            manifest.parameter("resumed_from", args.resume_band_from)

        staged: shardstore.ShardManifest | None = None
        # Set by the corpus pass below and left empty by `--sample-from`, which runs no pass
        # and therefore produces no sidecars. The two options are mutually exclusive, so a
        # staging run always takes the corpus-pass branch; this is declared here so the
        # staging call does not depend on which branch happened to assign it.
        sidecar_paths: list[Path] = []
        if args.sample_from:
            # The corpus pass is skipped entirely. The shards, the seed set and the
            # denominators all come from the staged manifest, and every object is verified
            # against its recorded digest before anything is searched against it.
            manifest.parameter("sample_from", args.sample_from)
            counts, shard_counts, shard_residues, staged = _load_staged_sample(
                args, client, work, seed_fasta, shard_paths
            )
            manifest.parameter("staged_sample_commit", staged.code_commit)
            reader = None
            stream = None
            label = args.sample_from
            corpus_seconds = 0.0
        else:
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
            # The strata sidecar, one per shard, beside the FASTA. It exists because the FASTA
            # cannot carry the taxid and the interval needs one for every sampled cluster
            # rather than only the matching ones (D-142). Written in the same pass, so a
            # sample staged from here is self-describing and no second corpus pass is owed.
            taxid_paths = [p.with_suffix(".taxids.tsv") for p in shard_paths]
            taxid_handles = [p.open("wb") for p in taxid_paths]
            # The sample and the seed set are independent: a viral cluster can be in both, and
            # must be, or the target would be missing exactly the records the filter is
            # supposed to remove.
            config = seeds.ScanConfig(
                denylist_taxids=frozenset(viral), sample_rate=args.sample_rate, buckets=args.buckets
            )
            try:
                seed_taxid_path = seed_fasta.with_suffix(".taxids.tsv")
                sidecar_paths = [*taxid_paths, seed_taxid_path]
                with seed_fasta.open("wb") as seedfh, seed_taxid_path.open("wb") as seed_taxidfh:
                    for batch in seeds.scan_parallel(
                        _chunks(
                            stream,
                            args.limit_bytes,
                            args.progress_seconds,
                            _make_heartbeat(
                                client,
                                bucket,
                                prefix,
                                HEARTBEAT_NAMES[args.measure],
                                args.code_commit,
                            ),
                        ),
                        config,
                        workers=args.workers,
                        batch_bytes=args.batch_bytes,
                    ):
                        counts.merge(batch.counts)
                        for cluster_id, sequence, taxid in batch.seeds:
                            seeds.write_fasta(seedfh, cluster_id, sequence)
                            similarity.write_taxid_row(seed_taxidfh, cluster_id, taxid)
                        for shard, cluster_id, sequence, taxid in batch.samples:
                            seeds.write_fasta(handles[shard], cluster_id, sequence)
                            similarity.write_taxid_row(taxid_handles[shard], cluster_id, taxid)
                            shard_counts[shard] += 1
                            shard_residues[shard] += len(sequence)
            finally:
                for handle in (*handles, *taxid_handles):
                    handle.close()
            corpus_seconds = time.monotonic() - started

            if args.verify_sample_against:
                # Before anything is searched, and before the strata are even read: if the
                # rebuilt shards are not the staged ones, every number this run would publish
                # is about a different sample and the run should cost nothing further.
                if client is None:
                    raise SystemExit("--verify-sample-against needs S3")
                vbucket, vkey = _parse_s3_uri(args.verify_sample_against)
                body = client.get_object(Bucket=vbucket, Key=vkey)["Body"].read()
                against = shardstore.ShardManifest.from_json(body)
                print(
                    f"verifying the rebuilt sample against {args.verify_sample_against}",
                    flush=True,
                )
                shardstore.verify_rebuilt(against, seed_fasta, shard_paths)
                print(
                    f"  identical to the staged sample: {len(shard_paths)} shards and the "
                    "seed set match their recorded digests",
                    flush=True,
                )
                manifest.parameter("verified_against", args.verify_sample_against)

        if staged is not None:
            print(
                f"\nstaged sample: {counts.clusters:,} clusters in the corpus it was drawn "
                f"from ({counts.seeded:,} viral-seeded), no corpus pass run",
                flush=True,
            )
        else:
            print(
                f"\ncorpus pass: {counts.clusters:,} clusters in {corpus_seconds:.0f}s"
                f"  ({counts.seeded:,} viral-seeded)",
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
            # None rather than 0 on the staged path: a zero here would read as a corpus
            # pass that took no time, which is exactly the kind of number that gets cited.
            "corpus_pass_seconds": None if staged is not None else round(corpus_seconds, 1),
            "sample_source": args.sample_from if staged is not None else "corpus-pass",
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
        if not args.seeds_uri:
            upload(seed_fasta, "viral-seed-set")

        if args.stage_sample or args.stage_sidecars_only:
            staged_uri = _stage_sample(
                args,
                client,
                bucket,
                prefix,
                seed_fasta,
                shard_paths,
                counts,
                shard_counts,
                shard_residues,
                sidecar_paths,
            )
            if staged_uri:
                payload["staged_sample"] = staged_uri
                # An output, not a parameter. `repro` closes the parameter window as soon as
                # an output is recorded — the rule that thresholds are fixed before results
                # are inspected — and the seed set has already been uploaded by this point, so
                # declaring this as a parameter is refused and takes the run down with it.
                manifest.output_object(staged_uri, role="staged-sample")
                publish()

        # Swap in a different denylist's seed set, after everything that checks the viral
        # one. The corpus pass still builds the shards and their strata, because those are
        # the target and the denominator and belong to the sample rather than to a denylist;
        # only the query changes. Placed here deliberately: `--verify-sample-against` digests
        # the viral seed FASTA against the staged manifest, so replacing it any earlier would
        # fail that check, and `--stage-sample` would stage the wrong seed set under the
        # sample's key.
        if args.seeds_uri:
            seed_fasta = _load_external_seeds(args.seeds_uri, client, work)
            payload["seed_set"] = args.seeds_uri
            manifest.parameter("seeds_uri", args.seeds_uri)

        if not args.skip_search:
            if args.measure == "band":
                _run_band(
                    args,
                    work,
                    seed_fasta,
                    shard_paths,
                    shard_residues,
                    taxonomy,
                    payload,
                    publish,
                    prior,
                )
            elif args.measure == "caps":
                _measure_caps(
                    args,
                    work,
                    seed_fasta,
                    shard_paths,
                    shard_residues,
                    payload,
                    publish,
                    client,
                    bucket,
                    prefix,
                )
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
        manifest.output_file(
            seed_fasta, role="scored-seed-set" if args.seeds_uri else "viral-seed-set"
        )
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
    client: Any = None,
    bucket: str = "",
    prefix: str = "",
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
    # Published now rather than with the first cell. Everything between here and that cell —
    # subsampling the seed set, the query database, concatenating shards, two target databases
    # — is tens of minutes of real work, and leaving it unpublished made a working run
    # indistinguishable from a stuck one for the third time in a day (D-127).
    publish()

    _progress(
        client, bucket, prefix, args, stage="cap-build-targets", points=str(args.cap_shard_points)
    )
    targets = _build_targets(args, work, db, shard_paths, shard_residues, args.cap_shard_points)
    _progress(client, bucket, prefix, args, stage="cap-targets-ready", targets=len(targets))

    # Reading 1 is the only one both coverage settings can produce, which makes it the one
    # place the post-filter can be checked against the aligner doing the filtering itself.
    # D-109 assumes they agree; a local rehearsal on 1,200 synthetic records disagreed by one
    # record, so the agreement is measured here rather than assumed.
    relaxed_reading1: dict[int, set[str]] = {}

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

            _progress(
                client,
                bucket,
                prefix,
                args,
                stage="cap-search",
                cell=f"{name}-shards{k}-slack",
                residues=residues,
            )
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
            agreement: dict[str, Any] | None = None
            if coverage_mode is None:
                relaxed_reading1[k] = ledger.records(1)
            elif coverage_mode == 1 and k in relaxed_reading1:
                post = relaxed_reading1[k]
                native = ledger.records(1)
                union = post | native
                agreement = {
                    "post_filtered_records": len(post),
                    "aligner_filtered_records": len(native),
                    "only_post_filtered": len(post - native),
                    "only_aligner_filtered": len(native - post),
                    "jaccard": (len(post & native) / len(union)) if union else None,
                }
                print(
                    f"    reading-1 agreement: post {len(post):,} vs aligner {len(native):,}, "
                    f"jaccard {agreement['jaccard']}",
                    flush=True,
                )
            cells.append(
                {
                    **base,
                    **({"reading1_agreement": agreement} if agreement else {}),
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
        # The check on D-109's premise rather than its price: if the post-filter and the
        # aligner's own --cov-mode 1 do not pick the same records, the three readings are
        # recovered approximately and the write-up has to say by how much.
        "reading1_agreement": [
            {"shards": c["shards"], **c["reading1_agreement"]}
            for c in cells
            if c.get("reading1_agreement")
        ],
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


def _filter_seed_fasta(src: Path, dest: Path, denominator: int) -> int:
    """Write the band's seed sample, returning how many seeds it holds.

    Streams rather than loading: the full seed set is 3.16M records. The ids come back from
    `select_seeds` by the same hash rule the cap run used, so band 1 re-runs that query set.
    """
    kept = 0
    with src.open("rb") as fh, dest.open("wb") as out:
        keep = False
        for raw in fh:
            if raw.startswith(b">"):
                ident = raw[1:].split()[0].decode("ascii", "replace")
                keep = bool(next(similarity.select_seeds([ident], denominator), None))
                kept += keep
            if keep:
                out.write(raw)
    return kept


def _seed_family_count(sidecar: Path, denominator: int, taxonomy: Any) -> int:
    """The realised seed-family count D-134 ships with every rate.

    Counts distinct families among the *sampled* seeds, not the whole seed set: it is the
    sample's family coverage that limits what the band can say at family level, and quoting
    the full set's would overstate it by the factor the sampling exists to buy.
    """
    families: set[str] = set()
    with sidecar.open() as fh:
        for cluster_id, taxid in similarity.parse_taxid_rows(fh):
            if not next(similarity.select_seeds([cluster_id], denominator), None):
                continue
            family = None if taxid is None else taxonomy.ancestor_at_rank(taxid)
            families.add(similarity.stratum_id(cluster_id, family))
    return len(families)


def _band_cell(
    args: argparse.Namespace,
    work: Path,
    db: Path,
    qdb: Path,
    target: Path,
    key: similarity.CellKey,
    index: similarity.FamilyIndex,
) -> similarity.TargetStream:
    """One cell's search, read back through the stream the band reports from.

    The search is the aligner's own coverage filter at the cell's `--cov-mode`, not a relaxed
    search with a post-filter: D-124 established that two filtered searches recover all three
    readings exactly, and that the post-filtered set was a strict superset rather than the
    same set.
    """
    out_db = db / f"B-{key.slug()}"
    tmp = work / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    params = similarity.search_argv(
        sensitivity=key.sensitivity, cap=similarity.HIT_CAP, coverage_mode=key.cov_mode
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
    print(f"  search {key.slug()} {elapsed:.0f}s", flush=True)
    tsv = work / f"band-hits-{key.slug()}.tsv"
    _mmseqs(
        "convertalis",
        str(qdb),
        str(target),
        str(out_db),
        str(tsv),
        "--format-output",
        similarity.CONVERTALIS_FORMAT,
    )
    sorted_tsv = _sort_by_target(tsv, work)
    tsv.unlink(missing_ok=True)
    stream = similarity.TargetStream.for_search(key.cov_mode, index=index)
    guard = similarity.Saturation(cap=similarity.HIT_CAP)
    with sorted_tsv.open() as handle:
        for row in similarity.parse_hits(handle):
            stream.observe(row)
            guard.observe(row.query)
    stream.close()
    sorted_tsv.unlink(missing_ok=True)
    guard.check()
    return stream


def _load_external_seeds(uri: str, client: Any, work: Path) -> Path:
    """Fetch a seed set and its strata sidecar, for scoring a denylist this pass did not build.

    A1.8's select-agent arm runs the same six cells over the same shards as A1.6's band 1 and
    differs only in the query set (D-159), so the alternative to this parameter is a second
    copy of the band pass. The sidecar is required rather than optional: without a taxid per
    seed there is no realised seed-family count, and `_run_band` refuses rather than publish a
    rate with no interval (D-142).

    The two objects are named by convention — `X.faa` and `X.taxids.tsv` — because they are
    written as a pair and a mismatched pair is worse than a missing one.
    """
    if client is None:
        raise SystemExit("--seeds-uri needs S3")
    bucket, key = _parse_s3_uri(uri)
    if not key.endswith(".faa"):
        raise SystemExit(f"--seeds-uri should name a .faa seed set, got {key}")
    sidecar_key = key[: -len(".faa")] + ".taxids.tsv"
    dest = work / "scored-seeds.faa"
    sidecar = dest.with_suffix(".taxids.tsv")
    for src, target in ((key, dest), (sidecar_key, sidecar)):
        print(f"fetching s3://{bucket}/{src}", flush=True)
        try:
            body = client.get_object(Bucket=bucket, Key=src)["Body"]
        except Exception as exc:
            raise SystemExit(
                f"cannot read s3://{bucket}/{src}: {exc}. The seed set and its strata sidecar "
                "are written as a pair and this pass needs both."
            ) from exc
        with target.open("wb") as fh:
            while chunk := body.read(8 << 20):
                fh.write(chunk)
        print(f"  {target.name}: {target.stat().st_size:,} bytes", flush=True)
    return dest


def _run_band(
    args: argparse.Namespace,
    work: Path,
    seed_fasta: Path,
    shard_paths: list[Path],
    shard_residues: list[int],
    taxonomy: Any,
    payload: dict[str, Any],
    publish: Any,
    prior: list[dict[str, Any]] | None = None,
) -> None:
    """One seed band: six cells over the target shard, each published as it finishes.

    The cell is the atom (D-134), so a reclaim or a timeout costs only the cell in flight and
    a re-run skips what is already on disk. Cells are ordered cheapest sensitivity first, so
    a run that is cut short has produced whole cells rather than two thirds of one.
    """
    denominator = args.band_denominator
    shard = args.band_shard
    if shard >= len(shard_paths):
        raise SystemExit(f"--band-shard {shard} but only {len(shard_paths)} shards are present")

    sidecar = shard_paths[shard].with_suffix(".taxids.tsv")
    if not sidecar.exists():
        raise SystemExit(
            f"no strata sidecar at {sidecar.name}. The staged sample predates them, so this "
            "band owes one corpus pass to build it — see D-142. Refusing rather than "
            "reporting a rate with no interval."
        )
    print(f"building strata from {sidecar.name}", flush=True)
    with sidecar.open() as fh:
        index = similarity.FamilyIndex.build(similarity.parse_taxid_rows(fh), taxonomy)
    unplaced_share = index.unplaced_records / max(index.searched_records, 1)
    print(
        f"  {index.searched_records:,} records, {len(index.totals):,} strata, "
        f"{index.unplaced_records:,} unplaced ({unplaced_share:.1%})",
        flush=True,
    )

    seed_sidecar = seed_fasta.with_suffix(".taxids.tsv")
    if not seed_sidecar.exists():
        raise SystemExit(f"no seed strata sidecar at {seed_sidecar.name}; see D-142")
    seed_families = _seed_family_count(seed_sidecar, denominator, taxonomy)

    band_seeds = work / f"band-seeds-q{denominator}.faa"
    kept = _filter_seed_fasta(seed_fasta, band_seeds, denominator)
    print(f"  band 1/{denominator}: {kept:,} seeds, {seed_families:,} seed families", flush=True)

    db = work / "db"
    db.mkdir(parents=True, exist_ok=True)
    qdb = db / f"Q-q{denominator}"
    _mmseqs("createdb", str(band_seeds), str(qdb))
    target = db / f"T{shard}"
    _mmseqs("createdb", str(shard_paths[shard]), str(target))

    payload["band"] = {
        "seed_denominator": denominator,
        "lower_bound": denominator > 1,
        "shard": shard,
        "seeds_searched": kept,
        "seed_families": seed_families,
        "searched_records": index.searched_records,
        "strata": len(index.totals),
        "unplaced_records": index.unplaced_records,
        "cells": [],
    }
    publish()

    # Cells an earlier run of this same band already paid for. `CellKey` documents the skip
    # and nothing implemented it until a spot reclaim took the sixth cell of six and a re-run
    # would have rebought the five that survived — and, because one result object is rewritten
    # on every publish, would have replaced them with the one new cell.
    cells: list[similarity.CellResult] = []
    done: dict[str, similarity.CellResult] = {}
    for raw in prior or ():
        cell = similarity.cell_from_dict(raw)
        if cell.key.shard != shard or cell.key.seed_denominator != denominator:
            continue
        if cell.searched_clusters != index.searched_records:
            raise SystemExit(
                f"published cell {cell.key.slug()} searched {cell.searched_clusters:,} "
                f"records against this run's {index.searched_records:,}; they are not the "
                "same target and their counts must not be combined"
            )
        done[cell.key.slug()] = cell
    if done:
        print(f"  resuming: {len(done)} cells already published", flush=True)

    for sensitivity in sorted(similarity.SENSITIVITIES):
        for cov_mode in sorted(similarity.SEARCH_READINGS):
            key = similarity.CellKey(shard, sensitivity, cov_mode, seed_denominator=denominator)
            if key.slug() in done:
                cell = done[key.slug()]
                cells.append(cell)
                payload["band"]["cells"].append(cell.to_dict())
                payload["band"]["combined"] = similarity.combine_cells(cells)
                print(f"  skip {key.slug()} (already published)", flush=True)
                continue
            stream = _band_cell(args, work, db, qdb, target, key, index)
            cell = similarity.cell_from_stream(
                key,
                stream,
                index,
                seeds_searched=kept,
                seed_families=seed_families,
                searched_residues=shard_residues[shard],
            )
            cells.append(cell)
            payload["band"]["cells"].append(cell.to_dict())
            # Published per cell, not at the end. A run that dies on cell five has still paid
            # for four and must not lose them — the lesson AGENTS.md records from the runs
            # that published nothing in four hours.
            payload["band"]["combined"] = similarity.combine_cells(cells)
            publish()
            for group in payload["band"]["combined"]["groups"]:
                r = group["rate"]
                lead = "at least " if r["lower_bound"] else ""
                shown = "n/a" if r["rate"] is None else f"{lead}{r['rate']:.4%}"
                lo, hi = r["ci95"]
                span = "" if lo is None else f" (95% CI {lo:.4%}-{hi:.4%})"
                print(
                    f"  s{group['sensitivity']:g} mode {group['reading']}: {shown}{span}, "
                    f"{r['families']} strata, {group['seed_families']:,} seed families",
                    flush=True,
                )


if __name__ == "__main__":
    raise SystemExit(main())

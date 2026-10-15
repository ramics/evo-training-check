#!/usr/bin/env python3
"""Stage the pinned MGnify protein release for A1.5, streaming it into object storage.

The file is 83 GB and the working disk here is 30 GB, so nothing lands locally: it is
pulled, hashed, and uploaded in one forward pass. See `src/amazebio/mgnify.py` for why
the verification can gate the upload here where A1.3's could not, and DECISIONS.md D-033
for the staging scope this implements — the 90%-clustered product, which is what ESM3's
"MGnify90" names, and not the 362 GB protein set behind it.

Two modes:

    --probe    Check the release still serves what the pin says, and transfer nothing.
               Cheap, and the right thing to run first: the pins come from a manifest
               captured on a particular day.

    --stage    The transfer, uploading only if the published md5 matches.

`--max-compressed-bytes` stops either mode early. A short run exercises the whole path —
resume, credentials, multipart — for about a minute of transfer, and a run stopped that
way is recorded as unverified rather than as a staged corpus.

The artefacts land in `artifacts/a1-5/` with a `run.json` beside them. Pass
`--allow-dirty` only while iterating; a staged corpus that will be cited must come from
a committed tree.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import esm3, mgnify, uniref
from amazebio.repro import ReproError, run

OUTDIR = Path("artifacts/a1-5")
# The regional endpoint, not the global one: this session's AWS credentials are
# injected by a proxy scoped to *.us-east-1.amazonaws.com.
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"

# The one file D-033 authorises. A list rather than a scalar so adding the protein set
# later is a pin, not a rewrite — but adding one is a scope decision, not a flag.
PINS = (esm3.MGNIFY_2023_02_CLUSTERS,)
RELEASE = "2023_02"


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TiB"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise SystemExit(f"not an s3 uri: {uri!r}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise SystemExit(f"no bucket in s3 uri: {uri!r}")
    return bucket, prefix.strip("/")


def head(url: str) -> dict[str, str]:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request) as response:
        return {k.lower(): v for k, v in response.headers.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true", help="check the pins, transfer nothing")
    mode.add_argument("--stage", action="store_true", help="transfer and upload")
    ap.add_argument(
        "--s3-uri",
        default=os.environ.get("AMAZEBIO_S3_URI"),
        help="destination prefix, default $AMAZEBIO_S3_URI",
    )
    ap.add_argument(
        "--max-compressed-bytes",
        type=int,
        default=None,
        help="stop after this many bytes — for a smoke test",
    )
    ap.add_argument("--part-bytes", type=int, default=128 << 20, help="multipart part size")
    ap.add_argument(
        "--fetch-concurrency",
        type=int,
        default=8,
        help="ranged connections to the publisher (measured: EBI gives ~1 MB/s on one "
        "and ~16 MB/s on eight). 1 falls back to a single resumable stream.",
    )
    ap.add_argument(
        "--window-bytes",
        type=int,
        default=32 << 20,
        help="bytes per ranged fetch; memory is this times the connections in flight",
    )
    ap.add_argument("--concurrency", type=int, default=8, help="parts uploaded at once")
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument(
        "--allow-dirty", action="store_true", help="iteration only, never for a cited run"
    )
    ap.add_argument("--progress-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)

    client = None
    bucket = key_prefix = ""
    if args.stage:
        if not args.s3_uri:
            raise SystemExit("--stage needs --s3-uri or $AMAZEBIO_S3_URI")
        bucket, key_prefix = parse_s3_uri(args.s3_uri)
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - environment problem, not logic.
            raise SystemExit("--stage needs boto3 installed") from exc
        from botocore.config import Config

        client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT,
            config=Config(
                max_pool_connections=4 * args.concurrency,
                retries={"max_attempts": 10, "mode": "standard"},
            ),
        )

    try:
        return _execute(args, client, bucket, key_prefix)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(args: argparse.Namespace, client: Any, bucket: str, key_prefix: str) -> int:
    partial = args.max_compressed_bytes is not None
    out = args.outdir / ("probe.json" if args.probe else "staged-mgnify.json")

    with run(
        "A1.5",
        seed=None,
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        # Shares a directory with the UniRef pass and the composition table, so the
        # manifests need distinct names or the last one to finish wins.
        manifest_name="run-mgnify.json",
    ) as manifest:
        manifest.parameter("release", RELEASE)
        manifest.parameter("mode", "probe" if args.probe else "stage")
        manifest.parameter("files", [p.name for p in PINS])
        manifest.parameter("published_md5", {p.name: p.md5 for p in PINS})
        manifest.parameter("published_bytes", {p.name: p.bytes for p in PINS})
        manifest.parameter("manifest_capture", esm3.MGNIFY_2023_02_MANIFEST)
        manifest.parameter("max_compressed_bytes", args.max_compressed_bytes)
        manifest.parameter("fetch_concurrency", args.fetch_concurrency)
        manifest.parameter("window_bytes", args.window_bytes)
        manifest.parameter("destination", f"s3://{bucket}/{key_prefix}" if args.stage else None)
        manifest.input_file(esm3.MGNIFY_2023_02_MANIFEST, role="published md5 per file")

        report: dict[str, Any] = {"release": RELEASE, "files": []}

        for pin in PINS:
            print(f"\n=== {pin.name}")
            print(f"url:      {pin.url}")
            print(f"expected: {human(pin.bytes)} ({pin.bytes:,} bytes), md5 {pin.md5}")

            headers = head(pin.url)
            served = int(headers.get("content-length", -1))
            ranges = headers.get("accept-ranges", "none")
            print(f"served:   {human(served)} ({served:,} bytes), accept-ranges: {ranges}")
            row: dict[str, Any] = {
                "name": pin.name,
                "url": pin.url,
                "expected_bytes": pin.bytes,
                "expected_md5": pin.md5,
                "served_bytes": served,
                "accept_ranges": ranges,
                "last_modified": headers.get("last-modified"),
            }

            if served != pin.bytes:
                # Not fatal in probe mode: the gap is the finding. Fatal in stage
                # mode, before a single byte is uploaded.
                row["size_agrees"] = False
                print("MISMATCH: the served size is not the pinned size")
                if args.stage:
                    raise uniref.VerificationError(
                        f"{pin.name}: the release now serves {served} bytes where the "
                        f"captured manifest pins {pin.bytes}. Re-capture the manifest and "
                        "re-verify the pin before staging; do not stage a file this "
                        "project has not pinned."
                    )
            else:
                row["size_agrees"] = True

            if args.probe:
                report["files"].append(row)
                continue

            # EBI throttles a single connection to about 1 MB/s, which makes this an
            # overnight transfer in one stream and under two hours in eight. The reader
            # still serves bytes in order, so the md5 remains a verification.
            reader: Any = uniref.ParallelRangeRead(
                pin.url,
                total_bytes=pin.bytes,
                window=args.window_bytes,
                concurrency=args.fetch_concurrency,
                on_reconnect=lambda attempt, pos, exc: print(
                    f"    refetch #{attempt} at {human(pos)}: {type(exc).__name__}",
                    flush=True,
                ),
            )
            if args.fetch_concurrency == 1:
                reader = uniref.ResumableRead(
                    pin.url,
                    expected_bytes=pin.bytes,
                    on_reconnect=lambda attempt, pos, exc: print(
                        f"    reconnect #{attempt} at {human(pos)}: {type(exc).__name__}",
                        flush=True,
                    ),
                )
            key = f"{key_prefix}/mgnify/{RELEASE}/{pin.name}".replace("//", "/")
            print(f"staging to s3://{bucket}/{key}")

            started = time.monotonic()
            last = [started]

            def progress(
                read: int,
                started: float = started,
                last: list[float] = last,
                total: int = pin.bytes,
            ) -> None:
                now = time.monotonic()
                if now - last[0] < args.progress_seconds:
                    return
                last[0] = now
                rate = read / max(now - started, 1e-9)
                share = 100 * read / total
                print(
                    f"    {human(read)} ({share:.1f}%), {human(rate)}/s, "
                    f"{(now - started) / 60:.1f} min",
                    flush=True,
                )

            try:
                with uniref.S3PartSink(
                    client,
                    bucket,
                    key,
                    part_bytes=args.part_bytes,
                    concurrency=args.concurrency,
                ) as sink:
                    # Inside the sink's `with`: a verification failure raises here, the
                    # sink aborts, and nothing becomes permanent in a bucket with no
                    # delete.
                    staged = mgnify.stream_verified(
                        reader,
                        sink,
                        expected_bytes=pin.bytes,
                        expected_md5=pin.md5,
                        url=pin.url,
                        progress=progress,
                        max_bytes=args.max_compressed_bytes,
                    )
            except mgnify.PartialRun as stopped:
                # A smoke test. The upload has already been aborted by the sink, which
                # is the point: it exercised the network, the resume, the credentials
                # and multipart without writing an object that could never be removed.
                staged = stopped.staged
                print(f"smoke test: {stopped}")
                row.update(staged.as_manifest())
                row["uri"] = None
                row["aborted"] = True
                report["files"].append(row)
                manifest.note(
                    f"{pin.name}: smoke test read {staged.bytes_read:,} bytes and the "
                    "upload was aborted; nothing was written"
                )
                continue
            finally:
                # The parallel reader holds a thread pool and windows in flight; a run
                # that ends either way must not leave them running.
                if hasattr(reader, "close"):
                    reader.close()

            elapsed = time.monotonic() - started
            print(
                f"done: {human(staged.bytes_read)} in {elapsed / 60:.1f} min, "
                f"md5 {'verified' if staged.verified else 'NOT verified'}, "
                f"{staged.reconnects} reconnect(s)"
            )
            row.update(staged.as_manifest())
            row["uri"] = f"s3://{bucket}/{key}"
            report["files"].append(row)

            manifest.input_url(
                pin.url,
                role="MGnify release file",
                bytes=staged.bytes_read,
                checksum=pin.md5,
                checksum_type="md5",
                verified=staged.verified,
            )
            manifest.output_object(
                f"s3://{bucket}/{key}",
                role="staged corpus component",
                bytes=staged.bytes_read,
                sha256=staged.sha256,
                md5=staged.md5,
                md5_verified=staged.verified,
                partial=staged.partial,
            )

        if partial:
            manifest.note(
                "stopped early by --max-compressed-bytes: a smoke test of the path, "
                "not a staged corpus, and nothing here is verified"
            )

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")
        # Every parameter is declared before the loop, so recording outputs here closes
        # the window on nothing that still needs declaring.
        manifest.output_file(out, role="probe report" if args.probe else "staging report")

    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

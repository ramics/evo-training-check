#!/usr/bin/env python3
"""Count clusters and members in the staged UniRef tiers, and check the totals.

This closes A1.3's last open piece. `tools/stage_uniref.py` put the tiers in
object storage and verified the archive against the release's published md5, but
the md5 covers the archive as a whole; it says nothing about whether the
extraction split the members correctly. Counting is the independent check, and
the composition table is the artefact the write-up cites.

What it compares against: the per-tier release notes give UniRef50 49,874,565
clusters and UniRef90 138,515,945. A mismatch is reported, never raised — per
`AGENTS.md`, the gap between stated and observed is itself a finding, and a
pipeline that aborts on one is a pipeline that hides it.

It also reads the `version` attribute off each tier's XML root. That is a
first-party statement, inside the data, of which release these bytes are —
independent of the filename and of the directory they came from. Trusting a path
is not the same as reading the data.

Reads 75 GB, so it is meant to run in us-east-1 where that transfer is free
(DECISIONS.md D-026). `--source` accepts a local path for testing.
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

from amazebio import uniref
from amazebio.repro import ReproError, run

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"
DEFAULT_TIERS = ("uniref50", "uniref90")


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tier", action="append", choices=list(DEFAULT_TIERS))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument(
        "--source",
        help="local .xml.gz to count instead of S3 — for testing the path end to end",
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-3"))
    ap.add_argument(
        "--upload-results",
        action="store_true",
        help="put the composition table and manifest back in S3, so a run on a "
        "machine nobody can log into still reports its result",
    )
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        help="the commit this code came from. A run on a machine with no git "
        "checkout cannot discover it, and a manifest that omits it cannot be "
        "traced back to the code that produced the numbers.",
    )
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    args = ap.parse_args(argv)

    tiers = tuple(dict.fromkeys(args.tier or DEFAULT_TIERS))
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
        return _execute(args, tiers, client, bucket, prefix)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _open_tier(args: argparse.Namespace, client: Any, bucket: str, prefix: str, tier: str):
    """Return (reader, label). The reader is forward-only with .read(n)."""
    if args.source:
        return open(args.source, "rb"), args.source
    key = f"{prefix}/uniref/{uniref.RELEASE}/{tier}.tar/{tier}.xml.gz"
    reader = uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {human(pos)}: {type(exc).__name__}", flush=True
        ),
    )
    return reader, f"s3://{bucket}/{key}"


def _execute(
    args: argparse.Namespace, tiers: tuple[str, ...], client: Any, bucket: str, prefix: str
) -> int:
    report: dict[str, Any] = {}
    out = args.outdir / "composition.json"
    with run("A1.3", seed=None, outdir=args.outdir, allow_dirty=args.allow_dirty) as manifest:
        manifest.parameter("release", uniref.RELEASE)
        manifest.parameter("tiers", list(tiers))
        manifest.parameter("markers", {k: v.decode() for k, v in uniref.MARKERS.items()})
        manifest.parameter("stated_clusters", uniref.STATED_CLUSTERS)
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        elif not manifest.git.get("available"):
            manifest.note(
                "no git checkout and no --code-commit: this manifest cannot be traced "
                "to the code that produced it, so the numbers are not citable"
            )
        manifest.note(
            "Counts are byte-scanned for start tags rather than XML-parsed. Sound because "
            "a literal '<' cannot appear in XML content or attribute values, so an "
            "occurrence of a start-tag marker is necessarily a tag."
        )

        counted: dict[str, int] = {}
        per_tier: dict[str, Any] = {}

        for tier in tiers:
            reader, label = _open_tier(args, client, bucket, prefix, tier)
            print(f"counting {tier}: {label}", flush=True)
            started = time.monotonic()
            last = [started]

            def progress(total: int, tier=tier, started=started, last=last) -> None:
                now = time.monotonic()
                if now - last[0] >= args.progress_seconds:
                    rate = total / max(now - started, 1e-9)
                    print(f"    {tier}: {human(total)} decompressed, {human(rate)}/s", flush=True)
                    last[0] = now

            stream = uniref.GunzipStream(reader, digest="sha256")
            # A peek, not a read: whatever it inspects is pushed back, so the
            # count below still sees the head of the file. Without that the first
            # 64 KiB of clusters would go uncounted in every tier.
            attrs = uniref.read_root_attributes(stream)
            counts = uniref.count_markers(stream, progress=progress)
            elapsed = time.monotonic() - started
            if hasattr(reader, "close"):
                reader.close()

            row = {
                "tier": tier,
                "source": label,
                "root": attrs,
                "counts": counts,
                "compressed_bytes": stream.compressed_bytes,
                "decompressed_bytes": stream.read_bytes,
                "elapsed_seconds": round(elapsed, 1),
                "reconnects": getattr(reader, "reconnects", 0),
            }
            per_tier[tier] = row
            counted[tier] = counts["clusters"]
            print(
                f"  {tier}: {counts['clusters']:,} clusters, "
                f"{counts['representatives']:,} representatives, "
                f"{counts['members']:,} further members, "
                f"root says version {attrs.get('version', '?')}",
                flush=True,
            )
            if attrs.get("version") and attrs["version"] != uniref.RELEASE:
                manifest.note(
                    f"{tier} XML root declares version {attrs['version']!r}, not "
                    f"{uniref.RELEASE!r} — the staged bytes are not the pinned release"
                )

        composition = uniref.composition_check(counted)
        for row in composition:
            tier = row["tier"]
            verdict = (
                "agrees"
                if row["agrees"]
                else ("not counted" if row["agrees"] is None else f"differs by {row['delta']:+,}")
            )
            print(
                f"{tier}: counted {row['counted_clusters']:,} vs stated "
                f"{row['stated_clusters']:,} — {verdict}"
                if row["counted_clusters"] is not None
                else f"{tier}: not counted"
            )
            if row["agrees"] is False:
                manifest.note(
                    f"{tier}: counted {row['counted_clusters']} clusters against the release "
                    f"notes' {row['stated_clusters']} ({row['delta']:+d}). Reported, not raised: "
                    "the gap between stated and observed is a finding."
                )

        report = {
            "release": uniref.RELEASE,
            "tiers": per_tier,
            "composition": composition,
            "all_tiers_agree": all(r["agrees"] for r in composition if r["agrees"] is not None)
            and any(r["agrees"] is not None for r in composition),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        manifest.output_file(out, role="composition-table")
        print(f"\nwrote {out}")

    # Uploads happen after the run block, not inside it: `run.json` is written by
    # the manifest's exit handler, so an upload inside the block would miss it.
    if args.upload_results and client is not None:
        # Keyed by the tiers counted. One process per tier runs concurrently, so a
        # shared key would have them overwrite each other and the surviving file
        # would report one tier as counted and the other as unknown.
        suffix = "-".join(tiers)
        for path, role in ((out, "composition"), (args.outdir / "run.json", "manifest")):
            if not path.exists():
                print(f"not uploaded (absent): {path}")
                continue
            key = f"{prefix}/results/{uniref.RELEASE}/{role}-{suffix}.json"
            client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
            print(f"uploaded s3://{bucket}/{key}")

    return 0 if report["all_tiers_agree"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

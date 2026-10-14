#!/usr/bin/env python3
"""Stage the pinned Evo nucleotide corpora for A1.2, streaming into object storage.

Two releases: `LongSafari/open-genome` (Evo 1, 147 GB) and
`arcinstitute/opengenome2` (Evo 2, 5.52 TB). Neither is staged whole. The
component the published exclusion procedure acts on is 11.2 GB of the 5.52 TB,
and 2.17 TB is eukaryotic reference genomes the filter never saw, so the
selection is by component — `src/amazebio/opengenome.py` records which component
plays which role in the audit, and the project owner approved the tier marked
`tier1` there (DECISIONS.md D-031).

Three modes, because they answer different questions:

    --probe      Read both release manifests and report composition: component,
                 role in the audit, files, bytes, share of release, and whether
                 the fetched tree still matches the recorded pin. No uploads, no
                 sequence transferred — it reads the dataset API only, so it
                 costs seconds and is the right thing to run first.

    --plan       What a staging pass would upload, and the monthly storage it
                 would commit to. Also no uploads.

    --stage      Upload the approved selection, verifying each file against the
                 SHA-256 the release publishes for it *before* completing the
                 upload. The corpus bucket withholds `s3:DeleteObject`, so a
                 completed object is permanent and a mismatch must not become one.

`--release` restricts any mode to one release. `--max-files` stops a staging pass
early, which makes a cheap end-to-end test of the whole path — manifest, pin
check, resume, transfer, checksum gate, credentials — against the smallest files
in the selection.

A repeated pass lists what is already staged and skips it, so an interrupted run
resumes rather than restarting. Artefacts land in `artifacts/a1-2/` with a
`run.json` beside them. Pass `--allow-dirty` only while iterating; a staged
corpus that will be cited must come from a committed tree.
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

from amazebio import opengenome as og
from amazebio.repro import ReproError, run
from amazebio.uniref import VerificationError

OUTDIR = Path("artifacts/a1-2")
# The endpoint has to be the regional one: this session's AWS credentials are
# injected by a proxy scoped to *.us-east-1.amazonaws.com, and the global
# s3.amazonaws.com host does not match it.
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"
DEFAULT_PREFIX = "corpora"


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{int(n)} B" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise SystemExit(f"not an s3 uri: {uri!r}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise SystemExit(f"no bucket in s3 uri: {uri!r}")
    return bucket, prefix.strip("/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true", help="report composition, upload nothing")
    mode.add_argument("--plan", action="store_true", help="report what staging would upload")
    mode.add_argument("--stage", action="store_true", help="upload the approved selection")
    ap.add_argument(
        "--release",
        action="append",
        choices=sorted(og.RELEASES),
        help="restrict to one release, repeatable (default: both)",
    )
    ap.add_argument(
        "--s3-uri",
        default=os.environ.get("AMAZEBIO_S3_URI"),
        help="destination bucket and prefix, default $AMAZEBIO_S3_URI",
    )
    ap.add_argument(
        "--key-prefix",
        default=DEFAULT_PREFIX,
        help=f"prefix under the bucket (default {DEFAULT_PREFIX})",
    )
    ap.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="stage at most this many files — for a smoke test of the whole path",
    )
    # 64 MiB: the selection is ~2,300 parts at this size, which stays inside the
    # account's free monthly request allowance. The largest file in the tier is
    # 11.2 GB, so a smaller part size would multiply requests for no gain.
    ap.add_argument("--part-bytes", type=int, default=64 << 20, help="multipart part size")
    ap.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="parts uploaded at once (measured on this bucket: 1 gives ~52 MB/s, 8 ~123)",
    )
    ap.add_argument(
        "--no-resume",
        action="store_true",
        help="re-upload files already present rather than skipping them",
    )
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument(
        "--allow-dirty", action="store_true", help="iteration only, never for a cited run"
    )
    ap.add_argument("--progress-seconds", type=float, default=30.0)
    args = ap.parse_args(argv)

    releases = [og.RELEASES[k] for k in (args.release or sorted(og.RELEASES))]

    client = None
    bucket = ""
    if args.stage:
        if not args.s3_uri:
            raise SystemExit("--stage needs --s3-uri or $AMAZEBIO_S3_URI")
        bucket, uri_prefix = parse_s3_uri(args.s3_uri)
        if uri_prefix:
            args.key_prefix = uri_prefix
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
                max_pool_connections=2 * args.concurrency,
                retries={"max_attempts": 10, "mode": "standard"},
            ),
        )

    try:
        return _execute(args, releases, client, bucket)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 3


def _execute(
    args: argparse.Namespace,
    releases: list[og.Release],
    client: Any,
    bucket: str,
) -> int:
    mode = "probe" if args.probe else "plan" if args.plan else "stage"
    with run(
        "A1.2",
        seed=None,  # Nothing here is random: a byte-for-byte transfer or a bug.
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
    ) as manifest:
        manifest.parameter("mode", mode)
        manifest.parameter("releases", [r.key for r in releases])
        manifest.parameter(
            "pins", {r.key: {"dataset": r.dataset, "revision": r.revision} for r in releases}
        )
        manifest.parameter(
            "staged_representation", {r.key: r.staged_representation for r in releases}
        )
        manifest.parameter("staging_tier", "tier1")
        manifest.parameter("part_bytes", args.part_bytes)
        manifest.parameter("upload_concurrency", args.concurrency)
        manifest.parameter("max_files", args.max_files)
        manifest.parameter("resume", not args.no_resume)
        manifest.parameter(
            "destination", f"s3://{bucket}/{args.key_prefix}" if args.stage else None
        )
        manifest.note(
            "Revisions are pinned to commit SHAs, not to `main`: both releases have moved "
            "since publication. Per-file SHA-256 comes from the Git LFS oid the dataset "
            "API publishes, so each staged object is checked against the release's own "
            "checksum before the upload completes."
        )
        manifest.note(
            "The FASTA representation is staged and the JSON is not. They hold the same "
            "sequences, but the JSON viral records are a bare `text` field with no "
            "accession and no lineage tag, so they cannot be traced to IMG/VR and A7.1's "
            "diff cannot run against them. See DECISIONS.md D-031."
        )

        composition_rows: list[dict[str, Any]] = []
        pin_rows: list[dict[str, Any]] = []
        plans: list[og.StagePlan] = []

        for release in releases:
            print(f"\n=== {release.dataset} @ {release.revision[:12]} ===", flush=True)
            blobs = og.fetch_tree(release)
            checks = og.verify_manifest(release, blobs)
            for row in checks:
                row["release"] = release.key
                flag = "ok" if row["agrees"] else "MISMATCH"
                print(
                    f"  pin {row['quantity']:>5}: stated {row['stated']:,} "
                    f"found {row['found']:,}  [{flag}]"
                )
            pin_rows.extend(checks)

            rows = og.composition(release, blobs)
            composition_rows.extend(rows)
            print(
                f"  {'component':26s} {'repr':8s} {'role':22s} {'files':>5} "
                f"{'bytes':>12} {'share':>7} staged"
            )
            for row in rows:
                print(
                    f"  {row['component']:26s} {row['representation']:8s} {row['role']:22s} "
                    f"{row['files']:5d} {human(row['bytes']):>12} "
                    f"{row['share_of_release']:7.3%} {'yes' if row['staged'] else '-'}"
                )

            staging_plan = og.plan(release, blobs)
            plans.append(staging_plan)
            print(
                f"  selection: {staging_plan.files} files, {human(staging_plan.bytes)}, "
                f"~${staging_plan.monthly_usd:,.2f}/month to store"
            )
            unverifiable = staging_plan.unverifiable()
            if unverifiable:
                print(f"  WARNING: {len(unverifiable)} selected files publish no checksum")

            if args.stage:
                _stage_release(args, release, blobs, client, bucket, manifest)

        total_bytes = sum(p.bytes for p in plans)
        print(
            f"\nselection across {len(plans)} release(s): {sum(p.files for p in plans)} files, "
            f"{human(total_bytes)}, ~${total_bytes / 1e9 * 0.023:,.2f}/month"
        )

        args.outdir.mkdir(parents=True, exist_ok=True)
        for name, payload in (
            ("composition.json", composition_rows),
            ("pin_check.json", pin_rows),
        ):
            path = args.outdir / name
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            manifest.output_file(path, role=name.removesuffix(".json"))

        if any(not row["agrees"] for row in pin_rows):
            print(
                "\nA release no longer matches its recorded pin. Nothing was staged for it; "
                "this is a question for the project owner, not something to resolve by "
                "uploading.",
                file=sys.stderr,
            )
            return 1
    return 0


def _stage_release(
    args: argparse.Namespace,
    release: og.Release,
    blobs: list[og.Blob],
    client: Any,
    bucket: str,
    manifest: Any,
) -> None:
    staged_rows: list[dict[str, Any]] = []
    last = [0.0]

    def progress(done: int, total: int) -> None:
        now = time.monotonic()
        if now - last[0] >= args.progress_seconds:
            last[0] = now
            print(f"    {human(done)} / {human(total)}", flush=True)

    def announce(blob: og.Blob, key: str) -> None:
        last[0] = 0.0
        print(f"  staging {blob.path} ({human(blob.size)})", flush=True)

    for count, staged in enumerate(
        og.stage(
            release,
            blobs,
            client,
            bucket=bucket,
            prefix=args.key_prefix,
            manifest_rows=staged_rows,
            resume=not args.no_resume,
            on_file=announce,
            part_bytes=args.part_bytes,
            concurrency=args.concurrency,
            on_progress=progress,
        ),
        start=1,
    ):
        if staged.skipped:
            mark = "verified by readback" if staged.verified else staged.verified_by
            print(f"  already staged: {staged.path} ({mark})")
        else:
            print(f"    verified {staged.sha256[:16]}… -> {staged.uri}")
            manifest.output_object(
                staged.uri,
                role=f"{release.key}:corpus",
                bytes=staged.bytes,
                sha256=staged.sha256,
                verified_against_release=True,
            )
        if args.max_files is not None and count >= args.max_files:
            print(f"  stopping after {count} file(s) at --max-files")
            break

    path = args.outdir / f"staged_{release.key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous: list[dict[str, Any]] = []
    if path.exists():
        previous = json.loads(path.read_text())
    merged = og.merge_staged_rows(previous, staged_rows)
    path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    manifest.output_file(path, role=f"{release.key}:staged")


if __name__ == "__main__":
    raise SystemExit(main())

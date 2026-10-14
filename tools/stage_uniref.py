#!/usr/bin/env python3
"""Stage the pinned UniRef release for A1.3, streaming it into object storage.

The archive is 169 GB and the working disk here is 30 GB, so nothing lands
locally: the release is pulled, verified, split and uploaded in one forward pass.
See `src/amazebio/uniref.py` for why that is the only shape available, and
DECISIONS.md D-024 (the version pin) and D-025 (that the corpus is UniRef50
clusters *with* their UniRef90 members, not the representatives).

Two modes, because they answer different questions:

    --probe    Walk the archive and report what is in it. No uploads. The
               archive's internal layout is not documented anywhere retrieved,
               and the release metalink lists only the tarball, so the layout is
               itself something to establish and record.

    --stage    The same pass, uploading the selected tiers.

`--max-compressed-bytes` stops either mode early. A short probe is a smoke test
of the whole path — resume, gunzip, tar alignment, credentials — for about a
minute of transfer, and it is the right thing to run before committing to the
full pass.

The artefacts land in `artifacts/a1-3/` with a `run.json` beside them. Pass
`--allow-dirty` only while iterating; a staged corpus that will be cited must
come from a committed tree.
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

DEFAULT_TIERS = ("uniref50", "uniref90")
OUTDIR = Path("artifacts/a1-3")
# The endpoint has to be the regional one: this session's AWS credentials are
# injected by a proxy scoped to *.us-east-1.amazonaws.com, and the global
# s3.amazonaws.com host does not match it.
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"


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


def tier_of(member: uniref.Member) -> str | None:
    """Which tier a member belongs to, by the enclosing archive or its own name."""
    for part in (*member.path, member.name):
        base = part.rsplit("/", 1)[-1]
        for tier in ("uniref100", "uniref90", "uniref50"):
            if base.startswith(tier):
                return tier
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true", help="report the layout, upload nothing")
    mode.add_argument("--stage", action="store_true", help="upload the selected tiers")
    ap.add_argument(
        "--tier",
        action="append",
        choices=["uniref50", "uniref90", "uniref100"],
        help=f"tier to stage, repeatable (default: {' '.join(DEFAULT_TIERS)})",
    )
    ap.add_argument(
        "--s3-uri",
        default=os.environ.get("AMAZEBIO_S3_URI"),
        help="destination prefix, default $AMAZEBIO_S3_URI",
    )
    ap.add_argument(
        "--max-compressed-bytes",
        type=int,
        default=None,
        help="stop after this many compressed bytes — for a smoke test",
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="also retain the release archive verbatim, in the same pass",
    )
    # 128 MiB rather than the 5 MiB floor for a reason beyond efficiency: at this
    # size the whole job is ~1,820 uploads, which fits the account's free monthly
    # allowance of 2,000. Smaller parts would double it for no benefit.
    ap.add_argument("--part-bytes", type=int, default=128 << 20, help="multipart part size")
    ap.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="parts uploaded at once per sink (measured: 1 gives ~52 MB/s, 8 gives ~123)",
    )
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument(
        "--allow-dirty", action="store_true", help="iteration only, never for a cited run"
    )
    ap.add_argument("--progress-seconds", type=float, default=60.0)
    args = ap.parse_args(argv)

    tiers = tuple(dict.fromkeys(args.tier or DEFAULT_TIERS))

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
            # The pool has to cover every uploader across both sinks at once —
            # the retained archive and the member being extracted — or threads
            # queue on connections and the concurrency buys nothing.
            config=Config(
                max_pool_connections=4 * args.concurrency,
                retries={"max_attempts": 10, "mode": "standard"},
            ),
        )

    try:
        return _execute(args, tiers, client, bucket, key_prefix)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(
    args: argparse.Namespace,
    tiers: tuple[str, ...],
    client: Any,
    bucket: str,
    key_prefix: str,
) -> int:
    partial = args.max_compressed_bytes is not None
    with run(
        "A1.3",
        seed=None,  # Nothing here is random: a byte-for-byte transfer or a bug.
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
    ) as manifest:
        manifest.parameter("release", uniref.RELEASE)
        manifest.parameter("archive_url", uniref.ARCHIVE_URL)
        manifest.parameter("published_md5", uniref.ARCHIVE_MD5)
        manifest.parameter("published_bytes", uniref.ARCHIVE_BYTES)
        manifest.parameter("mode", "probe" if args.probe else "stage")
        manifest.parameter("tiers", list(tiers))
        manifest.parameter("max_compressed_bytes", args.max_compressed_bytes)
        manifest.parameter("part_bytes", args.part_bytes)
        manifest.parameter("upload_concurrency", args.concurrency)
        manifest.parameter("retain_raw_archive", bool(args.raw))
        manifest.parameter("destination", f"s3://{bucket}/{key_prefix}" if args.stage else None)
        manifest.note(
            "DECISIONS.md D-025: the ESM-2 corpus is UniRef50 clusters with their UniRef90 "
            "members, so staging UniRef50 alone would reconstruct a different dataset."
        )

        reader = uniref.ResumableRead(
            uniref.ARCHIVE_URL,
            expected_bytes=uniref.ARCHIVE_BYTES,
            on_reconnect=lambda attempt, pos, exc: print(
                f"  reconnect #{attempt} at {human(pos)}: {type(exc).__name__}: {exc}",
                flush=True,
            ),
        )
        raw_sink = None
        if args.raw and args.stage:
            raw_key = f"{key_prefix}/uniref/{uniref.RELEASE}/uniref{uniref.RELEASE}.tar.gz"
            raw_sink = uniref.S3PartSink(
                client,
                bucket,
                raw_key.replace("//", "/"),
                part_bytes=args.part_bytes,
                concurrency=args.concurrency,
            ).open()
            print(f"retaining the archive verbatim -> s3://{bucket}/{raw_sink.key}", flush=True)

        stream = uniref.GunzipStream(reader, tap=None if raw_sink is None else raw_sink.write)

        started = time.monotonic()
        last_report = started
        members: list[dict[str, Any]] = []
        staged: list[dict[str, Any]] = []
        stopped_early = False

        def is_container(member: uniref.Member) -> bool:
            """A nested per-tier archive, which is walked into rather than stored."""
            return member.name.endswith(".tar")

        def wanted(member: uniref.Member) -> bool:
            # Excluding containers matters: `uniref50.tar` matches its own tier, and
            # the walk yields it with an empty payload before descending, so without
            # this it uploads as a 0-byte object. In a bucket that withholds
            # s3:DeleteObject that litter is permanent.
            return args.stage and not is_container(member) and tier_of(member) in tiers

        print(f"archive: {uniref.ARCHIVE_URL}")
        print(f"expected: {human(uniref.ARCHIVE_BYTES)}, md5 {uniref.ARCHIVE_MD5}")
        print(f"mode: {'probe' if args.probe else 'stage ' + ','.join(tiers)}", flush=True)

        walker = uniref.iter_tar_members(
            stream,
            want=wanted,
            recurse_into=is_container,
        )
        for member, payload in walker:
            row = {
                "qualified": member.qualified,
                "name": member.name,
                "enclosing": list(member.path),
                "bytes": member.size,
                "typeflag": member.typeflag,
                "tier": tier_of(member),
                "staged": False,
            }
            print(
                f"  member {member.qualified}  {human(member.size)}  type={member.typeflag}",
                flush=True,
            )

            if wanted(member):
                key = f"{key_prefix}/uniref/{uniref.RELEASE}/{member.qualified}".replace("//", "/")
                with uniref.S3PartSink(
                    client,
                    bucket,
                    key,
                    part_bytes=args.part_bytes,
                    concurrency=args.concurrency,
                ) as sink:
                    for chunk in payload:
                        sink.write(chunk)
                        now = time.monotonic()
                        if now - last_report >= args.progress_seconds:
                            rate = reader.pos / max(now - started, 1e-9)
                            print(
                                f"    {human(reader.pos)} read "
                                f"({100 * reader.pos / uniref.ARCHIVE_BYTES:.1f}%), "
                                f"{human(sink.bytes_written)} into {member.name}, "
                                f"{human(rate)}/s",
                                flush=True,
                            )
                            last_report = now
                described = sink.describe()
                row |= {"staged": True, **described}
                staged.append({"member": member.qualified, **described})
                manifest.output_object(
                    described["uri"],
                    role=f"corpus:{tier_of(member)}",
                    bytes=described["bytes"],
                    sha256=described["sha256"],
                    member=member.qualified,
                )
                print(f"    staged -> {described['uri']} ({human(described['bytes'])})", flush=True)
            else:
                for _ in payload:  # pragma: no cover - empty for unwanted members.
                    pass

            members.append(row)

            if args.max_compressed_bytes is not None and reader.pos >= args.max_compressed_bytes:
                stopped_early = True
                print(f"  stopping early at {human(reader.pos)} as asked", flush=True)
                break

        if not stopped_early:
            # The walk stops at the end-of-archive marker, which is not the end of
            # the file. Without draining the padding behind it, the md5 covers only
            # the bytes the walk happened to read and verifies nothing.
            trailing = stream.drain()
            if trailing:
                manifest.note(f"drained {trailing} bytes of trailing padding for the md5")

        elapsed = time.monotonic() - started
        reader.close()

        md5_verified: bool | None = None
        if not stopped_early and stream.exhausted:
            actual = stream.compressed_md5()
            md5_verified = actual == uniref.ARCHIVE_MD5
            print(f"md5: {actual} ({'matches' if md5_verified else 'DOES NOT MATCH'} published)")
            if not md5_verified:
                manifest.note(
                    f"published md5 {uniref.ARCHIVE_MD5} but read {actual} — the staged bytes "
                    "are not the released bytes and nothing downstream may treat them as such"
                )

        if raw_sink is not None:
            if md5_verified is not True:
                # The retained copy is only worth anything as a verifiable stand-in
                # for the release. Completing it without a matching md5 would put an
                # object into a bucket that withholds s3:DeleteObject, permanently,
                # claiming to be a release it has not been shown to be.
                raw_sink.abort()
                reason = "md5 did not match" if md5_verified is False else "md5 unverified"
                manifest.note(f"retained archive abandoned: {reason}")
                print(f"archive upload aborted: {reason}", flush=True)
            else:
                raw_sink.complete()
                described = raw_sink.describe()
                manifest.output_object(
                    described["uri"],
                    role="release-archive-verbatim",
                    bytes=described["bytes"],
                    sha256=described["sha256"],
                    md5_verified=md5_verified,
                )
                print(
                    f"archive retained -> {described['uri']} ({human(described['bytes'])})",
                    flush=True,
                )

        manifest.input_url(
            uniref.ARCHIVE_URL,
            role="release-archive",
            bytes=reader.pos,
            checksum=uniref.ARCHIVE_MD5,
            checksum_type="md5",
            verified=md5_verified,
        )
        manifest.note(f"compressed bytes read: {reader.pos} of {uniref.ARCHIVE_BYTES}")
        manifest.note(f"stream reconnects: {reader.reconnects}")
        if stopped_early or partial:
            manifest.note(
                "PARTIAL RUN: stopped at a byte limit, so the md5 is unverified and the "
                "member list is a prefix of the archive, not its layout."
            )

        layout = args.outdir / ("members-probe.json" if args.probe else "members.json")
        layout.parent.mkdir(parents=True, exist_ok=True)
        layout.write_text(
            json.dumps(
                {
                    "release": uniref.RELEASE,
                    "archive_url": uniref.ARCHIVE_URL,
                    "partial": stopped_early or partial,
                    "compressed_bytes_read": reader.pos,
                    "md5_verified": md5_verified,
                    "elapsed_seconds": round(elapsed, 1),
                    "members": members,
                    "staged": staged,
                    "composition": uniref.composition_check({}),
                },
                indent=2,
            )
            + "\n"
        )
        manifest.output_file(layout, role="archive-layout")
        print(f"\nwrote {layout}  ({len(members)} members, {human(reader.pos)} in {elapsed:.0f}s)")

    return 0 if md5_verified is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())

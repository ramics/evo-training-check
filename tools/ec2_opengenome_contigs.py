#!/usr/bin/env python3
"""Run A7.4's contig enumeration in us-east-1 — DESIGN.md §A7.

`tools/opengenome_contigs.py` reads OpenGenome2's four staged GTDB archives and writes one
line per contig. A contig accession lives inside a member's gzip stream, so there is no
shortcut like the genome half's header walk: all 109 GB has to be read and some 380 GB
decompressed. From the session container that is metered egress; in-region it is free, and
that is the data-movement test in `AGENTS.md`.

**Four workers, one per archive, and no more.** A gzip stream cannot be decompressed in
parallel and a member is one stream, so the real parallelism is across archives. Measured
in-container on 2026-10-20, one worker reads 15 genomes a second at one core saturated;
each archive holds roughly 27,000 genomes, so the four together are about half an hour on
8 vCPU with headroom to spare. A larger instance buys nothing: the ceiling is four streams.

Everything `AGENTS.md`'s EC2 section demands, because none of it can be fixed after launch:
one shot at `UserData`, no shell, no SSM, no inbound connection. A dead man's switch armed
before anything that can fail; every exit through one `die` that cancels the pending timer
first, since `shutdown -h now` does nothing while one is scheduled; the interpreter picked
by name because Amazon Linux 2023's `python3` is 3.9; a payload derived from the tool's own
import closure and tested, with an import check on the instance before the long read; a
heartbeat per archive to object storage, because a quiet console cannot be told apart from
a dead process; and the commit carried in, since the instance has no checkout.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

#: The archives, largest first. If the window runs out, the ones already published are the
#: ones that cost the most to read.
ARCHIVES = ("v214/batch1.tar", "v214/batch2.tar", "v214/batch3.tar", "v220_update.tar")

#: Scaled from the measured 15 genomes/s per worker over roughly 27,000 genomes an archive.
DEFAULT_HARD_STOP_MINUTES = 150

#: The code the instance needs, derived from the tool's first-party import closure and
#: checked by `tests/test_ec2_opengenome_contigs.py`. Twice in this project a module was
#: added to a tool's imports and not to a list like this, and the instance died on an
#: `ImportError` half a minute in, having read nothing.
PAYLOAD = (
    "src/amazebio/__init__.py",
    "src/amazebio/contigs.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/repro.py",
    "src/amazebio/uniref.py",
    "tools/opengenome_contigs.py",
)

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a7-4 contigs starting $(date -Is) ==="

# A dead man's switch, armed before anything that can fail. The launcher's own terminate in
# its `finally` covers a launcher that lives to run it; this covers the case it cannot.
shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` is a no-op while that timer is pending: systemd already has a shutdown
# scheduled and the immediate one does not replace it, so a script that fails in thirty
# seconds would otherwise idle until the timer fires and look exactly like a long pass
# still working (D-127). Cancel first, then go down, with fallbacks.
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3` and this project needs 3.12.
PYBIN=""
for cand in python3.12 python3.11; do
  dnf install -y "$cand" "$cand-pip" >/dev/null 2>&1 || true
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
  die "no python 3.11+ available; nothing to run"
fi
echo "=== interpreter: $PYBIN ($($PYBIN -V)) ==="
"$PYBIN" -m pip install --quiet boto3

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region}
tar xzf code.tar.gz

# Import the shipped tool before the long work rather than discovering a short payload
# after it. On the instance a missing import costs an hour and a launch; here, a second.
"$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD is short"
import importlib.util
import sys

sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("worker", "tools/opengenome_contigs.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("=== payload imports cleanly ===")
PRECHECK

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
# One worker per archive. A gzip stream cannot be split and a member is one stream, so this
# is the whole of the available parallelism; the archives differ in size so they end apart.
rc=0
pids=""
for archive in {archives}; do
  slug="${{archive//\\//-}}"
  ( "$PYBIN" tools/opengenome_contigs.py \
      --archive "$archive" \
      --outdir "/opt/amazebio/out-$slug" \
      --upload-results --allow-dirty --code-commit {commit} \
      --heartbeat-seconds {heartbeat} ; echo "=== $archive exited $? ===" ) &
  pids="$pids $!"
done
# `wait` with no arguments reports 0 whatever the jobs did, so a failed worker would be
# announced as a clean run. Waiting on each pid in turn is what makes the exit code mean
# something; `set +e` is needed because a non-zero wait would otherwise abort the script
# before `die` and leave the instance idling until the boot timer.
set +e
for pid in $pids; do
  wait "$pid" || rc=$?
done
set -e

echo "=== amazebio a7-4 contigs finished $(date -Is) ==="
die "run complete" "$rc"
"""


def _git_head(root: Path) -> tuple[str, bool]:
    """The commit the payload is built from, and whether the tree is dirty."""
    import subprocess

    def git(*a: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *a], capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    except Exception:
        return "unknown", True


def build_payload(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in PAYLOAD:
            tar.add(root / rel, arcname=rel)
    return buf.getvalue()


def slug(archive: str) -> str:
    """`v214/batch1.tar` -> `v214-batch1`. Mirrors the worker's own, which the test pins."""
    return archive.replace("/", "-").removesuffix(".tar")


def result_keys(prefix: str, commit: str, archives: tuple[str, ...] = ARCHIVES) -> dict[str, str]:
    """The objects the instance will publish, by archive — its only result channel.

    Must agree with what `repro.run(durable=...)` writes for the worker's outdir, which is
    `results/a7-4/<file name>`. The test asserts that rather than trusting two templates.
    """
    return {
        archive: f"{prefix}/results/a7-4/contigs-{slug(archive)}-{commit}.json"
        for archive in archives
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--instance-type",
        default="m6i.2xlarge",
        help="8 vCPU against four single-core workers, so the pass is never core-bound "
        "(default: %(default)s)",
    )
    ap.add_argument("--profile", default="AmazebioStager", help="instance profile name")
    ap.add_argument("--owner", default=os.environ.get("AMAZEBIO_OWNER", "claude"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--volume-size", type=int, default=30, help="GB, gp3; this pass streams")
    ap.add_argument(
        "--only",
        action="append",
        choices=ARCHIVES,
        help="run just this archive, repeatable. A spot reclaim leaves the published "
        "archives published; this is how the rest is re-run without paying for them again "
        "and without writing a second object under a key that can never be deleted",
    )
    ap.add_argument("--heartbeat-seconds", type=float, default=120.0)
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--hard-stop-minutes", type=int, default=None)
    ap.add_argument("--timeout-minutes", type=float, default=90.0)
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument("--attach", help="watch an already-running instance instead of launching")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.strip("/")
    archives = tuple(args.only or ARCHIVES)

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))
    import boto3

    from amazebio import ec2 as ec2mod

    ec2 = boto3.client("ec2", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    ssm = boto3.client("ssm", region_name=REGION)

    commit, dirty = _git_head(root)
    if dirty and not args.allow_dirty:
        raise SystemExit(
            "refusing to launch from a dirty tree: the instance has no checkout, so the "
            "commit is passed in and a manifest produced there would name a commit that "
            "does not describe the code that ran. Commit, or pass --allow-dirty."
        )

    if args.attach:
        return _run_and_collect(
            ec2, s3, ec2mod, args.attach, bucket, prefix, commit, archives, args
        )

    payload = build_payload(root)
    code_key = f"{prefix}/code/a7-4-contigs-{commit}.tar.gz"
    s3.put_object(Bucket=bucket, Key=code_key, Body=payload)
    print(f"code: s3://{bucket}/{code_key}  ({len(payload):,} bytes)")

    ami = ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]
    user_data = USER_DATA.format(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=REGION,
        archives=" ".join(archives),
        commit=commit,
        heartbeat=args.heartbeat_seconds,
        hard_stop_minutes=args.hard_stop_minutes or DEFAULT_HARD_STOP_MINUTES,
    )
    if len(user_data.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")

    # Omit either tag and the refusal is a bare `UnauthorizedOperation`, which reads exactly
    # like not having permission at all — a misreading that cost A1.3 a round trip.
    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": "amazebio-a7-4-contigs"},
    ]
    launch: dict[str, Any] = dict(
        ImageId=ami,
        InstanceType=args.instance_type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": args.profile},
        UserData=user_data,
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": tags},
            {"ResourceType": "volume", "Tags": tags},
        ],
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {"VolumeSize": args.volume_size, "VolumeType": "gp3"},
            }
        ],
        # `ec2:ModifyInstanceAttribute` is denied, so this cannot be set afterwards — and
        # without it a self-shutdown merely stops the instance and keeps billing its volume.
        InstanceInitiatedShutdownBehavior="terminate",
    )
    market = ec2mod.market_options(args.spot)
    if market is not None:
        launch["InstanceMarketOptions"] = market

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **launch)
        except Exception as exc:  # The dry run always raises; the code is the answer.
            print("dry run:", type(exc).__name__, str(exc)[:200])
        print(
            "\na dry run authorizes; it does not execute. It ran no UserData, so it cannot "
            "catch a missing dependency, a wrong interpreter or a broken script."
        )
        return 0

    try:
        instance = ec2.run_instances(**launch)["Instances"][0]
    except Exception as exc:
        message = ec2mod.spot_refusal(str(exc)) if args.spot else None
        if message:
            raise SystemExit(message) from exc
        raise
    iid = instance["InstanceId"]
    kind = "spot" if args.spot else "on-demand"
    print(f"launched {iid} ({args.instance_type}, {kind}, {args.volume_size} GB gp3)")
    return _run_and_collect(ec2, s3, ec2mod, iid, bucket, prefix, commit, archives, args)


def _run_and_collect(
    ec2: Any,
    s3: Any,
    ec2mod: Any,
    iid: str,
    bucket: str,
    prefix: str,
    commit: str,
    archives: tuple[str, ...],
    args: Any,
) -> int:
    """Watch, then terminate — unless the window simply ran out on a healthy run.

    A watch window expiring on an instance that is still working is not a failure, and
    killing it there threw away a finished corpus pass once already. The boot-armed timer
    bounds the instance whether or not this process is alive.
    """
    outcome, timed_out = 1, False
    try:
        outcome, timed_out = _watch(ec2, s3, ec2mod, iid, bucket, prefix, commit, archives, args)
    finally:
        state = ec2mod.state_of(ec2, iid)
        if timed_out and state == "running":
            print(
                f"\nwatch window expired and {iid} is still running — leaving it alone.\n"
                f"  its own shutdown timer bounds it.\n"
                f"  reattach:  python3 tools/ec2_opengenome_contigs.py --attach {iid}"
            )
        else:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminate requested for {iid}")
            except Exception as exc:
                print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")
    return outcome


def _watch(
    ec2: Any,
    s3: Any,
    ec2mod: Any,
    iid: str,
    bucket: str,
    prefix: str,
    commit: str,
    archives: tuple[str, ...],
    args: Any,
) -> tuple[int, bool]:
    """Poll object storage for results and heartbeats, and the console for progress.

    Object storage first, because it is the channel that distinguishes a working pass from
    a dead one. The heartbeats carry contigs read rather than only a timestamp, so a pass
    that is alive and one whose thread is alive are not the same reading (D-192).
    """
    import json

    wanted = result_keys(prefix, commit, archives)
    seen: set[str] = set()
    deadline = time.monotonic() + args.timeout_minutes * 60
    console_len = 0

    while time.monotonic() < deadline:
        for archive, key in wanted.items():
            if archive in seen:
                continue
            try:
                s3.head_object(Bucket=bucket, Key=key)
            except Exception:
                continue
            seen.add(archive)
            print(f"  published {archive}: s3://{bucket}/{key}", flush=True)

        if len(seen) == len(wanted):
            print(f"\nall {len(wanted)} archives published")
            return 0, False

        for archive in sorted(set(wanted) - seen):
            key = f"{prefix}/results/a7-4/heartbeat-{slug(archive)}-{commit}.json"
            try:
                beat = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
            except Exception:
                continue
            print(
                f"  {archive}: {beat.get('genomes', 0):,} genomes, "
                f"{beat.get('contigs', 0):,} contigs at {beat.get('written_at')}",
                flush=True,
            )

        state = ec2mod.state_of(ec2, iid)
        if state in ("shutting-down", "terminated", "stopped", "stopping"):
            reason = ec2mod.transition_reason(ec2, iid)
            missing = sorted(set(wanted) - seen)
            print(f"\n{iid} is {state}: {reason or 'no reason given'}")
            print(f"  published: {sorted(seen) or 'nothing'}")
            print(f"  missing:   {missing}")
            if "Service initiated" in reason:
                print(
                    "  'Service initiated' is how a spot reclaim reads, against the "
                    "'User initiated' AGENTS.md records for a shutdown or a manual "
                    "terminate (D-148). A published archive is reusable; re-run the rest "
                    "with --only."
                )
            return (0 if not missing else 1), False

        try:
            out = ec2.get_console_output(InstanceId=iid).get("Output", "") or ""
            if len(out) > console_len:
                print(out[console_len:], end="", flush=True)
                console_len = len(out)
        except Exception:
            pass

        time.sleep(args.poll_seconds)

    print(f"\nwatch window of {args.timeout_minutes:g} min expired; published {sorted(seen)}")
    return 1, True


if __name__ == "__main__":
    raise SystemExit(main())

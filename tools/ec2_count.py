#!/usr/bin/env python3
"""Run the composition count on an EC2 instance in us-east-1, and report back.

DECISIONS.md D-026 puts analysis in-region: the count reads 75 GB of staged
objects, which is free from inside us-east-1 and metered from anywhere else.

The shape of this script is dictated by what the account's IAM policy permits,
which is deliberately narrow and worth stating so the next person does not
rediscover it:

* `ssm:SendCommand` is denied and no key pair exists, so the instance cannot be
  driven after boot. Everything it does has to be in `UserData`, decided before
  launch.
* `ec2:AuthorizeSecurityGroupIngress` is denied, so nothing can connect *to* it
  either. Results come back the only way available: the instance writes them to
  S3, and progress is read from the serial console.
* The instance gets its S3 access from an instance profile. Credentials cannot
  be handed to it any other way — this session's own credentials are injected by
  a proxy and never exposed to it, so they cannot be copied onto a machine.

Parallelism is two processes, one per tier, and no more: a gzip stream is
sequential, so a single `.xml.gz` is one thread however many cores are present.
UniRef90 is the larger tier and therefore sets the wall clock.

The instance terminates itself when done, and is also terminated from here, so a
failed `UserData` cannot leave it running and billing.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import uniref

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

# The code the instance needs. Shipped as a tarball through S3 rather than baked
# into UserData: UserData is capped at 16 KiB and this is comfortably over it.
PAYLOAD = (
    "src/amazebio/__init__.py",
    "src/amazebio/uniref.py",
    "src/amazebio/repro.py",
    "tools/count_clusters.py",
)

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio count starting $(date -Is) ==="

dnf install -y tar gzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3`, and this project needs 3.12
# (pyproject requires-python) — `datetime.UTC` alone is 3.11+. Picking the
# interpreter explicitly rather than trusting `python3` is the difference between
# running and an ImportError 27 seconds in.
PYBIN=""
for cand in python3.12 python3.11; do
  dnf install -y "$cand" "$cand-pip" >/dev/null 2>&1 || true
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
  echo "FATAL: no python 3.11+ available; nothing to run"
  shutdown -h now
  exit 1
fi
echo "=== interpreter: $PYBIN ($($PYBIN -V)) ==="
"$PYBIN" -m pip install --quiet boto3

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region}
tar xzf code.tar.gz

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
# One process per tier. A gzip stream cannot be split, so this is the whole of
# the available parallelism; the tiers differ in size so they finish apart.
for tier in {tiers}; do
  ( "$PYBIN" tools/count_clusters.py --tier "$tier" \
      --outdir "/opt/amazebio/out-$tier" --upload-results --allow-dirty \
      --code-commit {commit} \
      --progress-seconds 60 ; echo "=== $tier exited $? ===" ) &
done
wait
echo "=== amazebio count finished $(date -Is) ==="
shutdown -h now
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--instance-type", default="c6i.xlarge")
    ap.add_argument("--profile", default="AmazebioStager", help="instance profile name")
    ap.add_argument("--owner", default=os.environ.get("AMAZEBIO_OWNER", "claude"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--tier", action="append", choices=["uniref50", "uniref90"])
    ap.add_argument("--timeout-minutes", type=float, default=90.0)
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.strip("/")
    tiers = tuple(dict.fromkeys(args.tier or ("uniref50", "uniref90")))

    import boto3

    s3 = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    ec2 = boto3.client(
        "ec2", region_name=REGION, endpoint_url=f"https://ec2.{REGION}.amazonaws.com"
    )
    ssm = boto3.client(
        "ssm", region_name=REGION, endpoint_url=f"https://ssm.{REGION}.amazonaws.com"
    )

    ami = ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]
    print(f"ami: {ami}")

    code_key = f"{prefix}/code/count-{int(time.time())}.tar.gz"
    payload = build_payload(Path(__file__).resolve().parent.parent)
    if not args.dry_run:
        s3.put_object(Bucket=bucket, Key=code_key, Body=payload)
    print(f"code: s3://{bucket}/{code_key}  ({len(payload):,} bytes)")

    commit, dirty = _git_head(Path(__file__).resolve().parent.parent)
    if dirty and not args.dry_run:
        raise SystemExit(
            "refusing to launch from a dirty tree: the instance has no git checkout, so the "
            "commit stamped into its manifest would not describe the code that ran. Commit first."
        )
    print(f"code commit: {commit}")

    user_data = USER_DATA.format(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=REGION,
        tiers=" ".join(tiers),
        commit=commit,
    )
    if len(user_data.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")

    # Both tags are required by the account's launch policy: Project gates the
    # action, Owner must merely be non-empty.
    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": "amazebio-a1-3-count"},
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
            # Nothing is written to disk — the tiers are streamed — so the root
            # volume only holds the OS, pip and the code.
            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 20, "VolumeType": "gp3"}}
        ],
        # Set at launch because ec2:ModifyInstanceAttribute is denied, so it
        # cannot be changed afterwards. Without it the self-shutdown would stop
        # the instance rather than terminate it, and keep billing the volume.
        InstanceInitiatedShutdownBehavior="terminate",
    )

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **launch)
        except Exception as exc:  # The dry run always raises; the code is the answer.
            print("dry run:", type(exc).__name__, str(exc)[:160])
        return 0

    instance = ec2.run_instances(**launch)["Instances"][0]
    iid = instance["InstanceId"]
    print(f"launched {iid} ({args.instance_type})")

    try:
        return _watch(ec2, s3, iid, bucket, prefix, tiers, args)
    finally:
        # Belt and braces: the instance shuts itself down, but a UserData failure
        # would otherwise leave it running and billing indefinitely.
        try:
            ec2.terminate_instances(InstanceIds=[iid])
            print(f"terminate requested for {iid}")
        except Exception as exc:  # Already gone is the expected case.
            print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")


def _watch(
    ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, tiers: tuple[str, ...], args: Any
) -> int:
    deadline = time.monotonic() + args.timeout_minutes * 60
    # One key per tier, matching what count_clusters.py writes.
    pending = {tier: f"{prefix}/results/{uniref.RELEASE}/composition-{tier}.json" for tier in tiers}
    collected: dict[str, Any] = {}
    seen_console = 0

    while time.monotonic() < deadline:
        time.sleep(args.poll_seconds)
        state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
            "State"
        ]["Name"]

        try:
            out = ec2.get_console_output(InstanceId=iid, Latest=True).get("Output", "")
            if len(out) > seen_console:
                tail = out[seen_console:]
                for line in tail.splitlines():
                    if any(
                        k in line
                        for k in (
                            "amazebio",
                            "clusters",
                            "counted",
                            "exited",
                            "Error",
                            "Traceback",
                            "wrote",
                        )
                    ):
                        print(f"  console: {line.strip()[:160]}")
                seen_console = len(out)
        except Exception:
            pass  # Console output is best-effort and often empty early on.

        for tier, key in list(pending.items()):
            try:
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            except s3.exceptions.NoSuchKey:
                continue
            collected[tier] = json.loads(body)
            del pending[tier]
            row = collected[tier]["tiers"][tier]
            print(
                f"  {tier}: {row['counts']['clusters']:,} clusters "
                f"({row['elapsed_seconds']:.0f}s, root version {row['root'].get('version')})"
            )

        if not pending:
            return _report(collected)

        print(f"  [{state}] waiting on {', '.join(sorted(pending))}")
        if state in ("terminated", "shutting-down") and pending:
            print(f"instance finished with {sorted(pending)} missing; see console output above")
            return _report(collected) if collected else 1

    print(f"timed out with {sorted(pending)} missing")
    return _report(collected) if collected else 1


def _report(collected: dict[str, Any]) -> int:
    """Merge the per-tier results into one verdict."""
    print("\n=== composition ===")
    agree = True
    for tier in sorted(collected):
        for row in collected[tier]["composition"]:
            if row["counted_clusters"] is None:
                continue
            verdict = "agrees" if row["agrees"] else f"differs by {row['delta']:+,}"
            print(
                f"{row['tier']}: counted {row['counted_clusters']:,} vs stated "
                f"{row['stated_clusters']:,} — {verdict}"
            )
            agree = agree and bool(row["agrees"])
    return 0 if agree else 1


if __name__ == "__main__":
    raise SystemExit(main())

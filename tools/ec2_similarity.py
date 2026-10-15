#!/usr/bin/env python3
"""Run A1.6's alignment calibration in us-east-1, and report back.

D-094 settled that this is in-region work: the staged ESM3 proxy is 295 GB, reading it from
outside the region is metered and measured at 42.5 MB/s, and it does not fit the session
container's disk. What it did not settle is the price of the full pass, which is what this
launches `tools/esm3_calibrate.py` to measure.

The shape of this script is dictated by the account's IAM policy, and `tools/ec2_count.py`
is the worked example AGENTS.md points at. Everything there applies here: no shell, no SSH,
no inbound connection, so all of it is decided before launch and written into `UserData`;
results come back by the instance writing to S3 and progress by the serial console; the
instance terminates itself and is terminated from here as well; the commit is passed in
because the instance has no git checkout.

Two things are specific to this run.

**The aligner travels as the upstream static build, pinned by checksum.** The lockfile pins
`mmseqs2 18.8cc5c` from bioconda, but that binary resolves its libraries out of the pixi
environment and there is no pixi on the instance. The upstream release for the same commit
ships a static AVX2 build, which is the same version by a route that works on a bare
Amazon Linux. `UserData` verifies its sha256 and gives up loudly rather than quietly
running a different aligner — the version is already one of ESM3's unstated parameters
(D-093) and it is not going to become one of ours.

**The run reports as it goes.** `esm3_calibrate.py` uploads its timing artefact after every
measurement, and `--search-budget-seconds` stops it starting a search it cannot finish. A
calibration whose largest shard times out should still hand back the smaller shards, since
the curve is the point and one missing endpoint is not fatal.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import tarfile
import time
from pathlib import Path
from typing import Any

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-latest/al2023-ami-kernel-default-x86_64"
AMI_PARAMETER_FALLBACK = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

#: The upstream static build of the version the lockfile pins. The tag is the release's,
#: the checksum is over the tarball, and both were verified in the session container before
#: this constant was written: the binary reports 8cc5ce367b5638c4306c2d7cfc652dd099a4643f,
#: which is the commit bioconda's 18.8cc5c is built from.
MMSEQS_URL = (
    "https://github.com/soedinglab/MMseqs2/releases/download/18-8cc5c/mmseqs-linux-avx2.tar.gz"
)
MMSEQS_SHA256 = "bd9b0234da5949ad528d5b5f9ea4cda9c1e23dce14b46c0791d4d919a76e61ce"

#: Shipped through S3 rather than baked into UserData, which is capped at 16 KiB.
PAYLOAD = (
    "src/amazebio/__init__.py",
    "src/amazebio/repro.py",
    "src/amazebio/uniref.py",
    "src/amazebio/seeds.py",
    "tools/esm3_calibrate.py",
)

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a1-6 calibration starting $(date -Is) ==="

# A dead man's switch, armed before anything that can fail. The launcher's own terminate
# in its `finally` covers a launcher that lives to run it; this covers the case it cannot
# — the session ending, the watcher being killed — and it is independent of whether the
# script below ever reaches its own shutdown. InstanceInitiatedShutdownBehavior=terminate
# at launch is what makes this a terminate rather than a stop that keeps billing a volume.
shutdown -h +{hard_stop_minutes} &

dnf install -y tar gzip unzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3`, and this project needs 3.12.
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

# The aligner, as the upstream static build of the pinned version. A checksum mismatch is
# fatal: running a different aligner than the one recorded would make every number here
# untraceable, which is worse than returning nothing.
curl -sSL -o mmseqs.tar.gz "{mmseqs_url}"
echo "{mmseqs_sha256}  mmseqs.tar.gz" | sha256sum -c - || {{
  echo "FATAL: mmseqs checksum mismatch; refusing to run a different aligner"
  shutdown -h now
  exit 1
}}
tar xzf mmseqs.tar.gz
export PATH="/opt/amazebio/mmseqs/bin:$PATH"
mmseqs version

# The taxonomy, pinned and dated. Not staged in the corpus bucket on purpose: that bucket
# has no DeleteObject, and an 80 MB input that is already served by its publisher at a
# dated URL does not need to be made permanent.
curl -sSL -o taxdmp.zip "{taxdump_url}"
echo "{taxdump_sha256}  taxdmp.zip" | sha256sum -c - || {{
  echo "FATAL: taxdump checksum mismatch"
  shutdown -h now
  exit 1
}}

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
( "$PYBIN" tools/esm3_calibrate.py \
    --release {release} --tier {tier} \
    --taxdump /opt/amazebio/taxdmp.zip \
    --outdir /opt/amazebio/out --workdir /mnt/work \
    --sample-rate {sample_rate} --buckets {buckets} --strict-buckets {strict_buckets} \
    --threads {threads} --workers {workers} --search-budget-seconds {budget} \
    --upload-results --allow-dirty --code-commit {commit} \
    --progress-seconds 300 ; echo "=== calibrate exited $? ===" )

echo "=== amazebio a1-6 calibration finished $(date -Is) ==="
shutdown -h now
"""


def _git_head(root: Path) -> tuple[str, bool]:
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
    root = Path(__file__).resolve().parent.parent
    import sys

    sys.path.insert(0, str(root / "src"))
    from amazebio import seeds

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # 8 vCPU and 64 GB. The account's policy allows the c6i, m6i and r6i families up to
    # 2xlarge and denies everything above it — probed, because the refusal is a bare
    # UnauthorizedOperation that reads like having no permission at all. Within that
    # ceiling the memory-heavy family is the right pick rather than the compute-heavy one:
    # 64 GB lets the query database and the target shards sit in memory, so MMseqs2 does
    # not split the target, and an unsplit search is what makes the measured curve a
    # scaling curve rather than a measurement of split behaviour. The corpus pass is one
    # gzip stream and therefore one core however many are present.
    ap.add_argument("--instance-type", default="r6i.2xlarge")
    ap.add_argument("--profile", default="AmazebioStager")
    ap.add_argument("--owner", default=os.environ.get("AMAZEBIO_OWNER", "claude"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--release", default="2023_02")
    ap.add_argument("--tier", default="uniref100")
    ap.add_argument("--sample-rate", type=int, default=50)
    ap.add_argument("--buckets", type=int, default=8)
    ap.add_argument("--strict-buckets", type=int, default=3)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument(
        "--workers",
        type=int,
        default=7,
        help="entry-parsing processes, one fewer than the vCPUs so the decompressor has "
        "a core to itself. Passed explicitly rather than left to the tool's default "
        "because this run's artefact gets cited (default: %(default)s)",
    )
    ap.add_argument(
        "--search-budget-seconds",
        type=float,
        default=7200.0,
        help="wall seconds the searches may consume before the run stops starting new "
        "ones (default: %(default)s)",
    )
    # 200 GB is the policy ceiling. The sample at the default rate is about 2 G residues,
    # whose database and temporaries are tens of gigabytes, so this is room to spare
    # rather than a tight fit — and the full target would not fit at any permitted size,
    # which is why the pass is sharded at all (D-094).
    ap.add_argument("--volume-size", type=int, default=120)
    ap.add_argument("--timeout-minutes", type=float, default=420.0)
    ap.add_argument(
        "--hard-stop-minutes",
        type=int,
        default=400,
        help="a shutdown timer armed on the instance at boot, before anything that can "
        "fail. Independent of the script reaching its own shutdown and of the launcher "
        "surviving to run its terminate (default: %(default)s)",
    )
    ap.add_argument("--poll-seconds", type=float, default=120.0)
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    args = ap.parse_args(argv)

    if args.volume_size > 200:
        raise SystemExit("the account's policy caps volumes at 200 GB in gp3/gp2")
    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.strip("/")

    import boto3

    s3 = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    ec2 = boto3.client(
        "ec2", region_name=REGION, endpoint_url=f"https://ec2.{REGION}.amazonaws.com"
    )
    ssm = boto3.client(
        "ssm", region_name=REGION, endpoint_url=f"https://ssm.{REGION}.amazonaws.com"
    )

    ami = ""
    for name in (AMI_PARAMETER_FALLBACK, AMI_PARAMETER):
        try:
            ami = ssm.get_parameter(Name=name)["Parameter"]["Value"]
            break
        except Exception as exc:
            print(f"ami lookup {name}: {type(exc).__name__}")
    if not ami:
        raise SystemExit("could not resolve an AL2023 AMI")
    print(f"ami: {ami}")

    commit, dirty = _git_head(root)
    if dirty and not args.dry_run:
        raise SystemExit(
            "refusing to launch from a dirty tree: the instance has no git checkout, so the "
            "commit stamped into its manifest would not describe the code that ran. Commit first."
        )
    print(f"code commit: {commit}")

    code_key = f"{prefix}/code/a1-6-calibrate-{int(time.time())}.tar.gz"
    payload = build_payload(root)
    if not args.dry_run:
        s3.put_object(Bucket=bucket, Key=code_key, Body=payload)
    print(f"code: s3://{bucket}/{code_key}  ({len(payload):,} bytes)")

    user_data = USER_DATA.format(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=REGION,
        commit=commit,
        release=args.release,
        tier=args.tier,
        sample_rate=args.sample_rate,
        buckets=args.buckets,
        strict_buckets=args.strict_buckets,
        threads=args.threads,
        workers=args.workers,
        budget=args.search_budget_seconds,
        hard_stop_minutes=args.hard_stop_minutes,
        mmseqs_url=MMSEQS_URL,
        mmseqs_sha256=MMSEQS_SHA256,
        taxdump_url=seeds.TAXDUMP_2023_04.url,
        taxdump_sha256=seeds.TAXDUMP_2023_04.sha256,
    )
    if len(user_data.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")

    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": "amazebio-a1-6-calibrate"},
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
        InstanceInitiatedShutdownBehavior="terminate",
    )

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **launch)
        except Exception as exc:  # The dry run always raises; the code is the answer.
            print("dry run:", type(exc).__name__, str(exc)[:200])
        return 0

    instance = ec2.run_instances(**launch)["Instances"][0]
    iid = instance["InstanceId"]
    print(f"launched {iid} ({args.instance_type}, {args.volume_size} GB gp3)")

    try:
        return _watch(ec2, s3, iid, bucket, prefix, args)
    finally:
        try:
            ec2.terminate_instances(InstanceIds=[iid])
            print(f"terminate requested for {iid}")
        except Exception as exc:
            print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")


def _watch(ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any) -> int:
    """Poll the result key and the serial console until the run lands or time runs out."""
    deadline = time.monotonic() + args.timeout_minutes * 60
    key = f"{prefix}/results/a1-6/calibration.json"
    seen_console = 0
    last_searches = -1

    while time.monotonic() < deadline:
        time.sleep(args.poll_seconds)
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            payload = json.loads(body)
            searches = len(payload.get("searches", []))
            if searches != last_searches:
                last_searches = searches
                done = [s for s in payload["searches"] if "search_core_seconds" in s]
                print(f"  [{searches} entries] " + _summarise(done))
        except Exception:
            pass

        try:
            out = ec2.get_console_output(InstanceId=iid, Latest=True).get("Output", "")
            if out and len(out) > seen_console:
                print(out[seen_console:], end="", flush=True)
                seen_console = len(out)
            if "calibration finished" in out:
                print("\n=== instance reported finished ===")
                break
        except Exception:
            pass

        state = _state(ec2, iid)
        if state in ("shutting-down", "terminated", "stopped"):
            print(f"\n=== instance {state} ===")
            break

    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        out = Path("artifacts/a1-6")
        out.mkdir(parents=True, exist_ok=True)
        (out / "calibration.json").write_bytes(body)
        print(f"collected s3://{bucket}/{key} -> artifacts/a1-6/calibration.json")
        return 0
    except Exception as exc:
        print(f"no result at s3://{bucket}/{key}: {type(exc).__name__}")
        return 1


def _summarise(done: list[dict[str, Any]]) -> str:
    return "  ".join(
        f"{d['reading'][:4]}/{d['shards']}: {d['search_core_seconds']:.0f} core-s"
        f" @ {d['residues'] / 1e9:.2f} Gres"
        for d in done
    )


def _state(ec2: Any, iid: str) -> str:
    try:
        return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
            "State"
        ]["Name"]
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())

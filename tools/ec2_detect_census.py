#!/usr/bin/env python3
"""Run A2.6's census-depth profile search in us-east-1 — DESIGN.md §A2.

A2.1 searched a 0.2% hash sample of OpenGenome and 0.1% of OpenGenome2, so every figure
resting on it is a lower bound. This runs the same search, with the same thresholds, over
the whole of both releases, so M1, M2 and M3 become population figures (D-222).

**Why in-region.** 35 GB of staged corpora, and every band worker streams its component in
full to test hash membership, so the pass moves hundreds of gigabytes. That is free inside
`us-east-1` and metered outside it, which is `AGENTS.md`'s test.

**Bands are the parallelism, and they already exist.** `detect_profiles.py --band LO:HI`
searches a slice of the hash space in multiples of the component's own initial rate, and
A2.1 built it for exactly this. OpenGenome's initial rate is 0.002, so `1:500` is
everything the first pass did not read; OpenGenome2's is 0.001, so `1:1000` is. Splitting
each into equal sub-bands gives one worker per core.

**The instance assembles nothing.** Each worker publishes its own part and stops. Assembly
is a merge of small tables with no corpus in it, so it runs in the session container where
a mistake costs a minute instead of a launch. `AGENTS.md` is explicit that you get one shot
at `UserData`; this keeps the shot small.

Everything that section demands, because none of it can be fixed after launch: a dead man's
switch armed before anything that can fail; every exit through one `die` that cancels the
pending timer first, since `shutdown -h now` is a no-op while one is scheduled; the
interpreter picked by name because Amazon Linux 2023's `python3` is 3.9; a payload derived
from the tool's import closure and imported on the instance before the long read; a
heartbeat through each worker's own published part; and the commit carried in, because the
instance has no checkout.
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import ec2 as ec2lib

TASK = "A2.6"
REGION = ec2lib.REGION
AMI_PARAMETER = ec2lib.AMI_PARAMETER

#: Each release's initial sampling rate, and therefore the band multiple that reaches a
#: census. A2.1 recorded these in its own manifests; they are repeated here because the
#: launcher has to split the band before anything reads a manifest, and
#: `tests/test_ec2_detect_census.py` checks them against `detect_profiles.SAMPLE_RATES`.
CENSUS_MULTIPLE = {"opengenome": 500, "opengenome2": 1000}

#: Pfam only. RVDB-prot's search is roughly fifteen times slower, about 815 core-hours, and
#: M3's bins are Pfam's. The asymmetry that creates — Pfam at census, RVDB still a sample —
#: is D-222's to report, not this launcher's to quietly resolve.
REGISTRY = "pfam"

#: Measured 2026-10-20: gene calling 666 knt/s/core, Pfam search 1.50 ms/gene on OpenGenome
#: and 2.19 ms on OpenGenome2, streaming 130 Mres/s. About 80 core-hours of real work, plus
#: the re-read each band pays. Six hours on 16 vCPU with headroom; the timer is the ceiling,
#: not the estimate.
DEFAULT_HARD_STOP_MINUTES = 540

#: The code the instance needs. Derived from the tool's first-party import closure and
#: checked by the test, because twice in this project a module was added to a tool's imports
#: and not to a list like this, and the instance died on an `ImportError` having read nothing.
PAYLOAD_MODULES = (
    "src/amazebio/__init__.py",
    "src/amazebio/apply.py",
    "src/amazebio/conformance.py",
    "src/amazebio/corpora.py",
    "src/amazebio/detect.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/policyspec.py",
    "src/amazebio/profiles.py",
    "src/amazebio/profilesearch.py",
    "src/amazebio/repro.py",
    "src/amazebio/seqstream.py",
    "src/amazebio/survival.py",
    "src/amazebio/uniref.py",
    "tools/detect_profiles.py",
    "tools/stage_profiles.py",
)

#: Wheels the instance needs. `pyhmmer` and `pyrodigal` are the search and the gene caller;
#: `pyarrow` reads OpenGenome's Parquet; `boto3` is the only way results come back.
WHEELS = "boto3 pyarrow 'pyhmmer>=0.11' 'pyrodigal>=3.7,<4' requests"

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a2-6 census starting $(date -Is) ==="

# A dead man's switch, armed before anything that can fail. The launcher's own terminate in
# its `finally` covers a launcher that lives to run it; this covers the case it cannot.
shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` is a no-op while that timer is pending: systemd already has a shutdown
# scheduled and the immediate one does not replace it, so a script that fails in thirty
# seconds would idle until the timer fires and look exactly like a long pass still working
# (D-127). Cancel first, then go down, with fallbacks.
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip xz >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3` and this project needs 3.12.
PYBIN=""
for cand in python3.12 python3.11; do
  dnf install -y "$cand" "$cand-pip" "$cand-devel" >/dev/null 2>&1 || true
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
  die "no python 3.11+ available; nothing to run"
fi
echo "=== interpreter: $PYBIN ($($PYBIN -V)) ==="
"$PYBIN" -m pip install --quiet {wheels} || die "the wheels did not install"

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region}
tar xzf code.tar.gz

# The A1.4 manifests say which records survive each reading. A2.1 consumes them rather than
# re-deriving a surviving set (D-059), so the census does too.
mkdir -p artifacts/a1-4
aws s3 cp "s3://{bucket}/results/a1-4/" artifacts/a1-4/ --recursive --region {region}

# Import the shipped tool before the long work rather than discovering a short payload
# after it. On the instance a missing import costs hours and a launch; here, a second.
"$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD_MODULES is short"
import importlib.util
import sys

sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("worker", "tools/detect_profiles.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("=== payload imports cleanly ===")
PRECHECK

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"

# The profiles come from EBI, pinned by URL and checked against their digests. Staging them
# before the workers start means one download rather than one per worker, and a failure here
# is cheap; a failure after six hours of reading is not.
"$PYBIN" tools/stage_profiles.py --registry {registry} --allow-dirty \
  || die "the pinned profiles did not stage"

# One worker per band. Each streams its component in full and keeps the records its slice of
# the hash space owns; in-region that read is free, and it is what buys the parallelism.
rc=0
pids=""
{worker_lines}
# `wait` with no arguments reports 0 whatever the jobs did, so a failed worker would be
# announced as a clean run. Waiting on each pid in turn is what makes the exit code mean
# something; `set +e` is needed because a non-zero wait would abort the script before `die`
# and leave the instance idling until the boot timer.
set +e
for pid in $pids; do
  wait "$pid" || rc=$?
done
set -e

echo "=== amazebio a2-6 census finished $(date -Is) ==="
die "run complete" "$rc"
"""

WORKER_LINE = """( "$PYBIN" tools/detect_profiles.py --task {task} --manifests artifacts/a1-4 \
--registry {registry} --release {release} --band {lo}:{hi} --out /opt/amazebio/out-{slug} \
--allow-dirty ; echo "=== {release} {lo}:{hi} exited $? ===" ) &
pids="$pids $!"
"""


def bands(multiple: int, workers: int) -> tuple[tuple[int, int], ...]:
    """Split `[1, multiple)` into `workers` contiguous sub-bands that tile it exactly.

    They must tile: `detect_profiles --assemble` checks that the bands cover the rate and
    refuses a table whose denominator claims records nothing read. A gap here would not be
    caught until six hours of compute had been spent, so the split is arithmetic rather
    than a convenience, and the test checks it tiles for every worker count.
    """
    if multiple <= 1:
        raise ValueError(f"a census multiple of {multiple} leaves nothing to read")
    if not 1 <= workers <= multiple - 1:
        raise ValueError(f"{workers} workers cannot split [1, {multiple})")
    edges = [1 + round(i * (multiple - 1) / workers) for i in range(workers + 1)]
    return tuple((edges[i], edges[i + 1]) for i in range(workers) if edges[i] < edges[i + 1])


def plan(releases: tuple[str, ...], workers_per_release: int) -> list[dict[str, Any]]:
    """Every worker the instance will start, in the order it starts them."""
    out: list[dict[str, Any]] = []
    for release in releases:
        multiple = CENSUS_MULTIPLE[release]
        for lo, hi in bands(multiple, workers_per_release):
            out.append({"release": release, "lo": lo, "hi": hi, "slug": f"{release}-{lo}-{hi}"})
    return out


def worker_lines(workers: list[dict[str, Any]], *, registry: str = REGISTRY) -> str:
    return "".join(WORKER_LINE.format(task=TASK, registry=registry, **w) for w in workers)


def build_payload(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in PAYLOAD_MODULES:
            tar.add(root / rel, arcname=rel)
    return buf.getvalue()


def user_data(
    *,
    bucket: str,
    prefix: str,
    code_key: str,
    workers: list[dict[str, Any]],
    hard_stop_minutes: int,
    registry: str = REGISTRY,
    region: str = REGION,
) -> str:
    return USER_DATA.format(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=region,
        registry=registry,
        wheels=WHEELS,
        hard_stop_minutes=hard_stop_minutes,
        worker_lines=worker_lines(workers, registry=registry),
    )


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--instance-type",
        default="m6i.4xlarge",
        help="16 vCPU at $0.18/h spot, which prices the pass at about a dollar "
        "(default: %(default)s)",
    )
    ap.add_argument("--workers-per-release", type=int, default=7)
    ap.add_argument(
        "--release",
        action="append",
        choices=sorted(CENSUS_MULTIPLE),
        help="run just this release, repeatable; the default is both",
    )
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--profile", default="AmazebioStager", help="instance profile name")
    ap.add_argument("--owner", default=os.environ.get("AMAZEBIO_OWNER", "claude"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument(
        "--volume-size",
        type=int,
        default=60,
        help="GB, gp3. The profiles unpack to about 1.5 GB and the corpora stream, so this "
        "is headroom rather than a requirement (default: %(default)s)",
    )
    ap.add_argument("--hard-stop-minutes", type=int, default=DEFAULT_HARD_STOP_MINUTES)
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--timeout-minutes", type=float, default=420.0)
    ap.add_argument("--poll-seconds", type=float, default=300.0)
    ap.add_argument("--attach", help="watch an already-running instance instead of launching")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    ap.add_argument("--print-user-data", action="store_true", help="print it and stop")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    releases = tuple(args.release or sorted(CENSUS_MULTIPLE))
    workers = plan(releases, args.workers_per_release)

    commit, dirty = _git_head(root)
    if dirty and not args.allow_dirty:
        raise SystemExit(
            "refusing to launch from a dirty tree: the instance has no checkout, so the "
            "commit is the only thing that makes its tables traceable (AGENTS.md)"
        )

    if not args.s3_uri:
        raise SystemExit("--s3-uri or AMAZEBIO_S3_URI is required; results come back that way")
    bucket, _, prefix = args.s3_uri.removeprefix("s3://").partition("/")
    prefix = prefix.strip("/")

    if args.print_user_data:
        print(
            user_data(
                bucket=bucket,
                prefix=prefix,
                code_key=f"{prefix}/code/a2-6-{commit}.tar.gz",
                workers=workers,
                hard_stop_minutes=args.hard_stop_minutes,
                registry=args.registry,
            )
        )
        return 0

    import boto3

    s3 = boto3.client("s3", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)

    code_key = f"{prefix}/code/a2-6-{commit}.tar.gz"
    print(f"{len(workers)} workers over {', '.join(releases)}", flush=True)
    for w in workers:
        print(f"  {w['release']} band {w['lo']}:{w['hi']}", flush=True)

    if args.attach:
        return _watch(ec2, args.attach, args)

    # Not on a dry run. A dry run authorizes and executes nothing, and the corpus bucket
    # has no delete, so an upload here would leave a permanent object behind for a launch
    # that never happened.
    if not args.dry_run:
        s3.put_object(Bucket=bucket, Key=code_key, Body=build_payload(root))
        print(f"payload at s3://{bucket}/{code_key}", flush=True)

    kwargs: dict[str, Any] = dict(
        ImageId=_ami(),
        InstanceType=args.instance_type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": args.profile},
        InstanceInitiatedShutdownBehavior="terminate",
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {"VolumeSize": args.volume_size, "VolumeType": "gp3"},
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": "ClaudeSpike"},
                    {"Key": "Owner", "Value": args.owner},
                    {"Key": "Task", "Value": TASK},
                ],
            }
        ],
        UserData=user_data(
            bucket=bucket,
            prefix=prefix,
            code_key=code_key,
            workers=workers,
            hard_stop_minutes=args.hard_stop_minutes,
            registry=args.registry,
        ),
    )
    market = ec2lib.market_options(args.spot)
    if market is not None:
        kwargs["InstanceMarketOptions"] = market

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **kwargs)
        except Exception as exc:  # DryRunOperation is the success case
            print(f"dry run: {exc}")
        return 0

    instance_id = ec2.run_instances(**kwargs)["Instances"][0]["InstanceId"]
    print(f"launched {instance_id}", flush=True)
    try:
        return _watch(ec2, instance_id, args)
    finally:
        # Both, not either: the boot timer covers a launcher that dies, this covers a
        # UserData that fails before reaching its own shutdown.
        try:
            ec2.terminate_instances(InstanceIds=[instance_id])
            print(f"terminate requested for {instance_id}", flush=True)
        except Exception as exc:
            print(f"terminate failed for {instance_id}: {exc}", file=sys.stderr)


def _ami() -> str:
    import boto3

    ssm = boto3.client("ssm", region_name=REGION)
    return ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]


def _watch(ec2: Any, instance_id: str, args: Any) -> int:
    deadline = time.time() + args.timeout_minutes * 60
    while time.time() < deadline:
        state = ec2lib.state_of(ec2, instance_id)
        print(f"  {instance_id} {state} at {time.strftime('%H:%M:%SZ', time.gmtime())}", flush=True)
        if state in {"terminated", "stopped", "shutting-down"}:
            print(f"  reason: {ec2lib.transition_reason(ec2, instance_id)}", flush=True)
            return 0
        time.sleep(args.poll_seconds)
    print("timed out waiting; the instance terminates itself on its own timer", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

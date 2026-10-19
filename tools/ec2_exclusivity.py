#!/usr/bin/env python3
"""Run A1.6's clause-(b) exposure pass in us-east-1 — D-158.

`tools/seed_exclusivity.py` reads a staged UniRef tier and asks, for each seed, whether the
publisher's cluster containing it holds a non-viral member. The two tiers are 62.7 GB and
30.4 GB of compressed stream, so reading them from the session container is metered egress
at a measured 42.5 MB/s; in-region it is free. That is the data-movement test in `AGENTS.md`
and this pass passes it.

**Both tiers run on one instance, sequentially.** A gzip stream cannot be decompressed in
parallel, so each tier wants the whole worker pool and running them concurrently would halve
each and save nothing. Sequential on one boot is about 45 minutes all in, scaled from D-100's
measured full-tier pass of 118.68 GB in 3,202.5 s on 8 vCPU with 7 parsing workers — roughly
$0.10 on spot.

Everything `AGENTS.md`'s EC2 section demands, because none of it can be fixed after launch:
one shot at `UserData`, no shell, no SSM, no inbound connection. A dead man's switch armed
before anything that can fail; every exit routed through one `die` that cancels the pending
timer first, since `shutdown -h now` does nothing while one is scheduled; the interpreter
picked by name because Amazon Linux 2023's `python3` is 3.9; a payload derived from the
tool's own import closure and tested, plus an import check on the instance before the long
read; a heartbeat to object storage, because a quiet console cannot be told apart from a
dead process; and provenance carried in, since an instance has no git checkout.
"""

from __future__ import annotations

import argparse
import io
import os
import tarfile
import time
from pathlib import Path
from typing import Any

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

#: Tiers, in the order the instance reads them. The 90 tier is twice the 50 tier's size and
#: goes first: if the window runs out, the tier that cost more is the one already published.
TIERS = ("uniref90", "uniref50")

#: The code the instance needs. Derived from the tool's first-party import closure and
#: checked by `tests/test_ec2_exclusivity.py` — twice in this task a module was added to a
#: tool's imports and not to a list like this, and the instance died on an `ImportError`
#: about half a minute in, having read nothing.
PAYLOAD = (
    "src/amazebio/__init__.py",
    "src/amazebio/exclusivity.py",
    "src/amazebio/repro.py",
    # repro imports objectstore for its durable-output upload (D-188); the closure test
    # catches the omission here rather than on the instance, where it costs a launch.
    "src/amazebio/objectstore.py",
    "src/amazebio/seeds.py",
    "src/amazebio/uniref.py",
    "tools/seed_exclusivity.py",
)

#: On-demand is 3-4x spot and this pass is cheap either way, so the default is the safe one
#: operationally rather than the cheap one. D-132 verified spot works in this account.
DEFAULT_HARD_STOP_MINUTES = 150

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a1-6 exclusivity starting $(date -Is) ==="

# A dead man's switch, armed before anything that can fail. The launcher's own terminate
# covers a launcher that lives to run it; this covers the case it cannot — the session
# ending, the watcher being killed. InstanceInitiatedShutdownBehavior=terminate at launch is
# what makes this a terminate rather than a stop that keeps billing a volume.
shutdown -h +{hard_stop_minutes} &

# `die` exists because `shutdown -h now` does nothing while that timer is pending: systemd
# already has a shutdown scheduled and the immediate one does not replace it. A script that
# fails in thirty seconds would otherwise sit idle until the timer fires, burning the whole
# window and looking from outside exactly like a long pass still working (D-127).
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip unzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3`, and this project needs 3.12; datetime.UTC
# alone is 3.11+. A run that trusts `python3` dies on an ImportError half a minute in.
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

# The taxonomy, pinned and dated. Not staged in the corpus bucket on purpose: that bucket
# has no DeleteObject, and an input already served by its publisher at a dated URL does not
# need to be made permanent.
curl -sSL -o taxdmp.zip "{taxdump_url}"
echo "{taxdump_sha256}  taxdmp.zip" | sha256sum -c - || {{
  die "taxdump checksum mismatch"
}}

# Import the tool before the long read rather than discovering a short payload after it. On
# the instance a missing import costs an hour and a launch; here it costs a second.
"$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD is short"
import importlib.util, sys
sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("tool", "tools/seed_exclusivity.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("=== payload imports cleanly ===")
PRECHECK

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
# Sequential, not concurrent: a gzip stream cannot be split, so each tier wants the whole
# pool and running them together would halve each for no gain.
rc=0
for tier in {tiers}; do
  ( "$PYBIN" tools/seed_exclusivity.py \
      --release {release} --tier "$tier" \
      --taxdump /opt/amazebio/taxdmp.zip \
      --outdir "/opt/amazebio/out-$tier" \
      --workers {workers} \
      --upload-results --allow-dirty --code-commit {commit} \
      --progress-seconds 120 --heartbeat-seconds 300 ) || rc=$?
  echo "=== $tier exited ${{rc}} ==="
done

echo "=== amazebio a1-6 exclusivity finished $(date -Is) ==="
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


def result_keys(prefix: str, release: str, commit: str) -> dict[str, str]:
    """The objects the instance will publish, by tier — the only channel its results use.

    Must agree with `tools/seed_exclusivity.py`'s own upload keys; the test asserts that
    rather than trusting two string templates to stay in step.
    """
    return {
        tier: f"{prefix}/results/a1-6/exclusivity/{release}/{tier}/counts-{commit}.json"
        for tier in TIERS
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", default="2023_02")
    ap.add_argument(
        "--instance-type",
        default="m6i.2xlarge",
        help="8 vCPU, which is what D-100's measured pass used and what the policy's "
        "ceiling allows (default: %(default)s)",
    )
    ap.add_argument("--profile", default="AmazebioStager", help="instance profile name")
    ap.add_argument("--owner", default=os.environ.get("AMAZEBIO_OWNER", "claude"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--volume-size", type=int, default=30, help="GB, gp3; this pass streams")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--hard-stop-minutes", type=int, default=None)
    ap.add_argument("--timeout-minutes", type=float, default=120.0)
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument("--attach", help="watch an already-running instance instead of launching")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.strip("/")

    import sys

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))
    import boto3

    from amazebio import ec2 as ec2mod
    from amazebio import seeds

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
        return _run_and_collect(ec2, s3, ec2mod, args.attach, bucket, prefix, commit, args)

    payload = build_payload(root)
    code_key = f"{prefix}/code/a1-6-exclusivity-{commit}.tar.gz"
    s3.put_object(Bucket=bucket, Key=code_key, Body=payload)
    print(f"code: s3://{bucket}/{code_key}  ({len(payload):,} bytes)")

    ami = ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]
    user_data = USER_DATA.format(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=REGION,
        release=args.release,
        tiers=" ".join(TIERS),
        workers=args.workers,
        commit=commit,
        hard_stop_minutes=args.hard_stop_minutes or DEFAULT_HARD_STOP_MINUTES,
        taxdump_url=seeds.TAXDUMP_2023_04.url,
        taxdump_sha256=seeds.TAXDUMP_2023_04.sha256,
    )
    if len(user_data.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")

    # Omit either tag and the refusal is a bare `UnauthorizedOperation`, which reads exactly
    # like not having permission at all — a misreading that cost A1.3 a round trip.
    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": "amazebio-a1-6-exclusivity"},
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
    return _run_and_collect(ec2, s3, ec2mod, iid, bucket, prefix, commit, args)


def _run_and_collect(
    ec2: Any, s3: Any, ec2mod: Any, iid: str, bucket: str, prefix: str, commit: str, args: Any
) -> int:
    """Watch, then terminate — unless the window simply ran out on a healthy run.

    Terminating in a bare `finally` is what `AGENTS.md`'s "both, not either" asks for and is
    wrong in exactly one case: a watch window expiring on an instance that is still working
    is not a failure, and killing it there threw away a finished corpus pass once already.
    The boot-armed timer is what prevents an orphan, and it does that whether or not this
    process is alive.
    """
    outcome = 1
    timed_out = False
    try:
        outcome, timed_out = _watch(ec2, s3, ec2mod, iid, bucket, prefix, commit, args)
    finally:
        state = ec2mod.state_of(ec2, iid)
        if timed_out and state == "running":
            print(
                f"\nwatch window expired and {iid} is still running — leaving it alone.\n"
                f"  its own shutdown timer bounds it.\n"
                f"  reattach:  python3 tools/ec2_exclusivity.py --attach {iid}"
            )
        else:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminate requested for {iid}")
            except Exception as exc:
                print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")
    return outcome


def _watch(
    ec2: Any, s3: Any, ec2mod: Any, iid: str, bucket: str, prefix: str, commit: str, args: Any
) -> tuple[int, bool]:
    """Poll object storage for results and the heartbeat, and the console for progress.

    Object storage first, because it is the channel that distinguishes a working pass from a
    dead one. `GetConsoleOutput` is allowed and best-effort — empty for the first minute or
    so, and unable to tell a process that has died from one printing nothing.
    """
    wanted = result_keys(prefix, args.release, commit)
    seen: set[str] = set()
    deadline = time.monotonic() + args.timeout_minutes * 60
    console_len = 0

    while time.monotonic() < deadline:
        for tier, key in wanted.items():
            if tier in seen:
                continue
            try:
                s3.head_object(Bucket=bucket, Key=key)
            except Exception:
                continue
            seen.add(tier)
            print(f"  published {tier}: s3://{bucket}/{key}", flush=True)

        if len(seen) == len(wanted):
            print(f"\nall {len(wanted)} tiers published")
            return 0, False

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
                    "terminate (D-148). A published tier is reusable; re-run the rest."
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

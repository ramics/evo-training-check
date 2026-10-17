#!/usr/bin/env python3
"""Run A2.4's prophage pass in region, where reading the corpus is free.

    python3 tools/ec2_proviruses.py --dry-run
    python3 tools/ec2_proviruses.py --owner you --rate 0.001      # proving run
    python3 tools/ec2_proviruses.py --owner you --rate 0.025      # the first band

`AGENTS.md`'s EC2 test is about data movement, and this qualifies: the pass reads 109 GiB of
Evo 2's GTDB and 118.5 GiB of Evo 1's to find the sampled genomes in them. That is free inside
`us-east-1` and metered out of it, and it is the only reason this is not a session-container job.

`tools/ec2_similarity.py` is the worked example this follows, and the lessons in it were
expensive. They are repeated here rather than imported because each launcher is its own one-shot
script and A1.6's is in active use by another track:

- **One shot at `UserData`.** No SSH, no SSM, no inbound. Everything the instance will do is
  decided before launch.
- **`shutdown -c` before `shutdown -h now`.** An immediate shutdown does nothing while the
  dead-man timer is pending, so a script that fails in thirty seconds otherwise sits idle for
  hours looking exactly like a long pass. That cost two launches and most of a day.
- **Terminate on shutdown *and* terminate from here**, except when the watch window merely
  expired on a healthy instance — killing that loses a finished pass, which has also happened.
- **Heartbeat to object storage.** The console is best-effort and cannot distinguish a dead
  process from a quiet one.
- **Derive the payload, do not list it by hand.** A module imported and not shipped kills the
  instance half a minute in, having read nothing; `tests/test_ec2_proviruses.py` derives the
  closure from the source.
- **Carry the commit in.** The instance has no checkout, so `repro` cannot discover it and an
  untraceable manifest is not citable.

One choice specific to this pass. The environments come from the project's own `pixi.lock`,
installed on the instance, rather than from packages pinned a second time in this file. The
lockfile *is* the pin (`AGENTS.md`: a compiled binary installed by side-channel instructions is
not pinned), and geNomad, VIBRANT, their interpreters and their search engines are four pins
that would otherwise have to be kept in step by hand in two places.
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

from amazebio.objectstore import REGION, split_uri
from amazebio.proviruses import GENOMAD

REPO = Path(__file__).resolve().parent.parent

#: Amazon Linux 2023, resolved from SSM at launch so the AMI is never stale in this file.
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

#: 8 vCPU and 64 GB. The policy caps instance types at 2xlarge, so this is the ceiling rather
#: than a preference. Memory is the reason for the `r` family: geNomad's marker search wants
#: about 24 GB to hold its index in one pass, and `--splits` trades that down at a cost in time.
DEFAULT_INSTANCE_TYPE = "r6i.2xlarge"

#: The volume has to hold the pixi environments (~3 GB), the profile registries (~700 MB), the
#: geNomad marker database (~3 GB unpacked), VIBRANT's pressed HMMs (~11 GB, needing ~20 GB of
#: temp while they are built) and the sampled sequence. 120 GB leaves room at every step and
#: stays under the policy's 200 GB cap.
DEFAULT_VOLUME_GB = 120

#: Used when --hard-stop-minutes is not given. Written into UserData at launch;
#: ec2:ModifyInstanceAttribute is denied, so nothing can change or read it back afterwards.
DEFAULT_HARD_STOP_MINUTES = 600

#: Where the instance writes. The watcher polls this prefix, and it is the only channel back.
RESULTS_PREFIX = "corpora/results/a2-4"

#: Shipped through S3 rather than baked into UserData, which is capped at 16 KiB.
#:
#: Derived, not trusted: `tests/test_ec2_proviruses.py` walks the shipped tool's imports and
#: fails if this is short. A1.6 lost two launches to exactly that, a month apart.
PAYLOAD = (
    "pixi.toml",
    "pixi.lock",
    "pyproject.toml",
    "src/amazebio/__init__.py",
    "src/amazebio/apply.py",
    "src/amazebio/corpora.py",
    "src/amazebio/detect.py",
    "src/amazebio/genomad.py",
    "src/amazebio/gtdb.py",
    "src/amazebio/imgvr.py",
    "src/amazebio/mgnify.py",
    "src/amazebio/models.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/opengenome.py",
    "src/amazebio/policyspec.py",
    "src/amazebio/profiles.py",
    "src/amazebio/profilesearch.py",
    "src/amazebio/proviruses.py",
    "src/amazebio/repro.py",
    "src/amazebio/seqstream.py",
    "src/amazebio/survival.py",
    "src/amazebio/uniref.py",
    "tools/detect_proviruses.py",
    "tools/stage_profiles.py",
)

USER_DATA = """#!/bin/bash
set -xuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a2-4 prophage pass starting $(date -Is) ==="

# Armed before anything that can fail. The launcher's own terminate covers a launcher that
# lives to run it; this covers the cases it cannot. InstanceInitiatedShutdownBehavior=terminate
# at launch is what makes this a terminate rather than a stop that keeps billing a volume.
shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` does nothing while that timer is pending: systemd already has a shutdown
# scheduled and the immediate one does not replace it. Cancel first, then go down, with
# fallbacks, because this is the one path that must not fail.
die() {{
  echo "=== shutting down: $1 ==="
  aws s3 cp - "s3://{bucket}/{results_prefix}/exit.txt" --region {region} <<<"$1" || true
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip unzip xz which >/dev/null 2>&1 || true

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region} || die "payload fetch failed"
tar xzf code.tar.gz || die "payload is not readable"

export PIXI_HOME=/opt/pixi
curl -fsSL https://pixi.sh/install.sh | bash >/dev/null 2>&1 || die "pixi install failed"
export PATH="/opt/pixi/bin:$PATH"
pixi --version || die "pixi not on PATH"

# The lockfile is the pin. Installing from it is what makes geNomad 1.12.0, VIBRANT 1.2.1 and
# their interpreters the same bytes the project records.
pixi install -e dev -e proviruses -e vibrant || die "pixi install failed"

export AMAZEBIO_S3_URI="s3://{bucket}/corpora"

# The profile registries, verified against the digests their publishers state.
pixi run -e dev python tools/stage_profiles.py --allow-dirty || die "profile staging failed"

# geNomad's marker database, pinned and checksummed. A mismatch is fatal: detecting with a
# different database than the one recorded would make every number here untraceable.
mkdir -p /opt/amazebio/db && cd /opt/amazebio/db
curl -sSL -o genomad_db.tar.gz "{genomad_db_url}" || die "genomad db download failed"
echo "{genomad_db_sha256}  genomad_db.tar.gz" | sha256sum -c - \
  || die "genomad database checksum mismatch; refusing to detect with a different database"
tar xzf genomad_db.tar.gz || die "genomad db is not readable"
cd /opt/amazebio

# VIBRANT's databases. Deliberately NOT fatal: it is the cheap second instrument, and losing
# the expensive pass to a failure here would be the wrong trade (D-114). If this fails the run
# continues and the tables say the count rests on one instrument.
( pixi run -e vibrant download-db.sh && echo "=== vibrant db ready ===" ) \
  || echo "=== vibrant db FAILED; continuing without the concordance arm ==="

pixi run -e dev python tools/detect_proviruses.py \
    --genomad-db /opt/amazebio/db/genomad_db \
    --rate {rate} \
    --out /opt/amazebio/out \
    --upload-results --allow-dirty --code-commit {commit} \
    {extra_flags}
echo "=== detect exited $? ==="

echo "=== amazebio a2-4 finished $(date -Is) ==="
die "run complete" 0
"""


def git_head(root: Path) -> tuple[str, bool]:
    """The commit this code is, and whether the tree is dirty."""
    import subprocess

    def git(*a: str) -> str:
        return subprocess.run(
            ["git", *a], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))


def build_payload(root: Path) -> bytes:
    """Tar the shipped files. Small enough to put in object storage and read back in a second."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for name in PAYLOAD:
            archive.add(root / name, arcname=name)
        manifests = root / "artifacts" / "a1-4"
        if not manifests.exists():
            raise SystemExit(
                "no A1.4 manifests at artifacts/a1-4: the instance consumes them rather than "
                "re-deriving a surviving set (D-059). Run tools/apply_policies.py first."
            )
        for path in sorted(manifests.glob("*.json")):
            archive.add(path, arcname=f"artifacts/a1-4/{path.name}")
    return buf.getvalue()


def market_options(spot: bool) -> dict[str, Any] | None:
    """One-time and terminate-on-interruption, for the reasons A1.6's launcher records.

    Persistent would re-launch after a reclaim and restart a multi-hour pass with nobody
    watching. Stop-on-interruption keeps billing the volume, which is the trap
    `InstanceInitiatedShutdownBehavior` exists to avoid.
    """
    if not spot:
        return None
    return {
        "MarketType": "spot",
        "SpotOptions": {
            "SpotInstanceType": "one-time",
            "InstanceInterruptionBehavior": "terminate",
        },
    }


def spot_refusal(text: str) -> str | None:
    """Why a spot launch was refused, in terms the next person can act on."""
    if "ServiceLinkedRole" in text or "AuthFailure" in text:
        return (
            f"spot was refused: {text[:200]}\n"
            "  the EC2 Spot service-linked role is what this needs, and no dry run detects "
            "its absence (D-120). It was verified present on 2026-10-17 (D-132), so this is "
            "either a new account state or a different failure — read the message above "
            "before re-running, and use --no-spot to proceed on demand."
        )
    if "InsufficientInstanceCapacity" in text or "capacity" in text.lower():
        return (
            f"spot capacity refused: {text[:200]}\n"
            "  the ordinary spot refusal. The same request may succeed later or on another "
            "instance type; nothing launched and nothing was billed."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owner", default=os.environ.get("USER") or "amazebio")
    ap.add_argument("--rate", type=float, default=0.025)
    ap.add_argument("--instance-type", default=DEFAULT_INSTANCE_TYPE)
    ap.add_argument("--volume-size", type=int, default=DEFAULT_VOLUME_GB)
    ap.add_argument("--profile", default="AmazebioStager")
    ap.add_argument("--no-spot", dest="spot", action="store_false")
    ap.add_argument("--release", action="append", help="restrict to one release; repeatable")
    ap.add_argument("--no-concordance", action="store_true")
    ap.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="read at most this many staged objects per source. For a proving run: it exercises "
        "the whole UserData path for pennies, and writes no table because its denominator is "
        "meaningless (D-143).",
    )
    ap.add_argument("--hard-stop-minutes", type=int, default=None)
    ap.add_argument("--timeout-minutes", type=float, default=90.0)
    ap.add_argument("--poll-seconds", type=float, default=30.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--attach", help="watch an already-running instance instead of launching")
    args = ap.parse_args(argv)

    import boto3

    bucket, _ = split_uri(os.environ["AMAZEBIO_S3_URI"])
    ec2 = boto3.client("ec2", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION, endpoint_url="https://s3.us-east-1.amazonaws.com")

    if args.attach:
        return watch_and_collect(ec2, s3, args.attach, bucket, args, launched_here=False)

    commit, dirty = git_head(REPO)
    if dirty and not args.allow_dirty:
        raise SystemExit(
            "the tree is dirty. A result that cannot be traced to the code that produced it is "
            "not citable, and the instance has no checkout to discover the commit from."
        )

    payload = build_payload(REPO)
    code_key = f"corpora/code/a2-4-{commit[:12]}.tar.gz"
    s3.put_object(Bucket=bucket, Key=code_key, Body=payload)
    print(f"payload {len(payload):,} bytes -> s3://{bucket}/{code_key}")

    extra = []
    for release in args.release or []:
        extra += ["--release", release]
    if args.no_concordance:
        extra.append("--no-concordance")
    if args.max_objects:
        extra += ["--max-objects", str(args.max_objects)]

    user_data = USER_DATA.format(
        bucket=bucket,
        region=REGION,
        code_key=code_key,
        results_prefix=RESULTS_PREFIX,
        rate=args.rate,
        commit=commit,
        extra_flags=" ".join(extra),
        hard_stop_minutes=args.hard_stop_minutes or DEFAULT_HARD_STOP_MINUTES,
        genomad_db_url=GENOMAD.database_url,
        genomad_db_sha256=GENOMAD.database_sha256,
    )
    if len(user_data.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")

    ami = boto3.client("ssm", region_name=REGION).get_parameter(Name=AMI_PARAMETER)["Parameter"][
        "Value"
    ]
    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": f"amazebio-a2-4-{args.rate}"},
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
    market = market_options(args.spot)
    if market is not None:
        launch["InstanceMarketOptions"] = market

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **launch)
        except Exception as exc:  # The dry run always raises; the code is the answer.
            print("dry run:", type(exc).__name__, str(exc)[:240])
        return 0

    try:
        instance = ec2.run_instances(**launch)["Instances"][0]
    except Exception as exc:
        message = spot_refusal(str(exc)) if args.spot else None
        if message:
            raise SystemExit(message) from exc
        raise
    iid = instance["InstanceId"]
    print(
        f"launched {iid} ({args.instance_type}, "
        f"{'spot' if args.spot else 'on-demand'}, {args.volume_size} GB gp3, rate {args.rate})"
    )
    return watch_and_collect(ec2, s3, iid, bucket, args, launched_here=True)


def watch_and_collect(
    ec2: Any, s3: Any, iid: str, bucket: str, args: Any, *, launched_here: bool
) -> int:
    """Watch, then terminate — unless the window merely ran out on a healthy instance.

    That exception is not a nicety. A1.6 killed a run at 115 minutes because that was the watch
    window and not because anything had failed, and lost the whole pass. The instance's own
    shutdown timer bounds it either way.
    """
    deadline = time.monotonic() + args.timeout_minutes * 60
    seen = 0
    observed_end = False
    try:
        while time.monotonic() < deadline:
            time.sleep(args.poll_seconds)
            try:
                beat = s3.get_object(Bucket=bucket, Key=f"{RESULTS_PREFIX}/heartbeat.json")[
                    "Body"
                ].read()
                print(f"  heartbeat: {json.loads(beat)}", flush=True)
            except Exception:
                pass
            try:
                out = ec2.get_console_output(InstanceId=iid, Latest=True).get("Output", "")
                if out and len(out) > seen:
                    print(out[seen:], end="", flush=True)
                    seen = len(out)
                if "a2-4 finished" in out:
                    print("\n=== instance reported finished ===")
                    observed_end = True
                    break
            except Exception:
                pass
            state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
                "State"
            ]["Name"]
            if state in ("shutting-down", "terminated", "stopped"):
                print(f"\n=== instance {state} ===")
                observed_end = True
                break
    finally:
        state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
            "State"
        ]["Name"]
        # Leave the instance alone whenever this process is giving up *without having seen
        # the run end* — a timeout, yes, but also a watcher that died. The first version
        # terminated on any exception, and a `| head -4` on the launcher's own output was
        # enough: head closed the pipe, the print raised BrokenPipeError, and the finally
        # killed a healthy instance thirty seconds after launch. The dead-man timer armed in
        # UserData is what prevents an orphan, and it does that whether or not this process
        # is alive.
        if not observed_end and state in ("running", "pending"):
            bound = (
                f"{args.hard_stop_minutes or DEFAULT_HARD_STOP_MINUTES} min from boot"
                if launched_here
                else "set by the launch that created it, which this process cannot read back"
            )
            print(
                f"\nstopped watching {iid} without seeing it finish, and it is {state} — "
                "leaving it alone.\n"
                f"  its own shutdown timer ({bound}) bounds it.\n"
                f"  reattach:  python3 tools/ec2_proviruses.py --attach {iid}"
            )
        else:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminate requested for {iid}")
            except Exception as exc:
                print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")

    collected = 0
    out = REPO / "artifacts" / "a2-4"
    out.mkdir(parents=True, exist_ok=True)
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=f"{RESULTS_PREFIX}/"
    ):
        for obj in page.get("Contents", []):
            name = obj["Key"].rsplit("/", 1)[-1]
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            (out / name).write_bytes(body)
            collected += 1
    print(f"collected {collected} artefact(s) into {out.relative_to(REPO)}")
    return 0 if collected else 1


if __name__ == "__main__":
    raise SystemExit(main())

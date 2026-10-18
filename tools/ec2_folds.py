#!/usr/bin/env python3
"""Launch one GPU instance to measure A2.2's 3Di throughput, then bring it down.

Why an instance at all, when AGENTS.md says to launch sparingly and that a memory ceiling is
not a reason: this is neither convenience nor memory. 3Di prediction is the whole cost of
A2.2 — D-163 measured 18.58 core-hours per million residues on CPU, 173x the profile search
it feeds — and the session container has no GPU, so the speedup that decides what depth A2.2
can pre-register cannot be measured here at all. One short run on one instance answers it.

Everything AGENTS.md's EC2 section learned the hard way applies, and the three that bite
hardest here:

**Only the GPU xlarges are authorized.** `RunInstances` with `DryRun=True` returns
`DryRunOperation` for `g5.xlarge` and `g6.xlarge` and `UnauthorizedOperation` for both
2xlarges (D-163). The refusal is bare — it reads exactly like having no permission at all,
which AGENTS.md records as having already cost a round trip — so this tool refuses an
unauthorized type itself, with the reason, rather than letting the API say nothing useful.

**The usual AMI has no GPU driver.** Every other `tools/ec2_*.py` boots the base AL2023 AMI,
which carries no NVIDIA driver; foldseek would then find no device and quietly do the work on
the CPU, and the headline number would be a fiction that looks fine. So this one boots the
Deep Learning base AL2023 AMI instead, and `fold_throughput.py` proves the GPU is usable
before it times anything on it.

**The instance cannot be asked anything.** No SSH, no SSM, no inbound. So the payload, the
pins and every command are decided here and written into `UserData`, results come back
through object storage, and progress comes back through a heartbeat the measurement publishes
per rung plus best-effort console output. A step with no heartbeat is a step whose silence
means nothing.

The shutdown is belt and braces, because each layer covers a case the others cannot: a
boot-armed `shutdown -h +N` that fires even if this launcher dies;
`InstanceInitiatedShutdownBehavior="terminate"` so that shutdown terminates rather than stops
and keeps billing a volume (`ec2:ModifyInstanceAttribute` is denied, so it cannot be set
later); a `die` helper that runs `shutdown -c` first, because an immediate shutdown does
nothing while that timer is pending and a script that fails in thirty seconds would otherwise
idle away the whole window; and a `terminate` in this launcher's `finally`.
"""

from __future__ import annotations

import argparse
import io
import json
import tarfile
import time
from pathlib import Path
from typing import Any

REGION = "us-east-1"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"

#: The Deep Learning *base* AMI: NVIDIA driver and CUDA, without the frameworks a PyTorch
#: image would carry, which this run has no use for. Readable through `ssm:GetParameter`,
#: verified before this constant was written. Not the parameter the other ec2 tools use —
#: that AMI has no driver, and the whole measurement depends on one being present.
AMI_PARAMETER = (
    "/aws/service/deeplearning/ami/x86_64/"
    "base-oss-nvidia-driver-gpu-amazon-linux-2023/latest/ami-id"
)

#: The only two instance types the account's policy permits with a GPU, established by dry
#: run rather than read off a table (D-163). `g5.xlarge` is an A10G, `g6.xlarge` an L4; both
#: are 4 vCPU, which is also the session container's core count, so the CPU rungs measured on
#: the instance are directly comparable with D-163's container figures.
ALLOWED_TYPES = ("g5.xlarge", "g6.xlarge")

PIXI_URL = (
    "https://github.com/prefix-dev/pixi/releases/download/v0.42.1/pixi-x86_64-unknown-linux-musl"
)
PIXI_SHA256 = "d305406a7630aab6484419833f9204b2fe9ea40632da8bb536496f123ca86e7f"

#: Where results land. The corpus bucket has no `s3:DeleteObject`, so these keys are
#: permanent and are written once per run under a distinct prefix.
RESULT_PREFIX = "corpora/results/a2-2"

#: Used when --hard-stop-minutes is not given. Deliberately not an argparse default: the timer
#: is baked into UserData at launch and `ec2:ModifyInstanceAttribute` is denied, so nothing
#: later can read it back or change it, and a watcher attaching to a running instance must be
#: able to tell the timer it armed from one it did not.
DEFAULT_HARD_STOP_MINUTES = 180

#: Every first-party module the shipped tool imports, transitively, plus what pixi needs to
#: rebuild the environment from the committed lockfile. Derived from the source by
#: `tests/test_ec2_folds.py` rather than kept by hand: AGENTS.md records two launches lost on
#: 2026-10-16 and 2026-10-17 to exactly this list being one module short, each time dying on
#: an ImportError about half a minute in having read nothing.
PAYLOAD = (
    "pixi.toml",
    "pixi.lock",
    "pyproject.toml",
    "src/amazebio/__init__.py",
    "src/amazebio/conformance.py",
    "src/amazebio/corpora.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/policyspec.py",
    "src/amazebio/repro.py",
    "tools/fold_throughput.py",
)

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a2-2 3di throughput starting $(date -Is) ==="

# Armed before anything that can fail. Covers the cases the launcher's own terminate cannot:
# the session ending, the watcher being killed. InstanceInitiatedShutdownBehavior=terminate at
# launch is what makes this terminate rather than stop and keep billing the volume.
shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` does nothing while that timer is pending — systemd already has a shutdown
# scheduled and the immediate one does not replace it — so a script that fails early would
# otherwise sit idle for the whole window, looking from outside exactly like a long run.
# Cancel first, then go down, with fallbacks, because this is the path that must not fail.
die() {{
  echo "=== shutting down: $1 ==="
  aws s3 cp /var/log/cloud-init-output.log \
    "s3://{bucket}/{prefix}/cloud-init-output.log" --region {region} || true
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

# The driver is the reason this AMI was chosen; if it is absent the whole run is pointless and
# would silently produce CPU numbers under a GPU label. Fail loudly instead.
nvidia-smi || die "no NVIDIA driver on this AMI; the GPU measurement is impossible"

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region} || die "payload fetch failed"
tar xzf code.tar.gz

curl -sSL -o /usr/local/bin/pixi "{pixi_url}" || die "pixi download failed"
echo "{pixi_sha256}  /usr/local/bin/pixi" | sha256sum -c - \
  || die "pixi checksum mismatch; refusing to build the environment with an unpinned tool"
chmod +x /usr/local/bin/pixi

export PIXI_HOME=/opt/pixi
pixi install -e dev -e foldseek || die "pixi env solve/install failed"
FOLDSEEK="$(pixi run -e foldseek bash -c 'command -v foldseek')"
echo "=== foldseek: $FOLDSEEK $($FOLDSEEK version) ==="

# Import the shipped tool before the long work, not after. On the instance a short PAYLOAD
# costs an hour and a launch; here it costs a second.
pixi run -e dev python -c "
import importlib.util, sys
sys.path.insert(0, 'src')
spec = importlib.util.spec_from_file_location('ft', 'tools/fold_throughput.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('=== payload imports cleanly ===')
" || die "the shipped payload cannot import; PAYLOAD is short"

# 2.3 GB of f16 GGUF from huggingface.co/Rostlab/ProstT5, unauthenticated (D-163).
pixi run -e foldseek foldseek databases ProstT5 /opt/amazebio/prostt5 /opt/amazebio/tmpdb \
  --threads {threads} || die "ProstT5 weights download failed"

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
( pixi run -e dev python tools/fold_throughput.py \
    --foldseek "$FOLDSEEK" \
    --prostt5-model /opt/amazebio/prostt5 \
    --outdir /opt/amazebio/out --workdir /opt/amazebio/work \
    --devices {devices} --ladder {ladder} --cpu-ladder {cpu_ladder} \
    --threads {threads} \
    --s3-uri "$AMAZEBIO_S3_URI" --upload-results \
    --allow-dirty --code-commit {commit} ; echo "=== throughput exited $? ===" )

echo "=== amazebio a2-2 3di throughput finished $(date -Is) ==="
die "run complete" 0
"""


def git_head(root: Path) -> tuple[str, bool]:
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


def render_user_data(**kwargs: Any) -> str:
    text = USER_DATA.format(**kwargs)
    if len(text.encode()) > 16 * 1024:
        raise SystemExit("user data exceeds the 16 KiB limit")
    return text


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--instance-type", default="g6.xlarge", choices=ALLOWED_TYPES)
    ap.add_argument("--owner", default="claude", help="non-empty Owner tag, required by policy")
    ap.add_argument("--profile", default="AmazebioStager", help="instance profile name")
    ap.add_argument("--volume-size", type=int, default=120, help="gp3 GiB; policy caps at 200")
    ap.add_argument("--threads", type=int, default=4, help="vCPUs on the chosen type")
    ap.add_argument("--devices", default="cpu,gpu")
    ap.add_argument("--ladder", default="100,500,1725,6000,20000")
    ap.add_argument(
        "--cpu-ladder",
        default="100,500",
        help="the CPU arm needs its own short ladder: at the measured CPU rate the largest "
        "GPU rung is about twenty hours, and the CPU arm is only here to pair with the GPU "
        "on identical input so the ratio is one machine's measurement.",
    )
    ap.add_argument("--hard-stop-minutes", type=int, default=DEFAULT_HARD_STOP_MINUTES)
    ap.add_argument("--bucket", default=None)
    ap.add_argument("--prefix", default=None, help="result prefix; defaults to a dated one")
    ap.add_argument("--dry-run", action="store_true", help="authorize only; runs no UserData")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import boto3

    args = parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    commit, dirty = git_head(root)
    if dirty and not args.allow_dirty:
        # The instance has no checkout, so `repro` cannot discover the commit there and the
        # launcher passes it in. A commit that does not describe the shipped code makes every
        # number untraceable, which is the whole point of carrying it.
        raise SystemExit(
            "refusing to launch from a dirty tree: the commit passed to the instance would "
            "not describe the code that ran. Commit first, or pass --allow-dirty."
        )
    if args.volume_size > 200:
        raise SystemExit("policy caps volumes at 200 GB in gp3/gp2")

    import sys

    sys.path.insert(0, str(root / "src"))
    from amazebio import corpora

    bucket = args.bucket or corpora.BUCKET
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    prefix = args.prefix or f"{RESULT_PREFIX}/throughput/{stamp}-{commit[:12]}"
    code_key = f"{prefix}/code.tar.gz"

    s3 = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    ec2 = boto3.client(
        "ec2", region_name=REGION, endpoint_url=f"https://ec2.{REGION}.amazonaws.com"
    )
    ssm = boto3.client(
        "ssm", region_name=REGION, endpoint_url=f"https://ssm.{REGION}.amazonaws.com"
    )

    user_data = render_user_data(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=REGION,
        commit=commit,
        devices=args.devices,
        ladder=args.ladder,
        cpu_ladder=args.cpu_ladder,
        threads=args.threads,
        hard_stop_minutes=args.hard_stop_minutes,
        pixi_url=PIXI_URL,
        pixi_sha256=PIXI_SHA256,
    )

    ami = ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]
    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": args.owner},
        {"Key": "Name", "Value": f"amazebio-a2-2-throughput-{stamp}"},
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
        # Authorizes; runs no UserData, so it cannot catch a missing dependency or a broken
        # script. Those checks live in the script and in the tests.
        try:
            ec2.run_instances(DryRun=True, **launch)
            print("dry run: unexpected success (it should always raise)")
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            print(f"dry run: {code}")
            if code == "UnauthorizedOperation":
                print(
                    f"  {args.instance_type} is not authorized. Only {ALLOWED_TYPES} carry a "
                    "GPU under this policy, and the refusal is bare rather than explanatory."
                )
        return 0

    print(f"=== uploading payload to s3://{bucket}/{code_key}", flush=True)
    s3.put_object(Bucket=bucket, Key=code_key, Body=build_payload(root))

    instance = ec2.run_instances(**launch)["Instances"][0]
    iid = instance["InstanceId"]
    print(
        f"=== launched {iid} ({args.instance_type}, ami {ami}, "
        f"hard stop +{args.hard_stop_minutes}m)\n"
        f"=== results: s3://{bucket}/{prefix}",
        flush=True,
    )

    try:
        return watch(ec2, s3, iid, bucket, prefix, args)
    finally:
        # Also, not instead: a UserData that fails before its own `shutdown` would otherwise
        # leave this running indefinitely.
        try:
            ec2.terminate_instances(InstanceIds=[iid])
            print(f"=== terminated {iid}", flush=True)
        except Exception as exc:
            print(f"=== TERMINATE FAILED for {iid}: {type(exc).__name__} — check the console")


def watch(ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any) -> int:
    """Poll the heartbeat and the console until the artefact lands or the instance goes.

    `GetConsoleOutput` is allowed and best-effort — empty for the first minute or so, and it
    cannot distinguish a dead process from a quiet one, which is exactly the misreading that
    cost four hours on 2026-10-16. The heartbeat is the channel that carries meaning; the
    console is for the boot failures that happen before the heartbeat exists.
    """
    deadline = time.monotonic() + args.hard_stop_minutes * 60 + 300
    result_key = f"{prefix}/throughput.json"
    seen_stage = None
    while time.monotonic() < deadline:
        time.sleep(args.poll_seconds)
        try:
            s3.head_object(Bucket=bucket, Key=result_key)
            print(f"=== result landed: s3://{bucket}/{result_key}", flush=True)
            body = s3.get_object(Bucket=bucket, Key=result_key)["Body"].read()
            data = json.loads(body)
            print(json.dumps(data.get("speedup", {}), indent=2, sort_keys=True), flush=True)
            print(json.dumps(data.get("projection", {}), indent=2, sort_keys=True), flush=True)
            return 0
        except Exception:
            pass
        try:
            beat = json.loads(
                s3.get_object(Bucket=bucket, Key=f"{prefix}/throughput-progress.json")[
                    "Body"
                ].read()
            )
            stage = (beat.get("stage"), len(beat.get("points", {}).get("gpu", []) or []))
            if stage != seen_stage:
                seen_stage = stage
                print(f"    heartbeat: {beat.get('stage')} {beat.get('written_at')}", flush=True)
        except Exception:
            pass
        state = instance_state(ec2, iid)
        if state in ("shutting-down", "terminated", "stopped"):
            print(f"=== instance {state}; no result object", flush=True)
            tail = console_tail(ec2, iid)
            if tail:
                print("--- console tail ---\n" + tail, flush=True)
            return 1
    print("=== watcher deadline reached", flush=True)
    return 1


def instance_state(ec2: Any, iid: str) -> str:
    try:
        r = ec2.describe_instances(InstanceIds=[iid])
        return str(r["Reservations"][0]["Instances"][0]["State"]["Name"])
    except Exception:
        return "unknown"


def console_tail(ec2: Any, iid: str, lines: int = 40) -> str | None:
    try:
        out = ec2.get_console_output(InstanceId=iid, Latest=True).get("Output", "")
    except Exception:
        return None
    return "\n".join(out.splitlines()[-lines:]) if out else None


if __name__ == "__main__":
    raise SystemExit(main())

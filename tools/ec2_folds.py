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

#: The same pinned pixi `tools/ec2_proviruses.py` uses, and deliberately the same three
#: constants rather than a re-derivation: the first launch of this tool died on a checksum
#: mismatch because they were copied by eye into one hardcoded URL, which lost both the
#: version (0.82.0, read off an f-string as 0.42.1) and the `.tar.gz` suffix. The URL was
#: still a real release asset, so it downloaded a valid binary and failed only at the
#: checksum — which is the pin doing its job, and the cheapest possible version of that
#: mistake. `tests/test_ec2_folds.py` now asserts these three agree with that tool's, so the
#: next person to change one changes both.
PIXI_VERSION = "0.82.0"
PIXI_URL = (
    f"https://github.com/prefix-dev/pixi/releases/download/v{PIXI_VERSION}"
    "/pixi-x86_64-unknown-linux-musl.tar.gz"
)
PIXI_SHA256 = "d305406a7630aab6484419833f9204b2fe9ea40632da8bb536496f123ca86e7f"

#: Where results land. The corpus bucket has no `s3:DeleteObject`, so these keys are
#: permanent and are written once per run under a distinct prefix.
RESULT_PREFIX = "corpora/results/a2-2"

#: The project owner's spending ceiling for A2.2, set on 2026-10-18 after being shown D-164's
#: figures: the detection pass may not exceed this. It is enforced here rather than remembered,
#: because the one control this tool has over spend is the shutdown timer it bakes into UserData
#: at launch — `ec2:ModifyInstanceAttribute` is denied, so nothing can shorten it afterwards, and
#: an instance that outlives its budget cannot be reined in, only killed. So the timer is derived
#: from the ceiling and the live price, and the launch is refused outright when the two cannot
#: buy a useful window.
DEFAULT_MAX_SPEND_USD = 30.0

#: Below this, a window is not worth a launch: the fixed cost of booting, building the
#: environment and fetching 2.3 GB of weights is about three minutes, and a run that then has
#: minutes left produces nothing while still being billed.
MIN_USEFUL_WINDOW_MINUTES = 20

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
    "src/amazebio/detect.py",
    "src/amazebio/folds.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/policyspec.py",
    "src/amazebio/profiles.py",
    "src/amazebio/profilesearch.py",
    "src/amazebio/repro.py",
    "src/amazebio/seqstream.py",
    "src/amazebio/survival.py",
    "src/amazebio/uniref.py",
    "tools/detect_folds.py",
    "tools/fold_throughput.py",
)

USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a2-2 {stage} starting $(date -Is) ==="

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

curl -sSL -o pixi.tar.gz "{pixi_url}" || die "pixi download failed"
echo "{pixi_sha256}  pixi.tar.gz" | sha256sum -c - \
  || die "pixi checksum mismatch; refusing to build the environment with an unpinned tool"
tar xzf pixi.tar.gz && install -m 0755 pixi /usr/local/bin/pixi || die "pixi install failed"

export PIXI_HOME=/opt/pixi
pixi install -e dev -e foldseek || die "pixi env solve/install failed"
FOLDSEEK="$(pixi run -e foldseek bash -c 'command -v foldseek')"
echo "=== foldseek: $FOLDSEEK $($FOLDSEEK version) ==="

# Import the shipped code before the long work, not after. On the instance a short PAYLOAD
# costs an hour and a launch; here it costs a second.
#
# Through the ordinary import machinery, and that detail is the whole lesson of the launch
# this replaced. The first version loaded the tool with `spec_from_file_location` +
# `module_from_spec` without registering it in `sys.modules`, and `@dataclass` then died on
# `sys.modules.get(cls.__module__).__dict__` being None. So the guard against a short payload
# failed on a payload that was complete — a false positive that killed the run just as
# effectively as the bug it was watching for. Importing every shipped module by name, and
# starting the tool the way the run starts it, tests the path that will actually be used.
pixi run -e dev python - <<'PRECHECK' || die "shipped modules cannot import; PAYLOAD is short"
import importlib
import pathlib
import sys

sys.path.insert(0, "src")
for path in sorted(pathlib.Path("src/amazebio").glob("*.py")):
    if path.stem != "__init__":
        importlib.import_module(f"amazebio.{{path.stem}}")
print("=== every shipped module imports cleanly ===")
PRECHECK
pixi run -e dev python {smoke_tool} --help >/dev/null \
  || die "the shipped tool cannot start"
{inputs_block}

# The 2.3 GB of f16 GGUF, fetched from **our own bucket** rather than from upstream.
#
# `foldseek databases ProstT5` downloads from a third-party Cloudflare worker, and on
# 2026-10-19 it returned `status=429` to all three attempts from an instance, fifteen minutes
# after the identical file downloaded cleanly in the session container. A rate limit is not a
# transient a short retry clears, and it sat on the critical path of a 24.7-hour pass.
#
# Pinning matters more than the outage. The published command names no digest, and D-171's
# threshold was measured with these exact bytes — an instance fetching a different build under
# the same name would apply a threshold measured on one instrument to another, silently. So the
# weights are staged by tools/stage_prostt5.py under a key derived from their digest, and
# verified here against it: in region, free, and identical on every launch.
mkdir -p /opt/amazebio/prostt5
aws s3 cp "s3://{bucket}/{weights_key}" /opt/amazebio/prostt5/{weights_name} \
  --region {region} || die "ProstT5 weights fetch from the staged copy failed"
echo "{weights_sha256}  /opt/amazebio/prostt5/{weights_name}" | sha256sum -c - \
  || die "staged ProstT5 weights do not match their pin; refusing to predict 3Di with them"

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
{run_block}

echo "=== amazebio a2-2 {stage} finished $(date -Is) ==="
die "run complete" 0
"""


def market_options(spot: bool) -> dict[str, Any] | None:
    """One-time and terminate-on-interruption, matching the other launchers.

    Persistent would relaunch after a reclaim and restart a long pass with nobody watching,
    and stop-on-interruption keeps billing the volume — the trap
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


def spot_price_now(ec2: Any, instance_type: str) -> tuple[float, str] | None:
    """The highest recent spot price for this type, and where it came from.

    The *highest* across availability zones on purpose. The launch does not pin an AZ, so
    which one it lands in is not ours to choose, and budgeting from the cheapest would
    under-reserve exactly when it matters.
    """
    try:
        history = ec2.describe_spot_price_history(
            InstanceTypes=[instance_type],
            ProductDescriptions=["Linux/UNIX"],
            MaxResults=24,
        )["SpotPriceHistory"]
    except Exception:
        return None
    prices = [(float(h["SpotPrice"]), h["AvailabilityZone"]) for h in history]
    if not prices:
        return None
    price, zone = max(prices)
    return price, f"spot, highest of {len(prices)} recent quotes (worst: {zone})"


def budget_window_minutes(max_spend_usd: float, price_per_hour: float) -> int:
    """How many minutes of this instance the ceiling buys."""
    if price_per_hour <= 0:
        raise SystemExit("a price per hour of zero or less cannot be budgeted against")
    return int(max_spend_usd / price_per_hour * 60)


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


#: What the search stage needs that it cannot rebuild on the instance, tarred and staged to
#: object storage beside the payload.
#:
#: The reference database is the case that decides this. Rebuilding it there would mean 103
#: unauthenticated RCSB fetches and a `gemmi` cut of every one of them, on a machine nobody can
#: reach, inside a window the budget caps — three new ways to lose a launch in service of
#: reproducing a 141-structure database that is a few megabytes and already has a `run.json`
#: pinning how it was built. The two artefacts come along because the shard records which
#: reference set and which alignment mode produced it, and both are read from these files.
INPUTS = (
    "artifacts/a2-2/reference/fold-universe.json",
    "artifacts/a2-2/reference/run.json",
    "artifacts/a2-2/calibration/threshold.json",
    "artifacts/a2-2/calibration/run.json",
)


def build_inputs(root: Path, refdb_dir: Path) -> bytes:
    """Tar the search stage's inputs: the two artefacts and the built reference database.

    Refuses rather than shipping a partial bundle. An instance that starts the search with no
    reference database dies after the ProstT5 download — about ten minutes in — and the refusal
    here costs nothing.
    """
    missing = [rel for rel in INPUTS if not (root / rel).exists()]
    if missing:
        raise SystemExit(
            f"the search stage's inputs are missing: {missing}. Run "
            "tools/build_fold_reference.py and tools/calibrate_folds.py first — the instance "
            "cannot produce either, and a shard written without them records no reference set."
        )
    if not refdb_dir.is_dir() or not any(refdb_dir.iterdir()):
        raise SystemExit(
            f"no reference database at {refdb_dir}. Build it with:\n"
            "  pixi run -e foldseek foldseek createdb "
            "/tmp/amazebio-a2-2/reference-structures /tmp/amazebio-a2-2/refdb/ref"
        )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in INPUTS:
            tar.add(root / rel, arcname=rel)
        for path in sorted(refdb_dir.iterdir()):
            if path.is_file():
                tar.add(path, arcname=f"refdb/{path.name}")
    return buf.getvalue()


def _guarded_run(label: str, command: str) -> str:
    """Wrap the run so that **every** exit path reaches `die`.

    This is the bug the first A2.2 smoke launch found, and it is the one AGENTS.md already
    records as having cost two launches and most of a day. The previous shape was
    `( <command> ; echo "exited $?" )`, with a comment asserting that a tool failure would fall
    through to `die "run complete" 0`. It does not. Under `set -euo pipefail` the failing command
    aborts the subshell *before* the echo, the non-zero status propagates to the parent, and
    `set -e` kills the script — so `die` never runs, the cloud-init log is never uploaded, and
    `shutdown -c; shutdown -h now` never happens. Measured 2026-10-19: the instance failed 77
    seconds in and then sat idle inside its 25-minute window, which from outside — no artefact,
    process gone, status checks `ok` — is indistinguishable from a long run still working. On the
    24.7-hour pass that would have burned the whole window and the budget with it.

    So the status is captured explicitly with `set -e` lifted around the call only, reported, and
    then routed through `die` with the tool's own exit code. A successful run falls through to
    the caller's `die "run complete" 0`, which uploads the log either way.
    """
    return (
        "set +e\n"
        f"{command}\n"
        "rc=$?\n"
        "set -e\n"
        f'echo "=== {label} exited $rc ==="\n'
        f'[ "$rc" -eq 0 ] || die "the {label} run failed (exit $rc)" "$rc"'
    )


#: The per-stage pieces of `USER_DATA`. Both stages stay reachable: `throughput` produced D-164's
#: cited speedup measurement and deleting its launch path would leave that artefact unreproducible.
#: Where shards accumulate across launches: stable, and keyed by the params fingerprint so that
#: only shards searched under one geometry ever share a prefix. Separate from the per-launch
#: prefix on purpose — the launch prefix carries a timestamp, so resumption looking there would
#: find an empty destination every time and silently redo finished work.
SHARD_PREFIX = "corpora/results/a2-2/shards"


def shards_uri_for(bucket: str, params: str) -> str:
    return f"s3://{bucket}/{SHARD_PREFIX}/{params}"


def stage_blocks(stage: str, *, bucket: str, prefix: str, region: str, **kw: Any) -> dict[str, str]:
    if stage == "throughput":
        return {
            "stage": "3di throughput",
            "smoke_tool": "tools/fold_throughput.py",
            "inputs_block": "",
            "run_block": _guarded_run(
                "throughput",
                "pixi run -e dev python tools/fold_throughput.py \\\n"
                '    --foldseek "$FOLDSEEK" \\\n'
                "    --prostt5-model /opt/amazebio/prostt5 \\\n"
                "    --outdir /opt/amazebio/out --workdir /opt/amazebio/work \\\n"
                f"    --devices {kw['devices']} --ladder {kw['ladder']} "
                f"--cpu-ladder {kw['cpu_ladder']} \\\n"
                f"    --threads {kw['threads']} \\\n"
                '    --s3-uri "$AMAZEBIO_S3_URI" --upload-results \\\n'
                f"    --allow-dirty --code-commit {kw['commit']}",
            ),
        }
    if stage == "search":
        caps = ""
        if kw.get("max_records"):
            caps += f" --max-records {kw['max_records']}"
        if kw.get("band"):
            caps += f" --band {kw['band']}"
        if kw.get("max_shards") is not None:
            caps += f" --max-shards {kw['max_shards']}"
        for release in kw.get("releases") or ():
            caps += f" --release {release}"
        return {
            "stage": "fold search",
            "smoke_tool": "tools/detect_folds.py",
            "inputs_block": (
                f'aws s3 cp "s3://{bucket}/{prefix}/inputs.tar.gz" inputs.tar.gz '
                f'--region {region} || die "inputs fetch failed"\n'
                'tar xzf inputs.tar.gz || die "inputs tarball is corrupt"\n'
                "test -f refdb/ref_ca || die "
                '"the reference database has no C-alpha file; the search cannot run"'
            ),
            "run_block": _guarded_run(
                "search",
                "pixi run -e dev python tools/detect_folds.py --search \\\n"
                '    --foldseek "$FOLDSEEK" \\\n'
                "    --prostt5-model /opt/amazebio/prostt5 \\\n"
                "    --refdb /opt/amazebio/refdb/ref \\\n"
                "    --reference artifacts/a2-2/reference \\\n"
                "    --calibration artifacts/a2-2/calibration \\\n"
                "    --shards /opt/amazebio/shards --workdir /opt/amazebio/work \\\n"
                f'    --shards-uri "{kw["shards_uri"]}" \\\n'
                f"    --threads {kw['threads']} --gpu{caps} \\\n"
                '    --s3-uri "$AMAZEBIO_S3_URI" \\\n'
                f"    --code-commit {kw['commit']}",
            ),
        }
    raise SystemExit(f"unknown stage {stage!r}")


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument(
        "--stage",
        choices=("search", "throughput"),
        default="search",
        help="search runs A2.2's pass; throughput re-runs D-164's speedup measurement",
    )
    ap.add_argument("--max-records", type=int, default=0, help="smoke test: cap per shard")
    ap.add_argument("--band", default=None, help="smoke test: override the band as LO:HI")
    ap.add_argument("--max-shards", type=int, default=None, help="stop after this many shards")
    ap.add_argument(
        "--release",
        action="append",
        help="restrict the search to these release keys; repeatable. Without it every release "
        "the pre-registered depth names is searched.",
    )
    ap.add_argument(
        "--refdb-dir",
        type=Path,
        default=Path("/tmp/amazebio-a2-2/refdb"),
        help="the built foldseek reference database, shipped to the instance",
    )
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
    ap.add_argument(
        "--max-spend-usd",
        type=float,
        default=DEFAULT_MAX_SPEND_USD,
        help="hard spending ceiling for this launch. The shutdown timer is capped at what this "
        "buys at the live price, because the timer is the only spend control available once "
        "the instance is running.",
    )
    ap.add_argument(
        "--spot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="spot by default: it is roughly a third off, and the run is resumable and "
        "restartable, so a reclaim costs time rather than the result.",
    )
    ap.add_argument(
        "--price-per-hour",
        type=float,
        default=None,
        help="override the price used for budgeting. Required with --no-spot, because "
        "pricing:GetProducts is denied in this account and this tool will not budget against "
        "a price it cannot look up.",
    )
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
    kind = "throughput" if args.stage == "throughput" else "search"
    prefix = args.prefix or f"{RESULT_PREFIX}/{kind}/{stamp}-{commit[:12]}"
    code_key = f"{prefix}/code.tar.gz"

    s3 = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    ec2 = boto3.client(
        "ec2", region_name=REGION, endpoint_url=f"https://ec2.{REGION}.amazonaws.com"
    )
    ssm = boto3.client(
        "ssm", region_name=REGION, endpoint_url=f"https://ssm.{REGION}.amazonaws.com"
    )

    # The budget, resolved before anything is uploaded or launched. The timer baked into
    # UserData is the only spend control that exists after launch, so the ceiling has to
    # become that timer here or it is not a ceiling at all.
    if args.price_per_hour is not None:
        price, price_source = args.price_per_hour, "given on the command line"
    elif args.spot:
        quoted = spot_price_now(ec2, args.instance_type)
        if quoted is None:
            raise SystemExit(
                "could not read a spot price for budgeting. Pass --price-per-hour to say what "
                "to budget against, rather than launching with no ceiling."
            )
        price, price_source = quoted
    else:
        raise SystemExit(
            "with --no-spot there is no price to read: pricing:GetProducts is denied in this "
            "account, so pass --price-per-hour explicitly. Budgeting against a remembered "
            "on-demand rate is how a ceiling silently becomes a guess."
        )

    affordable = budget_window_minutes(args.max_spend_usd, price)
    hard_stop = min(args.hard_stop_minutes, affordable)
    if hard_stop < MIN_USEFUL_WINDOW_MINUTES:
        raise SystemExit(
            f"${args.max_spend_usd:.2f} at ${price:.4f}/h buys {affordable} minutes, under the "
            f"{MIN_USEFUL_WINDOW_MINUTES} this run needs to get past setup. Raise the ceiling "
            "or pick a cheaper instance type; do not launch a window that cannot finish."
        )
    print(
        f"=== budget: ${args.max_spend_usd:.2f} at ${price:.4f}/h ({price_source}) "
        f"= {affordable} min; hard stop {hard_stop} min "
        f"(~${hard_stop / 60 * price:.2f} worst case)",
        flush=True,
    )

    from amazebio.folds import PROSTT5, params_fingerprint, sha256_of

    universe_path = root / "artifacts" / "a2-2" / "reference" / "fold-universe.json"
    if args.stage == "search" and not universe_path.exists():
        raise SystemExit(
            f"{universe_path} is missing; run tools/build_fold_reference.py first. The shard "
            "prefix is derived from it, so without it shards cannot be placed where a later "
            "launch would find them."
        )
    params = params_fingerprint(sha256_of(universe_path)) if universe_path.exists() else "none"
    shards_uri = shards_uri_for(bucket, params)
    if args.stage == "search":
        print(f"=== shards accumulate at {shards_uri}", flush=True)

    blocks = stage_blocks(
        args.stage,
        bucket=bucket,
        prefix=prefix,
        region=REGION,
        commit=commit,
        devices=args.devices,
        ladder=args.ladder,
        cpu_ladder=args.cpu_ladder,
        threads=args.threads,
        max_records=args.max_records,
        band=args.band,
        max_shards=args.max_shards,
        releases=args.release,
        shards_uri=shards_uri,
    )

    user_data = render_user_data(
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        weights_key=PROSTT5.key,
        weights_name=PROSTT5.name,
        weights_sha256=PROSTT5.sha256,
        region=REGION,
        commit=commit,
        devices=args.devices,
        ladder=args.ladder,
        cpu_ladder=args.cpu_ladder,
        threads=args.threads,
        **blocks,
        hard_stop_minutes=hard_stop,
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
    market = market_options(args.spot)
    if market is not None:
        launch["InstanceMarketOptions"] = market

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
    if args.stage == "search":
        body = build_inputs(root, args.refdb_dir)
        key = f"{prefix}/inputs.tar.gz"
        print(f"=== uploading inputs to s3://{bucket}/{key} ({len(body) / 1e6:.1f} MB)", flush=True)
        s3.put_object(Bucket=bucket, Key=key, Body=body)

    # A launch refusal is translated before it is raised. This tool had its own local copies of
    # the spot helpers and none of them classified `MaxSpotInstanceCountExceeded`, so the first
    # attempt at A2.2's smoke launch surfaced a raw botocore traceback — the same misreading
    # AGENTS.md records for a bare `UnauthorizedOperation`, which cost a round trip.
    try:
        instance = ec2.run_instances(**launch)["Instances"][0]
    except Exception as exc:
        from amazebio.ec2 import spot_refusal

        explained = spot_refusal(str(exc))
        if explained:
            raise SystemExit(explained) from exc
        raise
    iid = instance["InstanceId"]
    print(
        f"=== launched {iid} ({args.instance_type}{' spot' if args.spot else ''}, "
        f"ami {ami}, hard stop +{hard_stop}m)\n"
        f"=== results: s3://{bucket}/{prefix}",
        flush=True,
    )

    observed_end = False
    try:
        rc = watch(ec2, s3, iid, bucket, prefix, args, hard_stop)
        observed_end = True
        return rc
    finally:
        # Also, not instead: a UserData that fails before its own `shutdown` would otherwise
        # leave this running indefinitely.
        #
        # But **not** when the watcher itself died and the instance is healthy. A2.4 learned this
        # and `ec2_proviruses.py` has carried the guard since; this launcher did not, and on
        # 2026-10-19 a `timeout` sent SIGTERM to this process 117 minutes into a 3-hour window
        # while the instance was 112 minutes into a 3Di prediction. The terminate happened not to
        # fire, which was luck rather than design — it would have destroyed the whole shard,
        # because there is no checkpoint inside one.
        #
        # Leaving a healthy instance alone is safe here precisely because UserData arms
        # `shutdown -h +N` before anything can fail and the launch sets
        # InstanceInitiatedShutdownBehavior=terminate: the instance ends itself on time with no
        # watcher at all. That is what "both, not either" is for.
        state = instance_state(ec2, iid)
        if not observed_end and state in ("pending", "running"):
            print(
                f"=== watcher exited without seeing {iid} finish, and it is {state}.\n"
                f"=== LEAVING IT RUNNING: its own shutdown timer ends it within {hard_stop}m of\n"
                "=== boot, and terminating a healthy instance here would throw away the shard\n"
                f"=== it is working on. Re-attach with --prefix {prefix}, or terminate by hand.",
                flush=True,
            )
        else:
            # Nothing in this block returns a value: a `return` inside `finally` swallows
            # whatever took us out of `watch`, including the SystemExit or KeyboardInterrupt
            # that is the likeliest reason the watcher stopped early.
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"=== terminated {iid}", flush=True)
            except Exception as exc:
                print(f"=== TERMINATE FAILED for {iid}: {type(exc).__name__} — check the console")


def watch(ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any, hard_stop: int) -> int:
    """Poll the heartbeat and the console until the artefact lands or the instance goes.

    `GetConsoleOutput` is allowed and best-effort — empty for the first minute or so, and it
    cannot distinguish a dead process from a quiet one, which is exactly the misreading that
    cost four hours on 2026-10-16. The heartbeat is the channel that carries meaning; the
    console is for the boot failures that happen before the heartbeat exists.
    """
    deadline = time.monotonic() + hard_stop * 60 + 300
    searching = args.stage == "search"
    # The search has no single terminal artefact: it publishes one shard per finished unit so a
    # reclaim keeps what ran, which is the whole point of the shard split. So the watcher reports
    # shards as they appear and lets the instance's own exit end the wait.
    result_key = f"{prefix}/{'search-progress.json' if searching else 'throughput.json'}"
    beat_key = f"{prefix}/{'search-progress.json' if searching else 'throughput-progress.json'}"
    seen_stage = None
    seen_shards: set[str] = set()
    while time.monotonic() < deadline:
        time.sleep(args.poll_seconds)
        if searching:
            try:
                page = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/")
                for obj in page.get("Contents", []):
                    name = obj["Key"].rsplit("/", 1)[-1]
                    if name.endswith(".json") and "--" in name and name not in seen_shards:
                        seen_shards.add(name)
                        print(f"=== shard landed: {name} ({obj['Size']} bytes)", flush=True)
            except Exception:
                pass
        else:
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
            beat = json.loads(s3.get_object(Bucket=bucket, Key=beat_key)["Body"].read())
            stage = (
                beat.get("stage"),
                beat.get("shard"),
                len(beat.get("points", {}).get("gpu", []) or []),
            )
            if stage != seen_stage:
                seen_stage = stage
                print(f"    heartbeat: {beat.get('stage')} {beat.get('written_at')}", flush=True)
        except Exception:
            pass
        state = instance_state(ec2, iid)
        if state in ("shutting-down", "terminated", "stopped"):
            if searching and seen_shards:
                print(
                    f"=== instance {state}; {len(seen_shards)} shard(s) published and kept",
                    flush=True,
                )
                return 0
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

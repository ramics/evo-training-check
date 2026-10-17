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

#: Per measurement, because the two want opposite trades. The curve holds the full seed set
#: as query and needs a small target for its grid points to complete at all; the cap
#: measurement subsamples the query and needs a large target, since hits per seed is what the
#: cap truncates and it scales with the target.
SAMPLE_RATES = {"curve": 2000, "caps": 50}

#: Used when --hard-stop-minutes is not given. Not an argparse default, because a watcher
#: attaching to a running instance must be able to tell "I armed this" from "someone else
#: did": the timer is written into UserData at launch and ec2:ModifyInstanceAttribute is
#: denied, so no later process can change it or read it back.
DEFAULT_HARD_STOP_MINUTES = 400

#: Where each measurement's result lands, matching `esm3_calibrate.ARTEFACT_NAMES`. The
#: watcher polls this key, so a mismatch reads as a run that produced nothing.
RESULT_NAMES = {"curve": "calibration.json", "caps": "cap-measurement.json"}

#: Shipped through S3 rather than baked into UserData, which is capped at 16 KiB.
#: Shipped through S3 rather than baked into UserData, which is capped at 16 KiB.
#:
#: Every first-party module the shipped tools import, transitively. Keeping this by hand cost
#: two runs on 2026-10-16 and 2026-10-17: `similarity.py` and then `shardstore.py` were added
#: to `esm3_calibrate.py` and not here, so the instance died on an ImportError about half a
#: minute in. `tests/test_ec2_similarity.py` now derives the closure from the source and fails
#: if this list is short, because the instance is the one place where a missing import costs an
#: hour and a launch rather than a second.
PAYLOAD = (
    "src/amazebio/__init__.py",
    "src/amazebio/repro.py",
    "src/amazebio/uniref.py",
    "src/amazebio/seeds.py",
    "src/amazebio/similarity.py",
    "src/amazebio/shardstore.py",
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

# `die` exists because `shutdown -h now` does not work while that timer is pending: systemd
# already has a shutdown scheduled and the immediate one does not replace it. On 2026-10-16 a
# run whose script failed 31 seconds in therefore sat idle until the +240 minute timer fired,
# burning the whole window instead of dying at once — and looked from outside exactly like a
# wedged four-hour corpus pass. Cancel the schedule first, then go down, with fallbacks
# because this is the one path that must not fail.
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip unzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3`, and this project needs 3.12.
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

# The aligner, as the upstream static build of the pinned version. A checksum mismatch is
# fatal: running a different aligner than the one recorded would make every number here
# untraceable, which is worse than returning nothing.
curl -sSL -o mmseqs.tar.gz "{mmseqs_url}"
echo "{mmseqs_sha256}  mmseqs.tar.gz" | sha256sum -c - || {{
  die "mmseqs checksum mismatch; refusing to run a different aligner"
}}
tar xzf mmseqs.tar.gz
export PATH="/opt/amazebio/mmseqs/bin:$PATH"
mmseqs version

# The taxonomy, pinned and dated. Not staged in the corpus bucket on purpose: that bucket
# has no DeleteObject, and an 80 MB input that is already served by its publisher at a
# dated URL does not need to be made permanent.
curl -sSL -o taxdmp.zip "{taxdump_url}"
echo "{taxdump_sha256}  taxdmp.zip" | sha256sum -c - || {{
  die "taxdump checksum mismatch"
}}

# Import the tool before the pass rather than discovering a short payload after it. This is
# the check that would have turned two lost launches into two seconds.
"$PYBIN" -c "import sys; sys.path.insert(0,'src'); import tools.esm3_calibrate" 2>/dev/null \
  || "$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD is short"
import sys
sys.path.insert(0, "src")
import importlib.util
spec = importlib.util.spec_from_file_location("cal", "tools/esm3_calibrate.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("=== payload imports cleanly ===")
PRECHECK

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
( "$PYBIN" tools/esm3_calibrate.py \
    --release {release} --tier {tier} \
    --taxdump /opt/amazebio/taxdmp.zip \
    --outdir /opt/amazebio/out --workdir /mnt/work \
    --measure {measure} \
    --sample-rate {sample_rate} --buckets {buckets} --strict-buckets {strict_buckets} \
    --query-fractions {query_fractions} --shard-points {shard_points} \
    --cap-query-denominator {cap_query_denominator} \
    --cap-shard-points {cap_shard_points} --cap-fractions {cap_fractions} \
    {sample_flags} \
    --threads {threads} --workers {workers} --search-budget-seconds {budget} \
    --upload-results --allow-dirty --code-commit {commit} \
    --progress-seconds 300 ; echo "=== calibrate exited $? ===" )

echo "=== amazebio a1-6 calibration finished $(date -Is) ==="
die "run complete" 0
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
    # 2000, not the 50 the first run used. At rate 50 one shard was 334 M residues and the
    # full-query search against it had not finished in 61 minutes; at 2000 the whole sample
    # is 67 M residues, so every grid point can complete and the fit gets points instead of
    # one timeout.
    ap.add_argument("--sample-rate", type=int, default=None)
    ap.add_argument("--query-fractions", default="1000,100,10,1")
    ap.add_argument("--shard-points", default="1,2,4,8")
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
        default=None,
        help=f"a shutdown timer armed on the instance at boot, before anything that can "
        f"fail. Independent of the script reaching its own shutdown and of the launcher "
        f"surviving to run its terminate (default: {DEFAULT_HARD_STOP_MINUTES}). Has no "
        f"effect with --attach: the timer was armed by the launch, and ec2:"
        f"ModifyInstanceAttribute is denied, so no later process can change or read it",
    )
    ap.add_argument("--poll-seconds", type=float, default=120.0)
    ap.add_argument(
        "--attach",
        metavar="INSTANCE_ID",
        help="watch an instance that is already running instead of launching one, for "
        "picking a run back up after a watch window expired",
    )
    ap.add_argument(
        "--terminate-on-timeout",
        action="store_true",
        help="kill the instance when the watch window expires even if it is still "
        "working. Off by default: doing it unconditionally destroyed a healthy run once.",
    )
    ap.add_argument(
        "--stage-sample",
        action="store_true",
        help="stage the sample after the corpus pass so later runs skip it (D-122). The "
        "staging happens before the searches, so a run cut short still leaves the sample",
    )
    ap.add_argument(
        "--sample-from",
        metavar="S3_URI",
        help="load a staged sample instead of running the ~52-minute corpus pass (D-123)",
    )
    ap.add_argument(
        "--measure",
        choices=("curve", "caps"),
        default="curve",
        help="what the instance measures. `caps` prices the hit cap where it binds and "
        "relaxed coverage against D-109's three-cell fallback (default: %(default)s)",
    )
    # The cap measurement wants the opposite trade from the cost curve: a *larger* target
    # against a small query, because hits per seed — the thing the cap truncates — scales
    # with the target and is a per-seed property the query subsample does not bias. Rate 50
    # over UniRef100 is about 2 G residues against rate 2000's 67 M, which is the difference
    # between a cap that can be made to bind and one that cannot.
    ap.add_argument("--cap-query-denominator", type=int, default=100)
    ap.add_argument("--cap-shard-points", default="1,2")
    ap.add_argument("--cap-fractions", default="0.5,0.2")
    ap.add_argument("--dry-run", action="store_true", help="authorize only, launch nothing")
    ap.add_argument(
        "--spot",
        action="store_true",
        help="request a spot instance. D-104's $240-450 and D-109's $26 are both spot "
        "figures, so the authoritative passes need this; the price is that the instance "
        "can be reclaimed mid-run",
    )
    args = ap.parse_args(argv)
    if args.sample_rate is None:
        args.sample_rate = SAMPLE_RATES[args.measure]

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

    if args.attach:
        print(f"attaching to {args.attach} ({_state(ec2, args.attach)})")
        return _run_and_collect(ec2, s3, args.attach, bucket, prefix, args)

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

    code_key = f"{prefix}/code/a1-6-{args.measure}-{int(time.time())}.tar.gz"
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
        measure=args.measure,
        cap_query_denominator=args.cap_query_denominator,
        cap_shard_points=args.cap_shard_points,
        cap_fractions=args.cap_fractions,
        sample_flags=_sample_flags(args),
        sample_rate=args.sample_rate,
        buckets=args.buckets,
        strict_buckets=args.strict_buckets,
        query_fractions=args.query_fractions,
        shard_points=args.shard_points,
        threads=args.threads,
        workers=args.workers,
        budget=args.search_budget_seconds,
        hard_stop_minutes=args.hard_stop_minutes or DEFAULT_HARD_STOP_MINUTES,
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
        {"Key": "Name", "Value": f"amazebio-a1-6-{args.measure}"},
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
            print("dry run:", type(exc).__name__, str(exc)[:200])
        return 0

    try:
        instance = ec2.run_instances(**launch)["Instances"][0]
    except Exception as exc:
        message = spot_refusal(str(exc)) if args.spot else None
        if message:
            raise SystemExit(message) from exc
        raise
    iid = instance["InstanceId"]
    market = "spot" if args.spot else "on-demand"
    print(f"launched {iid} ({args.instance_type}, {market}, {args.volume_size} GB gp3)")

    return _run_and_collect(ec2, s3, iid, bucket, prefix, args)


def _run_and_collect(ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any) -> int:
    """Watch, then terminate — unless the watch window simply ran out on a healthy run.

    The first version of this terminated in a bare `finally`, which is what AGENTS.md's
    "both, not either" asks for and is wrong in exactly one case. On 2026-10-15 a run
    whose corpus pass had finished was killed at 115 minutes because that was the watch
    window, not because anything had failed: the searches were still going, and
    `StateTransitionReason` read "User initiated". Fifty-three minutes of corpus pass and
    the whole search curve went with it.

    So the rule is narrower than "always terminate". Terminate when the run finished, when
    it failed, or when the instance is already on its way down. When the window expires on
    an instance that is still running, leave it: the shutdown timer armed in `UserData`
    before anything that can fail is what prevents an orphan, and it does that whether or
    not this process is alive to watch. Reattach with `--attach`.
    """
    outcome = 1
    timed_out = False
    try:
        outcome, timed_out = _watch(ec2, s3, iid, bucket, prefix, args)
    finally:
        state = _state(ec2, iid)
        if timed_out and state == "running" and not args.terminate_on_timeout:
            print(
                f"\nwatch window expired and {iid} is still running — leaving it alone.\n"
                f"  {_shutdown_bound(args)}\n"
                f"  reattach:  python3 tools/ec2_similarity.py --attach {iid}"
            )
        else:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminate requested for {iid}")
            except Exception as exc:
                print(f"terminate: {type(exc).__name__}: {str(exc)[:120]}")
    return outcome


def _shutdown_bound(args: Any) -> str:
    """What bounds the instance once this watcher gives up — without inventing a number.

    The first version of this printed `args.hard_stop_minutes` unconditionally, which is a
    figure the launching process knows and an attaching one does not. On 2026-10-16 a watcher
    attached with `--attach` and reported a 400-minute bound on an instance launched with 260,
    which is exactly the sort of line someone later reads as fact when deciding whether an
    instance has already gone.
    """
    if args.hard_stop_minutes is not None:
        return (
            f"the instance's own shutdown timer ({args.hard_stop_minutes} min from boot, "
            f"armed by this launch) bounds it."
        )
    return (
        "the instance's own shutdown timer, armed at launch, bounds it — this process did "
        "not set it and cannot read it back, so check the launch that created the instance "
        "for the figure."
    )


def _watch(ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any) -> tuple[int, bool]:
    """Poll the result key and the console. Returns (exit code, whether time ran out)."""
    deadline = time.monotonic() + args.timeout_minutes * 60
    timed_out = True
    name = RESULT_NAMES[args.measure]
    key = f"{prefix}/results/a1-6/{name}"
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
                timed_out = False
                break
        except Exception:
            pass

        state = _state(ec2, iid)
        if state in ("shutting-down", "terminated", "stopped"):
            print(f"\n=== instance {state} ===")
            timed_out = False
            break

    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        out = Path("artifacts/a1-6")
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(body)
        print(f"collected s3://{bucket}/{key} -> artifacts/a1-6/{name}")
        return 0, timed_out
    except Exception as exc:
        print(f"no result at s3://{bucket}/{key}: {type(exc).__name__}")
        # A spot reclaim and a broken run both end with no result key, and they need
        # different responses: the first is a re-run of the same code, the second is not.
        # EC2 says which in StateTransitionReason, so read it rather than guessing.
        reason = _transition_reason(ec2, iid)
        if "Server.SpotInstanceTermination" in reason or "Server.Capacity" in reason:
            print(
                f"  {iid} was reclaimed by EC2, not failed: {reason!r}.\n"
                "  the run is interrupted, not refuted — re-run it. Partial results that "
                "reached S3 before the reclaim are still there."
            )
            return 2, timed_out
        if reason:
            print(f"  StateTransitionReason: {reason!r}")
        return 1, timed_out


def _summarise(done: list[dict[str, Any]]) -> str:
    return "  ".join(
        f"{d['reading'][:4]}/{d['shards']}: {d['search_core_seconds']:.0f} core-s"
        f" @ {d['residues'] / 1e9:.2f} Gres"
        for d in done
    )


def _sample_flags(args: Any) -> str:
    """The staging flags for `UserData`, or nothing.

    Built here rather than interpolated inline so that the mutually exclusive pair cannot both
    reach the instance: there is one shot at `UserData` and no way to ask the instance what it
    thought it was doing.
    """
    if args.stage_sample and args.sample_from:
        raise SystemExit("--stage-sample builds a sample; --sample-from loads one. Pick one.")
    if args.sample_from:
        if not args.sample_from.startswith("s3://"):
            raise SystemExit("--sample-from takes an s3:// uri pointing at a staged manifest")
        return f"--sample-from {args.sample_from}"
    return "--stage-sample" if args.stage_sample else ""


def spot_refusal(text: str) -> str | None:
    """Why a spot launch was refused, in terms the next person can act on. `None` if unclear.

    Both refusals this distinguishes mean nothing launched and nothing was billed, and they
    need opposite responses — which is why they are not one message.

    *The service-linked role.* Measured 2026-10-16, and no dry run finds it: a spot request
    needs `AWSServiceRoleForEC2Spot`, which EC2 creates on the caller's behalf on first use
    via `iam:CreateServiceLinkedRole`. AGENTS.md records that `iam:*` is denied in this
    account, so spot is not a flag that can be turned on from here. It needs one IAM action
    from someone who has that permission, and until then every spot-priced figure in this
    task is a price we cannot pay.

    *Capacity.* The ordinary spot refusal: the same request may succeed later, or on another
    permitted instance type.
    """
    if "ServiceLinkedRoleCreationNotPermitted" in text:
        return (
            f"spot is unavailable in this account: {text[:160]}\n"
            "  the EC2 Spot service-linked role does not exist and iam:* is denied, so it "
            "cannot be created from here.\n"
            "  nothing launched, nothing billed. Either someone with IAM permissions creates "
            "AWSServiceRoleForEC2Spot once, or the run goes on demand without --spot at "
            "roughly 3-4x the price.\n"
            "  that price difference is not a detail: D-104's $240-450 and D-109's $26 are "
            "spot figures."
        )
    if "Capacity" in text or "capacity" in text:
        return (
            f"spot capacity refused: {text[:200]}\n"
            "  nothing launched and nothing billed. Retry, try another permitted instance "
            "type, or run on demand without --spot at the higher price."
        )
    return None


def market_options(spot: bool) -> dict[str, Any] | None:
    """What to ask EC2 for, market-wise. `None` means say nothing and get on demand.

    Three choices, each of which has a cheaper-looking alternative that is wrong here:

    *One-time, not persistent.* A reclaim on a persistent request re-launches the instance,
    which restarts a multi-hour pass with nobody watching and bills for it. The pass is
    re-run deliberately or not at all.

    *Interruption behaviour terminate, not stop or hibernate.* Stop keeps billing the
    volume, which is the same trap `InstanceInitiatedShutdownBehavior` exists to avoid, and
    it leaves a resource to forget. That flag stays set independently: it governs the
    instance's own shutdown, this one governs EC2's reclaim, and both have to say terminate.

    *No maximum price.* Omitting it caps the bid at the on-demand price. The saving this
    task wants comes from spot being cheaper than on demand, not from bidding under the
    going rate — a bid below it converts a run that would have cost money into a launch that
    silently never happens, and nobody is watching to notice.
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


def _transition_reason(ec2: Any, iid: str) -> str:
    """Why EC2 says the instance changed state. Empty when it does not say."""
    try:
        inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
        return str(inst.get("StateTransitionReason", ""))
    except Exception:
        return ""


def _state(ec2: Any, iid: str) -> str:
    try:
        return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
            "State"
        ]["Name"]
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())

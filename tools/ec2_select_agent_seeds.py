#!/usr/bin/env python3
"""Run A1.8's select-agent seed pass in-region on EC2.

The pass reads UniRef100 2023_02 in full — 118.68 GB of staged object, 133.49 GB
decompressed — and that is the test AGENTS.md sets for launching anything: a full pass over
the staged corpora is free inside `us-east-1` and metered outside it. About an hour, and
well under a dollar.

`tools/ec2_similarity.py` is the worked example and its hard-won parts are imported from it
rather than copied: the spot refusal reading, the market options, the commit discovery, the
state and transition-reason queries. What is different here is the payload and one check.

**The payload carries data, and the import-closure test cannot see it.** A1.6's launcher ships
modules, so deriving the first-party import closure from the source catches a short payload —
which is what `tests/test_ec2_similarity.py` does, after two launches died on an `ImportError`
half a minute in. This pass also needs four *data* files: the three pinned CFR captures and the
curated reading table (D-137). Nothing imports them, so no closure derivation will ever notice
them missing, and the failure mode is identical — a dead instance a minute in, an hour of
corpus reading wasted. Two things answer that. The payload's data half is derived from the
tool's own `SECTION_FILES` and default mapping path rather than hand-listed, with a test; and
`UserData` runs `--check-inputs` on the instance *before* the pass, which resolves the taxa and
verifies every digest in about a second.

**No aligner here.** This pass scores nothing — it builds the query set. So, unlike A1.6's
calibration, there is no mmseqs to fetch and no checksum gate on it; the only pinned download
is the dated taxonomy.

Everything else follows the rules AGENTS.md records as having been learned the hard way:
`InstanceInitiatedShutdownBehavior=terminate` at launch because `ModifyInstanceAttribute` is
denied afterwards; a boot-armed `shutdown -h +N` dead man's switch; a `die` helper that runs
`shutdown -c` first, because an immediate shutdown does nothing while that timer is pending;
a terminate in the launcher's own `finally`; `python3.12` by name because Amazon Linux 2023
ships 3.9 as `python3`; the commit passed in because the instance has no checkout; and results
coming back through object storage because there is no shell, no SSH and no SSM.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from amazebio import seeds  # noqa: E402


def _load_similarity_launcher() -> Any:
    """Import A1.6's launcher for its hard-won helpers rather than copying them."""
    path = ROOT / "tools" / "ec2_similarity.py"
    spec = importlib.util.spec_from_file_location("ec2_similarity_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sim = _load_similarity_launcher()

#: Modules the shipped tool imports. Derived and tested, never hand-trusted.
PAYLOAD_MODULES = (
    "src/amazebio/__init__.py",
    "src/amazebio/repro.py",
    "src/amazebio/uniref.py",
    "src/amazebio/seeds.py",
    "src/amazebio/selectagents.py",
    "src/amazebio/similarity.py",
    "tools/select_agent_seeds.py",
)


def payload_data_files() -> tuple[str, ...]:
    """The data files the pass needs, asked of the tool rather than restated here.

    Hand-listing these is the trap this closes: they are not imports, so the closure
    derivation that guards `PAYLOAD_MODULES` is blind to them, and a missing one kills the
    instance exactly like a short module list. The tool owns the list because the tool is what
    reads them.
    """
    spec = importlib.util.spec_from_file_location(
        "select_agent_seeds_for_payload", ROOT / "tools" / "select_agent_seeds.py"
    )
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tuple(tool.required_data_files())


USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a1-8 select-agent seed pass starting $(date -Is) ==="

# Armed before anything that can fail. The launcher's own terminate in its `finally` covers a
# launcher that lives to run it; this covers the case it cannot — the session ending, the
# watcher being killed. InstanceInitiatedShutdownBehavior=terminate at launch is what makes
# this a terminate rather than a stop that keeps billing the volume.
shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` does nothing while that timer is pending: systemd already has a shutdown
# scheduled and the immediate one does not replace it. A script that fails in thirty seconds
# would otherwise sit idle until the timer fires, which from outside is indistinguishable from
# a long pass still working. Cancel first, then go down, with fallbacks.
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip unzip >/dev/null

# Amazon Linux 2023 ships python3.9 as `python3`; this project needs 3.12.
PYBIN=""
for cand in python3.12 python3.11; do
  dnf install -y "$cand" "$cand-pip" >/dev/null 2>&1 || true
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then die "no python 3.11+ available; nothing to run"; fi
echo "=== interpreter: $PYBIN ($($PYBIN -V)) ==="
"$PYBIN" -m pip install --quiet boto3

mkdir -p /opt/amazebio && cd /opt/amazebio
aws s3 cp "s3://{bucket}/{code_key}" code.tar.gz --region {region}
tar xzf code.tar.gz

# The taxonomy, pinned and dated. Not staged in the corpus bucket on purpose: that bucket has
# no DeleteObject, and a 60 MB input already served by its publisher at a dated URL does not
# need to be made permanent.
curl -sSL -o taxdmp.zip "{taxdump_url}"
echo "{taxdump_sha256}  taxdmp.zip" | sha256sum -c - || die "taxdump checksum mismatch"

# Import the tool before the pass rather than discovering a short payload after it.
"$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD_MODULES is short"
import sys, importlib.util
sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("sas", "tools/select_agent_seeds.py")
mod = importlib.util.module_from_spec(spec)
# Registered before execution: `dataclasses` resolves annotations through
# `sys.modules[cls.__module__]`, so a module loaded by spec alone dies on its first
# dataclass. This tool has none today, which is luck rather than design.
sys.modules["sas"] = mod
spec.loader.exec_module(mod)
print("=== payload imports cleanly ===")
PRECHECK

# Resolve the taxa and verify every pinned digest before reading a byte of corpus. The data
# files are not imports, so the check above cannot see them missing; this one can, and it
# costs a second against the hour the pass is about to spend.
"$PYBIN" tools/select_agent_seeds.py \
  --taxdump /opt/amazebio/taxdmp.zip --check-inputs \
  || die "inputs do not resolve; the payload's data files are short or a digest moved"

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"
# `set -e` plus a subshell swallows the failure path: the subshell aborts before its
# trailing echo, the script ends, and `die` never runs, so the instance idles until the
# boot timer instead of shutting down. Seen for real on the release count, 2026-10-18.
set +e
"$PYBIN" tools/select_agent_seeds.py \
  --release {release} --tier {tier} \
  --taxdump /opt/amazebio/taxdmp.zip \
  --outdir /opt/amazebio/out \
  {reading_flags} \
  --workers {workers} \
  --upload-results --allow-dirty --code-commit {commit} \
  --progress-seconds 120
rc=$?
set -e
echo "=== seed pass exited $rc ==="
if [ "$rc" -ne 0 ]; then die "seed pass failed with $rc" "$rc"; fi

echo "=== amazebio a1-8 select-agent seed pass finished $(date -Is) ==="
die "run complete" 0
"""


def build_payload(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in (*PAYLOAD_MODULES, *payload_data_files()):
            tar.add(root / rel, arcname=rel)
    return buf.getvalue()


def reading_flags(args: argparse.Namespace) -> str:
    flags = []
    if args.toxin_producers:
        flags.append("--toxin-producers")
    if args.alternatives:
        flags.append("--alternatives")
    return " ".join(flags)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--instance-type", default="r6i.2xlarge")
    ap.add_argument("--profile", default="AmazebioStager")
    ap.add_argument("--s3-uri", required=True)
    ap.add_argument("--release", default="2023_02")
    ap.add_argument("--tier", default="uniref100")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--toxin-producers", action="store_true")
    ap.add_argument("--alternatives", action="store_true")
    ap.add_argument(
        "--volume-size",
        type=int,
        default=30,
        help="the corpus is streamed rather than stored, so this holds only the taxonomy and "
        "the seed set (default: %(default)s GB; policy caps volumes at 200)",
    )
    ap.add_argument(
        "--hard-stop-minutes",
        type=int,
        default=180,
        help="the boot-armed dead man's switch. The pass is about an hour "
        "(default: %(default)s)",
    )
    ap.add_argument("--spot", action="store_true", default=True)
    ap.add_argument("--on-demand", dest="spot", action="store_false")
    ap.add_argument("--owner", default="claude")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--print-user-data",
        action="store_true",
        help="print the script the instance would run and exit, which is the only way to "
        "read it before it is the only thing that can be read",
    )
    ap.add_argument("--watch-seconds", type=float, default=120.0)
    ap.add_argument("--max-watch-minutes", type=float, default=150.0)
    args = ap.parse_args(argv)

    if args.volume_size > 200:
        raise SystemExit("policy caps volumes at 200 GB in gp3/gp2")

    if not args.s3_uri.startswith("s3://"):
        raise SystemExit("--s3-uri must be an s3:// uri")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    if not bucket:
        raise SystemExit("--s3-uri must name a bucket")
    prefix = prefix.strip("/")

    commit, dirty = _sim._git_head(ROOT)
    if dirty and not args.print_user_data:
        raise SystemExit(
            "refusing to launch from a dirty tree: the instance has no checkout, so the "
            "commit is the only thing tying a result to the code that produced it"
        )

    code_key = f"{prefix}/code/a1-8-seeds-{commit[:12]}.tar.gz"
    user_data = USER_DATA.format(
        hard_stop_minutes=args.hard_stop_minutes,
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=args.region,
        taxdump_url=seeds.TAXDUMP_2023_04.url,
        taxdump_sha256=seeds.TAXDUMP_2023_04.sha256,
        release=args.release,
        tier=args.tier,
        reading_flags=reading_flags(args),
        workers=args.workers,
        commit=commit,
    )

    if args.print_user_data:
        print(user_data)
        return 0

    import boto3

    ec2 = boto3.client("ec2", region_name=args.region)
    s3 = boto3.client(
        "s3", region_name=args.region, endpoint_url="https://s3.us-east-1.amazonaws.com"
    )

    # Built either way, because it is the cheapest check that every payload file exists, but
    # uploaded only for a real launch: a dry run must not write, and this one did until it was
    # run — leaving an object behind in a bucket with no DeleteObject.
    blob = build_payload(ROOT)
    print(f"payload {len(blob):,} bytes")

    request: dict[str, Any] = dict(
        ImageId=_sim.latest_al2023(ec2) if hasattr(_sim, "latest_al2023") else _al2023(ec2),
        InstanceType=args.instance_type,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={"Name": args.profile},
        UserData=user_data,
        InstanceInitiatedShutdownBehavior="terminate",
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {"VolumeSize": args.volume_size, "VolumeType": "gp3"},
            }
        ],
        # Omit either tag and the refusal is a bare UnauthorizedOperation, which reads exactly
        # like having no permission at all.
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": "ClaudeSpike"},
                    {"Key": "Owner", "Value": args.owner},
                ],
            }
        ],
    )
    market = _sim.market_options(args.spot)
    if market:
        request["InstanceMarketOptions"] = market

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **request)
        except Exception as exc:
            text = str(exc)
            if "DryRunOperation" in text:
                print("dry run authorizes this request")
                print("note: a dry run runs no UserData, so it cannot catch a short payload")
                return 0
            refusal = _sim.spot_refusal(text)
            print(refusal or text, file=sys.stderr)
            return 1
        return 0

    print(f"uploading payload -> s3://{bucket}/{code_key}")
    s3.put_object(Bucket=bucket, Key=code_key, Body=blob)

    iid = ""
    try:
        try:
            response = ec2.run_instances(**request)
        except Exception as exc:
            refusal = _sim.spot_refusal(str(exc))
            print(refusal or str(exc), file=sys.stderr)
            return 1
        instance = response["Instances"][0]
        iid = instance["InstanceId"]
        # The instance's own launch time, not this process's clock. Both are compared against
        # S3's `LastModified`, and only this one is in the same clock domain as it.
        launched_at = instance["LaunchTime"]
        market_label = "spot" if market else "on demand"
        print(f"launched {iid} ({args.instance_type}, {market_label}, {args.volume_size} GB gp3)")
        print(
            f"  hard stop in {args.hard_stop_minutes} min; results to s3://{bucket}/{prefix}/results/a1-8/"
        )
        return _watch(ec2, s3, iid, bucket, prefix, args, launched_at)
    finally:
        # Both, not either: a UserData that fails before its own shutdown would otherwise
        # leave the instance running until the boot-armed timer fires.
        if iid:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminated {iid}")
            except Exception as exc:
                print(f"could not terminate {iid}: {exc}", file=sys.stderr)


def _al2023(ec2: Any) -> str:
    """Newest Amazon Linux 2023 x86_64 AMI."""
    images = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-2023*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    if not images:
        raise SystemExit("no Amazon Linux 2023 AMI found")
    return max(images, key=lambda i: i["CreationDate"])["ImageId"]


def _watch(
    ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any, launched_at: datetime
) -> int:
    """Poll for the artefacts, reporting console output as it appears.

    Silence is the thing this cannot interpret, which is why the pass heartbeats and why the
    artefacts are what completion is judged by rather than the console.

    **Only artefacts written after this instance launched count.** The results prefix is
    stable across runs, so a re-run finds the previous run's objects already sitting in it and
    a presence check is satisfied before the new instance has finished booting. That is not
    hypothetical: it terminated the first attributed re-run ninety seconds in, reported the
    *old* run's reconciliation as the new one's, and would have been read as a completed pass
    by anyone who did not know the figures already. A2.4 hit the same shape with its heartbeat.
    """
    deadline = time.monotonic() + args.max_watch_minutes * 60
    results = f"{prefix}/results/a1-8/"
    seen_console = 0
    while time.monotonic() < deadline:
        time.sleep(args.watch_seconds)
        state = _sim._state(ec2, iid)
        try:
            out = ec2.get_console_output(InstanceId=iid).get("Output", "") or ""
        except Exception:
            out = ""
        if len(out) > seen_console:
            for line in out[seen_console:].splitlines():
                if line.strip():
                    print(f"  | {line}")
            seen_console = len(out)

        listing = [
            o
            for o in s3.list_objects_v2(Bucket=bucket, Prefix=results).get("Contents", [])
            if o["LastModified"] >= launched_at
        ]
        names = {Path(o["Key"]).name for o in listing}
        if any(n.startswith("seed-counts-") for n in names):
            print(f"artefacts present in s3://{bucket}/{results}:")
            for obj in listing:
                print(f"  {obj['Size']:>14,}  {obj['Key']}")
            return _report(s3, bucket, listing)
        if state in ("terminated", "shutting-down"):
            reason = _sim._transition_reason(ec2, iid)
            print(f"instance is {state} ({reason}) with no artefacts", file=sys.stderr)
            return 1
    print("watch deadline reached; the instance terminates on its own timer", file=sys.stderr)
    return 1


def _report(s3: Any, bucket: str, listing: list[dict[str, Any]]) -> int:
    """Print the reconciliation, which is the number the pass exists to produce."""
    key = next((o["Key"] for o in listing if Path(o["Key"]).name.startswith("seed-counts-")), None)
    if not key:
        return 1
    payload = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    counts = payload.get("counts", {})
    rec = payload.get("reconciliation") or {}
    print(
        f"\n{counts.get('clusters', 0):,} clusters, {counts.get('seeded', 0):,} seeded"
        f"   representative not seeded: {counts.get('representative_not_seeded', 0):,}"
    )
    if rec:
        # Read the keys `reconcile` actually publishes. It used to carry a `delta` that
        # subtracted a UniProtKB sequence count from a UniRef100 cluster count, which D-150
        # removed; `.get("delta", 0)` then printed a confident "+0" — a perfect match where
        # there is no comparison at all. A default that invents the most reassuring possible
        # number is worse than a missing line.
        reading = rec.get("reading_against_published")
        if reading is None:
            print(
                f"query set {rec.get('query_set_clusters', 0):,} UniRef100 clusters. The "
                f"published {rec.get('published_sequences', 0):,} counts UniProtKB sequences "
                "and is not comparable with it; no pinned UniProtKB count was found (D-150)."
            )
        else:
            print(
                f"query set {rec.get('query_set_clusters', 0):,} UniRef100 clusters "
                "(not comparable with the published figure, which counts UniProtKB "
                "sequences — D-150).\n"
                f"the reading against the published {rec.get('published_sequences', 0):,}: "
                f"{reading['uniprot_sequences']:,} at release "
                f"{reading.get('uniprot_release')} ({reading['delta']:+,})"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage UniProtKB 2023_02 and count it by taxon, in-region on EC2.

The archive is 182.7 GB and has to be pulled from UniProt whole — old releases are served as
one tarball whose only data members are `uniprot_sprot.dat.gz` and `uniprot_trembl.dat.gz`,
and tar is sequential, so there is nothing to range-request or skip. The session container
cannot sustain that: its outbound traffic goes through the agent proxy, measured at about
14 MiB/s against the roughly 87 MiB/s an instance gets direct, which turns a forty-minute
download into four hours on a link that also drops long transfers.

**Two phases, in this order, and the order is the whole design.** Staging copies the archive
into the corpus bucket, checksummed as it streams. Counting then reads the staged object. Run
the other way round, a parser bug would waste the download; run this way, the expensive
irreplaceable part is permanent before any parsing happens, and every later reading — the
toxin-producer switch, the alternatives switch (D-137) — is an in-region read that costs
nothing to move.

**Staging is irreversible.** The corpus bucket withholds `s3:DeleteObject`, which is what
makes a staged corpus un-rewritable and also means a wrong key is wrong forever. The key is
fixed in `tools/uniprot_release_count.py` as `STAGED_KEY` rather than derived at runtime, and
a partial object already at that key fails the run instead of being overwritten.

Everything else follows the rules AGENTS.md records as learned the hard way, and
`tools/ec2_select_agent_seeds.py` is the worked example this is built from: terminate-on-
shutdown set at launch because `ModifyInstanceAttribute` is denied afterwards, a boot-armed
dead man's switch, a `die` helper that cancels the pending timer before going down, a
terminate in the launcher's own `finally`, `python3.12` by name, the commit passed in because
the instance has no checkout, and results returning through object storage because there is
no shell, no SSH and no SSM.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from amazebio import objectstore, seeds  # noqa: E402


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `dataclasses` resolves a class's annotations through
    # `sys.modules[cls.__module__]`, so a module loaded by spec alone raises an opaque
    # AttributeError the moment it defines a dataclass.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_sim = _load(ROOT / "tools" / "ec2_similarity.py", "ec2_similarity_helpers_for_uniprot")

#: Modules the shipped tool imports. Derived and tested, never hand-trusted: twice, a module
#: was added to a tool's imports and not to its payload list, and the instance died on an
#: ImportError half a minute in having read nothing.
PAYLOAD_MODULES = (
    "src/amazebio/__init__.py",
    "src/amazebio/objectstore.py",
    "src/amazebio/repro.py",
    "src/amazebio/seeds.py",
    "src/amazebio/selectagents.py",
    "src/amazebio/uniprotkb.py",
    "src/amazebio/uniref.py",
    "tools/uniprot_release_count.py",
)


def payload_data_files() -> tuple[str, ...]:
    """The data files the pass reads, asked of the tool rather than restated here.

    They are not imports, so the closure derivation that guards `PAYLOAD_MODULES` is
    structurally blind to them and a missing one kills the instance exactly like a short
    module list.
    """
    tool = _load(ROOT / "tools" / "uniprot_release_count.py", "uniprot_release_count_for_payload")
    return tuple(tool.required_data_files())


USER_DATA = """#!/bin/bash
set -xeuo pipefail
exec > >(tee /dev/console) 2>&1
echo "=== amazebio a1-8 uniprotkb release count starting $(date -Is) ==="

shutdown -h +{hard_stop_minutes} &

# `shutdown -h now` does nothing while that timer is pending, so cancel first, then go down.
die() {{
  echo "=== shutting down: $1 ==="
  shutdown -c || true
  shutdown -h now || systemctl --no-block poweroff || halt -p || true
  exit "${{2:-1}}"
}}

dnf install -y tar gzip unzip >/dev/null

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

curl -sSL -o taxdmp.zip "{taxdump_url}"
echo "{taxdump_sha256}  taxdmp.zip" | sha256sum -c - || die "taxdump checksum mismatch"

"$PYBIN" - <<'PRECHECK' || die "the shipped payload cannot import; PAYLOAD_MODULES is short"
import sys, importlib.util
sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("urc", "tools/uniprot_release_count.py")
mod = importlib.util.module_from_spec(spec)
# Registered before execution. `dataclasses` resolves annotations through
# `sys.modules[cls.__module__]`, so a module loaded by spec alone dies on its first
# dataclass with an AttributeError — which `die` would then report as a short payload.
sys.modules["urc"] = mod
spec.loader.exec_module(mod)
print("=== payload imports cleanly ===")
PRECHECK

export AMAZEBIO_S3_URI="s3://{bucket}/{prefix}"

# Resolve the taxa and verify every pinned digest before touching 182.7 GB.
"$PYBIN" tools/uniprot_release_count.py \
  --taxdump /opt/amazebio/taxdmp.zip --check-inputs \
  || die "inputs do not resolve; the payload's data files are short or a digest moved"

# `set -e` and a subshell do not mix here: a failing command aborts the subshell *before*
# its trailing echo, so the subshell exits non-zero, `set -e` ends the script, and `die`
# never runs — leaving the instance idling until the boot timer, which is exactly the
# silence AGENTS.md says cannot be distinguished from work. Disarm `set -e` around the run
# and route the exit code through `die` explicitly.
set +e
"$PYBIN" tools/uniprot_release_count.py \
  --taxdump /opt/amazebio/taxdmp.zip \
  --outdir /opt/amazebio/out \
  {stage_flag} {reading_flags} \
  --upload-results --allow-dirty --code-commit {commit} \
  --heartbeat-seconds 120
rc=$?
set -e
echo "=== release count exited $rc ==="
if [ "$rc" -ne 0 ]; then die "release count failed with $rc" "$rc"; fi

echo "=== amazebio a1-8 uniprotkb release count finished $(date -Is) ==="
die "run complete" 0
"""


def build_payload(root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in (*PAYLOAD_MODULES, *payload_data_files()):
            tar.add(root / rel, arcname=rel)
    return buf.getvalue()


def _watch(
    ec2: Any, s3: Any, iid: str, bucket: str, prefix: str, args: Any, launched_at: datetime
) -> int:
    """Poll for the result object, reporting console output as it appears.

    Only artefacts written at or after this instance's own launch count. The results prefix is
    stable across runs, so a presence check alone is satisfied by an earlier run's object
    before the new instance has booted — which terminated a run ninety seconds in and printed
    the stale figure as though it were fresh.
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
            and Path(o["Key"]).name == "uniprotkb-release-count.json"
        ]
        if listing:
            print(f"result present: s3://{bucket}/{listing[0]['Key']}")
            return 0
        if state in ("terminated", "shutting-down"):
            reason = _sim._transition_reason(ec2, iid)
            print(f"instance is {state} ({reason}) with no result", file=sys.stderr)
            return 1
    print("watch deadline reached; the instance terminates on its own timer", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # The archive is one gzip stream, so decompression is single-threaded however many cores
    # are present and a bigger instance buys nothing (AGENTS.md). What matters is network and
    # a little memory for the upload parts.
    ap.add_argument("--instance-type", default="m6i.2xlarge")
    ap.add_argument("--profile", default="AmazebioStager")
    ap.add_argument("--s3-uri", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--owner", default="claude")
    ap.add_argument("--toxin-producers", action="store_true")
    ap.add_argument("--alternatives", action="store_true")
    ap.add_argument(
        "--no-stage",
        dest="stage",
        action="store_false",
        help="count without staging. Only for a re-run against an already-staged archive",
    )
    # Nothing is written to local disk: the archive streams through to object storage and the
    # count streams through memory. This holds the OS, python and the taxonomy.
    ap.add_argument("--volume-size", type=int, default=30)
    ap.add_argument(
        "--hard-stop-minutes",
        type=int,
        default=480,
        help="boot-armed dead man's switch. Staging is about 40 min and the count about two "
        "and a half hours, so this is margin rather than a target (default: %(default)s)",
    )
    ap.add_argument("--spot", action="store_true", default=True)
    ap.add_argument("--on-demand", dest="spot", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--print-user-data", action="store_true")
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

    flags = []
    if args.toxin_producers:
        flags.append("--toxin-producers")
    if args.alternatives:
        flags.append("--alternatives")

    code_key = f"{prefix}/code/a1-8-uniprot-{commit[:12]}.tar.gz"
    user_data = USER_DATA.format(
        hard_stop_minutes=args.hard_stop_minutes,
        bucket=bucket,
        prefix=prefix,
        code_key=code_key,
        region=args.region,
        taxdump_url=seeds.TAXDUMP_2023_04.url,
        taxdump_sha256=seeds.TAXDUMP_2023_04.sha256,
        stage_flag="--stage" if args.stage else "",
        reading_flags=" ".join(flags),
        commit=commit,
    )
    if args.print_user_data:
        print(user_data)
        return 0

    import boto3

    ec2 = boto3.client("ec2", region_name=args.region)
    s3 = objectstore.client()

    blob = build_payload(ROOT)
    print(f"payload {len(blob):,} bytes")

    request: dict[str, Any] = dict(
        ImageId=_al2023(ec2),
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
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": "ClaudeSpike"},
                    {"Key": "Owner", "Value": args.owner},
                    {"Key": "Name", "Value": "amazebio-a1-8-uniprotkb"},
                ],
            }
        ],
    )
    if args.spot:
        request["InstanceMarketOptions"] = {"MarketType": "spot"}

    if args.dry_run:
        try:
            ec2.run_instances(DryRun=True, **request)
        except Exception as exc:
            if "DryRunOperation" in str(exc):
                print("dry run authorizes this request")
                print("note: a dry run runs no UserData, so it cannot catch a short payload")
                return 0
            print(_sim.spot_refusal(str(exc)) or str(exc), file=sys.stderr)
            return 1
        return 0

    print(f"uploading payload -> s3://{bucket}/{code_key}")
    s3.put_object(Bucket=bucket, Key=code_key, Body=blob)

    iid = ""
    try:
        try:
            response = ec2.run_instances(**request)
        except Exception as exc:
            print(_sim.spot_refusal(str(exc)) or str(exc), file=sys.stderr)
            return 1
        instance = response["Instances"][0]
        iid = instance["InstanceId"]
        launched_at = instance["LaunchTime"]
        print(
            f"launched {iid} ({args.instance_type}, "
            f"{'spot' if args.spot else 'on demand'}, {args.volume_size} GB gp3)"
        )
        print(f"  hard stop in {args.hard_stop_minutes} min; results to s3://{bucket}/{prefix}")
        return _watch(ec2, s3, iid, bucket, prefix, args, launched_at)
    finally:
        if iid:
            try:
                ec2.terminate_instances(InstanceIds=[iid])
                print(f"terminated {iid}")
            except Exception as exc:
                print(f"could not terminate {iid}: {exc}", file=sys.stderr)


def _al2023(ec2: Any) -> str:
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

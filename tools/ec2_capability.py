#!/usr/bin/env python3
"""Measure which EC2 instance types this account may launch — task B1.1.

    python3 tools/ec2_capability.py              # probe and write the artefact
    python3 tools/ec2_capability.py --print      # probe and print, write nothing

`DESIGN.md` §B1 asks which Tier 2 models are in scope "if compute allows". That is not
answerable from a model card: it depends on what the account's launch policy permits, which
`AGENTS.md` describes as an allowlist without enumerating it. This probes the allowlist.

**Nothing is launched.** Every call passes `DryRun=True`, which authorizes and validates the
request and then refuses it: `DryRunOperation` means the launch would have succeeded,
`UnauthorizedOperation` means the policy refuses that instance type. No instance, no volume,
no cost. `AGENTS.md` warns that a dry run cannot catch a broken `UserData` — true, and
irrelevant here, because the question *is* the authorization.

Two details that would otherwise make the result a lie:

* The request carries the `Project=ClaudeSpike` and non-empty `Owner` tags and the
  `AmazebioStager` instance profile. Omit any of them and the refusal is also a bare
  `UnauthorizedOperation`, so an untagged probe would report every type as denied.
* The probed types are a fixed list in this file rather than a caller's argument, so a re-run
  measures the same thing and the artefact is comparable across dates. Extending the list is
  a code change, which is the point.

The output is `artifacts/b1-1/ec2-capability/allowlist.json` with a `run.json` beside it.
It gets its own directory because `run.json` is named by `amazebio.repro` and two tools sharing
an output directory would overwrite each other's provenance. It is a
snapshot of an account policy that can change, so it carries its date and must be re-run
rather than cited indefinitely.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio.repro import run

REPO = pathlib.Path(__file__).resolve().parent.parent
REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
PROFILE = "AmazebioStager"

# Enough of the space to bound it, not an exhaustive sweep. Accelerated families first,
# because they are what Phase B needs; then CPU sizes, to find the ceiling.
PROBE_TYPES: tuple[str, ...] = (
    # Accelerated: G for inference-class GPUs, P for training-class.
    "g4dn.xlarge",
    "g5.xlarge",
    "g5.2xlarge",
    "g5.12xlarge",
    "g6.xlarge",
    "g6e.xlarge",
    "p3.2xlarge",
    "p4d.24xlarge",
    "p5.48xlarge",
    # CPU: the families and sizes that bracket the known-good c6i.xlarge of A1.3.
    "t3.micro",
    "t3.large",
    "t3.xlarge",
    "t3.2xlarge",
    "c6i.large",
    "c6i.xlarge",
    "c6i.2xlarge",
    "c6i.4xlarge",
    "c6i.8xlarge",
    "c6a.2xlarge",
    "c7i.xlarge",
    "m5.xlarge",
    "m6i.xlarge",
    "m6i.2xlarge",
    "m6i.4xlarge",
    "r6i.xlarge",
    "r6i.2xlarge",
    "r6i.4xlarge",
)

# Families whose instances carry an attached accelerator. Used only to summarise the result;
# the per-type verdicts below are the measurement.
GPU_FAMILIES = ("g4dn", "g5", "g6", "g6e", "p3", "p4d", "p5")

ALLOWED = "DryRunOperation"


def _family(instance_type: str) -> str:
    return instance_type.split(".", 1)[0]


def probe(ec2: Any, ami: str, instance_types: tuple[str, ...], owner: str) -> dict[str, Any]:
    """Dry-run a launch of each type. Returns type -> {allowed, code, message}."""
    from botocore.exceptions import ClientError

    tags = [
        {"Key": "Project", "Value": "ClaudeSpike"},
        {"Key": "Owner", "Value": owner},
        {"Key": "Name", "Value": "amazebio-b1-1-capability-probe"},
    ]
    results: dict[str, Any] = {}
    for itype in instance_types:
        launch = dict(
            ImageId=ami,
            InstanceType=itype,
            MinCount=1,
            MaxCount=1,
            IamInstanceProfile={"Name": PROFILE},
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": tags},
                {"ResourceType": "volume", "Tags": tags},
            ],
            BlockDeviceMappings=[
                {"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 100, "VolumeType": "gp3"}}
            ],
            InstanceInitiatedShutdownBehavior="terminate",
        )
        try:
            ec2.run_instances(DryRun=True, **launch)
            # A dry run always raises. Reaching here means the API changed under us, and
            # reporting it as allowed would be a guess.
            results[itype] = {
                "allowed": None,
                "code": "NoException",
                "message": "dry run did not raise; treat as unmeasured",
            }
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            results[itype] = {
                "allowed": code == ALLOWED,
                "code": code,
                "message": exc.response["Error"]["Message"][:200],
            }
        print(f"  {itype:16} {results[itype]['code']}")
    return results


def summarise(results: dict[str, Any]) -> dict[str, Any]:
    allowed = sorted(t for t, r in results.items() if r["allowed"])
    gpu_allowed = sorted(t for t in allowed if _family(t) in GPU_FAMILIES)
    return {
        "allowed": allowed,
        "denied": sorted(t for t, r in results.items() if r["allowed"] is False),
        "unmeasured": sorted(t for t, r in results.items() if r["allowed"] is None),
        "gpu_allowed": gpu_allowed,
        "gpu_available": bool(gpu_allowed),
        "allowed_families": sorted({_family(t) for t in allowed}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="claude", help="value for the required Owner tag")
    ap.add_argument("--print", dest="print_only", action="store_true", help="write no artefact")
    ap.add_argument(
        "--allow-dirty", action="store_true", help="local iteration only; never for a citation"
    )
    args = ap.parse_args()

    import boto3

    ec2 = boto3.client(
        "ec2", region_name=REGION, endpoint_url=f"https://ec2.{REGION}.amazonaws.com"
    )
    ssm = boto3.client(
        "ssm", region_name=REGION, endpoint_url=f"https://ssm.{REGION}.amazonaws.com"
    )
    ami = ssm.get_parameter(Name=AMI_PARAMETER)["Parameter"]["Value"]
    print(f"region {REGION}  ami {ami}  profile {PROFILE}")
    print(f"dry-running {len(PROBE_TYPES)} instance types (nothing is launched)")

    if args.print_only:
        results = probe(ec2, ami, PROBE_TYPES, args.owner)
        print(json.dumps(summarise(results), indent=1))
        return 0

    outdir = REPO / "artifacts" / "b1-1" / "ec2-capability"
    with run("B1.1", outdir=outdir, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("region", REGION)
        m.parameter("ami_parameter", AMI_PARAMETER)
        m.parameter("instance_profile", PROFILE)
        m.parameter("probe_types", list(PROBE_TYPES))
        m.parameter("ami", ami)
        m.note(
            "RunInstances with DryRun=True for each probed type. Nothing was launched. The "
            "request carries the Project and Owner tags and the instance profile, without "
            "which every refusal would be an indistinguishable UnauthorizedOperation."
        )
        results = probe(ec2, ami, PROBE_TYPES, args.owner)
        summary = summarise(results)

        path = outdir / "allowlist.json"
        payload = {"region": REGION, "ami": ami, "summary": summary, "results": results}
        path.write_text(json.dumps(payload, indent=1) + "\n")
        m.output_file(path, role="ec2 launch allowlist as measured by dry run")

    print(f"\nallowed: {', '.join(summary['allowed']) or '(none)'}")
    print(f"gpu available: {summary['gpu_available']}")
    print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

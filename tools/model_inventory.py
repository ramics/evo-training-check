#!/usr/bin/env python3
"""Validate the Phase B model inventory and write it out — task B1.1.

    python3 tools/model_inventory.py --check    # validate only; CI runs this
    python3 tools/model_inventory.py            # also write artifacts/b1-1/inventory.json
    python3 tools/model_inventory.py --table    # print the table for a write-up

The inventory itself is `amazebio.models` and the evidence is `policies/models.md`. This tool
is the join: it checks every source a checkpoint cites against `policies/sources.json`, folds
in the measured compute envelope from `ec2-allowlist.json` when one exists, and writes the
machine-readable artefact that `AGENTS.md` requires behind any number in a write-up.

`--check` is cheap and catches the failure that matters — a checkpoint resting on a source
nobody retrieved, which looks exactly like a verified claim until someone follows the citation.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio.models import InventoryError, feasibility, inventory, validate
from amazebio.repro import run

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCES = REPO / "policies" / "sources.json"
# Each tool writes to its own directory: `run.json` is named by `amazebio.repro`, so two
# tools sharing one would overwrite each other's provenance.
OUTDIR = REPO / "artifacts" / "b1-1" / "inventory"
ALLOWLIST = REPO / "artifacts" / "b1-1" / "ec2-capability" / "allowlist.json"


def load_sources() -> dict[str, dict]:
    data = json.loads(SOURCES.read_text())
    return {s["id"]: s for s in data["sources"]}


def compute_envelope() -> dict:
    """The measured compute envelope, or a stated absence.

    Absence is reported rather than assumed either way: a feasibility verdict derived from a
    guess about the account's launch policy would be the kind of plausible-looking claim this
    project's checks exist to prevent.
    """
    if not ALLOWLIST.exists():
        return {
            "measured": False,
            "note": "run tools/ec2_capability.py; feasibility is unknown until it has run",
        }
    data = json.loads(ALLOWLIST.read_text())
    summary = data["summary"]
    return {
        "measured": True,
        # The accelerated types themselves, not a boolean: what a checkpoint needs is a
        # property of the accelerator, and "a GPU is available" cannot distinguish one 24 GB
        # card from eight H100s. See amazebio.models.GpuNeed.
        "gpu_types": summary["gpu_allowed"],
        "allowed_instance_types": summary["allowed"],
        "unmeasured_instance_types": summary["unmeasured"],
        "source": str(ALLOWLIST.relative_to(REPO)),
    }


def table(checkpoints) -> str:
    rows = [
        "| Checkpoint | Params | Role | Exclusion | Licence | Tier |",
        "|---|---|---|---|---|---|",
    ]
    for c in checkpoints:
        rows.append(
            f"| `{c.id}` | {c.params or '*unstated*'} | {c.role.value.replace('_', ' ')} "
            f"| {c.exclusion.value.replace('_', ' ')} | {c.licence} | {c.tier} |"
        )
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    ap.add_argument("--table", action="store_true", help="print the inventory as a table")
    ap.add_argument(
        "--allow-dirty", action="store_true", help="local iteration only; never for a citation"
    )
    args = ap.parse_args()

    checkpoints = inventory()
    sources = load_sources()
    try:
        validate(checkpoints, sources=sources)
    except InventoryError as exc:
        print(f"inventory invalid: {exc}", file=sys.stderr)
        return 1

    unverified = {c.id: list(c.unverified) for c in checkpoints if c.unverified}
    print(f"checked {len(checkpoints)} checkpoints, 0 problems")
    print(f"under-documented: {len(unverified)} of {len(checkpoints)} carry a §A0 finding")

    if args.table:
        print()
        print(table(checkpoints))

    if args.check:
        return 0

    envelope = compute_envelope()
    with run("B1.1", outdir=OUTDIR, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("tiers", [1, 2])
        m.parameter("compute_envelope_measured", envelope["measured"])
        m.input_file(SOURCES, role="source inventory each checkpoint's claims cite")
        if envelope["measured"]:
            m.input_file(ALLOWLIST, role="measured EC2 launch allowlist")
            feasible = feasibility(checkpoints, gpu_types=envelope["gpu_types"])
        else:
            feasible = {c.id: "unknown: compute envelope not measured" for c in checkpoints}
        m.note(
            "Every field traces to a quotation in policies/models.md, which tools/policies.py "
            "checks against the stored source. Fields no first-party source states are listed "
            "per checkpoint as under_documented rather than filled in."
        )

        path = OUTDIR / "inventory.json"
        path.write_text(
            json.dumps(
                {
                    "task": "B1.1",
                    "design_ref": "§B1",
                    "checkpoints": [c.to_dict() for c in checkpoints],
                    "under_documented": unverified,
                    "compute_envelope": envelope,
                    "feasibility": feasible,
                },
                indent=1,
            )
            + "\n"
        )
        m.output_file(path, role="verified Phase B model inventory")

    blocked = {k: v for k, v in feasible.items() if v != "runnable"}
    if blocked:
        print(f"\nnot runnable here: {len(blocked)} of {len(checkpoints)}")
        for cid, why in sorted(blocked.items()):
            print(f"  {cid}: {why}")
    print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

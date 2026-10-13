#!/usr/bin/env python3
"""Validate and render the filter policy specs in `policies/specs/`.

    python3 tools/specs.py            # validate every spec
    python3 tools/specs.py --describe # also print each policy as prose

Validation covers the schema (see `amazebio.policyspec`) plus two things only checkable here:

* every `source` a rule cites must exist in `policies/sources.json` and be a retrieved source,
  so a predicate can always be traced back to text somebody actually read;
* a policy that is not fully determined must say which values are missing, which the schema
  guarantees structurally but is worth reporting so the gaps are visible rather than buried.

CI runs this. A spec that cites a source nobody retrieved is the same failure mode
`tools/policies.py` guards against for quotes, one level up.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio.policyspec import Policy, PolicyError, describe, load_policy_dir

REPO = pathlib.Path(__file__).resolve().parent.parent
SPECS = REPO / "policies" / "specs"
SOURCES = REPO / "policies" / "sources.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--describe", action="store_true", help="print each policy as prose")
    args = ap.parse_args()

    try:
        policies = load_policy_dir(SPECS)
    except PolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sources = {s["id"]: s for s in json.loads(SOURCES.read_text())["sources"]}
    problems: list[str] = []

    for pid, policy in policies.items():
        cited = {policy.source} | {r.source for r in policy.rules}
        for sid in sorted(cited):
            if sid not in sources:
                problems.append(f"{pid}: cites unknown source {sid}")
            elif sources[sid]["status"] != "retrieved":
                problems.append(
                    f"{pid}: cites {sid}, whose status is '{sources[sid]['status']}'. A policy "
                    "may only be built from a source that was retrieved and stored."
                )

    # DESIGN.md §A0 requires three readings per policy, and A0.3 froze them. A model with a
    # spec at all must have all three: a missing reading would silently narrow the spread that
    # §A0 treats as the finding, and a downstream task would consume whichever readings existed.
    by_model: dict[str, set[str]] = {}
    for policy in policies.values():
        by_model.setdefault(policy.model, set()).add(policy.reading)
    for model, readings in sorted(by_model.items()):
        if missing := set(Policy.READINGS) - readings:
            problems.append(
                f"{model}: missing the {', '.join(sorted(missing))} reading(s). DESIGN.md §A0 "
                "requires all three per policy; the spread between them is the finding."
            )

    for p in problems:
        print(f"problem: {p}", file=sys.stderr)

    if args.describe:
        for policy in policies.values():
            print()
            print(describe(policy))

    undetermined = {pid: p.unspecified() for pid, p in policies.items() if not p.is_determined}
    print(f"\nspecs: {len(policies)} policies, {len(problems)} problems")
    for pid, gaps in sorted(undetermined.items()):
        detail = "; ".join(f"{rid} needs {', '.join(ps)}" for rid, ps in gaps.items())
        print(f"  not fully determined: {pid} — {detail}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

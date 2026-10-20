#!/usr/bin/env python3
"""Run one filter policy against one corpus and report survival by route — task A5.1, §A5.

    pixi run -e dev python tools/filter_audit.py --policy policies/specs/evo1-literal.yaml \
        --corpus fixture

This is the §5 deliverable's command line: the one door into Phase A's machinery, described
in `docs/filter-audit.md`. It composes `amazebio.filteraudit`, which in turn calls the same
functions that produced A3.2 — nothing here recomputes a metric, so "reproduces A3.2 exactly"
is true by construction rather than by comparison.

`--corpus fixture` runs the bundled nine-record corpus, which is what makes the end-to-end
path runnable in CI and on a machine with no access to the staged releases. A staged release
is named by its own loader; see the documentation for what a corpus has to supply.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import filteraudit, objectstore, policyspec, quantify, repro

TASK = "A5.1"

#: The bundled corpus, by name. A registry rather than an import path: a tool that imports a
#: module named on the command line is a tool that runs arbitrary code from its arguments.
CORPORA = ("fixture",)


def fixture_corpus() -> Any:
    """The nine-record corpus the tests check by hand. Imported lazily; it lives in `tests/`
    because it is a fixture, and shipping it as library code would invite it being mistaken
    for one of the real corpus loaders."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from test_filteraudit import UNIVERSE, FixtureCorpus, detector, policy

    return (
        FixtureCorpus(),
        {UNIVERSE.key: UNIVERSE},
        {"stub": detector("stub", {"FAM1": 3, "FAM2": 1})},
        policy(),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--policy", type=Path, help="a filter policy spec; omit with --corpus fixture")
    ap.add_argument("--corpus", choices=CORPORA, default="fixture")
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a5-1"))
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="re-run A3.2's own detector documents through this interface and diff",
    )
    args = ap.parse_args(argv)

    if args.verify:
        return verify(args)

    corpus, universes, detectors, default_policy = fixture_corpus()
    policy = policyspec.load_policy(args.policy) if args.policy else default_policy

    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=args.seed,
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-{args.corpus}.json",
            durable=objectstore.durable_results("a5-1"),
        ) as manifest:
            manifest.parameter("policy", policy.id)
            manifest.parameter("corpus", args.corpus)
            manifest.parameter("universes", sorted(universes))
            report = filteraudit.audit(
                filteraudit.AuditRequest(
                    policy=policy,
                    corpus=corpus,
                    universes=universes,
                    detectors=detectors,
                    seed=args.seed,
                )
            )
            out = args.outdir / f"report-{policy.id}-{corpus.release}.json"
            out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="survival-route report")
    except (repro.ReproError, filteraudit.AuditError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(summarise(report))
    return 0


def verify(args: argparse.Namespace) -> int:
    """Feed A3.2's own detector documents through this interface and diff the result.

    The Done-when criterion is that the deliverable reproduces A3.2 exactly. It does so by
    construction — `filteraudit.audit` calls `quantify.merge_group` and `quantify.quantify`
    rather than reimplementing them — but "by construction" is a claim about the code, and
    this is the measurement. It reads the detector documents A3.2's own headline names, runs
    the same three calls `audit` makes, and compares group by group.

    Not a second method. A3.3 is the second method, written by someone who has not read the
    first; this establishes only that the packaging changed no number.
    """
    import json as _json

    client = objectstore.client()
    bucket, key = objectstore.split_uri(objectstore.durable_results("a3-2") + "/headline.json")
    headline = _json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())

    tables = []
    for uri in sorted({d["source"] for g in headline["groups"] for d in g.get("detectors") or []}):
        b, k = objectstore.split_uri(uri)
        tables.append(
            quantify.load_table(
                _json.loads(client.get_object(Bucket=b, Key=k)["Body"].read()), source=uri
            )
        )

    mine = {}
    for group_key, group in quantify.group_tables(tables).items():
        quantified = quantify.quantify(
            quantify.merge_group(group_key, group),
            seed=headline["seed"],
            resamples=headline["bootstrap_resamples"],
        )
        mine[(group_key.policy_id, group_key.release, group_key.universe.key)] = quantified.document

    compared = ("m1_fraction", "m1_families_with_a_hit", "m1_ci_low", "m1_ci_high", "m2", "routes")
    differing = []
    for group in headline["groups"]:
        slot = (group["policy_id"], group["release"], group["universe"])
        theirs = {f: group.get(f) for f in compared}
        ours = {f: mine.get(slot, {}).get(f) for f in compared}
        if _json.dumps(theirs, sort_keys=True) != _json.dumps(ours, sort_keys=True):
            differing.append(slot)

    print(
        f"{len(headline['groups']) - len(differing)} of {len(headline['groups'])} A3.2 groups "
        "reproduce identically through this interface"
    )
    for slot in differing:
        print(f"  DIFFERS: {slot}")
    return 1 if differing else 0


def summarise(report: filteraudit.AuditReport) -> str:
    lines = [
        f"{report.policy_id} against {report.release}",
        f"  removed: {report.manifest.removed_records:,} records",
    ]
    for source in report.manifest.sources:
        verdict = source.uniform_outcome or ", ".join(
            f"{k} {v:,}" for k, v in sorted(source.counts.items())
        )
        lines.append(f"  {source.component}: {verdict}")
    for group in report.groups:
        document = group.document
        fraction = document.get("m1_fraction")
        if fraction is None:
            lines.append(f"  {document['universe']}: not searched")
            continue
        lines.append(
            f"  {document['universe']}: M1 {fraction:.4f} "
            f"[{document['m1_ci_low']:.4f}, {document['m1_ci_high']:.4f}] "
            f"over {document['families_in_universe']:,} families"
        )
    lines.append("")
    lines.append("What each route cannot say:")
    lines += [f"  {route}: {why}" for route, why in sorted(report.limitations.items())]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

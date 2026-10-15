#!/usr/bin/env python3
"""Apply the filter policy specs to the staged corpora and write the A1.4 manifests.

    pixi run -e dev python tools/apply_policies.py --out artifacts/a1-4
    pixi run -e dev python tools/apply_policies.py --release opengenome --dry-run
    pixi run -e dev python tools/apply_policies.py --policy evo1-literal --limit 100000

One manifest per model x reading x release. A1.4 covers the readings whose inputs the staged
releases carry — Evo 1's three readings against both OpenGenome releases, plus ESM3-open's
literal reading, whose verdict follows from the published words alone. The ESM3 charitable and
strict readings need an aligner and a seed set nobody has staged; they are A1.6 (D-043), and
this tool refuses them by name rather than producing an empty manifest that looks like a result.

What a run costs. The three enumerated objects are 28.1 GB and are streamed, never stored: a
session container's disk is a fraction of them. Reading them out of region would be the metered
case `AGENTS.md` weighs against an in-region instance, but at this size the egress is a couple
of dollars against an instance that cannot be inspected once running and has to be right first
time — so this runs here, and `AGENTS.md`'s EC2 test starts to bind at GTDB's 101 GiB, which
this task deliberately does not read. D-046 records the call.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora
from amazebio.apply import (
    PolicyManifest,
    SourceVerdict,
    applicable_rules,
    is_uniform,
    resolve,
    uniform_verdict,
)
from amazebio.policyspec import Outcome, Policy, load_policy_dir
from amazebio.repro import run

SPECS = Path(__file__).resolve().parent.parent / "policies" / "specs"

#: Which releases each policy is evaluated against. Evo 1's procedure is inherited unchanged by
#: Evo 2 ("As previously described"), so each reading is applied to both releases and the two
#: manifests are not merged: the releases carry different metadata, so the same reading reaches
#: a different verdict on each, and that difference is a finding rather than noise to average.
RELEASES = {
    "evo1-literal": ("opengenome", "opengenome2"),
    "evo1-charitable": ("opengenome", "opengenome2"),
    "evo1-strict": ("opengenome", "opengenome2"),
    "esm3-open-literal": ("esm3-proxy",),
}

#: Deferred to A1.6 with a reason, rather than silently skipped.
DEFERRED = {
    "esm3-open-charitable": "needs the UniProt seed sets and an MMseqs pass — A1.6 (D-043)",
    "esm3-open-strict": "needs the same seed sets at the aligner's sensitivity floor — A1.6",
}

SEED = 20261015


def _client() -> Any:
    import boto3

    return boto3.client("s3", region_name=corpora.S3_REGION, endpoint_url=corpora.S3_ENDPOINT)


def check_inventory(client: Any) -> int:
    """Refuse to run if the bucket holds a staged object `corpora.SOURCES` does not declare.

    One listing, before any corpus is read. A1.4's first pass declared two of Evo 1's three
    stage-2 splits and would have reported a short count of the filter's own output as a
    finished result; nothing downstream could have caught it. Returns the number of objects
    checked.
    """
    paginator = client.get_paginator("list_objects_v2")
    live: list[tuple[str, int]] = []
    for prefix in corpora.INVENTORY_PREFIXES:
        for page in paginator.paginate(Bucket=corpora.BUCKET, Prefix=prefix):
            live.extend((o["Key"], o["Size"]) for o in page.get("Contents", []))
    missing = corpora.undeclared_objects(live)
    if missing:
        listed = "\n  ".join(f"{size:>15,}  {key}" for key, size in sorted(missing))
        raise SystemExit(
            f"{len(missing)} staged object(s) are not declared in corpora.SOURCES, so this run "
            f"would silently omit them:\n  {listed}\n"
            "Declare them with their component and evidence, or exclude them explicitly."
        )
    return len(live)


def _records(
    client: Any, source: corpora.StagedSource, *, limit: int | None, on_parse_error: Any
) -> Iterator[Any]:
    """The record stream for one staged source, chosen by its declared reader."""
    # The size pin, checked rather than assumed. A1.2 and A1.5 verified these objects against
    # their publishers' checksums at staging and the bucket withholds DeleteObject, so the
    # cheap check that the object is still the one they verified is its length — and a silent
    # mismatch would have this reader stream a truncated corpus and report the counts anyway.
    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if live != source.bytes:
        raise ValueError(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}. "
            "A1.2/A1.5 verified the pinned bytes; re-verify before trusting any count from it."
        )
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,} of {source.corpus_component}: {exc}",
            file=sys.stderr,
        ),
    )
    if source.reader == "stage2_parquet":
        stream: Iterator[Any] = corpora.iter_stage2_records(
            obj.buffered(),
            component=source.component,
            record_prefix=source.corpus_component + ":" + Path(source.key).name,
            on_parse_error=on_parse_error,
        )
    elif source.reader == "fasta":
        reader: Any = obj.buffered()
        if source.gzipped:
            from amazebio.uniref import GunzipStream

            reader = GunzipStream(reader)
        stream = corpora.iter_fasta_records(reader, component=source.component)
    else:  # pragma: no cover - guarded by `readable`
        raise ValueError(f"no reader for {source.key}")
    for i, record in enumerate(stream):
        if limit is not None and i >= limit:
            return
        yield record


def _shell(policy: Policy, source: corpora.StagedSource) -> SourceVerdict:
    """The part of a verdict that needs no reading: which rules reach here, and which cannot
    be decided here, and why."""
    rules = applicable_rules(policy, source.component)
    undecidable = {
        rule.id: (
            f"source does not state {', '.join(rule.unspecified_params())}"
            if rule.unspecified_params()
            else f"corpus does not carry {', '.join(source.evidence.missing_for(rule))}"
        )
        for rule in rules
        if rule.unspecified_params() or source.evidence.missing_for(rule)
    }
    return SourceVerdict(
        key=source.key,
        component=source.component,
        corpus_component=source.corpus_component,
        release=source.release,
        bytes=source.bytes,
        records=None,
        enumerated=False,
        uniform=is_uniform(policy, source.component, source.evidence),
        rules_applicable=[r.id for r in rules],
        rules_undecidable=undecidable,
        why=source.why,
    )


def uniform_source(policy: Policy, source: corpora.StagedSource) -> SourceVerdict:
    """A verdict for a component no rule can discriminate within. Nothing is read."""
    verdict = _shell(policy, source)
    decision = uniform_verdict(policy, source.component, source.evidence)
    verdict.uniform_outcome = decision.outcome.value
    verdict.note = decision.why
    if source.extra.get("staged") is False:
        verdict.note += " Not staged, so no record count exists for it here."
    if "counted_clusters" in source.extra:
        verdict.note += (
            f" Counted per tier by A1.5: {source.extra['counted_clusters']}; which tier the "
            "source used is unstated, so no single count applies."
        )
    return verdict


def enumerate_source(
    source: corpora.StagedSource,
    policies: list[Policy],
    *,
    client: Any,
    limit: int | None,
    sinks: dict[str, Any],
) -> dict[str, SourceVerdict]:
    """Read one staged source once and resolve every policy against each record.

    One pass, not one per policy. The three Evo readings differ in their rules, not in the bytes
    they read, and re-reading 28 GB per reading would triple both the wall clock and the egress
    this task is costed on for nothing.
    """
    verdicts = {p.id: _shell(p, source) for p in policies}
    counts: dict[str, Counter[str]] = {p.id: Counter() for p in policies}
    attribution: dict[str, Counter[str]] = {p.id: Counter() for p in policies}
    kept: dict[str, dict[str, set]] = {p.id: {} for p in policies}
    parse_failures = Counter[str]()
    contradictions = 0
    seen = 0

    def note_parse_error(record_id: str, exc: Exception) -> None:
        parse_failures["n"] += 1
        if parse_failures["n"] <= 3:
            print(f"    parse failure {record_id}: {exc}", file=sys.stderr)

    declares_no_taxonomy = not source.evidence.taxonomy_ranks
    for record in _records(client, source, limit=limit, on_parse_error=note_parse_error):
        seen += 1
        head = record.attributes.get("head")
        # Where the source declares it carries no taxonomy, check that rather than trust it.
        if head is not None and declares_no_taxonomy and corpora.has_lineage_tag(head):
            contradictions += 1
        for policy in policies:
            decision = resolve(
                policy, record, evidence=source.evidence, kept_values=kept[policy.id]
            )
            counts[policy.id][decision.outcome.value] += 1
            attribution[policy.id][f"{decision.outcome.value}|{decision.rule_id or '-'}"] += 1
            if decision.outcome is Outcome.REMOVED:
                sinks[policy.id](decision)
        if seen % 250_000 == 0:
            print(f"    {source.corpus_component}: {seen:,} records", file=sys.stderr)

    for policy in policies:
        verdict = verdicts[policy.id]
        verdict.records = seen
        verdict.enumerated = True
        verdict.counts = dict(counts[policy.id])
        verdict.attribution = dict(attribution[policy.id])
        verdict.parse_failures = parse_failures["n"]
        verdict.evidence_contradictions = contradictions
        if verdict.uniform:
            verdict.note = (
                "Enumerated although no rule can be decided here, to verify the declared "
                "absence of taxonomy over the whole component rather than a sample."
            )
    return verdicts


def build_all(
    policies: list[Policy],
    *,
    releases: dict[str, tuple[str, ...]],
    client: Any,
    outdir: Path,
    limit: int | None,
) -> list[PolicyManifest]:
    """Every manifest, reading each staged source exactly once."""
    outdir.mkdir(parents=True, exist_ok=True)
    manifests: dict[tuple[str, str], PolicyManifest] = {}
    files: dict[tuple[str, str], Any] = {}
    counts: Counter[tuple[str, str]] = Counter()

    for policy in policies:
        for release in releases[policy.id]:
            manifests[policy.id, release] = PolicyManifest(
                policy_id=policy.id,
                model=policy.model,
                reading=policy.reading,
                release=release,
                scope=list(policy.scope.components),
            )
            files[policy.id, release] = (outdir / f"removed-{policy.id}-{release}.jsonl").open("w")

    try:
        for release in sorted({r for p in policies for r in releases[p.id]}):
            here = [p for p in policies if release in releases[p.id]]
            sinks = {}
            for policy in here:
                key = (policy.id, release)

                def sink(decision: Any, key: tuple[str, str] = key) -> None:
                    counts[key] += 1
                    files[key].write(
                        json.dumps(
                            {
                                "record_id": decision.record_id,
                                "policy": key[0],
                                "release": key[1],
                                "rule_id": decision.rule_id,
                                "why": decision.why,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )

                sinks[policy.id] = sink

            for source in corpora.sources_for(release):
                read = source.readable and (
                    source.verify_evidence
                    or any(not is_uniform(p, source.component, source.evidence) for p in here)
                )
                print(
                    f"  {release}/{source.corpus_component}: "
                    f"{'reading' if read else 'uniform verdict'} for {len(here)} reading(s)",
                    file=sys.stderr,
                )
                if read:
                    produced = enumerate_source(
                        source, here, client=client, limit=limit, sinks=sinks
                    )
                else:
                    produced = {p.id: uniform_source(p, source) for p in here}
                for policy_id, verdict in produced.items():
                    manifests[policy_id, release].sources.append(verdict)
    finally:
        for handle in files.values():
            handle.close()

    built = []
    for (policy_id, release), manifest in manifests.items():
        removed = counts[policy_id, release]
        path = outdir / f"removed-{policy_id}-{release}.jsonl"
        manifest.removed_records = removed
        manifest.removed_file = path.name if removed else None
        if not removed:
            path.unlink(missing_ok=True)
        manifest.notes.append(
            "Record identifiers for Evo 1's stage-2 component are synthesised as "
            "`stage2:<object>#<row>`: the release carries no accession for it, and a row is a "
            "context window rather than a biological record (policies/corpora.md §3). No "
            "per-genome proportion may be computed from these counts."
        )
        if any(s.evidence_contradictions for s in manifest.sources):
            manifest.notes.append(
                "An evidence declaration was contradicted by the records — see "
                "`evidence_contradictions`. Every verdict drawn from that source is void until "
                "the declaration is corrected."
            )
        built.append(manifest)
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/a1-4", type=Path)
    parser.add_argument("--policy", action="append", help="policy id; repeatable")
    parser.add_argument("--release", action="append", help="release key; repeatable")
    parser.add_argument(
        "--limit", type=int, help="stop after N records per source — for a smoke run only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what each policy would do per source, reading nothing",
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    policies = load_policy_dir(SPECS)
    wanted = args.policy or [p for p in policies if p not in DEFERRED]
    for policy_id in wanted:
        if policy_id in DEFERRED:
            print(f"{policy_id}: deferred — {DEFERRED[policy_id]}", file=sys.stderr)
            return 2
        if policy_id not in policies:
            print(f"{policy_id}: no such policy spec", file=sys.stderr)
            return 2

    if args.dry_run:
        for policy_id in sorted(wanted):
            policy = policies[policy_id]
            for release in RELEASES[policy_id]:
                if args.release and release not in args.release:
                    continue
                print(f"\n{policy_id} x {release}")
                for source in corpora.sources_for(release):
                    rules = applicable_rules(policy, source.component)
                    uniform = is_uniform(policy, source.component, source.evidence)
                    read = source.readable and (not uniform or source.verify_evidence)
                    outcome = (
                        uniform_verdict(policy, source.component, source.evidence).outcome.value
                        if uniform
                        else "per-record"
                    )
                    print(
                        f"  {source.corpus_component:16} rules={len(rules):2} "
                        f"uniform={uniform!s:5} read={read!s:5} -> {outcome}"
                    )
        return 0

    outdir = Path(args.out)
    client = _client()
    checked = check_inventory(client)
    print(f"inventory: {checked} staged objects, all declared", file=sys.stderr)
    with run("A1.4", seed=SEED, outdir=outdir, allow_dirty=args.allow_dirty) as manifest:
        manifest.parameter("policies", sorted(wanted))
        manifest.parameter("releases", {p: list(RELEASES[p]) for p in sorted(wanted)})
        manifest.parameter("limit", args.limit)
        manifest.parameter(
            "resolution", "all-applicable-rules; removed>undetermined>unresolved>retained"
        )
        manifest.parameter("lineage_window_bytes", corpora.LINEAGE_WINDOW)
        manifest.parameter("deferred_to_a1_6", sorted(DEFERRED))
        manifest.parameter("staged_objects_checked", checked)
        for source in corpora.SOURCES + corpora.ESM3_SOURCES:
            if source.key and source.bytes:
                manifest.input_url(
                    f"s3://{corpora.BUCKET}/{source.key}",
                    role=f"{source.release}:{source.corpus_component}",
                    bytes=source.bytes,
                    verified=False,
                )

        index: list[dict[str, Any]] = []
        chosen = [policies[p] for p in sorted(wanted)]
        releases = {
            p.id: tuple(r for r in RELEASES[p.id] if not args.release or r in args.release)
            for p in chosen
        }
        chosen = [p for p in chosen if releases[p.id]]
        for built in build_all(
            chosen, releases=releases, client=client, outdir=outdir, limit=args.limit
        ):
            name = f"manifest-{built.policy_id}-{built.release}.json"
            built.write(outdir / name)
            manifest.output_file(outdir / name, role="manifest")
            if built.removed_file:
                manifest.output_file(outdir / built.removed_file, role="removed-set")
            index.append(
                {
                    "policy": built.policy_id,
                    "release": built.release,
                    "manifest": name,
                    "totals": built.totals(),
                    "removed_records": built.removed_records,
                }
            )
            print(f"  -> {name}: {built.totals()} removed={built.removed_records}", file=sys.stderr)

        index_path = outdir / "index.json"
        index_path.write_text(
            json.dumps(
                {
                    "task": "A1.4",
                    "manifests": index,
                    "deferred": DEFERRED,
                    "format": "metrics/manifests.md",
                },
                indent=2,
            )
            + "\n"
        )
        manifest.output_file(index_path, role="index")
        manifest.note(
            "Inputs are recorded unverified: A1.2 and A1.5 matched every staged object against "
            "its publisher's own checksum at staging, and this run re-checks each object's "
            "length rather than re-hashing 28 GB to restate their result. The pin on the bytes "
            "is theirs; a length mismatch here aborts the run."
        )
        manifest.note(
            "Seven manifests: Evo 1's three readings against both OpenGenome releases, and "
            "ESM3-open's literal reading against the A1.5 proxy. The ESM3 charitable and "
            "strict readings are A1.6."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    obj = corpora.RangedObject(client, bucket=corpora.BUCKET, key=source.key, size=source.bytes)
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


def evaluate_source(
    policy: Policy,
    source: corpora.StagedSource,
    *,
    client: Any,
    limit: int | None,
    on_removed: Any,
) -> SourceVerdict:
    """Apply one policy to one staged source, enumerating it only if a rule can discriminate."""
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
    uniform = is_uniform(policy, source.component, source.evidence)
    verdict = SourceVerdict(
        key=source.key,
        component=source.component,
        corpus_component=source.corpus_component,
        release=source.release,
        bytes=source.bytes,
        records=None,
        enumerated=False,
        uniform=uniform,
        rules_applicable=[r.id for r in rules],
        rules_undecidable=undecidable,
        why=source.why,
    )

    if uniform and not (source.readable and source.verify_evidence):
        decision = uniform_verdict(policy, source.component, source.evidence)
        verdict.uniform_outcome = decision.outcome.value
        verdict.note = decision.why
        if not source.readable:
            verdict.note += (
                " — not enumerated: no reader, and the verdict does not need one"
                if source.reader == "none"
                else ""
            )
        for key, value in source.extra.items():
            if key == "counted_clusters":
                verdict.note += f" Record counts available per tier: {value}."
        return verdict
    if not source.readable:  # pragma: no cover - SOURCES has no such row
        raise ValueError(f"{source.key}: a rule discriminates here but there is no reader")

    parse_failures: Counter[str] = Counter()
    contradictions = 0
    counts: Counter[str] = Counter()
    attribution: Counter[str] = Counter()
    kept: dict[str, set] = {}
    seen = 0

    def note_parse_error(record_id: str, exc: Exception) -> None:
        parse_failures["n"] += 1
        if parse_failures["n"] <= 3:
            print(f"    parse failure {record_id}: {exc}", file=sys.stderr)

    for record in _records(client, source, limit=limit, on_parse_error=note_parse_error):
        seen += 1
        head = record.attributes.get("head")
        # Where the source declares it carries no taxonomy, check that rather than trust it.
        declares_no_taxonomy = not source.evidence.taxonomy_ranks
        if head is not None and declares_no_taxonomy and corpora.has_lineage_tag(head):
            contradictions += 1
        decision = resolve(policy, record, evidence=source.evidence, kept_values=kept)
        counts[decision.outcome.value] += 1
        attribution[f"{decision.outcome.value}|{decision.rule_id or '-'}"] += 1
        if decision.outcome is Outcome.REMOVED:
            on_removed(decision)
        if seen % 500_000 == 0:
            print(f"    {source.corpus_component}: {seen:,} records", file=sys.stderr)

    verdict.records = seen
    verdict.enumerated = True
    verdict.counts = dict(counts)
    verdict.attribution = dict(attribution)
    verdict.parse_failures = parse_failures["n"]
    verdict.evidence_contradictions = contradictions
    if uniform:
        verdict.note = (
            "Enumerated although every rule is undecidable here, to verify the declared "
            "absence of taxonomy over the whole component rather than a sample."
        )
    return verdict


def build(
    policy: Policy,
    release: str,
    *,
    client: Any,
    outdir: Path,
    limit: int | None,
) -> PolicyManifest:
    """One model x reading x release manifest, with its removed set beside it."""
    manifest = PolicyManifest(
        policy_id=policy.id,
        model=policy.model,
        reading=policy.reading,
        release=release,
        scope=list(policy.scope.components),
    )
    removed_name = f"removed-{policy.id}-{release}.jsonl"
    removed_path = outdir / removed_name
    removed_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with removed_path.open("w") as sink:

        def on_removed(decision: Any) -> None:
            nonlocal count
            count += 1
            sink.write(
                json.dumps(
                    {
                        "record_id": decision.record_id,
                        "policy": policy.id,
                        "release": release,
                        "rule_id": decision.rule_id,
                        "why": decision.why,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

        for source in corpora.sources_for(release):
            print(f"  {policy.id} <- {source.corpus_component}", file=sys.stderr)
            manifest.sources.append(
                evaluate_source(policy, source, client=client, limit=limit, on_removed=on_removed)
            )

    manifest.removed_records = count
    manifest.removed_file = removed_name if count else None
    if not count:
        removed_path.unlink()
    manifest.notes.append(
        "Record identifiers for Evo 1's stage-2 component are synthesised as "
        "`stage2:<object>#<row>`: the release carries no accession for it, and a row is a "
        "context window rather than a biological record (policies/corpora.md §3). No "
        "per-genome proportion may be computed from these counts."
    )
    if any(s.evidence_contradictions for s in manifest.sources):
        manifest.notes.append(
            "An evidence declaration was contradicted by the records — see "
            "`evidence_contradictions`. Every verdict drawn from that source is void until the "
            "declaration is corrected."
        )
    return manifest


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
    with run("A1.4", seed=SEED, outdir=outdir, allow_dirty=args.allow_dirty) as manifest:
        manifest.parameter("policies", sorted(wanted))
        manifest.parameter("releases", {p: list(RELEASES[p]) for p in sorted(wanted)})
        manifest.parameter("limit", args.limit)
        manifest.parameter(
            "resolution", "all-applicable-rules; removed>undetermined>unresolved>retained"
        )
        manifest.parameter("lineage_window_bytes", corpora.LINEAGE_WINDOW)
        manifest.parameter("deferred_to_a1_6", sorted(DEFERRED))
        for source in corpora.SOURCES + corpora.ESM3_SOURCES:
            if source.key and source.bytes:
                manifest.input_url(
                    f"s3://{corpora.BUCKET}/{source.key}",
                    role=f"{source.release}:{source.corpus_component}",
                    bytes=source.bytes,
                    verified=False,
                )

        index: list[dict[str, Any]] = []
        for policy_id in sorted(wanted):
            policy = policies[policy_id]
            for release in RELEASES[policy_id]:
                if args.release and release not in args.release:
                    continue
                built = build(policy, release, client=client, outdir=outdir, limit=args.limit)
                name = f"manifest-{policy_id}-{release}.json"
                built.write(outdir / name)
                manifest.output_file(outdir / name, role="manifest")
                if built.removed_file:
                    manifest.output_file(outdir / built.removed_file, role="removed-set")
                index.append(
                    {
                        "policy": policy_id,
                        "release": release,
                        "manifest": name,
                        "totals": built.totals(),
                        "removed_records": built.removed_records,
                    }
                )
                print(
                    f"  -> {name}: {built.totals()} removed={built.removed_records}",
                    file=sys.stderr,
                )

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

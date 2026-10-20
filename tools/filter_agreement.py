#!/usr/bin/env python3
"""Apply both filters' predicates to one corpus and cross-tabulate — task A8.1, DESIGN.md §A8.

    pixi run -e dev python tools/filter_agreement.py --tier uniref90 --taxdump taxdmp.zip
    pixi run -e dev python tools/filter_agreement.py --tier uniref50 --source local.xml.gz

One tier per run, as `seed_exclusivity.py` does and for the same reason: the two tiers are
independent forward reads, each wants the whole worker pool, and the launcher invokes this
once per tier.

`amazebio.agreement` holds the predicates and what they do not claim; this is the pass that
drives them over a staged tier. Read that module's docstring before this one — in particular
the three things the choice of corpus bounds, and why `label_only` is empty before the pass
begins rather than as a result of it.

What the two tiers buy. The similarity side is cluster co-membership, so the tier *is* the
threshold: UniRef90 is the predicate at 90% identity and UniRef50 at 50%. §A8's requirement
to report across a range rather than at a single assumed value is met by running both, and
the range is the publisher's own rather than a value we picked for a threshold nobody
published. A1.6's banded curve sweeps our range; this sweeps theirs. Neither is the other.

The label side does not vary at all, and that is worth a line in the artefact. All three Evo
readings carry the same two taxon rules and the same specificity rule; they differ only in
rules that read IMG/VR metadata, which a protein corpus does not carry. So on this corpus the
three readings are one predicate, and the reading ambiguity A0.3 measured has no effect here.

Reads 63 GB for the 90 tier and 30 GB for the 50, so it is meant to run in us-east-1 where
that transfer is free. `--source` accepts a local path, which is how the path is tested end
to end before an instance is paid for.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import agreement, objectstore, policyspec, repro, seeds, selectagents, uniref

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"
CHUNK = 8 << 20
TASK = "A8.1"

#: Tiers this pass can read, and the identity each one's co-membership stands for. UniRef100
#: is excluded for the reason `seed_exclusivity.py` excludes it: it is the tier the seed set
#: was built from, so its clusters are the seeds and the question is vacuous.
TIERS = {"uniref90": 0.90, "uniref50": 0.50}

#: The readings whose taxon rules this pass executes. All three, because they are the same
#: three rules — verified at run time rather than asserted here, since a spec edit that broke
#: it would otherwise turn one predicate into a silently-wrong three.
READINGS = ("evo1-literal", "evo1-charitable", "evo1-strict")

#: Rule kinds a protein corpus can answer. Everything else is declared as not runnable and
#: named in the artefact, so the output says what was left out instead of implying a whole
#: pipeline ran.
RUNNABLE = ("remove_if_taxon_in", "remove_if_unspecific")


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def taxon_rules(policies: dict[str, policyspec.Policy]) -> dict[str, Any]:
    """The rules a protein corpus can run, and a refusal if the readings disagree about them.

    The whole claim that this pass measures "Evo's predicate" rather than "one reading of
    Evo's predicate" rests on the three readings carrying identical taxon rules. That was true
    when A8.1 was written. It is checked here because a later spec edit would otherwise make
    the artefact quietly wrong about which readings it covers.
    """
    shapes: dict[str, Any] = {}
    not_runnable: list[tuple[str, str]] = []
    for reading in READINGS:
        policy = policies[reading]
        runnable = [r for r in policy.rules if r.kind in RUNNABLE]

        def named(suffix: str, rules: list[Any] = runnable) -> tuple[str, ...]:
            return tuple(next(r.params["names"] for r in rules if r.id.endswith(suffix)))

        shape = {"families": named("families"), "orders": named("orders")}
        unspecific = next(r for r in runnable if r.kind == "remove_if_unspecific")
        shape["stop_taxa"] = tuple(unspecific.params["stop_taxa"])
        shape["require_rank"] = unspecific.params["require_rank"]
        shape["ranks"] = tuple(unspecific.params["ranks"])
        shapes[reading] = shape
        for rule in policy.rules:
            if rule.kind not in RUNNABLE:
                not_runnable.append((f"{reading}:{rule.id}", rule.kind))

    distinct = {json.dumps(s, sort_keys=True) for s in shapes.values()}
    if len(distinct) != 1:
        raise SystemExit(
            "the Evo readings no longer share one set of taxon rules, so this pass cannot "
            "report a verdict that covers all three; split the run by reading first"
        )
    shape = shapes[READINGS[0]]
    return {**shape, "readings": READINGS, "not_runnable": tuple(sorted(set(not_runnable)))}


def other_names(taxdump: Path) -> dict[str, list[int]]:
    """Every non-scientific name in the dump, so a renamed taxon can be reported as renamed.

    `NameIndex` keeps scientific names only, which is right for looking a taxid up. Here the
    question runs the other way — the rules hand over a word, and whether the dump carries
    that word as a current name, an old one, or not at all is the finding.
    """
    out: dict[str, list[int]] = {}
    with zipfile.ZipFile(taxdump) as archive, archive.open("names.dmp") as handle:
        for raw in handle:
            fields = [c.strip() for c in raw.decode("utf-8", "replace").split("\t|")]
            if len(fields) > 3 and fields[3] != "scientific name":
                try:
                    out.setdefault(fields[1], []).append(int(fields[0]))
                except ValueError:
                    continue
    return out


def _make_heartbeat(client: Any, bucket: str, prefix: str, name: str, commit: str | None) -> Any:
    """Publish progress to object storage on an interval, best-effort.

    A running instance cannot be inspected here, and a quiet console cannot be told apart
    from a dead process (`AGENTS.md`; D-127). Its own key, overwritten each time, because a
    heartbeat is not a deliverable and a failure to publish one must never fail the run.
    """
    key = f"{prefix}/heartbeat/{name}.json"
    started = time.time()

    def beat(read: int, elapsed: float, **extra: Any) -> None:
        body = {
            "name": name,
            "code_commit": commit,
            "started_epoch": round(started, 1),
            "now_epoch": round(time.time(), 1),
            "decompressed_bytes": read,
            "elapsed_seconds": round(elapsed, 1),
            "bytes_per_second": round(read / elapsed) if elapsed else None,
            **extra,
        }
        try:
            client.put_object(
                Bucket=bucket, Key=key, Body=json.dumps(body, sort_keys=True).encode()
            )
        except Exception as exc:  # A failed heartbeat must never fail the run it reports on.
            print(f"    heartbeat failed: {type(exc).__name__}", flush=True)

    return beat


def _chunks(
    stream: Any,
    limit: int,
    progress_seconds: float,
    heartbeat: Any = None,
    heartbeat_seconds: float = 300.0,
) -> Any:
    """Yield decompressed chunks, reporting progress to stdout and object storage."""
    read = 0
    started = time.monotonic()
    last = started
    last_beat = started
    while True:
        if limit and read >= limit:
            print(f"    stopping at --limit-bytes {human(limit)}", flush=True)
            return
        want = CHUNK if not limit else min(CHUNK, limit - read)
        chunk = stream.read(want)
        if not chunk:
            return
        read += len(chunk)
        now = time.monotonic()
        if progress_seconds and now - last >= progress_seconds:
            rate = read / max(now - started, 1e-9)
            print(f"    {human(read)} decompressed, {human(rate)}/s", flush=True)
            last = now
        if heartbeat is not None and now - last_beat >= heartbeat_seconds:
            heartbeat(read, now - started)
            last_beat = now
        yield chunk


def _open_tier(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> tuple[Any, str]:
    if args.source:
        return open(args.source, "rb"), str(args.source)
    rel = uniref.RELEASES[args.release]
    key = f"{prefix}/uniref/{rel.release}/{args.tier}.tar/{args.tier}.xml.gz"
    reader = uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {human(pos)}: {type(exc).__name__}", flush=True
        ),
    )
    return reader, f"s3://{bucket}/{key}"


def summarise(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    cells = counts["cells"]
    out = [
        f"{payload['tier']} — the similarity predicate at {payload['identity']:.0%} identity, "
        f"against Evo's taxon rules",
        f"  {counts['clusters']:,} clusters, {counts['members']:,} records",
        f"  out of scope (not viral, so Evo's filter never sees them): "
        f"{counts['out_of_scope_members']:,}, of which "
        f"{cells[agreement.CELL_OUT_OF_SCOPE_REMOVED]:,} removed by similarity anyway",
        f"  of the {counts['judged_members']:,} records both predicates judge:",
    ]
    for cell in (
        agreement.CELL_BOTH,
        agreement.CELL_NEITHER,
        agreement.CELL_SIMILARITY_ONLY,
        agreement.CELL_LABEL_ONLY,
    ):
        out.append(f"    {cell:<16} {cells[cell]:,}")
    share = counts["agreement"]
    out.append(f"  agreement: {share:.4f}" if share is not None else "  agreement: no records")
    for name, how, _ in payload["name_resolution"]:
        if how == "scientific name":
            continue
        out.append(
            f"  the rules name {name}, which the pinned taxonomy carries as a {how}: "
            f"read as written that rule removes nothing, and a looser reading would "
            f"reach {counts['loose_only_members']:,} further records"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", choices=sorted(uniref.RELEASES), default="2023_02")
    ap.add_argument("--tier", choices=sorted(TIERS), required=True)
    ap.add_argument(
        "--taxdump",
        required=True,
        type=Path,
        help=f"dated NCBI taxonomy zip; pinned release is {seeds.TAXDUMP_2023_04.date}",
    )
    ap.add_argument("--specs", type=Path, default=Path("policies/specs"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--source", help="local .xml.gz to read instead of S3 — for testing")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a8-1"))
    ap.add_argument(
        "--limit-bytes",
        type=int,
        default=0,
        help="stop after this many decompressed bytes. UniRef is ordered by accession, so a "
        "prefix is not a sample and the artefact is marked accordingly",
    )
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    ap.add_argument("--batch-bytes", type=int, default=8 << 20)
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    ap.add_argument("--heartbeat-seconds", type=float, default=300.0)
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        help="the commit this code came from. An instance has no checkout, so a manifest "
        "that omits it cannot be traced to the code that produced the numbers",
    )
    args = ap.parse_args(argv)

    client = None
    bucket = prefix = ""
    if not args.source or args.upload_results:
        if not args.s3_uri:
            raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI (or --source without upload)")
        bucket, _, prefix = args.s3_uri[5:].partition("/")
        prefix = prefix.strip("/")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT,
            config=Config(retries={"max_attempts": 10, "mode": "standard"}),
        )

    try:
        return _execute(args, client, bucket, prefix)
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.release}-{args.tier}"
    out_path = args.outdir / f"agreement-{stem}.json"

    rules = taxon_rules(policyspec.load_policy_dir(args.specs))
    print(f"loading taxonomy from {args.taxdump}", flush=True)
    index = selectagents.NameIndex.from_taxdump_zip(args.taxdump)
    taxonomy = seeds.Taxonomy(index.parent, index.rank)
    synonyms = other_names(args.taxdump)
    predicate = agreement.build_predicate(
        taxonomy=taxonomy,
        names=index.names,
        family_names=rules["families"],
        order_names=rules["orders"],
        stop_taxa=rules["stop_taxa"],
        require_rank=rules["require_rank"],
        ranks=rules["ranks"],
        rules_not_runnable=rules["not_runnable"],
        synonyms=synonyms,
    )
    for name, how, _ in predicate.resolution:
        if how != "scientific name":
            print(f"  NAME NOT AS WRITTEN: {name} is a {how}", flush=True)
    print(
        f"  {len(taxonomy.parent):,} taxa, {len(predicate.viral):,} viral, "
        f"{len(predicate.removed):,} removed by the taxon rules",
        flush=True,
    )

    with repro.run(
        TASK,
        seed=None,  # one forward read of a pinned object: nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-agreement-{args.tier}.json",
        durable=objectstore.durable_results("a8-1"),
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("release", args.release)
        manifest.parameter("tier", args.tier)
        manifest.parameter("identity", TIERS[args.tier])
        manifest.parameter("readings", list(rules["readings"]))
        manifest.parameter("viral_root", seeds.VIRAL_ROOT)
        manifest.parameter("taxdump_pin", seeds.TAXDUMP_2023_04.date)
        manifest.parameter("workers", args.workers)
        manifest.parameter("limit_bytes", args.limit_bytes)
        manifest.input_file(args.taxdump, role="taxonomy")
        manifest.note(
            "The similarity side is cluster co-membership at the tier's identity, not an "
            "alignment against the whole of UniProt: it is the publisher's own grouping of "
            "exactly these records, used as a proxy for a threshold ESM3-open never "
            "published (D-015). A1.6's banded curve sweeps our stated range; this sweeps "
            "the publisher's two identities. Neither is presented as the other."
        )
        manifest.note(
            "Only Evo's taxon rules run here. The rest of its pipeline reads IMG/VR "
            "metadata — a confidence label, a vOTU, a host count — that a protein corpus "
            "does not carry, and those rules are named in rules_not_runnable rather than "
            "silently skipped. This measures the predicates, not the deployments: the two "
            "filters were applied to different corpora in their original use."
        )

        reader, label = _open_tier(args, client, bucket, prefix)
        print(f"reading {label}", flush=True)
        if args.source:
            manifest.input_file(args.source, role="tier")
        else:
            manifest.parameter("tier_object", label)

        heartbeat = None
        if client is not None and not args.source:
            heartbeat = _make_heartbeat(
                client, bucket, prefix, f"a8-1-agreement-{args.tier}", args.code_commit
            )

        counts = agreement.AgreementCounts()
        config = agreement.AgreementConfig(predicate=predicate)
        stream = uniref.GunzipStream(reader)
        started = time.monotonic()
        for batch in seeds.scan_parallel(
            _chunks(
                stream,
                args.limit_bytes,
                args.progress_seconds,
                heartbeat,
                args.heartbeat_seconds,
            ),
            config,
            workers=args.workers,
            batch_bytes=args.batch_bytes,
        ):
            counts.merge(batch)
        elapsed = time.monotonic() - started
        agreement.check_dominance(counts)

        # `GunzipStream` exposes these as attributes rather than `tell()`; a `tell` lookup
        # silently yields 0, which reads as "nothing was read" on a pass that read the tier.
        compressed = getattr(stream, "compressed_bytes", 0)
        decompressed = getattr(stream, "read_bytes", 0)
        detail = counts.to_dict()
        kinds = detail["kind_by_cell"][agreement.CELL_OUT_OF_SCOPE_REMOVED]  # type: ignore[index]
        payload = {
            "task": TASK,
            "design_ref": "§A8",
            "release": args.release,
            "tier": args.tier,
            "identity": TIERS[args.tier],
            "bounded": bool(args.limit_bytes),
            "readings": list(rules["readings"]),
            "label_rules": {
                "families": list(rules["families"]),
                "orders": list(rules["orders"]),
                "stop_taxa": list(rules["stop_taxa"]),
                "require_rank": rules["require_rank"],
            },
            "rules_not_runnable": [list(p) for p in rules["not_runnable"]],
            "name_resolution": [list(r) for r in predicate.resolution],
            "loose_reading_taxa": len(predicate.loose_only),
            "counts": detail,
            "cellular_in_covering_clusters": kinds[agreement.KIND_CELLULAR],
            "compressed_bytes_read": compressed,
            "decompressed_bytes_read": decompressed,
            "elapsed_seconds": round(elapsed, 1),
            "decompressed_bytes_per_second": (round(decompressed / elapsed) if elapsed else None),
            "taxdump": {
                "date": seeds.TAXDUMP_2023_04.date,
                "sha256": seeds.TAXDUMP_2023_04.sha256,
            },
            "confound": (
                "The two filters were applied to different corpora in their original use — "
                "nucleotide genomes against a protein database. Running both over one corpus "
                "measures the predicates and not the deployments."
            ),
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        manifest.output_file(out_path, role="agreement")
        if args.limit_bytes:
            manifest.note(
                "BOUNDED RUN: stopped at --limit-bytes. UniRef is ordered by accession, so "
                "this read a prefix rather than a sample and no share here estimates the "
                "tier's."
            )
        if hasattr(reader, "close"):
            reader.close()
        print("\n" + summarise(payload), flush=True)

    # Uploads happen after the run block: `run.json` is written by the manifest's exit
    # handler, so an upload inside the block would miss it.
    if args.upload_results and client is not None:
        tag = args.code_commit or "nocommit"
        for path, role in (
            (out_path, "agreement"),
            (args.outdir / f"run-agreement-{args.tier}.json", "manifest"),
        ):
            if not path.exists():
                print(f"not uploaded (absent): {path}")
                continue
            # The commit is in the key because this bucket has no DeleteObject, so an
            # overwrite destroys the earlier object irreversibly (D-126's reasoning).
            key = f"{prefix}/results/a8-1/{args.release}/{args.tier}/{role}-{tag}.json"
            client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
            print(f"uploaded s3://{bucket}/{key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build ESM3-open's select-agent denylist seed set from a staged UniRef tier — task A1.8.

The companion to `esm3_seeds.py`, which builds the viral denylist. Same pass, same machinery
in `amazebio.seeds`, one difference that matters: where the viral arm's taxid set is a single
subtree — everything under Viruses — this one is the output of a reading, and the reading has
to travel with the number.

**Why the provenance here is heavier than the viral arm's.** "Everything under taxid 10239" is
reproducible from one integer. The select-agent list is regulatory prose whose entries are not
taxon names, and D-137 records five distinct ways a name-matching implementation gets it wrong
— including one that silently maps a hemorrhagic-fever entry to a genus of flowering plants. So
this tool pins the regulation by digest, pins the curated reading table by digest, and writes
both into the manifest along with the count of list entries that contribute no taxon at all.
A seed count from here is not interpretable without those, which is why they are not optional.

**It reconciles against a published total, and is not expected to match it.** ESM3 states the
denylist is 147K non-viral plus 40K additional viral sequences, 187K in total (D-106). That is
the validation target in the way ~4M is for the viral arm (D-100), but the gap is informative
rather than a pass/fail: 16 of the 70 list entries contribute no taxon under the literal
reading — nine toxins, two constructs, one functional predicate, four absent from the pinned
taxonomy — which pushes our count down, while three deliberately over-inclusive readings push
it up. The run prints the reconciliation with both directions named rather than a bare delta.

**The denominator needs the whole tier, which is why this is not run against the sample.** The
pass that scores sequences is sampled (D-133), but a seed set rebuilt from 2.5% of the corpus
cannot be compared with a published total, so this one reads the tier in full. That is about
133.5 G residues of decompressed UniRef100 and one forward read of a `.xml.gz` object — in-region
work by the test in AGENTS.md, and about an hour.

A gzip stream cannot be decompressed in parallel, so one tier is one process however many cores
the machine has, exactly as for the viral arm.

**Shipping it.** The instance has no checkout, so the three CFR captures and the reading table
have to be in the launcher's payload alongside the modules. They are data rather than imports,
so the import-closure derivation that `tests/test_ec2_similarity.py` enforces will not catch
them being left out — `--check-inputs` exists to fail in a second on the instance, before the
hour of reading, rather than at the end of it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import repro, seeds, selectagents, uniref
from amazebio.repro import ReproError

S3_REGION = "us-east-1"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
CHUNK = 8 << 20

#: ESM3's own figure for the select-agent denylist, from the version of record (D-106). The
#: reconciliation target, not an assertion: see the module docstring on why a match is not
#: expected in either direction.
PUBLISHED_SEQUENCES = 187_000

#: Which capture each list section is parsed from. 9 CFR 121.4 is deliberately absent — it
#: restates 42 CFR 73.4, and counting both would double every overlap agent.
SECTION_FILES = {
    "73.3": "cfr-title42-part73-2024-06-01.xml",
    "73.4": "cfr-title42-part73-2024-06-01.xml",
    "121.3": "cfr-title9-part121-2024-06-01.xml",
    "331.3": "cfr-title7-part331-2024-06-01.xml",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAPTURES = REPO_ROOT / "policies" / "captures"
DEFAULT_MAPPING = REPO_ROOT / "policies" / "specs" / "select-agents-2024-06-01.json"


def required_data_files() -> tuple[str, ...]:
    """Repo-relative data files this pass cannot run without.

    The launcher ships these, and it asks here rather than keeping its own list. Nothing
    imports them, so the first-party import closure that guards a launcher's module list is
    structurally blind to them — and a missing data file kills the instance exactly like a
    missing module, a minute in, with the hour of corpus reading wasted. One list, in the
    place that reads them, so adding a CFR part cannot fail to ship it.
    """
    files = {f"policies/captures/{name}" for name in SECTION_FILES.values()}
    files.add(str(DEFAULT_MAPPING.relative_to(REPO_ROOT)))
    return tuple(sorted(files))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_reading(
    captures: Path, mapping_path: Path, *, toxin_producers: bool, alternatives: bool
) -> tuple[selectagents.SeedTaxa, dict[str, Any]]:
    """Build the taxid set and the provenance that makes it interpretable.

    Returns the taxa and a dict recording the reading: which regulation, at which digest,
    under which table, with how many entries contributing nothing. The second return value is
    the part that cannot be left out of a manifest — see the module docstring.
    """
    missing = [
        name for name in sorted(set(SECTION_FILES.values())) if not (captures / name).exists()
    ]
    if missing:
        raise SystemExit(
            f"missing pinned CFR capture(s) in {captures}: {', '.join(missing)}. "
            "The instance has no checkout, so these travel in the launcher's payload."
        )
    if not mapping_path.exists():
        raise SystemExit(f"missing the curated reading table at {mapping_path} (D-137)")

    for pin in selectagents.PINS_2024:
        stored = Path(captures) / Path(pin.capture).name
        found = digest(stored)
        if found != pin.sha256:
            raise SystemExit(
                f"{stored.name} does not match its recorded digest: expected {pin.sha256}, "
                f"found {found}. Refusing rather than reconstructing from unknown bytes."
            )

    entries = selectagents.parse_all(
        (section, (captures / name).read_bytes()) for section, name in SECTION_FILES.items()
    )
    mapping = selectagents.load_mapping(mapping_path)
    taxa = selectagents.seed_taxa(
        entries,
        mapping,
        include_toxin_producers=toxin_producers,
        use_alternatives=alternatives,
    )
    # Counted from the taxa rather than as `len(entries) - len(unresolved)`. A heading entry
    # ("South American hemorrhagic fever viruses:") contributes no taxon but is not one of the
    # four kinds `unresolved()` reports, because its content is the sub-entries below it rather
    # than something we failed to represent — so the subtraction overstates by one and the
    # arithmetic stops closing against `named_taxa`.
    unresolved = selectagents.unresolved(entries, mapping)
    by_kind: dict[str, int] = {}
    for entry in entries:
        mapped = mapping[entry.key]
        if not mapped.taxids:
            by_kind[mapped.kind.value] = by_kind.get(mapped.kind.value, 0) + 1
    naming = sum(1 for entry in entries if mapping[entry.key].taxids)

    provenance = {
        "list_as_of": selectagents.PINS_2024[0].as_of,
        "cfr_parts": [
            {
                "title": pin.title,
                "part": pin.part,
                "as_of": pin.as_of,
                "effective": pin.effective,
                "sha256": pin.sha256,
            }
            for pin in selectagents.PINS_2024
        ],
        "mapping_sha256": digest(mapping_path),
        "taxdump_pin": seeds.TAXDUMP_2023_04.date,
        "reading": {
            "toxin_producers": bool(toxin_producers),
            "alternatives": bool(alternatives),
        },
        "list_entries": len(entries),
        "entries_naming_taxa": naming,
        "entries_contributing_no_taxon": len(entries) - naming,
        "no_taxon_by_kind": by_kind,
        #: The subset of the above that we could not represent, as opposed to headings whose
        #: content sits in their sub-entries. This is the number the write-up owes a reader:
        #: which listed agents the seed set cannot speak for.
        "entries_unrepresentable": len(unresolved),
        "named_taxa": len(taxa.named),
        "named_taxa_descended": len(taxa.descend),
        "named_taxa_exact": len(taxa.exact),
    }
    return taxa, provenance


def reconcile(seeded: int) -> dict[str, Any]:
    """Compare the rebuilt count with the published figure, with both biases named.

    A bare delta would invite reading a shortfall as a reconstruction failure. Under-count and
    over-count have known, separate causes here (D-137), and both are stated so the number is
    read as evidence rather than as a score.
    """
    delta = seeded - PUBLISHED_SEQUENCES
    return {
        "published_sequences": PUBLISHED_SEQUENCES,
        "published_source": "D-106, ESM3 version of record: 147K non-viral + 40K viral",
        "rebuilt_sequences": seeded,
        "delta": delta,
        "delta_share": (delta / PUBLISHED_SEQUENCES if PUBLISHED_SEQUENCES else None),
        "known_downward_pressure": (
            "entries contributing no taxon: toxins under the literal reading, laboratory "
            "constructs, one functional predicate, and agents absent from the pinned taxonomy"
        ),
        "known_upward_pressure": (
            "deliberate over-inclusions where the taxonomy cannot express the regulation's "
            "restriction: avian influenza, Newcastle disease, the two Mycoplasma entries, and "
            "tick-borne encephalitis virus"
        ),
        "note": (
            "A match is not expected in either direction and a mismatch is not a failure. "
            "Compared against UniRef clusters, not UniProtKB entries, so the "
            "representative-versus-member gap in amazebio.seeds applies here too."
        ),
    }


def _chunks(stream: Any, limit: int, progress_seconds: float) -> Any:
    """Yield decompressed chunks, reporting progress on an interval.

    A step with no heartbeat is a step whose silence means nothing at all (AGENTS.md): this
    pass runs for about an hour on a machine with no shell and a best-effort console.
    """
    last = time.monotonic()
    started = last
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            return
        yield chunk
        now = time.monotonic()
        if progress_seconds and now - last >= progress_seconds:
            read = getattr(stream, "tell", lambda: 0)() or 0
            rate = read / (now - started) if now > started else 0
            print(
                f"  {read / 1e9:.1f} GB decompressed, {rate / 1e6:.1f} MB/s",
                flush=True,
            )
            last = now
        if limit and (getattr(stream, "tell", lambda: 0)() or 0) >= limit:
            return


def _open_tier(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> tuple[Any, str]:
    """Return (reader, label). The reader is forward-only with .read(n).

    The same key layout and the same reconnect reporting as the viral arm, deliberately: the
    reconnect line is what made the degrading-read failure in D-127 diagnosable, and a pass
    this long on an unobservable instance should not be the one that drops it.
    """
    if args.source:
        return open(args.source, "rb"), str(args.source)
    key = f"{prefix}/uniref/{args.release}/{args.tier}.tar/{args.tier}.xml.gz"
    reader = uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {pos / 1e9:.1f} GB: {type(exc).__name__}", flush=True
        ),
    )
    return reader, f"s3://{bucket}/{key}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", choices=sorted(uniref.RELEASES), default="2023_02")
    ap.add_argument(
        "--tier",
        default="uniref100",
        choices=["uniref50", "uniref90", "uniref100"],
        help="UniRef100 is the only tier covering every UniProtKB entry, which is what "
        "'sequences in UniProt belonging to organisms on the list' is about "
        "(default: %(default)s)",
    )
    ap.add_argument("--taxdump", required=True, type=Path)
    ap.add_argument(
        "--captures",
        type=Path,
        default=DEFAULT_CAPTURES,
        help="directory holding the pinned CFR XML captures (default: %(default)s)",
    )
    ap.add_argument(
        "--mapping",
        type=Path,
        default=DEFAULT_MAPPING,
        help="the curated reading table, D-137 (default: %(default)s)",
    )
    ap.add_argument(
        "--toxin-producers",
        action="store_true",
        help="switch the nine toxin entries from the literal reading — ESM3 says 'organisms', "
        "a toxin is not one — to their producing organisms. A sensitivity, not a default "
        "(D-137)",
    )
    ap.add_argument(
        "--alternatives",
        action="store_true",
        help="take the broader or narrower reading recorded against an entry where one was "
        "declined (D-137)",
    )
    ap.add_argument(
        "--check-inputs",
        action="store_true",
        help="resolve the taxid set, verify every pinned digest, print the reading and exit "
        "without reading the corpus. Run this on the instance before the hour-long pass: a "
        "missing data file costs a second here and an hour and a launch there",
    )
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--source", help="local .xml.gz to read instead of S3")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-8"))
    ap.add_argument(
        "--limit-bytes",
        type=int,
        default=0,
        help="stop after this many DECOMPRESSED bytes. Exercises the path and measures "
        "throughput; it does not produce a seed set, and the artefact says so. UniRef is "
        "ordered by accession, so a prefix is not a sample and no share measured from one "
        "estimates the tier's",
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        help="the commit this code came from; an instance has no checkout and cannot "
        "discover it, and a manifest without it cannot be traced to the code behind it",
    )
    ap.add_argument("--progress-seconds", type=float, default=120.0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    ap.add_argument("--batch-bytes", type=int, default=8 << 20)
    args = ap.parse_args(argv)

    taxa, provenance = load_reading(
        args.captures,
        args.mapping,
        toxin_producers=args.toxin_producers,
        alternatives=args.alternatives,
    )

    print(f"loading taxonomy from {args.taxdump}", flush=True)
    taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
    denylist = taxa.expand(taxonomy)
    provenance["expanded_taxa"] = len(denylist)
    print(
        f"  {len(taxonomy.parent):,} taxa; the list names {len(taxa.named):,}, "
        f"expanding to {len(denylist):,}",
        flush=True,
    )
    print(
        f"  {provenance['entries_contributing_no_taxon']} of "
        f"{provenance['list_entries']} list entries contribute no taxon "
        f"({provenance['no_taxon_by_kind']})",
        flush=True,
    )

    if args.check_inputs:
        print(json.dumps(provenance, indent=2, sort_keys=True))
        print("inputs resolve; exiting before the corpus pass as asked", flush=True)
        return 0

    client = None
    bucket = prefix = ""
    if not args.source:
        if not args.s3_uri:
            raise SystemExit("need --s3-uri, $AMAZEBIO_S3_URI, or --source")
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
        return _execute(args, client, bucket, prefix, denylist, provenance)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


def _execute(
    args: argparse.Namespace,
    client: Any,
    bucket: str,
    prefix: str,
    denylist: frozenset[int],
    provenance: dict[str, Any],
) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    fasta_path = args.outdir / f"select-agent-seeds-{args.release}-{args.tier}.faa"
    counts_path = args.outdir / f"seed-counts-{args.release}-{args.tier}.json"

    with repro.run(
        "A1.8",
        seed=None,  # one forward read of a pinned object: nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-select-agent-seeds-{args.tier}.json",
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("release", args.release)
        manifest.parameter("tier", args.tier)
        manifest.parameter("limit_bytes", args.limit_bytes)
        manifest.parameter("workers", args.workers)
        for key, value in provenance.items():
            manifest.parameter(f"list_{key}" if key == "reading" else key, value)
        manifest.input_file(args.taxdump, role="taxonomy")
        manifest.input_file(args.mapping, role="select-agent-reading-table")
        for pin in selectagents.PINS_2024:
            capture = args.captures / Path(pin.capture).name
            manifest.input_file(capture, role=f"cfr-title{pin.title}-part{pin.part}")

        reader, label = _open_tier(args, client, bucket, prefix)
        print(f"reading {label}", flush=True)
        if args.source:
            manifest.input_file(args.source, role="corpus")
        else:
            manifest.parameter("corpus_object", label)

        counts = seeds.SeedCounts()
        started = time.monotonic()
        stream = uniref.GunzipStream(reader)
        config = seeds.ScanConfig(denylist_taxids=frozenset(denylist))
        # The reader is closed explicitly rather than left to the garbage collector. On a
        # bounded or failed run the generator stops early and the descriptor would otherwise
        # survive to be reaped later, which `--limit-bytes` turns from a tidiness point into a
        # real leak — and on an instance with no shell, a leaked S3 reader is a connection
        # nobody can see holding open.
        try:
            with open(fasta_path, "wb") as fasta:
                for batch in seeds.scan_parallel(
                    _chunks(stream, args.limit_bytes, args.progress_seconds),
                    config,
                    workers=args.workers,
                    batch_bytes=args.batch_bytes,
                ):
                    counts.merge(batch.counts)
                    for cluster_id, sequence in batch.seeds:
                        seeds.write_fasta(fasta, cluster_id, sequence)
            elapsed = time.monotonic() - started
            compressed = getattr(reader, "tell", lambda: 0)() or 0
            decompressed = getattr(stream, "tell", lambda: 0)() or 0
        finally:
            for handle in (stream, reader):
                closer = getattr(handle, "close", None)
                if callable(closer):
                    closer()

        bounded = bool(args.limit_bytes)
        payload: dict[str, Any] = {
            "release": args.release,
            "tier": args.tier,
            "bounded": bounded,
            "compressed_bytes_read": compressed,
            "decompressed_bytes_read": decompressed,
            "elapsed_seconds": round(elapsed, 1),
            "decompressed_bytes_per_second": (round(decompressed / elapsed) if elapsed else None),
            "list_provenance": provenance,
            "counts": counts.to_dict(),
        }
        # A bounded run's count is a prefix of the tier, so reconciling it against a published
        # total would compare a fragment with a whole and read as a 99% shortfall.
        payload["reconciliation"] = None if bounded else reconcile(counts.seeded)
        counts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

        manifest.output_file(fasta_path, role="select-agent-seed-set")
        manifest.output_file(counts_path, role="seed-counts")
        if bounded:
            manifest.note(
                "BOUNDED RUN: stopped at --limit-bytes, so the seed set is a prefix of the "
                "tier and not the seed set. Throughput is measurable from it; counts are not "
                "a result and the reconciliation is withheld."
            )

        print(
            f"\n{counts.clusters:,} clusters, {counts.seeded:,} seeded "
            f"({100 * (counts.seeded / counts.clusters if counts.clusters else 0):.4f}%)"
            f" in {elapsed:.0f}s",
            flush=True,
        )
        print(
            f"  representative not seeded: {counts.representative_not_seeded:,}"
            f"   mixed members: {counts.mixed:,}",
            flush=True,
        )
        if not bounded:
            rec = payload["reconciliation"]
            assert rec is not None
            print(
                f"  against the published {rec['published_sequences']:,}: "
                f"{rec['delta']:+,} ({100 * (rec['delta_share'] or 0):+.1f}%) — "
                "a match is not expected in either direction, see D-137",
                flush=True,
            )

        if args.upload_results and client is not None:
            for path, role in (
                (fasta_path, "select-agent-seed-set"),
                (counts_path, "seed-counts"),
            ):
                key = f"{prefix}/results/a1-8/{path.name}"
                client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
                manifest.output_object(f"s3://{bucket}/{key}", bytes=path.stat().st_size, role=role)
                print(f"  uploaded s3://{bucket}/{key}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

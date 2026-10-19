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

from amazebio import repro, seeds, selectagents, similarity, uniref
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


def load_attribution(
    captures: Path,
    mapping_path: Path,
    taxonomy: seeds.Taxonomy,
    *,
    toxin_producers: bool,
    alternatives: bool,
) -> tuple[seeds.Attribution, dict[str, int]]:
    """Which list entry each denylisted taxon came from, and how many each contributes.

    Separate from `load_reading` rather than folded into it because the pooled seed set is
    what the pass needs and this is what the *reconciliation* needs; keeping them apart
    leaves `load_reading`'s contract alone. Re-parsing the three captures costs milliseconds
    against the hour the pass spends reading corpus.

    The taxon counts come back alongside so the manifest records the expansion by entry even
    for entries no cluster turns out to carry — an entry contributing 100,000 taxa and no
    seeded cluster says something quite different from one contributing neither.
    """
    entries = selectagents.parse_all(
        (section, (captures / name).read_bytes()) for section, name in SECTION_FILES.items()
    )
    mapping = selectagents.load_mapping(mapping_path)
    taxa_by_entry = selectagents.expand_by_entry(
        entries,
        mapping,
        taxonomy,
        include_toxin_producers=toxin_producers,
        use_alternatives=alternatives,
    )
    counts = {entry: len(taxa) for entry, taxa in taxa_by_entry.items() if taxa}
    return seeds.Attribution.from_entry_taxa(taxa_by_entry), counts


UNIPROT_COUNTS = REPO_ROOT / "policies" / "specs" / "select-agents-2024-06-01-uniprot-counts.json"


def reconcile(
    seeded: int,
    entry_counts: seeds.EntryCounts | None = None,
    uniprot_counts: Path | None = None,
) -> dict[str, Any]:
    """Place the pass's count against the published figure — at the level that figure counts.

    **The two numbers are of different objects, and the earlier version of this function
    compared them anyway.** ESM3 publishes 187K for a denylist it built as "all sequences in
    UniProt belonging to organisms on the Select Agents and Toxins List" (version of record,
    A.6.1 p47). This pass counts UniRef100 clusters. Comparing the two produced an apparent
    5.8x discrepancy, every part of which was the mismatch, and a one-line caveat under the
    delta did not stop a worker building a hypothesis on top of it (D-150). A caveat that does
    not change the number it qualifies is not a safeguard, so the number is changed.

    So `query_set` reports the UniRef100 count as what it is — the set searched against the
    corpus, deliberately broader than the publisher's object because breadth is the
    conservative choice for an audit (D-092) — and the comparison against 187K is made against
    the same reading executed over UniProtKB, which `tools/uniprot_denylist_count.py` pins.
    That validates the reading in D-137; nothing published can validate the seed set, because
    every published size is of a different object.
    """
    out: dict[str, Any] = {
        "query_set_clusters": seeded,
        "query_set_note": (
            "UniRef100 clusters seeded by the denylist taxa: the set searched against the "
            "corpus. Not a reconstruction of the published denylist object and not comparable "
            "with its size (D-150)."
        ),
        "published_sequences": PUBLISHED_SEQUENCES,
        "published_source": "D-106, ESM3 version of record: 147K non-viral + 40K viral",
        "published_counts": "UniProtKB sequences, per the version of record A.6.1 p47",
        "known_downward_pressure": (
            "entries contributing no taxon: toxins under the literal reading, laboratory "
            "constructs, one functional predicate, and agents absent from the pinned taxonomy"
        ),
        "known_upward_pressure": (
            "deliberate over-inclusions where the taxonomy cannot express the regulation's "
            "restriction: avian influenza, Newcastle disease, the two Mycoplasma entries, and "
            "tick-borne encephalitis virus"
        ),
    }
    path = UNIPROT_COUNTS if uniprot_counts is None else uniprot_counts
    if path.exists():
        pinned = json.loads(path.read_text())
        sequences = pinned["sequences"]
        delta = sequences - PUBLISHED_SEQUENCES
        out["reading_against_published"] = {
            "uniprot_sequences": sequences,
            "uniprot_release": pinned.get("uniprot_release"),
            "delta": delta,
            "delta_share": (delta / PUBLISHED_SEQUENCES if PUBLISHED_SEQUENCES else None),
            "what_this_checks": (
                "whether the regulation's entries were resolved to the same organisms the "
                "lab resolved them to. It does not validate the UniRef100 seed set."
            ),
            "release_gap": pinned.get("release_gap"),
        }
    else:
        out["reading_against_published"] = None
        out["reading_against_published_note"] = (
            f"no pinned UniProtKB count at {path}; run tools/uniprot_denylist_count.py. "
            "Without it the published figure has nothing comparable to sit against."
        )
    if entry_counts is not None:
        out["by_entry"] = entry_counts.to_dict()
        out["largest_contributor"] = _largest_contributor(seeded, entry_counts)
    return out


def _largest_contributor(seeded: int, entry_counts: seeds.EntryCounts) -> dict[str, Any] | None:
    """The single entry carrying the most of the seed set alone, and the set without it.

    Named from the measurement rather than written into the source, so a re-pin that changes
    which entry dominates reports the new one instead of the one that dominated in 2026.
    `without` counts the clusters no other entry also claims, which is exactly what reading
    that entry differently would remove — not the entry's whole `claimed` total, part of
    which another entry would keep.
    """
    if not entry_counts.exclusive:
        return None
    entry, exclusive = entry_counts.exclusive.most_common(1)[0]
    return {
        "entry": entry,
        "exclusive_clusters": exclusive,
        "share_of_seed_set": (exclusive / seeded if seeded else None),
        "query_set_without_it": seeded - exclusive,
        "note": (
            "Which entry the query set leans on hardest, named from the measurement so a "
            "re-pin reports whichever entry then dominates. `query_set_without_it` is the "
            "count with this entry's exclusively-claimed clusters removed — those are the "
            "ones no other entry would keep. Deliberately not compared with the published "
            "figure: that counts UniProtKB sequences and this counts UniRef100 clusters "
            "(D-150)."
        ),
    }


def _chunks(stream: Any, limit: int, progress_seconds: float) -> Any:
    """Yield decompressed chunks, reporting progress on an interval.

    A step with no heartbeat is a step whose silence means nothing at all (AGENTS.md): this
    pass runs for about an hour on a machine with no shell and a best-effort console.

    The count is accumulated here, from the chunks actually yielded. An earlier version asked
    the stream with `getattr(stream, "tell", ...)` and a zero fallback — and `GunzipStream` has
    no `tell`, it exposes `read_bytes`. So every heartbeat printed `0.0 GB` forever, which is
    worse than printing nothing: a heartbeat that always reads zero cannot distinguish a wedged
    pass from a working one, and that reading cost four hours once already (D-127). The same
    fallback also silently disabled `--limit-bytes`, and the local test passed anyway because a
    one-chunk stream ends on its own before any limit matters.
    """
    read = 0
    last = time.monotonic()
    started = last
    while True:
        want = CHUNK if not limit else min(CHUNK, limit - read)
        if want <= 0:
            print(f"    stopping at --limit-bytes {limit:,}", flush=True)
            return
        chunk = stream.read(want)
        if not chunk:
            return
        read += len(chunk)
        yield chunk
        now = time.monotonic()
        if progress_seconds and now - last >= progress_seconds:
            rate = read / max(now - started, 1e-9)
            print(
                f"    {read / 1e9:.2f} GB decompressed, {rate / 1e6:.1f} MB/s",
                flush=True,
            )
            last = now


def _heartbeat(client: Any, bucket: str, prefix: str, args: argparse.Namespace) -> Any:
    """Return a function that publishes progress to object storage.

    AGENTS.md requires this of anything running longer than a few minutes, and the first
    attempt at this pass is why: it heartbeat only to the serial console, the console went
    quiet after four minutes, and with no second channel there was no way to tell a wedged
    pass from a working one — so a possibly healthy run was terminated to regain a diagnosis.
    A console is best-effort and has no guaranteed freshness; an object either appears or does
    not.

    **One key, overwritten.** The corpus bucket has no `DeleteObject`, so an interval that
    wrote a new key each beat would leave dozens of permanent objects per run — A1.3 left four
    behind that cannot be removed. Overwriting a single key destroys only the previous beat,
    which is exactly what a heartbeat is for, and keeps the permanent footprint at one object.
    """
    if client is None:
        return lambda _payload: None
    key = f"{prefix}/heartbeat/a1-8/{args.tier}-{args.release}.json"
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def publish(payload: dict[str, Any]) -> None:
        body = dict(payload)
        body["run_started_at"] = started
        body["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            client.put_object(Bucket=bucket, Key=key, Body=json.dumps(body, indent=2).encode())
        except Exception as exc:
            # A heartbeat that fails must not take the pass down with it: losing the
            # diagnosis is bad, losing an hour of reading is worse.
            print(f"    heartbeat failed: {type(exc).__name__}: {exc}", flush=True)

    return publish


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
    ap.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=120.0,
        help="how often to publish progress to object storage. A step with no "
        "heartbeat is a step whose silence means nothing (default: %(default)s)",
    )
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
    attribution, taxa_by_entry = load_attribution(
        args.captures,
        args.mapping,
        taxonomy,
        toxin_producers=args.toxin_producers,
        alternatives=args.alternatives,
    )
    provenance["expanded_taxa_by_entry"] = dict(
        sorted(taxa_by_entry.items(), key=lambda kv: (-kv[1], kv[0]))
    )
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
        return _execute(args, client, bucket, prefix, denylist, provenance, attribution)
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
    attribution: seeds.Attribution,
) -> int:
    args.outdir.mkdir(parents=True, exist_ok=True)
    fasta_path = args.outdir / f"select-agent-seeds-{args.release}-{args.tier}.faa"
    counts_path = args.outdir / f"seed-counts-{args.release}-{args.tier}.json"

    manifest_name = f"run-select-agent-seeds-{args.tier}.json"
    with repro.run(
        "A1.8",
        seed=None,  # one forward read of a pinned object: nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=manifest_name,
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
        config = seeds.ScanConfig(denylist_taxids=frozenset(denylist), attribution=attribution)
        entry_counts = seeds.EntryCounts()
        # The reader is closed explicitly rather than left to the garbage collector. On a
        # bounded or failed run the generator stops early and the descriptor would otherwise
        # survive to be reaped later, which `--limit-bytes` turns from a tidiness point into a
        # real leak — and on an instance with no shell, a leaked S3 reader is a connection
        # nobody can see holding open.
        beat = _heartbeat(client, bucket, prefix, args)
        last_beat = time.monotonic()
        # The strata sidecar, beside the FASTA for the reason D-142 gives: MMseqs2 keys on
        # the first whitespace-delimited token, so the seed FASTA carries a bare cluster id
        # and cannot hold a taxid. The band pass needs one per seed to report the realised
        # seed-family count that D-134 ships with every rate, and recovering it afterwards
        # would mean a second corpus pass.
        taxid_path = fasta_path.with_suffix(".taxids.tsv")
        try:
            with open(fasta_path, "wb") as fasta, open(taxid_path, "wb") as taxids:
                for batch in seeds.scan_parallel(
                    _chunks(stream, args.limit_bytes, args.progress_seconds),
                    config,
                    workers=args.workers,
                    batch_bytes=args.batch_bytes,
                ):
                    counts.merge(batch.counts)
                    if batch.entries is not None:
                        entry_counts.merge(batch.entries)
                    for cluster_id, sequence, taxid in batch.seeds:
                        seeds.write_fasta(fasta, cluster_id, sequence)
                        similarity.write_taxid_row(taxids, cluster_id, taxid)
                    now = time.monotonic()
                    if now - last_beat >= args.heartbeat_seconds:
                        beat(
                            {
                                "elapsed_seconds": round(now - started, 1),
                                "decompressed_bytes": getattr(stream, "read_bytes", 0),
                                "compressed_bytes": getattr(stream, "compressed_bytes", 0),
                                "clusters": counts.clusters,
                                "seeded": counts.seeded,
                            }
                        )
                        last_beat = now
            elapsed = time.monotonic() - started
            # `GunzipStream` counts both itself; it has no `tell`, and asking for one with a
            # zero fallback wrote a throughput of nought into the artefact while looking
            # perfectly reasonable in the source.
            compressed = getattr(stream, "compressed_bytes", 0)
            decompressed = getattr(stream, "read_bytes", 0)
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
        payload["seeded_by_entry"] = entry_counts.to_dict()
        # A bounded run's count is a prefix of the tier, so reconciling it against a published
        # total would compare a fragment with a whole and read as a 99% shortfall.
        payload["reconciliation"] = None if bounded else reconcile(counts.seeded, entry_counts)
        counts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

        manifest.output_file(fasta_path, role="select-agent-seed-set")
        manifest.output_file(taxid_path, role="select-agent-seed-strata")
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
            # The published 187K counts UniProtKB sequences and this pass counts UniRef100
            # clusters, so the two are never printed as a delta (D-150).
            reading = rec.get("reading_against_published")
            if reading is None:
                print(f"  {rec['reading_against_published_note']}", flush=True)
            else:
                print(
                    f"  the reading against the published {rec['published_sequences']:,} "
                    f"UniProtKB sequences: {reading['uniprot_sequences']:,} at release "
                    f"{reading['uniprot_release']} ({reading['delta']:+,}, "
                    f"{100 * (reading['delta_share'] or 0):+.1f}%). This checks the reading, "
                    "not the seed set",
                    flush=True,
                )
            top = rec.get("largest_contributor")
            if top is not None:
                print(
                    f"  largest single contributor: {top['entry']} — "
                    f"{top['exclusive_clusters']:,} clusters claimed by it alone "
                    f"({100 * (top['share_of_seed_set'] or 0):.1f}% of the query set)",
                    flush=True,
                )

        if args.upload_results and client is not None:
            for path, role in (
                (fasta_path, "select-agent-seed-set"),
                (taxid_path, "select-agent-seed-strata"),
                (counts_path, "seed-counts"),
            ):
                key = f"{prefix}/results/a1-8/{path.name}"
                client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
                manifest.output_object(f"s3://{bucket}/{key}", bytes=path.stat().st_size, role=role)
                print(f"  uploaded s3://{bucket}/{key}", flush=True)

    # Outside the block on purpose. `repro.run` writes the manifest on exit, so inside it
    # there is no file to upload — which is why the first pass left its results in the
    # bucket and its provenance on a terminated instance's disk. The instance has no
    # checkout and nobody can log in to fetch it, so a manifest that does not leave this way
    # does not leave at all, and an unprovenanced result is not citable (AGENTS.md).
    if args.upload_results and client is not None:
        local = args.outdir / manifest_name
        key = f"{prefix}/results/a1-8/{manifest_name}"
        client.put_object(Bucket=bucket, Key=key, Body=local.read_bytes())
        print(f"  uploaded s3://{bucket}/{key}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

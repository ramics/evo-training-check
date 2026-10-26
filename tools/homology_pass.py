"""Search the §B3 homology axis against one release's surviving records — B3.1 and B3.2.

The expensive half, kept separate from the assembly on purpose: this reads a corpus for hours
and `tools/homology_rows.py` turns what it wrote into `metrics/homology.md` rows in seconds. A
run that has to be repeated repeats the search, not the schema.

Two model sets are searched over the same called proteins in the same pass, because the cost
here is gene calling and reading, not the search:

* **B3.1** — the 28 target profiles `tools/homology_targets.py` built, at the pinned E-value
  against the pinned `Z` (D-076), held to `profiles.MIN_MODEL_COVERAGE` of the profile.
* **B3.2** — the Pfam models for the domain families annotated on those targets, at Pfam's own
  gathering cutoffs and the same coverage floor, which is exactly A2.1's acceptance rule. That
  is deliberate: it makes this pass's verdict on a family joinable to A2.1's detected set, and
  `tools/homology_rows.py` reports the agreement as a check on both.

**What "surviving" means here.** A1.4's manifests for both Evo releases are the release's viral
component with the reading's removals taken out, and the three readings remove the identical
record set on each release (A1.4, D-044), so one pass serves all three manifests and the
artefact says so rather than implying three searches happened. The removed identifiers are read
from A1.4's own removed set rather than re-derived.

**An interrupted pass degrades honestly.** The best-hit table is written every
`--checkpoint-records` records with the record count it is over and
`selection: prefix`. A prefix of an accession-ordered object is **not** a sample — A1.6 paid for
that lesson — so a partial is published as a prefix, and the rows built from it are lower
bounds whose `absent` cells say nothing about the rest of the corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, homology, objectstore, profiles, profilesearch, seqstream, uniref
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B3.1/B3.2"
SEED = 20261026
TARGETS = REPO / "artifacts" / "b3-targets" / "targets.json"
CANONICAL_OUT = REPO / "artifacts" / "b3-pass"

#: The component each release's A1.4 manifest enumerates. Both manifests are the viral
#: component; the other staged components are `out_of_scope` or unenumerated (A1.4).
VIRAL_COMPONENT = {"opengenome": "stage2", "opengenome2": "imgvr"}

#: Records each release's manifest holds, from A1.4's index. Pinned here so a pass that reads a
#: different number of records fails rather than quietly reporting a wrong denominator.
MANIFEST_RECORDS = {"opengenome": 2_653_047, "opengenome2": 2_957_495}

#: The fraction of each manifest's surviving records this pass searches, declared before any
#: result was looked at (D-258). A hash band, not a prefix: membership is a function of the
#: record identifier, so the band is a sample of the component rather than the front of it.
#: Ten to a hundred times A2.1's own detection depth, and a tenth of the census that measured
#: throughput puts at about seventeen hours of container time.
DEPTH = 0.1

#: The sampling seed is **A2.1's**, not this task's, and that is the whole of why the
#: cross-check in `tools/homology_rows.py` can be a must-hold rather than a coincidence.
#: Band membership is a hash threshold, so the sample at rate `r` is nested inside the sample
#: at any larger rate under the same seed (`amazebio.detect.in_band`). A2.1 searched [0, 0.02)
#: of Evo 1's component and [0, 0.01) of Evo 2's at seed 20261015; this pass searches
#: [0, 0.1) at the same seed, so **every record A2.1 searched is a record this pass searched**.
#: A fresh seed would have made the two independent samples and the join a weak consistency
#: check instead of a directional one. D-258.
SAMPLE_SEED = 20261015

#: The readings whose surviving set is identical on these releases (A1.4).
READINGS = ("evo1-literal", "evo1-charitable", "evo1-strict")


def load_targets(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{path} is missing; run tools/homology_targets.py first")
    return json.loads(path.read_text())


def removed_ids(client: Any, release: str) -> set[str]:
    """The identifiers A1.4's readings remove from this release, from A1.4's own removed set."""
    key = f"corpora/results/a1-4/removed-{READINGS[0]}-{release}.jsonl"
    try:
        body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=key)["Body"].read()
    except Exception:
        # A reading that removes nothing publishes no removed set. That is a result, not a
        # missing file (metrics/manifests.md), and on Evo 2 it is the expected one.
        return set()
    out = set()
    for line in body.decode().splitlines():
        if line.strip():
            out.add(json.loads(line)["record_id"])
    return out


def target_models(
    payload: dict[str, Any], *, profile_dir: Path
) -> tuple[list[Any], dict[str, list[str]]]:
    """The distinct target profiles, and which assays each one stands for."""
    import pyhmmer

    owners: dict[str, list[str]] = {}
    for entry in payload["targets"]:
        if entry["profile"]:
            owners.setdefault(entry["profile"]["profile"], []).append(entry["dms_id"])
    models = []
    for filename in sorted(owners):
        path = profile_dir / filename
        if not path.exists():
            raise SystemExit(f"{path} is missing; re-run tools/homology_targets.py")
        with pyhmmer.plan7.HMMFile(path) as handle:
            models.append(handle.read())
    return models, owners


def domain_models(
    payload: dict[str, Any], *, hmm_file: Path, out: Path
) -> tuple[list[Any], dict[str, list[str]]]:
    """The Pfam models for every annotated domain family, and which assays carry each.

    Extracted once into a small file so the pass does not re-read a 1.5 GB profile set per
    batch, and so `run.json` can pin the subset by digest rather than by the whole registry.
    """
    import pyhmmer

    owners: dict[str, list[str]] = {}
    for entry in payload["targets"]:
        for family in entry["domain_families"]:
            owners.setdefault(family["accession"], []).append(entry["dms_id"])
    wanted = set(owners)
    models = []
    with pyhmmer.plan7.HMMFile(hmm_file) as handle:
        for hmm in handle:
            accession = profilesearch.text_of(hmm.accession or hmm.name)
            if accession in wanted:
                models.append(hmm)
    found = {profilesearch.text_of(m.accession or m.name) for m in models}
    if found != wanted:
        raise SystemExit(
            f"{len(wanted - found)} annotated families are not in the pinned registry: "
            f"{', '.join(sorted(wanted - found)[:3])}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as sink:
        for model in models:
            model.write(sink)
    return models, owners


def call_genes_payload(records: list[tuple[str, str]]) -> dict[str, Any]:
    """Call genes on one batch, in a worker process; returns plain strings, not Easel objects.

    Gene calling is where this pass spends its time and it is per-record, so it parallelises
    exactly. The worker returns `(name, protein)` text because an Easel digital sequence does
    not cross a process boundary cheaply, and digitizing in the parent is a rounding error
    beside the calling.

    The arithmetic is `amazebio.profilesearch.call_genes`'s, called rather than reimplemented:
    A2.1's gene calling and this one must not be two gene callers. Records whose genes cannot be
    called are counted rather than absorbed into "no hit" — D-077's rule, inherited with the
    function.
    """

    class _Row:
        __slots__ = ("id", "sequence")

        def __init__(self, record_id: str, sequence: str) -> None:
            self.id = record_id
            self.sequence = sequence

    proteins, stats = profilesearch.call_genes([_Row(i, s) for i, s in records])
    return {
        "proteins": [(profilesearch.text_of(p.name), p.textize().sequence) for p in proteins],
        "genes": stats["genes"],
        "residues": stats["residues"],
        "records_without_genes": stats["records_without_genes"],
    }


class Best:
    """Best hit per model, kept as a running maximum so nothing per-record is retained."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.hits = Counter()

    def offer(self, model: str, *, bits: float, record: str, detail: dict[str, Any]) -> None:
        self.hits[model] += 1
        current = self.rows.get(model)
        if current is None or bits > current["bits"]:
            second = current["bits"] if current else None
            self.rows[model] = {
                "bits": bits,
                "record": record,
                **detail,
                "second_best_bits": second,
            }
        elif current.get("second_best_bits") is None or bits > current["second_best_bits"]:
            current["second_best_bits"] = bits

    def to_dict(self) -> dict[str, Any]:
        return {
            m: {**r, "hits": self.hits[m], "bits": round(r["bits"], 4)}
            for m, r in sorted(self.rows.items())
        }


def _collect(top_hits: Any, best: Best, *, coverage_floor: float) -> None:
    for top in top_hits:
        model = profilesearch.text_of(top.query.accession or top.query.name)
        length = int(top.query.M)
        for hit in top:
            if hit.included is False:
                continue
            coverage = profilesearch.best_model_coverage(hit, length)
            if coverage < coverage_floor:
                continue
            name = profilesearch.text_of(hit.name)
            record = name.rsplit("|gene", 1)[0]
            region = profilesearch.best_domain_region(hit)
            best.offer(
                model,
                bits=float(hit.score),
                record=record,
                detail={
                    "model_coverage": round(coverage, 6),
                    "target_region": list(region) if region else None,
                    "model_length": length,
                },
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, choices=sorted(VIRAL_COMPONENT))
    parser.add_argument("--out", type=Path, default=CANONICAL_OUT)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument(
        "--profile-dir", type=Path, default=REPO / "data" / "b3" / "target-profiles"
    )
    parser.add_argument("--batch", type=int, default=2000, help="records per gene-calling batch")
    parser.add_argument(
        "--rate",
        type=float,
        default=DEPTH,
        help="hash-band fraction of the surviving records to search; 1.0 is a census",
    )
    parser.add_argument("--checkpoint-records", type=int, default=100_000)
    parser.add_argument("--cpus", type=int, default=1, help="threads for the search")
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="processes calling genes, which is where the pass spends its time",
    )
    parser.add_argument("--max-records", type=int, default=0, help="smoke runs only; 0 = all")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--no-durable",
        action="store_true",
        help="smoke runs only; the result is not citable and is not published",
    )
    args = parser.parse_args(argv)

    payload = load_targets(args.targets)
    pfam = profiles.registry("pfam")
    hmm_file = profilesearch.hmm_path(pfam, REPO / "data" / "profiles")
    out = args.out / args.release
    out.mkdir(parents=True, exist_ok=True)

    client = objectstore.client()
    sources = [
        s
        for s in corpora.SOURCES
        if s.release == args.release and s.corpus_component == VIRAL_COMPONENT[args.release]
    ]
    if not sources:
        raise SystemExit(f"no staged source for {args.release}'s viral component")

    with run(
        task=TASK,
        seed=SEED,
        outdir=out,
        manifest_name=f"run-pass-{args.release}.json",
        allow_dirty=args.allow_dirty,
        durable=None if args.no_durable else objectstore.durable_results("b3-pass"),
        durable_exempt=(
            "smoke run: --no-durable, so this output is scratch and is not cited"
            if args.no_durable
            else None
        ),
    ) as ctx:
        profile_models, profile_owners = target_models(payload, profile_dir=args.profile_dir)
        subset = out / f"annotated-domains-{args.release}.hmm"
        pfam_models, domain_owners = domain_models(payload, hmm_file=hmm_file, out=subset)

        ctx.parameter("release", args.release)
        ctx.parameter("component", VIRAL_COMPONENT[args.release])
        ctx.parameter("readings", list(READINGS))
        ctx.parameter("manifest_records", MANIFEST_RECORDS[args.release])
        ctx.parameter("target_profiles", len(profile_models))
        ctx.parameter("domain_profiles", len(pfam_models))
        ctx.parameter("pfam_registry", pfam.key)
        ctx.parameter("pinned_e_value", homology.PINNED_E_VALUE)
        ctx.parameter("pinned_z", homology.PINNED_Z)
        ctx.parameter("pinned_dom_z", profiles.PINNED_DOM_Z)
        ctx.parameter("domain_cutoffs", "pfam gathering")
        ctx.parameter("min_model_coverage", profiles.MIN_MODEL_COVERAGE)
        ctx.parameter("rate", args.rate)
        ctx.parameter("sample_seed", SAMPLE_SEED)
        ctx.parameter("sample_method", "blake2b(seed, record_id) < rate * 2**64, as A2.1 sampled")
        ctx.parameter("batch_records", args.batch)
        ctx.parameter("gene_calling_workers", args.workers)
        ctx.parameter("search_threads", args.cpus)
        ctx.parameter("max_records", args.max_records)
        ctx.input_file(args.targets, role="target side of the axis")
        ctx.input_file(hmm_file, role="pfam profiles")

        removed = removed_ids(client, args.release)
        ctx.parameter("removed_records", len(removed))

        import pyhmmer
        from pyhmmer.easel import Alphabet, DigitalSequenceBlock, TextSequence

        amino = Alphabet.amino()
        profile_best, domain_best = Best(), Best()
        stats = Counter()
        started = time.monotonic()
        checkpoint = out / f"best-{args.release}.json"

        def write_checkpoint(*, complete: bool) -> None:
            searched = stats["records_searched"]
            total = MANIFEST_RECORDS[args.release]
            checkpoint.write_text(
                json.dumps(
                    {
                        "task": TASK,
                        "release": args.release,
                        "component": VIRAL_COMPONENT[args.release],
                        "readings": list(READINGS),
                        "complete": complete,
                        "rate": args.rate,
                        "sample_seed": SAMPLE_SEED,
                        "nests_a2_1_sample": True,
                        "selection": (
                            ("census" if args.rate >= 1.0 else "hash_band")
                            if complete
                            else "prefix"
                        ),
                        "selection_note": (
                            (
                                "every surviving record of the component"
                                if args.rate >= 1.0
                                else f"a seeded hash band of {args.rate:.3g} of the "
                                "component's surviving records; membership is a function of "
                                "the record identifier, so this is a sample of the component "
                                "and an absent hit is a lower bound over it"
                            )
                            if complete
                            else "a leading prefix of a hash band, cut short: a prefix of an "
                            "accession-ordered object is not a sample, so an absent hit here "
                            "says nothing about the records not reached"
                        ),
                        "records_searched": searched,
                        "manifest_records": total,
                        "searched_fraction": (
                            round(searched / total, 8) if total and not complete else args.rate
                        ),
                        "band_records_searched": searched,
                        "removed_records_skipped": stats["removed_skipped"],
                        "gene_calling": {
                            "genes": stats["genes"],
                            "residues": stats["residues"],
                            "records_without_genes": stats["records_without_genes"],
                        },
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "sequence_profile_best": profile_best.to_dict(),
                        "domain_presence_best": domain_best.to_dict(),
                        "profile_owners": profile_owners,
                        "domain_owners": domain_owners,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

        def search_called(called: dict[str, Any]) -> None:
            stats["genes"] += called["genes"]
            stats["residues"] += called["residues"]
            stats["records_without_genes"] += called["records_without_genes"]
            if not called["proteins"]:
                return
            block = DigitalSequenceBlock(
                amino,
                [
                    TextSequence(name=name.encode(), sequence=protein).digitize(amino)
                    for name, protein in called["proteins"]
                ],
            )
            _collect(
                pyhmmer.hmmsearch(
                    profile_models,
                    block,
                    cpus=args.cpus,
                    E=homology.PINNED_E_VALUE,
                    Z=homology.PINNED_Z,
                    domZ=profiles.PINNED_DOM_Z,
                ),
                profile_best,
                coverage_floor=profiles.MIN_MODEL_COVERAGE,
            )
            _collect(
                pyhmmer.hmmsearch(pfam_models, block, cpus=args.cpus, bit_cutoffs="gathering"),
                domain_best,
                coverage_floor=profiles.MIN_MODEL_COVERAGE,
            )

        complete = True
        pool = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else None
        pending: deque[Any] = deque()

        def drain(*, keep: int) -> None:
            while len(pending) > keep:
                search_called(pending.popleft().result())

        def submit(batch: list[Any]) -> None:
            if not batch:
                return
            payload = [(r.id, r.sequence) for r in batch]
            if pool is None:
                search_called(call_genes_payload(payload))
                return
            pending.append(pool.submit(call_genes_payload, payload))
            # Bounded queue: the reader runs ahead of the callers by at most a couple of
            # batches per worker, so a fast object does not buffer the corpus into memory.
            drain(keep=2 * args.workers)

        for source in sources:
            # The pin is re-checked against the live object before it is read, as A2.1 does:
            # a staged object that is not the length the pin records is not the object this
            # audit measured, and every figure downstream would be about something else.
            live = int(
                client.head_object(Bucket=objectstore.CORPORA_BUCKET, Key=source.key)[
                    "ContentLength"
                ]
            )
            if source.bytes and live != source.bytes:
                raise SystemExit(
                    f"{source.key}: staged object is {live} bytes, the pin says "
                    f"{source.bytes}. Re-verify before trusting any count from it."
                )
            if source.reader == "fasta":
                # Forward-only, one GET held open. A ranged GET per read call costs an HTTP
                # round trip per few kilobytes through a decompressor, which is what killed
                # A1.8's count; `S3SequentialRead` exists for exactly this shape of read.
                raw: Any = objectstore.S3SequentialRead(
                    client, objectstore.CORPORA_BUCKET, source.key
                )
                stream = uniref.GunzipStream(raw) if source.gzipped else raw
                records = seqstream.iter_fasta_sampled(
                    stream, component=source.component, seed=SAMPLE_SEED, hi=args.rate
                )
            else:
                # Parquet needs random access — its footer is at the end of the object — so
                # this side takes the ranged reader A2.1 reads the same object with, not the
                # forward-only one.
                stream = corpora.RangedObject(
                    client,
                    bucket=objectstore.CORPORA_BUCKET,
                    key=source.key,
                    size=source.bytes or live,
                    on_retry=lambda attempt, pos, exc: print(
                        f"    reconnect {attempt} at byte {pos:,}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    ),
                ).buffered()
                records = seqstream.iter_stage2_sampled(
                    stream,
                    component=source.component,
                    # The identifier must be the one A1.4 and A2.1 built, or neither
                    # the removal exclusion nor the hash band means anything: it is
                    # `<component>:<object name>#<row>`, not `<component>#<row>`.
                    record_prefix=source.corpus_component + ":" + Path(source.key).name,
                    seed=SAMPLE_SEED,
                    hi=args.rate,
                )
            batch: list[Any] = []
            checked_shape = not removed
            for sampled in records:
                if not checked_shape:
                    # The removal exclusion is silent when it fails: a record identifier built
                    # differently from A1.4's matches nothing, every removed record is searched
                    # anyway, and the band is a different band from A2.1's. Both failures
                    # produce a complete, plausible table. So the first record's identifier is
                    # checked against the shape of the removed set rather than trusted.
                    # Shape, not equality: this release's component is published as several
                    # splits and only one of them carries a removed record, so an identifier
                    # from another split is legitimately absent from the removed set. What
                    # must agree is how the identifier is built — component, separator, object
                    # name, row — which is what distinguishes `stage2:train_stage2.parquet#0`
                    # from `stage2#0`.
                    stem_here = sampled.id.rsplit("#", 1)[0]
                    stems = {r.rsplit("#", 1)[0] for r in removed}
                    ok = any(
                        s.split(":", 1)[0] == stem_here.split(":", 1)[0]
                        and (":" in s) == (":" in stem_here)
                        for s in stems
                    )
                    if not ok:
                        raise SystemExit(
                            f"record identifiers do not match A1.4's: this pass builds "
                            f"{sampled.id!r} and the removed set is keyed on "
                            f"{sorted(stems)[:2]}. The removal exclusion and the hash band "
                            "both depend on one identifier, so this is refused rather than "
                            "reported."
                        )
                    checked_shape = True
                if sampled.id in removed:
                    stats["removed_skipped"] += 1
                    continue
                batch.append(sampled)
                stats["records_searched"] += 1
                if len(batch) >= args.batch:
                    submit(batch)
                    batch = []
                    if stats["records_searched"] % args.checkpoint_records < args.batch:
                        drain(keep=0)
                        write_checkpoint(complete=False)
                        print(
                            f"{stats['records_searched']:,} records, "
                            f"{stats['residues']:,} residues, "
                            f"{time.monotonic() - started:,.0f}s",
                            flush=True,
                        )
                if args.max_records and stats["records_searched"] >= args.max_records:
                    complete = False
                    break
            submit(batch)
            drain(keep=0)
            if not complete:
                break

        if pool is not None:
            pool.shutdown()
        write_checkpoint(complete=complete)
        ctx.output_file(checkpoint, role="best hit per model over the surviving records")
        ctx.output_file(subset, role="the annotated domain subset searched")

    print(
        f"{args.release}: {stats['records_searched']:,} records searched, "
        f"{stats['genes']:,} genes, {stats['residues']:,} residues, "
        f"{len(profile_best.rows)} target profiles with a hit, "
        f"{len(domain_best.rows)} domain families with a hit, "
        f"complete={complete}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

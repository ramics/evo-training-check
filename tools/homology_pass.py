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
from collections import Counter
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

#: The readings whose surviving set is identical on these releases (A1.4).
READINGS = ("evo1-literal", "evo1-charitable", "evo1-strict")


def load_targets() -> dict[str, Any]:
    if not TARGETS.exists():
        raise SystemExit(f"{TARGETS} is missing; run tools/homology_targets.py first")
    return json.loads(TARGETS.read_text())


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
            out.add(json.loads(line)["record"]["id"])
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
    parser.add_argument("--batch", type=int, default=2000, help="records per gene-calling batch")
    parser.add_argument("--checkpoint-records", type=int, default=100_000)
    parser.add_argument("--cpus", type=int, default=3)
    parser.add_argument("--max-records", type=int, default=0, help="smoke runs only; 0 = all")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--no-durable",
        action="store_true",
        help="smoke runs only; the result is not citable and is not published",
    )
    args = parser.parse_args(argv)

    payload = load_targets()
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
        profile_models, profile_owners = target_models(
            payload, profile_dir=REPO / "data" / "b3" / "target-profiles"
        )
        subset = out / "annotated-domains.hmm"
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
        ctx.parameter("batch_records", args.batch)
        ctx.parameter("max_records", args.max_records)
        ctx.input_file(TARGETS, role="target side of the axis")
        ctx.input_file(hmm_file, role="pfam profiles")

        removed = removed_ids(client, args.release)
        ctx.parameter("removed_records", len(removed))

        import pyhmmer
        from pyhmmer.easel import Alphabet, DigitalSequenceBlock

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
                        "selection": "census" if complete else "prefix",
                        "selection_note": (
                            "every surviving record of the component"
                            if complete
                            else "a leading prefix of an accession-ordered object, which is "
                            "not a sample: an absent hit here says nothing about the "
                            "records not reached"
                        ),
                        "records_searched": searched,
                        "manifest_records": total,
                        "searched_fraction": round(searched / total, 8) if total else None,
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

        def flush(batch: list[Any]) -> None:
            if not batch:
                return
            proteins, called = profilesearch.call_genes(batch)
            stats["genes"] += called["genes"]
            stats["residues"] += called["residues"]
            stats["records_without_genes"] += called["records_without_genes"]
            if not proteins:
                return
            block = DigitalSequenceBlock(amino, proteins)
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
        for source in sources:
            reader = objectstore.S3SequentialRead(client, objectstore.CORPORA_BUCKET, source.key)
            stream = uniref.GunzipStream(reader) if source.gzipped else reader
            if source.reader == "fasta":
                records = seqstream.iter_fasta_sampled(
                    stream, component=source.component, seed=SEED, hi=1.0
                )
            else:
                records = seqstream.iter_stage2_sampled(
                    stream,
                    component=source.component,
                    record_prefix=source.corpus_component,
                    seed=SEED,
                    hi=1.0,
                )
            batch: list[Any] = []
            for sampled in records:
                if sampled.id in removed:
                    stats["removed_skipped"] += 1
                    continue
                batch.append(sampled)
                stats["records_searched"] += 1
                if len(batch) >= args.batch:
                    flush(batch)
                    batch = []
                    if stats["records_searched"] % args.checkpoint_records < args.batch:
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
            flush(batch)
            if not complete:
                break

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

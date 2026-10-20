#!/usr/bin/env python3
"""Compare OpenGenome2's GTDB subtree against OpenGenome v1 — task A7.4, §A7.

    pixi run -e dev python tools/opengenome_compare.py --digest

Reads the two contig tables the other two tools produce — `opengenome_v1_contigs.py`'s
accession index and `opengenome_contigs.py`'s per-archive tables — joins them on the
accession D-213 fixes as the primary key, and gives every discrepancy a cause from the
closed set in `amazebio.reuse`.

**The digest stage is targeted, and that is the point of the index.** Separating a renamed
contig from a missing one needs the v1 record's residues, which live in a 118.5 GiB column
this project will not read in full to settle a question most of its rows are not party to.
The accession index records which shard and which row group each record sits in, so the
digest pass reads only the row groups that actually hold a disputed accession. With
`--digest` omitted, those records are reported as `undetermined` rather than guessed at.

Nothing here reports a rate without its interval, and the two sides of OpenGenome2 are
never pooled: the reused subtree tests "used in its entirety" and the added archive tests
the 28,174 figure, and letting the second cover a gap in the first is the one way this
comparison could flatter the claim.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import contigs as contiglib
from amazebio import objectstore, repro, reuse
from amazebio.reuse import Side

TASK = "A7.4"

#: v1's staged tier, for the targeted digest pass.
V1_PREFIX = "corpora/opengenome/84369c058d192dcb607086d71679b877421e3250/stage1/gtdb"

#: Which archive speaks to which half of Evo 2's claim.
SIDES = {
    "v214-batch1": Side.REUSED,
    "v214-batch2": Side.REUSED,
    "v214-batch3": Side.REUSED,
    "v220_update": Side.ADDED,
}

#: The published figure the added side is checked against (D-130).
STATED_ADDED = 28_174


def read_jsonl(path: Path) -> Any:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="ascii") as handle:  # type: ignore[operator]
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_v1(path: Path) -> dict[str, tuple[str, int]]:
    """accession -> (shard, row group), from the v1 index."""
    return {row["accession"]: (row["shard"], row["row_group"]) for row in read_jsonl(path)}


def load_og2(paths: list[Path]) -> tuple[list[tuple[str, Side]], dict[str, str], dict[str, int]]:
    """`(accession, side)` rows, accession -> digest, and genomes per side."""
    rows: list[tuple[str, Side]] = []
    digests: dict[str, str] = {}
    genomes: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        # `contigs-v214-batch1-<commit>.jsonl.gz` -> `v214-batch1`. The commit is the
        # last field and carries no hyphen, so dropping it is a single rsplit.
        stem = path.name.removeprefix("contigs-").removesuffix(".jsonl.gz").rsplit("-", 1)[0]
        side = SIDES.get(stem)
        if side is None:
            raise SystemExit(f"{path.name}: no side is recorded for archive {stem!r}")
        for row in read_jsonl(path):
            rows.append((row["accession"], side))
            digests[row["accession"]] = row["sha256"]
            genomes[side.value].add(row["assembly"])
    return rows, digests, {k: len(v) for k, v in genomes.items()}


def digest_v1(
    client: Any, wanted: dict[str, tuple[str, int]], *, verbose: bool = True
) -> dict[str, str]:
    """Digest just the v1 records named, reading only the row groups that hold them."""
    import pyarrow.parquet as pq

    by_shard: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for accession, (shard, group) in wanted.items():
        by_shard[shard][group].add(accession)

    out: dict[str, str] = {}
    for shard, groups in sorted(by_shard.items()):
        key = f"{V1_PREFIX}/{shard}.parquet"
        handle = objectstore.S3RandomRead(client, objectstore.CORPORA_BUCKET, key)
        with handle:
            parquet = pq.ParquetFile(handle)
            for group in sorted(groups):
                table = parquet.read_row_group(group, columns=["record", "text"])
                records = table.column("record").to_pylist()
                texts = table.column("text").to_pylist()
                for record, text in zip(records, texts, strict=True):
                    if record in groups[group]:
                        out[record] = contiglib.digest_sequence([text])[0]
        if verbose:
            print(f"  {shard}: {len(groups)} row groups, {len(out):,} digested", flush=True)
    return out


def report(
    result: reuse.Join,
    discrepancies: tuple[reuse.Discrepancy, ...],
    *,
    genomes: dict[str, int],
) -> dict[str, Any]:
    point, low, high = result.reused_coverage
    counts = reuse.tally(discrepancies)
    added_delta = genomes.get("added", 0) - STATED_ADDED
    return {
        "task": TASK,
        "design_ref": "§A7",
        "decisions": ["D-130", "D-213"],
        "v1_contigs": result.v1_accessions,
        "og2_reused_contigs": result.reused_accessions,
        "og2_added_contigs": result.added_accessions,
        "shared_with_reused": result.shared_with_reused,
        "reused_coverage": {"estimate": point, "low": low, "high": high, "method": "wilson"},
        "only_in_v1": len(result.only_v1),
        "only_in_reused": len(result.only_reused),
        "added_also_in_v1": len(result.added_also_in_v1),
        "discrepancies_by_cause": counts,
        "cause_meaning": {k.value: v for k, v in reuse.CAUSE_MEANING.items()},
        "added_genomes": genomes.get("added"),
        "stated_added": STATED_ADDED,
        "added_difference": added_delta,
        "examples": {
            "only_in_v1": list(result.only_v1[:5]),
            "only_in_reused": list(result.only_reused[:5]),
            "added_also_in_v1": list(result.added_also_in_v1[:5]),
        },
        "reading_this_file": [
            "The two sides of OpenGenome2 are never pooled: the reused subtree is what "
            '"used in its entirety" is about, and the added archive is what the 28,174 '
            "figure is about.",
            "`undetermined` is not a cause. It counts records whose digest has not been "
            "read, and it is never added to the other four.",
            "Only `content` bears on whether the corpus holds what its authors said; the "
            "other causes are differences in naming, in duplication, or in release date.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--indir", type=Path, default=Path("artifacts/a7-4"))
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a7-4"))
    ap.add_argument("--v1", type=Path, help="the v1 accession index (default: in --indir)")
    ap.add_argument("--digest", action="store_true", help="run the targeted v1 digest pass")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    v1_path = args.v1 or args.indir / "v1-contigs.jsonl.gz"
    og2_paths = sorted(args.indir.glob("contigs-*.jsonl.gz"))
    if not v1_path.exists():
        raise SystemExit(f"{v1_path} is not there; run tools/opengenome_v1_contigs.py first")
    if not og2_paths:
        raise SystemExit(
            f"no contig tables in {args.indir}; the in-region pass publishes them to "
            f"{objectstore.durable_results('a7-4')}"
        )

    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=None,  # a join; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-compare.json",
            durable=objectstore.durable_results("a7-4"),
        ) as manifest:
            manifest.input_file(v1_path, role="v1 accession index")
            for path in og2_paths:
                manifest.input_file(path, role="og2 contig table")
            manifest.parameter("decisions", ["D-130", "D-213"])
            manifest.parameter("digest_pass", args.digest)
            manifest.parameter("stated_added", STATED_ADDED)

            v1 = load_v1(v1_path)
            rows, og2_digests, genomes = load_og2(og2_paths)
            result = reuse.join(v1, rows)
            print(
                f"v1 {result.v1_accessions:,} contigs; reused {result.reused_accessions:,}; "
                f"added {result.added_accessions:,}; "
                f"{len(result.only_v1):,} only in v1, {len(result.only_reused):,} only in "
                f"the reused subtree",
                flush=True,
            )

            v1_digests: dict[str, str] = {}
            if args.digest:
                wanted = {a: v1[a] for a in result.only_v1 if a in v1}
                print(f"digesting {len(wanted):,} v1 records", flush=True)
                v1_digests = digest_v1(objectstore.client(), wanted)
                manifest.parameter("v1_records_digested", len(v1_digests))

            discrepancies = reuse.classify(result, og2_digests=og2_digests, v1_digests=v1_digests)
            document = report(result, discrepancies, genomes=genomes)

            out = args.outdir / "comparison.json"
            out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="contig comparison")

            table = args.outdir / "discrepancies.jsonl.gz"
            with gzip.open(table, "wt", encoding="ascii") as handle:
                for item in discrepancies:
                    handle.write(
                        json.dumps(
                            {
                                "accession": item.accession,
                                "present_in": item.present_in,
                                "cause": item.cause.value,
                                "evidence": item.evidence,
                            }
                        )
                        + "\n"
                    )
            manifest.output_file(table, role="discrepancies, one per record")
    except (repro.ReproError, contiglib.ContigError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    coverage = document["reused_coverage"]
    print(
        f"reused coverage {coverage['estimate']:.6f} "
        f"[{coverage['low']:.6f}, {coverage['high']:.6f}]\n"
        f"causes: {document['discrepancies_by_cause']}\n"
        f"added genomes {document['added_genomes']:,} against a stated "
        f"{STATED_ADDED:,} ({document['added_difference']:+,})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

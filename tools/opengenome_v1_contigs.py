#!/usr/bin/env python3
"""Enumerate OpenGenome v1's GTDB contigs, by accession alone — task A7.4, §A7.

    pixi run -e dev python tools/opengenome_v1_contigs.py

The other side of D-213's comparison. OpenGenome v1's `stage1/gtdb` is 118.5 GiB of Parquet
with one row per contig: an INSDC accession in `record` and the residues in `text`. Only
the accession is needed to make the primary comparison, and Parquet stores columns apart —
so reading `record` for all thirteen shards moves about **77 MB**, not 118.5 GiB, and this
half needs no instance at all. The contig side of OpenGenome2 has no such shortcut, because
its accessions live inside each member's gzip stream; `tools/ec2_opengenome_contigs.py`
runs that one in region.

**What it deliberately does not read.** The `text` column, and therefore any digest of a v1
sequence. D-213 puts the digest on the set the accessions disagree about, which is not known
until this table and OpenGenome2's are joined; digesting all thirteen million rows first
would read the whole 118.5 GiB to settle a question most of them are not party to. The
targeted digest pass is a separate step and takes this file's output as its input.

It also records where each accession was found — shard and row group — because that is what
lets the digest pass read a few row groups rather than a corpus.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, repro

TASK = "A7.4"

#: The staged release, pinned by the content hash it was staged under (D-119).
PREFIX = "corpora/opengenome/84369c058d192dcb607086d71679b877421e3250/stage1/gtdb"

#: The split each file belongs to. v1 publishes its own splits and the comparison reports
#: per split where they survive, so the split travels with the accession rather than being
#: flattened away here.
SPLITS = {"gtdb_train_shard_": "train", "gtdb_valid_small": "valid", "gtdb_test": "test"}


def split_of(name: str) -> str:
    for stem, split in SPLITS.items():
        if name.startswith(stem):
            return split
    return "unknown"


def shards(client: Any, bucket: str, prefix: str) -> list[str]:
    """Every Parquet file of the staged tier, in a stable order."""
    keys: list[str] = []
    token = None
    while True:
        kw: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix + "/", "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        page = client.list_objects_v2(**kw)
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".parquet")]
        if not page.get("IsTruncated"):
            return sorted(keys)
        token = page["NextContinuationToken"]


def read_accessions(
    client: Any, bucket: str, key: str, *, progress: Any = None
) -> list[tuple[str, int]]:
    """`(accession, row_group)` for every row of one shard, reading only `record`.

    The column is read in **one** call rather than a row group at a time. A shard here holds
    a thousand row groups and its `record` chunks are about six kilobytes each, so a read
    per group turns a six megabyte column into whatever the reader's buffer is per group —
    with a four megabyte buffer, four gigabytes a shard, which is the corpus pass this tool
    exists to avoid. The row group each row belongs to is then taken from the footer's own
    row counts, which cost nothing and are exact.
    """
    import pyarrow.parquet as pq

    # No buffering wrapper. A buffer's minimum read is charged to every one of the
    # thousand column chunks in a shard, which is how a six megabyte column becomes
    # gigabytes; pyarrow issues exact ranges and coalesces them itself.
    handle = objectstore.S3RandomRead(client, bucket, key)
    with handle:
        parquet = pq.ParquetFile(handle, pre_buffer=True)
        meta = parquet.metadata
        sizes = [meta.row_group(i).num_rows for i in range(meta.num_row_groups)]
        if progress is not None:
            progress(0, meta.num_row_groups, 0)
        values = parquet.read(columns=["record"]).column("record").to_pylist()

    rows: list[tuple[str, int]] = []
    position = 0
    for group, size in enumerate(sizes):
        rows += [(value, group) for value in values[position : position + size]]
        position += size
    if position != len(values):  # pragma: no cover - the footer disagreeing with the data
        raise ValueError(f"{key}: footer counts {position} rows, the column holds {len(values)}")
    if progress is not None:
        progress(len(sizes), len(sizes), len(rows))
    return rows


def measure(
    client: Any, bucket: str, keys: list[str], *, verbose: bool = True
) -> tuple[dict[str, Any], dict[str, list]]:
    """Enumerate every shard and report what the accessions are, per split."""
    per_shard: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    index: dict[str, list] = {}
    duplicates: Counter[str] = Counter()

    for key in keys:
        name = key.rsplit("/", 1)[-1].removesuffix(".parquet")
        split = split_of(name)

        def progress(done: int, total: int, rows: int, name: str = name) -> None:
            if verbose and (done % 200 == 0 or done == total):
                print(f"  {name}: row group {done}/{total}, {rows:,} rows", flush=True)

        rows = read_accessions(client, bucket, key, progress=progress)
        for accession, group in rows:
            if accession in index:
                duplicates[accession] += 1
                continue
            index[accession] = [name, group]
        counts[split] += len(rows)
        per_shard.append(
            {
                "shard": name,
                "split": split,
                "rows": len(rows),
                "distinct": len({r[0] for r in rows}),
            }
        )

    return {
        "task": TASK,
        "design_ref": "§A7",
        "decisions": ["D-119", "D-213"],
        "prefix": f"s3://{bucket}/{PREFIX}",
        "shards": per_shard,
        "rows": sum(counts.values()),
        "distinct_accessions": len(index),
        "rows_per_split": dict(counts),
        "repeated_accessions": len(duplicates),
        "repeated_examples": sorted(duplicates)[:5],
        "reading_this_file": [
            "Accessions only. The residues were not read, so nothing here says whether two "
            "records under one accession hold the same sequence (D-213).",
            "A repeated accession is counted once in the index and reported as a repeat; "
            "v1's own splits can carry the same contig more than once.",
        ],
    }, index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a7-4"))
    ap.add_argument("--limit-shards", type=int, help="read only this many shards; a smoke test")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    client = objectstore.client()
    bucket = objectstore.CORPORA_BUCKET
    keys = shards(client, bucket, PREFIX)
    if args.limit_shards:
        keys = keys[: args.limit_shards]
    print(f"{len(keys)} shards under s3://{bucket}/{PREFIX}", flush=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    try:
        with repro.run(
            TASK,
            seed=None,  # an enumeration; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-v1-contigs.json",
            durable=objectstore.durable_results("a7-4"),
        ) as manifest:
            manifest.parameter("prefix", PREFIX)
            manifest.parameter("shards", [k.rsplit("/", 1)[-1] for k in keys])
            manifest.parameter("decisions", ["D-119", "D-213"])
            manifest.note(
                "Only the `record` column is read. Parquet stores columns apart, so this "
                "moves about 77 MB of a 118.5 GiB tier and needs no in-region instance."
            )
            document, index = measure(client, bucket, keys)

            table = args.outdir / "v1-contigs.jsonl.gz"
            with gzip.open(table, "wt", encoding="ascii") as handle:
                for accession, (shard, group) in index.items():
                    handle.write(
                        json.dumps({"accession": accession, "shard": shard, "row_group": group})
                        + "\n"
                    )
            summary = args.outdir / "v1-contigs.json"
            summary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
            manifest.output_file(table, role="v1 contig index")
            manifest.output_file(summary, role="v1 contig summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    print(
        f"{document['rows']:,} rows, {document['distinct_accessions']:,} distinct accessions, "
        f"{document['repeated_accessions']:,} repeated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

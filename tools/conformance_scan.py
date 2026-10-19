#!/usr/bin/env python3
"""Scan a released Evo corpus for the fields A7.1's conformance diff needs.

This is the expensive half of A7.1, and it is deliberately the half that decides nothing. It
reads 28 GB of staged release and emits a few hundred kilobytes: for Evo 1's `stage2`, how many
records carry each distinct lineage tag; for Evo 2's IMG/VR FASTA, the accession inventory. The
diff against the published predicates then runs anywhere, from that artefact, in a second —
which is what makes the headline numbers reproducible from a published intermediate instead of
from a re-run of this scan, and what lets A3.3's independent reimplementation check them without
touching a corpus.

Three properties worth stating before anyone changes it.

**No sequence is retained, held or transferred.** Each row is split, its tag kept and its
sequence measured and dropped (`amazebio.conformance.split_row`). The scan's output could be
committed to this repository without breaking the commitment in D-020 that no genomic sequence
enters it. That is not tidiness: it is what allows the result to come back from an in-region
instance straight into the audit store.

**The structural premise is measured, not assumed.** Every count in A7.1 rests on "one released
row is one released record". Nobody published that, and it is false in the obvious reading —
records longer than 131,072 characters arrive as several same-tag blocks concatenated into one
row. So the scan counts, over every row: the blocks per row, the rows holding more than one
distinct tag, and the rows whose final block is full-length. The first two would mean a row packs
several records; the third would mean a record may continue into the next row. All three are
reported with the result, and the diff refuses to call its output a record count if they are
non-zero.

**Row groups are the unit of parallelism, and there are 2,653 of them.** Unlike the gzip streams
A1.3 dealt with, a Parquet file is splittable: each row group's column chunk decompresses
independently, so the scan scales with cores up to the I/O ceiling. The IMG/VR FASTA is a single
gzip stream and is therefore exactly one thread however large the instance — it is the smaller
file and still sets its own wall clock.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import conformance as cf
from amazebio import objectstore
from amazebio import opengenome as og
from amazebio.repro import run

S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"

#: The staged object each audited release lives at, relative to the corpora prefix. Both are
#: pinned by the release revision in `amazebio.opengenome`, so a key here names one immutable
#: artefact: the corpus bucket withholds `s3:DeleteObject`, which is what makes that true.
RELEASE_KEYS = {
    "opengenome-stage2": (
        f"opengenome/{og.OG1.revision}/stage2/train_stage2.parquet",
        f"opengenome/{og.OG1.revision}/stage2/valid_stage2.parquet",
        f"opengenome/{og.OG1.revision}/stage2/test_stage2.parquet",
    ),
    "opengenome2-imgvr": (f"opengenome2/{og.OG2.revision}/fasta/plasmids_phage/imgvr.fasta.gz",),
}

#: How many distinct tags the scan will carry before it stops naming them individually. The
#: released tag space is small — a few hundred lineages over millions of records — so this is a
#: tripwire rather than a budget: blowing through it means the tag field is not what D-020
#: established it to be, and the scan should say so rather than emit a multi-megabyte histogram.
MAX_DISTINCT_TAGS = 100_000


# --------------------------------------------------------------------------------------
# Object access
# --------------------------------------------------------------------------------------


def _client() -> Any:
    import boto3

    return boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)


class S3RandomRead(io.RawIOBase):
    """A seekable reader over an S3 object, backed by range requests.

    Parquet needs random access — the footer first, then the row groups the caller asks for —
    which is the one thing `amazebio.uniref.ResumableRead` deliberately does not provide. A
    range GET per read is more requests than a sequential stream would make and costs nothing
    in-region, which is where this runs.
    """

    def __init__(self, client: Any, bucket: str, key: str) -> None:
        self._c, self._bucket, self._key = client, bucket, key
        self.size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            self._pos = offset
        elif whence == os.SEEK_CUR:
            self._pos += offset
        else:
            self._pos = self.size + offset
        return self._pos

    #: Attempts per range, and the backoff between them. A range GET that breaks mid-stream is
    #: the normal failure at this concurrency rather than an exceptional one — sixteen readers
    #: through the project's outbound proxy produced an `IncompleteRead` partway through a
    #: 2.65M-row pass, which is the same class of failure `amazebio.uniref.ResumableRead` was
    #: written for. A range is re-requested whole rather than resumed: the request is a few
    #: megabytes, so re-reading it is cheaper than tracking a partial buffer, and a retried
    #: range either arrives complete or raises.
    ATTEMPTS = 5
    BACKOFF = 2.0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self._pos
        size = min(size, self.size - self._pos)
        if size <= 0:
            return b""
        end = self._pos + size - 1
        last: Exception | None = None
        for attempt in range(self.ATTEMPTS):
            try:
                body = self._c.get_object(
                    Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}"
                )["Body"].read()
            except Exception as exc:  # any transport failure here is worth one more attempt
                last = exc
                time.sleep(self.BACKOFF**attempt)
                continue
            if len(body) != size:
                # A short read is a broken stream that did not raise. Treating it as data would
                # corrupt a Parquet column chunk and the scan would fail far from the cause.
                last = OSError(f"short range read: got {len(body)} of {size} bytes")
                time.sleep(self.BACKOFF**attempt)
                continue
            self._pos += len(body)
            return body
        raise OSError(
            f"range {self._pos}-{end} of s3://{self._bucket}/{self._key} failed "
            f"{self.ATTEMPTS} times; last error: {last}"
        ) from last

    def readinto(self, buf: Any) -> int:
        """Required by `io.BufferedReader`, which calls this and never `read`.

        `RawIOBase` derives `read` from `readinto` and not the other way round, so a reader
        that implements only `read` works standalone and raises `NotImplementedError` the
        moment it is wrapped for buffering — which is how the FASTA arm first failed.
        """
        chunk = self.read(len(buf))
        buf[: len(chunk)] = chunk
        return len(chunk)


# --------------------------------------------------------------------------------------
# The Parquet arm — Evo 1's stage2
# --------------------------------------------------------------------------------------


def _blank_tally() -> dict[str, Any]:
    return {
        "rows": 0,
        "tags": collections.Counter(),
        "blocks_per_row": collections.Counter(),
        "rows_multi_tag": 0,
        "rows_last_block_full": 0,
        "rows_no_tag": 0,
        "sequence_chars": 0,
        "total_chars": 0,
        "max_row_chars": 0,
        "multi_tag_examples": [],
    }


def _merge(into: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    into["tags"].update(other["tags"])
    into["blocks_per_row"].update(other["blocks_per_row"])
    for k in (
        "rows",
        "rows_multi_tag",
        "rows_last_block_full",
        "rows_no_tag",
        "sequence_chars",
        "total_chars",
    ):
        into[k] += other[k]
    into["max_row_chars"] = max(into["max_row_chars"], other["max_row_chars"])
    into["multi_tag_examples"] = (into["multi_tag_examples"] + other["multi_tag_examples"])[:20]
    return into


def _scan_row_groups(bucket: str, key: str, groups: list[int]) -> dict[str, Any]:
    """Tally one worker's share of row groups. Runs in a subprocess; returns small."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    tally = _blank_tally()
    reader = pq.ParquetFile(pa.PythonFile(S3RandomRead(_client(), bucket, key), mode="rb"))
    for g in groups:
        table = reader.read_row_group(g, columns=["text"])
        for row in table.column("text").to_pylist():
            if row is None:
                tally["rows_no_tag"] += 1
                tally["rows"] += 1
                continue
            shape = cf.split_row(row)
            tally["rows"] += 1
            tally["total_chars"] += shape.total_chars
            tally["sequence_chars"] += shape.sequence_chars
            tally["max_row_chars"] = max(tally["max_row_chars"], shape.total_chars)
            tally["blocks_per_row"][shape.n_blocks] += 1
            if shape.n_blocks == 0:
                tally["rows_no_tag"] += 1
                continue
            distinct = shape.distinct_tags
            if len(distinct) > 1:
                tally["rows_multi_tag"] += 1
                if len(tally["multi_tag_examples"]) < 20:
                    tally["multi_tag_examples"].append({"row_group": g, "tags": list(distinct)})
            if shape.last_block_full:
                tally["rows_last_block_full"] += 1
            # One record, counted once, under the tag its first block carries. A row holding
            # more than one distinct tag is counted here too and flagged above: dropping it
            # would make the tag histogram disagree with the row count, and the disagreement
            # is the evidence that the premise broke.
            tally["tags"][distinct[0] if len(distinct) == 1 else shape.tags[0]] += 1
    return tally


def scan_parquet(
    bucket: str, prefix: str, keys: tuple[str, ...], *, workers: int, progress: float
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    client = _client()
    total = _blank_tally()
    per_file = {}
    for key in keys:
        full = f"{prefix}/{key}" if prefix else key
        meta = pq.ParquetFile(pa.PythonFile(S3RandomRead(client, bucket, full), mode="rb")).metadata
        n_groups, n_rows = meta.num_row_groups, meta.num_rows
        print(f"[scan] {key}: {n_rows:,} rows in {n_groups:,} row groups", flush=True)
        # Many small shards rather than one per worker. With one shard each, nothing completes
        # until a worker finishes its whole share, so a seven-minute pass prints nothing for
        # seven minutes and an operator cannot tell a slow run from a hung one. Chunks of 32
        # row groups give ~83 units of progress per worker and cost one extra Parquet footer
        # read each, which is a few kilobytes.
        chunk = 32
        shards = [list(range(i, min(i + chunk, n_groups))) for i in range(0, n_groups, chunk)]
        file_tally = _blank_tally()
        started = last = time.time()
        with ProcessPoolExecutor(max_workers=min(workers, len(shards))) as pool:
            futures = {
                pool.submit(_scan_row_groups, bucket, full, shard): shard for shard in shards
            }
            done_groups = 0
            for fut in as_completed(futures):
                _merge(file_tally, fut.result())
                done_groups += len(futures[fut])
                if time.time() - last >= progress:
                    last = time.time()
                    pct = 100.0 * done_groups / n_groups
                    print(
                        f"[scan] {key}: {pct:5.1f}%  {file_tally['rows']:,} rows  "
                        f"{time.time() - started:,.0f}s",
                        flush=True,
                    )
        if file_tally["rows"] != n_rows:
            raise RuntimeError(
                f"{key}: scanned {file_tally['rows']:,} rows but the footer declares "
                f"{n_rows:,}. A conformance count over an incomplete read is not a count."
            )
        per_file[key] = {
            "rows": n_rows,
            "row_groups": n_groups,
            "distinct_tags": len(file_tally["tags"]),
        }
        _merge(total, file_tally)
        print(f"[scan] {key}: done, {len(file_tally['tags']):,} distinct tags", flush=True)

    if len(total["tags"]) > MAX_DISTINCT_TAGS:
        raise RuntimeError(
            f"{len(total['tags']):,} distinct lineage tags, over the {MAX_DISTINCT_TAGS:,} "
            "tripwire. The tag field is not the small controlled vocabulary D-020 found; "
            "stop and characterise it before emitting a histogram."
        )
    return _report(total, per_file)


def _report(tally: dict[str, Any], per_file: dict[str, Any]) -> dict[str, Any]:
    """Shape the tally into the artefact, with the structural verdict attached."""
    tags = tally["tags"]
    parsed = {raw: cf.parse_lineage_tag(raw) for raw in tags}
    malformed = {raw: list(t.malformed) for raw, t in parsed.items() if t.is_malformed}
    one_row_one_record = (
        tally["rows_multi_tag"] == 0
        and tally["rows_last_block_full"] == 0
        and tally["rows_no_tag"] == 0
    )
    return {
        "rows": tally["rows"],
        "per_file": per_file,
        "distinct_tags": len(tags),
        # Key-sorted on write, like every artefact here, so a re-run diffs cleanly. Read the
        # counts, not the order.
        "tag_counts": dict(tags),
        "sequence_chars": tally["sequence_chars"],
        "total_chars": tally["total_chars"],
        "max_row_chars": tally["max_row_chars"],
        "blocks_per_row": {str(k): v for k, v in sorted(tally["blocks_per_row"].items())},
        "structure": {
            "one_row_one_record": one_row_one_record,
            "rows_multi_tag": tally["rows_multi_tag"],
            "rows_last_block_full": tally["rows_last_block_full"],
            "rows_no_tag": tally["rows_no_tag"],
            "multi_tag_examples": tally["multi_tag_examples"],
            "block_chars": cf.BLOCK_CHARS,
            "why_it_matters": (
                "Every count A7.1 publishes is a count of records. A row holding more than one "
                "distinct tag, or ending on a full-length block, breaks the identification of "
                "a row with a record; `one_row_one_record` false means the conformance numbers "
                "must be reported per row and said to be per row."
            ),
        },
        "malformed_tags": malformed,
        "rank_depth": {
            str(d): sum(n for raw, n in tags.items() if parsed[raw].depth == d)
            for d in sorted({t.depth for t in parsed.values()})
        },
        "realms": _realms(tags, parsed),
    }


def _realms(tags: dict[str, int], parsed: dict[str, cf.LineageTag]) -> dict[str, int]:
    out: collections.Counter = collections.Counter()
    for raw, n in tags.items():
        out[parsed[raw].taxonomy.get("realm", "(none)")] += n
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# --------------------------------------------------------------------------------------
# The FASTA arm — Evo 2's IMG/VR component
# --------------------------------------------------------------------------------------


def scan_fasta(
    bucket: str, prefix: str, key: str, *, progress: float, max_headers: int | None = None
) -> dict[str, Any]:
    """Inventory the IMG/VR FASTA's headers. One gzip stream, therefore one thread.

    This arm cannot test a single published rule: the headers carry an IMG/VR accession and no
    taxonomy, so the predicates have nothing to read. What it produces is the other thing A7.1
    needs and does not have — the identity of every record on the output side of the filter, in
    the accession space of the filter's input. A later task that acquires IMG/VR v4 joins on
    this and gets both the forward diff for Evo 2's release and the converse check this task
    cannot run at all.
    """
    full = f"{prefix}/{key}" if prefix else key
    client = _client()
    # Ranged chunk reads rather than one streaming GET of the whole object. Two reasons, one
    # of them discovered the hard way: a single GET of 11 GB does not begin delivering through
    # this project's outbound proxy, so the arm could not be smoke-tested at all before launch;
    # and a ranged reader resumes where a dropped connection left off, which is the same
    # lesson `amazebio.uniref.ResumableRead` exists for.
    body = io.BufferedReader(S3RandomRead(client, bucket, full), buffer_size=1 << 23)
    headers = 0
    accessions: collections.Counter = collections.Counter()
    sample: list[str] = []
    with_sep: collections.Counter = collections.Counter()
    seq_chars = 0
    started = last = time.time()
    with gzip.GzipFile(fileobj=body) as gz:
        for raw in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if raw.startswith(">"):
                headers += 1
                head = raw[1:].strip()
                if len(sample) < 20:
                    sample.append(head)
                first = head.split()[0] if head.split() else ""
                accessions[first.split("_")[0] if "_" in first else first] += 1
                with_sep[len([c for c in head if c in "|;"])] += 1
                if progress and time.time() - last >= progress:
                    last = time.time()
                    print(
                        f"[scan] imgvr: {headers:,} headers  {time.time() - started:,.0f}s",
                        flush=True,
                    )
                if max_headers is not None and headers >= max_headers:
                    break
            else:
                seq_chars += len(raw.strip())
    # Whether any sampled header carries a rank-prefixed field at all. If one ever does, the
    # claim that this release's taxonomy does not travel with its records is wrong and the
    # whole FASTA arm becomes testable — so it is measured rather than restated from D-020.
    lineage_like = any("__" in head for head in sample)
    return {
        "headers": headers,
        "complete": max_headers is None,
        "sequence_chars": seq_chars,
        "accession_prefixes": dict(accessions.most_common(50)),
        "header_sample": sample,
        "delimiters_per_header": {str(k): v for k, v in sorted(with_sep.items())},
        "carries_lineage": bool(lineage_like),
        "note": (
            "Headers carry IMG/VR accessions and no taxonomic lineage, so no published Evo rule "
            "can be re-executed against this release. The inventory is the join key a later "
            "acquisition of IMG/VR v4 needs; it is not a conformance result."
        ),
    }


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--release", choices=sorted(RELEASE_KEYS), required=True)
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--outdir", default=None, help="default: artifacts/a7-1/<release>")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--progress-seconds", type=float, default=60.0)
    ap.add_argument(
        "--row-groups",
        type=int,
        default=None,
        help="scan only the first N row groups of each file — a smoke run, never "
        "a result; the artefact records that it was partial",
    )
    ap.add_argument(
        "--max-headers",
        type=int,
        default=None,
        help="stop the FASTA arm after N headers — a smoke run, never a result",
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        default=None,
        help="the commit this code came from, for a run with no git checkout",
    )
    args = ap.parse_args(argv)

    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.rstrip("/")
    outdir = Path(args.outdir or f"artifacts/a7-1/{args.release}")
    keys = RELEASE_KEYS[args.release]

    with run(
        "A7.1",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty or bool(args.code_commit),
        manifest_name=f"run-scan-{args.release}.json",
        durable=objectstore.durable_results("a7-1"),
    ) as m:
        m.parameter("release", args.release)
        m.parameter("block_chars", cf.BLOCK_CHARS)
        m.parameter("max_distinct_tags", MAX_DISTINCT_TAGS)
        m.parameter("row_groups_limit", args.row_groups)
        m.parameter("max_headers", args.max_headers)
        m.parameter("workers", args.workers)
        if args.code_commit:
            m.parameter("code_commit", args.code_commit)
            m.note(
                "Launched with no git checkout, so the commit is passed in rather than "
                "discovered; see AGENTS.md on running work on EC2."
            )
        client = _client()
        for key in keys:
            full = f"{prefix}/{key}" if prefix else key
            head = client.head_object(Bucket=bucket, Key=full)
            m.input_url(
                f"s3://{bucket}/{full}",
                role="released-corpus",
                bytes=head["ContentLength"],
                verified=False,
            )
        m.note(
            "No genomic sequence is read into the output: each row's sequence is measured and "
            "dropped. The artefact holds lineage tags, accessions and counts only."
        )

        if args.release == "opengenome-stage2":
            if args.row_groups:
                result = _smoke_parquet(bucket, prefix, keys, args)
            else:
                result = scan_parquet(
                    bucket, prefix, keys, workers=args.workers, progress=args.progress_seconds
                )
        else:
            result = scan_fasta(
                bucket,
                prefix,
                keys[0],
                progress=args.progress_seconds,
                max_headers=args.max_headers,
            )

        result["release"] = args.release
        result["partial"] = bool(args.row_groups or args.max_headers)
        out = outdir / f"scan-{args.release}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="scan")
        print(f"[scan] wrote {out}", flush=True)

        if args.upload_results:
            key = (
                f"{prefix}/results/a7-1/scan-{args.release}.json"
                if prefix
                else f"results/a7-1/scan-{args.release}.json"
            )
            payload = out.read_bytes()
            client.put_object(Bucket=bucket, Key=key, Body=payload)
            m.output_object(f"s3://{bucket}/{key}", bytes=len(payload), role="scan")
            manifest_key = key.replace("scan-", "run-scan-")
            print(f"[scan] uploaded s3://{bucket}/{key}", flush=True)
            # The manifest goes up after the result, so a manifest present in the store always
            # describes a result that is also present.
            m.write(outdir / f"run-scan-{args.release}.json")
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=(outdir / f"run-scan-{args.release}.json").read_bytes(),
            )
    return 0


def _smoke_parquet(bucket: str, prefix: str, keys: tuple[str, ...], args: Any) -> dict[str, Any]:
    """A bounded read of the first N row groups per file, for checking the pipeline runs."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    client = _client()
    total = _blank_tally()
    per_file = {}
    for key in keys:
        full = f"{prefix}/{key}" if prefix else key
        meta = pq.ParquetFile(pa.PythonFile(S3RandomRead(client, bucket, full), mode="rb")).metadata
        groups = list(range(min(args.row_groups, meta.num_row_groups)))
        tally = _scan_row_groups(bucket, full, groups)
        per_file[key] = {
            "rows": tally["rows"],
            "row_groups": len(groups),
            "distinct_tags": len(tally["tags"]),
        }
        _merge(total, tally)
        print(f"[scan] {key}: {tally['rows']:,} rows (partial)", flush=True)
    return _report(total, per_file)


if __name__ == "__main__":
    raise SystemExit(main())

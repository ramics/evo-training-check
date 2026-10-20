#!/usr/bin/env python3
"""Count Evo 2's viral component in its *other* representation, for A7.3.

A7.2 established that Evo 2's released IMG/VR component carries 264,570 records the
procedure Evo 2 adopts by reference removes. That is the larger of the two conformance
failures in this project, and before it is written up as a conformance mismatch one
alternative has to be ruled out rather than mentioned: that the FASTA tree is a
pre-filter staging artefact and the filter was applied further down the pipeline, so
that the training format — the `json/` tree — carries the filtered set.

`policies/evo.md` §7 is the reason this is live rather than paranoid: it records that
the FASTA and JSON trees are not a strict mirror of one another.

The check is a count, and it is decisive in one direction. The JSON records carry a bare
`text` field with no accession and no lineage (see `amazebio.opengenome`'s docstring), so
the two trees cannot be joined record by record. What they can be compared on is how much
is there. If the JSON tree holds the same number of records and the same number of
nucleotides as the FASTA tree, the FASTA is not a pre-filter artefact and the alternative
is dead. If it holds about 264,570 records fewer, the alternative is alive and A7.3's
headline is wrong as stated.

Two things about the shape of the work.

**One gzip stream is one thread.** Six files, four of them large, and a gzip member cannot
be decompressed in parallel — but the six are independent, so the parallelism here is six
and the honest instance size is still none (AGENTS.md's test is data movement that is free
in-region; this reads from HuggingFace, which is metered wherever it runs). It streams in
the session container and never holds a file.

**Nothing is written to the corpus bucket.** This reads the release from its publisher and
writes one small JSON report. The staged copy is the FASTA; the JSON tree is deliberately
unstaged (`OG2_COMPONENTS`), and a pass that only needs counts is not a reason to make
10.4 GB permanent in a bucket with no delete.

    python3 tools/evo2_json_tree.py
    python3 tools/evo2_json_tree.py --max-records 5000   # smoke run, never a result
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import io
import json
import time
from pathlib import Path
from typing import Any

from amazebio import objectstore
from amazebio import opengenome as og
from amazebio.repro import run
from amazebio.uniref import ResumableRead

#: The component whose two representations are being compared.
FASTA_PATH = "fasta/plasmids_phage/imgvr.fasta.gz"
JSON_PREFIX = "json/pretraining_or_both_phases/imgvr_untagged/"

#: What A7.2 measured on the FASTA side, so the comparison is against a recorded figure
#: rather than against whatever happens to be in the output directory. Both come from
#: `corpora/results/a7-2/evo2-accessions.json`.
FASTA_RECORDS = 2_957_495
FASTA_SEQUENCE_CHARS = 38_877_282_216

#: A7.2's forward-direction count: released records the published procedure removes.
EVO2_FORWARD_MISMATCH = 264_570


class _Raw(io.RawIOBase):
    """Adapt `ResumableRead` to the file protocol `gzip` and `BufferedReader` expect.

    `ResumableRead` offers `read` and nothing else; it is used elsewhere by callers that
    drive it directly. Buffering it is what keeps the socket reads large while the gzip
    layer asks for small ones.
    """

    def __init__(self, inner: ResumableRead) -> None:
        self._inner = inner

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        chunk = self._inner.read(len(buffer))
        buffer[: len(chunk)] = chunk
        return len(chunk)


def _reader(url: str, size: int) -> io.BufferedReader:
    return io.BufferedReader(_Raw(ResumableRead(url=url, expected_bytes=size)), buffer_size=1 << 23)


def count_file(
    url: str,
    size: int,
    *,
    max_records: int | None = None,
    progress: float = 120.0,
    label: str = "",
) -> dict[str, Any]:
    """Stream one `.jsonl.gz` and return its record count and nucleotide total.

    The length histogram is coarse on purpose: it exists to show that the records are whole
    sequences rather than fixed-width training windows, which is what makes a record count
    comparable across the two representations at all.
    """
    records = 0
    chars = 0
    shortest: int | None = None
    longest = 0
    buckets: dict[str, int] = {}
    unparsable = 0
    missing_text = 0
    started = last = time.time()

    with gzip.GzipFile(fileobj=_reader(url, size)) as gz:
        for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                unparsable += 1
                continue
            text = record.get("text")
            if not isinstance(text, str):
                missing_text += 1
                continue
            n = len(text)
            records += 1
            chars += n
            shortest = n if shortest is None else min(shortest, n)
            longest = max(longest, n)
            edge = 1 << max(0, n.bit_length() - 1)
            buckets[str(edge)] = buckets.get(str(edge), 0) + 1
            if max_records is not None and records >= max_records:
                break
            now = time.time()
            if now - last >= progress:
                last = now
                rate = records / max(1e-9, now - started)
                print(
                    f"  {label}: {records:,} records, {chars:,} nt, {rate:,.0f} rec/s",
                    flush=True,
                )

    return {
        "records": records,
        "sequence_chars": chars,
        "shortest": shortest,
        "longest": longest,
        "length_buckets": dict(sorted(buckets.items(), key=lambda kv: int(kv[0]))),
        "unparsable_lines": unparsable,
        "records_without_text": missing_text,
        "partial": max_records is not None,
    }


def compare(total_records: int, total_chars: int, *, partial: bool) -> dict[str, Any]:
    """State what the two totals do and do not settle.

    The verdict is three-valued for the same reason A0.4's is (D-207): "the counts match"
    and "the counts differ by the mismatch" are both findings, and "they differ by
    something else" is a third thing that must not be rounded into either.
    """
    if partial:
        return {
            "verdict": "not_measured",
            "why": "a bounded read; a smoke run is never a result",
        }
    record_delta = FASTA_RECORDS - total_records
    char_delta = FASTA_SEQUENCE_CHARS - total_chars
    if record_delta == 0 and char_delta == 0:
        verdict = "same_content"
        why = (
            "the JSON tree holds the same records and the same nucleotides as the FASTA "
            "tree, so the FASTA is not a pre-filter staging artefact and the alternative "
            "that the filter was applied further down the pipeline is ruled out"
        )
    elif record_delta == EVO2_FORWARD_MISMATCH:
        verdict = "filtered_downstream"
        why = (
            "the JSON tree holds exactly the forward mismatch fewer records than the FASTA "
            "tree, which is what a filter applied between the two representations would "
            "look like; A7.3's headline does not stand as stated"
        )
    else:
        verdict = "differs_otherwise"
        why = (
            "the two representations differ by an amount that is neither zero nor the "
            "forward mismatch, so neither reading is supported and the difference is "
            "itself the thing to explain"
        )
    return {
        "verdict": verdict,
        "why": why,
        "fasta_records": FASTA_RECORDS,
        "json_records": total_records,
        "record_delta": record_delta,
        "fasta_sequence_chars": FASTA_SEQUENCE_CHARS,
        "json_sequence_chars": total_chars,
        "sequence_char_delta": char_delta,
        "forward_mismatch_for_reference": EVO2_FORWARD_MISMATCH,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", default="artifacts/a7-3")
    ap.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="stop each file after this many records. A smoke run, marked partial in the "
        "artefact and never a result.",
    )
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--progress", type=float, default=120.0)
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    release = og.RELEASES["opengenome2"]
    blobs = sorted(
        (b for b in og.fetch_tree(release) if b.path.startswith(JSON_PREFIX)),
        key=lambda b: b.path,
    )
    if not blobs:
        raise SystemExit(f"no files under {JSON_PREFIX} in {release.dataset}@{release.revision}")

    # A smoke run publishes nothing. The corpus bucket withholds `s3:DeleteObject`, so a
    # bounded read that reaches the durable prefix is permanent and indistinguishable from
    # a result at a glance — which is how a 20-record part landed in A2.6's census prefix.
    smoke = args.max_records is not None
    with run(
        "A7.3",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-json-tree.json",
        durable=None if smoke else objectstore.durable_results("a7-3"),
        durable_exempt="a bounded smoke read, marked partial and never cited" if smoke else None,
    ) as m:
        m.parameter("release", release.dataset)
        m.parameter("revision", release.revision)
        m.parameter("json_prefix", JSON_PREFIX)
        m.parameter("fasta_path", FASTA_PATH)
        m.parameter("fasta_records", FASTA_RECORDS)
        m.parameter("fasta_sequence_chars", FASTA_SEQUENCE_CHARS)
        m.parameter("max_records", args.max_records)
        m.note(
            "Counts only. The JSON records carry no accession, so the two representations "
            "are compared on how much is there, never joined record by record."
        )
        for blob in blobs:
            m.input_url(
                og.resolve_url(release, blob.path),
                role="opengenome2-json-viral",
                verified=False,
            )

        per_file: dict[str, dict[str, Any]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(
                    count_file,
                    og.resolve_url(release, blob.path),
                    blob.size,
                    max_records=args.max_records,
                    progress=args.progress,
                    label=blob.path.rsplit("/", 1)[-1],
                ): blob
                for blob in blobs
            }
            for future in concurrent.futures.as_completed(futures):
                blob = futures[future]
                row = future.result()
                row["bytes"] = blob.size
                row["sha256"] = blob.sha256
                per_file[blob.path] = row
                print(
                    f"done {blob.path.rsplit('/', 1)[-1]}: "
                    f"{row['records']:,} records, {row['sequence_chars']:,} nt",
                    flush=True,
                )

        total_records = sum(r["records"] for r in per_file.values())
        total_chars = sum(r["sequence_chars"] for r in per_file.values())
        report = {
            "release": release.dataset,
            "revision": release.revision,
            "files": {path: per_file[path] for path in sorted(per_file)},
            "totals": {
                "records": total_records,
                "sequence_chars": total_chars,
                "files": len(per_file),
                "bytes": sum(r["bytes"] for r in per_file.values()),
            },
            "comparison": compare(total_records, total_chars, partial=args.max_records is not None),
        }
        out = outdir / "json-tree.json"
        out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(out, role="json-tree-count")

    print(json.dumps(report["comparison"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

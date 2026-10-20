#!/usr/bin/env python3
"""What the 39,974 repeated accessions in Evo 2's released FASTA are, for A7.3.

A7.1 and A7.2 both counted them and both declined to explain them, because the header
cannot: `IMGVR_UViG_<taxon>_<n>` is the whole identifier, and the same identifier appearing
twice is equally consistent with a duplicated entry and with one record published in
several pieces. A7.2 reported the count beside the vOTU comparison rather than inside it,
on the grounds that folding it in would read as a deduplication failure the evidence could
not establish. A7.3 settles it, which means reading a base — the one thing A7.2
deliberately did not do.

**The test is arithmetic against the publisher's own length.** IMG/VR's sequence
information table gives a `Length` for every UViG. For a repeated accession, three
outcomes are distinguishable and they mean different things:

* every piece has the same length and it equals IMG/VR's — the record is published more
  than once, and a model trained on the FASTA would see it more than once;
* the pieces sum to IMG/VR's length — the record is published in parts, and the
  accession count rather than the record count is the one that means anything;
* neither — the release and the input disagree about the sequence, which is a third
  finding and must not be rounded into either of the first two.

The outcomes may be mixed across the 39,974, so each is counted rather than one verdict
being assigned to the whole population.

**Why this reads the corpus rather than an intermediate.** There is no reduced artefact
carrying per-record lengths; A7.2's inventory packs accessions and discards everything
else. The pass is one forward read of an 11.2 GB gzip member, which is one thread however
large the machine, so the honest instance size is none — the same conclusion A7.1 and A7.2
reached for the same file (D-050).

    python3 tools/evo2_duplicates.py
    python3 tools/evo2_duplicates.py --max-headers 200000   # smoke run, never a result
"""

from __future__ import annotations

import argparse
import array
import collections
import gzip
import io
import json
import time
from pathlib import Path
from typing import Any

from amazebio import imgvr, objectstore
from amazebio.repro import run

#: Evo 2's released viral component, as staged by A1.2.
RELEASE_KEY = (
    "corpora/opengenome2/84d2a7e690c8bb395d1f4868822dfa031ea561c6"
    "/fasta/plasmids_phage/imgvr.fasta.gz"
)

#: IMG/VR v4.1, the release A7.2 identified as the procedure's input (D-071). The
#: high-confidence table is the one the released accessions come from: every released
#: accession is a high-confidence vOTU representative.
IMGVR_KEY = "corpora/imgvr/2022-12-20/IMGVR_all_Sequence_information-high_confidence.tsv"
IMGVR_UVIG_COLUMN = 0
IMGVR_LENGTH_COLUMN = 6

#: What A7.1 and A7.2 both measured and neither explained.
EXPECTED_REPEATED_ACCESSIONS = 39_974


def unpack(packed: int) -> str:
    """The accession a packed key came from, for the examples in the artefact.

    `imgvr.uvig_key` packs `taxon_oid * 10**7 + n`; the suffix is written with six digits
    in the publisher's own headers. An example nobody can look up is not an example.
    """
    return f"IMGVR_UViG_{packed // 10**7}_{packed % 10**7:06d}"


def scan_lengths(
    bucket: str, key: str, *, max_headers: int | None, progress: float
) -> tuple[array.array, array.array, dict[str, list[int]], dict[str, Any]]:
    """One forward pass: every record's packed accession and its sequence length.

    Accessions that do not pack — the 1,783 giant-virus MAG forms — are carried in a dict
    on their string, because dropping them would silently remove from this question exactly
    the records a eukaryote-virus filter is judged on.

    **Read as bytes.** This publisher writes each record unwrapped, as one header line and
    one sequence line, so the stream is 5.9 million lines rather than the hundreds of
    millions a wrapped FASTA would be. Decoding 38.9 GB of it to text to look at the first
    character is the whole saving here; nothing downstream needs a `str` except the header,
    which is 29 bytes.
    """
    client = objectstore.client()
    body = io.BufferedReader(objectstore.S3RandomRead(client, bucket, key), buffer_size=1 << 23)
    keys = array.array("q")
    lengths = array.array("q")
    unpackable: dict[str, list[int]] = collections.defaultdict(list)
    headers = 0
    current: int | None = None
    current_name: str | None = None
    running = 0
    started = last = time.time()

    def flush() -> None:
        if current is not None:
            keys.append(current)
            lengths.append(running)
        elif current_name is not None:
            unpackable[current_name].append(running)

    with gzip.GzipFile(fileobj=body) as gz:
        for raw in gz:
            if not raw.startswith(b">"):
                running += len(raw.rstrip())
                continue
            flush()
            running = 0
            headers += 1
            name = raw[1:].split()[0].decode("utf-8", "replace")
            try:
                current, current_name = imgvr.uvig_key(name), None
            except ValueError:
                # `UvigNotPackable` for the GVMAG shape, plain `ValueError` for anything
                # else; both mean the string is the key, and neither may drop the record.
                current, current_name = None, name
            if max_headers is not None and headers > max_headers:
                headers -= 1
                current = current_name = None
                break
            now = time.time()
            if now - last >= progress:
                last = now
                rate = headers / max(1e-9, now - started)
                print(f"  {headers:,} records read, {rate:,.0f} rec/s", flush=True)
        flush()

    return keys, lengths, dict(unpackable), {"headers": headers, "partial": max_headers is not None}


def repeated(
    keys: array.array, lengths: array.array, unpackable: dict[str, list[int]]
) -> dict[str, list[int]]:
    """Accessions seen more than once, with each occurrence's length, keyed by accession.

    Both populations come out on the same key, which is the accession as the publisher
    writes it. Keeping the giant-virus MAG forms in a separate shape all the way through
    would have left them out of the classification, and they are the records a
    eukaryote-virus filter is judged on — the one place it would be worst to lose any.
    """
    seen: dict[int, list[int]] = collections.defaultdict(list)
    for k, n in zip(keys, lengths, strict=True):
        seen[k].append(n)
    out = {unpack(k): v for k, v in seen.items() if len(v) > 1}
    out.update({k: v for k, v in unpackable.items() if len(v) > 1})
    return out


def published_lengths(bucket: str, key: str, wanted: set[str]) -> dict[str, int]:
    """IMG/VR's own `Length` for the accessions asked for, from its sequence table.

    Matched on the accession string rather than on a packed key, so the giant-virus MAG
    forms resolve by the same route as everything else. An empty `wanted` skips the read:
    scanning 1.9 GB to find nothing is how the first smoke run spent its whole budget.
    """
    if not wanted:
        return {}
    client = objectstore.client()
    body = io.BufferedReader(objectstore.S3RandomRead(client, bucket, key), buffer_size=1 << 23)
    out: dict[str, int] = {}
    # The accession is the first field, so a partition finds it without splitting all
    # nineteen; the full split happens only on the few thousand rows that match. Over 5.6
    # million rows that is the difference between a minute and a timeout.
    want_bytes = {w.encode() for w in wanted}
    started = last = time.time()
    next(body, None)  # header
    rows = 0
    for rows, line in enumerate(body, start=1):
        uvig = line.partition(b"\t")[0]
        if uvig in want_bytes:
            fields = line.rstrip(b"\n").split(b"\t")
            if len(fields) > IMGVR_LENGTH_COLUMN:
                out[uvig.decode()] = int(fields[IMGVR_LENGTH_COLUMN])
                if len(out) == len(wanted):
                    break
        now = time.time()
        if now - last >= 60.0:
            last = now
            print(
                f"  input table: {rows:,} rows, {len(out):,}/{len(wanted):,} found, "
                f"{rows / max(1e-9, now - started):,.0f} rows/s",
                flush=True,
            )
    return out


def classify(occurrences: dict[str, list[int]], published: dict[str, int]) -> dict[str, Any]:
    """Assign each repeated accession to one of the three outcomes, and count them.

    A verdict is never assigned to the population from a majority: the three counts are
    reported, and whichever dominates is a description rather than a conclusion about the
    rest.
    """
    counts: collections.Counter = collections.Counter()
    extra_records = 0
    extra_nucleotides = 0
    examples: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    occurrence_histogram: collections.Counter = collections.Counter()

    for accession, lengths in occurrences.items():
        occurrence_histogram[len(lengths)] += 1
        want = published.get(accession)
        total = sum(lengths)
        if want is None:
            outcome = "not_in_the_input_table"
        elif len(set(lengths)) == 1 and lengths[0] == want:
            outcome = "republished_whole"
            extra_records += len(lengths) - 1
            extra_nucleotides += total - want
        elif total == want:
            outcome = "published_in_parts"
        else:
            outcome = "disagrees_with_the_input"
        counts[outcome] += 1
        if len(examples[outcome]) < 10:
            examples[outcome].append(
                {"accession": accession, "lengths": lengths, "imgvr_length": want}
            )

    return {
        "repeated_accessions": len(occurrences),
        "by_outcome": dict(sorted(counts.items())),
        "occurrences_per_accession": dict(sorted(occurrence_histogram.items())),
        "republished_whole": {
            "surplus_records": extra_records,
            "surplus_nucleotides": extra_nucleotides,
            "why_it_matters": (
                "a record published more than once is a record a model trained on this "
                "representation sees more than once; it is an upsampling nobody declared"
            ),
        },
        "examples": {k: v for k, v in sorted(examples.items())},
        "outcomes": {
            "republished_whole": "every occurrence has IMG/VR's own length for the accession",
            "published_in_parts": "the occurrences sum to IMG/VR's length for the accession",
            "disagrees_with_the_input": "neither; the release and the input disagree",
            "not_in_the_input_table": "the accession is not in the high-confidence table",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--outdir", default="artifacts/a7-3")
    ap.add_argument("--max-headers", type=int, default=None)
    ap.add_argument("--progress", type=float, default=180.0)
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    smoke = args.max_headers is not None
    bucket = objectstore.CORPORA_BUCKET

    with run(
        "A7.3",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-duplicates.json",
        durable=None if smoke else objectstore.durable_results("a7-3"),
        durable_exempt="a bounded smoke read, marked partial and never cited" if smoke else None,
    ) as m:
        m.input_url(f"s3://{bucket}/{RELEASE_KEY}", role="evo2-released-viral", verified=True)
        m.input_url(f"s3://{bucket}/{IMGVR_KEY}", role="imgvr-sequence-information", verified=True)
        m.parameter("max_headers", args.max_headers)
        m.parameter("expected_repeated_accessions", EXPECTED_REPEATED_ACCESSIONS)
        m.note(
            "Reads a base, which A7.2 deliberately did not. The three outcomes are counted "
            "separately; no verdict is assigned to the population from a majority."
        )

        keys, lengths, unpackable, scan_meta = scan_lengths(
            bucket, RELEASE_KEY, max_headers=args.max_headers, progress=args.progress
        )
        print(f"read {scan_meta['headers']:,} records", flush=True)
        occurrences = repeated(keys, lengths, unpackable)
        unpackable_repeated = {k: v for k, v in unpackable.items() if len(v) > 1}
        print(
            f"{len(occurrences):,} accessions repeated, of which "
            f"{len(unpackable_repeated):,} are the giant-virus MAG form",
            flush=True,
        )
        published = published_lengths(bucket, IMGVR_KEY, set(occurrences))
        print(f"{len(published):,} of them found in the input table", flush=True)

        report = {
            "task": "A7.3",
            "release_key": RELEASE_KEY,
            "imgvr_key": IMGVR_KEY,
            "records_read": scan_meta["headers"],
            "partial": scan_meta["partial"],
            "expected_repeated_accessions": EXPECTED_REPEATED_ACCESSIONS,
            "unpackable_accessions_repeated": len(unpackable_repeated),
            "result": classify(occurrences, published),
        }
        out = outdir / "duplicates.json"
        out.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
        m.output_file(out, role="repeated-accessions")

    print(json.dumps(report["result"]["by_outcome"], indent=1))
    print(json.dumps(report["result"]["republished_whole"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Count the staged IMG/VR releases, per component, against the stated figures — A1.7.

This is the denominator A1.7 exists to supply. Every conformance claim A7.2 makes about what
Evo 1's filter *removed* is a set operation against the pre-filter population, and a count of
what is absent from a corpus cannot be taken from that corpus. Until this ran, the only
IMG/VR numbers in the repo were A7.1's census of what survived into the released Evo 1 corpus
and Evo 1's own Table S3, both of which are post-filter.

What it counts, streaming each staged table out of object storage a chunk at a time:

* **records** per table — lines after the header;
* the **confidence split** in the unfiltered sequence-information table, which is what Evo 1's
  first published rule gates on;
* **distinct vOTUs**, which its second rule deduplicates by;
* **host-domain assignment**, which its third rule counts prokaryotic hosts with.

Nothing here reads a base. The nucleotide and protein sets are not staged and answer no
conformance question (D-053).

Three consistency checks fall out and are reported rather than asserted, because a disagreement
is a finding and not a crash:

1. The high-confidence file's record count against the `High-confidence` count in the unfiltered
   file. The publisher derives one from the other, so they should agree exactly.
2. The two releases against each other. v4.1 is an erratum of v4 touching "a few sequences/rows"
   in this exact table (D-063), so the difference should be small. A structural difference means
   our reading is wrong, not the publisher's.
3. The pre-filter total against Evo 1's own post-filter Table S3 figure of 2,653,046 records
   (D-055). That ratio is the headline this acquisition was blocking.

    python3 tools/imgvr_composition.py                      # artifacts/a1-7/composition.json
    python3 tools/imgvr_composition.py --release 2022-09-20 # one release
    python3 tools/imgvr_composition.py --print              # and to stdout, for reading
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import imgvr, objectstore
from amazebio.repro import run

OUTDIR = Path("artifacts/a1-7")
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"

#: Evo 1's own published figure for the IMG/VR component of its corpus, Table S3 p43, as
#: transcribed in D-055. Post-filter: it is what Evo 1 kept, not what IMG/VR holds. The
#: comparison against our pre-filter count is the point of recording it here.
EVO1_TABLE_S3_RECORDS = 2_653_046

#: A7.1's census of the same component in the *released* corpus, which exceeds Evo 1's own
#: stated figure by one record. Unexplained and reported rather than rounded away (D-055).
A7_1_RELEASED_RECORDS = 2_653_047

#: Columns of the sequence-information table, by header text rather than by index: the index is
#: stable across both releases today and a header lookup costs nothing and survives a re-cut.
COL_UVIG = "UVIG"
COL_VOTU = "vOTU"
COL_CONFIDENCE = "Confidence"
COL_HOST = "Host taxonomy prediction"

_CHUNK = 1 << 22


def stage_key(date: str, name: str, *, prefix: str) -> str:
    return f"{prefix}/imgvr/{date}/{name}" if prefix else f"imgvr/{date}/{name}"


def _lines(client: Any, bucket: str, key: str):
    """Stream one staged object as decoded lines, without holding it in memory.

    The largest table is 5.0 GB. `iter_lines` on a botocore stream buffers unboundedly on
    input without newlines, so this does the chunking itself and keeps only the tail.
    """
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    tail = b""
    while chunk := body.read(_CHUNK):
        tail += chunk
        *complete, tail = tail.split(b"\n")
        for line in complete:
            yield line.decode("utf-8", "replace")
    if tail:
        yield tail.decode("utf-8", "replace")


def _host_domain(value: str) -> str:
    """The domain rank of a host prediction, or a label for its absence.

    The field is a semicolon-joined lineage beginning at `d__`. An empty field and a field of
    bare separators both mean no prediction, and they are counted apart from each other because
    which one the publisher emits is itself under-specified.
    """
    v = value.strip()
    if not v:
        return "(empty)"
    if not v.strip(";"):
        return "(separators only)"
    first = v.split(";")[0].strip()
    if not first.startswith("d__"):
        return f"(unparsed: {first[:24]})"
    return first[3:] or "(empty d__)"


def count_sequence_information(client: Any, bucket: str, key: str) -> dict[str, Any]:
    """Records, confidence split, distinct vOTUs and host domains for one table."""
    rows = _lines(client, bucket, key)
    header = next(rows).split("\t")
    idx = {name: header.index(name) for name in (COL_UVIG, COL_VOTU, COL_CONFIDENCE, COL_HOST)}
    confidence: Counter[str] = Counter()
    host_domain: Counter[str] = Counter()
    votus: set[str] = set()
    records = 0
    malformed = 0
    for line in rows:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != len(header):
            # Counted, not dropped silently and not fatal: a row the publisher emitted that
            # does not fit its own header is exactly the kind of thing D-063's erratum note
            # leads one to expect, and hiding it would hide the finding.
            malformed += 1
            continue
        records += 1
        confidence[fields[idx[COL_CONFIDENCE]].strip()] += 1
        host_domain[_host_domain(fields[idx[COL_HOST]])] += 1
        votus.add(fields[idx[COL_VOTU]].strip())
    return {
        "records": records,
        "malformed_rows": malformed,
        "columns": len(header),
        "confidence": dict(confidence.most_common()),
        "distinct_votus": len(votus),
        "host_domain": dict(host_domain.most_common()),
    }


def count_host_information(client: Any, bucket: str, key: str) -> dict[str, Any]:
    """Rows and distinct UViGs for one host table.

    Rows and UViGs are not the same number here: the table lists *all* host predictions, so one
    UViG can appear more than once. Evo 1's third rule counts prokaryotic hosts, and whether it
    counts rows or genomes is precisely the kind of thing a published rule leaves open.
    """
    rows = _lines(client, bucket, key)
    header = next(rows).split("\t")
    uvig_col = 0
    host_col = header.index("Host taxonomy prediction")
    uvigs: set[str] = set()
    host_domain: Counter[str] = Counter()
    total = 0
    for line in rows:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != len(header):
            continue
        total += 1
        uvigs.add(fields[uvig_col].strip())
        host_domain[_host_domain(fields[host_col])] += 1
    return {
        "rows": total,
        "distinct_uvigs": len(uvigs),
        "columns": len(header),
        "host_domain": dict(host_domain.most_common()),
    }


def reconcile(per_release: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The checks that make this an audit artefact rather than a row of counts.

    Each returns a verdict and the two numbers behind it. A disagreement is reported, never
    raised: `DESIGN.md` §A0 is explicit that under-specification and mismatch are results.
    """
    checks = []
    for date, rel in per_release.items():
        full = rel["components"].get("sequence_information")
        hc = rel["components"].get("sequence_information_high_confidence")
        if full and hc:
            stated = full["confidence"].get("High-confidence")
            checks.append(
                {
                    "check": "high-confidence file matches the confidence label it is derived from",
                    "release": date,
                    "high_confidence_file_records": hc["records"],
                    "high_confidence_label_in_full_file": stated,
                    "agrees": stated == hc["records"],
                }
            )
        if full:
            checks.append(
                {
                    "check": "pre-filter population against Evo 1's own post-filter Table S3",
                    "release": date,
                    "imgvr_records": full["records"],
                    "evo1_table_s3_records": EVO1_TABLE_S3_RECORDS,
                    "a7_1_released_records": A7_1_RELEASED_RECORDS,
                    "retained_fraction_vs_table_s3": (
                        EVO1_TABLE_S3_RECORDS / full["records"] if full["records"] else None
                    ),
                }
            )
    dates = sorted(per_release)
    if len(dates) == 2:
        a, b = (per_release[d]["components"].get("sequence_information") for d in dates)
        if a and b:
            checks.append(
                {
                    "check": "v4 against its v4.1 erratum: 'a few sequences/rows' (D-063)",
                    "releases": dates,
                    "records": [a["records"], b["records"]],
                    "record_difference": b["records"] - a["records"],
                    "distinct_votus": [a["distinct_votus"], b["distinct_votus"]],
                    "high_confidence": [
                        a["confidence"].get("High-confidence"),
                        b["confidence"].get("High-confidence"),
                    ],
                }
            )
    return checks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", choices=sorted(imgvr.RELEASES), action="append")
    ap.add_argument("--s3-uri", default=None)
    ap.add_argument("--outdir", default=str(OUTDIR))
    ap.add_argument("--print", dest="show", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    import os

    import boto3

    uri = args.s3_uri or os.environ.get("AMAZEBIO_S3_URI")
    if not uri or not uri.startswith("s3://"):
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI, as s3://bucket/prefix")
    bucket, _, prefix = uri[len("s3://") :].partition("/")
    client = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)

    releases = args.release or sorted(imgvr.RELEASES)
    outdir = Path(args.outdir)

    # A distinct manifest name: `tools/stage_imgvr.py` writes `run.json` into this same
    # outdir, and a second pipeline silently overwriting the staging pass's provenance
    # would lose the only record of how the bytes got there.
    with run(
        "A1.7",
        seed=None,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        manifest_name="run-composition.json",
        durable=objectstore.durable_results("a1-7"),
    ) as m:
        m.parameter("releases", releases)
        m.parameter("source", uri)
        m.parameter("evo1_table_s3_records", EVO1_TABLE_S3_RECORDS)
        m.parameter("a7_1_released_records", A7_1_RELEASED_RECORDS)
        m.note(
            "Counts are over the staged metadata only. The nucleotide and protein sets are "
            "not staged and answer no conformance question (D-053)."
        )
        m.note(
            "Stated counts available from a primary source are Evo 1's own Table S3 figure "
            "(D-055). The IMG/VR v4 paper's own totals are not transcribed in this repo, so "
            "the publisher's stated population is a gap recorded rather than guessed."
        )

        per_release: dict[str, dict[str, Any]] = {}
        for date in releases:
            release = imgvr.release_on(date)
            components: dict[str, Any] = {}
            for f in imgvr.conformance_inputs(date):
                if f.role == "readme":
                    continue
                key = stage_key(date, f.name, prefix=prefix)
                name = f.role + ("_high_confidence" if f.high_confidence else "")
                print(f"[imgvr] counting {key}", flush=True)
                if f.role == "sequence_information":
                    components[name] = count_sequence_information(client, bucket, key)
                else:
                    components[name] = count_host_information(client, bucket, key)
                components[name]["file"] = f.name
                components[name]["bytes"] = f.bytes
                components[name]["md5"] = f.md5
                # The pin rests on the staging pass, which verified each file against the
                # publisher's md5 before uploading it. This run reads the object and does not
                # re-hash 15.8 GB to say so again, and `verified=False` is the honest record
                # of that: the bytes were read here, they were checked there.
                m.input_url(
                    f"s3://{bucket}/{key}",
                    role=name,
                    bytes=f.bytes,
                    checksum=f.md5,
                    checksum_type="md5",
                    verified=False,
                )
            per_release[date] = {"version": release.version, "components": components}

        doc = {
            "task": "A1.7",
            "releases": per_release,
            "reconciliation": reconcile(per_release),
        }
        out = outdir / "composition.json"
        out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        m.output_file(out, role="composition")

    if args.show:
        _render(doc, sys.stdout)
    return 0


def _render(doc: dict[str, Any], fh: io.TextIOBase) -> None:
    for date, rel in sorted(doc["releases"].items()):
        print(f"\n== {date}  ({rel['version']})", file=fh)
        for name, c in sorted(rel["components"].items()):
            if "records" in c:
                print(
                    f"   {name}: {c['records']:,} records, {c['distinct_votus']:,} vOTUs, "
                    f"{c['malformed_rows']} malformed",
                    file=fh,
                )
                for label, n in c["confidence"].items():
                    print(f"      confidence {label or '(blank)'}: {n:,}", file=fh)
            else:
                print(
                    f"   {name}: {c['rows']:,} rows, {c['distinct_uvigs']:,} distinct UViGs",
                    file=fh,
                )
    print("\n== reconciliation", file=fh)
    for c in doc["reconciliation"]:
        print(f"   {c['check']}", file=fh)
        for k, v in c.items():
            if k != "check":
                print(f"      {k}: {v}", file=fh)


if __name__ == "__main__":
    raise SystemExit(main())

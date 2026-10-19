#!/usr/bin/env python3
"""Index Evo 2's eukaryotic genome component, and report what a sample of it would cost — A2.3.

Pass one of the two-pass acquisition D-182 fixed. It walks the header chain of each of the 90
tars in `fasta/ncbi_eukaryotic_genomes` over HTTP Range reads, transferring 512 bytes per
assembly instead of the assembly, and writes an index of accession, tar, offset and size.

Why this is a pass of its own rather than part of staging:

- **It is the denominator.** Every figure A2.3 reports is "of the assemblies in this component",
  and nothing in the project has counted them. The release states a file count and a byte total,
  not a genome count.
- **It decides what the sample costs before anything irreversible happens.** The corpus bucket
  has no `s3:DeleteObject`, so the sample's realized byte size has to be known *before* the
  upload rather than discovered during it. Members span 4.7 MB to 428 MB compressed, so 1% of the
  assemblies is only approximately 1% of the bytes.
- **It costs almost nothing.** About 8 MB of transfer for the whole component, no writes outside
  `artifacts/`, and no sequence retained anywhere (D-103).

    python3 tools/index_eukaryotes.py --tars 1      # validate against one real tar
    python3 tools/index_eukaryotes.py              # the whole component
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import objectstore  # noqa: E402
from amazebio import opengenome as og  # noqa: E402
from amazebio.eukaryotes import (  # noqa: E402
    COMPONENT,
    Member,
    index_to_rows,
    sampled_members,
    size_summary,
    walk_index,
)
from amazebio.repro import run  # noqa: E402

#: The sampling seed, pinned by D-078 and reused by D-182 so a band here is nested inside every
#: other sampled pass in the project.
SEED = 20261015

#: The rate the project owner approved (D-182). A constant rather than an argparse default, so
#: the figure in the artefact is the figure in the source.
APPROVED_RATE = 0.01

ATTEMPTS = 5
BACKOFF = 2.0


def read_range(path: str, start: int, end: int) -> bytes:
    """One Range read of one blob in the pinned release, with retries.

    A failed read raises rather than returning what arrived. The walk advances by arithmetic on
    what it read, so a truncated header is not a smaller header but a lost block boundary, and
    `walk_index`'s checksum check is the backstop rather than the first line of defence.
    """
    url = og.resolve_url(og.OG2, path)
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF * (attempt + 1))
    raise RuntimeError(f"could not read {path} {start}-{end} after {ATTEMPTS} tries: {last}")


def component_tars(blobs: list[og.Blob]) -> list[og.Blob]:
    """The component's tars, by the prefix D-182 pinned, sorted by path."""
    tars = [b for b in blobs if b.path.startswith(COMPONENT)]
    if not tars:
        raise RuntimeError(
            f"the pinned release exposes no files under {COMPONENT!r}; the component has moved "
            "and the D-182 pin no longer describes it"
        )
    unexpected = [b.path for b in tars if not b.path.endswith(".tar")]
    if unexpected:
        raise RuntimeError(
            f"{COMPONENT} holds non-tar files {unexpected[:4]!r}; the layout D-182 measured has "
            "changed, so an index built from tars alone would not cover the component"
        )
    return sorted(tars, key=lambda b: b.path)


def index_one(blob: og.Blob) -> tuple[str, list[Member], str | None]:
    """Index one tar. A failure is returned rather than raised, so one bad tar still reports."""
    try:
        return blob.path, list(walk_index(blob.path, blob.size, read_range)), None
    except Exception as exc:  # surfaced per tar; the run still fails on any
        return blob.path, [], f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tars", type=int, default=0, help="index the first N tars only (0=all)")
    parser.add_argument("--rate", type=float, default=APPROVED_RATE, help="the band to cost")
    parser.add_argument("--workers", type=int, default=8, help="tars indexed concurrently")
    parser.add_argument("--outdir", default=str(REPO / "artifacts" / "a2-3"))
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    out = Path(args.outdir)
    with run(
        "A2.3",
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        durable=objectstore.durable_results("a2-3"),
        manifest_name="run-index.json",
    ) as m:
        m.parameter("component", COMPONENT)
        m.parameter("release", og.OG2.key)
        m.parameter("revision", og.OG2.revision)
        m.parameter("sample_seed", SEED)
        m.parameter("costed_rate", args.rate)
        m.parameter("approved_rate", APPROVED_RATE)
        m.parameter("decision_refs", ["D-182", "D-078", "D-136"])

        blobs = og.fetch_tree(og.OG2)
        # `verify_manifest` returns a row per quantity whether or not it agrees, so the drift is
        # the disagreeing rows and not the truthiness of the list.
        checks = og.verify_manifest(og.OG2, blobs)
        m.parameter("manifest_checks", checks)
        drift = [row for row in checks if not row["agrees"]]
        if drift:
            # The pin is what every count is attributed to. A release that has moved is a finding
            # to report, not something to index quietly against a changed tree.
            m.parameter("manifest_drift", drift)
            print(f"release has drifted from its pin: {drift}", file=sys.stderr)
            return 2

        in_component = [b for b in blobs if b.path.startswith(COMPONENT)]
        tars = component_tars(blobs)
        if args.tars:
            tars = tars[: args.tars]
        m.parameter("tars_indexed", len(tars))
        m.parameter("tar_bytes", sum(b.size for b in tars))
        for blob in tars:
            # `verified=False` is the honest record: this pass reads 512 bytes per member and
            # never the whole object, so it cannot match the published digest. The pin rests on
            # the tree's own checksum, which the staging pass does verify over the bytes it takes.
            m.input_url(
                og.resolve_url(og.OG2, blob.path),
                role="component tar (headers only)",
                bytes=blob.size,
                checksum=blob.sha256,
                checksum_type="sha256",
                verified=False,
            )

        started = time.time()
        members: list[Member] = []
        failures: dict[str, str] = {}
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for path, found, error in pool.map(index_one, tars):
                done += 1
                if error:
                    failures[path] = error
                    print(f"  [{done}/{len(tars)}] {path}: FAILED {error}", file=sys.stderr)
                    continue
                members.extend(found)
                print(f"  [{done}/{len(tars)}] {path}: {len(found)}", file=sys.stderr)
        elapsed = time.time() - started

        if failures:
            m.parameter("failed_tars", failures)
            print(f"{len(failures)} of {len(tars)} tars could not be indexed", file=sys.stderr)
            return 1

        repeated = sorted(a for a, n in Counter(x.accession for x in members).items() if n > 1)
        band = sampled_members(members, seed=SEED, hi=args.rate)
        summary: dict[str, Any] = {
            "component": COMPONENT,
            "release": og.OG2.key,
            "revision": og.OG2.revision,
            "tars_indexed": len(tars),
            "tars_in_component": len(in_component),
            "complete": len(tars) == len(in_component),
            "elapsed_seconds": round(elapsed, 1),
            "population": size_summary(members),
            "band": {
                "seed": SEED,
                "rate": args.rate,
                "method": "blake2b(seed, assembly_accession) < rate * 2**64",
                "decision_ref": "D-182",
                **size_summary(band),
            },
            "duplicate_accessions": repeated,
        }
        total = summary["population"]["bytes"]
        if total:
            summary["band"]["byte_share"] = round(summary["band"]["bytes"] / total, 6)

        # Written before being declared: `output_file` hashes the file as it records it.
        index_path = out / "assembly-index.json"
        index_path.write_text(
            json.dumps({"summary": summary, "members": index_to_rows(members)}, indent=1) + "\n"
        )
        m.output_file(index_path, role="assembly index")
        summary_path = out / "component-summary.json"
        summary_path.write_text(json.dumps(summary, indent=1) + "\n")
        m.output_file(summary_path, role="component summary")
        if repeated:
            m.note(f"{len(repeated)} accessions appear in more than one tar")

        print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

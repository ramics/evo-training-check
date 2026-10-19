#!/usr/bin/env python3
"""Measure what the retroelement arm costs per model and per megabase — A2.3, D-183.

D-183 pinned the registry, the selection rule and the threshold, and deliberately did **not**
fix the depth, because the per-genome cost was unmeasured. This is the measurement.

Why it is a tool with an artefact rather than a number in a shell:

- **The project has been wrong about this three times.** D-098 found an assumed rate wrong by
  thirty times; D-117 declined to fix a rate on one complete genome and D-149 then measured it
  2.74x cheaper on real draft assemblies; D-179 found D-164's ladder projection short by a
  multiple of the whole budget. "A cost assumed is a design decision taken by accident."
- **It is measured at more than one point, on purpose.** Profile search should be linear in
  models x residues, and the single-point extrapolations above are exactly what went wrong. Two
  or more points let the run report whether it is linear instead of assuming it, so the
  projection carries a check rather than a hope.
- **A depth decision will cite it.** It is the input to the entry that fixes the depth, so it has
  to regenerate from pinned inputs like any other result.

The genomes come from the band D-182 approved, taken as a nested sub-band at the same seed, so
nothing measured here is re-searched later. No sequence is retained: each assembly is fetched to
ephemeral scratch, searched and deleted (D-103).

    python3 tools/calibrate_eve.py --assemblies 2 --models 20 40
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from itertools import islice
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import objectstore  # noqa: E402
from amazebio import opengenome as og  # noqa: E402
from amazebio.eukaryotes import Member, fetch_member, load_index, sampled_members  # noqa: E402
from amazebio.repro import run  # noqa: E402

SEED = 20261015
BAND_RATE = 0.01
ATTEMPTS = 5
BACKOFF = 2.0


def read_range(path: str, start: int, end: int) -> bytes:
    url = og.resolve_url(og.OG2, path)
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF * (attempt + 1))
    raise RuntimeError(f"could not read {path} {start}-{end}: {last}")


def search(models: list[Any], sequences: list[Any], *, cpus: int) -> tuple[float, int]:
    """One timed search. Returns wall seconds and the number of reported hits."""
    import pyhmmer

    started = time.time()
    reported = 0
    for hits in pyhmmer.hmmer.nhmmer(models, sequences, cpus=cpus):
        reported += sum(1 for hit in hits if hit.reported)
    return time.time() - started, reported


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=str(REPO / "artifacts" / "a2-3" / "assembly-index.json"))
    parser.add_argument(
        "--library", default=str(REPO / "data" / "dfam" / "4.0" / "dfam-curated-ltr.hmm")
    )
    parser.add_argument("--assemblies", type=int, default=2, help="band assemblies to search")
    parser.add_argument(
        "--offset", type=int, default=0, help="skip this many band assemblies first"
    )
    parser.add_argument(
        "--models",
        type=int,
        nargs="+",
        default=[10, 20],
        help="model counts to time, two or more so linearity is checked rather than assumed",
    )
    parser.add_argument("--cpus", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--scratch", default=None, help="ephemeral dir for fetched sequence")
    parser.add_argument("--outdir", default=str(REPO / "artifacts" / "a2-3"))
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    from pyhmmer.easel import Alphabet, SequenceFile
    from pyhmmer.plan7 import HMMFile

    scratch = Path(args.scratch or os.environ.get("TMPDIR", "/tmp")) / "a2-3-calibration"
    scratch.mkdir(parents=True, exist_ok=True)
    out = Path(args.outdir)

    with run(
        "A2.3",
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        durable=objectstore.durable_results("a2-3"),
        manifest_name="run-calibration.json",
    ) as m:
        m.parameter("sample_seed", SEED)
        m.parameter("band_rate", BAND_RATE)
        m.parameter("model_counts", args.models)
        m.parameter("assemblies", args.assemblies)
        m.parameter("offset", args.offset)
        m.parameter("cpus", args.cpus)
        m.parameter("decision_refs", ["D-183", "D-103", "D-149"])
        m.tool("pyhmmer", [sys.executable, "-c", "import pyhmmer; print(pyhmmer.__version__)"])

        index = load_index(m.input_file(args.index, role="assembly index"))
        band = sampled_members(index, seed=SEED, hi=BAND_RATE)
        # The calibration set is the front of the band by accession, which is a deterministic
        # nested subset: the same assemblies every run, and already inside what the full pass
        # would search, so none of this is work the pass repeats.
        targets: list[Member] = band[args.offset : args.offset + args.assemblies]
        m.parameter("calibration_accessions", [t.accession for t in targets])

        dna = Alphabet.dna()
        measurements: list[dict[str, Any]] = []
        for target in targets:
            path = scratch / f"{target.accession}.fasta"
            fetch_started = time.time()
            provenance = fetch_member(target, read_range, path)
            fetch_seconds = time.time() - fetch_started
            try:
                with SequenceFile(str(path), digital=True, alphabet=dna) as handle:
                    sequences = handle.read_block()
                residues = sum(len(s) for s in sequences)
                for count in sorted(args.models):
                    with HMMFile(args.library) as handle:
                        models = list(islice(handle, count))
                    model_residues = sum(h.M for h in models)
                    seconds, hits = search(models, sequences, cpus=args.cpus)
                    core_seconds = seconds * args.cpus
                    unit = core_seconds / (len(models) * residues / 1e6)
                    measurements.append(
                        {
                            "accession": target.accession,
                            "contigs": len(sequences),
                            "residues": residues,
                            "compressed_bytes": provenance["compressed_bytes"],
                            "uncompressed_bytes": provenance["uncompressed_bytes"],
                            "fetch_seconds": round(fetch_seconds, 1),
                            "models": len(models),
                            "model_residues": model_residues,
                            "wall_seconds": round(seconds, 1),
                            "core_seconds": round(core_seconds, 1),
                            "core_seconds_per_model_mb": round(unit, 6),
                            # The unit that actually holds. D-186: cost does not scale with
                            # model *count* — wall time was identical at 4 and 8 models — so a
                            # per-model rate is only meaningful at a fixed model-length mix, and
                            # the mix here is not the registry's. Model residues is the unit any
                            # projection must use.
                            "core_seconds_per_model_residue_mb": round(
                                core_seconds / (model_residues * residues / 1e6), 9
                            ),
                            "reported_hits": hits,
                        }
                    )
                    print(json.dumps(measurements[-1]), flush=True)
            finally:
                # D-103: sequence lives in ephemeral scratch for as long as a search takes.
                path.unlink(missing_ok=True)

        units = [row["core_seconds_per_model_mb"] for row in measurements]
        summary: dict[str, Any] = {
            "task": "A2.3",
            "instrument": "pyhmmer.nhmmer against Dfam 4.0 curated LTR profiles",
            "decision_ref": "D-183",
            "cpus": args.cpus,
            "measurements": measurements,
            "core_seconds_per_model_mb": {
                "min": min(units),
                "median": statistics.median(units),
                "max": max(units),
                # Linear would mean the unit rate is the same at every model count. The spread is
                # reported rather than averaged away, because a rate that moves with the model
                # count is the thing a single-point extrapolation gets wrong (D-117, D-179).
                "spread_ratio": round(max(units) / min(units), 3) if min(units) else None,
                "linear_within_10_percent": bool(min(units) and max(units) / min(units) <= 1.1),
            },
        }

        registry = out / "registries" / "dfam-curated-ltr.json"
        if registry.exists():
            universe = json.loads(registry.read_text())
            families = [f for f in universe["families"] if f["threshold"] is not None]
            searchable_residues = sum(f["model_length"] for f in families)
            erv_residues = sum(f["model_length"] for f in families if f["is_erv"])
            band_bytes = sum(member.size for member in band)
            ratio = statistics.median(
                row["uncompressed_bytes"] / row["compressed_bytes"] for row in measurements
            )
            band_mb = band_bytes * ratio / 1e6
            # Projected from the measurement with the **most model residues**, not from the
            # median of the per-model rates. Two reasons, both D-186's: the per-model rate is
            # the unit the measurement discredited, and the deepest point's model-length mix is
            # the closest available to a full-registry pass. Using the median of a quantity that
            # moves with the model count is how a projection ends up disagreeing with the entry
            # that cites it.
            deepest = max(measurements, key=lambda row: row["model_residues"])
            rate = deepest["core_seconds_per_model_residue_mb"]
            summary["projection"] = {
                "band_assemblies": len(band),
                "band_compressed_bytes": band_bytes,
                "measured_compression_ratio": round(ratio, 3),
                "band_megabases_estimated": round(band_mb, 1),
                "unit": "core seconds per model-residue-megabase",
                "rate": rate,
                "rate_from": {
                    "models": deepest["models"],
                    "model_residues": deepest["model_residues"],
                    "why": "the deepest point measured; the per-model rate is not a usable unit",
                },
                "registry_model_residues": {
                    "all_searchable": searchable_residues,
                    "erv_only": erv_residues,
                },
                "core_hours_all_searchable": round(searchable_residues * band_mb * rate / 3600),
                "core_hours_erv_only": round(erv_residues * band_mb * rate / 3600),
                "caveat": (
                    "The band's sequence volume is estimated from the compression ratio of the "
                    "assemblies measured here, not from reading the band. It is a projection and "
                    "the depth decision cites it as one."
                ),
            }

        path = out / "calibration.json"
        path.write_text(json.dumps(summary, indent=1) + "\n")
        m.output_file(path, role="cost calibration")
        print(json.dumps({k: v for k, v in summary.items() if k != "measurements"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Acquire the pinned Dfam release and export A2.3's retroelement registry — D-183.

Runs once. It verifies the three pinned files against the digests the publisher serves beside
them, exports the curated LTR-class profiles with the publisher's own reader, applies the
selection rule in `amazebio.dfam`, and writes two things:

- **the registry artefact** (`artifacts/a2-3/registries/dfam-curated-ltr.json`) — the family
  universe, the per-model thresholds, the declared exclusions by accession, the subtype
  composition and the denominator restriction D-173 requires. This is what every figure traces
  to, and it carries no profile data.
- **the profile library** (under `data/`, git-ignored) — the selected models, for the detection
  pass to search. Large and regenerable, so it is an input rather than a result.

The split matters: the detection pass reads the artefact for its universe and the library for its
profiles, and never touches the HDF5 database or the reader again.

    python3 tools/stage_dfam.py --verify            # re-check the pins, download nothing
    python3 tools/stage_dfam.py                     # acquire, export, write both outputs
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import objectstore  # noqa: E402
from amazebio.dfam import (  # noqa: E402
    ERV_SUBTYPES,
    FILES,
    LTR_TYPE,
    RELEASE,
    DfamError,
    iter_models,
    universe,
)
from amazebio.repro import run  # noqa: E402

#: NCBI taxon id for Bilateria, the clade whose partition carries the ERV families. Passed to the
#: reader with `-d` so the export is that partition's descendants; the root partition's families
#: come with it because the reader always loads root.
BILATERIA = 33213


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire(destination: Path, *, verify_only: bool = False) -> list[dict[str, Any]]:
    """Download and verify each pinned file, skipping what is already correct.

    Verification gates the decompression, on D-031's principle for the corpus: a file that does
    not match its published digest is not unpacked and not used, because a registry assembled
    from unverified bytes cannot pin a result.
    """
    destination.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for pinned in FILES:
        gz = destination / pinned.name
        h5 = destination / pinned.name.removesuffix(".gz")
        row: dict[str, Any] = {
            "name": pinned.name,
            "partition": pinned.partition,
            "role": pinned.role,
            "md5_expected": pinned.md5,
            "gz_bytes_expected": pinned.gz_bytes,
        }
        if h5.exists() and not gz.exists():
            # Already unpacked by an earlier run, which verified it before unpacking.
            row |= {"state": "present", "verified": None, "h5_bytes": h5.stat().st_size}
            rows.append(row)
            continue
        if not gz.exists():
            if verify_only:
                row |= {"state": "absent", "verified": None}
                rows.append(row)
                continue
            print(f"  fetching {pinned.name} ({pinned.gz_bytes / 1e9:.2f} GB)", file=sys.stderr)
            with urllib.request.urlopen(pinned.url, timeout=300) as response, open(gz, "wb") as out:
                shutil.copyfileobj(response, out, 1 << 22)
        actual = md5_file(gz)
        row |= {
            "state": "fetched",
            "md5_actual": actual,
            "gz_bytes_actual": gz.stat().st_size,
            "verified": actual == pinned.md5,
        }
        if not row["verified"]:
            raise DfamError(
                f"{pinned.name}: md5 {actual} does not match the published {pinned.md5}. The "
                "file is not unpacked — a registry built from unverified bytes cannot pin a "
                "result."
            )
        if not verify_only:
            with gzip.open(gz, "rb") as src, open(h5, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 22)
            gz.unlink()
            row["h5_bytes"] = h5.stat().st_size
        rows.append(row)
    return rows


def export_profiles(db_dir: Path, out: Path, *, taxon: int = BILATERIA) -> None:
    """Export the curated LTR-class profiles with the publisher's reader.

    `--include-class-in-name` is what makes the selection rule auditable: the classification
    travels in the model name, so `amazebio.dfam.classify` reads the class the publisher assigned
    rather than this project inferring one.
    """
    command = [
        "pixi",
        "run",
        "-e",
        "dfam",
        "famdb.py",
        "-i",
        str(db_dir),
        "families",
        "-f",
        "hmm",
        "-d",
        "--curated",
        "--class",
        LTR_TYPE,
        "--include-class-in-name",
        str(taxon),
    ]
    with open(out, "wb") as handle:
        completed = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, cwd=REPO)
    if completed.returncode != 0:
        raise DfamError(
            f"the reader failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', 'replace')[-800:]}"
        )


def select(source: Path, library: Path, keep: set[str]) -> dict[str, int]:
    """Copy the selected models out of the export, streaming.

    Model blocks are copied verbatim rather than rewritten: a profile this project re-serialised
    is a profile whose search results are this project's responsibility rather than the
    publisher's, and the threshold lives inside the block.
    """
    written = 0
    skipped = 0
    with open(source) as src, open(library, "w") as out:
        block: list[str] = []
        accession: str | None = None
        for line in src:
            if line.startswith("HMMER3"):
                block = [line]
                accession = None
                continue
            if not block:
                continue  # the export's licence preamble
            block.append(line)
            if line.startswith("ACC "):
                accession = line[4:].strip()
            elif line.startswith("//"):
                if accession in keep:
                    out.writelines(block)
                    written += 1
                else:
                    skipped += 1
                block = []
    return {"models_written": written, "models_skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(REPO / "data" / "dfam" / RELEASE))
    parser.add_argument("--outdir", default=str(REPO / "artifacts" / "a2-3" / "registries"))
    parser.add_argument("--verify", action="store_true", help="re-check the pins, download nothing")
    parser.add_argument("--export", default=None, help="reuse an existing export instead")
    parser.add_argument(
        "--allow-count-drift",
        action="store_true",
        help="do not fail when the universe differs from the counts D-183 measured",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    data = Path(args.data)
    out = Path(args.outdir)

    with run(
        "A2.3",
        seed=None,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        durable=objectstore.durable_results("a2-3"),
        manifest_name="run-registry.json",
    ) as m:
        m.parameter("registry", "dfam-curated-ltr")
        m.parameter("dfam_release", RELEASE)
        m.parameter("taxon", BILATERIA)
        m.parameter("class", LTR_TYPE)
        m.parameter("erv_subtypes", sorted(ERV_SUBTYPES))
        m.parameter("decision_refs", ["D-183", "D-173", "D-076"])

        acquired = acquire(data, verify_only=args.verify)
        m.parameter("files", acquired)
        for pinned, row in zip(FILES, acquired, strict=True):
            m.input_url(
                pinned.url,
                role=pinned.role,
                bytes=pinned.gz_bytes,
                checksum=pinned.md5,
                checksum_type="md5",
                verified=bool(row.get("verified")),
            )
        if args.verify:
            print(json.dumps(acquired, indent=1))
            return 0

        export = Path(args.export) if args.export else data / "curated-ltr-export.hmm"
        if not export.exists():
            print(f"  exporting profiles to {export}", file=sys.stderr)
            started = time.time()
            export_profiles(data, export)
            m.parameter("export_seconds", round(time.time() - started, 1))
        m.parameter("export_bytes", export.stat().st_size)

        with open(export) as handle:
            models = list(iter_models(handle))
        summary = universe(models, strict=not args.allow_count_drift)

        keep = {
            model.accession
            for model in models
            if model.type == LTR_TYPE and model.threshold is not None
        }
        library = data / "dfam-curated-ltr.hmm"
        counts = select(export, library, keep)
        if counts["models_written"] != summary["searchable"]:
            raise DfamError(
                f"wrote {counts['models_written']} models for a universe of "
                f"{summary['searchable']}; the library and the registry would disagree about "
                "what was searched"
            )
        summary |= counts
        summary["library"] = str(library)
        summary["library_bytes"] = library.stat().st_size
        summary["thresholds"] = {
            model.accession: model.threshold for model in models if model.accession in keep
        }
        summary["families"] = [model.to_dict() for model in models if model.type == LTR_TYPE]

        out.mkdir(parents=True, exist_ok=True)
        path = out / "dfam-curated-ltr.json"
        path.write_text(json.dumps(summary, indent=1) + "\n")
        m.output_file(path, role="registry universe and thresholds")
        m.note(
            f"{summary['erv_models']} ERV-subtype models of {summary['ltr_models']} LTR-class; "
            f"{summary['excluded_no_threshold']} excluded for no curated threshold"
        )

        headline = {
            k: summary[k]
            for k in ("ltr_models", "searchable", "erv_models", "excluded_no_threshold")
        }
        print(json.dumps({**headline, "composition": summary["composition"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

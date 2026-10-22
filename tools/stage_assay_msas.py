"""Stage the alignments and structures B4.1's baseline needs, taking only what it needs.

§B4's baseline is an MSA + structure method, so it needs the alignment ProteinGym built for each
assay target and the predicted structure beside it. Both ship as single archives covering all
217 assays; this project analyses 31, whose alignments are 28 files because several assays share
a protein.

The alignment archive is 1.5 GB and the 28 members are 114 MB compressed. A zip's directory sits
at its end, so :class:`amazebio.webrange.WebRandomRead` lets :mod:`zipfile` open it over the
network and pull those members alone — the session's writable disk is a fixed allowance and
spending 1.4 GB of it on files nothing reads is how a later stage runs out. Members are written
back out gzipped for the same reason: 741 MB of alignment text uncompressed would not fit beside
the model weights, and the baseline streams them line by line anyway.

The structure archive is 19 MB, so it is simply downloaded.

Every staged file's digest is recorded in a manifest beside it, and re-running checks what is
already there rather than re-fetching it. The archives' own digests come from
`assays/licences.json`, which is the deposit this project's licence position rests on (D-228).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio.webrange import WebRandomRead  # noqa: E402

AGENT = "amazebio/0.1 (independent audit of training-data filtering)"
ZENODO = "https://zenodo.org/api/records/15293562/files/{name}/content"

MSA_ARCHIVE = "DMS_msa_files.zip"
STRUCTURE_ARCHIVE = "ProteinGym_AF2_structures.zip"

DATA = REPO / "data" / "proteingym" / "v1.3"
REFERENCE = DATA / "DMS_substitutions.csv"
MSA_DIR = DATA / "msa"
STRUCTURE_DIR = DATA / "structures"
MANIFEST = DATA / "baseline-inputs.json"

REGISTER = REPO / "assays" / "register.json"


def wanted(register: dict[str, Any], reference: Path) -> dict[str, str]:
    """Each in-scope assay's alignment filename, as the benchmark's own reference states it."""
    with reference.open(newline="") as handle:
        rows = {row["DMS_id"]: row for row in csv.DictReader(handle)}
    out = {}
    for assay in register["assays"]:
        row = rows.get(assay["dms_id"])
        if row is None:
            raise KeyError(f"{assay['dms_id']} is in the register but not in {reference.name}")
        out[assay["dms_id"]] = row["MSA_filename"]
    return out


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def stage_alignments(names: set[str], out: Path, *, force: bool = False) -> list[dict[str, Any]]:
    """Pull the named members out of the remote archive and write each one gzipped."""
    out.mkdir(parents=True, exist_ok=True)
    archive = zipfile.ZipFile(WebRandomRead(ZENODO.format(name=MSA_ARCHIVE), agent=AGENT))
    members = {info.filename.split("/")[-1]: info for info in archive.infolist()}
    missing = sorted(n for n in names if n not in members)
    if missing:
        raise KeyError(f"{MSA_ARCHIVE} has no member for: {', '.join(missing)}")

    staged = []
    for name in sorted(names):
        info = members[name]
        target = out / f"{name}.gz"
        if target.exists() and not force:
            print(f"  have {name}")
        else:
            print(f"  fetching {name} ({info.compress_size / 1e6:.1f} MB compressed)")
            # Written through a temporary name so an interrupted fetch cannot leave a short
            # file that the `target.exists()` check above would then accept as staged.
            partial = target.with_suffix(".gz.partial")
            with archive.open(info) as source, gzip.open(partial, "wb") as sink:
                shutil.copyfileobj(source, sink, length=1 << 20)
            partial.replace(target)
        staged.append(
            {
                "name": name,
                "path": str(target.relative_to(REPO)),
                "sha256": sha256_file(target),
                "uncompressed_bytes": info.file_size,
            }
        )
    return staged


def stage_structures(out: Path, *, force: bool = False) -> dict[str, Any]:
    """The structure archive is small enough to take whole."""
    out.mkdir(parents=True, exist_ok=True)
    local = out / STRUCTURE_ARCHIVE
    if not local.exists() or force:
        print(f"  fetching {STRUCTURE_ARCHIVE}")
        request = urllib.request.Request(
            ZENODO.format(name=STRUCTURE_ARCHIVE), headers={"User-Agent": AGENT}
        )
        partial = local.with_suffix(".zip.partial")
        with urllib.request.urlopen(request, timeout=600) as response, partial.open("wb") as sink:
            shutil.copyfileobj(response, sink, length=1 << 20)
        partial.replace(local)
    with zipfile.ZipFile(local) as archive:
        entries = len([i for i in archive.infolist() if not i.is_dir()])
    return {
        "archive": str(local.relative_to(REPO)),
        "sha256": sha256_file(local),
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-fetch what is already staged")
    parser.add_argument("--skip-structures", action="store_true")
    args = parser.parse_args(argv)

    register = json.loads(REGISTER.read_text())
    by_assay = wanted(register, REFERENCE)
    print(f"{len(by_assay)} assays, {len(set(by_assay.values()))} distinct alignments")

    staged = stage_alignments(set(by_assay.values()), MSA_DIR, force=args.force)
    structures = None if args.skip_structures else stage_structures(STRUCTURE_DIR, force=args.force)

    MANIFEST.write_text(
        json.dumps(
            {
                "source": "ProteinGym v1.3, Zenodo 10.5281/zenodo.15293562",
                "why_a_subset": (
                    "the alignment archive covers 217 assays and this project analyses the 31 "
                    "in assays/register.json. Members are pulled by range request and stored "
                    "gzipped; see tools/stage_assay_msas.py"
                ),
                "alignment_for_assay": dict(sorted(by_assay.items())),
                "alignments": staged,
                "structures": structures,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    total = sum(f["uncompressed_bytes"] for f in staged)
    print(f"wrote {MANIFEST}: {len(staged)} alignments, {total / 1e6:.0f} MB uncompressed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

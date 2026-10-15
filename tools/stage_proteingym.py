#!/usr/bin/env python3
"""Acquire and pin the benchmark DMS release — task B2.1.

    python3 tools/stage_proteingym.py              # download what is missing, then pin
    python3 tools/stage_proteingym.py --verify     # re-checksum what is staged, download nothing

`DESIGN.md` §B2 pins the benchmark at ProteinGym v1.3. This downloads that release's archives
and the reference file, records the SHA-256 of each, and writes
`artifacts/b2-1/release/release.json` with a `run.json` beside it.

Two things worth knowing before re-running it.

**The publisher ships no checksums**, unlike UniRef in A1.3, where a published md5 made the
pin the publisher's. Here the pin is ours: these hashes say the bytes have not changed since
*this* acquisition, not that they are the bytes the maintainers released. A silent re-cut of
v1.3 would be invisible to anyone who had not recorded a hash of their own, which is the
argument for recording one rather than a reason not to.

**Resume is deliberately not used.** An interrupted transfer is deleted and re-fetched whole.
A `curl -C -` resume onto a file another process is still writing produced an archive whose
central directory parsed while every member header was at the wrong offset — valid-looking and
unreadable. Re-fetching 1.9 GB is cheaper than trusting a file that lies about itself.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio.proteingym import RELEASE, load_reference, sha256_file, verify_release
from amazebio.repro import run

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "proteingym" / RELEASE.version
OUTDIR = REPO / "artifacts" / "b2-1" / "release"

# The reference file and the published per-assay leaderboard live in the maintainers' git
# repository rather than in the versioned data release, and that repository carries no tag for
# v1.3 — so these two are pinned by content hash and retrieval date, not by a version in their
# URL. That asymmetry is a finding, not a convenience: the per-assay numbers this project
# reproduces are a moving target upstream.
GITHUB_RAW = "https://raw.githubusercontent.com/OATML-Markslab/ProteinGym/main"
REPO_FILES = {
    "DMS_substitutions.csv": f"{GITHUB_RAW}/reference_files/DMS_substitutions.csv",
    "DMS_substitutions_Spearman_DMS_level.csv": (
        f"{GITHUB_RAW}/benchmarks/DMS_zero_shot/substitutions/Spearman/"
        "DMS_substitutions_Spearman_DMS_level.csv"
    ),
    "Summary_performance_DMS_substitutions_Spearman.csv": (
        f"{GITHUB_RAW}/benchmarks/DMS_zero_shot/substitutions/Spearman/"
        "Summary_performance_DMS_substitutions_Spearman.csv"
    ),
}

# What the maintainers' documentation says each archive weighs, for a stated-versus-actual
# record. Both are wrong, one by more than an order of magnitude, which is harmless in itself
# and exactly the kind of thing that should be logged rather than smoothed over.
STATED_SIZES = {
    "DMS_ProteinGym_substitutions.zip": "1.0GB",
    "zero_shot_substitutions_scores.zip": "4.4GB",
}


def fetch(url: str, dest: pathlib.Path) -> None:
    """Download `url` to `dest` whole, via a temporary file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    tmp.unlink(missing_ok=True)
    print(f"  fetching {dest.name} ...", flush=True)
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "--fail",
            "--retry",
            "5",
            "--retry-delay",
            "3",
            "--retry-all-errors",
            "-o",
            str(tmp),
            url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"download failed for {url}: {result.stderr.strip()[:300]}")
    shutil.move(tmp, dest)


def staged_entry(path: pathlib.Path, url: str) -> dict[str, Any]:
    return {
        "file": path.name,
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "stated_size": STATED_SIZES.get(path.name),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="re-checksum staged files only")
    ap.add_argument(
        "--allow-dirty", action="store_true", help="local iteration only; never for a citation"
    )
    args = ap.parse_args()

    wanted = {name: RELEASE.url(name) for name in RELEASE.files} | REPO_FILES

    if not args.verify:
        for name, url in wanted.items():
            path = DATA / name
            if path.exists():
                print(f"  have {name} ({path.stat().st_size:,} bytes)")
            else:
                fetch(url, path)

    missing = [n for n in wanted if not (DATA / n).exists()]
    if missing:
        raise SystemExit(f"not staged: {', '.join(missing)} — run without --verify")

    # Compare against the hashes pinned in amazebio.proteingym, which is the point of having
    # them. Until this call existed the tool recorded fresh hashes and never checked them, so
    # an upstream re-cut or a corrupted stage would have passed silently while the READMEs
    # claimed a check was happening. `unpinned` is a warning rather than a failure: it is the
    # expected state when staging a version whose hashes are not in the code yet.
    verdicts = verify_release(DATA)
    bad = {n: v for n, v in verdicts.items() if v not in ("ok", "unpinned")}
    unpinned = sorted(n for n, v in verdicts.items() if v == "unpinned")
    for name, verdict in sorted(verdicts.items()):
        print(f"  {verdict:8} {name}")
    if bad:
        raise SystemExit(
            "staged files do not match the pinned checksums: "
            + ", ".join(f"{n} ({v})" for n, v in sorted(bad.items()))
            + ". Either the publisher re-cut the release or the download is damaged; "
            "do not use this stage for a result until it is resolved."
        )
    if unpinned:
        print(f"  WARNING: no pinned checksum for {', '.join(unpinned)} — record one")

    with run("B2.1", outdir=OUTDIR, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("version", RELEASE.version)
        m.parameter("base_url", RELEASE.base_url)
        m.parameter("github_raw", GITHUB_RAW)
        m.parameter("checksum_verdicts", verdicts)
        m.note(
            "The publisher ships no checksums for these archives, so the recorded hashes are "
            "this acquisition's own: they show the bytes have not changed since staging, not "
            "that they are the bytes released. The reference file and the per-assay "
            "leaderboard come from the maintainers' git repository, which carries no v1.3 "
            "tag, so those two are pinned by hash and retrieval date only."
        )

        entries = []
        for name, url in wanted.items():
            path = DATA / name
            entry = staged_entry(path, url)
            entries.append(entry)
            m.input_url(
                url,
                role=f"pinned benchmark input: {name}",
                bytes=entry["bytes"],
                checksum=entry["sha256"],
                checksum_type="sha256",
                # Our hash of our download, not a publisher checksum we matched.
                verified=False,
            )
            print(f"  {name:52} {entry['bytes']:>13,}  {entry['sha256'][:16]}")

        assays = load_reference(DATA / RELEASE.reference_file)
        counts: dict[str, int] = {}
        for a in assays:
            counts[a.taxon.value] = counts.get(a.taxon.value, 0) + 1

        path = OUTDIR / "release.json"
        path.write_text(
            json.dumps(
                {
                    "task": "B2.1",
                    "design_ref": "§B2",
                    "version": RELEASE.version,
                    "staged_dir": str(DATA.relative_to(REPO)),
                    "files": entries,
                    "assays": len(assays),
                    "variants": sum(a.n_variants for a in assays),
                    "assays_by_taxon": counts,
                    "publisher_checksums_available": False,
                    "checksum_verdicts": verdicts,
                },
                indent=1,
            )
            + "\n"
        )
        m.output_file(path, role="pinned benchmark release record")

    print(f"\n{len(assays)} assays, {sum(a.n_variants for a in assays):,} variants")
    print(f"by taxon: {counts}")
    print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage the pinned profile registries A2.1 searches with — Pfam viral families and RVDB-prot.

    python3 tools/stage_profiles.py                 # download what is missing, verify, pin
    python3 tools/stage_profiles.py --verify        # re-checksum what is staged, download nothing
    python3 tools/stage_profiles.py --registry pfam # one registry only

The pins live in `amazebio.profiles`. This downloads each file, checks it against the digest its
*publisher* states, counts the profiles the staged file actually contains, and writes
`artifacts/a2-1/registries/registries.json` with a `run.json` beside it.

Two things this does that a plain download does not.

**It records stated-versus-counted.** RVDB-prot's metadata states 13,679 profiles; the staged
file is parsed and its profiles counted independently. `AGENTS.md` asks for exactly that gap to
be visible — a registry with fewer profiles than its publisher claims changes the denominator of
every survival figure drawn from it, and a denominator nobody checked is not pinned.

**It derives and ships the Pfam viral family universe.** The selection is this project's reading
of a phrase `DESIGN.md` §A2 leaves open (D-075), so the selected families are written out per
family — accession, name, description, clan, gathering cutoff — for a reviewer to argue with.
The artefact is the denominator of the Pfam-registry headline, and `metrics/survival.md` requires
it to be zero-filled across the pinned universe rather than built from whatever was detected.

Resume is deliberately not used, for the reason `tools/stage_proteingym.py` records: an
interrupted transfer is deleted and re-fetched whole rather than patched, because a resumed
download that lies about itself is worse than a slow one.
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

from amazebio.profiles import (
    MIN_MODEL_COVERAGE,
    PINNED_DOM_Z,
    PINNED_E_VALUE,
    PINNED_Z,
    REGISTRIES,
    ProfileError,
    Registry,
    clan_name_additions,
    md5_of,
    open_profiles,
    registry,
    rvdb_labels,
    select_viral_families,
)
from amazebio.repro import run

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "profiles"
OUTDIR = REPO / "artifacts" / "a2-1" / "registries"

#: Seed is recorded for provenance only: staging is a download and two parses, with no RNG in it.
SEED = 20261015


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
            "--max-time",
            "3600",
            "-o",
            str(tmp),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"download failed for {url}: {result.stderr.strip()[:300]}")
    shutil.move(tmp, dest)


def count_profiles(path: pathlib.Path) -> tuple[int, str | None]:
    """Profiles in a staged HMM file, and the HMMER format version its header declares.

    Counted by reading the `HMMER3/f` record headers rather than by loading the models, because
    the question is how many profiles the file holds and loading 13,679 of them to answer it
    would cost gigabytes of memory for a number already on the first line of each record.
    """
    count = 0
    fmt: str | None = None
    with open_profiles(path) as handle:
        for raw in handle:
            if raw.startswith(b"HMMER3"):
                count += 1
                if fmt is None:
                    fmt = raw.decode("ascii", "replace").strip().split()[0]
    return count, fmt


def stage(reg: Registry, *, verify_only: bool) -> dict[str, Any]:
    """Stage one registry and return its entry for `registries.json`."""
    target = reg.staged_dir(DATA)
    print(f"{reg.key} -> {target.relative_to(REPO)}", flush=True)
    files: list[dict[str, Any]] = []
    for spec in reg.files:
        dest = target / spec.local_name
        if not dest.exists():
            if verify_only:
                files.append({"file": spec.name, "staged": False, "why": "absent"})
                print(f"  {spec.name}: absent", flush=True)
                continue
            fetch(spec.url, dest)
        size = dest.stat().st_size
        digest = md5_of(dest)
        # A publisher-stated digest is checked; the one file that states none for itself
        # (RVDB's metadata) is recorded with our digest and explicitly marked unpinned, so a
        # reader is never left guessing whose checksum they are looking at.
        if spec.md5:
            matches = digest == spec.md5
            if not matches:
                raise ProfileError(
                    f"{reg.key}/{spec.name}: md5 {digest} does not match the publisher's "
                    f"{spec.md5} ({spec.md5_source}). The staged copy is not the release this "
                    "project pins — delete it and re-stage rather than searching it."
                )
            if spec.size and size != spec.size:
                raise ProfileError(
                    f"{reg.key}/{spec.name}: {size} bytes, publisher states {spec.size}"
                )
        else:
            matches = None
        print(f"  {spec.name}: {size:,} bytes, md5 {digest} ({'pinned' if spec.md5 else 'ours'})")
        files.append(
            {
                "file": spec.name,
                "staged": True,
                "url": spec.url,
                "bytes": size,
                "md5": digest,
                "published_md5": spec.md5 or None,
                "md5_source": spec.md5_source,
                "matches_published": matches,
            }
        )

    entry: dict[str, Any] = {
        "id": reg.id,
        "version": reg.version,
        "key": reg.key,
        "publisher": reg.publisher,
        "release_date": reg.release_date,
        "source": reg.source,
        "membership": reg.membership,
        "curated_cutoffs": reg.curated_cutoffs,
        "profile_count_stated": reg.profile_count,
        "files": files,
        "notes": list(reg.notes),
    }

    hmm = next((f for f in reg.files if f.name.endswith((".hmm.gz", ".hmm.xz", ".hmm"))), None)
    if hmm is not None and (target / hmm.local_name).exists():
        counted, fmt = count_profiles(target / hmm.local_name)
        entry["profile_count_counted"] = counted
        entry["hmm_format"] = fmt
        entry["profile_count_agrees"] = (
            None if reg.profile_count is None else counted == reg.profile_count
        )
        print(f"  profiles counted: {counted:,} (stated {reg.profile_count or 'none'})")
    return entry


def pfam_universe(reg: Registry) -> dict[str, Any]:
    """Derive the Pfam viral family universe and the clan-level reading it replaces (D-075)."""
    dat = reg.staged_dir(DATA) / "Pfam-A.hmm.dat.gz"
    clans = reg.staged_dir(DATA) / "Pfam-A.clans.tsv.gz"
    selected = select_viral_families(dat)
    additions = clan_name_additions(dat, clans)
    # The clan-level count is reported, not used: it is the measured consequence of the other
    # reading of §A2's phrase, and §A0's whole point is that under-specification is a result.
    from amazebio.profiles import iter_family_meta

    all_meta = list(iter_family_meta(dat))
    by_clan: dict[str, list[str]] = {}
    for meta in all_meta:
        if meta.clan:
            by_clan.setdefault(meta.clan, []).append(meta.accession)
    viral_clans = {m.clan for m in selected.values() if m.clan}
    clan_level = sorted({a for c in viral_clans for a in by_clan[c]})
    return {
        "registry": reg.key,
        "families_in_release": len(all_meta),
        "families_selected": len(selected),
        "selection": "family-level: the family's own ID or description names a viral entity",
        "clan_level_alternative": {
            "clans": len(viral_clans),
            "clans_in_release": len(by_clan),
            "families": len(clan_level),
            "families_not_themselves_viral": len([a for a in clan_level if a not in selected]),
            "selected_families_with_no_clan": len([a for a, m in selected.items() if not m.clan]),
            "why_not_used": (
                "a clan is a structural superfamily, so this reading is both over-broad (it "
                "adds thousands of cellular families) and incomplete (it drops every viral "
                "family that belongs to no clan). See DECISIONS.md D-075."
            ),
        },
        "clan_name_alternative": {
            "families": len(additions),
            "by_clan": sorted({clan for _, clan in additions.values()}),
            "examples": [
                {"accession": a, "name": meta.name, "clan_name": clan}
                for a, (meta, clan) in sorted(additions.items())[:10]
            ],
            "why_not_used": (
                "the narrowest widening available — the clan's own name rather than its "
                "membership — and still contaminated: CL0511 is called Retroviral_zf and holds "
                "cellular zinc fingers, CL0504 is called Phage_barrel and holds Alg8_N. It is "
                "also what would admit the families named for a virus taxon, Ebola_NP among "
                "them, which the family-name rule misses. Reported rather than used: D-083."
            ),
        },
        "families": [
            {
                "accession": a,
                "name": m.name,
                "selected_by": m.selected_by,
                "description": m.description,
                "clan": m.clan,
                "entry_type": m.entry_type,
                "model_length": m.model_length,
                "gathering_sequence": m.gathering[0] if m.gathering else None,
                "gathering_domain": m.gathering[1] if m.gathering else None,
            }
            for a, m in sorted(selected.items())
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", action="append", help="registry id; repeatable")
    parser.add_argument(
        "--verify", action="store_true", help="re-checksum what is staged, download nothing"
    )
    parser.add_argument("--out", default=OUTDIR, type=pathlib.Path)
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args()

    chosen = [registry(i) for i in (args.registry or sorted(REGISTRIES))]

    with run("A2.1", seed=SEED, outdir=args.out, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("registries", [r.key for r in chosen])
        m.parameter("pinned_z", PINNED_Z)
        m.parameter("pinned_dom_z", PINNED_DOM_Z)
        m.parameter("pinned_e_value", PINNED_E_VALUE)
        m.parameter("min_model_coverage", MIN_MODEL_COVERAGE)
        m.parameter("verify_only", args.verify)
        m.tool("curl", ["curl", "--version"])

        entries = [stage(r, verify_only=args.verify) for r in chosen]
        for reg in chosen:
            for spec in reg.files:
                path = reg.staged_dir(DATA) / spec.local_name
                if path.exists():
                    m.input_file(path, role=f"{reg.key}:{spec.name}")

        out = args.out
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "task": "A2.1",
            "registries": entries,
            "thresholds": {
                "pfam": "the release's own per-model GA gathering cutoffs, as published",
                "rvdb-prot": f"sequence E <= {PINNED_E_VALUE} against Z={PINNED_Z}",
                "min_model_coverage": MIN_MODEL_COVERAGE,
                "why": (
                    "bit-score-equivalent thresholds: an E-value computed against the number of "
                    "sequences a run happened to read would move the headline with the sample "
                    "size. See DECISIONS.md D-076."
                ),
            },
        }
        (out / "registries.json").write_text(json.dumps(payload, indent=2) + "\n")
        m.output_file(out / "registries.json", role="registry pins")

        rvdb = next((r for r in chosen if r.id == "rvdb-prot"), None)
        annotations = rvdb.staged_dir(DATA) / "U-RVDBv32.0-prot-hmm.sqlite.xz" if rvdb else None
        if annotations is not None and annotations.exists():
            labels = rvdb_labels(annotations)
            payload_labels = {
                "registry": rvdb.key,
                "families": len(labels),
                "label_is_derived": (
                    "RVDB assigns its families no descriptive name: the annotation database "
                    "holds keyword frequencies and taxon ids, not titles. `label` is this "
                    "project's summary of the publisher's own keyword frequencies and is for "
                    "readers only — `family_id` is the identity every count is keyed on, and "
                    "the only thing a figure may cite as the family. See DECISIONS.md D-097."
                ),
                "label_rule": "the four most frequent sequence-name keywords, in frequency order",
                "entries": [
                    {
                        "family_id": label.family_id,
                        "label": label.label,
                        "keywords": list(label.keywords),
                        "reference_keywords": list(label.reference_keywords),
                        "lca_taxid": label.lca_taxid,
                        "sequences": label.sequences,
                        "model_length": label.model_length,
                    }
                    for label in sorted(labels.values(), key=lambda entry: entry.family_id)
                ],
            }
            (out / "rvdb-families.json").write_text(json.dumps(payload_labels, indent=2) + "\n")
            m.output_file(out / "rvdb-families.json", role="RVDB family labels")
            print(f"\nRVDB family labels: {len(labels):,} families")

        pfam = next((r for r in chosen if r.id == "pfam"), None)
        if pfam is not None and (pfam.staged_dir(DATA) / "Pfam-A.hmm.dat.gz").exists():
            universe = pfam_universe(pfam)
            (out / "pfam-viral-families.json").write_text(json.dumps(universe, indent=2) + "\n")
            m.output_file(out / "pfam-viral-families.json", role="Pfam viral family universe")
            print(
                f"\nPfam viral family universe: {universe['families_selected']:,} of "
                f"{universe['families_in_release']:,} families. The clan-level reading would "
                f"take {universe['clan_level_alternative']['families']:,}, "
                f"{universe['clan_level_alternative']['families_not_themselves_viral']:,} of "
                "them not viral; the clan-name reading would add "
                f"{universe['clan_name_alternative']['families']:,}, contaminated in the same "
                "way (D-083)."
            )
        m.note(
            "Registry membership is defined by two different authorities — RVDB's curators and "
            "this project's reading of Pfam — so the two are never pooled (metrics/survival.md)."
        )
    print(f"\nwrote {args.out.relative_to(REPO)}/registries.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

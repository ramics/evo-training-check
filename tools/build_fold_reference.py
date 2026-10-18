#!/usr/bin/env python3
"""Build A2.2's reference structure database from the pinned fold universe.

    pixi run -e dev python tools/build_fold_reference.py --out artifacts/a2-2/reference
    pixi run -e dev python tools/build_fold_reference.py --manifest-only

Three steps, in order: select ECOD's curated representatives for the families
`amazebio.folds` enumerates, fetch each one's PDB entry from RCSB, and cut it to ECOD's residue
range. `foldseek createdb` over the resulting directory is the fourth step and runs in the
`foldseek` environment, so this tool writes the directory and reports the command rather than
shelling into another pixi environment from inside this one.

**The cut is the point, not a detail.** D-166 rejected foldseek's prebuilt PDB and CATH50
databases as the reference because they are whole chains, and "a capsid fold inside a larger
protein is the case that matters". So each reference structure is one ECOD domain — a residue
range inside one chain — and the range is applied with a real mmCIF parser because ECOD's ranges
carry insertion codes (`A:1B-99A`), author numbering that need not start at 1, and multi-segment
domains (`A:1-99,A:150-200`). Every one of those silently mis-cuts under a hand-rolled
ATOM-record filter, and a mis-cut reference domain is a reference to the wrong fold.

**A representative that cannot be cut is dropped loudly.** RCSB can refuse an entry, an entry can
lack the chain ECOD names, and a range can select no residues; all three happen in a set this
size. Each is recorded by domain id with its reason, counted in the manifest, and reported — the
same treatment `metrics/detections.md` gives a component a detector could not read. A reference
set quietly 8 structures short would weaken every fold claim drawn from it without saying so.

No sequence and no coordinates reach the repository: the cut structures go to `--structures`,
which defaults outside the working tree, and the committed artefact is the manifest of what was
selected, fetched and cut.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import folds
from amazebio.repro import run

#: RCSB's unauthenticated download endpoint. Verified reachable from this container for mmCIF;
#: `.cif.gz` rather than `.pdb` because PDB format cannot represent the larger viral capsid
#: entries at all, and a reference set that silently skipped them would skip the biggest
#: assemblies in the capsid fold.
RCSB_CIF = "https://files.rcsb.org/download/{pdb}.cif.gz"

#: ECOD's range syntax, one segment. The insertion-code groups are matched and deliberately not
#: used to filter: ECOD's `pdb_range` numbering is author numbering, and selecting on the number
#: alone takes every insertion code at the boundary residue, which is the inclusive reading of
#: the range. Dropping them would cut residues the domain contains.
SEGMENT = re.compile(r"^(?P<chain>\S+):(?P<lo>-?\d+)[A-Za-z]?-(?P<hi>-?\d+)[A-Za-z]?$")

#: Polite fixed pause between RCSB requests. The set is 141 domains over ~120 distinct entries,
#: so the whole fetch is a couple of minutes either way and there is no reason to hammer a public
#: endpoint for it.
FETCH_PAUSE_S = 0.2

#: Retries per entry, with a linear backoff. RCSB is reliable; this exists so one transient 503
#: does not cost the whole build.
FETCH_ATTEMPTS = 4


class ReferenceError(RuntimeError):
    """Raised when the reference set cannot be built as specified."""


def fetch_entry(pdb: str, cache: Path) -> Path:
    """Download one PDB entry's gzipped mmCIF into `cache`, or reuse what is there.

    Cached by entry rather than by domain: several representatives can come from one entry, and
    the capsid fold in particular draws repeatedly on the same large assemblies.
    """
    dest = cache / f"{pdb}.cif.gz"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = RCSB_CIF.format(pdb=pdb)
    last: Exception | None = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            # Fixed https host built from a pinned template; `pdb` is an ECOD id.
            with urllib.request.urlopen(url, timeout=120) as resp:
                body = resp.read()
            if not body:
                raise ReferenceError(f"{pdb}: RCSB returned an empty body")
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
            return dest
        except (urllib.error.URLError, OSError, ReferenceError) as exc:
            last = exc
            if attempt < FETCH_ATTEMPTS:
                time.sleep(attempt * 2)
    raise ReferenceError(f"{pdb}: fetch failed after {FETCH_ATTEMPTS} attempts: {last}")


def cut_domain(entry: Path, dom: folds.ReferenceDomain, out_dir: Path) -> dict[str, Any]:
    """Cut one ECOD domain out of its entry and write it as mmCIF.

    Returns what was cut, so the manifest can carry the residue count a reviewer would otherwise
    have to re-derive. Raises :class:`ReferenceError` when the range selects nothing, which is
    the case that must not pass silently: foldseek would accept a 0-residue structure as a target
    and it would match nothing for the rest of the project.
    """
    import gemmi

    st = gemmi.read_structure(str(entry))
    st.setup_entities()
    st.remove_ligands_and_waters()
    st.remove_alternative_conformations()
    st.remove_hydrogens()
    if not len(st):
        raise ReferenceError(f"{dom.domain_id}: {entry.name} holds no model")
    model = st[0]

    # One chain per domain, not one per segment. A discontinuous ECOD domain — 10 of the 141
    # carry multi-segment ranges — is still *one* domain, and `foldseek createdb` makes a
    # separate database entry per chain: segments in their own chains became 152 targets from 141
    # domains, which breaks the thing the geometry rests on. D-167 puts the coverage floor on the
    # target so that half of the reference *fold* has to be matched, and a fold split into three
    # targets lets a third of it clear a floor meant for the whole. Author numbering is kept, so
    # the gap between segments reads as a numbering gap, exactly as a chain with unresolved loops
    # does. Verified safe for this universe: no selected domain spans more than one chain, and
    # `cross_chain` refuses one rather than silently colliding residue numbers.
    chains = {seg.split(":", 1)[0].strip() for seg in dom.pdb_range.split(",")}
    if len(chains) > 1:
        raise ReferenceError(
            f"{dom.domain_id}: range {dom.pdb_range!r} spans chains {sorted(chains)}; "
            "merging those into one chain would collide author residue numbers"
        )
    out_model = gemmi.Model("1")
    out_chain = gemmi.Chain(next(iter(chains)))
    kept = 0
    for raw in dom.pdb_range.split(","):
        seg = raw.strip()
        m = SEGMENT.match(seg)
        if m is None:
            raise ReferenceError(f"{dom.domain_id}: cannot parse ECOD range segment {seg!r}")
        name = m["chain"]
        # gemmi signals an unknown chain with ValueError, not KeyError. Re-raised as a
        # ReferenceError so the drop is reported with the domain it belongs to; ECOD names a
        # chain that the current PDB entry has since renamed often enough to matter.
        try:
            chain = model[name]
        except (ValueError, KeyError, IndexError) as exc:
            raise ReferenceError(f"{dom.domain_id}: {entry.name} has no chain {name!r}") from exc
        lo, hi = int(m["lo"]), int(m["hi"])
        if lo > hi:
            lo, hi = hi, lo
        for res in chain:
            if lo <= res.seqid.num <= hi:
                out_chain.add_residue(res)
                kept += 1

    if kept:
        out_model.add_chain(out_chain)
    if kept == 0:
        raise ReferenceError(
            f"{dom.domain_id}: range {dom.pdb_range!r} selected no residues in {entry.name}"
        )

    cut = gemmi.Structure()
    cut.name = dom.domain_id
    cut.spacegroup_hm = "P 1"
    cut.add_model(out_model)
    cut.setup_entities()
    path = out_dir / dom.filename
    cut.make_mmcif_document().write_file(str(path))
    return {"residues": kept, "bytes": path.stat().st_size}


def build(
    domains: list[folds.ReferenceDomain],
    *,
    cache: Path,
    structures: Path,
    progress: Any = None,
) -> dict[str, Any]:
    """Fetch and cut every selected representative; report what landed and what did not."""
    cache.mkdir(parents=True, exist_ok=True)
    structures.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    fetched_entries: set[str] = set()
    for i, dom in enumerate(domains, start=1):
        try:
            if dom.pdb not in fetched_entries:
                entry = fetch_entry(dom.pdb, cache)
                if not (cache / f"{dom.pdb}.cif.gz").exists():  # pragma: no cover — defensive
                    raise ReferenceError(f"{dom.pdb}: no cached entry after fetch")
                fetched_entries.add(dom.pdb)
                time.sleep(FETCH_PAUSE_S)
            else:
                entry = cache / f"{dom.pdb}.cif.gz"
            cut = cut_domain(entry, dom, structures)
        except (ReferenceError, RuntimeError, ValueError) as exc:
            dropped.append(
                {
                    "domain_id": dom.domain_id,
                    "fold_id": dom.fold_id,
                    "family_id": dom.family_id,
                    "pdb": dom.pdb,
                    "pdb_range": dom.pdb_range,
                    "why": str(exc),
                }
            )
        else:
            written.append(
                {
                    "domain_id": dom.domain_id,
                    "uid": dom.uid,
                    "fold_id": dom.fold_id,
                    "family_id": dom.family_id,
                    "family_name": dom.family_name,
                    "pdb": dom.pdb,
                    "chain": dom.chain,
                    "pdb_range": dom.pdb_range,
                    **cut,
                }
            )
        if progress is not None and (i % 10 == 0 or i == len(domains)):
            progress(i, len(domains), len(written), len(dropped))

    by_fold = collections.Counter(d["fold_id"] for d in written)
    dropped_by_fold = collections.Counter(d["fold_id"] for d in dropped)
    return {
        "structures": written,
        "dropped": dropped,
        "counts": {
            "selected": len(domains),
            "written": len(written),
            "dropped": len(dropped),
            "entries_fetched": len(fetched_entries),
            "by_fold": {f.fold_id: by_fold.get(f.fold_id, 0) for f in folds.FOLDS},
            "dropped_by_fold": {f.fold_id: dropped_by_fold.get(f.fold_id, 0) for f in folds.FOLDS},
        },
    }


def universe_manifest(domains: list[folds.ReferenceDomain]) -> dict[str, Any]:
    """The fold universe as an artefact: every fold's membership rule and what it selected.

    This is the list D-166 required to ship with the table and D-168 re-derived. It carries the
    excluded identifier lists too, because a reader checking the membership rule needs to see
    what was deliberately left out, not infer it from absence.
    """
    reps = collections.Counter(d.fold_id for d in domains)
    return {
        "registry": "ECOD",
        "registry_version": folds.ECOD_V295_2.version,
        "registry_generated": folds.ECOD_V295_2.generated,
        "registry_url": folds.ECOD_V295_2.url,
        "registry_sha256": folds.ECOD_V295_2.sha256,
        "classified_domains": folds.ECOD_V295_2.classified_domains,
        "selection_level": "ECOD F-group (family), by enumerated identifier",
        "decisions": ["D-166", "D-168"],
        "folds": [
            {
                "fold_id": f.fold_id,
                "name": f.name,
                "curation": f.curation,
                "note": f.note,
                "families": list(f.families),
                "family_count": len(f.families),
                "representatives_selected": reps.get(f.fold_id, 0),
            }
            for f in folds.FOLDS
        ],
        "excluded": {
            "cellular_capsid_families": list(folds.EXCLUDED_CELLULAR_CAPSID),
            "unnamed_capsid_families": list(folds.EXCLUDED_UNNAMED_CAPSID),
            "host_rnai_families": list(folds.EXCLUDED_HOST_RNAI),
        },
    }


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ecod", type=Path, default=Path("data/ecod/ecod.v295.2.domains.txt"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/a2-2/reference"))
    ap.add_argument(
        "--structures",
        type=Path,
        default=None,
        help="where the cut mmCIF files go; defaults outside the working tree (D-103)",
    )
    ap.add_argument("--cache", type=Path, default=None, help="downloaded RCSB entries")
    ap.add_argument(
        "--manifest-only",
        action="store_true",
        help="write the fold universe manifest and fetch nothing",
    )
    ap.add_argument("--no-verify", action="store_true", help="skip the ECOD digest check")
    ap.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scratch = Path("/tmp/amazebio-a2-2")  # outside the tree on purpose (D-103)
    structures = args.structures or scratch / "reference-structures"
    cache = args.cache or scratch / "rcsb-cache"

    if not args.ecod.exists():
        print(
            f"missing {args.ecod}\n"
            f"  fetch it with: curl -sSL {folds.ECOD_V295_2.url} -o {args.ecod}",
            file=sys.stderr,
        )
        return 2

    domains = folds.reference_domains(args.ecod, verify=not args.no_verify)
    manifest_body = universe_manifest(domains)
    for f in manifest_body["folds"]:
        print(
            f"  {f['fold_id']:20s} families={f['family_count']:3d} "
            f"representatives={f['representatives_selected']:3d}  ({f['curation']})"
        )
    print(f"  selected {len(domains)} reference domains")

    if args.manifest_only:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "fold-universe.json").write_text(json.dumps(manifest_body, indent=2) + "\n")
        print(f"wrote {args.out / 'fold-universe.json'}")
        return 0

    def progress(done: int, total: int, ok: int, bad: int) -> None:
        print(f"    {done}/{total} cut={ok} dropped={bad}", flush=True)

    with run(
        "A2.2",
        seed=20261015,
        outdir=args.out,
        allow_dirty=args.allow_dirty,
    ) as manifest:
        manifest.parameter("ecod_version", folds.ECOD_V295_2.version)
        manifest.parameter("ecod_sha256", folds.ECOD_V295_2.sha256)
        manifest.parameter("selection_level", manifest_body["selection_level"])
        manifest.parameter("representatives_selected", len(domains))
        manifest.input_file(args.ecod, role="ecod_domains")

        built = build(domains, cache=cache, structures=structures, progress=progress)
        body = {**manifest_body, **built}
        out = args.out / "fold-universe.json"
        out.write_text(json.dumps(body, indent=2) + "\n")
        manifest.output_file(out, role="fold_universe")

    c = built["counts"]
    print(
        f"cut {c['written']} of {c['selected']} reference structures "
        f"from {c['entries_fetched']} PDB entries into {structures}"
    )
    if built["dropped"]:
        print(f"dropped {c['dropped']}:")
        for d in built["dropped"]:
            print(f"    {d['domain_id']} ({d['fold_id']}): {d['why']}")
    print(
        "\nnext, in the foldseek environment:\n"
        f"  pixi run -e foldseek foldseek createdb {structures} "
        f"{structures.parent / 'refdb' / 'ref'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Detect endogenous retroelements in the surviving host-genome component — A2.3, D-186.

One table per manifest, in the shape `metrics/detections.md` fixes, so A3.2 can merge this
detector's output with A2.1's, A2.2's and A2.4's and still take the merge apart again.

The pass is per assembly, and that is the architecture rather than an implementation detail:

- **The record is the genome** (D-136), so one assembly is one unit of work, one row of
  provenance and one unit of resumption.
- **Nothing accumulates on disk.** Each assembly is fetched from the publisher by byte range,
  searched, and deleted before the next one — 20 GB of working disk could not hold the band, and
  D-103 puts corpus sequence in ephemeral scratch and nowhere else.
- **Each assembly is searched once, not once per reading.** The three readings differ only in
  the survival route they imply for this component (`out_of_scope` under literal and charitable,
  `retained_by_design` under strict), never in what is in it — D-016 withdrew the only rule that
  could have removed anything here. Searching per reading would triple the cost for an identical
  set of alignments, which is one of the six faults A2.4 found by watching its own runs.

Evo 1's manifests get a table too, and it reads `not_searched` **by construction**: that release
exposes no eukaryotic genomes at all (D-018, D-019, D-182). That is a different claim from
A2.2's `not_searched`, where the component existed and was not bought, and the per-source
reason strings are where the difference is recorded rather than left in the log.

    python3 tools/detect_eve.py --rate 0.0025
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import opengenome as og  # noqa: E402
from amazebio.apply import route_for  # noqa: E402
from amazebio.detect import (  # noqa: E402
    DetectionTable,
    ManifestRef,
    SampleDesign,
    build_rows,
    check_route_coverage,
    detection_rows,
)
from amazebio.eukaryotes import fetch_member, load_index, sampled_members  # noqa: E402
from amazebio.eve import (  # noqa: E402
    ACCEPT,
    DETECTOR,
    MMSEQS_FORMAT,
    accept,
    detections_for,
    parse_alignments,
    write_queries,
)
from amazebio.policyspec import Outcome  # noqa: E402
from amazebio.repro import run, sha256_file  # noqa: E402

SEED = 20261015
REGISTRY = "dfam-curated-ltr"

#: The component this detector covers. Every other component of every manifest is listed with
#: `searched: false` and a reason, because a table that silently covered part of a release reads
#: as a verdict on all of it (D-080).
COVERED = "ncbi_eukaryotic_genomes"

#: Why each other component is not this detector's. Named per component rather than defaulted,
#: so a component added later arrives without a reason instead of inheriting a wrong one.
NOT_SEARCHED = {
    "stage2": "Evo 1's viral component; A2.1 searches it with profiles",
    "stage1_gtdb": "prokaryotic genomes; A2.4's integrated-element detector covers them",
    "stage1_imgpr": "plasmid and phage sequence; not a host genome",
    "imgvr": "viral component; A2.1 searches it with profiles",
    "imgpr": "plasmid and phage sequence; not a host genome",
    "gtdb_v220": "prokaryotic genomes; A2.4's integrated-element detector covers them",
    "metagenomes": "unassigned metagenomic sequence; A4.1 sizes it, and it is not a host genome",
    "ncrna": "non-coding RNA sequence, not assembled host genomes",
    "promoters": "promoter windows, not assembled host genomes",
    "organelles": "organelle sequence; eukaryote-derived but not the nuclear genomes this arm "
    "searches, and D-182 scoped this task to ncbi_eukaryotic_genomes",
    "eukaryotic_genic_windows": "windows cut from the genomes this arm searches, so they add no "
    "independent sequence and are cut around genes; excluded by D-182",
    "mrna": "transcript sequence, not assembled host genomes",
}

#: The reason an entire release carries no searchable component. Distinguished from "in scope and
#: not searched" because collapsing the two would make an absent component look like an
#: unfinished pass.
ABSENT = (
    "this release exposes no eukaryotic genome component at all (D-018, D-019), so there is "
    "nothing for this detector to search and every count is zero by construction rather than "
    "by a limit of this pass"
)
PROTEIN_PROXY = (
    "a protein corpus with no assembled genomes; its reader is A1.6's and no host-genome "
    "component exists in it"
)

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


def mmseqs(*args: str, env: Path, threads: int) -> None:
    """One aligner call, with its output captured and surfaced on failure.

    A2.4's fourth fault was the search tool's output being swallowed so its hours were silent;
    this keeps stderr and prints it only when the call fails, which is the balance that leaves a
    long run readable without hiding the one message that matters.
    """
    command = ["pixi", "run", "-e", "dev", "mmseqs", *args, "--threads", str(threads)]
    completed = subprocess.run(command, cwd=REPO, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"mmseqs {args[0]} failed ({completed.returncode}):\n"
            f"{completed.stdout.decode('utf-8', 'replace')[-2000:]}\n"
            f"{completed.stderr.decode('utf-8', 'replace')[-2000:]}"
        )


def self_check(query_db: Path, queries: Path, work: Path, *, threads: int, expect: int) -> dict:
    """Search the query set against itself and require almost every family to find itself.

    **This is the control that stops a false null.** A genome with no accepted alignment is a
    real and expected result — many of the sampled assemblies are lineages this registry's
    families do not occur in — so "zero" cannot be distinguished from a broken database, a wrong
    search type, a mis-parsed column or an acceptance rule that rejects everything. Each of those
    produces zero everywhere and a table that reads as a filter that worked.

    `AGENTS.md` forbids designing any part of the pipeline so that a null is harder to see. The
    converse obligation is this one: a null has to be *earned*, and the cheapest proof that the
    instrument can detect at all is that it detects the things it is made of. A self-hit is exact,
    full-length and far above the cut, so a pass rate below `expect` is a defect rather than
    biology.
    """
    started = time.time()
    control_db = work / "controlDB"
    result_db = work / "controlResultDB"
    tsv = work / "control.tsv"
    tmp = work / "controltmp"
    for stem in (control_db, result_db):
        for stale in stem.parent.glob(f"{stem.name}*"):
            stale.unlink() if stale.is_file() else shutil.rmtree(stale, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    mmseqs("createdb", str(queries), str(control_db), env=work, threads=threads)
    mmseqs(
        "search",
        str(query_db),
        str(control_db),
        str(result_db),
        str(tmp),
        "--search-type",
        "3",
        "-e",
        str(ACCEPT["max_evalue"]),
        env=work,
        threads=threads,
    )
    mmseqs(
        "convertalis",
        str(query_db),
        str(control_db),
        str(result_db),
        str(tsv),
        "--format-output",
        ",".join(MMSEQS_FORMAT),
        env=work,
        threads=threads,
    )
    with open(tsv) as handle:
        found = {
            a.family_id for a in parse_alignments(handle) if a.family_id == a.contig and accept(a)
        }
    shutil.rmtree(tmp, ignore_errors=True)
    tsv.unlink(missing_ok=True)

    rate = len(found) / expect if expect else 0.0
    result = {
        "families_expected": expect,
        "families_self_detected": len(found),
        "rate": round(rate, 4),
        "seconds": round(time.time() - started, 1),
        "why": (
            "a self-hit is exact and full-length, so this is the cheapest proof the instrument "
            "can detect at all; without it a zero in every genome is indistinguishable from a "
            "broken search"
        ),
    }
    if rate < 0.99:
        raise RuntimeError(
            f"the positive control failed: {len(found)} of {expect} families found themselves "
            f"({rate:.1%}). A zero in a real genome could not be read as absence, so the pass "
            "stops rather than producing tables that look like a null."
        )
    return result


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """A1.4's manifests, consumed rather than re-derived (D-059)."""
    index = manifest_dir / "index.json"
    if not index.exists():
        raise SystemExit(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. A2.3 "
            "consumes the manifests rather than re-deriving a surviving set (D-059)."
        )
    produced = json.loads(index.read_text())
    entries = produced.get("manifests", produced if isinstance(produced, list) else [])
    out = []
    for entry in entries:
        name = entry.get("manifest") or entry.get("file")
        path = manifest_dir / name if name else None
        if path is None or not path.exists():
            raise SystemExit(f"manifest listed in index.json is missing: {entry}")
        out.append({"path": path, "manifest": json.loads(path.read_text())})
    return out


def component_row(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """The manifest's row for the component this detector covers, or None if absent."""
    for source in manifest.get("sources", []):
        if source.get("corpus_component") == COVERED:
            return source
    return None


def outcome_of(row: dict[str, Any]) -> Outcome:
    """The component's policy outcome, read from the manifest rather than recomputed.

    This component is uniform and unread — `rules=0`, `read=False` for every reading — so the
    manifest states one verdict for all of it and there is no per-record evaluation to repeat.
    A row that is *not* uniform stops the run: it would mean a reading had gained a rule that
    reaches these genomes, which is the premise D-016 and D-182 both rest on.
    """
    if not row.get("uniform"):
        raise RuntimeError(
            f"{COVERED} is not uniform in this manifest, so a reading now has a rule that "
            "reaches it. D-182's route handling and D-016's withdrawal both assume otherwise, "
            "and the route of every detection here would be wrong."
        )
    name = row.get("uniform_outcome")
    try:
        return Outcome(name)
    except ValueError as exc:
        raise RuntimeError(f"unknown outcome {name!r} for {COVERED}") from exc


def search_assembly(
    accession: str,
    fasta: Path,
    query_db: Path,
    work: Path,
    *,
    threads: int,
) -> list[Any]:
    """Build a target database for one assembly, search it, and parse the alignments."""
    target_db = work / "targetDB"
    result_db = work / "resultDB"
    tsv = work / "alignments.tsv"
    tmp = work / "tmp"
    for path in (target_db.parent / "targetDB", result_db):
        for stale in path.parent.glob(f"{path.name}*"):
            stale.unlink() if stale.is_file() else shutil.rmtree(stale, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    mmseqs("createdb", str(fasta), str(target_db), env=work, threads=threads)
    # `--search-type 3` is nucleotide-to-nucleotide. Consensus is the query and the genome the
    # target, which is the direction AGENTS.md records as measured: the small side as query took
    # 335 s where the corpus as query had not left the prefilter after 45 minutes.
    mmseqs(
        "search",
        str(query_db),
        str(target_db),
        str(result_db),
        str(tmp),
        "--search-type",
        "3",
        "-e",
        str(ACCEPT["max_evalue"]),
        env=work,
        threads=threads,
    )
    mmseqs(
        "convertalis",
        str(query_db),
        str(target_db),
        str(result_db),
        str(tsv),
        "--format-output",
        ",".join(MMSEQS_FORMAT),
        env=work,
        threads=threads,
    )
    with open(tsv) as handle:
        alignments = list(parse_alignments(handle))
    shutil.rmtree(tmp, ignore_errors=True)
    tsv.unlink(missing_ok=True)
    return alignments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=0.0025, help="band rate (D-186: 0.0025)")
    parser.add_argument("--index", default=str(REPO / "artifacts" / "a2-3" / "assembly-index.json"))
    parser.add_argument("--manifests", default=str(REPO / "artifacts" / "a1-4"), type=Path)
    parser.add_argument(
        "--registry",
        default=str(REPO / "artifacts" / "a2-3" / "registries" / f"{REGISTRY}.json"),
    )
    parser.add_argument(
        "--library", default=str(REPO / "data" / "dfam" / "4.0" / f"{REGISTRY}.hmm")
    )
    parser.add_argument("--outdir", default=str(REPO / "artifacts" / "a2-3"))
    parser.add_argument("--scratch", default=None)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--limit", type=int, default=0, help="stop after N assemblies")
    parser.add_argument(
        "--release",
        action="append",
        help="limit to this release key; repeatable. Omit for every manifest in the dir",
    )
    parser.add_argument(
        "--tables-only",
        action="store_true",
        help=(
            "emit tables without searching, for manifests whose release has no such "
            "component at all; refuses any manifest that does have one"
        ),
    )
    parser.add_argument(
        "--skip-self-check",
        action="store_true",
        help="skip the positive control; a zero then cannot be read as absence",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    out = Path(args.outdir)
    scratch = Path(args.scratch or os.environ.get("TMPDIR", "/tmp")) / "a2-3-eve"
    scratch.mkdir(parents=True, exist_ok=True)

    # One provenance file per invocation, named for what it covered. `repro.run`'s own docstring
    # warns that a shared name means the second run silently overwrites the first one's
    # provenance — A1.5 hit it with two staging passes, and this tool hit it the first time the
    # searching pass and the tables-only pass both wrote `run-detect.json`.
    scope = "-".join(sorted(args.release)) if args.release else "all"
    if args.tables_only:
        scope = f"{scope}-tables-only"

    with run(
        "A2.3",
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name=f"run-detect-{scope}.json",
    ) as m:
        m.parameter("detector", DETECTOR)
        m.parameter("registry", REGISTRY)
        m.parameter("sample_seed", SEED)
        m.parameter("sample_rate", args.rate)
        m.parameter("acceptance_rule", dict(ACCEPT))
        m.parameter("covered_component", COVERED)
        m.parameter("decision_refs", ["D-186", "D-183", "D-182", "D-136", "D-103", "D-059"])
        m.tool("mmseqs", ["pixi", "run", "-e", "dev", "mmseqs", "version"])

        universe_doc = json.loads(m.input_file(args.registry, role="registry universe").read_text())
        universe = {
            f["family_id"]: f["name"]
            for f in universe_doc["families"]
            if f["is_erv"] and f["threshold"] is not None
        }
        thresholds = {acc: float(ACCEPT["min_identity"]) for acc in universe}
        m.parameter("families_in_universe", len(universe))
        if len(universe) != universe_doc["erv_models"]:
            raise SystemExit(
                f"selected {len(universe)} families but the registry reports "
                f"{universe_doc['erv_models']} searchable ERV models; the denominator would "
                "differ from the one D-185 recorded"
            )

        m.parameter("tables_only", args.tables_only)
        # Nothing below this point runs under --tables-only: no query set, no control, no
        # band. That mode exists for a release with no such component, where there is nothing
        # to search and the table's `not_searched` is a statement about the release rather than
        # about this pass. A manifest that *does* carry the component is refused below.
        query_db = scratch / "queryDB"
        if not args.tables_only:
            queries = scratch / "queries.fasta"
            query_info = write_queries(args.library, queries, universe)
            m.parameter("queries", query_info)
            for stale in scratch.glob("queryDB*"):
                stale.unlink() if stale.is_file() else shutil.rmtree(stale, ignore_errors=True)
            mmseqs("createdb", str(queries), str(query_db), env=scratch, threads=args.threads)

        work = scratch / "work"
        work.mkdir(parents=True, exist_ok=True)
        if args.tables_only:
            m.parameter("self_check", None)
        elif args.skip_self_check:
            m.note("positive control skipped; a zero in this run is not evidence of absence")
            m.parameter("self_check", None)
        else:
            control = self_check(
                query_db, queries, work, threads=args.threads, expect=len(universe)
            )
            m.parameter("self_check", control)
            print(
                f"  positive control: {control['families_self_detected']}/"
                f"{control['families_expected']} families found themselves "
                f"({control['rate']:.1%}) in {control['seconds']:.0f}s",
                flush=True,
            )

        index = load_index(m.input_file(args.index, role="assembly index"))
        band = [] if args.tables_only else sampled_members(index, seed=SEED, hi=args.rate)
        if args.limit:
            band = band[: args.limit]
        m.parameter("band_assemblies", len(band))
        m.parameter("band_compressed_bytes", sum(x.size for x in band))

        manifests = load_manifests(args.manifests)
        if args.release:
            wanted = set(args.release)
            manifests = [e for e in manifests if e["manifest"]["release"] in wanted]
            if not manifests:
                raise SystemExit(f"no manifest in {args.manifests} for release(s) {sorted(wanted)}")
        m.parameter("releases", sorted({e["manifest"]["release"] for e in manifests}))
        m.parameter(
            "manifests",
            [f"{e['manifest']['policy']['id']}/{e['manifest']['release']}" for e in manifests],
        )

        # One search per assembly, reused across readings: they differ only in route.
        alignments_by_assembly: dict[str, list[Any]] = {}
        searched: list[dict[str, Any]] = []
        for position, member in enumerate(band, start=1):
            fasta = work / f"{member.accession}.fasta"
            provenance = fetch_member(member, read_range, fasta)
            started = time.time()
            try:
                alignments = search_assembly(
                    member.accession, fasta, query_db, work, threads=args.threads
                )
            finally:
                fasta.unlink(missing_ok=True)  # D-103
            elapsed = time.time() - started
            alignments_by_assembly[member.accession] = alignments
            searched.append(
                {
                    "accession": member.accession,
                    "tar": member.tar,
                    "compressed_bytes": provenance["compressed_bytes"],
                    "uncompressed_bytes": provenance["uncompressed_bytes"],
                    "sha256_compressed": provenance["sha256_compressed"],
                    "alignments": len(alignments),
                    "search_seconds": round(elapsed, 1),
                }
            )
            print(
                f"  [{position}/{len(band)}] {member.accession}: "
                f"{provenance['uncompressed_bytes'] / 1e6:.1f} Mb, "
                f"{len(alignments)} alignments, {elapsed:.0f}s",
                flush=True,
            )

        residues = sum(s["uncompressed_bytes"] for s in searched)
        produced: list[dict[str, Any]] = []
        for entry in manifests:
            manifest = entry["manifest"]
            policy_id = manifest["policy"]["id"]
            release = manifest["release"]
            row = component_row(manifest)
            if args.tables_only and row is not None:
                raise SystemExit(
                    f"{policy_id}/{release} carries {COVERED}, so --tables-only would record "
                    "`not_searched` for a component this detector covers. That is the one "
                    "reading metrics/detections.md says must never be produced without a "
                    "search. Run the pass for this release instead."
                )

            sources: list[dict[str, Any]] = []
            detections: list[Any] = []
            sample: SampleDesign | None = None

            for source in manifest.get("sources", []):
                key = source.get("corpus_component")
                if key == COVERED and row is not None and band:
                    outcome = outcome_of(row)
                    route = route_for(outcome)
                    for accession, alignments in alignments_by_assembly.items():
                        detections.extend(
                            detections_for(
                                alignments,
                                record_id=accession,
                                route=route,
                                registry=REGISTRY,
                                registry_version=universe_doc["registry_version"],
                            )
                        )
                    sources.append(
                        {
                            "component": source.get("component", COVERED),
                            "corpus_component": COVERED,
                            "searched": True,
                            "uniform_outcome": outcome.value,
                            "route": route.value,
                            "records_in_source": universe_doc.get("assemblies") or len(index),
                            "records": len(searched),
                            "residues": residues,
                            "assemblies": searched,
                        }
                    )
                    sample = SampleDesign(
                        seed=SEED,
                        rate=args.rate,
                        population=len(index),
                        method="blake2b(seed, assembly_accession) < rate * 2**64",
                        decision_ref="D-182",
                        bands=((0.0, args.rate),),
                    )
                else:
                    # One row per component, not per staged object. Evo 1 publishes its viral
                    # component as three Parquet splits, so the manifest carries three rows for
                    # it; emitting all three would show one component three times, against
                    # `metrics/detections.md`'s "one row per component of the manifest". The
                    # objects behind the row are counted rather than dropped.
                    existing = next(
                        (s for s in sources if s["corpus_component"] == key and not s["searched"]),
                        None,
                    )
                    if existing is not None:
                        existing["staged_objects"] += 1
                        continue
                    why = NOT_SEARCHED.get(key)
                    if why is None:
                        why = PROTEIN_PROXY if release == "esm3-proxy" else ABSENT
                    sources.append(
                        {
                            "component": source.get("component", key),
                            "corpus_component": key,
                            "searched": False,
                            "staged_objects": 1,
                            "why": why,
                        }
                    )

            if row is None:
                # The release has no such component at all. Recorded as its own row so the
                # absence is visible rather than inferred from the other rows' silence.
                sources.append(
                    {
                        "component": COVERED,
                        "corpus_component": COVERED,
                        "searched": False,
                        "why": PROTEIN_PROXY if release == "esm3-proxy" else ABSENT,
                        "present_in_release": False,
                    }
                )

            table = DetectionTable(
                task="A2.3",
                detector=DETECTOR,
                registry=REGISTRY,
                registry_version=universe_doc["registry_version"],
                manifest=ManifestRef(
                    policy_id=policy_id,
                    release=release,
                    path=str(entry["path"].relative_to(REPO)),
                    sha256=sha256_file(entry["path"]),
                    removed_records=manifest.get("removed", {}).get("records", 0),
                ),
                sources=sources,
                sample=sample,
                rows=build_rows(detections, universe=universe, thresholds=thresholds),
                thresholds={
                    "rule": dict(ACCEPT),
                    "scalar": "sequence identity, the axis the rule is declared on",
                    "decision_ref": "D-186",
                    "note": (
                        "A conjunction: E-value, alignment length and identity. The table's "
                        "per-family threshold is the identity cut; the per-hit E-value, length "
                        "and bit score are in the .jsonl so a re-cut on any axis needs no "
                        "re-search."
                    ),
                },
                notes=[universe_doc["denominator"]["restriction"]],
            )
            check_route_coverage(table)

            stem = f"detections-{REGISTRY}-{policy_id}-{release}"
            table_path = out / f"{stem}.json"
            table_path.write_text(json.dumps(table.to_dict(), indent=1) + "\n")
            m.output_file(table_path, role=f"detection table {policy_id}/{release}")
            if detections:
                lines = list(
                    detection_rows(detections, extra={"detector": DETECTOR, "task": "A2.3"})
                )
                jsonl = out / f"{stem}.jsonl"
                jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
                m.output_file(jsonl, role=f"detections {policy_id}/{release}")
            produced.append(
                {
                    "policy": policy_id,
                    "release": release,
                    "table": table_path.name,
                    "estimate_kind": table.estimate_kind,
                    "families_with_a_hit": table.families_with_a_hit(),
                    "detections": len(detections),
                }
            )
            print(
                f"  {policy_id}/{release}: {table.estimate_kind}, "
                f"{table.families_with_a_hit()} families, {len(detections)} detections",
                flush=True,
            )

        # The index is **merged**, not overwritten. A release with no searchable component is
        # emitted by a separate --tables-only invocation, and a plain write would drop the
        # searching run's tables and its per-assembly provenance — leaving an index that says
        # nothing was searched beside tables that say it was. A2.4 reported the same shape as one
        # of its six faults: a collector flattening archived runs onto live ones.
        index_path = out / "detections-index.json"
        merged: dict[str, Any] = {
            "task": "A2.3",
            "detector": DETECTOR,
            "registry": REGISTRY,
            "families_in_universe": len(universe),
            "band": {"seed": SEED, "rate": args.rate, "assemblies": len(band)},
            "searched": [],
            "tables": [],
        }
        if index_path.exists():
            previous = json.loads(index_path.read_text())
            if previous.get("registry") != REGISTRY:
                raise SystemExit(
                    f"{index_path} indexes registry {previous.get('registry')!r}, not "
                    f"{REGISTRY!r}; merging would pool two universes"
                )
            merged["searched"] = list(previous.get("searched", []))
            merged["tables"] = list(previous.get("tables", []))
            # Keep the searching run's band rather than an empty one from a tables-only pass.
            if not band and previous.get("band", {}).get("assemblies"):
                merged["band"] = previous["band"]

        by_assembly = {row["accession"]: row for row in merged["searched"]}
        by_assembly.update({row["accession"]: row for row in searched})
        merged["searched"] = sorted(by_assembly.values(), key=lambda r: r["accession"])

        by_table = {(row["policy"], row["release"]): row for row in merged["tables"]}
        by_table.update({(row["policy"], row["release"]): row for row in produced})
        merged["tables"] = sorted(by_table.values(), key=lambda r: (r["release"], r["policy"]))

        index_path.write_text(json.dumps(merged, indent=1) + "\n")
        m.output_file(index_path, role="detection index")
        shutil.rmtree(work, ignore_errors=True)
        print(json.dumps(produced, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

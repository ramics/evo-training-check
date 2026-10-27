#!/usr/bin/env python3
"""Profile-search the surviving corpora and write the per-family hit tables — task A2.1.

    pixi run -e dev python tools/detect_profiles.py --manifests artifacts/a1-4
    pixi run -e dev python tools/detect_profiles.py --release opengenome --registry pfam
    pixi run -e dev python tools/detect_profiles.py --plan      # what it would read, no search

One table per manifest x registry. The pins, thresholds and sampling design are *inputs*: they
live in `amazebio.profiles` and `amazebio.detect` and are recorded in `tasks/DECISIONS.md`
D-075..D-080, fixed before any hit was inspected. This tool chooses nothing.

What it does, in order, per release:

1. **Reads A1.4's manifests** (`metrics/manifests.md`) for the sources in scope and the removed
   set. The surviving corpus is the released corpus minus what a reading removes, so the removed
   records are subtracted before anything is searched — and `amazebio.apply.route_for` refuses
   to route them, because a record a reading removes which is nonetheless in the release is a
   candidate conformance failure for A7.1 to establish, not a survival route A2.1 may assert.
2. **Samples by hash** (D-078) and streams only the sampled records' sequence
   (`amazebio.seqstream`). The object is read end to end — object storage offers no index into a
   gzip stream — but a 0.1% sample costs 0.1% of the search, which is the expensive part. The
   sample is here because D-078 pre-registered it, **not** because a census is unaffordable: the
   cost figure D-078 gave for that has been retracted (D-098 — its benchmark searched 300
   profiles against 2,000 short random sequences and understated throughput by about three
   orders of magnitude). A full pass over both releases against both registries is on the order
   of 3,000 core-hours.
3. **Calls genes** with Prodigal in metagenomic mode (D-077), then **searches both registries**
   at their declared thresholds (D-076).
4. **Resolves each hit's route** by re-running the same `amazebio.apply.resolve` A1.4 used, over
   the same evidence declaration, and checks the outcome against the manifest before trusting
   it. The manifest carries counts rather than per-record outcomes by design, so the route of a
   *named* record has to be recomputed; what is taken from the manifest is the surviving set
   itself, which is the thing A2.1 must not re-derive.

No sequence reaches an artefact. Residues live in memory, and called proteins in ephemeral
scratch when several band searches have to read them (D-103); the artefacts carry accessions,
scores and model coordinates only.
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, objectstore, profilesearch
from amazebio.apply import resolve, route_for
from amazebio.detect import (
    DetectionTable,
    ManifestRef,
    SampleDesign,
    build_rows,
    check_route_coverage,
    detection_rows,
    element_kind_for,
    in_band,
)
from amazebio.policyspec import Outcome, load_policy_dir
from amazebio.profiles import (
    MIN_MODEL_COVERAGE,
    PINNED_E_VALUE,
    PINNED_Z,
    REGISTRIES,
    Registry,
    registry,
)
from amazebio.repro import run, sha256_file
from amazebio.seqstream import iter_fasta_sampled, iter_stage2_sampled

REPO = Path(__file__).resolve().parent.parent
SPECS = REPO / "policies" / "specs"
DATA = REPO / "data" / "profiles"
OUTDIR = REPO / "artifacts" / "a2-1"

#: Seed for the sample. Pinned in D-078; the same value every run, so a wider pass extends the
#: same sample rather than drawing a new one.
#: Which task this run belongs to, and therefore which durable prefix its tables land under.
#: A2.1 searched a hash sample; A2.6 re-runs the same search at census depth (D-222). They are
#: separate measurements and neither may overwrite the other, so the task id is a parameter of
#: the run rather than a constant — the alternative is two copies of this tool drifting apart.
TASK_DEFAULT = "A2.1"
TASK = TASK_DEFAULT

#: Records gene-called and searched at a time. Chosen so a worker's peak stays in single-digit
#: gigabytes with eight of them on one machine: at A2.1's measured 1.50 ms per gene this is a
#: search of a couple of minutes, which is also short enough that a chunk's progress line is a
#: real heartbeat rather than silence (AGENTS.md).
CHUNK_RECORDS = 20_000


#: The deepest rate each task may read, by component. D-099 made the declared rate a
#: pre-registration rather than a flag, so reaching further is a decision recorded here in
#: code and not an argument someone can pass. A2.6's census rate of 1.0 is D-222's.
CENSUS_RATES = {"stage2": 1.0, "imgvr": 1.0, "imgpr": 1.0}


def rate_ceiling(task: str, component: str) -> float:
    """How deep `task` may read `component`, as a sampling rate.

    A2.1 pre-registered a tenfold deepening and may not exceed it. A2.6 exists precisely to
    read the rest, and its ceiling is the whole corpus; it is a separate task for that
    reason, so neither can quietly acquire the other's licence.
    """
    if task == "A2.6":
        return CENSUS_RATES[component]
    return DEEP_RATES[component]


def task_slug(task: str) -> str:
    """A task id as it appears in a path: `A2.6` -> `a2-6`."""
    return task.lower().replace(".", "-")


def canonical_out(task: str) -> Path:
    """Where a run that is the deliverable for `task` writes: `artifacts/a2-6` for A2.6."""
    return REPO / "artifacts" / task_slug(task)


def durable_for(task: str, out: Path, *, deliverable: bool = False) -> str | None:
    """The durable prefix for `task`, **or None for a run that is not its deliverable.**

    The prefix follows from the task id, which does not say where the run was told to write.
    On 2026-10-20 that published an end-to-end rehearsal of `--assemble` — real tables plus
    three synthetic band parts, written to a scratch directory — to `corpora/results/a2-6/`,
    under the exact names the census itself will use, in a bucket with no `DeleteObject`.
    `detect_segmented.py` had already learned this (D-193) and the lesson did not travel; it
    travels now. `--out` is the signal that separates a rehearsal from the deliverable, so it
    is the one used: publish from the task's canonical directory, and from nowhere else.

    The census workers are the exception that has to be declared rather than inferred. They
    run on an instance with no checkout and write to `/opt/amazebio/out-<band>`, which is a
    deliverable and is not the canonical directory. `--deliverable` says so explicitly, and
    the launcher is the only caller that passes it: an opt-in keeps the default refusing,
    which is the direction the incident says it must fail in.
    """
    if deliverable or out.resolve() == canonical_out(task).resolve():
        return objectstore.durable_results(task_slug(task))
    print(
        f"not publishing: --out {out} is not {canonical_out(task)}, so this run is a rehearsal",
        file=sys.stderr,
    )
    return None


SEED = 20261015

#: Per-source sample rates, fixed in D-078 before any hit was inspected. Keyed by the component
#: name `amazebio.corpora` uses. A component absent from this map is not searched by A2.1 (D-080).
SAMPLE_RATES = {
    "stage2": 0.002,
    "imgvr": 0.001,
    "imgpr": 0.001,
}

#: The deepened rates, declared before the deepening ran (D-099). Ten times the initial rates,
#: searched as the band [initial, deep) so the records the first pass read are not read again.
DEEP_RATES = {component: rate * 10 for component, rate in SAMPLE_RATES.items()}

#: Why each unsearched component is unsearched, by corpus component. Reported per manifest rather
#: than omitted, so a table is never read as a verdict on a release it only partly covers.
_PROPHAGE = (
    "bacterial and archaeal genomes: viral content there is prophage, and the instruments for "
    "it are A2.4's (D-080)"
)
_ESM3_READER = "protein corpus with no reader yet: the ESM3 proxy is read by A1.6 (D-043)"
NOT_SEARCHED = {
    "gtdb_v220": _PROPHAGE,
    "stage1_gtdb": _PROPHAGE,
    "stage1_imgpr": "Evo 1's plasmid/phage component: not staged as its own object (A1.2)",
    "ncrna": "non-coding RNA: a protein-profile search has nothing to find in it by construction",
    "organelles": "organelle genomes: host-side, which is A2.3 (D-080)",
    "promoters": "promoter sequence, not coding: no genes to call",
    "mrna": "mRNA: host-side transcript sequence, which is A2.3 (D-080)",
    "metagenomes": "not staged (A1.2)",
    "ncbi_eukaryotic_genomes": (
        "not staged (A1.2): 2.17 TB, and the component with no published viral screening step"
    ),
    "eukaryotic_genic_windows": "not staged (A1.2); endogenous elements in host genomes are A2.3",
    "uniref_2023_02": _ESM3_READER,
    "mgnify_2023_02": _ESM3_READER,
    "pdb": "not staged (D-033)",
    "jgi": "cannot be reconstructed at all (A1.5)",
}


# --------------------------------------------------------------------------------------
# Registry loading
# --------------------------------------------------------------------------------------


RegistryView = profilesearch.RegistryView


def family_universe(reg: Registry) -> profilesearch.RegistryView:
    """This tool's data root, bound to the shared `profilesearch.family_universe`."""
    return profilesearch.family_universe(reg, DATA)


def hits_dump_path(release: str, band: tuple[float, float] | None, *, root: Path | None) -> Path:
    """Where a finished search's raw hits are parked before routes are resolved.

    Searching is the expensive step and routing is the fragile one: three faults in this
    session's scaffolding — a cache keyed wrong, a guard that could not find a wide cache, and a
    taxonomy round-trip that lost its mapping — each fired *after* a 70-minute search and before
    its part was written, so each threw the search away. The dump makes that impossible: a run
    that has searched writes its hits here first, and a re-run with the same release and band
    reuses them instead of searching again. It holds scores, accessions and lineage, never
    sequence (D-103).
    """
    label = "full" if band is None else f"{band[0]:g}-{band[1]:g}"
    return (root or CACHE_ROOT) / release / f"hits-{label}.json"


def write_hits_dump(
    path: Path,
    *,
    hits: dict[str, list[dict[str, Any]]],
    per_source: list[dict[str, Any]],
    records: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "hits": hits,
                "per_source": per_source,
                "records": {
                    record_id: {
                        "component": record.component,
                        "taxonomy": dict(record.taxonomy or {}),
                    }
                    for record_id, record in records.items()
                },
            },
            indent=1,
        )
        + "\n"
    )


def read_hits_dump(
    path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    from amazebio.policyspec import Record

    payload = json.loads(path.read_text())
    records = {
        record_id: Record(
            id=record_id,
            component=row["component"],
            taxonomy=dict(row["taxonomy"] or {}),
        )
        for record_id, row in payload["records"].items()
    }
    return payload["hits"], payload["per_source"], records


def emit_hit_proteins(
    directory: Path,
    *,
    registry_id: str,
    proteins: list[Any],
    found: list[dict[str, Any]],
    family_of_profile: dict[str, str],
) -> int:
    """Write the residues of the genes that hit, per family, to ephemeral scratch.

    A3.4 has to place each surviving detection into one of its family's diversity bins, which
    needs the detection's residues — and no artefact carries residues (D-195, D-103). The
    residues exist for one moment, here, between gene calling and the hit row that replaces
    them with an accession and a score. This writes them out for the placement pass instead of
    making it read 35 GB of corpus again to re-derive what this pass already had in memory.

    What is written is the **matched domain region**, not the whole gene: A3.4's bins are built
    from Pfam's seed alignment, whose members are aligned regions, and a called gene is a whole
    protein — commonly two to three times the length of the member it is homologous to. The
    frozen criterion requires 80% coverage of both sequences, so comparing the two directly
    cannot place a detection however related it is, and the figure would read as an absence of
    diversity coverage when it measures a length asymmetry (D-241). A hit with no domain region
    is written whole and counted, so the choice is visible rather than silent.

    Scratch only, and the caller is responsible for pointing it outside the working tree:
    D-103 permits residues in memory and in ephemeral scratch, never in the repository, in
    `artifacts/`, or in the audit store. Appending rather than truncating, because one family
    collects hits from several sources and several bands.
    """
    wanted = {f"{row['record_id']}|{row['gene']}" for row in found}
    if not wanted:
        return 0
    sequences: dict[str, str] = {}
    for protein in proteins:
        name = profilesearch.text_of(protein.name)
        if name in wanted:
            sequences[name] = protein.textize().sequence
    by_family: dict[str, list[str]] = {}
    whole = 0
    for row in found:
        name = f"{row['record_id']}|{row['gene']}"
        sequence = sequences.get(name)
        if sequence is None:
            continue
        start, end = row.get("target_from"), row.get("target_to")
        if start and end:
            sequence = sequence[int(start) - 1 : int(end)]
        else:
            whole += 1
        by_family.setdefault(family_of_profile[row["profile"]], []).append(
            f">{name}|{start or 1}-{end or len(sequence)}\n{sequence}\n"
        )
    if whole:
        print(
            f"  {whole:,} hits carry no domain region and are written whole",
            flush=True,
        )
    out = directory / registry_id
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for family, entries in sorted(by_family.items()):
        with (out / f"{family}.faa").open("a") as handle:
            handle.writelines(entries)
        written += len(entries)
    return written


def hmm_path(reg: Registry) -> Path:
    """This tool's data root, bound to the shared `profilesearch.hmm_path`."""
    return profilesearch.hmm_path(reg, DATA)


def manifest_ref_path(path: Path) -> str:
    """How a manifest is cited in a detection table: repo-relative where it can be.

    `Path.relative_to` raises rather than giving up, and the path is whatever `--manifests`
    was given — relative in the census workers, since the instance has no checkout at the
    repository root. That raised *after* the search, so a worker would have spent its whole
    pass and then died with nothing written. Outside the repo the absolute path is the
    honest answer: it still says which file was read, and the digest beside it is what
    actually pins the content.
    """
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO))
    except ValueError:
        return str(resolved)


def call_genes(records: list[Any]) -> tuple[list[Any], dict[str, int]]:
    """A2.1's gene calling. Lives in `amazebio.profilesearch` so A2.4 calls the same one."""
    return profilesearch.call_genes(records)


def search_batch(
    regs: list[Registry],
    views: dict[str, Any],
    proteins: list[Any],
    *,
    source: Any,
    hits: dict[str, list[dict[str, Any]]],
    search_seconds: dict[str, float],
    emit_to: Path | None = None,
) -> set[str]:
    """Search one batch of called proteins against every registry, in place.

    Returns the record ids that hit something, because those are the only records the route
    resolution downstream looks up. At census depth, keeping the rest is the difference
    between a pass that fits in memory and one that does not.
    """
    touched: set[str] = set()
    if not proteins:
        return touched
    for reg in regs:
        t0 = time.time()
        found = search(reg, proteins, restrict_to=views[reg.id].restrict_to)
        search_seconds[reg.id] += time.time() - t0
        for row_hit in found:
            row_hit["component"] = source.component
            row_hit["corpus_component"] = source.corpus_component
            touched.add(row_hit["record_id"])
        hits[reg.id].extend(found)
        if emit_to is not None:
            emit_hit_proteins(
                emit_to,
                registry_id=reg.id,
                proteins=proteins,
                found=found,
                family_of_profile=views[reg.id].family_of_profile,
            )
    return touched


#: HMMER threads **per worker**, settable because at census depth the workers share a machine.
#: `profilesearch.search` defaults to 3, which is right for one process and wrong for eight:
#: eight band workers on an eight-vCPU instance ask for 24 threads, and D-233 measured three
#: concurrent jobs costing about sixteen times one rather than three. That is the trap this
#: knob exists to avoid, and `tools/ec2_detect_census.py` refuses a launch that oversubscribes.
DEFAULT_SEARCH_CPUS = 3
SEARCH_CPUS = DEFAULT_SEARCH_CPUS


def search(reg: Registry, proteins: list[Any], *, restrict_to: set[str] | None) -> list[Any]:
    """A2.1's search, at D-076's thresholds. Shared with A2.4 so the two tables can be joined
    rather than reconciled (D-113).

    Thread count changes timing and nothing else: `hmmsearch` partitions the same models over
    the same sequences at the same cutoffs, so a run at one thread and a run at three accept
    the same hits. That is what makes it safe to set per worker.
    """
    return profilesearch.search(
        reg, proteins, restrict_to=restrict_to, hmm_file=hmm_path(reg), cpus=SEARCH_CPUS
    )


# --------------------------------------------------------------------------------------
# Manifest reading
# --------------------------------------------------------------------------------------


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """A1.4's manifests, as written. The index is the list of what a run produced."""
    index = manifest_dir / "index.json"
    if not index.exists():
        raise SystemExit(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. A2.1 "
            "consumes the manifests rather than re-deriving a surviving set (D-059)."
        )
    produced = json.loads(index.read_text())
    manifests = []
    for entry in produced.get("manifests", produced if isinstance(produced, list) else []):
        # A1.4's index names each file under `manifest`; `file` is accepted as well rather than
        # assumed away, because the index is another task's artefact and this reader must fail
        # loudly on a shape it does not know instead of silently skipping an entry.
        name = entry.get("manifest") or entry.get("file")
        path = manifest_dir / name if name else None
        if path is None or not path.exists():
            raise SystemExit(f"manifest listed in index.json is missing: {entry}")
        manifests.append({"path": path, "manifest": json.loads(path.read_text())})
    return manifests


def removed_ids(manifest_dir: Path, manifest: dict[str, Any]) -> set[str]:
    """The record ids this reading removes, which are therefore not in the surviving corpus."""
    removed = manifest.get("removed", {}).get("file")
    if not removed:
        return set()
    path = manifest_dir / Path(removed).name
    if not path.exists():
        raise SystemExit(f"manifest names a removed set that is not there: {path}")
    return {json.loads(line)["record_id"] for line in path.read_text().splitlines() if line}


# --------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------


def searched_sources(
    manifest: dict[str, Any], release: str
) -> list[tuple[corpora.StagedSource, dict[str, Any]]]:
    """The staged objects A2.1 searches for one manifest, each with its manifest row.

    Per *object*, not per component: Evo 1 publishes stage 2 as three splits — train, valid and
    test — under one component name, and a loop over components would read the first and report
    counts as if it had read all three. `corpora.undeclared_objects` exists because that same
    three-for-two mistake was caught once already in A1.4.
    """
    rows = {s["key"]: s for s in manifest["sources"] if s.get("key")}
    chosen = []
    for source in corpora.sources_for(release):
        if source.corpus_component not in SAMPLE_RATES or not source.readable:
            continue
        row = rows.get(source.key)
        if row is None:
            raise SystemExit(
                f"{source.key} is a staged object A2.1 would search, and the manifest for "
                f"{manifest['policy']['id']} does not list it. The manifest is the surviving "
                "set; searching an object it does not account for would report a figure over a "
                "corpus nothing declared."
            )
        chosen.append((source, row))
    return chosen


def plan_lines(manifest: dict[str, Any], release: str) -> list[str]:
    """What `--plan` reports for one manifest: the objects, the rate and the sampled count.

    A function rather than a loop inside `main` because `--plan` reads
    :func:`searched_sources`, which changed shape once — from manifest rows to
    `(StagedSource, row)` pairs — and the plan branch was not changed with it, so the flag
    raised a `TypeError` until X1.6 came to use it. A search path is exercised by every real
    run; a reporting path is exercised only when somebody asks what a run would read, which
    is precisely when a stale call site is least welcome.
    """
    lines = []
    for source, row in searched_sources(manifest, release):
        rate = SAMPLE_RATES[source.corpus_component]
        records = row.get("records")
        expected = f"~{int(records * rate):,}" if records else "unknown"
        lines.append(
            f"  {source.corpus_component:>10}  rate {rate}  of "
            f"{records or '?'} records -> {expected} sampled"
        )
    return lines


def stream_source(client: Any, source: corpora.StagedSource, *, lo: float = 0.0, hi: float):
    """Sampled records with sequence, for one staged source, over the hash band `[lo, hi)`."""
    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if source.bytes and live != source.bytes:
        raise SystemExit(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}. "
            "Re-verify before trusting any count from it."
        )
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes or live,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,}: {exc}", file=sys.stderr
        ),
    )
    if source.reader == "stage2_parquet":
        yield from iter_stage2_sampled(
            obj.buffered(),
            component=source.component,
            record_prefix=source.corpus_component + ":" + Path(source.key).name,
            seed=SEED,
            lo=lo,
            hi=hi,
        )
    elif source.reader == "fasta":
        reader: Any = obj.buffered()
        if source.gzipped:
            from amazebio.uniref import GunzipStream

            reader = GunzipStream(reader)
        yield from iter_fasta_sampled(reader, component=source.component, seed=SEED, lo=lo, hi=hi)
    else:  # pragma: no cover - guarded by the caller
        raise SystemExit(f"no sequence reader for {source.key}")


#: Where called proteins live between a read pass and the searches that consume them (D-103).
#: Ephemeral per-session scratch, outside the working tree: sequence may live here and in memory,
#: never in the repository, `artifacts/`, or anything a reviewer reads as a result.
CACHE_ROOT = (
    Path(
        os.environ.get("AMAZEBIO_SCRATCH")
        or os.environ.get("CLAUDE_SCRATCH_DIR")
        or tempfile.gettempdir()
    )
    / "a2-1-proteins"
)


def cache_dir(release: str, *, root: Path | None = None) -> Path:
    return (root or CACHE_ROOT) / release


#: Cache layout version. Bumped when a cached file's meaning changes, so a cache written by
#: older code is refused with an instruction rather than misread. Version 1 wrote
#: `Record.taxonomy` as a list, which kept the ranks and dropped every taxon; nothing could
#: recover those taxa, so a version-1 cache has to be collected again.
CACHE_FORMAT = 2


def cache_stem(
    component: str, object_name: str, lo: float, hi: float, *, chunk: int | None = None
) -> str:
    """The cache's filename stem for one staged object and band.

    The *object* is in the key, not just the component, because Evo 1 publishes stage 2 as three
    splits under one component name: a stem keyed on the component alone makes the three collide,
    and the last write wins. That cost a 23-minute read once — the two empty splits overwrote the
    full one. Suffixes are concatenated rather than applied with `Path.with_suffix`, which would
    read the `.02` of a band bound as the suffix to replace.
    """
    stem = f"{component}--{object_name}--{lo:g}-{hi:g}"
    # A chunked collect writes one file per chunk. `read_cache` globs the object's files
    # and de-duplicates by record id, so the set reads back as one cache.
    return stem if chunk is None else f"{stem}--{chunk:05d}"


def write_cache(
    directory: Path,
    stem: str,
    proteins: list[Any],
    records: dict[str, Any],
    *,
    band: tuple[float, float],
) -> Path:
    """Write called proteins and their records' metadata for later searching.

    Two files: the proteins as gzipped FASTA named `<record_id>|gene<n>`, and a JSONL of each
    record's component and lineage, which is what the route resolution needs. No nucleotide
    sequence is written and nothing here is an artefact — see D-103.
    """
    directory.mkdir(parents=True, exist_ok=True)
    proteins_path = directory / f"{stem}.faa.gz"
    with gzip.open(proteins_path, "wt") as handle:
        for protein in proteins:
            handle.write(f">{profilesearch.text_of(protein.name)}\n{protein.textize().sequence}\n")
    with open(directory / f"{stem}.records.jsonl", "w") as handle:
        for record_id, record in records.items():
            handle.write(
                json.dumps(
                    {
                        "record_id": record_id,
                        "component": record.component,
                        # A rank -> taxon mapping, written as one. `list()` of it yields the
                        # ranks and loses every taxon, and the loss is silent until a rule
                        # reaches for `.get(rank)` — which is the whole evidence the taxonomy
                        # rules act on.
                        "taxonomy": dict(record.taxonomy or {}),
                        "band": list(band),
                        "format": CACHE_FORMAT,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return proteins_path


def read_cache(
    directory: Path, *, component: str, object_name: str, lo: float, hi: float
) -> tuple[list[Any], dict[str, Any], dict[str, int]]:
    """Load cached proteins for one staged *object*, keeping only records in band `[lo, hi)`.

    Keyed by the object, not the component, for the same reason `cache_stem` is: Evo 1's three
    stage-2 splits share a component name. Globbing on the component alone made each of the
    three load the whole component's cache, so the band's records were searched once per split
    and the part would have carried three copies of every detection — inflating each family's
    hit count threefold while leaving its record count right, which is the kind of error that
    survives a glance at the table.

    Band membership is recomputed from the record identifier rather than trusted from the file
    the cache was written by, which is what makes a cache unable to change what a run searched
    (D-103): a stale or wider cache yields exactly the band asked for, and a missing record
    yields a smaller count that the source row reports.
    """
    from pyhmmer.easel import Alphabet, TextSequence

    from amazebio.policyspec import Record

    amino = Alphabet.amino()
    proteins: list[Any] = []
    records: dict[str, Any] = {}
    stats = Counter({"records": 0, "genes": 0, "residues": 0, "records_without_genes": 0})
    seen: set[str] = set()

    for meta_path in sorted(directory.glob(f"{component}--{object_name}--*.records.jsonl")):
        for line in meta_path.read_text().splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row.get("format") != CACHE_FORMAT:
                raise SystemExit(
                    f"{meta_path} was written by cache format "
                    f"{row.get('format', 1)}, this is {CACHE_FORMAT}. Delete the cache "
                    "directory and re-run --collect: a format-1 cache stored the taxonomy's "
                    "ranks without their taxa, and the taxa cannot be recovered from it."
                )
            if not in_band(row["record_id"], seed=SEED, lo=lo, hi=hi):
                continue
            records[row["record_id"]] = Record(
                id=row["record_id"],
                component=row["component"],
                taxonomy=dict(row["taxonomy"] or {}),
            )
    for faa_path in sorted(directory.glob(f"{component}--{object_name}--*.faa.gz")):
        with gzip.open(faa_path, "rt") as handle:
            name = None
            for raw in handle:
                if raw.startswith(">"):
                    name = raw[1:].strip()
                    continue
                if name is None:
                    continue
                record_id = name.partition("|")[0]
                if record_id in records:
                    sequence = raw.strip()
                    proteins.append(
                        TextSequence(name=name.encode(), sequence=sequence).digitize(amino)
                    )
                    stats["genes"] += 1
                    stats["residues"] += len(sequence)
                    seen.add(record_id)
                name = None
    stats["records"] = len(seen)
    stats["records_without_genes"] = len(records) - len(seen)
    return proteins, records, dict(stats)


def _detection_from_row(row: dict[str, Any]) -> Any:
    """Rebuild a `Detection` from a written row, for assembling bands into one table."""
    from amazebio.survival import Detection, ElementKind, Route

    return Detection(
        family_id=row["family_id"],
        registry=row["registry"],
        registry_version=row["registry_version"],
        record_id=row["record_id"],
        route=Route(row["route"]),
        element_kind=ElementKind(row["element_kind"]),
        detector=row["detector"],
        score=row["score"],
        threshold=row["threshold"],
    )


def _merge_source_rows(parts: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Sum the per-source statistics of several band runs over the same sources.

    Counts add because the bands are disjoint (`amazebio.detect.in_band`); the bands themselves
    are collected rather than summed, so the assembled table can state which slices of the hash
    space were actually read and `SampleDesign.bands_cover_rate` can check they tile the rate.
    """
    merged: dict[str, dict[str, Any]] = {}
    for rows in parts:
        for row in rows:
            if not row.get("searched"):
                merged.setdefault(row["corpus_component"] + "|unsearched", dict(row))
                continue
            key = row["key"]
            if key not in merged:
                merged[key] = {**row, "bands": [row.get("band", [0.0, row["sample_rate"]])]}
                continue
            into = merged[key]
            for field in ("records", "genes", "residues", "records_without_genes"):
                into[field] = (into.get(field) or 0) + (row.get(field) or 0)
            into["read_seconds"] = round(
                into.get("read_seconds", 0) + row.get("read_seconds", 0), 1
            )
            for reg_id, seconds in row.get("search_seconds", {}).items():
                into["search_seconds"][reg_id] = round(
                    into["search_seconds"].get(reg_id, 0) + seconds, 1
                )
            into["bands"].append(row.get("band", [0.0, row["sample_rate"]]))
            into["sample_rate"] = max(into["sample_rate"], row["sample_rate"])
    return list(merged.values())


def _shelve_parts(
    part_paths: list[Path], out: Path
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    """Read each part once, keeping its counts and spilling its rows to one file per key.

    The counts are kilobytes and are needed by every table; the rows are gigabytes and are
    needed by exactly one. Parsing one part at a time and appending its rows as JSON lines
    means peak memory is one part rather than all of them, and the rows are then read back a
    line at a time by a generator that never holds the file.

    Returns the per-part counts in path order, and the shelf: `release|policy|registry` to the
    file holding that key's rows from every part of that release, in part order.

    **The release is in the key, and it has to be.** A part names its tables by policy and
    registry alone — `evo1-literal|pfam` — because within one part the release is implied. The
    two Evo releases are read under the same three policy ids, so a shelf keyed on the part's
    own key alone put both releases' rows in one file and every release's assembled table then
    read all of them. That is D-245: it inflated Evo 1's deepened Pfam figure from 590 families
    to 830 and Evo 2's from 811 to 836, in a table whose per-source counts were right, and it
    was found by re-running the search and getting the part back exactly.
    """
    shelf_dir = out / ".assemble"
    if shelf_dir.exists():
        shutil.rmtree(shelf_dir)
    shelf_dir.mkdir(parents=True)
    counts: list[dict[str, Any]] = []
    shelf: dict[str, Path] = {}
    handles: dict[str, Any] = {}
    try:
        for path in part_paths:
            part = json.loads(path.read_text())
            counts.append(
                {
                    "release": part["release"],
                    "band_multiple": part["band_multiple"],
                    "sources": part["sources"],
                }
            )
            for part_key, rows in part.get("tables", {}).items():
                key = f"{part['release']}|{part_key}"
                if key not in handles:
                    # The key carries a `|`, which is fine in a filename but reads badly; the
                    # shelf is internal and deleted, so the name only has to be unique.
                    shelf[key] = shelf_dir / (key.replace("|", "__") + ".jsonl")
                    handles[key] = shelf[key].open("w")
                handle = handles[key]
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            del part
    finally:
        for handle in handles.values():
            handle.close()
    return counts, shelf


def _shelved_rows(shelf: dict[str, Path], key: str) -> Iterator[dict[str, Any]]:
    """Every shelved row for one table key, one line at a time."""
    path = shelf.get(key)
    if path is None:
        return
    with path.open() as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def thresholds_for(reg: Registry) -> dict[str, Any]:
    """The threshold block a table records for `reg`.

    One definition, because the assembler needs it too when there is no initial pass to copy
    it from, and two copies of this would drift silently — a table's thresholds are read as
    the record of what the search actually applied.
    """
    return {
        "kind": "gathering" if reg.curated_cutoffs else "pinned-e-value",
        "e_value": None if reg.curated_cutoffs else PINNED_E_VALUE,
        "z": None if reg.curated_cutoffs else PINNED_Z,
        "min_model_coverage": MIN_MODEL_COVERAGE,
        "decision_ref": "D-076",
    }


def assemble(
    args: argparse.Namespace, regs: list[Registry], manifests: list[dict[str, Any]]
) -> int:
    """Merge the initial tables and every band part into the final tables, searching nothing.

    A deepened sample is produced by several runs because no single run here may exceed two
    hours (D-099). This is the step that makes them one result: detections are concatenated,
    per-source counts are summed, and the bands are recorded so the assembled table can prove
    its own denominator — `bands_cover_rate` is false if the bands leave a gap, which would mean
    the table claims a rate over records nobody read.
    """
    out = args.out
    views = {r.id: family_universe(r) for r in regs}
    parts_dir = out / "parts"
    part_paths = sorted(parts_dir.glob("part-*.json"))
    # Only the small half of each part — the band and the per-source counts — is held. The
    # detection rows are the large half and are shelved to one file per table key, because at
    # A2.6's census depth a part carries about one row per record searched and eight of them
    # parsed at once do not fit the container (D-099 sized the search, not the assembly).
    parts, shelf = _shelve_parts(part_paths, out)
    had_initial = any(out.glob("detections-*.json")) or (out / "initial").exists()
    print(
        f"assembling {len(parts)} band part(s)"
        + (" with the initial tables" if had_initial else " with no initial pass"),
        flush=True,
    )

    # Keep the first pass's tables as written, once, before anything overwrites them. They are
    # the result that was already reported, and a superseded artefact should stay readable.
    initial_dir = out / "initial"
    if not initial_dir.exists():
        # Only when there is one to keep. An empty `initial/` would read as a first pass that
        # found nothing, which is a different claim from a census that never had one.
        first_pass = sorted(out.glob("detections-*.json*"))
        if first_pass:
            initial_dir.mkdir(parents=True)
            for path in first_pass:
                shutil.copy2(path, initial_dir / path.name)
            print(f"  kept the initial pass in {manifest_ref_path(initial_dir)}", flush=True)

    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-assemble.json",
        durable=durable_for(TASK, out, deliverable=args.deliverable),
        durable_exempt=None
        if durable_for(TASK, out, deliverable=args.deliverable)
        else "rehearsal: --out is not the task's canonical directory",
    ) as m:
        m.parameter("assembled_parts", [part["band_multiple"] for part in parts])
        m.parameter("sample_seed", SEED)
        m.parameter("initial_rates", SAMPLE_RATES)
        m.parameter("deep_rates", DEEP_RATES)
        for entry in manifests:
            manifest = entry["manifest"]
            policy_id = manifest["policy"]["id"]
            release = manifest["release"]
            for reg in regs:
                view = views[reg.id]
                stem = f"detections-{reg.id}-{policy_id}-{release}"
                # A2.1 deepened a first pass, so the initial table was always there to merge
                # and to copy the table's own metadata from. A2.6 is a census: its bands start
                # at multiple 0 and tile the whole rate themselves, so there is no first pass
                # at all and this read raised FileNotFoundError — after the search, at the end of a run
                # costing hours. The three fields the initial table supplied are all
                # reconstructable from the manifest and the registry, which is what the
                # searching path does for them anyway.
                initial_path = initial_dir / f"{stem}.json"
                initial_table = (
                    json.loads(initial_path.read_text()) if initial_path.exists() else None
                )
                initial_jsonl = initial_dir / f"{stem}.jsonl"
                source_rows = [initial_table["sources"]] if initial_table else []
                for part in parts:
                    if part["release"] != release:
                        continue
                    source_rows.append(part["sources"])

                def _rows(
                    initial_jsonl: Path = initial_jsonl,
                    key: str = f"{release}|{policy_id}|{reg.id}",
                ) -> Iterator[dict[str, Any]]:
                    """The initial pass's rows, then every shelved band row, streamed.

                    Bound as defaults rather than closed over, because this is defined inside
                    two loops and a late-binding closure would hand every table the last
                    table's key — the kind of bug that produces a complete-looking artefact.
                    The release is part of the key for the reason the shelf records: without
                    it, this table reads the other release's rows as well as its own (D-245).
                    """
                    if initial_jsonl.exists():
                        with initial_jsonl.open() as fh:
                            for line in fh:
                                if line.strip():
                                    yield json.loads(line)
                    yield from _shelved_rows(shelf, key)

                # `build_rows` folds its argument into per-family counters, so it never needs
                # the detections as a list; generating them keeps the raw rows and the
                # Detection objects from being alive at the same time.
                detections = (_detection_from_row(row) for row in _rows())
                sources = _merge_source_rows(source_rows)
                searched = [s for s in sources if s.get("searched")]
                bands = sorted({tuple(b) for s in searched for b in s.get("bands", [])})
                rate = max((s["sample_rate"] for s in searched), default=1.0)
                sample = (
                    SampleDesign(
                        seed=SEED,
                        rate=rate,
                        population=sum(s["records_in_source"] or 0 for s in searched) or None,
                        bands=tuple(bands),
                    )
                    if searched
                    else None
                )
                table = DetectionTable(
                    task=TASK,
                    detector="profile-hmmer",
                    registry=reg.id,
                    registry_version=reg.version,
                    manifest=(
                        ManifestRef(**initial_table["manifest"])
                        if initial_table
                        else ManifestRef(
                            policy_id=policy_id,
                            release=release,
                            path=manifest_ref_path(entry["path"]),
                            sha256=sha256_file(entry["path"]),
                            removed_records=manifest.get("removed", {}).get("records", 0),
                        )
                    ),
                    sources=sources,
                    sample=sample,
                    rows=build_rows(
                        detections,
                        universe=view.universe,
                        thresholds=view.thresholds_by_family(),
                    ),
                    thresholds=(
                        initial_table["thresholds"] if initial_table else thresholds_for(reg)
                    ),
                    notes=[
                        *(initial_table["notes"] if initial_table else []),
                        (
                            f"Assembled from the initial pass and {len(parts)} band part(s) "
                            "(D-099). Bands are disjoint, so counts add and nothing was "
                            "searched twice."
                            if initial_table
                            else f"Assembled from {len(parts)} band part(s) with no initial "
                            "pass: the bands start at multiple 0 and tile the whole rate, so "
                            "every record the table claims was read by one of them."
                        ),
                    ],
                )
                check_route_coverage(table)
                if sample is not None and not sample.bands_cover_rate():
                    raise SystemExit(
                        f"{stem}: the bands {bands} do not tile [0, {rate}) — the table would "
                        "claim a rate over records nothing read. Run the missing band before "
                        "assembling."
                    )
                table.write(out / f"{stem}.json")
                m.output_file(out / f"{stem}.json", role="per-family hit table (assembled)")
                # The generator above is spent, so the record-level file streams a fresh pass
                # rather than a retained list: joining millions of rows into one string to
                # write it would cost more memory than holding the detections did.
                jsonl = out / f"{stem}.jsonl"
                written = 0
                with jsonl.open("w") as fh:
                    for line in detection_rows(
                        (_detection_from_row(row) for row in _rows()),
                        extra={"manifest": policy_id},
                    ):
                        fh.write(line + "\n")
                        written += 1
                if written:
                    m.output_file(jsonl, role="record-level detections (assembled)")
                else:
                    jsonl.unlink()
                survival = table.survival()
                print(
                    f"  {stem}: {survival['families_with_a_hit']:,} of "
                    f"{survival['families_in_universe']:,} families at rate {rate} "
                    f"({survival['estimate_kind']})",
                    flush=True,
                )
    # The shelf is an intermediate, and at census depth it is as large as the parts it came
    # from. The parts are the durable copy; this is scratch and goes.
    shelf_dir = out / ".assemble"
    if shelf_dir.exists():
        shutil.rmtree(shelf_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", default=REPO / "artifacts" / "a1-4", type=Path)
    parser.add_argument("--out", default=OUTDIR, type=Path)
    parser.add_argument("--registry", action="append", help="registry id; repeatable")
    parser.add_argument("--release", action="append", help="release key; repeatable")
    parser.add_argument("--policy", action="append", help="policy id; repeatable")
    parser.add_argument(
        "--limit-records", type=int, default=None, help="stop each source early; probing only"
    )
    parser.add_argument("--plan", action="store_true", help="print what would be read, then stop")
    parser.add_argument(
        "--task",
        default=TASK_DEFAULT,
        help="the task this run belongs to, which chooses the durable prefix its tables "
        "land under. A2.6's census pass must not write over A2.1's sampled tables: they "
        "are two measurements at two depths and the comparison between them is part of "
        "the result (D-222). (default: %(default)s)",
    )
    parser.add_argument(
        "--chunk-records",
        type=int,
        default=CHUNK_RECORDS,
        help="how many records to gene-call and search at a time. A band is read as a "
        "stream of chunks rather than one list, because at census depth a single staged "
        "object is the whole release: OpenGenome's stage-2 split holds 2,652,947 "
        "records. The chunk size changes no result, only the peak memory "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--search-cpus",
        type=int,
        default=DEFAULT_SEARCH_CPUS,
        help="HMMER threads for this worker's searches. The default suits one process on a "
        "machine; a census runs one worker per band on a shared instance, where workers "
        "times threads must not exceed the vCPUs — eight workers at the default ask for 24 "
        "threads on eight cores, which is why no band of the 2026-10-20 launch finished "
        "(D-233). Changes timing only, never which hits are accepted (default: %(default)s)",
    )
    parser.add_argument(
        "--band",
        help=(
            "hash band to search, as LO:HI in multiples of the component's own initial rate — "
            "so 1:2 reads from the initial rate out to twice it, whatever that rate is, and "
            "1:10 is the whole deepening. Writes a part file rather than tables; --assemble "
            "merges them. Bands exist because no single run here may exceed two hours while a "
            "10x pass is eight, and because the hash sample is nested, so a band re-reads "
            "nothing (D-099)."
        ),
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help=(
            "read the band and cache its called proteins to scratch, searching nothing. One "
            "collect pass then serves several --from-cache searches, so a release is read once "
            "rather than once per band (D-103)."
        ),
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="search a band from the cached proteins, reading no corpus",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        help="merge the initial tables and every part into the final tables, searching nothing",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=(
            "where called proteins are cached (D-103). Defaults to a scratch directory outside "
            "the working tree; never put it under artifacts/ or data/, where a reviewer looks "
            "for the audit's own artefacts."
        ),
    )
    parser.add_argument(
        "--emit-hit-proteins",
        type=Path,
        default=None,
        help=(
            "also write the residues of the genes that hit, one FASTA per family, for A3.4's "
            "bin placement to read (D-195). Ephemeral scratch only: residues never belong in "
            "the working tree or the audit store (D-103)."
        ),
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    parser.add_argument(
        "--deliverable",
        action="store_true",
        help="publish even though --out is not the task's canonical directory. For the census "
        "workers, which run on an instance with no checkout; never for a run by hand (D-224).",
    )
    args = parser.parse_args(argv)
    if args.emit_hit_proteins and args.collect:
        raise SystemExit(
            "--emit-hit-proteins needs a search to emit from; --collect searches nothing. "
            "Collect the band first, then search it with --from-cache --emit-hit-proteins."
        )

    global TASK, SEARCH_CPUS
    TASK = args.task
    if args.search_cpus < 1:
        raise SystemExit(f"--search-cpus {args.search_cpus} is not a thread count")
    SEARCH_CPUS = args.search_cpus

    regs = [registry(i) for i in (args.registry or sorted(REGISTRIES))]
    band: tuple[float, float] | None = None
    if args.band:
        lo_text, _, hi_text = args.band.partition(":")
        band = (float(lo_text), float(hi_text))
        # Multiples of the initial rate, not absolute rates: the upper end is checked per
        # component against the declared deep rate, which is what bounds it.
        if not 0 <= band[0] < band[1]:
            raise SystemExit(f"--band {args.band} is not a half-open band with LO < HI")
        if args.limit_records and not args.collect:
            # A band run publishes a part, and `--assemble` reads a part as *the* result for
            # that band. A part produced under `--limit-records` covers a few records and
            # claims the whole band, so merging it understates every family in it while the
            # coverage check still passes — the bands tile correctly. The guard is here
            # rather than in review because this exact pair, a 20-record probe of band
            # 1:126, published a part into the census prefix on 2026-10-20.
            raise SystemExit(
                "--limit-records with --band would publish a part covering a few records "
                "and claiming the whole band; --assemble cannot tell the difference. Probe "
                "without --band, or redirect the durable destination."
            )
    manifests = load_manifests(args.manifests)
    if args.release:
        manifests = [m for m in manifests if m["manifest"]["release"] in args.release]
    if args.policy:
        manifests = [m for m in manifests if m["manifest"]["policy"]["id"] in args.policy]
    if not manifests:
        raise SystemExit("no manifests selected")

    if args.assemble:
        return assemble(args, regs, manifests)

    policies = load_policy_dir(SPECS)
    by_release: dict[str, list[dict[str, Any]]] = {}
    for entry in manifests:
        by_release.setdefault(entry["manifest"]["release"], []).append(entry)

    if args.plan:
        for release, entries in sorted(by_release.items()):
            print(f"{release}:")
            for line in plan_lines(entries[0]["manifest"], release):
                print(line)
            print(f"  readings: {[e['manifest']['policy']['id'] for e in entries]}")
        return 0

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    views = {r.id: family_universe(r) for r in regs}
    client = _client()

    written: list[str] = []
    # One provenance file per invocation, named for what it covered. A full pass over both
    # nucleotide releases does not fit the time a single run gets here, so A2.1 is run per
    # release — and two runs sharing one `run.json` would leave the second silently overwriting
    # the first one's provenance, which A1.5 hit with two staging passes at once.
    scope = "-".join(sorted(by_release)) if len(by_release) < 3 else "all"
    # And the band, when there is one. A2.6 runs eight bands of one release at once on one
    # machine, and without this every worker names its provenance and its index for the
    # release alone: eight runs would write one `run-opengenome.json`, losing seven, and
    # eight different `index-opengenome.json` bodies under one durable key — which
    # `repro`'s commit-keyed copy refuses outright (D-216), after the work rather than
    # before it. A2.1 hit the same shape with two staging passes at once (A1.5).
    if band is not None:
        scope = f"{scope}-{band[0]:g}-{band[1]:g}"
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name=f"run-{scope}.json",
        durable=durable_for(TASK, out, deliverable=args.deliverable),
        durable_exempt=None
        if durable_for(TASK, out, deliverable=args.deliverable)
        else "rehearsal: --out is not the task's canonical directory",
    ) as m:
        m.parameter("registries", [r.key for r in regs])
        m.parameter("sample_seed", SEED)
        m.parameter("sample_rates", SAMPLE_RATES)
        m.parameter("pinned_z", PINNED_Z)
        m.parameter("pinned_e_value", PINNED_E_VALUE)
        m.parameter("min_model_coverage", MIN_MODEL_COVERAGE)
        m.parameter("gene_caller", "prodigal-meta")
        # Timing only, never which hits are accepted — but a timing probe whose manifest does
        # not say how many threads it had cannot cost anything, which is the gap D-267 is about.
        m.parameter("search_cpus", SEARCH_CPUS)
        m.parameter("limit_records", args.limit_records)
        for reg in regs:
            for spec in reg.files:
                path = reg.staged_dir(DATA) / spec.local_name
                if path.exists():
                    m.input_file(path, role=f"{reg.key}:{spec.name}")

        import pyhmmer
        import pyrodigal

        m.tools["pyhmmer"] = pyhmmer.__version__
        m.tools["pyrodigal"] = pyrodigal.__version__
        m.tools["prodigal"] = getattr(pyrodigal, "PRODIGAL_VERSION", None)

        for release, entries in sorted(by_release.items()):
            # One search per (release, source), reused by every reading of that release: the
            # readings differ in what they remove and in the route they imply, not in the
            # residues, and searching the same records three times would buy nothing.
            part: dict[str, Any] = {
                "release": release,
                # Multiples of each component's initial rate, as given on the command line, and
                # for the filename. The authoritative bands are the *resolved* rates recorded
                # per source, because components with different initial rates resolve the same
                # multiple to different bands — the assembler reads those and never this.
                "band_multiple": list(band) if band else [0.0, 1.0],
                "sources": [],
                "tables": {},
            }
            hits: dict[str, list[dict[str, Any]]] = {r.id: [] for r in regs}
            per_source: list[dict[str, Any]] = []
            sampled_records: dict[str, Any] = {}
            manifest0 = entries[0]["manifest"]
            dump = hits_dump_path(release, band, root=args.cache_dir)

            if dump.exists() and not args.collect and not args.emit_hit_proteins:
                # A previous run searched this band and something downstream failed. Reuse the
                # search rather than repeat it; the registries and thresholds are pins, so the
                # hits cannot have changed, and the dump records which bands they came from.
                # `--emit-hit-proteins` is the one case that must not reuse it: the dump holds
                # no residues by design, so reusing it would write an empty FASTA set and the
                # placement pass would read a coverage of zero as a measurement.
                hits, per_source, sampled_records = read_hits_dump(dump)
                print(
                    f"\n{release}: reusing the finished search in {dump} "
                    f"({sum(len(v) for v in hits.values()):,} hits over "
                    f"{len(sampled_records):,} records)",
                    flush=True,
                )
                m.note(f"Reused the search parked in {dump.name} rather than re-searching.")

            for source, row in [] if per_source else searched_sources(manifest0, release):
                initial = SAMPLE_RATES[source.corpus_component]
                # A band is given in rate units of the *initial* design, so --band 1:10 reads
                # "from the initial rate out to ten times it" whatever the component's rate is.
                # That keeps one flag meaningful across sources whose rates differ.
                lo, hi = (band[0] * initial, band[1] * initial) if band else (0.0, initial)
                ceiling = rate_ceiling(TASK, source.corpus_component)
                if hi > ceiling:
                    raise SystemExit(
                        f"--band {args.band} reaches rate {hi} for {source.corpus_component}, "
                        f"beyond {TASK}'s declared rate {ceiling} (D-099). A rate past the "
                        "pre-registered one is a new decision, not a flag."
                    )
                label = f"{source.corpus_component}/{Path(source.key).name}"
                print(
                    f"\n{release}/{label}: band [{lo}, {hi})",
                    flush=True,
                )
                started = time.time()
                search_seconds: dict[str, float] = {r.id: 0.0 for r in regs}
                hits_before = {r.id: len(hits[r.id]) for r in regs}
                if args.from_cache:
                    proteins, cached_records, stats = read_cache(
                        cache_dir(release, root=args.cache_dir),
                        component=source.corpus_component,
                        object_name=Path(source.key).name,
                        lo=lo,
                        hi=hi,
                    )
                    sampled_records.update(cached_records)
                    read_seconds = time.time() - started
                    # Any cache file for this object counts, not one named for the band being
                    # searched: a collect pass caches a wide band and each search takes a
                    # sub-band out of it by recomputing membership, which is the whole point of
                    # keying on the record id. Looking for an exact stem match cost a finished
                    # 70-minute search once — the guard fired after the work and before the
                    # part was written.
                    cached_any = any(
                        cache_dir(release, root=args.cache_dir).glob(
                            f"{source.corpus_component}--{Path(source.key).name}--*.faa.gz"
                        )
                    )
                    if not proteins and not cached_any:
                        raise SystemExit(
                            f"{label}: no cache for band [{lo}, {hi}). Run --collect for this "
                            "band first; searching nothing would write a part that silently "
                            "covers no records."
                        )
                    print(
                        f"  {stats['records']:,} records from cache in "
                        f"{read_seconds:.1f}s ({stats['genes']:,} genes, "
                        f"{stats['residues']:,} residues)",
                        flush=True,
                    )
                    if not args.collect:
                        search_batch(
                            regs,
                            views,
                            proteins,
                            source=source,
                            hits=hits,
                            search_seconds=search_seconds,
                            emit_to=args.emit_hit_proteins,
                        )
                    del proteins
                else:
                    # Chunked, not accumulated. The band used to be read into one list and
                    # gene-called in a single call, which is fine at the pre-registered rate
                    # and impossible at census depth: OpenGenome's stage-2 split is one
                    # object of 2,652,947 records, so the whole release arrives as a single
                    # source and the list is the corpus. Searching in chunks changes no
                    # result — the detections are a union over records and every threshold
                    # is per protein — and it is what makes the census fit a machine the
                    # account permits instead of one it does not (AGENTS.md: check whether
                    # the work can be split before concluding it needs a bigger machine).
                    stats = Counter(
                        {"records": 0, "genes": 0, "residues": 0, "records_without_genes": 0}
                    )
                    read_seconds = 0.0
                    stream = stream_source(client, source, lo=lo, hi=hi)
                    chunk_index = 0
                    while True:
                        if args.limit_records and stats["records"] >= args.limit_records:
                            break
                        want = args.chunk_records
                        if args.limit_records:
                            want = min(want, args.limit_records - stats["records"])
                        t_read = time.time()
                        batch = list(itertools.islice(stream, want))
                        read_seconds += time.time() - t_read
                        if not batch:
                            break
                        records_here = {s.id: s.record for s in batch}
                        proteins, chunk_stats = call_genes(batch)
                        del batch
                        stats.update(chunk_stats)
                        print(
                            f"  chunk {chunk_index}: {chunk_stats['records']:,} records, "
                            f"{chunk_stats['genes']:,} genes "
                            f"({stats['records']:,} records read so far in "
                            f"{read_seconds / 60:.1f} min)",
                            flush=True,
                        )
                        if args.collect:
                            # One cache file per chunk. `read_cache` globs the object's files
                            # and de-duplicates by record id, so several are read as one.
                            written_to = write_cache(
                                cache_dir(release, root=args.cache_dir),
                                cache_stem(
                                    source.corpus_component,
                                    Path(source.key).name,
                                    lo,
                                    hi,
                                    chunk=chunk_index,
                                ),
                                proteins,
                                records_here,
                                band=(lo, hi),
                            )
                            print(f"    cached to {written_to}", flush=True)
                        else:
                            found_any = search_batch(
                                regs,
                                views,
                                proteins,
                                source=source,
                                hits=hits,
                                search_seconds=search_seconds,
                                emit_to=args.emit_hit_proteins,
                            )
                            # Only the records a hit points at are kept. Downstream reads
                            # `sampled_records` to resolve a hit's route, and nothing else;
                            # keeping every record read would put the census back in memory
                            # by another door.
                            for record_id in found_any:
                                sampled_records[record_id] = records_here[record_id]
                        del proteins, records_here
                        chunk_index += 1
                print(
                    f"  {stats['genes']:,} genes, {stats['residues']:,} residues "
                    f"({stats['records_without_genes']:,} records with no gene called)",
                    flush=True,
                )
                source_row = {
                    "component": source.component,
                    "corpus_component": source.corpus_component,
                    "key": source.key,
                    "searched": True,
                    "sample_rate": hi,
                    "band": [lo, hi],
                    "records_in_source": row.get("records"),
                    **stats,
                    "read_seconds": round(read_seconds, 1),
                    # A source the sample drew nothing from still costs a full pass over the
                    # profile file — 418 MB for Pfam, 2.7 GB for RVDB — to search nothing.
                    # Evo 1's test and valid splits are under a megabyte each, so at the
                    # pre-registered rate they are expected to be empty, and the zero is
                    # recorded rather than searched for.
                    "search_seconds": {r.id: round(search_seconds[r.id], 1) for r in regs},
                }
                if args.collect:
                    continue
                for reg in regs:
                    print(
                        f"  {reg.key}: {len(hits[reg.id]) - hits_before[reg.id]:,} hits "
                        f"above threshold in {search_seconds[reg.id] / 60:.1f} min",
                        flush=True,
                    )
                per_source.append(source_row)
            if per_source and not args.collect and not dump.exists():
                write_hits_dump(dump, hits=hits, per_source=per_source, records=sampled_records)
                print(f"  parked the search in {dump}", flush=True)

            if args.collect:
                # A collect run searched nothing, so it must write no part: a part whose tables
                # are empty would be merged by --assemble as a band that was searched and found
                # nothing, which is an understated bound with nothing to show it. The coverage
                # check cannot catch that — the bands would tile correctly.
                print(f"  collected {release}; searched nothing and wrote no part", flush=True)
                continue

            for entry in entries:
                manifest = entry["manifest"]
                policy = policies[manifest["policy"]["id"]]
                removed = removed_ids(args.manifests, manifest)
                searched_keys = {r["key"] for r in per_source}
                unsearched = [
                    {
                        "component": s["component"],
                        "corpus_component": s["corpus_component"],
                        "searched": False,
                        "why": NOT_SEARCHED.get(s["corpus_component"], "not searched by A2.1"),
                    }
                    for s in manifest["sources"]
                    if s.get("key") not in searched_keys or not s.get("key")
                ]
                ref = ManifestRef(
                    policy_id=manifest["policy"]["id"],
                    release=manifest["release"],
                    path=manifest_ref_path(entry["path"]),
                    sha256=sha256_file(entry["path"]),
                    removed_records=manifest.get("removed", {}).get("records", 0),
                )
                for reg in regs:
                    view = views[reg.id]
                    detections = []
                    excluded = 0
                    for row_hit in hits[reg.id]:
                        if row_hit["record_id"] in removed:
                            excluded += 1
                            continue
                        record = sampled_records[row_hit["record_id"]]
                        source = next(
                            s
                            for s in corpora.sources_for(release)
                            if s.corpus_component == row_hit["corpus_component"]
                        )
                        decision = resolve(policy, record, evidence=source.evidence)
                        if decision.outcome is Outcome.REMOVED:
                            raise SystemExit(
                                f"{manifest['policy']['id']}: {row_hit['record_id']} resolves to "
                                "removed but is not in the manifest's removed set. The manifest "
                                "and this pass disagree about the surviving corpus; nothing "
                                "downstream may be trusted until that is explained."
                            )
                        family = view.family_of_profile[row_hit["profile"]]
                        detections.append(
                            _detection(
                                family=family,
                                reg=reg,
                                row=row_hit,
                                route=route_for(decision.outcome),
                                threshold=view.thresholds[row_hit["profile"]],
                            )
                        )
                    table = DetectionTable(
                        task=TASK,
                        detector="profile-hmmer",
                        registry=reg.id,
                        registry_version=reg.version,
                        manifest=ref,
                        sources=[*per_source, *unsearched],
                        sample=(
                            SampleDesign(
                                seed=SEED,
                                rate=max(
                                    (s["sample_rate"] for s in per_source if s.get("searched")),
                                    default=1.0,
                                ),
                                population=sum(
                                    s["records_in_source"] or 0
                                    for s in per_source
                                    if s.get("searched")
                                )
                                or None,
                            )
                            if per_source
                            else None
                        ),
                        rows=build_rows(
                            detections,
                            universe=view.universe,
                            thresholds=view.thresholds_by_family(),
                        ),
                        thresholds=thresholds_for(reg),
                        notes=[
                            f"{excluded} hits fell on records this reading removes and are "
                            "excluded from the surviving set; they are candidate conformance "
                            "failures for A7.1, not detections (metrics/manifests.md).",
                            f"Registry membership: {reg.membership}",
                        ],
                    )
                    check_route_coverage(table)
                    if band is not None:
                        # A band run writes a part, not a table: a table built from one band
                        # would report a rate it did not search. `--assemble` merges them.
                        part["tables"][f"{manifest['policy']['id']}|{reg.id}"] = list(
                            detection_rows(detections, extra={"manifest": ref.policy_id})
                        )
                        part["tables"][f"{manifest['policy']['id']}|{reg.id}"] = [
                            json.loads(line)
                            for line in part["tables"][f"{manifest['policy']['id']}|{reg.id}"]
                        ]
                        print(
                            f"  {manifest['policy']['id']}/{reg.id}: {len(detections):,} "
                            "detections in this band",
                            flush=True,
                        )
                        continue
                    stem = f"detections-{reg.id}-{manifest['policy']['id']}-{manifest['release']}"
                    table.write(out / f"{stem}.json")
                    m.output_file(out / f"{stem}.json", role="per-family hit table")
                    written.append(f"{stem}.json")
                    if detections:
                        jsonl = out / f"{stem}.jsonl"
                        jsonl.write_text(
                            "\n".join(detection_rows(detections, extra={"manifest": ref.policy_id}))
                            + "\n"
                        )
                        m.output_file(jsonl, role="record-level detections")
                        written.append(f"{stem}.jsonl")
                    survival = table.survival()
                    print(
                        f"  {stem}: {survival['families_with_a_hit']:,} of "
                        f"{survival['families_in_universe']:,} families "
                        f"({survival['estimate_kind']})",
                        flush=True,
                    )

            if band is not None:
                part["sources"] = [*per_source, *unsearched]
                parts_dir = out / "parts"
                parts_dir.mkdir(parents=True, exist_ok=True)
                name = f"part-{release}-{band[0]:g}-{band[1]:g}.json"
                (parts_dir / name).write_text(json.dumps(part, indent=2) + "\n")
                m.output_file(parts_dir / name, role="band part")
                written.append(f"parts/{name}")

        index = {
            "task": TASK,
            "detector": "profile-hmmer",
            "tables": sorted(written),
            "registries": [r.key for r in regs],
            "sample": {"seed": SEED, "rates": SAMPLE_RATES, "decision_ref": "D-078"},
        }
        index["scope"] = scope
        (out / f"index-{scope}.json").write_text(json.dumps(index, indent=2) + "\n")
        m.output_file(out / f"index-{scope}.json", role="index")
        m.note(
            "Family-level survival from a sample is a lower bound (D-078): an unread record can "
            "only add a family, never remove one."
        )
    return 0


def _detection(*, family: str, reg: Registry, row: dict[str, Any], route: Any, threshold: float):
    from amazebio.survival import Detection

    return Detection(
        family_id=family,
        registry=reg.id,
        registry_version=reg.version,
        record_id=row["record_id"],
        route=route,
        element_kind=element_kind_for(row["corpus_component"]),
        detector="profile-hmmer",
        score=row["score"],
        threshold=threshold,
    )


def _client() -> Any:
    return objectstore.client()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Detect integrated elements in the surviving bacterial genomes — task A2.4.

    pixi run -e dev python tools/detect_proviruses.py --plan
    pixi run -e dev python tools/detect_proviruses.py --genomad-db data/genomad_db --limit 20

One table per registry x manifest, in `metrics/detections.md`'s shared shape, with
`detector: provirus-genomad` so A3.2 can keep A2.1's profile hits and A2.4's prophage hits
apart (D-113).

The pass is in two halves, and keeping them apart is the whole design.

**Where.** geNomad's `annotate` plus `find-proviruses` runs over sampled genomes and returns an
interval in a host contig. This, and only this, is what licenses `element_kind: prophage` — the
kind D-079 reserved for A2.4 to establish rather than for A2.1 to infer from a profile hit.

**Which family.** The proteins geNomad already called *inside* that interval are searched against
the registries A2.1 pinned, at D-076's thresholds unchanged. The family never comes from
geNomad's marker-consensus taxonomy, because that is taxonomy, and `DESIGN.md` §A2 opens by
ruling the filter's own instrument out of the audit.

So a detection says: this surviving bacterial genome carries an integrated element, and inside it
is a protein of this viral family. Both halves are measured, by different instruments, and the
artefact records which said what.

**What the numbers are.** A lower bound twice over, in one direction (D-115, D-113): a genome
outside the sample is not read, and a viral-family protein outside a provirus call is not counted.
A detection is evidence; an absence is not evidence of absence, and `estimate_kind` says so.

**Scope.** Evo 2's `gtdb` and Evo 1's `stage1_gtdb`, and nothing else. Every other component of
every manifest appears as a row with `searched: false` and a reason — the convention
`metrics/detections.md` fixed so that a table never reads as a verdict on a release it only
partly covered. Evo 1 and Evo 2 are **not** pooled and neither substitutes for the other
(D-116): they pin different GTDB snapshots, v214.1 against v214.1 plus a 220.0 increment (D-130).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import gtdb, profilesearch
from amazebio.apply import route_for
from amazebio.detect import (
    DetectionTable,
    ManifestRef,
    SampleDesign,
    build_rows,
    in_sample,
)
from amazebio.policyspec import Outcome
from amazebio.profiles import registry as load_registry
from amazebio.proviruses import (
    GENOMAD,
    SCOPE_NOTE,
    VIBRANT,
    concordance,
    read_genomad_proviruses,
    read_vibrant_proviruses,
)
from amazebio.survival import Detection, ElementKind, Route

REPO = Path(__file__).resolve().parent.parent

#: Where `tools/stage_profiles.py` puts the pinned registries. The same root A2.1 reads, so
#: both detectors search the same staged bytes.
PROFILE_DATA = REPO / "data" / "profiles"

#: Shared with A2.1 so that "was this record in both samples" is answerable without storing
#: either list (D-115). Not a new seed, deliberately.
SEED = 20261015

#: The first band. D-118 fixed the shape — nested bands, the first one its own calibration —
#: and D-132 restored spot, so the deepening to ~10% is affordable if the measured cost allows.
FIRST_BAND_RATE = 0.025

#: The concordance subsample is the *same* hash under the *same* seed at a tenth the main rate,
#: so it is nested inside the main sample, declarable in advance, and checkable per record
#: afterwards (D-114). A separate draw would have none of those properties.
CONCORDANCE_FRACTION = 0.1

OUTDIR = REPO / "artifacts" / "a2-4"

#: The corpus components A2.4 answers for. Everything else is reported unsearched, with a reason.
BACTERIAL_COMPONENTS = {"gtdb_v220", "stage1_gtdb"}

#: Why each component A2.4 does not touch is not touched. Keyed by corpus component, with a
#: default for anything added later — an unexplained `searched: false` is as opaque as an
#: omission.
NOT_SEARCHED_WHY: dict[str, str] = {
    "stage2": "Evo 1's viral component: free virus, not an integrated element. A2.1 searches it.",
    "imgvr": "Evo 2's viral component: free virus, not an integrated element. A2.1 searches it.",
    "imgpr": "Plasmids. A2.4 detects integrated elements in host genomes; A2.1 covers this.",
    "ncbi_eukaryotic_genomes": "Eukaryotic host genomes are A2.3's endogenous elements, not A2.4's "
    "prophage, and the component is not staged.",
    "eukaryotic_genic_windows": "Same: eukaryotic, A2.3's, and not staged.",
    "metagenomes": "Unassembled metagenomic sequence; not a host genome, and not staged.",
    "mrna": "Transcripts, eukaryote-derived; no host genome to carry an integrated element.",
    "ncrna": "Transcripts; no host genome to carry an integrated element.",
    "promoters": "Regulatory windows; no host genome to carry an integrated element.",
    "organelles": "Organelle genomes; prophage detection is not defined over them.",
    "stage1_imgpr": "Plasmids, and not staged.",
    # ESM3-open's proxy corpus is protein. There is no nucleotide genome to find an integrated
    # element in, so these are not a gap in A2.4's coverage but a category it is not defined over.
    "uniref_2023_02": "Protein sequences. An integrated element is a nucleotide feature of a "
    "host genome, so this detector is not defined over a protein corpus at all.",
    "mgnify_2023_02": "Protein sequences; same as UniRef.",
    "pdb": "Protein structures; same.",
    "jgi": "Not staged, and protein in any case.",
}
_DEFAULT_WHY = "Not a bacterial host genome, so A2.4's instruments are not defined over it."


class RunError(RuntimeError):
    """Raised when the pass cannot produce a table it would be honest to publish."""


# --------------------------------------------------------------------------------------
# Manifests and scope
# --------------------------------------------------------------------------------------


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """A1.4's manifests, as written. A2.4 consumes them rather than re-deriving a surviving set."""
    index = manifest_dir / "index.json"
    if not index.exists():
        raise SystemExit(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. A2.4 "
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


def source_rows(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a manifest's sources into the ones A2.4 searches and the ones it reports unsearched.

    Every source appears in one list or the other and none is dropped. `metrics/manifests.md`
    took this decision for A1.4 and `metrics/detections.md` repeats it for detectors, for the
    reason D-080 gives: a table that silently covered part of a release reads as a verdict on
    all of it.
    """
    searched, skipped = [], []
    for row in manifest.get("sources", []):
        component = row.get("corpus_component") or row.get("component") or ""
        if component in BACTERIAL_COMPONENTS:
            searched.append(row)
        else:
            skipped.append(
                {
                    "component": row.get("component"),
                    "corpus_component": component,
                    "searched": False,
                    "why": NOT_SEARCHED_WHY.get(component, _DEFAULT_WHY),
                    "records_in_source": row.get("records"),
                }
            )
    return searched, skipped


def route_of_source(source: dict[str, Any]) -> Route:
    """The survival route every genome in a bacterial source takes, from the manifest.

    `metrics/detections.md` says a detector recomputes the route of a *named* record, because
    the manifest carries outcome counts rather than a per-record outcome. That applies to an
    enumerated component. These are not enumerated: no rule in any reading reaches GTDB, so A1.4
    records a single `uniform_outcome` for the whole component and A2.4 reads it rather than
    re-deriving it. Re-deriving would mean this tool re-implementing the policy evaluation A1.4
    exists to be the single source of, which is what D-059 forbids.

    The route differs by reading, and that is the finding rather than an inconsistency: under
    the charitable and literal readings GTDB is `out_of_scope` — the filter never looked at it,
    which is D-007's headline — while the strict reading's wildcard scope examines it and keeps
    it, which is `retained_by_design`. The same prophage therefore sits on different routes in
    different manifests, and A3.2 cross-tabulates exactly that.
    """
    outcome = source.get("uniform_outcome")
    if not outcome:
        raise RunError(
            f"source {source.get('corpus_component')!r} carries no uniform_outcome, so it was "
            "enumerated rather than resolved uniformly. A2.4 would have to recompute a route "
            "per record, which this pass does not do — regenerate the manifest or extend it."
        )
    return route_for(Outcome(outcome))


# --------------------------------------------------------------------------------------
# Reading the bacterial components
# --------------------------------------------------------------------------------------


def objects_under(client: Any, bucket: str, prefix: str) -> list[str]:
    """Every staged object under a prefix, smallest first.

    Smallest first so a `--limit` probe reads the small object rather than opening a 10 GB
    shard to take two genomes from it.
    """
    found: list[tuple[int, str]] = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Size"] > 0:
                found.append((obj["Size"], obj["Key"]))
    return [key for _, key in sorted(found)]


def sampled_genomes_og2(client: Any, bucket: str, key: str, *, rate: float):
    """Yield `(assembly_accession, contigs)` for sampled genomes of one Evo 2 GTDB tar.

    Sampling decides on the assembly accession, which the publisher supplies, so membership is
    a property of the genome's own identifier and nothing is derived (D-136).
    """
    for accession, contigs in gtdb.iter_og2_genomes(gtdb.tar_stream(client, bucket, key)):
        if in_sample(accession, seed=SEED, rate=rate):
            yield accession, contigs


def sampled_genomes_og1(client: Any, bucket: str, key: str, *, rate: float):
    """Yield `(genome_key, contigs)` for sampled genomes of one Evo 1 GTDB Parquet object.

    Evo 1 publishes contigs with no genome column, so the genome is derived from the WGS project
    accession (D-136) and the sampling decides on *that*, never on the contig — sampling contigs
    would read a different fraction of every genome and make "a genome was searched" meaningless.

    Contigs of one genome are not guaranteed adjacent in the file, so in-sample contigs are
    accumulated and yielded at the end of the object. Only sampled genomes are held, so the
    memory is the sample rather than the shard. A genome whose contigs span two objects is
    yielded once per object; the caller merges on the id.
    """
    import pyarrow.parquet as pq

    from amazebio.objectstore import S3RandomRead

    held: dict[str, list[tuple[str, str]]] = {}
    handle = pq.ParquetFile(S3RandomRead(client, bucket, key))
    for accession, sequence in gtdb.iter_og1_contigs(handle):
        genome = gtdb.genome_key(accession).key
        if in_sample(genome, seed=SEED, rate=rate):
            held.setdefault(genome, []).append((accession, sequence))
    yield from held.items()


def write_batch(genomes: list[tuple[str, list[tuple[str, str]]]], path: Path) -> dict[str, int]:
    """Write sampled genomes to one FASTA under :func:`contig_header` names.

    One multi-FASTA rather than a file per genome: geNomad's cost is dominated by loading the
    marker database, so a call per genome would pay that once per genome instead of once per
    batch (D-117 measured annotation at 97% of the run).
    """
    stats = {"genomes": 0, "contigs": 0, "bases": 0}
    with path.open("w") as out:
        for genome_id, contigs in genomes:
            if not contigs:
                continue
            stats["genomes"] += 1
            for index, (_, sequence) in enumerate(contigs):
                if not sequence:
                    continue
                stats["contigs"] += 1
                stats["bases"] += len(sequence)
                out.write(f">{contig_header(genome_id, index)}\n{sequence}\n")
    return stats


# --------------------------------------------------------------------------------------
# Running the tools
# --------------------------------------------------------------------------------------


def _stream(cmd: list[str], *, label: str, on_line: Any = None) -> tuple[int, str]:
    """Run a long subprocess with its output visible, keeping the tail for an error message.

    `capture_output=True` was the first version and it made the longest step of the whole pass
    invisible: geNomad ran for hours with its progress swallowed, and because `beat()` fired
    only before the call there was no heartbeat either. On an instance whose console is the
    only channel and cannot distinguish a dead process from a quiet one, that is the silence
    `AGENTS.md` spends a paragraph on — and A2.4 shipped it twice, once for the corpus read and
    once here.

    So the output streams, which reaches `/dev/console` through the `tee` in `UserData`, and
    `on_line` lets the caller beat while it runs. The last lines are kept for the exception,
    because a failure still has to say why.
    """
    import collections

    tail: collections.deque[str] = collections.deque(maxlen=40)
    process = subprocess.Popen(
        cmd,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        tail.append(line)
        print(f"    [{label}] {line}", flush=True)
        if on_line is not None:
            on_line(line)
    return process.wait(), "\n".join(tail)


def genomad(
    fasta: Path,
    outdir: Path,
    database: Path,
    *,
    splits: int = 8,
    threads: int | None = None,
    on_line: Any = None,
) -> Path:
    """Run `annotate` then `find-proviruses`, and return the provirus table.

    Two calls rather than `end-to-end` because end-to-end also runs the virus/plasmid classifier
    and the score calibration, which A2.4 does not read: the provirus boundary is what it wants,
    and paying for a classification it will not use would be most of the run. `annotate` is 97%
    of the cost either way (D-117).

    `--splits` for the reason `AGENTS.md` records against A4.2: the marker index wants about
    24 GB in one pass and a session container has 16, and splitting the target database changed
    nothing about the result.
    """
    for module, extra in (("annotate", ["--splits", str(splits)]), ("find-proviruses", [])):
        cmd = [
            "pixi",
            "run",
            "-e",
            "proviruses",
            "genomad",
            module,
            str(fasta),
            str(outdir),
            str(database),
            *extra,
        ]
        if threads:
            cmd += ["--threads", str(threads)]
        code, tail = _stream(cmd, label=f"genomad {module}", on_line=on_line)
        if code != 0:
            raise RunError(f"genomad {module} failed ({code}): {tail}")
    stem = fasta.name.split(".")[0]
    table = outdir / f"{stem}_find_proviruses" / f"{stem}_provirus.tsv"
    if not table.exists():
        raise RunError(
            f"genomad find-proviruses wrote no provirus table at {table}. An empty run and a "
            "failed run must not look alike, so this stops rather than reporting zero."
        )
    return table


def vibrant(fasta: Path, outdir: Path, *, threads: int = 4) -> Path | None:
    """Run VIBRANT over the same FASTA and return its integrated-prophage table.

    The second instrument of the concordance criterion (D-114). It returns `None` rather than
    raising when VIBRANT cannot run, and that asymmetry with :func:`genomad` is deliberate: the
    expensive half of this pass is geNomad over sampled genomes, and losing it to a failure in
    the cheap secondary half would be the wrong trade. A missing concordance figure is recorded
    as missing — the table says the count rests on one instrument — while a missing prophage
    table would be the run.

    VIBRANT writes nothing when it finds no prophage in the input, so an absent table is read as
    "no calls" rather than as a failure, the same convention geNomad's own output follows.
    """
    code, tail = _stream(
        [
            "pixi",
            "run",
            "-e",
            "vibrant",
            "VIBRANT_run.py",
            "-i",
            str(fasta),
            "-folder",
            str(outdir),
            "-t",
            str(threads),
        ],
        label="vibrant",
    )
    stem = fasta.name.rsplit(".", 1)[0]
    table = (
        outdir
        / f"VIBRANT_{stem}"
        / f"VIBRANT_results_{stem}"
        / (f"VIBRANT_integrated_prophage_coordinates_{stem}.tsv")
    )
    if table.exists():
        return table
    print(
        f"  vibrant produced no coordinate table (exit {code}): {tail[-400:]}",
        flush=True,
    )
    return None


def provirus_proteins(table: Path) -> Path:
    """The proteins geNomad called inside the delineated proviruses, beside its table."""
    faa = table.with_name(table.name.replace("_provirus.tsv", "_provirus_proteins.faa"))
    if not faa.exists():
        raise RunError(
            f"no provirus proteins at {faa}: find-proviruses writes them beside its table, so "
            "their absence means the run did not complete rather than that nothing was found."
        )
    return faa


def read_faa(path: Path):
    """Yield `(name, sequence)` from a FASTA of proteins."""
    name, chunks = None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if name is not None:
                yield name, "".join(chunks)
            name, chunks = line[1:].split()[0], []
        elif name is not None:
            chunks.append(line.strip())
    if name is not None:
        yield name, "".join(chunks)


#: Separator between a genome id and its contig index in the FASTA this pass feeds geNomad.
#: A tilde because neither INSDC accessions nor assembly accessions contain one, and because
#: geNomad's own names use `|`, which must stay unambiguous — see :func:`host_of_protein`.
CONTIG_SEP = "~"


def contig_header(genome_id: str, index: int) -> str:
    """The name one sampled contig is given on its way into geNomad.

    Both releases are reduced to the same shape here: `<genome_id>~<n>`. Evo 2 publishes a
    genome per tar member and Evo 1's is derived from WGS project accessions (D-136), and once
    a contig is named this way the rest of the pass does not need to know which release it came
    from — which is what lets one code path produce two tables that differ only in their inputs.
    """
    if CONTIG_SEP in genome_id:
        raise RunError(
            f"genome id {genome_id!r} contains {CONTIG_SEP!r}, which this pass uses to separate "
            "a genome from its contig; the attribution back to the host would be ambiguous"
        )
    return f"{genome_id}{CONTIG_SEP}{index}"


def host_of_protein(protein_name: str) -> str:
    """The genome a provirus protein is counted on.

    geNomad names a provirus `<source_seq>|provirus_<start>_<end>` and its proteins
    `<provirus_name>_<n>`, and `source_seq` here is the `<genome_id>~<n>` of
    :func:`contig_header`. So the genome is everything before the first `|`, then everything
    before the last `~`.

    Counting on the genome rather than on the fragment is what D-113 requires. The fragment name
    is geNomad's invention: counting on it would make every provirus its own record, inflating
    the denominator and attributing a prophage's families to a sequence that exists nowhere
    outside this run. Counting on the contig would be wrong the other way — two proviruses in one
    genome would be two surviving records.
    """
    source_seq = protein_name.split("|")[0]
    genome, sep, _ = source_seq.rpartition(CONTIG_SEP)
    return genome if sep else source_seq


# --------------------------------------------------------------------------------------
# Detections
# --------------------------------------------------------------------------------------


def detections_from_hits(
    hits: list[dict[str, Any]],
    *,
    registry_id: str,
    registry_version: str,
    thresholds: dict[str, float],
    route: Route,
    profile_to_family: dict[str, str],
) -> list[Detection]:
    """Profile hits inside proviruses, as schema detections with `prophage` as the kind.

    The element kind is `PROPHAGE` and is not inferred from the families that were hit — it is
    what the provirus finder established about the interval these proteins came from (D-079,
    D-113). A hit whose profile is outside the pinned universe stops the run rather than being
    counted, because a family id the registry does not know changes the denominator silently.
    """
    out: list[Detection] = []
    for hit in hits:
        family = profile_to_family.get(hit["profile"])
        if family is None:
            raise RunError(
                f"profile {hit['profile']!r} is not in {registry_id}'s pinned universe; the "
                "registry version and the searched profiles disagree, which would change the "
                "denominator without showing it"
            )
        out.append(
            Detection(
                family_id=family,
                registry=registry_id,
                registry_version=registry_version,
                record_id=hit["record_id"],
                route=route,
                element_kind=ElementKind.PROPHAGE,
                detector="provirus-genomad",
                score=float(hit["score"]),
                threshold=float(thresholds[family]),
            )
        )
    return out


def _throttled(fn: Any, seconds: float) -> Any:
    """Call `fn` with the latest line, at most once every `seconds`."""
    state = {"last": 0.0}

    def call(line: str) -> None:
        now = time.time()
        if now - state["last"] >= seconds:
            state["last"] = now
            fn(line)

    return call


def host_of_contig(source_seq: str) -> str:
    """The genome a provirus call sits in, from the contig name this pass gave geNomad."""
    genome, sep, _ = source_seq.rpartition(CONTIG_SEP)
    return genome if sep else source_seq


def _rehome(call):
    """A provirus call re-keyed from its contig to its genome, for record-level agreement.

    The 2x2 in D-114 is per *record*, and this pass's record is the genome (D-136). Both tools
    report against the contig names they were given, so both are re-keyed the same way — doing
    it to one and not the other would make every multi-contig genome a disagreement.
    """
    import dataclasses

    return dataclasses.replace(call, source_record=host_of_contig(call.source_record))


def table_notes(*, genomes: int, proviruses: int, concordance: dict[str, Any] | None) -> list[str]:
    """Caveats that travel with the numbers, not a changelog."""
    notes = [
        SCOPE_NOTE,
        f"{proviruses:,} provirus call(s) across {genomes:,} sampled genome(s). The family "
        "universe and thresholds are A2.1's, unchanged (D-113), so an A2.1 table and this one "
        "differ only in route, element kind and the records searched.",
        "Localisation is geNomad's and identity is the registries'. The family is never taken "
        "from geNomad's marker-consensus taxonomy: that is the filter's own instrument, and "
        "DESIGN.md §A2 rules it out of the audit.",
        f"Instruments: geNomad {GENOMAD.version} against marker database {GENOMAD.database_version}"
        f", pinned apart from A4.2's 1.1.0 object of study (D-112); VIBRANT {VIBRANT.version} for "
        "concordance (D-114).",
    ]
    if concordance is None:
        notes.append(
            "No concordance subsample was run, so this table rests on one instrument. The "
            "agreement figure D-114 requires is not in it, and the prophage count must not be "
            "quoted as instrument-independent until it is."
        )
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", default=REPO / "artifacts" / "a1-4", type=Path)
    parser.add_argument("--out", default=OUTDIR, type=Path)
    parser.add_argument("--genomad-db", type=Path, help="the pinned marker database directory")
    parser.add_argument("--rate", type=float, default=FIRST_BAND_RATE)
    parser.add_argument("--registry", action="append", help="registry id; repeatable")
    parser.add_argument("--release", action="append", help="release key; repeatable")
    parser.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="read at most this many staged objects per source, smallest first. Like --limit "
        "it makes the denominator meaningless, so it writes no table either.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many sampled genomes. Exercises the whole path and writes NO "
        "table: a limited run's denominator is not the sample's, so any survival figure from "
        "it would be a null over data nobody read",
    )
    parser.add_argument("--plan", action="store_true", help="print the scope and stop")
    parser.add_argument(
        "--no-concordance",
        action="store_true",
        help="skip the VIBRANT arm. The tables then say the count rests on one instrument.",
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    parser.add_argument(
        "--upload-results",
        action="store_true",
        help="copy the artefacts to the results prefix. For the in-region run, whose only "
        "channel back is object storage.",
    )
    parser.add_argument(
        "--code-commit",
        default=None,
        help="the commit this code came from. The instance has no checkout, so repro cannot "
        "discover it and an untraceable manifest is not citable.",
    )
    parser.add_argument("--heartbeat-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)

    # Either flag makes the sample a probe: both read less than the rate says, and
    # `estimate_kind` is derived from the rate alone, so a table from either would report a
    # census over records nobody read (D-143). One condition, so neither can be added later
    # without the guard following it.
    args.probe = bool(args.limit or args.max_objects)

    manifests = load_manifests(args.manifests)
    if args.release:
        manifests = [m for m in manifests if m["manifest"]["release"] in set(args.release)]

    if args.plan:
        for entry in manifests:
            manifest = entry["manifest"]
            searched, skipped = source_rows(manifest)
            print(f"\n{manifest['policy']['id']} x {manifest['release']}")
            for row in searched:
                print(f"  SEARCH {row.get('corpus_component')}  {row.get('key', '')}")
            for row in skipped:
                print(f"  skip   {row['corpus_component']}: {row['why']}")
            if not searched:
                print(
                    "  -> estimate_kind: not_searched. No bacterial component in this manifest, "
                    "so every count would be zero by construction (D-116)."
                )
        return 0

    if not args.genomad_db:
        raise SystemExit("--genomad-db is required for a search pass; use --plan for the scope")

    import os

    from amazebio.objectstore import client as s3_client
    from amazebio.objectstore import split_uri
    from amazebio.repro import run, sha256_file

    bucket, _ = split_uri(os.environ["AMAZEBIO_S3_URI"])
    client = s3_client()
    registries = [load_registry(rid) for rid in (args.registry or ["pfam", "rvdb-prot"])]
    views = {reg.id: profilesearch.family_universe(reg, PROFILE_DATA) for reg in registries}
    args.out.mkdir(parents=True, exist_ok=True)

    results_prefix = "corpora/results/a2-4"

    def beat(stage: str, **fields: Any) -> None:
        """Say where the pass has got to, in the only channel an instance has.

        `AGENTS.md`: the console is best-effort and cannot tell a dead process from a quiet
        one — four hours went on that reading once. A step with no heartbeat is a step whose
        silence means nothing, so every stage publishes as it starts rather than when it ends.
        A failed heartbeat never fails the run it reports on.
        """
        if not args.upload_results:
            return
        body = {
            "stage": stage,
            "code_commit": args.code_commit,
            "rate": args.rate,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **fields,
        }
        try:
            client.put_object(
                Bucket=bucket,
                Key=f"{results_prefix}/heartbeat.json",
                Body=json.dumps(body, sort_keys=True, default=str).encode(),
            )
        except Exception as exc:
            print(f"    heartbeat failed: {type(exc).__name__}", flush=True)

    def publish(path: Path, role: str) -> None:
        """Put one finished artefact in the results prefix, as soon as it exists.

        Not batched at the end of the run. The first band needed about ten hours against a
        twelve-hour shutdown timer, and a single upload after every manifest would have lost
        Evo 1's finished tables along with Evo 2's unfinished ones if the timer had won. An
        artefact that is complete is uploaded; the sweep at the end is a backstop, not the
        mechanism.
        """
        if not args.upload_results:
            return
        try:
            client.put_object(
                Bucket=bucket, Key=f"{results_prefix}/{path.name}", Body=path.read_bytes()
            )
            print(f"  uploaded {role}: {path.name}", flush=True)
        except Exception as exc:
            print(f"    upload of {path.name} failed: {type(exc).__name__}", flush=True)

    beat("starting", manifests=len(manifests))

    with run(
        "A2.4",
        seed=SEED,
        outdir=args.out,
        allow_dirty=args.allow_dirty or bool(args.code_commit),
        repo=REPO,
    ) as manifest_run:
        # The instance has no git checkout, so `repro` cannot discover the commit and a
        # manifest produced there would be untraceable. The launcher refuses a dirty tree and
        # passes it in; recording it as a parameter is how it reaches the artefact.
        manifest_run.parameter("code_commit", args.code_commit)
        manifest_run.parameter("sample_seed", SEED)
        manifest_run.parameter("sample_rate", args.rate)
        manifest_run.parameter("genomad", GENOMAD.to_dict())
        manifest_run.parameter("vibrant", VIBRANT.to_dict())
        manifest_run.parameter("bacterial_components", sorted(BACTERIAL_COMPONENTS))

        for entry in manifests:
            manifest = entry["manifest"]
            policy_id = manifest["policy"]["id"]
            release = manifest["release"]
            searched, skipped = source_rows(manifest)
            rows: list[dict[str, Any]] = list(skipped)
            detections_by_registry: dict[str, list[Detection]] = {r.id: [] for r in registries}
            concordance_tables: list[dict[str, Any]] = []
            genomes_total = proviruses_total = 0

            for source in searched:
                component = source.get("corpus_component")
                prefix = source.get("key") or ""
                keys = objects_under(client, bucket, prefix) if prefix else []
                if args.max_objects:
                    keys = keys[: args.max_objects]
                beat("reading", release=release, component=component)
                started = time.time()
                last_beat = time.time()
                seen_genomes: dict[str, list[tuple[str, str]]] = {}
                for index, key in enumerate(keys):
                    reader = (
                        sampled_genomes_og1 if component == "stage1_gtdb" else sampled_genomes_og2
                    )
                    for genome_id, contigs in reader(client, bucket, key, rate=args.rate):
                        # Merge rather than append. `sampled_genomes_og1` yields a genome once
                        # per object, and a genome whose contigs straddle a shard boundary is
                        # therefore yielded twice. Appending both would count it as two
                        # surviving records and — worse — give its contigs colliding
                        # `<genome>~<n>` names, since the index restarts per occurrence, so two
                        # different sequences would enter geNomad under one name and the
                        # attribution back to the host would be ambiguous.
                        if genome_id in seen_genomes:
                            seen_genomes[genome_id].extend(contigs)
                        else:
                            seen_genomes[genome_id] = list(contigs)
                        # Beat *during* the read, not only at its start. The corpus pass is
                        # the longest step — over an hour for Evo 1's 127 GB — and the first
                        # version published nothing between "reading" and the search that
                        # followed it. `AGENTS.md`: a step with no heartbeat is a step whose
                        # silence means nothing, and that reading cost A1.6 four hours.
                        if time.time() - last_beat >= args.heartbeat_seconds:
                            last_beat = time.time()
                            beat(
                                "reading",
                                release=release,
                                component=component,
                                objects_done=index,
                                objects_total=len(keys),
                                genomes_sampled=len(seen_genomes),
                                elapsed_seconds=round(time.time() - started, 1),
                            )
                        if args.limit and len(seen_genomes) >= args.limit:
                            break
                    if args.limit and len(seen_genomes) >= args.limit:
                        break
                batch = list(seen_genomes.items())
                read_seconds = round(time.time() - started, 1)

                with tempfile.TemporaryDirectory(prefix="a2-4-") as workdir:
                    work = Path(workdir)
                    fasta = work / f"{release}-{component}.fna"
                    counts = write_batch(batch, fasta)
                    genomes_total += counts["genomes"]
                    search_seconds: dict[str, float] = {}
                    calls = []
                    if counts["genomes"]:
                        beat(
                            "genomad",
                            release=release,
                            component=component,
                            genomes=counts["genomes"],
                            bases=counts["bases"],
                        )
                        # Bound explicitly rather than closed over: ruff's B023 is right that
                        # a closure over the loop variables would report whichever source the
                        # loop had reached by the time it fired, not the one being searched.
                        genomad_beat = _throttled(
                            lambda line, _r=release, _c=component, _n=counts: beat(
                                "genomad",
                                release=_r,
                                component=_c,
                                genomes=_n["genomes"],
                                bases=_n["bases"],
                                last_line=line[:160],
                            ),
                            args.heartbeat_seconds,
                        )
                        table_path = genomad(fasta, work, args.genomad_db, on_line=genomad_beat)
                        calls = read_genomad_proviruses(table_path)
                        proviruses_total += len(calls)
                        proteins_faa = provirus_proteins(table_path)
                        proteins, pstats = profilesearch.proteins_from_fasta(
                            read_faa(proteins_faa), record_of=host_of_protein
                        )
                        route = route_of_source(source)
                        for reg in registries:
                            began = time.time()
                            hits = profilesearch.search(
                                reg,
                                proteins,
                                restrict_to=views[reg.id].restrict_to,
                                hmm_file=profilesearch.hmm_path(reg, PROFILE_DATA),
                            )
                            search_seconds[reg.id] = round(time.time() - began, 1)
                            detections_by_registry[reg.id] += detections_from_hits(
                                hits,
                                registry_id=reg.id,
                                registry_version=reg.version,
                                thresholds=views[reg.id].thresholds_by_family(),
                                route=route,
                                profile_to_family=views[reg.id].family_of_profile,
                            )
                    else:
                        pstats = {"records": 0, "genes": 0, "residues": 0}

                    if counts["genomes"] and not args.no_concordance:
                        sub = [
                            (g, c)
                            for g, c in batch
                            if in_sample(g, seed=SEED, rate=args.rate * CONCORDANCE_FRACTION)
                        ]
                        sub_fasta = work / f"{release}-{component}-concordance.fna"
                        sub_counts = write_batch(sub, sub_fasta)
                        if sub_counts["genomes"]:
                            vib_table = vibrant(sub_fasta, work)
                            vib_calls = read_vibrant_proviruses(vib_table) if vib_table else []
                            searched_ids = [g for g, _ in sub]
                            gen_on_sub = [
                                c
                                for c in calls
                                if host_of_contig(c.source_record) in set(searched_ids)
                            ]
                            agreement = concordance(
                                searched_ids,
                                [_rehome(c) for c in gen_on_sub],
                                [_rehome(c) for c in vib_calls],
                            )
                            concordance_tables.append(
                                {
                                    "release": release,
                                    "component": component,
                                    "subsample_rate": args.rate * CONCORDANCE_FRACTION,
                                    **agreement.to_dict(),
                                }
                            )

                rows.append(
                    {
                        "component": source.get("component"),
                        "corpus_component": component,
                        "searched": True,
                        "objects": len(keys),
                        "sample_rate": args.rate,
                        "records_in_source": source.get("records"),
                        "records": counts["genomes"],
                        "contigs": counts["contigs"],
                        "bases": counts["bases"],
                        "proviruses": len(calls),
                        "genes": pstats.get("genes", 0),
                        "residues": pstats.get("residues", 0),
                        "proteins_unplaced": pstats.get("proteins_unplaced", 0),
                        "read_seconds": read_seconds,
                        "search_seconds": search_seconds,
                        "limited": bool(args.probe),
                    }
                )

            for reg in registries:
                stem = f"detections-{reg.id}-{policy_id}-{release}"
                table = DetectionTable(
                    task="A2.4",
                    detector="provirus-genomad",
                    registry=reg.id,
                    registry_version=reg.version,
                    manifest=ManifestRef(
                        policy_id=policy_id,
                        release=release,
                        path=str(entry["path"].relative_to(REPO)),
                        sha256=sha256_file(entry["path"]),
                        removed_records=manifest.get("removed", {}).get("records", 0),
                    ),
                    sources=rows,
                    sample=(
                        SampleDesign(
                            seed=SEED,
                            rate=args.rate,
                            population=None,
                            bands=((0.0, args.rate),),
                        )
                        if any(r.get("searched") for r in rows)
                        else None
                    ),
                    rows=build_rows(
                        detections_by_registry[reg.id],
                        universe=views[reg.id].universe,
                        thresholds=views[reg.id].thresholds_by_family(),
                    ),
                    thresholds={
                        "source": "D-076, unchanged from A2.1 so the two tables compare",
                        "pfam": "per-model gathering cutoff, sequence half, as published",
                        "rvdb-prot": "pinned E-value against the pinned Z, per model",
                        "min_model_coverage": profilesearch.MIN_MODEL_COVERAGE,
                    },
                    notes=table_notes(
                        genomes=genomes_total,
                        proviruses=proviruses_total,
                        concordance=concordance_tables or None,
                    ),
                )
                survival = table.survival()
                if args.probe:
                    # A probe stops here. `estimate_kind` is derived from the sample rate, so a
                    # `--limit 1 --rate 1.0` run would write `population` over one genome — a
                    # Wilson interval of [0, 0.002] across 1,719 families, computed from 25 kb.
                    # That is a precise-looking null from almost no data, which is the one
                    # artefact `AGENTS.md` forbids this pipeline to be able to produce. The
                    # counts are printed; nothing is written.
                    print(
                        f"  [probe] {stem}: {survival['families_with_a_hit']:,} of "
                        f"{survival['families_in_universe']:,} families, "
                        f"{proviruses_total:,} provirus call(s) in {genomes_total:,} genome(s)"
                        " — not written: --limit/--max-objects make the denominator meaningless",
                        flush=True,
                    )
                    continue
                table.write(args.out / f"{stem}.json")
                manifest_run.output_file(
                    args.out / f"{stem}.json", role="per-family prophage hit table"
                )
                publish(args.out / f"{stem}.json", "hit table")
                print(
                    f"  {stem}: {survival['families_with_a_hit']:,} of "
                    f"{survival['families_in_universe']:,} families "
                    f"({survival['estimate_kind']})",
                    flush=True,
                )

            if concordance_tables and not args.probe:
                # Its own artefact, not a field on the hit tables. The agreement is between
                # instruments over records; it is not per registry, and copying it into each
                # table would invite it being read as a per-registry figure.
                path = args.out / f"concordance-{policy_id}-{release}.json"
                path.write_text(
                    json.dumps(
                        {
                            "task": "A2.4",
                            "criterion": "D-114",
                            "tools": [GENOMAD.to_dict(), VIBRANT.to_dict()],
                            "subsamples": concordance_tables,
                        },
                        indent=1,
                        sort_keys=True,
                    )
                    + "\n"
                )
                manifest_run.output_file(path, role="two-tool concordance")
                publish(path, "concordance")
        if args.upload_results:
            beat("uploading")
            for path in sorted(args.out.glob("*.json")):
                client.put_object(
                    Bucket=bucket,
                    Key=f"{results_prefix}/{path.name}",
                    Body=path.read_bytes(),
                )
                print(f"  uploaded s3://{bucket}/{results_prefix}/{path.name}", flush=True)
            beat("finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
   gzip stream — but a 0.1% sample costs 0.1% of the search, which is the part that is out of
   reach: a full pass over one component against RVDB-prot is on the order of 40,000 core-hours.
3. **Calls genes** with Prodigal in metagenomic mode (D-077), then **searches both registries**
   at their declared thresholds (D-076).
4. **Resolves each hit's route** by re-running the same `amazebio.apply.resolve` A1.4 used, over
   the same evidence declaration, and checks the outcome against the manifest before trusting
   it. The manifest carries counts rather than per-record outcomes by design, so the route of a
   *named* record has to be recomputed; what is taken from the manifest is the surviving set
   itself, which is the thing A2.1 must not re-derive.

No sequence is written. D-020 holds here as everywhere: residues live in memory for as long as
the search takes, and the artefacts carry accessions, scores and model coordinates only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora
from amazebio.apply import resolve, route_for
from amazebio.detect import (
    DetectionTable,
    ManifestRef,
    SampleDesign,
    build_rows,
    check_route_coverage,
    detection_rows,
    element_kind_for,
)
from amazebio.policyspec import Outcome, load_policy_dir
from amazebio.profiles import (
    MIN_MODEL_COVERAGE,
    PINNED_DOM_Z,
    PINNED_E_VALUE,
    PINNED_Z,
    REGISTRIES,
    ProfileError,
    Registry,
    iter_profile_headers,
    open_profiles,
    registry,
    select_viral_families,
)
from amazebio.repro import run, sha256_file
from amazebio.seqstream import iter_fasta_sampled, iter_stage2_sampled

REPO = Path(__file__).resolve().parent.parent
SPECS = REPO / "policies" / "specs"
DATA = REPO / "data" / "profiles"
OUTDIR = REPO / "artifacts" / "a2-1"

#: Seed for the sample. Pinned in D-078; the same value every run, so a wider pass extends the
#: same sample rather than drawing a new one.
SEED = 20261015

#: Per-source sample rates, fixed in D-078 before any hit was inspected. Keyed by the component
#: name `amazebio.corpora` uses. A component absent from this map is not searched by A2.1 (D-080).
SAMPLE_RATES = {
    "stage2": 0.002,
    "imgvr": 0.001,
    "imgpr": 0.001,
}

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


class RegistryView:
    """One registry resolved for searching: its universe, its thresholds, and what to search.

    Three keyings have to be kept straight and conflating them is the easy mistake. A *profile
    name* is what the HMM file calls a model and what a hit comes back under. A *family id* is
    what the survival counts are keyed on — Pfam's stable accession, RVDB's family name. And
    `restrict_to` is the set of profile names to search at all: Pfam is cut to the viral
    selection (D-075), while RVDB-prot is searched whole because its publisher's curation *is*
    the membership criterion.
    """

    def __init__(
        self,
        *,
        universe: dict[str, str],
        thresholds: dict[str, float],
        family_of_profile: dict[str, str],
        restrict_to: set[str] | None,
    ) -> None:
        self.universe = universe
        self.thresholds = thresholds
        self.family_of_profile = family_of_profile
        self.restrict_to = restrict_to

    def thresholds_by_family(self) -> dict[str, float]:
        return {self.family_of_profile[n]: t for n, t in self.thresholds.items()}


def family_universe(reg: Registry) -> RegistryView:
    """Resolve one pinned registry into the view the search and the tables need."""
    if reg.id == "pfam":
        selected = select_viral_families(reg.staged_dir(DATA) / "Pfam-A.hmm.dat.gz")
        return RegistryView(
            universe={a: m.name for a, m in selected.items()},
            # Pfam's own curated per-model gathering cutoff, sequence half. Used as published.
            thresholds={m.name: m.gathering[0] for m in selected.values() if m.gathering},
            family_of_profile={m.name: a for a, m in selected.items()},
            restrict_to={m.name for m in selected.values()},
        )

    path = reg.staged_dir(DATA) / reg.files[0].local_name
    universe: dict[str, str] = {}
    thresholds: dict[str, float] = {}
    for header in iter_profile_headers(path):
        universe[header.name] = header.accession or header.name
        thresholds[header.name] = header.bit_threshold(e_value=PINNED_E_VALUE, z=PINNED_Z)
    if reg.profile_count is not None and len(universe) != reg.profile_count:
        raise ProfileError(
            f"{reg.key}: {len(universe)} profiles read, publisher states {reg.profile_count}. "
            "The family universe is the denominator of every figure from this registry, so a "
            "disagreement about its size voids them all."
        )
    return RegistryView(
        universe=universe,
        thresholds=thresholds,
        family_of_profile={n: n for n in universe},
        restrict_to=None,
    )


def hmm_path(reg: Registry) -> Path:
    name = "Pfam-A.hmm.gz" if reg.id == "pfam" else reg.files[0].local_name
    return reg.staged_dir(DATA) / name


# --------------------------------------------------------------------------------------
# Searching
# --------------------------------------------------------------------------------------


def call_genes(records: list[Any]) -> tuple[list[Any], dict[str, int]]:
    """Call genes on sampled nucleotide records; returns digital protein sequences and counts.

    Metagenomic mode (D-077). Records whose genes cannot be called are counted rather than
    absorbed into "no hit": that population is a limit of the method and has to be visible.
    """
    import pyrodigal
    from pyhmmer.easel import Alphabet, TextSequence

    amino = Alphabet.amino()
    finder = pyrodigal.GeneFinder(meta=True)
    proteins: list[Any] = []
    stats = Counter({"records": 0, "records_without_genes": 0, "genes": 0, "residues": 0})
    for sampled in records:
        stats["records"] += 1
        genes = finder.find_genes(sampled.sequence)
        if not len(genes):
            stats["records_without_genes"] += 1
            continue
        for i, gene in enumerate(genes):
            protein = gene.translate().rstrip("*")
            if not protein:
                continue
            stats["genes"] += 1
            stats["residues"] += len(protein)
            # The gene index travels in the name so a hit can be placed back on its record
            # without the artefact carrying any sequence.
            name = f"{sampled.id}|gene{i}".encode()
            proteins.append(TextSequence(name=name, sequence=protein).digitize(amino))
    return proteins, dict(stats)


def search(reg: Registry, proteins: list[Any], *, restrict_to: set[str] | None) -> list[Any]:
    """Search one registry over called proteins, returning accepted `(hit, profile)` rows.

    Pfam is searched at its own gathering cutoffs; RVDB at the pinned E-value against the pinned
    `Z`, which is the same thing as the per-model bit score `bit_threshold` derives (D-076).
    Both are then held to :data:`MIN_MODEL_COVERAGE` of the model's length, measured on the
    best-covering domain of the hit.
    """
    import pyhmmer
    from pyhmmer.easel import Alphabet, DigitalSequenceBlock

    amino = Alphabet.amino()
    block = DigitalSequenceBlock(amino, proteins)
    accepted: list[dict[str, Any]] = []
    options: dict[str, Any] = (
        {"bit_cutoffs": "gathering"}
        if reg.curated_cutoffs
        else {"Z": PINNED_Z, "domZ": PINNED_DOM_Z, "E": PINNED_E_VALUE}
    )

    with open_profiles(hmm_path(reg)) as handle, pyhmmer.plan7.HMMFile(handle) as hmms:
        models = hmms if restrict_to is None else (h for h in hmms if _name(h) in restrict_to)
        for top in pyhmmer.hmmsearch(models, block, cpus=3, **options):
            query_name = _text(top.query.name)
            query_length = top.query.M
            for hit in top:
                if hit.included is False:
                    continue
                coverage = _best_model_coverage(hit, query_length)
                if coverage < MIN_MODEL_COVERAGE:
                    continue
                record_id, _, gene = _text(hit.name).partition("|")
                accepted.append(
                    {
                        "profile": query_name,
                        "model_length": query_length,
                        "record_id": record_id,
                        "gene": gene,
                        "score": float(hit.score),
                        "evalue": float(hit.evalue),
                        "coverage": coverage,
                    }
                )
    return accepted


def _text(value: Any) -> str:
    """A pyhmmer name as text. The library returns `bytes` in some versions and `str` in others."""
    return value.decode() if isinstance(value, bytes) else str(value)


def _name(hmm: Any) -> str:
    return _text(hmm.name)


def _best_model_coverage(hit: Any, model_length: int) -> float:
    """Fraction of the model covered by the hit's best-covering domain.

    Per domain rather than summed across domains: a family detected because four unrelated
    fragments of its model matched in different places is not the same claim as a family
    detected because one region matched most of the model, and A2.1 reports the stronger one.
    """
    if not model_length:
        return 0.0
    best = 0.0
    for domain in hit.domains:
        if domain.included is False:
            continue
        alignment = domain.alignment
        covered = (alignment.hmm_to - alignment.hmm_from + 1) / model_length
        best = max(best, covered)
    return best


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


def stream_source(client: Any, source: corpora.StagedSource, *, rate: float):
    """Sampled records with sequence, for one staged source."""
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
            rate=rate,
        )
    elif source.reader == "fasta":
        reader: Any = obj.buffered()
        if source.gzipped:
            from amazebio.uniref import GunzipStream

            reader = GunzipStream(reader)
        yield from iter_fasta_sampled(reader, component=source.component, seed=SEED, rate=rate)
    else:  # pragma: no cover - guarded by the caller
        raise SystemExit(f"no sequence reader for {source.key}")


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
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    regs = [registry(i) for i in (args.registry or sorted(REGISTRIES))]
    manifests = load_manifests(args.manifests)
    if args.release:
        manifests = [m for m in manifests if m["manifest"]["release"] in args.release]
    if args.policy:
        manifests = [m for m in manifests if m["manifest"]["policy"]["id"] in args.policy]
    if not manifests:
        raise SystemExit("no manifests selected")

    policies = load_policy_dir(SPECS)
    by_release: dict[str, list[dict[str, Any]]] = {}
    for entry in manifests:
        by_release.setdefault(entry["manifest"]["release"], []).append(entry)

    if args.plan:
        for release, entries in sorted(by_release.items()):
            print(f"{release}:")
            for source in searched_sources(entries[0]["manifest"]):
                rate = SAMPLE_RATES[source["corpus_component"]]
                records = source.get("records")
                expected = f"~{int(records * rate):,}" if records else "unknown"
                print(
                    f"  {source['corpus_component']:>10}  rate {rate}  of "
                    f"{records or '?'} records -> {expected} sampled"
                )
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
    with run(
        "A2.1",
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name=f"run-{scope}.json",
    ) as m:
        m.parameter("registries", [r.key for r in regs])
        m.parameter("sample_seed", SEED)
        m.parameter("sample_rates", SAMPLE_RATES)
        m.parameter("pinned_z", PINNED_Z)
        m.parameter("pinned_e_value", PINNED_E_VALUE)
        m.parameter("min_model_coverage", MIN_MODEL_COVERAGE)
        m.parameter("gene_caller", "prodigal-meta")
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
            hits: dict[str, list[dict[str, Any]]] = {r.id: [] for r in regs}
            per_source: list[dict[str, Any]] = []
            sampled_records: dict[str, Any] = {}
            manifest0 = entries[0]["manifest"]

            for source, row in searched_sources(manifest0, release):
                rate = SAMPLE_RATES[source.corpus_component]
                label = f"{source.corpus_component}/{Path(source.key).name}"
                print(f"\n{release}/{label}: sampling at {rate}", flush=True)
                started = time.time()
                batch: list[Any] = []
                for sampled in stream_source(client, source, rate=rate):
                    batch.append(sampled)
                    sampled_records[sampled.id] = sampled.record
                    if args.limit_records and len(batch) >= args.limit_records:
                        break
                read_seconds = time.time() - started
                print(
                    f"  {len(batch):,} records sampled in {read_seconds / 60:.1f} min; "
                    "calling genes",
                    flush=True,
                )
                proteins, stats = call_genes(batch)
                del batch
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
                    "sample_rate": rate,
                    "records_in_source": row.get("records"),
                    **stats,
                    "read_seconds": round(read_seconds, 1),
                    "search_seconds": {},
                }
                for reg in regs:
                    t0 = time.time()
                    found = search(reg, proteins, restrict_to=views[reg.id].restrict_to)
                    source_row["search_seconds"][reg.id] = round(time.time() - t0, 1)
                    for row_hit in found:
                        row_hit["component"] = source.component
                        row_hit["corpus_component"] = source.corpus_component
                    hits[reg.id].extend(found)
                    print(
                        f"  {reg.key}: {len(found):,} hits above threshold in "
                        f"{source_row['search_seconds'][reg.id] / 60:.1f} min",
                        flush=True,
                    )
                del proteins
                per_source.append(source_row)

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
                    path=str(entry["path"].relative_to(REPO)),
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
                        task="A2.1",
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
                        thresholds={
                            "kind": "gathering" if reg.curated_cutoffs else "pinned-e-value",
                            "e_value": None if reg.curated_cutoffs else PINNED_E_VALUE,
                            "z": None if reg.curated_cutoffs else PINNED_Z,
                            "min_model_coverage": MIN_MODEL_COVERAGE,
                            "decision_ref": "D-076",
                        },
                        notes=[
                            f"{excluded} hits fell on records this reading removes and are "
                            "excluded from the surviving set; they are candidate conformance "
                            "failures for A7.1, not detections (metrics/manifests.md).",
                            f"Registry membership: {reg.membership}",
                        ],
                    )
                    check_route_coverage(table)
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

        index = {
            "task": "A2.1",
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
    import boto3

    return boto3.client("s3", endpoint_url=corpora.S3_ENDPOINT, region_name=corpora.S3_REGION)


if __name__ == "__main__":
    raise SystemExit(main())

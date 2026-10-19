#!/usr/bin/env python3
"""Structure-based detection of surviving folds — A2.2's shard contract and its tables.

    pixi run -e dev python tools/detect_folds.py --plan
    pixi run -e dev python tools/detect_folds.py --assemble --out artifacts/a2-2

A2.2 runs in two stages, deliberately split, because they fail differently. The **search** is
about 25 GPU instance-hours over corpora that only exist in region; the **assembly** is seconds
over a few megabytes of scores. Keeping them apart means a reclaimed instance costs the shard it
was on rather than the pass, and it means the tables can be rebuilt at a different threshold
without re-reading a byte of corpus. This file owns the shard *contract* and the assembly; the
search stage that produces shards is not implemented here yet (see "What is missing" below).

**The expensive step does not depend on the manifest, so it is paid once.** 3Di prediction is the
whole cost of A2.2 — D-163 measured it at 18.58 core-hours per million residues on CPU, 173x the
profile search it feeds. What a protein's 3Di string is has nothing to do with which policy
reading retained its record, so a shard is keyed on *(release, staged object, sample band)* and
searched once; the three Evo 1 readings are then attributed from the same scores, with each
reading's removed set subtracted here. Predicting per reading would have tripled the bill for
nothing. Each table's `notes` records how many hits fell on records that reading removes.

**Shards store every hit above a threshold-independent floor.** :data:`FLOOR_BITS` sits far below
any cut the calibration can return, so the declared threshold *and both of its bracketing values*
(`metrics/survival.md` section 2) can be applied here, and a reviewer can re-cut without
re-searching. The threshold is read from the calibration artefact and never hardcoded.

**The family universe is the three folds, not ECOD's families.** §A2 names three folds, D-166
calls the denominator "three folds and 141 reference structures", and A2.2's Done-when criterion
asks for per-fold hit tables. So `family_id` is the fold id and the denominator is 3. Which ECOD
families and representatives constitute each fold is the membership rule, shipped separately as
`fold-universe.json` (D-169); a reader checks the rule there and the counts here.

**No sequence reaches an artefact** (D-103). A shard carries record ids, ECOD domain ids, scores
and coverages; the tables carry accessions and counts.

## The shard contract

One JSON file per (release, staged object, band), written by the search stage:

```json
{
  "release": "opengenome2",
  "key": "corpora/imgvr/<rev>/IMGVR_all_nucleotides.fna.gz",
  "component": "IMG/VR",
  "corpus_component": "imgvr",
  "band": [0.0, 0.001],
  "reference_sha256": "<digest of the fold-universe artefact>",
  "params": "<fingerprint: reference set + geometry + floor>",
  "alignment_mode": "3di_aa",
  "records": 2957, "genes": 41233, "residues": 9120411,
  "records_without_genes": 12,
  "read_seconds": 812.4, "search_seconds": 3310.9,
  "hits": [
    {"record_id": "...", "gene": "...|gene7", "target": "e1hx6A1",
     "bits": 212.0, "evalue": 1.2e-9, "fident": 0.21, "alnlen": 188,
     "qlen": 402, "tlen": 230, "tcov": 0.82}
  ]
}
```

`records_without_genes` is counted rather than absorbed into "no hit": a record whose genes the
caller could not call is a limit of the method, and `metrics/detections.md` requires it to be
visible per source.

## What is missing, and why it is not stubbed here

The search stage needs what `tools/detect_profiles.py` already has: A1.4 manifest reading,
sampled streaming of staged objects, gene calling, and the per-object protein cache. Those are
A2.1's and are not yet importable — the house precedent for sharing them is D-113, which factored
`amazebio.profilesearch` out of that tool so A2.4 could call the same search. The same move is
needed for the corpus-reading half, and it touches a finished task's code, so it wants its own
decision entry rather than a copy of 250 lines with A2.1's error messages in it.

Two of A2.1's lessons belong in that stage when it is written. The shard key must carry the
*object* name and not just the component, because Evo 1 publishes stage 2 as three splits under
one component name and a component-keyed stem made them collide and last-write-win. And the "is
this shard done?" test must be a listing of what exists rather than an exact-key match, because
an exact match once fired after a finished 70-minute search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, detect, folds, objectstore
from amazebio.survival import Detection, Route

REPO = Path(__file__).resolve().parent.parent

#: The sampling seed, A2.1's (D-078). Shared so a fold table and a profile table drawn at the
#: same rate read the same records, which is what lets A3.2 cross-tabulate them.
SEED = 20261015

#: The pre-registered depth: A2.1's initial rates, component for component (D-164). Explicitly
#: not a census — 1,682 instance-hours against 24.7 — and parity rather than a figure of A2.2's
#: own choosing, because A3.2 merges this table with A2.1's and `metrics/detections.md` forbids
#: pooling a `lower_bound` table with a `population` one.
SAMPLE_RATES = {
    "stage2": 0.002,
    "imgvr": 0.001,
    "imgpr": 0.001,
}

#: Hits weaker than this are not stored in a shard. Low enough to sit far below any cut the
#: calibration grid can return — it starts at 20 bits — so a shard supports the declared
#: threshold and both brackets without re-searching, and high enough that a shard does not become
#: a dump of every chance alignment.
FLOOR_BITS = 15.0

#: Columns a shard's hits carry. The four structural measures a reader will look for are
#: **unavailable by construction** against a ProstT5 query database and are named as such rather
#: than written as nulls that look like missing data (D-167).
UNAVAILABLE_COLUMNS = ("alntmscore", "qtmscore", "ttmscore", "lddt")

#: The columns asked of `convertalis`, in this order.
FORMAT = "query,target,bits,evalue,fident,alnlen,qlen,tlen,tcov"

#: foldseek's `--alignment-type` value per mode name, as D-171 calibrated them. 3Di+AA is the
#: declared mode; 3Di-only stays reachable so the bracket can be re-measured without new code.
ALIGNMENT_FLAGS = {"3di_aa": "2", "3di_only": "0"}

#: How often a running step says it is still alive, in seconds.
HEARTBEAT_INTERVAL_S = 120

#: Every search runs exhaustively, and this is not a tuning knob.
#:
#: Foldseek's prefilter is mis-tuned against a target database this small and **silently returns
#: nothing**: measured on real corpus input, 77 called proteins against the 141 reference
#: structures produced `0 median result list length`, `76 sequences with 0 size result lists`,
#: and an exit status of 0 — while the identical query and target databases searched
#: exhaustively produced 49 hits. Zero against 49.
#:
#: Shipping that would have manufactured a false null: a complete set of well-formed shards with
#: correct provenance reporting no surviving folds anywhere in either Evo release, which is the
#: one result this audit must never produce by accident. AGENTS.md forbids designing any part of
#: the pipeline so a null is harder to see, and a prefilter that deletes every candidate is the
#: strongest possible version of that.
#:
#: It is also **scale-dependent**, which is what makes it so dangerous: at the calibration's
#: 1,567 queries the prefilter dropped about 7% of rows, so a threshold calibrated at one query
#: count and applied at another would have hidden the failure entirely. Exhaustive search removes
#: the heuristic rather than retuning it — with 141 targets every query is aligned against every
#: reference, which is exact, scale-free, and negligible beside 3Di prediction.
EXHAUSTIVE_SEARCH = True

#: Why each unsearched component is unsearched, by corpus component. Carried per manifest rather
#: than omitted: `metrics/detections.md` is explicit that a table silently covering part of a
#: release reads as a verdict on all of it.
_PROPHAGE = (
    "bacterial and archaeal genomes: viral content there is prophage, and the instruments for "
    "it are A2.4's (D-080)"
)
_ESM3 = (
    "the ESM3-open proxy: its records are UniRef entries and many may already carry predicted "
    "structures, which makes its cost a different question from the Evo corpora's and leaves it "
    "unanswered (D-033)"
)
NOT_SEARCHED = {
    "gtdb_v220": _PROPHAGE,
    "stage1_gtdb": _PROPHAGE,
    "stage1_imgpr": "Evo 1's plasmid/phage component: not staged as its own object (A1.2)",
    "uniref_2023_02": _ESM3,
    "mgnify_2023_02": _ESM3,
    "pdb": _ESM3,
    "jgi": _ESM3,
}


class FoldDetectError(RuntimeError):
    """Raised when a table would record something it cannot support."""


# --------------------------------------------------------------------------------------
# Shard identity
# --------------------------------------------------------------------------------------


def object_name(key: str) -> str:
    """The staged object's own basename, which is what makes a shard key unique.

    Keyed on the object and not the component because Evo 1's stage 2 is three objects under one
    component name; A2.1 lost a 23-minute read to exactly that collision.
    """
    return key.rstrip("/").split("/")[-1] or key


def params_fingerprint(reference_sha256: str) -> str:
    """A short digest of everything that would change a shard's scores.

    The threshold is deliberately **not** in it: shards are stored above :data:`FLOOR_BITS`, so
    re-cutting does not invalidate them. The reference set and the search geometry are, because
    either changing means the stored scores answer a different question.
    """
    body = json.dumps(
        {
            "reference_sha256": reference_sha256,
            "cov_mode": 1,
            "min_target_coverage": 0.5,
            "floor_bits": FLOOR_BITS,
            "exhaustive_search": EXHAUSTIVE_SEARCH,
            "seed": SEED,
        },
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def shard_name(release: str, key: str, lo: float, hi: float) -> str:
    return f"{release}--{object_name(key)}--{lo:g}-{hi:g}.json"


def planned_shards(releases: list[str] | None = None) -> list[dict[str, Any]]:
    """Every (release, staged object, band) the pre-registered depth asks for."""
    out: list[dict[str, Any]] = []
    # The release list comes from the staged sources themselves: `corpora` publishes
    # SOURCES, not a release enumeration, and hardcoding one here would drift.
    names = list(releases or ()) or sorted({s.release for s in corpora.SOURCES})
    for release in names:
        try:
            sources = corpora.sources_for(release)
        # A release with no staged sources is simply skipped.
        except Exception:
            continue
        for source in sources:
            rate = SAMPLE_RATES.get(source.corpus_component)
            if rate is None or not source.readable:
                continue
            out.append(
                {
                    "release": release,
                    "key": source.key,
                    "component": source.component,
                    "corpus_component": source.corpus_component,
                    "band": [0.0, rate],
                    "name": shard_name(release, source.key, 0.0, rate),
                }
            )
    return out


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------


def load_fold_universe(path: Path) -> dict[str, Any]:
    """The membership rule and the reference set, as `build_fold_reference.py` shipped it."""
    body = json.loads(path.read_text())
    if "folds" not in body or "structures" not in body:
        raise FoldDetectError(
            f"{path}: not a fold-universe artefact — run tools/build_fold_reference.py first"
        )
    return body


def fold_universe_names(universe: dict[str, Any]) -> dict[str, str]:
    """The denominator: fold id to display name, three entries."""
    return {f["fold_id"]: f["name"] for f in universe["folds"]}


def target_to_fold(universe: dict[str, Any]) -> dict[str, str]:
    """Map each reference domain id to its fold.

    Taken from the artefact rather than recomputed from ECOD, so a table is attributed with the
    same membership rule the database was built from. A hit on a domain the artefact does not
    list is an error rather than a row to drop: it means the search ran against some other
    reference set, and silently ignoring it would report a figure over an unknown denominator.
    """
    return {s["domain_id"]: s["fold_id"] for s in universe["structures"]}


def load_threshold(path: Path, *, mode: str | None = None) -> dict[str, Any]:
    """The declared bit score and its two brackets, from the calibration artefact (D-171)."""
    body = json.loads(path.read_text())
    modes = body.get("modes", {})
    if not modes:
        raise FoldDetectError(f"{path}: no calibrated modes — run tools/calibrate_folds.py first")
    chosen_mode = mode or body.get("declared_alignment_mode")
    if chosen_mode is None:
        raise FoldDetectError(
            f"{path}: the artefact names no declared alignment mode and none was given; "
            f"have {sorted(modes)}"
        )
    if chosen_mode not in modes:
        raise FoldDetectError(f"{path}: no calibration for {chosen_mode!r}; have {sorted(modes)}")
    t = modes[chosen_mode]["threshold"]
    return {
        "kind": "bit score",
        "declared": float(t["declared_bits"]),
        "brackets": [float(b) for b in t["brackets"]],
        "binding_decoy_class": t["binding_class"],
        "target_fpr": t["target_fpr"],
        "alignment_mode": chosen_mode,
        "cov_mode": 1,
        "min_target_coverage": 0.5,
        "decision_ref": "D-171",
        "unavailable": list(UNAVAILABLE_COLUMNS),
        "unavailable_why": (
            "a ProstT5 query database holds 3Di strings and no C-alpha coordinates, so TM-score "
            "and LDDT cannot be computed at all — the publisher states this (D-167)"
        ),
    }


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """A1.4's manifests, read from their own index exactly as A2.1 reads them."""
    index = manifest_dir / "index.json"
    if not index.exists():
        raise FoldDetectError(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. A2.2 "
            "consumes the manifests rather than re-deriving a surviving set (D-059)."
        )
    produced = json.loads(index.read_text())
    entries = produced.get("manifests", produced if isinstance(produced, list) else [])
    out: list[dict[str, Any]] = []
    for entry in entries:
        name = entry.get("manifest") or entry.get("file")
        path = manifest_dir / Path(name).name if name else None
        if path is None or not path.exists():
            raise FoldDetectError(f"manifest listed in index.json is missing: {entry}")
        out.append({"path": path, "manifest": json.loads(path.read_text())})
    if not out:
        raise FoldDetectError(f"{index} lists no manifests")
    return out


def removed_ids(manifest_dir: Path, manifest: dict[str, Any]) -> set[str]:
    """The record ids this reading removes, which are therefore not in the surviving corpus."""
    removed = manifest.get("removed", {}).get("file")
    if not removed:
        return set()
    path = manifest_dir / Path(removed).name
    if not path.exists():
        raise FoldDetectError(f"manifest names a removed set that is not there: {path}")
    return {json.loads(line)["record_id"] for line in path.read_text().splitlines() if line.strip()}


def load_shards(shard_dir: Path, *, release: str) -> list[dict[str, Any]]:
    """Every finished shard for one release.

    Globbed rather than matched exactly, for A2.1's reason: an exact-key test once fired after a
    finished 70-minute search. A shard whose `params` disagree with its siblings stops the
    assembly — scores produced against two different reference sets must not be merged.
    """
    found = sorted(shard_dir.glob(f"{release}--*.json"))
    out = [json.loads(p.read_text()) for p in found]
    # A smoke shard must never become part of the audit. `--max-records` exists so the whole
    # pipeline can be exercised for a fraction of a cent before an instance is launched, and the
    # shard it writes looks exactly like a real one apart from this flag — so the flag is what
    # stops it being assembled into a citable table. Refused here rather than filtered out,
    # because a partial shard sitting beside complete ones means the run that produced them was
    # not the run somebody thinks it was.
    partial = [s for s in out if s.get("partial")]
    if partial:
        raise FoldDetectError(
            f"{shard_dir}: {len(partial)} shard(s) for {release} are partial — written by a "
            "capped --max-records run, which reads a bounded prefix of the object and is a smoke "
            "test, not a sample. Delete them or point --shards at the real prefix."
        )
    fingerprints = {s.get("params") for s in out}
    if len(fingerprints) > 1:
        raise FoldDetectError(
            f"{shard_dir}: shards for {release} carry more than one params fingerprint "
            f"({sorted(map(str, fingerprints))}). They were searched against different reference "
            "sets or geometries and cannot be merged."
        )
    return out


# --------------------------------------------------------------------------------------
# The search
# --------------------------------------------------------------------------------------


def heartbeat(s3: Any, uri: str | None, name: str, body: dict[str, Any]) -> None:
    """Publish progress as it happens. Never fails the run it reports on.

    AGENTS.md: a step with no heartbeat is a step whose silence means nothing at all. There is no
    shell on the instance, and the console cannot distinguish a dead process from a quiet one.
    """
    if not uri:
        return
    bucket, prefix = objectstore.split_uri(uri)
    payload = dict(body)
    payload["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        s3.put_object(
            Bucket=bucket,
            Key=f"{prefix}/{name}",
            Body=json.dumps(payload, indent=2, sort_keys=True).encode(),
        )
    # Reporting must never fail the measurement it reports on.
    except Exception as exc:
        print(f"    heartbeat failed: {type(exc).__name__}", flush=True)


def finished_shards(s3: Any, uri: str | None) -> set[str]:
    """Shard names already present at the destination.

    A listing, not an exact-key `head_object`: A2.1's exact-key test once fired *after* a
    finished 70-minute search, so what is already done is established by looking at what is
    there. The corpus bucket has no `DeleteObject`, so a name that appears is permanent and
    skipping it is always right.
    """
    if not uri:
        return set()
    bucket, prefix = objectstore.split_uri(uri)
    out: set[str] = set()
    token: str | None = None
    while True:
        kw = {"Bucket": bucket, "Prefix": f"{prefix}/"}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        for obj in page.get("Contents", []):
            name = obj["Key"].rsplit("/", 1)[-1]
            if name.endswith(".json") and "--" in name:
                out.add(name)
        if not page.get("IsTruncated"):
            return out
        token = page.get("NextContinuationToken")


def stream_sampled(client: Any, source: Any, *, lo: float, hi: float):
    """Sampled records with their sequence, for one staged object.

    Thin by design: `amazebio.seqstream` is the shared reader — "the reader A2.1 needed and A1.4
    did not" — so A2.2 reads the corpus through exactly the code A2.1 reads it through, at the
    same seed. Re-implementing the sampling here would be a second definition of which records
    are in the sample, which is the one thing a cross-tabulation in A3.2 cannot survive.
    """
    from amazebio import seqstream

    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if source.bytes and live != source.bytes:
        raise FoldDetectError(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}. "
            "Re-verify before trusting any count from it."
        )
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes or live,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,}: {exc}", file=sys.stderr, flush=True
        ),
    )
    if source.reader == "stage2_parquet":
        yield from seqstream.iter_stage2_sampled(
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
        yield from seqstream.iter_fasta_sampled(
            reader, component=source.component, seed=SEED, lo=lo, hi=hi
        )
    else:  # pragma: no cover — guarded by the caller
        raise FoldDetectError(f"no sequence reader for {source.key}")


def write_fasta(proteins: list[Any], path: Path) -> tuple[int, int]:
    """Write called proteins as FASTA, named `<record_id>|gene<n>`; return (count, residues)."""
    n = residues = 0
    with path.open("w") as fh:
        for p in proteins:
            seq = str(getattr(p, "sequence", None) or getattr(p, "seq", ""))
            name = getattr(p, "name", None)
            name = name.decode() if isinstance(name, bytes) else str(name or f"p{n}")
            if not seq:
                continue
            fh.write(f">{name}\n{seq}\n")
            n += 1
            residues += len(seq)
    return n, residues


def run_step(cmd: list[str], *, workdir: Path, label: str, on_tick: Any = None) -> None:
    """Run one foldseek step, reporting on an interval while it runs.

    `Popen` with output to files, not `subprocess.run(capture_output=True)`. The latter publishes
    nothing for the duration — on the instance that is indistinguishable from a dead process —
    and a pipe nobody drains can deadlock a noisy child. Both mistakes were made once already in
    `tools/fold_throughput.py`, and the 3Di step here runs for hours.
    """
    out_p = workdir / f"{label}.out"
    err_p = workdir / f"{label}.err"
    started = time.monotonic()
    with out_p.open("w") as out_fh, err_p.open("w") as err_fh:
        proc = subprocess.Popen(cmd, stdout=out_fh, stderr=err_fh, text=True)
        next_tick = started + HEARTBEAT_INTERVAL_S
        while proc.poll() is None:
            time.sleep(1.0)
            now = time.monotonic()
            if now >= next_tick:
                if on_tick is not None:
                    on_tick(label, round(now - started, 1))
                next_tick = now + HEARTBEAT_INTERVAL_S
    if proc.returncode != 0:
        tail = err_p.read_text(errors="replace").strip()[-800:]
        raise FoldDetectError(f"{label} failed with exit {proc.returncode}: {tail}")
    blob = (out_p.read_text(errors="replace") + err_p.read_text(errors="replace")).lower()
    if "no gpu devices found" in blob:
        raise FoldDetectError(
            f"{label}: foldseek reported no GPU and fell back to the CPU. A GPU figure measured "
            "on the CPU looks right, which is what makes it dangerous — refusing rather than "
            "writing a shard that took 64x longer than its own provenance claims."
        )


def parse_hits(tsv: Path, *, floor: float = FLOOR_BITS) -> list[dict[str, Any]]:
    """Read `convertalis` output, keeping hits at or above the floor.

    One row per (protein, reference domain). The record id is recovered from the protein name,
    which `write_fasta` forms as `<record_id>|gene<n>`.
    """
    cols = FORMAT.split(",")
    out: list[dict[str, Any]] = []
    if not tsv.exists():
        return out
    with tsv.open() as fh:
        for line in fh:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(cols):
                continue
            row = dict(zip(cols, fields, strict=True))
            bits = float(row["bits"])
            if bits < floor:
                continue
            out.append(
                {
                    "record_id": row["query"].split("|", 1)[0],
                    "gene": row["query"],
                    "target": row["target"].removesuffix(".cif"),
                    "bits": bits,
                    "evalue": float(row["evalue"]),
                    "fident": float(row["fident"]),
                    "alnlen": int(row["alnlen"]),
                    "qlen": int(row["qlen"]),
                    "tlen": int(row["tlen"]),
                    "tcov": float(row["tcov"]),
                }
            )
    return out


def search_shard(
    client: Any,
    shard: dict[str, Any],
    *,
    foldseek: str,
    model: Path,
    refdb: Path,
    workdir: Path,
    threads: int,
    gpu: bool,
    params: str,
    alignment_mode: str,
    max_records: int = 0,
    on_tick: Any = None,
) -> dict[str, Any]:
    """One shard, end to end: read, call genes, predict 3Di, search, report hits above the floor.

    Returns the shard body defined in this module's docstring. `max_records` bounds how many
    sampled records are read: 0 is unbounded, and anything else marks the result `partial`,
    because a bounded read is a prefix of the object rather than a sample of it.
    """
    from amazebio import profilesearch

    source = next((s for s in corpora.sources_for(shard["release"]) if s.key == shard["key"]), None)
    if source is None:
        raise FoldDetectError(f"{shard['key']} is not a staged source of {shard['release']}")

    workdir.mkdir(parents=True, exist_ok=True)
    for stale in workdir.glob("shard-*"):
        stale.unlink() if stale.is_file() else shutil.rmtree(stale)

    lo, hi = shard["band"]
    read_started = time.monotonic()
    records: list[Any] = []
    for rec in stream_sampled(client, source, lo=lo, hi=hi):
        records.append(rec)
        if max_records and len(records) >= max_records:
            break
        if on_tick is not None and len(records) % 2000 == 0:
            on_tick("read", round(time.monotonic() - read_started, 1), records=len(records))
    read_seconds = time.monotonic() - read_started

    proteins, stats = profilesearch.call_genes(records)
    del records
    faa = workdir / "shard-query.faa"
    genes, residues = write_fasta(proteins, faa)
    del proteins

    search_started = time.monotonic()
    hits: list[dict[str, Any]] = []
    if genes:
        qdb = workdir / "shard-qdb"
        run_step(
            [
                foldseek,
                "createdb",
                str(faa),
                str(qdb),
                "--prostt5-model",
                str(model),
                "--gpu",
                "1" if gpu else "0",
                "--threads",
                str(threads),
            ],
            workdir=workdir,
            label="createdb",
            on_tick=on_tick,
        )
        aln = workdir / "shard-aln"
        run_step(
            [
                foldseek,
                "search",
                str(qdb),
                str(refdb),
                str(aln),
                str(workdir / "shard-tmp"),
                "--alignment-type",
                ALIGNMENT_FLAGS[alignment_mode],
                "--cov-mode",
                "1",
                "-c",
                "0.5",
                "-e",
                "1000",
                *(("--exhaustive-search", "1") if EXHAUSTIVE_SEARCH else ()),
                "--threads",
                str(threads),
            ],
            workdir=workdir,
            label="search",
            on_tick=on_tick,
        )
        tsv = workdir / "shard-hits.tsv"
        run_step(
            [
                foldseek,
                "convertalis",
                str(qdb),
                str(refdb),
                str(aln),
                str(tsv),
                "--format-output",
                FORMAT,
            ],
            workdir=workdir,
            label="convertalis",
            on_tick=on_tick,
        )
        hits = parse_hits(tsv)
    search_seconds = time.monotonic() - search_started

    body = {
        "release": shard["release"],
        "key": shard["key"],
        "component": shard["component"],
        "corpus_component": shard["corpus_component"],
        "band": [lo, hi],
        "params": params,
        "alignment_mode": alignment_mode,
        "gpu": gpu,
        "records": stats["records"],
        "genes": genes,
        "residues": residues,
        "records_without_genes": stats["records_without_genes"],
        "read_seconds": round(read_seconds, 2),
        "search_seconds": round(search_seconds, 2),
        "floor_bits": FLOOR_BITS,
        "hits": hits,
    }
    if max_records:
        body["partial"] = True
        body["records_cap"] = max_records
        body["partial_why"] = (
            "a capped read: the first "
            f"{max_records} sampled records of the object, not a sample of it. A smoke test."
        )
    return body


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def route_for_record(record_id: str, *, component: str, removed: set[str]) -> Route:
    """The survival route for a hit's record.

    A2.2 reads the surviving set *from the manifest* (D-059) rather than re-resolving each
    record, which is the part the manifest is authoritative for. Every record the manifest does
    not remove from a component the policy examined is on Evo's `undetected` route: A1.4 resolved
    all 2.95M of Evo 2's viral records to `unresolved` because not one carries a lineage tag, and
    that is exactly what `undetected` means in `metrics/survival.md` — in scope, the rule reaches
    it, and the mechanism could not see it.

    `conformance_failure` is never returned. `amazebio.apply.route_for` raises rather than
    returning it, because that claim is about a named laboratory's implementation and §7 requires
    A7.1 to establish it with record-level evidence, not a detector to assert it in passing.
    """
    if record_id in removed:
        raise FoldDetectError(
            f"{record_id} is in the manifest's removed set and must not reach a detection row"
        )
    return Route.UNDETECTED if component in SAMPLE_RATES else Route.OUT_OF_SCOPE


def detections_for_manifest(
    shards: list[dict[str, Any]],
    *,
    removed: set[str],
    target_fold: dict[str, str],
    threshold: float,
    registry: str,
    registry_version: str,
) -> tuple[list[Detection], dict[str, Any]]:
    """Accepted detections for one manifest, and what was excluded or skipped.

    One detection per (record, fold) and not per hit: a protein matching eight capsid
    representatives is one surviving capsid fold in that record, not eight. `hits` in the table
    still counts the alignments, which is what `metrics/detections.md` asks of it; the deduplicated
    unit is what `survival` is computed over.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    excluded = 0
    below = 0
    for shard in shards:
        component = shard["corpus_component"]
        for hit in shard["hits"]:
            if hit["bits"] < threshold:
                below += 1
                continue
            fold_id = target_fold.get(hit["target"])
            if fold_id is None:
                raise FoldDetectError(
                    f"{hit['target']} is not in the shipped reference set. The search ran "
                    "against a different reference database than the one this table is being "
                    "attributed with, so its denominator is unknown."
                )
            if hit["record_id"] in removed:
                excluded += 1
                continue
            key = (hit["record_id"], fold_id)
            if key not in best or hit["bits"] > best[key]["bits"]:
                best[key] = {**hit, "component": component, "fold_id": fold_id}

    out: list[Detection] = []
    for (record_id, fold_id), hit in sorted(best.items()):
        out.append(
            Detection(
                family_id=fold_id,
                registry=registry,
                registry_version=registry_version,
                record_id=record_id,
                route=route_for_record(record_id, component=hit["component"], removed=removed),
                element_kind=detect.element_kind_for(hit["component"]),
                detector="foldseek",
                score=hit["bits"],
                threshold=threshold,
            )
        )
    return out, {"excluded_on_removed_records": excluded, "hits_below_threshold": below}


def source_rows(manifest: dict[str, Any], shards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per component of the manifest, searched or not.

    A component this detector does not cover is **listed with a reason**, never omitted — the
    same treatment `metrics/manifests.md` requires of A1.4's own manifests, and for the same
    reason: a table that silently covered part of a release reads as a verdict on all of it.
    """
    by_key = {s["key"]: s for s in shards}
    rows: list[dict[str, Any]] = []
    for src in manifest.get("sources", []):
        key = src.get("key")
        shard = by_key.get(key) if key else None
        component = src.get("corpus_component") or src.get("component", "")
        if shard is None:
            rows.append(
                {
                    "component": src.get("component"),
                    "corpus_component": component,
                    "searched": False,
                    "why": NOT_SEARCHED.get(
                        component, "no shard was produced for this staged object"
                    ),
                    "records_in_source": src.get("records"),
                }
            )
            continue
        lo, hi = shard["band"]
        rows.append(
            {
                "component": src.get("component"),
                "corpus_component": component,
                "searched": True,
                "sample_rate": hi - lo,
                "records_in_source": src.get("records"),
                "records": shard["records"],
                "genes": shard["genes"],
                "residues": shard["residues"],
                "records_without_genes": shard.get("records_without_genes", 0),
                "read_seconds": shard.get("read_seconds"),
                "search_seconds": shard.get("search_seconds"),
            }
        )
    return rows


def build_table(
    *,
    manifest_entry: dict[str, Any],
    shards: list[dict[str, Any]],
    manifest_dir: Path,
    universe: dict[str, Any],
    thresholds: dict[str, Any],
) -> detect.DetectionTable:
    """One per-fold table for one A1.4 manifest."""
    manifest = manifest_entry["manifest"]
    release = manifest["release"]["key"] if isinstance(manifest.get("release"), dict) else None
    release = release or manifest.get("release")
    removed = removed_ids(manifest_dir, manifest)
    names = fold_universe_names(universe)
    declared = thresholds["declared"]

    detections, counts = detections_for_manifest(
        shards,
        removed=removed,
        target_fold=target_to_fold(universe),
        threshold=declared,
        registry="ECOD",
        registry_version=universe["registry_version"],
    )
    rows = detect.build_rows(
        detections,
        universe=names,
        thresholds=dict.fromkeys(names, declared),
    )
    srcs = source_rows(manifest, shards)
    searched = [s for s in srcs if s["searched"]]
    sample = (
        detect.SampleDesign(
            seed=SEED,
            rate=max(s["sample_rate"] for s in searched),
            population=sum(s["records_in_source"] or 0 for s in searched) or None,
            bands=tuple(tuple(s["band"]) for s in shards),
        )
        if searched
        else None
    )
    notes = [
        "The family universe is the three folds DESIGN.md §A2 names, not ECOD's families: the "
        "membership rule — which ECOD families and representatives constitute each fold — ships "
        "as fold-universe.json (D-166, D-169).",
        "No TM-score or LDDT is reported, and none can be: a ProstT5 query database holds 3Di "
        "strings and no C-alpha coordinates (D-167). The evidence is a structural-alphabet "
        "alignment against a reference fold, not a superposition.",
        "The 3Di string is predicted from sequence, so this route is less independent of "
        "sequence than a search over real structures would be (D-167).",
        "The class I fusion glycoprotein fold is this project's own construction — no single "
        "ECOD node means the class — and is the structural coverage gap A2.2 reports (D-166).",
        f"{counts['excluded_on_removed_records']} hits fell on records this reading removes and "
        "are excluded from every count; they are candidate conformance failures for A7.1, which "
        "no detection table may assert.",
        f"{counts['hits_below_threshold']} stored hits sit below the declared threshold. Shards "
        f"keep everything above {FLOOR_BITS:g} bits, so the brackets "
        f"{thresholds['brackets']} can be applied without re-searching.",
    ]
    table = detect.DetectionTable(
        task="A2.2",
        detector="foldseek",
        registry="ECOD",
        registry_version=universe["registry_version"],
        manifest=detect.ManifestRef(
            policy_id=manifest["policy"]["id"],
            release=str(release),
            path=str(manifest_entry["path"]),
            sha256=folds.sha256_of(manifest_entry["path"]),
            removed_records=manifest.get("removed", {}).get("records", 0),
        ),
        sources=srcs,
        sample=sample,
        rows=rows,
        thresholds=thresholds,
        notes=notes,
    )
    detect.check_route_coverage(table)
    return table, detections


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    stage = ap.add_mutually_exclusive_group(required=True)
    stage.add_argument("--plan", action="store_true", help="list the shards the depth asks for")
    stage.add_argument("--search", action="store_true", help="run the resumable per-shard search")
    stage.add_argument("--assemble", action="store_true", help="build the tables from shards")
    ap.add_argument("--reference", type=Path, default=Path("artifacts/a2-2/reference"))
    ap.add_argument("--foldseek", default="foldseek")
    ap.add_argument("--prostt5-model", type=Path, default=Path("data/prostt5"))
    # Scratch lives outside the working tree on purpose (D-103): residues may pass through
    # it, and nothing carrying sequence belongs anywhere a reviewer reads as a result.
    ap.add_argument("--refdb", type=Path, default=Path("/tmp/amazebio-a2-2/refdb/ref"))
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/amazebio-a2-2/work"))
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu", action="store_true", help="require a GPU and refuse a CPU fallback")
    ap.add_argument("--max-shards", type=int, default=None, help="stop after this many shards")
    ap.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="smoke test: read only this many sampled records per shard. The shard is marked "
        "partial and the assembly refuses it.",
    )
    ap.add_argument(
        "--band",
        default=None,
        help="smoke test: override the band as LO:HI, e.g. 0:1 to read a tiny object in full",
    )
    ap.add_argument("--code-commit", default=None, help="provenance where there is no checkout")
    ap.add_argument("--calibration", type=Path, default=Path("artifacts/a2-2/calibration"))
    ap.add_argument("--alignment-mode", default=None, help="defaults to the calibrated choice")
    ap.add_argument("--manifests", type=Path, default=Path("artifacts/a1-4"))
    ap.add_argument("--shards", type=Path, default=Path("artifacts/a2-2/shards"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/a2-2"))
    ap.add_argument("--release", action="append", help="release key; repeatable")
    ap.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    return ap.parse_args(argv)


def do_search(args: Any) -> int:
    """Run every outstanding shard, one at a time, skipping what is already written.

    One shard at a time and published as it finishes, because 24.7 instance-hours exceeds any
    window this account can hold: an instance that dies on shard four must leave shards one to
    three behind it. That is what makes spot safe here, so resumability protects the budget
    rather than competing with it.
    """
    universe_path = args.reference / "fold-universe.json"
    universe = load_fold_universe(universe_path)
    params = params_fingerprint(folds.sha256_of(universe_path))
    thresholds = load_threshold(args.calibration / "threshold.json", mode=args.alignment_mode)
    mode = thresholds["alignment_mode"]

    client = objectstore.client()
    shards = planned_shards(args.release)
    if args.band:
        lo_s, _, hi_s = args.band.partition(":")
        lo, hi = float(lo_s), float(hi_s)
        shards = [
            {**s, "band": [lo, hi], "name": shard_name(s["release"], s["key"], lo, hi)}
            for s in shards
        ]

    already = finished_shards(client, args.s3_uri)
    outstanding = [s for s in shards if s["name"] not in already]
    print(
        f"{len(shards)} shards planned, {len(already)} already written, "
        f"{len(outstanding)} to do; params {params}, mode {mode}"
    )
    if args.max_shards is not None:
        outstanding = outstanding[: args.max_shards]

    local = args.shards
    local.mkdir(parents=True, exist_ok=True)
    # A dict rather than a counter the closure captures: `done` is rebound every iteration, so a
    # heartbeat closing over it reports whatever ruff's B023 warns about rather than the live
    # count. The heartbeat is the only channel the instance has, so it has to be right.
    progress = {"done": 0}
    for shard in outstanding:
        print(f"=== {shard['name']}", flush=True)

        def tick(
            label: str, elapsed: float, *, records: int | None = None, shard: dict[str, Any] = shard
        ) -> None:
            body = {
                "stage": label,
                "shard": shard["name"],
                "elapsed_s": elapsed,
                "shards_done": progress["done"],
                "shards_outstanding": len(outstanding),
                "registry_version": universe["registry_version"],
                "params": params,
            }
            if records is not None:
                body["records_read"] = records
            print(
                f"    {label}: {elapsed}s"
                + (f", {records} records" if records is not None else ""),
                flush=True,
            )
            heartbeat(client, args.s3_uri, "search-progress.json", body)

        tick("starting", 0.0)
        body = search_shard(
            client,
            shard,
            foldseek=args.foldseek,
            model=args.prostt5_model,
            refdb=args.refdb,
            workdir=args.workdir,
            threads=args.threads,
            gpu=args.gpu,
            params=params,
            alignment_mode=mode,
            max_records=args.max_records,
            on_tick=tick,
        )
        body["code_commit"] = args.code_commit
        body["registry_version"] = universe["registry_version"]
        text = json.dumps(body, indent=2, sort_keys=True) + "\n"
        (local / shard["name"]).write_text(text)
        if args.s3_uri:
            bucket, prefix = objectstore.split_uri(args.s3_uri)
            client.put_object(Bucket=bucket, Key=f"{prefix}/{shard['name']}", Body=text.encode())
        progress["done"] += 1
        print(
            f"    records={body['records']} genes={body['genes']} "
            f"residues={body['residues']:,} hits={len(body['hits'])} "
            f"read={body['read_seconds']}s search={body['search_seconds']}s"
            + (" PARTIAL" if body.get("partial") else ""),
            flush=True,
        )
    print(f"{progress['done']} shard(s) written to {local}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.plan:
        shards = planned_shards(args.release)
        universe_path = args.reference / "fold-universe.json"
        fingerprint = (
            params_fingerprint(folds.sha256_of(universe_path))
            if universe_path.exists()
            else "<no reference artefact yet>"
        )
        for s in shards:
            print(f"  {s['name']:62s} {s['corpus_component']:12s} band={s['band']}")
        print(f"{len(shards)} shards at the pre-registered depth; params {fingerprint}")
        return 0

    if args.search:
        return do_search(args)

    from amazebio.repro import run

    universe = load_fold_universe(args.reference / "fold-universe.json")
    thresholds = load_threshold(args.calibration / "threshold.json", mode=args.alignment_mode)
    entries = load_manifests(args.manifests)

    with run("A2.2", seed=SEED, outdir=args.out, allow_dirty=args.allow_dirty, repo=REPO) as m:
        m.parameter("threshold_bits", thresholds["declared"])
        m.parameter("threshold_brackets", thresholds["brackets"])
        m.parameter("alignment_mode", thresholds["alignment_mode"])
        m.parameter("sample_rates", SAMPLE_RATES)
        m.parameter("floor_bits", FLOOR_BITS)
        m.parameter("registry_version", universe["registry_version"])

        written: list[str] = []
        for entry in entries:
            manifest = entry["manifest"]
            release = manifest.get("release")
            release = release["key"] if isinstance(release, dict) else release
            if args.release and release not in args.release:
                continue
            shards = load_shards(args.shards, release=str(release))
            table, detections = build_table(
                manifest_entry=entry,
                shards=shards,
                manifest_dir=args.manifests,
                universe=universe,
                thresholds=thresholds,
            )
            policy_id = manifest["policy"]["id"]
            stem = f"detections-ecod-{policy_id}-{release}"
            path = table.write(args.out / f"{stem}.json")
            m.output_file(path, role="per-fold hit table")
            written.append(path.name)
            if detections:
                jsonl = args.out / f"{stem}.jsonl"
                with jsonl.open("w") as fh:
                    for row in detect.detection_rows(detections, extra={"manifest": policy_id}):
                        fh.write(json.dumps(row) + "\n")
                m.output_file(jsonl, role="record-level detections")
                written.append(jsonl.name)
            surv = table.survival()
            print(
                f"  {stem}: {surv['families_with_a_hit']}/{surv['families_in_universe']} folds, "
                f"{surv['estimate_kind']}"
            )

        index = args.out / "index.json"
        index.write_text(
            json.dumps(
                {
                    "task": "A2.2",
                    "detector": "foldseek",
                    "registry": "ECOD",
                    "registry_version": universe["registry_version"],
                    "tables": sorted(written),
                    "thresholds": thresholds,
                    "sample": {
                        "seed": SEED,
                        "rates": SAMPLE_RATES,
                        "decision_ref": "D-078",
                    },
                },
                indent=2,
            )
            + "\n"
        )
        m.output_file(index, role="index")
        m.note(
            "Fold-level survival from a sample is a lower bound (D-078): the records not read "
            "can only add folds, never remove one."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

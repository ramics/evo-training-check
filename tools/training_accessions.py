#!/usr/bin/env python3
"""Produce the accession list for OpenGenome2's *training* representation — A7.6.

Every Evo 2 figure in this project is measured on the released FASTA, which carries a source
accession. The training representation carries only a bare `text` field: no accession, no
lineage. The two are not the same population — the FASTA holds **304,448 records more** (A7.3) —
so a count over the FASTA describes a superset of what the model was trained on, and says so
only if someone has done the join.

D-262 proved the join is complete: all 2,652,840 distinct training records resolve to the FASTA
by exact sequence digest, one by a `(length, first-48, last-48)` fallback, none unresolved. Then
it lost the output, because the accession list was a scratch file. This tool is that join, as an
artefact instead of a scratch file.

**What it does.** Two streaming passes, neither of which materialises a corpus.

1. The training side: the six `imgvr_untagged` JSONL members, digesting each record's sequence.
   Held as digests, never as sequence (D-103, D-020).
2. The accession side: the staged `imgvr.fasta.gz`, digesting each record's sequence and its
   reverse complement, and keeping the accession of every record whose sequence the training
   side holds.

**Why both orientations.** The two representations are published by different pipelines and
nothing promises a shared strand convention. Testing one orientation and finding 2.65 million
matches would look like success while silently dropping whatever was written the other way, so
the orientation that matched is counted and reported rather than assumed.

**Why a fallback tier.** It makes the degree of correspondence a measurement. An exact-digest
join answers yes or no; a run that reports "all but one exact, one by endpoints" has measured
how literally the sequences were carried across, which is the claim D-262 actually rests on.

**Output.** A sorted `int64` array of `amazebio.imgvr.uvig_join_key` values — packed where the
accession packs, hashed where it does not, so the GVMAG shape is not silently dropped (those are
giant-virus genomes, exactly the records a eukaryote-virus filter is judged on) — plus a JSON
report. Sorted so the downstream restriction is a `searchsorted` rather than a hash of millions
of strings, which is the same choice `tools/evo2_accessions.py` made for the same reason.

    python3 tools/training_accessions.py                     # artifacts/a7-6
    python3 tools/training_accessions.py --max-training 200000 --max-fasta 200000   # smoke
"""

from __future__ import annotations

import argparse
import array
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, imgvr, objectstore, opengenome
from amazebio.repro import run
from amazebio.seqstream import _iter_fasta

TASK = "A7.6"
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "artifacts" / "a7-6"
SEED = 20261028

#: The join's parameters, fixed here and declared to the run manifest before any count is taken.
#: `AGENTS.md`: thresholds and parameters are fixed before results are inspected.
DIGEST = "blake2b-16"
#: Uppercased, with whitespace removed. The FASTA wraps its sequences and the JSON does not, so
#: some normalisation is unavoidable; this is the least of it, and anything more — collapsing
#: ambiguity codes, trimming leading N — would be a judgement about what counts as the same
#: sequence and belongs in a decision entry rather than in a default.
NORMALISE = "uppercase, whitespace removed"
#: The fallback tier, on the triple rather than the sequence.
FALLBACK = "(length, first-48, last-48)"

#: The training representation of the viral component. The FASTA sibling of this prefix is what
#: every other Evo 2 pass reads; this is the one the model consumed.
TRAINING_PREFIX = "json/pretraining_or_both_phases/imgvr_untagged/"
#: The released component, staged. Keyed under the pinned revision like every staged corpus.
FASTA_KEY = (
    "corpora/opengenome2/84d2a7e690c8bb395d1f4868822dfa031ea561c6"
    "/fasta/plasmids_phage/imgvr.fasta.gz"
)

_COMPLEMENT = bytes.maketrans(b"ACGTNacgtn", b"TGCANtgcan")


def digest(sequence: str) -> bytes:
    """The join key for one sequence: a 16-byte BLAKE2b of its normalised bases.

    Sixteen bytes rather than eight. At 2.65 million records an 8-byte digest carries a
    birthday collision probability around 4e-7 — small, but a collision here does not look
    like an error, it looks like a record that was in the training data when it was not, and
    the whole point of this artefact is that someone will cite it.
    """
    return hashlib.blake2b(_normalise(sequence), digest_size=16).digest()


def _normalise(sequence: str) -> bytes:
    return sequence.strip().upper().encode("ascii", "ignore")


def reverse_complement(sequence: str) -> str:
    return _normalise(sequence).translate(_COMPLEMENT)[::-1].decode("ascii")


def fallback_key(sequence: str) -> bytes:
    """The endpoint-and-length key, for a sequence the exact digest does not place."""
    bases = _normalise(sequence)
    return hashlib.blake2b(
        b"%d|%s|%s" % (len(bases), bases[:48], bases[-48:]), digest_size=16
    ).digest()


def training_members(
    *, revision: str, limit: int | None, progress: float
) -> tuple[set[bytes], set[bytes], dict[str, Any]]:
    """Digest every record of the training tree, in both tiers.

    Returns `(exact, fallback, report)`. Streamed through `curl`, not `urllib`: the plain
    reader dies with `BrokenPipeError` part way through a multi-gigabyte HuggingFace transfer,
    and `--retry-all-errors` is what has survived it.
    """
    release = opengenome.RELEASES["opengenome2"]
    blobs = opengenome.fetch_tree(release)
    members = [
        blob
        for blob in blobs
        if blob.path.startswith(TRAINING_PREFIX) and blob.path.endswith(".jsonl.gz")
    ]
    files = sorted(blob.path for blob in members)
    if not files:
        raise SystemExit(f"no training members found under {TRAINING_PREFIX}")
    exact: set[bytes] = set()
    fallback: set[bytes] = set()
    records = 0
    empties = 0
    started = last = time.time()
    for path in files:
        url = opengenome.resolve_url(release, path)
        proc = subprocess.Popen(
            ["curl", "-sSL", "--retry", "6", "--retry-all-errors", url],
            stdout=subprocess.PIPE,
        )
        assert proc.stdout is not None
        try:
            with gzip.open(proc.stdout, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    text = json.loads(line).get("text") or ""
                    if not text.strip():
                        empties += 1
                        continue
                    exact.add(digest(text))
                    fallback.add(fallback_key(text))
                    records += 1
                    if progress and time.time() - last >= progress:
                        last = time.time()
                        print(
                            f"[training] {records:,} records  {len(exact):,} distinct  "
                            f"{time.time() - started:,.0f}s  {Path(path).name}",
                            flush=True,
                        )
                    if limit is not None and records >= limit:
                        break
        finally:
            proc.stdout.close()
            proc.wait()
        if limit is not None and records >= limit:
            break
    report = {
        "files": [Path(p).name for p in files],
        "bytes_published": sum(blob.size for blob in members),
        "records_read": records,
        "distinct_sequences": len(exact),
        "records_with_no_sequence": empties,
        "seconds": round(time.time() - started, 1),
    }
    print(
        f"[training] {records:,} records, {len(exact):,} distinct sequences "
        f"in {report['seconds']:,.0f}s",
        flush=True,
    )
    return exact, fallback, report


def matching_accessions(
    exact: set[bytes],
    fallback: set[bytes],
    *,
    limit: int | None,
    progress: float,
) -> tuple[array.array, dict[str, Any], list[str]]:
    """Stream the released FASTA, keeping the accession of every record the training side holds.

    The sequence of a record that does not match is discarded as it passes, which is the same
    contract every other reader in this project keeps: residues are never serialised.
    """
    client = objectstore.client()
    size = client.head_object(Bucket=corpora.BUCKET, Key=FASTA_KEY)["ContentLength"]
    # The same reader the census used over this exact object, eight times concurrently: a
    # seekable ranged object wrapped so small reads do not become small GETs. A gzip
    # decompressor asks for a few kilobytes at a time, and unbuffered that is one HTTP round
    # trip per block -- measured in-region at 3.9 MB/s against 128 MB/s buffered.
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=FASTA_KEY,
        size=size,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,}: {exc}", file=sys.stderr
        ),
    )
    from amazebio.uniref import GunzipStream

    reader = GunzipStream(obj.buffered())
    keys = array.array("q")
    hit_forward = hit_reverse = hit_fallback = 0
    seen = 0
    unparsable: list[str] = []
    gvmag: set[str] = set()
    started = last = time.time()
    for record in _iter_fasta(reader, component="viral", keep=lambda _: True, chunk=8 << 20):
        seen += 1
        tier = None
        if digest(record.sequence) in exact:
            tier = "forward"
            hit_forward += 1
        elif digest(reverse_complement(record.sequence)) in exact:
            tier = "reverse"
            hit_reverse += 1
        elif fallback_key(record.sequence) in fallback:
            tier = "fallback"
            hit_fallback += 1
        if tier is not None:
            try:
                key = imgvr.uvig_join_key(record.id)
            except ValueError:
                # A header this audit cannot read as an accession is a training record that
                # cannot be named. Counted and sampled, never skipped silently.
                if len(unparsable) < 32:
                    unparsable.append(record.id[:64])
                continue
            keys.append(key)
            if key < 0:
                gvmag.add(record.id)
        if progress and time.time() - last >= progress:
            last = time.time()
            print(
                f"[fasta] {seen:,} records  {len(keys):,} in training  "
                f"{time.time() - started:,.0f}s",
                flush=True,
            )
        if limit is not None and seen >= limit:
            break
    ok, n_acc, n_keys = imgvr.collision_free(sorted(gvmag))
    report = {
        "fasta_key": FASTA_KEY,
        "fasta_bytes": size,
        "records_read": seen,
        "in_training": len(keys),
        "absent_from_training": seen - len(keys) - len(unparsable),
        "matched_forward": hit_forward,
        "matched_reverse_complement": hit_reverse,
        "matched_by_fallback": hit_fallback,
        "unparsable_headers": len(unparsable),
        "unparsable_examples": unparsable,
        "gvmag_accessions": len(gvmag),
        "gvmag_keys_collision_free": ok,
        "gvmag_distinct_accessions": n_acc,
        "gvmag_distinct_keys": n_keys,
        "seconds": round(time.time() - started, 1),
    }
    print(
        f"[fasta] {seen:,} records read, {len(keys):,} in training "
        f"({hit_forward:,} forward, {hit_reverse:,} reverse, {hit_fallback:,} fallback) "
        f"in {report['seconds']:,.0f}s",
        flush=True,
    )
    return keys, report, unparsable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=OUTDIR)
    ap.add_argument(
        "--max-training", type=int, help="smoke run: stop after this many training records"
    )
    ap.add_argument("--max-fasta", type=int, help="smoke run: stop after this many FASTA records")
    ap.add_argument("--progress", type=float, default=60.0, help="seconds between heartbeats")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    smoke = args.max_training is not None or args.max_fasta is not None
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    durable = None if smoke else objectstore.durable_results("a7-6")
    if smoke:
        print(
            "not publishing: --max-training/--max-fasta make this a smoke run, and a partial "
            "join would be cited as the membership list",
            file=sys.stderr,
        )

    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        durable=durable,
        durable_exempt=None if durable else "smoke run: the join is partial",
    ) as m:
        # Declared before any count exists (AGENTS.md).
        m.parameter("digest", DIGEST)
        m.parameter("normalisation", NORMALISE)
        m.parameter("orientations", ["forward", "reverse_complement"])
        m.parameter("fallback_tier", FALLBACK)
        m.parameter("training_prefix", TRAINING_PREFIX)
        m.parameter("fasta_key", FASTA_KEY)
        m.parameter("decision_ref", "D-262")

        release = opengenome.RELEASES["opengenome2"]
        exact, fallback, training_report = training_members(
            revision=release.revision, limit=args.max_training, progress=args.progress
        )
        keys, fasta_report, _ = matching_accessions(
            exact, fallback, limit=args.max_fasta, progress=args.progress
        )

        import numpy as np

        packed = np.frombuffer(keys, dtype=np.int64).copy()
        packed.sort()
        unique = np.unique(packed)
        path = out / "training-accessions.npy"
        np.save(path, unique)
        m.output_file(path, role="the training-membership accession list, sorted")

        report = {
            "task": TASK,
            "what_this_is": (
                "IMG/VR accessions whose sequence is present in OpenGenome2's training "
                "representation, as join keys (amazebio.imgvr.uvig_join_key), sorted. "
                "Restricting a FASTA-measured figure to the trained population is a "
                "searchsorted over this array."
            ),
            "training": training_report,
            "fasta": fasta_report,
            "accessions": {
                "kept": int(packed.size),
                "distinct": int(unique.size),
                "duplicate_keys": int(packed.size - unique.size),
            },
            "reconciliation_with_d262": {
                "d262_distinct_training_records": 2652840,
                "d262_distinct_accessions": 2653047,
                "d262_absent_from_training": 304448,
                "d262_needed_fallback": 1,
                "measured_distinct_training_records": training_report["distinct_sequences"],
                "measured_distinct_accessions": int(unique.size),
                "measured_absent_from_training": fasta_report["absent_from_training"],
                "measured_needed_fallback": fasta_report["matched_by_fallback"],
            },
            "smoke": smoke,
        }
        report_path = out / "training-accessions.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        m.output_file(report_path, role="report")
        m.note(
            "The released FASTA is a superset of the training representation (A7.3): a figure "
            "measured on it covers records the model never trained on until restricted by this "
            "list. The list says nothing about filter status — the released component carries "
            "an accession and no lineage, so no published rule can be executed against it "
            "(D-049), and that limitation is not one a join can remove."
        )

        r = report["reconciliation_with_d262"]
        agree = (
            r["measured_distinct_accessions"] == r["d262_distinct_accessions"]
            and r["measured_absent_from_training"] == r["d262_absent_from_training"]
        )
        print(
            f"\n{'reconciles with' if agree else 'DISAGREES with'} D-262: "
            f"{r['measured_distinct_accessions']:,} distinct accessions "
            f"(D-262: {r['d262_distinct_accessions']:,}), "
            f"{r['measured_absent_from_training']:,} absent "
            f"(D-262: {r['d262_absent_from_training']:,})",
            flush=True,
        )
        if not agree and not smoke:
            print(
                "  A disagreement is a finding, not a tuning parameter (AGENTS.md). Record it.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

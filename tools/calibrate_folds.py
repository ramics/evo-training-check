#!/usr/bin/env python3
"""Fix A2.2's bit-score threshold against decoys, before any corpus hit is seen.

    pixi run -e dev python tools/calibrate_folds.py --stage queries --out artifacts/a2-2/calib
    pixi run -e foldseek bash <the printed foldseek commands>
    pixi run -e dev python tools/calibrate_folds.py --stage score --out artifacts/a2-2/calib

D-167 fixed everything about the score except its value: the corpus is the query, the 141
reference structures are the target, the coverage floor is on the target at `--cov-mode 1 -c
0.5`, and the score is the bit score. What is open is where to cut it, and one deferred option —
`--alignment-type 0` (3Di only) against foldseek's default 3Di+amino-acid scoring, which changes
the score distribution and therefore the cut. Both are settled here, from decoys, and
`amazebio.repro` refuses a threshold declared after an output exists so the order is enforced
rather than promised.

**The decoys are the design, and the sharpest ones are already in hand.** A shuffled sequence is
not a real test: three shuffled reference domains returned no hit at all at `-e 1000` during the
probe, so a threshold calibrated on composition-matched noise would be calibrated on nothing.
The decoys that matter are *real proteins that share the fold and are not viral*, and D-166 and
D-169 enumerated exactly those while deciding what to exclude — the cellular families of the
capsid H-group (nucleoplasmin, peptide-N-glycanase, Cu(2+) monooxygenase, TGF-beta propeptide)
and the host RNAi polymerase families that share the viral RdRp fold. Those are the false
positives this detector can actually make, so they set the cut. Four classes are measured:

| class | what it is | what it bounds |
|---|---|---|
| `near_fold_nonviral` | excluded cellular capsid + host RNAi | the binding rate: fold, not viral |
| `unrelated_fold` | ECOD X-groups disjoint from the universe's | the ordinary false-positive rate |
| `shuffled` | the positives' sequences, shuffled at a pinned seed | the composition-matched null |
| `positive` | held-out non-representative fold-family domains | sensitivity at the chosen cut |

**Held-out means held out.** A positive sharing a PDB entry with any reference structure is
dropped, not kept: the same deposition re-scored against itself measures nothing, and the
inflation would land in the sensitivity figure the write-up quotes. The count dropped is
reported.

**The queries take the corpus's path, not a shortcut.** Every query here is an amino-acid
sequence that goes through ProstT5 3Di prediction and then the search, exactly as a called gene
from the surviving corpus will. Calibrating on real structures instead would measure a different
instrument: D-167 records that the 3Di string is *predicted from sequence*, and the prediction
error belongs inside the threshold, not outside it.

Sequences come from RCSB's per-entry FASTA cut to ECOD's `seqid_range`, which indexes the SEQRES
sequence 1-based — verified against the structure-derived sequence of `e1hx6A1`. That is a few
kilobytes per entry rather than a few hundred, which is what makes a 1,600-query calibration
affordable at all.

No sequence reaches an artefact (D-103): queries live in the scratch directory, and the
calibration artefact carries counts, scores and the chosen threshold.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
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

#: RCSB's per-entry FASTA. One request per PDB entry, text only.
RCSB_FASTA = "https://www.rcsb.org/fasta/entry/{pdb}"

#: The pinned sampling seed, shared with A2.1's sampler (D-078) so that nothing in this project
#: draws a sample from an undeclared seed.
SEED = 20261015

#: Per-class query budget. 400 is chosen for what a *zero* means: with 400 decoys and no hit
#: above a threshold, the 95% upper bound on the per-query false-positive rate is about 0.75%,
#: which is tight enough to state a 1% rate honestly. Larger buys little and every query costs
#: 3Di prediction, which D-163 measured at 173x a profile search.
PER_CLASS = 400

#: Proteins shorter than this are dropped from every class alike. A 30-residue fragment cannot
#: carry a fold and would depress the positive rate for a reason that has nothing to do with the
#: threshold.
MIN_LENGTH = 30

#: Candidate thresholds the sweep reports, in bits. The declared value and its two bracketing
#: values are chosen from this grid, which `metrics/survival.md` requires to be fixed at the same
#: time as the headline value.
#:
#: **The grid was extended upward once, after the first run, and the declared value did not
#: move.** The rule — the lowest grid value whose binding-class false-positive rate is at or
#: below :data:`TARGET_FPR` — and the target itself were both fixed beforehand and are unchanged.
#: The first grid stopped at 500, which is where the rule's answer fell, so the declared value
#: had no upper neighbour and `metrics/survival.md`'s requirement of *two* bracketing values could
#: not be met. Extending only above 500 cannot change which value the rule selects: 500 already
#: satisfied the target and nothing was inserted below it. So this is the declared procedure
#: being completed, not a threshold re-picked after seeing results — the distinction AGENTS.md
#: cares about, and the reason the extension is recorded here rather than done quietly.
GRID = (
    20,
    30,
    40,
    50,
    60,
    70,
    80,
    90,
    100,
    120,
    140,
    160,
    180,
    200,
    250,
    300,
    400,
    500,
    600,
    700,
    800,
)

#: The false-positive rate the declared threshold is chosen at, on the binding decoy class.
#: Declared here, before any sweep is run.
TARGET_FPR = 0.01

#: The two alignment modes compared. Named by foldseek's own flag value.
ALIGNMENT_MODES = {"3di_aa": "2", "3di_only": "0"}

#: How the deferred mode choice is made. **Stated after seeing the sweep, and said so plainly:**
#: D-167 deferred the 3Di-only option "to the threshold calibration" without fixing a rule, so
#: unlike the threshold itself this one was not pre-registered. It is recorded rather than
#: dressed up as a prior commitment. What makes it safe to apply anyway is the margin: both modes
#: hold the same false-positive target at the same cut, and sensitivity differs by a factor of
#: five, so no defensible rule chooses otherwise.
ALIGNMENT_MODE_RULE = (
    "among modes whose declared threshold holds the target false-positive rate on the binding "
    "decoy class, take the one with the higher true-positive rate at that threshold"
)

#: The calibration searches exhaustively, because the pass does — see
#: `tools/detect_folds.py`'s EXHAUSTIVE_SEARCH for why the prefilter cannot be used against a
#: 141-structure target database. The threshold has to be measured under the geometry it will be
#: applied under: the prefilter dropped about 7% of rows here and ~100% on a 77-query shard, so
#: calibrating with it and searching without it would put the cut in the wrong place in a way no
#: later check would catch.
EXHAUSTIVE_SEARCH = True

FETCH_PAUSE_S = 0.1
FETCH_ATTEMPTS = 4

#: One span of ECOD's `seqid_range`, which indexes SEQRES and carries no insertion codes.
SPAN = re.compile(r"^(?P<lo>-?\d+)-(?P<hi>-?\d+)$")


class CalibrationError(RuntimeError):
    """Raised when the calibration cannot be run as specified."""


# --------------------------------------------------------------------------------------
# Selecting the query classes
# --------------------------------------------------------------------------------------


def fold_x_groups(path: Path) -> set[str]:
    """The X-groups the fold universe occupies, so `unrelated_fold` can avoid all of them.

    X-group rather than family: a domain from the same X-group as a reference fold is a near
    neighbour by construction, and putting it in the *unrelated* class would make that class
    measure the same thing as `near_fold_nonviral` while being labelled as measuring something
    else.
    """
    out: set[str] = set()
    for row in folds.iter_domains(path):
        if folds.fold_for_family(row["f_id"]) is not None:
            out.add(row["f_id"].split(".")[0])
    return out


def select_queries(path: Path, *, per_class: int = PER_CLASS) -> dict[str, list[dict[str, str]]]:
    """Choose the positive and decoy domains, deterministically from :data:`SEED`.

    One pass over the release collects every candidate; the sample is then drawn with a seeded
    RNG. Reservoir sampling would avoid holding the candidates, but the candidate sets here are
    tens of thousands of rows of five short fields, and an explicit sort before sampling is what
    makes the draw reproducible independently of the order the file happens to be in.
    """
    excluded_near = (
        set(folds.EXCLUDED_CELLULAR_CAPSID)
        | set(folds.EXCLUDED_UNNAMED_CAPSID)
        | set(folds.EXCLUDED_HOST_RNAI)
    )
    x_groups = fold_x_groups(path)

    reference_entries = {d.pdb for d in folds.reference_domains(path, verify=False)}
    reference_ids = {d.domain_id for d in folds.reference_domains(path, verify=False)}

    pools: dict[str, list[dict[str, str]]] = {
        "positive": [],
        "near_fold_nonviral": [],
        "unrelated_fold": [],
    }
    held_out_dropped = 0

    for row in folds.iter_domains(path):
        if row["valid_structure"] != "True" or not row["pdb"].strip():
            continue
        if not row["seqid_range"].strip():
            continue
        item = {
            "domain_id": row["ecod_domain_id"],
            "f_id": row["f_id"],
            "f_name": row["f_name"],
            "pdb": row["pdb"].strip().lower(),
            "chain": row["chain"].strip(),
            "seqid_range": row["seqid_range"].strip(),
        }
        fold = folds.fold_for_family(row["f_id"])
        if fold is not None:
            if item["domain_id"] in reference_ids:
                continue
            # Held out means held out: the same deposition re-scored against itself is not
            # evidence of sensitivity.
            if item["pdb"] in reference_entries:
                held_out_dropped += 1
                continue
            pools["positive"].append({**item, "fold_id": fold.fold_id})
        elif row["f_id"] in excluded_near:
            pools["near_fold_nonviral"].append({**item, "fold_id": "none"})
        elif row["f_id"].split(".")[0] not in x_groups:
            pools["unrelated_fold"].append({**item, "fold_id": "none"})

    rng = random.Random(SEED)
    chosen: dict[str, list[dict[str, str]]] = {}
    for name, pool in pools.items():
        pool.sort(key=lambda d: d["domain_id"])
        chosen[name] = (
            sorted(rng.sample(pool, per_class), key=lambda d: d["domain_id"])
            if len(pool) > per_class
            else pool
        )
    chosen["_meta"] = [  # type: ignore[assignment]
        {
            "held_out_dropped_sharing_a_reference_entry": str(held_out_dropped),
            "pool_sizes": json.dumps({k: len(v) for k, v in pools.items()}),
        }
    ]
    return chosen


# --------------------------------------------------------------------------------------
# Sequences
# --------------------------------------------------------------------------------------


def entry_chains(pdb: str, cache: Path) -> dict[str, str]:
    """Every chain's SEQRES sequence for one PDB entry, from RCSB's FASTA.

    RCSB groups identical chains into one record — `>1HX6_1|Chains A, B, C|...` — so the header
    is expanded to one key per chain id. Both `Chain X` and `Chains X, Y` appear.

    **Both the label id and the author id are registered**, because ECOD names the author id and
    RCSB prints the label id first: poliovirus 1HXS reads `Chain D[auth 4]` where ECOD's domain
    is `e1hxs11` on chain `4`. Keying on the label alone silently dropped 269 of 1,600 staged
    queries, and the loss was not random — it fell on the multi-chain picornavirus and rhinovirus
    capsid depositions, which is to say on the positive class for the largest of the three folds.
    A sensitivity figure measured with those missing would have understated exactly the fold the
    audit cares most about.
    """
    dest = cache / f"{pdb}.fasta"
    if not (dest.exists() and dest.stat().st_size > 0):
        last: Exception | None = None
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                url = RCSB_FASTA.format(pdb=pdb.upper())
                with urllib.request.urlopen(url, timeout=60) as resp:
                    body = resp.read().decode()
                if not body.startswith(">"):
                    raise CalibrationError(f"{pdb}: RCSB returned no FASTA")
                dest.write_text(body)
                break
            except (urllib.error.URLError, OSError, CalibrationError) as exc:
                last = exc
                if attempt < FETCH_ATTEMPTS:
                    time.sleep(attempt * 2)
        else:
            raise CalibrationError(f"{pdb}: FASTA fetch failed: {last}")
        time.sleep(FETCH_PAUSE_S)

    out: dict[str, str] = {}
    header: str | None = None
    parts: list[str] = []

    def flush() -> None:
        if header is None:
            return
        seq = "".join(parts)
        fields = header.split("|")
        if len(fields) < 2:
            return
        label = fields[1]
        if not label.startswith("Chain"):
            return
        ids = label.split(None, 1)[1] if " " in label else ""
        for raw in ids.split(","):
            token = raw.strip()
            if not token:
                continue
            label, _, bracket = token.partition("[")
            for cid in (label.strip(), bracket.replace("auth", "").strip(" ]")):
                if cid:
                    out.setdefault(cid, seq)

    with dest.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith(">"):
                flush()
                header, parts = line[1:], []
            else:
                parts.append(line.strip())
    flush()
    return out


def domain_sequence(item: dict[str, str], cache: Path) -> str:
    """Cut one domain's sequence out of its chain using ECOD's `seqid_range`.

    `seqid_range` is 1-based into SEQRES and can be multi-segment, mirroring `pdb_range`.
    Verified against the structure-derived sequence of `e1hx6A1`: `A:14-243` of 1HX6 chain A is
    the 230 residues the cut structure holds.
    """
    chains = entry_chains(item["pdb"], cache)
    pieces: list[str] = []
    for raw in item["seqid_range"].split(","):
        seg = raw.strip()
        if ":" not in seg:
            raise CalibrationError(f"{item['domain_id']}: unparseable seqid_range {seg!r}")
        cid, span = seg.split(":", 1)
        seq = chains.get(cid.strip())
        if seq is None:
            raise CalibrationError(f"{item['domain_id']}: entry has no chain {cid!r}")
        # A regex, not `partition("-")`: ECOD's author-derived numbering can start below 1, so
        # `-5-99` is a real span and splitting on the first hyphen reads its low bound as empty.
        m = SPAN.match(span.strip())
        if m is None:
            raise CalibrationError(f"{item['domain_id']}: unparseable seqid span {span!r}")
        lo, hi = int(m["lo"]), int(m["hi"])
        if lo > hi:
            lo, hi = hi, lo
        pieces.append(seq[max(lo - 1, 0) : hi])
    out = "".join(pieces)
    if not out:
        raise CalibrationError(f"{item['domain_id']}: seqid_range selected no residues")
    return out


def shuffle_of(seq: str, domain_id: str) -> str:
    """A composition-matched shuffle, seeded per domain so the decoy is reproducible.

    Seeded from the domain id rather than from a running RNG so that re-running the stage, or
    running it for a subset, produces the identical decoy for a given domain.
    """
    rng = random.Random(f"{SEED}:{domain_id}")
    chars = list(seq)
    rng.shuffle(chars)
    return "".join(chars)


def stage_queries(
    selection: dict[str, list[dict[str, str]]], *, cache: Path, out_fasta: Path
) -> dict[str, Any]:
    """Write every class's queries to one FASTA, named `<class>|<domain_id>`.

    One FASTA, not four: 3Di prediction is the whole cost of this task, and `createdb` over one
    file predicts each query once for both alignment modes to search afterwards.
    """
    cache.mkdir(parents=True, exist_ok=True)
    out_fasta.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = collections.Counter()
    residues: dict[str, int] = collections.Counter()
    dropped: list[dict[str, str]] = []
    labels: dict[str, dict[str, str]] = {}

    with out_fasta.open("w") as fh:
        for cls in ("positive", "near_fold_nonviral", "unrelated_fold"):
            for item in selection[cls]:
                try:
                    seq = domain_sequence(item, cache)
                except (CalibrationError, OSError) as exc:
                    dropped.append({"domain_id": item["domain_id"], "class": cls, "why": str(exc)})
                    continue
                if len(seq) < MIN_LENGTH:
                    dropped.append(
                        {
                            "domain_id": item["domain_id"],
                            "class": cls,
                            "why": f"sequence is {len(seq)} residues, below {MIN_LENGTH}",
                        }
                    )
                    continue
                name = f"{cls}|{item['domain_id']}"
                fh.write(f">{name}\n{seq}\n")
                labels[name] = {**item, "class": cls}
                counts[cls] += 1
                residues[cls] += len(seq)
                if cls == "positive":
                    sname = f"shuffled|{item['domain_id']}"
                    sseq = shuffle_of(seq, item["domain_id"])
                    fh.write(f">{sname}\n{sseq}\n")
                    labels[sname] = {**item, "class": "shuffled", "fold_id": "none"}
                    counts["shuffled"] += 1
                    residues["shuffled"] += len(sseq)

    if not counts:
        raise CalibrationError("no queries were staged")
    return {
        "counts": dict(counts),
        "residues": dict(residues),
        "dropped": dropped,
        "labels": labels,
        "fasta": str(out_fasta),
        "fasta_sha256": hashlib.sha256(out_fasta.read_bytes()).hexdigest(),
    }


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------

#: The columns the search is asked for, in this order.
FORMAT = "query,target,bits,evalue,fident,alnlen,qlen,tlen,tcov"


def read_hits(path: Path) -> list[dict[str, Any]]:
    """Read one foldseek result table."""
    cols = FORMAT.split(",")
    out: list[dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != len(cols):
                continue
            row = dict(zip(cols, fields, strict=True))
            row["bits"] = float(row["bits"])
            row["evalue"] = float(row["evalue"])
            row["tcov"] = float(row["tcov"])
            out.append(row)
    return out


def sweep(
    hits: list[dict[str, Any]],
    labels: dict[str, dict[str, str]],
    counts: dict[str, int],
    *,
    grid: tuple[int, ...] = GRID,
) -> list[dict[str, Any]]:
    """Per-query detection rate for each class at each candidate threshold.

    A query counts as *detected* at a threshold when at least one of its hits reaches it. That is
    the right unit because it is what a detection table records: a surviving record either
    carries the fold or it does not, and a protein matching eight capsid representatives is one
    detection, not eight. Counting hits instead would let one promiscuous query dominate the
    false-positive rate.
    """
    by_query: dict[str, float] = {}
    for h in hits:
        q = h["query"]
        if h["bits"] > by_query.get(q, float("-inf")):
            by_query[q] = h["bits"]

    best_by_class: dict[str, list[float]] = collections.defaultdict(list)
    for q, best in by_query.items():
        label = labels.get(q)
        if label is None:
            continue
        best_by_class[label["class"]].append(best)

    rows: list[dict[str, Any]] = []
    for t in grid:
        row: dict[str, Any] = {"bits": t}
        for cls, n in sorted(counts.items()):
            detected = sum(1 for b in best_by_class.get(cls, []) if b >= t)
            row[cls] = {
                "detected": detected,
                "queries": n,
                "rate": (detected / n) if n else None,
            }
        rows.append(row)
    return rows


def choose_threshold(
    rows: list[dict[str, Any]], *, binding: str = "near_fold_nonviral", target: float = TARGET_FPR
) -> dict[str, Any]:
    """The lowest grid value whose binding-class false-positive rate is at or below `target`.

    Lowest rather than highest: the threshold has to hold the false-positive rate, and among
    values that do, the most sensitive one is the one that finds the most surviving folds. The
    two bracketing values are the grid neighbours, fixed here in the same call so that no later
    step can pick them after seeing a result (`metrics/survival.md` section 2).
    """
    ok = [r for r in rows if (r.get(binding, {}).get("rate") or 0.0) <= target]
    if not ok:
        raise CalibrationError(
            f"no grid value holds {binding} at or below {target}; the grid is too low"
        )
    chosen = min(ok, key=lambda r: r["bits"])
    grid = [r["bits"] for r in rows]
    i = grid.index(chosen["bits"])
    return {
        "declared_bits": chosen["bits"],
        "brackets": [grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]],
        "binding_class": binding,
        "target_fpr": target,
        "realized": {k: v for k, v in chosen.items() if k != "bits"},
    }


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def choose_alignment_mode(modes: dict[str, Any]) -> str:
    """Apply :data:`ALIGNMENT_MODE_RULE` across the measured modes.

    Ties break on the mode name so the choice is deterministic rather than dict-order dependent.
    """
    scored = []
    for name, m in modes.items():
        realized = m["threshold"]["realized"]
        tpr = realized.get("positive", {}).get("rate")
        scored.append((tpr if tpr is not None else -1.0, name))
    if not scored:
        raise CalibrationError("no modes were measured, so none can be declared")
    best = max(scored, key=lambda pair: (pair[0], pair[1]))
    return best[1]


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("queries", "score"), required=True)
    ap.add_argument("--ecod", type=Path, default=Path("data/ecod/ecod.v295.2.domains.txt"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/a2-2/calibration"))
    ap.add_argument("--scratch", type=Path, default=Path("/tmp/amazebio-a2-2/calibration"))
    ap.add_argument("--refdb", type=Path, default=Path("/tmp/amazebio-a2-2/refdb/ref"))
    ap.add_argument("--per-class", type=int, default=PER_CLASS)
    ap.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.scratch.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    fasta = args.scratch / "queries.fasta"
    staged_json = args.scratch / "staged.json"

    if args.stage == "queries":
        selection = select_queries(args.ecod, per_class=args.per_class)
        meta = selection.pop("_meta")[0]  # type: ignore[index]
        for cls, items in selection.items():
            print(f"  {cls:20s} selected {len(items)}")
        print(f"  pools: {meta['pool_sizes']}")
        print(
            "  held out, sharing a reference entry: "
            f"{meta['held_out_dropped_sharing_a_reference_entry']}"
        )
        staged = stage_queries(selection, cache=args.scratch / "rcsb-fasta", out_fasta=fasta)
        staged["selection_meta"] = meta
        staged_json.write_text(json.dumps(staged, indent=2) + "\n")
        total = sum(staged["counts"].values())
        print(f"\nstaged {total} queries, {sum(staged['residues'].values()):,} residues")
        if staged["dropped"]:
            print(f"dropped {len(staged['dropped'])} (first few):")
            for d in staged["dropped"][:5]:
                print(f"    {d['domain_id']} ({d['class']}): {d['why']}")
        qdb = args.scratch / "qdb"
        print("\nnow, in the foldseek environment:")
        print(
            f"  pixi run -e foldseek foldseek createdb {fasta} {qdb} "
            f"--prostt5-model data/prostt5 --threads 4"
        )
        for name, flag in ALIGNMENT_MODES.items():
            res = args.scratch / f"aln-{name}"
            print(
                f"  pixi run -e foldseek foldseek search {qdb} {args.refdb} {res} "
                f"{args.scratch / ('tmp-' + name)} --alignment-type {flag} "
                f"--cov-mode 1 -c 0.5 -e 1000 --threads 4"
            )
            print(
                f"  pixi run -e foldseek foldseek convertalis {qdb} {args.refdb} {res} "
                f"{args.scratch / (name + '.tsv')} --format-output {FORMAT}"
            )
        return 0

    # --stage score
    if not staged_json.exists():
        print(f"missing {staged_json}; run --stage queries first", file=sys.stderr)
        return 2
    staged = json.loads(staged_json.read_text())
    labels = staged["labels"]
    counts = staged["counts"]

    tables = {}
    for name in ALIGNMENT_MODES:
        tsv = args.scratch / f"{name}.tsv"
        if not tsv.exists():
            print(f"missing {tsv}; run the printed foldseek commands first", file=sys.stderr)
            return 2
        tables[name] = tsv

    with run("A2.2", seed=SEED, outdir=args.out, allow_dirty=args.allow_dirty) as manifest:
        manifest.parameter("target_fpr", TARGET_FPR)
        manifest.parameter("binding_decoy_class", "near_fold_nonviral")
        manifest.parameter("grid_bits", list(GRID))
        manifest.parameter("per_class_queries", args.per_class)
        manifest.parameter("cov_mode", 1)
        manifest.parameter("min_target_coverage", 0.5)
        manifest.parameter("exhaustive_search", EXHAUSTIVE_SEARCH)
        manifest.parameter("queries_sha256", staged["fasta_sha256"])
        manifest.parameter("ecod_version", folds.ECOD_V295_2.version)

        modes: dict[str, Any] = {}
        for name, tsv in tables.items():
            hits = read_hits(manifest.input_file(tsv, role=f"hits_{name}"))
            rows = sweep(hits, labels, counts)
            modes[name] = {
                "hits": len(hits),
                "queries_with_a_hit": len({h["query"] for h in hits}),
                "sweep": rows,
                "threshold": choose_threshold(rows),
            }

        declared_mode = choose_alignment_mode(modes)
        manifest.parameter("alignment_mode_rule", ALIGNMENT_MODE_RULE)

        body = {
            "task": "A2.2",
            "detector": "foldseek",
            "registry": "ECOD",
            "registry_version": folds.ECOD_V295_2.version,
            "decision": "D-171",
            "declared_alignment_mode": declared_mode,
            "alignment_mode_rule": ALIGNMENT_MODE_RULE,
            "geometry": {
                "query": "corpus protein sequence, 3Di predicted by ProstT5",
                "target": "the 141 pinned reference structures",
                "cov_mode": 1,
                "min_target_coverage": 0.5,
                "exhaustive_search": EXHAUSTIVE_SEARCH,
                "score": "bit score",
                "unavailable": ["alntmscore", "qtmscore", "ttmscore", "lddt"],
            },
            "queries": {"counts": counts, "residues": staged["residues"]},
            "selection_meta": staged.get("selection_meta", {}),
            "dropped": staged["dropped"],
            "modes": modes,
        }
        out = args.out / "threshold.json"
        out.write_text(json.dumps(body, indent=2) + "\n")
        manifest.output_file(out, role="threshold")

    for name, m in modes.items():
        t = m["threshold"]
        print(f"\n{name}: declared {t['declared_bits']} bits, brackets {t['brackets']}")
        for cls, v in sorted(t["realized"].items()):
            if isinstance(v, dict):
                rate = v["rate"]
                print(
                    f"    {cls:20s} {v['detected']:4d}/{v['queries']:4d}"
                    f"  {'' if rate is None else f'{rate:6.3f}'}"
                )
    print(f"\nwrote {args.out / 'threshold.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

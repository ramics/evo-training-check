"""B4.1 — score every in-scope assay with the parameter-free baseline.

§B4 makes this baseline load-bearing: it is what separates "the assay is intrinsically hard"
from "this model's failure is attributable to its training data". D-229 fixes the method as
RSALOR, integrated from the authors' own implementation rather than reimplemented, with its
defaults recorded there before any score existed.

Three things here are integration risks rather than mechanics, and each is handled explicitly
because a baseline that is quietly wrong is worse than none at all.

**The sign.** RSALOR is written so that large positive values mean *disruptive*. A deep
mutational scan's fitness is the other way up, and ProteinGym's Spearman is computed with the
predictor oriented so that higher means fitter. So the score is negated, and the orientation is
checked against the benchmark's own published column rather than asserted.

**The offset.** ProteinGym's alignments are trimmed to a range of the target protein, stated per
assay as `MSA_start`. The benchmark's variants are numbered on the full protein. A mutation is
therefore translated into alignment coordinates, and a variant whose position falls outside the
aligned range is reported as unscored rather than silently dropped — an assay losing half its
variants to an off-by-one would otherwise show up only as a weak correlation.

**The reference.** Every assay is compared to ProteinGym's published RSALOR column. The verdict
comes from :mod:`amazebio.reference`, the same machinery B1.2 uses on the language models, so
"the baseline reproduces the published one" is a measured interval rather than an impression.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import objectstore, proteingym, reference, repro  # noqa: E402
from amazebio.repro import run  # noqa: E402

TASK = "B4.1"
SEED = 20261020
CANONICAL_OUT = REPO / "artifacts" / "b4-1"

DATA = REPO / "data" / "proteingym" / "v1.3"
REFERENCE = DATA / "DMS_substitutions.csv"
ASSAY_ARCHIVE = DATA / "DMS_ProteinGym_substitutions.zip"
PUBLISHED = DATA / "zero_shot_substitutions_scores.zip"
MSA_DIR = DATA / "msa"
STRUCTURES = DATA / "structures" / "ProteinGym_AF2_structures.zip"
INPUTS = DATA / "baseline-inputs.json"

REGISTER = REPO / "assays" / "register.json"

#: The published column this baseline is checked against, and the floor reported beside it.
PUBLISHED_COLUMN = "RSALOR"
FLOOR_COLUMN = "Site_Independent"

#: ProteinGym's AlphaFold models are single-chain, and the package needs one named.
CHAIN = "A"

#: D-229's parameters, repeated here so a run manifest records what was actually used rather
#: than what a decision entry said. These are the package's defaults, which are the settings
#: the published column was produced with.
PARAMETERS = {
    "theta_regularization": 0.01,
    "n_regularization": 0.0,
    "count_target_sequence": True,
    "remove_redundant_sequences": True,
    "seqid_weights": 0.80,
    "min_seqid": 0.35,
    "rsa_solver": "the package's own default",
    "rsa_factor": "1 - min(RSA, 100) / 100",
    "chain": "A, the only chain in ProteinGym's AlphaFold models",
    "decision_ref": "D-229",
}


class Unavailable(RuntimeError):
    """The baseline package is not installed in this environment."""


def load_rsalor() -> Any:
    try:
        from rsalor import MSA
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise Unavailable(
            "the `rsalor` package is not importable. Run this under the baseline environment: "
            "`pixi run -e baseline python tools/baseline_scores.py`"
        ) from exc
    return MSA


@contextlib.contextmanager
def plain_copy(path: Path, suffix: str):
    """A gzipped alignment, briefly on disk uncompressed, because the package takes a path.

    Deleted on the way out: the alignments total 741 MB uncompressed and this container's
    writable disk is a fixed allowance, so holding more than one at a time is how a run that
    worked on the small assays dies on the large ones.
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        target = Path(handle.name)
        with gzip.open(path, "rb") as source:
            shutil.copyfileobj(source, handle, length=1 << 20)
    try:
        yield target
    finally:
        target.unlink(missing_ok=True)


@contextlib.contextmanager
def structure_copy(archive: Path, member: str):
    with zipfile.ZipFile(archive) as zf:
        names = {Path(i.filename).name: i.filename for i in zf.infolist() if not i.is_dir()}
        if member not in names:
            raise KeyError(f"{archive.name} has no structure named {member}")
        with (
            zf.open(names[member]) as source,
            tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as handle,
        ):
            shutil.copyfileobj(source, handle, length=1 << 20)
            target = Path(handle.name)
    try:
        yield target
    finally:
        target.unlink(missing_ok=True)


def by_mutation(records: list[dict[str, Any]], key: str) -> dict[str, float]:
    """The package's per-mutation scores, keyed by its alignment-coordinate mutation code."""
    out = {}
    for row in records:
        code = row.get("mutation_fasta")
        value = row.get(key)
        if code is not None and value is not None:
            out[str(code)] = float(value)
    return out


def score_key(records: list[dict[str, Any]]) -> str:
    """Which key carries the combined score, read from the output rather than assumed."""
    if not records:
        raise RuntimeError("the baseline returned no mutations")
    for candidate in ("RSA*LOR", "RSALOR", "RSA_LOR"):
        if candidate in records[0]:
            return candidate
    raise RuntimeError(
        "the baseline's output carries no combined-score column; keys are "
        f"{sorted(records[0])}. Refusing to fall back to the bare LOR, which is a different "
        "method from the one D-229 fixed"
    )


def translate(mutation: str, msa_start: int) -> str | None:
    """A benchmark mutation in the alignment's own coordinates, or None if outside it."""
    wt, mt = mutation[0], mutation[-1]
    position = int(mutation[1:-1]) - msa_start + 1
    return None if position < 1 else f"{wt}{position}{mt}"


def score_assay(
    MSA: Any,
    assay: proteingym.Assay,
    truth: dict[str, float],
    row: dict[str, str],
    *,
    threads: int,
) -> dict[str, Any]:
    alignment = MSA_DIR / f"{row['MSA_filename']}.gz"
    msa_start = int(row["MSA_start"])
    with (
        plain_copy(alignment, ".a2m") as msa_path,
        structure_copy(STRUCTURES, row["pdb_file"]) as pdb_path,
    ):
        # Every argument left at its default, which is what D-229 fixed and what the
        # published column was produced with. Passing them explicitly would be the same
        # values with an extra way to drift from the package.
        msa = MSA(str(msa_path), str(pdb_path), CHAIN, num_threads=threads)
        records = msa.get_scores()

    key = score_key(records)
    combined = by_mutation(records, key)
    # The two halves are kept beside the combined score. They cost nothing to carry and they
    # are what makes a disagreement with the published column diagnosable: a difference in the
    # structural half shows up as a per-position ratio, and one in the evolutionary half does
    # not. Without them B4.2 would have to re-run all 31 assays to ask the question.
    lor = by_mutation(records, "LOR")
    rsa = {
        str(row["mutation_fasta"])[1:-1]: float(row["RSA"])
        for row in records
        if row.get("mutation_fasta") is not None and row.get("RSA") is not None
    }

    scored, unscored = {}, []
    for mutant in sorted(truth):
        # Only single substitutions have a position in the alignment. A multiple is reported
        # as unscored rather than scored by summing its parts, which would be a different
        # method from the one D-229 fixed.
        parts = mutant.split(":")
        codes = [translate(p, msa_start) for p in parts]
        values = [combined.get(c) if c else None for c in codes]
        if len(parts) != 1 or values[0] is None:
            unscored.append(mutant)
            continue
        # Negated: the package is oriented so that large positive means disruptive, and the
        # benchmark's fitness is the other way up. The orientation is then *checked* against
        # the published column rather than left as an assertion.
        scored[mutant] = -values[0]

    return {
        "assay": assay.dms_id,
        "alignment": row["MSA_filename"],
        "structure": row["pdb_file"],
        "msa_start": msa_start,
        "score_column": key,
        "orientation": "negated so that higher means fitter, as the benchmark's metric expects",
        "variants_in_assay": len(truth),
        "variants_scored": len(scored),
        "variants_unscored": len(unscored),
        "unscored_examples": sorted(unscored)[:10],
        "scores": scored,
        "components": {
            "note": (
                "the baseline's own two halves, in its sign convention and its alignment "
                "coordinates, not negated and not translated. For diagnosing a disagreement "
                "with the published column, not for analysis"
            ),
            "lor": lor,
            "rsa_by_position": dict(sorted(rsa.items(), key=lambda kv: int(kv[0]))),
        },
    }


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    compared = [r["reference_check"] for r in results if r["reference_check"].get("compared")]
    verdicts: dict[str, int] = {}
    for check in compared:
        verdicts[check.get("verdict")] = verdicts.get(check.get("verdict"), 0) + 1
    unscored = [
        {"assay": r["assay"], "unscored": r["variants_unscored"], "of": r["variants_in_assay"]}
        for r in results
        if r["variants_unscored"]
    ]
    return {
        "assays": len(results),
        "parameters": PARAMETERS,
        "published_column": PUBLISHED_COLUMN,
        "reference": {
            "assays_compared": len(compared),
            "verdicts": dict(sorted(verdicts.items(), key=lambda kv: str(kv[0]))),
            # None, not True: `all([])` is True and a field reading True because nothing was
            # compared is how an unvalidated baseline gets signed off.
            "all_reproduced": (
                all(c.get("verdict") == "reproduced" for c in compared) if compared else None
            ),
        },
        "assays_with_unscored_variants": unscored,
        "no_training_exposure": (
            "nothing in this baseline is trained. The alignment is built from sequence "
            "databases at inference time, the structure is a prediction of the target itself, "
            "and the score is a closed-form function of the two, so there are no weights and "
            "therefore no corpus a filter could have been applied to (D-229)"
        ),
    }


def durable_for(out: Path) -> str | None:
    """The durable prefix, **or None for a run that is not the deliverable** (D-224)."""
    if out.resolve() == CANONICAL_OUT.resolve():
        return objectstore.durable_results("b4-1")
    print(f"not publishing: --out {out} is not {CANONICAL_OUT}", file=sys.stderr)
    return None


def provenance(repo: Path = REPO) -> dict[str, Any]:
    """What a per-assay file must agree with before a later run may reuse it."""
    state = repro.git_state(repo)
    return {
        "parameters": dict(PARAMETERS),
        "commit": state.get("commit") if state.get("available") else None,
        "dirty": state.get("dirty") if state.get("available") else None,
    }


def reusable(path: Path, now: dict[str, Any]) -> dict[str, Any] | None:
    """An already-scored assay this run may carry over, or None to score it again.

    A pass over all 31 assays is hours, and a container that restarts halfway through
    threw all of it away — twice would be careless. But a half-finished directory is also
    how a result from the wrong code ends up in a deliverable looking like the rest, so
    the bar is exact agreement: same parameters, same commit, and neither run from a dirty
    tree. Anything else is rescored, which is the cheap mistake to make.
    """
    if not path.exists():
        return None
    try:
        earlier = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    had = earlier.get("provenance")
    if not isinstance(had, dict) or had != now or now.get("commit") is None or now.get("dirty"):
        return None
    return earlier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=CANONICAL_OUT, type=Path)
    parser.add_argument("--assay", action="append", help="limit to these assays, for a rehearsal")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="carry over an assay already scored by this commit with these parameters",
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    MSA = load_rsalor()
    register = json.loads(REGISTER.read_text())
    wanted = set(args.assay) if args.assay else {a["dms_id"] for a in register["assays"]}
    assays = {a.dms_id: a for a in proteingym.load_reference(REFERENCE)}
    with REFERENCE.open(newline="") as handle:
        rows = {r["DMS_id"]: r for r in csv.DictReader(handle)}

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    # A run limited to some of the assays writes the same `baseline.json` under the same
    # durable key as the full pass, and a summary over three assays reads exactly like a
    # summary over 31. The corpus bucket has no delete, so that file would be permanent
    # (D-193, D-224). `--out` is not the signal here because a one-assay rehearsal is most
    # naturally run against the canonical directory, which is where its per-assay file
    # belongs; `--assay` is.
    partial = bool(args.assay)
    destination = None if partial else durable_for(out)
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-baseline.json",
        durable=destination,
        durable_exempt=None
        if destination
        else (
            "a run over some of the assays, whose summary would read like the whole pass"
            if partial
            else "rehearsal: --out is not the canonical directory"
        ),
    ) as m:
        for path in (REFERENCE, INPUTS, REGISTER, PUBLISHED):
            m.input_file(path, role="input")
        for name, value in PARAMETERS.items():
            m.parameter(name, value)

        results = []
        carried: list[str] = []
        now = provenance()
        m.parameter("resume", bool(args.resume))
        for dms_id in sorted(wanted):
            path = out / f"baseline-{dms_id}.json"
            earlier = reusable(path, now) if args.resume else None
            if earlier is not None:
                print(f"carrying over {dms_id}", flush=True)
                m.output_file(path, role="baseline-scores")
                results.append(earlier)
                carried.append(dms_id)
                continue
            print(f"scoring {dms_id}", flush=True)
            assay = assays[dms_id]
            truth = proteingym.load_assay(ASSAY_ARCHIVE, assay)
            result = score_assay(MSA, assay, truth, rows[dms_id], threads=args.threads)
            published = proteingym.load_model_scores(PUBLISHED, assay, PUBLISHED_COLUMN)
            result["reference_check"] = reference.check_against_published(
                f"baseline-{PUBLISHED_COLUMN}",
                dms_id,
                result["scores"],
                published,
                truth,
                seed=SEED,
            ).to_dict()
            result["provenance"] = now
            path.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
            m.output_file(path, role="baseline-scores")
            results.append(result)

        report = summarise(results)
        report["carried_over"] = carried
        path = out / "baseline.json"
        path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(path, role="baseline-summary")

    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

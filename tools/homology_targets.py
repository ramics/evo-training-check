"""Build the target side of §B3's homology axis — tasks B3.1 and B3.2.

Nothing here reads a corpus. It fixes, before any surviving record is looked at, the two things
the corpus pass will search with:

**B3.1's profile per target.** §B3 item 1 names jackhmmer, which builds its model out of the
database it is searching. Against a corpus this project is auditing that is the wrong
instrument twice over — the model would be built from the thing being measured, so the score
would stop being a property of the target, and an iterated search over 28 GB is out of reach
besides. The profile is therefore built from the alignment the benchmark's own maintainers
distribute for the target: the same object B3.4 computed the depth covariate on, so the
covariate and the homology score rest on one input. D-255.

**B3.2's domain annotation per target.** §B3 item 2 asks whether a target's annotated domains
are present in surviving space, which first requires the annotation. It is computed here
against the Pfam 38.2 pin at Pfam's own gathering cutoffs, held to the same model-coverage
floor A2.1 applies, so a domain this file calls annotated and a family A2.1 calls detected are
the same kind of object and can be joined.

Outputs `targets.json`: one entry per assay target with its length, its profile's digest and
statistics, and its annotated domain families. The profiles themselves go to `data/` rather
than to an artefact — they are regenerable from a pinned alignment whose digest is recorded,
and a 28-profile binary in the audit store would be a second copy of an input.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import homology, objectstore, profiles, profilesearch
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B3.1/B3.2"
SEED = 20261026
CANONICAL_OUT = REPO / "artifacts" / "b3-targets"

#: B2.4's register: the pinned list of assays Phase B analyses. Read as a file, so a target in
#: the analysis is a target with a profile and an annotation.
REGISTER = REPO / "assays" / "register.json"

#: B2.1's staged release and B3.4's staged alignments.
STAGED = REPO / "data" / "proteingym" / "v1.3"
REFERENCE = STAGED / "DMS_substitutions.csv"
MSA_DIR = STAGED / "msa"

#: Where the built profiles go. Regenerable; git-ignored with the rest of `data/`.
PROFILE_DIR = REPO / "data" / "b3" / "target-profiles"

#: Columns read from the maintainers' reference file. All three are inputs, not results.
TARGET_SEQ = "target_seq"
MSA_FILENAME = "MSA_filename"
DMS_ID = "DMS_id"


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def load_register() -> list[dict[str, Any]]:
    return json.loads(REGISTER.read_text())["assays"]


def load_reference_rows(ids: set[str]) -> dict[str, dict[str, str]]:
    """The reference row for each assay in the register, by `DMS_id`."""
    rows: dict[str, dict[str, str]] = {}
    with REFERENCE.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row[DMS_ID] in ids:
                rows[row[DMS_ID]] = row
    missing = ids - set(rows)
    if missing:
        raise SystemExit(
            f"the reference file has no row for {len(missing)} register assays: "
            f"{', '.join(sorted(missing)[:3])}"
        )
    return rows


def _gunzip_to(src: Path, dest: Path) -> Path:
    with gzip.open(src, "rb") as handle, dest.open("wb") as sink:
        shutil.copyfileobj(handle, sink)
    return dest


def build_profile(alignment_gz: Path, *, name: str, scratch: Path, out: Path) -> dict[str, Any]:
    """Build one profile from one distributed alignment, and record what it was built from.

    The alignment is a2m — lowercase and `.` are insertions relative to the query — which Easel
    reads natively, so the match columns the profile's states come from are the same columns
    `amazebio.neff` computed the depth over. Reading it as anything else would silently build
    the model over a different set of columns.
    """
    import pyhmmer
    from pyhmmer.easel import Alphabet, MSAFile

    scratch.mkdir(parents=True, exist_ok=True)
    plain = _gunzip_to(alignment_gz, scratch / (alignment_gz.stem + ".a2m"))
    amino = Alphabet.amino()
    with MSAFile(plain, digital=True, alphabet=amino, format="a2m") as handle:
        msa = handle.read()
    if msa is None:
        raise SystemExit(f"{alignment_gz.name}: no alignment in the file")
    msa.name = name.encode()
    builder = pyhmmer.plan7.Builder(amino)
    background = pyhmmer.plan7.Background(amino)
    hmm, _, _ = builder.build_msa(msa, background)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as sink:
        hmm.write(sink)
    plain.unlink()
    return {
        "profile": out.name,
        "profile_sha256": sha256_file(out),
        "profile_length": int(hmm.M),
        "alignment": alignment_gz.name,
        "alignment_sha256": sha256_file(alignment_gz),
        "alignment_sequences": int(len(msa.sequences)),
        "alignment_columns": int(len(msa)),
    }


def annotate_domains(
    targets: dict[str, str], *, hmm_file: Path, cpus: int
) -> dict[str, list[dict[str, Any]]]:
    """Pfam families annotated on each target sequence, at the pin's own gathering cutoffs.

    Held to `profiles.MIN_MODEL_COVERAGE` as well as to the curated cutoff, for A2.1's reason
    (D-076's note on `MIN_MODEL_COVERAGE`): a short slice of a long model is an annotation Pfam
    is happy to make and not a family whose presence this axis would report. Applying the same
    floor on both sides is what lets B3.2 join its verdicts to A2.1's detected sets.
    """
    import pyhmmer
    from pyhmmer.easel import Alphabet, DigitalSequenceBlock, TextSequence

    amino = Alphabet.amino()
    block = DigitalSequenceBlock(
        amino,
        [
            TextSequence(name=dms_id.encode(), sequence=sequence).digitize(amino)
            for dms_id, sequence in targets.items()
        ],
    )
    found: dict[str, dict[str, dict[str, Any]]] = {d: {} for d in targets}
    with pyhmmer.plan7.HMMFile(hmm_file) as handle:
        for top in pyhmmer.hmmsearch(handle, block, cpus=cpus, bit_cutoffs="gathering"):
            accession = profilesearch.text_of(top.query.accession or top.query.name)
            family = profilesearch.text_of(top.query.name)
            length = int(top.query.M)
            for hit in top:
                if hit.included is False:
                    continue
                coverage = profilesearch.best_model_coverage(hit, length)
                if coverage < profiles.MIN_MODEL_COVERAGE:
                    continue
                dms_id = profilesearch.text_of(hit.name)
                entry = found[dms_id].setdefault(
                    accession,
                    {
                        "accession": accession,
                        "family": family,
                        "model_length": length,
                        "instances": 0,
                        "best_bits": None,
                        "best_model_coverage": None,
                    },
                )
                # Instances are the included domains of this family on this target. The count of
                # *families* is B3.2's score; the instance count travels beside it, because a
                # repeated domain is one family and `metrics/homology.md` says which is which.
                entry["instances"] += sum(1 for d in hit.domains if d.included is not False)
                if entry["best_bits"] is None or hit.score > entry["best_bits"]:
                    entry["best_bits"] = float(hit.score)
                    entry["best_model_coverage"] = round(coverage, 6)
    return {d: sorted(v.values(), key=lambda e: e["accession"]) for d, v in found.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=CANONICAL_OUT)
    parser.add_argument("--cpus", type=int, default=3)
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    parser.add_argument(
        "--no-durable",
        action="store_true",
        help="smoke runs only; the result is not citable and is not published",
    )
    args = parser.parse_args(argv)

    register = load_register()
    ids = {a["dms_id"] for a in register}
    reference = load_reference_rows(ids)
    pfam = profiles.registry("pfam")
    hmm_file = profilesearch.hmm_path(pfam, REPO / "data" / "profiles")
    if not hmm_file.exists():
        raise SystemExit(f"{hmm_file} is not staged; run tools/stage_profiles.py --registry pfam")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / "scratch"

    with run(
        task=TASK,
        seed=SEED,
        outdir=out,
        manifest_name="run-targets.json",
        allow_dirty=args.allow_dirty,
        durable=None if args.no_durable else objectstore.durable_results("b3-targets"),
        durable_exempt=(
            "smoke run: --no-durable, so this output is scratch and is not cited"
            if args.no_durable
            else None
        ),
    ) as ctx:
        ctx.parameter("register_sha256", sha256_file(REGISTER))
        ctx.parameter("reference_sha256", sha256_file(REFERENCE))
        ctx.parameter("pfam_registry", pfam.key)
        ctx.parameter("min_model_coverage", profiles.MIN_MODEL_COVERAGE)
        ctx.parameter("domain_cutoffs", "pfam gathering")
        ctx.parameter("profile_builder", "pyhmmer.plan7.Builder defaults over a2m match columns")
        ctx.parameter("pinned_e_value", homology.PINNED_E_VALUE)
        ctx.parameter("pinned_z", homology.PINNED_Z)
        ctx.input_file(REGISTER, role="assay register")
        ctx.input_file(REFERENCE, role="benchmark reference")
        ctx.input_file(hmm_file, role="pfam profiles")

        sequences = {d: reference[d][TARGET_SEQ].strip().upper() for d in sorted(ids)}
        empty = [d for d, s in sequences.items() if not s]
        if empty:
            raise SystemExit(f"no target sequence for: {', '.join(empty)}")

        built: dict[str, dict[str, Any]] = {}
        entries: list[dict[str, Any]] = []
        for dms_id in sorted(ids):
            filename = reference[dms_id].get(MSA_FILENAME, "").strip()
            staged = MSA_DIR / (filename + ".gz") if filename else None
            profile_meta: dict[str, Any] | None = None
            if staged is not None and staged.exists():
                if filename in built:
                    profile_meta = built[filename]
                else:
                    profile_meta = build_profile(
                        staged,
                        name=Path(filename).stem,
                        scratch=scratch,
                        out=PROFILE_DIR / (Path(filename).stem + ".hmm"),
                    )
                    built[filename] = profile_meta
                    ctx.input_file(staged, role="distributed alignment")
            entries.append(
                {
                    "dms_id": dms_id,
                    "uniprot_id": reference[dms_id].get("UniProt_ID") or None,
                    "target_length": len(sequences[dms_id]),
                    "alignment": filename or None,
                    "profile": profile_meta,
                    "profile_absent_because": (
                        None
                        if profile_meta
                        else (
                            "the maintainers distribute no alignment for this target"
                            if not filename
                            else f"{filename} is not staged"
                        )
                    ),
                }
            )

        annotations = annotate_domains(sequences, hmm_file=hmm_file, cpus=args.cpus)
        for entry in entries:
            families = annotations[entry["dms_id"]]
            entry["domain_families"] = families
            entry["domain_family_count"] = len(families)

        payload = {
            "task": TASK,
            "what_this_is": (
                "The target side of the §B3 homology axis, fixed before any surviving record "
                "is read: one profile per assay target built from the alignment its "
                "maintainers distribute, and the Pfam families annotated on each target. "
                "metrics/homology.md is the contract; D-255 records why the profile is not "
                "jackhmmer's."
            ),
            "pfam_registry": pfam.key,
            "min_model_coverage": profiles.MIN_MODEL_COVERAGE,
            "targets": entries,
            "totals": {
                "targets": len(entries),
                "distinct_alignments": len(built),
                "targets_without_profile": sum(1 for e in entries if not e["profile"]),
                "targets_without_domains": sum(1 for e in entries if not e["domain_family_count"]),
                "distinct_domain_families": len(
                    {f["accession"] for e in entries for f in e["domain_families"]}
                ),
            },
        }
        (out / "targets.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        ctx.output_file(out / "targets.json", role="target side of the homology axis")
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)

    totals = payload["totals"]
    print(
        f"{totals['targets']} targets, {totals['distinct_alignments']} distinct alignments, "
        f"{totals['distinct_domain_families']} distinct domain families, "
        f"{totals['targets_without_profile']} without a profile, "
        f"{totals['targets_without_domains']} without an annotated domain"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

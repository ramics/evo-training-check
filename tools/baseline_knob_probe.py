"""Sample the baseline's sequence-filtering knobs on one assay, as a diagnostic — B4.2, D-248.

    pixi run -e baseline python tools/baseline_knob_probe.py VRPI_BPT7_Tsuboyama_2023_2WNM

B4.2 established that the baseline's disagreement with ProteinGym's published RSALOR column is
about which sequences enter the alignment's frequency count: in the six worst assays the
published column treats up to a quarter of variants as absent from the column where this
implementation finds them present, and nowhere the reverse. The obvious next question is whether
one of the package's documented filtering parameters, set differently, would close it.

This tool answers that question and nothing else. It rebuilds one assay's scores at several
settings of the filtering knobs and reports the agreement each one reaches with the published
column.

**It is a diagnostic and its output must not choose a parameter.** D-229 fixed the parameters at
the package's defaults, which is what makes the baseline parameter-free and what lets its figure
be compared with a published one at all. Picking the setting that maximises agreement with a
reference column would fit the baseline to the thing it is being validated against, and the
resulting number would measure the fitting rather than the implementation. So this runs, its
output is recorded in the task file and in D-248, and the parameters do not move.

What it found, on 2026-10-21, over three assays chosen to span the range:

* The defaults reproduce B4.1's published figures exactly, which is the reproducibility check.
* `min_seqid` is the only knob that matters, and it pulls in opposite directions across assays:
  the weakest assay improves from 0.82 to 0.86 at 0.5 while the strongest falls from 0.9985 to
  0.87 at the same setting. No single value fits both.
* No setting reaches the 0.99 floor on the weakest assay, so the shortfall there is not a
  mis-set parameter in this harness. Whatever produced the published column saw a narrower
  sequence set than any filtering of ProteinGym's own alignment produces.

Needs the baseline environment, because it imports the scoring package, and the alignments and
structures staged by `tools/stage_assay_msas.py`.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import pathlib
import shutil
import sys
import tempfile
import zipfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from amazebio import proteingym
from amazebio.proteingym import spearman

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "proteingym" / "v1.3"
REFERENCE = DATA / "DMS_substitutions.csv"
PUBLISHED = DATA / "zero_shot_substitutions_scores.zip"
PUBLISHED_COLUMN = "RSALOR"
MSA_DIR = DATA / "msa"
STRUCTURES = DATA / "structures" / "ProteinGym_AF2_structures.zip"
CHAIN = "A"

#: The settings sampled. `defaults` is D-229's, and every other row changes exactly one knob,
#: so a difference is attributable. These are not candidates: see the module docstring.
SETTINGS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("defaults (D-229)", {}),
    ("remove_redundant_sequences=False", {"remove_redundant_sequences": False}),
    ("count_target_sequence=False", {"count_target_sequence": False}),
    ("min_seqid=0.0", {"min_seqid": 0.0}),
    ("min_seqid=0.5", {"min_seqid": 0.5}),
    ("min_seqid=0.8", {"min_seqid": 0.8}),
    ("seqid_weights=None", {"seqid_weights": None}),
)


def inputs(name: str, workdir: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, int]:
    """The assay's alignment and structure, unpacked, with its alignment offset."""
    with REFERENCE.open() as handle:
        row = next(r for r in csv.DictReader(handle) if r["DMS_id"] == name)
    a2m = workdir / "msa.a2m"
    with gzip.open(MSA_DIR / f"{row['MSA_filename']}.gz", "rb") as src, a2m.open("wb") as out:
        shutil.copyfileobj(src, out)
    with zipfile.ZipFile(STRUCTURES) as archive:
        member = next(n for n in archive.namelist() if n.endswith(row["pdb_file"]))
        pdb = workdir / "target.pdb"
        pdb.write_bytes(archive.read(member))
    return a2m, pdb, int(row["MSA_start"])


def agreement(
    a2m: pathlib.Path,
    pdb: pathlib.Path,
    msa_start: int,
    published: dict[str, float],
    *,
    threads: int,
    **settings: Any,
) -> tuple[float, int]:
    from rsalor import MSA

    records = MSA(str(a2m), str(pdb), CHAIN, num_threads=threads, **settings).get_scores()
    column = "RSA*LOR"
    if column not in records[0]:
        raise SystemExit(f"no {column!r} column in the package's output: {sorted(records[0])}")
    by_code = {r["mutation_fasta"]: float(r[column]) for r in records if r.get("mutation_fasta")}
    ours = {}
    for variant in published:
        if ":" in variant:
            # A multiple has no single position in the alignment and the baseline leaves it
            # unscored (D-229); the comparison is over what both sides score.
            continue
        code = f"{variant[0]}{int(variant[1:-1]) - msa_start + 1}{variant[-1]}"
        value = by_code.get(code)
        if value is not None:
            # Negated to the benchmark's orientation, as the baseline itself does.
            ours[variant] = -value
    shared = sorted(ours)
    return spearman([ours[v] for v in shared], [published[v] for v in shared]), len(shared)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("assay", nargs="+", help="one or more DMS ids")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--json", type=pathlib.Path, help="write the table here as well")
    args = ap.parse_args(argv)

    assays = {a.dms_id: a for a in proteingym.load_reference(REFERENCE)}
    out: list[dict[str, Any]] = []
    for name in args.assay:
        if name not in assays:
            raise SystemExit(f"{name} is not in {REFERENCE.name}")
        published = proteingym.load_model_scores(PUBLISHED, assays[name], PUBLISHED_COLUMN)
        workdir = pathlib.Path(tempfile.mkdtemp())
        try:
            a2m, pdb, msa_start = inputs(name, workdir)
            print(f"{name}, MSA_start {msa_start}", flush=True)
            for label, settings in SETTINGS:
                value, count = agreement(
                    a2m, pdb, msa_start, published, threads=args.threads, **settings
                )
                print(f"  {label:<36} agreement {value:.4f} over {count:,} variants", flush=True)
                out.append(
                    {
                        "assay": name,
                        "setting": label,
                        "agreement": round(value, 6),
                        "variants": count,
                    }
                )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "task": "B4.2",
                    "decisions": ["D-229", "D-248"],
                    "published_column": PUBLISHED_COLUMN,
                    "diagnostic_only": (
                        "these settings are not candidates; D-229's parameters do not move on "
                        "the strength of this table, because choosing them to maximise "
                        "agreement with the published column would fit the baseline to its own "
                        "validation"
                    ),
                    "rows": out,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

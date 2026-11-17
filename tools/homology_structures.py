"""The structural side of §B3's homology axis — task B3.3.

§B3 pre-registers this as the **primary** measure: "Foldseek TM-score to nearest surviving
structure", because remote structural homology is the route by which a fold's biophysics is
learned when sequence similarity is undetectable. A2.2 then established, one phase earlier and
over the same corpora, that the measure cannot be computed here — and the two halves of that
are worth keeping apart, because only one of them is about money:

1. **The TM-score is unavailable on the publisher's own statement.** The corpus side has no
   structures, so a search needs a structural alphabet predicted from sequence, and such a
   database carries no C-alpha coordinates: the tool refuses TM-score and LDDT output outright,
   not merely for coordinate-derived columns (D-167).
2. **The coordinate-free score that remains was priced and declined.** One manifest at the
   pre-registered depth came to 70+ instance-hours and $55-60 against a $30 ceiling, and the
   owner's call was to record the cost rather than buy the depth (D-180).

So this tool does what can be done without a corpus pass, and does it *before* any search so
the parameters are frozen in the sense §B3 requires rather than in retrospect:

* **Resolves a structure for every assay target** from the benchmark's own pinned structure
  archive, and records the mix — which targets have one, what predicted it, and how much of
  each target sequence it covers.
* **Quantifies the heterogeneity bias** §B3's third step asks about, on the side that exists:
  per-residue confidence is distributed across these structures, and a target modelled at low
  confidence over half its length would carry a nearest-structure score that says more about
  the prediction than about surviving space. The distribution is the measurement; D-257 records
  the reading.
* **Declares the search parameters**, so that if the depth is ever bought the run is executed
  against a specification written before a hit was seen, and states the one parameter that
  cannot be declared from here — the acceptance threshold, which needs a decoy calibration in
  this geometry and is part of the pass that was not bought.

What it does not do is produce a similarity score, and it does not quietly substitute a
sequence measure for the primary one. `tools/homology_rows.py` emits every `structural` cell as
`not_searched` with the reason, which is A2.2's precedent and `metrics/homology.md`'s rule.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B3.3"
SEED = 20261026
CANONICAL_OUT = REPO / "artifacts" / "b3-3"

REGISTER = REPO / "assays" / "register.json"
STAGED = REPO / "data" / "proteingym" / "v1.3"
REFERENCE = STAGED / "DMS_substitutions.csv"
STRUCTURES = STAGED / "structures" / "ProteinGym_AF2_structures.zip"

#: The confidence floor the predictor's own publishers call the boundary of a confident
#: prediction. Used only to summarise the distribution — nothing is filtered on it here, and
#: the whole distribution travels with every figure.
CONFIDENT_PLDDT = 70.0

#: The parameters a bought pass would run under, declared here and not later. Geometry follows
#: D-167: only the side with coordinates can be the target, so the corpus is the query and the
#: 31 target structures are the target database, with the coverage floor on the target.
SEARCH_PARAMETERS = {
    "tool": "foldseek 10.941cd33, as A2.2 pinned it",
    "corpus_side": "3Di predicted from sequence with the pinned ProstT5 weights",
    "query": "the corpus, because only the structure side carries C-alpha (D-167)",
    "target": "the assay targets' structures",
    "alignment_type": "default 3Di+amino-acid, as A2.2 ran it",
    "coverage": "--cov-mode 1 at 0.5 of the target, carrying A2.1's model-coverage floor",
    "score": "bit score, not E-value (D-076); TM-score and LDDT are unavailable (D-167)",
    "threshold": None,
    "threshold_note": (
        "Not declarable from here. A2.2's 500-bit cut was calibrated for its own geometry — a "
        "141-structure fold reference as the target — and this geometry's target database is a "
        "different size and composition, so carrying the number over would be a declared "
        "threshold that had never been calibrated against anything. The calibration is a decoy "
        "pass in this geometry and is part of the run that was not bought; declaring a number "
        "without it would be worse than declaring none, because the run would still produce a "
        "plausible table (D-167's first finding, one geometry over)."
    ),
}


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def target_rows(ids: set[str]) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with REFERENCE.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["DMS_id"] in ids:
                rows[row["DMS_id"]] = row
    return rows


def _parse_pdb(text: str) -> dict[str, Any]:
    """Residue count, per-residue confidence and the predictor, from one PDB member.

    Confidence is read from the B-factor column of the C-alpha records, which is where this
    predictor writes its per-residue confidence. One value per residue, not per atom: averaging
    over atoms would weight a residue by how many atoms it has.
    """
    plddt: list[float] = []
    method: str | None = None
    for line in text.splitlines():
        if line.startswith(("REMARK", "TITLE", "HEADER")) and method is None:
            upper = line.upper()
            for name in ("ALPHAFOLD", "ESMFOLD", "ROSETTA", "COLABFOLD"):
                if name in upper:
                    method = name.title()
                    break
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            try:
                plddt.append(float(line[60:66]))
            except ValueError:
                continue
    return {"residues": len(plddt), "plddt": plddt, "method_in_file": method}


def summarise(plddt: list[float]) -> dict[str, Any]:
    if not plddt:
        return {"residues": 0}
    confident = sum(1 for v in plddt if v >= CONFIDENT_PLDDT)
    return {
        "residues": len(plddt),
        "plddt_min": round(min(plddt), 2),
        "plddt_median": round(statistics.median(plddt), 2),
        "plddt_mean": round(statistics.fmean(plddt), 2),
        "plddt_max": round(max(plddt), 2),
        "residues_at_or_above_70": confident,
        "fraction_at_or_above_70": round(confident / len(plddt), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=CANONICAL_OUT)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--no-durable",
        action="store_true",
        help="smoke runs only; the result is not citable and is not published",
    )
    args = parser.parse_args(argv)

    if not STRUCTURES.exists():
        raise SystemExit(
            f"{STRUCTURES} is not staged; run tools/stage_assay_msas.py without "
            "--skip-structures"
        )
    register = json.loads(REGISTER.read_text())["assays"]
    ids = {a["dms_id"] for a in register}
    rows = target_rows(ids)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    with run(
        task=TASK,
        seed=SEED,
        outdir=out,
        manifest_name="run-structures.json",
        allow_dirty=args.allow_dirty,
        durable=None if args.no_durable else objectstore.durable_results("b3-3"),
        durable_exempt=(
            "smoke run: --no-durable, so this output is scratch and is not cited"
            if args.no_durable
            else None
        ),
    ) as ctx:
        ctx.parameter("confident_plddt", CONFIDENT_PLDDT)
        ctx.parameter("search_parameters", SEARCH_PARAMETERS)
        ctx.parameter("searched", False)
        ctx.parameter(
            "not_searched_because",
            "TM-score unavailable on the publisher's statement (D-167); the coordinate-free "
            "alternative priced at 70+ instance-hours for one manifest and declined (D-180)",
        )
        ctx.input_file(REGISTER, role="assay register")
        ctx.input_file(REFERENCE, role="benchmark reference")
        ctx.input_file(STRUCTURES, role="benchmark structure archive")

        with zipfile.ZipFile(STRUCTURES) as archive:
            members = {Path(n).name: n for n in archive.namelist() if n.lower().endswith(".pdb")}
            entries = []
            for dms_id in sorted(ids):
                row = rows.get(dms_id, {})
                uniprot = (row.get("UniProt_ID") or "").strip()
                target_length = len((row.get("target_seq") or "").strip())
                candidates = [
                    name for name in members if uniprot and name.upper().startswith(uniprot.upper())
                ]
                if not candidates:
                    entries.append(
                        {
                            "dms_id": dms_id,
                            "uniprot_id": uniprot or None,
                            "target_length": target_length,
                            "structure": None,
                            "absent_because": (
                                "the benchmark's structure archive has no member for this "
                                "target's entry name"
                            ),
                        }
                    )
                    continue
                member = members[sorted(candidates)[0]]
                with archive.open(member) as handle:
                    parsed = _parse_pdb(handle.read().decode("utf-8", "replace"))
                stats = summarise(parsed["plddt"])
                entries.append(
                    {
                        "dms_id": dms_id,
                        "uniprot_id": uniprot or None,
                        "target_length": target_length,
                        "structure": Path(member).name,
                        "source": "benchmark's own predicted-structure archive",
                        "method_in_file": parsed["method_in_file"],
                        "sequence_coverage": (
                            round(stats["residues"] / target_length, 4)
                            if target_length and stats["residues"]
                            else None
                        ),
                        **stats,
                    }
                )

        resolved = [e for e in entries if e["structure"]]
        fractions = [
            e["fraction_at_or_above_70"] for e in resolved if e.get("fraction_at_or_above_70")
        ]
        coverages = [e["sequence_coverage"] for e in resolved if e.get("sequence_coverage")]
        payload = {
            "task": TASK,
            "what_this_is": (
                "The structural side of §B3's homology axis: a structure resolved for every "
                "assay target, the confidence distribution that bounds what a nearest-structure "
                "score could mean, and the parameters a bought pass would run under. No "
                "manifest was searched; see `not_searched_because`."
            ),
            "contract": "metrics/homology.md",
            "role": "primary, pre-registered (DESIGN.md §B3 item 3)",
            "searched": False,
            "not_searched_because": {
                "tm_score": (
                    "A structural-alphabet database predicted from sequence carries no C-alpha, "
                    "and the tool refuses TM-score and LDDT output outright — the publisher's "
                    "own statement, not a limit of this run (D-167)."
                ),
                "coordinate_free_bit_score": (
                    "Priced at 70+ instance-hours and $55-60 for one manifest against a $30 "
                    "ceiling; the owner's call was to record the cost (D-180)."
                ),
            },
            "search_parameters": SEARCH_PARAMETERS,
            "structure_mix": {
                "targets": len(entries),
                "with_a_structure": len(resolved),
                "without_a_structure": len(entries) - len(resolved),
                "sources": sorted({e.get("source") for e in resolved if e.get("source")}),
                "one_source_only": len({e.get("source") for e in resolved if e.get("source")}) <= 1,
            },
            "heterogeneity": {
                "what_this_bounds": (
                    "Every target structure comes from one predictor, so the query side is "
                    "homogeneous and the heterogeneity that could bias a score is between the "
                    "two sides of the search, not within this one: these are predicted "
                    "all-atom models and the corpus side would be a structural alphabet "
                    "predicted from sequence. The per-residue confidence below bounds what the "
                    "better side is worth; it does not bound the comparison."
                ),
                "fraction_at_or_above_70_median": (
                    round(statistics.median(fractions), 4) if fractions else None
                ),
                "fraction_at_or_above_70_min": round(min(fractions), 4) if fractions else None,
                "targets_below_half_confident": sum(1 for f in fractions if f < 0.5),
                "sequence_coverage_median": (
                    round(statistics.median(coverages), 4) if coverages else None
                ),
                "sequence_coverage_min": round(min(coverages), 4) if coverages else None,
            },
            "targets": entries,
        }
        (out / "structures.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        (out / "structures.md").write_text(_markdown(payload))
        ctx.output_file(out / "structures.json", role="target structures and the frozen parameters")
        ctx.output_file(out / "structures.md", role="the same, for a person")

    mix = payload["structure_mix"]
    het = payload["heterogeneity"]
    print(
        f"{mix['with_a_structure']} of {mix['targets']} targets have a structure; "
        f"median confident fraction {het['fraction_at_or_above_70_median']}, "
        f"{het['targets_below_half_confident']} below half; no manifest searched"
    )
    return 0


def _markdown(payload: dict[str, Any]) -> str:
    mix, het = payload["structure_mix"], payload["heterogeneity"]
    lines = [
        "# B3.3 — the structural side of the homology axis",
        "",
        "Generated by `tools/homology_structures.py`. Contract: `metrics/homology.md`.",
        "",
        "**This is §B3's pre-registered primary measure and no manifest was searched for it.**",
        "",
        f"- TM-score: {payload['not_searched_because']['tm_score']}",
        f"- The coordinate-free alternative: "
        f"{payload['not_searched_because']['coordinate_free_bit_score']}",
        "",
        "## The target structures",
        "",
        f"{mix['with_a_structure']} of {mix['targets']} targets resolve to a structure, all from "
        f"{'one source' if mix['one_source_only'] else 'more than one source'}: "
        + ", ".join(mix["sources"]),
        "",
        f"Median fraction of residues at or above {CONFIDENT_PLDDT:.0f} confidence: "
        f"{het['fraction_at_or_above_70_median']}; lowest "
        f"{het['fraction_at_or_above_70_min']}; "
        f"{het['targets_below_half_confident']} target(s) confident over less than half their "
        "modelled length.",
        "",
        "| assay | structure | residues | coverage of target | median confidence | ≥70 |",
        "|---|---|---|---|---|---|",
    ]
    for entry in payload["targets"]:
        if not entry["structure"]:
            lines.append(f"| `{entry['dms_id']}` | — | — | — | — | {entry['absent_because']} |")
            continue
        lines.append(
            f"| `{entry['dms_id']}` | {entry['structure']} | {entry['residues']:,} | "
            f"{entry['sequence_coverage']} | {entry['plddt_median']} | "
            f"{entry['fraction_at_or_above_70']} |"
        )
    lines += [
        "",
        "## The parameters a bought pass would run under",
        "",
        "Declared here, before any search, which is what §B3's pre-registration requirement",
        "asks for. One parameter is deliberately `null`:",
        "",
    ]
    for key, value in payload["search_parameters"].items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

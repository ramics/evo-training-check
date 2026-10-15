---
id: A4.2
title: Benchmark taxonomy-tool misassignment
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A5.1, A6.1, A4.4]
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.2 — Benchmark taxonomy-tool misassignment

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Measure the error rate of the taxonomy assignment tools a filter depends on, on the sequence
class that matters for this audit.

## Steps

- Assemble a labelled evaluation set with trustworthy ground truth; document its provenance and
  biases.
- Benchmark the relevant tools at the versions the filters rely on.
- Report error rates with confidence intervals, broken down by error direction.
- State how tool error propagates into filter leakage.

## Done when

- Error rates reported with intervals and by direction.
- Evaluation-set provenance and bias documented.
- Propagation into leakage stated quantitatively where possible.

## In flight — 2026-10-15

**Branch:** `ccr-bcc7b994-9ycpzn`. Pre-registration is on `main` (D-084..D-088); the input-side
pass and the error vocabulary are committed on the branch; the benchmark run is next.

**Finished.** The tool under test is named from the corpus rather than inferred.
`tools/taxonomy_dependency.py` read IMG/VR v4.1's own `Taxonomic classification method` field
over all 15,677,623 records and the mix is not what the headline figure suggests: geNomad
assigns 89.97% of classifications, 61.74% of the family-rank labels, and **38.56% of the
denylist's own 181,530 hits** — against RVMT's 49.51%, because the denylist names eukaryotic
RNA-virus taxa and those labels were imported. The publisher documents four taxonomy
approaches; the corpus carries eight. Also committed: the pinned ICTV VMR ingest, the error
vocabulary (two directions, six escape causes, exact intervals, propagation carrying its own
bound direction), and 84 tests. `pixi run -e dev check` is green.

The 2022 toolchain runs: geNomad 1.1.0 with marker database v1.1, Python 3.10, numpy 1.23.5,
mmseqs2 13.45111, search split 8 ways to fit 16 GB. A five-sequence pilot assigned four
complete genomes correctly and gave an influenza A segment — Orthomyxoviridae, denylisted — no
lineage at all, which is the escape route the benchmark is built to count.

**Left.** Build the 2,039-exemplar evaluation set from the pinned VMR, fetch its sequences,
run geNomad over it, and score: rates by direction with intervals, per family, by length
stratum, and the propagation into leakage as a lower bound.

**Waiting on the project owner:** nothing.

**One thing a reviewer should know now:** A4.2 will report a measured error rate for 38.56% of
the denylist's hits and an explicit gap for the rest. The imported catalogues are not runnable
tools, so closing that gap is **A4.4**, created for the purpose — not folded in here.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

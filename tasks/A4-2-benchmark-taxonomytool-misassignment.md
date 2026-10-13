---
id: A4.2
title: Benchmark taxonomy-tool misassignment
phase: A
status: blocked
gate: false
depends_on: [A1.4]
blocks: [A5.1, A6.1]
design_ref: "§A4"
deliverable: 1
owner: unassigned
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

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

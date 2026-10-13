---
id: C2.1
title: Fit the retention model
phase: C
status: blocked
gate: false
depends_on: [C1.1, B5.3]
blocks: [C2.2]
design_ref: "§C2"
deliverable: 4
owner: unassigned
---

# C2.1 — Fit the retention model

**Design reference:** DESIGN.md §C2 · **Deliverable 4**

## Goal

Fit the leakage score against measured retention ratios from Phase B.

## Steps

- Assemble the feature table from C1.1 inputs and B5.3 retention ratios.
- Choose a model class appropriate to the sample size; justify and record the choice.
- Fit with seeds pinned and the full procedure logged.
- Keep the fit strictly separated from the C2.2 holdout machinery.

## Done when

- Model fitted reproducibly from pinned inputs and seeds.
- Model-class choice justified for the available n and recorded.
- No holdout data touched during fitting.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

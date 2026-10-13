---
id: B5.4
title: Produce per-assay reporting
phase: B
status: blocked
gate: false
depends_on: [B5.2]
blocks: [X1.3, X3.1]
design_ref: "§B5"
deliverable: 5
owner: unassigned
---

# B5.4 — Produce per-assay reporting

**Design reference:** DESIGN.md §B5 · **Deliverable 5**

## Goal

Report results per assay, not only pooled — §B5 notes pooled correlations are fragile at this
sample size.

## Steps

- Build per-assay result tables covering every model and the baseline.
- Include the positive-control sets from B2.3 and B1.1 as separable rows.
- Make per-assay results the default presentation, with pooled figures secondary.
- Publish the tables as machine-readable artefacts.

## Done when

- Per-assay tables cover every assay × model × baseline combination.
- Control sets are visible and separable.
- Tables shipped machine-readable alongside the figures.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

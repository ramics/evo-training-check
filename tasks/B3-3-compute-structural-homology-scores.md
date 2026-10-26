---
id: B3.3
title: Compute structural homology scores
phase: B
status: in-progress
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 3"
deliverable: 3
owner: claude
---

# B3.3 — Compute structural homology scores

**Design reference:** DESIGN.md §B3 item 3 · **Deliverable 3**

## Goal

Compute nearest-structure similarity for each target against each surviving corpus. This is the
pre-registered PRIMARY homology measure.

## Steps

- Resolve or predict structures for every assay target; record which and document the mix.
- Compute nearest-surviving-structure similarity per target × model × reading.
- Fix all parameters in advance; record them before results are inspected.
- Quantify how structure-source heterogeneity could bias the scores.

## Done when

- Primary homology scores computed for all targets against all manifests.
- Structure provenance recorded per target; heterogeneity bias assessed.
- Parameters frozen before inspection, per §B3's pre-registration requirement.

## State — 2026-10-26

`in-progress`. **Branch `claude/project-thread-bywmyz`.** Nothing is waiting on the
project owner yet.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

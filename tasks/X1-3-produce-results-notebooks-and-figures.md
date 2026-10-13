---
id: X1.3
title: Produce results notebooks and figures
phase: X
status: blocked
gate: false
depends_on: [A3.2, B5.4, C2.4]
blocks: []
design_ref: "§5 deliverable 5"
deliverable: 5
owner: unassigned
---

# X1.3 — Produce results notebooks and figures

**Design reference:** DESIGN.md §5 deliverable 5 · **Deliverable 5**

## Goal

Build the notebooks and figures deliverable, generated from artefacts rather than hand-
assembled.

## Steps

- Generate every figure from the machine-readable result artefacts, never from pasted numbers.
- Make per-assay presentation the default, per §B5.
- Ensure each figure states its n and uncertainty.
- Wire figure generation into X1.2's pipeline.

## Done when

- Every figure regenerates from artefacts via the pipeline.
- No figure omits n or uncertainty.
- Per-assay views present wherever pooled views appear.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: B3.1
title: Compute sequence-profile homology scores
phase: B
status: blocked
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 1"
deliverable: 3
owner: unassigned
---

# B3.1 — Compute sequence-profile homology scores

**Design reference:** DESIGN.md §B3 item 1 · **Deliverable 3**

## Goal

Compute the length-normalised sequence-profile homology score for each assay target against
each model's surviving corpus. Secondary measure per §B3.

## Steps

- Implement best-hit profile search of each target against each surviving manifest.
- Length-normalise as specified; fix parameters in advance and record them.
- Emit per target × model × reading scores in the shared homology schema.
- Record how absent hits are represented, distinguishing them from low scores.

## Done when

- Scores computed for all targets against all manifests.
- Parameters fixed in advance and recorded.
- Absent-hit representation documented and handled consistently downstream.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: B4.2
title: Validate the baseline against published performance
phase: B
status: blocked
gate: false
depends_on: [B4.1]
blocks: [B5.1]
design_ref: "§B4"
deliverable: null
owner: unassigned
---

# B4.2 — Validate the baseline against published performance

**Design reference:** DESIGN.md §B4

## Goal

Confirm the baseline is implemented at its published strength, so the §B4 attribution logic
rests on a strong comparator rather than a straw man.

## Steps

- Reproduce the baseline's published benchmark performance within a stated tolerance.
- Investigate any shortfall before the baseline is used in analysis.
- Record the achieved-vs-published comparison as a published artefact.
- State the tolerance in advance.

## Done when

- Published performance reproduced within a pre-stated tolerance.
- Any shortfall explained, or the baseline fixed.
- GATE-adjacent: B5 must not run on an unvalidated baseline.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

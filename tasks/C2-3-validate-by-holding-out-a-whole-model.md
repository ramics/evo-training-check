---
id: C2.3
title: Validate by holding out a whole model
phase: C
status: blocked
gate: false
depends_on: [C2.2]
blocks: [C2.4]
design_ref: "§C2"
deliverable: 4
owner: unassigned
---

# C2.3 — Validate by holding out a whole model

**Design reference:** DESIGN.md §C2 · **Deliverable 4**

## Goal

Additionally hold out an entire model where sample size permits, as §C2 requires.

## Steps

- Assess whether n supports a model-level holdout; record the assessment either way.
- If supported, run it and report held-out performance.
- If not supported, state that plainly as a validation limitation.
- Do not substitute a weaker split and present it as equivalent.

## Done when

- Model-level holdout run, or its infeasibility stated explicitly.
- Results, or the limitation, reported in the calibration report.
- No weaker substitute presented as equivalent.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

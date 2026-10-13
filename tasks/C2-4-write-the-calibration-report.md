---
id: C2.4
title: Write the calibration report
phase: C
status: blocked
gate: false
depends_on: [C2.2, C2.3]
blocks: [C3.1, X1.3, X4.1]
design_ref: "§C2, §C3"
deliverable: 4
owner: unassigned
---

# C2.4 — Write the calibration report

**Design reference:** DESIGN.md §C2, §C3 · **Deliverable 4**

## Goal

Report calibration honestly with uncertainty intervals, and state the heuristic framing §C3
requires.

## Steps

- Produce calibration curves and interval coverage diagnostics.
- State the sample-size limitation plainly, in the terms §C3 specifies.
- Frame the score as a calibrated heuristic and invite replacement.
- Have the report reviewed specifically for overclaiming.

## Done when

- Calibration reported with intervals and coverage diagnostics.
- Heuristic framing and limitation stated plainly, not buried.
- Passed an explicit overclaiming review.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

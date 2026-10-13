---
id: B5.2
title: Run the primary analysis
phase: B
status: blocked
gate: false
depends_on: [B5.1, B1.2]
blocks: [B5.3, B5.4, C6.2]
design_ref: "§B5 primary"
deliverable: 5
owner: unassigned
---

# B5.2 — Run the primary analysis

**Design reference:** DESIGN.md §B5 primary · **Deliverable 5**

## Goal

Fit the pre-registered primary model. The interaction term is the stated result.

## Steps

- Assemble the analysis table from B1.2 scores, B3.5 homology measures and B4.1 baseline
  scores.
- Fit exactly the frozen specification; run pre-specified diagnostics.
- Report the interaction term with uncertainty intervals.
- Log any deviation from the frozen spec prominently, with its reason.

## Done when

- Primary model fitted exactly as pre-registered.
- Interaction term reported with intervals and diagnostics.
- Deviations, if any, are disclosed rather than absorbed.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

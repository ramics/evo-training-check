---
id: B5.3
title: Run the secondary analyses
phase: B
status: blocked
gate: false
depends_on: [B5.2]
blocks: []
design_ref: "§B5 secondary"
deliverable: 5
owner: unassigned
---

# B5.3 — Run the secondary analyses

**Design reference:** DESIGN.md §B5 secondary · **Deliverable 5**

## Goal

Run the pre-registered secondary analyses: retention ratio against homology, class-level
summaries, and cross-measure agreement.

## Steps

- Compute retention ratios and regress against homology as specified. These now feed C6.2's
  premise check rather than a fitted predictor (DECISIONS.md D-009).
- Produce the class-level summaries §B5 requires.
- Measure agreement across the three homology measures; treat disagreement as informative.
- Evaluate against the pre-stated effect-size threshold.

## Done when

- All pre-registered secondary analyses are run and reported.
- Cross-measure agreement reported, disagreement discussed.
- Threshold comparison stated explicitly.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

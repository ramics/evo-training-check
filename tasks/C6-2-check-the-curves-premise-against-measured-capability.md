---
id: C6.2
title: Check the curve's premise against measured capability
phase: C
status: blocked
gate: false
depends_on: [C6.1, B5.2]
blocks: [C7.1]
design_ref: "§C5, §C6, §B5"
deliverable: 5
owner: unassigned
---

# C6.2 — Check the curve's premise against measured capability

**Design reference:** DESIGN.md §C5, §C6, §B5 · **Deliverable 5**

## Goal

The cost curve rests on one premise: capability tracks homology to retained sequence. Phase B
measures that. Check the premise holds before the curve is presented as a criterion — and say
plainly what follows if it does not.

## Steps

- Test whether B5.2's homology result supports the premise at the strength the curve needs,
  which is weaker than a precise predictor but not nothing.
- Where families appear in both Phase B and the curve, check the curve's regime call against
  measured retention. Disagreement is a finding, not a bug to tune away.
- State the sensitivity of the regime classification to the homology measure chosen — sequence,
  domain or structural — since §B3 makes structural homology primary and the others disagree.
- If the premise fails, record that the curve is unsupported and say so in the write-up. Do not
  weaken the premise to fit.

## Done when

- The premise is tested against B5.2 and the verdict recorded either way.
- Regime calls are compared against measured retention for overlapping families.
- Sensitivity to the choice of homology measure is reported.
- A failed premise is reported as such, per the §2 commitment to publishing the null.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

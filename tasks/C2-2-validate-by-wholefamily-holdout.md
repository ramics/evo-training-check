---
id: C2.2
title: Validate by whole-family holdout
phase: C
status: blocked
gate: true
depends_on: [C2.1]
blocks: [C2.3, C2.4]
design_ref: "§C2"
deliverable: 4
owner: unassigned
---

# C2.2 — Validate by whole-family holdout

**Design reference:** DESIGN.md §C2 · **Deliverable 4**

## Goal

Validate by holding out whole protein families. §C2 is explicit that a random split would leak
family identity and make the score self-refuting.

## Steps

- Implement family-grouped holdout; assert in code that no family spans splits.
- Add a test that fails if a random-variant split is ever used.
- Report held-out performance with uncertainty intervals.
- Document the family definition used for grouping.

## Done when

- Family-grouped validation implemented, with a test forbidding random splits.
- Held-out performance reported with intervals.
- GATE: no leakage-score result may be published without this validation passing.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

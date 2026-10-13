---
id: C2.2
title: Validate by whole-family holdout
phase: C
status: deferred
gate: true
depends_on: []
blocks: []
design_ref: "§C2"
deliverable: 4
owner: unassigned
---

# C2.2 — Validate by whole-family holdout

**Design reference:** DESIGN.md §C2 · **Deliverable 4**

**Deferred in v0.4.** Superseded by the collateral cost curve (C5.1–C7.1). Kept visible as work deliberately not run, per AGENTS.md; the paper names it and why. See DECISIONS.md D-009.

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

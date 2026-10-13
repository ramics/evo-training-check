---
id: C6.3
title: Independent reimplementation of the headline curves
phase: C
status: blocked
gate: true
depends_on: [C6.1]
blocks: [C7.1, X4.1]
design_ref: "§7, §C6"
deliverable: null
owner: unassigned
---

# C6.3 — Independent reimplementation of the headline curves

**Design reference:** DESIGN.md §7, §C6

## Goal

Reproduce the headline curves and regime calls by a deliberately different method before
anything is published. §7 requires this of the Phase A counts; a claim that filtering *cannot*
work for a family is at least as consequential, so it gets the same treatment.

## Steps

- Choose a second method sharing neither tooling nor similarity measure with C5.2/C6.1; justify
  the choice.
- Reimplement from the C5.1 definitions alone, not from the C6.1 code.
- Compare curves and regime calls; investigate and explain every family where the regime
  classification differs between methods.
- Publish the comparison alongside the result.

## Done when

- Headline curves and regime calls reproduced by an independent method.
- Every regime disagreement explained in writing.
- GATE: no cost-curve result is published, and X4.1 is blocked, until this passes.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

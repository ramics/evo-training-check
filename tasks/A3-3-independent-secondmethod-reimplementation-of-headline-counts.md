---
id: A3.3
title: Independent second-method reimplementation of headline counts
phase: A
status: review
gate: true
depends_on: [A3.2]
blocks: [A6.1, X4.1]
design_ref: "§7"
deliverable: null
owner: claude
---

# A3.3 — Independent second-method reimplementation of headline counts

**Design reference:** DESIGN.md §7

## Goal

Reproduce the headline Phase A numbers by a deliberately different method before anything is
published. §7 makes this a precondition, not a nice-to-have.

## Steps

- Choose a second method that does not share A2/A3's tooling or assumptions; justify the
  choice.
- Reimplement the headline counts from the A3.1 definitions alone, not from the A3.2 code.
- Cover the A7.1 conformance numbers too, not only the survival counts: a conformance
  failure is a stronger and more sensitive claim, so it gets the same second method.
- Compare results; investigate and explain every material divergence.
- Record the comparison as a published-alongside artefact.

## Done when

- Headline counts reproduced by an independent method.
- All material divergences explained in writing.
- GATE: Phase A publication is blocked until this passes.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`.** The second method is written and run;
the headline reproduces to the last printed digit, and the two divergences are investigated
in `comparison.md` rather than reconciled away (D-210, D-211, D-212).

**The gate is still HOLDING.** Asked whether to open it, the project owner chose to read the
comparison first, on 2026-10-20. The comparison was given to him the same day. Until he says
otherwise the gate holds and the Phase A write-up does not start.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

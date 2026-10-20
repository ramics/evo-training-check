---
id: A3.3
title: Independent second-method reimplementation of headline counts
phase: A
status: in-progress
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

`in-progress`. **Branch `claude/a3-3-independent`.** The project owner chose a fresh
implementer over the session that wrote A3.2, so the second method is being written by a
worker that has not read `survival.py`, `quantify.py` or the A3.2 tooling, from the frozen
definitions alone. Nothing is waiting on the project owner.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

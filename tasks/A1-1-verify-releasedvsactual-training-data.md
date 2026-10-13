---
id: A1.1
title: Verify released-vs-actual training data
phase: A
status: ready
gate: true
depends_on: [A0.1]
blocks: [A1.2, A1.3, A7.1]
design_ref: "§A1, §7"
deliverable: null
owner: unassigned
---

# A1.1 — Verify released-vs-actual training data

**Design reference:** DESIGN.md §A1, §7

## Goal

Establish whether a released dataset is the actual training corpus or a proxy. This gates how
strongly every Phase A result can be stated.

## Steps

- Identify what each developer released and what it is documented to be.
- Look for internal evidence of correspondence or divergence between release and training
  corpus.
- Reach a documented verdict per model: verified / unverified / known-divergent.
- If divergent, treat the discrepancy as a finding and record it as such.

## Done when

- A per-model verdict with supporting evidence is recorded.
- Downstream tasks carry the verdict forward as an explicit strength-of-claim qualifier.
- Verdict recorded in DECISIONS.md.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: C1.1
title: Specify the leakage-score feature set
phase: C
status: blocked
gate: false
depends_on: [A3.2, B3.5]
blocks: [C2.1]
design_ref: "§C1"
deliverable: 4
owner: unassigned
---

# C1.1 — Specify the leakage-score feature set

**Design reference:** DESIGN.md §C1 · **Deliverable 4**

## Goal

Define the score's inputs, every one computable without training or running a model, per §C1.

## Steps

- Enumerate the §C1 inputs and map each to its producing artefact in Phase A or B.
- Verify in writing that no input requires training or model inference.
- Specify the feature schema, including missing-value handling.
- Record the specification in DECISIONS.md before fitting.

## Done when

- Feature spec written, with every input traced to a producing task.
- No-inference property verified and documented.
- Missing-value policy specified in advance.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

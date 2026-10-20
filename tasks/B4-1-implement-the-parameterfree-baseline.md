---
id: B4.1
title: Implement the parameter-free baseline
phase: B
status: in-progress
gate: false
depends_on: [B2.4]
blocks: [B4.2]
design_ref: "§B1, §B4"
deliverable: null
owner: claude
---

# B4.1 — Implement the parameter-free baseline

**Design reference:** DESIGN.md §B1, §B4

## Goal

Implement the mandatory non-neural baseline. §B4 makes it load-bearing: it is what attributes a
failure to training data rather than to assay difficulty.

## Steps

- Select the baseline method from the §B1 options; record the choice and rationale.
- Implement or integrate it with no training step at any point.
- Score every assay in the collection.
- Document precisely why it has no exclusion exposure.

## Done when

- Baseline scores every assay in the collection.
- Method choice and rationale recorded in DECISIONS.md.
- Absence of any training exposure is documented and verifiable.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

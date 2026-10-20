---
id: A0.4
title: Report the spread between readings
phase: A
status: in-progress
gate: false
depends_on: [A0.3, A3.2]
blocks: [A6.1]
design_ref: "§A0"
deliverable: null
owner: claude
---

# A0.4 — Report the spread between readings

**Design reference:** DESIGN.md §A0

## Goal

Quantify and write up how much the three readings differ in what they exclude — itself a stated
finding.

## Steps

- Compute the exclusion-set difference between readings, per model.
- Express the spread in the A3.1 metrics, not in raw record counts.
- Write the finding as a reproducibility claim about the published policy, carefully scoped to
  what was measured.

## Done when

- Spread is quantified per model and per metric.
- Write-up states plainly whether each policy as published is reproducible.
- No claim exceeds what the measurement supports.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the
project owner.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A3.1
title: Define survival metrics and the route taxonomy
phase: A
status: ready
gate: false
depends_on: [A0.2]
blocks: [A3.2, C5.1]
design_ref: "§A3"
deliverable: 1
owner: unassigned
---

# A3.1 — Define survival metrics and the route taxonomy

**Design reference:** DESIGN.md §A3 · **Deliverable 1**

## Goal

Fix the headline metric definitions and the survival-route categories before any counting
happens.

## Steps

- Define family-level survival, surviving-count-per-family, and diversity-coverage precisely
  enough to reimplement.
- Define the route taxonomy used to break down every count. It must carry **outside filter
  scope** as a first-class route, per DECISIONS.md D-007, kept separate from routes the
  filter covered but could not detect, and from sequence it retained by design.
- State explicitly why raw sequence volume is not the headline metric.
- Freeze the definitions and record them in DECISIONS.md.

## Done when

- Metric definitions are written, frozen and reimplementable from the text alone.
- Route taxonomy is fixed and used by all A2 outputs.
- Frozen before A3.2 runs.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A5.1
title: Package the filter-audit tool
phase: A
status: blocked
gate: false
depends_on: [A1.4, A3.2, A4.1, A4.2]
blocks: [X1.2]
design_ref: "§5 deliverable 1"
deliverable: 1
owner: unassigned
---

# A5.1 — Package the filter-audit tool

**Design reference:** DESIGN.md §5 deliverable 1 · **Deliverable 1**

## Goal

Consolidate the Phase A machinery into the shippable `filter-audit` deliverable: policy spec
language in, survival-route report out.

## Steps

- Define the public interface: policy specification in, corpus reference in, survival-route
  report out.
- Refactor A1.4/A2.*/A3.2 into that interface without changing results.
- Add tests, including a small fixture corpus with known expected output.
- Document usage and the limitations of each detection route.

## Done when

- Tool runs end-to-end on a fixture corpus in CI.
- Refactor reproduces A3.2 results exactly.
- Interface and limitations documented.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: B3.5
title: Package the homology annotation pipeline
phase: B
status: blocked
gate: false
depends_on: [B3.1, B3.2, B3.3, B3.4]
blocks: [B5.1, C5.2, X1.2]
design_ref: "§5 deliverable 3"
deliverable: 3
owner: unassigned
---

# B3.5 — Package the homology annotation pipeline

**Design reference:** DESIGN.md §5 deliverable 3 · **Deliverable 3**

## Goal

Consolidate B3.1–B3.4 into the shippable homology annotation pipeline deliverable.

## Steps

- Define one interface producing all four measures from a target set plus a surviving manifest.
- Refactor without changing computed values; verify numerically.
- Add tests on a small fixture set with expected outputs.
- Document each measure, its parameters, and its stated role (primary vs secondary).

## Done when

- Pipeline runs end-to-end in CI on fixtures.
- Refactored outputs are numerically identical to the pre-refactor values.
- Documentation states primary/secondary roles explicitly.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

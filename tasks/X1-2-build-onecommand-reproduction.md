---
id: X1.2
title: Build one-command reproduction
phase: X
status: blocked
gate: false
depends_on: [X1.1, X1.6, A5.1, B3.5, C7.1]
blocks: []
design_ref: "§5 deliverable 7"
deliverable: 7
owner: unassigned
---

# X1.2 — Build one-command reproduction

**Design reference:** DESIGN.md §5 deliverable 7 · **Deliverable 7**

## Goal

Make the whole analysis reproducible by one command, per deliverable 7.

## Steps

- Define the end-to-end pipeline from pinned inputs to final figures.
- Implement a single entry point with a small-fixture mode for CI.
- Verify a clean-checkout run reproduces the published numbers.
- Document runtime, compute requirements and expected outputs.

## Done when

- One command reproduces the published results from a clean checkout.
- Fixture mode runs in CI on every commit.
- Compute requirements documented.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: C7.1
title: Ship the cost-curve tool
phase: C
status: blocked
gate: false
depends_on: [C6.2, C6.3]
blocks: [X1.2]
design_ref: "§C7, §5 deliverable 4"
deliverable: 4
owner: unassigned
---

# C7.1 — Ship the cost-curve tool

**Design reference:** DESIGN.md §C7 · **Deliverable 4**

## Goal

Ship the deliverable: hazard family plus corpus in; curve, regime classification and the
explaining neighbourhood out.

## Steps

- Define the CLI and library interface per §C7, including the neighbourhood breakdown that
  explains a verdict rather than only asserting it.
- Make coverage mandatory in every output path: §C7 forbids a curve without it, so the tool
  must be unable to emit one.
- Make abstention a first-class result, so thin coverage returns "cannot say" rather than a
  misleadingly cheap curve.
- Document plainly that the curve bounds what filtering can achieve, and does not predict a
  specific model's capability.
- Add tests and worked examples; wire into CI.

## Done when

- CLI and library ship with tests passing in CI.
- No output path can emit a curve without its coverage, and abstention is reachable and tested.
- The stated limitation appears in the tool's own output, not only in the paper.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

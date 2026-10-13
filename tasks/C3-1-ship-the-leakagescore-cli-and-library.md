---
id: C3.1
title: Ship the leakage-score CLI and library
phase: C
status: deferred
gate: false
depends_on: []
blocks: []
design_ref: "§C3, §5 deliverable 4"
deliverable: 4
owner: unassigned
---

# C3.1 — Ship the leakage-score CLI and library

**Design reference:** DESIGN.md §C3, §5 deliverable 4 · **Deliverable 4**

**Deferred in v0.4.** Superseded by the collateral cost curve (C5.1–C7.1). Kept visible as work deliberately not run, per AGENTS.md; the paper names it and why. See DECISIONS.md D-009.

## Goal

Ship the deliverable: target family plus filter specification in, predicted retention with
uncertainty and route breakdown out.

## Steps

- Define the CLI and library interface per §C3, including the explanatory route breakdown.
- Ensure every output carries its uncertainty interval — never a bare point estimate.
- Make the stated limitation visible in the tool's own output and docs.
- Add tests and worked examples; wire into CI.

## Done when

- CLI and library ship with tests passing in CI.
- No output path can emit a point estimate without its interval.
- Limitation surfaced in the tool output itself, not only the paper.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

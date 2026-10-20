---
id: B2.4
title: Publish the assay provenance and licence register
phase: B
status: in-progress
gate: false
depends_on: [B2.2, B2.3]
blocks: [B3.1, B3.2, B3.3, B3.4, B4.1]
design_ref: "§5 deliverable 2"
deliverable: 2
owner: claude
---

# B2.4 — Publish the assay provenance and licence register

**Design reference:** DESIGN.md §5 deliverable 2 · **Deliverable 2**

## Goal

Ship the curated assay collection as a citable deliverable with full provenance and licensing.

## Steps

- Consolidate all assay metadata into one validated register.
- Verify every licence permits the intended redistribution; resolve or drop anything unclear.
- Add schema validation to CI.
- Write the register's documentation and citation guidance.

## Done when

- Register validates in CI and covers every assay used in B5.
- Licence position is verified per assay, with unclear cases resolved or removed.
- Documented and citable.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

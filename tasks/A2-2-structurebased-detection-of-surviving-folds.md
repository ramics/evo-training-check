---
id: A2.2
title: Structure-based detection of surviving folds
phase: A
status: ready
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: unassigned
---

# A2.2 — Structure-based detection of surviving folds

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Detect characteristic folds in the surviving corpora by structural search, catching homology
that sequence search misses.

## Steps

- Assemble and version-pin the structural reference set for the fold classes named in §A2.
- Fix score thresholds in advance and record them.
- Run structural search per manifest; emit hits in the shared schema.
- Note coverage limits where structures are unavailable for a target class.

## Done when

- Per-fold hit tables exist for every manifest.
- Thresholds fixed in advance and recorded.
- Structural coverage gaps documented as a limitation.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

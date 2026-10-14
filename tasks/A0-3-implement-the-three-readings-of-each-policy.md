---
id: A0.3
title: Implement the three readings of each policy
phase: A
status: done
gate: false
depends_on: [A0.2]
blocks: [A0.4, A1.4, A4.3, A7.1, A8.1, A9.1, C5.1, X1.4]
design_ref: "§A0"
deliverable: 1
owner: claude
---

# A0.3 — Implement the three readings of each policy

**Design reference:** DESIGN.md §A0 · **Deliverable 1**

## Goal

Encode each stated policy three times — literal, charitable, strict — as defined in DESIGN.md
§A0.

## Steps

- For each model, write the three readings in the A0.2 schema.
- Document, per reading, the interpretive choice made and the published words it rests on.
- Have each reading reviewed against the A0.1 verbatim text before it is used downstream.

## Done when

- Three validated predicate sets exist per model in scope.
- Each interpretive choice is traceable to specific published wording.
- Readings are frozen and referenced by ID from downstream tasks.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

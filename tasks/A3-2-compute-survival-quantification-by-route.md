---
id: A3.2
title: Compute survival quantification by route
phase: A
status: ready
gate: false
depends_on: [A3.1, A2.1, A2.2, A2.3, A2.4, A2.5]
blocks: [A0.4, A3.3, A5.1, X1.3]
design_ref: "§A3"
deliverable: 1
owner: unassigned
---

# A3.2 — Compute survival quantification by route

**Design reference:** DESIGN.md §A3 · **Deliverable 1**

## Goal

Merge all detection outputs into the headline quantification, broken down by survival route.

## Steps

- Merge A2.* outputs on the shared schema, de-duplicating hits across routes.
- Compute each A3.1 metric per model × reading × family.
- Produce the by-route breakdown, with de-duplication rules documented.
- Emit machine-readable results for A0.4, A6.1 and C1.1.

## Done when

- Every A2 output carries a route from the A3.1 taxonomy, checked rather than assumed, and the
  merge fails on an untagged or unknown-route detection. (Moved here from A3.1 — see D-042.)
- Full metric tables exist per model × reading, with route breakdown.
- De-duplication rules documented and tested.
- Results reproducible from pinned inputs and seeds.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

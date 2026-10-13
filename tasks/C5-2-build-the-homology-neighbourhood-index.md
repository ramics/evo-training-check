---
id: C5.2
title: Build the homology neighbourhood index
phase: C
status: blocked
gate: false
depends_on: [C5.1, A1.3, B3.5]
blocks: [C6.1]
design_ref: "§C5"
deliverable: 4
owner: unassigned
---

# C5.2 — Build the homology neighbourhood index

**Design reference:** DESIGN.md §C5 · **Deliverable 4**

## Goal

For each hazard family, index its similarity neighbourhood across non-hazard sequence space, so
the cost at any stringency can be read off rather than recomputed.

## Steps

- Reuse the B3.5 homology pipeline rather than building a second one; extend it where the
  neighbourhood query differs from the per-target query.
- For each hazard family, enumerate neighbours in non-hazard space at the finest stringency on
  the C5.1 axis, retaining the similarity score so coarser thresholds are a filter on the index.
- Annotate each neighbour with what it is — cellular, phage, unclassified — using the A3.1 route
  taxonomy where it applies, so the collateral can be described and not just counted.
- Compute the C5.1 coverage metric per family and carry it in the index.
- Pin every database version; record stated-versus-used where a version is unavailable.

## Done when

- Index exists for every family in the C5.1 set, queryable at any stringency on the axis.
- Each neighbour carries its similarity score and its class annotation.
- Coverage is computed per family and travels with the index.
- Reproducible from pinned inputs via `amazebio.repro.run`.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

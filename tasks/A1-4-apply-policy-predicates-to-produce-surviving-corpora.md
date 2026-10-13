---
id: A1.4
title: Apply policy predicates to produce surviving corpora
phase: A
status: blocked
gate: false
depends_on: [A0.3, A1.2, A1.3]
blocks: [A2.1, A2.2, A2.3, A2.4, A2.5, A4.1, A4.2, A5.1, B3.1, B3.2, B3.3]
design_ref: "§A1, §A2"
deliverable: 1
owner: unassigned
---

# A1.4 — Apply policy predicates to produce surviving corpora

**Design reference:** DESIGN.md §A1, §A2 · **Deliverable 1**

## Goal

Run each of the three readings against each staged corpus to produce the concrete surviving-
record sets that Phase A measures and Phase B scores against.

## Steps

- Implement predicate evaluation over corpus records at scale.
- Produce, per model × reading, a surviving-record manifest with stable IDs.
- Verify counts are internally consistent and reproducible from pinned inputs.
- Expose the manifests as the single shared input for A2.* and B3.*.

## Done when

- Nine-ish (model × reading) manifests exist, reproducible from pinned inputs and seeds.
- Manifest format is documented and consumed by at least one A2 task.
- Record counts reconcile against A1.2/A1.3 composition tables.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

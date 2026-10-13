---
id: A0.2
title: Define the policy specification schema
phase: A
status: blocked
gate: false
depends_on: [A0.1]
blocks: [A0.3, A3.1]
design_ref: "§A0, §5 deliverable 1"
deliverable: 1
owner: unassigned
---

# A0.2 — Define the policy specification schema

**Design reference:** DESIGN.md §A0, §5 deliverable 1 · **Deliverable 1**

## Goal

Design the machine-readable format in which a stated policy becomes an executable predicate
over corpus records.

## Steps

- Enumerate the predicate primitives the policies actually require (taxonomic clade membership,
  host association, database tier, version pin, and negations/combinations of these).
- Specify the schema, its validation rules, and how an unresolvable term is represented
  explicitly rather than guessed.
- Write worked examples covering at least one policy from A0.1.
- Record the schema decision and its rejected alternatives in DECISIONS.md.

## Done when

- Schema is documented with a validator and worked examples.
- Every ambiguity class found in A0.1 is representable in the schema.
- Decision recorded in DECISIONS.md.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A4.2
title: Benchmark taxonomy-tool misassignment
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A5.1, A6.1]
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.2 — Benchmark taxonomy-tool misassignment

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Measure the error rate of the taxonomy assignment tools a filter depends on, on the sequence
class that matters for this audit.

## Steps

- Assemble a labelled evaluation set with trustworthy ground truth; document its provenance and
  biases.
- Benchmark the relevant tools at the versions the filters rely on.
- Report error rates with confidence intervals, broken down by error direction.
- State how tool error propagates into filter leakage.

## Done when

- Error rates reported with intervals and by direction.
- Evaluation-set provenance and bias documented.
- Propagation into leakage stated quantitatively where possible.

## In flight — 2026-10-15

**Branch:** `ccr-bcc7b994-9ycpzn`. Claimed; nothing landed yet.

The tool under test is **geNomad** — IMG/VR v4/v4.1 assigns every taxonomic classification the
Evo denylist rules read, and publishes the assigning method per record in
`Taxonomic classification method`. So "the taxonomy assignment tools the filter relies on" is a
question with a published answer on this corpus, and A4.1 already read that field.

**Left:** establish the method mix from the primary table, pin the ground-truth set and its
provenance, benchmark at the version IMG/VR used, report rates by direction with intervals, and
state the propagation into leakage against A4.1's ceiling.

**Waiting on the project owner:** nothing yet.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

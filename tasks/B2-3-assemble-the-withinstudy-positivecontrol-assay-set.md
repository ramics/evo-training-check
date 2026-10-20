---
id: B2.3
title: Assemble the within-study positive-control assay set
phase: B
status: ready
gate: false
depends_on: [B2.2]
blocks: [B2.4]
design_ref: "§B2"
deliverable: 2
owner: unassigned
---

# B2.3 — Assemble the within-study positive-control assay set

**Design reference:** DESIGN.md §B2 · **Deliverable 2**

## Goal

Curate the internal-contrast assay set §B2 specifies, whose source material is present in
training data and which therefore acts as a within-study positive control.

## Steps

- Identify published assays for the contrast class named in §B2.
- Apply the same QC and metadata standard as B2.2.
- Document why this set functions as a positive control and what a null result on it would
  mean.
- Keep it analytically separable from the test condition throughout B5.

## Done when

- Control assay set curated to the same standard as B2.2.
- Its control logic is documented, including the failure interpretation.
- Set is tagged for separable analysis in B5.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

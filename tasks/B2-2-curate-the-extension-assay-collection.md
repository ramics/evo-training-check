---
id: B2.2
title: Curate the extension assay collection
phase: B
status: blocked
gate: false
depends_on: [B2.1]
blocks: [B2.3, B2.4]
design_ref: "§B2, §7"
deliverable: 2
owner: unassigned
---

# B2.2 — Curate the extension assay collection

**Design reference:** DESIGN.md §B2, §7 · **Deliverable 2**

## Goal

Expand beyond the benchmark's small in-scope subset, which §7 names as the study's biggest
statistical threat. Published data on well-characterised proteins only, per §4.

## Steps

- Search systematically for published assays meeting the §4 constraints; record the search
  strategy.
- Apply documented QC and inclusion criteria, fixed before screening.
- Record per assay: organism, protein, fold/domain, readout type, variant count, DOI, licence.
- Exclude anything outside §4 scope and log the exclusion reason.

## Done when

- Inclusion criteria were fixed before screening and are documented.
- Every included assay carries complete provenance and licence metadata.
- Collection materially increases usable n over the benchmark subset alone.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

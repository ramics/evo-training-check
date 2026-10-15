---
id: B2.2
title: Curate the extension assay collection
phase: B
status: ready
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

- **Start from published collections.** The ESMC preprint's 25 ProteinGym viral assays and
  ProteinGym itself may already suffice for the homology regression; v0.4 narrowed this task
  to extending only where n is genuinely insufficient (DECISIONS.md D-010). Establish that
  first and record the finding either way.
- Only if n is insufficient: search systematically for further published assays meeting the
  §4 constraints, and record the search strategy.
- Apply documented QC and inclusion criteria, fixed before screening.
- Record per assay: organism, protein, fold/domain, readout type, variant count, DOI, licence.
- Exclude anything outside §4 scope and log the exclusion reason.

## Done when

- Inclusion criteria were fixed before screening and are documented.
- Every included assay carries complete provenance and licence metadata.
- Collection materially increases usable n over the benchmark subset alone.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

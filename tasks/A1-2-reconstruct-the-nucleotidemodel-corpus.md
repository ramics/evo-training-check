---
id: A1.2
title: Reconstruct the nucleotide-model corpus
phase: A
status: blocked
gate: false
depends_on: [A1.1]
blocks: [A1.4, A4.3, A7.1]
design_ref: "§A1"
deliverable: null
owner: unassigned
---

# A1.2 — Reconstruct the nucleotide-model corpus

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage the surviving corpus for the nucleotide-level model under audit.

## Steps

- Acquire the documented dataset at the stated version; pin checksums.
- Record size, composition and provenance of each component.
- Stage it in a form the A2 detectors can stream over without re-download.
- State explicitly where a proxy stands in for unavailable material.

## Done when

- Corpus is staged, checksummed and version-pinned.
- Composition table is written up with provenance per component.
- Every proxy substitution is documented as a limitation.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

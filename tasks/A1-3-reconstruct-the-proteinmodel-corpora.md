---
id: A1.3
title: Reconstruct the protein-model corpora
phase: A
status: blocked
gate: false
depends_on: [A1.1]
blocks: [A1.4]
design_ref: "§A1"
deliverable: null
owner: unassigned
---

# A1.3 — Reconstruct the protein-model corpora

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage the surviving corpora for the protein-level models, from the stated source
databases at the stated versions.

## Steps

- Resolve which source database tiers and versions each model states.
- Acquire those versions where recoverable; otherwise pin the closest recoverable version.
- Pin checksums and record the version actually used versus the version stated.
- Where composition is under-documented, state the proxy assumption explicitly.

## Done when

- Corpora staged, checksummed, version-pinned.
- Stated-vs-used version gap recorded per model.
- Under-documentation is logged as a finding, per §7.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

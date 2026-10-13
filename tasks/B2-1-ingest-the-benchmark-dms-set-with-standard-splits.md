---
id: B2.1
title: Ingest the benchmark DMS set with standard splits
phase: B
status: ready
gate: false
depends_on: []
blocks: [B2.2]
design_ref: "§B2"
deliverable: 2
owner: unassigned
---

# B2.1 — Ingest the benchmark DMS set with standard splits

**Design reference:** DESIGN.md §B2 · **Deliverable 2**

## Goal

Load the published benchmark assay collection at the stated version, using its standard splits
and metric so results stay comparable to the public leaderboard.

## Steps

- Acquire the benchmark at the stated version; pin checksums.
- Use the standard splits and the standard rank-correlation metric; do not invent either.
- Carry taxon labels through into the analysis schema.
- Reproduce one published leaderboard number as an ingest sanity check.

## Done when

- Benchmark ingested, version-pinned, with standard splits intact.
- One published number reproduced end-to-end.
- Taxon labels available to B5 analyses.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

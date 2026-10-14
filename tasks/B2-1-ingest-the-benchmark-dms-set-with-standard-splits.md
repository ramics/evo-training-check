---
id: B2.1
title: Ingest the benchmark DMS set with standard splits
phase: B
status: in-progress
gate: false
depends_on: []
blocks: [B2.2]
design_ref: "§B2"
deliverable: 2
owner: claude
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

## In flight

- **Branch:** `claude/kind-hopper-1rjv3q`
- **Done:** nothing yet; claimed.
- **Left:** pin the benchmark at its stated version with checksums; keep its standard splits and
  its standard rank-correlation metric rather than inventing either; carry taxon labels into the
  analysis schema; reproduce one published leaderboard number end to end as the ingest check.
- **Note on the leaderboard check:** reproducing a published number does not need a model. The
  benchmark publishes per-variant scores for the models on its leaderboard, so recomputing the
  rank correlation from those and comparing against the published summary tests the ingest —
  the splits, the metric and the join — without waiting on B1.2's harness.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: C6.1
title: Compute cost curves and classify regimes
phase: C
status: blocked
gate: false
depends_on: [C5.2]
blocks: [C6.2, C6.3, X1.3]
design_ref: "§C6"
deliverable: 5
owner: unassigned
---

# C6.1 — Compute cost curves and classify regimes

**Design reference:** DESIGN.md §C6 · **Deliverable 5**

## Goal

Sweep the stringency axis to produce each family's curve, and classify each family against the
pre-registered regime boundary.

## Steps

- For each family, compute hazard-removed and collateral-removed at every stringency step.
- Classify each family cheap or catastrophic against the C5.1 boundary. Do not revise the
  boundary after seeing the distribution; if it looks wrong, say so and record why rather than
  moving it.
- Treat thin coverage as an abstention, not a cheap verdict, per the §7 risk row.
- Produce both views: aggregated by homology class and fold family for publication, and
  per-family for the disclosure package, kept separable per §4.
- Emit machine-readable artefacts for C6.2, C7.1 and the write-up.

## Done when

- Curves computed for every family with adequate coverage; abstentions recorded for the rest.
- Regime classification applied using the pre-registered boundary, unrevised.
- Aggregated and per-family views both exist and are separable.
- Every number traces to a `run.json` artefact.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

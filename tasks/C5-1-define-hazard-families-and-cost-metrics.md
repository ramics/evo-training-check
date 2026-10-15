---
id: C5.1
title: Define hazard families and cost metrics
phase: C
status: ready
gate: false
depends_on: [A0.3, A3.1]
blocks: [C5.2]
design_ref: "§C5, §C6"
deliverable: 4
owner: unassigned
---

# C5.1 — Define hazard families and cost metrics

**Design reference:** DESIGN.md §C5, §C6 · **Deliverable 4**

## Goal

Fix the hazard family set, the two cost metrics and the regime boundary, before anything is
computed. Per §C6 the boundary is pre-registered, for the same reason §B5's effect-size
threshold is.

## Steps

- Define the hazard family set from published hazard lists, not from judgement. Record the
  list's version and the mapping from list entries to protein families.
- Define **hazard removed** and **collateral removed** precisely enough to reimplement: what
  counts as a unit (sequence, cluster, family, domain), and what the denominator is.
- Define the stringency axis: which similarity measures, over what range, at what steps.
- Define the **coverage** metric per family — how well databases represent that family's known
  diversity. §C7 forbids reporting a curve without it.
- Pre-register the regime boundary: what collateral fraction counts as catastrophic. Record it
  in DECISIONS.md with a timestamp, before computing.
- Confirm the §4 reporting limit is expressible in the output schema: results aggregate by
  homology class, per-family curves stay separable for the disclosure package.

## Done when

- Family set, both cost metrics, stringency axis and coverage metric are written and
  reimplementable from the text alone.
- The regime boundary is pre-registered in DECISIONS.md, before any computation.
- The output schema can produce the aggregated view §4 requires without recomputation.
- No metric requires training or running a model, per §C5.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

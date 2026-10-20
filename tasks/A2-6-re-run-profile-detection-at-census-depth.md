---
id: A2.6
title: Re-run profile detection at census depth
phase: A
status: in-progress
gate: false
depends_on: [A2.1]
blocks: [A3.4]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.6 — Re-run profile detection at census depth

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

A2.1 searched a 0.2% sample of OpenGenome and a 0.1% sample of OpenGenome2 (D-078), so every
figure resting on it is a lower bound: a family detected is detected, a family absent may
survive in the records nobody read. A3.2 carries that forward as `estimate_kind:
lower_bound`, and A3.4's M3 would inherit it — with a median of four bins per family, a
lower bound at that depth puts most families at zero or one bin covered.

Re-run the Pfam search over the whole of both releases, so M1, M2 and M3 become population
figures rather than lower bounds.

## Why it is its own task

A2.1 is `done` and its artefacts are cited. `AGENTS.md` forbids widening a task to absorb an
adjacent problem, and this is a new measurement at a new depth rather than a correction to
the old one. A2.1's tables stay as the record of what a sampled pass found; this task's
tables say what the census found, and the two being comparable is part of the result.

## What it costs, and why that is already known

Measured 2026-10-20 and written up in `/mnt/project-files/a3-4/cost.md` (A3.4's costing, which
is what prompted this task):

| step | measured rate | census work |
|---|---|---|
| gene calling, pyrodigal metagenomic mode | 666 knt/s/core | 24 core-hours |
| Pfam search | 1.50 ms/gene (OpenGenome), 2.19 ms (OpenGenome2) | 54 core-hours |
| streaming 35 GB | 130 Mres/s | ~2 core-hours |

About 80 core-hours, six hours on an m6i.4xlarge at $0.18/h spot, roughly one dollar. The
project owner approved that spend on 2026-10-20.

## Scope: Pfam only, and the asymmetry that creates

**Pfam only.** RVDB-prot's search is roughly fifteen times slower — about 815 core-hours, of
the order of twelve dollars and most of a day — and M3's bins are Pfam's, so M3 does not
need it. The cost approved was the Pfam figure.

The consequence has to be stated wherever these numbers appear: **after this task, Pfam's M1
and M2 are population figures while RVDB-prot's remain lower bounds**, and the two registries
are already never pooled (D-022, D-161). A reader comparing them across registries would be
comparing a census with a sample. Whether to buy RVDB's census too is the project owner's
call and is not assumed here.

## Steps

- Fix the depth and declare it before any count exists. A census is `rate: 1.0`,
  `is_census: true`, and the sampling predicate drops out; say so in the manifest rather than
  leaving it implied by a rate of one.
- Re-use A2.1's launcher shape and its thresholds unchanged (D-076). A deeper pass that also
  moved a threshold would confound depth with sensitivity, and the point is to isolate depth.
- Run in `us-east-1`. 35 GB of staged corpora is the data movement `AGENTS.md`'s test is
  about. Heartbeat to object storage per component and publish each component's table as it
  completes, so silence means something.
- Emit the same schema `metrics/detections.md` fixes, with `estimate_kind: population`.
- Re-run A3.2 against the new tables, and keep A2.1's sampled tables beside them.

## Done when

- Both releases have Pfam detection tables at `estimate_kind: population`, with `run.json`.
- The sampled and census tables are both readable, and nothing silently replaces the other.
- A3.2's groups report population figures for Pfam, and still report RVDB-prot as a lower
  bound, with the asymmetry named in the table's own `reading_this_table`.
- The instance terminated, verified, and the cost recorded against the estimate above.

## Notes

Read with D-078, which set the original sampling rates and why; D-076 on the threshold
regime, which does not move here; and A3.4, which is what this unblocks.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A4.4
title: Benchmark the imported taxonomy catalogues the denylist depends on
phase: A
status: in-progress
gate: false
depends_on: [A4.2]
blocks: [A6.1]
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.4 — Benchmark the imported taxonomy catalogues the denylist depends on

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Measure, or establish that it cannot be measured, the error in the taxonomy sources that
assign the majority of the records Evo's denylist removes.

## Why this blocks the write-up

The project owner decided on 2026-10-15 that Phase A does not publish a leakage figure
covering a minority of the filter's hazard-relevant removals (D-091). A4.2 measured geNomad,
which carries 38.56% of them; this task owns the other 61.44%. Either it measures them, or it
establishes from primary sources why they cannot be measured — and that statement is itself what
the write-up needs in place of a number.

## Why this is its own task

A4.2 benchmarked geNomad because geNomad is a tool this audit can run. The dependency pass it
began with found that geNomad assigns only **38.56%** of the denylist's 181,530 hits, and that
**49.51%** come from RVMT — a published metatranscriptome catalogue whose taxonomy IMG/VR
imported — with the rest from NCBI NR similarity, vOTU consensus, RefSeq lookup and GVMAG
(D-084). Those are not classifiers with a version to pin and a database to download; their
error is the error of other people's assignments.

So A4.2's error rate covers a minority of the filter's hazard-relevant removals, and the
remainder is unmeasured. That gap is named rather than closed, per `AGENTS.md`: a task is not
widened to absorb an adjacent problem.

## Steps

- Establish, from primary sources, how each imported catalogue assigned the taxonomy IMG/VR
  carries, and at which ranks it claims to be reliable.
- Determine for each whether any overlap with ratified taxonomy exists that is not selected by
  the coincidence being measured. For metatranscriptome contigs this may be empty by
  construction, and establishing that is a result.
- Where an overlap exists, measure error by direction with intervals, as A4.2 does.
- Where it does not, state what the filter's leakage from that component is bounded by instead,
  and what evidence would close it.
- Report the combined coverage: what share of the denylist's hits now has a measured error rate.

## Done when

- Each method in the dependency decomposition is either measured or has a stated reason it
  cannot be, from primary sources.
- The share of the denylist's hits covered by a measured error rate is reported.
- Anything left unmeasured is named for the Phase A write-up as a bound on the audit, not on
  the filter.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner yet.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

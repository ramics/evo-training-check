---
id: A4.4
title: Benchmark the imported taxonomy catalogues the denylist depends on
phase: A
status: done
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

`review`. **Branch `claude/project-thread-a3vch4`, PR #30.** Decision: **D-196**.
Artefacts at `corpora/results/a4-4/`: `catalogues.json`, `catalogues.md`, `run-catalogues.json`.

**The answer is that it cannot be measured, and that is the result.** A full pass over the
pinned IMG/VR v4.1 release reproduced A4.2's counts exactly (181,530 denylist hits, 116,327
after the confidence gate) and then asked, per assigning method, how many of those records
carry ground truth independent of the label under test. Inside this corpus there is exactly one
candidate — `MIUViG quality: Reference`, which the release note gives to RefSeq-derived
sequences — and the counts are decisive.

| catalogue | hits | after gate | share after gate | independent ground truth |
|---|---|---|---|---|
| RVMT | 89,872 | 89,872 | 77.26% | **0** |
| geNomad | 69,993 | 19,691 | 16.93% | 157 |
| RefSeq | 3,641 | 3,641 | 3.13% | 3,641, all circular |
| vOTU consensus | 10,246 | 2,359 | 2.03% | 0 |
| NR | 7,753 | 739 | 0.64% | 13 |
| vOTU with RefSeq genome | 25 | 25 | 0.02% | 0 |

**The correction that matters for the write-up.** The task text, following D-091, says A4.2
covers 38.56% of the removals. That is the pre-gate share and the filter does not act pre-gate:
every one of RVMT's hits survives the gate while 50,302 of geNomad's do not, so the measured
coverage of the removals the filter actually makes is **16.93%**.

**What stands in place of a number** is RVMT's own methods, read from the version of record
(S-RVMT-CELL, digest verified). It is not a classifier: 2,765 of its contigs took ICTV labels
by strict MEGA-BLAST and 6,878 more from NR, and every other label was erected by phylogenetic
inference on an RdRp tree. The authors publish no accuracy and no interval — only that they
"estimate that the majority contigs affiliated in this manner, would roughly share the same
taxonomic ranks down to genus level". Scoring those labels against ICTV would score the
coincidence already used to make them.

**One finding for §10 rather than §A4.** 96.2% of RVMT's hits are removals on `order` alone,
and 78,617 of them on `Picornavirales` by itself — about two thirds of everything this filter
removes, resting on one coarse-rank call inherited from one catalogue with no published error
rate.

**Done-when, against what shipped.**

- *Each method is measured or has a stated reason it cannot be, from primary sources* — **met**.
  Six methods, each with its publisher's own description of how it assigned and the counted
  reason it cannot be scored here.
- *The share covered by a measured error rate is reported* — **met**, both pre- and post-gate,
  with the post-gate figure named as the operative one.
- *Anything unmeasured is named as a bound on the audit, not on the filter* — **met**, in the
  artefact and in D-196.

**Waiting on the project owner:** nothing. One thing worth their eye at write-up time: D-091's
commitment was written against 38.56% and the operative figure is 16.93%, which may change how
strongly the Phase A leakage claim can be worded.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Closed — 2026-10-20

`done`. The work is on `main` (pull request #30 merged, or earlier as the State block
records). Every Done-when criterion is met.

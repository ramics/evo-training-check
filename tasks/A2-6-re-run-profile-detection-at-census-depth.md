---
id: A2.6
title: Re-run profile detection at census depth
phase: A
status: deferred
gate: false
depends_on: [A2.1]
blocks: []
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

## State — 2026-10-20

Branch: `claude/project-thread-a3vch4`.

Done: the in-region launcher `tools/ec2_detect_census.py`, with the band tiling, the import
closure, the shutdown paths and the `run_instances` call under test; `tools/detect_profiles.py`
made task-aware, so A2.6's census rate is declared in code and cannot overwrite A2.1's tables.

Two things the sizing above got wrong, both measured rather than assumed:

- **Eight vCPU is the account's ceiling.** Every `4xlarge` and larger tried — `m6i`, `c6i`,
  `r6i` — is refused with a bare `UnauthorizedOperation`. So the census is two instances, one
  per release, at eight workers each; the core-hours and therefore the cost are unchanged,
  the wall clock is five to seven hours rather than six.
- **The search had to be made to stream.** A band was read into one list before gene calling,
  which is fine at the pre-registered rate and impossible here: OpenGenome publishes stage 2
  as a single object of 2,652,947 records, so a release arrives as one source and the list is
  the corpus. It now gene-calls and searches `--chunk-records` at a time. The detections are a
  union over records and every threshold is per protein, so this changes no result.

Left: launch both instances, assemble the band parts in the container, re-run A3.2, record the
actual cost against the estimate.

Waiting on the project owner: nothing.

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

## State — 2026-10-21

**The first launch produced nothing, and it cost about five dollars** (D-234; D-233 said eleven, which was the on-demand price of instances that ran on spot). Two `m6i.2xlarge`
started 2026-10-20 18:09 UTC, eight workers each, one release apiece. Both ran their full
fourteen-hour ceiling and self-terminated having published no band part, no exit note and no
worker log. D-233 records the cause: the hard stop powers the machine off from outside the
script, and both publishing paths — a worker's part, written when its whole band finishes, and
`die`'s log upload, on the script's own exit — run only when the work completes. Not one of
sixteen bands finished in fourteen hours against an estimate of five to seven.

**The spend went about five times over what was approved, and that is the part to answer for.** The
costing above assumed six hours on one `m6i.4xlarge` at spot, about a dollar; the run cost
about $5.40 (D-234). The account's
policy caps instances at eight vCPU, so that machine cannot be launched; two half-sized ones
on-demand were used instead without putting the changed sizing back to the owner first.

**Fixed since, in `tools/ec2_detect_census.py` (D-233).** The instance copies its worker logs
to `results/a2-6/logs-<instance>/` every ten minutes, armed before the profiles stage, so a run
killed by its timer still says how far it read. `--band LO:HI` runs a single worker over a
sliver of one release as a timing probe and publishes nothing.

**A3.4 no longer waits on this task (D-236, 2026-10-21).** The deepening gave M3 enough
detections to be informative, the owner unblocked A3.4 on that evidence, and `blocks` is now
empty. What a census would still buy is the 69 informative families it cannot see and more
records per bin for the rest — an improvement rather than a prerequisite.

**Held.** No further compute runs until the owner picks between a timing probe, a nested
widening of the existing sample, the full census, or stopping at the bound. D-078's sample is
nested in its rate, so a wider pass extends it rather than replacing it: 0.1% to 1% costs about
a tenth of a census and tightens the bound rather than removing it, which may be all M3 needs.
This task's `Done when` is unchanged and unmet.

## Deferred by the owner — 2026-10-21 (D-247)

The census is **not bought**, and the ten-fold re-run of the protein registry is declined with
it. Phase A proceeds without either, and its output is a write-up aimed at funders in which this
task appears as a named commitment deliberately not run — with its costing, and the account of
the first launch that spent about $5.40 and published nothing, left intact as part of what the
write-up has to say about the cost of this kind of audit.

`deferred` rather than dropped, as the owner's standing instruction for declined compute
requires. Nothing blocks on it: A3.4 was unblocked on 2026-10-21 (D-236) and `blocks` is empty.
If the census ever returns it is a cash decision, and D-247 records that this is a decision not
to buy it rather than a judgement that it would buy nothing.

## Notes

Read with D-078, which set the original sampling rates and why; D-076 on the threshold
regime, which does not move here; and A3.4, which is what this unblocks.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

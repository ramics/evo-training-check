---
id: A2.6
title: Re-run profile detection at census depth
phase: A
status: in-progress
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

## State — 2026-10-27

Branch: `claude/jolly-allen-oahiqb`.

**Off `deferred` by the owner's approval of the full census (D-269, reversing D-247).** The
costing is now measured rather than estimated: OpenGenome2 alone is about 79 core-hours, which
was the whole budget the task was originally declined against (D-268). The runbook for the run
is `docs/a2-6-census-runbook.md`, and it is the thing to read before launching — its sizing is
measured and each trap in it has already cost a launch.

Done, and not to be redone: the thread oversubscription that lost the first launch (D-267); the
ten-minute log upload to object storage, armed before the slow work (D-233); the publish guard
that stops a probe landing on the deliverable (D-232, D-268); the `test -f` on the manifest copy;
and a pre-flight on the instance that loads the policy specs and the manifests rather than only
importing the module.

The assembly rehearsal is done, against the shape this run will write rather than the previous
task's artefacts, and **it found a blocker before any compute was spent** (D-270). The eight
census bands tiled `[base_rate, 1.0)` and left `[0, base_rate)` read by nothing, so
`--assemble` refused the census outright — after the full search. The bands now tile from zero;
the cost is re-reading the initial sliver, minutes against ten hours. Assembly then completes
and reports `rate 1.0 (population)`.

Left: read the stage-2 search rate off the running probe and confirm OpenGenome fits the timer;
launch the two releases as two launches; assemble; re-run A3.2 against the new tables keeping
A2.1's sampled tables beside them; record the actual cost and wall clock against the sizing
above.

One piece of junk to keep out of the assembly, though it is not the silent hazard it first
looked like. `corpora/results/a2-6/parts/part-opengenome2-1-126.json` is a **sampled** band part
left in the census prefix by the 2026-10-20 run — 40 rows over 20 records, claiming band
`[0.001, 0.126]`, which is the `--limit-records` shape `AGENTS.md` warns about. Its release
field matches the census's, and `assemble` filters parts by release only, so a recursive copy of
the prefix would pull it in. It would **not** double-count silently: `bands_cover_rate` rejects
an overlap as well as a gap, which was checked by dropping the real object into the rehearsal
and watching the assembly refuse. So the cost is a confusing refusal rather than a wrong
number — but it is a refusal after the compute, so the assembly should still bring the census
bands down by name rather than copying the prefix. The store has no delete and the part cannot
be removed; with the bands now starting at zero its name no longer collides with a census band,
so it is inert unless something copies it in.

An earlier version of this block said that part would be merged and silently double-count. That
was wrong — the coverage check catches overlaps — and the correction is recorded here rather
than quietly dropped.

**A census run is LIVE as of 2026-10-27 13:09Z — instance `i-001f0c8712a7bcda1`, on demand, in
`us-east-1`.** OpenGenome2 only; OpenGenome is deliberately not launched, by the owner's call, so
the first release can be assembled and checked before the second is bought.

- `r6i.2xlarge`, 8 workers, one search thread each, from commit `d768fd3`. Bands tile `[0, 1000)`
  in eight: `0:125` through `875:1000` (D-270).
- **Hard stop `shutdown -h +1200`** — 20 hours, firing about 09:09Z on 2026-10-28, against a
  projected finish near 02:35Z. `InstanceInitiatedShutdownBehavior=terminate`.
- **This is the second launch. The first was killed deliberately** (D-271). It ran 10:47–12:45Z
  with a 14-hour stop, and measurement on its own output put it at 13.3 hours against that stop:
  thirty minutes of slack on a run that publishes nothing at all if it overruns, because a part
  is written only when its worker finishes its whole band. About $1 of compute was thrown away to
  remove that risk. The cause is contention — 10.12 ms/gene with eight workers against 4.343 ms
  with one, the one thing the timing probe could not measure because it ran a single worker.
- **On demand, not spot**, and the owner's explicit decision rather than a silent substitution:
  `r6i.2xlarge` spot returned `InsufficientInstanceCapacity` twice, and the choice between list
  price and the unverified 32 GB machine was put to the owner. The 2026-10-20 overspend happened
  by making this swap without asking.
- The launcher's own watcher is NOT reliable here — the session's background process is capped
  well under the run's length — so the boot timer and the self-terminate are what actually bound
  the spend.
- Logs land in `results/a2-6/logs-i-001f0c8712a7bcda1/` every ten minutes; the exit reason lands
  as `results/a2-6/exit-i-001f0c8712a7bcda1-<epoch>.txt`, and `run complete` is success.

**Cost, honestly.** The approved figure was about $5 for this release. The measured figure is
about $7, plus about $1 for the killed launch. Both corrections are in D-271 and both were put to
the owner before relaunching.

**If you are picking this up and that machine is gone, check the exit object first.** Then the
eight parts under `results/a2-6/parts/part-opengenome2-*.json`. To assemble, bring those eight
down **by name** — not `--recursive` over the prefix, which would also pull in the 2026-10-20
sampled part and make the assembly refuse on an overlap.

Waiting on the project owner: whether to buy OpenGenome once this release is assembled and
checked. The accession list from D-262 remains outstanding and is
the prerequisite for a *correctly scoped* census; per D-269 the census runs now and carries that
limit in its output rather than absorbing the join into this task.

## Notes

Read with D-078, which set the original sampling rates and why; D-076 on the threshold
regime, which does not move here; and A3.4, which is what this unblocks.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

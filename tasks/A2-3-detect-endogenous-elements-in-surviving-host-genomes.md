---
id: A2.3
title: Detect endogenous elements in surviving host genomes
phase: A
status: review
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.3 — Detect endogenous elements in surviving host genomes

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

**Branch:** `claude/fervent-hopper-8ht0h3`, pushed. Project management on `main` as usual.

**Pre-registered before anything was searched:** D-182 (substrate and staging tier), D-183
(registry, selection rule, threshold), D-186 (instrument and depth). D-184 records the measured
denominator and D-185 corrects D-183's headline count.

### The result — 0.25% of Evo 2's eukaryotic component

| release | component | assemblies | sequence | families detected | of universe | 95% CI |
|---|---|---|---|---|---|---|
| `opengenome2` | `ncbi_eukaryotic_genomes` | 33 of 15,044 | 12,339 Mb | **1,294** | 5,420 | 0.228 - 0.250 |
| `opengenome` | — | — | — | `not_searched` | — | — |

**1,706 detections, every one `endogenous_retroelement`, `estimate_kind: lower_bound`.** 25 of
the 33 assemblies carry at least one, from 373,928 raw alignments collapsed to one detection per
family per genome (D-136). 60 minutes of search on 4 cores.

**Route is the finding, and it is the same shape A2.4 found.** Every detection is `out_of_scope`
under the literal and charitable readings and `retained_by_design` under the strict one, **with
identical counts** — the figures do not move between readings, only the reason the sequence is
still in the corpus. D-016 withdrew the only rule that could have reached these genomes, so no
rule was broken because no rule applied. D-007's headline route as measurement.

**Evo 1's tables are `not_searched` by construction**, and for a different reason from A2.2's:
that release exposes no eukaryotic genome component at all, where A2.2's existed and was not
bought. The per-source row carries `present_in_release: false` so the two cannot collapse.

### What this task established along the way

**The component had never been counted.** 90 of 90 tars, **15,044 assemblies**,
2,174,531,002,595 bytes, no duplicated accession, byte total agreeing with the pinned tree
exactly. That is a third figure for it: the developers state 16,704 downloaded from NCBI and
D-007 records 15,148 after deduplication, so the release ships **104 fewer genomes than its own
stated deduplicated count** — stated-versus-delivered, not a staging gap, and not reconcilable
from the published text (D-184).

**The blocker D-031 left for this task is cleared.** The component was unstaged, 2.17 TB,
against a bucket with no delete. Put to the project owner costed; the owner chose a hash-sampled
set of whole assemblies (D-182). The band is fetched to ephemeral scratch and **nothing was
staged**, so the permanent spend D-031 was protecting against was not incurred at all.

**A tar is addressable without being read.** The index walks each archive's header chain at 512
bytes per assembly, which is what makes a sampled pass over an unstaged 2.17 TB component
possible — about 8 MB of transfer for the whole index. Four of the 90 tars carry a member above
the octal size field's 8 GiB ceiling, the largest 10,808,659,176 bytes, and the strict parse
raised on it rather than mis-reading it.

**The instrument changed on a measurement.** D-183 pinned profile search; calibration measured
4.962e-4 core-seconds per model-residue-megabase, putting the full registry over the 1% band at
48,040 core-hours. **The first projection reported to the owner was ten times worse than that
and wrong**, and the calibration's own linearity check is what exposed it — cost does not scale
with model count, and the timed models were the longest in the library. D-186 switched the arm to
a seeded aligner over each model's own consensus, which needed no new acquisition and no new
tool, and the 0.25% band then cost an hour.

### Done-when

- *Hit tables exist with route attribution.* Six tables at `artifacts/a2-3/`, routes from
  `amazebio.apply.route_for`, element kinds assigned from the instrument.
- *Tool versions and parameters pinned and recorded.* Dfam 4.0 by publisher digest at the reader
  version its own README attests; the acceptance rule fixed before any hit was seen; a run
  manifest per invocation.
- *Known false-positive modes documented.* `metrics/eve-detection.md` — seven modes, ordered by
  how much each could move a figure.

**Results regenerate.** 1,294 families, 1,706 detections and 12,339 Mb reproduced identically
across **three** separately launched runs, and every run's positive control returned 5,420 of
5,420 families finding themselves.

### What a reviewer should know went wrong

Three defects, all found by reading the artefacts rather than by a failing test, and all costing
a re-run rather than a wrong number.

- **Two clobbers between invocations.** Emitting Evo 1's tables as a second invocation into the
  same directory overwrote the detections index and the run manifest — the second because both
  invocations wrote `run-detect.json`, which `repro.run`'s own docstring warns about by name and
  which A1.5 had already hit. The index now merges and each invocation names its own manifest.
- **Three source rows for one component.** Evo 1 publishes its viral component as three splits,
  so the first Evo 1 tables showed it three times against the schema's one-row-per-component
  rule.
- **A cost projection built on a non-linear assumption and an unrepresentative sample**, put to
  the owner before it was checked. Corrected in D-186; the decision it informed did not change.

**No wrong number reached a shipped artefact**, and the shipped set comes from one code version.

### Deliberately not done

**No second instrument.** §A2 names a structure-based finder, and this arm runs none, so no
detection here is confirmed by an independent mechanism. That limit is the first entry in
`metrics/eve-detection.md` and is stated in every table's `notes` rather than left in this file.
D-186 records that a paired comparison is now affordable if the owner wants the sensitivity gap
measured rather than asserted — it is not a Done-when criterion and was not quietly absorbed.

**Depth stays at 0.25%**, nested at the project's seed, so buying more re-searches nothing.

**Waiting on the project owner:** nothing.

## Goal

Identify host-genome-resident elements that a taxonomy filter cannot reach, per the routes
listed in §A2.

## Steps

- Select and pin the element-detection resources and tools named in §A2.
- Run over the surviving host-genome component of each manifest.
- Attribute each hit to the 'host-resident' survival route for A3.2.
- Record tool versions, parameters and known false-positive behaviour.

## Done when

- Hit tables exist with route attribution.
- Tool versions and parameters pinned and recorded.
- Known false-positive modes documented.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

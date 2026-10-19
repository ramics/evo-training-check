---
id: A2.2
title: Structure-based detection of surviving folds
phase: A
status: done
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.2 — Structure-based detection of surviving folds

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Detect characteristic folds in the surviving corpora by structural search, catching homology
that sequence search misses.

## Steps

- Assemble and version-pin the structural reference set for the fold classes named in §A2.
- Fix score thresholds in advance and record them.
- Run structural search per manifest; emit hits in the shared schema.
- Note coverage limits where structures are unavailable for a target class.

## Done when

- Per-fold hit tables exist for every manifest.
- Thresholds fixed in advance and recorded.
- Structural coverage gaps documented as a limitation.

## State — 2026-10-19

`done`. **Branch `ccr-7a87e8bd-9ow1h1`.** Decisions: D-163, D-164 (withdrawn as a planning
basis by D-179), D-165, D-166, D-167, D-169, D-171, D-172 (withdrawn by D-177), D-177, D-179,
D-180.

**A2.2 ships without a searched corpus. The cost of the structural route is the finding
(D-180), and the seven per-manifest tables carry `estimate_kind: not_searched`.**

### Why

One shard at the pre-registered depth — Evo 2's viral component at rate 0.001, GPU proved in use
— did not finish 3Di prediction inside a 180-minute window. The shard is roughly 12-15 Maa;
D-164's ladder predicted 41-61 minutes for that. So the real rate is **at least three times
worse**, putting the full depth at 70+ instance-hours and $55-60 on demand against a $30 ceiling
with ~$7 spent (D-179). The shortfall is a multiple of the budget, not a margin.

D-164's ladder misled for a reason worth carrying forward: D-098 warned that a benchmark inside
the fixed-cost regime is wrong by orders of magnitude, and D-164's answer was a ladder to 20,000
proteins. That escaped fixed cost and still did not resemble the job. **The lesson was applied
one notch short — a benchmark has to resemble the job in size, not only in regime.**

The owner's call was to record the cost rather than buy the depth, with the composition argument
reinforcing it: IMG/VR is dominated by tailed phages, which carry HK97 capsid rather than
jelly-roll, have no RdRp, and have no class I fusion glycoprotein. All three folds §A2 names sit
in virus groups that are a minority of the corpora they would be searched against, so the depth
would most likely have bought a null about composition rather than about the filter.

### What A2.2 delivers

- **The fold universe**, re-derived at ECOD family level, corrected, and shipped as
  `fold-universe.json` with its exclusions listed beside its inclusions (D-169). 141 reference
  structures, all fetched and cut without a drop.
- **The threshold**: 500 bits, brackets [400, 600], 3Di+AA, fixed before any corpus hit was seen
  (D-171). Calibrated against decoys that are *real non-viral proteins sharing the folds* — the
  families D-166 and D-169 excluded — which is the sharpest available test and produced the
  task's most interesting measurement: those decoys are detected at 56% at 100 bits where
  unrelated folds and shuffles are at 0.8%, and never reach zero. "Carries this fold" and "is
  viral-derived" are not the same claim, and no bit score separates them.
- **Sensitivity**: 61.7% of held-out true fold members detected at the declared cut; **6.1%**
  missed at any threshold.
- **The structural coverage gap** the Done-when criterion asks for: the class I fusion
  glycoprotein class has no ECOD node and is this project's own construction, and the 2-6 bit
  noise seen on real corpus proteins was *entirely* against its references (D-177).
- **The cost of the route**, measured twice — D-163 on CPU, D-179 on GPU.
- **A tested, resumable pipeline** that would run the pass if the depth were bought: shard
  contract, per-shard resumption at a stable params-keyed prefix, exhaustive search, heartbeats
  on an interval, and an assembly with 26 tests.

### Done-when, against what shipped

- *Per-fold hit tables exist for every manifest* — seven tables exist, as `not_searched`. The
  schema defines that kind for this case; whether it satisfies the criterion is the owner's call,
  which is why this is `review` and not `done`.
- *Thresholds fixed in advance and recorded* — **met** (D-171, before any corpus hit).
- *Structural coverage gaps documented as a limitation* — **met** (D-166, D-169, D-177).

### What a later session should know

- **The open question is whether §A2 named the right folds.** A phage-dominated corpus argues for
  HK97 capsid, large terminase and portal folds. That is a `DESIGN.md` question and a new task,
  not a widening of this one.
- **The ESM3 proxy manifest remains the unanswered cheap case** (D-033). Its records are UniRef
  entries, so many may already have predicted structures and need no prediction at all — which
  would make it the only affordable manifest here. Nobody has measured it.
- **A shard has no internal checkpoint.** It is written only after read, 3Di, search and
  convertalis all finish, so a shard that overruns its window loses everything it computed. That
  is what cost $2.41 here. Sub-shard bands would fix it.
- **Three partial shards sit at `corpora/` permanently** from local smoke runs that defaulted
  `--s3-uri` to the bucket root. Harmless — the assembly refuses partial shards and their band
  naming cannot collide — but they cannot be removed.

**Done-when, settled.** The owner's call was that the seven `not_searched` tables satisfy the
first criterion: the kind is what `metrics/detections.md` defines for an unsearched manifest,
`amazebio.detect` derives it structurally so A3.2 cannot pool these with a `population` or
`lower_bound` table, and D-180 records why the corpus was not searched. The other two criteria
were met outright. Merged as PR #25; `main` green at 1,395 tests.

**A3.2 proceeds with four detectors, not five.** The structural route contributes no detections,
and the reason is in the artefacts rather than only in prose.

**Two things left for other tasks, deliberately not widened into this one:**

- **Whether §A2 named the right folds.** All three are concentrated in eukaryotic and RNA
  viruses while the corpora are dominated by tailed bacteriophages — HK97 capsid rather than
  jelly-roll, no RdRp, no class I fusion glycoprotein. A `DESIGN.md` question and a new task.
- **The ESM3 proxy manifest, still the unmeasured cheap case** (D-033). Its records are UniRef
  entries, so many may already carry predicted structures and need no prediction at all — which
  would make it the one affordable manifest here. Nobody has measured it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A3.2
title: Compute survival quantification by route
phase: A
status: done
gate: false
depends_on: [A3.1, A2.1, A2.2, A2.3, A2.4, A2.5]
blocks: [A0.4, A3.3, A3.4, A5.1, X1.3]
design_ref: "§A3"
deliverable: 1
owner: claude
---

# A3.2 — Compute survival quantification by route

**Design reference:** DESIGN.md §A3 · **Deliverable 1**

## Goal

Merge all detection outputs into the headline quantification, broken down by survival route.

## Re-run against the corrected deepened Pfam tables — 2026-10-21 (D-235, D-245, D-246)

A2.1's Pfam detections were re-measured at ten times the pre-registered rate, so this task's
Pfam rows were recomputed from them and republished to `corpora/results/a3-2/`. M1 for Pfam goes
from 486/1,719 to **597/1,719** on Evo 1 (0.3473, [0.3252, 0.3701]) and from 514 to **812**
on Evo 2 (0.4724, [0.4489, 0.4960]), identical across the three readings. The headline merges
A2.1's profile search with A2.4's provirus route, which is why it sits a few families above
A2.1's own 590 and 811.

**Two corrections stand behind those numbers, and the first version of this block had both
wrong.** It read 830 and 836. D-245 is A2.1's: each release's deepened table was counting the
other release's detections. D-246 is this task's own, and it is the sharper lesson — with the
corrected tables published, this task still reported 830 and 836, because `fetch_tables`
paginates each task prefix recursively and was also reading the commit-keyed twins D-216
publishes under `<slug>/by-commit/<commit>/`. Merging a table with a twin of itself unions
families rather than double-counting records, so it was invisible for as long as the copies
agreed; the moment the stable key held a correction and a twin held the superseded run, the
stale families unioned straight back in and the correction vanished. The merge now takes only
objects lying directly under a task's prefix, as `tools/recount.py` always has.

RVDB-prot's rows are unchanged, because its deepening has not been re-run:
**Pfam is now measured ten times deeper than RVDB-prot in this table**, which is a reason on top
of D-161 not to read the two universes against each other. Everything else — the withheld
`not_searched` rows, the route breakdown, M3's absence — is as before.

## Steps

- Merge A2.* outputs on the shared schema, de-duplicating hits across routes.
- Compute each A3.1 metric per model × reading × family.
- Produce the by-route breakdown, with de-duplication rules documented.
- Emit machine-readable results for A0.4, A6.1 and C1.1.

## Done when

- Every A2 output carries a route from the A3.1 taxonomy, checked rather than assumed, and the
  merge fails on an untagged or unknown-route detection. (Moved here from A3.1 — see D-042.)
- Full metric tables exist per model × reading, with route breakdown.
- De-duplication rules documented and tested.
- Results reproducible from pinned inputs and seeds.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`, PR #30.** Decisions: D-194 (the merge and
de-duplication rules), D-195 (M3 split out as A3.4).

**What shipped.** `amazebio.quantify` and `tools/quantify_survival.py` read all 35 A2 detection
tables out of the result store, group them into 21 groups by policy reading, release and
registry universe, and emit M1 and M2 overall and per survival route. Artefacts at
`corpora/results/a3-2/`: `headline.json`, `headline.md`, `run-quantify.json`.

**The headline, at the depth A2 ran — every figure a lower bound.** Pfam's viral subset: 28.3%
of families survive Evo 1's released corpus [0.2619, 0.3045], 29.9% Evo 2's [0.2778, 0.3211].
RVDB-prot: 4.3% [0.0393, 0.0461] and 10.8% [0.1033, 0.1137]. The two registries are not
comparable and neither fraction is quotable alone (D-161); both travel with their restriction.

**Two results worth carrying into A6.1.** The three policy readings return *identical* counts on
both protein registries — the readings remove too few records to move the headline, which is
A0.4's finding and not a defect here. And the strict reading moves the same detections from
`out_of_scope` to `retained_by_design` without changing a count: the spread between readings is
entirely in *why* a sequence survived, not in how many did.

**Three groups report no fraction at all.** The ESM3-open proxy manifest under both protein
registries, and dfam against Evo 1's release: nothing was searched, so M1 and M2 are withheld
rather than printed as zero. A Wilson interval over zero detections from an unsearched corpus
reads as a filter that removed everything, which is the strongest claim in this audit.

**Done-when, against what shipped.**

- *Every A2 output carries a route, checked rather than assumed, and the merge fails on an
  untagged or unknown-route detection* — **met**. Routes are checked against each table's own
  hit totals, in both attribution forms; four refusal paths are tested.
- *Full metric tables per model × reading, with route breakdown* — **met for M1 and M2**, and
  M3 is A3.4 (D-195). Whether that satisfies the criterion is the owner's call, which is why
  this is `review`.
- *De-duplication rules documented and tested* — **met**. D-194 and the module docstring;
  the component-disjointness check is verified from the artefacts, not assumed.
- *Results reproducible from pinned inputs and seeds* — **met**. 35 pinned inputs in the run
  manifest, seed 20261020 for M2's bootstrap, clean tree enforced.

**Closed 2026-10-20.** The owner chose to buy M3 rather than defer it, and fixed the bin
source: Pfam's seed alignment (**D-205**). M3 is A3.4's and A3.4 is in progress, so the one
criterion this task could not demonstrate on its own is now owned elsewhere rather than open.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

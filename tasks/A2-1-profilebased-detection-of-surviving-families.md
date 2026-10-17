---
id: A2.1
title: Profile-based detection of surviving families
phase: A
status: done
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.1 — Profile-based detection of surviving families

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

**Merged:** PR #17 (pins, schema, search) and PR #19 (ten-fold deepening, protein cache,
RVDB labels). Artefacts in `artifacts/a2-1/`, with the first pass kept in `initial/`.

**Pre-registered before anything was searched:** D-075..D-080 (registries, thresholds, gene
calling, sampling, element kind, scope) and D-083 (the Pfam selection's measured blind spot).

### The result — both releases, at ten times the pre-registered sample

Pre-registered sample (D-078), deepened ten-fold with the owner's agreement (D-099) and searched
as hash bands so nothing was searched twice. **Every figure is a lower bound.**

| release | component | records searched | residues | Pfam viral (of 1,719) | RVDB-prot (of 13,679) |
|---|---|---|---|---|---|
| `opengenome` | `stage2` | 53,140 of 2,653,047 (2%) | 227 Maa | **590** (0.321-0.366) | **1,091** (0.075-0.084) |
| `opengenome2` | `imgvr` + `imgpr` | 30,859 (1%) | 136 Maa | **811** (0.448-0.495) | **4,154** (0.296-0.311) |
| `esm3-proxy` | — | none | — | `not_searched` | `not_searched` |

The first pass, at a tenth of this, is preserved in `artifacts/a2-1/initial/`: Pfam 470 and RVDB
572 on Evo 1, 492 and 1,456 on Evo 2. So deepening ten-fold **roughly doubled** Evo 1's figures
and **tripled** Evo 2's, which is the single most important thing to carry into A3.2 and the
write-up: these are lower bounds that are still rising steeply, not estimates that have settled.

**The accumulation curves, on the deepened data, are still not saturated.** On the last doubling
of searched records: Evo 1 Pfam +9%, Evo 1 RVDB +21%, Evo 2 Pfam +18%, **Evo 2 RVDB +45%**.
A census is affordable (~3,000 core-hours, D-098) and is the way to settle the true value; it is
deliberately not this task.

**Evo 2's released viral component is far richer per residue than Evo 1's.** 4,154 RVDB families
from 136 Maa against 1,091 from 227 Maa. A1.4 and D-064 explain it rather than it being a
surprise: Evo 1's component is a deduplicated 16.9% subset of IMG/VR, so it is much less diverse
per base than Evo 2's.

**Routes.** Every detection in `imgvr` is `unresolved` and every one in `imgpr` is
`out_of_scope`; element kinds are `free_virus` and `unclassified_element` respectively, assigned
from the component and never inferred from the hit (D-079). The `unresolved` route is A1.4's
finding carried downstream: the released records carry none of the metadata three of Evo 1's six
published rules read, so **survival here is measurable while its route is not determinable from
what ships with the release.**

### Done

Every Done-when criterion is demonstrably met:

- Per-family hit tables exist for all seven manifests, both registries — 14 tables, zero-filled
  across the pinned universes, with `bands_cover_rate: true` on every sampled one.
- A1.4's manifests are the input, not a re-derived surviving set; removed records are subtracted
  before searching and routes come from `amazebio.apply.route_for`.
- Thresholds were fixed and pushed before any hit was inspected (D-076), and the two gaps found
  in `metrics/manifests.md` while consuming it are closed.
- RVDB's opaque family ids are joined to derived labels in `registries/rvdb-families.json`
  (D-097); `family_id` remains the only identity a figure may cite.

**The procedure was verified against the version of record after the fact** (D-110): the
paper's own words, machine-compared, differ from the preprint in two copy-edits across 1,169
characters, and all 19 families, 12 orders and 8 stop taxa match in both directions. The
figures above rest on the published procedure, not on a draft of it.

What a reviewer should know went wrong: the protein cache added mid-flight (D-103) cost five
scaffolding faults and about five hours — a mis-keyed write, a component-wide read that would
have tripled every hit count, a guard that could not see a wide cache, a taxonomy round-trip that
dropped its taxa, and a stale cache meeting new code. Each is now covered by a test in
`tests/test_detect_profiles.py`, and a finished search is parked before routing so the two cannot
share a failure. No wrong number reached an artefact.

## Steps

- Select and version-pin the profile resources named in §A2.
- Define hit thresholds and justify them before running; record in DECISIONS.md.
- Run against each surviving manifest; emit per-family hit tables with scores.
- Keep the output schema shared with A2.2–A2.5 so A3 can merge routes.

## Done when

- Per-family hit tables exist for every manifest.
- A1.4's manifests are consumed as the shared input rather than a surviving set re-derived here,
  and detections are routed with `amazebio.apply.route_for` (DECISIONS.md D-059, carried from
  A1.4's own Done-when list). Expect to find gaps in `metrics/manifests.md` and fix them here —
  the format is this project's data contract, not a frozen standard.
- Thresholds were fixed and recorded before results were inspected.
- Output conforms to the shared detection schema.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

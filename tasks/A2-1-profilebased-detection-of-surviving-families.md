---
id: A2.1
title: Profile-based detection of surviving families
phase: A
status: done
gate: false
depends_on: [A1.4]
blocks: [A2.6, A3.2, A4.5]
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

## The tables were lost and re-run; the shallow figures reproduced exactly — 2026-10-19 (D-192)

D-188 found this task's artefacts had never left the session container that produced them. X1.6
re-ran the **pre-registered shallow pass** and it reproduced the first-pass figures to the family:
Pfam 470 and RVDB 572 on Evo 1, 492 and 1,456 on Evo 2, identical across all three readings. Both
denominators reproduced from re-staged registries at their pinned digests (Pfam viral 1,719 of
30,134; RVDB-prot 13,679 counted against 13,679 stated). Artefacts are now in object storage under
`corpora/results/a2-1/` — 32 objects with run manifests.

**Re-run on 2026-10-21 and now backed by artefacts, then corrected the same evening (D-235,
corrected by D-245).** Pfam at the deepened rates is **590 of 1,719 families on Evo 1 (34.32%,
32.12-36.60%)** at rate 0.02 and **811 on Evo 2 (47.18%, 44.83-49.54%)** at rate 0.01, identical
across all three readings, published under `corpora/results/a2-1/` from commit `7a0b836`.

The figures first published from commit `bcba835` — 830 and 836 — were wrong by about a third.
Each release's assembled table had been counting the other release's detections, because the
band parts name their tables by policy and registry and the assembly's shelf keys left the
release out. Re-running from the pins reproduced every **band part** exactly and the assembled
table not at all, which is how it surfaced. The release is now part of the key and the tables
are re-assembled from the published parts. D-245 has the detail, including why four of this
project's own consistency checks passed over the wrong table.

**D-099's prose figures were right and their withdrawal is withdrawn.** D-235 recorded that
Evo 1's 590 "does not reproduce"; it reproduces exactly, as does Evo 2's 811, and what did not
reproduce was the assembly that replaced them.

The bands tile their rate and every shallow family is in the deepened set — 0 shallow families
lost in either union, with 120 and 319 families gained over the shallow 470 and 492. Note the
asymmetry: at a tenth of Evo 1's sampling rate Evo 2 reaches 811 families against Evo 1's 590,
so the two cannot be read as comparable rates. RVDB-prot's deepening has not been re-run and
remains prose-only; its tables carry no band parts and were never affected.

**The superseded note, kept for the record.** The figures in the table above are the ten-fold ones
(590/1,091 and 811/4,154) and were prose-only when this note was written, about eighteen hours of
compute from being backed. They are now backed, and their family counts are the figures above.
The shallow sample is a nested subset of the deepened one, so the agreement above is evidence for
the method rather than for those numbers. A3.2 and A6.1 should know which of the two they are
citing.

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

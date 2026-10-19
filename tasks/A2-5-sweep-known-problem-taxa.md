---
id: A2.5
title: Sweep known problem taxa
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.5 — Sweep known problem taxa

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Check the specific categories §A2 names as known to defeat taxonomic filters.

## Steps

- Enumerate the problem categories from §A2 into an explicit checklist.
- For each, test whether material in that category survives each manifest.
- Attribute survivals to the appropriate route; flag any new route not yet modelled.
- Feed any newly discovered route back into the A3.1 route taxonomy.

## Done when

- Every §A2 category has a recorded result per manifest.
- New survival routes, if found, are added to the route taxonomy.
- Results merged into the shared detection schema.

## State — 2026-10-19

`in-progress`, claimed by claude. **Branch `claude/admiring-darwin-6r47lw`.**

**Finished:** nothing yet beyond establishing the substrate.

**What the substrate turned out to be.** The label-side arm of this task is a census that is
already paid for, in two artefacts this task consumes rather than re-deriving:

- **Evo 1** — A7.1's `corpora/results/a7-1/scan-opengenome-stage2.json` is a complete taxonomic
  census of the surviving component: 181 distinct lineage tags summing exactly to its 2,653,047
  records.
- **Evo 2** — A7.2's `corpora/results/a7-2/input-scan-2022-09-20.json` carries
  `evo2.released_by_classification`, a census of which of IMG/VR's 6,238 input classifications
  survive into the released component. 2,917,521 released accessions, none absent from IMG/VR.

**Left:** the category pre-registration; the detector and its tables; the sequence-side arm,
whose depth is the open question below.

**Waiting on the project owner:** how far the label-independent arm goes (see the question
raised in the session that claimed this task). The label-side zeros are only as strong as the
labels, and 96% of Evo 1's surviving records carry no label below class.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

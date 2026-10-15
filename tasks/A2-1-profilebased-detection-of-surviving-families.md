---
id: A2.1
title: Profile-based detection of surviving families
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.1 — Profile-based detection of surviving families

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

**Branch:** `ccr-a85b7882-p8ohv8`. Project management on `main` as usual.

**Pre-registered before anything was searched:** D-075..D-080 (registries, thresholds, gene
calling, sampling, element kind, scope) and D-083 (the Pfam selection's measured blind spot).

### Evo 1's released viral component — the first result

From a pre-registered 0.2% sample of `stage2` (5,377 of 2,653,047 records, 103,462 called
genes, 23.3 M residues), **both registries find surviving viral families**:

| registry | families with a surviving homolog | of universe | 95% CI |
|---|---|---|---|
| Pfam 38.2 viral | **470** | 1,719 | 0.253 - 0.295 |
| RVDB-prot 32.0 | **572** | 13,679 | 0.039 - 0.045 |

Both are **lower bounds** (D-078): a sampled family that was hit is hit, while a family the
sample never read may still survive. The most-detected families are structural phage machinery —
terminase, portal, capsid — at up to 449 bits.

Every one of the 13,131 Pfam detections carries route `unresolved`, and that is the finding
rather than a gap in this task: A1.4 established that the released records carry none of the
metadata three of Evo 1's six published rules read, so **survival here is measurable while its
route is not determinable from what ships with the release.**

### Where it stands

- Done: both registries pinned and verified against publisher digests; the shared detection
  schema (`metrics/detections.md`) that A2.2-A2.5 emit; the search pipeline; 34 new tests; the
  Evo 1 tables for all three readings.
- Running: the `opengenome2` pass (IMG/VR and the plasmid/phage component).
- Left: name RVDB's families from the release's own annotation file — the tables currently read
  `FAM004230`, which is correct and unreadable; then the ESM3-proxy table, which can only be a
  `not_searched` row until A1.6 builds the reader (D-043).
- Measured cost, for the scale decision: RVDB-prot over 23.3 M residues took 50 minutes on
  three cores, within 8% of the benchmark. A full pass over this one component would be about
  40,000 core-hours.

## Goal

Search the surviving corpora with curated protein-family profiles, by a route independent of
taxonomy labels.

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

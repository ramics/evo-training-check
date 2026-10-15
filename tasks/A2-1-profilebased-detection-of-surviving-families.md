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

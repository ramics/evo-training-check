---
id: A2.3
title: Detect endogenous elements in surviving host genomes
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.3 — Detect endogenous elements in surviving host genomes

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

**Branch:** `claude/fervent-hopper-8ht0h3`. Project management on `main` as usual.

**Where it stands:** claimed, nothing searched yet. Next step is pinning the
element-detection resources and fixing thresholds before any hit is inspected.

**Waiting on the project owner:** nothing yet.

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

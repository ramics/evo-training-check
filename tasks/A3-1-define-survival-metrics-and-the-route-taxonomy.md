---
id: A3.1
title: Define survival metrics and the route taxonomy
phase: A
status: review
gate: false
depends_on: [A0.2]
blocks: [A3.2, C5.1]
design_ref: "§A3"
deliverable: 1
owner: claude
---

# A3.1 — Define survival metrics and the route taxonomy

**Design reference:** DESIGN.md §A3 · **Deliverable 1**

## Goal

Fix the headline metric definitions and the survival-route categories before any counting
happens.

## Steps

- Define family-level survival, surviving-count-per-family, and diversity-coverage precisely
  enough to reimplement.
- Define the route taxonomy used to break down every count. It must carry **outside filter
  scope** as a first-class route, per DECISIONS.md D-007, kept separate from routes the
  filter covered but could not detect, and from sequence it retained by design.
- State explicitly why raw sequence volume is not the headline metric.
- Freeze the definitions and record them in DECISIONS.md.

## Done when

- Metric definitions are written, frozen and reimplementable from the text alone.
- Route taxonomy is fixed and used by all A2 outputs.
- Frozen before A3.2 runs.

## State — 2026-10-15

`review`. The work merged into `main` in pull request #3 (branch `ccr-2956d088-s25hlk`), so the
files named here are in a `main` checkout. Nothing is sitting in a branch.

- `metrics/survival.md` is the frozen specification, written to be reimplementable from that file
  alone, so A3.3's independent second implementation never has to read the first.
- `src/amazebio/survival.py` carries the route taxonomy every A2 detector tags its output with,
  plus a reference implementation of the metric definitions. `tests/test_survival.py` pins the
  specification's worked examples.
- The four substantive calls are in DECISIONS.md D-022, including the project owner's choice to
  report both family registries separately and never pool them.

**Why this is not `done`:** the Done-when criterion "route taxonomy is fixed and used by all A2
outputs" cannot be demonstrated while no A2 detector exists. Move it to `done` when the first A2
task emits `amazebio.survival.Detection`.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

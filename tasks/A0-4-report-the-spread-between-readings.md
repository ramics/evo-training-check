---
id: A0.4
title: Report the spread between readings
phase: A
status: review
gate: false
depends_on: [A0.3, A3.2]
blocks: [A6.1]
design_ref: "§A0"
deliverable: null
owner: claude
---

# A0.4 — Report the spread between readings

**Design reference:** DESIGN.md §A0

## Goal

Quantify and write up how much the three readings differ in what they exclude — itself a stated
finding.

## Steps

- Compute the exclusion-set difference between readings, per model.
- Express the spread in the A3.1 metrics, not in raw record counts.
- Write the finding as a reproducibility claim about the published policy, carefully scoped to
  what was measured.

## Done when

- Spread is quantified per model and per metric.
- Write-up states plainly whether each policy as published is reproducible.
- No claim exceeds what the measurement supports.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project owner.

**Done.** `src/amazebio/spread.py`, `tools/reading_spread.py`, `tests/test_spread.py` (20
tests, full `check` green), and the artefact at `corpora/results/a0-4/`. The finding is D-207:
Evo's three readings remove identical record sets from both releases and report identical
headline metrics, and the whole measurable spread is in declared scope and in which rules the
release leaves undecidable. Reported as `agree_on_the_corpus`, not as reproducibility.

**Left.** ESM3-open's spread is not measurable until A1.6 supplies the charitable and strict
manifests; that arm reports `not_measurable` and will want re-running when it does.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

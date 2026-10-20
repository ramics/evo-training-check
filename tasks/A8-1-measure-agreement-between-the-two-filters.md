---
id: A8.1
title: Measure agreement between the two filters
phase: A
status: in-progress
gate: false
depends_on: [A0.3, A1.3]
blocks: []
design_ref: "§A8"
deliverable: 1
owner: claude
---

# A8.1 — Measure agreement between the two filters

**Design reference:** DESIGN.md §A8 · **Deliverable 1**

## Goal

Both filters claim to remove viral sequence by different mechanisms. Apply both to one common
corpus and measure where they disagree, to test whether this class of safeguard denotes a
definite operation at all.

## Steps

- Choose the common corpus and justify it; a protein corpus both predicates can act on is the
  obvious candidate, and the choice constrains what the result can say.
- Run the label-based and similarity-based predicates over the same records.
- Report the four cells: both remove, neither removes, and each one-sided case, with the
  one-sided cases broken down by why.
- Characterise what kind of sequence falls in each gap — fold class, function, taxonomy.
- State the confound prominently: the two filters were deployed against different corpora, so
  this measures the predicates and not the deployments.
- For the similarity-based predicate, sweep the unpublished threshold across a stated range and
  report agreement as a function of it, since no single value is defensible.

## Done when

- Agreement reported across all four cells, with the one-sided cases characterised.
- Results reported across a threshold range, not at a single assumed value.
- The predicates-not-deployments confound is stated in the output, not only in the paper.
- Reproducible from pinned inputs.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner yet.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

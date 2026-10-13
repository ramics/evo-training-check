---
id: A0.1
title: Collect primary-source exclusion policy statements
phase: A
status: ready
gate: false
depends_on: []
blocks: [A0.2, A1.1, B1.1]
design_ref: "§A0, §B1 step 0"
deliverable: null
owner: unassigned
---

# A0.1 — Collect primary-source exclusion policy statements

**Design reference:** DESIGN.md §A0, §B1 step 0

## Goal

Assemble the verbatim published wording of each model's data-exclusion policy, with citations,
as the raw input every later reading depends on.

## Steps

- For each model in scope, locate the primary sources: paper, model card, release notes, repo
  docs, dataset docs.
- Record the exclusion wording verbatim, with a stable citation and access date.
- For each, record separately: what was excluded, by what definition, whether it applied to the
  released checkpoint, and whether any re-entry route is addressed.
- Flag every point where the prose is ambiguous or silent. Do not resolve the ambiguity here.
- Do not rely on secondary sources, DESIGN.md included.

## Done when

- A sources file exists with verbatim quotes + citations for every model in scope.
- Each ambiguity is logged as an open question, not silently interpreted.
- Any policy that cannot be sourced to primary material is marked as such.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

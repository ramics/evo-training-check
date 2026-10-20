---
id: B3.4
title: Compute the MSA-depth covariate
phase: B
status: in-progress
gate: false
depends_on: [B2.4]
blocks: [B3.5]
design_ref: "§B3 confounder"
deliverable: 3
owner: claude
---

# B3.4 — Compute the MSA-depth covariate

**Design reference:** DESIGN.md §B3 confounder · **Deliverable 3**

## Goal

Compute per-target alignment depth, without which 'intrinsically hard' and 'excluded from
training' are not separable.

## Steps

- Build alignments per target against a pinned reference database; document the procedure.
- Compute the depth statistic specified in §B3.
- Verify the statistic behaves sensibly across the target range.
- Expose it as a mandatory covariate to the B5 model.

## Done when

- Depth computed for every assay target.
- Procedure documented and reproducible.
- Covariate wired into the B5 analysis as mandatory, not optional.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner.

**Done.** Nothing yet; just claimed.

**Left.** The depth statistic itself, its definition pinned in `DECISIONS.md` before any
number is read, and the cross-check against the alignment maintainers' own published Neff.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

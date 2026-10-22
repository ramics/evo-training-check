---
id: X5.1
title: Draft the filter disclosure standard
phase: X
status: done
gate: false
depends_on: [A0.1, A7.1]
blocks: []
design_ref: "§10, §5 deliverable 8"
deliverable: 8
owner: claude
---

# X5.1 — Draft the filter disclosure standard

**Design reference:** DESIGN.md §10 · **Deliverable 8**

## Goal

Define the minimum a developer must publish for a data filter to be independently auditable,
then retro-fit it to all four models and report what is missing against each.

## Steps

- Derive the checklist from what actually blocked the audit, not from first principles: scope
  (which corpus components), predicate, thresholds, annotation sources and versions, tool
  versions, validation performed, and which released artefacts it applied to.
- Score all four models against it, citing `policies/` for every gap so each claim is traceable.
- Keep the tone on the mechanism rather than the labs: every gap found is an absence of
  convention, not misconduct, and the write-up should say so once and plainly.
- Apply it to this project's own filter specifications and publish those in the same format, so
  the standard is demonstrated rather than only proposed.
- Check the checklist against an existing framework's requirements and note where it adds
  something they do not already ask for.

## Done when

- Checklist is written and each item is justified by a specific audit obstacle encountered.
- All four models scored, with every gap traceable to a quoted source in `policies/`.
- This project's own filter specifications are published in the same format.
- Overlap with existing framework requirements is stated, so the contribution is clear.

## Closed — 2026-10-22

`done`. Merged to `main` in PR #31. All four Done-when criteria were met at the time of
writing and the review carry-over is now resolved as far as it can be: **A3.3 opened on
2026-10-21 and passed**, so the self-scored D2 cell no longer reads "neither gate has run yet".
It stays `~` rather than becoming `✓`, because C6.3 covers the Phase C curves and has not run,
and `docs/disclosure-standard.md` now says exactly that.

The other carry-over is left open deliberately and is not a defect: the framework comparison
rests on five frameworks read from their primary texts, and if a sixth belongs in it the one
most likely to is a sector instrument that search did not surface. That is a question for a
reader, not a blocker.

## State — 2026-10-20

Branch: `claude/project-thread-a3vch4`, commit `fb91506`. Nothing is waiting on the project
owner.

Done: all four Done-when criteria. `docs/disclosure-standard.md` holds the checklist — fourteen
items in five groups, each with the audit obstacle that produced it and what compliance costs —
the scoring of all four models with every cell traceable to `policies/`, this project's own
filter specifications scored in the same format, and the comparison against five existing
frameworks, each read from its primary text. D-223 records the ESM-2 scoping call.

Left: review. Two things a reviewer should look at first. Our own D2 is scored `~` and stays
there until A3.3 opens, so the self-scoring column is not complete and says so. And the
framework comparison rests on five frameworks; if a sixth belongs in it, the one most likely to
is a sector instrument this search did not surface.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

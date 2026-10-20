---
id: X5.1
title: Draft the filter disclosure standard
phase: X
status: in-progress
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

## State — 2026-10-20

Branch: `claude/project-thread-a3vch4`. Picked up while A2.6's census runs; nothing is
waiting on the project owner.

Done: nothing yet.

Left: all of it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

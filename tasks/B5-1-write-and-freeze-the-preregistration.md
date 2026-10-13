---
id: B5.1
title: Write and freeze the pre-registration
phase: B
status: blocked
gate: true
depends_on: [B3.5, B4.2]
blocks: [B5.2, X4.1]
design_ref: "§B5, §2"
deliverable: null
owner: unassigned
---

# B5.1 — Write and freeze the pre-registration

**Design reference:** DESIGN.md §B5, §2

## Goal

Write the analysis pre-registration and freeze it before any outcome is inspected. §B5 and §2
both require commitments made in advance.

## Steps

- Specify the primary model exactly: terms, interaction, random effects, covariates,
  estimation.
- Specify secondary analyses, the per-assay reporting requirement, and the effect-size
  threshold from §B5.
- Commit in writing to publishing the null result, per §2.
- Freeze by commit hash and timestamp; record the freeze in DECISIONS.md.

## Done when

- Pre-registration is complete, frozen, and referenced by hash from B5.2–B5.4.
- Effect-size threshold stated before any result is seen.
- GATE: no B5 analysis may run before this freeze.
- Null-result publication commitment recorded.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

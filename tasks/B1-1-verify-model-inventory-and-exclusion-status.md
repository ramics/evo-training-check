---
id: B1.1
title: Verify model inventory and exclusion status
phase: B
status: ready
gate: false
depends_on: [A0.1]
blocks: [B1.2]
design_ref: "§B1"
deliverable: null
owner: unassigned
---

# B1.1 — Verify model inventory and exclusion status

**Design reference:** DESIGN.md §B1

## Goal

Fix the model list for Phase B and confirm each one's exclusion status from primary sources,
including the positive controls.

## Steps

- Confirm from primary sources which checkpoints are exclusion-condition and which are
  controls. The v0.3 model list (ESM3-open as protein-level test condition, ESM-C as a
  second viruses-included comparison) comes from A0.1; re-verify it rather than
  inheriting it.
- Record checkpoint identifiers, versions, licences and access routes.
- Decide and record which Tier 2 models are in scope given available compute.
- Flag any model whose training composition is too under-documented to classify.

## Done when

- Model table is complete with verified status, versions and licences.
- Tier 2 scope decision recorded in DECISIONS.md.
- Under-documented cases flagged as findings per §7.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

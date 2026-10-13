---
id: B1.2
title: Build the zero-shot scoring harness
phase: B
status: blocked
gate: false
depends_on: [B1.1]
blocks: [B5.2]
design_ref: "§B1, §4"
deliverable: null
owner: unassigned
---

# B1.2 — Build the zero-shot scoring harness

**Design reference:** DESIGN.md §B1, §4

## Goal

Implement the inference harness for zero-shot variant scoring across all models on equal terms.
Scope limits in §4 apply strictly.

## Steps

- Implement a uniform scoring interface across the model families in scope.
- Enforce the §4 scope limits in code: zero-shot scoring only, no generation, no fine-tuning.
- Pin environments and seeds; verify run-to-run determinism.
- Validate against a published reference number per model where one exists.

## Done when

- All in-scope models score a common test set through one interface.
- §4 limits are enforced by the harness, not just by convention.
- Determinism verified; reference numbers reproduced where available.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

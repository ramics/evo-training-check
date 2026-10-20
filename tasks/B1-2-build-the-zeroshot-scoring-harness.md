---
id: B1.2
title: Build the zero-shot scoring harness
phase: B
status: in-progress
gate: false
depends_on: [B1.1]
blocks: [B5.2]
design_ref: "§B1, §4"
deliverable: null
owner: claude
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

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner.

**Done.** The harness contract and its §4 refusals (`src/amazebio/scoring.py`), the weight
loader split out so the refusals stay testable without a deep-learning stack
(`src/amazebio/backends.py`), the published-reference check with paired bootstrap intervals
(`src/amazebio/reference.py`, D-208), and the driver with a `--plan` mode that costs a pass
without loading a model (`tools/score_variants.py`). 93 tests across
`tests/test_scoring.py`, `tests/test_backends.py` and `tests/test_reference.py`.

**Left.** The GPU launcher and one real pass per Tier-1 checkpoint on a common test set, which
is what turns the plan into the reproduced reference numbers the Done-when asks for. The
nucleotide arm (`evo2_7b`) refuses without a published coding sequence and is reported as not
run rather than estimated.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

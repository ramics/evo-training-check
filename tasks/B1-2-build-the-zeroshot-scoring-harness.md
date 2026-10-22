---
id: B1.2
title: Build the zero-shot scoring harness
phase: B
status: review
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

## State — 2026-10-22

`review`. **The common test set is now nine assays wide, which closes the only carry-over the
block below left.** Table regenerated and published from a clean tree at `6833d53`:
`artifacts/b1-2/reference-check.md` and `.json`, and the same two objects under
`corpora/results/b1-2/`, over 36 score artefacts in the same prefix.

**36 runs, every one bitwise identical on a re-score. 27 have a published column and all 27
reproduce it**, the lowest agreement 0.9957; the nine `esm2_t33_650M_UR50D` runs agree to nine
decimal places. Four of the five roster checkpoints are scored, over the nine assays every one
of them covers. `evo2_7b` is still not run, for the reason its roster entry gives.

**What it cost, and the cost model that made it plannable.** 23 checkpoint-assay pairs, 75
minutes wall, on this container and nothing rented. Masked-marginal scoring scales with
distinct positions × sequence length rather than variant count: the nine-assay set is 370,227
such units and `A0A2Z5U3Z0_9INFA_Wu_2014` alone is 311,880 of them, so the eight assays left to
add were a fifth of the one already scored. A variant-count estimate had put the same work near
ten hours.

**One correction worth reading before trusting a capability claim about this machine.** A first
probe at the driver's default batch size was killed on memory for `esm3-sm-open-v1` and ran four
times over its predicted time for `esm2_t36_3B_UR50D`, which read as *these two do not fit here*.
They do. Both had been scored here before at batch sizes recorded in their own run manifests — 1
and 2 respectively — and at those sizes both completed all nine assays without incident. Recorded
as D-249.

**What nine assays is and is not.** A common set, not a representative one: all nine are viral
and five come from one stability study. It supports a like-for-like comparison across these four
checkpoints; it does not support a general ranking, and §B5 should say which of the two it is
making.

## State — 2026-10-21

`review`. The reference table is generated and published:
`artifacts/b1-2/reference-check.md` and `.json`, and the same two objects under
`corpora/results/b1-2/`, written from a clean tree at `e687797`.

**Twelve runs, all bitwise identical on a re-score. Eleven had a published column and all
eleven reproduce it**, the lowest agreement 0.9957 and the two ESM-2 checkpoints exact to four
places. Four of the five roster checkpoints are scored, over the one assay every one of them
covers.

**Two checkpoints have no published reference, for different reasons, and both are reported
rather than scored against something improvised.** `esm3-sm-open-v1` has no column in the
published table once that column is read correctly — D-238 established that the benchmark
produces its ESM3 column with the structure track on, while this harness scores the sequence
track alone, so the 0.2043 an earlier run reported was two different quantities compared and
not a disagreement. That caveat travels with every ESM3 figure: it is the one Tier-1 checkpoint
here with no published validation of any kind. `evo2_7b` needs a published coding sequence for
the assay's target and the benchmark publishes protein sequences; scoring a back-translation
would be scoring a sequence nobody published, so it is not run.

**What this leaves for B5.2.** The common test set is one assay wide, which is what the
determinism and reference checks need and not what a comparison needs. Widening it is scoring
time, not new code. _(Done on 2026-10-22 — see the block above and D-249.)_

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

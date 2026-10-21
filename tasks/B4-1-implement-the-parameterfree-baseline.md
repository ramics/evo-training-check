---
id: B4.1
title: Implement the parameter-free baseline
phase: B
status: review
gate: false
depends_on: [B2.4]
blocks: [B4.2]
design_ref: "§B1, §B4"
deliverable: null
owner: claude
---

# B4.1 — Implement the parameter-free baseline

**Design reference:** DESIGN.md §B1, §B4

## Goal

Implement the mandatory non-neural baseline. §B4 makes it load-bearing: it is what attributes a
failure to training data rather than to assay difficulty.

## Steps

- Select the baseline method from the §B1 options; record the choice and rationale.
- Implement or integrate it with no training step at any point.
- Score every assay in the collection.
- Document precisely why it has no exclusion exposure.

## Done when

- Baseline scores every assay in the collection.
- Method choice and rationale recorded in DECISIONS.md.
- Absence of any training exposure is documented and verifiable.

## State — 2026-10-21

`review`. The baseline has run over the whole collection and is published:
`artifacts/b4-1/baseline.json`, the 31 per-assay files beside it, and the same 32 objects under
`corpora/results/b4-1/`. The run took five and a half hours in the session container and cost
nothing.

**Every done-when condition is met.** All 31 assays are scored; D-229 records the method and
why it was chosen; and the artefact carries the no-training-exposure statement in full — the
alignment is built at inference time, the structure is a prediction of the target itself, and
the score is a closed-form function of the two, so there are no weights and no corpus a filter
could have been applied to.

**Against the benchmark's own published column, 19 of 31 assays reproduce** at or above the
0.99 agreement floor, the lowest of them 0.9945. Nine diverge and three are undetermined, which
means their interval straddles the floor rather than clearing it:

| verdict | assays | agreement with the published column |
|---|---|---|
| reproduced | 19 | 0.9945 to 1.0 |
| undetermined | 3 | 0.9901 to 0.9908 |
| diverges | 9 | 0.8207 to 0.9871 |

The weakest is `VRPI_BPT7_Tsuboyama_2023_2WNM` at 0.8207, and the divergences mostly do not move
the assay-level metric: six of the nine have a difference against the experimental truth whose
interval includes zero. **Why the nine differ is not established, and that is the open item
here** — it is a disagreement with a published column, not with the experiment.

**Multiple substitutions are deliberately unscored**, which matters for B4.2 because the
published column does score them. Four assays contain multiples, and in
`CAPSD_AAV2S_Sinai_2021` they are almost the whole assay: 532 of 42,328 variants are scored.
Summing a multiple's parts would be a different method from the one D-229 fixed, so they are
reported as unscored rather than approximated. B4.2 has to compare the baseline against the
models on the variants both of them score.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

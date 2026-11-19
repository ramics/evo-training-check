# Status

Hand-maintained, 19 November 2026. This page says where the work has got to. The figures and
their provenance are in `../results/README.md`.

## Phase A — does the filter remove what it claims to?

**Complete, and being written up.** Both corpora were reconstructed from pinned revisions, each
published policy was transcribed into executable predicates in three readings, the surviving
records were searched by sequence and by structure, and the headline counts were
reimplemented independently and reproduced to the number (334 of them). The audit of the
taxonomy dependency, the conformance re-execution, the specificity join, the label arm and the
decay measurement are all done.

Open:

- The write-up. A draft exists outside the repository and is being cut down.
- The deepening pass at census depth has been priced and not bought. The sampling design was
  pre-registered, so the lower bounds are the result the project set out to get, not a
  shortfall. The runbook is in `a2-6-census-runbook.md`.
- The protein-model arm (ESM3-open) is staged and priced, and publishes no figure. That filter
  works by similarity instead of by label, so re-executing it needs two denylists neither
  publisher released. Reconstructing them is most of the arm.
- Two reporting tasks: per-region metrics for a named record set, and the training-membership
  accession list.

## Phase B — where it does not, does surviving capability track homology?

**Instruments built and validated; the analysis has not run.** The zero-shot scoring harness
reproduces the benchmark's published numbers (27 of 27 comparisons, lowest 0.9957, runs bitwise
reproducible). The parameter-free baseline is at published strength, and was not tuned towards
the published column it is checked against: maximising agreement with that column would measure
the tuning instead of the method. The homology axis, the domain-level presence measure
and the alignment-depth covariate are computed, and the assay provenance register is validated
in CI.

**The gate is the pre-registration.** The primary and secondary analyses do not start until the
analysis plan is written and frozen, because a threshold chosen after seeing results is not a
pre-registered threshold. That is the next piece of work in Phase B.

The structural side of the homology axis was declined for good: it would tighten a bound rather
than produce a new result, and the sequence measure stays secondary.

## Phase C — can leakage be predicted from the filter spec alone?

**Deferred.** The cost-curve definitions and the hazard-family set are frozen
(`../metrics/costcurve.md`), including the second instrument, which reads biology instead of
family names. The leakage-score model itself is not started, and the curve work is blocked behind
its own independent-reimplementation gate.

## Gates

A gate is a commitment the project made in advance, and work downstream of a closed one does not
start. Two have passed and three are still closed.

| Gate | State | What it holds |
|---|---|---|
| Released-vs-actual training data verified | **passed** | — |
| Independent second-method reimplementation of the headline counts | **passed** | — |
| Pre-registration written and frozen | **closed** | Phase B's analyses, and the preprint |
| Independent reimplementation of the headline curves | **closed** | Phase C's output, and the preprint |
| Responsible-disclosure process run | **closed** | **all external circulation**, and the preprint |

**Nothing has been circulated outside the project, and nothing may be until the disclosure gate
opens.** No deadline or convenience lifts that one.

## The working record

The task cards, the append-only decision log and the generated board were removed from the tree
on 19 November 2026, to keep the project management out of a reader's way. They are in git
history at commit `fbc8b41`, and copied in full to the project's own files. Figures and contracts
still cite task ids (`A2.1`) and decision ids (`D-245`); `working-record.md` says how to look one
up.

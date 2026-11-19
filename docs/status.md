# Status

Hand-maintained, 19 November 2026. The figures and their provenance are in
`../results/README.md`; this page is only *where the work has got to*.

## Phase A — does the filter remove what it claims to?

**Complete as a result, and being written up.** Both corpora were reconstructed from pinned
revisions, each published policy was transcribed into executable predicates in three readings,
the surviving records were searched by sequence and by structure, and the headline counts were
reimplemented independently and reproduced to the number (334 of them). The audit of the
taxonomy dependency, the conformance re-execution, the specificity join, the label arm and the
decay measurement are all done.

Open:

- The write-up. A draft exists outside the repository and is being cut down.
- The deepening pass at census depth is priced, pre-registered and not bought. The sampling
  design was pre-registered, so the lower bounds are the result rather than a shortfall; the
  runbook is in `a2-6-census-runbook.md`.
- The protein-model arm (ESM3-open) is staged and priced, and publishes no figure. Its filter is
  similarity-based rather than label-based, so re-executing it needs two denylists neither
  publisher released, which is what the arm reconstructs.
- Two reporting tasks: per-region metrics for a named record set, and the training-membership
  accession list.

## Phase B — where it does not, does surviving capability track homology?

**Instruments built and validated; the analysis has not run.** The zero-shot scoring harness
reproduces the benchmark's published numbers (27 of 27 comparisons, lowest 0.9957, runs bitwise
reproducible). The parameter-free baseline is at published strength and deliberately not tuned
towards the column it is validated against. The homology axis, the domain-level presence measure
and the alignment-depth covariate are computed, and the assay provenance register is validated
in CI.

**The gate is the pre-registration.** The primary and secondary analyses do not start until the
analysis plan is written and frozen, because a threshold chosen after seeing results is not a
pre-registered threshold. That is the next piece of work in Phase B.

The structural side of the homology axis was declined for good: it would tighten a bound rather
than produce a new result, and the sequence measure stays secondary.

## Phase C — can leakage be predicted from the filter spec alone?

**Deferred.** The cost-curve definitions and the hazard-family set are frozen
(`../metrics/costcurve.md`), including the second instrument that reads biology rather than
family names. The leakage-score model itself is not started, and the curve work is blocked behind
its own independent-reimplementation gate.

## Gates

Gates are commitments, not milestones. Two have passed and three are closed; nothing downstream
of a closed gate is worked on.

| Gate | State | What it holds |
|---|---|---|
| Released-vs-actual training data verified | **passed** | — |
| Independent second-method reimplementation of the headline counts | **passed** | — |
| Pre-registration written and frozen | **closed** | Phase B's analyses, and the preprint |
| Independent reimplementation of the headline curves | **closed** | Phase C's output, and the preprint |
| Responsible-disclosure process run | **closed** | **all external circulation**, and the preprint |

**Nothing has been circulated outside the project, and nothing may be until the disclosure gate
opens.** That is the one rule in `../AGENTS.md` that no convenience lifts.

## The working record

The task cards, the append-only decision log and the generated board were removed from the tree
on 19 November 2026 so that a reader meets the work rather than the project management. They are
in git history at commit `fbc8b41`, and copied in full to the project's own files. Figures and
contracts still cite task ids (`A2.1`) and decision ids (`D-245`); see
`working-record.md` for how to read them.

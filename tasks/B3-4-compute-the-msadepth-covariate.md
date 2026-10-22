---
id: B3.4
title: Compute the MSA-depth covariate
phase: B
status: done
gate: false
depends_on: [B2.4]
blocks: [B3.5]
design_ref: "§B3 confounder"
deliverable: 3
owner: claude
---

# B3.4 — Compute the MSA-depth covariate

**Design reference:** DESIGN.md §B3 confounder · **Deliverable 3**

## Goal

Compute per-target alignment depth, without which 'intrinsically hard' and 'excluded from
training' are not separable.

## Steps

- Build alignments per target against a pinned reference database; document the procedure.
- Compute the depth statistic specified in §B3.
- Verify the statistic behaves sensibly across the target range.
- Expose it as a mandatory covariate to the B5 model.

## Done when

- Depth computed for every assay target.
- Procedure documented and reproducible.
- Covariate wired into the B5 analysis as mandatory, not optional.

## Closed — 2026-10-22

`done`. Merged to `main` in PR #31. Depth exists for all 31 assay targets over their 28
alignments (`corpora/results/b3-4/depth.{json,md}` with its run manifest), the procedure is
pinned in D-231 and reproducible from `tools/assay_depth.py`, and the covariate is wired in as
mandatory where it can be before B5 runs: `metrics/depth.md` is binding on B3.5 and B5, states
that every assay entering a B5 model carries a depth, and a change to it is a decision entry.
B5.1 inherits that contract rather than choosing whether to honour it.

## State — 2026-10-21

`review`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project owner.

**Done.** Depth for all 31 assay targets over their 28 distinct alignments, as
`artifacts/b3-4/depth.json` and `depth.md`, published durably. The statistic is pinned in
D-231 and implemented in `src/amazebio/neff.py`; `tools/assay_depth.py` builds the table and
`metrics/depth.md` states the contract B3.5 and B5 inherit. 51 tests.

Nineteen of the 28 alignments are summed exactly — six because the threshold admits only an
identical row as a neighbour, thirteen by narrowing each row's candidates with the pigeonhole
principle, which is what makes an exact sum affordable over 820,224 sequences. The other nine
are estimated from 20,000 sampled rows and carry a bootstrap interval 2.4% to 8.4% wide.

The maintainers' own published depth is in the artefact beside ours as a ratio: median 1.17
across the 31, and the four outliers are the two SARS-CoV-2 targets at 3.1x and 4.2x. That is
the expected direction and the expected targets — their figure is computed after their
coverage filters and ours on the alignment as distributed, and SARS-CoV-2 alignments carry far
more partial genomes than the rest. Reported, not reconciled.

Two alignments give different neighbour floors under the two readings of the identity
boundary (`POLG_DEN26`, `RPC1_LAMBD`); both readings are in the artefact.

**Left — one Done-when criterion cannot be demonstrated yet.** "Covariate wired into the B5
analysis as mandatory, not optional" needs a B5 analysis to wire it into, and B5.2 is blocked
behind B3.5 and the B5.1 pre-registration gate. What exists instead is the contract:
`metrics/depth.md` states that every assay entering a B5 model carries a depth, that a
specification omitting the covariate is not one this project will run, that it is never
imputed, and that it enters on the log scale. B5.1 inherits that and B3.5 packages it. This
task should move to `done` only once B5.2 reads the covariate and that contract is met in
code rather than in prose.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

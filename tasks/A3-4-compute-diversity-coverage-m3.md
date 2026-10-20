---
id: A3.4
title: Compute diversity coverage (M3)
phase: A
status: in-progress
gate: false
depends_on: [A3.2]
blocks: [A6.1]
design_ref: "§A3"
deliverable: 1
owner: claude
---

# A3.4 — Compute diversity coverage (M3)

**Design reference:** DESIGN.md §A3 · **Deliverable 1**

## Goal

Compute the third frozen headline metric, M3, which A3.2 could not: for each surviving family,
how much of that family's known diversity the surviving sequence covers.

Split out of A3.2 rather than widened into it — see **D-195**. A3.2 established that M3 is not
derivable from the A2 detection artefacts at any depth: those records carry a record id, a
score, a route and an element kind, and no sequence, alignment or coordinates. The measurement
was never taken, so taking it is a corpus pass with its own cost and its own declared depth.

## Steps

- Measure what the pass costs before buying it, at a size that resembles the job. D-164's ladder
  misled A2.2 by benchmarking at a size the real work did not resemble; that lesson applies here.
- Fix the depth and declare it before any coverage figure is inspected.
- For each registry, build the diversity bins exactly as `metrics/survival.md` §4 M3 specifies:
  the family's reference members from the pinned registry release, clustered at 50% amino-acid
  identity over 80% of the shorter sequence. Both values are frozen and are not parameters.
- Place each surviving detection into a bin of its family, and emit `coverage(f)` per family
  with its 95% Wilson interval over bins.
- Report the corpus-level summary as the distribution of `coverage(f)` across surviving
  families — median and IQR — and never as a single pooled coverage figure.

## Done when

- Per-family coverage exists for every surviving family in every group A3.2 reports, with
  intervals.
- The clustering is reproducible from the pinned registry releases and seeds.
- The corpus summary is a distribution, not a pooled figure.
- If the owner declines the compute, this task is `deferred` rather than dropped, so M3 appears
  in the write-up as a named commitment deliberately not run.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner; the bin-source question was answered on 2026-10-20 and is recorded in **D-205**.

The task has two halves and only the first is cheap. **Bins** come from Pfam's seed alignment,
complete rather than sampled, and are computed here. **Placement** — putting each surviving
detection into a bin of its family — needs the surviving sequence, which no A2 artefact
carries (D-195), so it is a corpus pass whose depth is declared before it runs.

D-205 also settles the other two registries: RVDB-prot publishes no sequence-to-family
mapping, so M3 is not computable there from the published release, and Dfam is nucleotide, so
the frozen amino-acid rule does not apply. Both are findings, not gaps to close here.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

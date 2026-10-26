---
id: A3.4
title: Compute diversity coverage (M3)
phase: A
status: done
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

## Closed — 2026-10-22

`done`. The work merged to `main` in PR #31 and the figures were corrected and re-landed in
PRs #32–#35; the deliverable is in the durable store at `corpora/results/a3-4/`, nine stable
objects with their commit-keyed twins beside them. Each Done-when criterion is met:
per-family coverage exists for both releases with intervals, the placement reproduces from the
pinned registry release and the frozen criterion, and the corpus figure is published as a
distribution. The compute was not declined, so the fourth criterion does not apply.

The one result a reader should not lose: **78.8% of matched regions on Evo 1 and 78.7% on
Evo 2 meet no diversity bin at all.** Two independently sampled corpora agreeing to a tenth of
a point makes that a property of the comparison rather than of either sample.

This closes A6.1's last dependency.

## M3 is computed and published — 2026-10-21 (late evening)

`review`. Both releases are placed and published to `corpora/results/a3-4/` from clean commits,
with run manifests: `coverage-pfam-evo1-literal-{opengenome,opengenome2}.{json,md}`.

| release | rate | families with a detection | regions placed | coverage(f) median | IQR |
|---|---|---|---|---|---|
| `opengenome` | 0.02 | 590 of 1,719 | 27,232 of 128,480 | 0.391 | 0.083 – 0.731 |
| `opengenome2` | 0.01 | 811 of 1,719 | 14,142 of 66,296 | 0.333 | 0.091 – 0.600 |

Restricted to the families whose interval can say anything at all (D-214), the medians fall to
0.333 over 250 families on Evo 1 and 0.206 over 302 on Evo 2. 92 and 106 families cover every
bin; 122 and 141 cover none.

**The corpus figure is the distribution and never a pooled coverage**, as `metrics/survival.md`
§4 requires: the families run from one bin to 421, and pooling would weight a one-bin family
equally with a 421-bin one.

**Three things in these numbers that the write-up has to carry.**

- **78.8% and 78.7% of matched regions meet no bin.** Those two figures come from independently
  sampled corpora and agree to a tenth of a point, which is what makes them a property of the
  comparison rather than of either corpus: a profile match establishes homology far below the
  50% identity the frozen criterion requires. Reported as its own figure and never folded into
  coverage. A region-length check bounds how much of it the criterion itself could explain —
  82.4% of regions sit within 0.8–1.25 of their family's model length, and only 16.5% are short
  enough that 80% coverage of both sides is unreachable against a full-length member — so the
  bulk of it is divergence, not arithmetic.
- **Evo 2 reads lower on the informative families despite carrying more of them**, 0.206 against
  0.333, because it is sampled at a tenth of Evo 1's rate: fewer records per bin, so fewer bins
  reached. The same asymmetry D-245 exposed in the family counts shows up here, and the two
  releases are no more comparable as coverage than as rates.
- **Every figure is a lower bound twice over.** The detections come from a sampled search, so a
  bin with no detection may hold surviving material nothing read; and the bins come from Pfam's
  seed alignment, which samples each family's diversity rather than exhausting it.

**Scope, stated rather than implied.** This is the Pfam registry under the `evo1-literal`
reading. The three policy readings were checked rather than assumed: their Pfam detections are
the identical set of (family, record) pairs on both releases — 127,077 and 65,132 pairs — so one
placement run covers all three and the published figures carry for each. The protein registry has
no bins artefact and no M3; building one means clustering 13,679 families' seed members, and it
belongs with the depth decision that left that registry at its pre-registered rate (D-247)
rather than with this task.

## State — 2026-10-21 (evening)

`in-progress` on branch **`claude/project-thread-rrpy0i`**, which is based on pull request #31
rather than on `main`: the detections this task places were produced by the chunked, task-aware
search on that branch, and `main`'s copy of the search is 445 lines behind it (D-242).

**The placement pass is written and under test.** `tools/place_detections.py` rebuilds each
family's bins, checks the rebuilt count against the published artefact rather than trusting it,
places every detection under D-239's rule, and reports `coverage(f)` as a distribution with the
unplaced detections counted apart. `detect_profiles.py --emit-hit-proteins` writes the residues
it reads, from inside the search, to ephemeral scratch (D-103).

**Two readings were forced and both are recorded before any coverage figure is kept.** D-244
opens the search's own prefilter and E-value gates so the frozen criterion alone decides a
placement. D-241 is the substantive one: a 400-record probe put 93% of detections in no bin,
and the cause was that the bins' members are aligned regions while a detection is a whole gene,
commonly two to three times as long, so the 80%-of-both criterion could not place them whatever
their identity. The unit placed is now the matched domain region. The probe's figures are
discarded.

Running now: a local re-read of the deepened sample and a re-search of it, to write out the
residues. Roughly two hours, no rented hardware and no cost. The pass writes no artefact of
A2.1's own — the durable upload is suppressed — so it cannot write a band part the published
tables were never assembled from.

Nothing is waiting on the project owner, except the standing D-236 question of whether Phase A
proceeds without the census.

## State — 2026-10-21, withdrawn

Another thread built this pass at the same time, not knowing this one was doing the same, and
stood down once it read this branch: its `--retain-hit-proteins`, `tools/diversity_coverage.py`
and the decision behind them are reverted, and D-243 withdraws its D-240. What survives from it
is in `tools/diversity_bins.py`, which now publishes each family's bin assignment with a digest
of the members it is positional over, and refuses to publish durably under `--limit` as D-232
requires. The placement pass here re-clusters rather than reading that assignment, so the two
agree by construction wherever both are run; the assignment makes the agreement checkable.

Its measurement of the remaining pass stands and matches this one: re-running the sampled band
over both releases took 65 and 55 minutes of local container time, with nothing to approve.

## State — 2026-10-20

`in-progress` on branch **`claude/project-thread-a3vch4`**. Unblocked 2026-10-21. The bins are built: 1,719 viral
Pfam families, 34,482 seed members, 17,502 bins, at 50% identity and 80% coverage
(D-205, D-206). The finding is in the shape of that distribution rather than in the count —
78.4% of families cannot carry an informative M3 whatever the detections turn out to be,
because Pfam's seed alignments hold too few members. D-214 fixes what is reported for them.

**Unblocked on 2026-10-21, and A2.6 is no longer a dependency.** D-222 blocked this task on
the census because the detections were too thin for M3 to say anything: most families had fewer
surviving records than bins. D-235 re-ran the ten-fold deepening and D-236 measured what that
did — in the 371 families whose M3 could be informative at all, the median went from about half
a record per bin to about four, and 302 of them now have a detection against 224 before. The
owner unblocked the task on that evidence. D-239 fixes how a detection is placed in a bin,
before any coverage figure exists. The superseded reasoning follows.

**Why it was blocked (D-222, superseded).** The placement pass itself
is cheap — 35 GB to stream, under an hour, about twenty cents — but the detections it would
place come from a 0.2% and a 0.1% sample, so M3 built on them would be a lower bound and
most families would land at zero or one bin covered. Costed at
`/mnt/project-files/a3-4/cost.md`; the owner chose to deepen the search first, which is A2.6.

Left once A2.6 lands: place the surviving detections into the bins at census depth, and
report pooled M3 by homology class alongside the 371 families that can carry a per-family
figure. Nothing is waiting on the project owner.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

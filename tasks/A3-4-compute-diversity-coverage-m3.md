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

## State — 2026-10-21

`in-progress` on branch **`claude/project-thread-a3vch4`**. Both halves of the measurement are
built and tested, and the cost of the remaining pass is measured rather than estimated.

- **The denominator carries its assignment.** The published bins recorded how many bins each
  family has and dropped which member went where, so there was nothing to place against.
  `tools/diversity_bins.py` now emits the assignment, positional over the seed members, with a
  digest of those members so a pass that re-reads the seed can prove it recovered the same list
  in the same order. It is being rebuilt locally; no money.
- **The numerator has a route to the sequence (D-240).** The detection tables carry no residues
  and the called-protein cache from the deepened pass is gone, so `detect_profiles.py
  --retain-hit-proteins` keeps the protein behind each hit as the search accepts it, in
  ephemeral scratch, one file per family. The retention directory is refused if it resolves
  inside the working tree (D-103).
- **The cost of the remaining pass, measured.** Re-running the sampled band over both releases
  took 65 and 55 minutes of local container time on 2026-10-21; retention adds a bounded write.
  Local, so there is nothing to approve.
- **`tools/diversity_coverage.py`** places the retained detections with D-239's rule and emits
  per-family `coverage(f)` with its Wilson interval, the distribution across families with a
  detection, the count of families with none, and the detections that met no bin.

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

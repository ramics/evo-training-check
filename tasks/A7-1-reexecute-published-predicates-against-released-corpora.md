---
id: A7.1
title: Re-execute published predicates against released corpora
phase: A
status: ready
gate: false
depends_on: [A0.3, A1.1, A1.2]
blocks: [X5.1]
design_ref: "§A7"
deliverable: 1
owner: unassigned
---

# A7.1 — Re-execute published predicates against released corpora

**Design reference:** DESIGN.md §A7 · **Deliverable 1**

## Goal

Run each developer's own published procedure against their own released corpus and diff. A
record that survives a rule its authors stated is a conformance failure — a comparison of
stated rule against delivered data, claiming nothing about homology or capability.

## Steps

- Execute each reading's predicate (A0.3) over the released dataset (A1.2).
- Identify records that survive but which the predicate says should have been removed.
- Classify each failure by cause: predicate ambiguous, required annotation absent or wrong,
  record postdates the filter, or the rule was never applied to that corpus component.
- Report count and rate per model and per reading; the spread across readings matters as much
  as any single number.
- Check the converse too — records removed that the predicate does not call for — since an
  over-broad filter is also a mismatch between rule and practice.
- Have the headline conformance numbers reproduced under A3.3 before any external circulation.

## Done when

- Conformance diff computed per model × reading, reproducible from pinned inputs.
- Every failure is classified by cause, and causes are defined before counting.
- A clean result is written up as a positive finding, per the §2 commitment, not buried.
- Claims are qualified by A1.1's verdict: a conformance claim against a proxy corpus is not a
  conformance claim, and the write-up says so plainly where that applies.
- Headline numbers independently reproduced via A3.3.

## Strength of claim and inputs (carried from A1.1)

See `policies/corpora.md` §2 and the corrected viral-component section, with DECISIONS.md D-017,
D-019 and D-020.

- **Evo is runnable, and against Evo 1's own release.** Input is IMG/VR v4 at its pinned version
  from its own publisher; output is `stage2` of `LongSafari/open-genome`, whose records carry
  inline lineage tags in the same rank-prefix scheme as the published stop-taxa. Running the diff
  against OpenGenome2's IMG/VR component as well stays worthwhile, since the releases differ — but
  do not write "OpenGenome" as though the two releases were one artefact.
- **Three published rules cannot be checked from the release.** The high-confidence gate, the vOTU
  representative and the prokaryotic-host count depend on IMG/VR metadata that does not travel
  with the released records. That is a property of the release, not an assumption, and it belongs
  in the write-up as a limit on what conformance was tested.
- **The vOTU representative is not reproducible.** `keep_one_per` is order-dependent and no input
  order is published, so compute the diff at vOTU level or it measures our sort order.
- **ESM3 has no conformance arm.** Neither corpus nor threshold is published. The reported 10.6M
  removal count is the only published quantity a reconstruction can be checked against, and any
  threshold recovered that way ships as an estimate with an interval, never as their parameter.
- **Qualify every Evo claim by the verdicts above**, and state plainly that the audited procedure
  is Evo 1's while one of the two audited outputs is Evo 2's.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

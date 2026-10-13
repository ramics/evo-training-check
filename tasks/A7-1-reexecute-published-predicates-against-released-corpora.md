---
id: A7.1
title: Re-execute published predicates against released corpora
phase: A
status: blocked
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

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: B2.3
title: Assemble the within-study positive-control assay set
phase: B
status: review
gate: false
depends_on: [B2.2]
blocks: [B2.4]
design_ref: "§B2"
deliverable: 2
owner: claude
---

# B2.3 — Assemble the within-study positive-control assay set

**Design reference:** DESIGN.md §B2 · **Deliverable 2**

## Goal

Curate the internal-contrast assay set §B2 specifies, whose source material is present in
training data and which therefore acts as a within-study positive control.

## Steps

- Identify published assays for the contrast class named in §B2.
- Apply the same QC and metadata standard as B2.2.
- Document why this set functions as a positive control and what a null result on it would
  mean.
- Keep it analytically separable from the test condition throughout B5.

## Done when

- Control assay set curated to the same standard as B2.2.
- Its control logic is documented, including the failure interpretation.
- Set is tagged for separable analysis in B5.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`**, in
[PR #31](https://github.com/ramics/amazebio/pull/31). Nothing is waiting on the project owner.

**Finished.** `tools/control_set.py` curates the set from B2.2's register and measures the
premise §B2 states; `tests/test_control_set.py` pins the arithmetic, the unit and the refusals.
Artefacts at `corpora/results/b2-3/` — `artifacts/b2-3/control-set.json`, `control-set.md`,
`run-control-set.json`.

**Done-when verdict.** The set is curated from B2.2's register rather than re-derived, so the
two cannot disagree about which assays are retained. The control logic and the failure
interpretation are in the artefact, written before any score exists. The set carries a
`within_study_positive_control` tag and the rule that it is never pooled with the excluded arm.

**What the measurement changed (D-227).** The premise is true at the class and nearly empty at
the genus: the four control organisms' genera hold 36 vOTUs between them out of 2,904,176,
while their class is 90.6% of the corpus. The control rests on homology to related corpus
sequence, not on these organisms being present. Six of the seven assays are retained because
their lineage has no family and no order node for Evo's rules to test, which is not the same
statement as phage having been decided to be in scope.

**Carried to B5.1:** with D-197's confound, this control cannot carry a null on its own. B5.1
has to say what it is for in the pre-registered plan rather than treating it as a free check.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A8.1
title: Measure agreement between the two filters
phase: A
status: review
gate: false
depends_on: [A0.3, A1.3]
blocks: []
design_ref: "§A8"
deliverable: 1
owner: claude
---

# A8.1 — Measure agreement between the two filters

**Design reference:** DESIGN.md §A8 · **Deliverable 1**

## Goal

Both filters claim to remove viral sequence by different mechanisms. Apply both to one common
corpus and measure where they disagree, to test whether this class of safeguard denotes a
definite operation at all.

## Steps

- Choose the common corpus and justify it; a protein corpus both predicates can act on is the
  obvious candidate, and the choice constrains what the result can say.
- Run the label-based and similarity-based predicates over the same records.
- Report the four cells: both remove, neither removes, and each one-sided case, with the
  one-sided cases broken down by why.
- Characterise what kind of sequence falls in each gap — fold class, function, taxonomy.
- State the confound prominently: the two filters were deployed against different corpora, so
  this measures the predicates and not the deployments.
- For the similarity-based predicate, sweep the unpublished threshold across a stated range and
  report agreement as a function of it, since no single value is defensible.

## Done when

- Agreement reported across all four cells, with the one-sided cases characterised.
- Results reported across a threshold range, not at a single assumed value.
- The predicates-not-deployments confound is stated in the output, not only in the paper.
- Reproducible from pinned inputs.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`**, in
[PR #30](https://github.com/ramics/amazebio/pull/30).

**Finished.** `src/amazebio/agreement.py` holds both predicates and the cross-tab;
`tools/filter_agreement.py` runs one tier; `tools/ec2_agreement.py` launches it in region;
`tools/agreement_report.py` puts the two tiers side by side. Artefacts at
`corpora/results/a8-1/` — `agreement.md` and one `agreement-2023_02-<tier>.json` per tier,
with their run manifests. The two tiers were run from different commits because a spot
reclaim took the first instance after it published UniRef90; each manifest names its own.

**Done-when verdict.** All four met. Agreement is reported across the cells with the
one-sided case characterised by kind and by which rule reached it; the two tiers are the
threshold range, run rather than assumed; the predicates-not-deployments confound is a field
in the artefact; and the pass regenerates from pinned inputs — the staged release, the dated
taxdump by digest, and the committed specs.

**Results in D-200.** 62.43% agreement over 5,405,462 judged records, which is strict
containment rather than convergence: `label_only` and `neither` are both empty, the
similarity predicate removes every viral record and the taxon rules 62% of them. The only
quantity the threshold moves is the non-viral collateral — 2,173,029 at 90% identity against
6,955,858 at 50%.

**Two findings for A9.1, in D-199.** `Reoviridae` is not a family name in the pinned
taxonomy, only a synonym of an order; and `require_rank: realm` asks for a rank NCBI does not
use, which run literally removes the whole viral corpus.

**Waiting on the project owner:** nothing.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

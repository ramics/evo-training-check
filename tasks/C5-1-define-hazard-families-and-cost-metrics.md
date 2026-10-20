---
id: C5.1
title: Define hazard families and cost metrics
phase: C
status: review
gate: false
depends_on: [A0.3, A3.1]
blocks: [C5.2]
design_ref: "§C5, §C6"
deliverable: 4
owner: claude
---

# C5.1 — Define hazard families and cost metrics

**Design reference:** DESIGN.md §C5, §C6 · **Deliverable 4**

## Goal

Fix the hazard family set, the two cost metrics and the regime boundary, before anything is
computed. Per §C6 the boundary is pre-registered, for the same reason §B5's effect-size
threshold is.

## Steps

- Define the hazard family set from published hazard lists, not from judgement. Record the
  list's version and the mapping from list entries to protein families.
- Define **hazard removed** and **collateral removed** precisely enough to reimplement: what
  counts as a unit (sequence, cluster, family, domain), and what the denominator is.
- Define the stringency axis: which similarity measures, over what range, at what steps.
- Define the **coverage** metric per family — how well databases represent that family's known
  diversity. §C7 forbids reporting a curve without it.
- Pre-register the regime boundary: what collateral fraction counts as catastrophic. Record it
  in DECISIONS.md with a timestamp, before computing.
- Confirm the §4 reporting limit is expressible in the output schema: results aggregate by
  homology class, per-family curves stay separable for the disclosure package.

## Done when

- Family set, both cost metrics, stringency axis and coverage metric are written and
  reimplementable from the text alone.
- The regime boundary is pre-registered in DECISIONS.md, before any computation.
- The output schema can produce the aggregated view §4 requires without recomputation.
- No metric requires training or running a model, per §C5.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`, pull request #30.** Nothing is waiting on
the project owner. Everything is fixed in **D-204** and written up in `metrics/costcurve.md`,
which is the authoritative text; `src/amazebio/costcurve.py` is the first implementation and
C6.3 reimplements the curves from the document.

**Nothing was computed before the definitions were fixed**, which is the point of the task.

- *Family set, both cost metrics, stringency axis and coverage metric reimplementable from the
  text alone* — met. The set is Pfam 38.2 entered by three published nominations, curve
  subjects being the virus-family and toxin strata; the organism stratum is counted and
  carries no curve, because a regulation naming an organism nominates no protein family.
- *The regime boundary is pre-registered before any computation* — met, and anchored to a
  measured quantity rather than a round number: catastrophic is "costs at least as much
  general biology as removing every virus", which is A8.1's 1.1154% of UniRef50 clusters.
- *The output schema produces §4's aggregated view without recomputation* — met.
  `published_view` aggregates by Pfam clan, pools clanless families, and withholds any class
  that would hold fewer than three subjects, so no family is nameable from the published form.
- *No metric requires training or running a model* — met. Every quantity is a count over
  pinned databases or arithmetic on such counts.

One input is dated rather than pinned and says so: UniProt's REST service serves the current
release only, so the nomination step records the release it saw, as the select-agent count
already does.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

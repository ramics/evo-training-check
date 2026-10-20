---
id: A9.1
title: Measure denylist decay against taxonomy updates
phase: A
status: in-progress
gate: false
depends_on: [A0.3]
blocks: []
design_ref: "§A9"
deliverable: 1
owner: claude
---

# A9.1 — Measure denylist decay against taxonomy updates

**Design reference:** DESIGN.md §A9 · **Deliverable 1**

## Goal

Replay the frozen denylist against successive taxonomy releases to quantify how much in-scope
diversity it stops naming over time, and derive the implied re-validation interval.

## Steps

- Pin the taxonomy releases to replay against, from the denylist's own vintage to current.
- For each release, identify taxa in scope by the policy's stated intent but not named by the
  frozen list: newly erected families, splits, renames, and reassignments across its boundary.
- Separate genuine new diversity from pure nomenclature churn — a rename that moves nothing is
  not decay, and conflating the two would inflate the result.
- Express decay over time and derive a re-validation interval with its assumptions stated.
- Test whether the host-occurrence rule decays differently from the named list, since a rule
  that reads the database each time may age better than a static enumeration. That contrast is
  the actionable part for filter designers.

## Done when

- Decay quantified across the pinned releases, with nomenclature churn separated out.
- Re-validation interval derived, with assumptions stated.
- The static-list versus computed-rule contrast is reported.
- Result is framed as applying to label-based filters generally, not only to these two.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner yet.

**Read D-199 before choosing the baseline.** A8.1 found two decay cases in the *pinned*
taxonomy, before any replay: `Reoviridae` is no longer a family name there, and
`require_rank: realm` asks for a rank NCBI has never used. The first is decay at time zero;
the second is not decay at all but a vocabulary mismatch, and conflating them would start the
curve at the wrong place.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

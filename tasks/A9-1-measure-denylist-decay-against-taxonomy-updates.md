---
id: A9.1
title: Measure denylist decay against taxonomy updates
phase: A
status: done
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

`review`. **Branch `claude/project-thread-a3vch4`, pull request #30.** Nothing is waiting on
the project owner.

Result in **D-202**; the window and the decay/churn separation were fixed first in **D-201**.
Artefacts `artifacts/a9-1/decay.json` and `decay.md`, each dump digested, uploaded to the
durable results store.

Done-when, one by one. *Decay quantified with churn separated* — reach 75.83% at the baseline
to 65.17% at 2026-10, driven by 44,261 new unnamed viral taxa against 787 renames, 890
renumberings and 7,723 re-ranks, never summed. *Re-validation interval with assumptions* —
4.34% of the viral taxonomy per year, reported at three tolerances with four stated
assumptions rather than as one constant. *Static versus computed contrast* — the realm rule
falls 8.39% relative against the list's 14.06%, with the caveat that the realm framework was
itself still filling in before the baseline. *Framed generally* — the slope is the same either
side of the filter's own vintage, so the finding is about how a list of names is built, not
about these two releases.

The case to lead with: `Herpesviridae` became a synonym of `Orthoherpesviridae` in January
2026, so a filter that names it as a family scientific name now removes no herpesvirus, and
nothing in the filter's output says so. Two of the other thirty names have failed the same
way.

**Read D-199 before choosing the baseline.** A8.1 found two decay cases in the *pinned*
taxonomy, before any replay: `Reoviridae` is no longer a family name there, and
`require_rank: realm` asks for a rank NCBI has never used. The first is decay at time zero;
the second is not decay at all but a vocabulary mismatch, and conflating them would start the
curve at the wrong place.


## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Closed — 2026-10-20

`done`. The work is on `main` (pull request #30 merged, or earlier as the State block
records). Every Done-when criterion is met.

---
id: B3.1
title: Compute sequence-profile homology scores
phase: B
status: done
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 1"
deliverable: 3
owner: claude
---

# B3.1 — Compute sequence-profile homology scores

**Design reference:** DESIGN.md §B3 item 1 · **Deliverable 3**

## Goal

Compute the length-normalised sequence-profile homology score for each assay target against
each model's surviving corpus. Secondary measure per §B3.

## Steps

- Implement best-hit profile search of each target against each surviving manifest.
- Length-normalise as specified; fix parameters in advance and record them.
- Emit per target × model × reading scores in the shared homology schema.
- Record how absent hits are represented, distinguishing them from low scores.

## Done when

- Scores computed for all targets against all manifests.
- Parameters fixed in advance and recorded.
- Absent-hit representation documented and handled consistently downstream.

## State — 2026-11-17

`done`. PR #44 merged on 2026-10-26; this file sat in `review` for three weeks afterwards with
nothing waiting on anyone. The criteria below were met by the merged work, and B3.3 — the third
measure of the same axis, from the same pull request — was already recorded as done.

The shared contract is `metrics/homology.md` — binding on B3.5 and B5 — and
`src/amazebio/homology.py` is its only producer. Four kinds rather than a score and a null
(D-256): `measured`, `absent`, `not_searched`, `unanswerable`. `Row` refuses a score beside
anything but `measured` and derives `bound` from the depth; `check_complete` refuses a table
missing a target x manifest x measure cell, so "all targets against all manifests" is a
property the artefact has rather than a claim this file makes. 651 rows, no cell missing.

**Depth, declared before any result was read (D-258): a seeded hash band of 0.1 per component,
at A2.1's sampling seed.** Measured throughput puts a census at about seventeen hours of
container time; the band is ten to a hundred times A2.1's own detection depth, and reusing
A2.1's seed nests its sample inside this one, which is what makes the cross-check directional.
Both passes completed: Evo 2's component 295,435 records and 1.21 bn protein residues in 48
minutes, Evo 1's 265,062 records and 1.13 bn residues in 56 minutes. Every row carries
`searched_fraction: 0.1` and `bound: lower`. The census stays available behind `--rate 1.0`.

**Reporting.** The axis is internal because of how it is keyed: a row names an assay and an
assay identifier names an organism, so the per-assay rows, the matched record identifiers and
any ordering of assays by score are restricted under D-125 and go to the project owner. What
publishes is by homology class and survival route, and nothing before X3.1.

Artefacts: `corpora/results/b3-targets/`, `corpora/results/b3-pass/`,
`corpora/results/b3-homology/`, `corpora/results/b3-3/`, each with its run manifest.
`pixi run -e dev check` green locally at 2,526 tests; **CI did not run** — the repository has
hit its GitHub Actions limit.

**B3.1's own result.** 28 profiles, one per distinct distributed alignment, built before any
corpus record was read. Of 31 targets, 19 have a `measured` sequence-profile score against Evo
2's manifest and 10 against Evo 1's; the rest are `absent` at this depth, which is a censored
observation at the cut and not a zero. No target is `unanswerable` — every one has an
alignment.

**The instrument is not §B3's named tool, and D-255 records why.** §B3 says jackhmmer; jackhmmer
builds its model out of the database it searches, so from the second iteration the score stops
being a property of the target and becomes a property of the corpus, which is the variable §B5
is trying to explain. The profile is built instead from the alignment the benchmark's
maintainers distribute — the same object B3.4 took the depth covariate from, digest for digest.
The write-up must say "profile search" and never "jackhmmer".

### Done-when
- *Scores computed for all targets against all manifests* — met, and enforced rather than
  asserted: `homology.check_complete` refuses a missing cell.
- *Parameters fixed in advance and recorded* — met. The acceptance rule is A2.1's, imported from
  `amazebio.profiles` rather than restated, with a test pinning the import; the depth is D-258.
- *Absent-hit representation documented and handled consistently downstream* — met, and it is
  the reason the kind vocabulary exists (D-256).

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

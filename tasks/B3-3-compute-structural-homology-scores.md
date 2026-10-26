---
id: B3.3
title: Compute structural homology scores
phase: B
status: done
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 3"
deliverable: 3
owner: claude
---

# B3.3 — Compute structural homology scores

**Design reference:** DESIGN.md §B3 item 3 · **Deliverable 3**

## Goal

Compute nearest-structure similarity for each target against each surviving corpus. This is the
pre-registered PRIMARY homology measure.

## Steps

- Resolve or predict structures for every assay target; record which and document the mix.
- Compute nearest-surviving-structure similarity per target × model × reading.
- Fix all parameters in advance; record them before results are inspected.
- Quantify how structure-source heterogeneity could bias the scores.

## Done when

- Primary homology scores computed for all targets against all manifests.
- Structure provenance recorded per target; heterogeneity bias assessed.
- Parameters frozen before inspection, per §B3's pre-registration requirement.

## State — 2026-10-26

`done`, at two of three Done-when criteria, **closed by the project owner's ruling (D-259): the
structural corpus pass is not being bought, now or later.** The third criterion is therefore
unreachable rather than open, and this file records it as closed rather than pending.
**Branch `claude/project-thread-bywmyz`, PR #44.**

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

**B3.3 is §B3's pre-registered PRIMARY measure and no manifest could be searched for it.** Both
walls are A2.2's, one phase earlier and over the same corpora. The TM-score is unavailable on
the publisher's own statement: a structural-alphabet database predicted from sequence carries no
C-alpha, so the tool refuses TM-score and LDDT output outright (D-167). The coordinate-free bit
score that remains was priced at 70+ instance-hours for one manifest against a $30 ceiling and
declined (D-180). Nothing in this task's geometry changes either: the corpus side is the same
objects at the same depth. Every `structural` cell is `kind: not_searched` with the reason, on
A2.2's precedent, so the primary measure's absence travels with the axis rather than being
inferable from which measure has numbers. D-257 records the scope.

**What did ship, and it is not nothing.** All 31 targets resolve to a structure from the
benchmark's own pinned archive — one predictor, so the query side is homogeneous — with a median
87.5% of residues at or above the predictor's confidence floor and **none below half**. So the
query side would not have been the limiting factor had the pass been bought; the limit is
entirely the corpus side, which is the sentence A2.2 ended on. The search parameters a bought
pass would run under are declared, with the acceptance threshold deliberately `null`: A2.2's 500
bits was calibrated against decoys in a different geometry, and carrying it over would be a
declared threshold calibrated against nothing.

### Done-when
- *Primary homology scores computed for all targets against all manifests* — **not met, and
  permanently unreachable** (D-259). Two independent reasons, neither of which a later session
  should re-open: the measure §B3 names is uncomputable, because the tool does not give a
  TM-score against a structural alphabet predicted from sequence (D-167); and the coordinate-free
  route that remains was priced and **declined outright by the project owner** on 2026-10-26
  (D-180, D-259). The cells exist as `not_searched` with the reason.
- *Structure provenance recorded per target; heterogeneity bias assessed* — met.
- *Parameters frozen before inspection, per §B3's pre-registration requirement* — met, and this
  is the only measure for which freezing before inspection was possible at all, since no hit
  was ever seen.

**Settled by the owner, 2026-10-26 (D-259).** The pass was put to him with its cost and with
what it would buy: structure is conserved past the point where sequence similarity is
detectable, so the structural route would have found relatives the profile search misses and
moved the sequence counts *up* — a tighter bound on the same quantity in the same direction, not
a second opinion about it. The asymmetry §B3 is establishing is already large and already
one-directional, so he declined it. Four things follow and are binding downstream:

- **`sequence_profile` is not promoted to primary.** `structural` stays marked primary in
  `metrics/homology.md` with no searched manifest. Promoting the measure that happens to have
  numbers is selection on the instrument.
- **B5.1's pre-registration inherits a stated absence:** the sequence measure as the one
  carrying numbers, the structural measure recorded absent with D-259 as the reason, and an
  explicit line that an `absent` row is **censored at the cut, not a zero** (D-256).
- **The sequence counts are floors and are reported as floors** — bounded both by the 0.1 band
  (D-258) and by the missing structural route.
- **The pass goes under "where funding extends this"**, with its price and what it would buy,
  the same handling D-236 gave the RVDB-prot deepening.

Whoever reports this axis — A6.1, X2.1, B5.4 — states in the first paragraph that the
pre-registered primary measure has no numbers, rather than in a footnote.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

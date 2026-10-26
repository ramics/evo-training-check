---
id: B3.2
title: Compute domain-level presence
phase: B
status: review
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 2"
deliverable: 3
owner: claude
---

# B3.2 — Compute domain-level presence

**Design reference:** DESIGN.md §B3 item 2 · **Deliverable 3**

## Goal

Determine, per target, whether its annotated domains are present in each surviving corpus — as
a binary and a count.

## Steps

- Annotate domains for every assay target; pin the annotation resource version.
- Test presence of each domain in each surviving manifest.
- Emit binary and count outputs in the shared homology schema.
- Document how multi-domain targets are handled.

## Done when

- Domain presence computed for all targets against all manifests.
- Multi-domain handling rule documented and applied consistently.
- Annotation resource version pinned.

## State — 2026-10-26

`review`. **Branch `claude/project-thread-bywmyz`, PR #44.** Nothing is waiting on the project
owner for this task.

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

**B3.2's own result.** 71 distinct Pfam families annotated across the 31 targets, at the Pfam
38.2 pin's own gathering cutoffs and A2.1's model-coverage floor. 62 of the 71 are present in
Evo 2's manifest and 12 in Evo 1's. One target carries no annotated family at those cutoffs and
is `unanswerable` rather than `absent` — nothing was looked for.

**The cross-check against A2.1 holds on all six Evo manifests.** Because this pass reuses A2.1's
sampling seed at a larger rate, every record A2.1 searched is a record this pass searched, so a
family A2.1 detected **must** be present here. It is: 2 of 2 on Evo 1, 20 of 20 on Evo 2, and
the deeper band finds 10 and 42 more. A violation would have been a finding about one of the two
pipelines; there is none.

**Multi-domain rule.** A target is annotated to a *set* of families, de-duplicated by
accession: a domain occurring twice is one family and the instance count travels in `evidence`
rather than in the score. The score is the count of families present and `normalised` is that
over the number annotated, so a single-domain and a six-domain target are comparable; the binary
§B3 also asks for is `score > 0`, derived rather than stored so the two cannot disagree.
Accessions join on the stem — the registry writes `PF00717.29`, A2.1's tables write `PF00717`.

### Done-when
- *Domain presence computed for all targets against all manifests* — met, enforced by
  `homology.check_complete`.
- *Multi-domain handling rule documented and applied consistently* — met; the rule is in
  `metrics/homology.md` and the artefact carries both the count and the per-family verdicts.
- *Annotation resource version pinned* — met: Pfam 38.2, the same registry pin A2.1 searched.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A2.4
title: Detect integrated elements in surviving bacterial genomes
phase: A
status: review
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.4 — Detect integrated elements in surviving bacterial genomes

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Identify integrated elements in the surviving bacterial component, another route taxonomy
labels do not capture.

## Steps

- Select and pin the detection tools named in §A2.
- Run over the surviving bacterial component of each manifest.
- Attribute hits to the 'integrated-element' survival route.
- Cross-check a sample of calls against a second tool for concordance.

## Done when

- Hit tables exist with route attribution.
- Two-tool concordance measured on a documented sample.
- Parameters and versions recorded.

## State — 2026-10-18

`review`. **Branch `ccr-a062d0fd-ocvx60`.** Every Done-when criterion is met; the result is
D-155 and the artefacts are at `corpora/results/a2-4/`.

**The result, 0.25% of both releases.** Every detection `element_kind: prophage`,
`estimate_kind: lower_bound`:

| release | genomes | bases | proviruses | Pfam viral | RVDB-prot |
|---|---|---|---|---|---|
| Evo 1 (GTDB v214.1) | 375 | 699 Mb | 128 | 203 / 1,719 = 11.8% (10.4-13.4) | 90 / 13,679 = 0.66% (0.54-0.81) |
| Evo 2 (v214.1 + 220.0) | 300 | 946 Mb | 178 | 251 / 1,719 = 14.6% (13.0-16.4) | 153 / 13,679 = 1.12% (0.96-1.31) |

Viral families inside integrated elements inside bacterial genomes the filter's rules never
reached — `out_of_scope` under charitable and literal, `retained_by_design` under strict, with
identical counts. D-007's headline route as measurement. Not a conformance failure: no rule was
broken because no rule applied.

**Concordance (D-114).** Evo 1: 40 records, kappa **0.908** (0.731-1.000). Evo 2: 28 records,
kappa **0.652** (0.337-0.968), with disagreement directional — VIBRANT calls three elements
geNomad does not, against one the other way. The headline is geNomad's, so on Evo 2 it is the
more conservative instrument.

**Cost, measured (D-149).** 0.996 core-min/Mb on real draft assemblies, 2.74x cheaper than
D-117's single-genome figure. The band ran 5h28m and self-terminated.

**What was checked rather than assumed.** The cache's route handling (literal matches charitable
exactly, strict differs only in route, reused rows marked); the sampling's determinism (375
genomes and 699,031,198 bases reproduced exactly across two separately launched instances); and
every table's `estimate_kind`.

**Open for the project owner: depth.** At the measured rate with de-duplication, 2.5% is about
33 wall hours and $7. It exceeds one instance's window, so it needs a longer timer or per-object
resumability. 0.25% is a shallow bound — a detection is a detection, but a null at this depth
would be weak — so deepening is an improvement to the strength of the claim rather than a
missing criterion.

**Six faults this task found by watching runs rather than reading code**, each invisible in a
green test suite: a probe writing `population` over one genome; the end-of-run upload that would
have lost a night's work; a genome straddling a shard boundary getting colliding contig names;
geNomad's output swallowed so its hours were silent; detection repeated per reading; and the
collector flattening archived runs onto live ones.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

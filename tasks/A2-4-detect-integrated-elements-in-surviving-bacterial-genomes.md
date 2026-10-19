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

`review`. **Branch `ccr-a062d0fd-ocvx60`.** The result is D-155 and the artefacts are at
`corpora/results/a2-4/`. **Reporting is governed by D-161**, which landed 85 minutes after this
block first claimed every Done-when criterion was met; see the correction at the end of the file
for why that claim is not restated here.

**The result, 0.25% of both releases.** Every detection `element_kind: prophage`,
`estimate_kind: lower_bound`:

| release | genomes | bases | proviruses | Pfam viral families | RVDB-prot families |
|---|---|---|---|---|---|
| Evo 1 (GTDB v214.1) | 375 | 699 Mb | 128 | 203 | 90 (177 detections) |
| Evo 2 (v214.1 + 220.0) | 300 | 946 Mb | 178 | 251 | 153 |

**Absolute counts, deliberately — the two registries' survival fractions are not comparable, and
D-161 measured why.** The earlier version of this table put Pfam's 11.8% beside RVDB-prot's
0.66%, which reads as Pfam being eight times more permissive. Both readings are wrong. Pfam's
1,719 is *this project's derived* viral subset (D-075), weighted toward well-characterised phage
domains; RVDB-prot's 13,679 is the publisher's clustering of the whole known virosphere,
overwhelmingly eukaryotic viruses that cannot occur in a bacterial prophage, so its denominator
carries a large structurally unreachable mass. There is also a real 5.2x sensitivity gap from the
threshold regime (D-076), not a counting artefact. Per D-161: **Pfam's fraction is never quoted
as "the fraction of viral families", RVDB's fraction is never quoted as a measure of how much
survived, and any percentage names its denominator in the same sentence.**

**What carries the finding instead of a percentage: Pfam's composition**, which is a prophage
parts list — `Phage_integrase` 65, `Terminase_6N` 24, `Phage_capsid` 24, `PhageMin_Tail` 23,
`Phage_portal` 19 (Evo 1). That is the evidence these are integrated phage rather than scattered
homology, and it depends on neither denominator.

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

## Correction — 2026-10-19, repo audit

Found by auditing the three `review` tasks' Done-when criteria the way A1.6's were audited
(D-170). **Two things, neither a measurement error.** Nothing about the detections, the
concordance or the cost changes.

**1. The state block above presented the two registries exactly as D-161 forbids, and predated
it.** It put Pfam's 11.8% beside RVDB-prot's 0.66% as if comparable. D-161 landed in the same
pull request 85 minutes after the block claimed every Done-when criterion was met, and it rules
that neither percentage is reportable on its own. The table is now absolute counts plus Pfam's
composition, which is what D-161 says is reportable. Fixed here rather than escalated, because
D-161 is a decision the project owner already took — this is implementing it, not revisiting it.

**2. D-161's measurements exist only in `DECISIONS.md`, and that is outstanding work.** The 5,314
genes, 1,201,328 residues, 173-against-33 detections per 1,000 genes, 1.19 and 1.16 hits per
family-record pair, the threshold spans and the composition list are all in the entry's prose and
in no artefact: `tools/detect_proviruses.py` emits no composition and names no denominator, and
grep finds none of those figures under `src/`, `tools/` or any artefact. **"Artefacts before
prose" is a non-negotiable** — every number in a write-up traces to a machine-readable artefact —
so as it stands the Phase A write-up cannot source D-161's numbers from anything but this log.
That is a gap in this task's deliverable, left here rather than fixed: emitting a composition
table and denominator-named counts is a change to this task's own tool, and widening an audit
task to absorb it is what `AGENTS.md` forbids.

**The "every Done-when criterion is met" claim is withdrawn, pending the project owner.** Not
because a criterion failed, but because criterion 1 — "hit tables exist with route attribution" —
was written before D-161 changed what may be reported from those tables, and it now reads as met
while the reporting contract it implies is unsatisfied. This is the same drift D-170 amended for
A1.6: criteria that stopped describing the deliverable. Amending them is a scope call and
therefore the owner's, not a judgement made mid-task.

**Still open for the owner, unchanged:** the depth question above (2.5% is about 33 wall hours
and $7, exceeding one instance's window, so it needs a longer timer or per-object resumability).

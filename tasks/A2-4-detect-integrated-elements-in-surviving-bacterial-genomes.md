---
id: A2.4
title: Detect integrated elements in surviving bacterial genomes
phase: A
status: in-progress
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

## State — 2026-10-17

`in-progress`. **Branch `ccr-a062d0fd-ocvx60`** carries the work; `main` has this file, the
board and D-112 to D-117.

**Why this task.** Of the four ready A2 detectors it is the one whose inputs are already staged
— OpenGenome2's GTDB v220 component was staged with "A2.4 searches these genomes for integrated
elements" as its stated reason — and whose tool was already pinned. A2.3's eukaryotic inputs are
2.17 TB and deliberately unstaged; A2.2 needs a structure search tool the environment does not
carry.

**Pre-registered, before any output existed (D-112..D-116).** The instrument pin is separate
from A4.2's object of study — A4.2 benchmarks geNomad 1.1.0 because that is the version IMG/VR's
labels came out of, and detecting with the same 2022 build against the same 2022 markers would
make the audit's blind spot and the filter's the same one. A2.4 runs geNomad 1.12.0 against
marker database v1.9, the newest pairing the publisher attests. Localisation comes from the
provirus finders and family identity from A2.1's registries at D-076's thresholds unchanged, so
an A2.1 table and an A2.4 table differ only in route, element kind and records searched.
VIBRANT 1.2.1 is the second tool, with agreement fixed at 0.5 reciprocal overlap and
disagreement reported by direction. And A2.4 answers for Evo 2's bacterial component **without
standing in for Evo 1's**, which is not staged — so Evo 1's tables are `not_searched`, not zero.

**Done.** `src/amazebio/proviruses.py` and `tests/test_proviruses.py` — pins, both output
parsers, reciprocal overlap, the record-level 2x2 and Cohen's kappa. 40 tests, full `check`
green at 829 passed. The two environments are in the lockfile (`feature.proviruses`,
`feature.vibrant`) and both tools run.

**Both parsers are validated against real output, and it caught two errors.** geNomad 1.12.0 on
*E. coli* K-12 returns five proviruses at the known positions of its cryptic prophages, and that
run is pinned as `tests/data/genomad_1_12_0_ecoli_provirus.tsv`. The score column is
`v_vs_c_score`; the documented guess `virus_score` had been returning `None` for every call.
VIBRANT's header, read off the line of `VIBRANT_run.py` that writes it, puts its protein columns
*before* its nucleotide ones — the opposite of the first assumption here — and its databases
turn out to be versioned after all (KOfam 2019-08-10, Pfam 32.0, VOG 94, hard-coded in
`VIBRANT_setup.py`), so the pin records them instead of reporting a gap that does not exist.

**Left, in order.** The size-stratified in-region calibration that fixes the sampling rate
(D-117). Then `tools/detect_proviruses.py`: read A1.4's manifests, sample, run the two tools,
search the provirus proteins against A2.1's registries, emit the `metrics/detections.md` table.
Two things it needs that do not exist yet — A1.4's manifests are not in this container and are
not in the audit store either, so they have to be regenerated before A2.4 can consume them; and
A2.1's search loop has to move out of `tools/detect_profiles.py` into the library for both tools
to call it (D-113).

**Waiting on the project owner — two questions, both put to them on 2026-10-17.**
The **spend** for the pass: a full census of GTDB is about 4,900 core-hours on the single-genome
calibration, the same order as A1.6's authoritative pass, against a sampled pass for a fraction
of it (D-117).
And whether to **stage Evo 1's prokaryotic component**, 130 GB, without which Phase A's prophage
route is measured on one of the two corpora under audit and not the other (D-116).

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

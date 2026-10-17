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

`in-progress`. **Branch `ccr-a062d0fd-ocvx60`** carries the work; `main` has only this
file, the board and the decision entries.

**Why this task now.** Of the four ready A2 detectors it is the one whose inputs are
already staged — OpenGenome2's GTDB v220 component was staged with "A2.4 searches these
genomes for integrated elements" as its stated reason — whose tool is already pinned
(geNomad 1.1.0, `feature.genomad`, with `src/amazebio/genomad.py` holding the version
evidence and the output parser), and whose error behaviour A4.2 already measured.
A2.3's eukaryotic inputs are 2.17 TB and deliberately unstaged; A2.2 needs a structure
search tool the environment does not carry.

**Left.** Everything. Pre-registration first: the second tool for the concordance
criterion, the sample it is measured on, and the thresholds — all fixed before any
output is inspected.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

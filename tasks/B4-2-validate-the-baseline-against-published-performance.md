---
id: B4.2
title: Validate the baseline against published performance
phase: B
status: review
gate: false
depends_on: [B4.1]
blocks: [B5.1]
design_ref: "§B4"
deliverable: null
owner: claude
---

# B4.2 — Validate the baseline against published performance

**Design reference:** DESIGN.md §B4

## Goal

Confirm the baseline is implemented at its published strength, so the §B4 attribution logic
rests on a strong comparator rather than a straw man.

## Steps

- Reproduce the baseline's published benchmark performance within a stated tolerance.
- Investigate any shortfall before the baseline is used in analysis.
- Record the achieved-vs-published comparison as a published artefact.
- State the tolerance in advance.

## Done when

- Published performance reproduced within a pre-stated tolerance.
- Any shortfall explained, or the baseline fixed.
- GATE-adjacent: B5 must not run on an unvalidated baseline.

## State — 2026-10-21

`review`. The comparison is published: `artifacts/b4-2/reference-audit.{json,md}` and the same
objects under `corpora/results/b4-2/`, from `tools/baseline_reference_audit.py`. It runs no model
and rebuilds no alignment — it is arithmetic over B4.1's published artefacts and the benchmark's
own per-variant scores, so it reproduces from pins in seconds.

**The tolerance was stated in advance and nine assays fall below it.** D-208 fixed the
variant-level floor at 0.99 before any score existed, and B4.1 measured 19 assays at or above it,
three undetermined and nine below, the weakest at 0.8207. That floor stands; this task's job was
to explain the shortfall, not to move it.

**The answer, recorded as D-248: the two sides disagree about what the alignment column
contains.** Within one position the baseline's ranking is its log-odds ratio alone, so every
amino acid absent from the column shares the most extreme score, and the sets can be compared
exactly. In the six worst assays the published column treats between 9.0% and 23.7% of compared
variants as absent where this implementation finds them present. No assay that reproduces the
column exceeds 1.7%, and across all 31 assays the reverse case happens 28 times in total. The
difference runs one way: the published column saw a narrower sequence set.

Ruled out on the way: the formula (the structural half agrees), the coordinates (both assays with
a non-trivial `MSA_start` compare on their full variant sets, and no position shift helps any
assay), and the unscored multiples (of the four assays with them, one reproduces, one is
undetermined, two diverge).

**It is not a mis-set parameter here either.** `tools/baseline_knob_probe.py` samples the
package's documented filtering knobs. The defaults reproduce B4.1's figures exactly; `min_seqid`
is the only one that moves anything, and it moves assays in opposite directions — the weakest
rises from 0.8207 to 0.8629 at 0.5 while the strongest falls from 0.9985 to 0.8692 at the same
setting. No value fits both and none reaches the floor on the weakest assay. **The parameters do
not move on the strength of that table**: choosing one to maximise agreement with the column the
baseline is validated against would fit the baseline to its own validation.

**What the task exists for is answered.** §B4 must not rest on a straw man, and the test of that
is the assay level — our correlation against the experiment beside the published column's, with
an interval on the difference. This implementation is **better on 13 assays, indistinguishable on
13 and worse on 5**, and only three of the five are worse by more than 0.02. The baseline is at
published strength.

**The restricted denominators, stated rather than implied.** The baseline leaves multiple
substitutions unscored while the published column scores them, so every comparison is over the
variants both cover: `CAPSD_AAV2S_Sinai_2021` 532 of 42,328 (1.3%), `POLG_PESV_Tsuboyama_2023_2MXD`
995 of 5,130 (19.4%), `RCRO_LAMBD_Tsuboyama_2023_1ORC` 1,195 of 2,278 (52.5%),
`RPC1_BP434_Tsuboyama_2023_1R69` 1,124 of 1,459 (77.0%). The other 27 assays compare on the whole
assay. A verdict on CAPSD is a verdict on 1.3% of it and the artefact says so on the row.

**Left open deliberately.** Which filtering or preprocessing step produced the narrower sequence
set is not established, because that would mean reconstructing an input the benchmark does not
publish. D-248 records it as a limitation of the published artefact so B5 can cite it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

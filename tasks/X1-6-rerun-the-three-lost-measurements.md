---
id: X1.6
title: Re-run the three lost measurements
phase: X
status: in-progress
gate: false
depends_on: []
blocks: [X1.2, X1.3]
design_ref: "§7"
deliverable: null
owner: claude
---

# X1.6 — Re-run the three lost measurements

**Design reference:** DESIGN.md §7 · **Decisions:** D-188, D-189

Three measurements have no surviving artefact and no intermediate to resume from. Each needs its
job run again from the top. They are unrelated in subject and share only that their output was
written somewhere that did not survive, so they are one task because the work is the same shape,
not because the results belong together.

The sister task X1.5 covers the hygiene that follows from the same cause — finding any tool that
writes a result the durability guard cannot see, and correcting the artefact contracts that still
point consumers at `artifacts/`. Neither task depends on the other.

| | what it costs | why nothing can be reused |
|---|---|---|
| **A2.1** profile detections | **~20 h** | the protein cache was deliberately ephemeral (D-103 bars corpus sequence from the audit store), so gene calling is redone |
| **A4.2** taxonomy benchmark | hours | the ICTV exemplar sequences live in git-ignored `data/` and are re-downloaded first |
| **A1.6** caps measurement | ~2 h, ~$0.25 | one shard, six cells; nothing partial survives |

## Steps

- **A2.1, shallow first.** Its sampling is a deterministic hash of the record id and **rates are
  nested**, so the pre-registered depth is about a tenth of the deepened pass and a superset
  relationship holds: re-running shallow costs ~2 h and yields a backed artefact, and deepening
  to D-099's depth is then a separate decision rather than a precondition. The figures to land
  against are in A2.1's own file — Pfam 470 and RVDB 572 on Evo 1, 492 and 1,456 on Evo 2 at the
  first pass; 590/1,091 and 811/4,154 deepened.
- **A4.2.** Re-download the pinned ICTV exemplar set, then the geNomad run. The error rates by
  direction and their exact intervals are in A4.2's file and the decisions log.
- **A1.6's caps measurement, under a NEW artefact name.** `--measure caps` defaults to
  `cap-measurement.json`, and that key's published figures are cited in A1.6's file. Writing
  there substitutes a fresh measurement for the published one under a cited key, which is worse
  than the gap — the same hazard A1.6 itself recorded twice and `esm3_calibrate.py`'s own module
  docstring warns about. Pass `--artefact-name` something new, and **never `--measure curve`**:
  `calibration.json` survived and holds published figures.
- **Check each regenerated figure against the recorded one, and write the comparison down** —
  agreement or disagreement. This is the first occasion on which any of these numbers can be
  checked against the committed code at all, so a mismatch is a finding and not a licence to
  adjust anything.

## Done when

- Each of the three has an artefact in object storage with its `run.json`.
- Every regenerated figure is compared against the recorded one and the comparison is recorded.
- A1.6's re-measurement sits under its own key, with the published one's loss stated beside it.

## Notes

**Why this blocks X1.2 and X1.3.** One-command reproduction and the figures both read result
artefacts, and neither can run against tables that are not there. A3.2 and A6.1 also want A2.1's
tables, but both sit behind their own gates, so the dependency is recorded here rather than as an
edge that would move their status.

**What is not in scope and needs no re-run.** A1.6's `viral-seeds.faa` is intact at
`corpora/samples/a1-6/uniref100/2023_02/rate40/viral-seeds.faa` — 1,249,029,570 bytes, sha256
`8a23f5ea…45632`, which is the key its own sample manifest names and the digest the exposure
manifests cite. The copy that was destroyed was a duplicate under `results/`. A1.6's `band.json`
was the superseded five-cell state and `band-viral-arm-5cells-backup-20261018.json` holds it;
`band-complete.json` is authoritative and untouched. Do not rebuild either.

**In flight.** Work is on branch `claude/busy-cannon-e6evl8`. All three re-runs are in scope for
this sitting, with A2.1 at its pre-registered shallow depth only — the ten-fold deepening remains
a separate decision, per the Steps above. Nothing finished yet; nothing waiting on the owner.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

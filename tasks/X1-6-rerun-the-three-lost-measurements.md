---
id: X1.6
title: Re-run the three lost measurements
phase: X
status: done
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

## Outcome — 2026-10-19 — all three re-ran, every figure reproduced (D-192)

Branch `claude/busy-cannon-e6evl8`, two tool fixes. Each measurement has an artefact in object
storage with its run manifest, so the three Done-when criteria are met. **Nothing was adjusted to
match a recorded figure.** A2.1 ran at its pre-registered shallow depth only; the ten-fold
deepening remains a separate decision.

### A2.1 — profile detections, shallow pass

| release | registry | published first pass | regenerated |
|---|---|---|---|
| `opengenome` | Pfam viral | 470 of 1,719 | **470** |
| `opengenome` | RVDB-prot | 572 of 13,679 | **572** |
| `opengenome2` | Pfam viral | 492 of 1,719 | **492** |
| `opengenome2` | RVDB-prot | 1,456 of 13,679 | **1,456** |

Identical across all three readings, `esm3-proxy` correctly `not_searched`. Both denominators
reproduced from the re-staged registries, every pinned digest matching: Pfam viral 1,719 of
30,134, RVDB-prot 13,679 counted against 13,679 stated. Corpus sizes agree too — stage2 as
2,652,947 + 50 + 50 = 2,653,047 records. 32 objects, 40 MB, `run.json` and `run-all.json`.

### A4.2 — taxonomy-tool misassignment

| figure | published | regenerated |
|---|---|---|
| escape | 546/1,507 = 36.23% (33.80–38.72) | **identical** |
| spurious removal | 50/1,642 = 3.05% (2.27–4.00) | **identical** |
| escape causes | 344 / 119 / 52 / 28 / 3 | **identical** |
| evaluation set | 3,149 seqs, 1,507 in scope / 44 families, 1,642 controls / 189 | **identical** |
| dependency: geNomad share of the denylist's hits | 38.56% | **38.5573%** |
| corpus, denylist hits | 15,677,623 · 181,530 | **identical** |
| propagation | 109,760 in scope, 39,767 (35,736–44,218) escaping | **identical** |

The pinned VMR matched its sha256 and byte count, and the geNomad 1.1 marker database matched
its pinned digest. The dependency pass had to be re-run as well: `misassignment.json` carries
`propagation: null` without it, and the propagation figure is one of A4.2's headline results.

### A1.6 — caps measurement, under `cap-measurement-rerun-20261019.json`

Six cells against a query and target identical to the published run's — 31,381 seeds, 417 M
residues, one shard.

| cap | relaxed: published → regenerated | `--cov-mode 1`: published → regenerated |
|---|---|---|
| slack, 100,000 | 2,137 s → **2,127.1 s** | 1,450 s → **1,441.4 s** |
| 50% | 770 s / 0.9% → **769.5 s / 0.88%** (288) | 356 s / 3.3% → **343.6 s / 3.31%** (1,073) |
| 20% | 530 s / 2.3% → **532.4 s / 2.28%** (743) | 252 s / 9.7% → **242.1 s / 9.72%** (3,148) |

All four findings stand. The cap does not bind: **5,078** hits/seed relaxed and **1,444** filtered
against 100,000 — the published prose said "~1,445", and the exact value is the sort of thing an
artefact keeps and a sentence rounds. A lower cap costs 3.75x more recall under filtering than
relaxed (3.31% against 0.88%). Relaxed coverage costs **1.476x** filtered against the published
1.47x. The reading-1 agreement check is identical: 32,644 post-filtered against 32,374 from the
aligner, **270** found only by the post-filter and none only by the aligner. This run also wrote
the `cap_summary` the published one ended too early to produce. `--cap-shard-points 1` was passed
deliberately: it reproduces the six cells that were published, and the published run ended before
its second target size, so there was never a linearity check to compare against.

`m6i.2xlarge` spot, about 1.5 h. The first spot request was refused for capacity with nothing
launched and nothing billed; the retry succeeded. A dry run does not check capacity, so three
dry runs spent on that question answered nothing — `AGENTS.md` says as much.

### Two defects found in the tools, both fixed on the branch

- **`detect_profiles.py --plan` was broken on `main`** — one argument to a two-argument function,
  and its result indexed as a mapping. The searches were never affected; a reporting path runs
  only when somebody asks what a run would read, which is the cheap check before a multi-hour
  search. Now a tested `plan_lines`.
- **`esm3_calibrate.py --artefact-name` moved the result and not its manifest**, so this re-run
  wrote `run-calibration.json` — the provenance key of the run it was replacing, in a bucket with
  no `DeleteObject`. Nothing citable was lost (D-189 records that object as already destroyed by
  the 15:18 test writes), but the next use of the flag would have destroyed a live manifest.

### Two corrections to D-189, and one gap left open

`corpora/results/a1-6/viral-seeds.faa` no longer holds test fixtures — the caps run re-published
it at 1,249,029,570 bytes, matching the canonical copy's length, from a staged sample verified
against its digests on load. No corpus pass was run, so "do not rebuild it" held, but the upload
was not predicted from reading the tool and should have been. `run-calibration.json` now holds
this re-run's provenance rather than junk. `band.json` and `cap-measurement.json` still hold
fixtures.

Left open and recorded rather than fixed (D-192): in caps mode the heartbeat is written once
before a reading's slack cell, so during a 35-minute cell it does not move — `written_at` stood
at 18:46 while the run was alive at 19:43. `AGENTS.md` cites this tool as the worked example for
interval heartbeats, and for this mode it is not one. The per-cell artefact publishing, which is
the other half of that instruction, does work and is what made the run observable here.

**For whoever closes A1.6's review:** its caps result traces to an artefact again, under a new
key, with the published measurement's loss stated beside it.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Closed — 2026-10-20

`done`. The work is on `main` (pull request #30 merged, or earlier as the State block
records). Every Done-when criterion is met.

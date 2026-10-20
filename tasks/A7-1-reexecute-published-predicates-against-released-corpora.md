---
id: A7.1
title: Re-execute published predicates against released corpora
phase: A
status: done
gate: false
depends_on: [A0.3, A1.1, A1.2]
blocks: [X5.1]
design_ref: "§A7"
deliverable: 1
owner: claude
---

# A7.1 — Re-execute published predicates against released corpora

**Design reference:** DESIGN.md §A7 · **Deliverable 1**

## Goal

Run each developer's own published procedure against their own released corpus and diff. A
record that survives a rule its authors stated is a conformance failure — a comparison of
stated rule against delivered data, claiming nothing about homology or capability.

## Steps

- Execute each reading's predicate (A0.3) over the released dataset (A1.2).
- Identify records that survive but which the predicate says should have been removed.
- Classify each failure by cause: predicate ambiguous, required annotation absent or wrong,
  record postdates the filter, or the rule was never applied to that corpus component.
- Report count and rate per model and per reading; the spread across readings matters as much
  as any single number.
- Check the converse too — records removed that the predicate does not call for — since an
  over-broad filter is also a mismatch between rule and practice.
- Have the headline conformance numbers reproduced under A3.3 before any external circulation.

## Done when

**Criterion 1 amended 2026-10-19 by D-174.** It promised a model × reading matrix this task's
deliverable never had, and could not have: D-047 established that every rule the three readings
differ over reads an input the release withholds, so the readings are identical *by construction*
rather than by agreement, and D-049 put the converse direction and Evo 2's arm outside this task.
ESM3 has no arm at all. Criteria that no longer describe the deliverable cannot be "demonstrably
met", and the board should not later read a one-model, 3/6-coverage result against a criterion
promising a matrix. The original is struck below.

- Conformance diff computed for **every model whose release carries the inputs its own rules
  read** — Evo 1 — reproducible from pinned inputs, with **coverage stated per count** (3/6) and
  the restriction derived mechanically from the specs rather than chosen, so a rule is never
  dropped by hand.
- The readings are reported as **identical by construction, not as agreement** (D-047), naming
  the withheld input that makes them so. A §A0 finding, not a null.
- Models with no arm are named, with the reason: Evo 2 and the converse direction are A7.2's
  (D-049), and ESM3-open has neither corpus nor threshold published, so it is A1.6's.
- ~~Conformance diff computed per model × reading, reproducible from pinned inputs.~~
- Every failure is classified by cause, and causes are defined before counting.
- A clean result is written up as a positive finding, per the §2 commitment, not buried.
- Claims are qualified by A1.1's verdict: a conformance claim against a proxy corpus is not a
  conformance claim, and the write-up says so plainly where that applies.
- Headline numbers independently reproduced via A3.3.

## Strength of claim and inputs (carried from A1.1)

See `policies/corpora.md` §2 and the corrected viral-component section, with DECISIONS.md D-017,
D-019 and D-020.

- **Evo is runnable, and against Evo 1's own release.** Input is IMG/VR v4 at its pinned version
  from its own publisher; output is `stage2` of `LongSafari/open-genome`, whose records carry
  inline lineage tags in the same rank-prefix scheme as the published stop-taxa. Running the diff
  against OpenGenome2's IMG/VR component as well stays worthwhile, since the releases differ — but
  do not write "OpenGenome" as though the two releases were one artefact.
- **Three published rules cannot be checked from the release.** The high-confidence gate, the vOTU
  representative and the prokaryotic-host count depend on IMG/VR metadata that does not travel
  with the released records. That is a property of the release, not an assumption, and it belongs
  in the write-up as a limit on what conformance was tested.
- **The vOTU representative is not reproducible.** `keep_one_per` is order-dependent and no input
  order is published, so compute the diff at vOTU level or it measures our sort order.
- **ESM3 has no conformance arm.** Neither corpus nor threshold is published. The reported 10.6M
  removal count is the only published quantity a reconstruction can be checked against, and any
  threshold recovered that way ships as an estimate with an interval, never as their parameter.
- **Qualify every Evo claim by the verdicts above**, and state plainly that the audited procedure
  is Evo 1's while one of the two audited outputs is Evo 2's.

## State — 2026-10-15, pointer corrected 2026-10-17

`review`. **The work merged to `main` in PR #8 and PR #9** (branch `ccr-2e82b91e-hou4gf`, now
merged). Nothing is left on a branch: `src/amazebio/conformance.py`,
`tools/conformance_scan.py`, `tools/conformance_diff.py` and their tests are all on `main`.

This block said until 2026-10-17 that the work was unmerged and absent from a `main` checkout.
That was true when written and became false when PR #8 merged; the findings below were accurate
throughout and are unchanged.

**The result.** Of 2,653,047 records in Evo 1's own released viral component, **95 (0.004%)
survive a rule Evo 1 published**, and **not one record assigned to any of the 19 denylisted
families or 12 denylisted orders survives**. On the three rules this release can test, the filter
removed everything its own denylists name — the positive finding §A7 anticipated, and the first
external confirmation of it. The 95 failures are a single mechanism, recorded as D-051: the
published rule removes records with no assigned realm, and all 95 are assigned at family rank
and no rank above it, against a modal released record that stops at class.

**What ran.** `tools/conformance_scan.py` reads the 16.92 GB staged Parquet in about two and a
half minutes and emits lineage tags and counts only — no genomic sequence is held or
transferred — and `tools/conformance_diff.py` recomputes the headline numbers from that artefact
in a second, from a local path or straight from the store. The scan and its manifest are at
`s3://…/corpora/results/a7-1/`; `artifacts/a7-1/` holds the diff and is regenerable from the
stored scan alone.

**What this does not cover,** each with its decision entry:

- **Three of the six published rules are not checkable from the release** (D-047). The
  high-confidence gate, the vOTU representative and the prokaryotic-host count all read IMG/VR
  metadata that does not travel with the released records, so coverage is `3/6` and is reported
  next to every count.
- **The reading spread is unmeasurable here** (D-047), because every rule the three readings
  differ over reads one of those absent inputs. This also defeats the argument in
  `policies/corpora.md` §2 that the release could identify the developers' de facto reading.
- **The converse direction is not run** (D-049). Over-removal needs the filter's input, IMG/VR
  v4, which this project has not acquired — it is not in `sources.json` and nothing stages it.
- **Evo 2's release has no conformance arm at all** (D-049): its IMG/VR FASTA headers carry
  accessions and no lineage, so no published rule can be re-executed against it. Established
  from a bounded 2,000-header read rather than a full pass.

**Why this is not `done`:** the last Done-when criterion is "headline numbers independently
reproduced via A3.3", and A3.3 is a holding gate blocked on A3.2. Nothing in this task can
discharge it. Move A7.1 to `done` when A3.3 has reproduced the 95 and the zero by a second
method. Until then, per §4 and X3.1, these numbers do not circulate outside the project.

**Waiting on the project owner:** nothing. The one call this task raised — whether acquiring
IMG/VR v4 should be its own task — was made, and **A1.7** took it; A1.7 is now `done`. The gaps
it unblocked — the converse check, Evo 2's arm, and the three rules D-047 records as unrunnable —
are **A7.2**'s, not this task's, and A7.2 closed all five (see its state block). The 95 and the
zero below reproduced unchanged from the input side.


## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Closed — 2026-10-20

`done`. The work is on `main` (pull request #30 merged, or earlier as the State block
records). Every Done-when criterion is met.

The condition this task set itself is discharged: A3.3's independent recount reproduces the
95 conformance failures in all three readings. One difference travels to the write-up rather
than against the result — A7.1 reports conformance coverage as 3/6, which is right for the
literal and strict readings; the charitable reading has seven rules, so its coverage is 3/7.
A3.3's gate opened on 2026-10-20 (D-215), under the two conditions that entry records.

---
id: A7.1
title: Re-execute published predicates against released corpora
phase: A
status: review
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

- Conformance diff computed per model × reading, reproducible from pinned inputs.
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

## State — 2026-10-15

`review`, on branch `ccr-2e82b91e-hou4gf` — pushed and green, **not merged into `main`**, so the
files named here are absent from a `main` checkout.

**The result.** Of 2,653,047 records in Evo 1's own released viral component, **95 (0.004%)
survive a rule Evo 1 published**, and **not one record assigned to any of the 19 denylisted
families or 12 denylisted orders survives**. On the three rules this release can test, the filter
removed everything its own denylists name — the positive finding §A7 anticipated, and the first
external confirmation of it. The 95 failures are a single mechanism, recorded as D-046: the
published rule removes records with no assigned realm, and all 95 are assigned at family rank
and no rank above it, against a modal released record that stops at class.

**What ran.** `tools/conformance_scan.py` reads the 16.92 GB staged Parquet in about two and a
half minutes and emits lineage tags and counts only — no genomic sequence is held or
transferred — and `tools/conformance_diff.py` recomputes the headline numbers from that artefact
in a second, from a local path or straight from the store. The scan and its manifest are at
`s3://…/corpora/results/a7-1/`; `artifacts/a7-1/` holds the diff and is regenerable from the
stored scan alone.

**What this does not cover,** each with its decision entry:

- **Three of the six published rules are not checkable from the release** (D-042). The
  high-confidence gate, the vOTU representative and the prokaryotic-host count all read IMG/VR
  metadata that does not travel with the released records, so coverage is `3/6` and is reported
  next to every count.
- **The reading spread is unmeasurable here** (D-042), because every rule the three readings
  differ over reads one of those absent inputs. This also defeats the argument in
  `policies/corpora.md` §2 that the release could identify the developers' de facto reading.
- **The converse direction is not run** (D-044). Over-removal needs the filter's input, IMG/VR
  v4, which this project has not acquired — it is not in `sources.json` and nothing stages it.
- **Evo 2's release has no conformance arm at all** (D-044): its IMG/VR FASTA headers carry
  accessions and no lineage, so no published rule can be re-executed against it. Established
  from a bounded 2,000-header read rather than a full pass.

**Why this is not `done`:** the last Done-when criterion is "headline numbers independently
reproduced via A3.3", and A3.3 is a holding gate blocked on A3.2. Nothing in this task can
discharge it. Move A7.1 to `done` when A3.3 has reproduced the 95 and the zero by a second
method. Until then, per §4 and X3.1, these numbers do not circulate outside the project.

**Waiting on the project owner:** one call, in the branch's report — whether acquiring IMG/VR v4
becomes its own Phase A task now, since it is the single blocker for the converse check, for
Evo 2's arm, and for the three rules D-042 records as unrunnable.


## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A1.2
title: Reconstruct the nucleotide-model corpus
phase: A
status: review
gate: false
depends_on: [A1.1]
blocks: [A1.4, A4.3, A7.1]
design_ref: "§A1"
deliverable: null
owner: claude
---

# A1.2 — Reconstruct the nucleotide-model corpus

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage the surviving corpus for the nucleotide-level model under audit.

## Steps

- Acquire the documented dataset at the stated version; pin checksums.
- Record size, composition and provenance of each component.
- Stage it in a form the A2 detectors can stream over without re-download.
- State explicitly where a proxy stands in for unavailable material.

## Done when

- Corpus is staged, checksummed and version-pinned.
- Composition table is written up with provenance per component.
- Every proxy substitution is documented as a limitation.

## Strength of claim (carried from A1.1)

A1.1's verdicts set how this task's results may be worded; see `policies/corpora.md` and
DECISIONS.md D-017, D-019, D-020.

- **Evo 2 — verified as published.** The paper and the dataset card both state the released
  OpenGenome2 is the training corpus. No independent evidence establishes byte-level
  correspondence, and none exists for any model here, so write "as published" rather than
  "verified" unqualified.
- **Evo 1 — released, and the viral component is in `stage2`**, labelled per record with inline
  taxonomic lineage. Stage 1 carries GTDB and IMG/PR accessions. Three rules cannot be checked
  from the release because their metadata does not travel with the records: the high-confidence
  gate, the vOTU representative, and the prokaryotic-host count.
- **Evo 1's version of record (S-EVO1-SCIENCE) is unretrieved.** If it names a deposit the
  preprint does not, revisit the Evo 1 entry before publication.

## In review

- **Branch:** `claude/jolly-hawking-wtgnid` (pushed).
- **Done — all three Done-when criteria met:**
  - **Staged, checksummed, version-pinned.** 12 objects, 134.2 GiB, under
    `s3://amazebio-corpora-897641797669/corpora/{opengenome,opengenome2}/<revision>/`.
    Every object is verified against the SHA-256 its release publishes per file: four by
    reading the object back out of the bucket, eight by hashing in flight (D-041 — the
    readback for those rides along with A7.1's in-region pass). Both pins reconcile exactly:
    22 files / 146,886,935,899 bytes and 1,126 files / 5,523,240,795,932 bytes.
  - **Composition with provenance per component.** `artifacts/a1-2/composition.json`, one row
    per component *and* representation, each carrying its role in the audit; written up in
    `policies/evo.md` §7.
  - **Proxy substitutions documented.** There are none — these are the only two corpora in the
    audit needing no acquisition qualifier. Stated explicitly in `policies/evo.md` §7, with
    A1.1's byte-level-identity limit carried forward.
- **Decisions:** D-031 (staging scope and representation), D-041 (verification method per object,
  appended as D-032 and renumbered).
- **Two findings for the Phase A write-up**, both in `policies/evo.md` §7-8:
  - The published procedure's subject is **0.2%** of Evo 2's corpus — 10.4 GiB of IMG/VR
    against 5.02 TiB — while **82%** is eukaryotic genomes added after the filter was designed.
    That is §5's scope gap, measured, and A4.3 inherits it.
  - Evo 1's inline lineage tags appear not to have survived into Evo 2's release, on a
    four-file sample. Not a census; A7.1 settles it when it reads the component in full.
- **For a reviewer:** the claim to check hardest is that the pinned revisions carry
  publication-time sequence content. It rests on the commit histories, and it supports
  "unchanged since February 2025" but not "nothing was removed" — a deletion would leave no
  trace in a listing of what is present. Said so in the write-up rather than left implicit.
- **Waiting on the project owner:** nothing.
- **For A2.3 and A4.1:** your components are deliberately unstaged — 2.17 TB of eukaryotic
  genomes and 252 GB of metagenomes. D-031 has the figures and the tier flag is in the code,
  so it is one resumable pass each, but it is permanent storage: re-ask the cost question.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

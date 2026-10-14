---
id: A1.2
title: Reconstruct the nucleotide-model corpus
phase: A
status: in-progress
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

## In flight

- **Branch:** `claude/jolly-hawking-wtgnid`
- **Done:** nothing yet; claimed 2026-10-14.
- **Left:** everything in Steps.
- **Waiting on the project owner:** nothing yet. A staging-scope question is likely, because the
  Evo 2 corpus is far larger than the UniRef release A1.3 staged; it will be asked with real
  byte counts rather than estimates.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

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
- **Done:**
  - Both releases pinned to commit SHAs with a published SHA-256 per file
    (`src/amazebio/opengenome.py`, `tools/stage_opengenome.py`, tests). Fetched manifests
    reconcile exactly to both pins: 22 files / 146,886,935,899 bytes for Evo 1, and
    1,126 files / 5,523,240,795,932 bytes for Evo 2.
  - Composition table computed per component and per representation, with each component's
    role in the audit recorded in code rather than left to the next pipeline.
  - Write-up in `policies/evo.md` §7-8; five sources registered with captures.
  - Staging scope settled with the project owner and logged as D-031.
- **Left:**
  - The staging pass itself is running (12 files, 134.2 GiB, ~22 MB/s). When it finishes,
    `artifacts/a1-2/run.json` records each object with the checksum it was verified against;
    that is what closes Done-when's first criterion.
  - Then status to `review`.
- **Waiting on the project owner:** nothing.
- **For whoever picks up A2.3 or A4.1:** your component is deliberately not staged. D-031 has
  the figures; the tier flag is already in the code, so it is one resumable pass, but it is
  2.17 TB (eukaryotic) or 252 GB (metagenomic) of permanent storage and the cost question
  should be re-asked rather than assumed.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

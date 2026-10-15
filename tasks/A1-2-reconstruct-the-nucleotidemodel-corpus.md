---
id: A1.2
title: Reconstruct the nucleotide-model corpus
phase: A
status: done
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

## Outcome

Merged as PR #7 (`claude/jolly-hawking-wtgnid`), CI green on the merge commit.

**All three Done-when criteria met.**

- **Staged, checksummed, version-pinned.** 12 objects, 134.2 GiB, under
  `s3://amazebio-corpora-897641797669/corpora/{opengenome,opengenome2}/<revision>/`. Every
  object verified against the SHA-256 its release publishes per file — four by reading the
  object back out of the bucket, eight by hashing in flight. Both pins reconcile exactly:
  22 files / 146,886,935,899 bytes, and 1,126 files / 5,523,240,795,932 bytes.
- **Composition with provenance per component.** `artifacts/a1-2/composition.json`, one row per
  component *and* representation, each carrying its role in the audit. Written up in
  `policies/evo.md` §7.
- **Proxy substitutions documented.** There are none. These are the only two corpora in the
  audit needing no acquisition qualifier; stated explicitly in `policies/evo.md` §7, with
  A1.1's byte-level-identity limit carried forward.

**Decisions:** D-031 (staging scope and representation), D-041 (verification method per object;
appended as D-032 and renumbered — see its `Numbering:` line).

**Two findings for the Phase A write-up**, both in `policies/evo.md` §7-8:

- The published procedure's subject is **0.2%** of Evo 2's corpus — 10.4 GiB of IMG/VR against
  5.02 TiB — while **82%** is eukaryotic reference genomes added after the filter was designed,
  with no viral screening step in their published curation. That is §A1's scope gap, measured.
  A4.3 inherits it.
- Evo 1's inline lineage tags appear not to have survived into Evo 2's release, on a four-file
  sample against 1,123. Not a census — written as "no tag found where v1 had one in every
  sampled record". A7.1 settles it when it reads the component in full.

**The limit on the strongest claim, carried forward.** That the pinned revisions hold
publication-time sequence content rests on the commit histories. It supports "unchanged since
February 2025" and **not** "nothing was removed": a deletion leaves no trace in a listing of
what is present.

**A7.1 inherits one obligation (D-041).** Run the readback over the eight large objects as part
of its in-region pass and merge the result into `artifacts/a1-2/staged_*.json`, upgrading those
rows from `stream` to `readback`. It costs nothing there. If A7.1 is re-scoped away from reading
those objects the obligation moves to whichever in-region task reads them first; it should not
become a reason to launch an instance on its own.

**For A2.3 and A4.1.** Your components are deliberately unstaged — 2.17 TB of eukaryotic genomes
(~$50/month) and 252 GB of metagenomes (~$6/month). D-031 has the figures and the tier flag is
in the code, so each is one resumable pass, but it is permanent storage: re-ask the cost
question rather than assume it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

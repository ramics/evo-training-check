---
id: A7.4
title: Verify Evo 2's reuse of OpenGenome v1
phase: A
status: ready
gate: false
depends_on: [A1.2, A1.4]
blocks: []
design_ref: "§A7, §A1"
deliverable: 1
owner: unassigned
---

# A7.4 — Verify Evo 2's reuse of OpenGenome v1

**Design reference:** DESIGN.md §A7, §A1 · **Deliverable 1**

## Goal

Evo 2 states that the OpenGenome dataset "was used in its entirety as part of the training data
for this study", comprising representative prokaryotic genomes from GTDB v214.1, and that new
genomes from GTDB release 220.0 were then added — "all species' reference genomes that had no
previously published (release 214.1) genomes within their species cluster, resulting in 28,174
additional genomes" (D-130).

That is a checkable claim about delivered data, and **both sides of it are now staged**:
OpenGenome v1's `stage1_gtdb` (Parquet, 118.5 GiB, staged under D-119) and OpenGenome2's
`fasta/gtdb_v220/v214/batch{1,2,3}.tar` plus `fasta/gtdb_v220/v220_update.tar`. Measure whether
the reused subtree is the sequence set it says it is.

This is the §A7 question one level down from A7.1: not "did the filter do what its authors said"
but "does the corpus contain what its authors said". It needs no hazard list and no homology, and
a clean result is as valuable as a dirty one (§2).

## Why it is its own task

It arrived as a by-product of A2.4's staging and `AGENTS.md` forbids widening a task to absorb an
adjacent problem. It is also not A2.4-shaped: A2.4 detects prophage, this compares two staged
representations of a sequence set, and the two share no machinery beyond the object store.

## Steps

- Fix the comparison key before reading either side. The two representations differ — Parquet
  with an INSDC contig accession per row against a tar of FASTA — so the key is a decision, and
  sequence digest, accession, or both-with-disagreement-reported are the candidates. Record it.
- Establish what a record is on each side, and whether the two agree on it. OpenGenome v1's rows
  are contigs; whether OpenGenome2's tar is organised by contig or by genome is to be read from
  the staged tree, not assumed.
- Compare the reused side against OpenGenome v1: present on both, present only in v1, present
  only in the v214 subtree. Report counts and rates, per split where v1's splits survive.
- Check the 28,174 figure against `v220_update.tar` independently of the first comparison.
- Classify every discrepancy by cause, as §A7 requires: representation (a sequence recorded
  differently rather than absent), deduplication, a record postdating one release, or an actual
  difference in content.

## Done when

- The comparison key and record definition are fixed and recorded before any count exists.
- Counts and rates exist for both directions, with intervals.
- The 28,174 figure is reconciled or the gap is quantified.
- Every discrepancy class has a count; none is left in a residual bucket.
- A `run.json` pins inputs, outputs, parameters and the commit.

## Notes

Read with D-130, which establishes both releases' GTDB versions and warns that OpenGenome2's
`gtdb_v220/` directory name is **not** the version of everything beneath it.

The Evo 2 statements this task tests come from the **preprint**. `S-EVO2-NATURE` is
`retrieved_not_stored` so nothing may be quoted from it, and `S-EVO2-NATURE-METHODS` is
`unretrieved` — the Methods are absent from both the article HTML and the PDF. Before this task
reports a conformance *failure* against a named laboratory, the version of record's wording has
to be in hand: §7 requires that claim to be airtight, and D-110 is the precedent for checking
rather than assuming the preprint and the published version agree. Settle that with the project
owner first; it is a retrieval a person can do and this environment cannot.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

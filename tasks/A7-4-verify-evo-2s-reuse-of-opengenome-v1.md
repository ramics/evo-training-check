---
id: A7.4
title: Verify Evo 2's reuse of OpenGenome v1
phase: A
status: in-progress
gate: false
depends_on: [A1.2, A1.4]
blocks: []
design_ref: "§A7, §A1"
deliverable: 1
owner: claude
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

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** The comparison key and the record
definition are fixed (D-213): contig accession primary, sequence digest on the set the
accessions disagree about, assembly accession for the 28,174 claim.

Built and tested: `amazebio.tarindex` and `tools/opengenome_reuse.py` for the genome half,
which walks each archive's header chain for about 14 MB of transfer instead of 25.6 GB;
`amazebio.contigs` for what an accession and a digest are, shared by both sides so a
difference is in the data rather than in the readers; `tools/opengenome_v1_contigs.py`,
which reads v1's accessions out of a 118.5 GiB tier for about 104 MB; `amazebio.reuse` and
`tools/opengenome_compare.py` for the join and the closed set of causes; and
`tools/opengenome_contigs.py` with `tools/ec2_opengenome_contigs.py` for the OpenGenome2
contig pass.

Measured: OpenGenome v1's GTDB tier holds **11,986,857 contigs, every accession distinct**
— 11,986,802 train, 50 test, 5 valid, no accession repeated across the fourteen shards. So
on the v1 side a contig accession is a key rather than a label, which is what D-213's
primary key needs it to be.

Running: the genome walk, in this container.

**Waiting on the project owner.** The OpenGenome2 contig pass reads 109 GB and has to run
in `us-east-1`; the launch needs the owner's go-ahead and was asked for on 2026-10-20. Until
it runs, the contig half of D-213's key has no data and the discrepancy classification
cannot be completed.

## Notes

Read with D-130, which establishes both releases' GTDB versions and warns that OpenGenome2's
`gtdb_v220/` directory name is **not** the version of everything beneath it.

The Evo 2 statements this task tests are in the **version of record** and are quotable (D-135).
The Methods are not in the article HTML or main PDF — they are the Supplementary Information,
stored at `pdfs/s41586-026-10176-5_sm.pdf` and registered under `S-EVO2-NATURE-METHODS` with its
CC BY-NC-ND 4.0 licence note. §A.2.1 "Data curation" carries the "used in its entirety" claim, the
GTDB v214.1 reuse and the 220.0 selection rule with its 28,174 figure, word for word as the
preprint had them. So this task may assert against the version of record, which §7 requires of a
claim naming a laboratory. `S-EVO2-NATURE` itself stays `retrieved_not_stored` and unquotable —
cite the Methods id, not the article id.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

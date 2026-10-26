---
id: A7.4
title: Verify Evo 2's reuse of OpenGenome v1
phase: A
status: done
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

## Closed — 2026-10-22

`done`. Merged to `main` in PR #31. All five Done-when criteria are met and were checked
against the artefacts in `corpora/results/a7-4/` (22 stable objects, commit-keyed twins
present): the key and record definition were fixed before any count existed, both directions
carry counts and intervals, the 28,174 figure reconciles with a difference of zero, all 48
discrepancies carry a cause with none residual, and `comparison.json` ships beside its run
manifest.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project owner.

Both halves of Evo 2's claim hold, and the result is clean rather than mixed.

**"Used in its entirety" is exact.** Every one of OpenGenome v1's 11,986,857 GTDB contigs is
present in OpenGenome2's reused subtree — 0 only in v1, coverage 1.000000 [0.999999680,
1.000000]. The in-region pass read all four archives in 25 minutes on one instance, 85,205
genomes and 11,986,902 contigs on the reused side, 28,174 genomes and 5,421,257 contigs on the
added side, with no unplaceable member in any archive.

**The 28,174 figure reconciles exactly**, with a difference of zero. It is a count of genomes,
and the added archive holds exactly that many distinct assembly accessions.

**Every discrepancy carries a cause and none is residual**: 48 `content`, 0 of the other three,
0 `undetermined`. Two findings sit inside that 48, and neither contradicts the reuse claim:

- 45 contigs the reused subtree has and v1 does not, all of one assembly, `GCA_023250385.1`.
  v1 carries 158 contigs of its WGS project and OpenGenome2 carries 203; the 45 are short
  (3.0–31.8 kb) and their residues are in none of v1's 158. So v1 held a truncated copy of
  that genome. That is extra material in the reuse, not missing material, and it is why the
  converse rate is reported separately: novelty 3.75e-06 [2.81e-06, 5.02e-06].
- 3 contigs on the *added* side that v1 already carried — `NZ_CP091285.1`, `NZ_CP091287.1`,
  `NZ_CP092365.1`. The stated selection rule takes species with no 214.1 genome, so it
  predicts this rate to be zero; measured 5.53e-07 [1.88e-07, 1.63e-06].

D-217 records how far a disputed contig's residues were looked for, and the artefact carries
that scope beside the counts: a `content` call here means "not in the 158 v1 contigs of the
same WGS project", not "not in v1".

Artefacts: `comparison.json` and `discrepancies.jsonl.gz` under
`corpora/results/a7-4/`, with the four per-archive contig tables and `run-compare.json`.

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

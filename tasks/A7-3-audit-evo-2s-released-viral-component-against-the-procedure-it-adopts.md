---
id: A7.3
title: Audit Evo 2's released viral component against the procedure it adopts
phase: A
status: review
gate: false
depends_on: [A7.2]
blocks: []
design_ref: "§A7"
deliverable: 1
owner: claude
---

# A7.3 — Audit Evo 2's released viral component against the procedure it adopts

**Design reference:** DESIGN.md §A7 · **Deliverable 1**

## Goal

Turn A7.2's Evo 2 arm into a result in its own right: a conformance audit of **Evo 2's** released
IMG/VR component against the procedure **Evo 1** published and Evo 2 adopts by reference.

A7.2 measured it as one of five gaps and found the larger of the two conformance failures in the
project. It needs a write-up, an independent reimplementation, and wording that survives a
motivated reader — none of which belongs inside a task whose subject was Evo 1.

## Why this is a separate task

A7.2's subject is Evo 1: its headline is that Evo 1's filter conforms to Evo 1's published
procedure to 95 records in 2.65 million. The Evo 2 number is four orders of magnitude larger and
is a claim about a different artefact, a different release and a different paper's adoption of
someone else's method. Reporting it as a sub-section of an Evo 1 result would bury the larger
finding under the smaller one, and would attach Evo 2's standing to Evo 1's reimplementation
rather than to its own.

It is also the first finding in this project where the audited developer did not publish the
procedure being audited. That raises wording questions A7.2 has no need to answer and §7's
adversarial reader will press on hard.

## What A7.2 already established

Measured over IMG/VR v4.1, the release the evidence identifies as Evo 1's input (D-071):

- Evo 2's released IMG/VR component carries **2,957,495 sequence records under 2,917,521 distinct
  accessions** — exactly the number of distinct high-confidence vOTUs in IMG/VR v4 — and every one
  of them joins to the staged input.
- **264,570 of those records are ones the published procedure removes**: 217,078 by the
  prokaryotic-host rule, 23,523 by the unspecificity rule, 21,867 from denylisted orders, and
  **2,102 from the 19 denylisted families**.
- The **converse direction is empty** at vOTU level, and the **vOTU rule conforms exactly**: every
  one of 2,651,376 predicted-surviving vOTUs contributed exactly one released record.
- **39,974 accessions appear more than once** in the released FASTA, which the header cannot
  explain.

Taken together: the release's size, its vOTU structure and its accession set match the output of
the procedure's first two steps — the confidence gate and the vOTU deduplication — and not the
output of all six.

## Steps

- Decide and record what may and may not be claimed from the arithmetic. A7.2 claims only the
  counts and explicitly claims no intent; this task has to say in print what the counts support.
  The weakest defensible wording is a conformance mismatch between a stated procedure and a
  released artefact. "Evo 2 did not apply the filter" is a stronger claim and needs either more
  evidence or no publication.
- Rule out the alternatives before writing, each as its own check rather than as a sentence. Three
  are live and all three are cheap: that the records were removed later in Evo 2's pipeline and
  the FASTA tree is a pre-filter staging artefact (`policies/evo.md` §7 already warns the FASTA and
  JSON trees are not a strict mirror — compare the JSON tree's viral component against the FASTA
  one); that Evo 2's component was built from a different IMG/VR release (A7.2's join found zero
  released accessions absent from v4, which bears on this); and that "as previously described"
  scopes the exclusion to the inherited OpenGenome v1 records rather than to Evo 2's own
  re-retrieval.
- Characterise the 2,102 denylisted-family records by family, since §4's reporting limits govern
  how that may be published: by homology class, fold family and survival route, never as a ranking
  of which model is most capable for which pathogen. The families are published names on a
  published list and the counts are of records in a released corpus; neither is a capability claim,
  and the write-up should say so rather than leaving a reader to wonder why the table stops where
  it does.
- Resolve the 39,974 repeated accessions. Whether they are duplicated entries or several pieces of
  one record is not visible in the header; sequence length per record against IMG/VR's own `Length`
  column settles it, and A7.2 deliberately did not read a base.
- Reconcile against Evo 2's own published figures for the component, as A7.1 did against Table S3.
  A7.2 compared only against Evo 1's.
- Run the independent reimplementation under A3.3 before any external circulation, and treat this
  task's headline as uncleared until it passes.

## Done when

- The claim is written at the strength the evidence carries, with each rejected alternative
  recorded as a check that was run rather than a possibility that was mentioned.
- The 264,570 figure is reproduced by a second method under A3.3.
- The repeated accessions are explained.
- Counts are reconciled against Evo 2's own published figures for the component, with any gap
  reported.
- The by-family breakdown is published within §4's reporting limits, with the limits stated.
- Every claim names the IMG/VR release it rests on, and the procedure/output provenance split is
  stated plainly: the procedure is Evo 1's, the output is Evo 2's (D-019).

## What this task is not

- **Not a re-run of A7.2.** The arithmetic is done and the artefacts are pinned. This task
  interprets it, checks the alternatives, and writes it up.
- **Not a judgement about intent.** The counts support a mismatch between a stated procedure and a
  released artefact. Nothing in the data speaks to what anyone meant to do.
- **Not an ESM3 arm.** There is none; see A7.2 and A1.6.

## State — 2026-10-20

Branch: `claude/project-thread-a3vch4`. Nothing is waiting on the project owner, but there is
one question for review, below.

**The headline changed, and it got stronger.** The alternative this task was told to rule out —
that the FASTA tree is a pre-filter staging artefact — came back confirmed. OpenGenome2's JSON
training format is Evo 1's released viral component to the record and to the nucleotide, zero on
both deltas. The FASTA representation holds 304,448 records and 2.64 billion nucleotides more,
among them the 264,570 the published procedure removes. So the filter's output was carried
forward unchanged into what was trained on, and the only representation carrying a source
accession — the only one the filter can be checked against at all — is a superset of it. The
earlier reading, that 264,570 records escaped the filter into the training data, is withdrawn in
the write-up.

Done:

- `docs/evo2-two-representations.md` — the write-up, with each alternative recorded as a check
  that was run and each claim graded by what the evidence carries.
- `policies/evo.md` §10 — the measurement, and the version of record's data-curation paragraph,
  which scopes the inheritance in a way the preprint does not. Two corrections there as well:
  §8 said the two trees hold the same sequences, and §6's caveat 5 said the version of record
  was unretrieved when it had been retrieved on 2026-10-17.
- The denylist rules broken down at the taxon each names, with the order-dependence published
  as a number: 2,102 family records under the published chain against 4,706 counting denylist
  membership alone.
- A second method for the headline count — newline counting and byte arithmetic, no decode and
  no parse — with its own premise check.
- The reconciliation against Evo 2's published figures: not possible, and that is the finding.
  The only published figure for the component is a training-mix percentage.

- The repeated accessions, resolved (D-225). They are not repeated accessions: the release
  carries 1,775 accessions on 41,749 headers, and 41,749 - 1,775 = 39,974, which is the figure
  A7.1 and A7.2 each reported as a population. Every one of the 1,775 is a giant-virus MAG
  whose occurrences sum exactly to IMG/VR's own length for it, so the surplus records and
  surplus nucleotides are both zero and the undeclared-upsampling concern does not arise.

- The headline recounted by a second method (`json-tree-second.json`): newline counting and
  byte arithmetic over the gzip stream as bytes, never decoding and never parsing, with a
  premise check guarding the subtraction. Zero record delta and zero sequence-character delta
  across all six files, no premise failure.

Nothing is left. The task is `review`.

**For review.** This task's Done-when says the 264,570 figure is reproduced by a second method
*under A3.3*. A3.3 is `done` and its gate is open (D-215), and its conformance arm reimplemented
Evo 1's 95 and not Evo 2's 264,570 — so that criterion is not met as written, and the figure is
no longer this task's headline either. A7.3 supplies a second method for the headline it does
have. Whether that satisfies §7 for this result, or whether A3.3's scope should be extended to
Evo 2's arm before the Phase A write-up cites it, is the project owner's call.

## Notes

Opened by A7.2 on 2026-10-15, on the project owner's decision that the Evo 2 result should stand
as its own Phase A finding rather than as a section of A6.1. `depends_on` names A7.2 because this
task consumes its artefacts; it becomes `ready` when A7.2 reaches `done`, which waits on the A3.3
gate.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

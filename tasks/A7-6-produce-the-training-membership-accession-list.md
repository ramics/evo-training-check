---
id: A7.6
title: Produce the training-membership accession list
phase: A
status: in-progress
gate: false
depends_on: [A7.3]
blocks: []
design_ref: "§A7"
deliverable: null
owner: claude
---

# A7.6 — Produce the training-membership accession list

**Design reference:** DESIGN.md §A7

## Goal

Produce, as a citable artefact through `amazebio.repro.run`, the list of IMG/VR accessions that
are present in **OpenGenome2's training representation** — not merely in its released FASTA.

## Why it is its own task

D-262 proved the join works and then lost its output. The two representations of Evo 2's viral
component can be linked completely: all 2,652,840 distinct JSON records resolve to the released
FASTA by exact sequence digest, one needing a `(length, first-48, last-48)` fallback, none
unresolved. But the accession list that join produced was a scratch file — sha256
`413b92e13df518b9cefa3bdeba99449a8298e41a40c98dd9aa39b735f16b0568`, 2,653,047 lines — and it died
with its container. D-262's own closing line says a task of its own should produce it properly,
and this is that task.

It is not folded into A2.6. D-269 settled that: the census runs carrying its scope limit rather
than waiting on this, so this is a separate instrument that upgrades A2.6's output afterwards.

## What it unlocks, and why it is worth more than its cost

Every figure measured on Evo 2's viral component is currently measured on the **released** FASTA,
which is a superset of the training set by **304,448 records** — about a tenth. A2.6's census
searched 2,957,495 records and found 1,636 of 1,719 viral Pfam families; that count therefore
describes a population including records the model never trained on.

**The census does not need re-running.** Its detection rows carry `record_id`, so restricting the
tables to training members is a re-tabulation over an existing artefact once this list exists.
Nineteen hours of search are already paid for and stay paid for.

The same restriction applies to A4.1, A7.3 and every Evo 2 figure D-262 names.

## Scope, measured before anything was launched

| side | artefact | size | what it carries |
|---|---|---|---|
| accessions | `fasta/plasmids_phage/imgvr.fasta.gz`, staged in-region | 11.22 GB gz | accession + sequence, 2,957,495 records |
| training | `json/pretraining_or_both_phases/imgvr_untagged/`, 6 files on HuggingFace | 10.44 GB gz | sequence only (`text`), ~2,652,840 records |

- **In-region is the right place** by `AGENTS.md`'s own test: a full pass is ~21.7 GB compressed,
  which is free inside `us-east-1` and metered outside it.
- **A small instance is the honest size.** One gzip member is one thread, so the accession side is
  a single thread and the training side is four. Useful parallelism caps near five; a `2xlarge`
  buys nothing.
- **Memory is not a constraint.** 2.96M packed accessions plus 2.65M digests is a few hundred MB,
  not the gigabytes the census needed.
- Estimated about **$1 and an hour**.

## Steps

- Fix the join's parameters before any count exists: digest algorithm, both orientations, and the
  `(length, first-48, last-48)` fallback tier D-262 used. Record them, then look.
- Stream both sides; never materialise either. Pack accessions with `amazebio.imgvr.uvig_key` as
  `tools/evo2_accessions.py` does, and ship a sorted array plus a small JSON report, so the join
  downstream is a `searchsorted` rather than a hash of millions of strings.
- Reconcile against D-262's figures — 2,652,840 resolved, 1 by fallback, 0 unresolved, 2,653,047
  distinct accessions, 304,448 FASTA entries absent. A disagreement is a finding, not a tuning
  parameter.
- Publish through `repro.run(durable=...)` so the artefact is traceable to its commit.

## Done when

- The accession list exists as a durable, commit-traceable artefact with a `run.json`.
- Its counts reconcile with D-262's, or the disagreement is measured and recorded.
- The parameters were fixed and recorded before the counts were inspected.
- New code has tests and CI is green.

## State — 2026-10-28

Branch: `claude/jolly-allen-oahiqb`.

Opened because A2.6's census landed (D-272) and the project owner asked directly whether its
1,636-of-1,719 figure describes what Evo 2 was trained on. It does not yet, for two separate
reasons, and this task removes one of them:

- **Training membership** — this task. The census covers a superset by about a tenth.
- **Filter status** — *not* this task and not fixable by it. Every one of the 2,957,495 records
  carries route `unresolved`, because the released FASTA has an accession and no lineage, so none
  of the six published rules can be executed against it (D-049). 6,734,534 of the census's
  6,857,916 hits sit in that state. That unauditability is a Phase A finding in its own right and
  the write-up must not let the two limitations blur into one.

Waiting on the project owner: nothing.

## Notes

Read with D-262, which proved the join and lost its output; A7.3, which established that the
training tree is Evo 1's released component to the record and the nucleotide while the FASTA is a
superset; and D-272 for what the census actually measured.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

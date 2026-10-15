---
id: A1.6
title: Evaluate the ESM3 similarity readings against the proxy corpus
phase: A
status: blocked
gate: false
depends_on: [A1.4, A1.5]
blocks: []
design_ref: "§A0, §A1"
deliverable: 1
owner: unassigned
---

# A1.6 — Evaluate the ESM3 similarity readings against the proxy corpus

**Design reference:** DESIGN.md §A0, §A1 · **Deliverable 1**

## Goal

Produce surviving-record manifests for ESM3-open's charitable and strict readings, which need an
alignment pass that A1.4 deliberately did not buy.

Split out of A1.4 (DECISIONS.md D-043). A1.4 covers every reading whose inputs the staged
releases already carry; these two are the ones that do not, and the difference is acquisition and
spend rather than more of the same work.

## Why this is not A1.4

ESM3-open's filter is similarity-based, so re-executing it needs three things A1.4 has none of:

- **The seed sets.** The viral denylist is "sequences that are annotated as viral in UniProt and
  align almost exclusively to other viral sequences in UniProt", roughly 4M sequences, and the
  select-agent denylist is "all sequences in UniProt belonging to organisms on the Select Agents
  and Toxins List". Neither is published as a set; both have to be rebuilt from UniProt
  annotation. "Almost exclusively" is unquantified in the source and stays that way — see the
  charitable spec's own note — so the reconstruction is itself a reading, and its construction
  needs recording as one.
- **An alignment pass.** ~295 GB of staged proxy corpus against the seed sets. That is in-region
  work by the test in `AGENTS.md`, and the only Phase A task so far whose compute is the cost
  rather than the data movement.
- **A decision about the strict reading's cost.** Strict removes on any detected hit
  (`identity_threshold: 0.0`), so it cannot be derived from a 0.70 run by filtering: it needs the
  full hit list at the aligner's own sensitivity floor, which is the expensive end of the sweep.

The literal reading is not here. It evaluates to `undetermined` for every in-scope record because
the threshold is unpublished, which needs no compute, so A1.4 ships it.

## Steps

- Rebuild both seed sets from UniProt annotation at a pinned release, recording the construction
  of "almost exclusively" as a reading with its alternatives, not as a fact.
- Pin the aligner, its version and every parameter before any output exists.
- Run the charitable reading (0.70) and the strict reading (any hit) over the staged proxy
  corpus, in region, writing manifests in A1.4's format so A2.* and B3.* consume one shape.
- Reconcile against the 10.6M sequences the paper reports its two denylists removed, and report
  the spread between the three readings as §A0 requires.

## Done when

- Both manifests exist in A1.4's format, reproducible from pinned inputs and seeds.
- Seed-set construction is pinned, checksummed and recorded as a reading.
- The comparison against the paper's reported 10.6M is written up, with the proxy qualifier
  A1.1 requires on every ESM3 result.
- A `run.json` manifest pins inputs, outputs, parameters, aligner version and seed.

## Before starting, re-ask the cost question

A1.5 and A1.2 both left this warning and it applies here with more force, because this is compute
rather than storage. Price the alignment pass and put the figure to the project owner before
launching anything. `AGENTS.md`'s EC2 section is the operating manual — one shot at `UserData`, no
shell, self-terminating, provenance carried in — and `tools/ec2_count.py` is the worked example.

Two things that are not fixable by spending more, carried from A1.5: JGI is about a third of
ESM3's unique training tokens and cannot be reconstructed at all, and the structure-side
components were not bought. So no figure of the form "x% of ESM3's corpus" is supportable from
this task either, however thorough the alignment pass is.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

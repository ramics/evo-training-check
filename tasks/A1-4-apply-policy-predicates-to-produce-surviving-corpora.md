---
id: A1.4
title: Apply policy predicates to produce surviving corpora
phase: A
status: in-progress
gate: false
depends_on: [A0.3, A1.2, A1.3, A1.5]
blocks: [A1.6, A2.1, A2.2, A2.3, A2.4, A2.5, A4.1, A4.2, A5.1, B3.1, B3.2, B3.3]
design_ref: "§A1, §A2"
deliverable: 1
owner: claude
---

# A1.4 — Apply policy predicates to produce surviving corpora

**Design reference:** DESIGN.md §A1, §A2 · **Deliverable 1**

## Goal

Run each of the three readings against each staged corpus to produce the concrete surviving-
record sets that Phase A measures and Phase B scores against.

## Steps

- Implement predicate evaluation over corpus records at scale.
- Produce, per model × reading, a surviving-record manifest with stable IDs.
- Verify counts are internally consistent and reproducible from pinned inputs.
- Expose the manifests as the single shared input for A2.* and B3.*.
- Wrap the run in `amazebio.repro.run`, declaring every parameter before results
  exist, so this pipeline is the first to enforce the X1.1 seed and provenance
  convention end to end (see DECISIONS.md D-003).

## Done when

- Nine-ish (model × reading) manifests exist, reproducible from pinned inputs and seeds.
- Manifest format is documented and consumed by at least one A2 task.
- Record counts reconcile against A1.2/A1.3 composition tables.
- A `run.json` manifest is produced, pinning inputs, outputs, parameters and seed.

## State — 2026-10-15 — in progress

**Branch:** `ccr-6ecfc2c1-668gtb`. Project management is on `main` as usual; the evaluator,
readers, tool and tests are on the branch.

**Scope settled before any code (D-043).** The ESM3 similarity readings are split out as A1.6.
A1.4 produces the Evo readings — which are runnable against the staged release today — and
ESM3-open's literal reading, whose result is `undetermined` for every in-scope record and needs
no compute to establish. So this task ships seven of the nine-ish manifests, and the two it does
not are blocked on acquisition rather than on effort.

**Finished:** nothing yet.

**Left:** the corpus-scale evaluator, record readers for the two staged Evo representations, the
manifest format, the run, and reconciliation against A1.2's composition table.

**Waiting on the project owner:** nothing. The one decision this task needed is D-043.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

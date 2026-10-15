---
id: B1.1
title: Verify model inventory and exclusion status
phase: B
status: done
gate: false
depends_on: [A0.1]
blocks: [B1.2]
design_ref: "§B1"
deliverable: null
owner: claude
---

# B1.1 — Verify model inventory and exclusion status

**Design reference:** DESIGN.md §B1

## Goal

Fix the model list for Phase B and confirm each one's exclusion status from primary sources,
including the positive controls.

## Steps

- Confirm from primary sources which checkpoints are exclusion-condition and which are
  controls. The v0.3 model list (ESM3-open as protein-level test condition, ESM-C as a
  second viruses-included comparison) comes from A0.1; re-verify it rather than
  inheriting it.
- Record checkpoint identifiers, versions, licences and access routes.
- Decide and record which Tier 2 models are in scope given available compute.
- Flag any model whose training composition is too under-documented to classify.

## Done when

- Model table is complete with verified status, versions and licences.
- Tier 2 scope decision recorded in DECISIONS.md.
- Under-documented cases flagged as findings per §7.

## State — 2026-10-14 — DONE

Merged in ramics/amazebio#4. CI green; `python3 tools/model_inventory.py --check` runs in CI.

**The model list.** Five Tier 1 checkpoints, each with its identifier, parameter count where one
is stated, corpus pin, licence, access route and exclusion status verified from first-party
sources: `esm2_t33_650M_UR50D`, `esm2_t36_3B_UR50D` (positive controls), `esm3-sm-open-v1`
(protein-level test condition), `ESMC-600M` (second positive control), `evo2_7b` (nucleotide-level
test condition). The inventory is `src/amazebio/models.py`, the evidence is `policies/models.md`
with 17 machine-verified quotations, and the artefact is
`artifacts/b1-1/inventory/inventory.json`.

**Three divergences from the model list in `DESIGN.md` §B1**, which is why §B1 step 0 requires
re-deriving it rather than inheriting it:

1. §B1 gives no checkpoint identifiers. Resolved as above.
2. "ESM-C (open release)" names no single checkpoint — 300M, 600M and 6B are all openly
   downloadable. 600M chosen; D-035.
3. §B1's Tier 2 list cannot be verified as written: nothing about Nucleotide Transformer or
   ProGen2 has been retrieved, so neither can be an inventory row. Acquiring them is a separate
   task if anyone wants them.

**Under-documented cases flagged per §7.** Two of six checkpoints carry a §A0 finding, reported
on every run of the inventory tool. The one that matters: `esm3-sm-open-v1`'s parameter count is
stated by no retrieved first-party source — the ESM3 family table lists the three flagship sizes
and omits the open checkpoint entirely. The familiar 1.4B is the ESM-C authors describing another
lab's model, which §B1 step 0 rules out. D-036.

**Tier 2 scope decision: out, by measurement.** `tools/ec2_capability.py` measures the account's
launch allowlist by dry run. The first probe found no accelerated instance type permitted at all;
the project owner then allowed `g5.xlarge` and `g6.xlarge`. So all five Tier 1 checkpoints are
runnable and Evo 2 40B is not, on its developers' stated requirement of FP8 on Hopper across
several GPUs. D-034.

**For B1.2:**

- The 24 GB allowance covers all five checkpoints. Nothing here establishes that a 200-assay
  zero-shot pass finishes in useful time on one; `feasibility()` answers the hard accelerator
  requirement only, and measuring throughput is B1.2's first job.
- Two hosted-inference routes exist (the ESM-C platform, Evo 2's Nvidia API) and
  `policies/models.md` argues against both: §4 requires the harness constrained in code, and a
  hosted endpoint cannot be. A GPU is now available, which also makes fine-tuning possible for
  the first time — §4 forbids it, so constrain the harness rather than relying on intent.
- D-036 is nearly free to close from B1.2: the checkpoint config is read when the model loads,
  so recording what it says converts a §A0 finding into a verified field.

**Noticed, and since fixed.** `tasks/DECISIONS.md` had two entries numbered D-032. Correctly left alone by this task; resolved on 2026-10-15 by renumbering A1.2's entry to D-041, which was the one not cited from source code. The convention that prevents a repeat is in AGENTS.md.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

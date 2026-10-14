---
id: B1.1
title: Verify model inventory and exclusion status
phase: B
status: review
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

## In flight

- **Branch:** `claude/kind-hopper-1rjv3q`
- **Done:**
  - The inventory is `src/amazebio/models.py`; the evidence is `policies/models.md`, with 16
    quotations all verifying against stored sources; the artefacts are
    `artifacts/b1-1/inventory/inventory.json` and `artifacts/b1-1/ec2-capability/allowlist.json`,
    each with its own `run.json`.
  - Five Tier 1 checkpoints, with identifiers resolved: `esm2_t33_650M_UR50D`,
    `esm2_t36_3B_UR50D`, `esm3-sm-open-v1`, `ESMC-600M`, `evo2_7b`. Licence, access route and
    exclusion status verified for each from first-party sources.
  - Three divergences from the model list in `DESIGN.md`, which is why re-deriving it mattered:
    it gives no checkpoint identifiers; "ESM-C (open release)" does not name a variant (D-035);
    and its Tier 2 list cannot be verified as written (D-034).
  - `esm3-sm-open-v1`'s parameter count is stated by no first-party source — the ESM3 family
    table omits the open checkpoint. Recorded as unstated and pinned by a test; D-036.
  - Tier 2 settled by measurement, not judgement. `tools/ec2_capability.py` dry-runs
    `RunInstances` to measure the launch allowlist. The first probe found no accelerated type
    permitted at all; the project owner then added `g5.xlarge` and `g6.xlarge`, so all five
    Tier 1 checkpoints are runnable and Evo 2 40B is not. D-034.
  - Four sources registered. The two ESM-2 HuggingFace cards are byte-identical, so one shared
    card serves every variant — the same situation already recorded for the ESMC cards.
    `esm2-LICENSE` and `evo2-LICENSE` were stored by A0.1 but never registered, so the licence
    claims resting on them were not quotable until now.
  - `models-check` wired into `pixi.toml` and CI. Full check suite green locally against the
    pinned ruff 0.8.6.
- **Left:** nothing in this task's scope. Moved to `review` rather than `done` because the
  Done-when criteria are met but a reviewer should check the §A0 findings are worded as
  findings and not as defects.
- **Waiting on the project owner:** nothing.
- **For whoever picks up B1.2:**
  - The 24 GB allowance covers all five checkpoints, but nothing here establishes that a
    200-assay zero-shot pass finishes in useful time on one. Measure that first; `feasibility()`
    deliberately answers the hard GPU requirement only.
  - Two hosted-inference routes exist (the ESM-C platform and Evo 2's Nvidia API) and
    `policies/models.md` argues against both: §4 requires the harness to be constrained in code,
    and a hosted endpoint cannot be. A GPU is now available, which also means fine-tuning is
    newly possible — §4 forbids it, so constrain the harness rather than relying on intent.
  - Closing D-036 is nearly free from B1.2: the checkpoint config is read when the model loads,
    and recording what it says converts a §A0 finding into a verified field.
- **Noticed, not fixed:** `tasks/DECISIONS.md` has two entries numbered D-032. Left alone — the
  IDs are referenced from commits and this task does not own them. Two capture files
  (`hf-ESMFold2-README.md`, `hf-esmc-300m-2024-12-README.md`) are still stored but unregistered,
  so they are not quotable; left for whoever needs them.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

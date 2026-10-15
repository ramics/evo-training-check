---
id: A1.5
title: Stage the ESM3-open proxy corpus
phase: A
status: review
gate: false
depends_on: [A1.1]
blocks: [A1.4, A4.3]
design_ref: "§A1"
deliverable: null
owner: claude
---

# A1.5 — Stage the ESM3-open proxy corpus

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage a proxy corpus for ESM3-open, and establish what ESM3 actually states about its
training data, which is the larger part of the result.

Split out of A1.3 when that task completed ESM-2 (DECISIONS.md D-030). A1.3 was scoped to "the
protein-model corpora"; ESM-2's turned out to be a task in itself, and ESM3-open's is a different
problem rather than more of the same one — no corpus release, no stated versions, so the work is
establishing what can be said at all rather than acquiring pinned bytes.

## Steps

- Resolve which source databases and versions ESM3 states, from primary sources only. The paper
  names PDB, UniRef, MGnify and JGI without versions, so expect the §A0 under-specification finding
  to be most of the result.
- Where a version is unstated, record that as the finding and state explicitly which version the
  proxy uses instead.
- Stage the proxy in a form the A2 detectors can stream over. `src/amazebio/uniref.py` already does
  resumable streaming, verifying gunzip, nested-tar walking and concurrent object-storage upload;
  reuse it rather than rewriting. Only `RELEASE`, `ARCHIVE_URL`, `ARCHIVE_MD5` and
  `STATED_CLUSTERS` are UniRef-specific.
- Pin checksums for whatever is acquired, and record stated-versus-used per component.

## Strength of claim (carried from A1.1)

A1.1's verdict governs the wording and is not negotiable here; see `policies/corpora.md` and
DECISIONS.md D-017.

- **ESM3-open — proxy only.** No corpus release; the availability statement covers weights and
  code. Every ESM3 result carries the proxy qualifier explicitly, in figures as well as prose.
  Combined with the unpublished threshold, neither the filter's parameter nor its corpus is
  available, so no conformance re-execution is possible for ESM3.

Note what this means in contrast to ESM-2, now that A1.3 is finished: ESM-2's corpus was verified
against the publisher's own checksum and counted to the digit, so its results carry no acquisition
qualifier. Nothing in this task can reach that standard, and a write-up must not let the two sit
side by side as though it could.

## Done when

- What ESM3 states about its training data is recorded from primary sources, with every unstated
  version logged as a §A0 finding rather than guessed.
- A proxy corpus is staged and checksummed, with stated-versus-used recorded per component.
- Every proxy substitution is documented as a limitation, per §7.

## In flight

- **Branch:** `claude/awesome-archimedes-4yxn9p` — ready for review, every Done-when met.
- **Done:**
  - **What ESM3 states, from the preprint, per component**, with locators and
    machine-verified quotations. The task's own premise was wrong — versions *are* stated for
    all eight components — and the correction plus the four places the under-specification
    actually sits are D-032 and `policies/esm3-open.md` §6-8: UniRef's unstated tier, MGnify's
    unstated granularity, JGI's unpinnable date, and three components the filter's scope list
    does not name.
  - **The reconciliation.** ESM3's stated corpus sizes are 14.7M (UniRef) and 108.2M (MGnify)
    short of the releases they name, each gap alone larger than the 10.6M the filter reports
    removing everywhere. `corpora.md` §5's proposal to validate a reconstruction against that
    figure is withdrawn: for ESM3 there is no substitute for a conformance re-execution.
  - **Both obtainable components staged and verified.** UniRef 2023_02's three tiers
    (211.8 GB) and MGnify 2023_02's 90%-clustered product (83.5 GB), 295.3 GB in all. Each
    matches the md5 its publisher publishes. Each UniRef tier was then counted in region
    against its own release note — 350,950,053 / 170,669,877 / 60,479,070, delta zero — because
    the archive md5 cannot show the tar walk split it into the right tiers. Scope was the
    project owner's call: D-033.
  - **Stated-versus-used for all eight components** in `artifacts/a1-5/composition.json`,
    joined from the staging manifests rather than retyped, with no coverage share by design.
  - **Two re-entry routes the filter's description does not reach**, recorded in
    `esm3-open.md` §8: predicted-structure databases over already-filtered sequences, and
    362M inverse-folded sequences that are in no database for an MMseqs query to match.
  - Code: `src/amazebio/esm3.py`, `src/amazebio/mgnify.py`, `tools/stage_mgnify.py`,
    `tools/esm3_composition.py`, plus a `Release` registry and `ParallelRangeRead` in
    `amazebio.uniref`. `boto3` is now pinned, which no staging tool had. 221 tests pass.
- **Left:** nothing. Move to `done` on review.
- **Waiting on the project owner:** nothing.
- **For whoever picks up A1.4 or A4.3:** A4.3's ESM3 scope table needs no staging — the
  composition is documentary and the artefact is there. Do not write any figure of the form
  "x% of ESM3's corpus": JGI is about a third of its unique training tokens and cannot be
  reconstructed at all, so coverage is over the components that could be staged.
- **For whoever picks up A2.2:** the two re-entry routes cannot be measured without the
  structure-side components (AlphaFoldDB v4, ESMAtlas), which D-033 deliberately did not buy.
  Re-ask the cost question rather than assuming it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

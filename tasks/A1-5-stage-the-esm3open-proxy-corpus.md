---
id: A1.5
title: Stage the ESM3-open proxy corpus
phase: A
status: in-progress
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

- **Branch:** `claude/awesome-archimedes-4yxn9p`
- **Done:**
  - What ESM3 states is established from the preprint, per component, with locators and
    machine-verified quotations. The task's own premise was wrong — versions *are* stated — and
    the correction plus the four places the under-specification actually sits are D-032 and
    `policies/esm3-open.md` §6-8.
  - The reconciliation: ESM3's stated corpus sizes are 14.7M and 108.2M short of the releases
    they name, each gap alone larger than the 10.6M the filter reports removing everywhere.
    `corpora.md` §5's proposal to validate a reconstruction against that figure is withdrawn.
  - Component table and arithmetic in `src/amazebio/esm3.py`, written out by
    `tools/esm3_composition.py` to `artifacts/a1-5/composition.json` with a `run.json`. Tests
    parse the stored release notes and check the transcribed integers against them.
  - Pins verified: UniRef 2023_02 (211,819,312,677 bytes, md5 from the release metalink) and
    MGnify 2023_02 (published md5 per file). Six captures registered as sources.
  - `amazebio.uniref` carries a `Release` registry, so 2023_02 stages through A1.3's verified
    path; `--release` is threaded through the staging, counting and EC2 tools.
- **Left:**
  - The staging pass. Nothing is staged yet.
  - Then the stated-versus-used record per staged component, and status to `review`.
- **Waiting on the project owner:** **the staging scope.** The bucket withholds
  `s3:DeleteObject`, so this is permanent spend, and the span is $0 to ~$15/month depending on
  which components are staged. Options and costs are with the owner; D-031 is the precedent for
  treating this as the owner's call rather than a worker's.
- **For whoever picks up A2.2 or A4.3:** A4.3's ESM3 scope table needs no staging — the
  composition is documentary and the artefact is already there. The two re-entry routes in
  `esm3-open.md` §8 cannot be measured without the structure-side components (AlphaFoldDB,
  ESMAtlas), which nothing has authorised staging; expect to ask the cost question for those.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

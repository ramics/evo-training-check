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
- **Done:** nothing yet; claimed.
- **Left:** everything in Steps.
- **Waiting on the project owner:** nothing yet. Expect a staging-scope question, as A1.2 had:
  the corpus bucket withholds `s3:DeleteObject`, so what gets staged is permanent spend.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

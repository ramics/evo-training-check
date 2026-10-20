---
id: B2.4
title: Publish the assay provenance and licence register
phase: B
status: review
gate: false
depends_on: [B2.2, B2.3]
blocks: [B3.1, B3.2, B3.3, B3.4, B4.1]
design_ref: "§5 deliverable 2"
deliverable: 2
owner: claude
---

# B2.4 — Publish the assay provenance and licence register

**Design reference:** DESIGN.md §5 deliverable 2 · **Deliverable 2**

## Goal

Ship the curated assay collection as a citable deliverable with full provenance and licensing.

## Steps

- Consolidate all assay metadata into one validated register.
- Verify every licence permits the intended redistribution; resolve or drop anything unclear.
- Add schema validation to CI.
- Write the register's documentation and citation guidance.

## Done when

- Register validates in CI and covers every assay used in B5.
- Licence position is verified per assay, with unclear cases resolved or removed.
- Documented and citable.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`**, in
[PR #31](https://github.com/ramics/amazebio/pull/31). Nothing is waiting on the project owner.

**Finished.** `assays/register.json` and `assays/register.md` are the deliverable, committed
rather than left in `artifacts/` because "publish" and "citable" ask for something a reader can
fetch. `tools/assay_register.py` builds them from B2.2's curation, B2.3's control set and
`assays/licences.json`; `tools/assay_licences.py` acquires that evidence and is the only step
that touches the network. `assays/README.md` documents both. `assays-check` is the ninth CI
step. 35 tests in `tests/test_assay_register.py`.

**Done-when verdict.** The register covers all 31 assays — 21 studies, 21 organisms, 7 of them
B2.3's control set — which is every assay B5 analyses, and `assays-check` fails on an assay with
no traceable study, an unrecognised licence URL, a deposit no longer established to be the bytes
we read, or a changed deposit licence. The licence position is per assay and carries both halves
(D-228). It is documented and citable, with the three-part citation in the register's own
`citation` block.

**What the measurement changed (D-228).** The pinned release was downloaded from a server that
states no licence. The Zenodo deposit of the same release is MIT, and its assay archive hashes
identically to the pinned copy, so the grant is demonstrated rather than inferred from matching
file sizes. Of the 21 source articles, 20 assays' studies deposited a permissive licence, 5
restrictive, 2 disagreed with themselves across versions and 4 deposited none — and none of that
constrains this project, which redistributes no assay data.

**Carried forward:** MIT on a data deposit is ordinary Zenodo practice rather than a settled
legal question, and the register says so. If this project ever redistributes assay data, D-228
does not cover it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

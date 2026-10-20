---
id: B2.2
title: Curate the extension assay collection
phase: B
status: review
gate: false
depends_on: [B2.1]
blocks: [B2.3, B2.4]
design_ref: "§B2, §7"
deliverable: 2
owner: claude
---

# B2.2 — Curate the extension assay collection

**Design reference:** DESIGN.md §B2, §7 · **Deliverable 2**

## Goal

Expand beyond the benchmark's small in-scope subset, which §7 names as the study's biggest
statistical threat. Published data on well-characterised proteins only, per §4.

## Steps

- **Start from published collections.** The ESMC preprint's 25 ProteinGym viral assays and
  ProteinGym itself may already suffice for the homology regression; v0.4 narrowed this task
  to extending only where n is genuinely insufficient (DECISIONS.md D-010). Establish that
  first and record the finding either way.
- Only if n is insufficient: search systematically for further published assays meeting the
  §4 constraints, and record the search strategy.
- Apply documented QC and inclusion criteria, fixed before screening.
- Record per assay: organism, protein, fold/domain, readout type, variant count, DOI, licence.
- Exclude anything outside §4 scope and log the exclusion reason.

## Done when

- Inclusion criteria were fixed before screening and are documented.
- Every included assay carries complete provenance and licence metadata.
- Collection materially increases usable n over the benchmark subset alone.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`**, in
[PR #30](https://github.com/ramics/amazebio/pull/30) alongside A3.2 and A4.4.

**Finished.** `src/amazebio/assays.py` places an assay in the pinned taxonomy and applies the
denylists; `tools/assay_register.py` builds the register; `tests/test_assays.py` pins the
arithmetic and the refusals. Artefacts at `corpora/results/b2-2/` —
`artifacts/b2-2/register.json`, `register.md`, `run-register.json`.

**Done-when verdict.** Inclusion criteria were fixed before screening and are in the artefact
(`inclusion_criteria`); every included assay carries organism, taxid, accession, family, order,
readout, variant count, length and DOI, with the source of each organism pin recorded. The third
criterion — *materially increases usable n* — is **not met, and D-197 records why it cannot be**:
the published collections do not give a usable design, and more assays do not fix it. Family is
perfectly confounded with exclusion status by construction, the retained arm is 7 bacteriophage
assays sharing one readout class from one study, and ESM3-open's exclusion status is a
similarity computation rather than a taxonomic lookup.

**Waiting on the project owner:** nothing. **Carried to B5.1:** §B5's pre-registered model
cannot be frozen as drafted — see D-197's consequence.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

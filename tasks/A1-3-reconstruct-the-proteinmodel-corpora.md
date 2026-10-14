---
id: A1.3
title: Reconstruct the protein-model corpora
phase: A
status: in-progress
gate: false
depends_on: [A1.1]
blocks: [A1.4, A4.3, A8.1, C5.2]
design_ref: "§A1"
deliverable: null
owner: claude
---

# A1.3 — Reconstruct the protein-model corpora

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage the surviving corpora for the protein-level models, from the stated source
databases at the stated versions.

## Steps

- Resolve which source database tiers and versions each model states.
- Acquire those versions where recoverable; otherwise pin the closest recoverable version.
- Pin checksums and record the version actually used versus the version stated.
- Where composition is under-documented, state the proxy assumption explicitly.

## Done when

- Corpora staged, checksummed, version-pinned.
- Stated-vs-used version gap recorded per model.
- Under-documentation is logged as a finding, per §7.

## Strength of claim (carried from A1.1)

A1.1's verdicts set how this task's results may be worded; see `policies/corpora.md` and
DECISIONS.md D-017.

- **ESM3-open — proxy only.** No corpus release; the availability statement covers weights and
  code. Every ESM3 result carries the proxy qualifier explicitly, in figures as well as prose.
  Combined with the unpublished threshold, neither the filter's parameter nor its corpus is
  available, so no conformance re-execution is possible for ESM3.
- **ESM-2 — reconstructible proxy, and the best pinned of the four**: a pinned UniRef release plus
  published held-out cluster IDs. Cheapest corpus here and the right first target.
- **ESM-C — not applicable.** No stated exclusion and no corpus release; comparison only.

## State — 2026-10-14

In progress on branch `ccr-2956d088-s25hlk`, pushed and green but **not merged into `main`**, so the files
named here are absent from a `main` checkout. None of this is a result; it is the handover.

**Done.** ESM-2's version pin is corrected from UniRef 2018-03 to **UniRef50 2021_04, with
training sequences sampled from UniRef90**, verified from the repository's own model table rather
than inferred. `policies/esm2.md` is rewritten on the branch; the reasoning and the knock-on
effects are in DECISIONS.md D-024. Retrievability of that release is established: the archive
serves 2021_04 only as a single 158 GB `uniref2021_04.tar.gz`, published md5
`444f0a7062a65a988ba1d5949d1d6419`, whose first member is a 93.7 GB `uniref100.tar` — so UniRef50
sits tens of gigabytes into the stream. The release notes give UniRef50 at 49,874,565 clusters, so
the pin is exact even where the bytes are not local. The project owner's acquisition decision is
recorded in D-024: 2021_04 is canonical, and the current per-tier release is an explicit proxy
mode that stamps the stated-vs-used gap onto every output.

**Not done.**

- The acquisition pipeline itself, which is the artefact this repo keeps: `data/` is git-ignored
  and a cloud session's disk is ephemeral, so the recipe and the provenance are the deliverable
  and the bytes are regenerated wherever it runs. It should pin the release, verify the published
  md5, extract the UniRef50 and UniRef90 members, and write the composition table and `run.json`
  through `amazebio.repro.run`.
- The ESM3-open proxy corpus. This is the better next step while the ESM-2 bytes are out of
  reach, and A1.1's verdict already fixes how it must be worded: proxy only, no corpus release.
- `UR50/S` versus `UR50/D` is never defined in any retrieved source, and the difference decides
  whether a reconstruction holds one representative per cluster or a per-epoch sample from each.
  It needs the ESM-2 paper added to `policies/sources.json` as a primary source. Do not guess it;
  §A0 makes the under-specification itself a finding.

**Waiting on the project owner.** Staging the 2021_04 bundle needs a machine with roughly 300 GB
of disk — download, verify the md5, then extract, in that order. AWS credentials were to arrive as
an environment secret under names of the owner's choosing; until they do, the pipeline can only
run in proxy mode. Note that A1.1 expected ESM-2 to be the cheapest corpus here and the right
first target. D-024 withdraws that: the pin is exact, but the bytes are the most expensive of the
four.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

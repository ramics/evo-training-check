---
id: X1.5
title: Restore the result artefacts lost to local-only writes
phase: X
status: ready
gate: false
depends_on: []
blocks: [X1.2, X1.3]
design_ref: "§7"
deliverable: null
owner: unassigned
---

# X1.5 — Restore the result artefacts lost to local-only writes

**Design reference:** DESIGN.md §7 · **Decision:** D-188

## Goal

Regenerate the two result sets that cost real compute to restore, and close out the audit
D-188 recorded.

D-188 is the full account. In short: `artifacts/` is git-ignored and the session containers that
wrote it were reclaimed, so **nine finished tasks had no surviving result artefact**. The guard
is already in place — `amazebio.repro.run` now refuses to complete a run that records a local
output and names no durable destination, and all 26 `run(...)` call sites in `tools/` pass
`durable=`, with no exemptions. **This task is the remediation, not the fix.**

Seven of the nine were cheap and were regenerated under D-188 (A1.2, A1.4, A1.5, A1.7, A4.1,
A4.3, B1.1, B2.1). Two were not.

## Steps

- **Regenerate A2.1's detection tables.** `tools/detect_profiles.py`, both registries, both Evo
  releases. A2.1's own file records what the pass was: the pre-registered sample of D-078
  deepened ten-fold under D-099, searched as hash bands so nothing is searched twice, about
  twenty hours of compute. The figures to reproduce are in that file — Pfam 590 and RVDB-prot
  1,091 on Evo 1, 811 and 4,154 on Evo 2, with the first pass preserved separately. **Treat a
  mismatch as a finding, not as a reason to adjust anything**: these tables were produced before
  the protein cache's five scaffolding faults were fixed, and whether the committed code
  reproduces the published numbers is exactly what regeneration is for.
- **Regenerate A4.2's taxonomy-misassignment benchmark.** `tools/taxonomy_benchmark.py`, a
  geNomad run against the pinned ICTV exemplar set. Hours, not tens of hours. The error rates by
  direction and their exact intervals are in A4.2's file and in the decisions log.
- **Check the regenerated numbers against the recorded ones** and record the comparison. This is
  the only chance to find out whether the published Phase A figures reproduce, because until now
  nothing could be re-run against them.
- **Audit the remaining `artifacts/` producers.** D-188 converted every `run(...)` call site in
  `tools/`, but a tool that writes a file *without* recording it as an output of a `run` block is
  still invisible to the guard. Find any, and either record the output or say why not.
- **Add the durable copy to the artefact contracts.** `metrics/detections.md` and
  `metrics/manifests.md` both name `artifacts/<task>/` as where their artefact lives and neither
  mentions the object store. A consumer reading either one today is told to look in the place
  that lost the files.

## Done when

- A2.1's and A4.2's tables exist in object storage with their `run.json`.
- The regenerated figures are compared against the recorded ones and the comparison is written
  down — agreement or disagreement, either way.
- No tool writes a result the guard cannot see.
- `metrics/detections.md` and `metrics/manifests.md` state where a consumer finds the durable copy.

## Notes

**Why this blocks X1.2 and X1.3.** One-command reproduction and the figures both read result
artefacts; neither can run against tables that are not there. A3.2 and A6.1 also need A2.1's
tables, but they are blocked behind their own gates, so the dependency is recorded here rather
than as an edge that would change their status.

**What was never at risk, so nobody re-checks it:** all 1.02 TB of staged corpora (that bucket
has no `s3:DeleteObject`), and everything in git — code, decisions, task records, policy specs,
evidence captures. No *finding* was lost either: every number survives in its task file and the
decisions log. That is precisely the problem, since `AGENTS.md` makes "artefacts before prose"
non-negotiable.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: X1.5
title: Close out the durability audit
phase: X
status: in-progress
gate: false
depends_on: []
blocks: []
design_ref: "§7"
deliverable: null
owner: claude
---

# X1.5 — Close out the durability audit

**Design reference:** DESIGN.md §7 · **Decision:** D-188

## Goal

Close the two gaps the durability guard cannot close by itself.

D-188 is the full account. In short: `artifacts/` is git-ignored and the session containers that
wrote it were reclaimed, so **nine finished tasks had no surviving result artefact**. The guard is
already in place — `amazebio.repro.run` refuses to complete a run that records a local output and
names no durable destination, all 38 `run(...)` call sites in `tools/` pass `durable=` with no
exemptions, a test parses `tools/` so a missed call site fails review rather than a six-hour run,
and no test process can reach the real bucket. Seven of the nine were cheap and were regenerated
under D-188.

**The three measurements that need their job run again are X1.6.** This task is what is left
after them, and neither task depends on the other.

## Steps

- **Audit for results the guard cannot see.** The guard fires on an output recorded in a `run`
  block. A tool that writes a file without recording it as an output is still invisible to it —
  and `stage_opengenome.py` showed how easy that is to miss by inspection, since it was skipped
  during the conversion *because* it uploads the staged corpus, while also writing local
  composition tables. Find any such writer, and either record the output or say why not.
- **Correct the artefact contracts.** `metrics/manifests.md` still names `artifacts/a1-4/` as
  where its manifests live, with no mention of object storage. A consumer reading it today is sent
  to the place that lost the files. `metrics/detections.md` has been corrected already and is the
  model: it says where a run writes, where a consumer reads, and that a local `artifacts/`
  directory is a cache whose absence means nothing.

## Done when

- No tool writes a result the durability guard cannot see.
- `metrics/manifests.md` states where a consumer finds the durable copy.

## State — 2026-10-20

`in-progress`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project
owner.

## Notes

**This task blocks nothing.** The dependency on X1.2 and X1.3 moved to X1.6 with the re-runs,
which are what those tasks actually wait on.

**What was never at risk, so nobody re-checks it:** all 1.02 TB of staged corpora (that bucket
has no `s3:DeleteObject`), and everything in git — code, decisions, task records, policy specs,
evidence captures. No *finding* was lost either: every number survives in its task file and the
decisions log. That is precisely the problem, since `AGENTS.md` makes "artefacts before prose"
non-negotiable.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

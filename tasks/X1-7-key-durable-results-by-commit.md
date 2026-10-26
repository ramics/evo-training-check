---
id: X1.7
title: Key durable results by commit
phase: X
status: done
gate: false
depends_on: []
blocks: []
design_ref: "§7"
deliverable: null
owner: claude
---

# X1.7 — Key durable results by commit

**Design reference:** DESIGN.md §7

## Goal

A pipeline that writes its outputs to the durable store a second time replaces the first
copy. The corpus bucket is un-rewritable only in the sense that nothing can be *deleted*
from it; `PutObject` on an existing key succeeds and the previous bytes stop being
readable. D-216 found this the ordinary way — `corpora/results/a3-4/bins-pfam-38.2.json`
was 2,446 bytes from a partial run at 10:42 and 215,098 bytes from the full run at 12:16,
under one key — and nothing was lost, because the thing replaced was the worse of the two.
That is luck, not a property.

The EC2 tools already do the right thing: D-126 puts the commit in the key, so two runs of
the same tool at different commits cannot collide. Every in-container pipeline writes to a
fixed name. Make the in-container path behave like the in-region one.

## Why it is its own task

It is a defect in `amazebio.repro`'s durable-write path, shared by every pipeline, and
`AGENTS.md` forbids widening whichever task next trips it to absorb the fix.

## Steps

- Read how `repro.run`'s `durable=` upload names a key today, and how
  `tools/ec2_opengenome_contigs.py`'s `result_keys` names one. Fix the convention for the
  in-container path before changing anything, and record it.
- Decide what a re-run at the *same* commit should do. Overwriting a byte-identical object
  is harmless; overwriting a different one at the same commit means a dirty tree or an
  undeclared parameter, which `repro` already has opinions about. Say which it is rather
  than leaving it to whichever pipeline hits it first.
- Apply it in `repro`, so a pipeline gets it without opting in.
- Leave the existing keys where they are. The store has no delete, so the un-keyed objects
  already written stay; what is needed is a way to tell which commit produced each one,
  and the `run.json` beside it already carries that.
- Settle, or record as unsettleable from here, whether the bucket keeps earlier versions.
  `get_bucket_versioning` and `list_object_versions` are both AccessDenied in this
  container, so this is a question for the project owner, not a retry.

## Done when

- A pipeline writing the same output twice at two commits produces two durable objects.
- The same-commit case behaves the way the decision says it should, with a test.
- No existing durable key is orphaned: whatever reads results can still find them.
- The versioning question is answered or registered as owner-blocked with what was tried.
- `python3 tools/board.py --check` passes and CI is green.

## Closed — 2026-10-22

`done`. **PR #31 merged on 2026-10-22, so the implementation this file has pointed at since
2026-10-20 is now on `main`** and nothing further was needed. Every Done-when criterion is met
and was re-checked against the live store rather than against the branch:

- Two commits produce two durable objects. `_upload_one` writes the stable key and the
  `by-commit/<commit>/` twin, and the twins are present in the bucket for every task that has
  published since — a3-4 carries 15 objects against 9 stable keys, b3-4 12 against 3, b4-2 9
  against 3.
- The same-commit case is `_check_commit_keys`, which refuses before uploading anything when
  this commit has already published different bytes, naming the object and both digests, and
  is escapable only through `replace_durable='<reason>'` which lands in the manifest. Covered
  by tests in `tests/test_repro.py`; the file's 49 tests pass.
- No key moved, so nothing is orphaned.
- Versioning is answered: on, noncurrent versions expiring after seven days, by the owner
  (D-218, D-219). This container can neither read nor set it, so it rests on his word, and the
  commit-keyed copies — which have no seven-day window — remain what a citation relies on.
- `tools/board.py --check` passes over 75 tasks with 0 problems.

**One residual, fixed rather than left implied — D-253.** The guard binds `amazebio.repro`'s
durable path, and `repro` only guards what goes through `repro`. Three tools published results
by calling `put_object` directly and so got neither the twin nor the clash check:
`tools/count_clusters.py`, `tools/evo2_accessions.py` and `tools/uniprot_release_count.py`.
They now go through `objectstore.put_once`, which `repro` also calls, so there is one write
path and not two.

The sweep AGENTS.md asks for before closing an incident turned up a second thing while it was
looking. The regional S3 endpoint — the one whose absence cost most of a day in October — was
hand-written at 26 call sites, fourteen of which a grep missed because the call spans several
lines. All 26 now call `objectstore.client()`, and a test walks the source tree and fails the
build on a twenty-seventh.

## Notes

Read with D-126, which put the commit in the EC2 result keys for this reason one tool at a
time, and D-216, which is the general case.

## State — 2026-10-21

`review`. The implementation is on `claude/project-thread-a3vch4`, which is **open pull request
#31** and not on `main`. A later task read this file from a container cloned at `main`, found no
commit-keyed writes in `amazebio.repro`, took the work to have been lost with its container and
began re-implementing it from the description below. D-242 records that, and the re-implementation
was dropped once the pull request was found. Nothing here needs redoing; what it needs is the
merge, which is the project owner's.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`.**

Done. `amazebio.repro` now writes every durable output twice: to the stable key it has always
used, so every reader keeps working, and to a twin under `by-commit/<commit>/` that a later
run of the same pipeline cannot reach. The commit comes from the checkout, or from the
`code_commit` parameter where there is no checkout, which is the EC2 case. Each object
carries its sha256 and its commit as metadata. A run whose own commit has already published
different bytes is refused before anything is uploaded, naming the object and both digests;
`replace_durable='<reason>'` allows it and the reason lands in the manifest. Twelve tests,
and the full suite is green.

No existing key moved, so nothing is orphaned.

**Versioning is on** (D-218, D-219). The owner enabled it on 2026-10-20 and set noncurrent
versions to expire after seven days, so it recovers a mistake someone notices that week and
nothing older. This session can neither make nor read that setting — both calls are denied —
so the state rests on his word. The commit-keyed copies have no such window and stay the
guarantee anything cited relies on.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: X1.7
title: Key durable results by commit
phase: X
status: review
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

## Notes

Read with D-126, which put the commit in the EC2 result keys for this reason one tool at a
time, and D-216, which is the general case.

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

**The versioning question is answered and is the owner's to act on** (D-218). He chose to
turn it on; this session cannot, being denied both `s3:PutBucketVersioning` and
`s3:GetBucketVersioning`, so it also cannot confirm the bucket's state afterwards.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

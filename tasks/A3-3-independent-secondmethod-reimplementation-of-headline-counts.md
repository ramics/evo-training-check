---
id: A3.3
title: Independent second-method reimplementation of headline counts
phase: A
status: review
gate: true
depends_on: [A3.2]
blocks: [A6.1, X4.1]
design_ref: "§7"
deliverable: null
owner: claude
---

# A3.3 — Independent second-method reimplementation of headline counts

**Design reference:** DESIGN.md §7

## Goal

Reproduce the headline Phase A numbers by a deliberately different method before anything is
published. §7 makes this a precondition, not a nice-to-have.

## Steps

- Choose a second method that does not share A2/A3's tooling or assumptions; justify the
  choice.
- Reimplement the headline counts from the A3.1 definitions alone, not from the A3.2 code.
- Cover the A7.1 conformance numbers too, not only the survival counts: a conformance
  failure is a stronger and more sensitive claim, so it gets the same second method.
- Compare results; investigate and explain every material divergence.
- Record the comparison as a published-alongside artefact.

## Done when

- Headline counts reproduced by an independent method.
- All material divergences explained in writing.
- GATE: Phase A publication is blocked until this passes.

## State — 2026-10-20

`review`. **Branch `claude/a3-3-independent`, merged into `claude/project-thread-a3vch4`.**

**Done.** `src/amazebio/recount.py`, `tools/recount.py`, `tests/test_recount.py` (38 tests),
and `corpora/results/a3-3/` holding `recount.json`, `comparison.md` and a `run-recount.json`
pinning 62 inputs. Written from the frozen definitions alone by an implementer that had not
read `survival.py`, `quantify.py`, `conformance.py` or the A3.2 and A7.1 tooling; the module
imports nothing from them and derives its own Wilson interval from `metrics/survival.md`.
Every M1 and conformance figure reproduces exactly; the two divergences are in per-route
record counts and in a coverage fraction, neither of which the headline passes through.
D-210 records the comparison, D-211 and D-212 the two calls it forced.

**Waiting on the project owner: whether this gate opens.** The Done-when criteria are met —
headline counts reproduced by an independent method, every material divergence explained in
writing, the comparison published alongside. `AGENTS.md` reserves opening a gate to the
project owner, so the task stays at `review` until that is recorded.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

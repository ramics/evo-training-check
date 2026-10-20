---
id: A3.3
title: Independent second-method reimplementation of headline counts
phase: A
status: done
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

`done`. **The gate is open** — the project owner read `comparison.md` and opened it on
2026-10-20, recorded in D-215. The Phase A write-up (A6.1) may begin once its other
dependencies clear.

The work is on branch `claude/project-thread-a3vch4` and lands on `main` through that
branch's pull request. Artefacts are at `corpora/results/a3-3/`: `recount.json`,
`comparison.md` and `run-recount.json`, 62 pinned inputs, 10,000 resamples at seed
20261020.

Two conditions travel into the write-up, both logged: a per-route record count for an
`opengenome2` group quotes the recount's figure or labels the apportioned one as
apportioned (D-211), and conformance coverage is quoted per reading (D-212).

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

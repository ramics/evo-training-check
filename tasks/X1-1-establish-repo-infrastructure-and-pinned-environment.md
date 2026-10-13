---
id: X1.1
title: Establish repo infrastructure and pinned environment
phase: X
status: review
gate: false
depends_on: []
blocks: [X1.2]
design_ref: "§5 deliverable 7"
deliverable: 7
owner: claude
---

# X1.1 — Establish repo infrastructure and pinned environment

**Design reference:** DESIGN.md §5 deliverable 7 · **Deliverable 7**

## Goal

Stand up the engineering substrate every other task assumes: pinned environment, seed
discipline, layout, CI.

## Steps

- Pin the environment with a lockfile; document the setup path.
- Establish the seed and determinism convention all pipelines must follow.
- Set up CI running tests, schema validation and linting.
- Document the repo layout and where artefacts land.

## Done when

- A clean checkout reaches a working environment by documented steps.
- Seed and provenance convention is documented, importable and covered by tests.
  (Enforcement in a real pipeline is verified by A1.4 — no pipeline exists at X1.1.
  See DECISIONS.md D-003.)
- CI green on an empty-but-valid repo state.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

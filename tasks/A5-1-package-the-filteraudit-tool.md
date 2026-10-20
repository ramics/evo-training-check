---
id: A5.1
title: Package the filter-audit tool
phase: A
status: done
gate: false
depends_on: [A1.4, A3.2, A4.1, A4.2]
blocks: [X1.2]
design_ref: "§5 deliverable 1"
deliverable: 1
owner: claude
---

# A5.1 — Package the filter-audit tool

**Design reference:** DESIGN.md §5 deliverable 1 · **Deliverable 1**

## Goal

Consolidate the Phase A machinery into the shippable `filter-audit` deliverable: policy spec
language in, survival-route report out.

## Steps

- Define the public interface: policy specification in, corpus reference in, survival-route
  report out.
- Refactor A1.4/A2.*/A3.2 into that interface without changing results.
- Add tests, including a small fixture corpus with known expected output.
- Document usage and the limitations of each detection route.

## Done when

- Tool runs end-to-end on a fixture corpus in CI.
- Refactor reproduces A3.2 results exactly.
- Interface and limitations documented.

## State — 2026-10-20

`review`. **Branch `claude/project-thread-a3vch4`.** Nothing is waiting on the project owner.

**Done.** `src/amazebio/filteraudit.py` (the one-door interface), `tools/filter_audit.py`
(its command line, with `--verify`), `tests/test_filteraudit.py` (14 tests including the
end-to-end fixture run CI exercises) and `docs/filter-audit.md`. D-209 records the facade
decision and the measurement behind it: all 21 of A3.2's groups reproduce identically through
the interface.

**Left.** Nothing for the Done-when. A staged-release corpus loader would let the interface
be pointed at the real releases from the command line rather than from the pipelines; that is
convenience, not a criterion, and it belongs to whoever next needs it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Closed — 2026-10-20

`done`. The work is on `main` (pull request #30 merged, or earlier as the State block
records). Every Done-when criterion is met.

---
id: X3.1
title: Run the responsible-disclosure process
phase: X
status: blocked
gate: true
depends_on: [A6.1, B5.4]
blocks: [X4.1]
design_ref: "§4, §7"
deliverable: null
owner: unassigned
---

# X3.1 — Run the responsible-disclosure process

**Design reference:** DESIGN.md §4, §7

## Goal

Execute the §4 disclosure process: share findings with the named parties before any preprint,
with a stated response window. §7 requires treating the window as substance, not formality.

## Steps

- Prepare the disclosure package from the frozen Phase A and B findings.
- Send to each party named in §4, with an explicit stated response window.
- Log send dates, recipients and the window per party.
- Record all responses and how each was addressed in the manuscript.

## Done when

- Disclosure sent to every party named in §4, with a stated window.
- Send log and response log both complete.
- GATE: X4.1 preprint is blocked until the window has elapsed and responses are addressed.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

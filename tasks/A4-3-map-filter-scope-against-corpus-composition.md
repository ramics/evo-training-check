---
id: A4.3
title: Map filter scope against corpus composition
phase: A
status: blocked
gate: false
depends_on: [A0.3, A1.2, A1.3, A1.5]
blocks: [A6.1]
design_ref: "§A4, §2 HA, §6 weekend 2"
deliverable: 1
owner: unassigned
---

# A4.3 — Map filter scope against corpus composition

**Design reference:** DESIGN.md §A4, §2 HA · **Deliverable 1**

## Goal

Establish, from the published methods, which corpus components each filter was actually applied
to, and what fraction of the trained-on corpus was therefore never a candidate for removal.
This is the leading Phase A result per DECISIONS.md D-007.

## Steps

- For each model and each of the three readings, record which corpus components the filter was
  applied to, quoting the published scope statement for each.
- Set that against the corpus composition from A1.2/A1.3: tokens, records and share of training
  data per component, in scope versus out of scope.
- Where a filter was inherited across model versions, record whether its scope was revisited
  when the corpus changed, and quote the text that does or does not address it.
- Identify every component carrying a plausible route for hazard-derived sequence that the
  filter could not reach, and state the route per component.
- Distinguish throughout: not applied to a component, applied but unable to detect, and applied
  and deliberately retaining. These are different findings with different remedies.
- Fix the share metrics with A3.1 before computing anything.

## Done when

- A scope table exists per model × reading, with every scope claim traced to a quoted source.
- In-scope versus out-of-scope shares are quantified against A1.2/A1.3 composition.
- Inheritance across model versions is documented, including whether scope was revisited.
- The three failure kinds above are kept separate in the output.
- No claim about what a filter did not cover rests on absence of mention alone without that
  absence being stated as the evidence.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A4.3
title: Map filter scope against corpus composition
phase: A
status: review
gate: false
depends_on: [A0.3, A1.2, A1.3, A1.5]
blocks: [A6.1]
design_ref: "§A4, §2 HA, §6 weekend 2"
deliverable: 1
owner: claude
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

## State — 2026-10-15

`review`. Work branch: `claude/kind-wozniak-ec94y4`. Artefacts:
`artifacts/a4-3/scope.json` and `scope.md`, from `tools/scope_map.py`.

**The headline.** The same policy, inherited verbatim by Evo 2 ("As previously described"),
covers **11.52% of OpenGenome v1 and 0.41% of OpenGenome2**. Out-of-scope shares are therefore
**88.48%** and **99.59%**. The scope gap widened as the corpus grew, under a filter nobody
changed — which is D-007's claim measured rather than asserted.

| corpus | reading | out of scope | reached, no rule | not addressed | in scope | share out of scope |
|---|---|---|---|---|---|---|
| Evo 1 | literal / charitable | 2 | 0 | 0 | 1 | 88.48% |
| Evo 1 | strict | 0 | 2 | 0 | 1 | 0% |
| Evo 2 | literal / charitable | 9 | 0 | 0 | 1 | 99.59% |
| Evo 2 | strict | 0 | 9 | 0 | 1 | 0% |
| ESM3-open | literal | 0 | 0 | 3 | 5 | 0% (10.62% not addressed) |
| ESM3-open | charitable / strict | 0 | 0 | 0 | 8 | 0% |

The strict rows are not a contradiction, they are the spread A0.4 reports: a wildcard-scope
reading *examines* every component and removes from one, so the same eukaryotic genome is
`out_of_scope` under the literal reading and `reached_no_rule` under the strict one. Different
claims about the same sequence (D-014).

By token share instead of bytes, the filtered component is **1.83% of Phase 1 pretraining** and
**0.40% of Phase 2 context extension** — the denominator has to be named because the two phases
weight the components differently by more than four-fold.

**Against the Done-when list:**

- *A scope table per model and reading, every scope claim traced to a quoted source* — yes;
  the six specs carry the quotations and `scope.json` carries the policy id per row.
- *In-scope versus out-of-scope shares quantified against A1.2/A1.3 composition* — yes, and
  the composition now rebuilds from committed captures rather than a live API call, so the
  figures regenerate from pinned inputs.
- *Inheritance across model versions documented, including whether scope was revisited* — yes.
  Evo 2 adds no procedure of its own and its eukaryotic-component curation contains no viral
  screening step; the same policy is therefore measured against both corpora and the
  difference between the two answers is the finding. ESM2 to ESM3 has no inherited filter to
  revisit: ESM-2 and ESM-C have no stated hazard-driven exclusion at all, so ESM3's filter is
  new at ESM3.
- *The three failure kinds kept separate* — yes, plus a fourth state that is not a failure
  kind. "Not applied" is `out_of_scope`; "applied but unable to detect" is the `limits` column
  (ESM3-open's literal reading leaves both identity thresholds unspecified); "applied and
  deliberately retaining" is the `retains_by_design` column (the high-confidence gate and the
  vOTU representative rule). The fourth is `not_addressed`, for a source that names a list and
  does not say the list is exhaustive.
- *No claim resting on absence of mention alone* — the `caveats` block in the artefact is that
  statement in machine-readable form, led by `absence-of-mention-is-the-evidence`, so a figure
  cannot be quoted out of the artefact without it.

**Two things the reviewer should look at hardest.**

1. **D-065 corrects a published number.** A1.2's "0.2% of OpenGenome2" divides FASTA bytes by a
   denominator spanning both trees, which `policies/evo.md` §7 itself forbids. Corrected within
   the FASTA tree it is 0.41%. The correction makes the filtered component *larger*, so it
   does not flatter this task's thesis; a test asserts that direction. `policies/evo.md` still
   says 0.2% and is A1.2's prose to amend, at A6.1.
2. **The spec-label to component-name join** (`amazebio.scope.COMPONENT_LABELS`) is declared
   rather than derived, per D-013. Running the classifier against the real specs before writing
   any test caught it reporting the viral component itself as `out_of_scope`, because the spec
   says `IMG/VR` and the composition says `imgvr`. An unmapped label now raises.

**Open, and carried as caveats rather than resolved here:** `S-EVO2-NATURE-METHODS` is
unretrieved and could add procedure the preprint omits; whether the denylist was revisited for
Evo 2 is not addressed by any retrieved source (A9.1 measures the decay); and ESM3 has no
corpus-level denominator at all, since JGI is 265,070 of 768,109 M stated unique training
tokens and is unreconstructible, so its shares are documentary rather than measured (D-033).

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

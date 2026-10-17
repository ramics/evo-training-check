---
id: A4.1
title: Measure the unfilterable fraction
phase: A
status: done
gate: false
depends_on: [A1.4]
blocks: [A5.1, A6.1]
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.1 — Measure the unfilterable fraction

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Quantify what share of the corpus taxonomy has not labelled, and is therefore outside a
taxonomic filter's reach in principle.

## Steps

- Define 'unclassified' precisely against the corpus's own annotation fields.
- Measure the unclassified share of the relevant corpus components.
- Express the result as a ceiling on any taxonomy-based filter's achievable coverage.
- Separate 'unlabelled' from 'labelled but out of policy scope'.

## Done when

- Unclassified fraction measured per corpus component.
- Result framed as an in-principle ceiling, with the definition stated.
- Unlabelled vs out-of-scope distinction preserved.

## Outcome — 2026-10-15 — done

**Merged.** The work landed on `main` in **PR #14** (branch `ccr-f17b9af4-4rp5eq`, merged
2026-10-15). Nothing is left on a branch: look on `main`. Moved `review` → `done` on
2026-10-17 — all three Done-when criteria are discharged below, and this task carries no
A3.3 reproduction criterion, so no gate holds it.

**Branch:** `ccr-f17b9af4-4rp5eq`. `src/amazebio/unfilterable.py`, `tools/unfilterable.py` and
`tests/test_unfilterable.py`; artefacts `artifacts/a4-1/unfilterable.{json,md}` with `run.json`
pinning commit `5b10b6c`, a clean tree, 4 inputs, 2 outputs and boto3 1.43.111. Both IMG/VR
releases read in 85 s and 90 s, 64 byte shards each, **0 malformed rows** in either.

### The headline

**Taxonomy labels IMG/VR at realm and not at family, and the only rules that name a hazard are
keyed on family and order.** v4.1, all 15,677,623 records:

| rank | labelled | share |
|---|---|---|
| realm | 15,157,100 | 96.68% |
| class | 14,965,115 | 95.46% |
| **order** | 1,359,211 | **8.67%** |
| **family** | 979,864 | **6.25%** |
| genus | 32,729 | 0.21% |
| species | 6,630 | 0.04% |

516,046 records (3.29%) fill no rank at all. That number is *not* the finding, and reporting it
as one would have been the easy mistake: the component is well labelled, just not at the ranks
the filter's hazard list is written against.

So the ceiling. Evo's 19-family denylist can discriminate on **6.25%** of the release and its
12-order denylist on 8.67%. Measured over the population those rules are actually handed — after
the confidence gate, which runs first and keeps 5,576,197 records — it is **7.87%** and 8.85%.
Both are in the artefact, because the first is a fact about the database and the second about
the filter, and either alone invites the obvious objection without answering it (D-081).

The host rule is the other half of the picture. 7.18% of the release carries any host prediction
at all (13.71% after the gate), so "found within a prokaryotic host at least twice" is a
judgement the annotation supports on a seventh of the gated records — and it removes the rest
*for lacking the evidence*, which is a different thing from being unable to see them.

### Two shares, not one, and why

Evo's pipeline is mostly keep-listing, so absence of a label fires rules rather than blocking
them. Each rule therefore carries both (D-081):

| rule | reads | decidable | discriminating |
|---|---|---|---|
| `keep-high-confidence` | confidence | 100% | 100% |
| `keep-one-per-votu` | vOTU | 100% | 100% |
| `keep-prokaryotic-host-twice` | host prediction | 100% | 7.18% |
| `remove-denylisted-families` | family | 6.25% | **6.25%** |
| `remove-denylisted-orders` | order | 8.67% | 8.67% |
| `remove-taxonomically-unspecific` | realm, absent | 100% | 0% |

Reporting only the right-hand column would say the filter cannot touch 94% of the component. It
can, bluntly: the unspecificity rule removes 599,507 records (3.82%) for having no realm
(520,523) or terminating in one of its eight named stop taxa (78,984, led by Bamfordvirae at
45,403). That backstop ships beside the ceiling as a caveat, not a finding — what survived is
A3.2's question over a population this pass does not compute.

### The output is worse labelled than the input

| component | records | family labelled |
|---|---|---|
| IMG/VR v4.1, after the confidence gate | 5,576,197 | 7.87% |
| Evo 1's released viral component | 2,653,047 | **2.62%** |
| Evo 2's released viral component (recovered by join) | 2,917,521 | 7.02% |

Evo 1's release is a third as well labelled at family as the population it was selected from.
Nothing here says the filter caused that, and this task does not claim it: the direction is what
the rules predict — a prokaryotic-host keep-list retains shallowly-labelled Caudoviricetes — and
establishing it by route is A3.2's, not a sentence to write here.

### Three things worth a reviewer's attention

1. **The independent pass agrees with A7.2 to the record.** All eight ranks, the 15,677,623
   total, the confidence split and the host-domain tallies, from two unrelated implementations
   (D-082). The agreement is only available because the input was re-read from the publisher's
   own file rather than taken from A7.2's scan; the two *released* components are taken from
   A7.1's and A7.2's pinned scans, each verified to sum to that scan's own record total before a
   share is taken from it.
2. **A bug this pass found in itself.** The classification-method field was tallied over the
   whole table and reported beside the gated subset — 15,161,577 labelled methods in a
   population of 5,576,197. Fixed by cross-tabbing it like the others, and the invariant that
   catches the class of error (a fill must be measured over the population it is reported
   beside) is now checked and tested by injecting the bug that motivated it.
3. **The v4-to-v4.1 erratum moves classifications, not records.** Both releases hold exactly
   15,677,623 records; v4.1 reassigns 1,982 records at realm, 682 at class and 1,300 at family,
   moving the family ceiling from 6.24% to 6.25%. D-063 called the erratum "a few
   sequences/rows"; it is a few, and the ceiling is robust to it.

One internal consistency check fell out and holds in both populations: the
`Taxonomic classification method` field is empty on exactly the records that fill no rank —
516,046 of the release, 19,098 of the gated subset.

### Done-when

- *Unclassified fraction measured per corpus component.* Both IMG/VR releases, each over two
  populations, from the primary tables; both released viral components, from pinned scans. Every
  other component each reading declares a view on carries a row with no fill and the reason.
- *Result framed as an in-principle ceiling, with the definition stated.* The artefact opens with
  the definition block — labelled-at-rank, unclassified, absent-field and ceiling — and the
  ceiling table names the binding rule and rank per reading.
- *Unlabelled vs out-of-scope distinction preserved.* Four states that may never be summed:
  `unlabelled`, `not_annotated` (Evo 2's release carries no lineage field and every accession
  resolves in IMG/VR — unannotated, not unclassified), `out_of_policy_scope` (A4.3 owns those
  shares) and `not_taxonomy_dependent` (ESM3-open's rule reads a similarity threshold, so no
  taxonomic ceiling binds it). The caveat block states it in machine-readable form.

**Not done, deliberately:** the three readings are indistinguishable here, as they were in A1.4
and A7.1 — every rule they differ over reads host evidence or record attributes, and the ceiling
is set by the family denylist all three share. A0.4 reports the spread; on this component it is
zero again, for the reason D-072 gives.

**Waiting on the project owner:** nothing.

**For whoever picks up A5.1 or A6.1:** the ceiling is the number to quote, and it must travel
with its population — 6.25% of the release, 7.87% of what the denylist sees. The artefact refuses
to hand over either without its caveat block.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

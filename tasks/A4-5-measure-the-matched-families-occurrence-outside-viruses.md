---
id: A4.5
title: Measure the matched families' occurrence outside viruses
phase: A
status: done
gate: false
depends_on: [A2.1]
blocks: []
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.5 — Measure the matched families' occurrence outside viruses

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Every Pfam survival figure in Phase A counts **families**. A family is detected when one of the
1,719 pre-registered profiles matches a record in the surviving corpus, and that supports the
sentence *a member of this protein family is present*. It does not support *viral material is
present*, because nothing in the search asks whether the family occurs only in viruses. The
selection rule (D-075) is a statement about what a family is **named for**, not a measurement
of where its members live.

This task measures where they live. For each family in the pinned universe: how many entries of
the curated section of UniProtKB carry it, split by whether the entry's own organism lineage is
viral. The result says how far the claim can move from the first sentence towards the second —
or shows that it cannot, and why.

A negative or mixed result is a result. The honest outcome may be that the claim cannot move,
in which case the limit is published as a measured one rather than an asserted one.

## Steps

1. Reproduce the 1,719-family universe from the Pfam 38.2 pin. Do not redefine the set: it was
   fixed before anything was searched and the survival denominators depend on it.
2. Pin the background: the curated (reviewed) section of UniProtKB at a stated release, by the
   publisher's own digest, with the release's published entry total as a truncation guard.
3. Instrument 1 — one forward pass over the flat file, reading the publisher's own `DR Pfam`
   cross-references and each entry's own lineage.
4. Instrument 2 — the same join performed by InterPro's API over its own index, per family,
   for every family rather than a sample. Report the two side by side; never merge them.
5. Classify each family `viral_only`, `shared` or `unmeasurable`, with `unmeasurable` taking
   precedence so that an absence of curation can never read as evidence for the claim.
6. Report the detected sets against that background: for each release, how many of its detected
   families are `shared`. This step needs the per-family detection lists from A2.1/A3.2.

   **The cut is fixed here, before the restricted counts exist.** The write-up wants a
   conservative variant of the headline beside the headline, and a cut chosen after seeing
   which one reads better is not a measurement. So:

   | variant | families counted |
   |---|---|
   | `headline` | every detected family — unchanged, as published |
   | `specific` | detected families classed `viral_only` |
   | `specific_plus_endogenous` | `viral_only`, plus `shared` families whose every non-viral occurrence the curators themselves mark as integrated viral material |

   Each variant is reported twice, once excluding `unmeasurable` families and once including
   them, because an unmeasured family belongs to neither side and a single number would have to
   pretend otherwise. The pair is the result; neither end of it is the result on its own.

   Both sides of every such comparison must be the same detector at the same depth over the
   same corpus. `tools/quantify_survival.py` is the thing to extend rather than reimplement:
   band parts name their tables by policy and registry and never by release (D-245), and a
   task prefix holds commit-keyed provenance twins beside the live tables (D-246). A subset
   assembled by hand gets both wrong.
7. Ship the per-family table as a committed artefact, with a run manifest.

## Done when

- The universe is reproduced from the pin and counted: 1,719 families, matching A2.1.
- The background release is verified against the publisher's digest **and** the pass's own entry
  count matches the release's published total, with a refusal rather than a figure on mismatch.
- Every family carries a count from both instruments, and the number of class disagreements
  between them is reported rather than resolved silently.
- The three classes partition the universe, and `unmeasurable` is reported as its own number
  rather than folded into either of the others.
- The artefact states, in the artefact itself, that no survival figure is corrected by anything
  in it, and that a non-viral occurrence is not proof of independent cellular ancestry.
- The detected-set restriction is either computed from the A2.1 detection lists, or recorded as
  outstanding with the bound that is computable without them.

## Result

Both halves done. The universe measurement is D-250; the detected-set restriction is D-251.
Of 1,719 families, 1,265 have no curated occurrence outside viruses, 212 do and 242 cannot be
judged, so 85.6% of the 1,477 judgeable are virus-only, and both instruments agree on all
1,719. Restricted to what was detected, the sharing rate is 30.3% of judgeable families on
Evo 1 and 22.6% on Evo 2 — 2.11 and 1.57 times the universe rate, which is the bias this step
existed to measure and it runs against the claim rather than for it. The `specific` variant of
the merged headline is 310–462 of 597 and 498–667 of 812.

The restriction was recorded as blocked on object storage for a day. It was not: the denial was
a client resolving to S3's legacy global hostname rather than an IAM grant. See D-251 and the
docstring on `amazebio.objectstore.client`.

## Notes

**What this task may not do.** It may not produce a corrected survival figure. The headline
counts stay as published; what changes is which sentence they support. D-158 drew the same line
for A1.6's exposure measurement and the reason is the same — a bound on exposure is not a
correction, and publishing one as the other would be the error the bound exists to prevent.

**Why two instruments.** D-245, D-246 and D-247 were all one table whose halves described
different things, and in each case the single instrument agreed with itself. A second join,
written by someone else over a different index, is the cheapest available check that the parse
means what it is taken to mean.

**The version skew is a measured class, not an assumption.** The universe is Pfam 38.2; the
background's cross-references were computed by the publisher against whatever Pfam release that
UniProtKB release was built on. A family held by 38.2 and not by that release would show no
occurrences and read as viral-only — an error in the direction that flatters the claim. Hence
`unmeasurable`, and hence its size is reported as the instrument's coverage of the universe.

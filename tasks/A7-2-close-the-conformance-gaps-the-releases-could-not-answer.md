---
id: A7.2
title: Close the conformance gaps the releases could not answer
phase: A
status: ready
gate: false
depends_on: [A1.7]
blocks: []
design_ref: "§A7"
deliverable: 1
owner: unassigned
---

# A7.2 — Close the conformance gaps the releases could not answer

**Design reference:** DESIGN.md §A7 · **Deliverable 1**

## Goal

Finish the conformance re-execution with the filter's **input** in hand. A7.1 ran the forward
direction against Evo 1's released output and could reach three of six published rules; this task
takes the other three, the converse direction, and Evo 2's release, all of which were blocked on
one missing artefact.

## Why this is a separate task

A7.1 shipped one-directional and sits at `review`. Everything below needs IMG/VR v4, which was
not acquired when A7.1 ran — `policies/corpora.md` §2 said it was independently available, which
was true and not the same as acquired (D-049). Reopening A7.1 to absorb this would be the
scope-widening AGENTS.md forbids, so the gaps live here instead of in a review note nobody owns.

`depends_on` names **A1.7 only**, deliberately. A7.2 also builds on A7.1's machinery —
`amazebio.conformance`, the restriction mechanism, the frozen cause taxonomy — and that code is
written and tested. What holds A7.1 at `review` is its independent reproduction via the A3.3
gate, which has nothing to do with this task, so depending on A7.1's *status* would block A7.2 on
something unrelated to whether it can start. It can start the moment A1.7 lands.

## The five gaps, and what closing each one requires

1. **The high-confidence gate** (`keep_if_attribute_in`, `confidence`). Needs the per-record
   confidence label from IMG/VR. Closes fully: it becomes a record-level diff like the taxonomy
   rules.
2. **The prokaryotic-host count** (`keep_if_host_occurrence_at_least`, 2). Needs the host
   assignment per record, counted per taxonomic classification rather than per record — the rule
   is about how often a *classification* was seen in a prokaryotic host, so the count is built
   over the database and then joined back. Closes fully, and getting the unit wrong here is the
   obvious way to produce a confident wrong number.

   **D-058 settles the unit and supplies a target.** Evo 1's own Figure S1B puts 2,374,733 of
   2,653,046 retained records — 89.5% — at host kingdom *Unknown*, with no Eukaryota category
   at all. A per-record reading of the rule cannot produce that; the classification-level
   reading does. So aggregate over classifications and join back, and treat it as a check
   rather than a choice: a re-execution that does not land near **2,374,733 retained records
   with no host kingdom** has the unit wrong, whatever else it reproduces.
3. **The vOTU representative** (`keep_one_per`, vOTU). **Does not fully close, ever.** The rule is
   order-dependent and no input order is published (D-017, carried into D-049), so which record
   survives a vOTU is undetermined. Compare at **vOTU level** — did each vOTU contribute exactly
   one surviving record — not at record level, or the diff measures our sort order.
   `amazebio.conformance.diff` already refuses an order-dependent rule rather than reporting the
   zero removals that would read as conformance, so this needs a separate vOTU-level comparison
   path and not a loosening of that guard.
4. **The converse direction.** Records the filter *removed* that the published predicate does not
   call for. An over-broad filter is as much a mismatch between rule and practice as a leaky one,
   and §A7 asks for both. This is the arm that needs the input most directly: it is a set
   difference between the predicate's survivors over IMG/VR v4 and the records actually released.
5. **Evo 2's conformance arm.** Its released IMG/VR FASTA carries `IMGVR_UViG_<taxon_oid>_<n>`
   accessions and no lineage, so no published rule could be re-executed against it at all. With
   the input in hand the accessions become a join key and both directions open. The audited
   *procedure* is Evo 1's while this audited *output* is Evo 2's — state that plainly, and do not
   write "OpenGenome" as though the two releases were one artefact (D-019).

## Steps

- Extend `RELEASE_INPUTS` with IMG/VR v4's own inventory, and let `restrict` do the rest. The
  coverage number should move from `3/6` to `5/6` at record level because the declaration
  changed, not because any rule was hand-picked back in (D-047).
- Build the host-occurrence counts over the database per taxonomic classification, and record the
  unit explicitly in the artefact. Rule 2 above is where a plausible-looking wrong denominator
  gets in.
- Add the vOTU-level comparison as its own path, with its own reported unit. Never report it as a
  record-level conformance rate.
- Run the converse diff and report it separately from the forward one. A single combined
  "mismatch rate" would hide which direction the filter errs in, which is the interesting part.
- Re-run the three readings now that they are distinguishable, and report the spread §A7 asks for.
  This is the first point at which that number exists; A7.1 could only establish that it was
  unmeasurable against the release.
- Carry A1.1's verdict into every claim, and A1.7's own proxy-or-not verdict for the input side.
  A conformance claim is only as strong as the weaker of its two ends.
- Keep the forward numbers A7.1 published reproducible and unchanged. If adding the input moves
  the 95 or the zero, that is a finding about one of the two runs and needs explaining, not
  quietly superseding.

## Done when

- Conformance diff computed per model × reading × direction, reproducible from pinned inputs,
  with coverage stated per count.
- The reading spread is reported, per model, as a number rather than as "unmeasurable".
- The vOTU rule is compared at vOTU level, with its unit named in the artefact and the write-up.
- The converse direction is reported separately from the forward direction.
- Evo 2's arm is run, with the procedure/output provenance split stated plainly.
- A7.1's forward numbers either reproduce unchanged or the difference is explained.
- Causes are assigned from the frozen taxonomy; any new cause is added before counting, not after.
- Headline numbers independently reproduced via A3.3 before any external circulation.

## What this task is not

- **Not a revision of A7.1's spec encodings.** Fitting a predicate to the data it audits is the
  one move a conformance audit may not make (D-051). If a rule looks wrong, that is a finding.
- **Not ESM3.** There is no conformance arm for ESM3-open at all: neither corpus nor threshold is
  published, and the 10.6M removal count is the only published quantity a reconstruction can be
  checked against. That belongs to A1.6, not here.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

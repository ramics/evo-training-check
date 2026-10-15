---
id: A7.2
title: Close the conformance gaps the releases could not answer
phase: A
status: review
gate: false
depends_on: [A1.7]
blocks: []
design_ref: "§A7"
deliverable: 1
owner: claude
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

## State — 2026-10-15

`review`. Work branch: **`claude/kind-brown-78c2qq`** (not `claude/kind-wozniak-ec94y4`, which
this file named when the task was claimed — that branch was A1.7's and A7.2's work never went
there). Every Done-when criterion is met except the last, which is the A3.3 gate: the headline
numbers need a second method before any external circulation, exactly as A7.1 is held.

**All five gaps are closed, and one of them closed the other way up.**

**Coverage.** Record-level coverage moves from A7.1's `3/6` to **`5/6`**, and `6/6` counting the
vOTU rule at its own unit. The declaration changed — `RELEASE_INPUTS` gained the input's own
inventory — and `restrict` did the rest; no rule was hand-picked back in (D-047).

**Evo 1 conforms to its own published procedure, to 95 records in 2.65 million.** Re-executed
over IMG/VR v4.1, the procedure retains **2,651,599 to 2,653,756** records — an interval, not a
point, because the vOTU representative depends on an input order nobody published (D-067).
Evo 1's own Table S3 figure of **2,653,046 is inside it**, which confirms the prediction A1.7
recorded as falsifiable (D-064). The converse direction is **empty**: not one record the rule
retains is missing from the release. The forward direction is **95 records**, all failing the
unspecificity rule, in three families assigned at family rank with no realm — the identical 95
A7.1 found from the release alone, now reproduced from the opposite direction.

**Which IMG/VR release Evo 1 used is now determined, from its own corpus** (D-071). A1.7 recorded
that Evo 1's citation does not say and staged both. Re-executed over v4.1 the procedure predicts
survivors in exactly the 181 lineages the release carries; over v4 it predicts 43 records in two
lineages the release carries none of, because v4 puts eighteen taxon names in the wrong rank field
and v4.1's erratum corrects exactly those. So the input is **v4.1 (2022-12-20)**. Note the
direction this cuts: under v4, 43 of A7.1's 95 would have been explained away as an
input-versus-output taxonomy mismatch; under the release the evidence identifies, all 95 stand.

**Evo 2's released viral component is the output of the procedure's first two steps and not of
its last four.** 2,917,521 distinct accessions — exactly the number of distinct high-confidence
vOTUs in IMG/VR v4 — every one of which joins to the input. **264,570 of them are records the
published procedure removes**: 217,078 by the prokaryotic-host rule, 23,523 taxonomically
unspecific, 21,867 from denylisted orders, and **2,102 from the 19 denylisted families**. The
procedure is Evo 1's, adopted by reference in Evo 2 ("As previously described"); the output is Evo
2's own (D-019). No intent is claimed — what is claimed is the arithmetic.

**The vOTU rule conforms exactly, at vOTU level.** Every one of 2,651,376 predicted-surviving
vOTUs contributed exactly one released record to Evo 2's release; none contributed two, none
contributed none. Reported at vOTU level with the unit printed beside every number, never as a
record-level rate (D-067). Separately, the released FASTA carries 2,957,495 sequence records under
2,917,521 distinct accessions — 39,974 accessions appear more than once, which the header cannot
explain and which is reported beside the comparison rather than inside it.

**The reading spread is a number for the first time, and the number is zero** (D-072). A7.1 could
only report it unmeasurable, because every rule the readings differ over reads host occurrences
the release withholds. Measured, it is zero on every quantity — and the cause is in the data:
**IMG/VR v4 asserts no eukaryotic host for any of its 15,677,623 records**, across all four
prediction methods and all 18,859 distinct host taxa. A filter whose stated aim is excluding
eukaryote-infecting viruses is implemented against a field that never names a eukaryote, which is
why the published procedure reaches that aim through a prokaryotic-host count and a clade
enumeration instead. A0.4 should read D-072 before reporting the Evo spread.

**Against the Done-when list:**

- *Conformance diff per model × reading × direction, reproducible from pinned inputs, coverage per
  count* — yes. `artifacts/a7-2/{2022-09-20,2022-12-20}/close-*.{json,md}`, recomputed in a second
  from the two reduced artefacts, with coverage beside every count.
- *The reading spread as a number* — yes, zero, with its cause measured and reported beside it.
- *The vOTU rule compared at vOTU level, unit named* — yes, in the artefact and the write-up.
- *Converse reported separately from forward* — yes, never summed, and forward is itself split by
  which rule the excess belongs to (D-069).
- *Evo 2's arm run, provenance split stated* — yes.
- *A7.1's forward numbers reproduce or the difference is explained* — reproduce **unchanged**: 95.
- *Causes from the frozen taxonomy, nothing added after counting* — yes; `annotation_missing`
  accounts for all 95 and `unexplained` for the bulk of Evo 2's.
- *Headline numbers independently reproduced via A3.3* — **outstanding.** This is the only open
  criterion and it is the A3.3 gate, not work inside this task.

**What is waiting on the project owner:** nothing to unblock this task. Two things worth a
decision elsewhere: whether D-071's identification of v4.1 should be carried back into
`policies/corpora.md`, which still records the release as ambiguous; and whether Evo 2's 264,570
figure is a Phase A headline in its own right or belongs inside A6.1's write-up.

**Reproducing it** (about 20 minutes end to end, all in the session container — the EC2 test was
applied and declined, D-070):

```bash
python3 tools/evo2_accessions.py --upload-results                  # 18 min, one gzip stream
python3 tools/imgvr_conformance_scan.py --release 2022-12-20 --workers 12 \
    --evo2-accessions artifacts/a7-2/evo2/evo2-imgvr-accessions.npy --upload-results
python3 tools/conformance_close.py \
    --release-scan s3://$BUCKET/corpora/results/a7-1/scan-opengenome-stage2.json
```

**For the reviewer:** the arithmetic is in `src/amazebio/conformance.py` (the restriction's third
category, the host units, the vOTU bounds) and `src/amazebio/imgvr.py` (the two accession shapes,
the host vocabulary); the passes are the three tools above; the tests are
`tests/test_conformance_close.py`, which runs both passes over a synthetic release whose expected
counts are worked out from the fixture rather than recorded from a run, plus
`tests/test_objectstore.py`, which pins the one property every sharded count rests on. Two bugs
were caught there rather than in review: a shard starting exactly on a line boundary dropped that
line, and the vOTU histogram was keyed by a per-pass index while the diff joined it by
classification string. Neither would have raised.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

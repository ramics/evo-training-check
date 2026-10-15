---
id: A1.4
title: Apply policy predicates to produce surviving corpora
phase: A
status: review
gate: false
depends_on: [A0.3, A1.2, A1.3, A1.5]
blocks: [A1.6, A2.1, A2.2, A2.3, A2.4, A2.5, A4.1, A4.2, A5.1, B3.1, B3.2, B3.3]
design_ref: "§A1, §A2"
deliverable: 1
owner: claude
---

# A1.4 — Apply policy predicates to produce surviving corpora

**Design reference:** DESIGN.md §A1, §A2 · **Deliverable 1**

## Goal

Run each of the three readings against each staged corpus to produce the concrete surviving-
record sets that Phase A measures and Phase B scores against.

## Steps

- Implement predicate evaluation over corpus records at scale.
- Produce, per model × reading, a surviving-record manifest with stable IDs.
- Verify counts are internally consistent and reproducible from pinned inputs.
- Expose the manifests as the single shared input for A2.* and B3.*.
- Wrap the run in `amazebio.repro.run`, declaring every parameter before results
  exist, so this pipeline is the first to enforce the X1.1 seed and provenance
  convention end to end (see DECISIONS.md D-003).

## Done when

- Nine-ish (model × reading) manifests exist, reproducible from pinned inputs and seeds.
- Manifest format is documented and consumed by at least one A2 task.
- Record counts reconcile against A1.2/A1.3 composition tables.
- A `run.json` manifest is produced, pinning inputs, outputs, parameters and seed.

## Outcome — 2026-10-15 — review

**Branch:** `ccr-6ecfc2c1-668gtb`. Project management on `main` as usual.

**Seven manifests**, one per model x reading x release, in `artifacts/a1-4/`, with
`run.json` pinning seed 20261015, commit `609075e`, a clean tree, 8 inputs and 11 outputs. The
format is specified in `metrics/manifests.md`. The ESM3 similarity readings are A1.6 (D-043).

### The headline

| reading | release | records | removed | unresolved |
|---|---|---|---|---|
| evo1-literal | opengenome | 2,653,047 | **95** | 2,652,952 |
| evo1-charitable | opengenome | 2,653,047 | **95** | 2,652,952 |
| evo1-strict | opengenome | 2,653,047 | **95** | 2,652,952 |
| evo1-literal / charitable / strict | opengenome2 | 2,957,495 | 0 | 2,957,495 |
| esm3-open-literal | esm3-proxy | not enumerated | — | all four components `undetermined` |

**The independent cross-check holds exactly.** A7.1 censused Evo 1's release with its own
implementation and found 95 records carrying no assigned realm (D-051). A1.4, written from the
specs with a different mechanism — per-record evidence declarations and a precedence lattice
rather than a restricted pipeline — removes the same 95, all attributed to
`remove-taxonomically-unspecific`, all for `no realm assigned`, and counts the same 2,653,047
records. Two implementations, one number.

**The three readings are indistinguishable on both releases**, and the removed record sets are
identical. §A0 requires the spread between readings to be reported as a finding; on these
releases it is unmeasurable, because every rule the readings differ over reads host evidence or
record attributes and neither release carries either. A7.1 asserted this from the specs
(`readings_agree_by_construction`); this is the same result measured over the corpus.

**Where the readings do differ is scope, and it is now measured.** On Evo 2's release the literal
and charitable readings put nine components `out_of_scope` while the strict reading's wildcard
scope marks the same nine `retained` — examined, nothing removed. Those nine include the 2.17 TB
of eukaryotic genomes that are 82% of that corpus and have no viral screening step in their
published curation. A4.3 inherits the figures.

**Evo 2's release decides nothing at all.** 2,957,495 records, every one `unresolved`: it carries
an IMG/VR accession and no lineage, so none of the six published rules can run. Written up as
`policies/evo.md` §9, which settles §8's four-file sample as a census — zero tags in 2,957,495
records, zero parse failures.

### Done-when

- *Manifests exist, reproducible from pinned inputs and seeds.* Seven, with `run.json`. The two
  that are not here are named in D-043 and are A1.6's.
- *Manifest format documented.* `metrics/manifests.md`. The "consumed by at least one A2 task"
  half moved to A2.1 under D-059, for the reason D-042 moved A3.1's: every A2 task depends on
  this one, so the criterion made the task that unblocks them wait on them.
- *Record counts reconcile.* Bytes: 12 staged objects, 144,132,509,090 bytes = 134.23 GiB,
  matching A1.2's outcome note exactly, and every object's length re-checked against its pin
  before reading. Records: 2,653,047 for Evo 1's viral component, matching A7.1's independent
  census; 2,957,495 for Evo 2's, counted here first. A1.2's composition table is file- and
  byte-level, so record counts reconcile against A7.1 rather than against it, and the components
  this task did not enumerate carry `records: null` with the reason rather than an estimate.
- *A `run.json` manifest pinning inputs, outputs, parameters and seed.* Yes, and it refuses a
  dirty tree — the first pipeline to enforce the X1.1 convention end to end, which was this
  task's own step (D-003).

### Two things found along the way, both fixed

- **The staged inventory was incomplete.** Evo 1 publishes stage 2 as three splits and
  `corpora.SOURCES` declared two. The run would have completed, every internal reconciliation
  would have agreed with itself, and the manifests would have under-counted the filter's own
  output with nothing downstream able to notice. The pipeline now lists both release prefixes and
  refuses to start on any staged object no entry accounts for.
- **The ranged reader could not survive the pass.** A 28 GB read died on a botocore
  `IncompleteRead` partway through the Parquet. It now resumes from the break rather than
  refetching the window, and reports reconnects with their offset.

### For whoever picks up the next thing

- **A1.6** writes to this format; `metrics/manifests.md` already says what an `unresolved` row
  must carry for an alignment result that does not exist yet.
- **A2.1** is the first consumer and owns the format check (D-059).
- **A7.2** extends the release inventory with IMG/VR v4. The cross-check test in
  `tests/test_apply.py` will fail if the matching `Evidence` declaration in `corpora.SOURCES` is
  not extended with it. That is intended: D-057 unified the rule-input table and left the
  release inventory in two granularities with a test pinning their agreement.
- **One piece of layering is untidy on purpose** and is recorded in D-057: `corpora` imports the
  released-format primitives from `conformance`, inverting the natural direction, because moving
  them would have churned a module at `review`. Whoever closes A7.1's review should move them.

**Waiting on the project owner:** nothing.

## Closing it out — 2026-10-15, second session

`review` still. **The work was never merged.** `main` carried this task at `review` while
`src/amazebio/{apply,corpora}.py`, `tools/apply_policies.py`, `metrics/manifests.md` and both
test files existed only on `ccr-6ecfc2c1-668gtb` — the split AGENTS.md warns about, and already
biting: A2.1's file and D-059 on `main` both cite `amazebio.apply.route_for`, which `main` has no
such module for.

**Merged onto current `main` and pushed: `claude/kind-brown-78c2qq`** (commit `e21c1a1`). It
merged with no conflicts even though A7.2 had since rewritten parts of `conformance.py`, and the
shared tables survived intact — `conformance.RULE_INPUTS is policyspec.RULE_INPUTS` still holds
and every rule kind is still declared. `pixi run -e dev check` is green on the merge: lint,
format, board, policies, specs, models, and **499 tests**.

**One claim in the outcome note above is wrong, and it matters.** It says the cross-check in
`tests/test_apply.py` "will fail if the matching `Evidence` declaration in `corpora.SOURCES` is
not extended" when A7.2 adds IMG/VR to the release inventory. A7.2 added two keys —
`imgvr-v4` and `imgvr-v4.1` — and the test did not fail, because
`test_the_two_release_declarations_agree_on_what_can_be_re_executed` never enumerates
`RELEASE_INPUTS`: it hard-codes the two sources it knows and checks those. It catches *drift* in
the pair it names and is blind to an *addition*. So the tripwire D-057 relied on does not cover
the case it was written for.

**The fix is designed and not yet written.** Enumerate `conformance.RELEASE_INPUTS` and require
every key to be accounted for on both sides, using the distinction A7.2 already introduced:
a key in `conformance.COMPARISON_KEYS` is a developer's released output, so it must have exactly
one `corpora.SOURCES` entry (joined mechanically — the keys are `f"{release}-{corpus_component}"`,
which holds for both: `opengenome-stage2`, `opengenome2-imgvr`) and the kept-rule sets must agree
for every Evo reading; a key absent from `COMPARISON_KEYS` is the filter's *input* and must have
no such entry. That makes the two IMG/VR keys explicitly accounted for rather than silently
tolerated, and it is what would have fired. Keep the existing explicit Evo-2 assertion — that
`restrict` raises rather than returning an empty pipeline — as its own test; it is a distinct
claim.

**The remaining `done` criterion is regeneration.** Everything else on the Done-when list is
satisfied (the manifest-consumption half having moved to A2.1 under D-059). `artifacts/` is
git-ignored and the container is ephemeral, so the headline numbers have to be reproduced on the
current merge before this goes to `done`:

```bash
export AMAZEBIO_S3_URI=s3://amazebio-corpora-897641797669/corpora
python3 tools/apply_policies.py --dry-run   # plan only; confirms the inventory check
python3 tools/apply_policies.py             # ~25-30 min: 28 GB Parquet, then one gzip stream
```

A run was launched in this session and did not finish before it ended; the dry run passed and the
inventory check reported "12 staged objects, all declared", and the pass was mid-way through
`opengenome/stage2` when the session closed. Nothing was learned from it that contradicts the
numbers above — it simply has to be re-run. What must reproduce: **2,653,047** records and
**95** removed for each of the three Evo 1 readings on `opengenome`, **2,957,495** records all
`unresolved` on `opengenome2`, and seven manifests with a `run.json` refusing a dirty tree.

**Deliberately not done, to avoid widening this task:** D-057's untidy layering — `corpora`
importing the released-format primitives from `conformance`, which inverts the natural direction
— is still there. That note assigns it to whoever closes A7.1's review, and A7.1 is still held at
`review` by the A3.3 gate, so it stays assigned there.

**Order for the next session:** push the merge to `main` (it is green and it unbreaks two
dangling references), write the enumerating tripwire, re-run the pipeline, check the three
numbers, then flip `status: done` on `main` with the board regenerated. The tripwire fix wants a
`DECISIONS.md` entry recording that D-057's guard did not cover additions; **D-074** is the next
free number, but re-check before pushing, per AGENTS.md.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A1.4
title: Apply policy predicates to produce surviving corpora
phase: A
status: done
gate: false
depends_on: [A0.3, A1.2, A1.3, A1.5]
blocks: [A1.6, A1.8, A2.1, A2.2, A2.3, A2.4, A2.5, B3.1, B3.2, B3.3, A4.1, A4.2, A5.1, A7.4]
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

**Every Done-when criterion is now demonstrably met and the results regenerate.** Two things had
to happen first, and neither was in the original list.

**The work was never merged.** `main` carried this task at `review` while
`src/amazebio/{apply,corpora}.py`, `tools/apply_policies.py`, `metrics/manifests.md` and both
test files existed only on `ccr-6ecfc2c1-668gtb` — the split AGENTS.md warns about, and already
biting: A2.1's file and D-059 on `main` both cite `amazebio.apply.route_for`, which `main` had no
such module for. Merged onto current `main` as **`claude/kind-brown-78c2qq`**, with no conflicts
despite A7.2 having rewritten parts of `conformance.py` in between; the shared tables survived
(`conformance.RULE_INPUTS is policyspec.RULE_INPUTS` still holds, every rule kind still
declared). `pixi run -e dev check` green at **502 tests**.

**One claim in the outcome note above was false, and it was the note a later worker would have
trusted** (D-074). It says the cross-check in `tests/test_apply.py` "will fail if the matching
`Evidence` declaration in `corpora.SOURCES` is not extended" when A7.2 adds IMG/VR to the release
inventory. A7.2 added `imgvr-v4` and `imgvr-v4.1` and nothing failed: the test named the two
releases it knew instead of enumerating `RELEASE_INPUTS`, so it caught drift in that pair and was
structurally blind to an addition. Fixed two ways — `conformance.INPUT_RELEASES` classifies every
entry as the filter's input or a released output, declared rather than inferred from a missing
comparison key, because inferring from an absence is what let this through; and the agreement
check now drives off the inventory itself, joining to a staged source mechanically by
`f"{release}-{corpus_component}"`. **Confirmed to fire rather than assumed to**: three failure
modes injected, three fired naming the culprit, where the old guard was silent on all three.

### The regeneration

`tools/apply_policies.py`, 45 minutes in the session container, from a clean tree at commit
`e21c1a1`, seed `20261015`, 8 inputs and 11 outputs. Seven manifests, `index.json` and
`run.json` in `artifacts/a1-4/`. Every number the outcome note above recorded reproduces:

| reading | release | records | removed | unresolved |
|---|---|---|---|---|
| evo1-literal / charitable / strict | opengenome | 2,653,047 | **95** | 2,652,952 |
| evo1-literal / charitable / strict | opengenome2 | 2,957,495 | 0 | 2,957,495 |
| esm3-open-literal | esm3-proxy | not enumerated | — | all four components `undetermined` |

Checked as literals rather than read off the output, and the integrity fields checked with them:

- **2,652,947 + 50 + 50 = 2,653,047** across stage 2's three splits, and that total matches
  A7.1's independent census of the same component exactly.
- **All 95 removals** are in `train_stage2`, all attributed to `remove-taxonomically-unspecific`,
  all for `no realm assigned`, and the removed *sets* are identical across the three readings —
  not merely the counts.
- **Zero parse failures and zero evidence contradictions** on all three splits, with
  `one_row_one_record` true on each: the premise every count rests on, re-measured on this pass
  rather than inherited (D-048).
- Everything else on Evo 1's release is `unresolved|keep-high-confidence` — the release cannot
  decide the pipeline's *first* rule, which is A7.1's finding reached from the other direction.
- ESM3-open's four components are each uniform `undetermined`, both rules undecidable for
  `source does not state identity_threshold`. Nothing about that reading is determinable from
  the published words, which is the result rather than a gap in the run.

**Three independent measurements now agree on 95**: A7.1's census of the release, A1.4's
per-record evidence lattice, and A7.2's re-execution from the input side. One caveat on the
third, stated because it would otherwise look like a stronger check than it is: Evo 1's release
carries no accession, so A1.4's record ids are positional (`stage2:<object>#<row>`) and cannot be
joined to A7.2's family breakdown of the same 95 (73 Bicaudaviridae, 21 Fuselloviridae, 1
Ovaliviridae). The counts and the attributed rule agree; a record-level identity check between
the two would need a targeted re-read of 95 row positions, and it belongs to **A3.3**, which
owns cross-method checking.

### Done-when, closed

- *Manifests, reproducible from pinned inputs and seeds* — seven, regenerated above, with
  `run.json` from a clean tree. The two that are not here are A1.6's (D-043).
- *Format documented* — `metrics/manifests.md`. The consumption half is A2.1's (D-059).
- *Record counts reconcile* — against A1.2 on bytes and against A7.1 on records, both exact.
- *`run.json` pinning inputs, outputs, parameters and seed* — yes, and it refused a dirty tree
  throughout; this task was the first pipeline to enforce the X1.1 convention end to end (D-003).

**Deliberately not done, to avoid widening a finished task:** D-057's inverted layering —
`corpora` importing the released-format primitives from `conformance` — is still there. That
note assigns it to whoever closes A7.1's review, and A7.1 is still held by the A3.3 gate, so it
stays assigned there. D-074 records why the right fix (one declaration instead of two) was
declined again, now with the cost measured rather than estimated.

**`done`.** PR #13 merged, so `src/amazebio/{apply,corpora}.py`, `tools/apply_policies.py`,
`metrics/manifests.md` and both test suites are on `main` and the two dangling references are
live: `amazebio.apply.route_for`, cited by A2.1's file and by D-059, now resolves. Nothing is
outstanding and nothing is left on a branch.

**What this unblocks:** eight tasks move from `blocked` to `ready` — A1.6, all five A2
detectors, A4.1 and A4.2. A5.1 and B3.1 through B3.3 also name A1.4 but have other blockers
still. A2.1 is the first consumer and owns the manifest-format check that moved to it under
D-059.

**And it identifies the real bottleneck, which is not what it looked like.** A3.2 does not
become ready: it depends on A3.1 — done — *and on all five A2 detectors*. So the path to the
A3.3 gate, which holds A7.1, A7.2 and the Phase A write-up, runs
A2.1–A2.5 → A3.2 → A3.3, and every one of those five has to land before A3.2 can start. They
are independent of each other and all five are ready now, so they are the one place in Phase A
where parallel tracks buy anything. Nothing closer to the gate can be worked on first.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

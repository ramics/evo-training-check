# Surviving-corpus manifests — the shared input contract

Task A1.4 · DESIGN.md §A1, §A2 · Deliverable 1

This is a data contract, not a metric. `metrics/survival.md` defines what the headline numbers
mean; this file defines the artefact those numbers are computed from, so that A2.\*, A4.\*, B3.\*
and A7.1 all read one shape. Written to be usable without reading
`src/amazebio/apply.py` — the independent reimplementation in A3.3 works from specifications,
not from our code.

Produced by `tools/apply_policies.py`. One manifest per **model x reading x release**.

## Why there is one per release and they are never merged

Evo 1's exclusion procedure is inherited unchanged by Evo 2 — the Evo 2 preprint says "As
previously described" and restates nothing — so each reading applies to both releases. The two
releases carry **different metadata**, so the same reading reaches a different verdict on each.
That difference is a finding and must not be averaged away:

| | record identifier | taxonomic lineage | IMG/VR metadata |
|---|---|---|---|
| Evo 1 `stage2` (Parquet) | none | **inline, 8 ranks, every record** | none |
| Evo 2 `imgvr` (FASTA) | **IMG/VR accession** | none | none |

Neither release carries the high-confidence flag, the vOTU, or the prokaryotic-host count that
three of the filter's six published rules read.

## Files

```
artifacts/a1-4/
  index.json                              every manifest produced, with its totals
  manifest-<policy-id>-<release>.json      the summary — read by a person
  removed-<policy-id>-<release>.jsonl      the removed set — read by a pipeline, one JSON per line
  run.json                                 provenance: seed, parameters, inputs, outputs, commit
```

The removed set is absent when a reading removes nothing. That is a result, not a missing file.

### `index.json`

The list a consumer reads first. `manifests[]`, one entry per manifest produced:

| field | meaning |
|---|---|
| `policy`, `release` | which model x reading x release the entry is for |
| `manifest` | the manifest's filename, relative to this directory — **`manifest`, not `file`** |
| `totals` | the same outcome counts as the manifest's own `totals` |
| `removed_records` | records the reading removes, so a consumer can size the removed set before opening it |

A2.1 read `file` first and failed on every entry, which is the right failure: a consumer of
another task's artefact should stop on a shape it does not know rather than skip entries it
cannot parse.

## Outcomes

Every record resolves to exactly one of five outcomes. The first four come from
`amazebio.policyspec.Outcome`; the fifth is the scope verdict.

| outcome | means | survival route |
|---|---|---|
| `removed` | A rule this reading states removes the record. Since the record is nonetheless *in* the released corpus, it is a **candidate conformance failure**. | none — see below |
| `undetermined` | A rule that applies cannot be decided because the **published source states no value** for a parameter it needs. ESM3-open's unpublished identity threshold is the whole of this column. | `unresolved` |
| `unresolved` | A rule that applies cannot be decided because the **release does not carry the metadata** it reads. | `unresolved` |
| `retained` | Every applicable rule was checked and none removed the record. Examined and kept. | `retained_by_design` |
| `out_of_scope` | The record's component is not in this policy's declared scope. The filter was never pointed at it. | `out_of_scope` |

Two things about this table are load-bearing.

**`undetermined` and `unresolved` are both "cannot decide" and are never merged.** One is a gap
in what a developer published about the *filter*, the other a gap in what they published about
the *corpus*. Stating a parameter fixes the first; shipping metadata with the records fixes the
second. They map to the same frozen survival route because the route taxonomy (D-022) has one
route for "cannot be determined from what travels with the release" — so the cause is kept in
the manifest's own field rather than by widening a frozen taxonomy.

**A `removed` record has no route, deliberately.** It is a claim that a named laboratory's
implementation did not do what its authors published. `metrics/survival.md` reserves
`conformance_failure` for A7.1, established with record-level evidence, and DESIGN.md §7
requires it to be airtight. `amazebio.apply.route_for` raises rather than returning that route,
so a detector cannot assert it in passing. Read the removed set as **candidates**.

## How a verdict is reached

Rules run in published order. Every rule that applies to the record's component is evaluated —
the pipeline does **not** stop at the first one to decide — and the outcomes resolve by
precedence:

```
removed  >  undetermined  >  unresolved  >  retained
```

Removal wins because it is the only definite verdict: if any rule removes a record, the record
does not survive, whatever an earlier rule could not decide. Retention loses because it is
contingent — "no rule removed it" is only true if every rule was actually checked. The policy
gap outranks the corpus gap because stating the parameter is a precondition for the corpus
question arising at all.

This differs from the reference evaluator in `amazebio.policyspec.evaluate`, which stops at the
first decision. The difference is not cosmetic: three of Evo's six rules are undecidable against
the release and they run *first*, so stopping would report every record as undecidable and lose
every removal the denylist rules make. D-044 records the choice.

For a removal, the rule attributed is the **first in published order** that removes it, because
that is the rule a conformance claim would cite.

## Enumerated and uniform sources

A component is read record by record only when a rule can **discriminate between its records** —
that is, when at least one applicable rule has both a published parameter and the evidence it
reads. Otherwise every record in the component gets the same verdict, and the manifest records
it once:

- `enumerated: true` — records were read. `records` is the count and `counts` the breakdown.
- `enumerated: false` — the verdict is in `uniform_outcome` and applies to every record in the
  component. `records` is `null`, never `0`: nothing counted them, and zero would read as an
  empty component.

So `totals` covers the enumerated sources only. A reader wanting corpus-wide figures must take
the uniform verdicts into account, which is why they are stated per source rather than summed.

One source is enumerated although its verdict is uniform: Evo 2's viral component. The claim
that it carries no lineage tag is one *this audit* makes, A1.2 could only sample it, and an
evidence declaration we assert rather than verify is the failure mode this project exists to
document. `evidence_contradictions` is the check — any non-zero value voids every verdict drawn
from that source.

## Record identifiers

| release | component | identifier |
|---|---|---|
| `opengenome2` | `imgvr` | the IMG/VR accession, e.g. `IMGVR_UViG_2505313053_000001` |
| `opengenome` | `stage2` | **synthesised**: `stage2:<object>#<row>`, e.g. `stage2:train_stage2.parquet#836` |

The synthesised form is stable and reproducible from pinned inputs, and it is **not an
accession**. Evo 1's release carries none for this component, so **nothing in `stage2` can be
joined to IMG/VR** — which is why the rules reading IMG/VR metadata cannot be closed for this
release by a key join (A1.7, A7.2).

**One row is one record** (D-048). A record longer than 131,072 characters — 2¹⁷, counting the
tag against the budget — arrives as several `|tag|block` pairs concatenated into *one* row, each
pair carrying the same tag, rather than as several rows. `policies/corpora.md` §3 first read
these rows as context windows from an 800-row sample and was corrected by a full scan.

Because every count for this component is a count of records, the reading is **re-measured on
every pass** rather than inherited, and the evidence travels in each source's `structure`:

| field | falsifies one-row-one-record? |
|---|---|
| `rows_multi_block` | No — several blocks under one tag are a long genome, chunked |
| `rows_multi_distinct_tag` | **Yes** — the row would pack several records |
| `rows_final_block_at_budget` | **Yes** — the record may continue into the next row |
| `rows_without_tag` | No, but reported: these rows yield no record and are counted as parse failures |

`structure.one_row_one_record` is the conjunction. **If it is false, every count in that
manifest is a count of rows, not of records**, and the manifest says so in its notes. Do not
quote a count from a manifest whose structure scan failed.

## Unstaged components are listed, not omitted

The strict reading's scope is the whole corpus, so its manifest covers components this project
deliberately did not stage — Evo 2's 2.17 TB of eukaryotic genomes among them, which are 82% of
that corpus and have no viral screening step in their published curation. They appear with
`records: null`, `extra.staged: false` and the reason. A wildcard-scope manifest that silently
covered only the staged components would read as a verdict on the whole release.

## Fields

### `manifest-*.json`

| field | meaning |
|---|---|
| `policy.id`, `policy.model`, `policy.reading`, `policy.scope` | the spec this manifest executes |
| `release` | `opengenome`, `opengenome2` or `esm3-proxy` |
| `records_enumerated` | records actually read across enumerated sources |
| `totals` | outcome counts over enumerated sources only |
| `removed.file`, `removed.records` | the removed set, or `null` when nothing was removed |
| `sources[]` | one row per component; see below |
| `notes` | caveats that travel with the numbers |

### `sources[]`

**One row per staged object, not per component.** Evo 1 publishes stage 2 as three splits —
train, valid and test — so `stage2` appears three times, with its own `key` in each row. A
consumer that groups by `corpus_component` and takes the first row reads one split and reports
its counts as if they covered the component; A2.1 hit exactly that and now joins on `key`. The
three-for-two version of this mistake is also why `corpora.undeclared_objects` exists.

| field | meaning |
|---|---|
| `key`, `bytes` | the staged object, and its pinned length — checked before reading. `key` is the row's identity: it is unique across the manifest, while `corpus_component` is not |
| `component` | the component name the **published methods** use, e.g. `IMG/VR` |
| `corpus_component` | the name `amazebio.opengenome` uses, e.g. `stage2` — so the row reconciles against A1.2's composition table without re-deriving either |
| `records`, `enumerated`, `uniform`, `uniform_outcome` | see above |
| `counts` | outcome name to count |
| `attribution` | `"<outcome>\|<rule-id>"` to count — *which rule* produced each verdict |
| `rules_applicable` | rule ids reaching this component, in published order |
| `rules_undecidable` | rule id to why it could not be decided here |
| `parse_failures` | records whose lineage tag would not parse. Counted separately, never absorbed into "unlabelled" — that population is one of the audit's own findings |
| `structure` | evidence that the record unit is what the counts assume; empty where the unit is the publisher's own, as in a FASTA entry |
| `evidence_contradictions` | records carrying evidence the source declares absent. Non-zero voids the source |

### `removed-*.jsonl`

One JSON object per line: `record_id`, `policy`, `release`, `rule_id`, `why`.

## Not in these manifests

ESM3-open's charitable and strict readings. Both need the two UniProt denylists rebuilt and an
alignment pass over the staged proxy corpus, which is **A1.6** (D-043). The ESM3-open *literal*
reading is here, and its result is that no record's fate is determinable from the published
words at all.

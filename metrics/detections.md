# Detection tables — the shared output contract for A2.1–A2.5

Task A2.1 · DESIGN.md §A2, §A3 · Deliverable 1

`metrics/survival.md` defines what the headline numbers mean and `metrics/manifests.md` defines
the surviving corpus they are computed over. This file defines the artefact in between: what a
detector emits, so that five detectors with five different instruments produce one shape A3 can
merge. Written to be usable without reading `src/amazebio/detect.py` — the independent
reimplementation in A3.3 works from specifications, not from our code.

Produced by `tools/detect_profiles.py` for A2.1. A2.2–A2.5 produce the same shape with their own
`detector` value, and nothing in this format is specific to profile search.

## One table per detector, registry and manifest — never pooled across any of the three

| axis | why it is never merged |
|---|---|
| **detector** | A3.2 reports by route *and* by detector. A merged table cannot be taken apart again, and a family found by both profile and structure is one finding reported twice unless the routes are separable. |
| **registry** | Membership criteria come from different authorities: RVDB-prot's from its curators, Pfam's viral subset from this project's reading (D-075). Pooling adds two denominators that mean different things. `metrics/survival.md` and D-022 already forbid it. |
| **manifest** | A manifest is one model × reading × release. The differences between readings and between releases are what Phase A is measuring; averaging them away discards the result. |

## Files

```
artifacts/a2-1/
  index.json                                              every table produced
  registries/registries.json                              the pinned registries, stated vs counted
  registries/pfam-viral-families.json                     the Pfam viral family universe
  detections-<registry>-<policy-id>-<release>.json        the table — read by a person
  detections-<registry>-<policy-id>-<release>.jsonl       the detections — read by a pipeline
  run.json                                                provenance: seed, parameters, inputs, outputs, commit
```

The `.jsonl` is absent when nothing was detected. That is a result, not a missing file — the
same convention `metrics/manifests.md` uses for an empty removed set.

## The two things a reader must check first

**`estimate_kind`**, which is one of three values and decides what the table's numbers are:

| value | means |
|---|---|
| `population` | Every record in the surviving set was searched. The figures are the population values. |
| `lower_bound` | A sample was searched (D-078). A family detected is detected; a family absent may survive in the records not read. **The survival fraction is a lower bound**, and A3.2 must not pool it with a `population` table. |
| `not_searched` | No source in this manifest could be searched at all. Every count is zero *by construction* and none of it is evidence of absence. The ESM3-open proxy corpus is the case: its reader is A1.6's. |

A sampled table is the normal case for A2.1. The cost of not sampling is **measured** rather
than estimated (D-098, which supersedes D-078's figure): 386 core-seconds per million residues
against RVDB-prot's 13,679 profiles, so a full census of both Evo releases against both
registries is about 3,000 core-hours. That is affordable, not out of reach — so a sampled table
is a first pass whose depth is a decision, and `estimate_kind` is what keeps the distinction
visible in the artefact.

**`families_without_a_hit`**, which is the other half of the denominator. `families` lists only
the families that were hit; every other family in the pinned universe is listed by accession in
`families_without_a_hit`. **A zero is a measured zero, not an absent row.** This is load-bearing:
a family with no surviving homolog is the result this audit is testing for, and a table built
only from what was detected would render a null as missing data. `AGENTS.md` forbids designing
any part of the pipeline so that a null is harder to see.

## Fields

### the table

| field | meaning |
|---|---|
| `task`, `detector` | which A2 task produced it, and with what instrument (`profile-hmmer`, …) |
| `registry`, `registry_version` | the pinned family universe the counts are drawn from |
| `manifest` | the A1.4 manifest consumed: policy id, release, path, **sha256**, and the records that reading removes |
| `sample` | seed, rate, population, method, and `is_census`; `null` for a census |
| `estimate_kind` | see above |
| `thresholds` | what a hit had to beat, and the decision that fixed it |
| `sources[]` | one row per component of the manifest, searched or not |
| `survival` | family-level survival with its Wilson interval, and how to read it |
| `routes`, `element_kinds` | totals across families, for A3.2's cross-tabulation |
| `families[]` | per-family rows, for families with at least one hit |
| `families_without_a_hit` | the rest of the universe, by accession |
| `notes` | caveats that travel with the numbers |

The manifest's **sha256** is what stops a table being read against a manifest regenerated later
under different policy prose: the numbers would still line up and would mean something else.

### `sources[]`

Every component of the manifest appears, including the ones the detector did not touch:

| field | meaning |
|---|---|
| `component`, `corpus_component` | the published name and the name `amazebio.corpora` uses |
| `searched` | **false** with a `why` for a component this detector does not cover |
| `sample_rate`, `records_in_source` | the rate applied, and the manifest's own record count |
| `records`, `genes`, `residues` | what was actually read and searched |
| `records_without_genes` | records whose genes the caller could not call — a limit of the method, counted rather than absorbed into "no hit" |
| `read_seconds`, `search_seconds` | cost per source and per registry, so a scale-up can be planned from measurement |

A component A2.1 does not search is **listed, not omitted**, for the reason
`metrics/manifests.md` gives for A1.4's own manifests: a table that silently covered part of a
release reads as a verdict on all of it. GTDB's bacterial genomes are A2.4's, host genomes are
A2.3's, and the rows say so (D-080).

### `families[]`

| field | meaning |
|---|---|
| `family_id` | the universe's key: Pfam's stable accession (`PF05505`, never `PF05505.16`), RVDB's family id (`FAM004230`) |
| `name` | the display name. For RVDB this equals `family_id`: the release assigns its families no descriptive name, so a readable label is **derived** and lives in `registries/rvdb-families.json`, joined on `family_id` (D-097). A table is a measurement and is not rewritten to carry a label. |
| `hits` | detections, which may exceed `records`: one record can carry several genes of a family |
| `records` | distinct surviving records carrying the family |
| `best_score` | highest bit score seen |
| `threshold` | what this family was accepted against — present on zero rows too, so the table can be re-cut at a stricter threshold without re-running the search |
| `routes`, `element_kinds` | this family's detections by survival route and element kind |

### the `.jsonl`

One JSON object per line: `record_id`, `family_id`, `registry`, `registry_version`, `detector`,
`score`, `threshold`, `route`, `element_kind`.

**No sequence in any artefact.** D-103 states the boundary: corpus sequence may live in
memory and in ephemeral scratch outside the working tree, never in the repository, in
`artifacts/`, in the audit store, or in anything a reviewer reads as a result. Residues
live in memory for as long as a search takes; the artefacts carry accessions, scores and model
coordinates only.

## Routes and element kinds

**Route** comes from the policy outcome for that record, through
`amazebio.apply.route_for` — the same mapping A1.4's manifests were built with. Two consequences
a detector cannot opt out of:

- **A record the reading removes is not in the surviving corpus.** Those records are subtracted
  before anything is searched, and any hit on one is excluded and counted in `notes`. They are
  *candidate* conformance failures for A7.1, with its record-level evidence requirement.
- **No table may assert `conformance_failure`.** `route_for` raises rather than returning it, and
  `check_route_coverage` refuses a table that assembled it another way. §7 requires that claim —
  about a named laboratory's implementation — to be established by A7.1 and not in passing.

**Element kind** is assigned from the record's *component*, taking the weakest kind that
component's own definition supports, and is never inferred from what was detected (D-079). IMG/VR
is a collection of viral genomes and metagenomic viral contigs, so a hit there is `free_virus` by
the publisher's definition; everything else is `unclassified_element`. A hit in a bacterial
genome becomes `prophage` when A2.4's instruments say so.

So A2.1's kind column is nearly constant by construction, and that is correct rather than a
defect: the cross-tabulation in A3.2 gets its information from A2.3 and A2.4. Do not read A2.1's
`unclassified_element` rows as a finding that the elements are unclassifiable.

## What the route comes from, and what it does not

The manifest carries outcome *counts* and the removed set, not a per-record outcome for every
record — by design, since the enumerated components run to millions of records. So the route of a
named record is recomputed with `amazebio.apply.resolve`, over the same evidence declaration,
which is the same implementation A1.4 used.

What is taken from the manifest is **the surviving set itself**: which sources are in scope, and
which records the reading removes. That is the part A2.1 must not re-derive (D-059), and the
recomputation is checked against it — a record that resolves to `removed` but is absent from the
manifest's removed set stops the run, because the manifest and the pass then disagree about what
survived and nothing downstream could be trusted.

## Sampling

Membership is a deterministic function of the record identifier and a pinned seed:

```
in_sample(record_id) == blake2b(key=seed, record_id)[:8] < rate · 2⁶⁴
```

Seed **20261015**. Four properties are the reason (D-078): it is declarable in advance,
reproducible without storing a list of ids, independent of the order the corpus is read in,
resumable after an interruption, and checkable per record afterwards — a reader can ask whether a
named record was in the sample without re-running anything.

**Rates are nested.** A deeper pass at the same seed is a superset of a shallower one, so
widening the sample never re-searches what has already been searched. A table's realized counts
are recorded per source, so a run that was stopped early reports the sample it actually read
rather than the one it intended.

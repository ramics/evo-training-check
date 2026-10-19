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
| `denominator` | what this registry's universe is, and how its fraction may **not** be quoted (D-161) |
| `composition` | the families carrying the detections, most first — depends on no denominator |
| `routes`, `element_kinds` | totals across families, for A3.2's cross-tabulation |
| `families[]` | per-family rows, for families with at least one hit |
| `families_without_a_hit` | the rest of the universe, by accession |
| `notes` | caveats that travel with the numbers |

## A survival fraction is not reportable on its own — `denominator` and `composition`

Added 2026-10-19, DECISIONS.md D-173, implementing D-161 in the artefact rather than in prose.

A2.4's first band reported 11.8% of Pfam's viral families and 0.66% of RVDB-prot's surviving as
prophage, from the same proteins. Side by side that reads as Pfam being eight times more
permissive, and a reader reaches for one number as the headline. Both readings are wrong:

- **The denominators answer different questions.** Pfam's universe is *this project's* derived
  viral subset (D-075), weighted toward well-characterised phage domains. RVDB-prot's is the
  publisher's clustering of the whole known virosphere, overwhelmingly eukaryotic viruses that
  **cannot** occur in a bacterial prophage — so it carries a large, structurally unreachable mass.
- **There is also a real sensitivity gap**, 5.2x, from the threshold regime (D-076), and it is not
  a counting artefact.

So every table carries **`denominator`**: the universe's authority, and the restriction on quoting
its fraction. Pfam's is never quoted as "the fraction of viral families"; RVDB's is never quoted
as a measure of how much survived. A registry the rule does not name still gets a restriction — a
new registry must not arrive with none, which is how a check that names two by hand goes blind to
a third (D-074).

And every table carries **`composition`**: the families holding the detections, most first. For a
prophage table that is a parts list — `Phage_integrase`, `Terminase_6N`, `Phage_capsid` — and it
is the evidence that detections are an integrated element rather than scattered homology.
**It depends on neither denominator**, which makes it, with the absolute counts, the part that
carries across registries.

Ties in `composition` break by accession, so a quoted parts list reproduces from pinned inputs.

**A3.3's reimplementation**: both fields are derivable from `families[]` and `registry`, so they
add no measurement. They are in the contract because `AGENTS.md` requires every published figure
to trace to a machine-readable artefact, and D-161's composition list was prose in the decisions
log with nothing emitting it.

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

## Where a table actually lives

Added 2026-10-19, DECISIONS.md **D-188**.

The `artifacts/a2-1/` paths above are where a run **writes**. They are not where a consumer
should expect to **find** a table, and the difference cost this project nine tasks' artefacts:
`artifacts/` is git-ignored and a session container is reclaimed, so a table that exists only
there is gone when the session ends.

Every table therefore has a durable copy at `s3://<corpora bucket>/corpora/results/<task>/`,
written by `amazebio.repro.run(durable=...)` on a clean exit, with the run's own `run.json`
beside it — a durable copy with no provenance is not citable, which is the point of keeping it.
`amazebio.objectstore.durable_results` builds the destination, so the scheme is one function
rather than a convention per tool.

**A consumer reads the durable copy.** A local `artifacts/` directory is a cache of the last run
in this container, and its absence says nothing about whether the table exists.

## A2.5's extension: a category is not a family, and `absent` is not `unlabelled`

A2.5 emits this shape with `detector: taxonomy-checklist`, and two fields of its own. Both are
extensions rather than reinterpretations: nothing above changes meaning.

**`categories[]` replaces `families[]`.** A2.5's universe is four §A2 problem categories defined
as ICTV taxon sets (D-187), not a registry's protein families, so `registry` is the pinned VMR
release and the zero-fill runs over **category members** — `members_with_a_record` and
`members_without_a_record` carry it. The composition rule of D-173 applies unchanged, and for a
problem-taxa table composition *is* the finding: `f__Phycodnaviridae 22,803` says what survived
in a way no fraction of an ICTV-derived universe does.

**`verdicts` has three values, not two.** This is the part another detector must not copy
blindly and A3.2 must not flatten:

| verdict | means |
|---|---|
| `present` | a category member matched the record's label, at its own rank or by lifting a finer one |
| `absent` | every member was **refuted** — at its rank, or at a coarser rank that excludes it |
| `unlabelled` | the label neither matches nor refutes. **Not evidence of absence.** |

A2.5 reads taxonomy, which is the evidence the filter itself acted on, and §A2 opens by warning
that an audit using taxonomy reproduces the filter's blind spots. A two-way split would record
"we could not tell" as "it is not there" — over a corpus where 2,543,536 of Evo 1's 2,653,047
surviving records carry no label below class, that is how a label-based sweep manufactures a
clean bill of health.

**Refutation runs up the ladder as well as down, and which way it runs differs per category.**
`c__Caudoviricetes` settles the giant-virus category outright, because every NCLDV family sits
under a class that is not that one. The same label cannot settle the segmented-genome category,
because three of its 48 families — Birnaviridae, Polymycoviridae, Polydnaviriformidae — are
themselves unplaced above family in MSL37.3. So `decided_at` records the rank each verdict rests
on, and a zero established at class over two million records does not support the same sentence
as a zero established family by family.

`unlabelled_by_reason` separates four cases that have different remedies: no label at all; a
taxon the reference does not know (taxonomic drift, which is A9.1's subject); a taxon the
reference knows but **does not place** above the category's rank, so no label on the record could
help; and a label that simply stops too high.

**Two shares, each naming its denominator.** `present_share_of_settled` divides by the records
whose label can answer the question; `present_share_of_all` divides by every record. They differ
by orders of magnitude for a family-keyed category over a class-labelled corpus, and quoting
either alone misleads in a different direction — the same failure D-161 measured one task over.

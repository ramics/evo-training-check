---
id: A2.5
title: Sweep known problem taxa
phase: A
status: review
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.5 — Sweep known problem taxa

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Check the specific categories §A2 names as known to defeat taxonomic filters.

## Steps

- Enumerate the problem categories from §A2 into an explicit checklist.
- For each, test whether material in that category survives each manifest.
- Attribute survivals to the appropriate route; flag any new route not yet modelled.
- Feed any newly discovered route back into the A3.1 route taxonomy.

## Done when

- Every §A2 category has a recorded result per manifest.
- New survival routes, if found, are added to the route taxonomy.
- Results merged into the shared detection schema.

## Result — 2026-10-19

`review`. Branch `claude/admiring-darwin-6r47lw`; artefacts at `corpora/results/a2-5/` (and
`artifacts/a2-5/`). Pre-registered as **D-187** before any count was taken.

**This is the label-side arm, and that bound is in every table.** The categories are taxa, so the
sweep reads the same evidence the filter acted on, and §A2 opens by warning that an audit using
taxonomy reproduces the filter's blind spots. So the verdict is three-way — present, absent,
**unlabelled** — and `unlabelled` is never folded into `absent`.

### The result: a census, both Evo releases, all three readings

Every figure is `estimate_kind: population`. The three readings agree exactly on every count in
both releases, so the reading spread is zero here — consistent with A1.4, since no Evo rule can be
decided on either component's released metadata.

| category | Evo 1 (2,652,952 surviving) | Evo 2 (2,917,521 accessions) |
|---|---|---|
| Giant viruses / NCLDV | **0** | **55,911** |
| Segmented genomes | **0** | **31,886** |
| Satellite viruses | **0** | **7** |
| Satellite nucleic acids | **0** | **228** |

**Evo 1's released viral component contains none of the four categories, and the giant-virus zero
is strong.** 2,652,952 records are `absent` and only **95** are `unlabelled` — the zero is
*established*, at phylum, for 99.996% of the surviving corpus. That is not a sampling artefact and
not an absence of evidence.

**The segmented and satellite-nucleic-acid zeros in Evo 1 are weak, and the tables say so.** Only
69,445 records (2.6%) are decidable at family; 2,583,602 (97.4%) are `unlabelled`. A zero over 2.6%
of a corpus is a statement about labels. The asymmetry is not about the corpus: a class-level label
excludes a phylum, so NCLDV is settled by `c__Caudoviricetes` alone, while **three of the 48
segmented families — Birnaviridae, Polymycoviridae, Polydnaviriformidae — are themselves unplaced
above family in MSL37.3**, so no class label can exclude them. The limit is in the reference
taxonomy.

**Evo 2's component carries all four categories, and the composition is what carries it:**

- **NCLDV** — `f__Phycodnaviridae` 22,787, `c__Megaviricetes` 22,454, `f__Mimiviridae` 5,423,
  `o__Algavirales` 1,617, `o__Imitervirales` 1,126, `o__Pimascovirales` 931.
- **Segmented** — `f__Botourmiaviridae` 8,350, `f__Tombusviridae` 7,317, `f__Nodaviridae` 4,438,
  `f__Picobirnaviridae` 1,420, `f__Partitiviridae` 1,261, and Geminiviridae.
- **Satellite viruses** — all five ratified taxa present: Albetovirus 2, Virtovirus 2, Aumaivirus 1,
  Papanivirus 1, Sarthroviridae 1.
- **Satellite nucleic acids** — `g__Betasatellite` 123, `f__Alphasatellitidae` 43.

**A second giant-virus signal that does not use the lineage column at all.** IMG/VR names its
giant-virus MAGs in the accession, and **1,783 such accessions are in Evo 2's released set**. This
is a giant-virus label *the publisher applied*, surviving independently of taxonomy. It is an upper
bound until every non-packable accession is enumerated: A7.2 published 20 examples and all 20 are
GVMAG. A7.2 had recorded them only as an accession shape its packing could not handle.

**Route: `unresolved`, and that is the finding, not a hedge.** Evo 2's records carry no taxonomy, so
no published rule can be decided on them — survival in a problem category is *measurable* there
while its route is *not determinable* from what ships with the release. **No table asserts
`conformance_failure`**: `amazebio.apply.route_for` refuses to return it, and §7 reserves that claim
for A7.1 with record-level evidence. Whether any of this is a conformance failure is A7.1's and
A7.2's question, and the classification here comes from IMG/VR's metadata through A7.2's published
accession join, cited as such.

**A fourth kind of not-knowing, which is a finding in its own right.** `unlabelled_by_reason`
separates four cases, and the third is the interesting one: a taxon the reference *knows but does
not place*. `Dinodnavirus` — Heterocapsa circularisquama DNA virus, a large dsDNA algal virus — is a
VMR genus at MSL37.3 with no family, order, class, phylum or realm above it. **No phylum-keyed rule
can reach it however completely the record is labelled.** 633 Evo 2 records are unlabelled for NCLDV
for exactly that reason, and Alphasatellitidae is unplaced above phylum too. That is §A2's
problem-taxa concern demonstrated from the authority's own data rather than from a detection.

### Done-when

- *Every §A2 category has a recorded result per manifest* — **met.** Four categories across seven
  manifests, 28 rows. The ESM3-open proxy is `not_searched` with its reason recorded: a taxon
  category is not expressible over a protein corpus carrying no viral taxonomy. Every component of
  every release is listed, searched or not, with a reason.
- *New survival routes, if found, are added to the route taxonomy* — **met, and none were found.**
  Every detection fell on a route the frozen D-022 taxonomy already carries. The route taxonomy is
  unchanged, which is the result rather than an absence of one.
- *Results merged into the shared detection schema* — **met.** Tables carry `detector`,
  the manifest with its **sha256**, `estimate_kind`, per-source rows, routes and element kinds.
  Two extensions are documented in `metrics/detections.md`: `categories[]` in place of `families[]`
  (the universe is an ICTV taxon set, not a protein clustering), and the three-way verdict.

A1.4's manifests are consumed, not re-derived (D-059): the removed set is subtracted before
anything is classified, and the route is re-resolved per record with `amazebio.apply.resolve` and
checked against the manifest — a record resolving to `removed` while absent from the removed set
stops the run.

### Outstanding, for the project owner

**The label-independent arm has not run.** The standing decision of 2026-10-19 was to ship this
census and then measure a small slice of a marker pass before committing to any of it. That
measurement was not taken — the session was spent on D-188 and D-189 instead. It is what would turn
Evo 1's weak segmented and satellite zeros into something stronger, and it is the one thing this
task still owes.

**Four faults found by testing rather than by reading**, each of which would have understated the
result: a family-level label reported as `unlabelled` for a phylum-level category, hiding a
detection as "could not tell"; the unlabelled reason chosen by sort order, burying a taxonomy gap
as a shallow label; a share computed from a non-iterable interval; and the zero-fill comparing
prefixed record labels against bare member names, which listed every category member as undetected
even where it had been detected. A fifth was caught before it cost anything: the sweep read stage 2
once per reading rather than once per source, which is D-046's tripled read repeated.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

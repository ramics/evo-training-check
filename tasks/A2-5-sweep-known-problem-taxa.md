---
id: A2.5
title: Sweep known problem taxa
phase: A
status: done
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

## Result — 2026-10-19, extended 2026-10-20

`done`. The label-side arm merged in PR #26 and the marker arm in PR #28
(`tools/marker_throughput.py`, `tools/detect_segmented.py`); **nothing is on a branch.**
Artefacts at `corpora/results/a2-5/` (and `artifacts/a2-5/`). Pre-registered as **D-187** before any
count was taken, **D-190** (family set and threshold) and **D-191** (depth ladder) before anything
was searched.

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

### The marker arm: Evo 1's segmented zero is withdrawn — **D-193**

**The label-side zero above is wrong, and the reason it is wrong is the point of the whole arm.**
Searching sequence rather than labels over the same records, at 10% depth:
**7 of 1,285 segmented virus families, 57 hits, in 265,062 records** (5,005,711 genes, 1,128 Maa
over 3.6 Gbp). Family-level share 0.54% (0.26–1.12%, Wilson); `estimate_kind: lower_bound`.

| family | records | ICTV family | genome |
|---|---|---|---|
| FAM000422 | **29** | Polydnaviriformidae | segmented dsDNA |
| FAM007500 | 6 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |
| FAM022414 | 2 | Nanoviridae (*Babuvirus*) | 6-segment ssDNA |
| FAM003906 | 1 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |
| FAM005477 | 1 | Geminiviridae (*Grablovirus*) | bipartite ssDNA |
| FAM023047 | 1 | Bromoviridae (*Ilarvirus*) | tripartite ssRNA |
| FAM033562 | 1 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |

**Five distinct ICTV segmented families, every one eukaryote-infecting**, in a component whose host
rule's published purpose is "to remove potential eukaryotic viruses" (D-110).

Three things make this more than a threshold artefact, and they are why D-193 states a finding
rather than a count: **FAM000422 appears in all four bands** (5, 7, 8, 9) and the bands are disjoint
hash samples; **three separately-built RVDB families converge on *Orthoreovirus***; and the models
are not all short — FAM003906 is 310 residues from 613 sequences, FAM000422 is 170 from 102, and
every hit cleared 50% model coverage on top of E≤1e-5.

**What is weak is named rather than averaged in.** FAM033562 (83-residue model, 7 sequences) and
FAM022414 (66 residues, 8) are the least safe of the seven. These are not seven equivalent findings
and must not be quoted as such.

Route is `unresolved` for all 265,062 records, and **no table asserts a conformance failure** — §7
reserves that for A7.1. Eight records the reading removes were subtracted before anything was
called. Bands `[0,0.02]`, `[0.02,0.05]`, `[0.05,0.08]`, `[0.08,0.1]`, assembled with an
overlap-and-gap check; band 1's 53,140 records match A2.1's published figure exactly, which is what
licenses comparing the two arms directly.

**D-187's sentence that "no marker pass can strengthen that category's zero" is wrong as written.**
It is true of segmentation as a *property* — a contig is not labelled segmented by a profile — and
false of the *families*, which have perfectly ordinary protein markers. D-190 drew that distinction
and D-193 settles it with data.

**This is §A2's own warning, measured.** The two arms read the same records and returned **zero**
and **seven**. The difference is not depth or threshold: one arm reads a label 2.6% of records
carry, the other reads the sequence every record carries.

**The satellite arm is unrunnable by the same route**, and that is a named limitation rather than an
unexamined gap: D-190's selection returns zero families for both satellite categories, because
satellite nucleic acids encode few or no proteins and RVDB has no family whose LCA sits inside them.
Evo 1's satellite zeros stay weak.

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

### Deliberately not done, for the record

**The marker arm stopped at 10% by choice, and the choice was a schedule not a budget.**
Nothing here blocks the task: every Done-when criterion is met and these are named limits, which
is the form `DESIGN.md` §A0 asks under-specification to take. The
owner authorised a full census at about $9.60 and it was then declined on the measurement: 2% took
55 minutes, so the remaining 90% is roughly 28 sequential runs inside this environment's two-hour
cap. D-191 had also pre-registered that deepening past band 2 was conditional on the question still
being open, and after band 1 it was not. **A census would refine how much survives, not whether.**
If anyone wants it, the route is one in-region EC2 instance rather than 28 session runs — that is a
new task, not a widening of this one.

**One permanent artefact is superseded.** `corpora/results/a2-5/segmented-assembled.json` written
2026-10-19 21:28 was a scratch-directory probe of `--assemble` that published to the real prefix,
because `repro.run` derives `durable` from the task id and cannot see `--out`. It overwrote nothing
and is self-labelling, but the bucket has no delete, so it is permanent and the real assembled run
superseded it in place. The fix is in `detect_segmented.py`: a run writing anywhere but the
canonical directory declares `durable_exempt` and says so on stderr. D-189's lesson arriving by a
second route, which is the argument for putting these guards in the code path.

**Four faults found by testing rather than by reading**, each of which would have understated the
result: a family-level label reported as `unlabelled` for a phylum-level category, hiding a
detection as "could not tell"; the unlabelled reason chosen by sort order, burying a taxonomy gap
as a shallow label; a share computed from a non-iterable interval; and the zero-fill comparing
prefixed record labels against bare member names, which listed every category member as undetected
even where it had been detected. A fifth was caught before it cost anything: the sweep read stage 2
once per reading rather than once per source, which is D-046's tripled read repeated.

**The marker arm's one unplanned event is a result about the design rather than about viruses.** The
container restarted mid-ladder. Three completed bands were intact in object storage; the in-flight
band lost 50 minutes of compute and **no results**. That is the first real test of D-188's
durability guard and of publishing each band as it completes, and both held.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

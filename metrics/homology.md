# The homology axis — the shared output contract

Tasks B3.1, B3.2, B3.3 · DESIGN.md §B3 · Deliverable 3

**Status: binding on B3.5 and B5.** A change to this file is a `DECISIONS.md` entry.

`metrics/depth.md` states the contract for §B3's confounder. This file states it for §B3's three
measures, for the same reason: the three are produced by different instruments at different
depths, and B5's regression takes them as one axis. One shape, read without reading the tools.

`DESIGN.md` §B3 asks for three measures against **each model's surviving corpus**, which A1.4
supplies as manifests (`metrics/manifests.md`) rather than as an assumption:

| # | measure | `measure` value | role |
|---|---|---|---|
| 1 | sequence-profile homology, length-normalised | `sequence_profile` | secondary |
| 2 | domain-level presence, binary and count | `domain_presence` | secondary |
| 3 | nearest-structure similarity | `structural` | **primary**, pre-registered |

§B3's instruction to pre-register #3 as primary is a commitment this file carries, not a
preference a later task may revisit: #3 stays primary in the schema even where a manifest
could not be searched for it, so a reader cannot mistake the measure that *has* numbers for
the measure the design relies on. What #3 can and cannot say here is **Availability** below.

## The row

One row per **target x manifest x measure**. The target is an assay target from B2.4's
register, keyed by `dms_id`; the manifest is a model × reading × release from A1.4, keyed by
`policy` and `release`. Nothing is pooled in the artefact — §B5's per-assay-before-pooled rule
applies to this file's own output, so pooling is the reader's step and is never pre-done here.

| field | meaning |
|---|---|
| `dms_id` | the assay, as B2.4's register keys it |
| `uniprot_id`, `target_length` | the target protein and its length in residues, from B2.1's pinned reference |
| `policy`, `release` | which manifest this row scores against |
| `measure` | one of the three values above |
| `kind` | how to read `score` — see **Kinds** |
| `score` | the measure's raw value, or `null` whenever `kind` is not `measured` |
| `normalised` | the length-normalised value, or `null`; defined per measure below |
| `searched_fraction` | the fraction of the manifest's records the verdict is over, `1.0` for a census |
| `bound` | `none`, `lower`, or `upper` — what the row is, relative to the same measure at census depth |
| `params` | the parameter block the row was produced under, by digest and by value |
| `evidence` | per measure: the best-hit identifiers and spans a reviewer needs to re-cut without re-searching |

## Kinds

`kind` exists so that "no homology" and "not looked for" are never the same cell. Four values,
and the arithmetic a consumer may do differs for each:

| `kind` | means | `score` | may enter a model as |
|---|---|---|---|
| `measured` | searched, and a hit met the declared cut | set | itself |
| `absent` | searched to `searched_fraction`, no hit met the cut | `null` | a censored observation at the cut, **never** as zero |
| `not_searched` | this manifest was not searched for this measure | `null` | nothing — the row is excluded and reported as excluded |
| `unanswerable` | the target has no input this measure needs | `null` | nothing — reported with the reason |

Two rules on top of that table, both of which B3.1's Done-when asks for in so many words:

- **`absent` is not a low score and never becomes one.** A consumer that wants a number for a
  censored row states the substitution and its justification in B5.1's pre-registration; this
  artefact does not make the substitution for it. `metrics/depth.md` forbids imputing the
  covariate; the same rule holds here for the response's homology term.
- **`absent` under a sample is a bound, not a negative.** Where `searched_fraction < 1.0`, a
  row's `kind: absent` means *not found at that depth* and the row carries `bound: lower` —
  the same distinction `metrics/detections.md` draws between a population figure and a lower
  bound, and for the same reason. A `measured` row under a sample is also `bound: lower`: the
  best hit over a sample cannot exceed the best hit over the whole, so the score is a floor.
  A census carries `bound: none`.

## The measures

### 1 `sequence_profile`

`score` is the **bit score of the best-scoring hit** of the target's profile against proteins
called from the manifest's surviving records. The bit score rather than the E-value, on D-076's
rule: an E-value scales with how much corpus a run happened to read, so a headline computed
from one would drift with depth, which is the one thing this axis must not do.

`normalised` is **bits per residue of the query**: `score / target_length`, the length
normalisation §B3 item 1 asks for. Both travel, because the raw bit score is what a reviewer
re-cuts and the normalised value is what crosses targets of different length.

`evidence` carries the matched record identifier, the model and target spans, the alignment
length, the fraction identical, and the second-best hit's bit score. Residues never appear,
here or anywhere in `artifacts/` — D-103.

### 2 `domain_presence`

`score` is the **count of the target's distinct annotated domain families present** in the
manifest, and `normalised` is that count over the number of annotated domain families, so a
single-domain and a six-domain target are comparable. The binary §B3 item 2 also asks for is
`score > 0`, derived rather than stored, so the two cannot disagree.

**Multi-domain handling.** A target is annotated to a *set* of domain families, de-duplicated by
accession: a domain that occurs twice in one target is one family, and the instance count
travels in `evidence` rather than in `score`. Presence is decided per family and the row
reports the per-family verdicts alongside the count, so a consumer may use the binary, the
count, or one named family without re-deriving any of them. A target with no annotated domain
is `unanswerable`, not `absent` — nothing was looked for.

### 3 `structural`

`score` is the similarity to the nearest surviving structure, under the parameters `params`
records, and `normalised` is that score on its own scale where the scale is already
length-independent.

**Availability.** The measure §B3 names is a TM-score, and A2.2 established that it cannot be
computed over these corpora — not as a matter of cost but on the publisher's own statement: a
structural-alphabet database predicted from sequence holds no C-alpha coordinates, and the
tool therefore refuses TM-score and LDDT output entirely (D-167). What that leaves is a
structural-alphabet bit score, and producing even that over a manifest was priced at 70+
instance-hours against this project's budget and declined (D-180). So a `structural` row for
an unsearched manifest is `kind: not_searched` with the reason named, on A2.2's precedent, and
the primary measure's absence is a stated limitation of Phase B rather than a gap a reader has
to notice. `score` is `null`; it is never a sequence measure wearing the primary measure's name.

## What may be published from it

**This artefact is internal, and not because of what it measures — because of how it is keyed.**
A row names an assay, and an assay's identifier names the organism its protein came from. That
puts the axis squarely inside D-125's reporting rule, which is that results go out by survival
route and homology class and never as a ranking of which model is most capable for which
pathogen, and inside §4's requirement that nothing circulates before X3.1.

So the division is the same one the label arm already works to. What may be published from this
file: counts and distributions by homology class and by survival route, the kinds table, the
depth and its bound, and the disagreement between the three measures, which is the result §B3
asks for. What stays internal and goes to the project owner: the per-assay rows, the matched
record identifiers and spans in `evidence`, and any ordering of assays by score. A figure built
from this artefact that can be read as "model X retains capability for pathogen Y" is outside
what this project publishes, whatever its caption says.

## What a reader may not conclude

- **A `measured` row says a homologue is present in surviving space. It does not say the
  target's own sequence survived.** The two differ by exactly the distance the measure reports,
  and A4.5's finding applies here with full force: a family being present is not the same claim
  as a viral genome being present, and which case a row is in is a lookup, not a guess.
- **The three measures are not interchangeable and disagreement between them is the result.**
  §B3 says so outright: "Report all three; disagreement is informative." A consumer that reads
  whichever measure has the most `measured` rows has selected on the instrument.
- **A row's depth is part of its value.** Comparing a census row against a sampled row compares
  a figure with a floor. D-247's rule — never set a single-detector figure beside a merged one —
  is the same rule one axis over.

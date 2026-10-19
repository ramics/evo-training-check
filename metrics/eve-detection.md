# The endogenous-element arm — method, and what can make it wrong

Task A2.3 · DESIGN.md §A2 · Deliverable 1 · decisions D-182, D-183, D-185, D-186

`metrics/detections.md` fixes the shape of the tables this arm emits and `metrics/survival.md`
fixes what the headline number means. This file is the third thing a reader needs and the one
A2.3's Done-when asks for by name: **how a detection here is produced, and every way it can be
something other than what it looks like.**

Written to be usable without reading the code, because A3.3 reimplements from specifications.

## What the arm does

| | |
|---|---|
| **Subject** | Evo 2's `ncbi_eukaryotic_genomes`, the only host-genome component in either audited release. Evo 1 exposes none (D-018, D-019), so its tables are `not_searched` *by construction* |
| **Registry** | Dfam 4.0, curated HMM component. Universe is the LTR class; the arm's headline is the ERV subtypes — **5,420 searched of 5,565 held** (D-185) |
| **Queries** | each family's own match-state consensus, read from the pinned models (D-186) |
| **Instrument** | `mmseqs2` nucleotide search, consensus as query and genomes as target |
| **Acceptance** | E-value ≤ 1e-10 **and** alignment ≥ 100 bp **and** identity ≥ 0.70, fixed before any hit was seen (D-186) |
| **Record** | the assembly. One detection per family per genome, never per alignment (D-136) |
| **Route** | from the manifest's own verdict via `amazebio.apply.route_for` — `out_of_scope` under the literal and charitable readings, `retained_by_design` under the strict one |
| **Element kind** | `endogenous_retroelement`, assigned from the instrument |

**Element kind is assigned from the instrument, which is the one place this arm departs from
D-079.** That entry says a *profile* hit cannot distinguish a free virus from an integrated
element and leaves the stronger claim "to A2.3 (EVEs) and A2.4 (prophage)". Making that claim is
this task's deliverable rather than an inference it is forbidden — but see **the first
false-positive mode below**, which is the price of making it.

## The positive control, and what it does not cover

Every run first searches the query set against itself and requires **99% of families to find
themselves**; the recorded runs return 100% (5,420 of 5,420). This exists because a genome with
no accepted alignment is a real and expected result here — many sampled assemblies are lineages
these families do not occur in — so a zero cannot otherwise be told apart from a broken
database, the wrong search type, a mis-parsed column, or an acceptance rule rejecting
everything. Each of those produces zero in every genome and a table that reads as a filter that
worked. `AGENTS.md` forbids designing the pipeline so a null is harder to see; this is the
converse obligation, that a null be earned.

It proves the instrument can detect. **It proves nothing about whether a detection in a real
genome is the thing the family name says it is.** That is what the rest of this file is about.

## False-positive modes

Ordered by how much they could change a reported figure, not by how likely they are.

**1. A sequence match is not an insertion.** The instrument reports local similarity between a
family consensus and a stretch of assembly. It does not establish that the matched sequence is
an integrated element: it does not check for the structural features an insertion has, it does
not require the match to be flanked by host sequence, and it does not distinguish a full-length
element from a fragment of one. This is the direct cost of assigning `endogenous_retroelement`
from the instrument, and it is why §A2 names a structure-based finder as a second instrument.
**This arm does not run one**, so no detection here has been confirmed by an independent
mechanism. D-186 records that a paired comparison is affordable if the sensitivity gap is ever
wanted measured rather than asserted.

**2. Contamination in the assembly is attributed to the assembly.** A published eukaryotic
assembly can carry sequence that is not the host's — from other organisms in the sample, from
cross-contamination, or from unremoved adapters and vectors. A hit in such sequence is recorded
against the accession it was found in, because the record is the genome. The audit's subject is
the corpus as released, so sequence the publisher shipped is in scope; but a detection does not
prove the element is in that species' genome.

**3. Similarity can run in the other direction.** Some families in any transposable-element
registry contain regions of host origin, captured from the genome rather than contributed to it.
A match to such a region can reflect the host's own gene rather than an element derived from it.
The family label is then right about the similarity and wrong about what the sequence is.

**4. The family label weakens with distance from the curation lineage.** The registry's curated
families come from the root and Bilateria partitions, so they are curated against animal
lineages. A large share of the component by count is fungi, plants and protists. A match in a
distant lineage is more likely to reflect a module shared widely among mobile elements than the
specific family named. **The detection may be real while its family attribution is not**, which
matters because the headline is family-level.

**5. Families are not independent, so the denominator is not a set of independent trials.** The
registry holds many closely related families; one locus can satisfy the cut against several of
them. A family count is therefore not a count of distinct elements, and the Wilson interval
`metrics/survival.md` attaches to the fraction treats families as independent when they are not.
The interval is a statement about sampling, not about biological independence.

**6. The cut does not exclude low-complexity or simple-repeat matches.** 100 bp at 70% identity
is satisfiable by simple repeats and low-complexity sequence that many elements contain and that
is also common in host genomes. No complexity filter is applied, and none was pre-registered.

**7. The consensus is not the family.** A consensus is one sequence standing for a family's
diversity. A match to it is weaker evidence than a match to the profile it was derived from,
and `fident` against a consensus is not a divergence estimate for the matched locus.

## The two directions do not cancel

A reader reaching for a single adjustment will not find one, and it is worth being explicit
rather than leaving the impression that the figure is simply conservative.

**Four things make the reported fraction a lower bound**, all declared in advance: the corpus is
sampled (D-182); only Dfam's curated component is used, excluding the much larger uncurated one
(D-183); 762 LTR-class families, 145 of them ERV-subtype, are excluded for carrying no curated
threshold (D-185); and a consensus search is less sensitive than the profile search it replaced
(D-186).

**The seven modes above push the other way** — toward counting families that are not there, or
are there under the wrong name.

So the honest reading is **not** "the true value is higher". It is that the figure is a lower
bound *on detectable similarity to this registry at this cut*, and that the step from that to a
count of integrated elements is exactly the step mode 1 says this arm does not take. A2.3's
tables support the first claim. The second needs the second instrument.

## How to quote a figure from these tables

- **Never as "the fraction of retroelement families".** The denominator is the curated component
  only, excludes the families with no curated threshold, and spans LTR retrotransposons as well
  as the ERV subtypes. The restriction travels in each table's `denominator` and `notes`, per
  D-173, so it does not depend on a reader finding this file.
- **Name the denominator in the same sentence as any percentage**, and give the ERV-subtype and
  other-LTR counts separately, each with its own count (D-183).
- **Absolute counts and `composition` carry across registries; fractions do not** (D-161).
- **Check `estimate_kind` first.** `not_searched` on Evo 1 means the component does not exist in
  that release — a different claim from A2.2's `not_searched`, where the component existed and
  the pass was not bought.

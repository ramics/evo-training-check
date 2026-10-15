---
id: A4.2
title: Benchmark taxonomy-tool misassignment
phase: A
status: review
gate: false
depends_on: [A1.4]
blocks: [A5.1, A6.1, A4.4]
design_ref: "§A4"
deliverable: 1
owner: claude
---

# A4.2 — Benchmark taxonomy-tool misassignment

**Design reference:** DESIGN.md §A4 · **Deliverable 1**

## Goal

Measure the error rate of the taxonomy assignment tools a filter depends on, on the sequence
class that matters for this audit.

## Steps

- Assemble a labelled evaluation set with trustworthy ground truth; document its provenance and
  biases.
- Benchmark the relevant tools at the versions the filters rely on.
- Report error rates with confidence intervals, broken down by error direction.
- State how tool error propagates into filter leakage.

## Done when

- Error rates reported with intervals and by direction.
- Evaluation-set provenance and bias documented.
- Propagation into leakage stated quantitatively where possible.

## Outcome — 2026-10-15 — review

**Branch:** `ccr-bcc7b994-9ycpzn`. `src/amazebio/{ictv,genomad,misassignment}.py`,
`tools/taxonomy_dependency.py`, `tools/taxonomy_benchmark.py`, 143 new tests. Artefacts
`artifacts/a4-2/{dependency,misassignment}.json` and `misassignment.md`, with one run manifest
per step pinning a clean tree. Pre-registration D-084..D-088 and the corrections D-089, D-090.

### The headline

**geNomad does not place 36.23% of the viral genomes Evo's denylist was written to remove —
measured on complete reference genomes, which is the easiest case it will ever see.**

| direction | count | rate | 95% CI |
|---|---|---|---|
| **escape** — true taxon denylisted, label does not say so | 546 / 1,507 | **36.23%** | 33.80–38.72% |
| **spurious removal** — true taxon not denylisted, label says it is | 50 / 1,642 | **3.05%** | 2.27–4.00% |

Escape is leakage. Spurious removal is the filter deleting records the policy never named. They
are reported separately because they are not recoverable from each other and no pooled accuracy
figure is offered (D-088).

Named hazard families, worst first: **Hantaviridae 106/106 (100%, CI 96.6–100)**,
**Orthomyxoviridae 122/136 (89.7%)**, **Picornaviridae 29/40 (72.5%)**, Hepadnaviridae 50.0%,
**Filoviridae 4/13 (30.8%)**, Retroviridae 17.5%. Fourteen families escape at 0%, and their
intervals are reported rather than a bare zero — Coronaviridae 0/40 is 0.0–8.8%, which is what
the data excludes rather than a claim of perfection.

### Why, and why it transfers

Escape has two mechanisms and they are not interchangeable:

| cause | records |
|---|---|
| unclassified — no lineage at all | 344 |
| shallower than the rule — labelled at order, not a denylisted one | 119 |
| misassigned order | 52 |
| absent at the rule's ranks | 28 |
| misassigned family | 3 |

So **491 of 546 escapes are the tool declining to place the record, and 55 are confident and
wrong.** That split matters for what this task adds: under-assignment is visible in the corpus
as a missing field, which is what A4.1 measured as the filter's ceiling. The 55 are the part
A4.1 could not see — a record labelled at family, confidently, in the wrong family.

Two covariates say the rate is a floor rather than a point:

- **Length.** 59.3% at under 2.5 kb, 47.8% at 2.5–5 kb, 37.1% at 5–10 kb, 8.5% at 10–20 kb,
  1.3% at 20–40 kb. The corpus is 84.67% `Genome fragment`; the evaluation set is complete
  genomes. A marker-based classifier given fewer markers assigns a shallower lineage, and a
  shallower lineage is itself an escape route.
- **Segmentation.** Segmented species escape at **64.6%** (369/571) against 18.9% (177/936) for
  single-segment ones. Five of the nineteen denylisted families are segmented, and this is why
  D-087 made the sequence rather than the species the unit: a filter acts per record, an
  assembly yields segments separately, and Hantaviridae's 100% is that fact.

820 of 3,149 submitted sequences received no taxonomy row at all.

### What it implies for the filter, and what it does not

The denylist removed 181,530 IMG/VR records. **38.56% of those removals rest on a
geNomad-assigned label**, which implies an in-scope population of 109,760 records for that
component, of which **39,767 (35,736–44,218) escaped**. The algebra is `R = N(1 - e)`, so
escapees are `R·e/(1-e)` — multiplying the removals by the escape rate understates it by
`(1-e)`, which is what D-089 corrects.

**61.44% of the denylist's removals are unmeasured.** They rest on taxonomies IMG/VR imported
from other datasets — RVMT alone supplies 49.51% — and those are not tools this audit can run.
That gap is A4.4, created rather than absorbed (D-084).

### The dependency decomposition, which is a result in its own right

Settled from IMG/VR's own per-record method field, not inferred:

| population | geNomad | RVMT | NR | vOTU consensus | other |
|---|---|---|---|---|---|
| all 15,677,623 records | 89.97% | 2.22% | 2.56% | 1.81% | 3.44% |
| labelled at family | 61.74% | 22.20% | 11.22% | 3.79% | 1.05% |
| the denylist's 181,530 hits | **38.56%** | **49.51%** | 4.27% | 5.64% | 2.02% |

The drift has a mechanism: the denylist names eukaryotic RNA-virus taxa and IMG/VR imported
those labels. **The publisher's help page documents four taxonomy approaches; the corpus
carries eight**, and three of the extras — RVMT, RefSeq, GVMAG — are described in neither the
release note nor the help page. §A0's "under-specification is data" applies, and it lands
precisely on the records the filter removes.

An internal benchmark was checked for and is thin rather than available: 13,971 records are
flagged `Reference`, but 97.29% took their lineage from the RefSeq lookup, where label and
ground truth are one fact. Only 272 carry a geNomad label — and 255 of those carry no family.

### Three things worth a reviewer's attention

1. **The version is a bound, not a statement.** The release note pins CheckV to v1.0.1 in the
   same field list and leaves geNomad unversioned; the help page contains no version string.
   geNomad 1.1.0 + marker database v1.1 is the newest pairing that could have produced the
   labels, from release dates the publisher does not control. The v4 paper could not be
   retrieved here (OUP 403, PMC proof-of-work), so the claim is scoped to the two sources
   checked and the paper is flagged for A6.1 (D-085).
2. **Two near-misses, both of which would have published a flattering number.** Validating
   `score` produced a 100% escape rate — an accession-version join failure, now tolerant with a
   guard that refuses a total mismatch outright. And the first parse read geNomad's lineage
   positionally when it is a compacted list, scoring 195 records as escapes the tool never
   committed and inflating the headline to 40.68%; its own suffix check caught it (D-090). The
   corrected run reads all 2,329 lineages with zero anomalies.
3. **`not_viral` is zero by construction, not by measurement.** The benchmarked step is
   `genomad annotate`; geNomad's virus classifier is not run, deliberately, because the records
   the denylist acts on are already in IMG/VR and so already called viral. The artefact says so
   rather than letting a structural zero read as evidence.

### Done-when

- *Error rates reported with intervals and by direction.* Both directions, each over the
  population it is a rate of, with exact Clopper-Pearson intervals; per family before pooled
  (44 families), by length stratum, and by escape cause.
- *Evaluation-set provenance and bias documented.* Ground truth is pinned ICTV VMR_20
  MSL37.3 (sha256 in `ictv.RELEASES`), contemporaneous with the corpus so that taxonomic
  revision stays A9.1's subject (D-086). Selection, caps, exclusions and three named biases
  ship in the artefact, all pointing the same way: the rate is a lower bound.
- *Propagation into leakage stated quantitatively where possible.* 39,767 records
  (35,736–44,218) for the geNomad component, with the algebra, the bound direction, and the
  61.44% it does not cover.

**Not done, deliberately:** the three policy readings are indistinguishable here for the same
reason as in A1.4, A7.1 and A4.1 — the denylists they share set the scope, and no rule they
differ over reads a taxonomic label. A0.4 reports the spread.

**Waiting on the project owner:** nothing — the one open judgement is now settled. A4.2
reports a measured rate for 38.56% of the filter's hazard-relevant removals and an explicit gap
for the rest, and the project owner decided that Phase A does not publish on that basis:
**A4.4 blocks A6.1** (D-091). So this task's result is final as a component, and the write-up
waits on the other 61.44% being measured or shown unmeasurable.

**For whoever picks up A5.1 or A6.1:** quote the escape rate with its population and its bound
— 36.23% of the denylisted genomes geNomad was asked to place, on complete genomes, a lower
bound for fragments. The artefact refuses to hand over the propagation figure without its
coverage field.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

# Auditing a training-data exclusion policy

Draft of 2026-10-22. Internal to the project: `AGENTS.md` holds findings inside the project until
the responsible-disclosure task (X3.1) has run, and that gate has not opened. Written for a reader
comfortable with software, statistics and the AI-safety literature, who knows no biology. This
project's own measurements cite the task and decision identifiers that carry them; those are not
public.

## Abstract

Two openly released genome models, Evo 1 and Evo 2, state that viral genomes infecting eukaryotic
hosts were excluded from their training data, and both publish the corpora they were trained on
[1-4]. We executed that policy against the released artefacts and searched what survived.

Four results. **(1) The rules that name organisms can act on a small fraction of their input.** The
policy's two denylists key on the family and order ranks of a record's taxonomic lineage; in the
source database, IMG/VR [5], 6.25% of 15,677,623 records carry a family label and 8.67% carry an
order label, rising to 7.87% and 8.85% over the population the rules are handed. Evo 1's released
component carries a family label on 2.62% of records. **(2) The denylists are written as names, and
names expire.** Of the 31 taxon names the policy lists, three no longer denote what they denoted
when it was written: *Herpesviridae* became a synonym of *Orthoherpesviridae* in January 2026, so a
rule naming it removes no herpesvirus and its output does not say so. Measured reach of the list
fell from 75.83% to 65.17% of the viral taxonomy, decaying at 4.34% per year. **(3) Sequence search
finds viral protein families in both released corpora**: at least 597 of 1,719 viral Pfam families
in Evo 1's component and 812 in Evo 2's, both lower bounds from 1-2% samples whose accumulation
curves have not flattened. In a targeted sweep of Evo 1's component, taxonomic labels report zero
segmented-virus records while sequence search over the same records finds markers of five
eukaryote-infecting virus families, one of them named on the policy's own denylist. **(4) The
artefact that can be audited is not the artefact that was trained on.** Evo 2 publishes its viral
component in two representations; the one that was trained on matches Evo 1's filtered output
exactly, while the only one carrying source identifiers holds 304,448 more records, including those
the policy removes. A filter's output therefore cannot be checked against the filter's own product.

**Two limits on what this establishes, stated here because they bound every number above.** A
profile hit places a protein in a sequence family at that family's curated threshold; it is not an
assessment of function or hazard, and nothing in this work measures whether any detected sequence
would do anything harmful. And while the family counts are of distinct, pre-registered family
identifiers drawn from two independently curated registries, we have not measured per family
whether a detected family occurs only in viruses — so "viral protein family present" is the claim,
not "viral genome present".

## 1. Why the claim is worth checking

The exclusion paragraph in a model release is load-bearing. It is the basis for describing a
release as having handled a category of risk at the data layer, and it is cited in arguments about
whether open weights are safe to publish.

It is also rarely checked, for mundane reasons: the policy is prose, so there is nothing to run;
the filter's implementation is not released; and the corpora run to millions of records. The Evo
releases are the best available case because both state a policy and both publish the corpus.

Their stated procedure, applied to IMG/VR, is five steps: keep only records the database flags as
high-confidence; keep one representative per viral operational taxonomic unit; keep only records
whose taxonomic classification has been observed in a prokaryotic host at least twice; remove
anything assigned to one of 19 named virus families or 12 named orders; remove records assigned no
realm or no deeper than one of eight named high-level taxa [1,2].

## 2. Method

### 2.1 The filter reads labels; this audit reads sequence

Every rule in the published pipeline reads a metadata field attached to a record by the source
database: a confidence flag, a cluster identifier, a host prediction, a rank in a taxonomic
lineage. No rule reads the sequence. The filter asks what a record's annotation says it is.

The detection pass reads no labels. It translates each record into protein coding sequence with
Prodigal in metagenomic mode — the caller IMG/VR's own annotation pipeline uses (`pyrodigal` 3.7.1,
vendoring Prodigal 2.6.3; D-077) — and searches those proteins with profile hidden Markov models
[6-8] against two version-pinned registries: Pfam 38.2, from which a frozen keyword rule selects
1,719 viral families of 30,134 [9], and RVDB-prot v32.0, 13,679 families [10].

The two instruments are independent, which is what makes the audit possible: a record carrying no
family label is invisible to the filter's family rule and fully visible to a profile search.

### 2.2 Thresholds, fixed before any result was seen

Pfam's own per-family gathering cutoffs are used as published. RVDB-prot uses its publisher's rule,
E ≤ 1e-5, evaluated against a pinned database size. The pinning matters: a sequence E-value scales
with the number of targets searched, so a fixed E-value cutoff corresponds to different bit scores
on a sample and on a whole corpus, and a headline built on one would move with how much corpus a
run happened to read (D-076).

### 2.3 Sampling

Sample membership is a deterministic function of the record identifier and a pinned seed —
`blake2b(key=seed, record_id)` below `rate · 2⁶⁴`, seed 20261015 — fixed before any search ran
(D-078). Samples at different rates are therefore nested: a deeper pass contains the shallower one,
and the two compare directly. Every count from a sampled pass is a lower bound, because a family is
counted only when a sampled record carried it.

A full census is affordable and has not been bought. The current measured cost is about 3,000
core-hours for both releases against both registries, tens of dollars at spot prices (D-098, which
supersedes an earlier estimate thirty times too high).

### 2.4 Second route, and verification

A second detection route covers material integrated into bacterial genomes, which the policy does
not address: a whole-document search of both papers finds no mention of proviruses, endogenous
elements or integrated viruses as a curation concern. Candidate regions are called with geNomad
[11] and then searched with the same profiles.

Each policy is executed in three readings — literal, charitable and strict — and the spread is
reported rather than resolved by choice; on these corpora the three agree exactly (D-221). Records
whose verdict depends on a field the release does not carry are recorded as `unresolved` and never
counted as retained. Headline counts are reproduced by a second implementation written without
reading the first, from primitive detection rows rather than aggregates, with denominators rebuilt
from the pinned registry files: 334 numbers across 16 groups, every headline figure identical
(A3.3, D-215).

## 3. Result 1: the reach of the rules that name organisms

The two denylists key on family and order. IMG/VR labels its records densely at coarse ranks and
sparsely at those two. Across all 15,677,623 records of v4.1:

| rank | records labelled | share |
|---|---|---|
| realm | 15,157,100 | 96.68% |
| class | 14,965,115 | 95.46% |
| **order** | 1,359,211 | **8.67%** |
| **family** | 979,864 | **6.25%** |
| genus | 32,729 | 0.21% |

Over the population the denylists are handed — after the confidence gate, which keeps 5,576,197
records — the figures are 7.87% at family and 8.85% at order. The host-association rule reads a
different field, can be evaluated on 13.71% of that population, and removes the rest for lacking
evidence rather than for failing the test (A4.1, D-081).

Three clarifications, each of which would otherwise be read into the table wrongly.

Only 3.29% of records carry no label at all. The database is well annotated; it is annotated at
ranks the policy's names do not use.

The pipeline's last rule reads coarse ranks and removes 599,507 records (3.82%) for having no realm
or stopping at one of eight named high-level taxa. It names no hazardous organism, but it is part of
the pipeline's reach and is reported with the ceiling.

The rank tallies were produced twice, by unrelated implementations re-reading the publisher's
primary table, and agree on all eight ranks and on the record total (D-082). They are robust to the
database's own v4-to-v4.1 erratum, which moves 1,300 records at family rank and the family share
from 6.24% to 6.25%.

Finally, the released corpora are less well labelled than the population they were drawn from:

| component | records | family-labelled |
|---|---|---|
| IMG/VR v4.1, after the confidence gate | 5,576,197 | 7.87% |
| Evo 1's released viral component | 2,653,047 | **2.62%** |
| Evo 2's released viral component (recovered by join) | 2,917,521 | 7.02% |

The direction is what the rules predict: a keep-list built on prokaryotic host association retains
shallowly-labelled material. Attributing the shift by route is a separate measurement.

## 4. Result 2: the denylists are lists of names, and names expire

A rule that names a taxon inherits the reference taxonomy's revisions. Replaying the policy's 31
names against taxonomy releases from its own vintage to 2026-10 (A9.1, D-201, D-202):

- *Herpesviridae* became a synonym of *Orthoherpesviridae* in January 2026. A rule naming
  *Herpesviridae* as a family scientific name now removes no herpesvirus, and its output records no
  failure. Two further names have failed the same way.
- *Reoviridae* is already not a family name in the taxonomy release this project pinned — decay at
  time zero, before any replay.
- Measured reach of the list falls from 75.83% to 65.17% over the window, at 4.34% of the viral
  taxonomy per year. New unnamed taxa (44,261) dominate the loss; renames (787), renumberings (890)
  and re-ranks (7,723) are counted separately and never summed.
- The slope is the same either side of the filter's vintage, so this is a property of specifying a
  filter as a list of names, not a criticism of one list.

A static name list and a computed rule decay differently: the realm-based rule lost 8.39% relative
against the name list's 14.06%.

## 5. Result 3: what the released corpora contain, by sequence

| release | records searched | viral Pfam families detected, of 1,719 |
|---|---|---|
| Evo 1 (`opengenome`) | 53,140 of 2,653,047 (2%) | **597** (34.7%) |
| Evo 2 (`opengenome2`) | 30,859 (1%) | **812** (47.2%) |

The profile route accounts for 590 and 811; the rest come from the integrated-element route, which
over 375 and 300 sampled bacterial genomes found 128 and 178 integrated regions carrying 203 and 251
viral families (A2.1, A2.4, A3.2, D-245, D-246).

Both counts are lower bounds, and the sampling has not saturated: deepening tenfold took Evo 1 from
470 families to 590 and Evo 2 from 492 to 811, with the accumulation curve still rising by 9% and
18% on the last doubling of records searched. The two releases are not comparable as rates — Evo 2
reaches 812 while sampled at a tenth of Evo 1's rate — and the first corpus is a deduplicated
subset of the same source database, which is the documented reason the second is richer per unit of
sequence.

### 5.1 The two instruments disagree, and the disagreement is the result

A targeted sweep of categories known to defeat taxonomic filters was run twice over the same
records of Evo 1's component: once reading labels, once reading sequence (A2.5, D-187, D-190,
D-193).

Reading labels, the component contains **no** segmented-virus records. That zero is a statement
about labels: only 2.6% of records are decidable at family rank.

Reading sequence at 10% depth, the same records carry markers of **7 of 1,285 segmented virus
families** — 57 hits in 265,062 records, 0.54% of families (0.26-1.12%). Five distinct ICTV families
are represented, and every one infects eukaryotes, in a component whose host rule exists to remove
eukaryote-infecting viruses:

| RVDB family | records | ICTV family |
|---|---|---|
| FAM000422 | 29 | Polydnaviriformidae |
| FAM007500 | 6 | Spinareoviridae (*Orthoreovirus*) |
| FAM022414 | 2 | Nanoviridae (*Babuvirus*) |
| FAM003906 | 1 | Spinareoviridae (*Orthoreovirus*) |
| FAM005477 | 1 | Geminiviridae (*Grablovirus*) |
| FAM023047 | 1 | Bromoviridae (*Ilarvirus*) |
| FAM033562 | 1 | Spinareoviridae (*Orthoreovirus*) |

*Geminiviridae* is one of the 19 families the policy denylists. *Spinareoviridae* is a successor of
*Reoviridae*, which the policy also denylists and which the pinned taxonomy no longer carries — the
two results meeting in one row.

Three features distinguish this from a threshold artefact: FAM000422 appears in all four bands, and
the bands are disjoint hash samples; three independently built RVDB families converge on
*Orthoreovirus*; and every hit cleared 50% model coverage in addition to E ≤ 1e-5, on models up to
310 residues. Two of the seven rest on short models — FAM033562 (83 residues, 7 sequences) and
FAM022414 (66 residues, 8) — and are the weakest of the set. The seven are not equivalent findings
and are not quoted as such.

What this does not assert is a conformance failure. Evo 2's records ship without taxonomy, so no
published rule can be decided on them, and the project reserves the conformance claim for
record-level evidence (A7.1). The strictest such check finds 95 records of 2,653,047 surviving a
rule the release's own metadata suffices to evaluate, all through one clause about unassigned
classification.

### 5.2 Cross-registry statements use an equal-rate pair

The second registry is measured at a tenth the depth of the first, so comparisons between
registries are read from an equal-rate pair, published as its own artefact
(`corpora/results/a3-2/equal-rate-pair`, commit `238313f`):

| release | rate | Pfam viral, of 1,719 | RVDB-prot, of 13,679 |
|---|---|---|---|
| Evo 1 (`opengenome`) | 0.002 | 470 = 27.34% [25.29, 29.50] | 572 = 4.18% [3.86, 4.53] |
| Evo 2 (`opengenome2`) | 0.001 | 492 = 28.62% [26.53, 30.80] | 1,456 = 10.64% [10.14, 11.17] |

Intervals are 95%. Both columns are the profile route alone, the only equal-rate pairing available,
since the integrated-element route sampled at a third rate. Equal sampling establishes one thing:
the gap between registries is not an artefact of depth. The two define a family differently and
their denominators differ eightfold, so neither column ranks one registry's families against the
other's, and no share from either is quoted without its denominator (D-161, D-247).

## 6. Result 4: the auditable artefact is not the trained artefact

Evo 2's released viral component is published twice, in two file formats. The arithmetic between
them suggested that 264,570 records the procedure removes had reached the training data. Both
representations were counted twice, the second time by newline counting and byte arithmetic that
never decodes or parses the content.

That suggestion is wrong, and the correct reading matters more. The representation that was trained
on matches Evo 1's released filtered output exactly — to the record and to the nucleotide, zero on
both deltas — so the filter's output was carried forward unchanged. The other representation, the
only one carrying source identifiers and hence the only one a filter can be checked against, holds
**304,448 more records** and 2.64 billion more nucleotides, including those the procedure removes
(A7.3, A7.4).

The consequence is structural rather than an accusation: two representations of one component is an
ordinary engineering convenience, and nothing in the data speaks to intent. But the filter cannot be
verified against its own product. The remedy is cheap — publish the filtered artefact in the
representation that carries identifiers, or publish the removal list — and it is item one of a
fourteen-item disclosure standard, each item of which exists because a specific audit obstacle
produced it (X5.1).

One nearby number does not survive inspection and is worth recording because it would otherwise be
repeated: 39,974 apparently repeated accessions are 39,974 surplus FASTA headers on 1,775 large
genomes published in contigs, with zero surplus records (D-225).

## 7. What this work does not establish

**No hazard assessment.** A profile hit places a protein in a sequence family at that family's
curated threshold. It says nothing about whether the sequence is functional, complete, or capable
of anything. No measurement in Phase A speaks to hazard, and none should be read that way.

**Family presence, not genome presence.** The counts are of distinct family identifiers from two
registries whose membership was fixed before any search: Pfam's selection is by its own family-level
naming, with `integrase` and `transposase` deliberately excluded because that machinery is shared
with transposons, and a clan-level selection was rejected after measuring that it would be 6,698
families of which 6,132 are not viral (D-075). The selection's known blind spot is measured and
published rather than closed: families named for a virus taxon rather than a viral structure — such
as `Ebola_NP` — fall outside the keyword rule, and the second registry, whose membership is its own
curators', is what covers them (D-083). What has *not* been measured is, per detected family,
whether that family occurs only in viruses. So the established claim is that a viral protein family
is present, not that a viral genome is.

**No claim that a filter failed to run.** On the one release where it can be checked, the filter's
output was carried forward exactly.

**Lower bounds, not population figures**, for every sampled count.

**One model family.** Two releases of one model family, on the nucleotide side. The protein-model
work is a policy comparison and a staged proxy corpus, not an audit of a released protein corpus.

**Label quality is out of scope.** Result 1 is about which ranks carry labels, not about whether
labels are correct.

## 8. What further work would add

**A census.** About 3,000 core-hours for both releases against both registries, tens of dollars at
spot prices (D-098), currently deferred by an explicit costed decision (D-247). It would convert the
headline from "at least 597 and 812" into a measured value.

**Depth parity between the registries.** About ten hours of local compute, no money. It raises a
bound rather than enabling a comparison the equal-rate pair already supports, so it is deferred,
with the guards a banded pass needs recorded: one output directory per release, an
identifier-prefix check of every published table against the release it claims to describe, and
retained band parts.

**Per-family specificity.** The limit named in §7 is measurable: for each detected family, count its
occurrence in curated non-viral reference proteomes and report detections against that background.
This would convert "viral protein family present" into a quantified statement about how
virus-specific each detection is. It is new work, not a deeper run of existing work.

**Breadth.** The audit runs behind one interface taking a policy, a corpus and a set of detectors,
against a bundled fixture in one command, so the marginal cost of the next release is staging its
corpus and transcribing its policy. Both the disclosure standard and Results 1 and 2 generalise
only as far as the number of policies tested.

**Disclosure.** Nothing here has left the project, and nothing should until the organisations
concerned have been contacted and given time to respond. That is weeks of calendar time and the
least automatable part of the work.

## References

1. Nguyen E. *et al.* Sequence modeling and design from molecular to genome scale with Evo.
   *Science* (2024). doi:[10.1126/science.ado9336](https://doi.org/10.1126/science.ado9336)
2. Brixi G. *et al.* Genome modelling and design across all domains of life with Evo 2. *Nature*
   (2026). doi:[10.1038/s41586-026-10176-5](https://doi.org/10.1038/s41586-026-10176-5); preprint
   doi:[10.1101/2025.02.18.638918](https://doi.org/10.1101/2025.02.18.638918)
3. `LongSafari/open-genome` dataset card, HuggingFace, retrieved 2026-10-13 and stored with digest
   as source `S-OPENGENOME1-CARD`.
4. `arcinstitute/opengenome2` dataset card, HuggingFace, retrieved 2026-10-13 and stored with digest
   as source `S-OPENGENOME2-CARD`.
5. Camargo A. P. *et al.* IMG/VR v4: an expanded database of uncultivated virus genomes within a
   framework of extensive functional, taxonomic, and ecological metadata. *Nucleic Acids Research*
   (2023). doi:[10.1093/nar/gkac1037](https://doi.org/10.1093/nar/gkac1037)
6. Hyatt D. *et al.* Prodigal: prokaryotic gene recognition and translation initiation site
   identification. *BMC Bioinformatics* **11**, 119 (2010).
   doi:[10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119)
7. Larralde M. Pyrodigal: Python bindings and interface to Prodigal. *Journal of Open Source
   Software* **7**(72), 4296 (2022). doi:[10.21105/joss.04296](https://doi.org/10.21105/joss.04296)
8. Eddy S. R. Accelerated profile HMM searches. *PLoS Computational Biology* **7**(10), e1002195
   (2011). doi:[10.1371/journal.pcbi.1002195](https://doi.org/10.1371/journal.pcbi.1002195)
9. Mistry J. *et al.* Pfam: the protein families database in 2021. *Nucleic Acids Research*
   **49**(D1), D412-D419 (2021). doi:[10.1093/nar/gkaa913](https://doi.org/10.1093/nar/gkaa913).
   Release 38.2 (EMBL-EBI, 2026-01-22) is pinned by versioned release directory and digest (D-075).
10. Bigot T., Temmam S., Pérot P., Eloit M. RVDB-prot, a reference viral protein database and its
    HMM profiles. *F1000Research* **8**, 530 (2019; v2 2020).
    doi:[10.12688/f1000research.18776.2](https://doi.org/10.12688/f1000research.18776.2). v32.0,
    13,679 profiles, pinned against the release's own metadata file (D-075).
11. Camargo A. P. *et al.* Identification of mobile genetic elements with geNomad. *Nature
    Biotechnology* (2024).
    doi:[10.1038/s41587-023-01953-y](https://doi.org/10.1038/s41587-023-01953-y)

Identifiers of the form A2.1 (tasks) and D-075 (decisions) refer to this project's own task files
and append-only decision log, which are not public.

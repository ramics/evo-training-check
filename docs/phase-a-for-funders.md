# The paragraph nobody checks

**A published model release says it removed a category of sequence from its training data. Here is
what happens when you try to verify that against the files it published.**

Draft of 2026-10-22. Internal to the project: `AGENTS.md` holds findings inside the project until
the responsible-disclosure task (X3.1) has run, and that gate has not opened. Written for a reader
comfortable with software, statistics and the AI-safety literature, who knows no biology. Sources
are at the end; this project's own measurements cite the task and decision identifiers that carry
them, which are not public.

---

## A paragraph everyone trusts and nobody checks

Somewhere in the release materials of most frontier biological sequence models there is a short
paragraph about what was removed from the training data. It names a public database, names a class
of organism the authors judged hazardous, and gives a rule or two for what counts as belonging to
that class. The two Evo releases are the clearest case to work with, because both state such a
policy and both publish their training corpora openly, as `OpenGenome` and `OpenGenome2` [1-4].

Both state the exclusion in the same terms — "we excluded viral genomes that infect eukaryotic
hosts", with the stated aim that an openly shared model should not "disseminate the capability to
manipulate and design pathogenic human viruses" [1,2]. The methods then make that concrete as a
short pipeline over one source database, IMG/VR [5]: keep only records the database itself flags
as high-confidence, keep one representative per viral operational taxonomic unit, keep only
records whose taxonomic classification has been seen in a prokaryotic host at least twice, then
remove anything assigned to one of 19 named virus families or 12 named orders, then remove records
too taxonomically unspecific to place.

That paragraph is load-bearing. It is why a release can be described as having handled a category
of risk at the data layer, which is the cheapest and most durable place to handle it, and it is
cited in governance arguments about whether open weights are safe to publish. A great deal of
inference rests on it.

Almost none of it is checked, for mundane reasons. The policy is prose, so there is nothing to
run. The filter's implementation is not released. The corpora are millions of records, so nobody
reads them. And the authors have already done the work once and have no reason to audit
themselves.

Three questions follow, and this project answers all three:

1. **How much of its input could the policy ever act on?** Every rule reads a metadata field, and
   a rule can only discriminate on records that carry that field.
2. **Is the material the policy excludes detectably present in what was released?**
3. **Can the claim be verified against the artefact the filter produced?**

## Two kinds of search, which must not be confused

Everything in this piece turns on a distinction that is easy to lose, so it comes before the
results.

**The filter searches labels.** Every rule in the published pipeline reads a metadata field
attached to a record by the source database — a confidence flag, a cluster identifier, a host
prediction, a rank in a taxonomic lineage. No rule reads the sequence itself. The filter asks "what
does this record's annotation say it is?" and acts on the answer. This matters because annotation
is incomplete, is produced by a separate pipeline with its own error rate, and is organised at
ranks that need not match the ranks a policy names.

**This audit searches sequence.** The detection pass never looks at a record's labels. It
translates the record into its protein content with a standard gene caller [6,7] and searches that
content with profile hidden Markov models [8] against version-pinned public registries of sequence
families: Pfam 38.2, from which a frozen keyword rule selects 1,719 viral families out of 30,134
[9], and RVDB-prot v32.0, with 13,679 families [10]. A family is counted as present when a hit
clears a threshold fixed and recorded before any result was inspected. The question is "what is in
this sequence, regardless of what the label says?"

The two searches are therefore independent instruments, and that independence is what makes the
audit possible at all: a record whose annotation carries no family assignment is invisible to the
filter's family rule and perfectly visible to a profile search.

### The methods, concretely

**Policy to specification.** Each published statement is transcribed into a machine-checkable spec
whose quotations are verified byte-for-byte against a stored capture of the source, so a quote
cannot drift from what the source says. Each spec is then executed in three readings — literal,
charitable and strict — because the prose admits all three, and the spread between readings is
reported rather than hidden in a choice. On these corpora the three readings return identical
counts, which is a fact about this corpus's metadata and not a general claim that the prose is
reproducible (D-221).

**Corpus through policy.** Every record is passed through each reading and comes out labelled:
removed by a named rule, retained, or *unresolved* because the release does not carry the field
that rule reads. Keeping "no verdict" as its own outcome is the most consequential design decision
in the audit; treating an absent field as an empty one would have reported a whole component as
cleanly removed by a rule whose input nobody can see.

**Detection by sequence, route one.** Genes are called with Prodigal in metagenomic mode
(`pyrodigal` 3.7.1, vendoring Prodigal 2.6.3) rather than by six-frame translation, because that
is the caller IMG/VR's own annotation pipeline uses (D-077). Thresholds are bit scores, or
E-values against a pinned database size: Pfam's own per-family gathering cutoffs, used as
published, and RVDB's published rule of E ≤ 1e-5 evaluated at a pinned database size. The reason
is specific — a sequence E-value scales with the number of targets searched, so a fixed E-value
cut-off corresponds to a different bit score on a sample than on a whole corpus, and a headline
built on one would drift with how much corpus a run happened to read (D-076).

**Sampling.** A full search is not expensive but arithmetically out of reach: about 40,000
core-hours for one release against one registry, measured on this project's own hardware. So
membership is a deterministic function of the record identifier and a pinned seed —
`blake2b(key=seed, record_id)` below `rate · 2⁶⁴`, seed 20261015 — fixed before any search ran
(D-078). Two consequences matter. Samples at different rates are nested, so a deeper pass contains
the shallower one and the two can be compared directly. And every figure from a sampled pass is a
lower bound, because a family is counted only when a sampled record carried it.

**Detection by sequence, route two.** The same profile search is applied to material integrated
into bacterial genomes, which the published policy does not address at all: a search of both
papers finds no mention of proviruses, endogenous elements or integrated viruses as a curation
concern. Candidate integrated regions are identified with geNomad [11] over a sample of the
bacterial component, and the profile search then runs on those regions.

**Verification.** A headline number is not treated as a result until a second module, written
without reading the first, reproduces it from different intermediates: primitive detection rows
rather than aggregates, denominators rebuilt from the pinned registry files, the policy
re-executed independently. 334 numbers were compared across 16 reported groups; every headline
figure agreed exactly, and the one surviving disagreement — how a family's records are apportioned
between the two routes, which no headline passes through — is published with the single family
that accounts for most of it (A3.3, D-215).

## Finding 1: the rules that name a hazard can see a sliver of their input

The two rules that name specific organisms key on the family and order ranks of a record's
taxonomic lineage. IMG/VR labels its records richly at coarse ranks and sparsely at exactly those
two. Across all 15,677,623 records of IMG/VR v4.1:

| rank | records labelled | share |
|---|---|---|
| realm | 15,157,100 | 96.68% |
| class | 14,965,115 | 95.46% |
| **order** | 1,359,211 | **8.67%** |
| **family** | 979,864 | **6.25%** |
| genus | 32,729 | 0.21% |
| species | 6,630 | 0.04% |

So the 19-family list can discriminate on 6.25% of the database and the 12-order list on 8.67%.
Over the population those rules are actually handed, after the confidence gate that runs first and
keeps 5,576,197 records, the figures are 7.87% and 8.85%. The host-association rule, which reads a
different field, can be evaluated on 13.71% of that population and removes the remainder *for
lacking the evidence* — a different act from examining them (A4.1, D-081).

**Three things this finding is not**, because each is a reading the data does not support.

*It is not a claim that the filter can only touch 6% of the corpus.* The pipeline's last step is a
specificity rule which reads coarse ranks — it removes records with no realm assignment at all, or
assigned only up to one of eight named high-level taxa — and that rule removes 599,507 records,
3.82% of the release. It names no hazard and discriminates nothing, but it is a real backstop and
it ships beside the ceiling rather than being left out of it.

*It is not an artefact of sparse annotation in general.* Only 3.29% of records fill no rank at all.
The component is well annotated; it is annotated at the wrong ranks for the rules written against
it. The two are different findings and only the second is true here.

*It is not one implementation's view of one file.* The rank tallies were produced twice by
unrelated implementations, re-reading the publisher's own primary table rather than reusing an
earlier scan, and they agree on all eight ranks, on the 15,677,623 total, on the confidence split
and on the host-domain tallies (D-082). The figure is also robust to the database's own v4-to-v4.1
erratum, which moves 1,300 records at family rank and the ceiling from 6.24% to 6.25%. An internal
consistency check holds in both populations: the classification-method field is empty on exactly
the records that fill no rank.

**And the released corpus is worse labelled than the database it was selected from.**

| component | records | family-labelled |
|---|---|---|
| IMG/VR v4.1, after the confidence gate | 5,576,197 | 7.87% |
| Evo 1's released viral component | 2,653,047 | **2.62%** |
| Evo 2's released viral component (recovered by join) | 2,917,521 | 7.02% |

Evo 1's release is a third as well labelled at family as the population it was drawn from. The
direction is what the rules predict rather than a surprise — a keep-list built on prokaryotic host
association retains exactly the shallowly-labelled material — and attributing it by route is a
separate question this measurement does not answer.

This is the most transferable result in Phase A. It depends on nothing biological, it applies to
any exclusion rule keyed on third-party metadata, and computing it for a new filter is an
afternoon's work: take the field the rule keys on, count how many records in the target database
carry it, and report the share both over the database and over the population the rule actually
sees. Any release stating a metadata-keyed exclusion policy could publish that number alongside
it. None does.

## Finding 2: material the policy excludes is detectably present in what was released

Searching surviving records by sequence, at the depth sampled:

| release | records searched | viral families detected (of 1,719) |
|---|---|---|
| Evo 1 (`opengenome`) | 53,140 of 2,653,047 (2%) | **597** (34.7%) |
| Evo 2 (`opengenome2`) | 30,859 (1%) | **812** (47.2%) |

The profile search alone accounts for 590 and 811; the remainder come from the integrated-element
route, which over 375 and 300 sampled bacterial genomes found 128 and 178 integrated regions
carrying 203 and 251 viral families between them (A2.1, A2.4, A3.2, D-245, D-246).

Three qualifications travel with these numbers wherever they go.

**They are lower bounds**, for the sampling reason given above: a family is counted only when a
sampled record carried it.

**The ceiling was not found.** Deepening the sample tenfold raised the counts steeply rather than
settling them — Evo 1 from 470 families to 590, Evo 2 from 492 to 811 — and the accumulation curve
was still climbing on the last doubling of records searched, by 9% and 18%. A quantity that nearly
doubles when you look twice as hard is a floor.

**The two releases are not comparable as rates.** Evo 2 reaches 812 families while sampled at a
tenth of Evo 1's rate. Whatever differs between the releases, this table does not measure it. There
is a structural reason the second corpus is richer per unit of sequence — the first publishes a
deduplicated subset of the same source database — and that explanation was in hand before the
measurement rather than fitted to it.

A deliberately stricter question is kept separate. How many records survive a rule the release's
own metadata is *sufficient* to evaluate? 95 of 2,653,047, all through a single clause about
unassigned classification (A7.1). Presence in the corpus and demonstrable non-conformance with the
written policy are different claims with different evidential bars, and only the second is an
inconsistency finding. It is small, and saying so is part of the result.

**The second registry is measured at a tenth the depth of the first**, so cross-registry statements
are read from an equal-rate pair, published as its own artefact — a recount over tables already in
the store, which refuses to run if a part names the wrong release or a source was sampled at a rate
its row does not claim (`corpora/results/a3-2/equal-rate-pair`, commit `238313f`):

| release | rate | Pfam viral, of 1,719 | RVDB-prot, of 13,679 |
|---|---|---|---|
| Evo 1 (`opengenome`) | 0.002 | 470 = 27.34% [25.29, 29.50] | 572 = 4.18% [3.86, 4.53] |
| Evo 2 (`opengenome2`) | 0.001 | 492 = 28.62% [26.53, 30.80] | 1,456 = 10.64% [10.14, 11.17] |

Intervals are 95%. Both columns are the profile search alone, which is the only genuinely
equal-rate pairing, since the integrated-element route sampled at a third rate again; the merged
protein counts, 582 and 1,483, are recorded in the artefact beside these with the reason they
differ. What equal sampling establishes is one thing only: the gap between the registries is not an
artefact of depth. The two define a family differently and their denominators differ eightfold, so
neither column says that one registry's families are more or less likely to survive than the
other's — and no percentage from either is quoted without naming its denominator in the same
sentence (D-161, D-247).

## Finding 3: the artefact you can audit is not the artefact that was trained on

Evo 2's released viral component is published twice, in two different file formats. The arithmetic
between them suggested that 264,570 records which the published procedure removes had nonetheless
reached the training data. The alternative — that the larger file was a pre-filter staging artefact
— had to be ruled in or out, so both representations were counted twice, the second time by newline
counting and byte arithmetic that never decodes or parses the content.

The alarming reading is wrong, and the correct reading matters more. The representation that was
trained on matches Evo 1's released filtered output exactly, to the record and to the nucleotide,
zero difference on both deltas: the filter's output was carried forward unchanged. But the *other*
representation — the only one carrying the source identifiers against which a filter can be checked
at all — holds **304,448 more records** and 2.64 billion more nucleotides, among them the records
the published procedure removes (A7.3, A7.4).

So the filter demonstrably did its job on what was trained, and the only artefact anyone can verify
that against is a different, larger set. The filter cannot be checked against the thing the filter
produced. Nothing in the data speaks to intent, and two representations of one component is an
ordinary engineering convenience whose consequence for auditability was probably invisible from
inside.

One nearby anomaly dissolved on inspection, which is worth a sentence because it is the kind of
number that gets repeated: 39,974 apparently repeated accessions are 39,974 surplus FASTA headers
on 1,775 large genomes published in contigs, with zero surplus records (D-225).

This is the finding most likely to change practice, because the remedy is nearly free: publish the
filtered artefact in the representation that carries identifiers, or publish the removal list.
Phase A's companion output is a fourteen-item disclosure standard in which every item exists
because a specific audit obstacle produced it (X5.1).

## What the numbers rest on

The project's working rule is that a figure is not a result until it can be regenerated from pinned
inputs, and the practices that enforce it are the ones above rather than a claim of care:
thresholds fixed and recorded before any hits were seen; sampling defined by a seeded hash so that
samples nest and runs reproduce; registries pinned by versioned release directory and digest, never
by a moving `current_release` pointer; three policy readings executed rather than one chosen;
absent metadata kept as `unresolved` instead of being read as empty; headline counts reproduced by
a second implementation from different intermediates; and a decision log that records corrections
as new entries rather than edits, so a withdrawn figure and the reasoning that withdrew it both
stay visible.

Two checks have earned particular weight. Re-running a whole pass from its pins catches faults in
how a result was assembled, which checks on a result's shape — band coverage, sample nesting,
per-source counts, denominators — provably do not. And requiring that a harness reproduce a
published reference column, wherever one exists, catches implementation faults that no amount of
reading the code reliably finds.

## What this does not show

- **Nothing about intent.** The measurements support a mismatch between a stated procedure and a
  published artefact, and say nothing about what anyone meant to do.
- **No claim that a filter failed to run.** On the one release where it can be checked, the
  filter's output was carried forward exactly.
- **No capability claim.** That a sequence family is present in a corpus is not a statement that a
  model trained on that corpus can do anything in particular. That is the next phase's question,
  measured against published benchmarks, and it is not answered here.
- **Not population figures.** Every survival count is a lower bound from a 1–2% sample.
- **One model family, properly.** The nucleotide work covers two releases of one family. The
  protein-model arm is a policy comparison and a staged proxy corpus, not an audit of a released
  protein corpus.
- **No claim about annotation quality in general.** The ceiling is about which ranks carry labels,
  not about whether the labels are right. Benchmarking the annotation tools themselves is a
  separate measurement in this project and a separate claim.

## What a funded continuation buys

Phase A was built by one person, with cloud compute measured in single-digit dollars. That sets the
scale of what follows: the binding constraints are skilled time and engineering discipline, not
hardware. Four items, in the order I would spend on them.

**1. Turn the lower bounds into population figures.** The survival counts come from a 1–2% sample
of a corpus whose accumulation curve has not flattened, and the full pass against the curated
registry is a few thousand core-hours — tens of dollars at spot prices. It is currently deferred by
an explicit decision with its costing recorded, not left hanging (D-247). It converts the headline
from "at least 34.7% and 47.2%" into a measured value, and it is the highest-value purchase in the
project.

**2. Deepen the second registry.** About ten hours of local compute and no money, deliberately not
spent yet: the equal-rate pair above already supports every cross-registry statement the piece
makes, so the deeper pass would raise one bound rather than enable a comparison. Funded, it comes
with the structural guards a banded pass needs — a separate output directory per release, an
identifier-prefix check of every published table against the release it claims to describe, and
retained band parts — and it brings a registry currently measured a tenth as deep as its neighbour
up to parity.

**3. Extend beyond one model family.** The audit is packaged behind a single interface that takes a
policy, a corpus and a set of detectors, and runs against a bundled fixture in one command. The
marginal cost of auditing the next release is staging its corpus and transcribing its policy. Both
the disclosure standard and the metadata-ceiling finding gain most of their force from breadth: one
release is an anecdote, six is a practice.

**4. Run the disclosure process.** Nothing here has left the project, by the project's own rule, and
nothing should until the organisations concerned have been contacted and given time to respond.
Doing that well takes weeks of calendar time and a person who will write carefully and wait. It is
the step that decides whether the work changes anything, and the least automatable part of it.

### What the work demonstrates, as distinct from what it found

The audit exists as reusable tooling with pinned inputs, pre-registered thresholds and a
second-implementation requirement, rather than as a notebook that produced a number once. Its most
transferable finding is a method — measure what share of a database a rule's key field can even
reach — that any lab can apply to any metadata-keyed filter in an afternoon. And the distinction it
is built on, between searching labels and searching sequence, is the one that governance arguments
about data filtering need and rarely make: a filter's guarantee is only ever as strong as the
annotation it reads, and that strength is measurable.

## References

1. Nguyen E. *et al.* Sequence modeling and design from molecular to genome scale with Evo.
   *Science* (2024). doi:[10.1126/science.ado9336](https://doi.org/10.1126/science.ado9336)
2. Brixi G. *et al.* Genome modelling and design across all domains of life with Evo 2.
   *Nature* (2026). doi:[10.1038/s41586-026-10176-5](https://doi.org/10.1038/s41586-026-10176-5);
   preprint doi:[10.1101/2025.02.18.638918](https://doi.org/10.1101/2025.02.18.638918)
3. `LongSafari/open-genome` dataset card, HuggingFace (OpenGenome v1), retrieved 2026-10-13 and
   stored with digest as source `S-OPENGENOME1-CARD`.
4. `arcinstitute/opengenome2` dataset card, HuggingFace, retrieved 2026-10-13 and stored with
   digest as source `S-OPENGENOME2-CARD`.
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
   **49**(D1), D412–D419 (2021). doi:[10.1093/nar/gkaa913](https://doi.org/10.1093/nar/gkaa913).
   Release 38.2 (EMBL-EBI, 2026-01-22) is pinned here by versioned release directory and digest
   (D-075).
10. Bigot T., Temmam S., Pérot P., Eloit M. RVDB-prot, a reference viral protein database and its
    HMM profiles. *F1000Research* **8**, 530 (2019; v2 2020).
    doi:[10.12688/f1000research.18776.2](https://doi.org/10.12688/f1000research.18776.2). v32.0,
    13,679 profiles, pinned against the release's own metadata file (D-075).
11. Camargo A. P. *et al.* Identification of mobile genetic elements with geNomad. *Nature
    Biotechnology* (2024).
    doi:[10.1038/s41587-023-01953-y](https://doi.org/10.1038/s41587-023-01953-y)

Internal identifiers of the form A2.1, A7.3, X5.1 (tasks) and D-075, D-245 (decisions) refer to
this project's own task files and decision log, which are not public.

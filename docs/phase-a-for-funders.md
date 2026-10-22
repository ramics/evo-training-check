# Auditing a training-data exclusion policy

Draft of 2026-10-22, internal to the project. `AGENTS.md` holds findings inside the project until
the responsible-disclosure task (X3.1) has run, and that gate remains closed. Citations of the form
(Author Year) are listed at the end; identifiers of the form A2.1 and D-075 refer to this project's
task files and append-only decision log, which are private.

## Abstract

The published release materials of Evo 1 and Evo 2 state that viral genomes infecting eukaryotic
hosts were excluded from the training corpora, and both releases publish those corpora openly
(Nguyen et al. 2024, Brixi et al. 2026). This study executes the stated policy against the released
artefacts and searches the surviving records for the material the policy describes.

Four results follow. First, the two rules that name organisms key on the family and order ranks of
a record's taxonomic lineage, and the source database labels 6.25% of its 15,677,623 records at
family rank and 8.67% at order rank (Camargo et al. 2023); over the population the rules are handed
those shares are 7.87% and 8.85%, and Evo 1's released component carries a family label on 2.62% of
records. Second, the denylists are enumerations of names, and names expire. Three of the 31 names
have ceased to denote what they denoted when the policy was written, among them *Herpesviridae*,
which became a synonym of *Orthoherpesviridae* in January 2026, so that a rule naming it now reaches
no herpesvirus while reporting success; measured reach of the list fell from 75.83% to 65.17% of the
viral taxonomy, at 4.34% per year. Third, profile search finds at least 597 of 1,719 viral Pfam
families in Evo 1's component and 812 in Evo 2's, each a lower bound from a 1-2% sample whose
accumulation curve continues to rise. In a targeted sweep of Evo 1's component the taxonomic labels
report zero segmented-virus records while profile search over the same records recovers markers of
five eukaryote-infecting virus families, one of them named on the policy's own denylist. Fourth, Evo
2 publishes its viral component in two representations: the one that was trained on reproduces Evo
1's filtered output exactly, while the only one carrying source identifiers holds 304,448 additional
records, including those the policy removes, so the filter admits audit only against an artefact
other than its own product.

Specificity of the family universe was measured against the reviewed section of UniProtKB (UniProt
Consortium 2025), with InterPro as a second instrument (Blum et al. 2025). Of the 1,719 families,
1,265 occur only in viruses in the curated data, 212 occur outside viruses, and 242 are absent from
the curated section; of the 1,477 that admit a verdict, 85.6% are virus-only, and the median shared
family appears in a single non-viral organism. The most heavily shared family is also among the most
frequently detected, `PF00589 Phage_integrase`, at 421 reviewed non-viral entries across 280
organisms against 21 viral. These shares describe the universe, and the measurement restricted to
the detected families remains outstanding.

One boundary applies throughout. A profile hit establishes membership of a sequence family at that
family's curated threshold, which is weaker than a statement about function and far weaker than one
about hazard. Hazard assessment lies outside this work.

## 1. The claim worth checking

The exclusion paragraph in a model release carries weight. It supports the description of a release
as having addressed a category of risk at the data layer, and it is cited in arguments about the
safety of publishing open weights.

Verification is rare, for practical reasons. The policy exists as prose, the filter's
implementation is unpublished, and the corpora run to millions of records. The Evo releases
are the most tractable case available, because each states a policy and each publishes its corpus.

Applied to IMG/VR, the stated procedure runs in five steps: retain records the database flags as
high-confidence; retain one representative per viral operational taxonomic unit; retain records
whose taxonomic classification has been observed in a prokaryotic host at least twice; remove
records assigned to any of 19 named virus families or 12 named orders; and remove records assigned
no realm, or assigned no deeper than one of eight named high-level taxa (Nguyen et al. 2024, Brixi
et al. 2026).

Three questions follow from that procedure, and this study answers each: how much of its input can
the policy act upon, whether the excluded material is detectable in the released corpora, and
whether the claim can be verified against the artefact the filter produced.

## 2. Method

### 2.1 Label search and sequence search

Each rule in the published pipeline reads a metadata field that the source database attached to a
record: a confidence flag, a cluster identifier, a host prediction, or a rank in a taxonomic
lineage. The pipeline therefore asks what a record's annotation declares it to be.

The detection pass works from sequence alone. Records are translated into protein coding sequence
with Prodigal in metagenomic mode, the gene caller IMG/VR's own annotation pipeline uses (Hyatt et
al. 2010, Larralde 2022, D-077), and the resulting proteins are searched with profile hidden Markov
models (Eddy 2011) against two version-pinned registries: Pfam 38.2, from which a frozen keyword
rule selects 1,719 viral families of 30,134 (Paysan-Lafosse et al. 2025, D-075), and RVDB-prot
v32.0, with 13,679 families (Bigot et al. 2019).

The independence of the two instruments is what makes the audit possible. A record carrying no
family label falls outside the reach of the filter's family rule while remaining fully visible to a
profile search.

### 2.2 Thresholds

Pfam's per-family gathering cutoffs are used as published, and RVDB-prot uses its publisher's rule
of E ≤ 1e-5 evaluated against a pinned database size. The pinning matters: a sequence E-value scales
with the number of targets searched, so one E-value cutoff implies different bit scores on a sample
and on a whole corpus, and a headline built that way would drift with the volume of corpus a run
happened to read (D-076). Thresholds were recorded before any hit was inspected.

### 2.3 Sampling

Sample membership is a deterministic function of the record identifier and a pinned seed:
`blake2b(key=seed, record_id)` below `rate · 2⁶⁴`, seed 20261015, fixed before the first search
(D-078). Two properties follow. Samples at successive rates nest, so a deeper pass extends the
shallower one and the two compare directly. And each count is a lower bound, since a family enters
the count only when a sampled record carried it.

A full census costs about 3,000 core-hours across both releases and both registries, tens of dollars
at spot prices, and remains unpurchased (D-098, which supersedes an earlier estimate thirty times
too high).

### 2.4 Second detection route

A second route covers material integrated into bacterial genomes, a case the policy leaves
unaddressed: a whole-document search of both papers returns no occurrence of prophage, provirus,
endogenous or integrated element in a data-curation context. Candidate integrated regions are called
with geNomad (Camargo et al. 2024) and searched with the same profiles.

### 2.5 Verification

Each policy executes in three readings — literal, charitable and strict — and the spread between
them is reported as a result; on these corpora the three readings agree exactly
(D-221). A record whose verdict depends on a field the release omits is recorded as `unresolved`,
which is held apart from retention throughout.

Headline counts are reproduced by a second implementation written without reading the first, from
primitive detection rows rather than aggregates, with denominators rebuilt from the pinned registry
files: 334 numbers across 16 reported groups, every headline figure identical (A3.3, D-215). Where a
measurement depends on parsing an external reference, agreement is sought from a second instrument
joining through a different source, since a re-run reproduces a parse error faithfully while an
independent join exposes it.

## 3. Result 1: the reach of the rules that name organisms

The two denylists key on family and order. IMG/VR labels its records densely at coarse ranks and
sparsely at those two. Across all 15,677,623 records of v4.1:

| rank | records labelled | share |
|---|---|---|
| realm | 15,157,100 | 96.68% |
| class | 14,965,115 | 95.46% |
| order | 1,359,211 | 8.67% |
| family | 979,864 | 6.25% |
| genus | 32,729 | 0.21% |

Over the population the denylists are handed, after the confidence gate retains 5,576,197 records,
the shares are 7.87% at family and 8.85% at order. The host-association rule reads a different field,
admits evaluation on 13.71% of that population, and removes the remainder for want of evidence
(A4.1, D-081).

Three clarifications keep the table from being read too widely. Labels are present at some rank for
96.71% of records, so the database is well annotated and annotated at ranks the policy's names leave
unused. The pipeline's final rule reads coarse ranks and removes 599,507 records, 3.82% of the
release, for having no realm or terminating at one of eight named high-level taxa; it names no
hazardous organism, and it forms part of the pipeline's reach. And the rank tallies come from two
unrelated implementations, each re-reading the publisher's primary table, which agree on all eight
ranks and on the record total (D-082); they also survive the database's own v4-to-v4.1 erratum,
which moves 1,300 records at family rank and the family share from 6.24% to 6.25%.

The released corpora are labelled more sparsely than the population they were drawn from:

| component | records | family-labelled |
|---|---|---|
| IMG/VR v4.1, after the confidence gate | 5,576,197 | 7.87% |
| Evo 1's released viral component | 2,653,047 | 2.62% |
| Evo 2's released viral component (recovered by join) | 2,917,521 | 7.02% |

The direction follows from the rules, since a keep-list built on prokaryotic host association retains
the shallowly-labelled material. Attribution of the shift by route belongs to a separate
measurement.

## 4. Result 2: a denylist of names ages

A rule that names a taxon inherits every subsequent revision of the reference taxonomy. Replaying
the 31 names against quarterly NCBI Taxonomy releases from 2020-01 to 2026-10, with the baseline at
2023-04 (Schoch et al. 2020, A9.1, D-201, D-202), gives four findings.

Three names have ceased to resolve. *Herpesviridae* became a synonym of *Orthoherpesviridae* in
January 2026, so a rule naming *Herpesviridae* as a family scientific name reaches no herpesvirus
and reports success while doing so; *Orthopolintovirales* failed the same way in the same release;
and *Reoviridae* had already ceased to be a family name in the taxonomy release this project pinned,
making it decay present at time zero.

Reach falls from 75.83% to 65.17% across the window, at 4.34% of the viral taxonomy per year. New
material dominates that loss: 44,261 viral taxa present at 2026-10 are absent from the baseline,
unreachable from it through NCBI's merge records, and named by nothing in the list, which is 15.18%
of the current viral taxonomy. Churn is smaller and is counted separately: 787 renamed, 890
renumbered, 7,723 re-ranked.

A computed rule ages more slowly. Descent from an ICTV realm, asked of each release, covers 96.57%
at the baseline and 88.47% at 2026-10, a relative decline of 8.39% against the name list's 14.06%.
Its floor is the taxonomy's own completeness, since 11.5% of viral taxa at 2026-10 descend from no
realm.

The slope is equal either side of the filter's own vintage, so the finding concerns the practice of
specifying a filter as an enumeration of names, and applies to any such list.

### 4.1 Why the renames were left unresolved

Three reasons, in order of weight.

Resolution would recover little. Of the gap at 2026-10, renaming accounts for 787 taxa against
44,261 that no name reaches, so resolving every synonym restores three names and reaches none of the
new material.

Resolution can enlarge a rule silently. *Reoviridae* survives in the pinned taxonomy as a synonym of
*Reovirales*, an order rather than a family, so following that synonym converts a family rule into
an order rule: on the corpus used for the cross-filter comparison, an additional 90,530 records at
90% identity. The looser reading is computed as a separate quantity, `loose_only_members`, and is
held out of every result (D-199).

Where a literal reading measures vocabulary rather than the filter, the audit does substitute and
declares it. The specificity rule declares `require_rank: realm`, a rank NCBI has never used; run
literally it finds a realm on no record and removes the whole viral corpus, reporting a unit
mismatch as a filter result. It is therefore resolved to descent from one of the six ICTV realms,
and the substitution travels in the artefact's `name_resolution` field. The line held is between a
rule that cannot execute, which the audit repairs and declares, and a rule that executes and fails,
which the audit reports.

The constructive reading is that durability is achievable. A rule that resolves taxa through the
reference's own synonym and merge records, pinned to a dated release and re-validated on a stated
interval, ages more slowly and ages visibly. At 4.34% per year, holding unnamed new material below
1% requires re-validation about every 0.2 years. The disclosure standard arising from this work asks
in item C1 for annotation sources cited as dated releases with digests; this result argues for a
companion item requiring a stated re-validation interval wherever a rule is written as a list of
names.

## 5. Result 3: the contents of the released corpora

| release | records searched | viral Pfam families detected, of 1,719 |
|---|---|---|
| Evo 1 (`opengenome`) | 53,140 of 2,653,047 (2%) | 597 (34.7%) |
| Evo 2 (`opengenome2`) | 30,859 (1%) | 812 (47.2%) |

The profile route accounts for 590 and 811 of those families. The remainder arrive by the integrated
route, which over 375 and 300 sampled bacterial genomes called 128 and 178 integrated regions
carrying 203 and 251 viral families between them (A2.1, A2.4, A3.2, D-245, D-246).

Both counts are lower bounds, and the sampling continues to yield. A tenfold deepening took Evo 1
from 470 families to 590 and Evo 2 from 492 to 811, with the accumulation curve rising by 9% and 18%
on the last doubling of records searched. The two releases stand at different sampling rates, Evo 2
reaching 812 families at a tenth of Evo 1's rate, so this table ranks neither release against the
other; Evo 1's corpus is a deduplicated subset of the same source database, which accounts for the
second corpus being richer per unit of sequence.

A stricter question is kept separate. Of Evo 1's 2,653,047 records, 95 survive a rule the release's
own metadata suffices to evaluate, all of them through a single clause about unassigned
classification (A7.1). Presence in a corpus and demonstrable non-conformance with a written policy
are distinct claims carrying different evidential burdens, and only the second is an inconsistency
finding. It is small, and the smallness is part of the result.

### 5.1 The two instruments disagree, and the disagreement is the finding

A sweep of the categories known to defeat taxonomic filters ran twice over the same records of Evo
1's component, once on labels and once on sequence (A2.5, D-187, D-190, D-193).

On labels, the component holds zero segmented-virus records. That zero describes the labels, since
2.6% of records admit a verdict at family rank.

On sequence at 10% depth, the same records carry markers of 7 of 1,285 segmented virus families: 57
hits in 265,062 records, a family-level share of 0.54% (0.26-1.12%). Five families of the ICTV
taxonomy are represented, each of them eukaryote-infecting, in a component whose host rule exists to
remove eukaryote-infecting viruses:

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
*Reoviridae*, which the policy also denylists and which the pinned taxonomy no longer carries, so
the two results meet in a single row.

Three features separate this from a threshold artefact: FAM000422 appears in all four bands, and the
bands are disjoint hash samples; three independently built RVDB families converge on *Orthoreovirus*;
and every hit cleared 50% model coverage in addition to E ≤ 1e-5, on models as long as 310 residues.
Two of the seven rest on short models, FAM033562 at 83 residues over 7 sequences and FAM022414 at 66
residues over 8, and rank as the weakest of the set. The seven differ in strength and are reported
individually for that reason.

Conformance is left open here. Evo 2's records ship without taxonomy, so no published rule admits a
verdict on them, and the conformance claim is reserved for record-level evidence under A7.1.

### 5.2 Cross-registry comparison at equal rate

The second registry stands at a tenth the depth of the first, so comparisons between registries are
read from an equal-rate pair, published as its own artefact (`corpora/results/a3-2/equal-rate-pair`,
commit `238313f`):

| release | rate | Pfam viral, of 1,719 | RVDB-prot, of 13,679 |
|---|---|---|---|
| Evo 1 (`opengenome`) | 0.002 | 470 = 27.34% [25.29, 29.50] | 572 = 4.18% [3.86, 4.53] |
| Evo 2 (`opengenome2`) | 0.001 | 492 = 28.62% [26.53, 30.80] | 1,456 = 10.64% [10.14, 11.17] |

Intervals are 95%. Both columns report the profile route alone, the one available equal-rate
pairing, since the integrated route sampled at a third rate. Equal sampling establishes a single
point: depth does not account for the gap between the registries. The two registries define a family
differently and their denominators differ eightfold, so each column stands alone, and every share
from either carries its denominator in the same sentence (D-161, D-247).

### 5.3 Specificity of the family universe

The pinned universe was measured against the reviewed section of UniProtKB at release 2026_03,
575,748 entries read against the release notes' published 575,748, with InterPro joining the same
families as a second instrument; the two agree on all 1,719 families (A4.5, D-250).

| class | families | share |
|---|---|---|
| virus-only in the curated data | 1,265 | 73.6% |
| occurring outside viruses | 212 | 12.3% |
| absent from the curated section | 242 | 14.1% |

Of the 1,477 families the curated section can judge, 85.6% occur only in viruses. Sharing is
generally thin: the median shared family appears in one non-viral organism, and for 15 of the 212
every non-viral occurrence carries the curators' annotation as integrated viral material, which
describes a host genome holding the element rather than a family with cellular members.

The measurement also audits the denominator it is taken against. The selection vocabulary matches
substrings, so "macrophage" matches "phage", and 7 of the 1,719 families entered the universe on
that basis alone, each of them a cellular host protein; 113 families have curated cellular entries
and no curated viral entry. A cellular family in the denominator contributes a near-certain zero, so
the denominator is conservative, and the pre-registered 1,719 therefore stands uncorrected: on a
universe of 1,712, Evo 1's profile-route share would read 34.46% rather than 34.32%.

Two properties bound what the measurement licenses. A family absent from the curated section is
recorded as unmeasurable and never as virus-only, which is why 242 families are set aside rather
than counted favourably. And an occurrence outside viruses is weaker evidence than independent
cellular ancestry, because host genomes carry integrated viral material and such an entry is
annotated to the host.

The figures describe the universe. Detected families are drawn from it unevenly, since an abundant
family is likelier to be found, so the restricted measurement over the detected set is outstanding
and the universe shares stand in for it poorly. The relevant exception is already visible:
`PF00589 Phage_integrase` is the most heavily shared family in the set, at 421 reviewed non-viral
entries across 280 organisms against 21 viral, and it is also among the most frequently detected.

## 6. Result 4: the auditable artefact and the trained artefact differ

Evo 2's released viral component appears twice, in two file formats. The arithmetic between them
suggested that 264,570 records removed by the procedure had reached the training data, so both
representations were counted twice, the second time by newline counting and byte arithmetic that
decodes and parses nothing.

The suggestion proves false, and the correct reading carries further. The representation that was
trained on reproduces Evo 1's released filtered output exactly, to the record and to the nucleotide,
with both deltas at zero, so the filter's output passed forward unchanged. The other representation,
the only one carrying source identifiers and therefore the only one a filter can be checked against,
holds 304,448 additional records and 2.64 billion additional nucleotides, including those the
procedure removes (A7.3, A7.4).

The consequence is structural. Publishing one component in two representations is ordinary
engineering practice, the data speaks to intent in no way, and the effect is that verification must
run against an artefact other than the filter's product. The remedy is inexpensive: publish the
filtered artefact in the representation carrying identifiers, or publish the removal list. It is the
first of fourteen items in a disclosure standard whose every item arose from a specific audit
obstacle (X5.1).

One adjacent figure dissolves on inspection and is recorded to stop its repetition: 39,974
apparently repeated accessions are 39,974 surplus FASTA headers on 1,775 large genomes published in
contigs, with surplus records at zero (D-225).

## 7. Scope of the claims

A profile hit establishes membership of a sequence family at that family's curated threshold.
Function, completeness and capability lie beyond it, and hazard assessment lies outside this work
altogether. The counts therefore establish the presence of viral protein families; presence of a
viral genome is a stronger claim, and §5.3 bounds how far the evidence carries toward it.

On the one release where the question can be settled, the filter's output passed forward exactly, so
these results describe auditability and reach. Every sampled count is a lower bound. The nucleotide
work covers two releases of one model family, and the protein-model arm is a policy comparison over
a staged proxy corpus.

Two further limits are worth stating in their own right. Result 1 concerns which ranks carry labels,
while label correctness is a separate measurement in this project and a separate claim. And
agreement between the three policy readings is a property of these corpora's metadata, which falls
short of evidence that the prose is reproducible (D-221).

## 8. What further work would add

A census. About 3,000 core-hours over both releases and both registries, tens of dollars at spot
prices (D-098), deferred by an explicit costed decision (D-247). It would convert the headline from
"at least 597 and 812" into a measured value.

Depth parity between the registries. About ten hours of local compute and no expenditure. The
equal-rate pair already supports the cross-registry statements this study makes, so the deeper pass
would raise one bound without enabling a new comparison, and it carries the structural guards a banded
pass needs: one output directory per release, an identifier-prefix check of every published table
against the release it describes, and retained band parts.

Specificity over the detected families. The universe measurement is complete; restricting it to the
detected set, and so reporting the headline beside a variant counting only families that occur in
viruses alone, requires the per-family detection tables, which the audit containers currently cannot
read. The three variants, and the decision to report each as a pair that excludes and then includes
the unmeasurable families, are fixed in the task file ahead of any restricted count.

Breadth. The audit runs behind one interface taking a policy, a corpus and a set of detectors, and
against a bundled fixture in one command, so the marginal cost of the next release is staging its
corpus and transcribing its policy. Results 1 and 2 and the disclosure standard generalise as far as
the number of policies tested and no further.

Disclosure. These findings remain inside the project until the organisations concerned have been
contacted and given time to respond, which takes weeks of calendar time and careful writing, and
which determines whether the work changes anything.

## References

Bigot T., Temmam S., Pérot P., Eloit M. (2019; v2 2020) RVDB-prot, a reference viral protein
database and its HMM profiles. *F1000Research* **8**, 530.
doi:[10.12688/f1000research.18776.2](https://doi.org/10.12688/f1000research.18776.2). Pinned here at
v32.0, 13,679 profiles, against the release's own metadata file (D-075).

Blum M. *et al.* (2025) InterPro: the protein sequence classification resource in 2025. *Nucleic
Acids Research* **53**(D1), D444-D456.
doi:[10.1093/nar/gkae1082](https://doi.org/10.1093/nar/gkae1082).

Brixi G. *et al.* (2026) Genome modelling and design across all domains of life with Evo 2.
*Nature*. doi:[10.1038/s41586-026-10176-5](https://doi.org/10.1038/s41586-026-10176-5). Preprint
doi:[10.1101/2025.02.18.638918](https://doi.org/10.1101/2025.02.18.638918).

Camargo A. P. *et al.* (2023) IMG/VR v4: an expanded database of uncultivated virus genomes within a
framework of extensive functional, taxonomic, and ecological metadata. *Nucleic Acids Research*.
doi:[10.1093/nar/gkac1037](https://doi.org/10.1093/nar/gkac1037).

Camargo A. P. *et al.* (2024) Identification of mobile genetic elements with geNomad. *Nature
Biotechnology*. doi:[10.1038/s41587-023-01953-y](https://doi.org/10.1038/s41587-023-01953-y).

Eddy S. R. (2011) Accelerated profile HMM searches. *PLoS Computational Biology* **7**(10),
e1002195. doi:[10.1371/journal.pcbi.1002195](https://doi.org/10.1371/journal.pcbi.1002195).

Hyatt D. *et al.* (2010) Prodigal: prokaryotic gene recognition and translation initiation site
identification. *BMC Bioinformatics* **11**, 119.
doi:[10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119).

ICTV Virus Metadata Resource, release `VMR_20-190822_MSL37.3`, pinned by sha256 (D-086). The ICTV
issues no DOI for an individual Master Species List or VMR release; recent releases are archived on
Zenodo, and no persistent identifier was confirmed for this release, so it is cited by release name
and digest.

Larralde M. (2022) Pyrodigal: Python bindings and interface to Prodigal. *Journal of Open Source
Software* **7**(72), 4296. doi:[10.21105/joss.04296](https://doi.org/10.21105/joss.04296).

Nguyen E. *et al.* (2024) Sequence modeling and design from molecular to genome scale with Evo.
*Science*. doi:[10.1126/science.ado9336](https://doi.org/10.1126/science.ado9336).

`LongSafari/open-genome` (OpenGenome), HuggingFace datasets, pinned at revision
`84369c058d192dcb607086d71679b877421e3250` with a published sha256 per file; dataset card retrieved
2026-10-13 and stored with its digest. HuggingFace issues no persistent identifier for a dataset, so
the revision hash serves as the pin.

`arcinstitute/opengenome2` (OpenGenome2), HuggingFace datasets, pinned at revision
`84d2a7e690c8bb395d1f4868822dfa031ea561c6`, under the same provisions.

Paysan-Lafosse T. *et al.* (2025) The Pfam protein families database: embracing AI/ML. *Nucleic
Acids Research* **53**(D1), D523-D534.
doi:[10.1093/nar/gkae997](https://doi.org/10.1093/nar/gkae997). Pinned here at release 38.2
(EMBL-EBI, 2026-01-22) by versioned release directory and digest rather than by the
`current_release` pointer (D-075).

Schoch C. L. *et al.* (2020) NCBI Taxonomy: a comprehensive update on curation, resources and tools.
*Database* **2020**, baaa062.
doi:[10.1093/database/baaa062](https://doi.org/10.1093/database/baaa062). The decay replay uses
`taxdump_archive` quarterly dumps from 2020-01-01 to 2026-10-01, 28 releases, baseline 2023-04-01
(D-201).

UniProt Consortium (2025) UniProt: the Universal Protein Knowledgebase in 2025. *Nucleic Acids
Research* **53**(D1), D609-D617.
doi:[10.1093/nar/gkae1010](https://doi.org/10.1093/nar/gkae1010). The curated background is the
reviewed section at release 2026_03: 575,748 entries read, of which 17,529 are viral.

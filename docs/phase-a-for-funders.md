# Auditing a training-data exclusion policy

Draft of 2026-10-22, internal to the project. `AGENTS.md` holds findings inside the project until
the responsible-disclosure task (X3.1) has run, and that gate remains closed. Citations of the form
(Author Year) are listed at the end; identifiers of the form A2.1 and D-075 refer to this project's
task files and append-only decision log, which are private.

## Abstract

Evo 1 and Evo 2 state that viral genomes infecting eukaryotic hosts were excluded from their
training corpora, and both publish those corpora openly (Nguyen et al. 2024, Brixi et al. 2026).
This study searches the released artefacts by sequence, then executes the stated policy against them
to account for what the search returns. Both ends of the pipeline are in hand: the source database
the filter was applied to, read from the publisher's primary table, and the released corpora, staged
from pinned revisions.

Profile search finds viral protein families in both corpora: at least 597 of 1,719 viral Pfam
families in Evo 1's released component and 812 in Evo 2's, each a lower bound from a 1-2% sample
whose accumulation curve is still rising. Evo 1's detections sit in the training data itself, since
the component searched and OpenGenome2's JSON training format agree to the record and to the
nucleotide; Evo 2's sit in the only representation carrying source accessions, which exceeds that
training format by 304,448 records and admits no record-level join to it. In a targeted sweep of Evo
1's component the taxonomic labels report zero segmented-virus records while profile search over the
same records recovers markers of five eukaryote-infecting virus families, one named on the policy's
own denylist.

Three measurements account for that. The two rules that name organisms key on the family and order
ranks of a record's lineage, and the source database labels only 6.25% of its 15,677,623 records at
family rank and 8.67% at order rank (Camargo et al. 2023); Evo 1's released component carries a
family label on 2.62% of records (§4). The denylists enumerate names, and names expire:
*Herpesviridae* became a synonym of *Orthoherpesviridae* in January 2026, so a rule naming it now
reaches no herpesvirus while reporting success, and measured reach of the 31 names fell from 75.83%
to 65.17% of the viral taxonomy, at 4.34% per year (Appendix A). And Evo 2's viral component is
published twice, the representation carrying source identifiers holding 304,448 records more than
the one trained on, so the filter admits audit only against an artefact other than its own product
(§5).

Are the detected families specific to viruses? Measured against the reviewed section of UniProtKB
(UniProt Consortium 2025), with InterPro as a second instrument (Blum et al. 2025): of the 1,719
families, 1,265 occur only in viruses in the curated data, 212 occur outside viruses and 242 are
absent from the curated section, so 85.6% of the 1,477 that admit a verdict are virus-only, and the
median shared family appears in a single non-viral organism. Restricted to what each release
detected, sharing among judgeable families rises to 30.3% on Evo 1 and 22.6% on Evo 2, because a
family with cellular members is easier to find; the figures to hold are 69.7% virus-only for Evo 1's
detections and 77.4% for Evo 2's. Counting only families with no curated occurrence outside viruses,
Evo 1's 597 becomes 310 to 462 and Evo 2's 812 becomes 498 to 667, depending on the treatment of the
unjudgeable families.

Do the sequences encode anything hazardous? The detected material is mostly bacteriophage structural
and packaging machinery, which is what IMG/VR, a database of uncultivated viruses assembled from
environmental metagenomes, mostly contains. A profile hit establishes membership of a sequence
family at that family's curated threshold, which is weaker than a statement about function and far
weaker than one about hazard, and no hazard assessment was performed. What can be said rests on
labels. All 19,646 detected Evo 2 records join to their source database entry, and 31 of them carry
a taxonomic label belonging to a virus family the policy itself names for removal, including one
complete flavivirus genome and one commensal human papillomavirus; none names a regulated select
agent. Only 6.47% of detected records carry a family label at all, so 31 is a floor over a small
window rather than a count, and Evo 1's released records carry no source accession, so the question
cannot be put to that release (§3.6).

The finding of this study is about process and auditability: the published filter did not do what
its description implies.

## 1. The claim, and what a search of the corpora returns

Evo 1 and Evo 2 state that viral genomes infecting eukaryotic hosts were excluded from their
training corpora, and both publish those corpora openly (Nguyen et al. 2024, Brixi et al. 2026).
The exclusion is the safeguard the releases offer alongside open weights, and each paper supports it
with model behaviour: Evo 2's materials report that the model "is less performant on eukaryotic
viruses, as intended". Press coverage reassures the public with the same pairing, reporting that
"its developers also incorporated safeguards by excluding viruses that infect eukaryotic organisms
from the training data" (EurekAlert 2026) and describing the corpus as "carefully curated to exclude
genomic sequences from viruses that infect eukaryotic hosts", with the purpose "to mitigate
potential misuse" (Jackson 2025). The safeguard travels further than the paper, and in a shorter
form, where the curation step is reported as accomplished.

Model behaviour is one claim. The claim underneath it, which this study tests, is what the published
corpus contains. Testing it takes both ends of the pipeline, and this study holds them: the source
database the filter was applied to, IMG/VR v4.1, read from the publisher's own primary table, and
the released corpora, staged from the publishers' pinned revisions.

A profile search over the surviving records returns hits. At a 1-2% sample, Evo 1's released viral
component carries at least 597 of 1,719 viral Pfam families and Evo 2's at least 812, and a sweep of
Evo 1's component recovers markers of five eukaryote-infecting virus families in records whose
taxonomic labels report none (§3).

For Evo 1 those detections sit in the training data. The component searched is `stage2`, Evo 1's
released viral component, which OpenGenome2 republishes as its JSON training format; the two agree
to the record and to the nucleotide, 2,653,047 records and 36,236,025,613 nucleotides, both deltas
zero (§5). For Evo 2 the same sentence cannot be written, and the release's own publishing choice is
why. The component searched is `imgvr.fasta.gz`, the only representation carrying source accessions,
which exceeds the training format by 304,448 records; records in the training format carry a bare
text field and no accession, so the two admit no record-level join, and each Evo 2 detection is
located in the released component without being attributable to the trained copy. For one release
the audit reaches the training data; for the other the published artefacts prevent it.

On inspection the hits are explicable, and the explanation is the substance of the study. The
procedure, applied to IMG/VR, runs in five steps: retain records the database flags as
high-confidence; retain one representative per viral operational taxonomic unit; retain records
whose taxonomic classification has been observed in a prokaryotic host at least twice; remove
records assigned to any of 19 named virus families or 12 named orders; and remove records assigned
no realm, or assigned no deeper than one of eight named high-level taxa (Nguyen et al. 2024, Brixi
et al. 2026). Every step reads a metadata field. The two steps that name organisms read the two
ranks the source database labels most sparsely (§4), the names they enumerate decay against a
reference taxonomy that keeps moving (Appendix A), and the representation of the corpus that carries
source identifiers is not the one that was trained on (§5).

Verification of this kind is rare for practical reasons: the policy exists as prose, the filter's
implementation is unpublished, and the corpora run to millions of records. The Evo releases are the
most tractable case available, because each states a policy and each publishes its corpus.

## 2. Method

**Label search and sequence search.** Each rule in the published pipeline reads a metadata field the
source database attached to a record: a confidence flag, a cluster identifier, a host prediction, or
a rank in a taxonomic lineage. The pipeline asks what a record's annotation declares it to be. The
detection pass works from sequence alone: records are translated into protein coding sequence with
Prodigal in metagenomic mode, the gene caller IMG/VR's own annotation pipeline uses (Hyatt et al.
2010, Larralde 2022, D-077), and the proteins are searched with profile hidden Markov models (Eddy
2011) against two version-pinned registries, Pfam 38.2, from which a frozen keyword rule selects
1,719 viral families of 30,134 (Paysan-Lafosse et al. 2025, D-075), and RVDB-prot v32.0, with 13,679
families (Bigot et al. 2019). The independence of the two instruments makes the audit possible: a
record carrying no family label falls outside the reach of the filter's family rule while remaining
fully visible to a profile search.

**Thresholds.** Pfam's per-family gathering cutoffs are used as published, and RVDB-prot uses its
publisher's rule of E ≤ 1e-5 against a pinned database size, since an E-value scales with the number
of targets searched and one cutoff would otherwise imply different bit scores on a sample and on a
whole corpus (D-076). Thresholds were recorded before any hit was inspected.

**Sampling.** Sample membership is a deterministic function of the record identifier and a pinned
seed, `blake2b(key=seed, record_id)` below `rate · 2⁶⁴`, seed 20261015, fixed before the first
search (D-078). Samples at successive rates therefore nest, so a deeper pass extends the shallower
one and the two compare directly, and each count is a lower bound, since a family enters it only
when a sampled record carried it. A full census costs about 3,000 core-hours across both releases
and both registries, tens of dollars at spot prices, and remains unpurchased (D-098).

**Second detection route.** A second route covers material integrated into bacterial genomes, a case
the policy leaves unaddressed: a whole-document search of both papers finds prophage, provirus,
endogenous and integrated element absent from any data-curation context. Candidate integrated
regions are called with geNomad (Camargo et al. 2024) and searched with the same profiles.

**Verification.** Each policy executes in three readings, literal, charitable and strict, and the
spread between them is reported as a result; on these corpora the three agree exactly (D-221). A
record whose verdict depends on a field the release omits is recorded as `unresolved`, held apart
from retention throughout. Headline counts are reproduced by a second implementation written without
reading the first, from primitive detection rows with denominators rebuilt from the pinned registry
files: 334 numbers across 16 reported groups, every headline figure identical (A3.3, D-215). Where a
measurement depends on parsing an external reference, agreement is sought from a second instrument
joining through a different source, since a re-run reproduces a parse error faithfully while an
independent join exposes it.

## 3. Result 1: the contents of the released corpora

| release | component searched | records searched | viral Pfam families detected, of 1,719 |
|---|---|---|---|
| Evo 1 (`opengenome`) | `stage2`, identical to the training format | 53,140 of 2,653,047 (2%) | 597 (34.7%) |
| Evo 2 (`opengenome2`) | `imgvr` + `imgpr`, the accession-carrying representation | 30,859 (1%) | 812 (47.2%) |

The profile route accounts for 590 and 811 of those families; the remainder arrive by the integrated
route, which over 375 and 300 sampled bacterial genomes called 128 and 178 integrated regions
carrying 203 and 251 viral families between them (A2.1, A2.4, A3.2, D-245, D-246).

Both counts are lower bounds, and the sampling continues to yield: a tenfold deepening took Evo 1
from 470 families to 590 and Evo 2 from 492 to 811, the accumulation curve still rising by 9% and
18% on the last doubling of records searched. Evo 2 reaches 812 at a tenth of Evo 1's rate, so the
table ranks neither release; Evo 1's corpus is a deduplicated subset of the same source database,
which accounts for the second corpus being richer per unit of sequence.

A stricter question is kept separate. Of Evo 1's 2,653,047 records, 95 survive a rule the release's
own metadata suffices to evaluate, all through a single clause about unassigned classification
(A7.1). Presence in a corpus and demonstrable non-conformance with a written policy carry different
evidential burdens, and only the second is an inconsistency finding.

### 3.1 Labels and sequence disagree on the same records

A sweep of the categories known to defeat taxonomic filters ran twice over the same records of Evo
1's component, once on labels and once on sequence (A2.5, D-187, D-190, D-193). On labels the
component holds zero segmented-virus records, a zero that describes the labels, since 2.6% of
records admit a verdict at family rank. On sequence at 10% depth the same records carry markers of 7
of 1,285 segmented virus families: 57 hits in 265,062 records, a family-level share of 0.54%
(0.26-1.12%). Five ICTV families are represented, each eukaryote-infecting, in a component whose
host rule exists to remove eukaryote-infecting viruses:

| RVDB family | records | ICTV family |
|---|---|---|
| FAM000422 | 29 | Polydnaviriformidae |
| FAM007500 | 6 | Spinareoviridae (*Orthoreovirus*) |
| FAM022414 | 2 | Nanoviridae (*Babuvirus*) |
| FAM003906 | 1 | Spinareoviridae (*Orthoreovirus*) |
| FAM005477 | 1 | Geminiviridae (*Grablovirus*) |
| FAM023047 | 1 | Bromoviridae (*Ilarvirus*) |
| FAM033562 | 1 | Spinareoviridae (*Orthoreovirus*) |

*Geminiviridae* is one of the 19 denylisted families. *Spinareoviridae* is a successor of
*Reoviridae*, also denylisted and no longer carried by the pinned taxonomy, so two results meet in
one row.

Three features separate this from a threshold artefact: FAM000422 appears in all four bands, which
are disjoint hash samples; three independently built RVDB families converge on *Orthoreovirus*; and
every hit cleared 50% model coverage as well as E ≤ 1e-5, on models as long as 310 residues. Two
rest on short models, FAM033562 at 83 residues over 7 sequences and FAM022414 at 66 over 8, and are
the weakest of the set, which is why the seven are reported individually. Conformance is left open:
Evo 2's records ship without taxonomy, so no published rule admits a verdict on them.

### 3.2 Cross-registry comparison at equal rate

The second registry stands at a tenth the depth of the first, so comparisons between registries are
read from an equal-rate pair, published as its own artefact (`corpora/results/a3-2/equal-rate-pair`,
commit `238313f`):

| release | rate | Pfam viral, of 1,719 | RVDB-prot, of 13,679 |
|---|---|---|---|
| Evo 1 (`opengenome`) | 0.002 | 470 = 27.34% [25.29, 29.50] | 572 = 4.18% [3.86, 4.53] |
| Evo 2 (`opengenome2`) | 0.001 | 492 = 28.62% [26.53, 30.80] | 1,456 = 10.64% [10.14, 11.17] |

Intervals are 95%. Both columns report the profile route alone, the one available equal-rate
pairing, since the integrated route sampled at a third rate. Equal sampling establishes one point:
depth does not account for the gap between the registries. The registries define a family
differently and their denominators differ eightfold, so each column stands alone and every share
carries its denominator in the same sentence (D-161, D-247).

### 3.3 Specificity of the family universe

The pinned universe was measured against the reviewed section of UniProtKB at release 2026_03,
575,748 entries read against the release notes' published 575,748, with InterPro joining the same
families as a second instrument; the two agree on all 1,719 families (A4.5, D-250).

| class | families | share |
|---|---|---|
| virus-only in the curated data | 1,265 | 73.6% |
| occurring outside viruses | 212 | 12.3% |
| absent from the curated section | 242 | 14.1% |

Of the 1,477 families the curated section can judge, 85.6% occur only in viruses, and sharing is
generally thin: the median shared family appears in one non-viral organism, and for 15 of the 212
every non-viral occurrence is annotated as integrated viral material, which describes a host genome
holding the element rather than a family with cellular members.

The measurement audits its own denominator. The selection vocabulary matches substrings, so
"macrophage" matches "phage", and 7 of the 1,719 families entered the universe on that basis alone,
each a cellular host protein; 113 families have curated cellular entries and no curated viral entry.
A cellular family in the denominator contributes a near-certain zero, so the denominator is
conservative and the pre-registered 1,719 stands uncorrected: on a universe of 1,712, Evo 1's
profile-route share would read 34.46% rather than 34.32%.

Two properties bound the measurement. A family absent from the curated section is recorded as
unmeasurable, never as virus-only, which is why 242 families are set aside; and an occurrence
outside viruses is weaker evidence than independent cellular ancestry, since host genomes carry
integrated viral material and such an entry is annotated to the host.

### 3.4 Specificity of the families actually detected

Detected families are drawn from that universe unevenly, because a family with cellular members is
easier to find. The same measurement, restricted to what each release detected (A4.5, D-251):

| release | detected | virus-only | shared | unjudgeable | shared, among judgeable |
|---|---|---|---|---|---|
| Evo 1, both routes | 597 | 310 | 135 | 152 | 30.3% |
| Evo 2, both routes | 812 | 498 | 145 | 169 | 22.6% |

The bias runs against the audit. Sharing among judgeable families is 14.4% over the universe against
30.3% and 22.6% over what was detected, 2.11 and 1.57 times as often, so the universe figure
understates the problem instead of standing in conservatively: a reader holding 85.6% virus-only for
the universe should hold 69.7% for Evo 1's detections and 77.4% for Evo 2's. `PF00589
Phage_integrase` is the clearest case, the most heavily shared family in the selection at 421
reviewed non-viral entries across 280 organisms against 21 viral, and among the most frequently
detected.

The conservative variant was pre-registered as a pair and is quoted as one: counting only families
with no curated occurrence outside viruses, Evo 1's 597 becomes 310 excluding the unjudgeable
families and 462 including them, and Evo 2's 812 becomes 498 and 667. No survival figure changes;
what changes is the sentence they support. The detected sets, compared as sets across the three
policy readings on both releases, are identical.

### 3.5 What the detected families are

Read by name, the detected set is dominated by bacteriophage machinery, matching the source
database's composition: over the union of both releases' detected families, 378 carry `phage` in
their Pfam name or description, 140 name a tail component, 59 a capsid, 39 a baseplate, 21 a
terminase, 10 a portal and 4 a prohead protease.

Detected families also carry names referring to the denylisted groups, and the count depends
entirely on the matching rule, so the rule was pinned before anything was counted (A4.6). The group
list is the 19 families named in the policy's remove-step, with nothing added; a family refers to a
group if its Pfam identifier or description contains the family name, the virus noun, the adjective
or the subfamily form, or if the group's stem (`Flavi`, `Pox`, `Gemini`) appears as a whole token of
the identifier, tokens being runs of letters and digits between non-alphanumeric characters. No
detected family touches two groups.

Under that rule 41 of the 1,719 families refer to a denylisted group, 9 in Evo 1's detected set and
all 41 in Evo 2's, carrying 173 and 388 hits. *Flaviviridae* accounts for 15, spanning capsid,
prM/M, envelope E, NS1, NS2B, the NS3 protease and helicase, NS4A, NS4B and the NS5 polymerase;
*Geminiviridae* 6, *Poxviridae* 5, *Adenoviridae*, *Hantaviridae* and *Retroviridae* 3 each,
*Papillomaviridae* and *Picornaviridae* 2 each, *Caliciviridae* and *Rhabdoviridae* 1 each. Nine of
the 19 groups, among them *Coronaviridae*, *Filoviridae* and *Herpesviridae*, name no detected
family. The two per-release counts come from samples at different rates and do not rank the
releases.

Reading identifiers alone gives 31, the floor, since the ten families only the description catches
are named for a protein rather than a taxon (`Peptidase_C5`, `Rhv`, `RVP`, `GP41` and the like). The
rule matches stems as whole tokens because a substring rule admits `PF22759 E217_GP41`, a phage
baseplate protein whose identifier carries the string `GP41` that a retroviral envelope family also
carries: the "macrophage" failure of §3.3 in another guise. That blind spot closes here too — of the
seven families admitted to the universe on it, none is detected on Evo 1 and two on Evo 2, every hit
falling on an IMG/PR plasmid record (D-252).

The weakness of the whole observation is specific. A Pfam family's name records where its curators
built the model, so matching on names is evidence for constructing a list rather than a mechanism
for applying one (D-166): a hit on `Flavi_NS5` establishes that a protein in the released corpus
clears Pfam's curated threshold for that family, and leaves open whether the record is a flavivirus
or an environmental sequence carrying a distant homolog. That is settled per record, by label, next.

### 3.6 What the detected records are, by their own labels

The names above describe models; the records behind the hits carry labels of their own. All 19,646
Evo 2 records the profile search hits join by accession to the source database pin, with none
missing (A4.6).

The question can be put to one release only. For Evo 2 the per-hit tables name public IMG
accessions; Evo 1's name training identifiers, because its released viral component carries no
source accession (§5). Of the 57,487 distinct records hit across both releases, 19,646 resolve and
37,278 do not, every one of the latter Evo 1's, so every figure here is Evo 2's alone.

The bound that matters is the labelling: 6.47% of the 19,646 carry a family label and 5.71% an order
label. A negative result therefore means not labelled, never not present, and each count below is a
floor over a 6.5% window.

| label on the record, from the source database | records |
|---|---|
| one of the 19 denylisted families | 31 |
| one of the 12 denylisted orders | 308 |

The family labels are *Picobirnaviridae* 10, *Geminiviridae* 8, *Papillomaviridae*,
*Picornaviridae* and *Rhabdoviridae* 3 each, and *Circoviridae*, *Flaviviridae*, *Hantaviridae* and
*Retroviridae* 1 each; the order labels are led by *Picornavirales* at 226. *Picobirnaviridae* and
*Circoviridae* name no detected family but do label detected records, so the two arms are
independent and the name arm alone would have missed them.

Against the project's pinned Select Agents and Toxins List, as codified 2024-06-01, no detected
record carries a label naming a select agent. Three denylisted families in the table do contain
select agents, and in each case the labelled species is a different one: the single *Flaviviridae*
record is Entebbe bat virus, and the *Picornaviridae* records are a *Hepatovirus*, *Aichivirus E*
and one labelled no deeper than the family. Eight of the 31 are labelled only to family, so for
those the comparison is unanswerable rather than negative.

Under a severity rank fixed before the result was read — a select agent, then a species an authority
names as human-infecting, then a species the ICTV metadata resource calls `vertebrates`, then any
other labelled species, then unlabelled — the top tier is empty. One record is a human virus,
*Gammapapillomavirus 7*, a commensal of skin and oral mucosa whose infections the ICTV chapter
describes as usually asymptomatic. The most complete record is the flavivirus: labelled Entebbe bat
virus and hit by all 15 detected *Flaviviridae* families across the whole polyprotein, with scores
to 737.8 against a threshold of 25.0. For that record the distant-homolog reading is excluded, since
label and sequence agree, and what is in the released corpus is a flavivirus genome. Entebbe bat
virus was isolated from bat tissue in Uganda in 1957, has no known vector, and neither the ICTV nor
the European Virus Archive records human infection. Eight of the 31 are plant viruses, mostly
begomoviruses of tomato, potato and okra.

Whether a record bearing a denylisted label in the source database is a conformance failure of the
published procedure is a separate question, decided against record-level evidence under the three
readings (A7.1, A7.2), and this result does not assert it.

## 4. Result 2: the reach of the rules that name organisms

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
the shares are 7.87% at family and 8.85% at order. The host-association rule reads a different
field, admits evaluation on 13.71% of that population, and removes the remainder for want of
evidence (A4.1, D-081).

Three clarifications keep the table from being read too widely. Labels are present at some rank for
96.71% of records, so the database is well annotated, at ranks the policy's names leave unused. The
pipeline's final rule does read coarse ranks, removing 599,507 records, 3.82% of the release, for
having no realm or terminating at one of eight named high-level taxa; it names no organism and forms
part of the pipeline's reach. And the rank tallies come from two unrelated implementations, each
re-reading the publisher's primary table, agreeing on all eight ranks and the record total (D-082)
and surviving the database's own v4-to-v4.1 erratum, which moves 1,300 records at family rank and
the family share from 6.24% to 6.25%.

The released corpora are labelled more sparsely than the population they were drawn from:

| component | records | family-labelled |
|---|---|---|
| IMG/VR v4.1, after the confidence gate | 5,576,197 | 7.87% |
| Evo 1's released viral component | 2,653,047 | 2.62% |
| Evo 2's released viral component (recovered by join) | 2,917,521 | 7.02% |

The direction follows from the rules: a keep-list built on prokaryotic host association retains the
shallowly-labelled material.

## 5. Result 3: the auditable artefact and the trained artefact differ

Evo 2's released viral component appears twice, in two file formats, and both were counted twice,
the second time by newline counting and byte arithmetic that decodes and parses nothing. The
representation that was trained on reproduces Evo 1's released filtered output exactly, to the
record and to the nucleotide, with both deltas at zero, so the filter's output passed forward
unchanged. The other, the only one carrying source identifiers and therefore the only one a filter
can be checked against, holds 304,448 additional records and 2.64 billion additional nucleotides,
including those the procedure removes (A7.3, A7.4).

The consequence is structural. Publishing one component in two representations is ordinary
engineering practice and the data speaks to intent in no way; the effect is that verification must
run against an artefact other than the filter's product. The remedy is inexpensive: publish the
filtered artefact in the representation carrying identifiers, or publish the removal list. It is the
first of fourteen items in a disclosure standard whose every item arose from a specific audit
obstacle (X5.1).

## 6. Scope of the claims

A profile hit establishes membership of a sequence family at that family's curated threshold.
Function, completeness and capability lie beyond it, and hazard assessment lies outside this work
altogether. The counts establish the presence of viral protein families; presence of a viral genome
is a stronger claim, and §3.3 bounds how far the evidence carries toward it. Every sampled count is
a lower bound. The nucleotide work covers two releases of one model family, and the protein-model
arm is a policy comparison over a staged proxy corpus.

Hazard statements are narrower still. They rest on the source database's labels, reached by the
accession the release carries, so they cover Evo 2 and the 6.47% of its detected records that carry
a family label, and they are floors over that window. No alignment arm has been run.

Two further limits stand in their own right. Result 2 concerns which ranks carry labels; label
correctness is a separate measurement and a separate claim. And agreement between the three policy
readings is a property of these corpora's metadata, which falls short of evidence that the prose is
reproducible (D-221).

## 7. What further work would add

A census. About 3,000 core-hours over both releases and both registries, tens of dollars at spot
prices (D-098), deferred by an explicit costed decision (D-247); it would convert the headline from
"at least 597 and 812" into a measured value.

Depth parity between the registries. About ten hours of local compute and no expenditure. The
equal-rate pair already supports the cross-registry statements made here, so the deeper pass would
raise one bound without enabling a new comparison.

Taxonomic placement by sequence. §3.6 settles by label the 6.47% of detected records that carry one.
An alignment arm would settle the rest: for each detection, whether the record carries a coherent
set of a denylisted taxon's domains or a single distant homolog, compared against the registries'
own sequences rather than their labels. It is the most direct answer to the question a reader asks
first, it reaches the 93.5% of detected records labels cannot, and it is new work.

Breadth. The audit runs behind one interface taking a policy, a corpus and a set of detectors, so
the marginal cost of the next release is staging its corpus and transcribing its policy. The results
generalise as far as the number of policies tested and no further.

Disclosure. These findings remain inside the project until the organisations concerned have been
contacted and given time to respond, which takes weeks of calendar time and careful writing, and
determines whether the work changes anything.

## Appendix A. Result 4: a denylist of names ages

A rule that names a taxon inherits every subsequent revision of the reference taxonomy. The 31 names
were replayed against quarterly NCBI Taxonomy releases from 2020-01 to 2026-10, baseline 2023-04
(Schoch et al. 2020, A9.1, D-201, D-202).

Three names have ceased to resolve. *Herpesviridae* became a synonym of *Orthoherpesviridae* in
January 2026, so a rule naming it as a family scientific name reaches no herpesvirus and reports
success while doing so; *Orthopolintovirales* failed the same way in the same release; and
*Reoviridae* had already ceased to be a family name in the taxonomy release this project pinned, so
its decay was present at time zero.

Reach falls from 75.83% to 65.17% across the window, at 4.34% of the viral taxonomy per year. New
material dominates that loss: 44,261 viral taxa present at 2026-10 are absent from the baseline,
unreachable from it through NCBI's merge records, and named by nothing in the list, which is 15.18%
of the current viral taxonomy. Churn is smaller and counted separately: 787 renamed, 890 renumbered,
7,723 re-ranked.

A computed rule ages more slowly. Descent from an ICTV realm, asked of each release, covers 96.57%
at the baseline and 88.47% at 2026-10, a relative decline of 8.39% against the name list's 14.06%;
its floor is the taxonomy's own completeness, since 11.5% of viral taxa at 2026-10 descend from no
realm. The slope is equal either side of the filter's own vintage, so the finding concerns the
practice of specifying a filter as an enumeration of names and applies to any such list.

**Why the renames were left unresolved.** Resolution would recover little: of the gap at 2026-10,
renaming accounts for 787 taxa against 44,261 that no name reaches. It can also enlarge a rule
silently — *Reoviridae* survives in the pinned taxonomy as a synonym of *Reovirales*, an order
rather than a family, so following that synonym converts a family rule into an order rule, an
additional 90,530 records at 90% identity on the corpus used for the cross-filter comparison; the
looser reading is computed separately as `loose_only_members` and held out of every result (D-199).
Where a literal reading measures vocabulary rather than the filter, the audit substitutes and
declares it: the specificity rule declares `require_rank: realm`, a rank NCBI has never used, which
run literally finds a realm on no record and removes the whole viral corpus, so it is resolved to
descent from one of the six ICTV realms, with the substitution travelling in the artefact's
`name_resolution` field. The line held is between a rule that cannot execute, which the audit
repairs and declares, and a rule that executes and fails, which the audit reports.

Durability is achievable. A rule that resolves taxa through the reference's own synonym and merge
records, pinned to a dated release and re-validated on a stated interval, ages more slowly and ages
visibly; at 4.34% per year, holding unnamed new material below 1% requires re-validation about every
0.2 years. The disclosure standard arising from this work asks in item C1 for annotation sources
cited as dated releases with digests, and this result argues for a companion item requiring a stated
re-validation interval wherever a rule is written as a list of names.

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

EurekAlert (2026) Evo 2 brings artificial intelligence closer to reading and writing the language
of life. News release, 20 July 2026, AAAS. https://www.eurekalert.org/news-releases/1136823
(retrieved 2026-10-22). Quoted for how the release's safeguard is reported, not as evidence about
the corpus.

Hyatt D. *et al.* (2010) Prodigal: prokaryotic gene recognition and translation initiation site
identification. *BMC Bioinformatics* **11**, 119.
doi:[10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119).

ICTV Virus Metadata Resource, release `VMR_20-190822_MSL37.3`, pinned by sha256 (D-086). The ICTV
issues no DOI for an individual Master Species List or VMR release; recent releases are archived on
Zenodo, and no persistent identifier was confirmed for this release, so it is cited by release name
and digest.

Jackson J. (2025) Introducing Evo 2, a predictive and generative genomic AI for all domains of
life. *Phys.org*, 3 March 2025.
https://phys.org/news/2025-03-evo-generative-genomic-ai-domains.html (retrieved 2026-10-22).

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

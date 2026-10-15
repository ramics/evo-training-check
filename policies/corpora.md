# Released corpus versus actual training corpus

Task A1.1. For each model: what was released, what it is documented to be, and therefore whether
Phase A audits the real training corpus or a proxy. That verdict sets how strongly every
downstream claim may be worded, which is why it gates corpus reconstruction.

Same rule as the rest of this store: no quote here unless `tools/policies.py` has checked it
against the source it cites.

---

## 1. Evo 2 — released, and stated to be the training corpus

The data availability statement:

[source: S-EVO2-PREPRINT, p33]
> The OpenGenome2 dataset used to train Evo 2 is available at:

The dataset card makes the same claim and goes further, distinguishing the sequences from the
preprocessed form the model actually consumed:

[source: S-OPENGENOME2-CARD]
> OpenGenome2 is a database of nearly 9 trillion base pairs of curated DNA from across all domains of life. Collected from diverse species and public data sources, OpenGenome2 was used to train Evo 2 models.

[source: S-OPENGENOME2-CARD]
> which include the specific preprocessed sequences used for Evo 2 pretraining, such as adding special tokens and phylogenetic tags

**Verdict: verified as published.** The developers state that the released dataset is the training
corpus, in two independent places, and nothing retrieved contradicts it. What cannot be
established from published sources is byte-level identity between the release and what the
dataloader saw; no developer in this audit provides evidence that would settle that, and the
write-up should say so rather than implying a stronger check than was performed.

## 2. Why this makes the conformance re-execution (A7.1) runnable

The structural fact that matters is not the release itself but which side of the filter it sits on.
Evo 2's curation section states that Evo 1's corpus was carried over whole, already filtered:

[source: S-EVO2-PREPRINT, p22]
> Our previously published OpenGenome dataset was used in its entirety as part of the trainingdataforthisstudy(Nguyenetal., 2024a). Thisincludedrepresentativeprokaryoticgenomesavailable through GTDB release v214.1, and curated phage and plasmid sequences retrieved through IMG/VR and IMG/PR.

(The run-together words are an artefact of PDF text extraction from justified type, not the
source. Rendered: "...as part of the training data for this study (Nguyen et al., 2024a). This
included representative prokaryotic genomes available through GTDB release v214.1, ...". Quoted
as extracted, so the stored source and this file agree character for character; the same
artefact appears in `evo.md` and is noted there too. The capitals in `Nguyenetal.` and
`Thisincluded` were lowercased here when the quote was first stored, and this file's own note
previously blamed PDF extraction for losing them — extraction preserves them. X1.4's
case-sensitive check caught it; see DECISIONS.md D-023.)

[source: S-EVO2-PREPRINT, p22]
> As previously described, the OpenGenome dataset was curated to exclude genomic sequences of viruses which infect eukaryotic hosts.

So the released viral component is **post-filter output**, while the filter's **input** — IMG/VR
v4 — is independently available at its pinned version from its own publisher. Both ends of the
published procedure are therefore in hand, and A7.1 is a diff rather than an inference: apply the
A0.3 predicates to IMG/VR v4 and compare the survivors against the released component.

**"IMG/VR v4" names two releases, and the input is v4.1 — identified from Evo 1's output, not
from Evo 1's words.** The publisher ships a v4 (2022-09-20) and a v4.1 erratum (2022-12-20) that
corrects "a few sequences/rows" of the sequence-information table, which is the table every
published rule here reads; Evo 1 cites only "IMG/VR v4" and does not date its corpus build, so
D-052 and D-063 recorded the question as not determinable from the citation. It is determinable
from the released corpus. The erratum corrects eighteen classifications whose taxon name sits in
the wrong rank field — `r__Bicaudaviridae;;;;;;;` and `r__Fuselloviridae;;;;;;;` among them, a
family name in the realm position — and the published unspecificity rule tests for an assigned
realm, so the two releases predict *different survivor sets*. Re-executed over v4.1 the procedure
predicts survivors in exactly the 181 lineages Evo 1's release carries and no others; over v4 it
predicts 43 records in two lineages the release carries none of (A7.2, D-071).

Three qualifications travel with that, and this paragraph is the only place they are stated
together. **It is an inference from the audited artefact, not a retrieved fact**: no source says
which release was used, and nothing here should be cited as though one did. **It identifies the
release the output is consistent with**, which is weaker than identifying what the developers
ran. And **it is not an inference about awareness** — nothing suggests the developers knew of
either release or of the erratum. Both releases remain staged and every A7.2 number names the one
it came from, because the test rests on the asymmetry between them and would be circular if the
repo pinned only its own answer.

Two consequences for how A7.1 must be run, both knowable now:

- **The vOTU representative is not reproducible.** `keep_one_per` is order-dependent and no input
  order is published, so which record survives a vOTU is undetermined. Compare at vOTU level, not
  record level, or the diff measures our sort order rather than their filter.
- **Which reading is theirs does not become measurable, and the reason is a finding.** This
  paragraph expected that whichever of the three readings best reproduced the released component
  would be the developers' de facto reading, turning A0.4's spread into an estimate. It does not
  work, twice over. A7.1 found that every rule the readings differ over reads metadata the release
  withholds, so they are indistinguishable on anything it can test (D-047). A7.2, with the input
  in hand, found the spread is **zero** — and not because the readings agree: **IMG/VR v4 asserts
  no eukaryotic host for any of its 15,677,623 records**, across all four of the publisher's
  prediction methods, so the eukaryotic-host rules the charitable and strict readings turn on have
  nothing to fire on (D-072). The release cannot identify the developers' reading because no
  reading is distinguishable on this input. A0.4 should read D-072 before reporting the Evo
  spread, and should not generalise the zero to a model whose corpus carries eukaryotic host
  annotation.

## 3. Evo 1 — the procedure's source, and a gap in this store

Evo 1 is where the only published exclusion procedure lives, so what its corpus was matters. Its
own availability section names source databases rather than a released artefact:

[source: S-EVO1-PREPRINT, p16]
> We used the following datasets for pretraining:

[source: S-EVO1-PREPRINT, p16]
> Curated prokaryotic viruses from the IMG/VR v4 database

Evo 2, quoted in §2 above, calls that corpus "previously published". The artefact is indeed
published, and it is now retrieved. Evo 1's own repository — the pointer its paper gives — names
the location:

[source: S-EVO1-REPO]
> The OpenGenome dataset for pretraining Evo is available at [Hugging Face datasets](https://huggingface.co/datasets/LongSafari/open-genome).

It sits under `LongSafari`, not under an `arcinstitute` namespace, which is worth recording
because the obvious guess returns HTTP 401 and a guess that returns an error looks like an absent
artefact. Checked rather than assumed, on 2026-10-13: the HuggingFace API lists 22 public datasets
under `arcinstitute`, and `opengenome` is not among them — only `opengenome2` — while `LongSafari`
publicly lists exactly one dataset, `open-genome`. So the 401 was not a gate on an existing
dataset. HuggingFace answers 401 identically for gated, renamed and never-existent repositories,
so a non-200 from that host supports no claim about an artefact on its own.

This is also the smallest concrete instance of what §10 is about. One model family's corpus is
"OpenGenome" in the papers, `LongSafari/open-genome` for v1 and `arcinstitute/opengenome2` for v2,
with nothing linking the three but a line in a GitHub README. A downstream developer asking what a
model was trained on has one reliable route — the paper's own pointer — and guessing returns an
error that reads as absence. The same README describes its scope:

[source: S-EVO1-REPO]
> Evo has 7 billion parameters and is trained on [OpenGenome](https://huggingface.co/datasets/LongSafari/open-genome), a prokaryotic whole-genome dataset containing ~300 billion tokens.

### What the release exposes, and the one thing it does not

The card describes two stages and gives the data files for each:

[source: S-OPENGENOME1-CARD]
> The OpenGenome dataset is organized in 2 stages, where stage 1 has context length 8k and stage 2 has context length 131k.

Its stage 1 configuration names two sources, `stage1/gtdb` and `stage1/imgpr` — GTDB genomes and
IMG/PR plasmids. **It names no viral component**, in a corpus the paper describes as including
IMG/VR. That is an observation about a configuration block, so it was checked against the release
itself rather than left as an inference. The stored file listing (S-OPENGENOME1-TREE, retrieved
2026-10-13 at revision `main`) contains 22 files: fourteen under `stage1/gtdb`, three under
`stage1/imgpr`, three stage 2 parquet files, the README and `.gitattributes`. No path at any depth
corresponds to IMG/VR or to viral sequence.

### Corrected: stage 2 *is* the viral component

An earlier version of this section concluded that "the release exposes no separately identifiable
viral component". That was true of the file paths and wrong about the release. Stage 2 is the viral
component; it simply is not named by path, and the records inside it are not undifferentiated at
all. Each one carries its taxonomic lineage inline.

Sampled with the HuggingFace rows API on 2026-10-13 — 800 rows of `stage2/train`, eight contiguous
blocks of 100 spread across all 2,652,947 rows (S-OPENGENOME1-ROWS):

- **Every sampled row carries a lineage tag**, formatted `|r__…;k__…;p__…;c__…;;;;|` ahead of the
  sequence. That is the same rank-prefix scheme as the stop-taxa in Evo 1's published rule, which
  names `r:Riboviria`, `k:Heunggongvirae`, `c:Tectiliviricetes` and the rest.
- **Every sampled tag is a viral realm**: 696 `r__Duplodnaviria`, 104 `r__Monodnaviria`. No
  prokaryotic or eukaryotic lineage appeared, and neither did `r__Riboviria`.
- **Most records resolve no deeper than class**: of 800 tags, 675 fill four ranks, 33 fill five and
  92 fill six.

Stage 1 is differentiated too, by a `record` field carrying accessions — GTDB contig accessions and
`IMGPR_plasmid_*` identifiers — against stage 2's single `text` field.

What this supports and what it does not. The qualitative claim is solid: the released v1 corpus
contains viral sequence, in stage 2, labelled per record with the taxonomy the filter acts on. No
proportion from it should be published: 800 of 2.65M rows is 0.03%, the blocks are contiguous
rather than random so rare categories are under-represented, and the sample describes one dated
revision. The absence of `r__Riboviria` is consistent with a filter that removed
eukaryote-infecting lineages but is a sample of 800, not a census, and must not be reported as an
absence from the corpus.

**Corrected (D-048, as that entry asks).** This paragraph also gave a fourth reason — "rows are
context windows rather than records so one genome may span many" — and it was wrong. A7.1's full
scan and A1.4's independent pass both establish the opposite: **one row is one record**. A record
longer than 131,072 characters arrives as several `|tag|block` pairs concatenated into *one* row,
each pair repeating the same tag, rather than as several rows. Over all 2,652,947 rows of the
training split: 7,574 carry more than one block, none carries more than one distinct tag, none
ends on a full block, and none carries no tag at all. The refusal to publish a proportion from
the sample stands on the three reasons left above, which are about the sampling design and are
undisturbed by this.

The census also settles the `r__Riboviria` caution in the affirmative: there are **6,105**
Riboviria records, every one of them `c__Leviviricetes` and no deeper (D-051).

**Consequence for A7.1, and it is better than §2 assumed.** The conformance check no longer has to
borrow Evo 2's release for its output: Evo 1's own procedure can be re-executed against Evo 1's own
released corpus, with input IMG/VR v4 and output `stage2`, and the lineage tags supply exactly the
field the taxonomy rules need. The rules needing IMG/VR metadata rather than taxonomy — the
high-confidence gate, the vOTU representative, and the prokaryotic-host count — still cannot be
checked from the release alone, because none of that metadata travels with the released records.
Running the diff against OpenGenome2 as well remains worthwhile, since the two releases differ, but
it is no longer the only option.

**And a check on our own work.** The withdrawn strict reading that required family-rank assignment
(D-016, D-018) would have removed 675 of these 800 released records — roughly 84% of the sampled
viral corpus — on the grounds that they are too unspecific to test against a family-and-order
denylist. The developers kept them. Whatever else that rule was, it was not a reading of what these
authors did, and the release says so independently of the textual argument that defeated it.

## 4. What the released corpus shows about filter scope

Not A1.1's verdict, but established by the same passages and worth recording where it was found.
Three components were added to the corpus after the filter was designed, and the published
curation of each contains no viral screening step:

[source: S-EVO2-PREPRINT, p22]
> New prokaryotic reference genomes made available through the GTDB release 220.0

[source: S-EVO2-PREPRINT, p22]
> All available eukaryotic reference genomes were downloaded from NCBI on May 31, 2024, excluding atypical genomes, metagenome-assembled genomes, and genomes from large multi-isolate projects. This resulted in 16,704 genomes including an estimated 10.7 trillion nucleotides.

After deduplication and quality filtering, that component is reported as:

[source: S-EVO2-PREPRINT, p22]
> This final filtered set included 15,032 genomes and 6.98 trillion nucleotides.

And the metagenomic component, whose stated curation is length, ambiguity, open-reading-frame and
redundancy filtering only:

[source: S-EVO2-PREPRINT, p22]
> This included 41,253 metagenomes and metagenome-assembled genomes from NCBI,

[source: S-EVO2-PREPRINT, p22]
> All contigs were split at consecutive stretches of ambiguous nucleotides of length 5 bp or longer, the split contigs were filtered by a minimum sequence length of 1 kb, and only contigs with at least one open reading frame as predicted by Prodigal

The metagenomic component is the one DESIGN.md §A4 anticipates: sequence that taxonomy has never
labelled cannot be acted on by a taxonomy-based filter at all, whatever that filter's scope. A4.1
measures the fraction; the point here is only that the published curation confirms no taxonomic
screening was applied to it.

The dataset card's token table gives the proportions, which A4.3 should use rather than deriving
its own: the viral component the filter acts on is reported at 34 billion tokens of the pretraining
mix, against 854 billion metagenomic and thousands of billions of eukaryotic genomic tokens in
context extension. Figures are the card's own; A4.3 states the denominator it uses, since the two
training phases weight the components differently.

## 5. ESM3-open — no corpus released

The availability statement covers weights and code, and says nothing about training data:

[source: S-ESM3-PREPRINT, p11]
> Weights and code for ESM3-open are provided for academic research use at

**Verdict: proxy only.** No release, so A1.3 must reconstruct from the stated source databases at
whatever versions are recoverable, and every ESM3 result carries that qualifier. This compounds the
unpublished threshold: for ESM3 neither the filter's parameter nor its corpus is available, so no
conformance re-execution in the A7.1 sense is possible. The reported removal count — 10.6M
sequences — is the one published quantity a reconstruction can be checked against, and sweeping the
threshold until a reconstruction reproduces it is the nearest available substitute. That estimate
inherits the proxy's error and must ship with an interval.

**Three corrections from A1.5, which this section predates.** The verdict stands — proxy only,
and every ESM3 result carries that qualifier. Three of its clauses do not.

The reconstruction does not have to work "at whatever versions are recoverable". ESM3 states a
release for all eight components, and for UniRef and MGnify they are exact releases still served
with a published checksum per file (`esm3-open.md` section 6). What is unstated is narrower and
sharper than a missing version: which UniRef *tier* was parsed, across which the component's size
varies 5.8-fold.

The 10.6M removal count cannot be used to check a reconstruction. This section proposed sweeping
the unpublished threshold until a reconstruction reproduced that figure, as the nearest available
substitute for a conformance re-execution. A1.5 withdraws the proposal: the corpus sizes ESM3
states are already 14.7M (UniRef) and 108.2M (MGnify) short of the releases they name, each on
its own more than the 10.6M the filter is reported to have removed everywhere. Whether the
remainder is ESM3's own re-clustering or removal the filter description omits is not decidable
from published text, so a threshold tuned to hit 10.6M would be fitting to a number that does not
mean what the sweep would assume. For ESM3 there is no substitute for a conformance
re-execution, and the honest statement is that there is none.

A third of the corpus cannot be reconstructed at all. JGI is 265,070M of 768,109M unique training
tokens, pinned only by a date — stated inconsistently as July 30th and July 31st 2023 — over a
set whose membership changes. Every ESM3 coverage figure is therefore a fraction of the
components that could be staged, not of the corpus, and must say so in figures as well as prose.

## 6. ESM-2 — no corpus released, but precisely pinned

[source: S-ESM2-REPO]
> The split files establishing which UniRef50 clusters were used as held-out evaluation set for pre-training

**Verdict: reconstructible proxy.** No corpus release, but the UniRef release is pinned and the
held-out cluster IDs are published, which makes ESM-2 the cheapest corpus to reconstruct and the
right first target for the A1.3 pipeline. As the positive control it needs no exclusion predicate.

**Two corrections from A1.3, which this section predates.** The verdict stands; two of its clauses
do not. The pinned release is 2021_04, not the 2018-03 release the split files use, and no held-out
split is published for 2021_04 (`esm2.md` §2–3; DECISIONS.md D-024). And the pinned corpus is
`UR50/D` — cluster members, not the UniRef50 representatives — so it is the most expensive of the
four to stage rather than the cheapest (`esm2.md` §4; D-025).

## 7. ESM-C — not applicable

No stated exclusion (`esm-c.md`) and no corpus release. It enters the audit only as a
viruses-included comparison, so corpus reconstruction is not required for it.

## 8. A pattern across both developers

In both labs the short public artefact diverges from the paper. ESM3's model card says "data
related to viruses has been removed" where the paper says "sequences unique to viruses"
(`esm3-open.md` §1). The OpenGenome2 card lists prokaryotic genomes as "GTDBv220" where the paper
describes v214.1 inherited from Evo 1 plus a v220 increment of 28,174 genomes — the card is not
wrong, but it is not the corpus either, and a developer reconstructing from the card alone would
pin the wrong version.

Neither divergence is misconduct and neither is hard to explain. Both matter for §10's disclosure
standard: the artefact a downstream developer actually reads is the card, and in both cases here it
is the less accurate of the two documents. That is a finding about filter disclosure rather than
about either lab.

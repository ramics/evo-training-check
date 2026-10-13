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
> Our previously published OpenGenome dataset was used in its entirety as part of the trainingdataforthisstudy(nguyenetal., 2024a). thisincludedrepresentativeprokaryoticgenomesavailable through GTDB release v214.1, and curated phage and plasmid sequences retrieved through IMG/VR and IMG/PR.

(The run-together words and lost capitals are artefacts of PDF text extraction from justified
type, not the source. Rendered: "...as part of the training data for this study (Nguyen et al.,
2024a). This included representative prokaryotic genomes available through GTDB release v214.1,
...". Quoted as extracted, so the stored source and this file agree character for character; the
same artefact appears in `evo.md` and is noted there too.)

[source: S-EVO2-PREPRINT, p22]
> As previously described, the OpenGenome dataset was curated to exclude genomic sequences of viruses which infect eukaryotic hosts.

So the released viral component is **post-filter output**, while the filter's **input** — IMG/VR
v4 — is independently available at its pinned version from its own publisher. Both ends of the
published procedure are therefore in hand, and A7.1 is a diff rather than an inference: apply the
A0.3 predicates to IMG/VR v4 and compare the survivors against the released component.

Two consequences for how A7.1 must be run, both knowable now:

- **The vOTU representative is not reproducible.** `keep_one_per` is order-dependent and no input
  order is published, so which record survives a vOTU is undetermined. Compare at vOTU level, not
  record level, or the diff measures our sort order rather than their filter.
- **Which reading is theirs becomes measurable.** Whichever of the three readings best reproduces
  the released component is the developers' de facto reading. For Evo this turns A0.4's spread
  from an interpretive argument into an estimate — and it is an argument against freezing any
  single reading as canonical before that number exists.

## 3. Evo 1 — the procedure's source, and a gap in this store

Evo 1 is where the only published exclusion procedure lives, so what its corpus was matters. Its
own availability section names source databases rather than a released artefact:

[source: S-EVO1-PREPRINT, p16]
> We used the following datasets for pretraining:

[source: S-EVO1-PREPRINT, p16]
> Curated prokaryotic viruses from the IMG/VR v4 database

Evo 2, quoted in §2 above, calls that corpus "previously published". **Those two statements do not
contradict each other, but this store cannot close the gap between them**: the OpenGenome v1
release artefact is not in `sources.json` and has not been retrieved. Recorded as an open item
rather than resolved by assumption — a dataset card nobody in this project has read is a secondary
source. It is cheap to close and should be closed before A7.1 runs.

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

## 6. ESM-2 — no corpus released, but precisely pinned

[source: S-ESM2-REPO]
> The split files establishing which UniRef50 clusters were used as held-out evaluation set for pre-training

**Verdict: reconstructible proxy.** No corpus release, but the UniRef release is pinned and the
held-out cluster IDs are published, which makes ESM-2 the cheapest corpus to reconstruct and the
right first target for the A1.3 pipeline. As the positive control it needs no exclusion predicate.

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

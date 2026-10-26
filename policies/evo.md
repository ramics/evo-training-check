# Evo 1 and Evo 2 — eukaryote-infecting virus exclusion

One policy lineage. Evo 1 states the procedure; Evo 2 restates the intent and defers to Evo 1
for the procedure. Evo 2 is the model under audit, so both are recorded here.

**Mechanism: label-based.** A denylist over viral taxonomy, plus a host-occurrence rule,
applied as a curation step to one component of the corpus.

---

## 1. What was excluded

Evo 1, main text:

[source: S-EVO1-PREPRINT, p4]
> For safety considerations, we excluded viral genomes that infect eukaryotic hosts.

Evo 2, main text — the same claim, with the inheritance made explicit:

[source: S-EVO2-PREPRINT, p4]
> As in Evo 1, we excluded genomic sequences from viruses that infect eukaryotic hosts from the training data.

Evo 2, discussion — the same mechanism, but note the stated *aim* is narrower than the
mechanism: eukaryote-infecting viruses are excluded, in order to withhold a capability
described in terms of human pathogens.

[source: S-EVO2-PREPRINT, p18]
> By excluding genomic sequences of viruses that infect eukaryotes from our training data, we aimed to ensure our openly shared model did not disseminate the capability to manipulate and design pathogenic human viruses.

Two further formulations state the measure as a capacity or a likelihood rather than as a
property of origin. Both are in figure captions, and both were found during A0.3's review rather
than A0.1's sweep; they matter because they bear on what the exclusion predicates on.

[source: S-EVO2-PREPRINT, p51]
> To decrease dual use risks, safety filtering was performed on the training data to remove viral sequences that can infect eukaryotic hosts.

That is the caption head of Figure S2, the figure whose panel A the p4 sentence cites as its own
verification. The same caption states the intended consequence:

[source: S-EVO2-PREPRINT, p51]
> Evo 2 is less performant on eukaryotic viruses, as intended.

And Evo 1's Figure S1 caption, which defines the excluded class by pointer to the Methods:

[source: S-EVO1-PREPRINT, p41]
> We excluded viruses that are likely to infect eukaryotic hosts (Methods).

**Counting the formulations.** Across the two papers the exclusion is stated ten distinct ways:
once on whole viral genomes (Evo 1 p4), four times on genomic sequences of or from viruses (Evo 2
p4, p18, p22; Evo 1 p14), twice on a database subset or the dataset as a whole (Evo 1 p9, p14),
once as the operational rule over IMG/VR host metadata (Evo 1 p32), and twice on a capacity or
likelihood to infect (the two captions above). "Potential eukaryotic viruses" at Evo 1 p32 is a
third non-indicative framing within the operational rule. No two of them delimit the same class,
and A0.4 reports the spread.

One thing no formulation addresses, and the reason the count matters: none of the ten says what
becomes of viral-derived sequence integrated in a eukaryotic genome the corpus retains. §4 below
records the searches establishing that absence.

The corpus does contain such genomes, including the human reference:

[source: S-EVO2-PREPRINT, p9]
> the only human genome in OpenGenome2 is the reference genome

The same source also states, unprompted, that the measure is defeasible downstream:

[source: S-EVO2-PREPRINT, p18]
> Task-specific post-training may circumvent this risk mitigation measure and should be approached with caution.

## 2. By what definition — the operational procedure

This is the only published procedure for the Evo exclusion. It is in Evo 1, and it is
executable as written.

The corpus it applies to:

[source: S-EVO1-PREPRINT, p32]
> The OpenGenome pretraining dataset (S3for summary statistics) was compiled from three different sources:

— GTDB v214.1 bacterial and archaeal genomes, IMG/VR v4 viruses, and IMG/PR plasmids. Then,
scoped to the viral component only:

[source: S-EVO1-PREPRINT, p32]
> For IMG/VR, sequences were retained only if they were labeled as "High-confidence" according to the database metadata, and only one representative per viral operational taxonomic unit (vOTU) was kept.

Step 1 — a host-occurrence rule:

[source: S-EVO1-PREPRINT, p32]
> These sequences were further curated to remove potential eukaryotic viruses by keeping only sequences whose assigned taxonomic classification was found within a prokaryotic host at least twice.

Step 2 — an explicit denylist of 19 families and 12 orders:

[source: S-EVO1-PREPRINT, p32]
> Next, the remaining taxonomic classifications were inspected and further filtered to exclude all viruses assigned to any of 19 families (Adenoviridae, Caliciviridae, Coronaviridae, Filoviridae, Flaviviridae, Hantaviridae, Hepadnaviridae, Herpesviridae, Orthomyxoviridae, Papillomaviridae, Paramyxoviridae, Picornaviridae, Poxviridae, Reoviridae, Retroviridae, Rhabdoviridae, Circoviridae, Geminiviridae, Picobirnaviridae) or 12 orders (Amarillovirales, Durnavirales, Geplafuvirales, Herpesvirales, Lefavirales, Ortervirales, Orthopolintovirales, Piccovirales, Picornavirales, Priklausovirales, Cirlivirales, Mulpavirales).

Step 3 — records too taxonomically unspecific to classify are dropped:

[source: S-EVO1-PREPRINT, p32]
> Next, viruses with poor taxonomic specificity were excluded, including those with no assignedrealmatall,andthoseonlyassigneduptothelevelofr:Riboviria,r:Monodnaviria,k:Heunggongvirae, k:Bamfordvirae, p:Preplasmiviricota, p:Cressdnaviricota, p:Pisuviricota, or c:Tectiliviricetes.

(The run-together words in that last quote are an artefact of PDF text extraction, not the
source. Rendered: "those with no assigned realm at all, and those only assigned up to the
level of r:Riboviria, …".)

Evo 2 adds no procedure of its own:

[source: S-EVO2-PREPRINT, p22]
> As previously described, the OpenGenome dataset was curated to exclude genomic sequences of viruses which infect eukaryotic hosts.

"As previously described" cites the Evo 1 paper. Evo 2's own Methods state the inheritance and
stop there.

## 3. Did it apply to the released checkpoint

Yes, as published. Both papers describe the exclusion as applied to the pretraining data of
the released models, and Evo 2 states that the training dataset is released alongside the
model (see S-EVO2-PREPRINT, "Data availability", and S-OPENGENOME2-CARD). Whether the released
dataset is byte-for-byte the training corpus is a separate question and is task A1.1's, which
gates the strength of every downstream Phase A claim.

## 4. Is any re-entry route addressed

**No route is addressed in any retrieved source.** Recorded as searches, with their extent:

| Term | Evo 1 (47pp) | Evo 2 preprint (65pp) |
|---|---|---|
| prophage | 0 | 11 |
| endogenous | 0 | 0 |
| provirus | 0 | 0 |
| "integrated virus" | 0 | 0 |
| ERV (word-boundary) | 0 | 0 |

Case-insensitive, whole-document. The Evo 2 "prophage" hits are all in the mechanistic
interpretability results — the model's learned features — not in data curation. No retrieved
source discusses endogenous viral elements, proviruses or integrated elements as a data
filtering concern.

## 5. The scope gap

The procedure in §2 is applied to the IMG/VR viral component. Evo 2's corpus adds whole
eukaryotic genomes, whose curation is stated in full:

[source: S-EVO2-PREPRINT, p22]
> All available eukaryotic reference genomes were downloaded from NCBI on May 31, 2024, excluding atypical genomes, metagenome-assembled genomes, and genomes from large multi-isolate projects. This resulted in 16,704 genomes including an estimated 10.7 trillion nucleotides.

[source: S-EVO2-PREPRINT, p22]
> Only contigs that were annotated as 'Primary Assembly', 'non-nuclear', or 'aGasCar1.hap1' (an aberrant annotation that applied only to GCA_027917425.1) were retained.

Deduplication and quality curation follow — Mash distance clustering, then:

[source: S-EVO2-PREPRINT, p23]
> Genomes were further filtered by removing ambiguous nucleotides at the termini of each contig, by removing regions annotated as "centromere" in an available GFF file, and by removing contigs that were less than 10 kb in total length.

Every stated filter on this component is assembly quality or redundancy. A search for viral or
virus within the eukaryotic-genome curation passages returned nothing.

**What is established:** the published viral exclusion procedure operates on the viral
component; the eukaryotic component's published curation contains no viral screening step.

**What is not established:** that no unpublished screening occurred, or how much
virus-derived sequence is consequently present. The first is unknowable from published
sources; the second is what A2, A3 and A4.3 measure. Phage are explicitly retained
(S-EVO1-PREPRINT p32 describes IMG/VR as "curated prokaryotic viruses"), so a phage-versus-
eukaryotic-virus contrast is available within the corpus itself.

## 6. Open questions for A0.3

Carried forward, unresolved:

1. **Scope.** The procedure names IMG/VR. Does the policy, read charitably, extend to any
   corpus component — and if so, by what procedure? No source says.
2. **"At least twice."** Why two occurrences in a prokaryotic host? The threshold is stated
   but not justified, and its error rate on real viral records is measurable (A4.2).
3. **Denylist currency.** The 19 families and 12 orders are a 2024 list against an evolving
   taxonomy. Was it revisited for Evo 2? No source says.
4. **"Infect eukaryotic hosts" versus "pathogenic human viruses."** The mechanism and the
   stated aim differ in scope (§1). Which does the policy commit to?
5. **Version of record.** ~~The Evo 2 Methods section of the Nature paper is unretrieved
   (S-EVO2-NATURE-METHODS) and should be checked before publication, in case it adds procedure
   the preprint omits.~~ **Closed 2026-10-20 by A7.3.** S-EVO2-NATURE-METHODS was retrieved on
   2026-10-17 and is quotable; this entry was stale. It adds no procedure the preprint omits,
   and what it does add is a scoping sentence that changes how the inheritance reads — §10.

## 7. The released corpora, as pinned for A1.2

Task A1.2. Both releases are now pinned to commit SHAs, with a published SHA-256 per file; the
per-file manifests are S-OPENGENOME1-MANIFEST and S-OPENGENOME2-MANIFEST, read on 2026-10-14.

| | OpenGenome (Evo 1) | OpenGenome2 (Evo 2) |
|---|---|---|
| Repository | `LongSafari/open-genome` | `arcinstitute/opengenome2` |
| Pinned revision | `84369c058d192dcb` | `84d2a7e690c8bb39` |
| Files | 22 | 1,126 |
| Bytes | 146,886,935,899 | 5,523,240,795,932 |
| Representations | Parquet | FASTA and JSON, same sequences |
| Sequence files last changed | 2024-07-06 | 2025-02-18 |

**Why a commit and not `main`.** Both have moved since publication. OpenGenome2's head on
2026-10-14 is three commits past the state the preprint describes, and `main` is therefore not a
pin — a reader resolving it next year gets whatever is there then.

**What moved, and what did not.** This matters more than the pin itself, because it decides
whether the audited bytes are the published bytes. From S-OPENGENOME2-COMMITS: all 1,123
sequence files were last touched on 2025-02-17 and 2025-02-18, alongside the preprint, and
nothing has changed them since. The three later commits are a README edit on 2025-09-20 and,
on 2026-09-02, the addition of `species_metadata.csv` and a README mention of it. For Evo 1 (S-OPENGENOME1-COMMITS) all 20 data files landed in a single
commit on 2024-07-06 and the 11 commits since are README edits. So the pinned revisions carry
publication-time sequence content in both cases.

One limit on that, stated because an adversarial reader will ask: a listing shows what is
present, so this supports "these files have not changed since February 2025" and not "nothing
was removed". A deletion would leave no trace in either capture. Nothing in the file counts
suggests one — both match the composition the papers describe — but the stronger claim is not
available from these sources.

### No proxy substitution arises here, and that is worth saying

A1.2's steps require stating where a proxy stands in for unavailable material. For the Evo
corpora the answer is **nowhere**: both releases exist, both are stated by their developers to be
the training corpora, and both are now staged from the pinned revisions with every object checked
against the checksum the release publishes for it. Of the four corpora in this audit these are the
only two needing no acquisition qualifier at all — ESM3-open has no release (`corpora.md` §5) and
ESM-2's staged release is 14% larger than the subset the model trained on (`esm2.md`, D-029).

The one limit carried from A1.1 stands and must travel with every Phase A claim: nothing
published establishes byte-level identity between a release and what the dataloader actually
consumed, for any model here. So "as published" is the right phrasing, and "verified" unqualified
is not. What *is* established, and was not before this task, is that the bytes we hold are the
bytes the developers released — which is a different claim, and the one the checksums support.

### Composition

`artifacts/a1-2/composition.json`, regenerated by `tools/stage_opengenome.py --probe`, is the
machine-readable form; it reconciles to the file against both manifests. The shape of it, by
share of release:

- **OpenGenome2 is 82% eukaryotic reference genomes and genic windows**, a component added after
  the filter was designed and with no viral screening step in its published curation (§5 above,
  and `corpora.md` §4).
- **9% is metagenomic** — sequence taxonomy has never labelled, which a taxonomy-based filter
  cannot act on at whatever its scope. A4.1 measures this fraction properly.
- **The component the published procedure acts on is 0.2%**: 10.4 GiB of IMG/VR sequence in the
  FASTA tree, against 5.0 TiB of release. The filter's subject is a rounding error in the corpus
  it is a safeguard for. That is not a criticism of the filter — it is the scope gap in §5,
  measured — and it is the single most important number A4.3 inherits from this task.
- In Evo 1, by contrast, the viral component is **11.5%** of a much smaller corpus, and GTDB
  prokaryotic genomes are 87%.

A caveat on the two OpenGenome2 trees: they are not a strict one-to-one mirror. The GTDB
component is 101.6 GiB as FASTA and 190.8 GiB as JSON, because the JSON tree carries both a
pretraining and a "stitched" midtraining variant where the FASTA carries one. Component totals
should therefore be quoted per representation, never summed across them.

## 8. What each representation can prove, and why only one was staged

**Corrected by A7.3 — see §10.** The two trees were taken here to hold the same sequences, on
the publisher's own description of the JSON as the preprocessed form of the FASTA. Counted in
full, they do not: the JSON tree holds 2,653,047 records and the FASTA 2,957,495. Everything
below about what each representation *carries* stands, and the sentence about them holding the
same sequences does not.

The two OpenGenome2 trees were understood to hold the same sequences and are not interchangeable
as evidence. From
S-OPENGENOME2-RECORD-FIELDS, reading the leading ~3 MB of four files:

- **FASTA viral records carry a source accession** of the form `IMGVR_UViG_<taxon-oid>_<n>` —
  1,588 of 1,588 sampled headers.
- **JSON viral records carry a single `text` field.** No accession, no lineage tag. The directory
  is named `imgvr_untagged`, and the name is accurate.
- **JSON prokaryotic records do carry an identifier** — a `record` field holding GTDB contig
  accessions — so the absence on the viral component is not a property of the JSON format.
- **JSON promoter records carry `text` alone**, like the viral ones.

**Consequence, and it decided A1.2's staging.** A7.1 has to diff released viral records against
IMG/VR v4, and a record with no accession cannot be diffed. The FASTA is the only representation
from which the released viral component can be traced back to the filter's input, so the FASTA is
what was staged; the JSON is recorded in the composition table and left in place. See
DECISIONS.md D-031.

**And a divergence worth recording.** `corpora.md` §3 established that OpenGenome v1's stage 2
carries a taxonomic lineage tag inline on every sampled record — the same rank-prefix scheme the
published rule's stop-taxa use. No record in any OpenGenome2 component sampled here carries one,
in either representation, while the OpenGenome2 card describes the released preprocessed
sequences as including "phylogenetic tags" (quoted in `corpora.md` §1). So the lineage labelling
that makes Evo 1's corpus checkable against its own filter appears not to have survived into Evo
2's release.

That is a four-file sample against 1,123, so it is a qualitative observation and not a census:
read as "no tag was found where v1 had one in every sampled record", not as "the tags are
absent". Settling it needs a wider pass, which A7.1 will do anyway when it reads the component in
full. If it holds, it is a fourth instance of the pattern in `corpora.md` §8 — the short public
artefact describing the release more generously than the release supports — and it is the one
instance with a direct cost to reproducibility, because the tag is the field the taxonomy rules
act on.

## 9. Settled by A1.4: the lineage tags are absent from Evo 2's release, as a census

§8 left its central observation as a four-file sample and named the pass that would settle it.
A1.4 read Evo 2's viral component in full — `imgvr.fasta.gz`, 11,220,266,895 bytes, **2,957,495
records** — checking every record's header and the start of its sequence for a tag in the
rank-prefix scheme Evo 1's rule uses. **Not one record carries one.** Zero contradictions, zero
parse failures, over the whole component rather than over 0.4% of it.

So §8's qualitative observation can now be stated as a fact about the release: the lineage
labelling that makes Evo 1's corpus checkable against its own filter did not survive into Evo 2's
release. The OpenGenome2 card's "phylogenetic tags" (quoted in `corpora.md` §1) describes
something the released viral FASTA does not contain.

**What that costs, measured.** None of the six published rules can be re-executed against Evo 2's
release at all. Each one needs an input the records do not carry:

| rule | input it reads | in Evo 2's release |
|---|---|---|
| `keep-high-confidence` | `record_attributes:confidence` | absent |
| `keep-one-per-votu` | `record_attributes:vOTU` | absent |
| `keep-prokaryotic-host-twice` | `host_occurrences:prokaryotic` | absent |
| `remove-denylisted-families` | `taxonomy:family` | absent |
| `remove-denylisted-orders` | `taxonomy:order` | absent |
| `remove-taxonomically-unspecific` | all eight ranks | absent |

Every record is therefore `unresolved`: the filter's output is published, and its own stated
procedure cannot be checked against it. Evo 1's release answers three of the six (A7.1's `3/6`
coverage); Evo 2's answers none. The audited *procedure* is Evo 1's and this audited *output* is
Evo 2's, which is why the two releases are reported separately and never merged (D-019).

**The two releases' viral components are not the same artefact.** Evo 1's stage 2 holds 2,653,047
records and Evo 2's IMG/VR component holds 2,957,495 — about 304,000 more. No proportion should
be drawn from that difference without knowing what Evo 2 re-derived: the point here is only that
"the OpenGenome dataset was used in its entirety" (quoted in `corpora.md` §2) does not make the
two components interchangeable as evidence.

**A note on what is complementary rather than merely missing.** Evo 1's release carries the
taxonomy and no accession; Evo 2's carries the accession and no taxonomy. Neither carries the
IMG/VR metadata three of the rules read. The accession is the more valuable of the two for A7.2,
because it is a join key to the filter's input and a lineage tag is not — which is why A1.7's
acquisition opens both directions on Evo 2's release and only one on Evo 1's.

## 10. Settled by A7.3: one component, two representations, and only one of them was trained on

§8 recorded the two OpenGenome2 trees as holding the same sequences, on the publisher's own
description of the JSON as the preprocessed training form of the FASTA. A7.3 counted both in
full. They do not.

| | records | nucleotides |
|---|---|---|
| Evo 1's released viral component (A7.1) | 2,653,047 | 36,236,025,613 |
| OpenGenome2 `json/…/imgvr_untagged/`, train + test | **2,653,047** | **36,236,025,613** |
| OpenGenome2 `fasta/plasmids_phage/imgvr.fasta.gz` (A1.4) | 2,957,495 | 38,877,282,216 |

**The training format is Evo 1's released component exactly** — zero on both deltas, not
approximately. The FASTA representation holds 304,448 records and 2,641,256,603 nucleotides
more, and among them are the 264,570 records the published procedure removes (A7.2).

Two notes on the arithmetic. The JSON tree publishes six files; its `valid` chunk holds the same
50 records and the same 363,466 nucleotides as its `test` chunk, at a different sha256 — gzip
metadata, not content — so summing all six double-counts one split. The distinct total is train
plus test. And the comparison is on counts rather than on identity: the JSON records carry no
accession (§8), so the two representations cannot be joined record by record, and "the same
number of records and the same number of nucleotides" is the strongest statement the published
artefacts support. It is a strong one — the probability of two independently derived corpora
agreeing to the nucleotide on 36.2 billion of them is not worth writing down — but it is not a
proof of identity and is not reported as one.

**The version of record scopes the inheritance, and the scoping is what makes this read
cleanly.** S-EVO2-NATURE-METHODS was retrieved on 2026-10-17, after §6's caveat 5 was written,
and is quotable under CC BY-NC-ND. Its data-curation section opens:

[source: S-EVO2-NATURE-METHODS, §A.2.1 "Reused datasets"]
> Our previously published OpenGenome dataset was used in its entirety as part of the training data for this study [80]. This included representative prokaryotic genomes available through GTDB release v214.1, and curated phage and plasmid sequences retrieved through IMG/VR and IMG/PR. As previously described, the OpenGenome dataset was curated to exclude genomic sequences of viruses which infect eukaryotic hosts.

Three things follow, and the third is the finding.

**The curation sentence is in the past tense and its subject is OpenGenome.** It states what was
done to the dataset being reused, not a step applied to OpenGenome2. The preprint's "As in Evo 1,
we excluded genomic sequences from viruses that infect eukaryotic hosts from the training data"
(§1) reads as a claim about this release; the version of record's sentence reads as provenance
on a reused one. Both are published and they do not say the same thing.

**The Methods enumerate what OpenGenome2 added, and nothing viral is in the list.** The sections
following "Reused datasets" are updated prokaryotic genomes, eukaryotic reference genomes,
metagenomes, eukaryotic organelle genomes, eukaryotic promoters, and augmented transcript and
genic-region derivations. IMG/VR appears three times in the whole document: in the sentence
above, in a note that phylogenetic tags are prefixed to IMG/VR sequences, and as a row in the
training-mix table. No new viral retrieval is described.

**So the released FASTA is 304,448 records larger than the only viral component the Methods
account for, and the training format is not.** Read together, the measurement and the quote
agree: what was trained on is the filter's output carried forward whole, and the representation
that carries the source accessions — the only one from which the filter can be checked at all
(§8) — is a superset of it that the Methods do not describe.

Nothing here is a claim about intent, and nothing here says the filter failed on the training
data; measured against the training format, it did not. What it says is that the artefact a
reader must use to audit the filter is not the artefact the filter produced, and that no
published sentence distinguishes them.

**The only published figure for the component is not reconcilable with it.** Supplementary
Table 9 gives IMG/VR as 3% of pretraining, 2% of midtraining and 1.7% of the ablation. Those are
shares of a training mix with upsampling, not of a corpus, so they cannot be checked against
either 2,653,047 records or 2,957,495. There is no published record count, nucleotide count or
removal count for the component in either Evo 2 document. This is the gap `docs/disclosure-standard.md`
records as item **D1**, and the one that made the reconciliation A7.3 was asked for impossible
rather than merely difficult.

---

## 11. How the safeguard is reported outside the papers

Two press accounts carry the exclusion claim, and both report the curation step as accomplished
and unqualified, with no mention of the component it was applied to or of what the papers leave
unstated. They are recorded because the safeguard travels further than the paper and in a
shorter form, which is a finding about the claim's public life rather than about the corpus.

`S-EUREKALERT-EVO2` (AAAS news release, 20 July 2026) states that the developers "also
incorporated safeguards by excluding viruses that infect eukaryotic organisms from the training
data". `S-PHYSORG-EVO2` (Phys.org, 3 March 2025) states that the training dataset "was carefully
curated to exclude genomic sequences from viruses that infect eukaryotic hosts to mitigate
potential misuse".

**Neither is a verified quotation, and neither may be written as one.** Both pages carry no
redistribution licence, so they are `retrieved_not_stored`: their wording was checked against
the retrieved page by the fetch that recorded their digests, on the retrieval date, and
`tools/policies.py` cannot re-check it — it refuses a blockquote citing a source that is not
stored. The wording above is therefore reproduced inline, with the verbatim sentence in each
entry's `quoted` field, and a claim resting on it carries its retrieval date. A news page may be
revised or withdrawn without notice.

Nothing in this section is evidence about the corpus. For that, §1 to §10 above and the tasks
they cite.

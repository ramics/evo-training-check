# ESM3-open (`esm3-sm-open-v1`) — similarity-based removal

**Mechanism: similarity-based.** A denylist seeded from taxonomic annotation, then expanded by
sequence alignment, applied across every training database.

This is the protein-level test condition from `DESIGN.md` v0.3 (see DECISIONS.md D-005).

---

## 1. What was excluded

The model card, which is the shortest statement and the one most readers will see:

[source: S-ESM3-HF-OPEN]
> data related to viruses has been removed from the training dataset

The paper is narrower, and the difference matters more than anything else in this file:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> We identified and removed sequences unique to viruses, as well as viral and non-viral sequences from the Select Agents and Toxins List

"Related to viruses" and "unique to viruses" are not the same set. The second excludes only
sequence that is distinctively viral; virus-associated sequence that also resembles cellular
sequence is outside the denylist by construction. See §5.

Stated purpose:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> As a precaution, we filtered the training data of ESM3-open to minimize model performance on sequences of potential concern while otherwise maintaining performance.

And the rationale for filtering data rather than outputs:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> Previous work has shown that the performance of protein language models is closely related to the number of similar sequences present in the training data

## 2. By what definition — the operational procedure

Two denylists:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> To filter data, we create two denylists: the Viral Denylist and the Select Agent Denylist.

The matching step:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> We then remove all sequences from the training set that are detected to align to those in the denylists by MMseqs2 at or above a given sequence identity threshold.

How the Viral Denylist is built — note that this is where "unique to viruses" is operationalised:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> sequences that are annotated as viral in UniProt and align almost exclusively to other viral sequences in UniProt

The authors' own characterisation of that construction:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> This gives us a procedure that removes viral proteins with both high sensitivity and specificity (as measured by UniProt taxonomic annotations).

The Select Agent Denylist:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> To create the Select Agents Denylist we identify all sequences in UniProt belonging to organisms on the Select Agents and Toxins List

Scope and scale — unlike Evo, this filter was applied across the whole corpus:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> For each denylist, MMseqs was used to query against the full set of training databases, (including PDB, UniRef, MGnify, and JGI) and all hits were removed from the training set.

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> This filter removes a total of 10.6M sequences across all training sets.

A second, separate measure acts on the function-prompt vocabulary rather than the sequence data:

[source: S-ESM3-PREPRINT, Appendix A.6.1 p67]
> We also removed the capability for the model to follow prompts related to viruses and toxins.

## 3. Did it apply to the released checkpoint

Yes, and specifically to it. The filtering is described as applied to ESM3-open, the released
open-weight model, and the paper reports a comparison against an unfiltered compute-matched
model — so the filtered and unfiltered variants are distinguished deliberately.

The developers' own efficacy check:

[source: S-ESM3-PREPRINT, p69]
> ESM3-open has an average LDDT of 0.56 on the viral structures.

measured on a held-out viral structure set defined as:

[source: S-ESM3-PREPRINT, p69]
> For the chains in PDB that were > 70% sequence identity hits to the Viral Denylist, we cluster at 40% sequence identity and then select the longest chain (with length ≤ 1024) from each cluster.

## 4. Is any re-entry route addressed

Partly, and this is the substantive difference from Evo. The alignment step is itself a
re-entry control: it removes homologs of denylisted sequence rather than only records bearing
a viral label, so it reaches sequence that taxonomy alone would miss. There is no mention of
host-genome-resident viral sequence, but the corpus is protein databases rather than genomes,
so that route is not applicable in the same way.

## 5. Open questions for A0.3

1. **The threshold is unpublished.** "At or above a given sequence identity threshold" — the
   value is never stated. The filter cannot be reproduced without it. This is the single
   largest under-specification across all four policies, because the whole filter's reach is
   that one number.
2. **"Almost exclusively" is unquantified.** The denylist's inclusion criterion depends on it.
3. **Model card versus paper.** "Related to viruses" (card) versus "unique to viruses" (paper)
   describe materially different sets. Which is the policy? The literal reading of the card is
   broader than anything the paper describes.
4. **The keyword list is withheld.** The function-decoder filter terms are, per the paper,
   available on request rather than published, so that measure is not independently checkable.
5. **"Some proteins."** The card says "some proteins belonging to organisms on the" Select
   Agents list were removed; the paper describes removing all UniProt sequences from those
   organisms. "Some" appears to understate the paper.
6. **Version of record.** S-ESM3-SCIENCE is unretrieved (paywalled). Quotes here are from the
   preprint and should be checked against the published version before publication.

---

## 6. What ESM3 states about its training data

Added by A1.5. §2 above quotes the filter's own description of its scope, which names four
databases and no versions: that sentence is what made this task expect an under-specification
finding about missing versions. It is the wrong place to look. The pretraining-data appendix
states a release for every component, and Table S3 repeats them in a table. The versions are
mostly there, and several are exact.

The sequence databases:

[source: S-ESM3-PREPRINT, Appendix A.2.1.1, p37]
> UniRef release 2023 02 is downloaded and parsed from the official UniRef website

[source: S-ESM3-PREPRINT, Appendix A.2.1.1, p37]
> MGnify90 version 2023 02 is downloaded and parsed from MGnify

[source: S-ESM3-PREPRINT, Appendix A.2.1.1, p37]
> studies available in JGI on July 31st, 2023 are downloaded and concatenated into the JGI dataset

(The sentence opens "All non-restricted"; the quotation starts a word later because
the PDF breaks that hyphenated word across a line and the extracted text joins it up.)

[source: S-ESM3-PREPRINT, Appendix A.2.1.1, p37]
> OAS, which includes over a billion antibody sequences from 80 studies, is downloaded and clustered at 95% sequence identity

(The release identifiers read `2023 02` rather than `2023_02` because that is how the
underscore extracts from the PDF, and quotations here are checked against the extracted text.
The source renders them with underscores.)

The structural ones:

[source: S-ESM3-PREPRINT, Appendix A.2.1.5, p38]
> We use all PDB chains, clustered by unique PDB ID and entity ID within the PDB structure.

[source: S-ESM3-PREPRINT, Appendix A.2.1.5, p38]
> We filter to all structures deposited before May 1, 2020, determined by X-ray crystallography

— and better than 9 angstrom resolution, which is quoted here in prose rather than as a
quotation only because the resolution symbol does not survive text extraction.

[source: S-ESM3-PREPRINT, Appendix A.2.1.5, p38]
> AlphaFoldDB is downloaded as the v4 version specified

[source: S-ESM3-PREPRINT, Appendix A.2.1.5, p38]
> ESMAtlas is downloaded as version v0 and v2023 02

So eight components with a stated release, of which `amazebio.esm3` records two as obtainable
exactly as stated, four as obtainable but not at the stated granularity, and two as not
obtainable at all. The under-specification is real but it is not where it was expected, and it
is in four places.

**First: UniRef's tier is not stated.** "The official UniRef website" serves UniRef50, UniRef90
and UniRef100, and parsing any one of them satisfies the sentence. For release 2023_02 those
hold 60,479,070, 170,669,877 and 350,950,053 clusters — a 5.8-fold spread. Table S3's
clustering columns do not settle it, because they report ESM3's own clustering rather than
UniRef's tiers:

[source: S-ESM3-PREPRINT, Appendix A.2.1.2, p38]
> In all cases, data is clustered with mmseqs2

at its own identity thresholds. Any survival rate expressed as a fraction of "the UniRef
component" is therefore undefined until a tier is chosen and named, which is what the proxy
does rather than leaving the reader to assume one.

**Second: the counts do not reconcile.** Table S3 reports what ESM3 trained on after filtering,
by its own statement:

[source: S-ESM3-PREPRINT, Table S3, p40]
> Pretraining dataset statistics. Includes number of tokens, release, and clustering level. Numbers are derived after dataset filtering.

Its 90% level for UniRef is 156M against UniRef90's published 170,669,877 — 14.7M short. Its
90% level for MGnify is 621M against the release's own 729,215,663 clusters at 90% — 108.2M
short. Each shortfall, on its own, is larger than the 10.6M sequences §2 reports the filter
removing across every component together. Two readings survive and the published text does not
choose between them: either ESM3's own re-clustering produced different cluster counts from the
publishers' (plausible — the flags differ, and MGnify clusters with linclust at 90% coverage
where ESM3 states `--cov-mode 1 -c 0.8`), or more was removed than the filter description
accounts for. The consequence is specific and it costs this audit something: §5 of
`corpora.md` proposed sweeping the unpublished threshold until a reconstruction reproduced the
reported 10.6M, as the nearest available substitute for a conformance re-execution. That is not
available. The reported figure cannot validate a reconstruction when the stated corpus sizes
already miss their own sources by ten times it.

**Third: JGI cannot be pinned, and the two statements of its pin disagree.** The prose says
July 31st; Table S3's own cell says:

[source: S-ESM3-PREPRINT, Table S3, p40]
> All non-restricted studies available on July 30th, 2023.

A day either way would not matter if a snapshot existed. None does: the cited system is IMG/M
v.7, which serves no dated, checksummed release, and "non-restricted" is a per-study access
state that changes over time, so the same query on the same date made today need not return the
same set. This is the largest sequence component — 265,070M of 768,109M unique training tokens,
a little over a third of everything ESM3 saw — and it is unreconstructible. No proxy is
proposed for it. A different metagenomic collection would not be this component, and
substituting one would overstate what the audit covers.

**Fourth: the filter's scope list is not exhaustive, and three components fall outside it.**
§2's scope sentence names PDB, UniRef, MGnify and JGI, prefixed by "including". OAS,
AlphaFoldDB and ESMAtlas are training databases it does not name — 439M of the 3,379M unique
samples in Table S4. Whether the filter reached them is not stated either way, so they are
recorded as not addressed rather than as out of scope: A4.3 keeps "not applied", "applied but
undetectable" and "applied and retained" apart, and absence of mention supports none of the
three on its own.

## 7. What a proxy can pin

`amazebio.esm3` holds the component table and `tools/esm3_composition.py` writes it out; this
section is the argument behind two of its columns.

**UniRef 2023_02 is pinnable to the standard A1.3 reached for ESM-2.** The release is still
served from UniProt's previous-releases archive as one 211,819,312,677-byte tarball, and the
release metalink publishes an md5 over it, so the staged bytes can be shown to be the released
bytes rather than asserted to be. It is the same archive shape one release later, so
`amazebio.uniref` stages it unchanged. Because the tier is unstated, the pin is the whole
archive — all three tiers — rather than a tier chosen on the reader's behalf.

**MGnify 2023_02 is pinnable, and the release publishes an md5 per file.** "MGnify90" names the
release's 90%-clustered product, served as one 83,473,342,442-byte `mgy_clusters.fa.gz`; the
full protein set behind it is 30 further files and 362 GB. Which was parsed is not stated, and
§6's second finding is why the counts cannot settle it. This is also the component that carries
no taxonomic annotation at all — MGnify assigns MGYP accessions to predicted genes from
metagenomic assemblies, with biome metadata and no taxonomy — which makes it the clearest case
in the whole audit of a component an alignment-based filter can reach and a taxonomy-based one
cannot. That contrast with Evo's denylist is worth stating in the Phase A write-up on its own.

**PDB is a reproducible query rather than a release**, and the only component of the eight for
which that is true: deposition dates do not change, so the stated filter can be re-run today.
Two things keep it a substitution. Table S3's row states the date alone where the prose adds
X-ray crystallography and the resolution cutoff, and the table's wording would select a larger
set. And entries obsoleted since 2020 are no longer served, so what is reconstructed now is a
subset of what was available then.

**AlphaFoldDB v4 and ESMAtlas are stated exactly and not proposed as proxies here**, because
neither is named in the filter's scope and staging either is a large permanent cost for a
component whose filter status is unstated. That is a scope judgement, not a claim that they do
not matter — §8 is why they matter.

**JGI and OAS have no proxy.** §6's third finding covers JGI. OAS is served as a growing
per-study download set with no dated snapshot, and the prose states no date for it where
Table S3 does.

## 8. Two re-entry routes this corpus has and §4 above does not address

§4 above judged the alignment step a partial re-entry control, and that stands for the
components the filter is stated to query. Reading the pretraining-data appendix adds two routes
that the filter's description does not reach, and the second is specific to this model.

**Predicted-structure databases over already-filtered sequences.** AlphaFoldDB holds predicted
structures of UniProt sequences and ESMAtlas holds predicted structures of MGnify sequences. A
sequence removed from the UniRef component by the denylist has a counterpart in AlphaFoldDB
unless that database was filtered too, and the paper does not say it was. The sequence track and
the structure track are trained jointly, so this is not a route that needs the structure to be
decoded into sequence to matter.

**Inverse-folded sequences, which are in no database at all.** A 200M-parameter inverse-folding
model was trained on structures:

[source: S-ESM3-PREPRINT, Appendix A.2.1.3, p38]
> The model is trained on the sequence and structure pairs in PDB, AlphaFold-DB, and ESMAtlas

and then used to generate training data:

[source: S-ESM3-PREPRINT, Appendix A.2.1.3, p38]
> This model is used to generate additional sequences corresponding to each structure in the training data for ESM3

at 5 sequences per structure for ESMAtlas and AlphaFoldDB and 64 per structure for the PDB.
Table S4 counts 111M of these from AlphaFoldDB and 251M from ESMAtlas. That 362M is not a
footnote: the table's own sequence components sum to 2,781M and its sequence total is 3,143M,
so the generated sequences make up the difference and are counted as sequence training data.

The filter is an MMseqs query against the training databases, and a generated sequence is in no
database. Nothing in the published description reaches it. Whether the generated set was
filtered after generation, or the structures it was generated from were filtered before, is
unstated — and the question is sharper here than the usual absence-of-mention, because a
sequence generated from a viral structure is a novel sequence that no denylist built from
UniProt annotation has ever seen.

This is a Phase A finding about the published description, not a measurement. Whether anything
hazard-related actually survives by either route is A2's work, and neither route can be
measured without the structure-side components staged — which is a cost question for whoever
reaches A2.2, not an assumption to make here.

### What was actually staged

Recorded here because §7 argues what a proxy *can* pin; this is what it did pin, and the
numbers are the artefact's, not retyped — `artifacts/a1-5/composition.json` and the two run
manifests beside it carry them with the commit that produced them.

UniRef 2023_02, all three tiers, extracted from the release archive in one streaming pass:
UniRef100 118,682,175,057 bytes, UniRef90 62,727,425,913, UniRef50 30,392,833,174, plus each
tier's README, schema and release note. The md5 over the whole 211,819,312,677-byte archive
matched the value the release metalink publishes, so these are the released bytes rather than
bytes that look like them. MGnify 2023_02's 90%-clustered product staged as one
83,473,342,442-byte object, matching the md5 the release's own `md5sum.txt` publishes for it.
295.3 GB in total.

Two things about the acquisition are worth recording, because the next worker will hit them.
The 2023_02 archive's members are ordered UniRef100 first, so a run wanting only UniRef50 reads
past 110.5 GiB to reach it. And the two publishers throttle very differently: UniProt served
this container about 100 MiB/s across eight ranged connections, where EBI managed about 19
MiB/s across sixteen — 38 minutes against 69 for a file 40% the size.

One limit this does not remove. The staged components are the two that could be obtained as
stated; JGI and OAS could not, and the structure-side components were not bought. So nothing
here supports a statement of the form "x% of ESM3's corpus", and the composition artefact
carries no such figure by design.

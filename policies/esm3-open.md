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

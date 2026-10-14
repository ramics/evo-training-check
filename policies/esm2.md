# ESM-2 — no exclusion; positive control

ESM-2 is the positive control: a protein language model trained without a hazard-driven data
filter. Its value here is a concrete version pin for corpus reconstruction (A1.3).

---

## 1. What was excluded

**Nothing.** No retrieved source states any hazard-driven exclusion for ESM-2. The repository
documentation describes the training corpus and its held-out split without reference to safety
filtering of any kind.

## 2. Corpus and version pin

The repository's model table states ESM-2's training corpus and release directly. Every ESM-2
checkpoint carries the same one:

[source: S-ESM2-REPO, model table]
> UR50/D 2021_04

and the same table's overview row names the sampling:

[source: S-ESM2-REPO, model overview]
> UR50 (sample UR90)

So the corpus is the UniRef50 2021_04 clustering, with training sequences sampled from the
UniRef90 members of those clusters. **This corrects an earlier reading of this file**, which
pinned ESM-2 to the UniRef 2018-03 release (A1.3; DECISIONS.md D-024). 2018-03 is the release
the *held-out split files* refer to, and the same table attaches that release to the ESM-1-era
models rather than to ESM-2:

[source: S-ESM2-REPO, model table]
> UR50/S 2018_03

## 3. The held-out split files, and what they are not

[source: S-ESM2-REPO]
> The split files establishing which UniRef50 clusters were used as held-out evaluation set for pre-training

[source: S-ESM2-REPO]
> These files only contain only the UniRef50 IDs and UniRef100 IDs corresponding to the

— the UniRef database 2018-03 release, linked from the same sentence, under CC BY 4.0. The
duplicated "contain only" is in the source.

These IDs are a 2018-03 artefact. They identify held-out clusters in the release ESM-1 and
ESM-1b trained on, not in the 2021_04 release ESM-2 trained on, and UniRef50 cluster IDs are not
stable across releases. **No held-out split is published for ESM-2's own release.** Treat the
split files as evidence about the earlier models, and do not carry them into an ESM-2
reconstruction on the assumption that the IDs transfer.

## 4. What `UR50/S` and `UR50/D` mean, and how that is known

The suffixes are never defined anywhere in the ESM repository's own documentation. They are
defined in the lab's earlier paper, which introduces the three datasets the notation names:

[source: S-ESM1B-PNAS]
> 1) the low-diversity dataset (UR100) uses the UniRef100 representative sequences, 2) the high-diversity sparse dataset (UR50/S) uses the UniRef50 representative sequences, and 3) the high-diversity dense dataset (UR50/D) samples the UniRef100 sequences evenly across the UniRef50 clusters.

So **`/S` is sparse: one representative sequence per UniRef50 cluster. `/D` is dense: cluster
members, drawn evenly across clusters rather than in proportion to cluster size.**

That is a definition from a different paper about different models, so it is applied here only
because the repository's model table demonstrably uses the same notation. Three rows of that table
are the three datasets of this paper, one each:

[source: S-ESM2-REPO, model table]
> `esm1_t34_670M_UR100`        | 34           | 670M        | UR100 2018_03

[source: S-ESM2-REPO, model table]
> `esm1_t34_670M_UR50S`        | 34           | 670M        | UR50/S 2018_03

[source: S-ESM2-REPO, model table]
> `esm1_t34_670M_UR50D`        | 34           | 670M        | UR50/D 2018_03

and the paper states which of them ESM-1b is, matching the table's `UR50/S 2018_03` row for
`esm1b_t33_650M_UR50S`:

[source: S-ESM1B-PNAS]
> We scale the hyperparameters identified by this search to train a model with ∼650 M parameters (33 layers) on the UR50/S dataset, resulting in the ESM-1b Transformer.

**What this settles for a reconstruction.** ESM-2 is `UR50/D`, so its corpus is not the UniRef50
representative sequences; it is cluster members with cluster membership preserved. A reconstruction
that stages only the 49,874,565 UniRef50 representatives would be the wrong dataset — the sparse
one — and would understate the corpus by the ratio of members to clusters.

**What it does not settle, and must not be read as settling.** Two gaps survive:

1. **The tier sampled differs.** The definition above samples *UniRef100* members; ESM-2's own
   overview row reads `UR50 (sample UR90)` (§2), i.e. UniRef90 members. The suffix therefore
   carries the mechanism — even per-cluster sampling of members — and ESM-2's own table carries
   the tier. A reconstruction follows the table: UniRef50 clusters, UniRef90 members.
2. **"Evenly" is a dataloader property, not a corpus property.** Whether the even draw is one
   member per cluster per epoch, resampled each epoch, and under what seed, is not stated for
   either model. It does not change what to stage — members plus membership — and it does bear on
   any claim about how often a given sequence was seen, which this audit does not make. Not
   guessed; see §5.

## 6. What ESM-2's own paper says, and where it contradicts itself

Retrieved 2026-10-14 (S-ESM2-PREPRINT), so the corpus pin no longer rests on the repository model
table alone. The paper confirms the pin, resolves both of §4's open mechanism questions, and
introduces one internal contradiction that has to be carried rather than resolved.

**The version.** The dataset appendix opens:

[source: S-ESM2-PREPRINT]
> UniRef50, September 2021 version, is used for the training of ESM models.


No UniProt release is dated September 2021. The 2021 releases are 2021_01 (10-Feb), 2021_02
(07-Apr), 2021_03 (09-Jun) and 2021_04 (27-Oct), so a download taken in September 2021 would have
been 2021_03. Two other statements in the same paper point the other way. The de-novo filtering is
described as run

[source: S-ESM2-PREPRINT]
> when 2021 04 was the most recent release


and the main text gives the scale as

[source: S-ESM2-PREPRINT]
> 138 million UniRef90 sequences


which is 2021_04's UniRef90 count of 138,515,945, not 2021_03's 135,301,051. So the pin stays at
2021_04 on the weight of three first-party statements — the model table, the "most recent release"
remark, and the UniRef90 figure — against one bare date that matches no release at all. The
contradiction is logged rather than smoothed over; see DECISIONS.md D-028.

**The sampling mechanism**, which §4 left open in both directions, is stated outright:

[source: S-ESM2-PREPRINT]
> a minibatch of UniRef50 sequences is sampled for each training update. Each sequence is then
> replaced with a sequence sampled uniformly from the corresponding UniRef90 cluster


That settles two things D-025 had to leave as gaps. The members are drawn from UniRef90, confirming
the repository table's `UR50 (sample UR90)` over the ESM-1b paper's UniRef100 — D-025 called that
right. And "evenly" means resampled per training update, uniformly within the cluster, not a single
draw. The seed remains unstated, so exposure frequency claims stay constrained.

**ESM-2's training set is not the release.** This matters for A1.3's deliverable and it is easy to
miss. The release holds 49,874,565 UniRef50 clusters; the paper trains on

[source: S-ESM2-PREPRINT]
> 43 million UniRef50 training clusters


The difference is roughly 6.9 million clusters, and the paper itemises only about 310,000 of it: a
0.5% validation split (≈250,000 sequences), 1,027 sequences annotated "artificial sequence", and
58,462 proteins returned by a jackhmmer search around 81 manually curated de-novo proteins. The
remainder falls to an unquantified step — removing training sequences that match a validation
sequence at 50% identity under a stated MMseqs search. So the staged corpus is the *release*, and
ESM-2's *training set* is a filtered subset of it whose filter is specified as to method and
parameters but not as to magnitude, and whose inputs (the validation split, the 81 de-novo queries)
are not published. Reconstructing the training set exactly is therefore not possible from published
material; the gap is a §A0 finding.

One thing worth naming for the project rather than just for this file: that de-novo filter *is*
exclusion-based data filtering, with reproducible parameters and a stated purpose — though the
purpose given is enabling future generalisation work, not biosecurity. ESM-2 is this audit's
positive control precisely because it carries no biosecurity exclusion, and it remains so. But it
is not unfiltered, and a write-up that calls it unfiltered would be wrong.

## 5. Open questions

None material for A0.3 — ESM-2 carries no policy to read three ways. What remains for A1.3, after
§6 answered the rest:

1. **The resampling seed is unstated**, so the per-update draw from each UniRef90 cluster cannot be
   reproduced. §6 settled that the draw happens per update and is uniform within the cluster; the
   seed is the residue. Recorded as under-specification per §A0. It constrains claims about
   exposure frequency, not corpus contents.
2. **The magnitude of ESM-2's own filtering is undocumented**, and its inputs are unpublished — see
   §6. About 6.6 million of the 6.9 million clusters separating the release from the training set
   fall to one unquantified MMseqs step.
3. **The Science version of record is still paywalled** (S-ESM2-SCIENCE, HTTP 403). Quotes here come
   from the preprint. Anything load-bearing should be checked against the version of record before
   publication, including — especially — the "September 2021" contradiction, which may simply have
   been corrected in review.
4. **2021_04 is staged and verified.** The release is served only as a single 169 GB
   `uniref2021_04.tar.gz`, published md5 `444f0a7062a65a988ba1d5949d1d6419`, which a streaming pass
   read in full and matched; UniRef50 then counted 49,874,565 clusters against the release notes'
   49,874,565. See D-026 and D-027.

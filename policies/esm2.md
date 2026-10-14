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

## 5. Open questions

None material for A0.3 — ESM-2 carries no policy to read three ways. Three matter for A1.3:

1. **The sampling schedule behind `/D` is unstated** for both papers: per-epoch resampling versus a
   single draw, and the seed. Recorded as under-specification per §A0. It constrains claims about
   exposure frequency, not the corpus contents.
2. **ESM-2's own paper is not a retrieved source.** bioRxiv rate-limited every attempt on
   2026-10-14 and the Science version is paywalled (S-ESM2-PREPRINT, S-ESM2-SCIENCE). The corpus
   pin here therefore rests on the repository model table, which is first-party but is not the
   paper. Retry the preprint; rate limiting lifts.
3. **2021_04 is retrievable, but only in bulk.** The UniProt previous-releases archive serves that
   release as a single 158 GB `uniref2021_04.tar.gz` with no per-tier files, published md5
   `444f0a7062a65a988ba1d5949d1d6419`. The release notes give the composition
   (UniRef50: 49,874,565 clusters), so the version pin is exact even where the bytes are not
   local. See D-024 for how A1.3 handles that.

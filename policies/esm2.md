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

## 4. Open questions

None material for A0.3 — ESM-2 carries no policy to read three ways. Two matter for A1.3:

1. **`UR50/S` versus `UR50/D` is never defined.** Both strings appear in the model table; nothing
   in the retrieved documentation says what the suffixes mean. The distinction decides whether the
   corpus is one representative per cluster or a per-epoch sample from each cluster, which changes
   what a reconstruction should contain. Resolving it needs the ESM-2 paper, which is not a
   retrieved source. Recorded as under-specification per §A0, not guessed.
2. **2021_04 is retrievable, but only in bulk.** The UniProt previous-releases archive serves that
   release as a single 158 GB `uniref2021_04.tar.gz` with no per-tier files, published md5
   `444f0a7062a65a988ba1d5949d1d6419`. The release notes give the composition
   (UniRef50: 49,874,565 clusters), so the version pin is exact even where the bytes are not
   local. See D-024 for how A1.3 handles that.

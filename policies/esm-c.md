# ESM-C — no exclusion stated; viral sequence included

Recorded for the record. ESM-C was listed as the viral-excluded protein-level test condition in
`DESIGN.md` v0.2. Its own sources contradict that, which is why v0.3 moved that role to
ESM3-open and kept ESM-C as a second viruses-included comparison (DECISIONS.md D-005).

---

## 1. What was excluded

**Nothing, as regards hazard-driven data filtering.** No retrieved source states a
training-data exclusion for ESM-C.

What the training data is:

[source: S-ESMC-HF-6B]
> ESMC was trained on protein sequences from UniRef, MGnify, and the Joint Genome Institute (JGI).

The preprint lists the source databases in full, and viral genomes are among them:

[source: S-ESMC-PREPRINT, p100 Table]
> IMG/VR (release 7, Dec 19, 2022)

described in the same table row as "Cultivated and uncultivated viral genomes". The composition
of that viral content:

[source: S-ESMC-PREPRINT, p14]
> Almost all viral sequences are metagenomic, largely derived from bacteriophages.

So ESM-C's viral content is present, version-pinned, and predominantly bacteriophage — which
is what makes it a useful comparison rather than merely a correction.

## 2. The safeguards that do exist are not data filtering

The published measures are release-time evaluation and deployment-time control:

[source: S-ESMC-HF-6B]
> Prior to release, we conducted evaluations to inform our understanding of capability uplift for specific misuse-relevant functional tasks.

[source: S-ESMC-HF-6B]
> We implement guardrails that detect and restrict the use of keywords and sequences corresponding to controlled pathogens and toxins on our freely accessible platform.

The second is an inference-time control on the hosted platform, not a property of the released
weights. It is a different kind of safeguard from anything else in this store and is out of
scope for this audit, which concerns training-data filtering.

## 3. Searches establishing the absence

| Term | ESMC preprint (111pp) | ESMC-6B card |
|---|---|---|
| exclud* | 16, all unrelated | 0 |
| select agent | 0 | 0 |

The 16 "exclud" occurrences concern benchmark latency comparisons, Pfam annotation counts,
optimizer weight decay, and the AlphaFold3 ligand exclusion list. None concerns hazard-driven
data filtering. Searched case-insensitively across the full document.

## 4. A developer-run precedent worth noting

The ESMC authors ran an evaluation closely resembling this project's Phase B:

[source: S-ESMC-PREPRINT, p110]
> datasets collected from ProteinGym, all of which are from viral proteins

on 25 such datasets, comparing ESMC against ESM2 650M, ESM3 1.4B Open, a BLOSUM62 baseline and
EVMutation, concluding:

[source: S-ESMC-PREPRINT, p110]
> The results show ESMC models perform worse than or similar to existing tools for variant effect prediction in viral proteins

This is a direct precedent for the Phase B design, including the non-neural baseline that
`DESIGN.md` §B4 requires, and it uses 25 viral assays where §B2 anticipated as few as four.
It also means any Phase B result on ESMC has a published comparison to be consistent with.

## 5. Note on source quality

The ESMC-6B and ESMC-600M model cards are byte-identical (same SHA-256; see sources.json). One
shared card serves multiple variants, so neither can be cited as evidence about a specific
variant's training data. Variant-level claims need the preprint.

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
5. **Version of record.** The Evo 2 Methods section of the Nature paper is unretrieved
   (S-EVO2-NATURE-METHODS) and should be checked before publication, in case it adds procedure
   the preprint omits.

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

The two OpenGenome2 trees hold the same sequences and are not interchangeable as evidence. From
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

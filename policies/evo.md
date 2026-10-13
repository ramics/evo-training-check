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

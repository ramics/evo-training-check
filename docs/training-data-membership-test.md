# Direct test: are the detected records in Evo 2's training data?

**Belongs to:** A6.1 · **Bears on:** A7.3, A7.5, X1.8, X1.9 · **Date:** 2026-10-26

## The question, and why counting could not answer it

A7.3 established that OpenGenome2's JSON training format matches Evo 1's released viral
component to the record and the nucleotide, and that the released **FASTA** is a 304,448-record
superset of it carrying the 264,570 records the published procedure removes. That is an argument
from totals. It could not be upgraded by a join: the JSON carries a single `text` field with no
accession and no lineage tag, so no identifier links it to anything (`policies/evo.md` §8), and
none of the filter's six rules can even be executed against it.

Both representations carry the nucleotides. That is the available bridge, and this is the test.

## Method

- **Queries.** All 314 records of X1.9's published per-component table — the records whose
  detected Pfam family is named for a denylisted virus family — pulled from the pinned FASTA in
  one pass (length-checked against `source.bytes` first). **314 of 314 found, none missing.**
- **Needles.** Three 48-mers per record at spread offsets, each with its reverse complement:
  1,880 strings. Windows containing an ambiguous base are skipped. 48 is chosen so chance
  occurrence is not a live alternative — 36.2 Gnt against 4^48 is an expected count near 5e-19.
- **Target.** All six files of `arcinstitute/opengenome2`
  `json/pretraining_or_both_phases/imgvr_untagged/` at pinned revision
  `84d2a7e690c8bb395d1f4868822dfa031ea561c6` — the training format itself, not its equal-totals
  twin. Streamed and matched with multi-pattern exact search.
- **Coverage check.** The pass counted **2,653,047** records before the duplicated `valid`
  chunk, which is A7.1's and A7.3's figure to the record, reproduced here by a different method.
  2,653,097 including the duplicate.

## Result — the records the filter removes are absent

| | |
|---|---|
| records read | 2,653,097 (2,653,047 distinct) |
| needle matches | 1,252, mapping to **341 distinct needles** and **90 distinct records** |
| **records the published rule removes that are present** | **0 of 17** |
| **the papillomavirus record** (`IMGVR_UViG_643677429_000001`) | **0 of its 6 needles — absent** |

All three `Papillomaviridae` records among the 17 are absent, as are the Geminiviridae (8),
Retroviridae, Rhabdoviridae, Hantaviridae, Flaviviridae, Picornaviridae and
Caliciviridae|Picornaviridae ones.

**So the filter held on the training data, by direct per-record measurement rather than by
counts reconciling.** The 264,570-record discrepancy is a property of the released FASTA alone.

## The 90 records that *are* present, and why they belong there

82 Poxviridae-named, 5 Flaviviridae, one each Geminiviridae, Adenoviridae, Retroviridae. Every
one has `label_rule_outcome = ''` — the published rule does not remove it. The filter reads
taxonomy labels, not protein content, so these were never candidates for removal.

**And they are not mislabelled viruses.** This is a false positive of *this project's* naming
rule, which is the finding worth carrying forward:

- X1.8's `matched_on` is **`identifier`** for all of them — the family entered a denylisted
  group because its Pfam *name* begins `Pox`, `Av_adeno` and so on. Pfam's own descriptions
  hedge accordingly: `PF03288` is "Poxvirus D5 protein-**like**", `PF04947` is "Poxvirus Late
  Transcription Factor VLTF3 **like**". These are families shared across nucleocytoplasmic large
  DNA viruses and phages, named for where the gene was first characterised. Contrast `PF00519`,
  "Papillomavirus helicase", matched on **description**, with no hedge.
- The match strengths separate cleanly:

  | | these 90 records | the papillomavirus record | A7.5's top row |
  |---|---|---|---|
  | score ÷ threshold | median **1.4×**, max **6.8×** | 17× | 29.5× |
  | rows above 10× threshold | **0 of 92** | — | — |
  | identity to consensus | 0.24–0.44 | 0.59 | 0.62 |
  | model coverage | median 0.74 | 0.997 | 0.993 |

  76 of the 92 rows sit within 2× of threshold.
- Their labels are specific rather than missing: `r__Duplodnaviria;k__Heunggongvirae` (tailed
  bacteriophages), `r__Varidnaviria;k__Bamfordvirae` (large DNA viruses), one `Mimiviridae`.
  These are phages and giant viruses carrying genes genuinely in those broad families.

**Consequence for reporting.** The name axis over-counts. Assigning a family to a denylisted
group on its Pfam identifier pulls in NCLDV-wide genes, so the 314 is an upper bound on
"records carrying a denylisted family's protein" and should not be reported as though every
member were a near relative of the named family. See D-261.

## What is unaffected

The papillomavirus worked example (`docs/phase-a-worked-example-papillomavirus.md`) stands as
written: `PF00519` matched on description, 449.8 against a curated cutoff of 26.5 over 99.65% of
the model. Its claim was always about the released FASTA, and this test is the direct evidence
for the negative half of that claim rather than a change to it.

## Reproducing

Exploratory check, scratch output only, nothing published to the durable store (D-193, D-224).
Scripts were throwaway; the method above is the specification, and the registry
(`data/pfam/38.2/`) verifies against the publisher's md5.

---

# Addendum: the training corpus can be joined to the released FASTA, and is therefore auditable

**Date:** 2026-10-26 · **See:** D-262

The test above searched for named sequences. This closes the general case.

## Method

Hash-join on sequence, the only field the two artefacts share. Inverted deliberately — the
HuggingFace read goes first and persists, because an earlier attempt built a 20-minute in-memory
FASTA index and lost it to a `BrokenPipeError` on the download. Only `curl --retry
--retry-all-errors` has survived this transfer; a non-zero exit refuses rather than persisting a
truncated read, so a partial download cannot pass as a complete one.

1. **Phase A** — stream all six training files, digest each record's `text`
   (blake2b-64 of the uppercased sequence, plus a `(length, first-48, last-48)` fallback key),
   persist both digest arrays to disk. 2,653,097 records, 448 s.
2. **Phase B** — one in-region FASTA pass, testing each entry's forward **and reverse-complement**
   digests against those arrays. 2,957,495 entries, ~19 min.

## Result — a complete join

| | |
|---|---|
| JSON records | 2,653,097 (**2,652,840** distinct; 257 are byte-identical duplicates) |
| resolved by exact sequence digest | **2,652,840 — all of them** |
| needing the length+ends fallback | **1** |
| unresolved | **0** |
| distinct accessions resolved | **2,653,047** |
| FASTA entries absent from the training corpus | **304,448** |

**Sequences are preserved verbatim or not present at all.** With the fallback tier catching one
record in 2.65 million, there is no systematic preprocessing transformation between the released
FASTA and the form the model consumed — whatever the dataset card means by distinguishing them,
it is not a change to the bases.

Two of A7.3's figures come back independently here, by a method sharing no code with it:
**304,448** absent entries, and **2,653,047** records in the training corpus.

The accession list is `training_accessions.txt`, 2,653,047 lines, sha256
`413b92e13df518b9cefa3bdeba99449a8298e41a40c98dd9aa39b735f16b0568`. It is scratch, not
published: producing it as a citable artefact belongs to a task of its own, through
`repro.run`.

## What this changes

**Every rule in `policies/specs/evo1-literal.yaml` is now executable against what Evo 2 trained
on.** That has not been possible before — `policies/evo.md` §8 records the training format as
carrying no accession and no lineage, and §10's finding rests on matching totals for exactly
that reason. A sequence join supplies the accession the artefact omits, and the IMG/VR metadata
supplies the labels from there. Every Phase A number currently measured on the released FASTA
can be re-measured where it matters.

**It also narrows the disclosure finding, and that should be said plainly.** "The only
representation anyone can audit is the one that fails the audit" is no longer right. The
training representation is auditable too — via a 36-gigabase sequence join that no published
sentence mentions and that an outside reader would have to invent. That is still a real
reporting gap, and it is a smaller claim than the one it replaces.

## The open number

2,917,521 accessions in the FASTA, 2,653,047 in the training corpus: a difference of
**264,474**. The published procedure removes **264,570**. The gap is **96 records**, against
A7.2's 95 forward failures.

So on this arithmetic roughly 96 records that the published procedure removes are nonetheless in
the training corpus. They are now enumerable by a metadata join with no sequence work. **Not yet
enumerated** — and the arithmetic chains counts measured on two IMG/VR releases, so the 96 is a
pointer, not a result.

## A disagreement between the two methods, unresolved

On the 314 records, the needle search reported 90 present and the join reports **82**, agreeing
on all 82, with the join finding nothing the needles missed. The asymmetry has an obvious
candidate: a 48-mer can match a homologous *different* record where a full-sequence digest
cannot, making the join the stricter instrument and those 8 likely needle false positives. If
so the earlier "90 records" figure is 82. Stated as a discrepancy rather than resolved, because
it has not been checked.

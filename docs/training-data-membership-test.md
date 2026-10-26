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

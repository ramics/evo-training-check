# A worked example: one papillomavirus genome in OpenGenome2's released FASTA

**Belongs to:** A6.1 (Phase A write-up) · **Instrument:** A7.5 · **Inputs:** X1.8, X1.9 ·
**Context:** `policies/evo.md` §10, A7.3

A6.1 reports the Evo 2 conformance result as counts. This is the one record behind them traced
end to end, for a reader who wants to see a single case rather than a population. It is a worked
example and not a finding of its own: the finding is A7.3's, the counts are A7.2's, and the
measurement is A7.5's.

**Written to be dropped into the A6.1 draft**, whose canonical copy is
`phase-a-writeup/phase-a-for-funders.md` in the project's shared folder and not in this
repository. Whoever lands A6.1 should either bring that file into the repo or state where the
canonical copy lives — A6.1's own State section flags the same gap, because the third Done-when
criterion is not mechanically checkable while the draft sits outside.

## The record

| | |
|---|---|
| record | `IMGVR_UViG_643677429_000001`, entry 1 |
| component | OpenGenome2 `fasta/plasmids_phage/imgvr.fasta.gz` |
| length | 7,346 nt — near-complete for a papillomavirus (~7.9 kb) |
| genes called | 6 (pyrodigal metagenomic, D-077) |
| IMG/VR taxonomy | `r__Monodnaviria; k__Shotokuvirae; p__Cossaviricota; c__Papovaviricetes; o__Zurhausenvirales; f__Papillomaviridae; g__Gammapapillomavirus; s__Gammapapillomavirus 7` |
| label method | **RefSeq** reference match — not a geNomad prediction (21 of X1.9's 314 records are RefSeq; 223 are geNomad) |
| published rule outcome | **`removed`** — executing Evo 1's `remove-denylisted-families` against this record's own label removes it. 17 of the 314 reach that outcome; for the rest the rule does not resolve |

`Papillomaviridae` is one of the 19 families the published procedure names for removal
(`policies/specs/evo1-literal.yaml`, rule `remove-denylisted-families`, `S-EVO1-PREPRINT`
Appendix B.2 p32). D-110 verified that enumeration against the Science version of record: the
procedure paragraph is character-for-character identical to the preprint across 1,169
characters bar two copy-edits, and all 19 families match in both directions.

## The two matched regions

Both sit on the same called gene, `gene1`, which is 649 residues. Pfam 38.2, searched at Pfam's
own curated gathering cutoffs (D-076); no threshold is supplied by the caller.

| accession | profile | region on gene | model coverage | score | cutoff | identity to consensus |
|---|---|---|---|---|---|---|
| `PF20450` | `PPV_E1_DBD` — E1 DNA-binding domain | 211–350 | 140/140 = **1.000** | 170.4 | 25.0 | 0.4286 |
| `PF00519` | `PPV_E1_C` — papillomavirus helicase | 354–640 | 288/289 = **0.9965** | 449.8 | 26.5 | 0.5868 |

`identity` is identity to the model's **consensus string**, which is a summary of a family's
model and not a sequence that exists. It is not identity to any member of the family and not a
measure of resemblance to any named organism. The bit score against the curated cutoff is the
detection claim; coverage and identity describe the shape of the match. See A7.5's
`reading_this_table`.

## Why the gene call is sound

The question was asked directly — whether the protein derivation, rather than the corpus, could
account for a hit like this. It cannot, and the reason is structural rather than statistical.

One called protein carries **two different Pfam models, non-overlapping, in the canonical E1
order**: the DNA-binding domain over 100% of its model at 211–350, then the C-terminal helicase
over 99.65% of its model at 354–640, with a three-residue gap between them. A frameshift, a
wrong-strand call or a chimeric ORF breaks one alignment or both; none of them lays two domains
of the same viral protein end to end in the order the real protein has them. The region also
carries the Walker A / P-loop motif, the functional signature of the SF3 helicase E1 is.

An independent BLAST of that protein against nr, run by the project owner through A7.5's
`--fasta-out` side channel (D-254), returned papillomavirus E1. The HMM reading and the
alignment-based reading agree.

## Provenance, link by link

Every link was verified rather than assumed, on 2026-10-26.

| link | how it was verified |
|---|---|
| the staged object is the pinned one | `head_object` length = 11,220,266,895 bytes, checked before the first byte is read; the pass refuses on a mismatch |
| the record is in that object | found as entry 1 on a fresh sequential read, 19 minutes in, at 97% of the object |
| the protein derives from that record | re-derived with `profilesearch.call_genes`; `gene1` is **byte-for-byte identical** to the sequence that was BLASTed (649 residues, sha256 `7cb51c7e…`) |
| the profiles are the pinned ones | Pfam 38.2 `Pfam-A.hmm.gz` and `Pfam-A.hmm.dat.gz` match the publisher's stated md5 (`7ab3c4e2…`, `aab36468…`); `PF00519`'s cutoff 26.5 and model length 289 are read from the registry |
| the numbers reproduce | both rows reproduce to the digit, twice, independently — once from the supplied protein alone and once from the protein re-derived from the corpus |
| the row is the published one | A7.5's published table, `corpora/results/a7-5/regions-denylist-named-family-records-imgvr-pfam-38.2.tsv` |
| the record was a named input, not a chosen one | X1.9's published per-component table, `corpora/results/x1-9/denylist-named-family-records-imgvr.tsv` |
| the accession was a named input | X1.8's published family table, `corpora/results/x1-8/denylist-named-families.tsv`: `Papillomaviridae`, `specificity: viral_only` |

No residues are carried here, in A7.5's three published outputs, or in the durable store
(D-103). The protein is cited by digest and coordinates.

## What may be claimed, and what may not

This is the distinction A7.3 withdrew a claim over, and it governs every sentence about this
record.

**Supportable.** A near-complete papillomavirus genome, which Evo 1's published procedure
removes when that procedure is executed against the record's own IMG/VR metadata, is present in
OpenGenome2's released FASTA representation — the only representation carrying source
accessions, and therefore the only one from which the filter can be audited at all
(`policies/evo.md` §8).

**It is a record of the population A7.3 counted, and not a verified member of that count.**
A7.3's `denylist-detail.json` reports the family rule removing **2,102** records from the
released FASTA under the published chain (4,706 counting denylist membership alone), across 8
of the 19 named families, of which **129 are labelled `Papillomaviridae`** — the rest being
Picobirnaviridae 1,420, Circoviridae 461, Orthomyxoviridae 56, Retroviridae 18, Adenoviridae
10, Coronaviridae 6, Geminiviridae 2. This record is a `Papillomaviridae`-labelled record that
the rule removes, which is the same shape as those 129.

Membership is not asserted, because the two figures read **different IMG/VR releases**: A7.3's
count rests on the 2022-12-20 release scan, and X1.9's record list — the input this example was
drawn from — rests on 2022-09-20. The two releases carry the same file name and differ in it
(D-052, D-054), so joining a record from one onto a count from the other is exactly the kind of
step that looks free and is not. Whoever wants the count and the example in one sentence should
re-derive one of them on the other's release first.

Note also that A7.3's 129 is the **label** axis — records whose IMG/VR metadata carries a
denylisted family label — while X1.9's `Papillomaviridae 4` is the **name** axis: records where
the audit's own Pfam detection named that family. Neither set contains the other, and A7.5's
State section records the same trap costing a round of confusion between 31, 308, 314, 315 and
319. Any sentence pairing a count with this example has to say which axis it is on.

**Not supportable.** That it is in what Evo 2 was trained on. A7.3 counted both
representations: the JSON training format holds 2,653,047 records and 36,236,025,613
nucleotides, which is Evo 1's released viral component exactly — zero delta on both — while the
FASTA holds 304,448 records and 2,641,256,603 nucleotides more. Measured against the training
format, the filter did not fail. The earlier reading, that these records escaped into the
training data, is withdrawn (`policies/evo.md` §10).

**The limit of even the negative claim.** The JSON records carry no accession, so the two
representations cannot be joined record by record. "The same record count and the same
nucleotide count" is the strongest statement the published artefacts support — a strong one,
but not a proof of identity. So this record cannot be shown *absent* from the training format
either; what is shown is that the training format's totals equal the filtered component's
exactly.

**Whose filter.** The procedure is Evo 1's; the output is Evo 2's (D-019). Evo 2 adopts it by
reference, and its version of record scopes the adoption in the past tense — "As previously
described, the OpenGenome dataset **was** curated to exclude..." reads as provenance on a reused
dataset, where the preprint's "As in Evo 1, we excluded..." reads as a claim about the new
release. Both are published and they do not say the same thing (`policies/evo.md` §10).

**No claim about intent.** Nothing here speaks to what anyone meant to do. The claim is a
conformance mismatch between a stated procedure and a released artefact.

**No hazard claim.** A7.5 reports alignment statistics and nothing about what a sequence does;
DESIGN.md §4 keeps hazard assessment out of scope. For calibration rather than for publication:
`Gammapapillomavirus 7` is a cutaneous type rather than one of the oncogenic alpha types, and E1
is the replication helicase rather than an oncogene. The conformance finding does not rest on
the hazard reading and should not be written as though it does.

**Reporting limits (§4).** The family is a published name on a published list and the count is
of records in a released corpus. Neither is a capability claim, and this example is not a
statement that any model is more capable for this family than another.

**Disclosure.** Record identifiers and coordinates stay with the project owner until X3.1, which
is `HOLDING`. No external circulation, including informal.

## Reproducing it

```
# the published row
aws s3 cp s3://amazebio-corpora-897641797669/corpora/results/a7-5/\
regions-denylist-named-family-records-imgvr-pfam-38.2.tsv - | grep IMGVR_UViG_643677429_000001

# the registry, verified against the publisher's md5
pixi run -e dev python tools/stage_profiles.py --registry pfam
```

Re-deriving the protein is one sequential pass over the 11.22 GB object — there is no index into
a gzip stream and the record sits at 97% of it, so the cost is ~19 minutes, in-region and
unmetered. A7.5's own pass is the supported path; the one-record check was a throwaway script
and is deliberately not shipped, because A7.5 already measures what it measured.

# Evo 2's viral component, audited against the procedure it adopts

**Task A7.3 · `DESIGN.md` §A7 · Deliverable 1**

> **Not cleared for circulation.** `DESIGN.md` §4 requires disclosure before publication and
> §7 requires the headline reproduced by a second method. A3.3 is `done` and the gate is open
> (D-215); X3.1's disclosure window is not. Nothing here goes outside the project until it is.

---

## The finding in three sentences

Evo 2 publishes its viral component twice, as a FASTA tree and as a JSON training tree. The
JSON tree — the preprocessed form the model trains on — is Evo 1's released viral component
exactly, to the record and to the nucleotide. The FASTA tree, which is the only representation
carrying a source accession and therefore the only one from which the filter can be checked at
all, holds 304,448 records and 2.64 billion nucleotides more, among them 264,570 records that
the published procedure removes.

So the filter's output was carried forward unchanged into what was trained on. The artefact a
reader must use to audit the filter is not that set, and no published sentence distinguishes
them.

## What was measured

| | records | nucleotides | source |
|---|---|---|---|
| Evo 1's released viral component | 2,653,047 | 36,236,025,613 | A7.1 scan |
| OpenGenome2 `json/…/imgvr_untagged/`, train + test | **2,653,047** | **36,236,025,613** | A7.3, `json-tree.json` |
| OpenGenome2 `fasta/plasmids_phage/imgvr.fasta.gz` | 2,957,495 | 38,877,282,216 | A1.4 / A7.2 |
| difference, FASTA over training format | 304,448 | 2,641,256,603 | |

Both deltas against Evo 1's release are **zero**. Not close — zero.

Two notes on how that total is formed, because both would otherwise be invisible. The JSON tree
publishes six files; its `valid` chunk holds the same 50 records and the same 363,466
nucleotides as its `test` chunk at a different sha256, which is gzip metadata rather than
content, so summing all six double-counts a split. The distinct total is train plus test, and
the duplicate is detected by comparing split totals rather than assumed from the file sizes. And
the comparison is on counts, not identity: the JSON records carry a bare `text` field with no
accession (`policies/evo.md` §8), so the two representations cannot be joined record by record.
Two independently derived corpora agreeing to the nucleotide on 36.2 billion of them is not a
coincidence worth entertaining, but it is evidence of identity rather than proof of it, and this
document does not call it proof.

## What is claimed, and at what strength

The task's first step was to decide what the arithmetic supports before writing. Four
statements, in descending order of what the evidence carries:

**Claimed.** OpenGenome2 publishes one component in two representations that differ by 304,448
records, and the published Methods describe no step that would produce the difference. This is
arithmetic over two pinned artefacts and a quotation; it is not contestable without contesting
the publisher's own files.

**Claimed.** The 264,570 records the published procedure removes are present in the FASTA
representation and absent from the training format. This follows from the first claim and A7.2's
re-execution, both reproduced here from pinned intermediates.

**Claimed, and this is the one that matters for `DESIGN.md` §A7.** The filter's conformance
cannot be checked against the artefact the filter produced. The training format is the filter's
output and carries no accession; the FASTA carries the accession and is not the filter's output.
Each representation withholds exactly what the other supplies.

**Not claimed.** That Evo 2 failed to apply the filter. Measured against the training format it
plainly did apply it, and the version of record says the reused dataset was curated. Nothing
here speaks to intent, and the earlier reading of A7.2's figure — that 264,570 records escaped
the filter into the training data — is withdrawn by this document. It was the natural reading of
the FASTA alone and it is wrong.

## The alternatives, each as a check that was run

### 1. The FASTA is a pre-filter staging artefact

**Live, and it is the finding.** `policies/evo.md` §7 recorded that the FASTA and JSON trees are
not a strict mirror, so this was never speculative. `tools/evo2_json_tree.py` streamed all six
JSON files — 10.4 GB, 2,653,097 records counted — and the result is the table above. The check
came back confirming the alternative rather than excluding it, which is why this document's
headline is not A7.2's.

The verdict is recorded in the artefact as one of four values, decided before the counts were
read: `same_content`, `training_format_is_evo1s_release`, `filtered_downstream`, and
`differs_otherwise` for the case where neither reference matches. It returned the second.

### 2. Evo 2's component was built from a different IMG/VR release

**Excluded.** A7.2 joined all 2,917,521 distinct released accessions against staged IMG/VR v4.1
and found **zero** absent from it. A component built from a later release would carry accessions
v4.1 does not have; none does. The v4/v4.1 distinction does not bear on this, because the
erratum corrects taxon rank fields and not the accession set (D-063, D-071).

### 3. "As previously described" scopes to the inherited records rather than to Evo 2's corpus

**Confirmed by the version of record, and it does not weaken the finding — it sharpens it.**
S-EVO2-NATURE-METHODS, retrieved 2026-10-17 and quotable under CC BY-NC-ND, opens its data
curation with:

> Our previously published OpenGenome dataset was used in its entirety as part of the training
> data for this study. This included representative prokaryotic genomes available through GTDB
> release v214.1, and curated phage and plasmid sequences retrieved through IMG/VR and IMG/PR.
> As previously described, the OpenGenome dataset was curated to exclude genomic sequences of
> viruses which infect eukaryotic hosts.

The curation sentence is past tense and its subject is OpenGenome. It is provenance on a reused
dataset, not a step applied to OpenGenome2. And the Methods' own enumeration of what OpenGenome2
added — updated prokaryotic genomes, eukaryotic reference genomes, metagenomes, organelle
genomes, promoters, augmented transcripts, genic regions — contains nothing viral. IMG/VR
appears three times in the whole document: in that sentence, in a note about phylogenetic tags,
and as a row in the training-mix table.

So the Methods account for 2,653,047 viral records, and the released FASTA holds 2,957,495. The
reading is right and the consequence is that the FASTA has 304,448 records the Methods do not
explain. Recorded in full at `policies/evo.md` §10.

## The denylist rules, at the taxon each one names

Of the 264,570 records in the FASTA that the published procedure removes, 2,102 fall to the
19-family denylist and 21,867 to the 12-order denylist. Broken down (`tools/evo2_denylist_detail.py`,
`denylist-detail.json`, literal reading):

| family | records | | order | records |
|---|---:|---|---|---:|
| Picobirnaviridae | 1,420 | | Picornavirales | 13,277 |
| Circoviridae | 461 | | Priklausovirales | 3,921 |
| Papillomaviridae | 129 | | Durnavirales | 1,261 |
| Orthomyxoviridae | 56 | | Cirlivirales | 1,235 |
| Retroviridae | 18 | | Mulpavirales | 1,199 |
| Adenoviridae | 10 | | Geplafuvirales | 650 |
| Coronaviridae | 6 | | Orthopolintovirales | 208 |
| Geminiviridae | 2 | | Herpesvirales | 56 |
| | | | Piccovirales | 37 |
| | | | Lefavirales | 10 |
| | | | Ortervirales | 8 |
| | | | Amarillovirales | 5 |

**On `DESIGN.md` §4's reporting limits.** §4 bars a published ranking of which model is most
capable for which pathogen. This table is not one. The taxa are names on the developer's own
published denylist, the counts are of records in a released corpus, and no capability is
measured anywhere in this document. The table stops where it does because that is the whole
denylist, not because something was withheld.

**The order of the chain is load-bearing, and the artefact publishes both figures.** Counting
released records whose family is on the denylist, ignoring the chain, gives 4,706 rather than
2,102, because the host rule fires first and removes 2,604 of them. For the order rule it is
51,438 rather than 21,867. A breakdown computed independently of the published order would be
wrong by more than the figure itself. This is the concrete cost of the gap D-067 recorded and
`docs/disclosure-standard.md` asks about as item **B4**: Evo's procedure reads as ordered and is
nowhere stated to be.

## The repeated accessions

**They are not repeated accessions, and there are not 39,974 of them.** A7.1 and A7.2 both
reported "39,974 repeated accessions" and neither read a base. Reading the bases settles it
(`tools/evo2_duplicates.py`, `duplicates.json`): the released FASTA carries **1,775** accessions
that appear more than once, on **41,749** headers between them. 41,749 − 1,775 = 39,974. The
figure both earlier tasks reported is the surplus of headers over accessions, and reporting it
as a population of accessions overstates that population by a factor of twenty-three. The
artefact publishes the subtraction and asserts that it reconciles, so the correction is
checkable rather than claimed.

What the 1,775 are is the more useful half. Every one is a giant-virus metagenome-assembled
genome — IMG/VR's `GVMAG-` accession form — and every one, all 1,775, classifies as
**published in parts**: its occurrences sum exactly to IMG/VR's own `Length` for that accession.
One example carries 12 fragments totalling 267,319 bases; another carries 30. These are contigs
of one assembly, not copies of one record.

So the surplus records are **0** and the surplus nucleotides are **0**. The concern that
motivated the check — that an undeclared duplication is an undeclared upsampling, a record the
model sees more than once — does not arise here. The pass was built to count four outcomes
separately rather than assign one verdict to the population, and three of the four came back
empty: nothing republished whole, nothing disagreeing with the input, nothing missing from it.

This is a correction to two `done` tasks' wording rather than to their arithmetic — both counted
39,974 of something and the something was headers. Recorded in `tasks/DECISIONS.md`.

## Reconciliation against Evo 2's own published figures

**Not possible, and that is the finding.** A7.1 reconciled Evo 1 against its Table S3. Evo 2
publishes no record count, no nucleotide count and no removal count for the viral component in
either the preprint or the version of record. The only published figure is Supplementary
Table 9, which gives IMG/VR as 3% of pretraining, 2% of midtraining and 1.7% of the ablation —
shares of a training mix with upsampling, not of a corpus, and therefore not checkable against
2,653,047 records or against 2,957,495.

This is item **D1** of `docs/disclosure-standard.md`, and A7.3 is the worked example of what it
costs: a reconciliation that took A7.1 an afternoon against Evo 1 cannot be performed at all
against Evo 2.

## Provenance, stated plainly

The audited **procedure** is Evo 1's, restated by reference in Evo 2. The audited **output** is
Evo 2's own release. Two artefacts, not one (D-019). Every count above names the IMG/VR release
it rests on: v4.1, dated 2022-12-20, the release A7.2 identified as the procedure's input from
the corpus itself (D-071).

The input end is the publisher's own files at the publisher's own checksums (A1.7). The output
end is each developer's own release (A1.1, D-017). No proxy is substituted at either end.

## What would change this

An adversarial reader has three places to push, and each has an answer.

**"The JSON tree is a subset by design — a training split, not the component."** Then it would
be a round number, or a fraction, or anything other than Evo 1's released component to the
nucleotide. It is exactly that, and the version of record says exactly that dataset was reused
in its entirety.

**"The FASTA's extra records are new material the filter never saw."** Then they would not join
to IMG/VR v4.1, and they do — all 2,917,521 accessions do, with zero absent. They are records
IMG/VR had and Evo 1's procedure removed.

**"The counts are ours, not the publisher's."** They are, which is why both passes are pinned,
seeded, manifested through `amazebio.repro`, and published with their inputs' checksums — and
why the headline was recounted by a method sharing nothing with the first.

The first method decompresses each file to text, parses every line as JSON and takes the length
of the `text` field. The second (`--second-method`, `json-tree-second.json`) never decodes and
never parses: it counts newlines in the gzip stream as bytes and subtracts a fixed per-record
wrapper cost from the byte total, with a premise check that refuses the subtraction if the
wrapper is not what it assumes. The two share the socket and the gzip member and nothing else, so
a fault in the decode, the parser or the field lookup appears in one and not the other. Across
all six files: **zero** record delta, **zero** sequence-character delta, no premise failure.

One caveat stated rather than buried. This task's Done-when says the figure is reproduced by a
second method *under A3.3*, and A3.3's conformance arm reimplemented Evo 1's 95 records, not
anything of Evo 2's. That criterion is not met as written. The recount above is this task's own
and covers the headline this document actually makes; whether §7 is satisfied by that, or whether
A3.3's scope should extend to Evo 2's arm before the Phase A write-up cites this, is recorded in
the task file as the one question for the project owner.

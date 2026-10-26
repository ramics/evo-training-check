# Taxonomy and label references

The published filter's two organism-naming rules read taxonomy, not sequence, and so does the
label arm of the hazard check (X1.8). This page records the three third-party references that
arm reads, what each one can answer, and what it cannot. The sources themselves are in
`sources.json`; nothing here is analysis.

`policies/evo.md` holds what the developers published about the filter. This page holds the
reference data a reader needs in order to re-execute it.

| Source | What it supplies | Stored? |
|---|---|---|
| `S-IMGVR-V4-SEQINFO-2022-09-20` | the per-record family and order labels the filter's rules read | no — 1.9 GB and access-gated; staged in object storage at the publisher's md5 |
| `S-ICTV-VMR-MSL37-3` | the host of a labelled species, from its `Host source` column | no — pinned input, held in git-ignored `data/` |
| `S-ICTV-REPORT-PAPILLOMAVIRIDAE` | what the taxonomic authority says about one genus | yes, CC BY 4.0 |
| `S-ICTV-REPORT-ORTHOFLAVIVIRUS` | the natural history of the one named record in the worst case | yes, CC BY 4.0 |

## The two tables, and the questions they cannot answer

**Labels are sparse, and a negative is not an absence.** Only 6.25% of IMG/VR v4's records
carry a family label at all (A4.1), so a count of records whose label names a given family is a
floor over that window and never a census of what is present. The same table is the only route
from a released record to a taxonomic name, and only one of the two released corpora carries
the source accessions that make the join possible.

**The VMR's host vocabulary stops well above the question.** Its finest value is `vertebrates`.
It never says `human`. A sentence of the form "N records came from human pathogens" therefore
cannot be built from it, however the column is aggregated — which is a limitation of the
reference and not of the measurement. Two further asymmetries are worth stating with any host
figure: a species named after the pin is *absent* from the release rather than hostless, and a
record labelled no further than its family has no species and so no host at all.

## The one organism statement, quoted

The label arm's worst case is ranked by a scale fixed before the result was read, and tier 2 of
that scale — a species an authority names as human-infecting — turns on a judgement about a
genus rather than on a join. That judgement is quoted here rather than paraphrased.

The genus is one of the three whose members infect people:

[source: S-ICTV-REPORT-PAPILLOMAVIRIDAE, Taxonomy section]
> have been used for the genera containing papillomaviruses that infect humans

And it is the genus the chapter describes as ordinary flora of intact skin, with infection
usually producing nothing a patient would notice:

[source: S-ICTV-REPORT-PAPILLOMAVIRIDAE, Pathogenicity section]
> Healthy skin harbors a large spectrum of different papillomavirus types belonging to
> different genera. While the majority of viral infections are subclinical

[source: S-ICTV-REPORT-PAPILLOMAVIRIDAE, Pathogenicity section]
> even in the case of viral types associated with specific pathologies, the majority of
> infections still present as subclinical

The chapter attributes the epidemiological and clinical material it carries to one genus in
particular — not this one — and says so itself:

[source: S-ICTV-REPORT-PAPILLOMAVIRIDAE, Biology section]
> Epidemiological and biological data is primarily available for the viral types belonging to
> the genus

## The named record's natural history, quoted and — where it is a silence — labelled as one

Tier 3's most complete record is labelled with a flavivirus species, and two things said about
it travelled through this project as recollection until now. Both are in the authority's own
chapter. Its species table heads the group the species sits in:

[source: S-ICTV-REPORT-ORTHOFLAVIVIRUS, species table]
> Unknown vector, Entebbe bat virus group

And the genus description says that such members exist and how they move:

[source: S-ICTV-REPORT-ORTHOFLAVIVIRUS, Distinguishing features]
> Some orthoflaviviruses transmit between rodents or bats without known arthropod vectors

**The third claim is a silence, and is recorded as one.** That no human infection is recorded
for the species is not a statement in any source read here; it is the absence of one. The
chapter's pathogenicity section does name the genus's human pathogens by species:

[source: S-ICTV-REPORT-ORTHOFLAVIVIRUS, Pathogenicity]
> More than 50% of known orthoflaviviruses have been associated with human disease, including
> many important human pathogens such as yellow fever virus, dengue virus, Zika virus, Japanese
> encephalitis virus, West Nile virus and tick-borne encephalitis virus

That list does not include this species, and the species name occurs twice in the whole chapter,
both times in the vector-group table — searched 2026-10-22 over the full chapter text for the
species name and for `human`, `patient`, `disease` and `encephalitis`. A list of a genus's human
pathogens that omits a species is weaker evidence than a sentence about that species, and under
`policies/README.md`'s rule a silence is labelled, never upgraded. Note also that the chapter has
moved the species under a renamed genus while the MSL37.3 pin this project joins against carries
the older name — the churn A9.1 measures, met here in one row.

## Where the quotations end and the attributions begin

That last sentence is the reason the quotations are here at all. An earlier draft of the label
arm attributed to this chapter a description of the genus as "found on the skin and oral mucosa
of primates" and its infections as "usually asymptomatic". The substance survives the check and
the wording does not: the chapter says `subclinical`, says it of papillomaviruses of healthy
skin generally, and never writes that phrase. `tools/policies.py` is what caught it, which is
the whole argument for this store existing.

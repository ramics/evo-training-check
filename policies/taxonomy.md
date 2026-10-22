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

That last sentence is the reason the quotations are here at all. An earlier draft of the label
arm attributed to this chapter a description of the genus as "found on the skin and oral mucosa
of primates" and its infections as "usually asymptomatic". The substance survives the check and
the wording does not: the chapter says `subclinical`, says it of papillomaviruses of healthy
skin generally, and never writes that phrase. `tools/policies.py` is what caught it, which is
the whole argument for this store existing.

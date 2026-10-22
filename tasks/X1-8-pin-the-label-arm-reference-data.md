---
id: X1.8
title: Pin the label arm's reference data
phase: X
status: done
gate: false
depends_on: []
blocks: []
design_ref: "§7"
owner: claude
---

# X1.8 — Pin the label arm's reference data

**Design reference:** DESIGN.md §7

## Goal

The label arm of the hazard check reads taxonomy rather than sequence, and it reads it from
three third-party references that this repository did not record. Its tables and figures lived
in the project's shared folder, two of them as copies — produced once, by hand, from inputs
named in prose. `AGENTS.md`'s rule is that a result which cannot be regenerated from pinned
inputs is not a result yet, and a figure that is about to be published in the write-up is
exactly where that rule earns its place.

So: register the three references in the evidence store with a digest and a provenance record
each, and regenerate what can be regenerated from them.

## The three references

| Source id | What it is | Digest |
|---|---|---|
| `S-IMGVR-V4-SEQINFO-2022-09-20` | IMG/VR v4's per-record metadata table for the 2022-09-20 release: the family and order labels the filter's own rules read | the publisher's md5, from their file listing |
| `S-ICTV-VMR-MSL37-3` | the ICTV Virus Metadata Resource at MSL37.3, whose `Host source` column is where every host statement comes from | sha256, re-fetched from the publisher and byte-identical to the pin `amazebio.ictv` has carried since A4.2 |
| `S-ICTV-REPORT-PAPILLOMAVIRIDAE` | the ICTV Report chapter behind the worst case's one organism statement | sha256 of the stored capture |

Two are downloads and the third is a publication, so its record is its quoted wording and where
that wording was read: `policies/taxonomy.md` carries four quotations from it, and
`tools/policies.py` checks each one against the stored page. The chapter page states CC BY 4.0,
which is what makes storing it permissible; the other two are recorded by URL and digest under
the `retrieved_not_stored` convention in `policies/README.md`, because a 1.9 GB access-gated
table and an xlsx are pinned inputs rather than captures and neither states a wording to quote.

**A quotation was wrong and the check found it.** The prose this replaces attributed to the
chapter a description of the genus as "found on the skin and oral mucosa of primates", with
infections "usually asymptomatic". The chapter's own wording is `subclinical`, said of the
papillomaviruses of healthy skin generally, and the phrase does not appear in it. The substance
of the worst case is unchanged; the attribution is now checkable, which it was not before.

## What was regenerated, and what was not

**The family table regenerates, and reproduces.** `tools/denylist_named_families.py` builds the
table of detected families whose Pfam name refers to a denylisted group from the Pfam 38.2 pin
(verified against the publisher's md5 before it is read), the group names in
`policies/specs/evo1-literal.yaml`, and the published per-family detection tables of A2.1 and
A2.4. It reproduces the hand-built table exactly: 41 rows, identical in every column, the same
per-group distribution, 9 families detected on Evo 1 and 41 on Evo 2, 173 and 388 profile-route
hits.

**The row count depends on the matching rule, so the rule is in the code and both readings are
in the table.** A family refers to a group when the group's name, virus noun, adjective or
subfamily form appears in the family's Pfam identifier or its curator description, or when the
group's stem appears as a whole token of the identifier. Reading identifier *and* description
gives **41 rows**; reading the identifier alone gives **31**, which is the
`matched_on == 'identifier'` subset of the same 41 and is the floor. Ten families are caught
only by the description because they are named for a protein rather than a taxon. Publish the
count with the rule attached.

The whole-token half of the rule is there because a substring match over protein names counted
`PF22759 E217_GP41`, a phage baseplate hub protein, as a retroviral family — the same failure as
the `macrophage` blind spot already on record. A Pfam family's name records where its curators
built the model, not what a record is.

**The per-record table was not regenerated, by instruction and on its own merits.** Rebuilding
`denylisted-label-records.tsv` means joining the detected record accessions against
`S-IMGVR-V4-SEQINFO-2022-09-20` — a pass over a 1.9 GB staged table, access-gated, which this
session was told not to run. The existing table stays where it is, and the README beside it now
says how it was produced: the 19,646 detected Evo 2 accessions from the A2.1 per-hit tables,
joined by accession to the pinned label table, with lineage and the VMR host column attached.
Its figures are unverified by this task, which is a different statement from unverifiable: the
join is deterministic and the tool to repeat it is a day's work, not a measurement.

**Hit columns are per route, never summed.** D-247's rule is that a single-detector figure is
not set beside a merged one, so the profile-search and provirus-route hits are separate columns.
The label arm's per-record work covers the profile route only, because A2.4 publishes no per-hit
table and so no record behind a provirus hit can be looked up at all.

## Done when

- The three references are in `policies/sources.json`, each with a digest, a URL, a retrieval
  date and a revision label, and `tools/policies.py` passes.
- The quotation source is stored and its wording machine-verified, not paraphrased.
- The family table is produced by a tool from pinned inputs, and the tool's output matches the
  hand-built table column for column.
- The tool states the matching rule and reports the count under both readings of it.
- The per-record table is left in place with its production recorded, and the reason it was not
  re-run is written down rather than implied.
- `python3 tools/board.py --check` passes and CI is green.

## Result

Done. 54 sources in the store, 105 quotations verified. The regenerated table is at
`corpora/results/x1-8/denylist-named-families.tsv` with its summary and `run.json` beside it,
published through `repro.run(durable=...)` and so through `objectstore.put_once`, with the
commit-keyed twin X1.7 requires.

## Notes

**Why this is an X task and not part of the hazard check.** The hazard check's own question is
whether what the audit detected is dangerous. Whether its inputs are pinned is a property of
every task that reads taxonomy — A4.1, A4.2, A7.1 and A9.1 all read the same two tables — and
`AGENTS.md` forbids widening whichever task next trips a shared defect to absorb the fix.

**The ceiling travels with the pin.** Only 6.25% of IMG/VR v4's records carry a family label,
and the VMR's finest host value is `vertebrates`. Both limits are recorded in the source notes
and in `policies/taxonomy.md`, so a later reader meets them where the reference is registered
rather than only in the prose of whichever task quoted it.

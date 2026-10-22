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

## The references

**Two kinds of provenance, and they are not interchangeable.** A *file* is pinned by a digest:
re-fetch the bytes, hash them, and either they are the bytes the figure was computed from or
they are not. A *publication* is pinned by its wording: the claim rests on a sentence, so the
record is that sentence and where it was read, and the check is that the sentence is still
there. Which kind a claim rests on is the first thing a later reader needs, so it is in the
table.

| Source id | What it is | Pinned by |
|---|---|---|
| `S-IMGVR-V4-SEQINFO-2022-09-20` | IMG/VR v4's per-record metadata table for the 2022-09-20 release: the family and order labels the filter's own rules read | **file** — the publisher's md5 from their file listing, now verified over the whole staged stream |
| `S-ICTV-VMR-MSL37-3` | the ICTV Virus Metadata Resource at MSL37.3, whose `Host source` column is where every host statement comes from | **file** — sha256, re-fetched from the publisher and byte-identical to the pin `amazebio.ictv` has carried since A4.2 |
| `S-ICTV-REPORT-PAPILLOMAVIRIDAE` | the ICTV Report chapter behind the worst case's one human-virus statement | **wording** — four quotations in `policies/taxonomy.md`, machine-checked against the stored capture |
| `S-ICTV-REPORT-ORTHOFLAVIVIRUS` | the natural history of the one named record: unknown vector, bat-borne without an arthropod vector | **wording** — three quotations, machine-checked; the absence of recorded human infection is recorded as a labelled silence, not a quotation |
| `S-EUREKALERT-EVO2`, `S-PHYSORG-EVO2` | the two press accounts that report the exclusion as accomplished | **wording, unverifiable by CI** — no redistribution licence, so the sentence sits in each entry's `quoted` field, checked at retrieval only (`policies/evo.md` §11) |

The two ICTV chapters state CC BY 4.0, which is what makes storing them permissible. The two
tables and the two press pages are recorded by URL and digest under the `retrieved_not_stored`
convention in `policies/README.md` — a 1.9 GB access-gated table and an xlsx state no wording to
quote, and a news page may not be redistributed, so `tools/policies.py` refuses a blockquote
citing any of them. A claim resting on one of those carries its retrieval date.

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

**The per-record table regenerates too, and the pass that does it verifies the pin.**
`tools/denylisted_label_records.py` joins the detected Evo 2 record accessions from the A2.1
per-hit table against `S-IMGVR-V4-SEQINFO-2022-09-20`, attaches the VMR host column, and flags
the labels against the spec's 19 families and 12 orders. It reproduces the hand-built table
exactly: 315 rows, every cell identical, 31 records with a denylisted family label and 308 with
a denylisted order label, 24 with both, and 1,272 of 19,646 detected records carrying a family
label at all.

It takes 47 seconds, because the 1.9 GB table is **streamed and never stored** — the session's
writable disk is smaller than the file. The md5 of the whole stream is computed as it passes and
compared with the publisher's, so this is also the first end-to-end check that the staged bytes
are the published bytes: they are.

Three classes of record id, kept distinct rather than filtered quietly. `IMGVR_…` records are
what the table is about. The 562 `IMGPR_…` plasmid records are counted and set aside: IMG/PR is
out of the published policy's scope by its own words and has no viral taxonomy to join against.
Anything else resolves to nothing, which is the whole of Evo 1's released viral component, and
the tool refuses rather than reporting a floor as a count.

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
- The per-record table is regenerated from the pinned inputs, and the pass that does it checks
  the staged bytes against the publisher's digest rather than trusting the staging.
- Records whose identifiers cannot be resolved are refused, not skipped: a floor must not be
  reported as a count.
- `python3 tools/board.py --check` passes and CI is green.

## Result

Done. **57 sources in the store, 108 quotations verified**, and both label-arm tables regenerate
from pinned inputs and reproduce their hand-built versions cell for cell. Outputs at
`corpora/results/x1-8/` and `corpora/results/x1-8/records/`, each with its summary and
`run.json`, published through `repro.run(durable=...)` and so through `objectstore.put_once`,
with the commit-keyed twins X1.7 requires.

Six references, not three. The write-up's own sweep found three further claims resting on one
session's retrieval: the two press accounts of the exclusion, and the natural history of the one
named record. All three are now registered — the press sentences verified verbatim at retrieval
and marked as not re-checkable, the natural history quotable from the ICTV genus chapter, and
the one part of it that is an absence rather than a statement recorded as a labelled silence
with the terms and extent of the search. That is the same correction as the Papillomaviridae
one, applied before it could become an error: **three of the five organism-level claims in this
result were travelling on recollection, and the two that turned out to be exactly right were
indistinguishable, from the inside, from the one that was not.**

## Notes

**Why this is an X task and not part of the hazard check.** The hazard check's own question is
whether what the audit detected is dangerous. Whether its inputs are pinned is a property of
every task that reads taxonomy — A4.1, A4.2, A7.1 and A9.1 all read the same two tables — and
`AGENTS.md` forbids widening whichever task next trips a shared defect to absorb the fix.

**The ceiling travels with the pin.** Only 6.25% of IMG/VR v4's records carry a family label,
and the VMR's finest host value is `vertebrates`. Both limits are recorded in the source notes
and in `policies/taxonomy.md`, so a later reader meets them where the reference is registered
rather than only in the prose of whichever task quoted it.

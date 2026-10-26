---
id: X1.9
title: Regenerate the label arm's per-record table
phase: X
status: done
gate: false
depends_on: [A2.1]
blocks: []
design_ref: "§7"
deliverable: null
owner: claude
---

# X1.9 — Regenerate the label arm's per-record table

**Design reference:** DESIGN.md §7 · **Deliverable** — none; it supplies an input A7.5 consumes.

## Goal

X1.8 (PR #38, not yet merged, so not in this branch's task graph and not in `depends_on`) pinned the label arm's three references and regenerated its *family* table. It left the
**per-record** table alone, and said so: rebuilding it needs a pass over the 1.9 GB staged label
table and that session was told not to start one. So the per-record figures are still a
hand-built copy, produced once from inputs named in prose — which `AGENTS.md` says is not a
result yet.

This is that pass. It exists as its own task because the alternative was widening one of two
tasks that must not absorb it: X1.8 is `done`, and A7.5 *consumes* this table, so deriving its
own input inside it would make the tool's record set a thing it chose rather than a thing it was
given — the division A7.5's design is explicit about.

## The question

Of the records the audit detected in Evo 2's released viral component, which ones does IMG/VR's
own metadata label as belonging to one of the nineteen virus families the published filter names
for removal?

## Inputs — three, all pinned, none of them sequence

| input | what it is | how it is verified |
|---|---|---|
| A2.1's published per-hit tables for Pfam on `opengenome2`, one per reading of the filter | the detected record set | all three readings read whole and **required to agree**: every taxonomy rule is unresolvable against this component (A1.4), so they cannot differ, and a disagreement means a table is not what it says it is |
| `IMGVR_all_Sequence_information-high_confidence.tsv`, 2022-09-20 release | the family labels the filter's own rules read | the publisher's own md5, read out of their captured file listing (`S-IMGVR-JGI-INVENTORY`) by release date and file name, and computed over the bytes as they stream. The object's length is checked against that listing before the read — two releases carry this file name and differ in it by 237 bytes (D-052, D-054) |
| `policies/specs/evo1-literal.yaml`, rule `remove-denylisted-families` | the nineteen groups **and the predicate** | X1.4 machine-verifies the rule's quotations against the source PDF |

**The rule is executed, not restated.** `tools/denylist_label_records.py` loads the rule and
applies it through `policyspec.decide` — the same code path A1.4's corpus-scale evaluator uses.
A record is a denylisted-label record when the published rule, given that record's own label,
removes it. The tool implements no matching rule of its own, which is the difference between
reproducing the filter's reading and inventing one that resembles it.

Columns are read **by header name**: the file has nineteen columns and one header containing a
comma and a parenthesis, so a positional read would be a silent dependency on column order.

## What the table is not

A row says two things and no more: IMG/VR's metadata labels this record as a member of a family
the published filter names, and the audit detected a viral protein family on it. It does not say
the record is dangerous, and it does not say the label is right — `label_method` travels with
every row so a reader can see which rows rest on a geNomad prediction rather than a reference
match.

The count is a floor three times over, and the output says so: the detections come from a
sampled search, only a minority of IMG/VR records carry a family label at all, and the label
table covers the high-confidence subset — so a detected record absent from it is unlabelled
*here* rather than unlabelled in IMG/VR.

## Output

`artifacts/x1-9/denylisted-label-records.{tsv,json,md}`, published to `corpora/results/x1-9/`
from the canonical directory only (`durable_for`, D-193 and D-224). The TSV's first column is
the record list A7.5 reads — which is a use and not a dependency, deliberately: A7.5 measures
whatever record set it is handed, and `blocks` says so by staying empty.

No sequence is read and no residues are written (D-103). The table carries record identifiers,
so it is internal under X3.1.

## Done when

- The three inputs are verified as above, with refusals, demonstrated by test.
- The rule is loaded from the spec and executed through `policyspec.decide`, not reimplemented.
- The table, its summary and `run.json` are published from pinned inputs.
- The count is reported with its three ceilings attached.
- Frontmatter current and `python3 tools/board.py --check` passes.

**The pin comes from the publisher, not from a second register entry.** X1.8 registers this
table as `S-IMGVR-V4-SEQINFO-2022-09-20`, whose own `md5_source` names the JGI file listing it
was transcribed from. That listing is already in the evidence store, so this pass reads the
digest from it directly: one less transcription to keep in step, and it works whether or not
PR #38 has merged.

## Result — 2026-10-22

Ran. The table, both summaries and `run.json` are at `corpora/results/x1-9/`, published from the
canonical directory. The pass read 1.89 GB in-region in under two minutes and verified the
publisher's md5 over every byte of it.

**The hand-built pipeline is reproduced, and the number it was built from is confirmed.** X1.8
records the per-record table as built from "the 19,646 detected Evo 2 accessions"; this pass
finds 20,208 detected records, of which **19,646** are in the pinned label table. The family
axis carries **388** hits, which is exactly the figure X1.8 publishes for it. Two independent
figures landing on the published ones is what makes the rest of this table citable.

**The 562-record gap is the plasmid component, entirely.** It is not records the
high-confidence subset left out, which is what it looked like before the component column
existed: every one of the 19,646 detected IMG/VR records is in the label table, and all 562
absent records are `IMGPR_plasmid_*`. The label table is IMG/VR's, so those records were never
in it — a different statement from being unlabelled, and the counts keep them apart.

**Two axes, reported separately and never summed:**

| axis | what it counts | records |
|---|---|---|
| family | detected records whose detected Pfam family is *named* for a denylisted group | **319** — 314 IMG/VR, 5 IMG/PR |
| label | detected records the published denylist rule removes on their own IMG/VR label | **31** |

Neither set contains the other. The first is a property of Pfam's curation, the second of the
record. Of the 314 viral records on the family axis, 97 carry a family label at all and 17 are
ones the published rule would have removed had it been able to read that label. Across all
19,646 labelled records, 1,272 carry a family label — 6.5%, consistent with the 6.25% ceiling
X1.8 records.

**The hand-built 308 is not reproduced and is not treated as a target.** The nearest derived
figure is 314, the viral records on the family axis. X1.8's own account explains a difference of
that size: the family list behind the hand-built copy was counted 42, 40 and 33/41 before it was
regenerated to 41, so the per-record copy predates the rule that settled it. This derivation
rests on pinned inputs and states its rule; the older figure rests on neither and is superseded
rather than matched.

## What this task left in the results prefix, permanently

Three keys and a manifest in `corpora/results/x1-9/` are from the first pass and describe a
shape that no longer exists: `denylisted-label-records.{tsv,json,md}` and
`run-denylist-label-records.json`. That pass keyed the table on the *label* axis alone, which
gave 31 records and did not reconcile with anything published, and it had no component column.
The bucket has no `s3:DeleteObject`, so they cannot be removed.

They are recorded here rather than left to be rediscovered. The live table is
`denylist-named-family-records*`; anything reading `denylisted-label-records.*` is reading the
first attempt, whose figure is a subset of one axis of the current table and is reported in it
as `records_the_label_rule_removes`. The cost of learning this was four permanent keys, which
is the same lesson A1.3's four 0-byte objects and A4.5's `.write-probe` record: in a bucket that
cannot delete, the first run of a tool is a publication.

## State — 2026-10-22

`review`, on branch `claude/project-thread-ff52l2` (with A7.5, which consumes the IMG/VR list).

Tool, tests and the published tables are done. What is left is one question for the project
owner rather than any work: whether the hand-built 308-row table should now be replaced by this
one wherever the hazard check cites it, which is a decision about the write-up and not about
this task.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

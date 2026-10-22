---
id: X1.9
title: Regenerate the label arm's per-record table
phase: X
status: in-progress
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
| `IMGVR_all_Sequence_information-high_confidence.tsv`, 2022-09-20 release | the family labels the filter's own rules read | the publisher's md5, taken from `S-IMGVR-V4-SEQINFO-2022-09-20` in `policies/sources.json` and computed over the bytes as they stream. The object's length is checked against the register before the read |
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

## State — 2026-10-22

`in-progress`, on branch `claude/project-thread-ff52l2` (with A7.5, which consumes the table).

The tool and its tests are written and green. The pass itself is ~1.9 GB of in-region reading,
authorised by the project owner, who asked for this derivation rather than supplying the
hand-built table.

**One number to expect a disagreement about.** X1.8 records the hand-built table as built from
"the 19,646 detected Evo 2 accessions". A2.1's published tables carry **20,208** distinct
detected records on `opengenome2`, identically under all three readings. The difference is most
likely the records absent from the high-confidence label table, which this pass counts and
reports rather than absorbs — so the join is also a check on that figure.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

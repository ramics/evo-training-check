---
id: X1.10
title: Decide what M2's n_f counts, and record it
phase: X
status: ready
gate: false
depends_on: [A2.1]
blocks: []
design_ref: "§7, metrics/survival.md §M2"
deliverable: null
owner: unassigned
---

# X1.10 — Decide what M2's `n_f` counts, and record it

**Design reference:** `metrics/survival.md` M2 · **Deliverable** — none; it settles a definition
two published artefacts already depend on.

## The problem

`metrics/survival.md` defines `n_f` as "the number of surviving **sequences** detected for family
`f`". A2.1's published per-hit tables are what `n_f` is computed from, and they carry no `gene`
field. So a row's key is (`family_id`, `record_id`), and in
`detections-pfam-evo1-literal-opengenome2.jsonl`:

- 66,296 rows over 65,132 distinct (family, record) keys;
- **897 keys carry more than one row, 1,164 rows in total** — 1.8% of the table;
- those rows are identical in every field the table records.

Two different things produce them and the table cannot tell them apart:

1. **two genes of one record** hitting the same family, and
2. **two corpus entries sharing one accession** — the released component repeats record
   identifiers, 1,775 of them with one appearing 161 times (A7.3), and A7.5 measured two entries
   under one accession carrying different proteins: 38.0 and 34.4 bits against the same model at
   the same gene index.

Both are real. Neither is recoverable from the published table.

## Why it matters

`n_f` is a count of *sequences*, and the three readings give three different numbers:

| reading | what a repeated hit means |
|---|---|
| count rows | two genes is 2, and two entries of one accession is also 2 |
| count distinct records | both are 1, which makes `n_f` a record count and not a sequence count |
| count entries | needs the entry, which the table does not carry |

M2 is reported as a distribution with a bootstrap interval, so a 1.8% ambiguity will not move its
median much — but the definition should not rest on which of three readings whoever computes it
happens to pick.

**M1, the headline, is unaffected.** `survival(R) = |{f : n_f ≥ 1}| / |F_R|` only asks whether
`n_f ≥ 1`, and all three readings agree on that. The denominator is the family universe, not a
record count, so repeated accessions cannot touch it.

## What this task is

A decision and a record, not a re-run:

1. Decide which reading `n_f` takes, and write it into `metrics/survival.md` — a change to a
   metric spec is a `DECISIONS.md` entry (`AGENTS.md`, *Repo map*).
2. Check whether any published M2 figure was computed under a different reading, and say so where
   it is cited rather than silently restating it.
3. Decide whether A2.1's per-hit tables should carry the gene and the entry. That is the only
   thing that would make the three readings distinguishable, and it costs a re-run of A2.1's
   search — which is why it is a decision for the project owner and not a side effect of this
   task.

## Not in scope

Measuring repeated accessions: A7.3 owns that and has published the distribution. Re-running
A2.1: that is A2.1's, and only if (3) is decided that way.

## Done when

- `metrics/survival.md` states which reading `n_f` takes.
- A `DECISIONS.md` entry records the choice and the alternatives rejected.
- Any published M2 figure computed under another reading is identified, or it is established that
  none was.
- `python3 tools/board.py --check` passes.

## How this was found

A7.5 asked for 314 named records and its pass reported 551 found, which is how the repeated
accessions surfaced. Chasing that produced A7.5's own `entry` column; this is the part of it that
belongs to a published artefact of another task rather than to A7.5's table, and `AGENTS.md`
forbids widening A7.5 to absorb it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

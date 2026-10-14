# AGENTS.md

Operating manual for anyone — human or agent — picking up work in this repo.
Read this before touching anything else.

## What this project is

An independent audit of exclusion-based data filtering as a safeguard in open-weight
biological models. The full specification is **`DESIGN.md`** and it is the single source of
truth for scope, method and commitments. This file governs *how* the work is executed, not
*what* the work is. Where the two appear to conflict, `DESIGN.md` wins — and say so, rather
than resolving it silently.

Three phases, strictly ordered by dependency rather than preference:

| Phase | Subject | Note |
|---|---|---|
| **A** | Does the filter remove what it claims to? | Headline result. Ships alone if B and C slip. |
| **B** | Where it doesn't, does surviving capability track homology? | Depends on A's output, not on assumptions about it. |
| **C** | Can leakage be predicted from the filter spec alone? | Turns the finding into an instrument. |

## Repo map

```
DESIGN.md             the specification — authoritative, read it before planning anything
AGENTS.md             this file: process, conventions, non-negotiables
README.md             setup and everyday commands
pixi.toml / pixi.lock the pinned environment (conda-forge + bioconda + python)
pyproject.toml        package metadata, lint and test config
src/amazebio/         library code
  repro.py            seeding, input pinning, run provenance
  survival.py         the frozen route taxonomy and headline metrics
metrics/survival.md   FROZEN — the headline metric spec; changing it is a DECISIONS entry
tools/board.py        regenerates tasks/BOARD.md from task frontmatter
tasks/README.md       the task protocol in detail
tasks/BOARD.md        GENERATED — never hand-edit
tasks/DECISIONS.md    append-only log of resolved ambiguities
tasks/*.md            one file per unit of work
tests/                tests
data/                 pinned inputs (git-ignored)
artifacts/            pipeline outputs and run manifests (git-ignored)
```

Run `pixi run -e dev check` before every commit — it is exactly what CI runs (lint, format,
task graph, tests), so a green local run means a green CI run.

## How to pick up work

1. Read `DESIGN.md` for the phase you are entering, and this file.
2. Run `python3 tools/board.py` and read **Ready to pick up**. Take a task from there.
   If nothing is ready, the blocking dependency *is* the work — do not invent a side quest.
3. Check the task's **Gates** column. Never work past a `HOLDING` gate (see below).
4. Set `status: in-progress` and `owner:` in the task's frontmatter, regenerate the board,
   and commit that **on `main`** as its own small commit — pushed immediately, so parallel
   workers see the claim. See **Where commits go**.
5. Do the work, on a feature branch.
6. Set `status: review`, regenerate, commit on `main`. Move to `done` only when every
   Done-when criterion is demonstrably met — not when the code runs.

Keep one task per branch and per commit series where you can. A task that turns out to be
two tasks should be split into two files, not quietly widened.

## Where commits go

**Project management lands on `main`. The work itself lands on a feature branch.**

Parallel tracks are the whole reason. A claim nobody else can see is not a claim, and a board
that exists only in your branch cannot stop two workers taking the same task.

| Goes straight to `main` | Goes on your feature branch |
|---|---|
| task frontmatter (`status`, `owner`) | library code, tools, tests |
| `tasks/BOARD.md` | specs, metric specifications, write-ups |
| `tasks/DECISIONS.md` | anything else a reviewer reads as the work |
| this file | |

So one task normally produces: a claim commit on `main`, the work on a branch, a decisions
entry on `main` when an ambiguity is resolved, and a status commit on `main` when the task
reaches `review` or `done`.

Three rules make that safe:

- **Push project management as soon as you commit it.** A claim sitting unpushed while you
  work is worse than no claim, because the board says the task is taken and nobody can see it.
- **Pull `main` before you touch it.** `DECISIONS.md` is append-only so appends merge cleanly;
  `BOARD.md` is generated, so regenerate it after pulling rather than resolving a conflict in
  it by hand. Run `python3 tools/board.py --check` after every such pull.
- **Keep project-management commits free of work.** A commit that moves a status *and* changes
  a tool cannot land on `main` without dragging unreviewed work with it.

One consequence to accept rather than work around: `DECISIONS.md` on `main` can describe code
still sitting in a branch, so the log runs slightly ahead of the repo. That is the cost of
every track seeing a resolved ambiguity the moment it is resolved, and it is cheaper than two
branches resolving the same ambiguity twice.

## The frontmatter contract

Every task file opens with:

```yaml
---
id: A2.1                      # stable, never reused, never renumbered
title: ...
phase: A                      # A | B | C | X (cross-cutting)
status: blocked               # blocked | ready | in-progress | review | done | deferred
gate: false                   # true = blocks downstream work unconditionally
depends_on: [A1.4]            # task IDs
blocks: [A3.2]                # reverse edges; board.py verifies these
design_ref: "§A2"             # where in DESIGN.md this comes from
deliverable: 1                # §5 deliverable number, or null
owner: unassigned
---
```

`tools/board.py --check` validates the graph: unknown IDs, cycles, stale `blocks` lists, and
status/dependency inconsistencies. Run it before every commit that touches `tasks/`. It is
cheap and it catches the whole class of "board says ready, dependency says otherwise".

`deferred` is for work `DESIGN.md` explicitly declines (see §4). Those stay visible as
*deliberately not run*, so they end up in the paper as named future work rather than being
forgotten.

## Gates

Five tasks carry `gate: true`. They are not work items so much as checkpoints that make it
*structurally impossible* to walk past a commitment by accident:

| Gate | Holds | Why |
|---|---|---|
| **A1.1** released-vs-actual data verified | all corpus reconstruction | Determines whether Phase A audits the real thing or a proxy, and therefore how strongly every downstream claim may be worded. |
| **A3.3** headline counts independently reimplemented | Phase A write-up, preprint | §7 requires a second method before publication. Not optional. |
| **B5.1** pre-registration frozen | all Phase B analysis | §B5 requires the analysis plan fixed before results are seen. A freeze after the fact is not a freeze. |
| **C2.2** whole-family holdout validated | leakage-score results | §C2: a random split leaks family identity, and a leakage score with leaked evaluation refutes itself. |
| **X3.1** disclosure window honoured | preprint | §4 requires disclosure before any preprint; §7 requires treating the window as substance. |

If you believe a gate should open, that is a decision for the project owner, recorded in
`DECISIONS.md`. It is never a judgement call made mid-task.

## Non-negotiables

Lifted from `DESIGN.md` §2 and §4. These are not style preferences and they are not
negotiable by a task that finds them inconvenient.

- **Scope limits (§4) are enforced in code, not by good intentions.** Zero-shot scoring only.
  No sequence generation. No fine-tuning to restore excluded capability. No in-context
  capability-recovery experiments. Published data on well-characterised proteins only. No wet
  work. If a harness *could* be used outside these limits, constrain the harness.
- **The null result is publishable and must be published if observed (§2).** This is the line
  between an audit and an advocacy exercise. Nothing in the pipeline may be designed in a way
  that makes a null harder to see.
- **Thresholds, parameters and analysis specs are fixed before results are inspected.** Every
  task that chooses one says so in its Steps. Record the choice in `DECISIONS.md` with its
  timestamp, then look.
- **Reporting limits (§4).** Results go out by homology class, fold family and survival route.
  No published ranking of which model is most capable for which pathogen.
- **Disclosure before publication (§4).** No external circulation of findings — including
  informal — before X3.1.

## Working conventions

- **Pin everything.** Database versions, tool versions, model checkpoints, seeds. A result
  that cannot be regenerated from pinned inputs is not a result yet. Wrap every pipeline in
  `amazebio.repro.run`: it seeds the RNGs, writes a `run.json` recording inputs, outputs,
  parameters and tool versions, refuses a dirty git tree, and refuses a parameter declared
  after an output exists. Where a stated version is
  unrecoverable, record stated-vs-used explicitly; the gap is a finding, not an embarrassment.
- **Under-specification is data.** When a policy, dataset or model card is vague, log it and
  measure the consequence. Do not paper over it with a plausible guess — `DESIGN.md` §A0 turns
  exactly this into a result.
- **Artefacts before prose.** Every number in a write-up traces to a machine-readable artefact
  produced by a pipeline. No figure is assembled from pasted values.
- **Per-assay before pooled.** §B5 is explicit that pooled correlations are fragile at this
  sample size. Per-assay reporting is the default presentation everywhere.
- **Uncertainty travels with the estimate.** No point estimate ships without its interval —
  in papers, in figures, and in the shipped tool's own output.
- **Write for the adversarial reader.** §7 notes Phase A names real labs and must be airtight.
  Assume a motivated, well-informed reviewer who wants the result to be wrong.

## Reporting to the project owner

Write plainly. Say what a thing is rather than citing a section number — "the model list"
not "the model table in B1". Keep updates short and lead with what changed or what is needed.
When a decision is needed, ask a direct question with the real options, rather than describing
the tension and leaving it open.

Two rules, not preferences:

- **Simple and concise.** Short sentences, plain words, no preamble. Say the thing once.
- **Ask with the choice mechanism.** Every question goes through the tool that renders real
  options to pick from, never as prose in a message. One question, the real options, done.

Precision in the repo files is a separate matter: task files, decisions and write-ups still
cite `DESIGN.md` sections, because traceability is the point there.

## Decisions

`tasks/DECISIONS.md` is append-only. Add an entry whenever you resolve an ambiguity that a
later reader would otherwise have to reverse-engineer: a proxy substitution, a threshold, a
reading of vague policy prose, a model-class choice, a scope call. One entry, dated, with the
alternatives you rejected and why.

This is not bureaucracy. §A0 and §B1 both say under-specification is itself a finding — the
log is what turns scattered judgement calls into a paper appendix instead of lost context.

## Definition of done

A task is `done` when all of:

- every Done-when criterion is demonstrably met;
- results regenerate from pinned inputs and seeds;
- new code has tests, and CI is green;
- any decision made along the way is in `DECISIONS.md`;
- frontmatter is current and `python3 tools/board.py --check` passes.

## Things not to do

- Do not hand-edit `tasks/BOARD.md`. Regenerate it.
- Do not renumber or reuse task IDs. They are referenced from commits and write-ups.
- Do not widen a task's scope to absorb an adjacent problem. New file, new ID, new entry.
- Do not leave project management in a feature branch. A status, a board or a decision that
  only exists in your branch is invisible to every other track until it merges.
- Do not add models or assays for their own sake — §7 names scope creep as a live risk.
- Do not trust secondary sources for any factual claim about a model's training data,
  `DESIGN.md` included. §B1 step 0 is explicit: verify from primary sources.

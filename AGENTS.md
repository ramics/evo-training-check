# AGENTS.md

Operating manual for anyone — human or agent — picking up work in this repo.
Read this before touching anything else.

## How to talk to the project owner

These two come first and they override every other instruction about tone, including the
longer "Reporting to the project owner" section below.

**1. No code names.** Never write a decision number, task id, tool name or internal label in a
message to the owner. Not `D-269`, not `A2.6`, not "the stage-2 probe", not `detect_profiles.py`.
Say the thing itself: "the test run", "the census", "the filter rules". If a number genuinely
has to be referred to, describe it — "the decision that deferred the census" — rather than
citing it.

**2. Be very brief and very plain.** Short sentences. Everyday words. Lead with what changed or
what is needed. Say it once. No preamble, no status taxonomy, no headings unless the owner asks
for a document. If it can be two sentences, it is two sentences.

Repo *files* are the opposite and stay that way: task files, the decisions log and write-ups
cite ids because traceability is the whole point there, and the decisions checker enforces it.
The rule above is about messages to a person, not about the repository.

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

**The module and tool lists below are excerpts, not inventories.** There are 52 modules in
`src/amazebio/` and 73 scripts in `tools/`; the ones named here are the entry points worth
knowing before you plan anything. For the rest, read the docstring — every module and tool
opens with one line saying what it is for and which task it belongs to. Do not infer from this
map that something does not exist.

```
DESIGN.md             the specification — authoritative, read it before planning anything
AGENTS.md             this file: process, conventions, non-negotiables
README.md             setup and everyday commands
pixi.toml / pixi.lock the pinned environment (conda-forge + bioconda + python)
pyproject.toml        package metadata, lint and test config
.github/workflows/    CI — runs exactly the seven steps `check` runs
policies/             the policy evidence store: primary-source quotes, each traceable
  README.md           how a quote is stored and verified; read before adding one
  sources.json        the source register — retrieval status, digests, blockers
  specs/              each filter policy as executable predicates, three readings
  captures/           the captured primary sources the quotes cite
assays/               the assay provenance and licence register (deliverable 2), committed
  README.md           the two licence questions and why they are kept apart; read before editing
  register.json       GENERATED — one entry per assay: provenance, arm, control tag, terms
  licences.json       GENERATED — the evidence: the deposit's grant and each article's terms
pdfs/                 owner-supplied subscription sources and supplements
src/amazebio/         library code — 52 modules; a selection follows
  repro.py            seeding, input pinning, run provenance
  survival.py         the frozen route taxonomy and headline metrics
  uniref.py           streaming acquisition of a pinned UniRef release, per release
  esm3.py             what ESM3-open states about its corpus, and what does not reconcile
  ictv.py             the pinned ICTV Virus Metadata Resource — the benchmark ground truth
  genomad.py          the tool A4.2 benchmarks: version bound, output parser, scope note
  misassignment.py    taxonomy-tool error by direction, exact intervals, leakage propagation
  similarity.py       parameters, readings and rates-with-intervals for the A1.6 pass
  seeds.py            reconstructs ESM3-open's denylist seed sets from pinned inputs
  policyspec.py       published filter prose as an executable predicate
  ec2.py              launch-time facts about this account's EC2, shared by every launcher
metrics/              the output contracts — a change to one is a DECISIONS entry
  survival.md         FROZEN — the headline metric spec
  detections.md       the shared detection schema every A2 detector emits
  manifests.md        the surviving-corpus manifest contract
tools/                73 scripts; a selection follows
tools/board.py        regenerates tasks/BOARD.md from task frontmatter
tools/stage_uniref.py stages a pinned UniRef release into object storage, streaming
tools/count_clusters.py counts clusters in a staged tier and checks the composition
tools/stage_opengenome.py stages the pinned Evo nucleotide corpora, by component
tools/ec2_count.py    runs the count in-region on EC2; see "Running work on EC2"
tools/esm3_composition.py writes ESM3's stated composition and its reconciliation gaps
tools/taxonomy_dependency.py which taxonomy tool the denylist's removals actually rest on
tools/taxonomy_benchmark.py builds the labelled set and scores the tool's error by direction
tools/assay_register.py builds and validates the assay licence register; CI runs --check
tools/assay_licences.py acquires that register's evidence; the only online step in B2.4
tools/policies.py     verifies every quote in policies/ against its cited source; CI runs it
tools/specs.py        validates the filter policy specs; CI runs it
tools/esm3_calibrate.py prices an in-region pass; the worked example for heartbeats
tools/ec2_similarity.py launches it; its `die` is the worked example for shutdown paths
tasks/README.md       the task protocol in detail
tasks/BOARD.md        GENERATED — never hand-edit
tasks/DECISIONS.md    append-only log of resolved ambiguities
tasks/*.md            one file per unit of work
tests/                tests
data/                 pinned inputs (git-ignored)
artifacts/            pipeline outputs and run manifests (git-ignored)
```

Run `pixi run -e dev check` before every commit — it is exactly what CI runs, so a green local
run means a green CI run. Nine steps, in order: lint, format, task graph, decisions log, **policy evidence**,
**filter specs**, **model inventory**, **assay register**, tests. The four in bold are the evidence checks, and
they are the ones a change to `policies/` or `assays/` trips; do not read "lint and tests" and assume a
documentation-only change is safe.

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
- **A task in flight names its branch.** While a task is `in-progress` or `review`, its file
  records — on `main` — the branch its work sits on, what is finished, what is left, and what is
  waiting on the project owner. Without that, the split loses the pointer: `main` says `review`
  while the code sits somewhere only the last worker knows, and whoever picks the task up next
  cannot find it.

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

Six tasks carry `gate: true`. They are not work items so much as checkpoints that make it
*structurally impossible* to walk past a commitment by accident:

| Gate | Holds | Why |
|---|---|---|
| **A1.1** released-vs-actual data verified | all corpus reconstruction | Determines whether Phase A audits the real thing or a proxy, and therefore how strongly every downstream claim may be worded. |
| **A3.3** headline counts independently reimplemented | Phase A write-up, preprint | §7 requires a second method before publication. Not optional. |
| **B5.1** pre-registration frozen | all Phase B analysis | §B5 requires the analysis plan fixed before results are seen. A freeze after the fact is not a freeze. |
| **C6.3** headline curves independently reimplemented | cost-curve results, preprint | §7's second-method requirement, one phase over: a claim that filtering *cannot* work for a family is at least as consequential as a Phase A count. |
| **X3.1** disclosure window honoured | preprint | §4 requires disclosure before any preprint; §7 requires treating the window as substance. |
| **C2.2** whole-family holdout validated | nothing — `deferred` | Superseded by the collateral cost curve (C5.1–C7.1) in DESIGN v0.4; D-009. Carries `gate: true` and an empty `blocks` so it stays visible as a commitment deliberately not run, per `deferred` above. C6.3 is the live gate on Phase C results. |

`tasks/BOARD.md`'s **Gates** section is generated from this frontmatter and lists the five live
gates with what each currently holds. It is the authoritative view; this table explains *why*
each exists. If they disagree, the board is right and this table is stale — fix it here.

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

## Running work on EC2

The rules are in **`docs/runbooks/ec2.md`** — observability, teardown, account limits,
spot handling, and the pre-launch checklist. Read it before launching anything. In short:
launch only when being inside the region is the point, never construct an S3 client,
copy a launcher rather than re-deriving one, and make the run observable from its first
minute or it is a bet rather than a run.

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

## When a source is blocked for an agent, stop and say so loudly

**A human can retrieve in thirty seconds what no agent in this container can retrieve at all.**
The project owner has a browser, a subscription, an institutional login, an ORCID, a credit card
and a face. This session has none of those. So a blocked acquisition is not a dead end and it is
not a reason to proceed on a proxy — it is a *handover*, and the only thing that makes it happen
is saying so, specifically, out loud, in the moment.

What is permanently blocked here, and should be escalated rather than worked around:

- a paywall, a 403 from a publisher, a subscription article's supplementary materials;
- a captcha or a bot challenge — including a page that returns **HTTP 200** and serves a
  challenge instead of content, which is the one that fools a status-code check;
- an institutional or federated login, an SSO redirect, anything needing 2FA;
- a licence click-through, a registration form, a data-use agreement;
- a token or API key tied to a human identity, and an account only a person can create.

**How to escalate.** Say it in the message you are already writing, not in a note somebody might
read later. Name the artefact, the exact URLs tried, what each one returned, what the file would
settle, and where to put it. Then ask with the choice mechanism, because what to fetch is often a
real decision — the main article, the supplement, or both — and the answer changes what you do.
Register the blocker in `policies/sources.json` with `status: unretrieved` and the blocker text
in the same breath, so the gap is in the repository and not only in a conversation.

**What not to do, in order of how badly it goes wrong:**

- Do not quietly fall back to a secondary source. `DESIGN.md` §B1 step 0 and the last line of
  this file both forbid it, and a blocked primary source is exactly the moment the temptation
  arrives.
- Do not keep working on the proxy and mention the gap in a caveat. A caveat at the end of a
  long run is not an ask; by the time it is written, the work resting on the proxy is already
  done.
- Do not treat "I tried three times and it failed" as a finished investigation. It is a finished
  *attempt*, and the next step is a person, not a fourth retry.

**This is a live lesson, not a hypothetical.** A2.1 re-executed Evo's six published rules against
both releases, ran a ten-fold deepening over about twenty hours of compute, and reported family
survival figures — all of it resting on the **preprint**, because the version of record was
registered as blocked (`S-EVO1-SCIENCE`: science.org 403, a PMC page serving a captcha behind an
HTTP 200). The owner asked whether the rules were identical to the labs' own. They were not
*known* to be. One sentence — "the Science version is blocked for me, can you grab it" — would
have settled the foundation of the whole task before the compute was spent, and when it was
finally asked the four files arrived within the hour. **Ask at the moment you discover the
blocker, not when someone questions the result.**

Two smaller cases are on the record for shape: A1.7 stopped with everything establishable
without a JGI credential finished, said precisely what it needed, and kept `in-progress` with a
waiting-on line rather than inventing a workaround — that is the behaviour to copy. And ESM3's
version of record and its 101-page supplement were supplied by the owner the same way; the
supplement, not the main text, was what settled the question, which is usually true of a methods
appendix.

**Licence, when a human supplies a subscription file.** Storage is the owner's call and the
register records which way it went: committed with a licence note, or `retrieved_not_stored`
with only a digest, which bars every quote from citing that id and `tools/policies.py` enforces.
Ask; do not assume redistribution is permitted because the bytes are now on disk.

## Decisions

`tasks/DECISIONS.md` is append-only. Add an entry whenever you resolve an ambiguity that a
later reader would otherwise have to reverse-engineer: a proxy substitution, a threshold, a
reading of vague policy prose, a model-class choice, a scope call. One entry, dated, with the
alternatives you rejected and why.

This is not bureaucracy. §A0 and §B1 both say under-specification is itself a finding — the
log is what turns scattered judgement calls into a paper appendix instead of lost context.

**Take the number when you append, then check it again before you push.** Two tracks appending
at once both pick the next free number, and because they are appends to different parts of the
file they merge cleanly while colliding semantically — the log ends up with two entries sharing an
ID, which makes every citation of it ambiguous. Pulling first does not prevent this: the other
track's append can land between your pull and your push. So re-read the headings after the pull
that precedes your push, and if your number has been taken, renumber yours to the next free one.

When renumbering, two rules. **Move the entry that is cited from fewer places** — an entry already
referenced from `src/` or from a merged write-up is the expensive one to move, and which entry was
committed first is the tie-breaker, not the deciding factor. And **leave a `Numbering:` line in the
renumbered entry** recording what it used to be: commit messages and pull requests citing the old
number are already published and cannot be rewritten, so that line is the only thing that makes
them resolve. This happened once, between A1.2 and A1.5 at D-032; D-041 is the worked example.

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

**A database larger than 200 GB cannot be one database.** The policy caps volumes at 200 GB in
`gp3`/`gp2`, and A1.6's alignment target — UniRef's three tiers plus MGnify90 — is upward of
400 GB once built. No permitted instance can hold it, so the corpus is sharded and the small
side of the comparison is queried against each shard in turn. Work out which side of a search is
the small one before sizing anything: measured on identical data, querying 15,845 seeds against
a 2M-sequence target took 335 s, and the same comparison with the corpus as the query had not
left the prefilter after 45 minutes.

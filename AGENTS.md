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

`README.md` carries the map and `results/README.md` carries the figures; neither is duplicated
here, because the two maps this file used to hold drifted apart. What an agent needs on top of
the README:

- **`results/README.md`** is the record that matters now: every published figure with the
  contract defining it, the tool that computed it, its artefact, and the task and decision ids
  it was fixed under. Update it in the same change as any figure it describes.
- **`docs/status.md`** is what is done, what is open and which gates are closed. It is
  hand-maintained, so correct it rather than working around it.
- **`docs/working-record.md`** says how to resolve a task id (`A2.1`) or a decision id (`D-245`):
  the 80 task cards, the append-only decision log and the generated board left the tree on
  19 November 2026 and are in git history at `fbc8b41`, plus a copy in the project's own files.
- **`metrics/`** holds the output contracts, and they are still authoritative definitions.
- **`tools/README.md`** indexes all 97 scripts by purpose and marks the ones a published figure
  rests on. Every tool and module opens with a docstring naming its task; read that rather than
  inferring from a list.
- **`src/amazebio/repro.py`** is the one module to know before writing a pipeline: seeding, input
  pinning, run provenance, and the two refusals (dirty tree, parameter declared after an output).
- **`src/amazebio/objectstore.py`** is the only way to reach the result store. Never construct an
  S3 client; a test fails the build if a module under `src/` or `tools/` builds its own.

Run `pixi run -e dev check` before every commit — it is exactly what CI runs, so a green local
run means a green CI run. Seven steps, in order: lint, format, **policy evidence**,
**filter specs**, **model inventory**, **assay register**, tests. The four in bold are the evidence checks, and
they are the ones a change to `policies/` or `assays/` trips; do not read "lint and tests" and assume a
documentation-only change is safe.

## How to pick up work

1. Read `DESIGN.md` for the phase you are entering, and this file.
2. Read `docs/status.md` for where the work has got to, and `results/README.md` for what is
   already measured and how. Do not re-derive a figure that has a row there.
3. Check the **Gates** below. Never work past a closed gate, however convenient it would be.
4. Work on a feature branch, one piece of work per branch, and open a pull request.

A piece of work that turns out to be two should be split into two branches and two pull
requests, not quietly widened. Say in the pull request what the work was for and what it
settles, because that description is now the record: it is what a later reader finds when they
ask why something is the way it is.

If a figure changes, or a decision bears on one, the change is not finished until
`results/README.md` says so in the same pull request.

## Where commits go

Everything lands on a feature branch and arrives on `main` through a pull request. There is no
longer a class of change that goes straight to `main`: the project management that used to
need that — task claims, a generated board, an append-only log — left the tree on
19 November 2026 (`docs/working-record.md`).

## Gates

Five commitments act as gates. They are not work items so much as checkpoints that make it
*structurally impossible* to walk past a commitment by accident. Three are closed;
`docs/status.md` carries their current state:

| Gate | Holds | Why |
|---|---|---|
| **A1.1** released-vs-actual data verified | all corpus reconstruction | Determines whether Phase A audits the real thing or a proxy, and therefore how strongly every downstream claim may be worded. |
| **A3.3** headline counts independently reimplemented | Phase A write-up, preprint | §7 requires a second method before publication. Not optional. |
| **B5.1** pre-registration frozen | all Phase B analysis | §B5 requires the analysis plan fixed before results are seen. A freeze after the fact is not a freeze. |
| **C6.3** headline curves independently reimplemented | cost-curve results, preprint | §7's second-method requirement, one phase over: a claim that filtering *cannot* work for a family is at least as consequential as a Phase A count. |
| **X3.1** disclosure window honoured | preprint | §4 requires disclosure before any preprint; §7 requires treating the window as substance. |

A sixth, whole-family holdout validation, was superseded by the collateral cost curve
(D-009) and is deliberately not run; the independent reimplementation of the curves is the live
gate on Phase C.

**If you believe a gate should open, that is the project owner's call, and it is never a
judgement made mid-task.** Record the answer in the pull request that acts on it.

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

A decision is any resolution a later reader would otherwise have to reverse-engineer: a proxy
substitution, a threshold, a reading of vague policy prose, a model-class choice, a scope call.
Record it with the alternatives you rejected and why. §A0 and §B1 both say under-specification
is itself a finding, so these are material, not bureaucracy.

Where it goes:

- **If it bears on a published figure**, into `results/README.md` beside that figure, in the
  same change. That file is what a reader is sent to, so a qualification that lives anywhere
  else will not be read.
- **Otherwise, into the pull request** that acts on it, and into the project thread where the
  work is discussed.

Decisions up to 19 November 2026 are in the append-only log in git history, cited throughout
this repository as `D-NNN`; `docs/working-record.md` says how to read one. Do not start a new
log. The log's purpose — that a number is readable against what was known when it was fixed —
is served by keeping those ids resolvable and by keeping new qualifications next to the figures
they qualify.

**Never edit a historical decision.** It was append-only for a reason: an entry describes what
was known on its date, and a result read against a rewritten record is not traceable.

## Definition of done

A task is `done` when all of:

- every Done-when criterion is demonstrably met;
- results regenerate from pinned inputs and seeds;
- new code has tests, and CI is green;
- any decision made along the way is written down where **Decisions** says it goes;
- `results/README.md` and `docs/status.md` are true after the change.

## Things not to do

- Do not reuse or renumber a task or decision id. They are cited from commits, from the
  metrics contracts, from `results/README.md` and from the write-up.
- Do not widen a piece of work to absorb an adjacent problem. New branch, new pull request.
- Do not start a replacement for the decision log. See **Decisions**.
- Do not leave a figure's qualification only in a pull request. It belongs in
  `results/README.md`, where it will be read.
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

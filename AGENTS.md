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

**The module and tool lists below are excerpts, not inventories.** There are 31 modules in
`src/amazebio/` and 36 scripts in `tools/`; the ones named here are the entry points worth
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
pdfs/                 owner-supplied subscription sources and supplements
src/amazebio/         library code — 31 modules; a selection follows
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
tools/                36 scripts; a selection follows
tools/board.py        regenerates tasks/BOARD.md from task frontmatter
tools/stage_uniref.py stages a pinned UniRef release into object storage, streaming
tools/count_clusters.py counts clusters in a staged tier and checks the composition
tools/stage_opengenome.py stages the pinned Evo nucleotide corpora, by component
tools/ec2_count.py    runs the count in-region on EC2; see "Running work on EC2"
tools/esm3_composition.py writes ESM3's stated composition and its reconciliation gaps
tools/taxonomy_dependency.py which taxonomy tool the denylist's removals actually rest on
tools/taxonomy_benchmark.py builds the labelled set and scores the tool's error by direction
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
run means a green CI run. Seven steps, in order: lint, format, task graph, **policy evidence**,
**filter specs**, **model inventory**, tests. The three in bold are the evidence checks, and
they are the ones a change to `policies/` trips; do not read "lint and tests" and assume a
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

**Launch an instance sparingly, and only when being in-region is the point.** The test is whether
the work is bound by data movement that is free inside `us-east-1` and metered outside it — reading
the staged corpora is the case that qualifies, because a full pass over them is tens of gigabytes.
Compute that would run acceptably in the session container does not qualify, and neither does
convenience. An instance costs money, leaves a resource that can be forgotten, and cannot be
inspected once running: assume you get one shot at `UserData` and nothing else.

A1.3 learned the following the hard way. `tools/ec2_count.py` is the worked example.

**What the account's policy allows, and what it does not.** `ec2:RunInstances` is permitted, but
only with a `Project=ClaudeSpike` tag and a non-empty `Owner` tag, from an allowlisted instance
type, with volumes of 200 GB or less in `gp3`/`gp2`. Omit the tags and the refusal is a bare
`UnauthorizedOperation`, which reads exactly like not having permission at all — that misreading
cost a round trip. `iam:*` is denied, so you cannot create, inspect or list roles and instance
profiles; the `AmazebioStager` instance profile and the matching `iam:PassRole` grant already exist
and are the only way an instance gets AWS credentials. Do not try to supply credentials another
way: the session's own are injected by a proxy and never exposed to it, so they cannot be copied
onto a machine, and a presigned URL cannot be generated for the same reason.

**You cannot talk to the instance.** `ssm:SendCommand` is denied, no key pair exists, and
`ec2:AuthorizeSecurityGroupIngress` is denied, so there is no shell, no SSH and no inbound
connection. Everything the instance will do must be decided before launch and written into
`UserData`. Results come back by the instance writing them to S3. Progress comes back through
`ec2:GetConsoleOutput`, which is allowed, best-effort, and empty for the first minute or so.

**Make it terminate itself, and terminate it anyway.** Pass
`InstanceInitiatedShutdownBehavior="terminate"` at launch — `ec2:ModifyInstanceAttribute` is denied,
so it cannot be set afterwards, and without it a self-shutdown merely stops the instance and keeps
billing its volume. Then also call `ec2:TerminateInstances` from the launcher in a `finally`, because
a `UserData` that fails before its own `shutdown` would otherwise leave the instance running
indefinitely. Both, not either.

**Pick the interpreter explicitly.** Amazon Linux 2023 ships Python 3.9 as `python3`, and this
project needs 3.12; `datetime.UTC` alone is 3.11+. Install `python3.12` and invoke it by name. A
run that trusts `python3` dies on an `ImportError` about half a minute in, having read nothing.

**Make a long run report to object storage, and do not trust silence.** `GetConsoleOutput` does
keep recording well after boot — verified 2026-10-17, with per-cell progress lines arriving 103
minutes in — so it is a real channel, just a best-effort one with no guarantee of freshness. What
it cannot do is distinguish a process that has died from one that is printing nothing: on
2026-10-16 two runs died 31 seconds in, the console held only their boot output, and that looked
exactly like a long pass with a quiet console. Four hours were spent on that reading, and the
correction is in D-127.

The other channels are genuinely closed here: `cloudwatch:GetMetricStatistics` and
`ec2:GetConsoleScreenshot` are both denied, on top of the SSH and SSM denials above, and
`DescribeInstanceStatus` only reports that the OS is alive. One channel that *is* allowed and
worth knowing: `ec2:DescribeInstanceAttribute` returns the instance's `UserData`, which settles
what a running instance was actually told to do.

So anything that runs longer than a few minutes writes a heartbeat to object storage on an
interval and publishes each measurement as it is taken — `esm3_calibrate.py` is the worked
example, and it took three attempts to apply that to every stage rather than only to the one that
had just failed. A step with no heartbeat is a step whose silence means nothing at all.

It is the worked example for the second half of that more than the first, measured 2026-10-19
(D-192): in `--measure caps` the heartbeat is written once before a reading's slack cell and the
interval heartbeat covers only the corpus pass, so through a 35-minute cell it does not move —
`written_at` read 18:46 while the run was demonstrably alive at 19:43. What made that run
observable was the artefact growing as each cell published. Both halves are the rule; only one of
them is implemented everywhere, so check which one a mode gives you before reading its silence.

**A log uploaded on exit is not a channel.** A2.6's census workers redirect stdout to a file on
the instance and upload it when the worker finishes, which gives you nothing at all while it
runs — the console stops recording after boot, and the parts appear only as each band completes.
That is the same silence as a dead process. Upload the log on the heartbeat interval, not at the
end, and do it from whichever loop is already running rather than from a handler that a hard
failure skips.

**The boot-armed shutdown timer works, and it also blocks the immediate shutdown — cancel it
first.** Arm `shutdown -h +N` in `UserData` before anything that can fail; observed 2026-10-16, it
fires on time, four hours after a watcher had been killed and the launcher could no longer
terminate anything, and EC2 reports it in `StateTransitionReason` as `User initiated` — the same
wording as a manual termination, and **not** `Server.SpotInstanceTermination`, so that field
distinguishes a reclaim from a shutdown but not a shutdown from a human.

The trap is the other direction. **`shutdown -h now` does nothing while that timer is pending**:
systemd already has a shutdown scheduled and the immediate one does not replace it. So a script
that fails in thirty seconds sits idle until the timer fires, burning the whole window, and from
outside — no console after boot, no artefact, process alive, status checks `ok` — that is
indistinguishable from a long pass still working. It cost two launches and most of a day to
diagnose as exactly that (D-127). Run `shutdown -c` before `shutdown -h now`, keep
`systemctl --no-block poweroff` and `halt -p` as fallbacks, and route every exit path through one
helper; `tools/ec2_similarity.py`'s `die` is the worked example.

**Ship the payload by derivation, not by hand.** The instance has no checkout, so the launcher
tars up a list of files. Twice — 2026-10-16 and 2026-10-17 — a module was added to a tool's
imports and not to that list, and the instance died on an `ImportError` about half a minute in,
having read nothing. Derive the first-party import closure from the source and test it, as
`tests/test_ec2_similarity.py` does, and import the shipped tool on the instance **before** the
long work starts: on the instance a missing import costs an hour and a launch, and in a test it
costs a second.

**An import closure is not a dependency closure.** A2.6 spent four launches on this in one
afternoon, each one dying in five or six minutes. The closure walk finds what a source
*imports*; it cannot find what a source *reads*, and it cannot find an import that happens
inside a function. The payload shipped no `policies/specs`, so eight workers died on `no
policy specs found` — nothing imports a YAML directory. Then the specs shipped and the
workers died again, because `policyspec` imports `yaml` inside `load_policy_dir` rather than
at module scope, so the payload imported cleanly and failed on the first policy read, and no
wheel carried PyYAML. Two things fix the class rather than the instance. Walk the shipped
sources with `ast` for *every* third-party import, map each to the wheel that provides it,
and fail the test on one that is not mapped. And unpack the payload into a bare directory in
a test and run it there with nothing else on the path — `tests/test_ec2_detect_census.py`
does both, and the second is the only check that fails for the same reasons the instance
does. The pre-flight on the instance should likewise *load* what the run needs — the policy
specs, the manifests — not merely import the module.

**Parallel workers on one instance must not share an output name.** A2.6 runs eight bands of
one release at once and every worker publishes to the same durable prefix. Anything named for
the release alone is written eight times: the run manifest loses seven, and eight different
index bodies under one key are refused outright by the commit-keyed copy (D-216) — *after*
each worker's six hours, not before. Put the band in the name. A1.5 hit the same shape with
two staging passes, which is why `detect_profiles` already named its manifest per release;
one more level of parallelism needed one more level of naming.

**`aws s3 cp --recursive` over an empty prefix exits 0.** A2.6's first launch copied the A1.4
manifests from `s3://bucket/results/a1-4/` with the bucket prefix missing, the copy reported
success, and the workers started on an empty directory. A copy that must bring something is
followed by a `test -f` on something it must have brought.

**Bring the logs back yourself; the console will not.** Across those four launches
`GetConsoleOutput` truncated mid-way through staging twice and returned empty twice, including
for ten minutes after the instance that needed reading had terminated. Tee the whole script to
a file, give each worker its own log, and have the `die` helper upload all of them before it
powers off. Write the exit reason as its own small object too: it is the one thing you always
want and the cheapest thing to lose.

**Probe without the flag that publishes.** `detect_profiles --band` publishes a part that
`--assemble` reads as *the* result for that band, so a probe with `--limit-records` publishes
a part covering twenty records and claiming the whole band — and the coverage check still
passes, because the bands do tile. One reached the census prefix on 2026-10-20 and the store
has no delete. Either refuse the pair in code, which is what was done, or redirect the durable
destination for the probe.

**A dry run authorizes; it does not execute.** `DryRun=True` checks permissions and parameters and
returns `DryRunOperation` on success, which is worth doing. It runs no `UserData`, so it cannot
catch a missing dependency, a wrong interpreter or a broken script. Those checks belong inside the
script.

**Carry provenance in, because the instance has none.** There is no git checkout on the instance, so
`amazebio.repro` cannot discover the commit and a manifest produced there is untraceable. The
launcher refuses to run from a dirty tree and passes the commit in explicitly; keep that. A result
that cannot be traced to the code that produced it is not citable, which is the whole point of
`repro`.

**A memory ceiling is not a reason to launch an instance.** A4.2 hit one: reproducing IMG/VR's own
marker search needs about 24 GB to hold the profile index in a single pass and the session container
has 16. The test in this section is data movement, and a memory bound is not that — splitting the
target database (`--splits 8` for geNomad, which is the same thing one rank down) made the search
fit and changed nothing about the result. Check whether the work can be split before concluding it
needs a bigger machine.

**Know the parallelism before choosing a size.** A gzip stream cannot be decompressed in parallel,
so one `.gz` file is one thread however many cores are present. For the UniRef tiers that caps
useful parallelism at one process per tier, and the largest tier sets the wall clock; a bigger
instance buys nothing. Work out the real ceiling first — the honest answer is often that a small
instance is the right one.

**The corpus bucket has no `s3:DeleteObject`.** Anything written there is permanent. That is
deliberate — it is what makes a staged corpus un-rewritable — but it means a bug that writes junk
writes it forever. Before a run that uploads, be sure about the keys it will produce; A1.3 left four
0-byte objects behind that cannot be removed.

**A rehearsal is the thing most likely to write junk there, because `--out` and the durable prefix
are decided separately.** `repro.run`'s `durable` is derived from the task id, so it cannot see
where the run was told to write: a probe from a scratch directory publishes to the real results
prefix under the names the deliverable will use. The fix is one line per tool — publish only when
`--out` resolves to the task's canonical `artifacts/<slug>`, claim `durable_exempt` otherwise, and
print why. `tools/detect_segmented.py`'s `durable_for` is the worked example.

**And when you fix something like that, fix the shape, not the tool.** A2.5 hit exactly this on
2026-10-19, the guard went into `detect_segmented.py`, and on 2026-10-20 A2.6 hit it again in
`detect_profiles.py` — permanently, in a bucket with no delete (D-193, then D-224). One tool was
guarded and four were not. Before closing an incident, grep for every call site with the same
shape and fix all of them, or say in the decision entry which ones you left and why.

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

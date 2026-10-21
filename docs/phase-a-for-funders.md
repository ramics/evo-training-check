# Can you check whether a published data filter did what it says?

**A funder-facing account of Phase A.** Draft of 2026-10-21, internal to the project. Not for
circulation: `AGENTS.md` holds findings inside the project until the disclosure task (X3.1) has
run, and that gate has not opened.

This is written for a reader who is comfortable with software and statistics and knows nothing
about biology or about this project. It explains what was measured, why the measurement is worth
money, what the numbers are, and — at the end, with costs — what more funding would buy.

---

## 1. The problem, from first principles

Large models are trained on public sequence databases. Several of the organisations that release
those models say, in their papers or model cards, that they first removed a category of material
they judged hazardous from the training data. The statement usually takes the form of a short
prose paragraph: a named database, a named list of excluded organisms, a rule or two about what
counts as too similar to something on that list.

Those statements are doing real work. They are cited in policy discussions as evidence that a
category of risk has been handled upstream, at the data layer, where handling it is cheap and
durable. A great deal is inferred from a paragraph.

Almost nothing is checked. The paragraph is prose, not code; the filter's own implementation is
not usually released; and the released corpus is large enough that nobody reads it. So three
questions sit unanswered:

1. **Is the policy even executable?** Prose admits more than one reading. Does the choice of
   reading change what gets removed?
2. **Does the released corpus match the policy?** If the policy says a category is absent, is it
   absent from the artefact anyone can download?
3. **How much could the policy ever remove?** A rule that keys on a metadata field can only act
   on records that carry that field. That ceiling is measurable and nobody had measured it.

Phase A of this project is an attempt to answer those three questions for real releases, with
every number traceable to an artefact that can be regenerated. It is a measurement project, not
an adversarial one: it builds no capability, attacks nothing, and treats the discrepancy between
a stated procedure and a published artefact as a documentation and provenance problem.

## 2. What was actually built and measured

The subject is the pair of publicly released training corpora for the Evo family of nucleotide
models (`opengenome` and `opengenome2`), together with the published exclusion policies for those
releases and, for comparison, the policy statements of several protein models. The work has four
parts.

**A policy becomes a specification.** Each published paragraph was transcribed into a machine
checkable spec with its quotations verified against the source text, and then into *three*
executable readings — literal, charitable and strict — because prose genuinely admits all three.
The spread between readings is reported as a result in its own right rather than hidden by a
choice.

**The released corpus is streamed through the policy.** Every record in the release is passed
through each reading, and each record comes out labelled with which rule, if any, would remove
it, and which rules could not reach a verdict because the release does not carry the metadata
that rule reads. "No verdict" is kept as its own category throughout. Declaring an absent
evidence channel as present would have manufactured a clean pass out of missing metadata, and the
audit refuses to do that.

**What survives is searched for the material the policy says it excluded.** This is the
substantive measurement. Surviving records are translated into their protein content and searched
against two independent public registries of sequence families — one assembled from curated
protein-family models (1,719 of its 30,134 families are viral), one from a virus-specific
reference set (13,679 families). A family counts as present only when a hit clears a threshold
that was fixed and recorded *before* any result was looked at. A second detection route looks for
material integrated into bacterial genomes rather than free-standing.

**The headline is re-derived by a second implementation.** A separate module, written without
reading the first, rebuilds the headline counts from the primitive detection rows rather than
from the aggregates, rebuilds the denominators from the pinned registry files, and re-executes the
policy over the release independently. 334 numbers were compared across 16 reported groups. Every
headline figure agrees exactly.

## 3. The three findings

### 3.1 A filter's reach is bounded by the metadata it reads, and the bound is small

The published exclusion rules for the Evo releases name specific organism groups at two
taxonomic ranks. The database they were applied to labels its records richly at coarse ranks and
sparsely at the two ranks the rules actually use: across all 15,677,623 records, 96.7% carry a
label at the coarsest rank, and **6.25% carry one at the rank the hazard list is written
against** (8.67% at the other). Measured over the population the rules are really handed, after
an earlier confidence step, the figures are 7.87% and 8.85%. A companion rule about host
association can be evaluated on 13.71% of that population and removes the remainder *for lacking
the evidence*, which is a different act from examining them.

The component is not badly annotated. It is annotated at the wrong ranks for the rules written
against it. So the policy's discriminating power over its own input has a measured ceiling in the
single-digit percentages, and that is a structural fact about writing filters against
third-party metadata rather than a criticism of one team. It is also, we think, the single most
transferable result in Phase A: it applies to any filter keyed on a metadata field, and it can be
computed for any such filter in an afternoon.

### 3.2 Material the policy excludes is detectably present in the released corpora

Searching the surviving records against the curated family registry finds, at the depth sampled:

| release | records searched | viral families detected (of 1,719) |
|---|---|---|
| Evo 1 (`opengenome`) | 53,140 of 2,653,047 (2%) | **597** (34.7%) |
| Evo 2 (`opengenome2`) | 30,859 (1%) | **812** (47.2%) |

The profile search alone accounts for 590 and 811 of these; the remainder come from the second,
integrated-element route.

Three qualifications travel with those numbers everywhere, and they are not decoration.

**They are lower bounds.** A family is counted only when a sampled record carried it. Anything
the sample missed is absent from the count and present in the corpus. The honest form of the
claim is *at least this much, and the ceiling was not found*.

**The ceiling really was not found.** The sample was deepened tenfold and the counts rose
steeply rather than settling: Evo 1 from 470 families to 590, Evo 2 from 492 to 811, with the
accumulation curve still climbing on the last doubling of records searched. A number that nearly
doubles when you look twice as hard is a floor, not an estimate.

**The two releases are not comparable as rates.** Evo 2 reaches 812 families while being sampled
at a tenth of Evo 1's rate. Whatever the difference between the two releases is, this table does
not measure it, and any presentation that puts the two numbers side by side has to say which rate
each came from. (There is a known structural reason the second release is richer per unit of
sequence — the first publishes a deduplicated subset of the same source database — but that
explanation was in hand before the measurement, not invented to fit it.)

A separate, much stricter check asks the complementary question: how many records survive a rule
that the release's own metadata is sufficient to evaluate? The answer is 95 of 2,653,047, all of
them through a single clause about unassigned classification. Those are two different questions
and the audit keeps them apart: the first measures what is in the corpus, the second measures
demonstrable non-conformance with the written policy. Only the second is an inconsistency claim,
and it is small.

### 3.3 The artefact that can be audited is not the artefact that was trained on

This began as the project's most alarming-looking number and ended as its most interesting one.

The second release publishes its viral component twice, in two different file formats. The
arithmetic between them suggested that 264,570 records which the published procedure removes had
nonetheless reached the training data. Phase A's job was to rule that in or out, so it counted
both representations by two independent methods, the second using newline counting and byte
arithmetic that never decodes or parses the content at all.

The alarming reading is **wrong, and the correct reading is more consequential**. The format that
was trained on matches the first release's filtered output exactly — to the record and to the
nucleotide, zero difference on both deltas. The filter's output was carried forward unchanged.
But the *other* representation, the only one that carries the source identifiers a filter can be
checked against, holds **304,448 more records** (and 2.64 billion more units of sequence),
including the ones the procedure removes.

So the filter demonstrably worked on what was trained, and the only artefact against which anyone
can verify that claim is a different and larger set. The filter cannot be checked against the
thing the filter produced. Nothing in the data speaks to anyone's intent, and the project says so
explicitly; this is a provenance and release-hygiene finding. It is also the finding most likely
to change practice, because the fix is nearly free: publish the filtered artefact in the
representation that carries identifiers, or publish the removal list. Phase A's companion output
is a fourteen-item disclosure standard in which each item exists because an audit obstacle
produced it.

## 4. Why these numbers can be trusted: the project's error record

The strongest argument for this work's rigour is not that it has been careful. It is that it has
caught its own serious errors, in public, with the corrections recorded alongside the original
claims, and that the instruments which caught them were built before they were needed. Three
examples from the past two days, all of them embarrassing and all of them documented:

**A headline was 32% too high, and four internal checks passed over it.** The deepened search
runs in bands, and the code that reassembled the bands named its output files by policy and
registry but not by release, so both releases' rows landed in one file and each release counted
the other's detections. The inflated figure passed the project's checks on band tiling, sample
nesting, per-source counts and denominator — because each of those asks whether a result has the
right *shape*, and none asks whether a row belongs to the corpus the result is about. What caught
it was re-running the whole pass from its pins: the bands reproduced exactly and the assembly did
not. A second, independent fault in the same area was found the same evening — a provenance copy
of each table, written for a different good reason, was being read back in and silently restored
superseded rows — and it was found by asking which objects the pass had read rather than whether
its output looked right. The corrected figures are the ones in §3.2, and they turn out to equal
the figures from the project's own earlier prose, which an intervening correction had wrongly
withdrawn.

**Every protein score the project had produced was computed on a truncated sequence.** The
scoring harness for Phase B built each input row by hand and never appended the token that marks
the end of a sequence, and encoded the opening token as a count rather than an identifier. The
models were therefore reading every protein as if it stopped early. This was found by the
project's own requirement that the harness reproduce a published reference column where one
exists: agreement sat persistently just below the acceptance floor, and regressing the
disagreement position by position showed it concentrated in the last few residues of every assay
and worst on the shortest construct — the signature of a truncation. On the worst assay the fix
moved agreement from 0.9359 to 0.9994. Every earlier score was recomputed and none of the
pre-fix numbers is cited anywhere.

**The project's second-method requirement is real and has teeth.** Headline counts are
reimplemented by a module written without reading the first implementation, and the comparison
publishes its disagreements as well as its agreements: one divergence survives, in how a family's
records are apportioned between routes, and it is reported with the single family that accounts
for most of it. The headline never passes through that split, so no headline figure moves — and
the audit says so rather than quietly reconciling.

A funder should read this section as the reason to believe §3. The project's working rule is that
a figure is prose until it can be regenerated from a pinned artefact, and all three of these were
caught by instruments that exist to enforce that rule.

## 5. What Phase A does not claim

- **Nothing about intent.** The counts support a mismatch between a stated procedure and a
  published artefact. They say nothing about what anyone meant to do.
- **No claim that any filter failed to run.** On the one release where it can be checked, the
  filter's output was carried forward exactly.
- **No capability claim.** Detecting that a sequence family is present in a corpus is not a
  statement that a model trained on that corpus can do anything in particular. That question is
  Phase B's, it is being measured separately against published benchmarks, and it is not
  answered here.
- **Not a population measurement.** Every survival figure is a lower bound from a sample. The
  pass that would turn them into population figures has not been bought.
- **One model family, properly.** The nucleotide work covers two releases of one model family.
  The protein-model arm is a policy comparison and a staged proxy corpus, not an audit of a
  released protein corpus.
- **Three readings agree here, which is not a claim that the policy is reproducible.** On this
  corpus the literal, charitable and strict readings return identical counts. That is a fact
  about this corpus's metadata, not a general finding about the prose.

## 6. Where funding expands the study

Four items, in the order we would spend on them. The cash numbers are small and honest; the real
cost is skilled time, and that is what a grant would buy.

**1. Turn the lower bounds into population figures.** The survival counts come from a 1–2%
sample. A full pass over the corpus against the curated registry is a compute job of a few
thousand core-hours — tens of dollars at spot prices, not thousands. The project's first attempt
at it failed instructively: two machines ran for fourteen hours, published nothing, and cost
about $5.40, because results were only written when a whole band finished and the machines were
powered off from outside the script before any band did. The fix (publish per chunk, sync logs
on a timer, time one band before launching sixteen) is written down and untested. This is the
single highest-value purchase in the project, because it converts the headline from "at least
34.7% and 47.2%" into a measured value, and it is the one item where the obstacle is engineering
discipline rather than money.

**2. Deepen the second registry, and keep it honest in the meantime.** The virus-specific
registry is currently measured at a tenth the depth of the curated one: 4.25% and 10.84% of its
13,679 families. Deepening it is about ten hours of local compute and no money. We are *not*
recommending it yet, for a reason worth stating because it is the kind of judgement a funder is
buying: both registries were already searched at the same per-release rates, so a like-for-like
comparison between registries exists for free, and the deeper pass would raise one bound while
carrying exactly the structural risk that produced the 32% error above, with no second instrument
available to catch it (a ten-hour pass cannot be re-run from pins as a matter of routine). The
limitation is better named, costed and published than papered over with a second deep number. It
becomes worth buying the moment the argument comes to rest on that registry, or as soon as the
machine is free.
**Presentation consequence either way:** any table carrying both registries has to state that
they were sampled at different depths, because a reader who sets 34.7% beside 4.25% will read a
sampling artefact as a finding.

**3. Extend beyond one model family.** Everything above is tooling, not a one-off: the audit is
packaged behind a single interface that takes a policy, a corpus and a set of detectors, and runs
against a bundled fixture in one command. The marginal cost of auditing the next release is
staging its corpus and transcribing its policy. The value of the disclosure standard rises
steeply with the number of releases scored against it, and so does the credibility of the
structural finding in §3.1.

**4. Run the disclosure process properly.** Nothing here has left the project, by the project's
own rule, and it should not until the organisations concerned have been contacted and given time.
Doing that well — writing to each, handling responses, revising — is unglamorous, takes weeks of
calendar time, and is the step that decides whether this work changes anything. It needs a person,
not a machine.

## 7. Provenance

Every figure above traces to a task file, a pinned artefact and a numbered decision in the
project's append-only decision log, which records corrections as new entries rather than edits.
The headline survival figures are the corrected ones recorded on 2026-10-21; the superseded
versions, and the reasoning that withdrew them, remain in the log. Figures quoted here that are
still prose rather than regenerated artefacts are the deepened second-registry numbers, which is
why §6 treats them as a direction and not a result.

Reproduction: the environment is pinned, the registries are pinned by digest, and the thresholds
were recorded before any result was inspected.

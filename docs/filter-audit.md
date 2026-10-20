# `filter-audit` — the Phase A deliverable

Policy specification in, corpus in, survival-route report out.

This is the shippable form of Phase A (`DESIGN.md` §A5). The audit itself is five modules
deep — `policyspec` reads a filter policy, `apply` streams a release through it, `detect`
defines what a detection has to carry, `quantify` merges the detectors, `survival` holds the
frozen metrics — and that is the right shape for doing the work and the wrong shape for
anyone who wants to run it against their own filter. `amazebio.filteraudit` is the one door.

```
pixi run -e dev python tools/filter_audit.py --corpus fixture
```

## What it is not

**It is not a second implementation.** Every number in a report comes from the same function
that produced A3.2's headline. That is deliberate: two implementations behind one interface
are two things to keep in step, and the one that drifts is the one nobody is reading. The
second-method requirement in `DESIGN.md` §7 is A3.3's job, and A3.3 is written by someone who
has not read the first implementation — a different thing from this.

`tools/filter_audit.py --verify` is the measurement behind that claim: it reads the detector
documents A3.2's own headline names, runs them through this interface, and diffs group by
group. All 21 groups reproduce identically.

**It is not a filter.** It does not remove anything from anything. It reads a published
policy, works out what that policy would remove from a named corpus, and counts what survives
against a pinned family registry. The records it reports as removed are what the *policy*
says; whether they are actually absent from the released corpus is a separate question
(A7.1's conformance check) with a much higher evidential bar.

## The interface

### A policy

A `policyspec.Policy`, normally loaded from a YAML spec in `policies/specs/`. Three readings
of the same published prose are normal and expected — literal, charitable, strict — and the
spread between them is itself a result (A0.4). Nothing here prefers one.

### A corpus

Three methods. A staged release implements them by streaming object storage; the bundled
fixture implements them from a dict.

| Method | Returns |
|---|---|
| `components()` | the component names, in report order |
| `records(component)` | every record in one component, as `policyspec.Record` |
| `evidence(component)` | which evidence channels that component can answer |

`evidence` is the one that is easy to get wrong and expensive to get wrong. A channel the
corpus does not carry must be declared absent, so that a rule reading it yields `unresolved`.
Declaring it present when it is empty makes every rule reading it *decide* — in Evo's case
that would have reported the whole viral component as removed by a rule whose input nobody
can see, which is a clean pass manufactured out of missing metadata. Absence of a *key*
inside a carried channel is different: it is data. "No family assigned" is exactly what a
denylist rule has to see.

### Detectors

A detector is a callable taking the surviving records per component and returning a detection
document in the shape `metrics/detections.md` specifies, or `None` if it searched nothing.
Returning `None` rather than an empty table is load-bearing: a detector that found nothing
and a detector that never ran are different facts about a null, and the report keeps them
apart in `detectors_run` and `detectors_absent`.

### The report

A manifest (what the policy did to each component), the quantified groups (M1 and M2 per
registry, overall and per route, each with its interval), and the limitations.

## What each route cannot say

Every report carries these next to its counts, because a count quoted without its route's
limit says more than the audit established.

| Route | What the count does not establish |
|---|---|
| `retained_by_design` | the record was examined and no rule removed it — only as strong as the set of rules that could actually be checked against this release |
| `out_of_scope` | the component is outside this reading's declared scope, so no rule touched it. Another reading of the same published policy may put it in scope without changing any count |
| `unresolved` | the release does not carry the evidence a rule reads. A gap in what was published, not an inference about the record |
| `undetected` | no instrument found the family. Bounds survival from below and never from above: a profile library has no profile for what it has not curated, a structural search depends on predicted structure, and a sampled pass reads a fraction of the corpus |
| `misassigned` | the record survived because a taxonomy tool labelled it as something the policy does not remove. A claim about the tool's error, which A4.* bounds by direction |
| `conformance_failure` | §7 requires record-level evidence before this route is asserted; a detector may not route a detection here in passing |

Two more that hold across every route:

- **The per-route figures do not sum to the overall figure.** A family can survive by more
  than one route. Every table says so; adding them gives a number that means nothing.
- **Survival fractions are never pooled across registries.** Pfam, RVDB-prot and Dfam answer
  different questions about what a "family" is, and a fraction is not quotable without the
  registry it was computed over.

## Reproducibility

The tool runs under `amazebio.repro.run`, which seeds the RNGs, refuses a dirty git tree,
refuses a parameter declared after an output exists, and writes a `run.json` recording inputs,
outputs, parameters and tool versions beside the report. `seed` is required rather than
defaulted: every interval is a bootstrap, and an unseeded one cannot be regenerated.

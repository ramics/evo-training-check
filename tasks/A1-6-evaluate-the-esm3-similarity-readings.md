---
id: A1.6
title: Evaluate the ESM3 similarity readings against the proxy corpus
phase: A
status: in-progress
gate: false
depends_on: [A1.4, A1.5]
blocks: []
design_ref: "§A0, §A1"
deliverable: 1
owner: claude
---

# A1.6 — Evaluate the ESM3 similarity readings against the proxy corpus

**Design reference:** DESIGN.md §A0, §A1 · **Deliverable 1**

## Goal

Produce surviving-record manifests for ESM3-open's charitable and strict readings, which need an
alignment pass that A1.4 deliberately did not buy.

Split out of A1.4 (DECISIONS.md D-043). A1.4 covers every reading whose inputs the staged
releases already carry; these two are the ones that do not, and the difference is acquisition and
spend rather than more of the same work.

## Why this is not A1.4

ESM3-open's filter is similarity-based, so re-executing it needs three things A1.4 has none of:

- **The seed sets.** The viral denylist is "sequences that are annotated as viral in UniProt and
  align almost exclusively to other viral sequences in UniProt", roughly 4M sequences, and the
  select-agent denylist is "all sequences in UniProt belonging to organisms on the Select Agents
  and Toxins List". Neither is published as a set; both have to be rebuilt from UniProt
  annotation. "Almost exclusively" is unquantified in the source and stays that way — see the
  charitable spec's own note — so the reconstruction is itself a reading, and its construction
  needs recording as one.
- **An alignment pass.** ~295 GB of staged proxy corpus against the seed sets. That is in-region
  work by the test in `AGENTS.md`, and the only Phase A task so far whose compute is the cost
  rather than the data movement.
- **A decision about the strict reading's cost.** Strict removes on any detected hit
  (`identity_threshold: 0.0`), so it cannot be derived from a 0.70 run by filtering: it needs the
  full hit list at the aligner's own sensitivity floor, which is the expensive end of the sweep.

The literal reading is not here. It evaluates to `undetermined` for every in-scope record because
the threshold is unpublished, which needs no compute, so A1.4 ships it.

## Steps

- Rebuild both seed sets from UniProt annotation at a pinned release, recording the construction
  of "almost exclusively" as a reading with its alternatives, not as a fact.
- Pin the aligner, its version and every parameter before any output exists.
- Run the charitable reading (0.70) and the strict reading (any hit) over the staged proxy
  corpus, in region, writing manifests in A1.4's format so A2.* and B3.* consume one shape.
- Reconcile against the 10.6M sequences the paper reports its two denylists removed, and report
  the spread between the three readings as §A0 requires.

## Done when

- Both manifests exist in A1.4's format, reproducible from pinned inputs and seeds.
- Seed-set construction is pinned, checksummed and recorded as a reading.
- The comparison against the paper's reported 10.6M is written up, with the proxy qualifier
  A1.1 requires on every ESM3 result.
- A `run.json` manifest pins inputs, outputs, parameters, aligner version and seed.

## Before starting, re-ask the cost question

A1.5 and A1.2 both left this warning and it applies here with more force, because this is compute
rather than storage. Price the alignment pass and put the figure to the project owner before
launching anything. `AGENTS.md`'s EC2 section is the operating manual — one shot at `UserData`, no
shell, self-terminating, provenance carried in — and `tools/ec2_count.py` is the worked example.

Two things that are not fixable by spending more, carried from A1.5: JGI is about a third of
ESM3's unique training tokens and cannot be reconstructed at all, and the structure-side
components were not bought. So no figure of the form "x% of ESM3's corpus" is supportable from
this task either, however thorough the alignment pass is.

## State — 2026-10-15

`in-progress`. **Branch `ccr-3e0650c5-8fsgiq`** carries the work; `main` has only this file,
the board and DECISIONS.md D-092 to D-094.

**Done.** The viral seed set is rebuilt and tested — `src/amazebio/seeds.py`,
`tools/esm3_seeds.py`, `tests/test_seeds.py`, 12 tests, full `check` green. It comes from the
staged UniRef100 tier rather than from UniProtKB, which D-092 argues and prices: the
representative-versus-member gap it opens is 2.38% of viral-seeded clusters, measured, and
travels with the seed count. The taxonomy is pinned to `taxdmp_2023-04-01.zip`, contemporaneous
with UniRef 2023_02 rather than current. MMseqs2 is pinned at 18.8cc5c (D-093).

**The cost question is answered in part.** Orientation and sharding are settled and measured
(D-094): seeds as query against sharded corpus targets, because corpus-as-query had not left the
prefilter after 45 minutes against 335 s the other way round, and because the account's 200 GB
volume cap makes a single 400 GB+ target database impossible on any permitted instance. The
*price* is not yet a number — extrapolation from a 1/88,000 slice spans $10 to $1,400 for the
charitable reading — and the project owner's decision was to calibrate in-region first, about
$10, before the full pass is authorised.

**Left.** The in-region calibration launcher and run; the select-agent seed set; the charitable
and strict passes once the calibration prices them; the comparison against the stated 4M.

**Two things the next worker should not rediscover.** The seed-set reconstruction has a
validation target that works — ESM3 states the viral denylist is roughly 4M sequences — which is
worth having because D-032 established the reported 10.6M removals cannot validate a
reconstruction. And a bounded run cannot estimate the viral share of a tier: UniRef is ordered by
accession, so a prefix is not a sample, and only the full-tier pass produces a seed count.

**Update 2026-10-16.** The first in-region run finished its corpus pass and lost its searches.
The seed set is measured — 3,159,223 viral-seeded clusters out of 350,950,053, the latter matching
the publisher's own count exactly (D-100) — and the representative gap is 1.06%, half what the
prefix suggested. Two faults in how results leave the instance cost the rest, both fixed (D-101).
The one surviving search measurement puts a floor of 3,250 core-hours on UniRef100 alone, which
rules out the cheap end of the estimate, so **A1.6 now targets a sampled pass reporting survival
rates with intervals rather than per-record manifests over the whole corpus**. Downstream consumers
of these manifests need telling.

**Update 2026-10-16, second.** Calibration is finished and the search parameters are fixed
(D-104, D-105). The cost model separates a per-search target scan, linear in target size, from a
marginal per-query term whose exponent climbs from 0.5 to 0.84 over a 200-fold range and is still
rising, so the pass is planned against the linear bound. **The exhaustive charitable pass over the
whole corpus is about $240-450 on spot, both readings roughly $1,000 — so A1.6 scores every record
and the sampled design of D-101 is withdrawn**, along with the clustering and denominator problems
a corpus sample would have carried. Parameters are fixed with their measurements: `-s 5.7`,
`-c 0.8 --cov-mode 1`, `--max-seqs 100000` behind a saturation guard that fails the run rather than
truncating silently, seeds as query, and reporting in identity bands because 8% of matches sit
between 0.70 and 0.75.

**Left:** the select-agent seed set; the `--max-seqs` cost measured where the cap actually binds;
spot support in the launcher; then the authoritative pass.

**Waiting on the project owner:** the spend decision for the authoritative pass, now that it has a
figure — about $240-450 for the charitable reading, roughly $1,000 for both.


## Handoff — 2026-10-16

`in-progress`. **The code is merged — PR #18 landed on `main`, nothing is left on a branch.**
`src/amazebio/seeds.py`, `tools/esm3_seeds.py`, `tools/esm3_calibrate.py`,
`tools/ec2_similarity.py` and their tests are all on `main`, along with decisions D-092 to
D-107. Read those plus this block and you have the task; there is no branch to find.

**Settled.** The viral seed set is measured and stored: 3,159,223 viral-seeded clusters of
350,950,053, the latter matching the publisher's own count exactly (D-100). The FASTA is in
the results prefix beside two preserved calibration grids. The cost model is characterised
over a 200-fold range and plans against its conservative bound (D-104). Search parameters
are fixed with their measurements (D-105), with one correction in D-107: coverage mode is a
three-way reading, not recovered guidance, so the pass reports sensitivity to that choice.
The unpublished threshold is confirmed against the version of record, and the omission is
selective — four other procedures in the same appendix carry full parameter sets (D-107).
Sampling is no longer forced by cost, so D-101's sampled design is withdrawn.

**Left, in order.** The second seed set is not built, and two questions gate it, each needing
its own decision entry: how organism names map to taxonomy ids, which the published list does
not do for you; and which version of that list was in force when the filter ran, since the
source cites a 2024 access date and the retrievable page is live and undated. Then the hit
cap's cost measured where it binds, spot support in the launcher, and the pass.

**Waiting on the project owner.** The scope and handling of the second arm. It is the part of
this task whose output the §4 reporting limits and the X3.1 gate are written for, and it was
being planned as simply the cheaper arm to run first, which is the wrong frame. That needs
settling before the arm is built, not after. Splitting the remaining work into its own task id
is the tidier option under the one-task-per-file rule and is the owner's call, since ids are
permanent and cited.


## Scope settled — 2026-10-16, third

The pass **splits by denylist rather than by corpus** (D-108). The cost/stakes split runs along the
query set, not the target, and the two denylists differ in size by orders of magnitude — so the arm
that needs an exhaustive all-clear is not the expensive arm.

- **Narrow denylist — exhaustive, whole corpus.** Small query set, affordable against every record
  even pessimistically. This is the arm that has to support "nothing survived", which a sample
  cannot.
- **Broad viral denylist (3.16M clusters) — sampled, rate with an interval.** It buys an aggregate
  number, and a rate with an interval is the honest form and the project's house style.
- **The design question is already answered without any alignment.** A4.3's ceilings — filter scope
  against corpus composition, and the label coverage its rules depend on — cap what a filter of this
  design achieves whatever leaked. No pass is needed for that claim.

Neither the corpus cut nor a uniform sample is taken. D-101 returns for the broad arm only; D-104
stands for the narrow arm only. **The two arms report in different forms and must not be pooled** —
downstream consumers need telling which they are reading.

**Left, in order.** The broad arm's sampling design, which is its own decision entry and must answer
the clustering and denominator problems D-104 raised *before* the arm runs. The hit cap's cost
measured where it binds. Spot support in the launcher. Then the two passes.

**Still waiting on the project owner — and this one blocks.** The handling and reporting rules for
the narrow arm. Its scope is settled; what may be said about its output, at what granularity, and
what waits on X3.1 is not. The arm is not built until that decision exists.

## Sampling design fixed — 2026-10-16

D-109. Owner constraints: about $30 total, and a sweep rather than one setting.

**Three of the four parameters cost nothing extra.** The identity threshold comes free from banded
reporting — one search at the lowest cut emits every higher one. Coverage mode comes free by
emitting `qcov`/`tcov` and post-filtering, which turns D-107's three-way reading into three
predicates over one search. Sensitivity is the one that cannot be post-filtered, because D-105
measured that the settings are not nested, and it is the sweep worth paying for: `-s` is our
parameter, so the sweep separates a property of the filter from a property of our instrument.

**So the budget buys a 2.5% sample across three sensitivities — about 1,296 core-hours, $26** on
`c6i.2xlarge` spot, from D-104's fitted cost model and D-105's measured ratios, checked against
D-104's own full-pass endpoint.

**The two objections D-104 raised are answered in the design, not waved through.** Intervals use a
design effect from between-family variance, not binomial — at this n the binomial error is under
0.01% and is not the real uncertainty — and every rate ships with its realised family count. UniRef
and MGnify are reported separately because MGnify's granularity is unstated, so its denominator
carries a reading that must not be pooled into an exact-looking number.

**One item is unmeasured and the design is provisional on it:** relaxing coverage to allow the
post-filter admits more rows, so it raises cost and may make the hit cap bind. That folds into the
hit-cap measurement already on the list. If it costs more than three separate coverage cells, three
cells is the fallback and D-109 is superseded.

**Left, in order.** The hit-cap and relaxed-coverage cost measured together where they bind. Spot
support in the launcher. Then the broad arm's sampled pass. The narrow arm stays blocked on the
owner's handling decision.

## Instrument built, spot refused — 2026-10-16, fourth

Branch `claude/fervent-hopper-8ht0h3`.

**Built and green** (805 tests, full `check`): `src/amazebio/similarity.py` is the instrument
both remaining passes need — D-105's parameters, the three coverage readings as post-filters
over one relaxed search, identity banding, the saturation guard, and rates with D-109's
design-effect intervals. `tools/esm3_calibrate.py --measure caps` measures the two items left
open: the hit cap priced where it *binds* rather than where it is slack, and relaxed coverage
against D-109's three-cell fallback. The launcher passes the mode through and each mode writes
its own artefact name, since the corpus bucket has no `DeleteObject`.

**One finding from rehearsing the path locally against the pinned aligner.** The post-filter
and the aligner's own `--cov-mode 1` do not pick exactly the same records — 138 against 137 on
1,200 synthetic records. The post-filtered set was a strict *superset* both times, so the
approximation errs toward overstating leakage rather than understating it, which is the
defensible side. The run now measures that agreement at corpus scale instead of assuming it.
D-109's "three readings for the price of one" is therefore approximate, and the write-up has
to say by how much.

**Spot does not work in this account (D-110).** `RunInstances` with spot options is refused
with `AuthFailure.ServiceLinkedRoleCreationNotPermitted`: the request needs the
`AWSServiceRoleForEC2Spot` service-linked role, which EC2 creates via
`iam:CreateServiceLinkedRole`, and `iam:*` is denied here. A dry run authorizes the same
request, so no dry run finds this. Nothing was launched or billed. Spot support stays in the
launcher — the code is right and one IAM action makes it work.

**Left.** The cap measurement has not run: on demand it is about $1 and the launch needs the
project owner's go-ahead, since the session is not permitted to spend. Then the broad arm's
sampled pass, whose budget is now an open question rather than a settled $26.

**The budget question is answered (D-111): the spot role gets created**, so D-109's design
runs unchanged at the price it was designed against. Nothing in the repo is waiting on code.

**Blocked on one external action.** Someone with IAM permissions creating
`AWSServiceRoleForEC2Spot`, once. `iam:*` is denied here, so this project cannot check whether
it exists except by attempting a launch — which is also the launch it wants, so the attempt is
the check. On confirmation, in order: the cap and coverage measurement on spot (well under a
dollar), then the broad arm's sampled pass (about $26).

**Still waiting on the project owner: the narrow arm's handling and reporting rules**,
unchanged from the previous block and still blocking that arm. Nothing in this round touched
it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

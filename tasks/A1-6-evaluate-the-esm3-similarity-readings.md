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

**Spot does not work in this account (D-120).** `RunInstances` with spot options is refused
with `AuthFailure.ServiceLinkedRoleCreationNotPermitted`: the request needs the
`AWSServiceRoleForEC2Spot` service-linked role, which EC2 creates via
`iam:CreateServiceLinkedRole`, and `iam:*` is denied here. A dry run authorizes the same
request, so no dry run finds this. Nothing was launched or billed. Spot support stays in the
launcher — the code is right and one IAM action makes it work.

**Left.** The cap measurement has not run: on demand it is about $1 and the launch needs the
project owner's go-ahead, since the session is not permitted to spend. Then the broad arm's
sampled pass, whose budget is now an open question rather than a settled $26.

**The budget question is answered (D-121): the spot role gets created**, so D-109's design
runs unchanged at the price it was designed against. Nothing in the repo is waiting on code.

**Blocked on one external action.** Someone with IAM permissions creating
`AWSServiceRoleForEC2Spot`, once. `iam:*` is denied here, so this project cannot check whether
it exists except by attempting a launch — which is also the launch it wants, so the attempt is
the check. On confirmation, in order: the cap and coverage measurement on spot (well under a
dollar), then the broad arm's sampled pass (about $26).

**The narrow arm has moved to A1.8** (D-129). A1.6 is the broad viral denylist only, from
here on: sampled, reporting a rate with an interval. The two arms must not be pooled (D-108).

## The cap run was lost, and what came out of losing it — 2026-10-16, fifth

`i-072947a778cb59a60`, `m6i.2xlarge` spot, launched 16:48 after `r6i.2xlarge` spot capacity was
refused. It published nothing in four hours on a pass that takes 52 minutes, and terminated on
its boot-armed timer at 21:09. Cost about $0.60.

**Why is not known.** What is established: the pass never completed (the seed FASTA uploads
immediately after the first publish, and a failing upload would have raised and taken the
instance down), and the process stayed alive throughout. Beyond that, nothing — every
diagnostic channel is closed, which is now recorded in `AGENTS.md`.

**Two causes are consistent with the evidence** and the second is now the stronger. The
instance type, since all three completed passes ran on `r6i.2xlarge` and this is the only
`m6i.2xlarge` attempt — a coincidence of one. Or a degrading S3 read: `S3RangeRead` reset its
retry counter per `read()` call by design, while `self.reconnects` accumulated against no
bound, so a connection delivering one chunk and then stalling retried for ever at a read
timeout plus backoff per cycle. That needs only one bad connection and explains three prior
successes.

**Fixed either way, with tests.** A global reconnect budget bounds the degrading case
(`src/amazebio/uniref.py`; `S3RangeRead` had no tests at all before — it now has five). A
corpus-pass heartbeat to object storage makes the next occurrence diagnosable in minutes. And
`AGENTS.md` carries both findings: that a running instance cannot be observed here, and that
the boot-armed shutdown timer does fire, reported as `User initiated` rather than as a reclaim.

**The re-run is much smaller than this one was.** D-124 removed the relaxed-coverage half of
the measurement entirely, so only the hit cap remains, and it runs against a staged sample
rather than a fresh corpus pass.

## The narrow arm is unblocked — 2026-10-16, sixth

D-125. The project owner's rule, fixed before any result exists because §2 requires analysis
specs settled before results are inspected, and because an empty result and a non-empty one
would invite different rules once either was visible: **counts by survival route and homology
class, never by organism or taxon**, with per-record detail in the disclosure package only and
the preprint carrying the aggregate. Both branches are covered in advance.

Four things follow rather than being separate calls, and they are in D-125 as amended by
D-126: the exact per-record manifest is computed, kept and **staged** — aggregation happens at
the publication boundary, not the computation boundary — never committed, since the public repo
is a deliverable; A2.* and B3.* inherit the rule for their published outputs; the limit is
enforced in the harness per the non-negotiables, not left to be remembered; and nothing
circulates before X3.1.

**D-126 reverses D-125's storage sentence.** D-125 said the manifest must never be staged,
reasoning that an unwithdrawable object is a liability. That went further than the reporting
rule required and would have left a pipeline that holds nothing — breaking A3.3's independent
reimplementation and the manifest A2.* and B3.* consume. The owner's call is to stage it and
accept permanence, with the key fixed in advance as
`corpora/results/a1-6/narrow-arm/<release>/<tier>/manifest-<commit>.jsonl`; the commit is in
the key because an overwrite in this bucket destroys the earlier object irreversibly.

**Nothing on this arm now waits on the owner.** What remains is ours, in order:

1. Two decisions, each its own entry — how the published organism list's names map to taxonomy
   ids, which the list does not do for you; and which version of that list was in force when the
   filter ran, since the source cites a 2024 access date and the retrievable page is live and
   undated.
2. Build the second seed set. Validation target: 187K sequences, published in the source (D-106).
3. Score it exhaustively. Cost is linear in query count, so at 187K against 3.16M this arm is
   roughly a seventeenth of the broad arm's compute — cheap even over the whole corpus, which is
   what D-108 relied on.

## The cap measurement is complete at one target size — 2026-10-17

Instance `i-059cba6e4273c7345`, `m6i.2xlarge` spot, ~2 h, about $0.25. Six cells at shards=1;
the run ended before the second target size, so **there is no linearity check** and
`cap_summary` was never written — the cells carry everything.

Query: 31,381 seeds (1/100 by hash). Target: shard 0 of the staged sample, 417 M residues.

| cap (% of that cell's max hits/seed) | relaxed: wall / records lost | `--cov-mode 1`: wall / records lost |
|---|---|---|
| slack, 100,000 | 2,137 s / — | 1,450 s / — |
| 50% | 770 s / 0.9% | 356 s / 3.3% |
| 20% | 530 s / 2.3% | 252 s / 9.7% |

**Four findings.**

1. **The cap does not bind** at the pass's scale: 5,078 hits for the worst seed under relaxed
   coverage, ~1,445 under filtered, against 100,000. D-105's guard is satisfied and D-128 keeps
   the published value.
2. **A lower cap costs 3-4x more recall under coverage filtering than under relaxed** — 3.3%
   against 0.9% at the same fraction of the observed maximum — because the filtered search
   yields far fewer hits per seed, so truncation reaches real matches sooner. The pass uses
   filtered coverage, so the cheap-cap option is worse than the relaxed cells alone suggested.
3. **Relaxed coverage costs 1.47x filtered**, not the 9x first inferred from the relaxed cell
   against D-104's model. That refutes D-124's *cost* argument while leaving its exactness
   argument standing (D-124).
4. **Both cost about 6x D-104's model**, because the model was fitted with `--min-seq-id 0.70`
   and the pass cannot use an identity floor. This is the finding that moved the broad arm's
   price from $26 to $300-430 and then to 0.3125% for about $50 (D-128).

**The post-filter agreement check, at real scale:** 32,644 records post-filtered against 32,374
from the aligner's own `--cov-mode 1`, with 270 found only by the post-filter and **none** found
only by the aligner. A strict superset, 0.83% wide, so the approximation errs toward
overstating leakage. The local rehearsal saw 1 record in 138; this is the number to cite.

**Left.** Slice the query so a cell fits one instance run (a full cell is ~40 h), then run the
first cell of the broad arm against the staged shard.

## Preliminary results instead of an exhaustive pass — 2026-10-17

D-134. **Branch `ccr-81045ff3-7u9p0a`** carries the work.

The broad arm now runs as **nested bands on the seed axis**, reporting a lower bound. D-128's
full-seed pass is not withdrawn — it becomes band 3 and is what the accumulation curve decides on.

Why the seed axis rather than more corpus: a full cell is ~40 h, so D-128's pass needs the query
sliced, and **band counts are per corpus record — additive across shards but not across query
slices**, since a record matched by seeds in two slices would be counted twice and its band is a
max over all seeds rather than a sum. That is a new correctness argument and new machinery, built
before any result exists, to buy a rate where a bound suffices for the headline.

Sampling seeds understates leakage **monotonically** — a record is counted if any seed matches it,
so dropping seeds can only drop records and lower their best identity. Every band count is a strict
lower bound, which is the direction §2 and D-105 both point.

| Band | Seeds | Cells | Wall | Largest cell | Spot |
|---|---|---|---|---|---|
| 1 | 31,381 (1/100) | 6 | ~4.1 h, one run | ~1.6 h | ~$0.50 |
| 2 | ~315,922 (1/10) | 6 | ~41 h, six launches | ~15.8 h | ~$5 |
| 3 = D-128 | 3,159,223 (all) | 6 | ~413 h | ~40 h, needs slicing | ~$50 |

Band 2 is taken **only if** band 1's measured per-seed cost and hit-table size say it fits, per
D-132's discipline. Neither band 1 nor band 2 slices the query.

**The one external blocker is gone.** D-132 verified spot by a real launch, so D-120 and D-121 are
settled and every spot-priced figure in this task is payable.

**Reporting.** The corpus axis keeps D-109's design-effect interval; the seed axis contributes a
bound, not an interval. Figures read "at least X%, interval from the corpus sample" and never as a
point rate. Every rate ships its realised **seed**-family count as well as its corpus-family count,
because the accumulation between bands 1 and 2 is the only evidence about the gap to the full-seed
rate.

**Left, in order.** Seed-fraction support in the instrument and the launcher, with the lower-bound
qualifier carried in the artefact rather than added in prose; band 1's six cells; then band 2 if
band 1 prices it.

**Nothing waits on the project owner.**


## The instrument carries the band and the strata — 2026-10-17

Branch `ccr-81045ff3-7u9p0a`, 930 tests, full `check` green. Everything the band needs that
can be tested without an aligner is in the library.

**The seed axis** (D-134). `select_seeds` is the cap run's own hash rule, so band 1 re-runs that
query set exactly. The bands are **nested** — 100 is a multiple of 10 — so band 1's seeds are a
subset of band 2's and the difference between them is an accumulation rather than two unrelated
samples; that is pinned by a test, because the whole nested design rests on it. The band is in
the cell slug, since the corpus bucket has no `DeleteObject` and a shared name would make band 2
read as band 1; a full-seed cell keeps D-128's slug. `lower_bound` sits on the `Rate` itself and
`describe()` cannot format the number without "at least". `combine_cells` refuses to pool bands.

**The interval's sampling unit** (D-140, corrected by D-141). `rate_with_interval` had wanted a
family per corpus record since it was written and nothing produced one — the interval D-109
promised had no unit at all. Taxonomic family does variance, A2.1's registries do every published
family count. `FamilyIndex` builds the strata from the target shard, which is the only place the
misses appear; `TargetStream` counts hit records per stratum in the same pass as the bands; and
`cell_from_stream` assembles the cell, taking the denominator from the index rather than from its
caller.

**One correction worth reading** (D-141). D-140 asserted that pooling the taxonomy-unplaced
records would understate the interval. Measured, it does so by 0.2% when their rate matches the
overall one and **overstates by 10.9x** when it does not — pooling has no direction, it just makes
the interval a function of one stratum's own rate with a third of the data behind it. The
singleton treatment stands and its justification is replaced. Both claims were a minute's work to
check.

**Left, in order.** A `band` mode in `tools/esm3_calibrate.py` that runs the six cells and
publishes each one, which needs the hit table sorted by target for `TargetStream` and the seed
set's own realised family count; launcher plumbing for the mode; then band 1 — one run, ~4.1 h,
~$0.50 on spot — and band 2 only if band 1's measured per-seed cost and hit-table size say it
fits.

**Nothing waits on the project owner.**


## Band 1 is built and the launch is the only thing left — 2026-10-17

Branch `ccr-81045ff3-7u9p0a`, 940 tests, full `check` green, including a band run end to end
against the pinned aligner.

**`--measure band` is the pass.** Six cells over one staged shard, each published as it
finishes rather than at the end — a run that dies on cell five has paid for four, which is the
lesson `AGENTS.md` records from the runs that published nothing in four hours. Plumbed through
the launcher, so the mode the instance invokes is the mode that exists.

**Verified against the bucket rather than against a reading of the code.** The staged sample is
10 objects at rate 40: 8 shards and the seed set, **no sidecars**, so D-142's gap is real.
Shard 0 holds **1,097,174 clusters and 417,056,773 residues** — the cap run's target exactly,
so its 1/100-seed timings transfer without adjustment. The version-1 manifest reads cleanly
with the new optional `sidecars` field, which is what D-142 required of it.

**Three things found by building it, each now a test.**

- `Saturation` had no way to act on itself; every caller was left to remember the check D-105
  requires. It raises now, because a cap-truncated lower bound and a seed-sampled one are
  different claims and failing is the only way they cannot be confused.
- The band's functions sat below the `__main__` guard, so `main()` ran before they were defined
  and the mode was unreachable with a `NameError`. Only the end-to-end smoke test catches that.
- The upload plan is seed, shards, sidecars, so the shard loop slices by length; left
  open-ended it would have paired a sidecar with a shard index under a strict zip.

**One launch, not two.** D-142 left band 1 owing a corpus pass for the sidecars and then the
band. `shardstore.verify_rebuilt` checks the rebuilt shards against the staged manifest's own
digests before anything is searched, so the two can be one run: the band is a result about the
staged sample because the bytes are proved identical, not because the sampling rule is
deterministic and ought to agree.

**Left: the launch.** `--measure band --spot --verify-sample-against <manifest>`, about 5 hours
and roughly $0.70 — the 52-minute corpus pass for the sidecars, then band 1's six cells. The
session is not permitted to spend, so this needs the project owner's go-ahead.

**Waiting on the project owner:** authorisation to launch. Nothing in the repo waits on code.


## Band 1 is running — 2026-10-17

Instance **`i-0d81555e994423a79`**, `m6i.2xlarge` spot, 120 GB gp3, launched from commit
`ba33811`. Owner authorised the spend; about $0.70 expected.

Dry run returned `DryRunOperation` first, so the parameters and the spot path authorise. Note
what that does **not** establish, per D-120: a dry run runs no `UserData`, so the end-to-end
smoke test is what covers the script itself.

One run, two stages. The 52-minute corpus pass rebuilds the sample and its strata sidecars,
then `shardstore.verify_rebuilt` checks the rebuilt shards against the staged manifest's own
digests **before anything is searched** — if they differ the run stops having cost only the
pass. Then band 1's six cells over shard 0, each published to the results prefix as it
finishes.

Expected: about 5 hours. Boot-armed shutdown at 480 minutes, which D-127 established does fire
and is reported as `User initiated`. Watch it with `--attach i-0d81555e994423a79`.

What to look for in `band.json`: `searched_records` should be **1,097,174** and
`searched_residues` **417,056,773**, which are shard 0's figures from the staged manifest and
the cap run's target exactly. Six distinct cell slugs, all carrying `-q100`. Nine groups, each
with `lower_bound: true`.


## The validation target was never one — correction from A1.8 — 2026-10-18

D-150, raised by the A1.8 track. **A1.6 has recorded a validation target it does not have.**

The state blocks above say the reconstruction "has a validation target that works — ESM3 states
the viral denylist is roughly 4M sequences". The same paragraph of the same methods appendix says
that figure counts sequences **in UniProt**: "we identify ~4M sequences that are annotated as
viral in UniProt". A1.6 counts **UniRef100 clusters** — 3,159,223 of them. The two are different
objects, so the closeness is a coincidence of scale and not evidence of anything. Every earlier
line in this file calling the 4M a validation target is wrong and stays only as a record of the
error.

**What this does not touch.** The seed set and the band run are unaffected. The set was never an
attempt to reproduce ESM3's denylist object — it is the query set for searching the staged
corpus, built from UniRef100 because UniProtKB is not staged and because cluster members catch
material a representative-only set misses (D-092). Breadth is the conservative direction for an
audit, which is why rebuilding it from UniProtKB to match their object is refused: it would make
the audit *less* likely to find surviving material, and §2 forbids an error in that direction.

**What it costs.** Phase A loses a validation it believed it had, on both arms. No corpus-level
reconstruction here can be checked against a published size, because the only published sizes
count a different object. "The paper's only stated denylist sizes cannot validate any
corpus-level reconstruction" is itself a §A0 finding and belongs in the write-up as one.

**For the write-up, concretely:** strike any sentence offering the 4M as corroboration, and do
not replace it with a hedged version of the same comparison.

**Noted for the next worker.** D-150 makes the general point better than this file can: the
caveat was already in the code — "compared against UniRef clusters, not UniProtKB entries" — and
it was far too quiet to stop a hypothesis being built on top of it. A caveat that does not change
the number it qualifies is not a safeguard.


## Handoff — 2026-10-18

`in-progress`. **Branch `ccr-81045ff3-7u9p0a`**, 945 tests, full `check` green. Read this block,
the three above it and D-134, D-140 to D-142, D-148 and D-150, and you have the task.

**Band 1 is five-sixths published and the sixth cell is in flight.** Instance
`i-091497604cc5e805d`, resumed, writing to `band-complete.json` so `band.json` cannot be
touched. It loaded the 5 published cells at 37 s, then started the corpus pass; it skips those
five and runs only `s7.5 cov2`. **Do not relaunch it.**

**If it fails, resume from the band artefact with the most cells in it — never the newest.**
`band-complete.json` is published early in the run holding **no cells**, about two and a half
hours before the sixth one lands, because `publish()` runs before the band stage. Resuming from
it because it is newest would drop the five paid cells and rebuy all six. Open each candidate and
count `band.cells`.

**The five published cells**, all lower bounds, over 1,097,174 records, 132,473 strata, 7,366
seed families, from 1/100 of the seed set:

| | mode 0 | mode 1 | mode 2 |
|---|---|---|---|
| s2 | ≥1.5473% | ≥1.7609% | ≥1.9458% |
| s5.7 | ≥2.3624% | ≥2.9507% | ≥3.6187% |
| s7.5 | published | published | **in flight** |

The five cells are `s2 cov1`, `s2 cov2`, `s5.7 cov1`, `s5.7 cov2` and `s7.5 cov1`. Since
`SEARCH_READINGS[1] = (0, 1)`, that `s7.5 cov1` cell speaks for modes 0 **and** 1 — so **eight of
the nine groups are published** and only `s7.5 cov2` is outstanding. The `s7.5` rates are in
`band.json` and are omitted here deliberately, so that reading this table cannot substitute for
reading the artefact once the band is whole.

95% intervals are in `band.json`; the widest among the six values above is ±0.57 points. **Not a
result yet**: D-109's sensitivity sweep is the only check on whether the rate is a property of the
filter or of our aligner settings, and it is one cell short. Sensitivity moves the figure 1.5-1.9x
across the rows above, so no single number here may be quoted alone.

**Measured, and worth carrying (D-152).** The taxonomy-unplaced share is **11.8%** (129,113 of
1,097,174), not the ~36% D-140 and D-141 borrowed from A4.2, which measured a different quantity.
Both conclusions stand — D-141's point is that pooling is unstable whatever the share — but the
design effect is diluted by exactly this fraction, so the realised intervals are wider relative to
binomial than those entries implied.

**Left, in order.**

1. The sixth cell lands, then `band-complete.json` is the band. Check `searched_records` is
   1,097,174 and every cell carries `-q100`.
2. Stage the strata sidecars with `--stage-sidecars-only`, so band 2 and A1.8 do not each rebuild
   them — six launches otherwise pay the 52-minute pass for nothing. **This is its own launch and
   its own spend**, roughly $0.20: the flag needs a corpus pass to build what it uploads, so it
   cannot use `--sample-from`. It needs the owner's go-ahead like any other launch.
3. Band 2 at `--band-denominator 10` **only if** band 1's measured per-seed cost and hit-table
   size say it fits (D-134), and it is what decides whether D-128's full-seed band 3 is worth
   buying.
4. Strike the 4M validation claim from the write-up (D-150) and report the §A0 finding instead.

**Waiting on the project owner: the spend for steps 2 and 3.** Band 1 is authorised and paid for,
and the cell in flight completes it. Everything after it is a fresh launch and none is authorised.

**Coming from A1.8, unprompted and worth waiting for rather than duplicating.** Its UniProtKB
pass is counting at release **2023_02** — the release ESM3 names, which matters because UniProt
has since lost about 40% of its entries, so a current-release count would prove nothing. That
pass counts the Viruses superkingdom in the same sweep, since it reads every OX line anyway and a
separate run would mean a second 182.7 GB download. So **a viral entry count at the correct
release is on its way**, to check this arm's reading against the stated ~4M.

Two things to keep straight about what that buys. It validates the **reading** — whether "annotated
as viral in UniProt" was interpreted as they interpreted it — and **not the seed set**, which
nothing published can validate (D-150). And it does not reinstate the 4M as corroboration for the
3,159,223 UniRef100 clusters; those remain different objects.

The archive is also being staged permanently at `corpora/uniprotkb/2023_02/`, so a different viral
reading is an in-region re-read rather than another download. **Do not start a UniProtKB pass for
this arm** — it is already being paid for once.

**The measured unplaced share is D-152, not the 36% D-140 and D-141 reason from.** That entry
records why both conclusions stand anyway.


## Band 1 is complete — 2026-10-18

D-153. Six cells, nine groups, over shard 0's **1,097,174 records** from **31,381 seeds** (1/100)
and **7,366 seed families**. 132,473 strata, 129,113 of them unplaced singletons (11.8%, D-152).
Artefact: `corpora/results/a1-6/band-complete.json`. Two launches and a resume (D-148), about
$0.75 in total. `i-091497604cc5e805d` terminated.

**These are not clean lower bounds — see D-154, which corrects D-153 on exactly this.** Two
errors run in opposite directions: 1/100 of the seeds understates, and the seed set implements
only the *first* clause of ESM3's rule ("annotated as viral") and not the second ("aligns almost
exclusively to other viral sequences"), which makes it a superset of their denylist and
overstates. The net direction is not known. **Do not write "at least" in front of these figures.**
They are a measurement of the annotation-only reading.

| | any identity | **≥0.70 (charitable)** | ≥0.90 | design effect |
|---|---|---|---|---|
| s2 mode 0 | ≥1.5473% | **≥0.6537%** | 0.4996% | 557.0 |
| s2 mode 1 | ≥1.7609% | **≥0.6836%** | 0.5244% | 515.2 |
| s2 mode 2 | ≥1.9458% | **≥0.6770%** | 0.5572% | 455.0 |
| s5.7 mode 0 | ≥2.3624% | **≥0.6544%** | 0.4996% | 388.1 |
| s5.7 mode 1 | ≥2.9507% | **≥0.6844%** | 0.5244% | 331.0 |
| s5.7 mode 2 | ≥3.6187% | **≥0.6780%** | 0.5572% | 267.5 |
| s7.5 mode 0 | ≥2.5536% | **≥0.6544%** | 0.4996% | 361.6 |
| s7.5 mode 1 | ≥3.2687% | **≥0.6844%** | 0.5244% | 304.9 |
| s7.5 mode 2 | ≥4.0975% | **≥0.6780%** | 0.5572% | 238.8 |

95% intervals are in the artefact; at `s5.7 cov1` the any-identity bound is 2.3746-3.5267%.

**Read the bold column, not the first one.** The 0.70 figure spans 0.6537-0.6844% across all nine
cells — a relative spread of 4.7% — while the any-identity figure spans a factor of 2.6. The
sub-threshold tail is largely a property of our aligner settings; the quantity the charitable
reading turns on is a property of the filter. That is exactly what D-109 bought the sweep to
distinguish, and it is why a single number from this band must be the 0.70 one.

**The inferred cut falls in a trough, not through the mass.** At `s5.7 cov1` the identity
distribution is 24,865 below 0.70, then 255 / 279 / 1,221, then 5,754 at ≥0.90. So of the 7,509
records at or above the cut, 3.4% sit in the 0.70-0.75 band and 77% are near-identical matches.
D-105 separated that band because 8.07% of hit *rows* fell in it; per record it is 3.4%, which is
a measured reassurance rather than an assumption.

**Do not use a binomial interval.** Design effects run 238.8 to 557.0, so honest intervals are
15-24x binomial. D-109 argued the case expecting ~40.

**What this is not.** 0.3125% of the corpus, UniRef100 only, 1% of the seeds, MGnify90 unscored
(D-133). Not validated against any published size (D-150). Not a bound in a known direction
(D-154). And **not a statement about what the matched records are** — this band measures that they
align, not whether they are viral material or host protein that resembles it. The 77%-at-≥0.90
figure rules out distant resemblance; it does not separate a captured host gene from a viral one.
That is A2.*'s and B3.*'s question.

**The next priority is clause (b), not band 2** (D-154). Restricting the seed set to sequences
that align almost exclusively to other viral sequences changes what the numbers above *mean*;
band 2 only makes them more precise. It is a seeds-against-UniProtKB pass, and A1.8 is staging
that archive in-region, so it is affordable.


## Note for the next session — 2026-10-18

**Read in this order:** D-134, D-153, D-154, **D-156** (which corrects D-154), then this block.
D-156 is the one that changes what you do.

### Where the task is

Branch `ccr-81045ff3-7u9p0a`, 946 tests, full `check` green, nothing left on a branch that
matters — the instrument is all there. Band 1 is **complete and paid for**:
`corpora/results/a1-6/band-complete.json`, nine groups over shard 0's 1,097,174 records from
31,381 seeds (1/100). Two launches, one spot reclaim, one resume, about $0.75. No instance is
running.

### The one thing to get right before touching anything

Band 1 ran the **strict** reading's seed set (annotated-viral only) against the **charitable**
reading's 0.70 threshold, and D-153 labelled the 0.70 column "charitable". That combination is not
one of the three readings D-015 fixed. **The fix is relabelling, not recomputation** (D-156):

- the **any-identity** column is the strict reading proper, since strict removes on any detected
  hit — ≥1.5473% to ≥4.0975% across our settings, and these **are** clean lower bounds, because
  the only sampling error on that reading is the 1/100 seed sample;
- the **0.70** column is the strict seed set at the charitable threshold, which is a hybrid and
  should be named as one — 0.6537% to 0.6844%, remarkably flat across settings;
- the **charitable reading's seed set is not executable** from the published text, because clause
  (b) ("align almost exclusively to other viral sequences") carries no number and D-015 declined
  to invent one. That is a §A0 finding to report, not a gap to close.

**Do not implement clause (b)** unless the project owner asks for it as a *fourth* reading with
its own entry. An earlier version of this note told you to do it next; D-156 withdraws that.

### What is genuinely left

1. **Relabel the write-up per D-156.** No compute. This is the whole of the correction.
2. **Stage the strata sidecars** — `--stage-sidecars-only`, one launch, about $0.20. Saves every
   later band and A1.8 a 52-minute corpus pass. Needs the owner's go-ahead.
3. **A per-cell heartbeat before band 2.** The heartbeat covers the corpus pass only; a search
   cell publishes nothing until it finishes. Band 1's longest cell was a 95-minute silence in
   which a live run and a dead one are indistinguishable from outside — survivable because the
   cell is the unit, and dangerous at band 2's ~15.8-hour cells. `AGENTS.md` has the general form.
4. **Band 2** (`--band-denominator 10`) only if the owner authorises it. Its value is now the
   *seed* axis alone: the 0.70 figure is already flat across sensitivities, so what band 2 buys is
   how far the bound rises as the seed sample deepens — the only available evidence about the gap
   to a full-seed rate. Not authorised.

### Things that will bite you

- **Resume from the band artefact with the most cells, never the newest.** `band-complete.json`
  is published holding **no cells** hours before the last one lands, because `publish()` runs
  before the band stage. Open each candidate and count `band.cells`. A resumed run also needs
  `--artefact-name` pointing somewhere new, and the tool refuses the same-key case outright.
- **The watcher dies at 2 hours** in this harness, three times over in this task. The run
  survives; the launcher's `finally` termination does not. Poll object storage and terminate
  explicitly, or the boot-armed timer bills the remainder.
- **Nothing published can validate either seed set** (D-150). ESM3's stated sizes count UniProtKB
  entries; we count UniRef100 clusters. A1.8 is producing a viral entry count at release 2023_02
  which validates the *reading* only. UniProtKB 2023_02 is staged at
  `corpora/uniprotkb/2023_02/knowledgebase2023_02.tar.gz`, 182.7 GB — **do not download it again**.
- **Use the measured 11.8% unplaced share** (D-152), not A4.2's 36%, which measured something else.
- **Design effects are 239-557.** A binomial interval understates by 15-24x.

### The process lesson, three times in one task

D-150 was a caveat sitting quietly in code. D-154 was a qualifier sitting quietly in a docstring.
D-156 was a decision already recorded in `policies/specs/` that nobody re-read. Each time a number
travelled without the thing that qualified it. **Before treating a gap as work, check whether a
fixed reading already governs it** — and when you carry a seed set, artefact or figure forward,
carry its qualifier into the result, not into a note beside it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Correction from A1.8 — 2026-10-18 (D-150)

**The "~4M validates the viral seed set" claim does not hold, and this task's state block
asserts it in two places.**

ESM3's version of record, §A.6.1 p47: "we identify ∼4M sequences that are **annotated as viral
in UniProt**". That figure counts UniProtKB sequences. This task's 3,159,223 is UniRef100
clusters. The two are different objects, so their agreement is a coincidence of scale and not
evidence that the reconstruction is right — in the same way, and for the same reason, that
A1.8's select-agent set came out 5.8x its published figure.

**What is not affected.** The seed set itself, the band run in flight, and every measurement
resting on them. A1.6's seed set is a query set for searching the staged corpus, and breadth is
the conservative choice for an audit; nothing about it depends on matching the publisher's count.
D-100's other validation — 350,950,053 clusters matching the publisher's own release-note count
exactly — is a UniRef-to-UniRef comparison and stands untouched.

**What is affected.** The sentence "ESM3 states the viral denylist is roughly 4M sequences —
which is worth having because D-032 established the reported 10.6M removals cannot validate a
reconstruction" describes a validation target this task does not have. It needs removing from
the write-up and from this file's state block. The honest position is that **no published
denylist size can validate either arm's reconstruction**, because every published size is of a
different object; what can be validated is the *reading*, by executing the stated method against
UniProtKB, which is what A1.8 did for its arm (140,591 against a published 187K).

Left here for whoever resumes A1.6 rather than edited into its state block by another task.

## The viral reading, measured at the right release — 2026-10-18 (D-157)

A1.8 read all of UniProtKB 2023_02 and counted the Viruses superkingdom on the same pass, so
this arm now has the comparison it wanted. Both members matched the publisher's own entry
statistics exactly, so the read is whole.

**5,379,748 taxonomically viral UniProtKB sequences at release 2023_02**, against ESM3's stated
~4M. A 1.34x gap with a described cause: the paper's viral denylist is not "annotated as viral"
alone but sequences that *also* "align almost exclusively to other viral sequences in UniProt",
and a 26% reduction from a specificity filter is what that step is for. "Almost exclusively" is
unquantified, which is already on the open-questions list.

So this arm's **reading** checks out — the difference between our set and theirs is accounted
for by a step they describe. That is worth having, and it is the strongest statement available.

**It still does not validate the seed set,** and the correction from 2026-10-18 above stands:
3,159,223 UniRef100 clusters cannot be compared with a UniProt sequence count, so the "roughly
4M validates the reconstruction" sentence has to come out regardless. What replaces it is this:
the reading is validated against the stated method at the correct release; the seed set is a
query set and nothing published can size it.

Worth knowing for contrast: the select-agent arm does **not** come out this way. Its stated
procedure has no second step, and no reading of the regulation reproduces its published total —
1.7x over at the most conservative, 6.8x on the literal reading (D-157).

## The clause-(b) exposure, measured without implementing clause (b) — 2026-10-18

D-158. **Branch `ccr-ff660039-p1xxuf`** carries the work. `main` has only D-158 and this block.
D-158 was appended as D-157 and renumbered — A1.8 took that number and landed first; its
`Numbering:` line has the reasoning and names the two commit messages that cite the old one.

The project owner asked whether band 1's hits are unique to viruses. D-156 answers the half the
source answers — clause (b) is deliberately dropped by the strict reading, so the annotation-only
seed set is that reading's own and quantifying "almost exclusively" invents the number D-015
declined. What it left open is **how much of band 1's figure rests on seeds clause (b) would have
excluded**, and that is answerable from staged bytes without choosing a cut.

**Built and green** (13 tests, full `check` at 959 passed): `src/amazebio/exclusivity.py` reduces a
UniRef90 or UniRef50 cluster block to a verdict about the seeds it covers, and `Tally` turns rows
into the two seed-side shares D-157 fixes. `seeds.scan_parallel` is now generic over a
`BatchScanner` protocol so it drives this reduction unchanged rather than the project carrying two
copies of its ordering and back-pressure guarantees.

**Two things the next worker should not rediscover.**

- **Workers need only the viral taxid set, not the seed set.** UniRef is strictly hierarchical, so
  the cluster containing a seed also contains that seed's viral member. Emitting one row per viral
  member reaches every seed and the join happens once, afterwards, against the staged seed FASTA.
  Shipping 3.16M ids to each of seven workers would cost a few hundred megabytes per worker to
  answer the same question.
- **`UNDETERMINED` is a seed-level outcome and cannot be a cluster-level one.** A cluster with no
  placed taxid has no viral member either, so it can carry no verdict about any seed. `Tally`
  therefore counts a seed it never saw a row for, rather than dropping it — dropping it would
  shrink the denominator and flatter the share, which is the error D-157's two-denominator rule
  exists to prevent.

**Three schema facts, read from the staged bytes rather than assumed.** Both tiers carry a
`UniRef100 ID` and an `NCBI taxonomy` property on every member and representative, so each tier
joins to the seed set directly and neither needs reconstructing from the other. `member count`
**includes** the representative — a cluster reporting 3,252 has 3,251 `<member>` elements.
`uniref.xsd` is staged but settles neither point: properties are generic `type`/`value` pairs
there. This is the fourth time in this task a field would have been taken on trust.

**Left, in order.** The on-instance pass script; the launcher and its first-party import-closure
test, modelled on `tools/ec2_count.py`, which already launches this exact shape per `--tier` over
these tiers; the join step from staged rows to the two shares. Then the launch.

**Spend is authorised: about $0.10.** 62.73 GB plus 30.39 GB of compressed stream, roughly 45
minutes sequentially on one spot instance, scaled from D-100's measured full-tier pass of 118.68 GB
in 3,202.5 s on 8 vCPU with 7 parsing workers. Read from the session container instead it is 93 GB
of metered egress at the 42.5 MB/s this project has measured — slower and two orders of magnitude
dearer, so this is in-region work by `AGENTS.md`'s test.

**Nothing on this is waiting on the project owner.** The spend is authorised and the
measurement's definition is fixed, so what remains is the launcher and the pass.

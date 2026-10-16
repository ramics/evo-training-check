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


## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

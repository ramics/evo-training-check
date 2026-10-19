---
id: A1.8
title: Evaluate the narrow denylist against the ESM3-open proxy corpus
phase: A
status: review
gate: false
depends_on: [A1.4, A1.5]
blocks: []
design_ref: "§A0, §A1"
deliverable: 1
owner: claude
---

# A1.8 — Evaluate the narrow denylist against the ESM3-open proxy corpus

**Design reference:** DESIGN.md §A0, §A1 · **Deliverable 1**

## Goal

Score ESM3-open's narrow (select-agent) denylist exhaustively against every record of the
staged proxy corpus, and report the result under the handling rules the project owner fixed
in **D-125** and **D-126**.

Split out of A1.6 (D-129). A1.6 keeps the broad viral denylist, which is sampled and buys an
aggregate rate; this task carries the arm that buys the all-clear statement the audit rests
on. The two arms report in different forms and **must not be pooled** (D-108).

## Why this is its own task

D-108 settled that the pass splits by denylist rather than by corpus, because cost is linear
in the size of the query set and the two denylists differ by orders of magnitude. The expensive
arm and the high-stakes arm are not the same arm. They then diverge in method, in budget and in
what may be published, so they are two task files rather than one widened one.

## Read these first

- **D-125** — the handling and reporting rules: counts by survival route and homology class,
  **never by organism or taxon**. Per-record detail to the disclosure package only; the
  preprint carries the aggregate.
- **D-126** — the exact per-record result **is** retained and staged. Aggregation happens at
  the publication boundary, not the computation boundary. The staged key is fixed in advance:
  `corpora/results/a1-6/narrow-arm/<release>/<tier>/manifest-<commit>.jsonl`, with the commit
  in the key because an overwrite in that bucket destroys the earlier object irreversibly.
- **D-106** — the denylist's size is published: 147K non-viral plus 40K additional viral
  sequences, **187K** in total. That is the validation target for the reconstruction, in the
  way ~4M is for the broad arm's (D-100).
- **D-105, D-107, D-124** — the fixed search parameters, the three coverage readings, and why
  the three readings come from two coverage-filtered searches rather than one relaxed one.
- **D-128** — what the cap measurement found. The hit cap of 100,000 does not bind at sample
  scale but would at exhaustive scale, so this arm must check its own saturation guard rather
  than assume the broad arm's finding carries over.

## Steps

- **Decide how the published organism list's names map to NCBI taxonomy ids**, and record it as
  a decision entry. The list does not do this for you, and the mapping is a reading rather than
  a fact — synonyms, reclassifications and strain-level entries all have to be resolved
  somehow, and whatever is chosen becomes part of the reconstruction's provenance.
- **Decide which version of that list was in force when the filter ran**, and record it. The
  source cites a 2024 access date; the retrievable page is live and undated. Under-specification
  is data (§A0), so the gap is a finding and not an obstacle.
- Rebuild the seed set from UniProt annotation at the pinned release, reconciling against the
  published 187K.
- Score it against every record of the staged proxy corpus, using the staged sample
  machinery where it helps (`src/amazebio/shardstore.py`) and the instrument in
  `src/amazebio/similarity.py`.
- Report per D-125: counts by survival route and homology class, with the proxy qualifier A1.1
  requires on every ESM3 result, and nothing finer.

## Done when

- The seed-set reconstruction is pinned, checksummed, and reconciled against the published
  187K, with both decisions above recorded. The reconciliation runs against a full-tier pass,
  not against the sample — a seed set rebuilt from 2.5% of the corpus cannot be compared with a
  published total.
- The staged 2.5% sample is scored in full, with the saturation guard checked at this arm's own
  query scale and reported (**D-133**: the exhaustive scope D-108 fixed is withdrawn, and with it
  the all-clear this arm was built to support).
- The result ships as a rate with its interval and its realised family count, carrying an
  explicit statement that no all-clear is made, enforced in the harness.
- The per-record manifest exists at the key D-126 fixes, covering the records scored, and the
  published output is the aggregate only.
- A `run.json` manifest pins inputs, outputs, parameters, aligner version and seed.

## Cost

**Superseded by D-133 — this section priced dollars and not wall clock, and wall clock was the
binding constraint.** The exhaustive pass is about $272 and about 1,700 instance-hours, and the
account's policy ceiling is eight vCPU, so it is seventy days on one instance or seventy to a
hundred one-shot unobservable launches. The arm is now a sampled pass against the staged 2.5%
sample: about $3 and one launch. The reasoning below stands as the cost model; its conclusion
does not.

Cheap, and that is why D-108 could afford to make it exhaustive. Cost is linear in query count,
so at 187K seeds against the broad arm's 3,159,223 this arm is roughly **a seventeenth** of the
broad arm's compute for the same corpus. The measured per-query cost to plan against is
**0.37 core-seconds per seed per 417 M residues of target** (A1.6, 2026-10-17) — and note that
D-104's cost model under-predicts by about 6x because it was fitted with an identity floor the
pass cannot use (D-128).

## What this task must not do

- **Publish anything by organism or taxon** (D-125). The restriction travels to every
  downstream consumer: A2.* and B3.* inherit it for their published outputs.
- **Commit the per-record manifest.** The public repo is deliverable 7.
- **Circulate anything before X3.1**, the aggregate included (§4).
- **Pool its output with A1.6's rate** (D-108). Downstream consumers need telling which they
  are reading — and now that both arms report rates, telling them apart matters more, not less.
- **State or imply that nothing on the narrow denylist survived** (D-133). The pass is sampled;
  a sample with no surviving material is evidence of a low rate and not of absence, and the error
  runs in the direction that flatters the safeguard.

## State — 2026-10-17

`ready`, unassigned, nothing started. Nothing on this task waits on the project owner: the
handling rules exist (D-125, D-126) and its two open questions are the worker's to decide and
record.

**The instrument is on `main`,** as of PR #20 on 2026-10-17: `src/amazebio/similarity.py`
(fixed parameters, the three coverage readings, identity banding, the saturation guard, rates
with design-effect intervals), `src/amazebio/shardstore.py` (staged, checksummed corpus
samples), `tools/esm3_calibrate.py` and `tools/ec2_similarity.py`. Build on them rather than a
second copy.

**A staged sample exists, and it is *not* this task's target.** A 2.5% hash sample of
UniRef100 2023_02 sits at
`s3://amazebio-corpora-897641797669/corpora/samples/a1-6/uniref100/2023_02/rate40/`, with a
checksummed manifest, the full seed counts and the exact denominators (350,950,053 clusters,
3,159,223 viral-seeded). `--sample-from <that manifest>` skips the 52-minute corpus pass — which
makes it the right target for a **calibration** run, and the wrong one for the pass itself. This
arm is exhaustive against **every** record (D-108), because what it buys is an all-clear that a
sample cannot support. Scoring 2.5% and reporting it as exhaustive is the one mistake this note
exists to prevent; the real pass reads A1.5's staged tiers in full. And the cap and coverage behaviour is measured (D-128, and A1.6's state block): the
100,000 cap does not bind at sample scale but would at exhaustive scale, which is this task's
scale — so **check the saturation guard rather than assuming the broad arm's finding carries
over**, and note that a lower cap costs 3-4x more recall under coverage filtering than under
relaxed.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

## Claimed — 2026-10-17

`in-progress`, owner `claude`. **Branch `ccr-51fc983f-tyojje`** carries the work; `main` has
this file, the board and the decisions.

**The depth question is open and is the project owner's.** D-108 fixed this arm as exhaustive
against every corpus record, and the owner has asked for a proof-of-concept returning
preliminary results instead. That reverses a settled commitment, so it is a decision entry and
not a judgement call made mid-task — the question is being put with its priced options, and
whichever way it goes is recorded before the pass runs. Nothing below Stage 2 depends on the
answer.

**Three things are needed either way, and are being built now:**

1. The two readings this task owns, each its own decision entry — how the published organism
   list's names map to NCBI taxonomy ids, and which version of that list was in force when the
   filter ran.
2. The narrow seed-set builder, reusing `src/amazebio/seeds.py` rather than a second copy. The
   narrow list is 147K non-viral plus 40K viral (D-106), so the existing viral seed FASTA covers
   at most a fifth of it and a fresh taxid-set pass is unavoidable.
3. One in-region full-tier pass to build that seed set and reconcile it against the published
   187K. About 52 minutes and well under a dollar; the depth decision does not change it,
   because a seed set reconstructed from a corpus sample cannot be reconciled against a
   published total.

**The depth is answered: D-133.** The proof-of-concept *is* the deliverable, not a stage before
an exhaustive pass. The arm scores the staged 2.5% sample of UniRef100, one shard first as a
smoke test — about $3 and one launch of roughly nineteen hours, against $272 and seventy to a
hundred launches at the account's eight-vCPU ceiling. D-108's exhaustive scope is withdrawn and
so is the all-clear: this arm reports a rate with an interval and Phase A does not say that
nothing on the narrow denylist survived.

**Waiting on the project owner:** nothing. Two things for the owner to know rather than decide,
both in D-133. The error now runs in the direction that flatters the safeguard — a survivor
outside the sampled 2.5% is one this audit does not see, which §2 treats as the same class of
failure as overstating leakage. And the sample is UniRef100 only, so MGnify90 is scored by
neither arm; that gap is older than this decision but D-108's "every corpus record" was the one
place in the plan that would have closed it.

**Plan, in order.** Steps 1 and 2 are done; 3 onwards remain.

1. ~~The two readings, each its own decision entry.~~ **Done — D-137 and D-138.**
2. ~~The list reconstructed as taxa.~~ **Done** — `src/amazebio/selectagents.py`,
   `policies/specs/select-agents-2024-06-01.json`, the three pinned CFR captures and
   `tests/test_selectagents.py`, on the branch. Full `check` green, 926 passed.
3. ~~Settle the naming of the shared seed machinery.~~ **Done — D-139.** The counters are
   renamed denylist-neutral (`viral` to `denylist_taxids`, `viral_seeded` to `seeded`, and so
   on), A1.6's call sites updated in the same commit. The serialised keys accept both spellings,
   because the staged sample manifest carries the old one and cannot be rewritten.
4. The narrow seed-set builder itself: scan the staged UniRef100 tier for clusters whose members
   carry the taxa D-137 names, reusing `seeds.ScanConfig` rather than a second copy.
5. One in-region full-tier pass to build the seed set and reconcile against the published 187K.
   ~1 h, well under a dollar. Needed under any depth: a seed set rebuilt from a corpus sample
   cannot be reconciled against a published total.
6. One shard as a smoke test, then the 2.5% sample. ~$3 (D-133).
7. The aggregate, with its interval, its realised family count and the no-all-clear statement.

**What step 4 will have to reconcile against, and the gap to expect.** The literal reading names
53 taxa expanding to 114,206, and 16 of the 70 list entries contribute no taxon at all — nine
toxins, two constructs, one functional predicate, four absent from the pinned taxonomy. So the
reconstruction is not expected to land on 187K exactly, and the direction of each discrepancy is
recorded in D-137 rather than reverse-engineered later. Three entries are deliberately
over-inclusive, which overstates the denylist; the 16 non-contributing entries understate it.

## In flight — 2026-10-17, second

Steps 1 to 4 are done and on the branch; the full-tier seed pass is running.

**Built and green** (full `check`, 959 tests): the list reconstruction
(`src/amazebio/selectagents.py`, `policies/specs/select-agents-2024-06-01.json`, three pinned
CFR captures), the denylist-neutral rename of the shared seed machinery (D-139), the seed
builder (`tools/select_agent_seeds.py`) and its launcher
(`tools/ec2_select_agent_seeds.py`).

**What the reading comes to, under the literal reading.** 70 list entries, one-to-one with the
regulation; 53 name a taxon, expanding to 114,206; 17 contribute none — nine toxins, two
constructs, one functional predicate, one heading, four absent from the pinned taxonomy — of
which 16 are agents the seed set cannot speak for at all. The toxin-producer reading is a
switch, not a rebuild, and takes it to 62 named and 125,008 expanded.

**Two things the next worker should not rediscover.**

*The staged sample's manifest is readable under the rename, and it had to be made so
deliberately.* It carries `viral_seeded` in its `seed_counts`, it is the input the sampled pass
reads, and the corpus bucket has no `DeleteObject`. `ShardManifest.from_json` refuses any
manifest version it does not recognise — by design, so it never guesses which fields still mean
what they did — so bumping the version would have refused exactly that object. Both spellings
are accepted instead. Verified against the real staged manifest, not a fixture.

*D-133's cost arithmetic is confirmed rather than merely scaled.* It projected 133.4 G residues
for UniRef100 by scaling shard 0; the staged manifest's own measured figure is 133.49 G, so the
seventy-days-on-one-instance figure that withdrew the exhaustive scope stands on a measurement.

**Launch notes, which cost a round trip each.** `r6i.2xlarge` spot was refused for
`InsufficientInstanceCapacity`, exactly as A1.6 saw; `m6i.2xlarge` is the fallback and this pass
has no search, so the memory-heavy family A1.6 needed for in-memory target shards is not needed
here. And the payload upload sat above the `--dry-run` branch, so a dry run wrote a permanent
object before changing nothing — fixed, with a regression test.

**The check that is worth keeping.** The payload carries four data files the first-party import
closure is structurally blind to, so the launcher asks the tool which files it reads rather than
keeping its own list, and `UserData` runs `--check-inputs` on the instance before the pass. Both
were validated by extracting the tarball to a bare directory and resolving the taxa from the
shipped files alone.

**Left:** the pass to finish and reconcile against the published 187K; then one shard as a smoke
test and the 2.5% sample (D-133); then the aggregate with its interval, realised family count
and the statement that no all-clear is made.

## State — 2026-10-17, third

`in-progress`, owner `claude`. **Branch `ccr-44355df9-hi20t9`** now carries the work (it
continues `ccr-51fc983f-tyojje`, which it contains); `main` has this file, the board and the
decisions.

**The seed pass finished, and it does not reconcile — for one measurable reason.** 1,079,124
seeded clusters of 350,950,053, read from the whole staged UniRef100 2023_02 tier in 54 minutes
from commit `b00640f`. That is 5.8x the published 187K, and **D-146** traces essentially all of
it to a single list entry: avian influenza reads onto Influenza A entire, 112,716 of the 114,467
expanded taxa. The other 52 taxon-naming entries contribute about 1,750 between them.

**D-133's budget is wrong by about 34x and the correction is in D-146.** It assumed 187K seeds
where there are 1,079,124, and it costed one search where the pass runs six cells per shard.
The full 2.5% sample is about 1,135 instance-hours and $180, not one launch of nineteen hours.
Its *comparison* with the exhaustive pass stands — both sides were costed the same way — but
nothing should be planned against its absolute figure.

**The owner's call (D-146): keep D-137's reading, measure the split, report two strata.** The
primary result is the seed set without the influenza entry's exclusively-claimed clusters, which
is what the scoring pass is sized against; influenza is reported separately and named.

**Done since.** `selectagents.expand_by_entry`, `seeds.Attribution` and `seeds.EntryCounts` give
the pass a per-entry decomposition, off by default so A1.6's single-entry viral arm pays nothing
for it. A test asserts the per-entry expansion unions to the pooled one exactly under all three
readings. `reconcile` now names the largest contributor from the measurement rather than from the
source. Full `check` green, 984 passed.

**And a provenance gap closed.** `repro.run` writes its manifest on block exit, so the upload
inside that block had no file to send: the first pass staged its results and left its `run.json`
on an instance that terminated. Fixed, with a test. The first pass is traceable only via its code
tarball key, which is why the re-run supersedes it at the same keys.

**In flight.** The attributed re-run is on `i-0425941a33e981a94` (m6i.2xlarge spot, launched
22:2x UTC, about an hour, commit `5cd5e07`). `r6i` spot is still refused for capacity, as A1.6
and the first pass both saw.

**Left.** The attributed counts, and the primary-stratum figure they produce; then the scoring
pass, which needs sizing against that figure rather than against D-133's; then the aggregate with
its interval, realised family count and the statement that no all-clear is made.

**Note for whoever sizes the scoring pass.** A1.6's band mode — the machinery this arm needs — is
on branch `ccr-81045ff3-7u9p0a` and is not merged. It is hardwired to the viral seed set, so this
arm needs it to take a seed FASTA. Do not write a second copy.
*(Superseded 2026-10-18: that branch merged to `main` in PR #22. See the correction at the end of
this file — the band mode is in `src/amazebio/similarity.py` on `main`.)*

**Waiting on the project owner:** nothing.

## State — 2026-10-18

`in-progress`, owner `claude`. Branch `ccr-44355df9-hi20t9`.

**The attributed re-run is done and it overturned D-146's headline.** 1,079,124 seeded clusters,
reproducing the first pass exactly, now decomposed per list entry with a `run.json` that actually
leaves the instance. By clusters the set is broad-based — *Burkholderia pseudomallei* 30.7%,
avian influenza 25.4%, *Ralstonia solanacearum* 14.7%, top five 82% — not the single-entry
concentration the taxon counts suggested. Taxon count is not cluster count.

**The reconciliation gap is closed, and not by any reading.** D-150: ESM3's 187K counts
UniProtKB sequences and this arm counts UniRef100 clusters. Executing their stated method against
UniProtKB gives 140,591 against the published 187,000. The seed set stands as the query set; the
reconciliation target is what was wrong.

**The strain-descent hypothesis was withdrawn before its launch was spent** — the methods
appendix names the database, and the owner asked whether the published material answered the
question before a pass was run on a guess fitted to the gap.

**Done.** Per-entry attribution (`selectagents.expand_by_entry`, `seeds.Attribution`,
`seeds.EntryCounts`), the manifest upload fix, and a watcher that no longer reads a previous
run's artefacts as this run's completion — it terminated a relaunch ninety seconds in and printed
the stale reconciliation as if it were new. Full `check` green, 986 passed.

**Left.** `reconcile` to compare against the UniProtKB-level count per D-150 rather than the raw
187K. Then the scoring pass: size it against this seed set and the six-cell grid, not against
D-133's withdrawn arithmetic. Then the aggregate with its interval, realised family count and the
statement that no all-clear is made.

**Note for whoever sizes the scoring pass.** A1.6's band mode is on branch
`ccr-81045ff3-7u9p0a`, unmerged, and hardwired to the viral seed set. Do not write a second copy.
*(Superseded 2026-10-18: merged to `main` in PR #22. See the correction at the end of this file.)*

**Waiting on the project owner:** nothing.

## State — 2026-10-18, second

`in-progress`, owner `claude`. Branch `ccr-44355df9-hi20t9`.

**The reading is now checked against the release ESM3 names, and it does not reproduce their
total.** UniProtKB 2023_02 read end to end from the staged archive: 249,877,975 entries, both
members matching the publisher's release statistics exactly. Select agents **1,277,073** against
a published 187,000 — and the per-taxid detail brackets every reading we can construct:
1,277,073 with strain descent, 321,669 named organisms only, 229,787 excluding avian influenza.
All of them above 187,000. **D-157** has the reasoning and the contrast with the viral arm,
which *does* reconcile because the paper describes a second filtering step for it and none for
this one.

**Also staged, permanently:** `corpora/uniprotkb/2023_02/knowledgebase2023_02.tar.gz`,
182,691,908,438 bytes, checksummed in the stream. A different reading is now an in-region
re-read rather than another 182.7 GB.

**Three faults found and fixed, all of which produced plausible numbers rather than errors.**
The `UserData` precheck loaded the shipped tool without registering it in `sys.modules`, so it
died on the tool's first dataclass and reported it as a short payload; the fix is a test that
runs the precheck verbatim against the extracted payload. The count read the staged archive
through `S3RandomRead`, one ranged GET per block, 3.9 MB/s against 128 MB/s streaming — a
2.6-hour pass on course for fifteen. And `scan_chunks` was called once per block, discarding
the remainder that stitches records across boundaries, losing 126 entries of 249,308,459 —
caught only by the integrity gate, which is the whole reason it exists.

**Left.** The scoring pass: size it against the UniRef100 query set and the six-cell grid, not
D-133's withdrawn arithmetic. Then the aggregate with its interval, realised family count and
the statement that no all-clear is made.

**Note for whoever sizes it.** A1.6's band mode is on branch `ccr-81045ff3-7u9p0a`, unmerged,
and hardwired to the viral seed set. Do not write a second copy.
*(Superseded 2026-10-18: merged to `main` in PR #22. See the correction at the end of this file.)*

**Waiting on the project owner:** nothing.

## Band 1 result — 2026-10-18

**Complete: six cells, nine groups, shard 0, band 1/100.** Artefact at
`corpora/results/a1-8/band-select-agent.json`, written by `c027951` on `i-0cd905307d15249ff`.
10,769 seeds of 1,079,124 (1/100 hash), **34 seed families**, against 1,097,174 records in
132,473 strata (11.8% unplaced, matching A1.6's D-152 figure on an independently rebuilt shard).

**At the charitable reading's 0.70 cut the figure is 0.8362% to 0.9135%,** and the structure of
that range is the result:

| coverage reading | ≥0.70, across all three sensitivities |
|---|---|
| mode 0 | 0.8362% – 0.8362% |
| mode 1 | 0.9133% – 0.9135% |
| mode 2 | 0.9084% – 0.9086% |

**Sensitivity changes nothing.** Within a coverage reading, moving `-s` from 2.0 to 7.5 moves
the banded figure by at most 0.03% relative — identical to four decimal places at mode 0. The
whole 9.2% spread is the three readings of ESM3's coverage description (D-107), which is a
property of the source text rather than of our instrument. Meanwhile the any-identity figure
runs 13.0186% to 25.5524%, a factor of 1.96. So D-153's finding reproduces on a different
denylist: the sub-threshold tail is our aligner's reach, and the quantity the charitable
reading turns on is not.

**The caveat that outweighs the number, and it differs from the viral arm's.** Of the 10,023
records at ≥0.70 (s5.7 mode 1), **32.9% sit in 0.70-0.75** and 23.2% at ≥0.90. D-153 measured
the opposite for viral — 3.4% and 77% — and concluded the result "does not balance on the
inferred threshold as much as feared". **This one does.** The threshold is unpublished (D-107);
0.70 is our inference from the source, not their number. A third of this arm's matches sit in
the band immediately above it, so the figure is materially more sensitive to that unknown than
A1.6's is, and that travels with every quotation of it.

**The banded figure has no interval, and should.** The artefact's interval is on the
any-identity rate (s5.7 mode 1: 23.80%, 95% CI 21.72%-25.89%, design effect **685**). The
≥0.70 figure is a band count with no interval attached, because the family-level detail is
kept for the any-identity rate. "Uncertainty travels with the estimate" is a non-negotiable, so
the headline cannot ship this way: it needs the interval recomputed over families restricted to
≥0.70 matches, which the staged per-cell `seed-hits-*.tsv.gz` sidecars can supply without
re-running anything. **That is the next piece of work, before any figure is quoted.**

A design effect of 685 is the 34 families made quantitative: matches cluster hard within few
families, so the effective sample is far smaller than 1,097,174 suggests. Widening to more
shards adds corpus and not families, and will not fix it.

**Labelling defect in this artefact.** It carries `lower_bound: true` and no `net_direction`,
because the instance ran a commit predating the fix. Per **D-159** that flag may not be read as
a claim about this result: sampling understates, the query set overstates by a measured 1.7x to
6.8x (D-157), and the net direction is not established. `b96a678` makes `"at least"` render only
when a caller asserts a direction; a re-run would relabel, but the numbers are unaffected and a
re-run for a flag is not worth 2.3 hours. **Read this artefact with D-159 beside it.**

**Not yet compared with A1.6's 0.6537%-0.6844%.** Same shard, same six cells, same instrument —
but different denylists of different and unquantified relative breadth. The comparison needs an
argument, not a subtraction.

## Correction — 2026-10-18, repo audit

**A1.6's band mode is on `main`. It is not on a branch, and the three notes above saying
otherwise are wrong.** Branch `ccr-81045ff3-7u9p0a` merged via PR #22 and is an ancestor of
`main`; the band machinery is in `src/amazebio/similarity.py` (`IDENTITY_BAND_EDGES`,
`SEED_BANDS`, `band_of`, `band_labels`), with its launcher at `tools/ec2_similarity.py`.

Those notes exist to stop a second copy being written. Left uncorrected they cause exactly that,
because the next worker looks on a branch, finds work that has already landed, and concludes it
has to be rebuilt. **Size the scoring pass against `main`.**

What still holds from them: the band mode was hardwired to the viral seed set, so this arm needs
it to take a seed FASTA. Check that against `main` before planning the change — it is the one
substantive claim in those notes, and it is the part worth re-reading the code for.

## Exact matches — 2026-10-19

The 0.90-1.00 band could not distinguish a distant relative of listed material from the
material itself, so the top band was cut finer and band 1 re-run. Artefact:
`corpora/results/a1-8/band-select-agent-fine.json`, commit `34e989f`, instance
`i-0052370935f5d73d4`. Six cells, nine groups, same shard and band as before; every figure
below reproduced the earlier run exactly, including the ≥0.70 rates to four decimal places.

| identity | records | share of 1,097,174 searched |
|---|---|---|
| 0.90-0.95 | 1,122 - 1,179 | 0.1023% - 0.1075% |
| 0.95-0.98 | 753 - 807 | 0.0686% - 0.0736% |
| 0.98-0.99 | 150 - 170 | 0.0137% - 0.0155% |
| 0.99-1.00 | 87 - 112 | 0.0079% - 0.0102% |
| **1.00 exact** | **115 - 128** | **0.0105% - 0.0117%** |

Ranges are across the three coverage readings. **Sensitivity changes nothing**: the counts are
identical at `-s 2.0`, `5.7` and `7.5` in every column, so these are not an artefact of how
hard the aligner was asked to look.

**Why this matters more than the 0.9%.** Every figure in this arm so far has rested on the
0.70 cut, which is *our* inference — the source does not state its threshold (D-107) — and
32.9% of the ≥0.70 matches sit in the band immediately above it. **An exact match needs no
threshold argument.** Whatever value the filter actually used, 1.00 is above it, so these
records are not sensitive to the one parameter this arm could not pin down.

**What may be said, and what may not.** The supportable statement is: *material identical to
sequences from organisms named on the Select Agents and Toxins List is present in the sampled
proxy corpus, in roughly 0.011% of records.* It may **not** be said that the filter missed
them: D-159's broadening term is unchanged, and this arm's query set exceeds the published
denylist by a measured 1.7x to 6.8x (D-157), so whether any given record was in ESM3's
denylist is a per-record question for the disclosure package (D-125, D-126). Nor may these be
scaled to the corpus: one shard of eight, one seed band of a hundred, and the sampling
interacts.

**This does not replace the ≥0.70 headline and does not carry an interval either.** It is a
count in a band, subject to the same gap recorded above — the interval work over families
restricted to the band is still owed before any figure is quoted.

`FINE_TOP_EDGES` is reported alongside the frozen `IDENTITY_BAND_EDGES` and does not change
them; `metrics/survival.md` is untouched.

## Intervals — 2026-10-19

The owed interval work is done (**D-178**). Artefact
`corpora/results/a1-8/band-select-agent-intervals.json`, commit `a9e369a`, six cells, nine
groups, shard 0, band 1/100. Every earlier figure reproduced exactly for the third time.

| reading | ≥0.70 | 95% CI | deff | exact 1.00 | 95% CI |
|---|---|---|---|---|---|
| mode 0 | 0.8362% | 0.2978 – 1.3747% | 999 | 0.01048% | 0 – 0.02486% |
| mode 1 | 0.9135% | 0.3526 – 1.4745% | 993 | 0.01130% | 0 – 0.02606% |
| mode 2 | 0.9086% | 0.3488 – 1.4685% | 994 | 0.01167% | 0 – 0.02762% |

**The exact-match interval includes zero**, so D-178 splits the claim: the *count* of 115-128
records at identity 1.00 is an observation and stands; the *rate* may not be generalised to
the corpus. The ≥0.70 interval excludes zero but spans a factor of 4.9 and may never be
quoted as "about 0.9%" without it.

**Do not buy more shards expecting tighter intervals.** The variance is between families and
shard 0 already holds all 34; more corpus adds records, not families. Only a wider seed band
adds families, and whether it adds many is unknown — 34 come from 53 named taxa.

**Every Done-when criterion is now met except the two that were never this task's to close.**
The seed set is pinned, checksummed and reconciled at the release ESM3 names (D-157); the
sample is scored with the saturation guard checked; the result ships as rates with intervals
and a realised family count; the per-record manifest and the no-all-clear statement are in
place; `run.json` manifests pin every pass. What remains is the comparison with A1.6's band,
which needs an argument about relative denylist breadth rather than a subtraction, and the
disclosure-package question of which specific records were in ESM3's denylist.

## At review — 2026-10-19

**PR #24**, branch `ccr-44355df9-hi20t9`. `pixi run -e dev check` green at 1,266 passed.

Everything from the seed set through the scored band with intervals is in it, with the
decisions it rests on already on `main`: D-137, D-138, D-139, D-146, D-150, D-157, D-159,
D-162, D-178.

**Not claimed by this task, and left for whoever takes it further.** The comparison against
A1.6's band needs an argument about relative denylist breadth rather than a subtraction — same
shard, same six cells, same instrument, different denylists of unquantified relative size. And
which specific records were in ESM3's denylist is a per-record question for the disclosure
package (D-125, D-126), not for this arm.

**One piece of shared infrastructure nobody owns.** The shard strata sidecars are still not
staged, so every band run pays a 52-minute corpus pass to rebuild them. A1.8 paid it four
times on 2026-10-19. `--stage-sidecars-only` exists for it; A1.8 did not use it because it
writes into A1.6's sample prefix.

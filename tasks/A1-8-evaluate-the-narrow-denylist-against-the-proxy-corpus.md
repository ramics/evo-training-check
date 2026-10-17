---
id: A1.8
title: Evaluate the narrow denylist against the ESM3-open proxy corpus
phase: A
status: ready
gate: false
depends_on: [A1.4, A1.5]
blocks: []
design_ref: "§A0, §A1"
deliverable: 1
owner: unassigned
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
  187K, with both decisions above recorded.
- Every corpus record is scored, with the saturation guard checked and reported.
- The per-record manifest exists at the key D-126 fixes, and the published output is the
  aggregate only.
- A `run.json` manifest pins inputs, outputs, parameters, aligner version and seed.

## Cost

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
  are reading.

## State — 2026-10-17

`ready`, unassigned, nothing started. Nothing on this task waits on the project owner: the
handling rules exist (D-125, D-126) and its two open questions are the worker's to decide and
record.

**The instrument is on `main`,** as of PR #20 on 2026-10-17: `src/amazebio/similarity.py`
(fixed parameters, the three coverage readings, identity banding, the saturation guard, rates
with design-effect intervals), `src/amazebio/shardstore.py` (staged, checksummed corpus
samples), `tools/esm3_calibrate.py` and `tools/ec2_similarity.py`. Build on them rather than a
second copy.

**Two things already paid for that this task should not pay again.** A staged 2.5% sample of
UniRef100 2023_02 sits at
`s3://amazebio-corpora-897641797669/corpora/samples/a1-6/uniref100/2023_02/rate40/`, with a
checksummed manifest, the full seed counts and the exact denominators (350,950,053 clusters,
3,159,223 viral-seeded). `--sample-from <that manifest>` skips the 52-minute corpus pass
entirely. And the cap and coverage behaviour is measured (D-128, and A1.6's state block): the
100,000 cap does not bind at sample scale but would at exhaustive scale, which is this task's
scale — so **check the saturation guard rather than assuming the broad arm's finding carries
over**, and note that a lower cap costs 3-4x more recall under coverage filtering than under
relaxed.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

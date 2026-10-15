---
id: B2.1
title: Ingest the benchmark DMS set with standard splits
phase: B
status: done
gate: false
depends_on: []
blocks: [B2.2]
design_ref: "§B2"
deliverable: 2
owner: claude
---

# B2.1 — Ingest the benchmark DMS set with standard splits

**Design reference:** DESIGN.md §B2 · **Deliverable 2**

## Goal

Load the published benchmark assay collection at the stated version, using its standard splits
and metric so results stay comparable to the public leaderboard.

## Steps

- Acquire the benchmark at the stated version; pin checksums.
- Use the standard splits and the standard rank-correlation metric; do not invent either.
- Carry taxon labels through into the analysis schema.
- Reproduce one published leaderboard number as an ingest sanity check.

## Done when

- Benchmark ingested, version-pinned, with standard splits intact.
- One published number reproduced end-to-end.
- Taxon labels available to B5 analyses.

## State — 2026-10-15 — DONE

Merged in ramics/amazebio#5. CI green.

**What is pinned.** ProteinGym v1.3 at `data/proteingym/v1.3/`: 217 substitution assays,
2,465,767 variants, taxon labels Virus 31 / Prokaryote 50 / Human 96 / Eukaryote 40. Five files,
each with a recorded SHA-256; `tools/stage_proteingym.py --verify` re-checks them against the pin
in `amazebio.proteingym.RELEASE` and refuses to proceed on a mismatch.

**The ingest check went further than the Done-when criterion.** Rather than one published
leaderboard number, `tools/proteingym_check.py` recomputes the published per-assay Spearman for
every assay and for two models:

| Model | Agreeing | Max deviation | Mean deviation |
|---|---|---|---|
| ESM-2 650M | 217/217 | 0.0005 | 0.000246 |
| Site-Independent | 217/217 | 0.000491 | 0.000253 |

Judged at the three decimals the published file carries; the deviations are what rounding alone
produces. That validates the variant list, the join and the metric's tie handling together, and
it is the evidence behind D-037's choice to implement Spearman in the standard library rather
than adding scipy. `Site-Independent` is the non-neural baseline §B4 requires, so B4.2 already
has a published comparison.

**Decisions.** D-037 the metric; D-038 what "standard splits" means where there is no training
step; D-039 the leaderboard's headline average is not reproduced and is not the mean of the
per-assay values; D-040 the pin is ours because the publisher ships none, and two files carry no
version at all.

**For B2.2 and B4.2:**

- Four of the five Tier 1 protein checkpoints are already on the published leaderboard with
  per-assay values — ESM-2 650M and 3B, ESM3-open, ESM-C 600M and 300M — so B4.2 has a published
  comparison for each without scoring anything. Evo 2 is absent, as expected of a nucleotide
  model.
- The viral subset is 31 of 217 assays. That is the small-n threat §B2 names, and the number
  B2.2's extension collection has to improve on.
- Size downloads from `content-length`, not documentation: the documented archive sizes are
  1.0GB and 4.4GB against 43MB and 1.91GB served (D-040).
- A full pass over the score archive takes about six minutes single-threaded. Fine as a one-off;
  if B5 needs it repeatedly, read the one needed column by index rather than parsing all 99 per
  row.
- Archive members must be streamed, not read whole. The largest is 1.15 GB uncompressed and
  peaked over 5 GB resident before this was fixed — more than any instance size this account can
  launch.

**Left open deliberately.** The agreement tolerance sits exactly at the rounding bound of
0.0005, with an epsilon for float representation but no real headroom. If a future release
publishes more decimals, tighten it.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: B2.1
title: Ingest the benchmark DMS set with standard splits
phase: B
status: review
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

## In flight

- **Branch:** `claude/kind-hopper-1rjv3q`
- **Done:**
  - ProteinGym v1.3 staged and pinned at `data/proteingym/v1.3/`: 217 substitution assays,
    2,465,767 variants, taxon labels carried into the schema (Virus 31, Prokaryote 50,
    Human 96, Eukaryote 40). Five files, each checksummed, verified by
    `tools/stage_proteingym.py --verify`.
  - The ingest is `src/amazebio/proteingym.py`; artefacts are
    `artifacts/b2-1/release/release.json` and
    `artifacts/b2-1/leaderboard-check/check-ESM2_650M.json`, each with a `run.json`.
  - **The ingest check is stronger than this task asked for.** Rather than one leaderboard
    number, `tools/proteingym_check.py` recomputes the published per-assay Spearman for every
    assay: 217/217 agree at the three decimals the maintainers publish, max deviation 0.0005,
    mean 0.000246 — what rounding alone gives. That validates the variant list, the join and
    the metric together.
  - Four decisions: D-037 the metric is stdlib rather than adding scipy; D-038 what "standard
    splits" means with no training step; D-039 the leaderboard's headline average is not
    reproduced and is not the mean of the per-assay values; D-040 the pin is ours because the
    publisher ships no checksums, and two files carry no version at all.
- **Left:** nothing in this task's scope.
- **Waiting on the project owner:** nothing for B2.1. One judgement call is flagged for review
  rather than decided: the agreement tolerance sits exactly at the rounding bound (0.0005), so
  it has an epsilon for float representation but no real headroom. If a future release
  publishes more decimals, tighten it.
- **For whoever picks up B2.2:**
  - Four of the five Tier 1 protein checkpoints are already on the published leaderboard with
    per-assay values — ESM-2 650M and 3B, ESM3-open, ESM-C 600M and 300M — so B4.2 has a
    published comparison for each without scoring anything. Evo 2 is absent, as expected for a
    nucleotide model.
  - The viral subset is 31 of 217 assays, which is the small-n problem §B2 names. The extension
    collection is B2.2's job and this is the number it has to improve on.
  - Size downloads from `content-length`, not from the documentation: the documented archive
    sizes are 1.0GB and 4.4GB against 43MB and 1.91GB actually served (D-040).
  - A full pass over the score archive takes about six minutes, single-threaded. Fine as a
    one-off check; if B5 needs it repeatedly, read the one needed column by index rather than
    parsing all 99 per row.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

---
id: A2.2
title: Structure-based detection of surviving folds
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.2 — Structure-based detection of surviving folds

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Detect characteristic folds in the surviving corpora by structural search, catching homology
that sequence search misses.

## Steps

- Assemble and version-pin the structural reference set for the fold classes named in §A2.
- Fix score thresholds in advance and record them.
- Run structural search per manifest; emit hits in the shared schema.
- Note coverage limits where structures are unavailable for a target class.

## Done when

- Per-fold hit tables exist for every manifest.
- Thresholds fixed in advance and recorded.
- Structural coverage gaps documented as a limitation.

## State — 2026-10-18 (second session)

`in-progress`. **Branch `ccr-7a87e8bd-9ow1h1`** (the earlier branch `ccr-3db3a0c2-il11ej` is
merged into it). Decisions: D-163, D-164, D-165, D-166, D-167, **D-169**.

**The fold universe and the reference set are built; the threshold is being calibrated; no corpus
hit has been looked at.**

### Finished this session

- **The fold universe is re-derived, shipped and corrected (D-169).** D-166's identifier list was
  never written as the artefact its own decision required, so it was re-derived from the pinned
  release. The ECOD pin re-verifies exactly, and the pin is now version + sha256 rather than a URL,
  because the publisher keeps no per-version filename for the current release. Two corrections:
  the capsid fold had been selected at H-group level, which admits 867 cellular domains and 12
  cellular representatives (nucleoplasmin, peptide-N-glycanase, Cu monooxygenase, TGF-beta
  propeptide); and D-166's six RdRp family names were illustrative, missing influenza PB1,
  flavivirus NS5 and the mononegavirus, bunyavirus and coronavirus polymerases. The universe is now
  **141 reference structures** (capsid 97, RdRp 30, fusion 14) against D-166's recorded 166. The
  capsid cut was the owner's choice between three options; they took the strict one.
- **The reference database is built.** All 141 representatives fetched from RCSB and cut to ECOD's
  residue ranges, no drops, `foldseek createdb` ignoring none. `gemmi` is pinned for the cut.
  One silent bug fixed: segments of a discontinuous domain were each becoming their own chain, so
  141 domains made **152** database entries — which defeats D-167's target coverage floor, since a
  fold split into three targets lets a third of it clear a floor meant for the whole.
- **The whole path is proved end to end.** A native domain sequence recovers its own reference at
  939 bits; three shuffled decoys return nothing at all at `-e 1000`. That last figure is why the
  calibration does not rest on shuffles.
- **The heartbeat is fixed.** `tools/fold_throughput.py` used `subprocess.run(capture_output=True)`
  and so published only *between* rungs; the 32-minute CPU rung was 32 minutes of silence. Now
  `Popen` with a 60-second tick, output to files rather than pipes, and a test that fails if the
  tick is refactored out.

### Finished this session, continued

- **The threshold is fixed and recorded (D-171): 500 bits, brackets [400, 600], 3Di+AA.** 1,567
  queries, 385,185 residues, 3Di predicted once in 1h39m and both alignment modes searched
  against the same query database. At the declared cut: cellular near-fold decoys 0.8%,
  unrelated folds 0%, shuffles 0%, held-out true fold members 61.7%.
  **The decoy curve is a finding, not a diagnostic.** Real cellular proteins carrying these
  folds are detected at 56% at 100 bits, where unrelated folds and shuffles are already at 0.8%
  — seventy times apart — and the near-fold curve tracks the true-positive curve closely until
  about 160 bits. Holding them to 1% costs sensitivity (61.7% against 78.8% at 100 bits) and
  never reaches zero: 3 of 389 pass at 500 bits. That is the method working. Nucleoplasmin,
  peptide-N-glycanase and Cu monooxygenase genuinely have the jelly-roll capsid fold, so
  "carries this fold" and "is viral-derived" are different claims this instrument cannot fully
  separate. It justifies D-169's exclusions quantitatively, it is a stated write-up limitation,
  and it means the dominant false positive in the real pass will be cellular fold-carriers
  rather than chance alignments.
  A second ceiling: 13% of held-out true fold members never hit their own fold at all, even at
  20 bits. That caps what any threshold here achieves.
- **D-167's deferred 3Di-only option is closed**: 3Di+AA finds five times as many true members at
  the same false-positive target. Recorded honestly as a rule stated after seeing the sweep,
  since D-167 deferred it without fixing one.
- **A1.4's manifests are regenerated** — 7 manifests, 95 records removed for Evo 1 and 0 for
  Evo 2, 2.65M and 2.96M records unresolved.
- **The shard contract and the per-fold tables are written and tested** (`tools/detect_folds.py`,
  18 tests). A shard is keyed on (release, staged object, band) and searched **once**, with the
  three Evo 1 readings attributed from the same scores: 3Di prediction is the entire cost and a
  protein's 3Di string does not depend on which reading kept its record. Shards store every hit
  above a threshold-independent floor so the declared cut and both brackets apply at assembly.
  The family universe is the three folds; the membership rule ships separately.
- **Two corrections to D-167, both from running the chain.** `convertalis` does *not* refuse
  against a ProstT5 database in the direction D-167 chose — read literally, that entry says this
  pipeline is impossible. And foldseek silently disables `--sort-by-structure-bits` for want of
  C-alpha data, so the reported `bits` is the plain alignment score.
- **A `repro` bug fixed:** the dirty-tree refusal named files that do not exist ("ixi.lock" for
  `pixi.lock`), because porcelain's leading space on a modified-tracked line is stripped and the
  fixed `line[3:]` slice then eats a character. The old test only ever dirtied the tree with an
  untracked file, the one case the slice gets right.

### The search stage is written, and the smoke tier caught a false-null generator

- **`tools/detect_folds.py --search` is complete and resumable.** One shard at a time, published
  as it finishes, skipping what is already at the destination by listing rather than an exact-key
  probe. **No refactor was needed**: `amazebio.seqstream` already is the shared sampled-record
  reader and `profilesearch.call_genes` is already public from D-113, with stats carrying exactly
  the per-source fields the shard contract wants. The earlier claim in this file that a 250-line
  factoring was required was wrong.
- **D-172: foldseek's prefilter silently returned nothing.** 77 real called proteins against the
  141 reference structures gave `76 sequences with 0 size result lists` and exit 0; the same
  databases searched exhaustively gave 49 hits. Shipping that would have produced well-formed
  shards reporting no surviving folds anywhere in either release — a false null, manufactured.
  Every search now runs `--exhaustive-search 1`. The failure is scale-dependent (about 7% of rows
  lost at the calibration's 1,567 queries, nearly everything at 77), so the calibration alone
  could never have found it.
  **The threshold re-derives unchanged** at 500 bits with brackets [400, 600] and 3Di+AA; only
  one D-171 figure moves, and it moves favourably: the share of true fold members missed at any
  threshold is **6.1%**, not 13%. Half of that was the prefilter rather than the method.
- **The launcher is repointed.** `--stage search|throughput`, with throughput kept reachable
  because it produced D-164's cited measurement. An inputs bundle (0.25 MB) carries the reference
  database and the two artefacts the instance cannot rebuild; per-stage result and heartbeat keys;
  the watcher reports shards as they land, so a reclaim keeps what ran.
- **The free smoke tier is established and has already paid for itself twice.** `--max-records`
  bounds egress as well as time — 8 records off a 16.9 GB object in 15.5 seconds — so the whole
  pipeline rehearses against real corpus data for a fraction of a cent. It also confirmed the
  heartbeat fires through a 22-minute step, and the container CPU rate is consistent with D-163.
  A capped shard is marked `partial` and `load_shards` refuses it, so a smoke shard cannot reach
  a citable table.
- Payload: `detect_folds.py`'s import closure is seven modules wider than
  `fold_throughput.py`'s, and none were shipped — the ImportError that cost two launches. Fixed,
  and the test now parametrises over both tools rather than only the one UserData names.

### What is left, in order

1. **The paid smoke launch (~$1).** Only what needs the hardware: the NVIDIA driver, foldseek
   actually using the GPU (the tool now *refuses* a shard whose log says "no GPU devices found"
   rather than writing one that took 64x longer than its provenance claims), the instance role
   reading corpora and writing shards, the ProstT5 download, the inputs fetch, and the
   `shutdown -c` → `shutdown -h now` die path. Same capped invocation, short hard stop. It also
   returns the in-region read rate, which is worth having before committing the full spend.
2. **The full pass (~$19 at the live $0.76/h g6.xlarge spot quote).** 5 shards at the
   pre-registered depth; 24.7 instance-hours. Resumable, so a reclaim costs one shard.
   Cumulative spend is worth tracking across relaunches: the launcher enforces the ceiling per
   launch, and roughly $4 of the $30 has already gone on S3 egress.
3. **Assemble.** `--assemble` is written and tested (24 tests) and needs only the shards.

### Still open, unchanged

**The ESM3 proxy manifest is a separate, unanswered cost question.** A2.1 left it `not_searched`;
D-033 records that AlphaFoldDB and ESMAtlas were deliberately not staged and that measuring either
is A2.2's work. Its records are UniRef entries, so much of it may already have predicted structures
and need no prediction at all — which would make it the cheapest manifest here, not the dearest.

**A limitation to carry into the write-up, not a parameter.** A2.2 can never report a TM-score or
LDDT for an Evo hit — the publisher states it. The evidence is a structural-alphabet alignment
against a reference fold, not a superposition. It also partly undercuts the independence §A2 wants
from this route: the 3Di string is predicted *from sequence*.

**Waiting on the project owner:** nothing.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

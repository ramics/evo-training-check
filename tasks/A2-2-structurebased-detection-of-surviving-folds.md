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

### What is left, in order

1. **Factor A2.1's corpus reading into a module, then write the search stage.** This is the only
   thing between here and a table. The search needs A1.4 manifest reading, sampled streaming,
   gene calling and the per-object protein cache, all private to `tools/detect_profiles.py`.
   The precedent is D-113, which factored `amazebio.profilesearch` out of that same tool for
   A2.4; this is the corpus-reading half of the same move. It touches a finished task's code, so
   it wants its own decision entry — and A2.1's numbers must not move, which its own tests guard.
   **Correction to the earlier state note:** the resumability shape to copy is **A2.1's**, not
   A2.4's. `detect_profiles.py` has the real per-object checkpointing (`cache_stem` keyed on the
   *object* name, after a component-keyed stem made Evo 1's three splits collide and
   last-write-win; plus `hits_dump_path` as a second layer). A2.4 has incremental publish and an
   in-memory cache but no S3 checkpoint and no restart logic — its docstring says the pass "is
   re-run deliberately or not at all".
2. **Point `tools/ec2_folds.py` at the search tool.** It currently runs `fold_throughput.py`.
   Repointing means its `PAYLOAD` tuple, the `--help` smoke test, the run command and `watch()`'s
   result and heartbeat keys. `PAYLOAD` must carry the new tool's first-party import closure or
   the instance dies on an ImportError half a minute in; `tests/test_ec2_folds.py` enforces that.
   Simulate the bootstrap locally first — build the real payload, unpack it, run both precheck
   steps — which is the habit three lost launches paid for.
3. **Run the pass and assemble.** 5 shards at the pre-registered depth (`--plan` lists them).
   24.7 instance-hours, so it exceeds one window and needs the resumability above; the $30
   ceiling is not the binding constraint but cumulative spend across relaunches is worth tracking,
   since the launcher enforces the cap per launch.

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

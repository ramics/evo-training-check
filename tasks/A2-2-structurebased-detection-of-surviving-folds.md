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

### In flight

- **The threshold (D-170).** `tools/calibrate_folds.py` is written and its 1,567 queries are
  staged; 3Di prediction over them is running in the container. The decoy design is the substance:
  the binding class is **real proteins that share the fold and are not viral** — exactly the
  cellular capsid families and host RNAi polymerases D-166 and D-169 enumerated while excluding
  them. Unrelated X-groups and composition-matched shuffles are measured beside them, and held-out
  non-representative domains of the fold families give sensitivity. Every query takes the corpus's
  own path, amino acids through ProstT5, so the prediction error sits inside the threshold.
  This run also settles D-167's deferred 3Di-only option: 3Di is predicted once and both alignment
  modes search the same query database.
  One bias worth recording: keying RCSB's FASTA on the label chain id dropped 269 of 1,600 queries,
  and the loss was **not random** — it fell on the multi-chain picornavirus and rhinovirus capsid
  depositions, i.e. on the positive class for the largest fold. ECOD names the author id
  (`Chain D[auth 4]`); both are now registered.
- **A1.4's manifests.** Regenerating in the container (D-046), streaming the 28.1 GB. `repro`
  correctly refused the first attempt on a dirty tree.

### What is left, in order

1. **Finish the calibration and record D-170** — the declared bit score with its two bracketing
   values fixed in the same breath, and the alignment mode chosen.
2. **Make the pass resumable.** 24.7 instance-hours exceeds one window. **Correction to the
   previous state note:** the shape to copy is **A2.1's**, not A2.4's — `tools/detect_profiles.py`
   has the real per-object checkpointing (`cache_stem` keyed on the *object* name, not the
   component, after a component-keyed stem made Evo 1's three splits collide; plus
   `hits_dump_path` as a second layer). A2.4 has incremental publish and an in-memory cache but no
   S3 checkpoint and no restart logic at all — its docstring says the pass "is re-run deliberately
   or not at all".
3. **Write the search tool and point the launcher at it.** `tools/ec2_folds.py` currently runs
   `tools/fold_throughput.py`; repointing means its `PAYLOAD` tuple, the `--help` smoke test, the
   run command and `watch()`'s result/heartbeat keys. `PAYLOAD` must also carry the new tool's
   first-party import closure or the instance dies on an ImportError half a minute in, which the
   existing test enforces.
4. **Run the pass and emit the tables**, in `metrics/detections.md`'s schema with
   `detector: foldseek`, `element_kind` from the record's component per D-079 and never from the
   hit, and routes from `amazebio.apply.route_for`.

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

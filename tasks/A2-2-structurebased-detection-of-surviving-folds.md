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

## State — 2026-10-18

`in-progress`. **Branch `ccr-3db3a0c2-il11ej`** (pushed). Project management on `main` as usual.
**Method and sizing are settled; nothing has been searched, and no corpus hit has been looked
at.** Decisions: D-163, D-164, D-165, D-166, D-167.

**Why this task and not A2.3.** A2.3 reads the 2.17 TB eukaryotic component, which is not
staged: `OG2_COMPONENTS` carries it `tier1=False` with the note "Deferred to A2.3, which is the
only task that needs it", D-031 says A2.3 "must stage its own component before it can run" and
must re-ask the cost question, and D-046 puts a pass over those genomes in the in-region case. So
A2.3 opens with a standing-bill decision for the owner, not with analysis. A2.2 reads corpora
that are already staged.

### What is settled

**The cost, and it nearly killed the task (D-163).** The query side has no structures, so 3Di
must be predicted from sequence. Measured on real corpus input: ProstT5 on CPU is **18.58
core-hours per million residues, 173x A2.1's profile search**. A census is 458,800 core-hours and
even A2.1's sample depth is 6,745 — about seventy days of this container. CPU is not a slow route
here, it is no route.

**The GPU speedup, 64.48x (D-164).** One `g6.xlarge` (NVIDIA L4), both devices timed on the same
machine over identical input, both arms linear, and the instance reproduced the container's CPU
figure to within 1.7% — which is what licenses reading the CPU and GPU projections off one scale.
Artefacts and `run.json`: `corpora/results/a2-2/throughput/20261018T170641Z-9303d375d237/`.
Four launch facts verified rather than assumed, each otherwise worth a wasted launch: only
`g5.xlarge` and `g6.xlarge` authorize (**both GPU 2xlarges return `UnauthorizedOperation`**, so
the "up to 8 cores" allowance holds for CPU only); the base AL2023 AMI the other `ec2_*` tools
use has **no NVIDIA driver** while the Deep Learning base AMI is reachable via `ssm:GetParameter`;
bioconda's single foldseek 10.941cd33 build **is** CUDA-capable; and the 2.3 GB ProstT5 weights
download unauthenticated.

**The depth, pre-registered at A2.1 parity: 363 Maa = 24.7 GPU instance-hours.** Explicitly not a
census (1,682 instance-hours). Parity because A3.2 merges this table with A2.1's, A2.4's and
A2.5's, and `metrics/detections.md` forbids pooling a `lower_bound` table with a `population` one.

**The budget, $30, enforced in code (D-165).** `tools/ec2_folds.py` derives the instance's
shutdown timer from the ceiling and the live price, because that timer is the only spend control
surviving a launch (`ec2:ModifyInstanceAttribute` is denied). Prices are read, never remembered;
spot takes the worst recent zone quote; `--no-spot` demands an explicit price because
`pricing:GetProducts` is denied. The ceiling is **not** the binding constraint — it buys ~39
instance-hours against a 25-hour pass.

**The fold universe: 3 folds, 166 curated representative structures (D-166).** ECOD v295.2,
selected at **family level by enumerated identifiers, never by regex over names**. The three
measurements that forced that rule: the `jelly-roll` architecture holds 15,544 Concanavalin A
lectins and 9,881 galactose-binding domains beside 16,690 viral capsid domains; viral RdRp is
filed under topologies named for adenylyl cyclases and reverse transcriptases, and its own
English name finds only 81 birnavirus domains while missing every canonical family; and **"class
I fusion glycoprotein" has no ECOD node at all** — influenza HA2, HIV gp41, coronavirus S2 and
paramyxovirus F sit in unrelated branches, and the family name `GP41` matches a phage tail
protein as readily as HIV's envelope. Two folds borrow a curator's definition; the fusion class
is this project's own construction and ships labelled so — that is the structural coverage gap
the Done-when criterion requires. Host RNAi polymerases are excluded from RdRp deliberately:
they share the fold and are not viral-derived content.

**The search geometry and the score (D-167).** The **corpus is the query** and the reference set
is the target, because a ProstT5 database holds 3Di strings and no coordinates, so only the
structure side can be the target. This inverts AGENTS.md's "query the small side" rule — the
tool decides it — and it puts the coverage floor on the **target** (`--cov-mode 1`), since the
reference domain is the target and half the reference *fold* must be matched. The score is the
**bit score**, database-size independent and so satisfying D-076 outright. Two traps found by
testing rather than declaring: `--tmscore-threshold` can be **silently disabled** (foldseek says
so and carries on, still producing a plausible table), and `convertalis` refuses to report from a
ProstT5 database at all, even for columns needing no coordinates.

**A limitation to carry into the write-up, not a parameter.** A2.2 **can never report a TM-score
or LDDT for an Evo hit** — the publisher states it. The evidence is a structural-alphabet
alignment against a reference fold, not a superposition, which caps how strongly the fold claim
may be worded. It also partly undercuts the independence §A2 wants from this route: the 3Di
string is predicted *from sequence*, and the default alignment mode scores amino acids alongside
3Di.

### What is left, in order

1. **Calibrate the threshold's value.** Everything else about scoring is fixed; the cut is not.
   Search the reference set against shuffled or unrelated queries, pick a bit score at a stated
   false-discovery rate, and fix its **two bracketing values in the same breath**, as
   `metrics/survival.md` requires. This also decides the one deferred option: 3Di-only
   (`--alignment-type 0`) against the default 3Di+AA, which changes the score distribution and
   therefore the cut. Must happen before any corpus hit is seen; `amazebio.repro` enforces it.
2. **Regenerate A1.4's manifests.** They are not in object storage and `artifacts/` is empty in a
   fresh container, so there is currently no surviving-record set to search over. A1.4 runs in
   the session container (D-046).
3. **Make the pass survivable.** 24.7 instance-hours exceeds one instance's window, so it needs
   per-object resumability or a longer timer — A2.4 reached the same conclusion about deepening,
   so reuse that shape rather than reinvent it. Resumability is also what makes spot safe, so it
   protects the budget rather than competing with it. While there, fix the heartbeat in
   `tools/fold_throughput.py`: it publishes **between** rungs, not on an interval, so the
   32-minute CPU rung was 32 minutes of silence — half of what AGENTS.md requires, and exactly
   the condition under which silence means nothing.
4. **Build the reference set as a foldseek database.** 166 ECOD representatives fetched from
   RCSB by accession and cut to ECOD's residue ranges. Verified reachable: RCSB serves
   structures unauthenticated, and `foldseek createdb` over a directory of `.cif` files produces
   the `_ca` files the target side needs.
5. **Then the search**, emitting `metrics/detections.md`'s schema with `detector: foldseek`
   (already pinned as a valid detector string by `tests/test_survival.py`), `element_kind` from
   the record's component per D-079 and **never** from the hit, and routes from
   `amazebio.apply.route_for` rather than re-derived. Re-calling genes is expected: A2.1's called
   proteins were deliberately not persisted (D-103), and `--collect`/`--from-cache` is the
   machinery for doing it once per release instead of once per search.

### Also worth knowing

**The ESM3 proxy manifest is a separate, unanswered cost question.** A2.1 left it
`not_searched`. D-033 records that AlphaFoldDB and ESMAtlas were deliberately not staged and that
"measuring either is A2.2's work", with the cost question to be re-asked. Its records are UniRef
entries, so much of it may already have predicted structures and need no prediction at all —
which would make it the *cheapest* manifest here rather than the dearest. Settle that before
assuming it costs what the Evo corpora cost.

**Three launches were spent, none on the measurement itself**, and the lasting fix was not either
patch: a pixi URL re-derived by eye (lost the version and the `.tar.gz` suffix), then a payload
guard that failed on a *complete* payload (`module_from_spec` without registering in
`sys.modules`, so the first `@dataclass` raised). Both died in ~40 seconds through their own `die`
path with logs in object storage rather than idling away a 150-minute window. What would have
caught both for free is **simulating the instance bootstrap locally** — build the real payload,
unpack it, run both precheck steps against it — and that is now the habit to keep.

**Waiting on the project owner:** nothing. The GPU authorization and the $30 ceiling are both
answered and recorded.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

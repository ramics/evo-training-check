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

`in-progress`. **Branch `ccr-3db3a0c2-il11ej`.** Sizing settled, nothing searched yet.

Picked over A2.3 because A2.3 cannot start without a project-owner decision. The eukaryotic
component A2.3 targets is 2.17 TB and is not staged — `OG2_COMPONENTS` carries it with
`tier1=False` and the note "Deferred to A2.3, which is the only task that needs it" — and D-031
is explicit that A2.3 "must stage its own component before it can run" and that whoever picks it
up "should expect to re-ask the cost question". D-046 adds that a pass reading the eukaryotic
genomes is the in-region case. So A2.3's first move is a standing-bill question for the owner plus
an EC2 staging pass, not analysis. A2.2 reads corpora that are already staged.

**Finished: the sizing question, and it was nearly fatal (D-163).** The query side of this search
has no structures, so 3Di has to be predicted from sequence. Measured on real corpus input,
ProstT5 on CPU costs **18.58 core-hours per million residues — 173x A2.1's profile search**. A
full census is 458,800 core-hours and merely matching A2.1's sample depth is 6,745, about 70 days
of this container against a two-hour run ceiling. CPU is not a slow route to this result; it is
not a route to it.

**The project owner authorized a GPU instance**, and four things were then verified rather than
assumed, each of which would otherwise have cost a launch: `g5.xlarge` and `g6.xlarge` authorize
under `DryRun` but **both GPU 2xlarges return `UnauthorizedOperation`**, so the "up to 8 cores"
allowance holds for CPU and not for GPU; the base AL2023 AMI the other `ec2_*` tools use has no
NVIDIA driver, while the Deep Learning base AL2023 AMI is reachable through `ssm:GetParameter`;
bioconda's single foldseek 10.941cd33 build **is** CUDA-capable, established by `--gpu 1`
reporting "No GPU devices found" rather than "compiled without CUDA"; and the 2.3 GB ProstT5
GGUF downloads unauthenticated, so it is not a blocked acquisition.

**Finished: the GPU measurement (D-164).** `tools/fold_throughput.py` measures 3Di throughput and
`tools/ec2_folds.py` launches it; both are on the branch with tests. One `g6.xlarge` run (NVIDIA
L4) measured **64.48x** over CPU at the largest rung both devices ran, both arms linear, and the
instance reproduced the container's CPU figure to within 1.7% — which is what licenses reading
D-163's CPU numbers and these GPU ones off one scale. Artefacts and `run.json` at
`corpora/results/a2-2/throughput/20261018T170641Z-9303d375d237/`.

**The depth is therefore pre-registered at A2.1 parity: 363 Maa, 24.7 GPU instance-hours.** Not a
census, which is 1,682 instance-hours and about seventy days on the only GPU type the policy
permits. Parity is the target because A3.2 merges this table with A2.1's, A2.4's and A2.5's, and
`metrics/detections.md` forbids pooling a `lower_bound` table with a `population` one.

**What is left, in order.**

1. **Make the detection pass survivable.** 24.7 instance-hours exceeds one instance's window, so
   it needs a longer timer or per-object resumability — the same conclusion A2.4 reached about
   deepening, and it should reuse that shape rather than reinvent it. While doing that, fix the
   heartbeat in `fold_throughput.py`: it publishes between rungs rather than on an interval, so
   the 32-minute CPU rung was 32 minutes of silence, which is only half of what AGENTS.md
   requires and exactly the condition under which silence means nothing.
2. ~~**Fix the fold-family universe and its membership rule.**~~ **Done (D-166).** ECOD v295.2,
   selected at family level by enumerated identifiers rather than by name, giving three folds and
   **166 curated representative structures** as the reference side. The three measurements that
   set the rule: the `jelly-roll` architecture holds more lectin than capsid, so it cannot be the
   unit of selection; viral RdRp is filed under topologies named for adenylyl cyclases and
   reverse transcriptases, and searching its own English name finds 81 birnavirus domains and
   misses the canonical families entirely; and **"class I fusion glycoprotein" has no ECOD node
   at all** — its members sit in unrelated branches, and the name `GP41` matches a phage tail
   protein as readily as HIV's envelope. So that one fold's membership is this project's own
   construction, shipped labelled as such, and it is the structural coverage gap the Done-when
   criterion asks for. Host RNAi polymerases are excluded from RdRp deliberately: they share the
   fold and are not viral-derived content.

3. **Fix the threshold's value by decoy calibration (D-167 settled everything else).** The
   search geometry is now measured rather than assumed: the **corpus is the query** and the
   166-structure reference set is the target, because a ProstT5 database holds 3Di strings and
   no coordinates, so only the structure side can be the target. That inverts AGENTS.md's
   "query the small side" rule — the tool decides it here — and it flips the coverage floor onto
   the target (`--cov-mode 1`), since the reference domain is now the target and the requirement
   is that half the reference *fold* is matched. The score is the bit score, which is
   database-size independent and so satisfies D-076 outright.
   **A2.2 can never report a TM-score or LDDT for an Evo hit**, on the publisher's own
   statement. The evidence is a structural-alphabet alignment, not a superposition, which caps
   how strongly the fold claim can be worded and belongs in the write-up.
   What remains is the cut itself: the reference set searched against shuffled or unrelated
   queries, to pick a bit score at a stated false-discovery rate with its two bracketing values
   fixed at the same time.

4. **Then the search**, emitting `metrics/detections.md`'s schema with `detector: foldseek`
   (already a valid detector string, pinned by `tests/test_survival.py`), `element_kind` from the
   record's component per D-079 and never from the hit, and routes from `amazebio.apply.route_for`
   rather than re-derived.

**Two prerequisites worth naming.** A1.4's manifests are not in object storage and `artifacts/`
is empty in a fresh container, so they have to be regenerated before A2.2 can read a surviving
set. And A2.1's called proteins were deliberately not persisted (D-103's artefact boundary), so
A2.2 calls genes again rather than reusing them; `--collect`/`--from-cache` is the machinery for
doing that once per release instead of once per search.

**The ESM3 proxy is a different problem, not a smaller one.** A2.1 left it `not_searched`. D-033
records that AlphaFoldDB and ESMAtlas were deliberately not staged by A1.5 and that "measuring
either is A2.2's work", with the cost question to be re-asked. Since its records are UniRef
entries, much of it may already have predicted structures and need no prediction at all — which
would make it the cheapest manifest here rather than the most expensive. Worth settling before
assuming it costs what the Evo corpora cost.

**Waiting on the project owner:** nothing. The GPU decision was the blocker and it is answered.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

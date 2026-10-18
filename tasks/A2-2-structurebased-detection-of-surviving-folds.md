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

**What is left, in order.**

1. **Measure the GPU speedup.** It sets the depth A2.2 can pre-register and it cannot be measured
   here, because nothing in this container has a GPU. It is measured on the instance, as the
   first thing the instance does.
2. **Fix the fold-family universe and its membership rule.** §A2 names three folds in prose, not
   by identifier. D-083 says this membership rule is "a finding about the registry, not a detail
   of the pipeline" and names A2.2 as facing the question; D-097 adds that the id-to-label
   mapping is an artefact with a stated rule. Candidate reference sides are all retrievable and
   none is paywalled: SCOPe 2.08, ECOD v295.2 and CATH 4.4 all serve their classification files,
   and foldseek itself distributes **PDB**, **CATH50** and **BFVD** (viral predicted structures)
   as prebuilt databases.
3. **Fix thresholds before any hit is inspected**, per D-076's rule that a threshold must not
   scale with how much corpus a run happened to read. Foldseek's E-value is target-database-size
   dependent in exactly the way D-076 rejects, so the declared cut should be a TM-score, with the
   normalisation direction stated, plus a coverage floor analogous to A2.1's `MIN_MODEL_COVERAGE`.
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

---
id: A2.3
title: Detect endogenous elements in surviving host genomes
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.3 — Detect endogenous elements in surviving host genomes

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

**Branch:** `claude/fervent-hopper-8ht0h3`, pushed. Project management on `main` as usual.

**Pre-registered before anything was searched:** D-182 (substrate and staging tier), D-183
(registry, selection rule, threshold). D-184 records the measured denominator.

### What is settled

**A2.3 is a one-release task.** Evo 1's release exposes no eukaryotic genomes at all
(D-018, D-019), so its manifests are `not_searched` *by construction* — and for a different
reason than A2.2's, which had a component and did not buy it. The per-source reason strings
carry that difference rather than leaving it in the log.

**The blocker D-031 left is cleared.** The target component was unstaged, 2.17 TB, against a
bucket with no delete. Put to the project owner with three costed options; **the owner chose a
hash-sampled set of whole assemblies** (D-182). Sampling is by assembly accession at the
project's existing seed, so the band is nested and depth can be bought later without re-staging.

**The component is measured, for the first time in this project** (D-184). 90 of 90 tars,
**15,044 assemblies**, 2,174,531,002,595 bytes, no duplicated accession, byte total agreeing
with the pinned tree exactly. That is a third number for this component: the developers state
16,704 downloaded from NCBI and D-007 records 15,148 after deduplication, so the release carries
**104 fewer genomes than its own stated deduplicated count** — stated-versus-delivered, not a
staging gap, and not reconcilable from the published text.

**The 1% band is 167 assemblies, 16,782,960,377 bytes** — 0.77% by bytes rather than 1%, because
assemblies run from 2,030 bytes to a single compressed member of 28.9 GB. Inside what the owner
approved.

**The instruments are pinned and the arm is pre-registered** (D-183). Dfam 4.0's curated HMM
component, at the reader version the publisher's own README attests; the universe is the
curated LTR class, **8,593 models**, of which **5,565** are the ERV subtypes that are the arm's
headline and **762 (8.9%)** are excluded for carrying no curated threshold and named by
accession. The threshold is Dfam's own per-model general cutoff, as A2.1 took Pfam's under
D-076. RepeatMasker was dropped: these are nucleotide profiles, so the already-pinned `pyhmmer`
searches them directly against genomic DNA — no gene calling, no six-frame translation, which is
the right instrument for a degraded relic no gene caller will call.

### Landed on the branch

- `src/amazebio/eukaryotes.py` — the tar-header walker and the member fetch. The walker transfers
  512 bytes per assembly instead of the assembly, which is what makes a sampled stage of an
  unstaged 2.17 TB component possible; the fetch verifies each member against its own gzip CRC,
  which is the only integrity check available because the publisher digests whole tars.
- `src/amazebio/dfam.py` — the pinned release, the selection rule, the threshold policy.
- `tools/index_eukaryotes.py` — the index pass, run complete.
- `tests/test_eukaryotes.py`, `tests/test_dfam.py` — 44 tests. `pixi run -e dev check` green.
- `pixi.toml` / `pixi.lock` — `famdb` 3.0.0 in its own environment, used once for the export.
- Artefacts in `artifacts/a2-3/`: `assembly-index.json`, `component-summary.json`,
  `run-index.json`.

### What is left

1. **Calibrate** the per-assembly cost of the retroelement arm against the pinned registry, on
   real assemblies. Deliberately not assumed: D-098, D-117 and D-149 are three separate records
   of what assuming this costs, and D-149 came in 2.74x off a single-genome extrapolation.
2. **Pre-register the depth** from that measurement, then stage the band and run. Staging is
   irreversible, so calibration comes first.
3. **The non-retroviral arm.** §A2 names it separately and it needs its own registry, denominator
   rule and threshold. D-183 covers the retroelement arm only, on purpose — bundling an arm whose
   universe and cost are unmeasured would weaken the pre-registration rather than strengthen it.
4. **Document the false-positive modes**, which is the third Done-when criterion and is not
   satisfied by either arm running.

Two things worth knowing before picking this up. A structural LTR finder is the natural second
instrument for a concordance check of the kind D-114 fixed for A2.4; this task's Done-when does
not require one, and D-183 records it as the obvious extension rather than dropping it silently.
And `element_kind` here is assigned from the instrument rather than from the component, which is
the one place A2.3 departs from D-079 — legitimately, since D-079 leaves exactly this claim to
A2.3 and A2.4.

**Waiting on the project owner:** nothing. The staging question was the one that needed an
answer and it has one.

## Goal

Identify host-genome-resident elements that a taxonomy filter cannot reach, per the routes
listed in §A2.

## Steps

- Select and pin the element-detection resources and tools named in §A2.
- Run over the surviving host-genome component of each manifest.
- Attribute each hit to the 'host-resident' survival route for A3.2.
- Record tool versions, parameters and known false-positive behaviour.

## Done when

- Hit tables exist with route attribution.
- Tool versions and parameters pinned and recorded.
- Known false-positive modes documented.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

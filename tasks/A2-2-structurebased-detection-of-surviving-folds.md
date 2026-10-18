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

`in-progress`. **Branch `ccr-3db3a0c2-il11ej`.** Just claimed; no work done yet.

Picked over A2.3 because A2.3 cannot start without a project-owner decision. The eukaryotic
component A2.3 targets is 2.17 TB and is not staged — `OG2_COMPONENTS` carries it with
`tier1=False` and the note "Deferred to A2.3, which is the only task that needs it" — and D-031
is explicit that A2.3 "must stage its own component before it can run" and that whoever picks it
up "should expect to re-ask the cost question". D-046 adds that a pass reading the eukaryotic
genomes is the in-region case. So A2.3's first move is a standing-bill question for the owner plus
an EC2 staging pass, not analysis. A2.2 reads corpora that are already staged.

**What is left:** all of it. The method's shape is the first thing to settle, and it is not
obvious — see below.

**Waiting on the project owner:** nothing yet.

### The open methodological question, before any compute

§A2 names three fold classes (jelly-roll capsid, viral RdRp, class I fusion glycoprotein) and
names Foldseek. Neither side of that search exists yet:

- **The reference set** has to be assembled and pinned from structures for three fold classes
  that §A2 names in prose, not by identifier. Which structures count as "the jelly-roll capsid
  fold" is a curation decision with a defensible answer (a structural classification's own
  family boundaries) and several indefensible ones.
- **The query side has no structures at all.** The surviving corpora are nucleotide (Evo) and
  sequence-only (the ESM3 proxy). Foldseek needs 3Di, so something has to supply it —
  ProstT5 from sequence is the candidate — and this container has 4 cores and no GPU, against
  a surviving set of ~2.65M and ~2.96M records whose called genes number far more.

So the sizing question comes before the threshold question. AGENTS.md's rule applies directly:
work out which side of the search is the small one before sizing anything.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

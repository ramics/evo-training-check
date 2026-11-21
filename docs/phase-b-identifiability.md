# Phase B cannot be identified from the released models — and that is a finding

Recorded 21 November 2026, while writing the B5.1 pre-registration. `DESIGN.md` §B5, §B1 ·
tasks B5.1, B1.2, B3.1 · supersedes nothing, and is the reason B5.1 cannot be frozen in the
form §B5 states.

## The claim

§B5's primary estimand is a regression of per-assay Spearman ρ on homology score **with
model-exclusion-status as the interaction term**. Fitting it needs two things per assay: a score
from an excluded model, and that assay's exclusion status under that model's filter.

Across the 31 assays in `assays/register.json`, **no model supplies both**, and neither gap is
one more pass would close.

| Model | Role (B1.1) | Per-assay exclusion status | Scoreable on these assays |
|---|---|---|---|
| `esm2_t33_650M_UR50D`, `esm2_t36_3B_UR50D` | positive control | not excluded, by definition | yes |
| `ESMC-600M` | second positive control | not excluded, by definition | yes |
| `esm3-sm-open-v1` | **protein-level test condition** | **undecidable, all 31** | yes |
| `evo2_7b` | **nucleotide-level test condition** | **decidable: 24 excluded, 7 retained** | **no** |

## Why the protein-level test condition is undecidable, structurally

`esm3-open`'s filter removes sequences by **similarity to a denylist**, not by taxonomic label.
`src/amazebio/assays.py` therefore places every assay in `undecidable_by` for all three readings
of that policy, and the register's own docstring states why this is carried rather than filled:
a policy that reaches this register with no verdict and no reason is how a missing arm becomes an
apparently complete table.

No quantity of taxonomy decides a single target here. Deciding one means executing the filter,
which means the denylist, which the publisher did not release — the gap A1.6 was opened to
reconstruct and which is parked, with the published total of 187K sequences (D-106) as its only
validation target.

## Why the decidable test condition cannot be scored

`src/amazebio/scoring.py` refuses the nucleotide backend for a stated reason rather than a
missing feature: scoring protein substitutions through a nucleotide model needs a pinned coding
sequence per assay and a stated codon-to-residue mapping, and reverse-translating the published
protein would make this project choose codons no source states. The harness carries
`nucleotide_wild_type` and never synthesises it.

This is the model that already has what §B5 wants on the other axis: a reconstructed surviving
corpus (A1.4), measured homology for its targets (B3.1 — 19 of 31 in Evo 2's surviving records,
10 of 31 in Evo 1's), and decidable exclusion labels for every assay.

## So the two halves of the design sit in different models

The decidable exclusion axis and the scoreable interface never meet. The consequence for the
gate is exact, and it is not a matter of sample size:

- Scoring the remaining assays on the four protein checkpoints yields per-assay tables and a
  comparison against the parameter-free baseline. **It yields no interaction term.**
- A pre-registration written in §B5's form would freeze a specification that cannot be fitted.
  B5.1 is held open for that reason rather than frozen to a plan nobody can run.

## What is answerable, and at what price

1. **Pin a published coding sequence per assay and open the nucleotide arm.** The only route to
   the estimand as designed. Needs a CDS whose translation matches each published wild type, a
   codon-to-residue rule pre-registered before any score, and one accelerated pass. Feasibility
   is being measured per assay rather than assumed; see `/mnt/project-files/bc-acceleration/`.
2. **Report the impossibility.** One laboratory's filter cannot be checked against any single
   protein because its denylist is unpublished; the other's can be checked but is scoreable
   through no published protein interface. This is the metadata ceiling one phase over: an audit
   defeated by what a release withholds, and §A0's habit says to measure the consequence rather
   than paper over it with a plausible guess. It costs nothing and it is true whatever else is
   decided.
3. **Reconstruct the unpublished denylist** (A1.6). Most of that arm's work, resting on a proxy.
4. **Score the protein models anyway.** Tables, a baseline comparison, nothing about exclusion.

Routes 1 and 2 are not alternatives: 2 is written up either way, and 1 decides whether the
write-up also carries a measured interaction term. Which of 1 and 3 to buy is the project
owner's call, and it was put to them on 21 November 2026.

## What this does not say

- **It does not say Phase B's instruments were wasted.** The harness, the baseline at published
  strength (D-248), the homology axis, the depth covariate and the register are what establish
  the gap above *as* a gap rather than a guess. An identifiability failure can only be stated by
  a project that built the instrument far enough to see it.
- **It does not weaken Phase A.** Nothing here touches survival, the metadata ceiling or the
  hazard check. Phase A ships alone if B stays unanswerable, which `AGENTS.md` already allows.
- **It does not settle Phase C.** `metrics/costcurve.md` §10 states the dependency the other
  way round: the curves inherit "capability tracks homology" as a premise, and C6.2 checks it
  against whatever Phase B ends up able to say. If Phase B ends at route 2, C6.2's verdict is
  that the premise is **untested**, reported as such, and the curves price an operation whose
  effect on capability is unestablished. That is a narrower claim than the one §C6 hoped for and
  it is still publishable; what it may not do is go unstated.

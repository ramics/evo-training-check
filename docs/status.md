# Status

Hand-maintained, 19 November 2026. This page says where the work has got to. The figures and
their provenance are in `../results/README.md`.

## Phase A — does the filter remove what it claims to?

**Complete, and being written up.** Both corpora were reconstructed from pinned revisions, each
published policy was transcribed into executable predicates in three readings, the surviving
records were searched by sequence and by structure, and the headline counts were
reimplemented independently and reproduced to the number (334 of them). The audit of the
taxonomy dependency, the conformance re-execution, the specificity join, the label arm and the
decay measurement are all done.

Open:

- The write-up. A draft exists outside the repository and is being cut down.
Closed rather than open, as of 21 November 2026, each with its reason already measured:

- The deepening pass at census depth is **declined, not pending**. It was priced and not bought,
  and the sampling design was pre-registered, so the lower bounds are the result the project set
  out to get rather than a shortfall. The runbook is in `a2-6-census-runbook.md`.
- The protein-model arm (ESM3-open) is **parked**. It is staged and priced and publishes no
  figure: that filter works by similarity instead of by label, so re-executing it needs two
  denylists neither publisher released, and reconstructing them is most of the arm. It is the
  only route to a decidable exclusion label for that model, which is why
  `phase-b-identifiability.md` carries it as one of the ways out of Phase B.
- The per-region metrics for a named record set are **done**; the figure is in
  `../results/README.md`.
- The training-membership accession list belongs to the disclosure package and waits on the
  disclosure gate rather than on work.

## Phase B — where it does not, does surviving capability track homology?

**Instruments built and validated; the analysis has not run.** The zero-shot scoring harness
reproduces the benchmark's published numbers (27 of 27 comparisons, lowest 0.9957, runs bitwise
reproducible). The parameter-free baseline is at published strength, and was not tuned towards
the published column it is checked against: maximising agreement with that column would measure
the tuning instead of the method. The homology axis, the domain-level presence measure
and the alignment-depth covariate are computed, and the assay provenance register is validated
in CI.

**The analysis cannot be identified from the released models, and the pre-registration is held
open rather than frozen to a plan nobody can run.** The primary result needs, per assay, both a
score from an excluded model and that assay's exclusion status under that model's filter. No
released model supplies both: the protein-level test condition removes sequences by similarity to
a denylist it never published, so no label decides any single target, while the nucleotide-level
test condition — the one with decidable labels, a reconstructed surviving corpus and measured
homology — is scoreable through no published protein interface, and reverse-translating a
published protein would mean scoring codons no source states. `phase-b-identifiability.md`
records this with its evidence and the four ways out. The project owner was asked on
21 November 2026 which to buy.

That gap is itself the same shape of finding as the metadata ceiling, one phase over, and is
written up either way.

The structural side of the homology axis was declined for good: it would tighten a bound rather
than produce a new result, and the sequence measure stays secondary.

## Phase C — can leakage be predicted from the filter spec alone?

**The cost-curve arm is the live one; the leakage score is closed as deliberately not run.** The
definitions and the hazard-family set are frozen (`../metrics/costcurve.md`), including the
second instrument, which reads biology instead of family names, and the family set is published:
1,144 nominated families, 646 of them carrying a curve.

What is left is one measured pass and then arithmetic. Each of the eight stringency steps is a
filter over a single similarity search of those families' seeds against the pinned cluster
release, so the whole sweep, the coverage pair and the intervals come from one job rather than
646. The curves then go to their own independent-reimplementation gate, which is still closed.

The leakage score — a predictor fitted to Phase B's measurements — was superseded by the cost
curve in v0.4 and its six tasks are closed as deliberately not run, rather than carried as
deferred. The write-up names them and why.

## What was cut, and why — 21 November 2026

The project overflowed. Nine pieces of work were closed on one reading: does it produce a figure
nobody has? Each is recorded here rather than deleted, because work deliberately not run is part
of what this project reports.

| Cut | Why |
|---|---|
| The leakage score, six tasks (C1.1, C2.1–C2.4, C3.1) | Superseded by the cost curve in v0.4 (D-009). Carried as deferred since; now closed. |
| Packaging the homology pipeline (B3.5) | Its own brief is a refactor that must not change a number, and it blocked both the pre-registration and the cost-curve index. The three tools and `../metrics/homology.md` are the deliverable. |
| The cost-curve CLI (C7.1) | Polish ahead of a curve. `costcurve.published_view` and `disclosure_view` already give the two views the reporting limit needs. |
| One-command reproduction and the notebooks (X1.2, X1.3) | The README already carries a three-command reproduction, and figures ship as artefacts indexed by `../results/README.md`. |
| The cross-measure agreement analysis (part of B5.3) | Unrunnable rather than unfinished: the structural measure was declined for good, so two of the three measures exist. Reported as a limitation. |

Nothing cut here removes a measurement. Every arm that delivered one is kept, including the ones
that publish no figure — the structural route's cost, the endogenous-element route, and each
launcher, which is the only way back to a corpus-scale pass.

## Gates

A gate is a commitment the project made in advance, and work downstream of a closed one does not
start. Two have passed and three are still closed.

| Gate | State | What it holds |
|---|---|---|
| Released-vs-actual training data verified | **passed** | — |
| Independent second-method reimplementation of the headline counts | **passed** | — |
| Pre-registration written and frozen | **closed, and held open deliberately** | Phase B's analyses, and the preprint. See `phase-b-identifiability.md`: the specification §B5 states cannot be fitted from the released models, and freezing a plan nobody can run would be a freeze in name only |
| Independent reimplementation of the headline curves | **closed** | Phase C's output, and the preprint |
| Responsible-disclosure process run | **closed** | **all external circulation**, and the preprint |

**Nothing has been circulated outside the project, and nothing may be until the disclosure gate
opens.** No deadline or convenience lifts that one.

## The working record

The task cards, the append-only decision log and the generated board were removed from the tree
on 19 November 2026, to keep the project management out of a reader's way. They are in git
history at commit `fbc8b41`, and copied in full to the project's own files. Figures and contracts
still cite task ids (`A2.1`) and decision ids (`D-245`); `working-record.md` says how to look one
up.

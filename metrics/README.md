# metrics/

The output contracts. Each fixes what a number *means* before any code computes it, so a
definition cannot drift towards a result. **A change to one of these is an entry in
`../tasks/DECISIONS.md` saying what was known at the time and what changed — not an edit.**

The two that carry the headline are written to be reimplementable from themselves alone, because
an independent second implementation has to reproduce the figures without reading the first.

- **`survival.md`** — FROZEN. The headline survival metrics and the route taxonomy: the unit (a
  family in a pinned registry), the two registries reported separately and never pooled, the
  threshold contract, and M1–M3. Frozen 2026-10-14, before any detection ran.
- **`detections.md`** — the one table shape every detector emits, including the `not_searched`
  kind that keeps an unsearched manifest from being pooled with a sampled one.
- **`manifests.md`** — the surviving-corpus contract: the artefact the detectors read, so that
  every arm is measured over the same records.
- **`homology.md`** — the Phase B homology axis: sequence-profile score, domain-level presence,
  and the structural measure that stays secondary. Binding on the pre-registration.
- **`depth.md`** — the alignment-depth covariate, which is what keeps "viral proteins are hard"
  and "viral proteins were excluded" separable.
- **`costcurve.md`** — FROZEN. Phase C's cost-curve definitions and the hazard-family set, built
  by database cross-reference rather than by reading a family's name.
- **`eve-detection.md`** — the endogenous-element arm: its substrate, registry, selection rule
  and threshold, and what can make the arm wrong.

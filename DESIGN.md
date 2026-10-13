# Does taxonomic data filtering work as a safeguard?

**An independent audit of exclusion-based safeguards in open-weight biological models**

Design specification, v0.5 — 13 October 2026

---

## 0. What changed from v0.4

Four additions to Phase A, all of which exploit the same asset: the filter predicates are now
formalised (A0), and nobody else has them. None needs a GPU, a hazard list, or any capability
measurement. See `tasks/DECISIONS.md` D-011.

- **§A7 Conformance re-execution.** Run each published predicate against the developer's own
  released corpus and diff. A record that survives a rule its own authors stated is a
  conformance failure — binary, and not an inference about homology.
- **§A8 Filter agreement.** Apply both filters' predicates to one corpus and measure overlap.
  If two labs' "remove viruses" safeguards disagree about what counts as viral, this class of
  safeguard is not reproducible, which is what governance currently assumes it is.
- **§A9 Safeguard decay.** Evo's denylist is 19 families and 12 orders fixed in 2024, against a
  taxonomy that keeps changing. Quantify what newly-named diversity the frozen list no longer
  names. The output is a re-validation schedule: a filter has a shelf life.
- **§10 A disclosure standard for data filters.** The deepest finding in A0 is not leakage but
  that these filters are unauditable as published. Define the minimum a developer must publish
  for a filter to be auditable, and retro-fit it to all four models.

**Phase A is now a paper on its own**, and the schedule in §6 reflects that: Phase A ships as
the first paper, Phase B and C as the second. This replaces "Phase A alone is publishable if
Phase B slips" with a deliberate split.

## 0.1. What changed from v0.3

Two changes, both from the prior-art check. See `tasks/DECISIONS.md` D-009 and D-010.

- **Phase C becomes the collateral cost curve; the leakage score is dropped.** A predictor of
  retained capability fitted to a few dozen measurements across three models cannot carry
  honest uncertainty intervals narrow enough to guide a decision, and its users would be
  extrapolating outside the fitted domain. The replacement asks a question that needs no fit:
  for each hazard family, what else would have to be removed to actually remove the capability?
  That prices the remedy instead of predicting the leak, and it is computable from public
  databases with no GPU.
- **Phase B shrinks to the homology check.** ESM-C's own preprint already publishes the model
  comparison Phase B was built around — 25 viral DMS assays from ProteinGym against ESM-2 650M
  and ESM3-open, with BLOSUM62 and EVMutation baselines. Redoing it would spend most of the
  schedule re-deriving a published result. Phase B keeps the part that is new and that the cost
  curve depends on: whether per-assay performance tracks homology to retained sequence.

## 0.1. What changed from v0.2

Three changes, all forced by primary-source verification in A0.1. See `tasks/DECISIONS.md`
D-005 to D-007 for the evidence behind each.

- **The protein-level test model changes from ESM-C to ESM3-open.** ESM-C's own preprint lists
  IMG/VR viral genomes among its training sources and states no exclusion. ESM3-open is the
  model that filtered. ESM-C stays in as a second viruses-included comparison, where its
  largely bacteriophage-derived viral content is a useful contrast.
- **The subject broadens from taxonomic filtering to hazard-driven data filtering generally.**
  Evo filters by taxonomic label; ESM3-open filters by sequence similarity outwards from a
  taxonomy-seeded denylist. These are different mechanisms with different failure modes, and
  comparing them is stronger than auditing one.
- **Phase A now leads with the scope gap rather than with leakage magnitude.** The Evo
  exclusion is a curation step applied to the IMG/VR viral component. Evo 2 inherited it
  unchanged while adding ~10.7T nucleotides of eukaryotic reference genomes that received only
  assembly-quality and redundancy curation. The gap between what was filtered and what was
  trained on is visible in the published methods, before any measurement.

## 0.1. What changed from v0.1

v0.1 measured the *effect* of viral exclusion on model capability. v0.2 adds the prior
question — whether the exclusion was ever achieved — and the posterior one — whether leakage
can be predicted before training. Three phases now:

- **Phase A — Filter audit.** Do the stated filters remove what they claim to? Pure
  bioinformatics, no GPU, no model inference.
- **Phase B — Capability audit.** Does residual capability track homology to non-excluded
  space? (This was v0.1.)
- **Phase C — Leakage score.** A calibrated, pre-computable predictor of how much capability
  a given filter will fail to remove, shipped as a tool.

The framing is also broadened: the subject is **hazard-driven data filtering as a class of
safeguard**, covering both label-based and similarity-based mechanisms. Viral exclusion is the
test case because it is the one with public models, public policies and public ground truth.

---

## 1. The question

Pre-training data filtering is becoming the default safeguard for biological AI models, and is
being written into pre-development review frameworks, Biosecurity Data Level schemes and
if-then commitments. Two mechanisms are in use, and they fail differently:

- **Label-based** — remove records whose taxonomic annotation falls in a denylist. Evo 1 and
  Evo 2 do this.
- **Similarity-based** — seed a denylist from annotation, then remove everything that aligns to
  it above a threshold. ESM3-open does this.

A label-based filter can only act on records that carry the label, and only within the files it
is pointed at. A similarity-based filter reaches further but, by construction, retains anything
that also resembles non-hazardous sequence.

Two open-weight models state viral exclusion as an explicit safety measure:

- **Evo 2** (Arc Institute) excluded eukaryotic viruses — stated as leaving out pathogens that
  infect humans and other complex organisms — for ethics and safety reasons.
- **ESM3-open** (EvolutionaryScale) excluded viral proteins.

Arc's own testing found the exclusion weakens language modelling and downstream prediction for
human viruses, and their red-teaming found generated sequences effectively random for
pathogenic viral proteins. Those claims rest on internal red-teaming; no independent external
review has been published. Hanke et al. (2026) state that the efficacy of risk mitigations is
unproven and call for rigorous efficacy studies.

**Three questions, in order:**

- **A.** Was the filter applied to all of the data it would need to cover, and does it remove
  what it says it removes within that scope?
- **B.** Where it doesn't, does the surviving capability track homology to non-excluded space?
- **C.** Can leakage be predicted from the filter specification alone, before training?

---

## 2. Hypotheses

**HA (filter leakage).** Stated exclusions leave substantial viral-derived sequence in the
surviving corpus. The routes, in the order they are expected to matter:

- **Outside the filter's scope.** The filter was applied to some corpus components and not
  others. Sequence in the unfiltered components was never a candidate for removal, regardless
  of what it is. This is first because it is the largest and because it is established from
  the published methods rather than measured.
- **Invisible to the filter's labels.** Within the components the filter did cover: endogenous
  viral elements in host genomes, prophage in bacterial genomes, unclassified metagenomic
  content, host-derived genes captured by viruses.
- **Mis-labelled.** Misassignment by the taxonomy tools the filter depends on.
- **Deliberately retained.** For similarity-based filters, sequence that also resembles
  non-hazardous sequence falls below the denylist threshold by design.

**HB (capability tracks homology).** For virus-excluded models, per-assay performance on viral
DMS is predicted by homology to non-excluded sequence space, not by viral taxonomy. Residual
capability concentrates in classes with cellular or phage homologs — polymerases, reverse
transcriptases, proteases, helicases, nucleases — and is absent for virus-specific folds such
as capsids, envelope glycoproteins and matrix proteins.

**HC (predictability).** A score computed from the filter specification and public sequence and
structure databases predicts measured capability retention well enough to be useful as a
pre-training review criterion.

**H0.** Filters achieve their stated exclusion; the performance drop is uniform across viral
proteins regardless of homology; taxonomy is a sufficient filter.

**H0 is a publishable result and must be published if observed.** Commit to this before
running anything. It is the difference between an audit and an advocacy exercise.

### Motivating cases

- HIV-1 reverse transcriptase is homologous to LINE-1 retroelement RT, present in the human
  genome and therefore in training data that excluded "viruses."
- Filovirus and bornavirus endogenous viral elements are present in mammalian genomes. A
  filter that excludes Ebola by taxon but includes bat and mammal genomes has not excluded
  filovirus sequence.

---

# PHASE A — Filter audit

No GPU required. This phase is the headline result and the part only a real bioinformatician
can do properly.

**Lead with scope.** The first question is not how much a filter leaked but what it was pointed
at. A filter applied to one component of a corpus cannot act on the others, however well it
works internally. Establish the scope gap from the published methods first (A0, A4.3), then
measure what survived through it (A2, A3). Sizing a gap that is already visible is a stronger
result than hunting for one.

## A0. Formalise each policy as an executable predicate

Stated policies are prose, and the prose is ambiguous. Arc's phrase concerns pathogens
infecting humans and other complex organisms, which is neither a taxonomic clade nor
equivalent to "all eukaryotic viruses."

For each model, implement **three readings** of its stated policy:

- **Literal** — the narrowest defensible reading of the published words.
- **Charitable** — what the authors most plausibly meant.
- **Strict** — the broadest reading a cautious reviewer would want.

Report results under all three. **The spread between readings is itself a finding**: if the
three readings differ substantially in what survives, the policy as published is not
reproducible, and that matters for any governance framework that tries to mandate it.

Record, verbatim and with citation, for each model: what was excluded, by what definition,
whether it applied to the released checkpoint, and whether any route for viral-derived
sequence to re-enter is addressed. Under-specification is data, not an obstacle.

## A1. Reconstruct the corpora

Arc states it released its training data. **Verify whether the released dataset is the actual
training corpus** — if so, Phase A audits the real thing rather than a proxy, which is much
stronger. If not, document the gap and use the closest documented proxy.

For protein models, use the stated source databases (UniRef tiers) at the stated versions where
recoverable; otherwise state the proxy and its version explicitly as a limitation.

## A2. Detect surviving viral-derived content — by methods independent of taxonomy labels

This is the methodological core. The filter uses taxonomy; the audit must not, or it will
reproduce the filter's own blind spots.

- **Profile search** — viral protein family HMMs (Pfam viral clans; RVDB, which exists for
  exactly this purpose) against the surviving corpus.
- **Structural search** — Foldseek for virus-characteristic folds: jelly-roll capsid, viral
  RdRp, class I fusion glycoprotein.
- **Endogenous viral elements** — retroelement and ERV detection in surviving host genomes
  (Dfam/RepeatMasker, LTR finders), and non-retroviral EVEs (filovirus, bornavirus,
  parvovirus) in mammalian genomes.
- **Prophage** — geNomad / VIBRANT / CheckV on surviving bacterial genomes.
- **Known problem taxa** — giant viruses and NCLDV, segmented genomes, satellite viruses.

## A3. Quantify

Headline metric is **family-level survival**, not base pairs:

- fraction of viral protein families with at least one surviving homolog above threshold
- surviving sequence count per family
- coverage of each family's known diversity by surviving sequence
- the same, broken down by the route of survival (EVE / prophage / unclassified / misassigned)

Raw bp understates the problem: one good homolog teaches a fold.

## A4. Audit the taxonomy dependency itself

A taxonomy-based filter can only act on sequence that taxonomy has labelled.

- What fraction of the metagenomic component is unclassified or dark matter, and therefore
  unfilterable in principle?
- Benchmark the misassignment rate of the taxonomy assignment tools the filter relies on, on
  viral sequence specifically.

## A7. Conformance re-execution — did the filter do what its authors said?

The cheapest airtight question available, and it only became askable once A0 turned the prose
into an executable predicate.

Each developer published a procedure and, in Evo's case, the corpus it was applied to. So run
the procedure against the released corpus and diff:

- Execute each reading's predicate over the released dataset.
- Identify **conformance failures**: records that survive which the developer's own stated rule
  should have removed.
- Classify each failure by cause — the predicate is ambiguous, the annotation the predicate
  relies on is absent or wrong, the record postdates the filter, or the rule was simply not
  applied to that component.
- Report the count and the rate, per model and per reading.

This claims nothing about homology, capability or hazard. It compares a stated rule against
delivered data. **A clean result is as valuable as a dirty one** and must be published either
way (§2): it would be the first external confirmation that a stated filter was actually applied
as described.

A failure here is a stronger finding than any leakage estimate, and a more sensitive one. It
gets the §7 treatment: independent re-execution by a second implementation before publication,
and the disclosure window honoured as substance.

## A8. Filter agreement — do two labs mean the same thing by "viral"?

Both filters claim to remove viral sequence. They are different mechanisms (§A0), so apply both
to a single common corpus and measure where they disagree.

- Run Evo's label-based predicate and ESM3-open's similarity-based predicate over the same
  records.
- Report agreement: records both remove, records neither removes, and records exactly one
  removes — with the last broken down by which and why.
- Where they disagree, characterise what kind of sequence falls in the gap.

If agreement is high, the safeguard class is at least consistently defined and that strengthens
it. If agreement is low, then "we filtered viral data" does not denote a definite operation,
and any framework that mandates it is mandating something underdetermined. Either way this is
measurable now, and it needs no hazard list.

Note the confound to handle honestly: the two filters were applied to different corpora in
their original use (nucleotide genomes versus protein databases). Running both on one corpus
measures the predicates, not the deployments, and the write-up must say so.

## A9. Safeguard decay — does a filter have a shelf life?

Evo's denylist names 19 families and 12 orders, fixed against the taxonomy of 2024. Viral
taxonomy is revised continuously, and corpora are rebuilt from newer database releases.

- Take the frozen denylist and replay it against successive taxonomy releases.
- Count taxa that are in scope by the policy's intent but not named by the frozen list: newly
  erected families, renamed or split taxa, and reassignments across the list's boundary.
- Express the result as decay over time, and derive the implied re-validation interval.

The governance consequence is concrete and absent from current frameworks: a filter approved
once does not stay approved, and a review regime with no re-validation requirement is approving
a decaying control. This is cheap, needs no hazard list, and applies to every label-based
filter rather than only these two.

**Phase A deliverable:** a filter-audit tool that takes a policy specification plus a corpus
and reports what survives, by route; plus the conformance, agreement and decay results.

---

# PHASE B — Capability audit

**Narrowed in v0.4.** Phase B is no longer a standalone model comparison — ESM-C's developers
have published that (25 ProteinGym viral assays against ESM-2 650M and ESM3-open, with
BLOSUM62 and EVMutation baselines). Cite it; do not re-derive it. Phase B's job here is the one
thing that comparison does not do and that Phase C depends on: **establish whether per-assay
performance tracks homology to retained sequence.** That premise is what licenses the cost
curve. Where this document still describes the fuller comparison, treat the homology regression
as primary and everything else as supporting.

## B1. Models

**Step 0 before anything:** verify every exclusion policy from primary sources (§A0 covers
this). Do not trust secondary sources, including this document.

| Model | Exclusion status | Role |
|---|---|---|
| ESM-2 650M and 3B | UniRef50, viral **included** | Positive control |
| ESM-C (open release) | viral **included** — IMG/VR, largely bacteriophage | Second positive control |
| **ESM3-open** (`esm3-sm-open-v1`) | similarity-based removal of sequences **unique to viruses** | **Test condition, protein level** |
| Evo 2 7B | eukaryote-infecting viruses **excluded** by label; phage included | Test condition, nucleotide level |

ESM-C was listed as the protein-level test condition in v0.2. Its own preprint contradicts
that: IMG/VR release 7 appears in its training sources and no exclusion is stated. It is kept
as a second viruses-included comparison, which is worth having because its viral content is
largely bacteriophage — the same contrast Evo 2 provides at the nucleotide level.

Tier 2 if compute allows: Evo 2 40B, Nucleotide Transformer, ProGen2.

**Mandatory non-neural baseline:** a parameter-free MSA + structure method (RSALOR, GEMME, or
a site-independent MSA model). See §B4.

## B2. Data

**ProteinGym v1.3** — 217 zero-shot DMS substitution assays with taxon labels. Use standard
splits and Spearman so results are comparable to the published leaderboard.

**Viral extension.** The viral subset is small; published Evo 2 comparisons have used as few
as four viral assays. Small n is the study's biggest statistical threat. Curate a larger,
QC'd viral DMS collection: HIV-1 protease / RT / integrase / Env; influenza HA, NA, PB2;
SARS-CoV-2 RBD and Spike; HCV NS5A/NS5B; Zika; dengue E. Include **phage proteins as an
internal contrast** — phage is in Evo 2's training data, so phage performance is a
within-study positive control.

Record per assay: organism, protein, fold/domain, readout type (binding / stability /
replication fitness / drug resistance), variant count, DOI, licence.

## B3. The homology axis

Against a reconstruction of each model's **surviving** corpus — which Phase A now gives you
directly, rather than as an assumption:

1. **Sequence-profile homology** — jackhmmer best-hit bitscore, length-normalised. Secondary.
2. **Domain-level presence** — Pfam/InterPro domain present in surviving space? Binary + count.
3. **Structural homology** — Foldseek TM-score to nearest surviving structure. **Primary**,
   because remote structural homology is the route by which a fold's biophysics is learned when
   sequence similarity is undetectable.

Pre-register #3 as primary. Report all three; disagreement is informative.

**Confounder: MSA depth.** Compute Neff per target and include as covariate. Without it,
"viral proteins are hard" and "viral proteins were excluded" are not separable.

## B4. Why the parameter-free baseline is load-bearing

An MSA + structure method built at inference time has no training exclusion.

- pLM fails **and** baseline fails → assay is intrinsically hard. Says nothing about filtering.
- pLM fails **but** baseline succeeds → failure attributable to training data. **This is the
  measurement.**

RSALOR already outperforms most billion-parameter pLMs on ProteinGym, so this is a strong
baseline, not a straw man.

## B5. Analysis plan (pre-register before running)

**Primary.** Hierarchical regression of per-assay Spearman ρ on homology score, with
model-exclusion-status as interaction term, random effects for assay and protein family, and
covariates for Neff, readout type, length and variant count. **The interaction term is the
result.**

**Secondary.** Retention ratio (excluded-model ρ ÷ included-model ρ) against homology;
class-level summary by fold family; agreement across the three homology measures.

**Effect size that matters.** If excluded models retain ≥80% of included-model performance on
high-homology viral proteins, exclusion has failed for that class. State the threshold before
looking at results.

Report per-assay, not only pooled. With n in the tens, pooled correlations are fragile.

---

# PHASE C — The collateral cost curve

Asks what it would cost to *not* leak. This is the part that turns an audit into a criterion
reviewers can apply to filters that do not exist yet.

## C1–C4 (superseded in v0.4)

The leakage score — a predictor of retained capability, fitted to Phase B measurements — is
superseded by §C5–C8 below. See `tasks/DECISIONS.md` D-009. Tasks C1.1, C2.1–C2.4 and C3.1 are
`deferred` rather than deleted: the work is deliberately not run, and the paper names it as
such, with the reason.

## C5. Definition

For a hazard protein family **F**, the cost curve answers: to remove F's capability from a
training corpus, what else must be removed?

Capability tracks homology (Phase B). So removing the capability for F means removing F's
homologs — and F's homologs may include cellular and phage proteins that are not hazards at
all. For each F and each filter stringency **s** (a sequence-identity or structural-similarity
threshold), compute two quantities:

- **Hazard removed** — the fraction of F's known diversity that a filter at stringency s would
  remove.
- **Collateral removed** — what else goes with it: non-hazard sequences, families and domains
  that fall inside the same similarity neighbourhood.

The curve is hazard-removed against collateral-removed, swept over s, per family. Everything in
it is computable from public sequence and structure databases. **No model is trained, fine-tuned
or run to produce it.**

## C6. The result is a triage, not a number

Two regimes, and which one a family falls into is the finding:

- **Cheap** — the curve rises steeply: most of F's diversity is removable for little collateral.
  Filtering works for F. A reviewer can reasonably require it.
- **Catastrophic** — removing F's diversity requires deleting a large slice of general biology.
  **Filtering cannot work for F**, at any stringency, and no amount of filtering better will
  change that. A different control is needed — access control, deployment-side guardrails,
  structured access — and saying so is more useful than a leakage estimate.

This explains something Phase A found: ESM3-open removed only sequences "unique to viruses"
(§A0, `policies/esm3-open.md`). That is precisely what a developer does on meeting the
catastrophic regime. The design decision is already evidence for the curve; this work prices it.

**Pre-register the regime boundary before computing anything.** State what collateral fraction
counts as catastrophic, in advance, as §B5 requires for its own threshold.

## C7. Ship it

A CLI and library: input a hazard family and a corpus, output the curve, the regime
classification, and the similarity neighbourhood that explains it. The uncertainty is in the
homology estimates and the database coverage, not in a fitted model, so it is reportable
directly rather than as a calibration interval.

**State the limitation plainly:** the curve is only as good as the databases' coverage of a
family's diversity, and coverage is uneven across families. Report coverage per family
alongside the curve, and never a curve without it.

## C8. Why it matters

Pre-development review frameworks ask reviewers to judge whether a filter is adequate, with no
criterion to apply. A leakage estimate would tell them how much a specific filter leaked. The
cost curve tells them something more useful and more durable: **whether any filter could work
for this hazard, and what it would cost.** For the catastrophic families that converts the
review question from "is this filter good enough" — which has no good answer — into "data
filtering is the wrong control here, use another one."

---

## 3. Generalisation beyond viruses

The subject is hazard-driven data filtering as a mechanism. The same structure applies to
select-agent lists, toxin lists and specific pathogen lists, under either mechanism: a filter
pointed at part of a corpus, over labels that are incomplete, across a boundary the biology is
homologous over, with an unclassified fraction that is unfilterable in principle.

Include a short section mapping the method onto those cases and stating clearly that it is
**untested** there. Claiming the transfer without testing it would undercut the rest.

---

## 4. Scope limits — read before coding

- **Zero-shot scoring only. No sequence generation.**
- **No fine-tuning to restore excluded capability.**
- **No in-context capability-recovery experiments.** This is the obvious next question and is
  deliberately declined; the right version happens with an institutional partner and a
  disclosure process already in place. Name it in the paper as future work not run.
- **No published ranking of which model is most capable for which pathogen.** Report by
  homology class, fold family and survival route.
- **Cost curves are published aggregated by homology class, never as a per-family hazard
  ranking.** A per-family curve read uncharitably is a map of which hazards filtering protects
  least. This limit is set before Phase C runs, not after seeing results: publish the regime
  classification by homology class and fold family; keep per-family curves in the disclosure
  package and out of the preprint; and let the disclosure window close before any of it
  circulates. The tool may compute a per-family curve for a user's own corpus — that is its
  purpose — but this project does not publish a ranked table of them.
- Published DMS data on well-characterised proteins only. No wet work. Nothing concerning
  enhancement, transmissibility or host range.
- **Responsible disclosure:** share Phase A and B findings with Arc Institute,
  EvolutionaryScale and SecureBio before any preprint, with a stated response window.

Framing throughout is *auditing a published safeguard*. The actionable conclusion is for
developers to filter better, which is defensive-dominant.

---

## 5. Deliverables

1. `filter-audit` — policy specification language, corpus auditor, survival-route reporting.
2. Viral DMS assay register with provenance and licensing — reusing published collections
   where licensing allows, extended only where n is genuinely insufficient.
3. Homology annotation pipeline.
4. `cost-curve` — CLI and library: hazard family plus corpus in, curve, regime and
   neighbourhood out, with per-family database coverage reported alongside.
5. Results notebooks and figures.
6. Preprint.
7. Public repo: pinned environment, seeds, one-command reproduction.
8. A filter disclosure standard, with all four models scored against it.

---

## 6. Schedule

**Two papers, not one.** Phase A now carries conformance, agreement, decay, scope and the
disclosure standard — enough for a complete paper that needs no GPU. Phase B and C follow as a
second paper. Trying to ship all of it at once is how both end up late.

**Paper 1 — Phase A.**

| Weekend | Work |
|---|---|
| 1 | A0 policy formalisation (three readings); A1 corpus reconstruction; verify released-vs-actual training data |
| 2 | **A7 conformance re-execution**; **A9 decay** — both pure predicate work, both cheap |
| 3 | A2 detection; A3 quantification; A4 taxonomy dependency and scope |
| 4 | **A8 filter agreement**; A3.3 independent reimplementation; **§10 disclosure standard** |
| 5 | Phase A write-up; figures; repo polish; disclosure emails; window opens |

**Paper 2 — Phases B and C**, after the Paper 1 disclosure window closes.

| Weekend | Work |
|---|---|
| 6 | B1–B3: assay register; homology axis against surviving corpora; MSA baseline |
| 7 | B5 homology regression; the C6.2 premise check |
| 8 | C5–C6 cost curves and regime classification |
| 9 | C7 tool; write-up; figures |

Five weekends for Paper 1 is realistic; it was optimistic for less work before. The split is
also a hedge: if the premise check in C6.2 undermines the cost curve, Paper 1 is already out.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| **Phase A embarrasses named labs** | Must be airtight. Independently reimplement the headline counts by a second method before publishing. Honour the disclosure window as substance, not formality. |
| Released training data ≠ actual training corpus | Verify first; if it differs, say so and treat the discrepancy as a finding |
| Policy prose too vague to implement | The three-readings design turns this from blocker into result |
| Small viral n in Phase B | Curate beyond ProteinGym; hierarchical model; per-assay reporting; phage internal control |
| ESM3-open filter threshold unpublished ("a given sequence identity threshold") | Report under all three readings; the unstated threshold is itself a finding |
| Cost curve misleads where database coverage of a family is thin | Report coverage per family alongside every curve; never publish a curve without it; treat thin coverage as an abstention, not a cheap verdict |
| **Cost curve reads as a map of least-protected hazards** | Aggregate by homology class; per-family curves stay in the disclosure package; limit set in §4 before the work runs |
| **Scope creep — five work streams against a weekend schedule** | The §6 two-paper split is the mitigation: Phase A ships first and alone. Resist adding models and assays for their own sake. If Paper 1 slips, cut A8 before A7 or A9. |
| Conformance re-execution depends on the released corpus being the training corpus | A1.1 gates it. A conformance claim against a proxy corpus is not a conformance claim; say so or do not make it. |

---

## 10. A disclosure standard for data filters

The hardest problem in A0 was not that the filters leak. It was that they cannot be audited
from what was published:

- Evo 2 states the policy and defers the procedure to Evo 1, so the operative specification is
  in a different paper about a different corpus.
- ESM3-open's filter turns on a sequence-identity threshold that is never stated, and its
  keyword list is available on request rather than published.
- ESM-C's model card is shared byte-for-byte across model variants, so it cannot evidence any
  variant's training data.
- ESM3-open's card says "data related to viruses"; its paper says "sequences unique to
  viruses". These denote materially different sets.

None of that is misconduct; there is simply no standard for what a filter disclosure must
contain. Propose one, in the form of a minimum checklist — scope, predicate, thresholds,
annotation sources and versions, tool versions, validation performed, and which released
artefacts it applied to — then retro-fit it to all four models and report what is missing
against each.

This is the most durable output in the project. A leakage number ages; a disclosure standard
changes what the next model publishes, and it is derived from evidence rather than asserted.

Pair it with the obvious reciprocal obligation: publish our own filter specifications in the
same format, so the standard is demonstrated and not merely proposed.

---

## 8. Theory of change

Data filtering is being written into governance as a primary safeguard for biological AI
models, on the strength of developer self-assessment. This work asks three things in order: was
the filter even applied to the data it would need to cover, does the surviving capability track
homology, and could any filter have worked for this hazard at an acceptable cost.

The third question is the one governance actually needs answered. A reviewer asked to judge a
filter's adequacy has no criterion today. "How much did this filter leak" is the wrong
criterion, because for some hazard families the answer is irrelevant: no filter can remove the
capability without removing a large slice of general biology, and the right response is a
different control altogether. Separating those families from the ones filtering genuinely
protects is a usable standard, and nobody has drawn the line.

The measurement is cheap, public, repeatable and defensive. That is the point.

# Decisions

Append-only. Newest at the bottom. One entry per resolved ambiguity.

Add an entry whenever you make a call a later reader would otherwise have to
reverse-engineer: a proxy substitution, a threshold, a reading of vague policy prose, a model
or metric choice, a scope decision, or the opening of a gate.

`DESIGN.md` §A0 and §B1 both treat under-specification as a finding rather than an obstacle.
This log is what turns scattered judgement calls into a paper appendix instead of lost
context — several entries here are expected to be cited directly in the write-up.

## Entry format

```markdown
### D-00N — <short title>
- **Date:** YYYY-MM-DD
- **Task:** <task ID>
- **Context:** what was ambiguous, and why a choice was forced.
- **Decision:** what was chosen, precisely enough to reimplement.
- **Rejected:** the alternatives, and why not.
- **Consequence:** what this constrains downstream; whether it is a stated limitation,
  a finding in its own right, or neither.
```

Keep `Decision` precise enough that someone could reimplement from the entry alone. If the
decision has a threshold or parameter in it, the number goes in the entry.

---

### D-001 — Project management lives in AGENTS.md plus a generated task board
- **Date:** 2026-10-13
- **Task:** — (project setup)
- **Context:** `DESIGN.md` specifies the work but not how it is executed. The project needs
  sequencing, commitment-keeping and enough context per unit of work that it can be picked up
  independently. Three properties made a plain checklist insufficient: Phase B is meaningless
  without Phase A's output, several analyses must be pre-registered before results are seen,
  and publication is gated on disclosure.
- **Decision:** Process in `AGENTS.md`. One file per task in `tasks/`, with machine-readable
  frontmatter (`id`, `phase`, `status`, `depends_on`, `blocks`, `gate`, `design_ref`,
  `deliverable`, `owner`). `tasks/BOARD.md` generated from that frontmatter by
  `tools/board.py`, which also validates the graph. Fine granularity: 49 tasks at
  per-method level. Methodological commitments modelled as `gate: true` tasks that block
  downstream work. This append-only decisions log alongside.
- **Rejected:** Coarse per-phase tasks — too large to hand over without re-planning from
  `DESIGN.md`, and they hide the dependency structure that matters most here. A hand-maintained
  board — guaranteed to drift from the task files. GitHub Issues — the dependency graph and the
  gates are the valuable part, and both are easier to validate as files in the repo next to the
  code they govern.
- **Consequence:** Neither a finding nor a limitation; pure process. Note that `tools/board.py
  --check` is the mechanism by which gate and dependency violations are caught, so it belongs
  in CI from the first commit of real work (X1.1).

### D-002 — Environment pinned with pixi over conda-forge and bioconda
- **Date:** 2026-10-13
- **Task:** X1.1
- **Context:** `AGENTS.md` requires that a result regenerate from pinned inputs, and most
  of the Phase A toolchain (profile search, structural search, element detection,
  taxonomy assignment) is distributed via bioconda rather than PyPI. A Python-only
  lockfile would leave the compiled tools that produce the headline results unpinned.
- **Decision:** pixi, with channels `["conda-forge", "bioconda"]` and platforms
  `["linux-64", "osx-arm64"]`, lockfile `pixi.lock` committed. Two environments sharing
  one solve group: `default` (python 3.12 only) and `dev` (adds pytest, ruff). Phase A
  tools are added by the task that needs them, each with its own entry here recording the
  version choice — `pixi.toml` is deliberately not pre-populated with the toolchain, per
  §7 on scope creep. `PYTHONPATH` is set via `[activation.env]` so `import amazebio`
  works in every task and shell without a build step or an editable pip install.
- **Rejected:** uv + pip — fast for the Python side, but the compiled bioinformatics
  tools fall outside the lockfile, which is exactly where the Phase A results live.
  Docker/Apptainer — strongest guarantee and easiest for an external replicator, but
  heavier to iterate on against the weekend-scale §6 schedule; worth revisiting for the
  deliverable-7 reproduction artefact, where the audience is a replicator rather than a
  contributor. conda/mamba with `environment.yml` — covers bioconda but is not a true
  lockfile without conda-lock, so the pinning would be weaker than it appears.
- **Consequence:** Not a limitation of the study. One operational note: `pixi.lock` must
  be regenerated whenever `pixi.toml` changes, and CI runs `setup-pixi` with
  `locked: true` so a stale lock fails the build rather than silently diverging.

### D-003 — X1.1 cannot verify pipeline enforcement; criterion moved to A1.4
- **Date:** 2026-10-13
- **Task:** X1.1 (affects A1.4)
- **Context:** X1.1 was written with the done-criterion "seed convention is documented and
  enforced in at least one pipeline." No pipeline exists at X1.1 — it is the first task in
  the project — so the criterion was unmeetable as written. Marking it met would have been
  false; ignoring it would have lost the requirement.
- **Decision:** X1.1's criterion narrowed to what it can actually demonstrate: the seed and
  provenance convention is documented, importable and covered by tests. The enforcement
  requirement moved into A1.4, the first real pipeline, as both a step and a done-criterion
  (`run.json` manifest produced, parameters declared before results exist).
- **Rejected:** Writing a synthetic smoke pipeline at X1.1 purely to satisfy the criterion —
  it would have demonstrated the module against itself rather than against real work, and
  left a fixture pipeline in the repo with no result attached.
- **Consequence:** Neither a finding nor a limitation. Worth noting as a check on the task
  decomposition: this is the first case of a done-criterion that could not be met by its own
  task, and the fix was to move the criterion rather than to weaken it. Apply the same test
  when writing new tasks.

### D-004 — pixi.lock generated from a conda-channel copy of pixi; installer host blocked
- **Date:** 2026-10-13
- **Task:** X1.1
- **Context:** The cloud session's egress policy denies `pixi.sh` and the GitHub releases
  API, so pixi could not be installed by its documented route. `conda.anaconda.org` is
  reachable, and pixi is itself distributed as a conda package.
- **Decision:** Obtained pixi 0.81.0 from `conda-forge/linux-64` and used it to solve and
  write `pixi.lock`. The lock is therefore machine-generated by pixi itself, not
  hand-authored. Contributors and CI install pixi by its normal documented route; nothing
  about this workaround is baked into the repo.
- **Rejected:** Hand-writing `pixi.lock` — a fabricated lockfile is far worse than none,
  since it would claim a solve that never happened. Falling back to uv + pip — would have
  reversed D-002 for an environment-access reason unrelated to the project's needs.
- **Consequence:** No effect on the pinning guarantee: the lock is a genuine pixi solve
  against conda-forge and bioconda. Operational note for anyone working in this cloud
  environment: regenerating the lock here needs the same workaround, or the egress policy
  widened to allow `pixi.sh`.

### D-005 — Protein-level test model changed from ESM-C to ESM3-open
- **Date:** 2026-10-13
- **Task:** A0.1 (affects B1.1, B1.2, B2.*, B3.*, B5.*)
- **Context:** `DESIGN.md` v0.2 §B1 listed ESM-C as the viral-excluded protein-level test
  condition. Primary sources contradict this. The ESMC/ESMFold2 preprint
  (`10.64898/2026.06.03.729735`) lists "IMG/VR (release 7, Dec 19, 2022) — Cultivated and
  uncultivated viral genomes" among its training sources (p100) and states "Almost all viral
  sequences are metagenomic, largely derived from bacteriophages" (p14). Sixteen occurrences of
  "exclud" across 111 pages are all unrelated to data filtering; "select agent" appears zero
  times. The ESMC-6B model card's Training Data section names UniRef, MGnify and JGI with no
  exclusion. The model that does state a training-data exclusion is ESM3-open.
- **Decision:** ESM3-open (`esm3-sm-open-v1`) becomes the protein-level test condition. ESM-C
  is retained as a second viruses-included comparison, where its largely bacteriophage-derived
  viral content parallels the phage contrast Evo 2 provides at the nucleotide level.
- **Rejected:** Keeping ESM-C as the test condition — it would test a model for the effects of
  a filter it never had. Dropping ESM-C entirely — loses a useful phage-rich comparison for no
  saving, since the scoring harness covers it anyway.
- **Consequence:** `DESIGN.md` §B1 and the weekend-3 schedule row updated in v0.3. A finding in
  its own right: a published safeguard was mis-attributed to the wrong model in a design
  written from secondary sources, which is exactly what §B1 step 0 exists to catch.

### D-006 — Subject broadened to hazard-driven filtering, both mechanisms
- **Date:** 2026-10-13
- **Task:** A0.1 (affects A0.2, A0.3, A3.1, C1.1)
- **Context:** The two filters under audit are architecturally different. Evo 1 Appendix B.2
  removes IMG/VR records assigned to any of 19 named families or 12 named orders, plus records
  failing a host-occurrence rule — purely label-based. ESM3-open (ESM3 preprint Appendix A.6.1)
  seeds a denylist from UniProt viral annotation, then removes everything aligning to it by
  MMseqs2 above an unstated identity threshold, across PDB, UniRef, MGnify and JGI — a
  similarity-based filter. "Taxonomic filtering" describes only the first.
- **Decision:** The subject becomes hazard-driven data filtering, covering label-based and
  similarity-based mechanisms. The policy specification schema (A0.2) must express both.
- **Rejected:** Narrowing the audit to Evo only — would discard the half of the work with the
  most completely specified filter. Keeping the narrow framing while covering both anyway —
  the stated subject would not match the work done.
- **Consequence:** `DESIGN.md` §1, §0, §3 and HA updated in v0.3. Note for A0.2: a schema built
  only for clade membership cannot express ESM3-open's policy at all.

### D-007 — Phase A leads with filter scope, not leakage magnitude
- **Date:** 2026-10-13
- **Task:** A0.1 (affects A3.1, A4.3, A6.1)
- **Context:** The Evo eukaryotic-virus exclusion is a curation step applied to the IMG/VR
  viral component of the corpus (Evo 1 Appendix B.2). Evo 1 contains no mention of prophage,
  endogenous viral elements or proviruses across 47 pages. Evo 2 inherited the procedure
  unchanged ("As previously described") while adding 15,148 deduplicated eukaryotic reference
  genomes (~10.7T nt) whose curation is entirely assembly-quality and redundancy based — Mash
  dedup at distance < 0.01, centromere and short-contig removal — with no viral screening at
  any step. Evo 2's own Nature paper reports an SAE feature activating on annotated prophages
  in *E. coli*, viral-derived content learned from GTDB genomes the filter never examined.
- **Decision:** Phase A leads with the gap between what the filter was applied to and what the
  model was trained on, established from published methods. Survival quantification then sizes
  that gap. A new task A4.3 maps filter scope against corpus composition.
- **Rejected:** Leading with the measurement and treating scope as explanation — weaker, and
  it buries the part of the finding that needs no new bioinformatics to establish.
- **Consequence:** `DESIGN.md` §0, question A, the Phase A preamble and HA updated in v0.3.
  A3.1's route taxonomy must carry "outside filter scope" as a first-class route. This is the
  strongest Phase A result and it is also the most sensitive, so A3.3's independent
  verification applies to the scope claim too, not only to the counts.

### D-008 — Quotes are machine-verified against their sources
- **Date:** 2026-10-13
- **Task:** A0.1
- **Context:** A0.1's value is entirely in verbatim accuracy about what named laboratories
  published. The failure mode that would do most damage is a plausible paraphrase acquiring
  quote marks — a risk that applies with particular force to an agent working from training
  knowledge, since a model's recollection of a paper is exactly the secondary source §B1 step 0
  forbids relying on. Two concrete near-misses occurred while building the store: WebFetch's
  summarising model silently truncated a quote to fit a character limit, and a manual
  transcription rendered `≤` as `<=`.
- **Decision:** Quotes live in `policies/*.md` as blockquotes preceded by a `[source: ID]`
  marker. `tools/policies.py` extracts the cited source — PDFs included — normalises PDF
  typography (soft hyphenation, ligatures, curly punctuation, whitespace) and fails if the
  quoted wording does not literally appear, if a stored source's checksum has changed, or if a
  quote cites a source that was never retrieved. It runs in CI and via
  `pixi run -e dev policies-check`. `pypdf` is pinned in `pixi.toml` for it. Normalisation is
  unit-tested against near-miss pairs to confirm it does not fold away differences in wording.
  Source retrieval used raw `curl` rather than WebFetch, for the reason above.
- **Rejected:** Trusting care alone — the two near-misses above both happened under care.
  Committing extracted PDF text instead of the PDFs — adds a derived artefact that can drift
  from its source, and the extraction is cheap to redo. Normalising `≤` to `<=` to make the
  failing quote pass — that difference is wording, not typography, and folding it away would
  defeat the check.
- **Consequence:** `policies/captures/MANIFEST.json` is superseded by `policies/sources.json`,
  which carries stable citable ids, checksums and retrieval status in one place rather than
  duplicating provenance across two files. Three sources remain unretrieved and are recorded
  with the reason: the Evo 2 Nature Methods section, the ESM3 Science version of record, and
  the Biohub Platform Resources page (referenced in prose but never linked — itself an
  under-specification finding). A quote may not cite any of them, and the checker enforces it.

### D-009 — Leakage score replaced by the collateral cost curve
- **Date:** 2026-10-13
- **Task:** A0.1 prior-art check (retires C1.1, C2.1–C2.4, C3.1; adds C5.1–C7.1)
- **Context:** Phase C as specified fitted a predictor of retained capability to Phase B's
  measurements: a few dozen assays across three or four models, validated by holding out whole
  families and a whole model. Two problems. Statistically, honest intervals on a fit that small
  will be too wide to guide the decision the deliverable promises, and §C3 already conceded it
  was "a calibrated heuristic, not a precise predictor" — a reviewer applying it to a new filter
  extrapolates outside the fitted domain. Substantively, a leakage estimate answers the wrong
  question: it tells a reviewer how much one filter leaked, not whether filtering could work at
  all for the hazard in front of them. Phase A had already turned up the evidence that the
  second question is the live one — ESM3-open removed only sequences "unique to viruses",
  deliberately retaining virus-associated sequence with cellular homologs.
- **Decision:** Phase C becomes the collateral cost curve. For each hazard family, sweep filter
  stringency and compute hazard-removed against collateral-removed, giving a per-family curve
  and a regime classification: cheap, where filtering works, or catastrophic, where removing the
  capability requires deleting a large slice of general biology and no filter can work. Computed
  from public sequence and structure databases with no model trained, fine-tuned or run. The
  regime boundary is pre-registered before computing, as §B5 requires of its own threshold.
  C6.3 gates publication on an independent reimplementation, mirroring A3.3.
- **Rejected:** Keeping the predictor — fails its own validation honestly applied. Running both
  — the predictor's wide intervals would undercut the curve's cleaner claim, and the schedule
  does not hold both. Phase A alone — leaves the governance question unanswered when it is now
  answerable cheaply.
- **Consequence:** `DESIGN.md` v0.4 replaces §C1–C4 with §C5–C8, leaving a superseded-note so
  the deferred tasks' `design_ref` still resolves. Old Phase C tasks are `deferred`, not
  deleted, and detached from the live graph. **A new scope limit went into §4 before any of this
  work runs:** a per-family cost curve read uncharitably is a map of which hazards filtering
  protects least, so published results aggregate by homology class, per-family curves stay in
  the disclosure package, and nothing circulates before the disclosure window closes. Also a new
  §7 risk row: thin database coverage of a family must produce an abstention, never a cheap
  verdict.

### D-010 — Phase B narrowed to the homology check
- **Date:** 2026-10-13
- **Task:** A0.1 prior-art check (affects B2.2, B5.3)
- **Context:** The prior-art check found that ESM-C's developers have already published the
  comparison Phase B was built around. The ESMC/ESMFold2 preprint evaluates on 25 viral DMS
  assays from ProteinGym against ESM-2 650M and ESM3-open, with BLOSUM62 and EVMutation as
  non-neural baselines — the same benchmark, the same models, and the same kind of
  parameter-free baseline §B4 requires. Re-deriving it would consume most of the schedule.
- **Decision:** Phase B keeps what is new and what Phase C depends on: whether per-assay
  performance tracks homology to retained sequence. The published comparison is cited, not
  repeated. B2.2 is narrowed to establish first whether existing published collections already
  give sufficient n, and to extend only if they do not. B5.3's retention ratios now feed C6.2's
  premise check rather than a fitted predictor.
- **Rejected:** Keeping Phase B at full scope as independent replication — defensible in
  principle, but it spends the bulk of the remaining time re-deriving a published result.
  Cutting Phase B entirely — the cost curve's premise would then go untested, which is the first
  thing a reviewer will push on.
- **Consequence:** Deliverable 2 shrinks from a curated collection to an assay register reusing
  published collections where licensing allows. A side effect worth noting: the ESMC paper is
  now both prior art and a comparison point, so any Phase B result has a published number it
  should be consistent with — and a discrepancy would itself be a finding.

### D-011 — Four additions to Phase A, all built on the formalised predicates
- **Date:** 2026-10-13
- **Task:** design review (adds A7.1, A8.1, A9.1, X5.1)
- **Context:** A brainstorm after the prior-art check asked what would make a meaningful novel
  contribution. The answer turned on an asset the project had not been exploiting: A0 converts
  published filter prose into executable predicates, and nobody else has them. Four questions
  follow directly, none needing a GPU, a hazard list, or any capability measurement.
- **Decision:** Added to Phase A —
  **A7 conformance re-execution:** run each published predicate against the developer's own
  released corpus and diff. A surviving record that the authors' own rule should have removed is
  a conformance failure: a comparison of stated rule against delivered data, with no homology
  inference in it. A clean result is equally publishable and would be the first external
  confirmation that a stated filter was applied as described.
  **A8 filter agreement:** apply both predicates to one corpus and measure overlap. Low
  agreement would mean "we filtered viral data" does not denote a definite operation, which
  matters to any framework mandating it.
  **A9 safeguard decay:** replay the frozen 2024 denylist against successive taxonomy releases
  to derive a re-validation interval. A filter approved once does not stay approved.
  **§10 disclosure standard:** the minimum a developer must publish for a filter to be
  auditable, derived from what actually blocked this audit, retro-fitted to all four models, and
  applied to this project's own specifications.
- **Rejected:** A reference audit corpus with ground-truth route annotations — durable
  infrastructure, but more work than the others and its value depends on adoption; revisit after
  Paper 1. Training small controlled models for a causal result — the only way to get causation,
  but outside the compute and the §4 scope limits as written.
- **Consequence:** **Phase A becomes a paper on its own** and §6 now schedules two papers rather
  than one, which replaces "Phase A alone is publishable if Phase B slips" with a deliberate
  split. A new §7 risk row names the scope creep this creates and says what to cut first (A8
  before A7 or A9). A7 is gated on A1.1: a conformance claim against a proxy corpus is not a
  conformance claim. A3.3's independent reimplementation now covers the conformance numbers too,
  since a conformance failure is a stronger and more sensitive claim than a survival count.

### D-012 — Cost curve retained over the recommendation to park it
- **Date:** 2026-10-13
- **Task:** design review (C5.1–C7.1)
- **Context:** Having proposed the cost curve in D-009, I argued against it a day later in the
  same session. The objection: "collateral removed" counts sequences deleted, but the quantity
  that matters is useful capability lost, and the two are only connected by an untested
  assumption. Measuring the latter needs trained models, which the project does not have. So the
  curve's headline quantity is a proxy whose relationship to the real cost is unestablished, and
  a reviewer can reasonably say that deleting some fraction of a database may cost the model
  nothing. It also requires a hazard-family list, which is the one input that carries dual-use
  sensitivity in an otherwise low-exposure project. My recommendation was to park C5.1–C7.1
  until the C6.2 premise check came back strong enough to license them.
- **Decision:** The project owner elected to keep Phase C as specified in v0.4. Recorded here
  rather than re-argued. `DESIGN.md` is authoritative and this is a scope call that belongs to
  the owner.
- **Rejected:** Parking or dropping the cost curve, per the above — not adopted.
- **Consequence:** No change to the v0.4 Phase C specification or its tasks. Two things follow
  for whoever runs C6.2. First, the premise check is now load-bearing in a way it was not when
  the curve was uncontested: if capability does not track homology at usable strength, the
  curve's collateral metric has no established link to cost and the write-up must say so rather
  than presenting the curve as a criterion. Second, the proxy limitation belongs in the tool's
  own output and in the paper's limitations, stated as plainly as the coverage limitation in §C7:
  the curve bounds how much *data* a filter must remove, not how much *capability* that costs.
  The two-paper split in §6 means Paper 1 does not depend on any of this resolving.

### D-013 — Policy specs are YAML with declared scope and representable gaps
- **Date:** 2026-10-13
- **Task:** A0.2
- **Context:** The schema has to express two different machines (D-006): Evo's label-based
  pipeline over named families and orders, and ESM3-open's similarity-based removal against a
  seed set. It also has to survive the two things A0.1 found hardest — that the Evo filter was
  applied to one corpus component while the corpus grew around it, and that ESM3-open's
  threshold is never published.
- **Decision:** `src/amazebio/policyspec.py` defines the language; specs live in
  `policies/specs/*.yaml`. Three properties are structural rather than conventional:
  **scope is declared**, as a list of corpus components, so a record in an unfiltered component
  evaluates to `out_of_scope` rather than `retained` — the distinction A4.3 measures;
  **an unstated value is representable** via an `unspecified:` mapping carrying its reason, and
  any rule holding one evaluates to `undetermined`, so no guessed number can enter a result;
  **every rule cites a source id and locator** from `policies/sources.json`, and
  `tools/specs.py` fails if a rule cites a source that was never retrieved.
  Rules are an ordered pipeline, matching how the published procedures read. A reference
  evaluator over an in-memory record model pins the semantics and is covered by tests; the
  corpus-scale evaluator is A1.4 and the conformance diff is A7.1, and both consume these specs
  rather than reimplementing the semantics. Similarity rules consume precomputed alignment
  results, so this module never pretends to run an aligner.
- **Rejected:** JSON, to avoid a new dependency — these files are read by reviewers checking a
  predicate against quoted prose, and nested JSON with embedded multi-line quotes is not
  readable; `pyyaml` is pinned instead. Defaulting the unpublished threshold to a plausible
  value — it would convert an under-specification finding into a fabricated parameter, and the
  fabrication would propagate into every downstream number. Inferring scope from which rules
  mention which components — scope is the headline finding and deserves to be stated, not
  derived. Allowing a rule kind's meaning to change later — specs and results are version-pinned
  against these semantics, so A0.3 may add kinds but not redefine them.
- **Consequence:** Two worked examples are committed: `evo1-literal` (fully determined, scope
  `[IMG/VR]`) and `esm3-open-literal` (scope across all four training databases, and **not
  fully determined** — both rules depend on the unpublished threshold). The ESM3 spec is
  therefore unusable for a conformance diff until A0.3's readings supply a threshold range to
  sweep, which is itself the finding rather than a blocker. One test asserts the Phase A finding
  directly: the same Filoviridae record is `removed` in the viral component and `out_of_scope`
  in a host-genome component — what decides its fate is which file it was in, not what it is.

### D-014 — The three readings differ by scope and inference, never by denylist membership
- **Date:** 2026-10-13
- **Task:** A0.3
- **Context:** `DESIGN.md` §A0 requires each policy encoded three times — literal, charitable,
  strict — and treats the spread as the finding. "Strict" needed an operational meaning before
  anything was written, because the obvious reading of it (the largest filter the schema can
  express) would have meant extending the published denylists with clades of our own choosing.
  That would be untraceable, outside §4's limits, and would make the spread a measure of our own
  hazard judgement rather than of the policies' ambiguity.
- **Decision:** A reading may broaden only along axes the published words themselves leave open:
  which corpus components the policy reaches, whether a stated proxy or the aim behind it is the
  predicate, what counts as sufficient evidence to retain a record, which of a developer's two
  published descriptions governs, and what an unstated parameter is taken to be. Every taxon
  named in any of the six specs is quoted from its source; no reading adds one. Each rule carries
  the published wording its reading rests on in its `note`, and each file header states what the
  reading deliberately does not do. Two consequences worth recording: the strict Evo reading does
  not remove prophage, because IMG/VR is described in the source as curated prokaryotic viruses
  and phage retention is explicit and deliberate — and that retention is also Phase A's
  within-corpus contrast; and the IMG/VR quality and deduplication steps are carried unchanged
  into all three readings, so A0.4's spread isolates interpretive difference rather than mixing
  in a dropped curation step.
- **Rejected:** Extending the 19 families and 12 orders under the strict reading — unciteable,
  and it would convert an audit into an assertion of our own hazard list. Dropping the
  quality/dedup steps from the strict reading as "not hazard predicates" — defensible in itself,
  but it moves the surviving-record count for a reason that has nothing to do with the
  interpretation being tested. Making the charitable reading extend to corpus components whose
  published curation contains no viral screening step — reading authors charitably means taking
  their stated aim seriously, not crediting them with a procedure no source describes; component
  scope is the strict reading's axis, and keeping each difference on one axis is what makes the
  spread interpretable.
- **Consequence:** Three schema additions were needed and are additive only (A0.2 permits new
  rule kinds, not redefined ones): the rule kinds `remove_if_host_class_in`,
  `keep_if_host_evidence_exclusive` and `remove_if_element_detected`; a wildcard scope `["*"]`
  for a reading that holds a policy to the whole corpus, including components nobody enumerated;
  and an optional per-rule `components` list, because a corpus-wide policy still cannot apply a
  viral-taxonomy predicate to a bacterial genome record. A record that a wildcard-scope policy
  reaches but no rule removes is `retained`, not `out_of_scope` — examined and survived, which is
  a different claim and the one A4.3 needs. `remove_if_element_detected` consumes A2.3's
  detections; it detects nothing itself, exactly as the similarity rules consume alignments.

### D-015 — ESM3-open's unpublished threshold is read as a three-point range, not a value
- **Date:** 2026-10-13
- **Task:** A0.3
- **Context:** The identity threshold that determines the entire reach of ESM3-open's filter is
  never published — the paper says only "at or above a given sequence identity threshold". D-013
  kept the literal spec honestly `undetermined` rather than guessing, which is correct and also
  unusable: with no number the filter cannot be re-executed, and the ESM3 arms of A1.4, A7.1 and
  A8.1 cannot run at all.
- **Decision:** The three readings bound a sweep instead of naming a value. Literal stays
  `undetermined`. Charitable reads 0.70, on the only published figure anywhere in the source that
  ties sequence identity to the Viral Denylist: the authors used "> 70% sequence identity hits to
  the Viral Denylist" to define the held-out viral structure set they evaluated the filtered model
  on (S-ESM3-PREPRINT p69). Strict reads any detected alignment, encoded as 0.0 against a record
  model that carries only detected hits. Downstream tasks sweep that range and report across it;
  no task may describe any of the three as the developers' parameter. The charitable 0.70 is
  flagged in the spec and in `policies/specs/README.md` as the weakest inference in the
  directory, because the 70% cut defines an evaluation set rather than the filter.
- **Rejected:** Leaving all three readings undetermined — it preserves the finding but ships no
  usable predicate, and the under-specification is already recorded as a finding in its own right
  by the literal reading and `policies/esm3-open.md`. Picking a single conventional MMseqs2
  default (0.3 or 0.5) and proceeding — a fabricated parameter that would propagate into every
  downstream number with nothing published behind it. Treating the two denylists as having
  different thresholds — the source describes one matching step applied to both, so splitting
  them would invent a distinction the text does not make.
- **Consequence:** `esm3-open-charitable` and `esm3-open-strict` are fully determined, so the
  ESM3 arm of Phase A can run; `esm3-open-literal` remains the standing record that it should not
  have had to. A8.1's filter-agreement measurement inherits the range, so its results are
  reported per reading rather than pooled. If the published version of record (S-ESM3-SCIENCE,
  still unretrieved) states the threshold, this decision is superseded and the literal reading
  becomes decidable — which is worth re-checking before publication.

### D-016 — Two strict-reading rules withdrawn after independent review against the PDFs
- **Date:** 2026-10-13
- **Task:** A0.3
- **Context:** A0.3's own Steps require each reading reviewed against the A0.1 verbatim text
  before downstream use. Rather than a single read-through, the seven interpretive claims behind
  the four new readings were each put to two independent agents working from the preprint PDFs —
  one ruling on whether the published wording bears the reading, one attempting to refute that
  ruling, with instructions that this project's own evidence store and the specs' own notes are
  not authority for a verdict. Five claims survived. Two did not, and one survivor carried an
  encoding defect both passes found independently.
- **Decision:** Both failed rules are withdrawn from `evo1-strict`, and the defect is fixed.
  **The endogenous-element rule is gone.** It removed records carrying a detected endogenous
  viral element, retrovirus or provirus, on the argument that "genomic sequences from viruses that
  infect eukaryotic hosts" predicates on the sequence rather than the record carrying it. Evo 2's
  Figure S2 caption — the figure the p4 sentence cites as its own verification — says safety
  filtering removed "viral sequences that can infect eukaryotic hosts". The predicate is a
  capacity to infect, which a defective integrated relic does not have. And 16,704 eukaryotic
  reference genomes, the human reference among them, unavoidably carry such elements, so on the
  withdrawn reading the authors' own published claim would be false of the corpus they built; a
  reading on which a published claim is true of what was built beats one on which it is false.
  **`require_rank` returns to realm.** The raised rank was defeated twice: the authors printed the
  rank of every stop-taxon they named (two realms, two kingdoms, three phyla, one class, ceiling
  at class, no order and no family), and the published procedure carries a 12-order denylist
  precisely so order-resolved records are testable without a family — with deliberate family/order
  pairs showing they handled those records on purpose. A family requirement would have made their
  order denylist dead code. **The strict host rule carries `count: 2`.** Dropping it left a
  classification with a single prokaryotic observation removed by the literal reading and kept by
  the strict one, so the strict reading was not uniformly stricter and its claim to subsume the
  charitable host rule was false.
- **Rejected:** Keeping either rule relabelled as the audit's own sensitivity arm — defensible,
  and it would have kept the endogenous-element route executable for A2.3, but it costs the
  property that makes these specs worth anything: that every reading rests on published wording.
  An arm of our own construction belongs in a task of its own, declared as such. Also rejected:
  encoding the printed `r:`/`k:`/`p:`/`c:` prefixes in `stop_taxa` — they are the authors' rank
  annotations, not parts of the taxon names a corpus record carries, so putting them in the data
  would break matching; they are recorded in the rule's note instead.
- **Consequence:** The withdrawn element rule took its schema machinery with it —
  `remove_if_element_detected` and `Record.detected_elements` are removed, since nothing uses them
  and dead kinds in a contract are a liability. `keep_if_host_evidence_exclusive` now takes
  `count`. The strict reading keeps its corpus-wide scope while no rule reaches any component but
  the viral one, which is not a defect of the encoding: a eukaryotic genome record now evaluates
  to `retained` under the strict reading and `out_of_scope` under the literal one, and that gap is
  what A4.3 measures. Three findings came out of the review and belong to A0.4: the exclusion is
  stated five ways across the two papers and none resolves integrated viral-derived sequence; the
  published unspecificity parameter is an enumerated stop-list with an unquantified "including",
  not a rank threshold of any kind; and the charitable host rule should report its removals in two
  sets, those that would have failed the published count anyway and those removed despite clearing
  it, because only the second is contested. Two wording corrections: the ESM3 strict note's flat
  "It was not" overstated what the text supports, since the paper also says all hits were removed,
  and the charitable 0.70 is now framed as an upper bound the text licenses rather than a point
  estimate. D-015 stands as amended by that framing.

### D-017 — Released-vs-actual verdicts, and why they differ by model
- **Date:** 2026-10-13
- **Task:** A1.1 (gate)
- **Context:** §A1 and §7 make this the gate on corpus reconstruction: whether Phase A audits the
  real training corpus or a proxy sets how strongly every downstream claim may be worded.
  Evidence is in `policies/corpora.md`, every quote machine-checked against its source.
- **Decision:** Four verdicts. **Evo 2 — verified as published.** The data availability statement
  and the dataset card both state the released OpenGenome2 is the corpus used to train Evo 2, and
  the card distinguishes the FASTA sequences from the preprocessed form the model consumed.
  Nothing retrieved contradicts it. Byte-level identity between release and dataloader input is
  not established and is not establishable from published sources for any model in this audit, so
  the write-up states what was checked rather than implying more. **Evo 1 — procedure source, with
  a gap.** Evo 1 is where the only published exclusion procedure lives; its own availability
  section names source databases rather than a released artefact, while Evo 2 calls that corpus
  "previously published". The release artefact is not in `sources.json` and has not been
  retrieved, so this is recorded as an open item rather than resolved by assumption, and it should
  be closed before A7.1 runs. **ESM3-open — proxy only.** Its availability statement covers
  weights and code and says nothing about training data, so A1.3 must reconstruct from the stated
  databases and every ESM3 result carries that qualifier. **ESM-2 — reconstructible proxy**, and
  the best pinned of the four: no corpus release, but a pinned UniRef release plus published
  held-out cluster IDs, which makes it the cheapest first target for the A1.3 pipeline. ESM-C
  needs no verdict: no stated exclusion and no corpus release, so it enters only as a comparison.
- **Rejected:** Treating Evo 2's released dataset as unverified because byte-identity cannot be
  shown — that standard would fail every open model ever released and would discard the strongest
  auditable artefact in the field. Treating Evo 1's corpus as released on the strength of Evo 2's
  "previously published" — the artefact itself is unretrieved, and a dataset card nobody in this
  project has read is a secondary source. Recording one verdict for "Evo" — the procedure and the
  auditable corpus belong to different papers, and collapsing them would hide exactly that.
- **Consequence:** A7.1 is runnable for Evo, and better than expected: the released viral
  component is post-filter output while the filter's input, IMG/VR v4, is independently available
  at its pinned version, so the conformance check is a diff rather than an inference. Two things
  follow and are recorded in `policies/corpora.md` §2: the vOTU representative is not reproducible
  because no input order is published, so the diff must be computed at vOTU level or it measures
  our sort order; and whichever reading best reproduces the released component is the developers'
  de facto reading, which turns A0.4's spread into an estimate for Evo and is an argument against
  freezing any single reading as canonical before that number exists. For ESM3 no conformance
  re-execution is possible at all; the reported 10.6M removal count is the only published quantity
  a reconstruction can be checked against. **This gate stays closed.** AGENTS.md reserves opening
  a gate to the project owner; the verdicts are recorded here for that decision.

### D-018 — Corrections from re-reviewing the rewrites, and three errors of our own
- **Date:** 2026-10-13
- **Task:** A0.3
- **Context:** D-016 withdrew two strict-reading rules. The rewrites were put back through the
  same two-pass primary-source review, which refused both: not the withdrawals, which it upheld,
  but the prose arguing for them. Four errors, three of them ours rather than the sources'.
- **Decision:** All four corrected in place. **The formulation count was wrong.** The withdrawal
  block claimed the exclusion is stated five ways across the two papers; there are ten, and the
  typology was wrong too — only one formulation predicates on whole viral genomes, four on genomic
  sequences of or from viruses, two on a database subset or the dataset, one on IMG/VR host
  metadata, and two on a capacity or likelihood to infect. The ten are now enumerated with
  verified quotes in `policies/evo.md`, where the quote checker covers them, and A0.4 enumerates
  from there rather than restating a count. **An external premise was passed off as a reading.**
  "An endogenous element is in the ordinary case a defective relic that cannot infect anything" is
  true and appears in neither paper. It is now marked as an external biological premise, and the
  withdrawal's weight moved onto the leg that needs no such premise: the corpus contains
  eukaryotic genomes including the human reference, which carry endogenous viral sequence, so the
  withdrawn reading would make the authors' own published claim false of their own released
  corpus. **A claim about the denylists was false.** The rank note said requiring family would
  have made the published 12-order denylist dead code. It would not: Lefavirales and Piccovirales
  are denylisted orders contributing no family to the 19, and Ortervirales contributes only one of
  several, so the order list removes fully family-resolved records the family list alone would
  miss. Narrowed to the true claim — it would have made the order list redundant for the records
  it is best placed to catch. **A denominator came from an unretrieved source.** "Only two of the
  recognised virus realms appear, so the list cannot be read as anything at or above class" counts
  realms from ICTV, which this project has not retrieved. The claim is now that the text
  underdetermines the generalisation its own "including" invites, which is both weaker and sound.
  Two attributions were also softened: the purpose of the order denylist and the deliberateness of
  the family/order pairs are our inferences, not stated in Appendix B.2.
- **Rejected:** Letting the count stand as "approximately five" — the enumeration is cheap, it is
  the finding, and a count nobody checked is how the next error gets in. Keeping the dead-code
  claim in hedged form — it is false on the published lists, not merely unsupported, and hedging a
  false claim is worse than deleting it. Adding an ICTV release to `sources.json` to rescue the
  realm count — defensible later, but the argument does not need the number, and fetching a source
  to support a sentence already written is the wrong order of operations.
- **Consequence:** Both withdrawals stand; the arguments for them are now narrower and, in the
  element case, rest on the corpus rather than on a modal verb in a caption. The review also
  caught the eukaryotic genome count being used as corpus contents when 16,704 is the NCBI
  download and 15,032 is what survived dereplication — the same slip A1.1 found independently
  within the hour, from the same Methods paragraph, which is some evidence the two checks are
  genuinely independent. Standing lesson, worth more than the four fixes: every error here was in
  prose arguing for a correct decision. The decisions survived two adversarial passes; the
  reasoning did not. Write-ups should expect their supporting arguments to be the weakest part,
  and X1.4's quote checker will not catch any of this class, since none of it is a misquotation.

### D-019 — The Evo 1 corpus gap is closed, and the release exposes no viral component
- **Date:** 2026-10-13
- **Task:** A1.1 (gate)
- **Context:** D-017 left one open item: Evo 2 calls Evo 1's corpus "previously published" while
  Evo 1's own availability section names only source databases, and the release artefact was
  unretrieved. The project owner's instruction was to close that gap before opening the gate.
- **Decision:** Closed, with a finding attached. The artefact is at `LongSafari/open-genome`,
  located via the pointer in Evo 1's own repository README rather than guessed — the obvious guess
  under an `arcinstitute` namespace returns HTTP 401, which is worth recording because an error
  from a wrong URL is indistinguishable from an absent artefact unless you follow the paper's own
  pointer. Three sources are now stored at recorded checksums: the dataset card, the repository
  README, and a file listing of the release. The finding: **the release exposes no separately
  identifiable viral component.** Stage 1 is GTDB plus IMG/PR by both the card's configuration
  block and the file listing; no path at any depth corresponds to IMG/VR. What is *not*
  established is that the release contains no viral sequence — the three stage 2 parquet files are
  undifferentiated by source, so settling that needs their contents read rather than their paths
  listed, and the listing describes one dated revision.
- **Rejected:** Reading the card's configuration block alone as proof of absence — a config is not
  an inventory, and the file listing was one request away. Claiming the viral component was never
  released — the stage 2 parquets are opaque to a path listing and the claim would outrun the
  evidence. Storing the listing as though it were a document — it is dated and mutable, so its
  source entry says so and claims from it carry the revision and date.
- **Consequence:** A7.1's post-filter viral set must come from OpenGenome2's IMG/VR component,
  which its card names, not from OpenGenome v1. The conformance check in D-017 is unaffected — its
  input/output pair was always IMG/VR v4 against the Evo 2 release — but the audited *output*
  belongs to the Evo 2 release while the audited *procedure* belongs to the Evo 1 paper, and
  write-ups must not refer to "OpenGenome" as if the two releases were one artefact. Also
  recorded, since it bears on A4.3: Evo 1's repository describes OpenGenome as "a prokaryotic
  whole-genome dataset", which is consistent with a filter designed for a corpus that contained no
  eukaryotic genomes at all — the scope gap opens with Evo 2's additions rather than with Evo 1.
  The gate's open item is now discharged; opening the gate itself remains the project owner's call.

### D-020 — OpenGenome v1 does contain the viral component; the earlier conclusion is corrected
- **Date:** 2026-10-13
- **Task:** A1.1 (gate)
- **Context:** D-019 concluded that the v1 release "exposes no separately identifiable viral
  component", on the card's configuration block and a file listing, and left open whether the
  release contained viral sequence at all. The project owner asked for that settled, by reading
  the stage 2 files and by seeking Evo 1's version of record.
- **Decision:** The earlier conclusion is corrected. **Stage 2 is the viral component.** Sampling
  800 rows of `stage2/train` across eight offsets spanning all 2,652,947 rows: every sampled row
  carries an inline taxonomic lineage tag, and every tag is a viral realm — 696 Duplodnaviria, 104
  Monodnaviria, no prokaryotic or eukaryotic lineage, no Riboviria. The tag format uses the same
  rank prefixes as the stop-taxa in Evo 1's published rule. Most records resolve no deeper than
  class: 675 of 800 fill four ranks. Stage 1 is differentiated by a `record` field of GTDB and
  IMG/PR accessions. The sample is stored as S-OPENGENOME1-ROWS, holding lineage tags and counts
  only — no genomic sequence enters this repo — and its source entry states that it supports
  qualitative claims and no published proportion: 0.03% of rows, contiguous blocks rather than
  random, rows are context windows rather than records, one dated revision.
  **Evo 1's version of record remains unretrieved** and is now registered as S-EVO1-SCIENCE with
  its blockers: science.org 403, Europe PMC holds PMC12057570 but serves fullTextXML as 500 and
  marks the article not open access, and the PMC article page returns HTTP 200 while serving a
  reCAPTCHA challenge instead of content.
- **Rejected:** Letting the path-based conclusion stand with the open question appended — it read
  as "no viral component in the release", which is false, and a reader would have carried that into
  A7.1. Publishing any proportion from the sample, including the realm split — the sampling design
  does not support it. Downloading stage 2 in full to get exact counts — 16.9 GB against a fixed
  session disk allowance, for numbers that only become publishable under a sampling design this
  task does not need. Recording the PMC attempt as a success because it returned HTTP 200.
- **Consequence:** A7.1 improves. Evo 1's published procedure can be re-executed against Evo 1's
  own released corpus — input IMG/VR v4, output `stage2` — rather than borrowing Evo 2's release
  for the output, and the inline lineage tags are exactly the field the taxonomy rules consume. The
  three rules that need IMG/VR metadata rather than taxonomy — the high-confidence gate, the vOTU
  representative and the prokaryotic-host count — still cannot be checked from the release, since
  that metadata does not travel with the records; that limitation is now a property of the release
  rather than an assumption. Running the diff against OpenGenome2 as well stays worthwhile because
  the releases differ. Independently, the release refutes the strict rank rule withdrawn in D-016
  and D-018: `require_rank: family` would have removed 675 of 800 released records, about 84% of
  the sampled viral corpus, which the developers plainly kept. Two lessons worth carrying: a file
  listing answers questions about paths and not about contents, and in this session both an HTTP
  401 against a repository that does not exist and an HTTP 200 serving a bot challenge would have
  produced a wrong entry in this store if the status code had been trusted over the content.

### D-021 — The A1.1 gate is opened
- **Date:** 2026-10-13
- **Task:** A1.1 (gate)
- **Decision:** The project owner opened the gate. A1.1 is `done`; A1.2 and A1.3 are `ready`, and
  A7.1 follows A1.2. Evidence and verdicts are in `policies/corpora.md` with D-017, D-019 and
  D-020.
- **Qualifiers carried, not resolved:** the Evo 2 verdict rests on the developers' own statement,
  with no independent evidence of byte-level correspondence available for any model here; and
  Evo 1's version of record (S-EVO1-SCIENCE) is unretrieved, so revisit that entry if it names a
  deposit the preprint does not. Both were put to the owner before opening.
- **Consequence:** A1.2, A1.3 and A7.1 each carry a "Strength of claim" section stating the verdict
  that governs them, which is what A1.1's Done-when requires — so a downstream task cannot consume
  a corpus without the qualifier in front of whoever runs it.

### D-022 — The survival metrics and route taxonomy are frozen
- **Date:** 2026-10-14
- **Task:** A3.1 (affects A2.1–A2.5, A3.2, A3.3, A4.3, A7.1, C5.1)
- **Context:** `DESIGN.md` §A3 makes family-level survival the headline number and A3.3 must
  reimplement it by a second method before publication. `AGENTS.md` requires analysis specs fixed
  before results are inspected. Nothing had been detected yet, so this is the moment to fix them.
- **Decision:** `metrics/survival.md` is the authoritative, frozen specification, written to be
  reimplementable from that file alone so A3.3's second implementation need never read the first.
  `src/amazebio/survival.py` carries the machine-readable route taxonomy and a reference
  implementation of the metric definitions. Four substantive calls inside it:
  **1. Both family registries, reported separately, never pooled.** Pfam viral clans and RVDB each
  define their own family universe and the headline is reported once per registry. The project
  owner chose this over either registry alone. The denominator is a choice about where family
  boundaries fall, and reporting both turns our dependence on that choice into a measurement: a
  gap between the two registries is itself a finding, and pooling would average away the one thing
  the pair exists to show. Pfam alone biases survival upward by an amount Pfam cannot size;
  RVDB alone buys coverage at the cost of defending looser boundaries line by line.
  **2. Six routes, partitioning the detections.** `out_of_scope` is first-class per D-007, and is
  kept separate both from `retained_by_design` (a published decision, not leakage) and from
  `undetected` / `misassigned` (taxonomy's limits). `conformance_failure` is never merged into
  those two, because it is a claim about a named laboratory's implementation rather than about
  what taxonomy can do, and §7 holds it to a higher evidential standard. `unresolved` exists
  because A1.2 established that three of Evo 1's published rules cannot be checked from the
  released corpus; it is reported as its own row so a table never claims more evidence than
  exists. Element kind is a separate axis, cross-tabulated, never a route.
  **3. Wilson intervals at 95%, and the confidence level is part of the spec.** Family-level
  survival is expected near 0 or near 1, where the normal approximation strays outside [0, 1] and
  its width collapses to zero. Distribution summaries use a bootstrap percentile interval at a
  declared seed. M2 reports median and IQR rather than a mean, and M3 reports a per-family
  distribution rather than a pooled coverage figure.
  **4. Thresholds: A3.1 fixes the metrics, each A2 task fixes its own detector's threshold.** The
  metric is parameterised by a declared threshold set; A3.2 refuses to compute while any threshold
  is undeclared, and refuses one declared after a detection output exists — the discipline
  `amazebio.repro.run` already applies to pipeline parameters. Sensitivity to a threshold is
  reported as a curve over the declared value plus two bracketing values fixed at the same time,
  labelled as sensitivity analysis and never as the headline.
- **Rejected:** Raw sequence volume as the headline — it answers a question nobody is asking, since
  one good homolog teaches a fold; it disagrees with family survival in the direction that matters
  (a filter leaving one homolog per family scores 0.1% on bp and near 100% on families); and it
  tracks corpus composition, so the same filter scores better the larger the corpus grows, which
  inverts the actual finding. Volume ships as labelled context. Also rejected: folding
  `unresolved` into `undetected`, which would convert absent metadata into a measured blind spot;
  a single pooled diversity-coverage number, fragile at this sample size per §B5; and picking
  detector thresholds here, which would mean choosing bioinformatics parameters before the tools
  they belong to are pinned.
- **Consequence:** Every A2 detector emits `amazebio.survival.Detection` with exactly one route,
  so A3.2's breakdowns are a regrouping rather than a reinterpretation. Per-route survival figures
  do not sum to the overall figure, since a family can survive by several routes, and any table
  showing them must carry that sentence. Three properties keep a null visible and are tested:
  counts are zero-filled across the whole pinned universe, no minimum-count filtering of families
  is permitted, and an interval spanning the interesting range is reported as uninformative in the
  abstract rather than as a point estimate with the interval in a footnote. C5.1 inherits this
  route taxonomy for its cost metrics rather than defining a second one.

### D-023 — Spec quotations are machine-verified; case is significant, spacing is not
- **Date:** 2026-10-14
- **Task:** X1.4 (affects A0.3, A7.1, and every later quotation in this repo)
- **Context:** `tools/policies.py` verified every blockquote in `policies/*.md` against its cited
  source. The spec files quote the same published prose in rule `note:` fields and `#` headers,
  and nothing checked those — while the specs are what downstream tasks actually execute. A0.3
  verified its quotations by hand and found two errors that way: a changed capital and a
  transliterated `≤`.
- **Decision:** `tools/specquotes.py` verifies every quotation in `policies/specs/*.yaml`, wired
  into `specs-check` so CI runs it. 60 quotations are now checked. Three calls were needed:
  **1. Case is significant, and used to be folded.** `policies.normalise` lowercased both sides,
  so it could not catch the one class of error that has actually occurred here. Removing the fold
  immediately found a second instance nobody had noticed: `corpora.md` quoted Evo 2 with
  `nguyenetal.` and `thisincluded` where the source extracts `Nguyenetal.` and `Thisincluded`,
  and the file's own parenthetical blamed PDF extraction for losing capitals that extraction in
  fact preserves. Quote and note both corrected.
  **2. Spacing is not significant** (`policies.match_key`). PDF extraction from justified type
  runs words together — Evo 1's appendix comes out as `thoseonlyassigneduptothelevelof` — which
  had pushed `corpora.md` into quoting the mangled form and apologising for it. Spacing is layout,
  so it is folded for matching and a quotation may be written as the page reads. The cost is that
  a missing or added space is undetectable, which is not a difference in wording.
  **3. In a spec, a double-quoted span is a verbatim quotation.** Five spans were our own
  phrasing, a defined term, or words from an earlier draft wearing quote marks — among them
  `'curated prokaryotic viruses'`, which `policies/specs/README.md` had attributed to the source
  as a description of IMG/VR. Those are now single-quoted and excluded from checking. Quotations
  that cross sources carry an inline `[source: S-ID]` marker, reusing the markdown store's syntax;
  a marker is exact and does not fall back, so a wrong id fails as a wrong id rather than passing
  because the text happens to appear elsewhere in the file's sources.
- **Rejected:** Attributing every quotation strictly to its enclosing rule's source, as the task
  file proposed — faithful quotations legitimately cross sources within one note, so strict
  attribution failed on correct text. Requiring quotations to be written as extracted, matching
  `corpora.md`'s existing workaround — it makes specs unreadable and spreads a PDF artefact
  through the repo. Folding case to make the run-together Evo 2 quote pass — that would have
  discarded the check that found it. A regex extractor without the odd-mark guard: a naive pairing
  joins one quotation's closing mark to the next one's opening mark, which is the trap A0.3 hit.
- **Consequence:** A quotation that drifts from its source now fails CI in both stores. Three
  extraction classes are handled and tested: multi-line `#` comment blocks, folded block scalars,
  and fragments quoted mid-sentence, where a sentence-initial capital is tolerated on the first
  character only. `policies/specs/README.md` and `policies/README.md` carry the convention, since
  the check only stays honest if the next writer knows which quote character means what. Tests
  pin both of A0.3's hand-found errors as regressions, and a deliberately corrupted quotation is
  shown to fail.

### D-024 — ESM-2's corpus is UniRef 2021_04; 2021_04 is canonical, the current release is a proxy
- **Date:** 2026-10-14
- **Task:** A1.3 (corrects A0.1's pin; qualifies A1.1's carried verdict)
- **Context:** `policies/esm2.md` pinned ESM-2 to the UniRef 2018-03 release, inferred from the
  held-out split files, and A1.1's verdict carried into A1.3 described ESM-2 as "a pinned UniRef
  release plus published held-out cluster IDs" and "the cheapest corpus here and the right first
  target". Verifying that from the primary source before downloading anything showed the pin is
  attached to the wrong release.
- **Decision:** ESM-2's corpus is the **UniRef50 2021_04** clustering with training sequences
  sampled from UniRef90 members, per the repository's own model table: every ESM-2 checkpoint
  reads `UR50/D 2021_04`, and the overview row reads `UR50 (sample UR90)`. 2018-03 is the release
  the split files use, and the same table attaches it to ESM-1 and ESM-1b. `policies/esm2.md` is
  corrected. On what to acquire, the project owner chose: **2021_04 is the canonical pin, with the
  current per-tier release available as an explicit proxy mode** that stamps every output with the
  stated-vs-used gap. The acquisition pipeline pins 2021_04 by its published md5
  `444f0a7062a65a988ba1d5949d1d6419` and the release notes' composition (UniRef50: 49,874,565
  clusters), so the pin is exact whether or not the bytes are local.
- **Rejected:** Keeping the 2018-03 pin — it is a fact about the evaluation split, not the training
  corpus, and ESM-2 is the positive control that every Phase B comparison rests on. Carrying the
  published split files into an ESM-2 reconstruction — UniRef50 cluster IDs are not stable across
  releases, so those IDs identify held-out clusters in a release ESM-2 never saw; **no held-out
  split is published for ESM-2's own release**, and treating the 2018-03 IDs as if they transfer
  would silently contaminate any held-out claim. Guessing what `UR50/S` and `UR50/D` mean — the
  suffixes are never defined in the retrieved documentation, and the difference decides whether a
  reconstruction holds one representative per cluster or a per-epoch sample from each, so it is
  logged as under-specification per §A0 and needs the ESM-2 paper, which is not a retrieved
  source. Pinning the current release alone — nothing in the repo would then point at the version
  the model actually used. Streaming the stated bundle inside a cloud session — the archive serves
  2021_04 only as a single 158 GB `uniref2021_04.tar.gz` with no per-tier files, and its first
  member is a 93.7 GB `uniref100.tar`, so UniRef50 sits tens of gigabytes into the stream, against
  a fixed session disk allowance of about 30 GB.
- **Consequence:** A1.3's ESM-2 track is no longer the cheap first target A1.1 expected; the pin is
  exact but the bytes need a machine that can hold the bundle, so the acquisition script is the
  deliverable in this repo and the staging runs where there is disk. A1.1's ESM-2 verdict should be
  read with this correction attached: the pinned release survives, the usable held-out split does
  not. B1.2 and B4.2 are affected — a held-out evaluation on ESM-2 cannot cite published cluster
  IDs at the matching release, and any such claim needs its own construction and its own
  limitation. Nothing here changes the ESM3-open verdict: that corpus remains proxy-only.

### D-025 — `UR50/D` means cluster members, read from the paper that defines the notation
- **Date:** 2026-10-14
- **Task:** A1.3 (closes the under-specification D-024 left open)
- **Context:** D-024 pinned ESM-2 to `UR50/D 2021_04` and logged `UR50/S` versus `UR50/D` as
  under-specification, because no retrieved source defines the suffixes and the difference decides
  whether a reconstruction holds one representative per cluster or members of each. D-024 said that
  needs the ESM-2 paper. It does not: the notation is defined in the lab's earlier ESM-1b paper,
  which is open access.
- **Decision:** **`/S` is sparse — the UniRef50 representative sequences. `/D` is dense — members
  drawn evenly across the UniRef50 clusters.** From Rives et al. 2021 (PNAS, version of record),
  now stored as `S-ESM1B-PNAS`: the three pretraining datasets are UR100 (UniRef100
  representatives), UR50/S (UniRef50 representatives) and UR50/D (UniRef100 sequences sampled
  evenly across the UniRef50 clusters). The definition is applied to ESM-2's table only because
  that table demonstrably uses the same notation: its `esm1_t34_670M_UR100`, `_UR50S` and `_UR50D`
  rows are the paper's three datasets one for one, and its `UR50/S 2018_03` row for
  `esm1b_t33_650M_UR50S` matches the paper's statement that ESM-1b was trained on UR50/S. So **A1.3 stages UniRef50 clusters with their UniRef90 members and membership
  preserved, not the 49,874,565 representatives.** Two residual gaps stay logged rather than
  guessed: the definition samples UniRef100 members where ESM-2's own overview row reads
  `UR50 (sample UR90)`, so the suffix carries the mechanism and the table carries the tier, and
  the table wins; and whether "evenly" is a per-epoch redraw, with what seed, is unstated in both
  papers.
- **Rejected:** Waiting for the ESM-2 paper — bioRxiv rate-limits every path to it (HTTP 429,
  Cloudflare 1015) and the Science version is paywalled, both now recorded as `S-ESM2-PREPRINT` and
  `S-ESM2-SCIENCE` with their blockers; the notation would not be defined there anyway, since it is
  inherited. Reading `/D` as "deduplicated" or `/S` as "sequences" — plausible expansions, and both
  wrong, which is exactly why D-024 refused to guess. Staging representatives and noting the
  difference as a limitation — that is a different dataset, not a qualified version of this one, and
  ESM-2 is the positive control every Phase B comparison rests on. Treating the paper's UniRef100
  as authoritative over ESM-2's own `sample UR90` row — a definition from an earlier paper cannot
  override the model's own documentation on a point that documentation addresses directly.
- **Consequence:** Changes what A1.3's acquisition pipeline must produce: cluster membership and
  UniRef90 member sequences, so the extraction covers the `uniref50` and `uniref90` members of the
  2021_04 bundle rather than UniRef50 alone, and the composition table reports members as well as
  clusters. Raises the staging cost again — D-024 had already withdrawn A1.1's "cheapest corpus"
  expectation, and this confirms ESM-2 as the most expensive of the four. The two residual gaps are
  §A0 findings about ESM-2's documentation, not obstacles: the suffix a model card leads with is
  defined only in a different paper about different models. `policies/corpora.md` §6 carries a
  pointer to both corrections, since A1.1's verdict predates them.

### D-026 — the 2021_04 bundle is staged by streaming, and the archive is kept verbatim
- **Date:** 2026-10-14
- **Task:** A1.3
- **Context:** D-024 recorded that staging UniRef 2021_04 needs a machine with roughly 300 GB of
  disk, and that the pipeline could only run in proxy mode until that and credentials existed. The
  project owner provided an S3 bucket in the project account instead, on free tier. 300 GB of local
  disk turns out not to be needed: the archive's HTTP endpoint advertises `Accept-Ranges: bytes`, so
  the compressed stream is resumable, and measured pull rate is 86.7 MB/s.
- **Decision:** **Stage by streaming in one forward pass, with nothing buffered to local disk**, and
  **keep the released archive verbatim alongside the extracted tiers.** The pass pulls the 169 GB
  `.tar.gz`, forks the compressed chunks to one upload while gunzipping the same chunks to extract
  `uniref50` and `uniref90`, and verifies the whole stream against the published md5
  `444f0a7062a65a988ba1d5949d1d6419`. UniRef100 — 87.3 GiB of the archive, and nothing Phase A uses —
  is pulled past and discarded rather than stored. Destination is
  `s3://amazebio-corpora-897641797669/corpora/uniref/2021_04/`.
  Three consequences worth stating, since each is a commitment rather than an implementation detail:
  **the retained archive is abandoned unless the md5 matches**, including when a run ends early and
  so cannot distinguish "unverified" from "wrong" — the bucket withholds `s3:DeleteObject`, so a
  completed upload is irreversible, and an object claiming to be a release it has not been shown to
  be is worse than no object. **Analysis runs on EC2 in us-east-1**, decided together with this, so
  reads of the staged corpus are same-region and free; a full pass from outside AWS would cost about
  $6.80 in egress each time, which argues for reducing in-region and shipping only the result out.
  **Storage runs past the free allowance by design**: ~245 GB against 5 GB free, about $5.50/month,
  accepted with those figures stated.
- **Rejected:** Waiting for a 300 GB machine — unnecessary once the stream proved resumable, and it
  was the stated blocker holding A1.4, A4.3, A8.1 and C5.2. Staging the extracted tiers only, at
  about $1.60/month — cheaper, but the extracted tiers have no published checksum of their own, so
  the pin would rest on a URL that may not outlive the project; the archive is the only artefact
  whose md5 the release publishes. Storing UniRef100 as well — it triples the bill to retain the one
  tier D-025 establishes is not the corpus. Downloading the archive twice, once to keep and once to
  extract — the fork costs nothing and the second pull costs 169 GB.
- **Consequence:** D-024's "proxy mode only" condition is lifted for ESM-2: the corpus is staged at
  the stated version, verified against the release's own checksum, so ESM-2 results no longer carry
  the acquisition proxy qualifier. A1.1's "cheapest corpus" expectation stays withdrawn — the pin is
  exact and the bytes are still the most expensive of the four. One finding came out of the pass
  itself and is recorded in the task file: **the release bundles XML, not FASTA**, which happens to
  suit D-025, since UniRef XML states cluster membership explicitly rather than leaving it to be
  reconstructed.

### D-027 — ESM-2's corpus is staged and verified against the release's own md5
- **Date:** 2026-10-14
- **Task:** A1.3
- **Context:** D-024 pinned ESM-2 to UniRef 2021_04 but could only do so from the release notes,
  with the bytes out of reach; D-026 settled how to acquire them. Until a run actually matched the
  published checksum, every ESM-2 result had to carry an acquisition proxy qualifier.
- **Decision:** **The qualifier is dropped for ESM-2.** One streaming pass read all
  169,188,630,923 bytes of `uniref2021_04.tar.gz` with zero reconnects, and the md5 over the whole
  stream is `444f0a7062a65a988ba1d5949d1d6419` — the value UniProt publishes for that release. The
  staged corpus is therefore the released bytes, not a reconstruction resembling them, and
  `artifacts/a1-3/run.json` records `verified: true` as the evidence. Staged at
  `s3://amazebio-corpora-897641797669/corpora/uniref/2021_04/`: `uniref50.xml.gz` (25,107,210,941
  bytes), `uniref90.xml.gz` (50,350,462,472 bytes), and the archive verbatim (169,188,630,923
  bytes). 244.6 GB in total, about $5.63/month.
- **Rejected:** Nothing was rejected here — this entry records a verification outcome rather than a
  judgement call. It is logged because the distinction it settles, between a corpus that matches
  the release and one that merely claims the same version, is exactly what §7 requires an
  adversarial reader to be able to check, and because the wording of every downstream ESM-2 claim
  depends on it.
- **Consequence:** A1.3's remaining work is no longer acquisition. The composition check is the open
  piece: `amazebio.uniref.composition_check` compares counted clusters against 49,874,565 for
  UniRef50 and 138,515,945 for UniRef90, and nothing counts them yet. Counting means parsing the
  staged XML, which D-026 says should run in us-east-1. Note the release ships **XML only, no
  FASTA**, which suits D-025: UniRef XML states cluster membership explicitly.
  One caveat for whoever reads the bucket: it also holds four 0-byte objects — the two nested
  container tars, which matched their own tier filter and uploaded empty before the filter was
  fixed, and a `.probe` from verifying bucket access. The bucket withholds `s3:DeleteObject`, so
  they are permanent. They are not part of the corpus.

### D-028 — ESM-2's paper confirms the 2021_04 pin, contradicts itself on the date, and shows the training set is a filtered subset
- **Date:** 2026-10-14
- **Task:** A1.3
- **Context:** D-024 pinned ESM-2 to UniRef 2021_04 from the repository's model table, and D-025
  read `UR50/D` from an earlier paper about different models, both because ESM-2's own paper was
  unretrievable (bioRxiv HTTP 429). It is now retrieved (S-ESM2-PREPRINT): the host rate-limits
  bursts rather than sustaining a block, so one request every few minutes succeeds.
- **Decision:** **The pin stays at 2021_04, and the paper's own date statement is recorded as a
  contradiction rather than resolved.** The dataset appendix says "UniRef50, September 2021
  version", and no UniProt release is dated September 2021 — 2021_01 is 10-Feb, 2021_02 07-Apr,
  2021_03 09-Jun, 2021_04 27-Oct — so a September download would have been 2021_03. Against that
  single bare date stand three first-party statements: the model table's `UR50/D 2021_04`, the
  paper's own "when 2021 04 was the most recent release" describing its filtering, and its
  "138 million UniRef90 sequences", which is 2021_04's 138,515,945 and not 2021_03's 135,301,051.
  The weight of evidence is 2021_04 and the staged corpus is correct.
  **D-025's two residual gaps are closed.** The paper states the mechanism directly: a minibatch of
  UniRef50 sequences is sampled per training update, and each is replaced by a sequence drawn
  uniformly from the corresponding UniRef90 cluster. So members come from UniRef90 — confirming the
  model table's `sample UR90` over the ESM-1b paper's UniRef100, which is how D-025 called it — and
  "evenly" means per-update uniform resampling, not one draw. Only the seed is unstated.
  **ESM-2's training set is not the release.** 2021_04 holds 49,874,565 UniRef50 clusters; the paper
  trains on "43 million UniRef50 training clusters". Of that ~6.9 million difference the paper
  itemises roughly 310,000 — a 0.5% validation split (≈250,000), 1,027 sequences annotated
  "artificial sequence", and 58,462 proteins returned by a jackhmmer search around 81 curated
  de-novo proteins. The remainder falls to one unquantified step: removing training sequences
  matching a validation sequence at 50% identity under a stated MMseqs search. Method and
  parameters are published; magnitude is not, and the inputs — the validation split and the 81
  de-novo queries — are not published at all.
- **Rejected:** Repinning to 2021_03 on the strength of "September 2021" — it is one unsupported
  date against three corroborating statements, one of which is a release-size figure that matches
  2021_04 to within rounding and misses 2021_03 by over three million. Treating the contradiction
  as a typo and not recording it — §A0 makes under-specification a result, and a reader checking
  the paper will hit the same sentence and needs to find it already addressed. Attempting to
  reconstruct the training subset now — not possible from published material, and a scope question
  for the project owner rather than a judgement to make mid-task.
- **Consequence:** A1.3's staged corpus is the **release**, and ESM-2's **training set** is a
  filtered subset of it that cannot be reproduced exactly. Every downstream claim must say which of
  the two it is about; they differ by about 14% of clusters. Phase B comparisons that assume ESM-2
  saw the whole release are wrong by that margin. One further point worth stating plainly, because a
  write-up could easily get it backwards: that de-novo filter *is* exclusion-based data filtering,
  with reproducible parameters and a stated purpose, though the purpose given is enabling future
  generalisation work rather than biosecurity. ESM-2 remains the positive control — it carries no
  biosecurity exclusion — but it is not unfiltered, and describing it as unfiltered would be false.
  Also: S-ESM2-PREPRINT's sha256 does not reproduce, because biorxiv.org stamps the download time
  into the PDF's XMP metadata. Established by diffing the capture against an independently obtained
  copy — 30 bytes differ, all in ModifyDate and MetadataDate, extracted text identical — so a hash
  mismatch on re-fetch is expected and is not evidence of tampering.

### D-029 — A1.3 stages the release, not ESM-2's filtered training set
- **Date:** 2026-10-14
- **Task:** A1.3
- **Context:** D-028 established that ESM-2's training set is a filtered subset of UniRef50 2021_04
  — about 43 million clusters against the release's 49,874,565 — and that the filter cannot be
  reproduced exactly, because the validation split and the 81 curated de-novo query proteins are
  unpublished. That left a scope question A1.3 could not settle itself: which of the two is "the
  corpus" this audit reconstructs.
- **Decision:** **The release.** A1.3 is complete with UniRef50 2021_04 as published, and the ~14%
  gap to ESM-2's training set is carried as a documented limitation rather than chased. Every
  downstream claim states which of the two it concerns.
- **Rejected:** Reproducing the filter from what the paper specifies — the MMseqs 50%-identity
  removal and the 1,027 "artificial sequence" entries are reproducible, but the validation split
  that the MMseqs search runs against is not published, so the output would be an approximation
  whose error cannot be bounded. An approximation of unknown accuracy is worse than a known 14% gap,
  because the gap can be stated and the error cannot. Asking the authors for the filter inputs —
  defensible, and a refusal would itself be a finding about reproducibility, but it is external
  contact and §4's disclosure requirement plus gate X3.1 govern what may be said to whom; not a
  call to make inside a staging task.
- **Consequence:** Closes A1.3's scope. The limitation belongs in the Phase A write-up, not just in
  this log: a reader comparing our corpus against ESM-2's behaviour needs to know the corpus is the
  release and the model saw roughly 86% of it, with the missing portion selected by similarity to an
  unpublished validation split rather than at random. That last point matters more than the
  percentage — the excluded clusters are not a uniform sample, so the gap is not simply noise.

### D-030 — A1.3 closes on ESM-2; ESM3-open's corpus becomes A1.5
- **Date:** 2026-10-14
- **Task:** A1.3 → A1.5
- **Context:** A1.3 was scoped to "the protein-model corpora", plural, and its Done-when requires
  the stated-versus-used gap recorded *per model*. ESM-2 is finished to a standard nothing else in
  the project has yet reached: the archive verified against UniProt's published md5 across all
  169,188,630,923 bytes, and both tiers counted exactly to the release notes' 49,874,565 and
  138,515,945. ESM3-open's proxy corpus is not started. Leaving A1.3 open would block A1.4 on work
  that is a different problem, and marking it done silently would leave four downstream tasks
  depending on a corpus nobody staged.
- **Decision:** **Split rather than widen or shrink.** A1.3 is `done` for ESM-2. ESM3-open's corpus
  is now **A1.5**, `ready`, depending on A1.1 and blocking A1.4 and A4.3. The split follows
  AGENTS.md: a task that turns out to be two tasks becomes two files, not a quietly redefined one.
  It is a split rather than a scope reduction because ESM3-open is a different kind of problem —
  there are no pinned bytes to acquire, so the work is establishing what ESM3 states at all, and
  A1.1 already fixes the answer as proxy-only.
  **Which downstream tasks A1.5 blocks was a judgement call and should be challenged if wrong.**
  A1.4 runs the three readings "against each staged corpus", so it needs every corpus including the
  ESM3 proxy. A4.3 needs per-model corpus composition to state what fraction was never a candidate
  for removal. A8.1 applies both filters to "one common corpus", which the staged UniRef satisfies,
  so it is not blocked and is now `ready`. C5.2 indexes homology neighbourhoods across sequence
  space and is not model-specific. The board's reverse edges were corrected to match, and
  `tools/board.py --check` passes on 62 tasks.
- **Rejected:** Holding A1.3 open until ESM3-open is staged — it would block A1.4 and A4.3 on
  finished work, and a task that stays open because part of its title is unaddressed teaches the
  board to be ignored. Marking A1.3 done and leaving ESM3-open unrecorded — the §A0 finding about
  ESM3's unstated versions is a result the project wants, not an oversight to drop; it would simply
  have vanished. Renumbering A1.3 or editing its title to say "ESM-2" — IDs and titles are cited
  from commits and write-ups.
- **Consequence:** Six tasks are now ready, including A1.5 and A8.1. The contrast between ESM-2 and
  ESM3-open is itself a reportable asymmetry and A1.5's file carries the warning: ESM-2's corpus
  carries no acquisition qualifier, nothing in A1.5 can reach that standard, and a write-up must
  not place the two side by side as though it could.

### D-031 — A1.2 stages the filter-relevant components only, from the FASTA representation
- **Date:** 2026-10-14
- **Task:** A1.2
- **Context:** Both Evo corpora are released and A1.1 verified them as published, so there was no
  acquisition question — only a scope one. OpenGenome2 is 5.52 TB across 1,126 files, published
  twice over: a `fasta/` tree and a `json/` tree holding the same sequences. The corpus bucket
  withholds `s3:DeleteObject`, so anything staged is permanent spend, which makes the scope call
  irreversible and therefore the project owner's rather than a worker's. Four options were costed
  from the pinned manifests and put to the owner: the filter-relevant components (144 GB,
  ~$3/month), those plus the metagenomic component (396 GB, ~$9), all of one representation
  (2.88 TB, ~$66), or both representations of everything (5.67 TB, ~$130).
- **Decision:** **The filter-relevant tier, in the FASTA representation, pinned to commit SHAs.**
  Twelve files, 134.2 GiB, about $3.32/month: Evo 2's IMG/VR viral component, IMG/PR plasmids, GTDB
  prokaryotic genomes, promoters, ncRNA and organelles, plus Evo 1's `stage2` viral component.
  Three parts of this are commitments rather than implementation detail.
  **The representation choice is evidence-driven, not a preference.** The FASTA viral records carry
  `IMGVR_UViG_*` source accessions; the JSON viral records carry a bare `text` field with no
  accession and no lineage tag — the component is literally named `imgvr_untagged`. A7.1 diffs
  released viral records against IMG/VR v4, and a record with no accession cannot be diffed, so the
  JSON could not do the job at any price. Staging both would have doubled a permanent cost to hold
  a copy that cannot support the claim. Both representations still appear in the composition table:
  unstaged is not the same as not corpus.
  **The pin is a commit, not `main`.** Both releases have moved since publication. All 1,123 of
  OpenGenome2's sequence files were last touched on 2025-02-17/18 alongside the preprint and none
  has changed since, so the pinned revision carries publication-time sequence content — but that is
  a fact established from the commit history, not something `main` guarantees.
  **Verification gates the upload, not the other way round.** Each file is hashed as it streams and
  `complete_multipart_upload` is called only once the digest matches the SHA-256 the release
  publishes for that file; a mismatch aborts and writes nothing. With no delete, that ordering is
  the only chance to not write the wrong bytes — the same commitment D-026 made for UniRef.
- **Rejected:** Staging all of one representation (2.88 TB, ~$66/month) — it would cover A2.3's
  eukaryotic component, but A2.3 is not started and deferring costs only a second resumable pass
  over one named component, against a twentyfold standing bill from now until the project ends.
  Both representations (5.67 TB, ~$130/month) — the extra copy is the untraceable one.
  Pinning `main` — it has moved twice since publication and would move again.
  Staging the eukaryotic and metagenomic components "while we are here" — that is scope creep with
  a monthly invoice, and AGENTS.md names scope creep as a live risk.
  Deciding the cost unilaterally the way D-026 did at ~$5.50/month — the span here was $3 to $130
  and the write cannot be undone, so it was not a worker's call.
- **Consequence:** A1.4, A4.3 and A7.1 have the nucleotide corpora they need, and A7.1 in
  particular can now run as a real diff: pinned input (IMG/VR v4 at its own publisher) against
  pinned, accession-bearing output. **A2.3 and A4.1 must each stage their own component before
  they can run** — 2.17 TB of eukaryotic genomes and 252 GB of metagenomes respectively. That is a
  known, named, resumable pass with the tier flag already in the code, not a redesign, and whoever
  picks those tasks up should expect to re-ask the cost question for their component.
  Two things found along the way are recorded in `policies/evo.md` §7–8 rather than here, because
  they are observations about the releases and not decisions: the published procedure's subject is
  0.2% of OpenGenome2 against 82% eukaryotic genomes the filter never saw, which is DESIGN.md
  §A1's scope gap measured; and Evo 1's inline lineage tags appear not to have survived into Evo
  2's release, on a four-file sample that A7.1 will settle properly.

### D-032 — A1.5's premise was wrong: ESM3 states its releases, and the gap is elsewhere
- **Date:** 2026-10-14
- **Task:** A1.5
- **Context:** A1.5's file, written when A1.3 split (D-030), said: "The paper names PDB, UniRef,
  MGnify and JGI without versions, so expect the §A0 under-specification finding to be most of the
  result." That came from the filter appendix, whose scope sentence does name four databases and no
  versions. The pretraining-data appendix two pages earlier states a release for every component,
  and Table S3 tabulates them. Taking the task's premise on trust would have produced a finding
  that is false and that an adversarial reader checks in one minute.
- **Decision:** **Record the correction as the first result, and relocate the under-specification
  finding to the four places it actually sits.** All eight components carry a stated release.
  UniRef 2023_02 and MGnify 2023_02 are exact releases still served with a publisher checksum, so
  two of ESM3's components are pinnable to the standard A1.3 reached for ESM-2. What is unstated
  is: (1) which UniRef *tier* was parsed, across which the component varies 5.8-fold; (2) whether
  "MGnify90" means the released 90% product or the full protein set behind it; (3) JGI's pin, which
  is a date — given as July 31st in prose and July 30th in Table S3 — over a set whose membership
  changes, with no snapshot; (4) whether the filter reached OAS, AlphaFoldDB and ESMAtlas, which its
  scope list does not name. Written up in `policies/esm3-open.md` §6-8, with the component table and
  the arithmetic in `src/amazebio/esm3.py` and `tools/esm3_composition.py`.
- **A second finding falls out of the arithmetic, and it costs us something.** ESM3's stated corpus
  sizes are 14.7M (UniRef, against UniRef90's 170,669,877) and 108.2M (MGnify, against the release's
  729,215,663 clusters at 90%) short of the releases they name. Each gap alone exceeds the 10.6M
  sequences the filter is reported to have removed across every component together. The cause is not
  decidable from published text — ESM3 re-clusters with its own mmseqs flags, which is sufficient to
  explain a different cluster count, and so is removal the filter description omits. `corpora.md` §5
  had proposed sweeping the unpublished threshold until a reconstruction reproduced 10.6M, as the
  nearest available substitute for a conformance re-execution. **That proposal is withdrawn.**
  Tuning a threshold to hit a figure that cannot be reconciled with the corpus it was measured on
  would be fitting to a number that does not mean what the sweep assumes. For ESM3 there is no
  substitute for a conformance re-execution, and the write-up says so.
- **Rejected:** Keeping the task file's premise and reporting "versions unstated" — false, and §7
  requires Phase A to survive a motivated reader. Editing the premise out of the task file silently —
  the premise was a reasonable reading of the filter appendix, and a later reader asking why A1.5
  did not report the obvious finding deserves the answer. Resolving the UniRef tier by inference: the
  70%/90% columns are consistent with parsing UniRef100 and re-clustering, which is suggestive, but
  Table S3's clustering levels are ESM3's own and no arrangement of the published numbers identifies
  the input. A proxy chooses and says it chose; it does not guess and present the guess as recovered.
- **Consequence:** `amazebio.uniref` now carries a `Release` registry rather than four module
  constants, so ESM3's 2023_02 stages through A1.3's verified path unchanged and the 2021_04
  constants remain as aliases that A1.3's manifests still resolve. Because the tier is unstated, a
  UniRef proxy stages the whole archive — all three tiers — rather than a tier chosen on the
  reader's behalf; that is a cost, and it is the subject of the staging-scope question put to the
  project owner separately. A4.3 gains its ESM3 scope table without waiting for any staging: the
  composition is documentary. Two re-entry routes the filter's description does not reach are
  recorded in `policies/esm3-open.md` §8 — predicted-structure databases over already-filtered
  sequences, and 362M inverse-folded sequences that are in no database for an MMseqs query to
  match. Both are findings about the published description, not measurements; A2 would need the
  structure-side components staged to measure either, which nothing has authorised.

### D-041 — eight of the twelve staged objects are verified in flight, not by readback
- **Date:** 2026-10-14
- **Task:** A1.2
- **Numbering:** appended as D-032 and renumbered to D-041 on 2026-10-15. A1.5 took D-032 first and this entry collided with it: both tracks chose a number at append time and the two appends merged cleanly while clashing semantically. A1.5's entry is cited from `src/amazebio/esm3.py` and `uniref.py`, so this is the cheaper of the two to move. Commit `d6473bb` and PR #7 cite the old number; this line is how they resolve.
- **Context:** Each object is hashed as it streams and the upload completes only on a match
  against the SHA-256 the release publishes, so all twelve are verified. But an in-flight hash
  checks the bytes that went past, and a readback checks the bytes the bucket holds — which is
  strictly stronger, because it would also catch a fault in our own multipart assembly rather than
  trusting the code that is under test. Four of the twelve were small enough to re-read for
  nothing and are readback-verified. Re-reading the other eight means 134 GiB of egress from
  outside the region, about $12, for files whose digests already matched.
  A related mistake happened here and is worth recording because the fix is now in code: a resumed
  pass wrote its own weaker rows over the manifest and erased the evidence that the eight had been
  checked at all. Manifests now merge and keep the stronger proof per file.
- **Decision:** **Leave the eight verified in flight, and fold the readback into the first
  in-region pass rather than launching anything for it.** D-026 already settled that analysis runs
  in `us-east-1`, where reads of this bucket are free. A7.1 reads the IMG/VR component in full
  anyway, so the readback costs nothing when it rides along with work that was happening regardless.
  Until then the manifest says, per file, how its checksum was established — "stream" or
  "readback" — rather than a bare `verified: true` that flattens the difference.
- **Rejected:** Paying the $12 egress now — it buys a stronger check on twelve files that already
  matched, weeks before anything depends on it, and the same check is free later.
  Launching an EC2 instance for the readback alone — AGENTS.md says launch only when being
  in-region is the point, and bookkeeping that can ride along with A7.1 is not that.
  Recording all twelve as simply verified — true, but it hides which were checked the stronger way,
  and §7 assumes a reader who wants to know exactly that.
  Re-uploading the eight with `--no-resume` to force a fresh in-flight hash — it repeats the
  weaker check at the cost of the whole transfer, and the bucket cannot delete, so an overwrite is
  the one operation worth being most careful with.
- **Consequence:** A1.2's corpus is staged and checksummed, so its Done-when is met. **A7.1
  inherits one small obligation:** run the readback over the eight large objects as part of its
  in-region pass and merge the result into `artifacts/a1-2/staged_*.json`, which upgrades those
  rows from "stream" to "readback". If A7.1 is re-scoped away from reading those objects, the
  obligation moves to whichever in-region task reads them first; it should not become a reason to
  launch an instance on its own.

### D-033 — A1.5 stages the two components ESM3 states exactly, at their published granularity
- **Date:** 2026-10-14
- **Task:** A1.5
- **Context:** D-032 established that all eight of ESM3's components carry a stated release but
  only two can be obtained as stated: UniRef 2023_02 and MGnify 2023_02, both still served with a
  publisher checksum. JGI and OAS have no dated snapshot at all. AlphaFoldDB v4 and ESMAtlas are
  stated exactly but are large and fall outside the filter's named scope. That left a scope question
  A1.5 could not settle itself, for the same reason D-031 could not: the corpus bucket withholds
  `s3:DeleteObject`, so anything staged is permanent spend. Four options were costed and put to the
  project owner, spanning $0 to about $15 a month.
- **Decision:** **UniRef 2023_02's three tiers plus MGnify 2023_02's 90%-clustered product.** About
  294 GB, roughly $6.80 a month. Three parts of this are commitments rather than implementation
  detail.
  **All three UniRef tiers, because the tier is unstated.** ESM3 says "UniRef release 2023 02" and
  the release holds UniRef50, UniRef90 and UniRef100 — 60,479,070, 170,669,877 and 350,950,053
  clusters. Staging one would be choosing on the reader's behalf and would have to be defended in
  the write-up; staging all three makes the proxy independent of a question nobody can answer.
  **MGnify at the granularity its name states, not both readings.** "MGnify90" is the release's
  90%-clustered product, served as one 83,473,342,442-byte file with a published md5. The full
  2.97-billion-sequence protein set behind it is 362 GB more, and D-032 established that the
  published counts cannot settle which was parsed. The clustered product is what the name says, and
  the other reading is deferred rather than bought at four times the price.
  **The raw UniRef archive is not retained, which is where this departs from A1.3.** A1.3 kept its
  169 GB archive verbatim alongside the extracted tiers. Retention buys re-read speed and nothing
  else: the md5 is verified in the same streaming pass either way, and both publishers serve
  previous releases indefinitely — UniProt still serves 2021_04 and EBI still serves MGnify
  releases from 2017. Not retaining it saves about $4.90 a month, permanently.
- **Rejected:** UniRef only (~210 GB, ~$4.80/month) — it would leave the audit silent on MGnify,
  which is 105.5B of ESM3's stated tokens and, carrying no taxonomic annotation at all, the clearest
  case in the project of a component an alignment-based filter can reach and a taxonomy-based one
  cannot. Both MGnify readings (~656 GB, ~$15/month) — the extra copy answers an ambiguity that the
  published counts cannot resolve anyway, so it buys coverage of a question rather than an answer.
  Staging nothing — the composition table and the findings need no bytes and are already committed,
  but A1.4 would then run ESM3's predicates against ESM-2's UniRef 2021_04, which is a different
  release as well as a different tier, and that substitution is worse than the storage bill.
  Staging AlphaFoldDB or ESMAtlas "while we are here" — they are the two re-entry routes in
  `policies/esm3-open.md` §8 and they matter, but measuring either is A2.2's work and A2.2 is not
  started; this is the scope creep AGENTS.md names.
- **Consequence:** A1.4 and A4.3 get the ESM3 proxy they depend on, at a standard that carries the
  proxy qualifier A1.1 requires but no acquisition qualifier: both components are verified against
  their publishers' own checksums. **Three things the next worker should expect.** JGI remains
  unstageable, so every ESM3 coverage figure is a fraction of the components staged and must say so
  — that is not fixable by spending more. The MGnify protein set and the two structure-side
  components are deliberately unstaged, with the figures here; whoever needs one should re-ask the
  cost question rather than assume it. And the stated-versus-used record for ESM3 is not a byte
  comparison like ESM-2's: it is the component table in `src/amazebio/esm3.py`, because what ESM3
  states and what is obtainable differ by release granularity rather than by content.

### D-034 — Tier 2 is out of scope, decided by measuring the launch policy rather than judging it
- **Date:** 2026-10-14
- **Task:** B1.1
- **Context:** `DESIGN.md` §B1 names Evo 2 40B, Nucleotide Transformer and ProGen2 as Tier 2 "if
  compute allows", and B1.1 owes a recorded scope decision. "If compute allows" had never been
  measured. `AGENTS.md` describes the account's launch policy as an allowlist of instance types
  without enumerating it, and the session container has no GPU, so neither the ceiling nor the
  availability of an accelerator was known. `tools/ec2_capability.py` measured it by dry-running
  `RunInstances` across a fixed list of types — `DryRun=True` authorizes the request and then
  refuses it, so nothing is launched and nothing is billed. The request carries the `Project` and
  `Owner` tags and the instance profile, without which every refusal is an indistinguishable
  `UnauthorizedOperation` and the probe would have reported the whole space as denied.
- **Decision:** **Tier 2 is out of scope, on compute.** The first probe found no accelerated type
  permitted at any size — `g4dn`, `g5`, `g6`, `g6e`, `p3`, `p4d`, `p5` all refused — with a ceiling
  of 8 vCPU and 64 GB. That was put to the project owner, who added `g5.xlarge` and `g6.xlarge`; the
  second probe confirms them, so one 24 GB accelerator is available and every Tier 1 checkpoint is
  runnable. Evo 2 40B is not: its own developers state it needs FP8 via Transformer Engine on a
  Hopper GPU and multiple H100s for the weights, which means `p5.48xlarge` and roughly $98 an hour
  against roughly $1 for a single-GPU box. Nucleotide Transformer and ProGen2 are out for a
  different and stronger reason — nothing about either has been retrieved into `sources.json`, and
  §B1 step 0 forbids inheriting a training-data claim from `DESIGN.md`, so neither can be an
  inventory row at all until someone acquires its sources.
- **Rejected:** Asking for Hopper access so 40B is runnable — the 40B and 7B checkpoints share one
  policy, one corpus and one lineage (`policies/evo.md`), so the second size buys a scaling result
  the homology regression does not need, at about a hundred times the hourly cost, on an account
  that cannot stop an instance mid-run. Adding Nucleotide Transformer and ProGen2 as rows marked
  unverified — it would put two checkpoints in the inventory whose exclusion status rests on nothing,
  which is precisely the shape of claim this store exists to prevent. Recording Tier 2 as deferred
  pending compute without measuring — that was the state of the question before this task, and it
  would have left a scope decision resting on an assumption about an account policy that in fact
  changed twice in one afternoon.
- **Consequence:** Phase B's model list is the five Tier 1 checkpoints. `evo2_40b` stays in
  `amazebio.models` as a Tier 2 row, because its requirement is a published fact worth recording and
  the thing that excludes it is a measurement that can change; `tools/model_inventory.py` recomputes
  feasibility from the current allowlist rather than from a frozen verdict. The allowlist snapshot
  carries its date and must be re-run rather than cited — it changed during this task, which is the
  argument for not hard-coding it. One consequence for B1.2: a 24 GB card fits all five, but nothing
  here establishes that a 200-assay zero-shot pass finishes in useful time, and that measurement is
  B1.2's first job rather than an inventory's claim.

### D-035 — ESM-C enters Phase B as the 600M variant, and "open release" does not name one
- **Date:** 2026-10-14
- **Task:** B1.1
- **Context:** `DESIGN.md` §B1 lists the second positive control as "ESM-C (open release)". That
  phrase does not pick out a checkpoint: the family is 300M, 600M and 6B, and all three are openly
  downloadable from the same HuggingFace collection, with the smaller two described by their own
  developers as overtrained variants for local inference. B1.1 has to record a checkpoint
  identifier, so the ambiguity had to be resolved rather than carried.
- **Decision:** `ESMC-600M`. It is the largest variant that runs comfortably on the one 24 GB
  accelerator this account permits (D-034), and the role §B1 gives ESM-C is a second
  viruses-included comparison — the contrast being that its viral content is largely bacteriophage
  — not a capability ceiling. The corpus claim behind that role rests on the preprint either way,
  because the 600M and 6B model cards are byte-identical and neither evidences anything
  variant-specific (`policies/esm-c.md` §5).
- **Rejected:** ESMC-6B — the strongest model in the family, but it answers a question Phase B is
  not asking, and §B1's own narrowing in v0.4 makes the homology regression primary and model
  comparison supporting. The published ESM-C evaluation this design leans on compares "ESMC models"
  as a family, so nothing downstream depends on which variant. ESMC-300M — no reason to prefer it
  once 600M fits. All three — scope creep for a control, and `DESIGN.md` §7 names that as a live
  risk.
- **Consequence:** If a later task wants the 6B model, that is a compute decision and not a
  re-verification: the exclusion status, licence and access route recorded in `policies/models.md`
  §3 are family-level and already cover it. Note the asymmetry this creates with the ESM-2 arm,
  which carries two sizes because §B1 names two.

### D-036 — ESM3-open's parameter count is recorded as unstated, not as 1.4B
- **Date:** 2026-10-14
- **Task:** B1.1
- **Context:** Phase B needs ESM3-open's size, and it is universally given as 1.4B. No first-party
  source retrieved into this store states it. The ESM3 family table lists `esm3-large-2024-03` at
  98B, `esm3-medium-2024-08` at 7B and `esm3-small-2024-08` at 1.4B, and does not list
  `esm3-sm-open-v1` at all — the open checkpoint appears only in the prose above the table, as the
  one whose weights are public. So neither its size nor which flagship checkpoint it corresponds to
  is established by its developers' own documentation. The model card gives corpus scale and token
  counts and no parameter count. The only size attribution in the store is the ESM-C preprint's
  "ESM3 1.4B Open", which is one lab describing another lab's model.
- **Decision:** `params` is recorded as `None`, with the gap named in
  `src/amazebio/models.py`, argued from the sources in `policies/models.md` §2, and pinned by a test
  so that filling it in requires a primary source. §B1 step 0 says to verify from primary sources
  and trust no secondary source; a second lab's parenthetical about someone else's checkpoint is a
  secondary source, however reliable it looks. The inference is very probably correct and that is
  not the standard.
- **Rejected:** Recording 1.4B cited to the ESM-C preprint — it would put a number in the inventory
  on the authority of a source that is primary for ESM-C and secondary for ESM3, and the whole
  reason this store checks quotations mechanically is that a plausible attribution acquiring a
  citation is the failure mode that would most damage the project. Recording 1.4B as "widely
  reported" — same defect, with the citation removed. Inferring it from the checkpoint's own config
  on HuggingFace — that would actually settle it, and it is a legitimate route, but it means
  downloading the weights, which belongs to B1.2 rather than to an inventory task.
- **Consequence:** Two checkpoints of six now carry a §A0 under-specification finding, which
  `tools/model_inventory.py` reports on every run. Anything in a write-up that turns on
  ESM3-open's size needs either the Science version of record (S-ESM3-SCIENCE, still unretrieved)
  or the config from the weights themselves. For B1.2 this is nearly free to close: the config is
  read anyway when the model loads, and recording what it says would convert a §A0 finding into a
  verified field.

### D-037 — Spearman is implemented in the standard library rather than adding scipy
- **Date:** 2026-10-14
- **Task:** B2.1
- **Context:** `DESIGN.md` §B2 requires the benchmark's standard rank-correlation metric so
  results stay comparable to the published leaderboard, and `AGENTS.md` says a tool is added by
  the task that needs it, with the version choice recorded. The metric is Spearman's rho with
  ties averaged, which the maintainers compute with `scipy.stats.spearmanr`. The project has no
  numeric dependency at all: `pixi.toml` carries `pypdf` and `pyyaml` and nothing else.
- **Decision:** Implement it in `amazebio.proteingym.spearman` — Pearson's correlation of
  average ranks, about twenty lines — and add no dependency. This is not inventing a metric,
  which §B2 forbids; it is the same definition, and the evidence for that is empirical rather
  than asserted: `tools/proteingym_check.py` recomputes the published per-assay value for all
  217 assays and every one agrees at the three decimals the maintainers publish, with a maximum
  deviation of 0.0005 and a mean of 0.000246 — which is what rounding alone produces. A unit
  test against hand-computed values could not establish that; agreement with the published
  numbers on 2.47 million variants does.
- **Rejected:** Adding scipy (and numpy beneath it) now — it is a large pinned dependency for
  one function, at a point where nothing else needs it, and `pixi.toml` explicitly warns against
  pre-populating the environment with tools no result depends on yet. Deferring the metric to
  B5 and shipping the ingest without one — then nothing validates the ingest, and the join and
  the variant list would go unchecked until the analysis, which is the worst time to find a
  mismatch. Using the maintainers' own scripts — they pull in the full benchmark toolchain, and
  an independent implementation that agrees with their published output is better evidence than
  running their code and finding it agrees with itself.
- **Consequence:** Phase B will almost certainly need numpy when B5 fits regressions and
  bootstraps intervals, and that is the task to add it, with its own entry. Until then the
  metric has no dependency and one pure-Python implementation that a reviewer can read in full.
  Note the incidental benefit for §7: the published leaderboard is now an independent check on
  our metric code, which is the same kind of second-method agreement A3.3 requires of the
  headline counts.

### D-038 — "standard splits" in the zero-shot setting means the published variant list, whole
- **Date:** 2026-10-14
- **Task:** B2.1
- **Context:** §B2 says to use the benchmark's standard splits and not to invent either the
  splits or the metric. The release ships CV fold files — `cv_folds_singles_substitutions.zip`
  and `cv_folds_multiples_substitutions.zip` — so a reader could reasonably expect B2.1 to load
  them. Those folds belong to the benchmark's *supervised* track, where a model is trained on
  some variants and tested on others. `DESIGN.md` §4 restricts this project to zero-shot
  scoring, which has nothing to train and therefore nothing to split.
- **Decision:** No fold file is used. "Standard split" here means the published variant list
  per assay, taken exactly as shipped: every variant the maintainers include is scored, none is
  filtered, and the assay is the unit of analysis. This is recorded in the module docstring as
  well as here, because it is the kind of thing a later reader would otherwise assume had been
  overlooked rather than decided.
- **Rejected:** Loading the CV folds anyway for "comparability" — it would make this project's
  numbers comparable to a benchmark track it does not run and is forbidden from running.
  Restricting to single substitutions and dropping multi-mutants — plausible-looking, since most
  assays are singles-only, and wrong: it would silently redefine the benchmark and break the
  comparability §B2 asks for. 24 of the 217 assays carry multi-mutants.
- **Consequence:** Per-assay variant counts match the reference file's own counts exactly, which
  `tests/test_proteingym.py` checks for a sample and the reproduction check confirms for all 217
  assays by agreeing with the published numbers. If a later task needs a subset — B2.3's
  within-study positive controls, say — it must subset explicitly and say so, rather than
  changing what the ingest returns.

### D-039 — the leaderboard's headline average is not reproduced, and is not the mean of the per-assay values
- **Date:** 2026-10-14
- **Task:** B2.1
- **Context:** §B2's ingest check is "reproduce one published leaderboard number". The obvious
  candidate is a model's headline average Spearman, and that number cannot be reproduced by
  averaging the per-assay values. The maintainers state that their performance scripts correct
  for biases — assays per protein family, functional groupings — so the published average is a
  weighted quantity whose weighting is theirs, and the arithmetic mean of 217 per-assay values
  is a different number.
- **Decision:** Reproduce the published *per-assay* values instead, and do it for every assay
  rather than the one §B2 asks for. The aggregate is deliberately not reproduced and no
  aggregate of ours is reported in this task's artefact. Any pooled figure this project
  publishes later must be computed by us, specified before results are seen, and reported
  after the per-assay breakdown — which `AGENTS.md` requires anyway, and which §B5 states is
  the default presentation because pooled correlations are fragile at this sample size.
- **Rejected:** Reimplementing their bias correction to match the headline number — it is their
  weighting, reimplementing it would be a second place for it to be wrong, and nothing in this
  project needs the aggregate to agree. Comparing our arithmetic mean to their corrected
  average and calling a small gap agreement — that is the failure mode this entry exists to
  prevent: the two are different quantities, and a close-looking match would be a coincidence
  presented as a check.
- **Consequence:** The ingest check is per-assay and exact. One number that follows, and should
  not be misread: the mean of our per-assay values for ESM-2 650M is not the leaderboard's
  0.414, and any write-up that cites a leaderboard rank must cite their aggregate as theirs.

### D-040 — the benchmark release is pinned by our own checksums, and two of its files carry no version at all
- **Date:** 2026-10-14
- **Task:** B2.1
- **Context:** `AGENTS.md` requires every input pinned, and A1.3 set the standard: UniRef was
  verified against the publisher's own md5, so the pin was the publisher's and a re-cut release
  would have been caught. The benchmark publishes no checksums for its archives. Worse for
  pinning, two files this task depends on — the assay reference file, which carries the taxon
  labels, and the published per-assay leaderboard, which the reproduction check compares against
  — are not in the versioned data release at all. They live in the maintainers' git repository,
  which carries no tag for v1.3, so their URLs name `main` rather than a version.
- **Decision:** Record a SHA-256 of all five staged files in `amazebio.proteingym.RELEASE` and
  check them with `verify_release`, while keeping the two unversioned files in a separate
  `unversioned` mapping rather than folding them in with the versioned archives. The separation
  is the point: a hash in `files` sits behind a URL that names v1.3, and a hash in `unversioned`
  is the entire pin. State plainly, here and in the artefact, that these hashes attest the bytes
  have not changed since *this* acquisition and not that they are the bytes released.
- **Rejected:** Treating all five as equivalently pinned — it would hide that two of them track
  a moving branch. Pinning the repository files by commit SHA, which would be better — the
  GitHub API is not reachable from this environment to resolve `main` to a commit, and the raw
  endpoint does not return one; a later task with API access should upgrade this. Declining to
  use the unversioned files — not an option: the reference file is the only source of the taxon
  labels §B5 reports by, and the leaderboard file is what makes the ingest checkable.
- **Consequence:** Two things for whoever comes next. The per-assay numbers this project
  reproduces are a moving target upstream, so a future re-run that disagrees should first check
  whether the leaderboard file changed rather than assuming the ingest broke — the recorded hash
  makes that a one-command question. And the documented archive sizes are wrong, one by more
  than an order of magnitude (1.0GB documented against 43MB served, 4.4GB against 1.91GB); the
  stated-versus-actual record is in `artifacts/b2-1/release/release.json`, and the lesson for
  B2.2 is to size downloads from `content-length` rather than from documentation.

### D-042 — A3.1's conformance criterion moves to A3.2, because a freeze cannot demonstrate it
- **Date:** 2026-10-15
- **Task:** A3.1
- **Context:** A3.1 is the freeze task for the headline metrics and the survival-route taxonomy:
  `metrics/survival.md` is the specification, `src/amazebio/survival.py` carries the taxonomy and
  a reference implementation, and the four substantive calls are in D-022. All of that is merged.
  Its Done-when list, though, also required the taxonomy to be "used by all A2 outputs", which no
  amount of work inside A3.1 can satisfy: every A2 detector is blocked behind A1.4, so the
  criterion made a definitional task wait on five detection tasks that depend on it in turn. The
  board showed A3.1 as live work for as long as that held, which is exactly the phantom-progress
  the task protocol exists to prevent.
- **Decision:** Split the criterion by what each task can actually show. A3.1 keeps the freeze —
  definitions reimplementable from the text alone, every route named and distinguishable, a
  reference implementation to tag against — and closes. A3.2 picks up conformance: every A2
  output carries a route from the taxonomy, checked rather than assumed, with the merge failing
  on an untagged or unknown-route detection. A3.2 already depends on all five A2 tasks and is
  where their outputs meet, so it is the first point at which the check is possible at all.
- **Rejected:** Leaving A3.1 in `review` until the first detector lands — correct, but it parks a
  finished specification behind unstarted work and leaves the board misreporting for weeks.
  Closing A3.1 with the criterion unmet and unrecorded — that is how a Done-when list stops
  meaning anything. Bringing A1.4 and A2.1 forward to demonstrate it inside A3.1 — two
  substantial tasks absorbed into a definitional one, which the scope rule forbids.
- **Consequence:** The conformance check is now a Done-when criterion on a task that does not
  yet exist in code, so it has to be built rather than inherited: whoever runs A3.2 writes the
  check that rejects an untagged detection, and it is not satisfied by detectors merely importing
  `amazebio.survival`. Against that, a detector written before A3.2 runs now has nothing
  enforcing the tag at the point it is written — A2.1, as the first one, should carry the
  convention into the others.

### D-043 — A1.4 covers every reading the releases can answer; the ESM3 alignment pass becomes A1.6
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** A1.4's goal is to run each of the three readings against each staged corpus, which
  reads as six policy specs over the staged releases. Inspecting the inputs before writing code
  shows the six are not one kind of work. The Evo readings turn on taxonomy, record attributes and
  host counts, and the component the policy acts on is staged with an inline lineage tag on every
  record. ESM3-open's turn on similarity to two denylists: the literal reading's threshold is
  unpublished, so it evaluates to `undetermined` without touching a sequence; the charitable
  (0.70) and strict (any hit) readings need both denylists rebuilt from UniProt annotation — ~4M
  sequences, with the source's "almost exclusively" unquantified — and an aligner run over ~295 GB
  of staged proxy corpus in region. Nothing has staged a seed set, no aligner is pinned, and the
  spend has not been priced. Meanwhile A1.4 blocks ten tasks, every A2 detector among them.
- **Decision:** A1.4 ships the readings whose inputs the staged releases already carry: Evo 1's
  three readings against both OpenGenome releases, and ESM3-open's literal reading, whose result
  is that no record's fate is determinable from the published words. The ESM3 charitable and
  strict readings move to a new task, A1.6, which depends on A1.4 for the evaluator and manifest
  format and on A1.5 for the staged corpus. A1.4's Done-when count changes from "nine-ish" to
  seven manifests, and the two that move are named rather than dropped.
- **Rejected:** Keeping all six in A1.4 — it holds ten downstream tasks behind an unpriced
  alignment run and an acquisition nobody has approved, and it is exactly the widening the scope
  rule forbids. Deferring ESM3 entirely, including the literal reading — it would drop a finding
  that costs nothing to produce and is among the strongest in the audit: the filter as published
  cannot be re-executed at all, because the one number that sets its reach is not in the source.
  Supplying a threshold in A1.4 so the ESM3 arm could run — that is what the charitable reading
  already does under a label, and doing it unlabelled would convert an under-specification finding
  into a fabricated parameter.
- **Consequence:** The three-reading spread §A0 asks for is complete for Evo and partial for ESM3
  until A1.6 runs, so A0.4's report on the ESM3 axis is bounded by A1.6 rather than by A1.4 —
  whoever picks up A0.4 should check which of the two is actually its blocker. The manifest format
  A1.4 freezes has to be the format A1.6 writes, which means it must carry a route for a record
  whose fate is undecidable for want of an aligner result, not only for want of a published
  parameter. Both land as `unresolved` against different causes, and the manifest records the
  cause.

### D-044 — corpus-scale evaluation runs every applicable rule, rather than stopping at the first to decide
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** The reference evaluator in `policyspec.evaluate` applies rules as a pipeline and
  stops at the first one that decides a record, which is how a filter implementation behaves and
  is the right reference semantics. Against the actual releases it gives an answer that is not
  merely imprecise but empty. Three of Evo's six published rules read metadata the release does
  not carry — the high-confidence flag, the vOTU, the prokaryotic-host count — and all three run
  *before* the denylist rules in the published order. Stopping at the first undecidable rule
  therefore reports every record in the viral component as undecidable, including records the
  family denylist removes beyond any doubt, which are exactly the records the audit is looking
  for.
- **Decision:** The corpus-scale evaluator (`apply.resolve`) evaluates every rule that reaches a
  record and resolves the set by precedence: `removed` > `undetermined` > `unresolved` >
  `retained`. Removal wins because it is the only definite verdict — if any rule removes a
  record then the record does not survive, whatever an earlier rule could not decide. Retention
  loses because it is contingent: "no rule removed it" is only true if every rule was actually
  checked. Between the two undecidable outcomes the policy gap (`undetermined`, a parameter
  never published) outranks the corpus gap (`unresolved`, metadata the release does not ship),
  because stating the parameter is a precondition for the corpus question arising at all. A
  removal is attributed to the first removing rule in published order, since that is the rule a
  conformance claim would cite. Both strategies stay, named and documented against each other,
  and a test pins the difference so neither is silently turned into the other.
- **Rejected:** Changing `evaluate` to match — it pins the published pipeline's own semantics
  with tests and A0.2's schema is version-pinned against them. Treating an undecidable rule as
  passing, so later rules still run and the record ends up retained — that is the unsafe
  direction: it reports a record as examined-and-kept when nobody can say whether the filter's
  first three steps would have dropped it. Treating it as removed — the other unsafe direction,
  and it would have manufactured a filter that removed Evo's entire viral component.
- **Consequence:** A1.4's counts are not comparable with a naive re-run of `evaluate` over the
  same records, and A7.1 must use `apply.resolve` or restate the precedence. The `unresolved`
  population is now a first-class result rather than an error bar: for Evo's releases it is most
  of the corpus, and the number is a measurement of what the release's own metadata permits, not
  of what the filter did.

### D-045 — manifests carry the removed set record by record and everything else by count
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** A1.4's output is the shared input for every A2 detector and for B3.*, so its shape
  is a contract. Two forces pull against each other. Record-level detail is what a conformance
  claim and a detector's exclusion list need; but the released corpora run to billions of
  records, the strict reading's scope is all of them, and a manifest enumerating every retained
  record would be a multi-gigabyte restatement of the corpus that no downstream task would read.
  There is also a mismatch to resolve: A1.4 distinguishes two causes of undecidability, while
  the frozen route taxonomy (D-022) has a single `unresolved` route.
- **Decision:** A manifest names records only where a reading *removes* them, written as JSONL
  beside a JSON summary. Everything else is reported by count, per component, with the verdict
  stated once. A component is read record by record only where some applicable rule can
  discriminate between its records; otherwise the verdict is uniform, is recorded as such, and
  its record count is `null` rather than `0` — nothing counted it, and zero would read as an
  empty component. Unstaged components are listed with their reason rather than omitted, so a
  wildcard-scope reading's manifest cannot be mistaken for a verdict on the staged subset. Both
  undecidable outcomes map to the frozen `unresolved` route, with the cause kept in the
  manifest's own field. The published-methods component name (`IMG/VR`) and the corpus component
  name (`stage2`) are both recorded per row, from an explicit mapping rather than string
  normalisation; Evo 1's mapping rests on `policies/corpora.md` §3, where the release names no
  viral component but stage 2 is established to be it. The format is `metrics/manifests.md`.
- **Rejected:** Widening the route taxonomy with a second undecidable route — it is frozen
  precisely so that counts stay comparable, and the distinction is not about why a sequence
  survived, which is what a route answers. Emitting `conformance_failure` for a removed record
  that is present in the release — `metrics/survival.md` reserves that route for A7.1 with
  record-level evidence and §7 requires it airtight, so `apply.route_for` raises on a removal
  instead of returning a route, and the removed set is documented as candidates. Enumerating
  every component for symmetry — 101 GiB of GTDB read to write one verdict a billion times.
- **Consequence:** A reader cannot sum a manifest's `totals` to get a corpus-wide figure,
  because the uniform verdicts are deliberately not in it; the per-source rows are the unit of
  reporting, which is also what §4's reporting limits want. A2 tasks get their exclusion list
  from the removed JSONL and must treat it as candidates, not findings. And whoever needs a
  record count for an unenumerated component adds one pass for it rather than finding a
  plausible number already in the manifest.

### D-046 — the A1.4 pass runs in the session container, not on an instance
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** `AGENTS.md` weighs an in-region instance against reading staged corpora from
  outside the region, where a full pass is "tens of gigabytes" of metered transfer. A1.4 needs
  three objects read in full: Evo 1's stage-2 Parquet (16.9 GB), its validation split, and Evo
  2's IMG/VR FASTA (11.2 GB) — 28.1 GB once the build reads each source once for all three
  readings rather than once per reading. Measured throughput on the Parquet was 12.9 MB/s single
  stream, so the pass is tens of minutes, and nothing is written to local disk.
- **Decision:** Run it here. 28.1 GB of egress is a couple of dollars, against an instance that
  cannot be inspected once running, gets one shot at its `UserData`, needs provenance passed in
  by hand, and leaves a resource that can be forgotten. The deciding factor is not the price but
  that this pass needed three iterations to get right — a schema assertion, a chunk-boundary
  bug and the policy-outer loop that tripled the read — and each would have cost a full launch
  cycle to discover on an instance.
- **Rejected:** An in-region instance for the whole pass — the honest reading of `AGENTS.md` is
  that its test binds on GTDB's 101 GiB, which A1.4 deliberately does not read, and A1.3's own
  note says a small instance is often the right answer precisely because the parallelism is not
  there: a gzip stream is one thread, so Evo 2's FASTA is single-threaded wherever it runs.
  Sampling instead of a full pass — the component is the filter's own output and the headline is
  a count over it; a sample would also have left A1.2's four-file observation about the missing
  lineage tags a sample.
- **Consequence:** The threshold is now stated for whoever comes next: a pass that reads GTDB,
  the metagenomes or the eukaryotic genomes is the in-region case and should be planned as one,
  with `tools/ec2_count.py` as the worked example. A1.4's own numbers regenerate with one
  command here, which is what X1.2 wants.
### D-047 — What a conformance re-execution can test against Evo 1's release, and why the reading spread is unmeasurable
- **Date:** 2026-10-15
- **Task:** A7.1
- **Numbering:** appended as D-042 and renumbered to D-047 on 2026-10-15. The A3.1/A1.4 track took D-042 through D-046 first and all five of this task's entries collided with them: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically, exactly as D-041 records. Their five are already on `main` and cited from its commits, so this block is the cheaper of the two to move. Commit `2c8c18c` and the A7.1 push cite the old numbers; these lines are how they resolve.
- **Context:** §A7 says to execute each reading's predicate over the released dataset and to
  report the spread across readings, which "matters as much as any single number". Evo 1's
  published procedure has six steps reading four kinds of input: IMG/VR confidence labels, vOTU
  identifiers, host-occurrence counts, and taxonomic lineage. Exactly one of those travels with
  the released records — the inline lineage tag D-020 established. The naive run is not merely
  weaker, it is wrong in a way that would look like a result: with no `confidence` attribute on
  any released record, `keep-high-confidence` removes all 2,652,947 of them at the first step,
  and a "conformance failure rate of 100%" would be our missing metadata published as their
  filter.
- **Decision:** A7.1 re-executes a **restriction** of each published policy, derived
  mechanically from a declared inventory of what each release carries per record
  (`amazebio.conformance.RELEASE_INPUTS`, with `RULE_INPUTS` mapping each frozen rule kind to
  the one input it reads). For `opengenome-stage2` the inventory is `{taxonomy}`, so three of the
  six rules are re-executed — `remove-denylisted-families`, `remove-denylisted-orders`,
  `remove-taxonomically-unspecific` — and three are reported as not checkable with the input
  each needs named. Coverage (`3/6`) is carried in the artefact next to every count and in every
  table of the write-up, never separately. A rule kind absent from `RULE_INPUTS` raises rather
  than defaulting to checkable, and a release that can re-execute nothing raises rather than
  returning an empty pipeline a caller could run and report zero failures from.
  **The reading spread is unmeasurable against this release, and that is the finding.** Every
  rule the literal, charitable and strict readings differ over — the prokaryotic-host count, the
  charitable eukaryotic-host rule, the strict exclusivity rule, and the wildcard scope — reads
  `host_occurrences` or `record_attributes`. The taxonomy rules are identical in all three
  specs. So the three readings re-execute the same pipeline here by construction, and
  `readings_agree_by_construction` asserts that from the specs so the write-up reports a
  property of the release rather than three identical output columns read as agreement.
- **Rejected:** Hand-picking the testable rules — it would put the most consequential judgement
  in this task, which of an author's rules we hold them to, into an unreviewable list, and a
  reader could not distinguish a rule dropped because the release omits its input from one
  dropped because it was inconvenient. Treating an absent input as
  `Outcome.UNDETERMINED` — that already means something different and load-bearing, namely that
  the *published source* does not state a value (ESM3's identity threshold is why it exists);
  merging a gap in somebody's prose with a gap in somebody's data would lose both findings.
  Imputing the missing metadata from any secondary source — AGENTS.md forbids secondary sources
  for factual claims about training data, and an imputed host count would make the conformance
  number a measurement of our imputation. Reporting the restricted rate as the policy's
  conformance rate — it is the rate for three named rules.
- **Consequence:** The headline A7.1 number is a conformance rate for Evo 1's three taxonomy
  rules against Evo 1's own released viral component, and must always be worded that way. Two
  consequences beyond this task. **A0.4 cannot get its Evo spread from the release.** The
  argument in `policies/corpora.md` §2 — that whichever reading best reproduces the released
  component is the developers' de facto reading — does not survive contact with the release:
  the readings are indistinguishable on everything it can test, so the release cannot identify
  which reading is theirs. That paragraph should be read with this entry. **The three
  unrunnable rules are themselves a disclosure finding**, and the one X5.1 can act on: a
  developer who published the filter's output without the three metadata fields their own
  procedure turns on made two thirds of their stated filter unauditable from their own release.
  That belongs in the filter disclosure standard as a requirement, not as a complaint.

### D-048 — One released row is one released record; D-020's "context windows" is corrected
- **Date:** 2026-10-15
- **Task:** A7.1
- **Numbering:** appended as D-043 and renumbered to D-048 on 2026-10-15; see D-047's note.
- **Context:** Every count A7.1 publishes is a count of records, and nothing published about
  `LongSafari/open-genome` states what one row of `stage2` contains. D-020, sampling 800 rows
  through the HuggingFace rows API, recorded the opposite of what is true: "rows are context
  windows rather than records, one genome may span many", and used it to refuse publishing any
  proportion from the sample. The refusal was right for its own reasons — 0.03%, contiguous
  blocks — but the stated reason was wrong, and left as it stood it would have forced A7.1 to
  report per-window counts or to dedupe on a field the release does not carry.
- **Decision:** The row is the record, and the claim is measured on every pass rather than
  assumed. A row is `|tag|sequence`; a record longer than **131,072 characters** (2^17, counting
  the tag against the budget) arrives as several `|tag|block` pairs concatenated into *one* row,
  each pair carrying the same tag, rather than as several rows. So the scan counts, over all
  2,652,947 rows: blocks per row, rows carrying more than one distinct lineage tag, rows whose
  final block is full-length, and rows carrying no tag at all. The first two would mean a row
  packs several records; the third would mean a record may continue into the next row. The
  artefact carries `structure.one_row_one_record` as the conjunction, and when it is false the
  diff relabels every count per row and says so in the summary — a count of records that is
  really a count of rows is the kind of error that survives review and then gets quoted.
  Length distribution supports the reading independently: lengths run continuously from about
  1.5 kb past 300 kb with no mode at any context size, which is a genome-length distribution
  and not a window one.
- **Rejected:** Counting tag occurrences rather than rows — it would count a 300 kb genome three
  times, because the chunking repeats the tag. Deduplicating within a row by tag and leaving it
  there — right for the common case and silently wrong the moment a row genuinely packs two
  records, which is why both are counted and reported. Trusting D-020's characterisation —
  the standing lesson of D-019 and D-020 both is that a sample answers questions about the
  sample; two corrections to the same paragraph is enough.
- **Consequence:** A7.1's counts are per record, and the evidence that they are is in the
  artefact rather than in this entry. `policies/corpora.md` §3 needs its "rows are context
  windows" sentence corrected the next time that file is touched; D-020's refusal to publish a
  proportion stands on its sampling design, which this does not disturb. For A2 and A4.1, which
  will read the same component: the release's record identity is the row, there is no accession
  on it, and no join to IMG/VR is possible from `stage2` at all.

### D-049 — A7.1 runs the forward direction only; the converse and Evo 2's arm both need IMG/VR v4
- **Date:** 2026-10-15
- **Task:** A7.1
- **Numbering:** appended as D-044 and renumbered to D-049 on 2026-10-15; see D-047's note.
- **Context:** The task calls for the converse check as well as the forward one — records removed
  that the predicate does not call for, since an over-broad filter is also a mismatch between
  rule and practice — and for running the diff against OpenGenome2's IMG/VR component as well as
  Evo 1's. Both turn out to need the filter's *input*. `policies/corpora.md` §2 states IMG/VR v4
  is independently available at its pinned version from its own publisher, which is true and is
  not the same as acquired: it is not in `policies/sources.json`, there is no staging tool for
  it, and nothing in the corpus bucket holds it.
- **Decision:** A7.1 ships the forward direction only, and says so in a field of the artefact
  rather than in prose, because a missing arm mentioned only in a footnote gets cited as a null
  result. Evo 2's IMG/VR release is read far enough to establish what it can and cannot support
  and no further: its FASTA headers carry `IMGVR_UViG_<taxon_oid>_<n>` accessions, zero
  delimiters and no rank-prefixed field, so **no published Evo rule can be re-executed against
  Evo 2's release at all** — the inverse of Evo 1's release, which is testable against the
  taxonomy rules and traceable to nothing. That was established from a bounded 2,000-header read
  rather than a full 11.2 GB pass, and `conformance_scan.py` keeps the `--max-headers` bound
  that makes it reproducible. The accession inventory the join would need is **not** collected
  here.
- **Rejected:** Acquiring IMG/VR v4 inside this task — it is a corpus acquisition with its own
  pinning, verification and staging work, on the scale of A1.2 and A1.3, and AGENTS.md is
  explicit that a task which turns out to be two tasks is split rather than quietly widened.
  Collecting the full OpenGenome2 accession inventory because the pass was cheap — nothing
  consumes it yet, and pixi.toml's own rule about unused pinned tools applies as well to unused
  pinned data: it is a maintenance cost with no result attached. Inferring over-removal from the
  released component's composition alone — without the input there is no denominator, and a
  count of what is absent from a corpus cannot be taken from the corpus. Reporting the forward
  rate as the conformance rate without qualification.
- **Consequence:** An IMG/VR v4 acquisition is the blocker for three things, and should be its
  own Phase A task rather than an item inside A7.1: the converse check, the forward check for
  Evo 2's release, and the three rules D-047 records as unrunnable, all of which the input
  supplies. Until it exists, A7.1's result is one-directional and `X5.1` inherits the stronger
  of the two findings anyway — that two thirds of a published filter cannot be audited from the
  release that filter produced.

### D-050 — The release pass runs in the session container, and the EC2 test is applied and declined
- **Date:** 2026-10-15
- **Task:** A7.1
- **Numbering:** appended as D-045 and renumbered to D-050 on 2026-10-15; see D-047's note.
- **Context:** AGENTS.md sets a test for launching an instance: whether the work is bound by data
  movement that is free inside `us-east-1` and metered outside it, with "reading the staged
  corpora" named as the case that qualifies because a full pass is tens of gigabytes. A7.1's
  pass is 16.92 GB of Parquet, which reads like exactly that case, and A1.3's worked example in
  `tools/ec2_count.py` was sitting there to copy.
- **Decision:** Measured first, and the test fails: the pass runs in the session container in
  about seven minutes, so no instance is launched. Three numbers decided it. A single ranged read
  from the corpus bucket through this project's outbound proxy runs at 19 MB/s, and sixteen
  concurrent readers at 178 MB/s, so the transfer is minutes rather than hours. Unlike the gzip
  streams A1.3 was bound by, `train_stage2.parquet` is **2,653 row groups of 1,000 rows**, each
  column chunk independently decompressible, so parallelism is bounded by cores and not by the
  format — the honest answer A1.3's own note asks for turned out to be that no instance is the
  right size. Measured single-process throughput is 1,646 rows/s, giving about 6.7 minutes on
  four processes. AGENTS.md's own sentence settles it: compute that would run acceptably in the
  session container does not qualify.
  `pyarrow>=18,<22` is pinned for the Parquet read, per pixi.toml's rule that the task needing a
  tool adds it; 21.0.0 is what the lockfile resolved to.
- **Rejected:** Launching anyway because the file is large and the pattern existed — an instance
  costs money, leaves a resource that can be forgotten, and cannot be inspected once running,
  and none of that is worth paying to save three minutes. Treating the 16.92 GB of metered
  egress as the deciding cost — it is about $1.50, and an instance is not free either; wall clock
  and the risk of a forgotten resource are the real terms. Applying the Arrow-native fast path
  that would have cut the Python per-row cost — the pass is network-bound at four processes, so
  it would buy nothing and the naive path is the one the tests cover.
- **Converging independently:** the A1.4 track applied the same AGENTS.md test to a different
  pass and also declined to launch (their D-046, on `main`). Two tracks reading the same
  paragraph and both measuring first is some evidence the paragraph is doing its job; it also
  means the EC2 note in AGENTS.md now has two worked declines against A1.3's one launch, and
  should probably say so the next time that file is touched.
- **Consequence:** A7.1 leaves no AWS resource behind, and the scan tool runs anywhere with
  credentials rather than only in-region. For the next task weighing this: measure the three
  numbers before copying `ec2_count.py` — streams, format parallelism, rows per second — because
  a splittable format changes the answer that a gzip stream forced. The in-region route stays
  right for the gzip corpora, which cannot be split at all.

### D-051 — The published realm test is not a specificity test, and the release proves it on 95 records
- **Date:** 2026-10-15
- **Task:** A7.1
- **Numbering:** appended as D-046 and renumbered to D-051 on 2026-10-15; see D-047's note.
- **Context:** Evo 1's last exclusion step is encoded as `require_rank: realm`, from "viruses with
  poor taxonomic specificity were excluded, including those with no assigned realm at all" and
  the eight named stop-taxa. A0.3 debated the required rank twice — D-016 and D-018 withdrew a
  strict reading that raised it to family, because the authors ceiling their own enumeration at
  class — and both times the argument was textual. The re-execution supplies data.
- **Decision:** Record the conflation as a finding in its own right, separate from the
  conformance count that exposed it. Of 2,653,047 released records, **95 carry no assigned realm
  and are therefore removed by the rule as published**, and all 95 are assigned at **family**
  rank: 73 `f__Bicaudaviridae`, 21 `f__Fuselloviridae`, 1 `f__Ovaliviridae`. The modal released
  record fills four ranks and stops at **class** — 2,543,536 of 2,653,047. So the published rule
  removes records that are better resolved than the overwhelming majority it keeps, because rank
  of assignment and taxonomic specificity are different axes and the encoding tests the first
  while the sentence is about the second. A family with no realm above it is not a poorly
  specified virus; it is a family whose higher placement the taxonomy has not settled.
  Two things this entry deliberately does **not** claim. It does not say which hosts those three
  families infect — that needs a taxonomy source this project has not retrieved, and A9.1 is
  where one enters. And it does not revise the spec: `require_rank: realm` stays, because it is
  the conservative encoding of the published words and A7.1's job is to re-execute what was
  published, not to improve it.
- **Rejected:** Classifying the 95 as `predicate_ambiguous` — the realm limb is stated outright
  and fires unambiguously; the ambiguity is in the *other* limb, the unquantified "including",
  and conflating the two would hide a clean failure behind a vague one. Reporting the 95 as a
  filter defect without the rank context — true as a conformance statement and misleading as a
  finding, since the filter's judgement looks better than its stated rule. Amending
  `require_rank` to something that reproduces the release — that is fitting the spec to the
  data, which is the one thing a conformance audit may not do. Treating 0.004% as too small to
  report: the rate is small and the mechanism is not, and §2 commits this project to publishing
  what it finds either way.
- **Consequence:** Three downstream uses. **A9.1 gains its sharpest case**: this is a static rank
  test decaying against a live taxonomy, measured on real records rather than argued from the
  text. **A0.4 gains a worked example** of under-specification with a count attached, which is
  what §A0 asks for. **X5.1 gains a disclosure requirement** that follows from the mechanism
  rather than from a preference: a filter spec should state the property it tests for, not the
  rank it happens to read, because the two diverge exactly where a taxonomy is unsettled — which
  is where the records nobody has placed live.
  Also recorded, because it closes an open caution rather than opening one: D-020 found no
  `r__Riboviria` in an 800-row sample and was careful to say that must not be reported as absence
  from the corpus. The census settles it — **6,105 Riboviria records**, every one of them
  `c__Leviviricetes` and no deeper. All are correctly retained by the rule as written, whose
  stop-taxon limb removes a record whose *finest* assignment is a named stop and not one that
  merely sits under `r__Riboviria`. The caution was right and the number is now exact.

### D-052 — "IMG/VR v4" names two releases, and they disagree on exactly the metadata the audit needs
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** Evo 1's data availability section cites "curated prokaryotic viruses from the
  IMG/VR v4 database (Camargo et al., 2023)" and nothing more specific; Appendix B.2 repeats the
  same phrase. The publisher ships IMG/VR in folders identified by release *date*, not by version
  number, and two of them answer to v4: **2022-09-20** and **2022-12-20**. The v4 paper issued in
  the December. Nothing in either Evo paper distinguishes them.
- **Decision:** Pin **both**, and treat the choice as unresolved rather than picking the later one
  because it is later. The comparison that makes this matter is in
  `amazebio.imgvr.differs_between`, computed from the publisher's own md5sums: the two releases
  are **byte-identical** in their nucleotide sets (full and high-confidence) and in their
  host-information tables, and **differ** in their sequence-information tables (both variants)
  and their protein sets. The sequence-information table is where the **confidence label** and
  the **vOTU assignment** live. So the two candidate releases agree on precisely what Evo 1's
  prokaryotic-host rule reads and on the sequences themselves, and disagree on precisely what its
  high-confidence gate and its vOTU representative read — two of the three rules A7.1 could not
  run (D-047). A7.2 must therefore either run both releases and report the spread, or be given a
  release by the project owner; it may not quietly choose one.
- **Rejected:** Taking 2022-12-20 because it is contemporaneous with the paper Evo 1 cites — a
  plausible inference, and the kind this project is supposed to log rather than act on, since
  Evo 1's own corpus was built at an unstated date and the September release was available for
  three months before the paper issued. Taking 2022-09-20 because it is the first to answer to
  v4 — same objection in reverse. Treating the difference as immaterial because the sequences are
  identical — it is immaterial for the sequence set and decisive for two of the three rules this
  acquisition exists to unblock. Asking the authors — in scope for X3.1's disclosure
  correspondence, not for an acquisition task, and §4 forbids external circulation before then.
- **Consequence:** A §A0-shaped under-specification finding with a sharp edge: a published
  procedure cites a database version, the database distributes by date, two dated releases carry
  that version, and they differ in the field the procedure gates on. It belongs in A0.4's spread
  report and in X5.1's disclosure standard as a requirement — a filter spec should name the
  dated release it was applied to, not the version string, because a version string is not a pin.
  For A7.2: the host-count rule can be audited against either release, the sequence set is
  unambiguous, and the confidence and vOTU rules carry this ambiguity into whatever they report.

### D-053 — A conformance re-execution needs IMG/VR's metadata, not its sequence: 7.9 GB, not 128.7 GB
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** The obvious reading of "acquire the filter's input" is to stage the release, and
  the release is 128.7 GB per dated version — 48.3 GB of nucleotides, 31.5 GB of proteins and
  the rest metadata. A1.2's precedent is selective staging by component, and the question here is
  which files any downstream task actually reads.
- **Decision:** Stage **metadata only**: both sequence-information tables, both host-information
  tables, and the two READMEs — **7.9 GB of the 128.7 GB**, encoded as
  `amazebio.imgvr.conformance_inputs` so the scope is a function rather than a habit. No
  nucleotides and no proteins. The reason is not frugality but that every check A7.2 runs is a
  set operation over accessions and metadata: the forward diff asks which released records a
  predicate would have removed, the converse asks which removed records it would have kept, and
  both are joins on `IMGVR_UViG_*` identifiers against confidence, vOTU, host and taxonomy
  fields. None of them reads a base.
  **Both confidence variants are staged, and the unfiltered one is not optional.** Evo 1's first
  rule *keeps* records labelled High-confidence, so auditing that rule requires records that are
  not so labelled; JGI's pre-filtered high-confidence file cannot contain one, because every
  record in it passes the gate by construction. A run against the high-confidence file alone
  would report a clean gate as a matter of arithmetic. `tests/test_imgvr.py` pins that.
- **Rejected:** Staging the full release because the bucket is permanent and the decision would
  not have to be made twice — 241 GB across both candidate releases, for files no task reads, in
  a bucket with no `s3:DeleteObject`; pixi.toml's rule about unused pinned tools applies to
  unused pinned data, and permanence is an argument for care rather than for volume. Staging the
  high-confidence variant only, which is the subset Evo 1's pipeline keeps — it makes the first
  rule unauditable, which is the opposite of the point. Deferring the sequence until a task needs
  it *and* not recording why — the next reader would reasonably assume it was an oversight.
- **Consequence:** A1.7 is a ~7.9 GB acquisition per release rather than a 128.7 GB one, which
  also means the staging pass is small enough that AGENTS.md's in-region test does not arise at
  all (contrast D-050). If a later task needs IMG/VR sequence — A2's detectors are the plausible
  case — it stages the nucleotides then, as its own decision, and this entry is what it argues
  against.

### D-054 — JGI publishes the inventory and withholds the files; the pin is established before the bytes
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** A1.7's first question was whether the release is retrievable from this environment
  at all, since an unretrievable release is a finding to record rather than a failure to work
  around (the A1.1 pattern in D-019 and D-020). The answer is split, and usefully so.
- **Decision:** Record both halves. **The inventory is public.** JGI's data portal serves a
  complete file listing for the IMG/VR dataset — every file, its size, its release date and *the
  publisher's own md5sum* — with no authentication, at
  `https://files.jgi.doe.gov/search/?datasets=Custom_MPI-IMG_VR`. The dataset identifier
  `Custom_MPI-IMG_VR` was not guessed: it came from the portal's own redirect, after the
  documented download page turned out to be a JavaScript application with no static links. The
  listing is captured at `policies/captures/jgi-imgvr-inventory.json` (42 files, 10 releases,
  sha256 recorded in `sources.json`). **The files are not.** Every download endpoint returns
  HTTP 401 `{"detail":"Authentication credentials were not provided."}`, and the listing marks
  these records `_es_public_data: false`. A free JGI account exists; this environment has no
  credential for one.
  Because the checksums are public, `amazebio.imgvr.RELEASES` pins all 20 files of the two v4
  releases **before this project holds any of the bytes**. That is a stronger pin than one taken
  at download time: the figure was recorded before anyone went looking for a match, so a staging
  pass that verifies against it is checking the publisher's attestation rather than its own
  (the A1.3 standard in D-026 and D-027, not the weaker self-attestation D-040 had to accept).
- **Rejected:** Looking for a mirror — a secondary copy of a primary input is exactly what
  AGENTS.md forbids for factual claims about training data, and a mirror's bytes cannot be
  attributed to the publisher. Registering an account from this session — it accepts a data-use
  policy on the project's behalf and creates a credential the project owner did not ask for;
  that is theirs to do. Reading the 401 as "the data is gone", the error D-020 records in both
  directions: a status code is not a finding until the content behind it is read.
- **Consequence:** A1.7 cannot complete here, and stops in the right place: everything that can
  be established without the bytes is established and committed — the dated releases, the file
  roles, the full md5 pins, the two-v4 ambiguity, and the 7.9 GB scope. What remains is one
  credential. The task's own Done-when criteria about reading the metadata back are the only ones
  outstanding. Whoever resumes it needs a JGI account token in the environment's secrets and
  should not need to rediscover any of the above.

### D-055 — Evo 1's own Table S3 corroborates A7.1's census to within one record
- **Date:** 2026-10-15
- **Task:** A1.7 (verifying A7.1)
- **Context:** A7.1's headline rests on a denominator — 2,653,047 released records — and on the
  premise that one released row is one released record, which D-048 established by measuring the
  release's structure because nobody published it. Reading Evo 1's PDF for A1.7's first step
  (which IMG/VR release) turned up Table S3, where the authors publish their own statistics for
  the IMG/VR component of OpenGenome.
- **Decision:** Record the comparison as a verification of A7.1 rather than folding it into
  A1.7's own result. Evo 1 Table S3 (p43) publishes, for Prokaryotic Viruses / IMG/VR:
  **2,653,046** genomes/loci, **36,236** M bases, **13,658** average length. A7.1's census of
  the released `stage2` files counted **2,653,047** rows, **36,236,025,613** sequence characters
  and **13,658.3** average. Records agree to **+1**; bases agree to **0.0001%**; average length
  agrees exactly at the published precision.
  Two things follow, and the second matters more than the first. The denominator is right. And
  **the row-is-a-record premise is now corroborated by the developers' own published count**,
  independently of the structural argument D-048 made from block sizes and tag repetition — a
  count of context windows could not land within one of a count of genomes. Relatedly, Evo 2
  p24 states that for IMG/VR "phylogenetic tags are added at the beginning of every IMG/VR
  sequence" and that GTDB tags are added "every 131 kb", which is the mechanism D-048 measured
  as a 131,072-character block; cite that as consistent rather than as proof, since the table
  describes Evo 2's preprocessing and `stage2` is Evo 1's release.
  The **+1 is not explained** and is recorded as stated-versus-actual rather than rounded away.
  It is one record out of 2.65M; candidates include their count excluding a record, an
  off-by-one in the table, or one record present in two splits. The per-file split is train
  2,652,947 + valid 50 + test 50; train alone is 99 short of the published figure, so the
  published number is a count of the whole release and not of the training split.
- **Rejected:** Treating the agreement as exact and dropping the +1 — a conformance audit that
  rounds its own denominator has no standing to report a 95-record finding. Claiming Table S3
  as independent confirmation of the *filter's* behaviour — it is their count of their own
  output, so it corroborates our reading of the artefact and nothing about whether the filter
  worked. Moving this entry to A7.1 — it was found doing A1.7, and the log records where a
  thing was established.
- **Consequence:** A7.1's headline is materially stronger for the adversarial reader §7 calls
  for: its denominator and its unit of count both now rest on the developers' own published
  figures as well as on our measurement. A3.3's independent reimplementation gains a free check
  it should use — any second method whose record count is not 2,653,046 ± 1 has a bug. The
  unexplained +1 should be named in the Phase A write-up rather than smoothed over.

### D-056 — Both v4 releases are audited, and one of them is on tape
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** D-052 left a choice open that an acquisition task may not make for itself: Evo 1
  cites "IMG/VR v4" and two dated releases answer to it, differing in the metadata two of the
  three unrunnable rules read. The project owner was asked and chose **both, with the spread
  reported**, and chose to supply a JGI account token rather than fetch the files by hand.
- **Decision:** `tools/stage_imgvr.py` defaults to staging **both** 2022-09-20 and 2022-12-20,
  and A7.2 reports the confidence-gate and vOTU results as a range across them rather than a
  point. The host-count rule and the sequence set are unaffected, since those files are
  byte-identical across the two (D-052), so "both" costs one extra sequence-information table
  per confidence variant — about 6.9 GB more — and converts an unresolvable citation into a
  measured range, which is what §A0 asks of an under-specification.
  **One operational fact that changes the shape of the staging pass:** every file in JGI's
  listing carries a `file_status`, and the two releases differ. **2022-09-20 is `RESTORED`** —
  on disk, directly downloadable. **2022-12-20 is `BACKUP_COMPLETE`** — on tape, and
  unavailable until restored through `POST /request_archived_files/`, which is asynchronous and
  can take hours. So the staging tool requests a restore and polls rather than failing, and a
  run that ends with files still on tape says so and exits 0: re-running picks them up. Without
  that, the December release would have presented as a permissions failure, which is the
  misreading D-020 warns about in both directions.
  Authentication is a **Bearer token in the `Authorization` header** — JGI's API declares
  exactly one security scheme (`files.jgi.doe.gov/swagger.json`: apiKey named `Authorization`,
  in header), so this is read from their spec rather than guessed. Read from `$JGI_API_TOKEN`
  and never written to a manifest or an error.
- **Rejected:** Staging only the September release because it is already on disk — it would pick
  the audited input by what was convenient to fetch, which is the worst available reason, and it
  is precisely the choice D-052 says may not be made quietly. Failing the run on a tape file —
  it reads as an access problem and would have sent the next person after a credential that was
  already working. Treating the two releases as one artefact and merging their metadata — they
  disagree about the confidence label, so a merge would silently pick a winner per record.
- **Consequence:** A1.7 completes in two passes rather than one: September immediately once a
  token exists, December after a restore. A7.2 inherits a range rather than a number for two of
  its five gaps, and should report it that way from the start rather than discovering it late.
  Also worth recording because it caught a real bug: the inventory check compares live listing
  against capture against pins, and its first run reported four changed files that had not
  changed. Two 2018 directories share a release date *and* four file names, so a
  `(date, name)` key compares one release's file against another's. Every lookup in
  `amazebio.imgvr` and `tools/stage_imgvr.py` is keyed on `(date, directory, name)`, and
  `tests/test_imgvr.py` pins that the collision exists so the key cannot be simplified back.

### D-057 — A1.4 and A7.1 declared the same facts twice; the rule-input table and the released-format parser are unified
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** A1.4 and A7.1 ran in parallel and converged on the same problem from opposite
  ends. A7.1 needed to know which of Evo's published rules its release could re-execute, and
  built `conformance.RULE_INPUTS` plus `RELEASE_INPUTS`, deriving a restricted policy and
  reporting `3/6` coverage (D-047). A1.4 needed to classify every record rather than every rule,
  and built `policyspec.Evidence` plus a new `Outcome.UNRESOLVED`. Both tracks also wrote a
  parser for the released lineage tag and a splitter for the released row. The two
  rule-input tables agreed on all eight kinds, and the agreement was luck: that mapping decides
  which of an author's rules we hold them to, and A7.2's first step is to extend the release
  inventory with IMG/VR v4. Both branches were unmerged when this was noticed, which is the only
  cheap moment to fix it.
- **Decision:** Unify the two declarations that are the same fact at the same granularity, and
  guard the one that is not. `RULE_INPUTS` moves to `policyspec` as the single declaration,
  keeping A7.1's input names because its artefacts and write-up already report them;
  `conformance.RULE_INPUTS` re-exports it and A1.4's per-key evidence checks take their channel
  from it. A1.4 drops its own lineage parser and row splitter in favour of A7.1's, which read
  the format better: prefix wins over position, a disagreement is recorded rather than resolved,
  and a short tag is a formatting variation rather than a finding — so a malformed tag is now
  counted and its taxonomy still used, where A1.4 previously discarded the record. The release
  inventory stays in two granularities, because they genuinely differ: A7.1 restricts per
  channel, A1.4 checks per key, and the key matters (Evo 2's release carries
  `record_attributes` in the shape of an accession, which answers no rule that reads that
  channel). A test pins their agreement instead — identical kept rule sets on `stage2`, and both
  declarations refusing Evo 2's release.
- **Rejected:** Forcing the release inventory into one representation — it would mean rewriting
  `restrict` inside a module at `review` whose numbers are published, and rewriting the test
  that guards a real hazard: a release that carried vOTU identifiers would make `keep_one_per`
  checkable and the diff would report zero removals as conformance. Having A1.4 import A7.1's
  tables wholesale — its coarser per-kind mapping cannot express a rule that needs every host
  class rather than one, which is what separates the strict reading's exclusivity rule from the
  literal reading's count. Leaving both and documenting the overlap — the drift it invites is
  not visible in any artefact, which is what makes it dangerous rather than merely untidy.
  Keeping A1.4's stricter parser — it raised on a short tag and on a prefix out of position,
  discarding records whose taxonomy is perfectly usable, and a parse failure that imitates an
  unlabelled record corrupts one of this audit's own findings.
- **Consequence:** `policyspec` now owns the statement of what each rule kind reads, so a new
  rule kind must be declared there and both consumers pick it up at once. A7.2 extends
  `RELEASE_INPUTS` for IMG/VR v4 as planned, and the cross-check test will fail if the
  corresponding `Evidence` declaration in `corpora.SOURCES` is not extended with it — which is
  the intended behaviour, not an obstacle: the two must move together. One piece of layering is
  left untidy on purpose: `corpora` imports the released-format primitives from `conformance`,
  which inverts the natural direction, because moving them would have churned a module under
  review. Whoever closes A7.1's review should move `LineageTag`, `parse_lineage_tag`, `RowShape`,
  `split_row` and `BLOCK_CHARS` into `corpora` and re-export them, at which point the import
  direction is right and nothing else changes.

### D-058 — Evo 1's own Figure S1 reconciles our census by realm, and sizes the host rule's reach
- **Date:** 2026-10-15
- **Task:** A7.1 (found while starting A1.7)
- **Context:** D-055 checked A7.1's census against Evo 1's Table S3 and found agreement to within
  one record on three aggregate quantities. Aggregates can agree while composition does not, and
  the project owner asked whether the three rules no release can re-execute could be got at any
  other way. Figure S1 turns out to answer both: its panels publish per-category counts for the
  same component, and panel B is downstream of one of those three rules.
- **Decision:** Record the reconciliation, with its provenance caveat stated rather than buried.
  **By realm** (Figure S1A, p41), published against our census: Duplodnaviria 2,628,512 against
  2,628,513; Monodnaviria 17,781 against 17,781; Riboviria 6,105 against 6,105; Other 648
  against 648. **Three of four categories agree exactly**, and the +1 from D-055 is therefore
  localised: whatever it is, it is one Duplodnaviria record. Their `Other` bin decomposes
  exactly into our Varidnaviria 413, Adnaviria 140 and **the 95 realmless records** — so the
  records behind A7.1's headline finding are accounted for in the developers' own published
  figure, not only in ours. That is the strongest corroboration this finding is going to get
  short of the authors confirming it.
  **By host kingdom** (Figure S1B): Unknown 2,374,733, Bacteria 276,569, Archaea 1,744, and
  **no Eukaryota category at all**. The last is consistent with the filter's stated aim. The
  first is the useful one, and it is not the contradiction it first looks like: the published
  rule retains records whose *taxonomic classification* was found in a prokaryotic host at least
  twice, so a record with no host annotation of its own survives on evidence attached to its
  classification. **89.5% of retained records sit in that position.** That sizes how much of the
  corpus was kept on evidence not attached to the record, and it settles that A7.2's
  host-rule check must aggregate over classifications and join back, never read a per-record
  host field — the unit error that would otherwise produce a confident wrong number.
  **Provenance is weaker here than for Table S3, and the entry says so.** Figure S1 is a
  flattened raster: `Duplodnaviria` appears nowhere in the PDF's text layer though it is 99% of
  the released records, so these values were read off the rendered image and X1.4's quote
  checker cannot reach them. What backs them is arithmetic — each panel must sum to Table S3's
  record count, which *is* text-extractable — and `tools/conformance_diff.py` asserts both sums
  on import so a mis-transcription cannot reach an artefact. Panel B's Archaea label is printed
  malformed as "N = 17,44"; 1,744 is recovered as the residual, the printed form is kept
  alongside it, and that is exactly why the sum check is load-bearing rather than decorative.
- **Rejected:** Treating the figure values as equivalent in standing to the table's — they are
  not, and the write-up must not cite them as though a quote checker had verified them.
  Publishing the realm percentages rather than the counts — the counts are what the figure gives
  and what reconciles; percentages would invite comparison with D-020's sample, which was
  explicitly not a census. Reading the panel B result as the host rule having failed — the
  classification-level reading accounts for it and is the natural reading of the published
  sentence; asserting a failure here would be the over-claim §7's adversarial reader is waiting
  for. Adding an image library to the pinned environment to extract the figure — the PNG was
  rendered in the scratchpad with the standard library, and nothing in a pipeline needs it.
- **Consequence:** A7.1's census is now corroborated per category rather than only in aggregate,
  and the 95-record finding is visible in the developers' own figure. A7.2 inherits a hard
  constraint on its host-rule check and a quantity to compare against once IMG/VR v4 is staged:
  if a re-execution does not reproduce roughly 2,374,733 retained records with no host kingdom,
  the reading is wrong. And one for whoever writes Phase A up: the exact counts in this paper's
  figures are not in its text layer, so anything relying on a figure needs reading, not grepping
  — there may be more of this in the Evo 2 and ESM3 papers, which nobody has checked.

### D-059 — A1.4's "consumed by an A2 task" criterion moves to A2.1, which is the first point it can be shown
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** A1.4's Done-when list required the manifest format to be "documented and consumed
  by at least one A2 task". The first half is satisfied — `metrics/manifests.md` specifies the
  format, written to be usable without reading the code, as A3.3's independent-reimplementation
  requirement needs. The second half cannot be satisfied from inside A1.4: all five A2 tasks
  depend on A1.4 and none has started, so the criterion makes the task that unblocks them wait
  on them. That is exactly the phantom-progress D-042 removed from A3.1, for the same structural
  reason, and leaving A1.4 at `review` for it would park a finished pipeline behind unstarted
  work while ten tasks stay blocked.
- **Decision:** Split the criterion the way D-042 did. A1.4 keeps the half it can demonstrate —
  the format is specified, and the artefacts conform to the specification — and closes. A2.1, as
  the first detector, picks up the consumption half as a Done-when: it reads the manifests as the
  shared input rather than re-deriving a surviving set, and it tags its detections with
  `amazebio.apply.route_for`, which is the point of contact that would catch a format that looks
  complete and is not usable.
- **Rejected:** Holding A1.4 at `review` until a detector lands — it misreports the board for as
  long as that takes and blocks the ten tasks A1.4 gates. Writing a token A2 consumer inside
  A1.4 to satisfy the criterion — a detector written to validate a format rather than to detect
  anything is scope creep that proves nothing, and §A2's detectors are substantial tasks with
  their own thresholds to fix before results are seen. Dropping the criterion — the risk it
  guards against is real: a format that no downstream task has read is a format nobody has
  tested, and recording that in a closed task's notes is how it stops being anyone's job.
- **Consequence:** The format contract is now checked at A2.1 rather than at A1.4, so A2.1 should
  expect to find gaps in `metrics/manifests.md` and fix them there rather than treating the spec
  as frozen — it is a data contract this project owns, not a published standard, and A1.6 will
  write to it too. One concrete thing for A2.1 to verify rather than assume: `route_for` refuses
  to map a removed record to `conformance_failure`, so a detector meeting a record from a
  manifest's removed set has to route it through A7.1's evidence rather than tag it in passing.

### D-060 — The download endpoint A1.7 was pointed at does not accept a GET; the publisher's own spec names the one that does
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** A session was told the `JGI_API_TOKEN` secret had been added, and found no such
  variable in its environment and no credential reaching JGI: every request to
  `files.jgi.doe.gov` still answers `401 {"detail":"Authentication credentials were not
  provided."}`, and a request carrying a deliberately bogus `Authorization: Bearer` header gets
  the same answer rather than an invalid-token one. So the authenticated path still has not run.
  Probing it did, however, settle a question the previous pass had closed on weaker evidence.
  That pass recorded the download host as unmoved because
  `files.jgi.doe.gov/filedownload/` "still answers (401 unauthenticated), so the endpoint is
  live and no change is needed". It answers 401 to *every* method, and its `Allow` header reads
  `POST, OPTIONS`. `stage_imgvr.py` was sending a GET.
- **Decision:** Take the shape from the publisher's download API spec, which is a separate
  service from the portal search API and has its own document:
  `files-download.jgi.doe.gov/apidoc/?format=openapi` (version 202610.92006.17, the same version
  string `files.jgi.doe.gov/swagger.json` reports). It declares two operations,
  `POST /download_files/` for a zipped multi-file stream and
  `GET /download_files/{jamo_id}/` for one file by the `_id` the public listing gives it. The
  single-file read is what this task needs — each file is verified against its own published md5
  before upload, which a zip of ten files does not allow — so `amazebio.imgvr.download_url`
  builds that URL and `stage_imgvr.py` uses it. Unauthenticated, that path answers 401 with
  `Allow: GET, HEAD, OPTIONS`.
- **Rejected:** Leaving the GET in place and discovering this when a token arrived — the failure
  mode is the expensive one. This endpoint checks authentication before method, so a GET to the
  POST-only path returns 401, which is exactly what `stage_imgvr.py`'s own guard reports as a
  missing credential. A worker with a valid token would have read "the token is not working",
  re-copied it, and had the same thing happen again. Guessing the shape from the search API's
  query-parameter form instead of reading the download API's own spec — D-019 and D-020 are both
  records of a guessed URL answering in a way that looked like data.
- **Consequence:** Two things for whoever resumes with a credential. **A mid-run 401 is now
  ambiguous in one fewer way but not unambiguous** — it still means either an expired session
  token or a file whose `_id` has changed, and the task file's existing advice to re-copy the
  token before concluding anything about permissions stands. **The 409 is the tape signal.** The
  download spec documents 409 as "files that are currently on tape and need to be restored",
  which is the same condition `file_status: BACKUP_COMPLETE` reports in the listing. The tool
  decides from the listing and never sees the 409; that is fine, and worth knowing if a file is
  ever restored between the listing fetch and the download.

### D-061 — The JGI token is valid and never reaches JGI: the session proxy owns credential injection for that host
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** The project owner supplied a credential and it is now in the session environment
  as `JGI_API_TOKEN`. It is well-formed and current: a three-segment RS256 JWT issued by
  `https://auth.jgi.doe.gov/auth/realms/jgi-web`, `iat` 12:58:39 UTC and `exp` 00:01:21 the
  following day, so roughly eleven hours of validity remained when it was tested. The
  authenticated download still fails, and it fails the same way it did with no credential at
  all: `401 {"detail":"Authentication credentials were not provided."}` from
  `GET /download_files/{jamo_id}/`. That is the message Django REST Framework returns when the
  `Authorization` header is **absent or does not carry the expected keyword** — not the
  message for a token that is present and rejected, which is what an expired session token
  would produce.
  Three observations isolate where it is lost, and the third is the one that settles it:
  1. The request is built correctly. The download API's own spec
     (`files-download.jgi.doe.gov/apidoc/?format=openapi`, version 202610.92006.17) declares one
     security scheme — `apiKey`, name `Authorization`, in `header` — and types the parameter
     with pattern `^Bearer \S+$`. That is the shape sent, via `amazebio.imgvr.download_url`
     (D-060).
  2. The token's own issuer reports no credential either. `GET
     /protocol/openid-connect/userinfo` on `auth.jgi.doe.gov` answers `401` with
     `WWW-Authenticate: Bearer realm="jgi-web"` and an empty body, **identically for the real
     token and for `Bearer notatoken`**. Keycloak adds `error="invalid_token"` and an
     `error_description` when a bearer token is present and bad; the bare challenge is its
     no-token response. So two different JGI services, on two hosts, both see no credential.
  3. The client does send it. A control request carrying the same header to a local HTTP server
     on `127.0.0.1` — which is in the proxy's `noProxy` list and therefore not proxied — arrives
     with `Authorization` present and 1540 bytes long, exactly `Bearer ` plus the 1533-character
     token. The header is constructed and transmitted; it is removed in transit.
  The session's outbound HTTPS goes through an agent proxy that re-terminates TLS and is
  configured to **inject credentials for `*.jgi.doe.gov`**. That is the only element between the
  client and the publisher, and it is the one element documented to rewrite this exact header
  for this exact host. Whatever it injects does not satisfy the API, and a client-supplied
  header does not survive it.
- **Decision:** Record this as an environment finding and stop probing it. The token is not the
  problem, the endpoint is not the problem (D-060 settled that), and the tool is not the
  problem. What is needed from the project owner is that the credential reach JGI in the
  `Authorization: Bearer <token>` form the publisher's spec requires — in practice, that the
  token be available to this session as the plain environment variable `JGI_API_TOKEN` **without
  the proxy also claiming `*.jgi.doe.gov` for credential injection**, since that claim is what
  strips the header the tool sets. A session started after that change picks it up.
- **Rejected:** Routing around the proxy — unsetting `HTTPS_PROXY`, disabling TLS verification,
  or reaching JGI by any path that evades the policy layer. The environment forbids all three and
  they are the wrong answer to a misconfiguration regardless: a corpus acquired by circumventing
  the session's egress policy is not a corpus this audit can cite. Also rejected: concluding the
  token had expired and asking for another. The task file's existing advice is to read a mid-run
  401 as "expired, re-copy the token" before suspecting permissions, and that advice is right in
  general and wrong here — the JWT's own `exp` and the shape of the 401 both rule expiry out, and
  a second token would have been stripped exactly as the first was. Checking the claim before
  acting on it saved a round trip rather than costing one.
- **Consequence:** A1.7 stays `in-progress` and its waiting-on line changes from "a credential
  that reaches a session" to the narrower and more actionable "a credential that is not
  intercepted". Everything that can be established without the bytes remains established, and
  one thing was added while blocked: the transfer path is no longer the one that was written.
  `download_verify_upload` buffered each whole file in memory, so the 5.0 GB
  sequence-information table would have peaked at about twice that against 15 GB of RAM; it now
  spools to disk, uploads with `upload_file` rather than a `put_object` whose 5 GiB single-PUT
  ceiling the file sits just under, and is covered by tests for the no-delete bucket's one
  real hazard — bytes uploaded that were never verified. So the first authenticated run will
  exercise a path that has been tested, which it would not have before.

### D-062 — With the token reaching JGI, the download is a POST returning a zip; the documented single-file GET answers 404
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** The project owner made `JGI_API_TOKEN` a plain environment variable and removed
  the proxy's claim on `*.jgi.doe.gov`, which is exactly what D-061 asked for. The credential
  now reaches the publisher, and that is settled by the shape of the refusals rather than by
  assertion: with the header the download host answers `404` or `405`, without it `401
  {"detail":"Authentication credentials were not provided."}`. D-061 is closed. The first
  authenticated measurement in this task's history then moved the endpoint a second time.
  `GET /download_files/{jamo_id}/` is the publisher's own documented single-file read and is
  what D-060 corrected to. Authenticated, it answers `404` for **every** IMG/VR file tried —
  the 4 KB README and the 696 MB host table alike — and as nginx HTML rather than the API's own
  JSON, so the request is authenticated and routed and the bytes are still not served that way.
  Unauthenticated, the same URL answers `401` with `Allow: GET, HEAD, OPTIONS`, which is why no
  measurement made before a credential existed could have distinguished the two. D-060 was not
  wrong about what the spec documents; it was as right as an uncredentialed measurement allows.
- **Decision:** Fetch files through `POST /download_files/` on the same host, keyed by organism
  id: `{"ids": {"Custom_MPI-IMG_VR": {"file_ids": [...], "top_hit": "<id>"}}}`. The response is
  a single `application/zip` stream holding the requested files under a per-release directory,
  plus a `Download_<n>_File_Manifest.csv` carrying the publisher's md5 and size for each. Two
  details are dictated and neither is guessable: `top_hit` is the `_id` **string** of the
  organism's top-hit file, and posting the object the search response nests there instead
  returns HTTP 500; and `POST /request_archived_files/`, which starts a tape restore, takes the
  same organism-keyed body — a flat list of ids is refused as HTTP 404 by the search host's
  nginx, reading as an absent endpoint rather than a malformed body.
- **Verified:** End to end before any bulk transfer. The two 2022-09-20 READMEs came back inside
  the zip at exactly the sizes and md5s pinned in `amazebio.imgvr.RELEASES` — pins recorded from
  the public inventory before this project held any of the bytes, which is the A1.3 standard and
  not D-040's weaker self-attestation. All six metadata files of the 2022-09-20 release then
  staged on the same path, each verified against the publisher's md5 before its upload, and the
  three fields this task exists for were read back out of the bucket: `Confidence`, `vOTU` and
  `Host taxonomy prediction` are columns 9, 5 and 16 of the staged sequence-information table.
- **Rejected:** Treating the 404 as a transient or a permissions problem and retrying or
  re-copying the token. Both were ruled out by measurement — a small file and a large one fail
  identically, and the unauthenticated control on the same URL returns a different status — and
  D-061 exists precisely because the previous pass's 401 looked like a credential problem and
  was not. Also rejected: keeping the single-file GET as a fallback. Two endpoints for one job
  means a future failure is ambiguous between them, which is the ambiguity that cost D-060 and
  this entry a round trip each.
- **Consequence:** The transfer path changes shape with the endpoint. One file is requested per
  call, so the zip holds one member and the spool stays bounded by the largest single file
  rather than by the 7.9 GB release; the member is verified by streaming it once and uploaded by
  streaming it again, so the extracted copy never lands on disk; and verification still strictly
  precedes upload, because the corpus bucket withholds `s3:DeleteObject` and an object that
  completes is permanent. A zip that does not hold exactly one member with the expected name
  refuses rather than guessing which member was meant. The 2022-09-20 release — 6 files,
  7.92 GB — is staged and verified. The 2022-12-20 release is on tape and its restore is
  asynchronous, so A1.7 completes in the second pass D-056 anticipated.

### D-063 — The two releases are not two v4s: the publisher calls the December one v4.1, and says what it corrects
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** D-052 established from the public inventory that two dated releases answer to
  "IMG/VR v4" — 2022-09-20 and 2022-12-20 — and that they differ in exactly the
  sequence-information table and the protein set. That was inferred from the publisher's md5sums,
  because the bytes were not in hand. They now are, and the releases' own READMEs say it
  outright. The September one opens `### IMG/VR database v4 release Oct. 2022 ###`. The December
  one opens `### IMG/VR database v4.1 release Dec. 2022 ###` and carries a note:
  > Note: IMG/VR version 4.1 includes the same sequences as IMG/VR v4, but fixes issues with two
  > files (IMGVR_all_proteins.faa and IMGVR_all_Sequence_information.tsv) in which a few
  > sequences/rows were incorrect
  > Everything else is identical between v4.1 and v4

  Two things follow. D-052's md5-derived difference set is confirmed by the publisher
  independently and exactly — the same two files, named in the same terms. And the second
  release is not a rival v4; it is an **erratum** of v4, with a distinct version string.
- **Decision:** Record the September 2022-09-20 release as **v4** and the December 2022-12-20
  release as **v4.1**, and keep auditing both (D-056 stands). The naming changes what the
  disagreement between them *means*, not whether both are needed. Evo 1 cites "IMG/VR v4"; on the
  publisher's own naming that names the September release and not the December one, which is a
  narrower reading than D-052 could support. But the content of the erratum is that some rows of
  the September sequence-information table — the table carrying the confidence label and the vOTU
  assignment — **were incorrect**. So the reading that best fits Evo 1's citation is also the
  reading in which Evo 1's high-confidence gate and vOTU rule were applied to rows the publisher
  has since withdrawn. Auditing both is what measures that, and auditing only the one Evo 1 names
  would hide it.
- **Rejected:** Treating the citation as settled and dropping the December release. The version
  string points at September, but Evo 1's corpus was built at an unstated date and the paper
  issued after v4.1 did; a citation is not a pin, which is D-052's point and is not weakened by
  knowing the second release's name. Also rejected: treating v4.1 as strictly superior and
  auditing it alone. The audit's subject is what Evo 1's filter was applied to, not what the
  publisher now considers correct — if the filter read withdrawn rows, that is the finding.
- **Consequence:** D-052's unresolved-ambiguity finding survives with a sharper edge for A0.4 and
  X5.1: a published procedure cited a version string, the publisher issued a correction under a
  new version string three months later touching exactly the field the procedure gates on, and
  the procedure's citation cannot distinguish them. It also gives the conformance work a concrete
  expectation — the difference between the two sequence-information tables should be a small
  number of rows, not a structural change, and a diff that shows otherwise means something is
  wrong with our reading rather than with the publisher. `amazebio.imgvr` should carry the
  version strings alongside the dates so that no later task has to re-derive this from a README.

### D-064 — The IMG/VR denominator is 15,677,623 records, and Evo 1 kept 16.9% of it
- **Date:** 2026-10-15
- **Task:** A1.7
- **Context:** With both releases staged and verified, the counts A1.7 exists to supply are
  measured rather than cited. Streaming the four metadata tables out of the corpus bucket
  (`tools/imgvr_composition.py`, artefact `artifacts/a1-7/composition.json`):

  | | v4 (2022-09-20) | v4.1 (2022-12-20) |
  |---|---|---|
  | records | 15,677,623 | 15,677,623 |
  | distinct vOTUs | 8,606,551 | 8,606,551 |
  | High-confidence | 5,576,197 | 5,576,197 |
  | Putative | 10,101,426 | 10,101,426 |
  | high-confidence file records | 5,576,197 | 5,576,197 |
  | distinct vOTUs, high-confidence only | 2,917,521 | 2,917,521 |
  | malformed rows | 0 | 0 |

  Three things fall out. The high-confidence file matches the `High-confidence` label count in
  the unfiltered file **exactly**, in both releases, so the publisher's two files are internally
  consistent and either can be used as the gate's output. The two releases agree on **every**
  aggregate counted here while differing in md5 — which is exactly what D-063's erratum note
  predicts: v4.1 corrects the content of a few rows in place, it does not add or remove any.
  And the pre-filter population is **15,677,623** against Evo 1's own stated post-filter figure
  of 2,653,046 (Table S3, D-055): Evo 1's procedure retained **16.9%** of IMG/VR v4.
- **Decision:** Record 15,677,623 as the audited denominator for the Evo 1 viral component, and
  state the retained fraction as 16.9% against Evo 1's own published count rather than against
  A7.1's census of the release, which exceeds it by one record for reasons D-055 leaves open.
  Both numbers travel together in the artefact so neither is silently substituted for the other.
- **Not claimed here:** that the three published rules reconcile to 2,653,046. They are close
  enough to be suggestive — the high-confidence gate leaves 5,576,197, of which 2,917,521 are
  distinct vOTUs, and Evo 1 reports 2,653,046, a further 9.1% down, which is the order of
  magnitude a prokaryotic-host requirement would remove. That is **A7.2's** computation, over
  joined accessions and not over aggregates, and stating it as a result here would be exactly
  the scope widening AGENTS.md forbids. It is recorded as a prediction A7.2 can falsify.
- **Rejected:** Reporting the retained fraction against the high-confidence subset (47.6%)
  rather than against the full release. The published procedure's input is IMG/VR v4, and the
  high-confidence gate is the procedure's own first step — using its output as the denominator
  would credit the filter with a reduction and then exclude that reduction from the measurement.
  Also rejected: treating the identical aggregates as evidence the releases are interchangeable.
  They disagree at row level by construction, and A7.2's checks are row-level.
- **Consequence:** A1.7's last open criteria close. **This is the real input, not a proxy** —
  the publisher's own files, at the publisher's own checksums, pinned from a public inventory
  before this project held any bytes. The one qualification, and it is the same one D-052 and
  D-063 record: *which* of v4 and v4.1 Evo 1 applied its procedure to is not determinable from
  Evo 1's words. Both are staged. For anything counted at aggregate level the ambiguity is
  immaterial, since the aggregates are identical; for A7.2's row-level conformance it is not,
  and A7.2 must report both or say which it used and why.

### D-065 — Scope shares are normalised within one representation, which corrects A1.2's published 0.2%
- **Date:** 2026-10-15
- **Task:** A4.3
- **Context:** `opengenome.composition()` divides each component's bytes by the whole release,
  and an OpenGenome2 release spans two trees — FASTA and JSON — that `policies/evo.md` §7
  warns are not a strict mirror and must never be summed. A4.3 reports one row per component,
  choosing the staged representation, so taking `share_of_release` for that row silently uses a
  denominator that includes the other tree. The symptom was unmissable once the table was
  assembled: Evo 2's out-of-scope share came out at **49%**, which is not a plausible answer
  for a policy scoped to a single viral component. A1.2's published figure has the same shape —
  `policies/evo.md` reports the filtered component as **0.2% of OpenGenome2** by comparing
  10.4 GiB of IMG/VR FASTA against the 5.0 TiB release total, which is FASTA bytes over a
  denominator that includes the JSON tree. That is the summing the same document forbids.
- **Decision:** Normalise within the chosen representation and state the representation in the
  denominator on every figure. Within the FASTA tree the filtered component is **0.41%** of
  OpenGenome2 and the out-of-scope share is **99.59%**; for OpenGenome v1, which is parquet
  only and so unaffected, the filtered component is **11.52%** and the out-of-scope share
  **88.48%**. Both the within-representation share and the whole-release share are carried in
  `artifacts/a4-3/scope.json`, so the corrected and published figures can be reconciled rather
  than one quietly replacing the other.
- **Note on direction:** the correction makes the filtered component **larger** — 0.41% rather
  than 0.2% — so it weakens the headline slightly rather than strengthening it. Recording that
  explicitly because a correction that happens to favour the author's thesis deserves more
  scrutiny than one that does not, and this one does not. A test asserts the direction, so a
  regression cannot silently flatter the filter.
- **Rejected:** Keeping the whole-release denominator for continuity with A1.2's write-up. It
  is wrong by that document's own rule, and §7's adversarial reader will check it. Also
  rejected: summing the two trees into a single corpus size — they overlap in content and
  differ by a factor of two on GTDB alone, so their sum is not a quantity.
- **Consequence:** `policies/evo.md`'s 0.2% needs amending when A6.1 writes Phase A up; it is
  not amended here, because A4.3 owns the share and A1.2's prose is A1.2's. The headline this
  task delivers is unaffected in substance and sharper in form: **the same policy, inherited
  verbatim by Evo 2 ("As previously described"), covers 11.52% of OpenGenome v1 and 0.41% of
  OpenGenome2.** The scope gap widened as the corpus grew, which is D-007's claim measured.

### D-066 — The host rule counts sequences per classification, and the unit is declared before the numbers
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** Evo 1's third published rule keeps "only sequences whose assigned taxonomic
  classification was found within a prokaryotic host at least twice". D-058 already settled the
  subject of the count from the developers' own Figure S1B: it is the **classification**, not the
  record, because 89.5% of their retained records carry no host kingdom at all and a per-record
  reading cannot retain any of them. What D-058 did not settle, because the published sentence
  does not, is what one *finding* is. The publisher offers three countable things per
  classification, and they are not the same number: the sequences of that classification carrying
  a prokaryotic host prediction; the rows of the host-prediction table for those sequences, of
  which one sequence may have several; and the distinct host taxa the classification was
  predicted in. AGENTS.md forbids choosing after looking.
- **Decision:** `amazebio.conformance.PRIMARY_HOST_UNIT = HostUnit.RECORDS` — sequences of the
  classification carrying a prokaryotic host prediction — declared in code and committed before
  the pass that computes any of the three ran. The argument, in one line: the sentence's
  grammatical subject is "sequences", so a sequence found in a prokaryotic host is the natural
  unit of a finding; it is the only one of the three that neither inflates with the publisher's
  prediction-method count nor demands two *different* hosts where the text asks for two findings.
  The other two are computed on every run and travel with the headline as a sensitivity, per
  reading, in the artefact and in the write-up — because the choice is ours and a reader is
  entitled to see what it cost. The count is built over the whole database per classification and
  joined back to the record, never read from a record's own host field.
- **Rejected:** Reading the rule per record — it is the unit error D-058 exists to prevent, and it
  would remove every record with no host annotation, which is most of the corpus the filter kept.
  Counting host-prediction rows as primary — the publisher emits one row per prediction *method*
  as well as per host, so a sequence with a CRISPR match and a k-mer match to the same host
  contributes two findings to a threshold of two, which makes the rule turn on IMG/VR's method
  coverage rather than on host evidence. Counting distinct host taxa as primary — it reads "twice"
  as corroboration by two different hosts, which is a defensible sentence but a different one.
  Picking whichever unit reproduced Evo 1's published count most closely — that is fitting a
  predicate to the data it audits, which D-051 forbids outright.
- **Consequence:** Every host-rule number in A7.2 names its unit. The three readings of the
  *policy* and the three readings of the *unit* are reported as separate spreads and never
  multiplied into one, because they are different kinds of under-specification: one is an
  ambiguity in what the authors meant, the other in what their data lets anyone count.

### D-067 — The vOTU rule is deferred, not dropped, and the retained total is an interval
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** A7.1 split a published policy in two against a release: the rules whose inputs the
  release carries, and the rules it does not (D-047). The input side breaks that in two places.
  Every input Evo 1's vOTU rule reads is present in IMG/VR v4 — the vOTU assignment is a column —
  and the rule still cannot be re-executed per record, because `keep_one_per` depends on the
  order records arrive in and no published source states one (D-017). Reporting it as "input
  missing" would be false. Reporting it as checkable would hand `conformance.diff` a rule that
  retains every record as its own representative and reports zero removals, which reads as
  conformance — the exact failure A7.1's guard exists to prevent.
- **Decision:** A third category. `Restriction.deferred` holds a rule whose inputs are all present
  and which is order-dependent; it is held out of the record-level chain, counted in the coverage
  denominator like a dropped rule, and compared at the unit of the attribute it deduplicates on.
  Two numbers are therefore reported side by side and never merged: `rule_coverage`, the
  record-level figure (5/6 for Evo 1's literal reading against this input, against A7.1's 3/6
  against the release), and `unit_coverage` (6/6), which counts the vOTU rule as run at its own
  unit. The guard inside `diff` stays, unreachable through `restrict` and tested directly, because
  it is what will stop the next order-dependent rule kind from producing the same silent zero.
  **And the retained total becomes an interval.** The published order gates on confidence, then
  keeps one representative per vOTU, then applies the host and taxonomy rules — so one surviving
  vOTU is one retained record and whether a vOTU survives depends on which of its records was
  chosen. Where every high-confidence record of a vOTU carries the same classification the choice
  cannot matter; where they do not, it does. `votu_bounds` reports both ends, and the width is
  exactly the vOTUs whose records straddle the predicate.
- **Rejected:** Sorting the input deterministically and reporting the resulting count — it is a
  number, and it is our sort order rather than their filter, which is precisely what D-017
  refused. Reporting the midpoint or either end alone — AGENTS.md requires uncertainty to travel
  with the estimate, and here the uncertainty is not statistical but a gap in the published
  procedure, which makes it more important to show, not less. Folding the vOTU comparison into a
  record-level conformance rate — a rate mixing a per-record check with a per-vOTU one is neither.
- **Consequence:** A7.2 reports a conformance rate for the vOTU rule at vOTU level with the unit
  printed beside every number, and the retained-count check against Evo 1's own Table S3 figure
  asks whether a published count falls *inside* an interval rather than how close it is to a
  point. X5.1 inherits a requirement with a clean justification: publishing the input order of an
  order-dependent filter step costs a sentence and is the difference between a reproducible step
  and an unreproducible one.

### D-068 — IMG/VR ships two accession shapes, and the second one is the giant viruses
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** Every count in A7.2 is a join: the host table against the sequence table, and Evo
  2's released FASTA against both. 15.7 million 28-character accessions do not fit the memory this
  pass runs in as dictionary keys, so `IMGVR_UViG_<taxon_oid>_<n>` is packed losslessly into one
  integer. The first version of that packing raised on anything else and the caller skipped the
  row. Measuring the skipped rows rather than trusting the count found a second published shape:
  `IMGVR_UViG_GVMAG-<M|S>-<oid>-<n>_<m>`, whose middle field is a giant-virus
  metagenome-assembled genome identifier carrying letters and hyphens. **1,783 of Evo 2's released
  accessions are of that shape.** Giant viruses infect eukaryotes, which makes these the single
  worst population to lose from an audit of a filter aimed at eukaryote-infecting viruses: they
  would have vanished from the converse direction silently, and their absence would have made the
  filter look cleaner than it is.
- **Decision:** Carry them. `imgvr.uvig_join_key` packs the numeric shape and falls back to a
  truncated BLAKE2b digest of the accession, returned negative so it cannot collide with a packed
  key by construction. The digest is a function of the accession string alone, which is what lets
  two passes run at different times join on it without a shared vocabulary. A hash is not an
  injection, so both passes check: `imgvr.collision_free` compares the number of distinct
  non-packable accessions against the number of distinct keys and the pass **raises** rather than
  emitting an artefact if they differ. The count and examples of both shapes are carried in every
  artefact, as is the count of accessions this audit cannot read at all, which is a different and
  so far empty category.
- **Rejected:** Dropping the non-packable accessions and reporting the count — 1,783 records is
  small and they are not a random 1,783. Widening the packing to cover the GVMAG fields — it has
  four of them and would not fit an `int64`, and a packing that fails on the next shape the
  publisher introduces fails the same way this one did. A vocabulary-assigned id — it cannot match
  across two passes. Assuming the hash injective — the check costs nothing on a small vocabulary
  and the failure mode is two records silently merging in every join.
- **Consequence:** Both joins are complete, and the completeness is asserted rather than assumed.
  One lesson worth carrying past this task: the bug was found by *measuring the rows the parser
  rejected* instead of counting the rows it accepted. A pass that reports what it could not read
  is the only kind whose totals mean anything.

### D-069 — A released record in excess of the vOTU bound is the deduplication rule's failure, not the taxonomy rules'
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** The forward direction asks which released records a published rule removes. Against
  Evo 1's release the comparison is per lineage, because the release carries a lineage tag and no
  accession, and two quite different things make a lineage's released count exceed what the
  procedure predicts. Either a record-level rule removes that lineage outright, in which case
  every released record under it is that rule's failure; or the lineage survives every
  record-level rule and more records were released than it has vOTUs to represent, in which case
  one representative per vOTU was not kept. The first draft of the diff attributed both to
  whichever rule the lineage's verdict named, which for a surviving lineage is no rule at all —
  the artefact carried `rule: null` against the largest excess in the table.
- **Decision:** Split the forward direction by which rule the excess belongs to, and report the
  two components separately under one total:
  `records_removed_by_a_record_level_rule` and `records_in_excess_of_the_votu_bound`, the latter
  attributed to the deduplication rule by name. Each row of the detail table carries an
  `attributed_to` field. The excess is measured against the bound that favours the developer —
  the **most** the procedure could have retained under any input order — so nothing inside the
  interval is counted against them.
- **Rejected:** One combined forward count — §7 notes Phase A names real labs, and a write-up that
  reports a lineage's excess under the heading of a taxonomy rule names the wrong rule. Dropping
  the surviving-lineage excess because it cannot be attributed per record — it is the only
  evidence about the vOTU rule that Evo 1's release can give, since the release carries no vOTU
  identifier of its own.
- **Consequence:** Forward, converse, and the two components of forward are four numbers that are
  never summed into one. The artefact says so in a field rather than in prose.

### D-070 — The whole of A7.2 runs in the session container, and the EC2 test is applied and declined again
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** AGENTS.md's test for launching an instance is whether the work is bound by data
  movement that is free inside `us-east-1` and metered outside it, and names reading the staged
  corpora as the case that qualifies. A7.2 reads 11.5 GB of IMG/VR metadata and 10.4 GiB of Evo
  2's gzipped FASTA, which reads like exactly that case. D-050 applied the same test for A7.1 and
  declined, and AGENTS.md is explicit that the test is to be applied rather than the precedent
  copied.
- **Decision:** No instance, and the parallelism ceiling decided it in both directions. The IMG/VR
  metadata tables are plain TSV, which is splittable: `objectstore.byte_shards` cuts the 5 GB
  sequence table into byte ranges and the pass reads it with twelve workers, so it is bound by
  cores and the outbound proxy rather than by the format. Evo 2's FASTA is a single gzip member,
  which is one thread however large the instance — the pass took 18 minutes in the container, and
  an instance would have taken the same 18 minutes plus its own provisioning. Compute that runs
  acceptably in the session container does not qualify, which is AGENTS.md's own sentence.
- **Rejected:** Launching for the FASTA pass because it is the slow one — a bigger instance cannot
  decompress one gzip member faster, which is the ceiling A1.3's note asks to be worked out before
  choosing a size. Splitting the FASTA by byte range as the TSVs are split — a gzip stream has no
  addressable member boundaries, so a range read starts mid-stream and decompresses nothing.
- **Consequence:** Three tasks have now applied this test and none has launched. The pattern worth
  stating for whoever reads `tools/ec2_count.py` as a template: the question is not how large the
  input is but whether the format admits parallelism, and for every corpus staged in this project
  so far the honest answer has been that the container is the right size.

### D-071 — One taxon written at two ranks is reconciled, and it identifies which IMG/VR release Evo 1 used
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** A7.1's headline finding is 95 released records whose finest taxonomic assignment is
  a family and which carry no realm, so the published unspecificity rule removes them and Evo 1's
  release contains them. Re-executed from the input side, the same 95 records come back — and so
  does something A7.1 could not see. IMG/VR v4 carries eighteen classifications whose taxon name
  sits in the wrong rank field: `r__Bicaudaviridae;;;;;;;` and `r__Fuselloviridae;;;;;;;` among
  them, a family name in the **realm** position. Those forms have an assigned realm as far as the
  published rule can tell, so they survive it, while the correctly-ranked form of the same family
  does not. Scored per lineage and nothing else, that makes the same records a forward failure
  under one rank and a converse failure under the other, and reporting both would overstate both.
- **Decision:** Classifications are grouped by their set of taxon names with ranks discarded
  (`conformance_close.rank_normalisation`), and a group whose members the rule splits is
  reconciled rather than counted twice. Each group's released total is checked against the
  high-confidence vOTUs across its forms, and the released records divide into the part the rule
  retains under the taxon's other rank and the part it removes however the taxon is written. The
  write-up reports the second number as the unexplained one.
- **The reconciliation then identifies the input, which Evo 1's own words could not.** v4.1 is an
  erratum of v4 that corrects exactly these strings: in v4.1 `r__Bicaudaviridae;;;;;;;` does not
  exist and its 494 records sit under `;;;;;f__Bicaudaviridae;;` (432 + 494 = 926, and the same
  identity holds for Fuselloviridae, Ovaliviridae and the four misplaced `r__Naldaviricetes`
  forms). So the two releases predict different survivor *sets*, and only one of them matches
  what Evo 1 released: **re-executed over v4.1 the procedure predicts survivors in exactly the
  181 lineages the release carries and no others, while over v4 it predicts 43 records in two
  lineages the release carries none of.** D-052 and D-063 recorded that which release Evo 1
  applied its procedure to is not determinable from Evo 1's citation. It is determinable from Evo
  1's corpus, and the answer is **v4.1 (2022-12-20)**.
- **Consequence, and it cuts against the audit's own earlier reading:** under v4 these 43 records
  would have been explained away as a mismatch between the input's taxonomy strings and the
  release's, leaving 52 of A7.1's 95 unexplained. Under v4.1, which is the release the output
  identifies, there is no second form to explain anything and **all 95 stand as conformance
  failures**. The reconciliation machinery stays, because it is what made the identification
  possible and because it is the honest way to score any future release that carries a taxon
  twice — but the number it produces on the identified input is zero records explained. Recording
  the direction explicitly, because a mechanism that would have weakened this project's own
  headline finding and then did not deserves more scrutiny than one that confirmed it.
- **Rejected:** Reporting the 43 in both directions — the same records, counted twice, in two
  directions that are supposed to mean opposite things. Averaging the two releases' results, or
  reporting only the release that gives the smaller failure count — one of them is the input and
  the other is not, and the evidence says which. Treating the eighteen misplaced-rank strings as
  a defect to correct before re-execution — the filter ran on the publisher's strings as shipped,
  and normalising them first would audit a pipeline nobody ran (D-051).
- **Not claimed:** that Evo 1 built its corpus from v4.1 *because* of the erratum, or that the
  developers were aware of either. What is claimed is that their released corpus is consistent
  with v4.1 on this test and not with v4.

### D-072 — The reading spread is measured, it is zero, and the cause is that IMG/VR names no eukaryotic host
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** §A7 asks for the spread across the three readings of a policy, and says it matters
  as much as any single number. A7.1 had to report it as **unmeasurable**: every rule the literal,
  charitable and strict readings differ over reads host occurrences, and Evo 1's release carries
  none, so the three readings re-executed an identical pipeline by construction (D-047). A7.2 has
  the host data, so the number exists for the first time.
- **Decision:** Report it as measured and zero, with the cause named in the same breath, and never
  as agreement between readings. The cause is in the data: **IMG/VR v4 asserts no eukaryotic host
  for any of its 15,677,623 records.** The host-prediction field is empty, bacterial or archaeal
  and nothing else, across every record and all four of the publisher's prediction methods, and
  across all 18,859 distinct host taxa in the host table. Both rules the readings differ over —
  the charitable reading's one-strike eukaryotic-host removal and the strict reading's exclusivity
  requirement — are keyed on eukaryotic evidence, so neither can fire. The spread is therefore
  zero on every quantity A7.2 computes: records removed, classifications surviving, both ends of
  the retained interval, and both releases' forward failure counts. `conformance_close.host_evidence`
  measures the vocabulary and the artefact carries it beside the spread table, so a reader cannot
  take the zero for three readings agreeing.
- **Why this is a finding and not a formality:** the published aim is to exclude viruses that
  infect eukaryotic hosts, and the only host evidence the filter's own input carries never names a
  eukaryote. That is why the published procedure reaches the aim through a prokaryotic-host
  *count* and a clade enumeration rather than through a eukaryotic-host test — the direct test is
  not available in the data, whatever a reader of the paper's prose would assume. It also means
  the charitable reading, which A0.3 constructed precisely to implement the authors' stated aim
  more directly than their own procedure does, **cannot be implemented against this database at
  all**. A0.4 should read this entry before reporting the Evo spread: the spread between readings
  of this policy is zero for a reason that is a property of IMG/VR, and will not generalise to a
  model whose corpus carries eukaryotic host annotation.
- **Rejected:** Reporting zero without the cause — three identical columns read as agreement
  between readings, which is the misreading D-047 built `readings_agree_by_construction` to
  prevent in the structural case and which needs preventing just as much in the empirical one.
  Inferring eukaryotic host assignments from a taxonomy source to make the readings separable —
  AGENTS.md forbids secondary sources for factual claims about this data, and the resulting spread
  would measure our inference. Dropping the charitable and strict readings from the artefact
  because they produce identical numbers — the identity is the result.
- **Consequence:** X5.1 gains a requirement with evidence behind it: a filter that excludes by
  host range should publish which host-range evidence it used and what that evidence can express,
  because an exclusion criterion stated over a field that cannot represent the excluded category
  is unauditable in a way no amount of re-execution fixes. And B1 should not assume that any
  host-based exclusion claim in any model card is backed by host annotation that names the hosts
  it excludes.

### D-073 — Evo 2's conformance result becomes its own Phase A task, and the v4.1 identification is carried into `corpora.md`
- **Date:** 2026-10-15
- **Task:** A7.2
- **Context:** A7.2 produced two things it was not the right task to own. Its Evo 2 arm found
  264,570 released records that the procedure Evo 2 adopts by reference removes — four orders of
  magnitude larger than its Evo 1 finding of 95, and a claim about a different artefact, a
  different release, and a different paper's adoption of someone else's published method. And
  D-071 identified Evo 1's input as IMG/VR v4.1 from Evo 1's own released corpus, where
  `policies/corpora.md` §2 and D-052/D-063 all record the release as not determinable.
- **Decision:** Both put to the project owner, who decided both.
  **The Evo 2 result gets its own task, A7.3**, rather than a section of A6.1's Phase A write-up.
  The reasons the owner's choice turns on: reporting the larger finding inside an Evo 1 result
  would bury it, and it would attach Evo 2's standing to Evo 1's A3.3 reimplementation rather
  than to its own. A7.3 carries the interpretive work A7.2 deliberately did not do — what the
  arithmetic licenses in print, the three live alternative explanations as checks rather than
  sentences, the by-family breakdown within §4's reporting limits, and the repeated accessions.
  **The v4.1 identification is carried into `policies/corpora.md` with its caveat**: recorded as
  identified from Evo 1's own output rather than from Evo 1's words, so a later reader cannot
  mistake an inference for a retrieved fact. D-052, D-063 and D-071 stay as they stand; the
  earlier entries are the record of what the sources said and are not rewritten.
- **Rejected:** Folding Evo 2 into A6.1 — considered and declined for the reasons above. Holding
  the decision until A3.3 runs — the finding's standing depends on the reimplementation, but
  where it is written up does not, and leaving it unowned until then is how a result becomes a
  review note nobody owns (which is the mistake A7.2 exists to avoid repeating, per its own
  "why this is a separate task"). Leaving `corpora.md` ambiguous — the identification is evidence
  about the audited artefact, and a verdict document that omits it would have A7.2's own claims
  resting on a release the repo says is unknown.
- **Consequence:** A7.3 is `blocked` on A7.2, which is `review` behind the A3.3 gate. Phase A now
  has two conformance findings of very different sizes about two different releases, and the
  write-ups must not be allowed to blur into one: Evo 1's is a near-clean result with a 95-record
  exception, Evo 2's is a mismatch across four of six rules. A6.1 should state both and claim
  neither on the other's evidence.

### D-074 — D-057's cross-declaration guard did not cover an addition, and the classification is now explicit
- **Date:** 2026-10-15
- **Task:** A1.4
- **Context:** D-057 unified the rule-input table that A1.4 and A7.1 had each declared
  independently, and deliberately left the *release* inventory standing in two granularities
  rather than refactor a module under review: `conformance.RELEASE_INPUTS`, which `restrict`
  reduces a policy by, and the per-record `Evidence` on each `corpora.StagedSource`, which A1.4
  checks a rule against. A test was left pinning their agreement, and A1.4's outcome note told
  the next worker what to expect from it: "A7.2 extends the release inventory with IMG/VR v4. The
  cross-check test in `tests/test_apply.py` will fail if the matching `Evidence` declaration in
  `corpora.SOURCES` is not extended with it. That is intended."
  A7.2 extended the inventory with `imgvr-v4` and `imgvr-v4.1`, did not touch `corpora.SOURCES`,
  and **nothing failed.** The test named the two releases it knew —
  `opengenome-stage2` and `opengenome2-imgvr` — and asserted agreement on those. It caught drift
  in the pair it hard-coded and was structurally blind to a third release being added. Both
  tasks' CI was green throughout, and the note's promise was simply false.
- **Decision:** Two changes, and the first is the one that matters.
  **`conformance.INPUT_RELEASES` classifies every entry that is the filter's input rather than a
  corpus a developer released.** A7.2 had already introduced the distinction behind
  `COMPARISON_KEYS` — a release in it has something to join on, an input has nothing to be
  compared against — so the classification could have been inferred from a key's absence. It is
  declared instead, because inferring a fact from an absence is precisely what let this through:
  a new key with no comparison key looked exactly like an input, and a new key that *is* an
  input looks exactly like a mistake. A key classified as neither, as both, or classified but
  absent from `RELEASE_INPUTS` now fails a test.
  **And the agreement check drives off `RELEASE_INPUTS` itself**, joining each key to a staged
  source mechanically — a `StagedSource` is addressed by `f"{release}-{corpus_component}"`, which
  is the form the inventory keys already take — rather than through a second hard-coded map that
  would need extending by hand and would fail the same way the first one did.
- **Verified by making it fail, not by watching it pass.** The old guard passed; that is the
  whole problem, so a green test proves nothing here. Three failure modes were injected and each
  was confirmed to fire with a message naming the culprit: a release added and left unclassified,
  a release classified but absent from the inventory, and a released output with no staged source.
  The scratch harness is not committed — it mutates a module under test — but the method should
  be: a guard whose job is to fire on a change nobody remembers to make is not tested until it
  has been seen to fire.
- **Rejected:** Collapsing the two declarations into one, which is what would actually remove the
  class of bug. It is the right fix and it is not this task's: `corpora` would have to stop
  carrying per-record evidence or `conformance` would have to start, and both modules are at
  `review` behind the A3.3 gate. D-057 declined the same refactor for the same reason and this
  entry declines it again, with the cost now measured rather than estimated — one silent drift
  across two tasks. Also rejected: deleting the hard-coded test in favour of the enumerating one.
  It asserts something the general version does not, namely that `restrict` *raises* on Evo 2's
  release rather than returning an empty pipeline a caller could report zero failures from.
- **Consequence:** A1.4's outcome note is corrected on `main` rather than left to be discovered,
  since it was the note a later worker would have trusted. The general lesson is the one worth
  carrying: **a guard that enumerates the thing it guards cannot be outflanked by an addition, and
  a guard that names its cases can.** The other two tables in this repo that are checked across
  declarations were looked at rather than left as a worry. The rule inputs are now literally one
  object, so there is nothing to drift. `models.validate` iterates the whole inventory and
  requires every cited source to exist and be `retrieved`, so a checkpoint added without its
  source fails there — it is enumeration-driven already and does not share this defect. The
  release inventory was the one that did.

### D-075 — The profile registries are Pfam 38.2 and RVDB-prot 32.0, and "viral clans" is read at family level
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** `DESIGN.md` §A2 names the profile resources as "viral protein family HMMs (Pfam
  viral clans; RVDB, which exists for exactly this purpose)". Neither half is a set this project
  can simply load. RVDB is published in several forms and versions and §A2 pins none of them.
  And **"Pfam viral clans" does not denote a usable set at all**: a Pfam clan is a *structural*
  superfamily, so clans mix viral with cellular families freely. `CL0055` (Nucleoplasmin) holds
  seven viral capsid families beside the cellular nucleoplasmins; `CL0063` (NADP_Rossmann) holds
  two reovirus methyltransferase domains inside one of the largest cellular clans in the
  database. A profile set built from clans would call a Rossmann fold viral content, and this
  audit's headline is the fraction of viral families with a surviving homolog — so an inflated
  numerator inflates the finding, in the direction that favours the result the project is
  testing for. The gap had to be closed before anything was searched.
- **Decision:** Two registries, pinned by version, searched separately and never pooled
  (`metrics/survival.md`, D-022):
  **Pfam 38.2** (EMBL-EBI, 2026-01-22), pinned by its versioned release directory rather than
  `current_release`, which is a moving pointer. 30,134 families, every one carrying a GA
  gathering cutoff. Digests are the publisher's own `md5_checksums`.
  **RVDB-prot 32.0** (Bioinformatics Hub, Institut Pasteur, 2026-07), the HMM form:
  `U-RVDBv32.0-prot.hmm.xz`, 13,679 profiles, with digests, counts and the build's own tool
  versions taken from the release's `U-RVDBv32.0-prot-metadata.yaml`. The staged file's profiles
  are counted independently of that metadata: stated 13,679, counted 13,679.
  **The Pfam viral set is selected at family level, not clan level.** A family is in when its
  own Pfam ID or description names a viral entity, against a keyword list frozen in
  `amazebio.profiles.VIRAL_KEYWORDS` before the corpus was searched. That selects **1,719 of
  30,134** families. `integrase` and `transposase` are deliberately *not* in the list: they are
  mobile-element machinery shared with transposons, and a bacterial transposase counted as
  viral content would be the same inflation by another route. The selected set ships per family
  — accession, name, description, clan, cutoff — as `artifacts/a2-1/registries/pfam-viral-families.json`,
  so the membership is reviewable family by family rather than taken on trust.
- **Rejected:** The clan-level reading, with its consequence measured rather than asserted. Every
  family in every clan containing at least one viral family is **6,698 families across 131 clans,
  of which 6,132 are not themselves viral** — the profile set is four times larger and
  overwhelmingly cellular. It is also *incomplete*: only 13,933 of Pfam's 30,134 families belong
  to a clan at all, and **1,153 of the 1,719 selected viral families have no clan**, so the
  clan-level reading would drop two thirds of them. Over-broad and under-inclusive at once.
  Also rejected: RVDB's clustered FASTA with a sequence-similarity search instead of the HMMs.
  §A2 asks for profile search, profiles are the sensitive instrument at this distance, and
  RVDB-prot ships the HMMs ready-built.
  Also rejected: deriving the viral set from the taxonomy of each family's seed alignment, which
  would be a stronger criterion than keywords. It needs the full seed alignments (another
  release to pin and parse) and it would still be this project's reading rather than Pfam's.
  Recorded as the better instrument if a reviewer disputes the membership.
- **Consequence:** The two registries answer "is this family viral" by *different authorities* —
  RVDB's by its curators, Pfam's by this project — which is why the headline is reported once per
  registry and the two denominators are never added together. The Pfam membership is this
  project's judgement call and is therefore a stated limitation of every Pfam-registry figure;
  the per-family artefact is what makes it an auditable one. The clan-level numbers above are a
  §A0-style finding in their own right: a specification that says "viral clans" names no set,
  and the spread between its two readings is a factor of four.

### D-076 — Hit thresholds are bit scores, or E-values against a pinned database size
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** A2.1 has to fix its thresholds before looking at any hits, and the obvious choice
  — "E ≤ 1e-5", the field default — is unsound for this audit in a way that is easy to miss.
  A sequence E-value is scaled by the number of target sequences searched, so the same profile
  at the same E-value cut-off corresponds to a *different bit score* on a sample than on a whole
  corpus, and to different bit scores on two manifests of different size. The headline — the
  fraction of families with a surviving homolog — would then move with how much corpus a run
  happened to read, in the direction of finding more survival the more was searched. That is a
  threshold that reports its own sample size.
- **Decision:** Every threshold in A2.1 is a bit score, or an E-value computed against a pinned
  database size, which is the same thing:
  **Pfam: the release's own per-model GA gathering cutoffs, used as published.** Pfam curates a
  cutoff per family and all 30,134 carry one; this project does not get to pick its own threshold
  for somebody else's curated database. Searched with `bit_cutoffs="gathering"`.
  **RVDB-prot: sequence E ≤ 1e-5 against `Z = 1_000_000`** (`domZ` the same), pinned in
  `amazebio.profiles.PINNED_Z` / `PINNED_E_VALUE`. RVDB's profiles are built automatically and
  carry no curated cutoff, so a threshold has to come from somewhere; fixing `Z` makes it a
  constant per-model bit score. The equivalent bit score is derived per model from the model's
  own calibrated Forward tail, `T = f_tau + ln(Z/E) / f_lambda`, and it is `T` that is recorded
  as each detection's threshold — so `amazebio.survival.Detection`'s score-above-threshold
  invariant is checked against a real bit score, and a stricter threshold can be re-applied to
  the artefact later without re-running the search. One million is not a magic number: it is
  within an order of magnitude of the translated gene count of a single staged source, which
  keeps the reported E-values readable as E-values rather than as a rescaled bit score.
  **Both registries additionally require envelope coverage of at least 0.5 of the model**
  (`MIN_MODEL_COVERAGE`). A profile search over called genes finds short partial matches in
  abundance, and a 20-residue slice of a 400-residue capsid model is not a surviving homolog of
  that family in any sense §A3 reports. This applies on top of Pfam's gathering cutoffs too,
  because Pfam curates those for annotating domains in proteins, which is a different question
  from whether a family survived a filter.
  Every accepted hit's score, E-value, threshold and coverage are written to the artefact, so
  the thresholds are re-checkable and a reviewer can re-cut at a stricter one.
- **Rejected:** A plain `E ≤ 1e-5` with `Z` left to the search, for the reason above — it is the
  default and it would have made the headline a function of the sample size.
  A single fixed bit score across a whole registry (say 30 bits), which ignores that a 60-residue
  model and an 1,800-residue model reach that score with wildly different amounts of evidence.
  Pfam's trusted cutoffs (TC) instead of gathering (GA): TC is the lowest score of a sequence
  *in* the family, which is stricter than Pfam's own inclusion decision and would discard
  homologs Pfam itself would annotate. GA is the curated inclusion boundary and is the one to use.
  Tightening the coverage floor to 0.8, which would be defensible and is not pre-registered as
  the primary: the artefact carries coverage per hit, so 0.8 is a sensitivity analysis A3.2 can
  run from what A2.1 already wrote, rather than a second search.
- **Consequence:** Thresholds are comparable across manifests, releases, sample sizes and the two
  registries, which is what lets A3.2 merge A2.1's output with A2.2–A2.5's. The numbers are fixed
  here, dated, before any hit was inspected, which is what `AGENTS.md` requires. The coverage
  floor is the one place A2.1 is stricter than the registries' own authors, and it is stated as
  such beside every figure.

### D-077 — Reading frames come from gene calling, not from six-frame translation
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** The profiles are protein and two of the three surviving corpora are nucleotide, so
  something has to decide what the reading frames are. The cheap answer is six-frame
  translation: translate every record in all six frames and search the lot.
- **Decision:** Genes are called with Prodigal in metagenomic mode (`pyrodigal` 3.7.1, vendoring
  Prodigal v2.6.3), and the called proteins are what gets searched. Metagenomic mode because the
  records are contigs and fragments of unknown provenance rather than finished genomes with
  enough sequence to train a genome-specific model.
- **Rejected:** Six-frame translation. It puts five wrong answers beside every right one, and a
  profile hit on a frame no gene occupies is a false positive — in a project whose headline is
  "this family survived the filter", reported against named laboratories, with §7 requiring the
  result to be airtight. It also costs six times the search for the privilege. The honest
  trade is the other way round: gene calling can *miss* a gene, so it costs sensitivity, and a
  missed gene can only make the survival figure lower, which is the safe direction for a finding
  of this kind.
  Also rejected: calling genes with a tool of this project's choosing on the grounds of accuracy.
  Prodigal is the caller IMG/VR's own annotation pipeline uses, so the genes in the records are
  called the way the records' publisher calls them, and a disagreement about gene boundaries
  cannot be a disagreement this audit introduced.
- **Consequence:** Reported family survival is a lower bound with respect to gene calling as well
  as sampling (D-078). Records whose genes Prodigal cannot call contribute nothing and are
  counted separately in each table's per-source row, rather than being absorbed into "no hit" —
  that population is a limitation of the method and has to be visible as one.

### D-078 — The sample is a deterministic hash of the record id, and what it supports is a lower bound
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** A profile search over the whole surviving corpus is not expensive, it is
  arithmetically out of reach. Measured on this project's own environment: 98 million
  profile-residues per second for RVDB-prot and 254 million for the Pfam viral set, on three
  cores. The Evo 1 viral component alone is 36.2 Gbp (2,653,047 records, A7.1's census), which is
  about 10.9 G amino acids of coding sequence; against 13,679 RVDB profiles that is roughly
  40,000 core-hours, and Evo 2's viral component is larger again. No instance size and no budget
  this project has changes the order of magnitude. So the headline comes from a sample, and the
  sample has to be pre-registered rather than chosen once the hits are in.
- **Decision:** Sample membership is a deterministic function of the record identifier and a
  pinned seed: a record is in when `blake2b(key=seed, record_id)` read as a 64-bit integer is
  below `rate · 2⁶⁴` (`amazebio.detect.in_sample`). Seed **20261015**. Rates, fixed now, one per
  source, chosen so that each source contributes a comparable residue budget rather than a
  comparable record count — the headline is per family, not per record, and the binding
  constraint is compute:
  | source | rate | expected records |
  |---|---|---|
  | `opengenome` / `stage2` | 0.002 | ~5,306 of 2,653,047 |
  | `opengenome2` / `imgvr` | 0.001 | ~1 in 1,000 |
  | `opengenome2` / `imgpr` | 0.001 | ~1 in 1,000 |
  Hash sampling rather than a random draw because it is declarable in advance, reproducible
  without storing a list of ids, resumable after an interruption, independent of the order
  records are read in, and checkable per record after the fact: a reader can ask whether a named
  record was in the sample without re-running anything.
  **The resulting family-level survival figure is a lower bound, and the schema says so in its
  own field** (`estimate_kind: lower_bound`). A family detected in the sample is detected, and no
  amount of unread corpus takes that back; a family absent from the sample may survive in the
  records not read. The bound is reported with its Wilson interval over the sampled denominator,
  and A3.2 must not read a sampled table as a population estimate.
- **Rejected:** A uniform record-count sample across sources, which would have spent most of the
  budget on whichever source has the shortest records.
  A reservoir or RNG-drawn sample, which needs the draw stored to be reproducible and cannot be
  resumed or checked per record.
  Waiting for a faster method before producing any number — a profile-vs-profile prefilter, or
  MMseqs2 profile search at one to two orders of magnitude more throughput. That is the right way
  to widen this and it is a method substitution with its own sensitivity to establish, so it is
  put to the project owner as a scale decision rather than absorbed into A2.1 unannounced.
  Scaling up by sampling less deeply but reporting it as a population figure. The bound is what
  the evidence supports.
- **Consequence:** Every A2.1 figure is a lower bound on two counts — sampling and gene calling
  (D-077) — and both are stated in the artefact rather than in a footnote. This is the safe
  direction: the audit under-reports survival rather than over-reporting it, and `DESIGN.md` §2's
  commitment is that a null result must remain visible, which a lower bound does not threaten.
  A3.2 reads `estimate_kind` and must refuse to pool a `lower_bound` table with a `population`
  one. If the owner funds a wider pass, the same seed and a larger rate *extend* the same sample
  rather than replacing it — hash membership is nested in the rate — so nothing already searched
  is searched again.

### D-079 — A profile hit names a family, never an element kind
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** `amazebio.survival.Detection` requires an `ElementKind` beside the route, and the
  taxonomy has seven: free virus, prophage, endogenous retroelement, non-retroviral EVE,
  satellite, viral-derived fragment, unclassified element. A profile hit supports almost none of
  them. It says a viral protein family is present in a record; it does not say whether the record
  is a free virus, a prophage in a bacterial genome, or an endogenous element in a host genome —
  and those are precisely what A2.3 (EVEs) and A2.4 (prophage) establish with their own methods.
- **Decision:** A2.1 assigns element kind from the record's *component*, taking the weakest kind
  that component's own definition supports, and never infers one from the hit
  (`amazebio.detect.COMPONENT_KINDS`). IMG/VR is a database of viral genomes and metagenomic
  viral contigs, so a hit there is `free_virus` by the publisher's definition of the collection.
  Everything else — `stage2`, `imgpr`, and any component added later — is
  `unclassified_element`. A hit in a bacterial genome becomes `prophage` when A2.4 says so, not
  when A2.1 guesses.
- **Rejected:** Inferring the kind from which families were hit — a capsid plus a terminase plus
  a portal protein in a bacterial contig does look like a prophage. It is also exactly A2.4's
  result, arrived at by a weaker method, and `metrics/survival.md` cross-tabulates kind against
  route specifically so that the two claims stay separable.
  Leaving the kind null. The field is not optional in the frozen schema, and a null would be
  silently read as "not viral-derived" by anything tabulating it.
- **Consequence:** A2.1's kind column is nearly constant by construction and carries no
  information beyond the component — which is correct, and the cross-tabulation in A3.2 gets its
  information from A2.3 and A2.4 as intended. `metrics/detections.md` states this so that a
  reader does not mistake A2.1's `unclassified_element` rows for a finding that the elements are
  unclassifiable.

### D-080 — A2.1 searches the viral components; the non-viral ones are A2.3's and A2.4's
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** The strict reading's scope is the whole corpus, so its manifests cover components
  far beyond the viral ones — GTDB's bacterial genomes (110 GB staged), organelles, ncRNA,
  promoters, and Evo 2's unstaged eukaryotic genomes. A profile search would run on any of them,
  and "search the surviving corpora" could be read as covering all of it.
- **Decision:** A2.1 searches the components the filter's own viral rules act on and that A1.4
  enumerates: `stage2` for the `opengenome` release, `imgvr` and `imgpr` for `opengenome2`. Every
  other component appears in the manifest's table as a row with `searched: false` and the reason
  — `A2.3` for host genomes, `A2.4` for bacterial genomes, or not staged — so a reader sees the
  full scope of the manifest and exactly which part of it A2.1 answered for.
- **Rejected:** Searching GTDB's bacterial genomes here. Viral content in bacterial genomes is
  prophage, geNomad and CheckV are the instruments §A2 names for it, and that is A2.4 — running a
  profile search over it first would duplicate the task with a weaker method and widen A2.1 past
  one unit of work, which `AGENTS.md` forbids in as many words.
  Omitting the unsearched components from the tables, which is what would make the omission
  invisible. `metrics/manifests.md` already took this decision for A1.4's own manifests, for the
  same reason: a table that silently covered only part of a release reads as a verdict on all of it.
- **Consequence:** A2.1's survival figures are survival *in the viral components*, stated that
  way. The cross-component question — whether viral families survive in the components the filter
  never pointed at — is A2.3's and A2.4's, and A3.2 merges the three by route. The
  `out_of_scope` route is where that merge will mostly land, and it is the headline Phase A
  finding (D-007), so it matters that it comes from the detector built for it.

### D-081 — The unfilterable fraction is two shares per rule, because absence of a label fires half of Evo's rules
- **Date:** 2026-10-15
- **Task:** A4.1
- **Context:** §A4 asks what share of the corpus is outside a taxonomy filter's reach in
  principle. The obvious implementation is one number per component — the unclassified share —
  and it is wrong twice over.
  **There is no single unclassified share.** IMG/VR v4.1 labels 96.68% of its 15,677,623 records
  at realm and 6.25% at family. The two rules in Evo's published procedure that name a hazard
  are the 19-family and 12-order denylists, keyed on family and order. A component-level
  "unclassified fraction" averages over the only distinction that matters: 3.29% of records fill
  no rank at all, which would have been the headline, and it is not the finding.
  **A rule can read the absence of a label.** Evo 1's pipeline is mostly keep-listing:
  "viruses with poor taxonomic specificity were excluded, including those with no assigned realm
  at all" removes a record *because* its realm is missing, and "keeping only sequences whose
  assigned taxonomic classification was found within a prokaryotic host at least twice" removes
  a record with no host prediction for the same reason. Those rules are decidable on every
  record in the database. Reporting them as blocked by missing labels would overstate the
  finding, and §2's commitment to publishing a null cuts both ways: a measurement tilted in the
  audit's favour fails in the same way as one tilted in the filter's.
- **Decision:** Every rule carries two shares over every population, and the artefact reports
  both.
  **`decidable_share`** is where the rule produces its stated outcome; a rule firing on absence
  scores 1.0. **`discriminating_share`** is where the rule's own criterion can be evaluated
  against a label that is present, and that is the ceiling §A4 asks for. The headline per
  reading is the *lowest* discriminating share among the rules that need a label — not the mean,
  because a procedure is as blind as its blindest discriminating step.
  The direction each rule kind reads its evidence (`label_present`, `label_absent`, `either`) is
  **declared** in `unfilterable.FIRES_ON`, keyed by the same rule kinds as
  `policyspec.RULE_INPUTS`, with a test driving off that table rather than a list written beside
  it — the D-074 lesson — and an unknown kind raising rather than defaulting. Which way an
  author's rule reads its evidence is a reading of their words, and a default here would decide
  it silently.
- **And the ceiling is reported over two populations, not one.** Evo's confidence gate runs
  first, so the denylists are handed 5,576,197 records rather than 15,677,623. Over the whole
  release the family denylist can discriminate on **6.25%**; over the population the gate
  actually hands it, **7.87%**. Both are in the artefact, because the first answers a question
  about the database and the second about the filter, and quoting either alone invites the
  obvious objection without answering it.
- **Rejected:** A single unclassified fraction per component, for the reason above. Also
  rejected: reporting the discriminating share alone, which reads as "the filter cannot touch
  the other 94%" — it can, bluntly. The shallowness backstop ships beside the ceiling to say how
  much: 599,507 records of v4.1 (3.82%) are removed by the unspecificity rule for having no
  realm or terminating in one of its eight named stop taxa. That count is a caveat and not a
  finding, because what actually survived is A3.2's question over a population this pass does
  not compute.
- **Consequence:** Four labelling states stay separate all the way into the artefact —
  `unlabelled` (the field is present and empty), `not_annotated` (the component carries no such
  field), `out_of_policy_scope` (the filter was never applied; A4.3 owns the share) and
  `not_taxonomy_dependent` (ESM3-open's rule reads a similarity threshold, so no taxonomic
  ceiling binds it). None may be summed with another, and the artefact's caveat block says so in
  machine-readable form.

### D-082 — A4.1 measures the filter's input from the primary tables and reuses the pinned released-corpus scans
- **Date:** 2026-10-15
- **Task:** A4.1
- **Context:** A ceiling is a claim about the population the filter was applied to, which is the
  two staged IMG/VR releases. A4.1 also wants the same per-rank measurement on the two
  *released* viral components, so the filter's input and its output can be compared on one axis.
  A7.1 and A7.2 already read those two components — 17 GB of Parquet and 11 GB of gzipped FASTA
  — and published lineage histograms alongside their own independently counted record totals.
- **Decision:** The input is measured by a fresh pass over the publisher's own tables: both
  releases' `IMGVR_all_Sequence_information.tsv`, byte-sharded 64 ways, five fields per record,
  which is every field any published Evo rule reads. The released components are taken from
  A7.1's and A7.2's pinned scans rather than re-read.
  The reuse is sound only because a histogram can be checked, so it is: each one is verified to
  sum to that scan's own record total, counted by a different code path, before any share is
  taken from it, and the check raises rather than warning. A partition that sums to the
  component's record count cannot be missing a record, and a dropped shard shows up as a
  mismatch — which is the failure mode that makes reusing a derived artefact dangerous at all.
- **The independent pass agrees with A7.2 exactly**, which is worth more than the saved
  minutes: all eight ranks, the record total, the confidence split and the host-domain tallies
  match to the record, from two unrelated implementations — A7.2's sharded classification-id
  arrays and numpy joins against this pass's per-shard counters.
- **Rejected:** Re-reading 28 GB to recompute tallies that are already pinned and checkable.
  That is not an independent second method, it is the same method over the same bytes, and §7's
  independent-reimplementation requirement belongs to A3.3 over the headline counts. Also
  rejected: taking the *input* figures from A7.2's scan too. They are the ceiling, A4.1 should
  be able to state them from the publisher's file, and the agreement above is only available if
  the two passes are actually separate.
- **Consequence:** Evo 2's released viral component is reported as `not_annotated` rather than
  unclassified. It carries no lineage field at all, and all 2,917,521 of its distinct accessions
  resolve in IMG/VR, so its ranks come from A7.2's join and are labelled as recovered.
  "100% unclassified" would have been the easiest wrong number in this task.

### D-083 — The Pfam viral selection misses families named for a virus taxon, and both wider rules are contaminated
- **Date:** 2026-10-15
- **Task:** A2.1
- **Numbering:** drafted as D-081, which A4.1 took first; renumbered per `AGENTS.md`. A commit
  message on branch `ccr-a85b7882-p8ohv8` cites this finding as D-081 and is already pushed, so
  that citation resolves here.
- **Context:** D-075 selects the Pfam viral family universe by matching a frozen vocabulary
  against each family's own ID and description. Writing the tests for it surfaced a class of
  family the rule cannot see: one **named for a virus taxon** rather than for a viral structure.
  `Ebola_NP` is described as "Ebola nucleoprotein"; `Rhabdo_ncap` and `Paramyxo_ncap` are the
  same shape. None of them contains `virus`, `viral`, `capsid`, `nucleocapsid` or anything else
  in the vocabulary, so all three sit outside the universe — a filovirus nucleoprotein family
  excluded from an audit of viral content. This was found by a test expecting `Ebola_NP` to be
  selected, not by inspecting results, so nothing downstream had been computed yet.
- **Decision:** The universe stays as D-075 defines it — the family-name rule alone, 1,719
  families — and the gap is **measured and reported per family** rather than closed. Three things
  make that defensible:
  **The rule stays crisp.** A denominator assembled from two rules of different reliability
  cannot be defended family by family, and the per-family artefact is what makes this
  project's selection auditable at all.
  **Both wider rules were measured, and both are contaminated.** The clan-level reading is
  6,698 families with 6,132 not viral (D-075). The *narrowest* widening available — admitting a
  family whose own clan's **name** names a viral entity — adds 61 families, and inspecting them
  shows the same defect in miniature: `CL0511` is called `Retroviral_zf` and contributes
  cellular zinc fingers (`CLIP1_ZNF`, `AIR2-like_ZnK4`), `CL0504` is called `Phage_barrel` and
  contributes `Alg8_N`. 32 of the 61 come from `Phage_barrel` alone. It would admit `Ebola_NP`,
  via the `Nucleocapsid` clan, at the price of a third of the addition being cellular.
  **The other registry covers the gap.** RVDB-prot's membership is its curators' and is built
  for virus detection; a filovirus nucleoprotein family is in it on their authority, not ours.
  This is exactly why A2.1 searches two registries whose membership comes from two different
  authorities and never pools them.
  `amazebio.profiles.clan_name_additions` computes the addition, and
  `artifacts/a2-1/registries/pfam-viral-families.json` carries it beside the universe with every
  family's `selected_by`. A reviewer who disagrees can re-cut from the artefact without
  re-running a search.
- **Rejected:** Extending the vocabulary with virus taxon names — `ebola`, `rhabdo`, `paramyxo`,
  `filo`, `herpes`, and the fifty more it would take to be consistent. It would work, and it
  would replace one reviewable rule with a long list of this project's own judgements, each of
  which a reviewer would have to check individually. If a reviewer asks for it, the artefact
  makes the swap cheap.
  Adopting the clan-name rule, for the contamination above. Note the direction, though, because
  it is not symmetric and the write-up should say so: a *cellular* family inside the universe
  contributes a near-guaranteed zero and pushes the survival fraction **down**, while a missing
  viral family removes a row from both numerator and denominator. Contamination is the
  conservative error and omission is the neutral one, which is a further reason not to trade the
  second for the first.
- **Consequence:** Every Pfam-registry figure is explicitly "survival among families Pfam's own
  names identify as viral", and the blind spot is a stated limitation with a number attached
  rather than a surprise for a reviewer to find. The general lesson is the one to carry into
  A2.2–A2.5: **the family universe is a denominator, and its membership rule is a finding about
  the registry, not a detail of the pipeline.** A2.2's fold families and A2.5's problem taxa both
  face the same question, and both should expect to report their membership rule rather than
  assume one.

---

### D-084 — The tool A4.2 benchmarks is named by the corpus, and it is not the one with the largest share

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** §A4 says to benchmark "the taxonomy assignment tools the filter relies on". That
  is a question of fact and IMG/VR answers it per record, in `Taxonomic classification method`.
  The pass in `tools/taxonomy_dependency.py` read it over the whole of v4.1 and the mix is not
  what the corpus-wide figure suggests:

  | population | geNomad | RVMT | NR | vOTU consensus | other |
  |---|---|---|---|---|---|
  | all 15,677,623 records | **89.97%** | 2.22% | 2.56% | 1.81% | 3.44% |
  | records labelled at family | **61.74%** | 22.20% | 11.22% | 3.79% | 1.05% |
  | the denylist's own 181,530 hits | **38.56%** | **49.51%** | 4.27% | 5.64% | 2.02% |

  The direction of that drift has a mechanism rather than being noise. The denylist names
  eukaryotic RNA-virus taxa — Picornavirales, Durnavirales, Amarillovirales, Flaviviridae,
  Reoviridae, Picobirnaviridae among them — and the RNA-virus labels in IMG/VR were imported
  from RVMT, a published metatranscriptome catalogue. So the records the rules actually remove
  are disproportionately the ones geNomad did not label.

  Two further things the same pass established. The publisher's help page names **four**
  taxonomy approaches; the corpus carries **eight** method values, and three of the extra ones
  (`RVMT`, `RefSeq`, `GVMAG`) are described nowhere in the release note or the help page. And
  an *internal* benchmark — scoring a predictor against records whose ground truth the corpus
  already carries — is thin rather than available: 13,971 records are flagged `Reference`
  (NCBI RefSeq, per the release note), but 97.29% of them took their lineage from the RefSeq
  lookup, where the label and the ground truth are one fact and nothing is tested. Only 272
  carry a geNomad label.
- **Decision:** A4.2 benchmarks **geNomad**, at the version contemporaneous with the release
  (D-085), against external ground truth (D-086), and reports the dependency decomposition
  above as a result in its own right.

  It does **not** benchmark RVMT, NR, vOTU consensus, RefSeq or GVMAG. Those are not tools this
  audit can run: they are taxonomies imported from other datasets, so their error is the error
  of those datasets' own assignments, and measuring it needs a different instrument — an
  overlap between each catalogue's records and ratified taxonomy, which for metatranscriptome
  contigs does not exist by construction. Pretending otherwise by scoring their labels against
  ICTV where they happen to coincide would measure the coincidence.

  The consequence is stated rather than hidden: **A4.2's error rate covers the 38.56% of the
  denylist's hits that rest on geNomad, and the remaining 61.44% is unmeasured.** That is a
  gap in the audit and it is named as one. `AGENTS.md` forbids widening a task to absorb an
  adjacent problem, so the imported catalogues get a new task ID rather than being folded in
  here — recorded as **A4.4** in the board, blocking nothing that A4.2 blocks, because the
  Phase A write-up can state the decomposition and the one measured component without it.
- **Rejected:** *Benchmark whichever method has the largest corpus share* — that is geNomad at
  89.97%, and it would have produced a precise answer to a question about the database rather
  than about the filter. The hazard-relevant share is the one that propagates.
  *Report a single pooled error rate across all eight methods* — it would be a weighted average
  of one measured quantity and seven unmeasured ones.
  *Treat the `Reference` records as the evaluation set* — 272 scorable records, selected by the
  fact that the RefSeq lookup did **not** resolve them, which is not a random subset of
  anything. They are reported as corroboration with that caveat attached, not as the benchmark.

---

### D-085 — The geNomad version IMG/VR used is unrecoverable, so the benchmark pins the newest one that could have produced the labels

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** `AGENTS.md` requires benchmarking a tool at the version the filter relies on, and
  requires that where a stated version is unrecoverable the stated-versus-used gap be recorded
  explicitly as a finding. This is that case, and the gap is specific rather than general:

  - The v4 release note **pins CheckV to v1.0.1** by name, in the same field list, and names
    geNomad with no version at all.
  - The publisher's help page (`https://img.jgi.doe.gov/docs/IMG-VR.pdf`, 13 pages, retrieved
    2026-10-15) describes geNomad's role in detail and contains no version string anywhere —
    the strings `version` and `v1.` do not occur in it.
  - The IMG/VR v4 paper could not be retrieved in this environment: OUP returns 403 and PMC
    serves a proof-of-work interstitial rather than the PDF. So the claim this audit may make
    is **"no version is stated in the release note or the publisher's help page"**, scoped to
    the two primary sources actually checked, and not "no version is stated anywhere". The
    paper is registered `unretrieved` and the gap is flagged for A6.1.

  What *can* be established is a bound, from dates the publisher does not control. geNomad's
  first public release is 1.0.0 (2022-07-30) and the next is 1.1.0 (2022-08-22); 1.2.0 did not
  exist until 2022-11-15. The v4 release files are dated 2022-09-20. So the labels were
  produced by geNomad ≤ 1.1.0 — or by a pre-release build, since geNomad and IMG/VR come from
  the same group and the geNomad preprint postdates v4 by a year. The marker database pairs
  with the code by the publisher's own `releases.txt`, which maps package 1.1 to database v1.1;
  the v1.1 database's files are dated 2022-08-22, three days after the ICTV release D-086 pins.
- **Decision:** Benchmark **geNomad 1.1.0 with marker database v1.1** — the newest pairing that
  could have produced the labels — and record in the artefact that the version is a bound, not
  a statement by the publisher. Reporting an error rate against 1.1.0 and calling it "the
  version IMG/VR used" would be the overclaim; reporting it against the current 1.12.0 would
  measure a tool the filter cannot have touched.

  Four environment pins are part of the decision, not incidental, because without them the 2022
  tool does not run in 2026 at all. They live in a `genomad` pixi environment with
  `no-default-feature`, so the project's own Python stack is not held back to 2022:
  - **Python 3.10** and **numpy <1.24**: geNomad 1.1.0's `marker_classification` calls
    `np.warnings`, removed in numpy 1.24, so the tool does not import against a current numpy;
    numpy 1.23 is the last series built for 3.10.
  - **mmseqs2 13.45111**, the series geNomad 1.1.0's own recipe floors at. The current 18.x
    dies in the prefilter against the 2022 profile database however far the search is split.
  - **`--splits 8`**. mmseqs needs ~24 GB to hold the 227,900-profile index in one pass and the
    session container has 16 GB; splitting the target database is what makes the search fit.
    Recorded because it changes nothing about the result and everything about whether there is
    one.

  One provenance trap is recorded because it would silently falsify a manifest: **`genomad
  --version` reports the wrong version in this environment.** geNomad 1.1.0 calls
  `click.version_option()` with no package name, and a modern click resolves the distribution
  by walking the call frame, finding `rich-click` instead — so the CLI prints `1.9.8`. The
  pipeline records the version from the installed distribution's own metadata
  (`genomad.__version__`, `genomad-1.1.0.dist-info`), never from `--version`, and
  `repro.tool_version(["genomad", "--version"])` must not be used for it.
- **Rejected:** *Benchmark 1.0.0 as well, to bracket* — worth doing and not free; the two
  releases are three weeks apart and the marker databases differ (v1.0 vs v1.1), so a
  difference between them would be a finding about geNomad's own churn rather than about the
  filter. Deferred to A4.4 rather than dropped.
  *Ask the publisher* — correct in the long run and outside this task's timeline; §4's
  disclosure process (X3.1) is where contact with the developers is handled, and A4.2 must not
  pre-empt it.

---

### D-086 — Ground truth is the ICTV taxonomy in force when the corpus was built, so revision stays A9.1's subject

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** Measuring a classifier's error needs labels that did not come from a classifier.
  For viral family there is one such source: the ICTV, which does not predict family membership
  but defines it, and publishes per species the ratified lineage and the GenBank accession of
  the exemplar isolate. Which ICTV release to use is the live choice, because the taxonomy moves
  — §A9 is a whole task about that — and a later release would score geNomad as wrong wherever
  the ICTV has since reclassified a taxon.
- **Decision:** Pin **VMR_20-190822_MSL37.3** (sha256
  `66791e9bfea59ff051b5098d67d6a7406f972ee8ab0c759076c5e8b8f059bf32`), the taxonomy in force
  when IMG/VR v4 was built. VMR_20 is dated 2022-08-19: three days before the geNomad marker
  database D-085 pins, and a month before the v4 release files. Revision `.3` is the last
  correction to that same VMR_20 content, so it renders the taxonomy of the time as accurately
  as the ICTV ever did without advancing to a later MSL.

  The division of labour this protects is the point. **A4.2 measures what the tool got wrong
  about the taxonomy of its own day; A9.1 measures what the taxonomy did afterwards.** Using
  MSL41 here would sum the two and attribute the total to the tool, which would overstate
  A4.2's finding — and §2's commitment to a publishable null cuts both ways, so an error in the
  audit's favour is the same failure as one in the filter's.
  `ictv.release()` refuses an unpinned release and a test asserts the pin predates 2022-09-20,
  so the property is enforced rather than remembered.
- **Rejected:** *The current VMR (MSL41)* — conflates tool error with taxonomic revision.
  *VMR_21-221122_MSL37 (Nov 2022)* — same MSL, but published after the corpus was built, so it
  can contain decisions the tool could not have known; it is the natural sensitivity check and
  is noted for A4.4 rather than used here.
  *NCBI Taxonomy instead of the VMR* — it is the taxonomy geNomad's own database is keyed on, so
  scoring geNomad against it would be partly self-referential, and it carries no exemplar
  designation.

---

### D-087 — The evaluation set: one sequence is one record, complete genomes only, capped per family and sampled by hash

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** The VMR's 10,434 exemplars do not become an evaluation set without four choices,
  each of which moves the result. All are fixed here, before any error rate has been computed.
- **Decision:**
  **The unit is the sequence, not the species.** A filter acts on one record at a time, and a
  metagenomic assembly yields the segments of a segmented virus as separate contigs. Five of
  the nineteen denylisted families are segmented, so scoring per species would hide exactly the
  case where a short segment carries too few marker genes to be placed — which a five-sequence
  pilot already showed, with an influenza A segment 7 (Orthomyxoviridae, denylisted) receiving
  no lineage at all while four complete genomes in the same run were assigned correctly. Each
  segment is scored as its own record and remembers the species it came from.

  **Complete genomes only** for the primary arm: the VMR's `Complete genome` and `Complete
  coding genome` wordings both count, `Partial genome` and `No entry in Genbank` are excluded.
  This is the condition under which ground truth is trustworthy, and it is deliberately the
  *easiest* case for the tool — which is why the headline rate is a **lower bound** (D-088).

  **Capped at 40 exemplars per in-scope family and 8 per control family.** Uncapped, the
  in-scope set is 2,723 exemplars of which Geminiviridae alone is 520, so a pooled rate would be
  weighted by how many species the ICTV has ratified in each family — a fact about taxonomic
  effort, not about the tool. The caps give 1,111 in-scope and 928 control exemplars across 44
  and 189 families, which keeps every family's own interval reportable and the whole run inside
  the session container.

  **Sampling within a family is a deterministic function of the accession** — `sha256` of the
  accession, lowest first — following D-078. The same set is selected on every run from the
  pinned VMR, with no seed to lose and no reliance on dict ordering.

  **Controls are the other direction, not filler.** The 928 out-of-scope exemplars are what the
  spurious-removal rate is measured over; without them the benchmark could only see leakage, and
  §2 forbids a pipeline built so that one direction is easier to find than the other.
- **Rejected:** *All 9,870 complete exemplars* — ~5× the compute for a pooled figure dominated by
  the largest families, and no better per-family precision where it matters.
  *A flat random sample* — reproduces the taxonomic-effort weighting the caps exist to remove,
  and leaves small denylisted families with single-digit counts.
  *Partial genomes included in the primary arm* — a weaker ground truth mixed into the headline;
  the length dependence is measured by strata instead (D-088).

---

### D-088 — The analysis is fixed here: two directions, six causes, exact intervals, per family before pooled

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** `AGENTS.md` requires that thresholds, parameters and analysis specifications be
  fixed before results are inspected, and that the choice be recorded with its timestamp. At the
  time of writing, the evaluation set has been defined and sized but geNomad has been run only
  on the five-sequence pilot named in D-087; no error rate over the evaluation set exists.
- **Decision:** The reported quantities, and the form they take:

  **Two rates, never one accuracy figure, each over the population it is a rate of.** *Escape* —
  the record's true taxon is denylisted and the tool's label does not put it there, so it
  survives a filter written to remove it — is a proportion of the records the policy meant to
  remove. *Spurious removal* — the true taxon is not denylisted and the label says it is — is a
  proportion of the records the policy meant to keep. The two have opposite consequences and are
  not recoverable from each other, and `misassignment.rates` divides each by its own denominator
  so that neither moves when the control set is resized. No pooled accuracy is offered by the
  module at all.

  **Six escape causes**, reported underneath the rate: absent at the rule's ranks, shallower
  than the rule, misassigned family, misassigned order, unclassified, and not called viral. The
  split matters because only under-assignment is visible in the corpus as a missing field —
  which is what A4.1 already measured as the filter's ceiling — so the quantity A4.2 *adds* is
  the confidently-and-wrongly-labelled part that A4.1 could not see. `not_viral` is kept
  separate from `unclassified` so that an escape occurring one stage earlier is not charged to
  the taxonomy step.

  **Exact (Clopper-Pearson) intervals at 95%, on every rate, with no point estimate shipped
  without one.** Exact rather than normal-approximate because several per-family counts will be
  zero, and a normal interval puts a zero-error family's upper bound at zero — reporting a
  certainty the data does not contain. A rate over an empty denominator raises rather than
  returning `(0, 1)`, so an untested family cannot appear in a results table as though it had
  been tested.

  **Per family before pooled**, which `AGENTS.md` makes the default presentation everywhere.

  **Length strata**, over the edges `tools/taxonomy_dependency.py` already measured the corpus
  against. This is what makes the result transferable at all: the evaluation set is complete
  genomes and the corpus is 84.7% `Genome fragment`, so the honest way to carry one onto the
  other is to show how the rate moves as the evidence shrinks.

  **Propagation is reported as a lower bound, with the bound's direction in the artefact rather
  than in prose.** `misassignment.propagate` multiplies the escape rate and both interval
  endpoints by an estimate of the in-scope corpus population, and carries a `bound: "lower"`
  field with its reason: a fragment carries fewer marker genes than the genome it came from, and
  a marker-based classifier given less evidence assigns a shallower lineage, which is itself an
  escape route. The in-scope population is recorded as an **input**, not a finding, because
  knowing it exactly would need the ground truth the corpus lacks.
- **Rejected:** *A single accuracy or F-score* — collapses the two directions, and the filter's
  behaviour is not symmetric in them.
  *Wilson intervals* — adequate in the middle, wrong at the zero-count families this set will
  contain.
  *Bootstrap intervals* — no advantage over the exact method for a binomial, and they would put
  a seed where a closed form does.
  *Pooling across families as the headline* — reports the ICTV's species-ratification effort.

---

### D-089 — Leakage is derived from the records a rule removed, not by multiplying them by the escape rate

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** D-088 fixed the propagation step as multiplying the escape rate by "an estimate
  of the in-scope corpus population". Implementing it exposed that the obvious estimate is the
  wrong one, and wrong in the direction that flatters the filter. Recorded before the
  benchmark's escape rate existed: the geNomad run over the evaluation set was still in its
  marker search when this was written, so no rate had been seen.
- **Decision:** What the corpus shows is `R`, the records the rule **did** remove — 181,530
  denylist hits, of which 38.56% rest on a geNomad label. What a leakage figure needs is `N`,
  the records it **should** have removed. A rule removes the in-scope records it did not miss,
  so `R = N(1 - e)`, giving `N = R / (1 - e)` and an escaping count of `R * e / (1 - e)`.

  Multiplying `R` by `e` — the reflex, and what D-088's wording invited — understates leakage by
  a factor of `1 - e`, because it treats the observed removals as the whole in-scope population
  when they are precisely that population *minus the thing being counted*. At an escape rate of
  a half it is wrong by a factor of two.

  Each interval endpoint goes through the same derivation, so the reported range is a range of
  implied populations rather than an interval around one of them. At `e = 1` the result is
  `None`, not infinity: if nothing in scope was ever removed, the observed removals carry no
  information about how many there were, and a sentinel is more honest than a very large number.
  The artefact carries the algebra in an `arithmetic` field, because this is the step a reader
  is most likely to redo.
- **Rejected:** *Keep `R * e` and note the bias in prose* — the number gets quoted and the prose
  does not travel with it, which is the same failure `propagate`'s `bound` field exists to
  prevent.
  *Estimate `N` from A4.1's family-labelled share instead* — that counts records the corpus
  labels at family, which is a different population again (it includes out-of-scope families and
  excludes everything unlabelled), and it would silently mix two tasks' denominators.
  *Report the escaping count without an implied population* — the derivation is the part a
  reviewer has to check, so hiding it inside one multiplication is the wrong trade.

---

### D-090 — geNomad's lineage is a compacted list, not a positional ladder, and reading it wrong inflated the headline

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** `amazebio.genomad.parse_lineage` originally read geNomad's lineage field by
  position — `Viruses;<realm>;<kingdom>;<phylum>;<class>;<order>;<family>` — and used the ICTV's
  mandated rank suffixes only to *check* that read, on the same principle
  `conformance.parse_lineage_tag` applies to Evo's released tag (D-057). The check fired on 195
  of 2,329 classified records in the first scored run, and it was right.

  geNomad **omits** a rank it cannot resolve rather than leaving the field empty. Its lineage is
  therefore a compacted list of the ranks it did resolve. A phage placed at class and family but
  not order comes back as
  `Viruses;Duplodnaviria;Heunggongvirae;Uroviricota;Caudoviricetes;Ackermannviridae`, where the
  family sits in what a positional reader calls the order slot.

  The consequence ran in the direction that flatters this audit. Read positionally, such a
  record has no family at all, so a denylisted family lands in `predicted_order`, matches
  nothing on the order list, and is scored as an **escape the tool never committed**. It
  inflated precisely the headline the task reports.
- **Decision:** Rank comes from the ICTV suffix; position is demoted to nothing. Suffixes are
  tried longest-first so `-viridae` can never be read as `-virae`. A name carrying no recognised
  suffix is claimed for nothing rather than guessed at — guessing is how a family becomes an
  order. Ranks below family (`-virinae`, `-virus`) are skipped knowingly rather than recorded as
  unreadable. A rank named twice keeps the first and records the collision.

  The corrected run reads all 2,329 lineages with **zero anomalies**, which is the evidence that
  the suffix is the real signal rather than a second guess at one.

  What it changed, recorded because the superseded figures appear in this session's history and
  nowhere else — no artefact with the old numbers was ever committed, pushed or cited:

  | quantity | positional read | suffix read |
  |---|---|---|
  | escape rate | 40.68% (38.18–43.21) | **36.23% (33.80–38.72)** |
  | spurious removal | 1.10% (0.65–1.73) | **3.05% (2.27–4.00)** |
  | escapes at 80–200 kb | 55 of 110 | 1 of 110 |
  | lineage anomalies | 195 | 0 |

  Both directions moved as the mechanism predicts. Escapes fell because false ones were removed;
  spurious removals *rose*, because records whose family the tool did place — correctly, into a
  denylisted family the policy never named — had previously been misread as having no family and
  so as not removed. The 80–200 kb stratum collapsing from 55 to 1 is the same artefact
  concentrated: the large insect dsDNA families (`Baculoviridae`, `Nudiviridae`) are the ones
  geNomad places at family while skipping order.
- **Rejected:** *Keep the positional read and treat the 195 anomalies as a reported caveat* —
  the anomalies are not uncertainty about the tool, they are a defect in our reading of it, and
  §2's commitment cuts both ways: an error in the audit's favour is the same failure as one in
  the filter's.
  *Use position where the suffix is absent* — the only names without a suffix are ones no rank
  can be claimed for, and falling back to position there reintroduces the whole bug for exactly
  the records that triggered it.
  *Re-run geNomad* — unnecessary and misleading as a remedy: the tool's output was correct
  throughout and is unchanged on disk. Only the parse was wrong, so only the scoring step was
  re-run, against the same pinned `evalset_taxonomy.tsv`.

---

### D-091 — Phase A does not publish a leakage figure covering a minority of the filter's removals, so A4.4 blocks the write-up

- **Date:** 2026-10-15
- **Task:** A4.2 (decision by the project owner; recorded by A4.2)
- **Context:** A4.2 measured geNomad's escape rate at 36.23% (33.80–38.72) and established that
  geNomad carries **38.56%** of the 181,530 records Evo's denylist removes from IMG/VR. The
  other **61.44%** rest on taxonomies IMG/VR imported from other datasets — RVMT alone supplies
  49.51% — which are not classifiers this audit can run (D-084). A4.4 was created to own that
  remainder and, as created, blocked nothing: A6.1 could have written up Phase A on A4.2 alone,
  reporting the measured component and naming the rest as a bound on the audit.

  That left a real choice, because both readings are defensible. Publishing now gets the
  headline out and states its own coverage honestly; waiting risks A4.4 concluding that the
  overlap needed to measure RVMT does not exist by construction, which would hold the write-up
  on a question that cannot be answered.
- **Decision:** The project owner's call: **A4.4 blocks A6.1.** Phase A does not publish a
  quantified leakage figure that covers a minority of the filter's hazard-relevant removals.
  `A4.4.blocks` gains `A6.1` and `A6.1.depends_on` gains `A4.4`.

  What that does *not* require is worth stating, because it is what keeps the gate from becoming
  unanswerable. A4.4's Done-when is already satisfied either by measuring a method or by
  establishing from primary sources why it cannot be measured. So the write-up is blocked on
  **the statement**, not on a number: "RVMT's labels cannot be scored against ratified taxonomy
  because its records are metatranscriptome contigs with no ICTV exemplar overlap" is a
  completed A4.4, and §2's commitment to publishing a null applies to that finding as much as to
  a clean conformance result.

  The reasoning behind the call, since a later reader will want it: §7 notes Phase A names real
  labs and must be airtight against a motivated reviewer. "geNomad misses 36% of what the
  denylist targets" invites the obvious objection that geNomad accounts for a third of the
  denylist's work, and answering it with a named-but-unmeasured remainder concedes the point.
- **Rejected:** *Leave A4.4 non-blocking and publish with the coverage gap stated prominently* —
  the gap is stated in the artefact already and the number would still be quoted without it.
  *Split A6.1 so the dependency decomposition and conformance results publish early while the
  leakage figure waits* — defensible, and it needs a new task ID and a second disclosure pass
  under §4, which buys less than it costs while B and C are still running.

### D-092 — The viral seed set is rebuilt from staged UniRef100, and what that costs is measured
- **Date:** 2026-10-15
- **Task:** A1.6
- **Context:** ESM3-open's filter is similarity-based, so re-executing it needs the two denylists
  it queries against. Neither is published as a set. The viral one is "sequences that are
  annotated as viral in UniProt and align almost exclusively to other viral sequences in
  UniProt", roughly 4M sequences; the select-agent one is "all sequences in UniProt belonging to
  organisms on the Select Agents and Toxins List". "Annotated as viral in UniProt" is a statement
  about UniProtKB entries, so the faithful source is UniProtKB.
- **Decision:** **Build the seed set from the staged UniRef 2023_02 UniRef100 tier, not from
  UniProtKB, and report the gap that substitution opens rather than closing it.** UniProt serves
  no 2023_02 viral taxonomic division as a separate file — the previous-releases directory holds
  whole-release tarballs only, and the per-division files are inside the knowledgebase archive —
  so using UniProtKB would mean streaming the entire knowledgebase to reach one member of it.
  UniRef100 covers every UniProtKB entry, is already staged, and carries each member's own NCBI
  taxonomy id, so viral membership is answerable from bytes this project holds. Three parts of
  this are commitments.
  **A cluster is viral-seeded if *any* member is viral, not if its representative is.** Testing
  the representative would drop clusters that are viral through a member, and dropping them
  understates the filter's reach, which §2's commitment treats as the same failure as overstating
  it.
  **The exactness this costs is measured, not assumed.** UniRef100 merges sub-fragments of 11 or
  more residues as well as identical sequences, and the release carries only the representative's
  sequence per cluster, so a cluster can be viral-seeded through a member whose sequence is not
  the one we hold. On the first 796,477 clusters of the tier: 2.38% of viral-seeded clusters have
  a non-viral representative and 7.75% are taxonomically mixed. Both counts travel with the seed
  count in the artefact. The direction is not symmetric and the write-up should say so: an
  over-long representative makes the seed set over-inclusive, which pushes removal up and
  survival down, so contamination is the conservative error here exactly as it was in D-083.
  **The taxonomy is pinned to a dated dump contemporaneous with the corpus.** Whether an organism
  counted as viral is a property of the taxonomy in force when the filter ran, so the pin is
  `taxdmp_2023-04-01.zip` (60,742,039 bytes, sha256 `6afaee95…1d07`), against UniRef 2023_02. It
  matters: that snapshot has 236,541 taxa under Viruses where today's has 291,938. The undated
  `taxdump.tar.gz` NCBI serves at the top of its taxonomy directory is rewritten daily and pins
  nothing, which is why it is not the input even though it is the obvious one.
- **Rejected:** Acquiring UniProtKB 2023_02 to get the annotation exactly — it is the faithful
  source and it is a whole-release tarball against a question answerable from staged bytes; the
  2.38% gap is cheaper to report than the acquisition is to buy, and D-033's warning about
  permanent spend in a bucket with no delete applies. Quantifying "almost exclusively" so the
  second clause of the definition could be applied — the source attaches no number to it, and
  inventing one would propagate a fabricated parameter into every ESM3 figure, which is what
  D-015 refused for the threshold. This module therefore produces the **annotation-only** seed
  set, the first clause alone, which is a superset of the set described and again overstates
  removal rather than understating it. Using NCBI's division codes (`VRL`, `PHG`) instead of
  descent from taxid 10239 — descent is one rule over the tree the annotation is defined on,
  and it keeps phages in, which nothing in ESM3's description carves out.
- **Consequence:** `src/amazebio/seeds.py` and `tools/esm3_seeds.py`, with tests, on branch
  `ccr-3e0650c5-8fsgiq`. Every ESM3 similarity figure is explicitly "against a seed set
  reconstructed from UniRef100 cluster membership", and carries the representative gap beside it.
  One thing this buys that D-032 took away: the reconstruction has a **validation target that
  works**. ESM3 states the viral denylist is roughly 4M sequences, and a seed count can be set
  against that — unlike the reported 10.6M removals, which D-032 established cannot validate a
  reconstruction because the stated corpus sizes already miss their own sources by ten times it.
  Note what a bounded run cannot do: UniRef is ordered by accession, so a prefix of a tier is not
  a sample of it and no share measured from one estimates the tier's share. The full-tier pass is
  the only thing that produces a seed count.

### D-093 — MMseqs2 is pinned at 18.8cc5c, against a source that names no version
- **Date:** 2026-10-15
- **Task:** A1.6
- **Context:** `pixi.toml` requires a DECISIONS entry for each tool version it adds, and A1.6 is
  the first task to need an aligner. ESM3's filter description says "MMseqs" was used to query the
  training databases and states no version, no sensitivity, no coverage mode and no identity
  threshold — the threshold being the gap D-015 already reads as a three-point range.
- **Decision:** Pin `mmseqs2 18.8cc5c` from bioconda, the current release, and record the version
  gap as one more stated-versus-used entry rather than as a detail. There is nothing to match
  against: no version is stated, so no version can be reproduced, and choosing an older release to
  be closer to ESM3's publication date would be picking a number for the same reason D-015
  refused to pick a threshold — it would look like recovery and be inference.
- **Rejected:** An MMseqs2 release contemporaneous with ESM3's preprint — defensible-sounding and
  unfounded, since the paper names no version and the filter may predate the preprint by any
  amount. Using DIAMOND or BLAST because they are better documented — the source names MMseqs, and
  substituting a different aligner changes what is being re-executed.
- **Consequence:** Every ESM3 similarity figure is qualified by the aligner version being ours and
  the parameters being a reading. The parameter choices themselves are fixed before any output
  exists, in the entry that records the pass's design, not here.

### D-094 — The pass queries seeds against sharded corpus targets, and the orientation was measured
- **Date:** 2026-10-15
- **Task:** A1.6
- **Context:** A1.6's file says the alignment pass is the one Phase A task whose compute is the
  cost, and instructs that it be priced and put to the project owner before anything launches.
  Pricing it needs two things decided first: which way round the search runs, and how a database
  larger than the account's volume limit is handled.
- **Decision:** **Seed set as query, corpus as target, with the corpus sharded.** Measured in the
  session container on 4 cores over an identical 2,058,701-cluster slice: seeds-as-query took 335 s,
  and corpus-as-query had not left the prefilter after 45 minutes and was abandoned. The cause is
  that MMseqs2's prefilter does per-query work, so 2M queries against a small target costs far more
  than 15,845 queries against a large one. Sharding is not a tuning choice: the account's policy
  caps volumes at 200 GB in gp3/gp2, and a target database over UniRef's three tiers plus MGnify90
  is upward of 400 GB, so the corpus cannot be one database on any instance the policy permits.
  Querying the seed set against each shard in turn keeps the cheap orientation and respects the cap,
  and the per-shard hit lists concatenate because a hit is a property of one corpus record.
  **Clustering was considered and is the wrong instrument.** `linclust` over the union of seeds and
  corpus ran in 110 s against `search`'s 335 s on the same slice, and that comparison is a trap: the
  question is whether a given corpus sequence has a hit to the seed set, which is a search, and
  cluster membership is global and would change with the shard boundaries. The speed is real and it
  answers a different question.
- **The price is not yet a number, and the owner's decision was to make it one.** Extrapolating 335 s
  from a slice at 1/88,000 of the full target spans roughly 200 to 33,000 core-hours — about $10 to
  $1,400 for the charitable reading alone — depending on how the prefilter's cost divides between
  query batching and target scanning, which does not show up at container scale. The strict reading
  removes on any detected hit and so runs at the sensitivity floor, 10 to 50 times the charitable
  one. Put to the project owner as four options; the decision was **calibrate in-region first**,
  about $10, running the real pipeline over one UniRef shard to turn the two-order-of-magnitude
  range into a measured figure before the full pass is authorised.
- **Rejected:** Launching the full charitable pass without calibration — the range is too wide to
  commit to and AGENTS.md gives one shot at `UserData` with no shell, so a script that has never run
  at scale is the wrong thing to launch large. Running the pass in the session container — 295 GB at
  the measured 42.5 MB/s out of the bucket is about two hours and roughly $26 of metered egress, and
  it does not fit the 29 GB of free disk; this is the data-movement case the EC2 section describes,
  unlike the memory ceiling A4.2 recorded as not being one. Dropping MGnify to halve the residues —
  it carries no taxonomic annotation at all, which makes it the one component where an alignment
  filter is the only filter possible, so it is the last thing to cut.
- **Consequence:** The calibration run is next, and its figure decides the full pass. The sharding
  requirement is a property of the account's policy rather than of this task, so it belongs in
  AGENTS.md's EC2 section alongside the parallelism and memory notes.

---

### D-095 — geNomad's markers were annotated from a different VMR than A4.2 scored against, and it changes nothing

- **Date:** 2026-10-15
- **Task:** A4.2
- **Numbering:** drafted as D-092, which A1.6 took first; renumbered per `AGENTS.md`. Commit
  `b5200a2` on branch `ccr-bcc7b994-9ycpzn` is already pushed and cites this entry as D-092 in
  its message, so that citation resolves here. A1.6's D-092 is the one left in place: it was
  committed first and is cited from three entries of its own series.
- **Context:** D-086 pinned ICTV VMR_20-190822_MSL37.3 as ground truth, reasoning that the
  taxonomy in force when IMG/VR v4 was built is what isolates tool error from the taxonomic
  revision A9.1 measures. Retrieving the geNomad paper (`S-GENOMAD-NATBIOTECH`) afterwards
  surfaced a fact that reasoning did not account for: geNomad's taxonomically informed markers
  were annotated from **ICTV Virus Metadata Resource version 19**, four months earlier than
  VMR 20 though still MSL37.

  That matters because it splits the question D-086 treated as one. Scoring against the VMR the
  markers were built from measures the tool against its own reference — can it reproduce the
  taxonomy it was taught? Scoring against the VMR in force when the corpus was built measures
  what the filter inherited. A4.2 reports the second, which is the audit's question, but a
  reviewer is entitled to ask whether the first would give a different number.

  The same paper also states, from the tool's authors, that geNomad produced the data IMG/VR v4
  was built from. D-084 established the dependency from the corpus's own method field; this
  corroborates it from a primary source, which `AGENTS.md`'s rule against secondary sources
  makes worth having.
- **Decision:** The pin stands, and the sensitivity check is run and reported rather than
  argued. `ictv.MARKER_SOURCE_RELEASE` pins VMR 19 (`VMR_19-250422_MSL37.xlsx`, sha256
  `e8ed871a…`) so the comparison is re-runnable, and a test asserts it is the same MSL as the
  benchmark release — a different MSL would make the comparison a measure of taxonomic revision
  rather than of this choice.

  Over the 3,149 scored accessions:

  | difference | count |
  |---|---|
  | family assignment differs | 4 |
  | order assignment differs | 0 |
  | **denylist scope differs** | **0** |
  | accession absent from VMR 19 | 24 |

  All four family differences are bacteriophage renames — `Flexireviridae`→`Graaviviridae`,
  `Queuoviridae`→`Druskaviridae` — and every one is an out-of-scope control. **No record
  changes which side of the denylist it falls on, so neither reported rate moves.** The 24
  absences are accession-field edits between the two revisions, not taxonomic changes.

  So A4.2's escape rate of 36.23% and spurious-removal rate of 3.05% stand as reported, and the
  artefact's choice of ground truth is now a measured non-issue rather than an assumption.
- **Rejected:** *Re-score against VMR 19 and report that instead* — it answers a question about
  geNomad's self-consistency rather than about what the filter inherited, and D-086's reasoning
  for the later release is unchanged by this.
  *Report both as parallel headline rates* — they are identical to within four out-of-scope
  renames, so a second column would imply a distinction the data does not contain.
  *Leave the discrepancy unrecorded because the result is unchanged* — the check is cheap, the
  objection is obvious, and §7 requires writing for a reviewer who wants the result to be wrong.

---

### D-096 — The IMG/VR v4 paper states the geNomad version and documents the taxonomy methods, so two of A4.2's findings are corrected

- **Date:** 2026-10-15
- **Task:** A4.2
- **Context:** D-084 and D-085 were written with the IMG/VR v4 paper unretrieved. Four automated
  access paths refused it (OUP 403; PMC proof-of-work interstitial; the eScholarship and OSTI
  mirrors HTTP 202 behind a bot challenge), and both entries were scoped accordingly — D-085
  said in terms that its claim covered "the release note and the publisher's help page, the two
  sources actually checked". The project owner then supplied the PDF
  (`S-IMGVR-V4-NAR`, sha256 `06de029f…`), and it answers both questions.

  This entry is a **correction**, and it goes in the direction that costs the audit rather than
  the filter. §2's commitment cuts both ways and §7 assumes a reviewer who wants the result to
  be wrong; a finding that survives only because a source was unreachable is exactly the kind
  that reviewer would overturn.
- **Decision:**

  **1. The geNomad version is stated, and it is the one A4.2 benchmarked.** The paper's Methods
  name **geNomad version 1.1.0** twice — once for mining UViGs from IMG/M assemblies retrieved
  2022-04-10, and once for the marker-based taxonomic assignment specifically — and reference 19
  is the Zenodo deposit of that release (doi:10.5281/zenodo.7015982). D-085's framing of the
  version as "a bound, not a statement" and as "unrecoverable from the publisher" is withdrawn:
  it was unrecoverable from this environment, which is a different claim and the one the audit
  may make. The pin itself is vindicated — A4.2 derived 1.1.0 from release dates alone, before
  the paper was in hand, and `genomad.VERSION_EVIDENCE` keeps that argument as independent
  corroboration precisely so the agreement is checkable rather than circular.

  What survives from D-085 is narrower and still worth reporting: the **release note pins CheckV
  to v1.0.1 in the same field list and names geNomad with no version**, and the help page carries
  none either. So the data a user downloads does not carry the version its own labels came from,
  and recovering it requires the paper. That is a provenance observation about the distribution,
  not a claim that the publisher withheld anything.

  One residual gap is real and now stated as the only inferred part of the pin: **no source
  states the marker database version.** The paper gives the package version and the code's
  Zenodo deposit; the pairing to database v1.1 rests on the publisher's own `releases.txt`
  mapping. `VERSION_EVIDENCE["residual_gap"]` carries it and the report prints it.

  **2. The "three undocumented taxonomy methods" finding does not survive.** D-084 observed that
  the help page names four taxonomy approaches while the corpus carries eight method values, and
  called `RVMT`, `RefSeq` and `GVMAG` undocumented. The paper documents all three: sequences
  imported from RefSeq "were assigned to their NCBI taxonomy", and UViGs from the RVMT and GVMAG
  projects "were designated to taxonomic lineages listed in their original studies", with the
  four-method priority order applying to the remainder. Table 1 lists RVMT and GVMAG as data
  sources with their own references. **That part of D-084 is withdrawn.**

  What survives, and it is the part that bears on the audit: the **decomposition itself**, which
  was measured from the corpus and is untouched — geNomad carries 38.56% of the denylist's
  181,530 removals and RVMT 49.51%. The paper strengthens rather than weakens A4.4's premise by
  saying where those lineages came from, which is where A4.4 must now look. And the §A0 point
  survives in reduced form: the methods are documented in a paper behind an access path that
  refused four automated attempts, not in the release note or help page that ship with the data.

  **3. Two independent pins are confirmed.** The paper states the taxonomy is assigned against
  **ICTV Taxonomy Release #37**, which is the MSL D-086 pinned, and gives the IMG/M retrieval
  date as 2022-04-10 — closer to VMR 19 than to VMR 20, which is consistent with D-095's finding
  that the choice between them changes no denylist-scope decision in the evaluation set.

  **No measured result changes.** The escape rate of 36.23% (33.80–38.72) and the
  spurious-removal rate of 3.05% (2.27–4.00) were produced by geNomad 1.1.0 against ICTV MSL37
  and stand exactly as reported; `score` was re-run only so the artefact carries the corrected
  evidence rather than the superseded bound.
- **Rejected:** *Amend D-084 and D-085 in place* — `DECISIONS.md` is append-only, and an entry
  that quietly becomes right is worse than one that is visibly corrected.
  *Store the paper in `pdfs/` with the committed preprints* — those are bioRxiv CC-BY
  submissions; this PDF states no redistribution licence, so it is recorded
  `retrieved_not_stored` with its checksum, as `S-EVO2-NATURE` already is.
  *Treat the access failure as a finding about the publisher* — it is a finding about this
  container's network path. Unpaywall reports the article open access, and a person with an
  ordinary browser retrieved it in one attempt.

### D-097 — RVDB's families get a derived label, and `family_id` stays the only identity
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** A2.1's RVDB hit tables are correct and unreadable: the registry names its families
  `FAM004230` and the top of Evo 1's result is a column of such ids. The release ships an
  annotation database (`U-RVDBv32.0-prot-hmm.sqlite.xz`, pinned against the publisher's own md5),
  and inspecting it settles what is available: tables of **keyword frequencies** — one set
  harvested from the member sequences' names, one from the domain literature — plus an LCA taxon
  id, a member count and a model length. **There is no family name anywhere in it.** So a
  readable label cannot be looked up; it has to be derived, and deriving a name for somebody
  else's family is exactly the kind of step that later gets quoted as if the publisher had said
  it.
- **Decision:** Three parts, and the second is the one that matters.
  **The label is the four most frequent sequence-name keywords, in frequency order.** It reads as
  a rough function: `FAM000069` becomes "helicase virus rna dependent", `FAM005268` becomes
  "reductase ribonucleotide virus large". All 13,679 families get one; none came back empty.
  Reference-derived keywords travel *beside* the label rather than inside it, because they
  describe the domain literature rather than the member sequences, and mixing the two would make
  a derived string look like a curated title.
  **`family_id` remains the only identity.** Counts are keyed on it, the survival denominator is
  a set of ids, and it is the only thing a figure or a paper sentence may cite as the family. The
  label is for a reader's orientation and carries a field saying so.
  **The labels ship in the registry artefact and are joined on `family_id`**, in
  `artifacts/a2-1/registries/rvdb-families.json`. The hit tables are not rewritten to carry them.
- **Rejected:** Writing the label into each table's `name` field. It would read better and it
  would mean editing a measurement after the fact — the tables already have their `run.json`,
  their manifest digest and their provenance, and a relabelling pass would either invalidate that
  or silently not. The join costs a reader one small file.
  Re-running the search with labels in place, which would be the clean way to get them into the
  tables and costs 50 minutes of RVDB search per release to change a display string.
  Taking the label from the LCA taxon instead ("Caudoviricetes family 4230"). It is the
  publisher's own datum rather than a derivation, which is attractive, but 10239 (Viruses) is the
  LCA for most families, so it labels almost everything identically.
  Leaving the ids bare and letting A6.1 solve it. The write-up is where an unreadable table
  becomes a figure nobody can check, and `AGENTS.md` requires every number in a write-up to trace
  to a machine-readable artefact — the artefact is the right place for the mapping.
- **Consequence:** A reader joins one file to read any RVDB result. The write-up must present the
  label as derived — this project's summary of the publisher's keyword frequencies — and never as
  RVDB's own name for the family, which is a sentence-level discipline rather than something code
  can enforce. The same question returns in A2.2 for fold families and in C5.2 for the homology
  neighbourhood index: where a registry ships identifiers without names, the mapping is an
  artefact with a stated rule, not a label invented at figure time.

### D-098 — D-078's cost figure was wrong by a factor of thirty, and a full census is affordable after all
- **Date:** 2026-10-15
- **Task:** A2.1
- **Context:** D-078 pre-registered the sample and justified it with a measurement: "98 million
  profile-residues per second for RVDB-prot ... against 13,679 RVDB profiles that is roughly
  40,000 core-hours", and concluded that a full pass is "not expensive, it is arithmetically out
  of reach". **The conclusion was false and the measurement behind it was worthless.** The
  benchmark searched 300 profiles against 2,000 random 300-residue sequences — a job small enough
  that per-profile fixed cost dominated it, which understated real throughput by about three
  orders of magnitude.
  The real runs settle it. RVDB-prot over 23.28 M residues of Evo 1's viral component took 50.0
  minutes on three cores: **386 core-seconds per million residues**, against the benchmark's
  implied 140,000. Evo 2's component gives 428 and its plasmid/phage component 344, so the figure
  is stable across sources.
- **Decision:** The cost of a full, unsampled census is recorded here as measured, and D-078's
  figure is superseded. Scaling each component's own measured rate to its full residue count:
  | component | residues | RVDB | Pfam viral |
  |---|---|---|---|
  | `opengenome`/`stage2` | ~11,642 Maa | 1,250 core-hours | 87 |
  | `opengenome2`/`imgvr` | ~11,577 Maa | 1,375 core-hours | 95 |
  | `opengenome2`/`imgpr` | ~1,472 Maa | 141 core-hours | 43 |
  **About 3,000 core-hours for both releases against both registries** — not 40,000 for one
  component of one release. Linear scaling is sound here: `hmmsearch`'s cost is residues x
  profiles, and the sample is a 0.1-0.2% random draw.
  **The sampling design itself stands**, unchanged and still pre-registered: a sample was the
  right first pass, it produced the result, and the hash nesting means a deeper pass extends it
  rather than repeating it. What is withdrawn is the *reason* given — "out of reach" — and every
  statement resting on it.
- **Rejected:** Correcting D-078 in place. The log is append-only and that entry was cited in the
  PR for #17, in `metrics/detections.md` and in the task file before the error was found;
  rewriting it would leave those citations pointing at text that no longer says what they
  reported. The citations are repointed to this entry instead.
  Also rejected: treating this as a private slip to fix quietly. The figure had already been
  published in a merged pull request body and used to justify a methodological choice to the
  project owner, which makes it a finding about this project's own rigour. `AGENTS.md` asks for
  airtight work against a motivated reader; a reader who re-derived the arithmetic would find
  this in a minute.
- **Consequence:** The scale decision changes from impossible to affordable and goes back to the
  project owner with real numbers. Two bounds on it: the account's policy allows nothing larger
  than `c6i.2xlarge` (8 vCPU — `c6i.4xlarge` and above return `UnauthorizedOperation`), so a
  census is about 375 instance-hours of one machine or a fan-out across several, and an instance
  cannot be inspected once running (`AGENTS.md`). And the accumulation curves say the current
  bound is weak: on the last doubling of sampled records, Pfam still gained 16% more families and
  RVDB 31-39%, so family discovery is far from saturated and a deeper pass would move the
  headline materially rather than confirm it.
  The general lesson, which is the part worth carrying: **a benchmark that does not resemble the
  real job is not evidence.** This one was off by 1,000x because it was too small to leave the
  fixed-cost regime, and it was used to justify a decision about what is possible. Any later task
  costing a pass over the corpora — A2.2's structural search above all, which has the same shape —
  should take its throughput from a run of realistic size or not quote one.

### D-099 — The sample is deepened ten-fold, searched as bands, and why that cannot bias the bound
- **Date:** 2026-10-16
- **Task:** A2.1
- **Context:** The first pass produced a lower bound on family-level survival from a 0.2%/0.1%
  sample (D-078). Two facts then arrived together. D-098 corrected the cost: a full census is
  about 3,000 core-hours rather than the 40,000 that had been claimed, so depth is a decision
  rather than a limit. And the family accumulation curves, computed from the first pass's own
  detections, show discovery nowhere near saturation — on the **last doubling** of sampled
  records Pfam still gained 16% more families and RVDB 31-39%. A bound that moves that fast
  under more data is a weak bound. The project owner was given the three options with those
  numbers and **chose a ten-fold deepening in this container**.
- **Decision:** Rates go to ten times the pre-registered ones — `stage2` 0.02, `imgvr` 0.01,
  `imgpr` 0.01 — at the same seed **20261015**, declared here before the deepening ran.
  **It is searched as hash bands, and the already-searched prefix is not searched again.** Sample
  membership is `blake2b(seed, record_id) < rate · 2⁶⁴`, so the sample at rate `r` is a *prefix*
  of the sample at any larger rate, and widening from `r` to `10r` is exactly the band
  `[r, 10r)`. `amazebio.detect.in_band` is that primitive and a test pins the property:
  prefix and band are disjoint, and their union is the wider sample exactly.
  **Bands are run separately because no single run in this environment may exceed two hours**,
  while a ten-fold pass over Evo 1's viral component is about eight. Each band run writes a
  *part*; `--assemble` merges the parts with the first pass into the final tables, summing
  per-source counts and recording the bands. The assembler **refuses** to write a table whose
  bands leave a gap in `[0, rate)`, because such a table would claim a rate over records nothing
  read — an understated lower bound with nothing to show it.
  **Why changing a pre-registered sample size after seeing results is legitimate here, stated
  plainly rather than assumed.** `AGENTS.md` fixes thresholds and analysis specs before results
  are inspected, and that is not relaxed: the thresholds (D-076), the family universes (D-075,
  D-083), the route mapping and the metric definitions are all unchanged and none of them is
  touched by this entry. What changes is only *how many records were read*. The headline is a
  lower bound whose dependence on sample size is **monotone**: more records can only add
  families, never remove one, so there is no choice of depth that makes a family appear or
  disappear to order, and no analysis decision rides on the result. The one thing that could have
  been gamed — stopping at a depth that flattered a conclusion — is foreclosed by the bands being
  declared here, the seed being fixed, and the coverage check refusing a partial tiling.
- **Rejected:** A full census now (~3,000 core-hours, ~$130, and capped at 8 vCPU per instance so
  about 375 instance-hours), which the owner declined for this pass; it remains available as its
  own task rather than as A2.1 widened.
  One long run instead of bands. It does not fit the two-hour limit, and `apply_policies` already
  demonstrated the failure mode earlier in this session: a 20 GB read was lost when its run was
  stopped at the limit, because it wrote its output only at the end.
  Re-running from zero at the deeper rate, which would re-search the first pass's records for
  nothing. The nesting exists precisely so that is unnecessary.
  Deepening only the component with the steepest curve (`imgvr`, whose RVDB discovery is rising
  fastest). It would buy the most families per core-hour and make the two releases' figures
  incomparable, which is the comparison Phase A is for.
- **Consequence:** The headline stays a `lower_bound` and becomes a tighter one; `estimate_kind`
  does not change and A3.2's refusal to pool a bound with a population figure still holds. Every
  table will carry its bands and a `bands_cover_rate` flag, so a reader can see that the rate it
  claims was actually tiled. Expect roughly 14 band runs and about 18 hours of wall clock, nearly
  all of it RVDB-prot, which is 93% of the search cost. The first pass's tables are preserved
  under `artifacts/a2-1/initial/` so the reported result stays readable beside the deepened one.
### D-100 — The viral seed set is 3,159,223 clusters, and the corpus pass reconciles exactly
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** The first in-region run (instance `i-0f551e14f56b7916d`, code commit `26663b5`)
  completed a full pass over the staged UniRef100 tier of UniRef 2023_02. Its searches were lost
  to two faults recorded in D-101; the corpus pass itself finished and is a result.
- **Decision:** Record these as A1.6's measured seed-set figures, superseding every number taken
  from the prefix sample during development.

  | quantity | value |
  |---|---|
  | clusters read | 350,950,053 |
  | residues | 133,486,060,660 |
  | viral-seeded clusters | 3,159,223 (0.900%) |
  | viral-seeded residues | 1,180,922,524 |
  | viral-seeded with a non-viral representative | 33,394 (1.057% of viral-seeded) |
  | taxonomically mixed | 59,308 (1.877% of viral-seeded) |
  | wall time | 3,202.5 s on 8 vCPU, 7 parsing workers |

  **The cluster count reconciles exactly with the publisher's.** UniRef 2023_02 states 350,950,053
  UniRef100 clusters and the pass read 350,950,053. That is the check that the parser saw the whole
  tier and dropped nothing — worth more than any internal consistency test, because it is against a
  number this project did not produce.
  **The reconstruction corroborates ESM3's stated denylist size.** The source describes the viral
  denylist as "roughly 4M sequences"; the reconstruction is 3.16M UniRef100 clusters. The direction
  is right and expected: UniRef100 collapses identical sequences and sub-fragments, so clusters sit
  below the UniProtKB sequence count they cover. This is the validation target D-092 argued for and
  D-032 established the reported 10.6M removals could not provide. It is corroboration, not
  reproduction, and the write-up should say which.
  **D-092's measured limitation shrinks by half.** The representative-versus-member gap is 1.06%
  against the 2.38% measured on the first 796,477 clusters, and mixed membership 1.88% against
  7.75%. The prefix overstated both, which is the hazard D-078 and this task's own file warn about:
  UniRef is ordered by accession, so a prefix is not a sample. Every figure in D-092 taken from the
  prefix is superseded here; the reading itself is unchanged.
- **Rejected:** Reporting the prefix figures with a note — they are wrong, not provisional, and a
  reader comparing the two would have no way to know which governs. Treating the 3.16M as
  reproducing the stated 4M — the two count different things, and asserting agreement would paper
  over exactly the kind of unit mismatch §7's adversarial reader checks first.
- **Consequence:** `artifacts/a1-6/calibration.json`, at
  `s3://amazebio-corpora-897641797669/corpora/results/a1-6/calibration.json`. The seed-set FASTA
  itself was not uploaded before the run was cut (D-101), so the sequences have to be rebuilt; the
  counts above do not. Mean cluster length is 380.4 residues, which sizes every later estimate.

### D-101 — Two faults cost a finished corpus pass, and the sampled pass follows from the cost
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** The run in D-100 finished its corpus pass at minute 53 and returned only counts. Both
  causes were in how results escape a machine nobody can log into, and neither was in the analysis.
- **Decision:** **Terminate on an outcome, not on a timer; and ship a deliverable the moment it
  exists.** The launcher terminated in a bare `finally` — "both, not either", as the EC2 section
  requires — which is right except in one case: the watch window expiring is not a failure. The
  searches were still running at 115 minutes, that was the watch timeout and nothing else, and
  `StateTransitionReason` reads "User initiated". It now terminates when the run finished, failed,
  or is already going down, and when the window merely expires on a running instance it leaves it to
  the shutdown timer armed in `UserData` ahead of anything that can fail. `--attach` resumes a watch.
  Separately, the seed set was written at minute 53 and uploaded only after the searches, so the
  searches being cut destroyed it; it now uploads before any search starts.
  **The surviving search measurement redirects the task.** One shard of 333,742,778 residues ran 61
  minutes on 8 cores without finishing, which is a lower bound of 87,743 core-seconds per G residue
  of target, hence **more than 3,250 core-hours for UniRef100 alone** and more than 550 dollars for
  the full target at r6i.2xlarge rates. The bound is weak — the search was incomplete, so the true
  figure is higher — but it is enough to rule out the cheap end of D-094's range for good.
  **So the pass becomes a sampled one.** A1.6 will score a hash sample of the corpus and report
  survival as a rate with an interval, rather than scoring every record. This is what the project
  already does everywhere else: uncertainty travels with the estimate, and a rate with an interval
  is the honest form of this measurement regardless of budget. Cost falls with the sample fraction.
  Put to the project owner with the alternatives; this was the decision.
- **Rejected:** Scoring every record — defensible and very likely four figures, for per-record
  manifests whose extra precision no downstream task has asked for. Keeping the unconditional
  terminate and simply setting a longer window — the window would have to be guessed against a
  runtime nobody can predict, which is the position that caused this. Dropping the alignment pass —
  it is the only way the ESM3 arm of the survival work gets any input at all.
- **Consequence:** The calibration is redesigned around far smaller target shards and a sweep over
  query-set size, because the query side is 3.16M sequences and the first run showed it dominates.
  What A1.6 delivers changes with it: survival **rates with intervals** over a sample, not
  per-record manifests over the whole corpus, and every downstream consumer must be told which.

### D-102 — Search cost is affine in target size, not sub-linear; the power-law reading was an artefact
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** The grid run (instance `i-0fab283b268b592cc`, commit `64e613f`) measured 19 points
  over query sizes 3,130 to 3,159,223 and target sizes 8.3 to 66.4 M residues. D-101 framed the
  remaining uncertainty as a target-size *exponent*, and the first reading of these points put it at
  0.36–0.48 — strongly sub-linear, which would have made even a whole-corpus pass cost tens of
  dollars. That reading is wrong and the error is worth recording, because it is the kind that
  survives review by looking like a measurement.
- **Decision:** **Model search cost as affine in target size, not as a power law.** Per-query cost
  at the four target sizes, at 315,266 queries:

  | target (M residues) | core-s per query |
  |---|---|
  | 8.3 | 0.01003 |
  | 16.6 | 0.01289 |
  | 33.2 | 0.01625 |
  | 66.4 | 0.02281 |

  The increments per M residue across the top three are 0.000202 and 0.000198 — flat. Fitting
  `cost/query = a + b·T` on those gives **a = 0.009583 core-s, b = 0.0001992 core-s per M
  residue**, which reproduces the 33.2 point to 0.3%. A power law fitted to the same data returns
  an exponent near 0.4 only because the constant term dominates at these target sizes: at 8.3 M
  residues the fixed cost is three quarters of the total. **The apparent sub-linearity is the
  intercept, not the scaling.** Extrapolating the exponent would have understated the full pass by
  about a hundred-fold.
  **Query cost is linear, and that is measured at the real query size rather than extrapolated.**
  Per-query cost converges to 0.00994–0.01003 core-s at 315,266 and 3,159,223 queries against the
  same target, so doubling the seed set doubles the cost with no surprise at the size the pass will
  actually use. This is the one axis that needs no further measurement.
  **The strict reading costs 3.2× the charitable one**, consistent across the grid (2.3× at the
  smallest query, 3.12× and 3.20× at the two largest). D-094 feared 10–50×. Both readings are
  therefore affordable together wherever one of them is, and no choice between them is needed.
- **Consequence, with the arithmetic stated so it can be checked:** at `Q = 3,159,223` and a
  whole-corpus target of about 376,000 M residues, the affine model gives 236M core-seconds, or
  **65,700 core-hours — about $4,100 at r6i.2xlarge rates for the charitable reading and roughly
  $17,000 with strict included.** A 1-in-50 sample is about $83 and $350 respectively. So the
  sampled pass D-101 chose stands, and it stands on a firmer basis than when it was chosen.
  **This is still an extrapolation of 5,600× in target size and is not yet a result.** The affine
  fit makes a sharp, falsifiable prediction that the next run tests directly: at 13,350 M residues
  and 3,130 queries it predicts 17.4 minutes where the power law predicts 2.0. Instance
  `i-0afb243ec1234245c` is measuring exactly that, with targets from 66.7 to 13,350 M residues.
- **Rejected:** Reporting the 0.4 exponent with a caveat — it is not a conservative estimate, it is
  a hundred-fold error in the project's favour, and §2's commitment makes an error that flatters the
  audit the same failure as one that flatters the filter. Extrapolating from the affine fit without
  testing it — the fit is excellent over an 8× range and the pass needs 5,600×, and the physical
  reason to distrust it is concrete: at large target sizes MMseqs2 splits the target to fit memory,
  and a split target is re-scanned per chunk, which would make the true cost **worse** than linear
  rather than better.

### D-103 — Where sequence may live: memory and ephemeral scratch, never the repo, the artefacts or the audit store
- **Date:** 2026-10-16
- **Task:** A2.1
- **Context:** Four modules now cite D-020 for the proposition that "this project stores no
  genomic sequence" — `metrics/detections.md`, `src/amazebio/seqstream.py`,
  `src/amazebio/conformance.py` and `tools/detect_profiles.py`. **D-020 does not say that.** It
  is the A1.1 gate correction establishing that stage 2 is Evo 1's viral component, and the
  commitment is a parenthetical about one stored artefact: the sample "holding lineage tags and
  counts only — no genomic sequence enters this repo". A1.3 and A7.1 read it correctly as a rule
  about *outputs* ("a scan that never holds any cannot leak any, so the in-region pass can emit
  its result straight to the audit store"). A2.1 escalated it to "no sequence is written
  anywhere" and then paid for that reading: every one of the deepening's thirteen band runs
  re-reads its whole staged object, because the called proteins were not allowed to touch disk
  between runs. At 0.09 USD per GB that is about 10 USD of egress and two hours of wall clock to
  avoid writing 190 MB to a scratch directory that is destroyed with the container.
- **Decision:** The boundary is stated here rather than inferred from a parenthetical, and it is
  the one A1.3 and A7.1 were already working to:
  **Corpus sequence may exist in memory, and in ephemeral per-session scratch outside the
  repository, for as long as a computation needs it.** A2.1 caches called proteins there so a
  band search does not re-read the corpus.
  **It may never enter the repository, `artifacts/`, the audit store, or any file a reviewer or
  a later task reads as a result.** Every artefact carries accessions, scores, coordinates,
  counts and lineage tags only. That is what D-020's commitment protects and it is unchanged.
  **A cache is never an input to a result.** It is keyed by record identifier, and band
  membership is recomputed from the identifier when it is read, so a cache cannot change which
  records a run searched — only whether they had to be fetched again. Delete it and the run
  reproduces from the pinned corpus.
  The four citations are repointed here.
- **Rejected:** Keeping the stronger reading, which the project owner was offered with its price
  and declined. It is defensible — the safest handling of sequence is not to write it at all —
  but it was never decided, only inherited from a misreading, and paying for an unstated rule is
  worse than either reading.
  Caching under `artifacts/` or `data/`, which are git-ignored and would therefore be "outside
  the repository" in the only sense git cares about. They are inside the working tree, they are
  where every other task's inputs and results live, and a reviewer looking for the audit's
  artefacts should not find corpus sequence among them. Scratch is outside both.
  Caching the raw nucleotide records rather than the called proteins. The proteins are what the
  search consumes, they are a tenth of the size, and gene calling is the step whose determinism
  (D-077) is worth not repeating.
- **Consequence:** The remaining deepening reads each release once rather than once per band:
  about 28 GiB instead of 107, roughly 7 USD and two hours saved. Nothing about the result
  changes — same seed, same bands, same records, and the coverage check still refuses a table
  whose bands do not tile its rate. The lesson is the one to carry: **a commitment that four
  modules cite should be written where it can be read, not left as a parenthetical in an entry
  about something else.** This session escalated it once without noticing; the next task to
  inherit it would have had no way to tell the inherited reading from the decided one.

### D-104 — The cost model decomposed: a linear per-search scan plus a marginal per-query term approaching linear
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** D-102 recorded search cost as affine in target size, with a per-query coefficient of
  0.0001992 core-seconds per M residue, and refuted a sub-linear power law. That entry was fitted
  on a grid spanning 8× in target size, and on the sparse-query row of the sweep that followed.
  Both readings were wrong, in opposite directions, and the reason is worth recording because it
  is a general trap in benchmarking: **a cost with two components cannot be characterised by
  varying one input.**
- **Decision:** Model cost as `core_s = F(T) + Q · g(T)`, fitting both components from two query
  sizes at each target size. Measured on `r6i.2xlarge`, 8 threads, unsplit targets, at Q = 3,130
  and Q = 31,381:

  | target (M residues) | F (per-search, core-s) | g (per-query, core-s) | local exponent of g |
  |---|---|---|---|
  | 67 | 50 | 0.02156 | — |
  | 134 | 84 | 0.03173 | 0.56 |
  | 534 | 305 | 0.06232 | 0.49 |
  | 2,137 | 1,240 | 0.13788 | 0.57 |
  | 8,546 | 6,494 | 0.42834 | 0.82 |
  | 13,351 | 9,848 | 0.62277 | 0.84 |

  **`F` is linear in `T`** — 0.738 core-s per M residue at the top, which is the target scan, and it
  is negligible at the query sizes this task will use.
  **`g` is sub-linear but its exponent is climbing toward 1** — about 0.5 at small targets, 0.84 at
  13,351 M residues and still rising. This is the expected physics: once the target dominates, cost
  becomes proportional to it. **The chord exponent over the whole range, 0.635, therefore
  understates the real pass and must not be used to extrapolate.** Plan against the linear bound.
  **Where each earlier error came from.** The 0.36–0.48 exponent in D-101 was fitted where the
  constant term dominated. D-102's "affine, linear" came from the sparse-query row, where `F` — which
  is genuinely linear — dominates, so the per-search scan was mistaken for the per-query term. Each
  fitted its own data well and generalised wrongly.
  **Large query size needs no further measurement.** Per-query cost at T = 8.3 M residues is 0.01003
  at Q = 315,266 and 0.00994 at Q = 3,159,223 — within 1%. Beyond roughly 300,000 queries the
  marginal cost is flat, so the real query size is multiplication rather than a regime to explore.
- **Consequence:** the exhaustive **charitable** pass over the whole corpus (Q = 3,159,223,
  T ≈ 288,000 M residues after dropping the nested UniRef90 and UniRef50 tiers) is **11,800
  core-hours at the linear bound, 7,200 at the observed 0.84** — about **$240 to $450** on
  `c6i.2xlarge` spot at $0.16/hour, or $450 to $740 on `r6i.2xlarge` on demand. With the strict
  reading's measured 3.2× multiplier, both readings come to roughly **$1,000 on spot** before the
  hit-cap correction in D-105. **That makes the exhaustive pass affordable, so A1.6 scores every
  record and reports no sampled rate.** D-101's sampled design is withdrawn, and with it the
  clustering, design-effect and denominator problems a corpus sample would have carried.
  Artefacts: `calibration-rate2000-grid.json` and `calibration-rate10-targetsweep.json` under
  `s3://amazebio-corpora-897641797669/corpora/results/a1-6/`.
- **Rejected:** Extrapolating the fitted 0.635 — it is a chord across a range whose slope is still
  increasing, and using it would understate the pass by about three-fold in the project's favour.
  Measuring the large-query, large-target corner directly — proposed, then found unnecessary, since
  query linearity above 300,000 is already measured and the corner is the product of two measured
  quantities. Sampling the corpus to save money — the money is no longer the constraint, and a
  sample cannot support the per-family all-clear statement the exhaustive pass can.

### D-105 — Search parameters for the authoritative pass, fixed before any result is produced
- **Date:** 2026-10-16 14:51 UTC
- **Task:** A1.6
- **Context:** §2 and the working conventions require thresholds and parameters fixed before results
  are inspected, recorded with their timestamp. A1.6 has now run enough calibration that the author
  can see which settings produce which costs, which is precisely the condition under which a
  parameter choice stops being neutral. Fixing them here, with the measurements that justify each.
  The policy threshold itself is **not** in scope: D-015 fixed the three readings and nothing below
  revisits them.
- **Decision — six parameters, each with its measured justification.**

  **1. Aligner: `mmseqs2 18.8cc5c`** (D-093). The source names no version, so there is nothing to
  match; the pin is ours and is reported as such.

  **2. Orientation: seed set as query, corpus as target, sharded.** Re-confirmed rather than
  assumed. D-094 chose it on a measurement taken at default parameters; the obvious objection is
  that the question is per corpus record, so the cap belongs on the corpus side and could be set to
  1. Re-measured with `--max-seqs 1` in the reversed orientation: it ran **over 30 minutes without
  completing** against the forward orientation's **503 seconds** on identical data. The forward
  orientation stands.

  **3. Sensitivity: `-s 5.7`** (the tool's default). Chosen not because it is complete but because
  both alternatives are worse in measured, specific ways, over 15,845 seeds against 2,058,701
  records:
  - `-s 2.0` is 2.08× faster and **loses 5 records at identities 0.737, 0.771, 0.791, 0.836 and
    0.863** — well above the 0.70 cut. That is real recall loss, and it biases toward *understating*
    leakage, which §2 treats as the same failure as overstating it. The 2× saving is refused.
  - `-s 7.5` is 2.66× slower and does **not** dominate: it finds 31 records `-s 5.7` misses and
    loses 51 that `-s 5.7` finds.

  **4. Coverage: `-c 0.8 --cov-mode 1`.** Not a free choice: these are the flags ESM3 states for its
  own clustering, and they are the only parameter guidance anywhere in the source.

  **5. Hit cap: `--max-seqs 100000`, with a saturation guard that fails the run.** The default of 300
  caps hits per *seed*, and at full corpus scale each seed would match on the order of 10⁴–10⁵
  records, so the cap would bind hard — and it truncates worst for the corpus records matching the
  most seeds, which are the most viral-like ones. Measured: capping at 20, a ratio of about 12% of
  true hits per seed, **lost 983 of 18,046 distinct records — 5.4%**. Raising 300 → 5,000 at a scale
  where the cap does not bind cost 1.62× for 0.21% more records, so the correction is not free.
  Because a number alone cannot be defended across shard sizes, the commitment is a **guard**: the
  pass records the maximum hits per seed on every shard, and if any seed reaches the cap the run
  reports its counts as a **lower bound** and refuses to publish them as a result until the cap is
  raised. A silent truncation is the failure mode this guard exists to make impossible.

  **6. Reporting: identity bands, not a single threshold.** 8.07% of hit rows — 14,050 of 174,180 —
  lie between 0.70 and 0.75 identity, and the records on which two sensitivity settings disagree are
  98% inside that band. So the removed set is not sharply defined even given a threshold, and the
  threshold itself was inferred from one sentence about an evaluation set (D-015). Every figure
  therefore ships banded, with the 0.70–0.75 band shown separately from ≥0.75, so a reader can see
  how much of the result balances on the inferred cut.
- **Rejected:** `-s 2.0` for its 2× saving, per the recall measurement above — recorded explicitly
  because the saving was attractive and the author had already seen the price. `-s 7.5` as a gold
  standard — it is not a superset of `-s 5.7`, so calling it one would be false. A bare
  `--max-seqs` number with no guard — the cap's effect depends on the shard size it runs against,
  and an unverified number would reintroduce exactly the silent truncation that this entry exists to
  prevent. Reporting one number at 0.70 — it would hide that an eighth of the evidence sits within
  five points of an inferred boundary.
- **Consequence:** these are fixed. A later task changing any of them changes a published parameter
  and needs its own entry saying so. **A finding falls out of parameter 6 that belongs in the
  write-up rather than only here:** ESM3's filter is not reproducible even in principle from its
  published description, because at the margin its output depends on search parameters the paper
  does not state — and 8% of matches sit at that margin. The unpublished threshold is not a tidy
  omission; it is most of the uncertainty.

### D-106 — The unpublished threshold is verified across every reachable source, and the version of record is the one gap
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** D-015 reads ESM3-open's identity threshold as unpublished and infers 0.70 for the
  charitable reading. Every ESM3 figure in this audit rests on that, and D-105 has just made the
  claim load-bearing for a published parameter set. The claim had been carried forward since
  2026-10-13 without being re-tested, which for the central under-specification finding of the ESM3
  arm is not good enough — §7 assumes a reader who checks exactly this.
- **Decision:** Re-verify by exhaustive machine search rather than recollection, and record the
  result including what remains unchecked.
  **The preprint is confirmed, by sweeping every page for identity, threshold, denylist and select
  agent rather than re-reading the section we knew about.** The filter sentence carries no number:
  "We then remove all sequences from the training set that are detected to align to those in the
  denylists by MMseqs2 at or above a given sequence identity threshold" (p67). Every other 70% in
  the paper belongs to a different procedure — validation purging via `mmseqs easy-search` (p38),
  the worked deduplication example of clustering at 90% then 70% (p38), and the held-out evaluation
  set, "the chains in PDB that were > 70% sequence identity hits to the Viral Denylist" (p69). That
  last is the sentence D-015 infers from, and seeing all of them together strengthens rather than
  weakens the reading: the figure exists in the paper three times and never as the filter's
  parameter.
  **Four sources never previously checked, all negative.** The `evolutionaryscale/esm` repository
  cloned in full and searched — 283 files, no denylist implementation, no MMseqs invocation, no
  identity threshold, the only numeric identity being an unrelated 58% in a GFP tutorial. The
  ESM3 launch post on evolutionaryscale.ai. The Europe PMC record: PMID 39818825, `inPMC` N,
  `isOpenAccess` N, `hasSuppl` N. The HuggingFace model card, re-confirmed.
  **One gap, and it is the one a reviewer checks first.** `S-ESM3-SCIENCE`
  (doi 10.1126/science.ads0018) is still `unretrieved`: both the article and its supplementary file
  return 403. A1.5's earlier check established only that no *correction* is registered against it,
  which is a different question from what it says. Europe PMC reporting no supplementary is that
  publisher-independent index's metadata, not Science's own, so it does not settle the point.
  **A fact recovered by the sweep that was previously recorded as unknown.** The Select Agent
  Denylist's size *is* published: "This process gives us 147K non-viral sequences and 40K additional
  viral sequences" (p67) — 187K in total. A1.6 had been treating that size as unknown and as the
  thing deciding whether an exhaustive select-agent pass was affordable. It is small, so that pass
  is cheap, and 187K is a validation target for the select-agent reconstruction in exactly the way
  ~4M is for the viral one (D-100).
- **Rejected:** Leaving the claim as carried forward from D-015 — it is the ESM3 arm's central
  finding and had not been tested since the day it was written. Treating Europe PMC's `hasSuppl` N
  as proof that no supplementary exists — it is an index's view of a closed-access record, and
  Science hosts its own supplementary files. Inferring from the absence of a threshold in the
  repository that none was ever used — the repository ships inference code, not the training
  pipeline, so its silence is weak evidence and is recorded as such.
- **Consequence:** the wording stands for now, with its scope stated: the threshold is unpublished
  **in every source this project can reach**, which is not the same as unpublished. **This is an open
  item against the Phase A write-up, not just against A1.6.** If the version of record states the
  threshold, D-015 is superseded, the literal reading becomes decidable, the charitable reading's
  0.70 may be wrong, and the ESM3 similarity pass has to be re-run at the stated value — so it must
  be settled before the authoritative pass, not after. The project owner has access and is
  retrieving it; a PDF capture with a sha256 in `sources.json` is what the convention requires,
  since quotes are machine-verified against their source and a pasted excerpt cannot be cited.

### D-107 — The threshold is confirmed unpublished in the version of record, and the omission is selective
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** D-106 left one gap: the Science version of record and its supplementary materials,
  unreachable from this container. The project owner supplied all three files. `S-ESM3-SCIENCE-SM`
  is 101 pages and is the version of record of the appendix the preprint calls A.6.
- **Decision — D-015 stands, now against the version of record rather than a preprint.** The filter
  sentence on p47 of the supplementary materials is **word for word identical to the preprint**:
  "We then remove all sequences from the training set that are detected to align to those in the
  denylists by MMseqs2 at or above a given sequence identity threshold." After peer review, in
  Science, it is still "a given sequence identity threshold". The two occurrences of "identity
  threshold" in 101 pages are this one and the validation purge on p23; the three occurrences of
  70% are the purge, the deduplication worked example, and the held-out evaluation set on p48. The
  charitable reading's 0.70 remains an inference, the literal reading remains `undetermined`, and
  **no ESM3 result needs re-running.**
- **The finding is stronger than "unpublished", and this is the form it should take in the
  write-up.** The authors publish complete MMseqs parameter sets for **four** other procedures in
  the same document:

  | procedure | page | published flags |
  |---|---|---|
  | clustering the training data | 21 | `--kmer-per-seq 100 --cluster-mode 2 --cov-mode 1 -c 0.8 --min-seq-id <seqid>` |
  | validation purge | 23 | `--alignment-mode 3 -c 0.8 --cov-mode 0 --max-seqs 300 --max-accept 3 --start-sens 2 -s 7 --sens-steps 3` |
  | similarity of generations to training set | 29 | `--cov-mode 2 -c 0.8 -s 6.0` |
  | GFP pretraining-exposure search | 45 | `-s 6 -a --max-seqs 10000` |

  The safety filter is the **only** MMseqs procedure in the paper whose parameters are withheld, and
  it is the one the open release's safety case rests on. That is not a stylistic omission: the same
  authors, in the same appendix, state flags four times when they choose to. §A0 asks what
  under-specification costs; here it can be stated precisely — the filter cannot be reproduced from
  the paper while every other search in it can.
- **Three secondary confirmations, all unchanged from the preprint.** The Select Agent Denylist is
  "147K non-viral sequences and 40K additional viral sequences" (p47), confirming the 187K D-106
  recovered. The total removed is 10.6M (p47). The scope list is still "including PDB, UniRef,
  MGnify, and JGI" (p47), so whether OAS, AlphaFoldDB and ESMAtlas were filtered remains unstated.
  "Almost exclusively" is still unquantified.
- **D-032's two under-specification findings survive peer review.** The UniRef tier is still
  unstated — p21 says only "UniRef release 2023 02 is downloaded and parsed from the official
  UniRef website", and Table S3's 70%/90% columns are ESM3's own clustering, not UniRef's tiers.
  **The JGI date still contradicts itself in the version of record**: p21 prose says "July 31st,
  2023" and Table S3 on p76 says "July 30th, 2023". Both were reported to a journal, peer reviewed,
  and published uncorrected.
- **One correction to D-105, in our disfavour.** D-105 justified `-c 0.8 --cov-mode 1` as "the flags
  ESM3 states for its own clustering, the only parameter guidance anywhere in the source". That was
  true of the preprint reading and is now too strong: the paper uses **three different coverage
  modes** for three procedures (1 for clustering, 0 for the purge, 2 for the similarity search), and
  the filter's is unstated. So coverage mode is a three-way reading, not a single piece of guidance,
  and the authoritative pass must report its sensitivity to that choice rather than presenting
  `--cov-mode 1` as recovered.
- **One upgrade to D-094 and D-105, in our favour.** The orientation was chosen on a timing
  measurement; the source states it. "For each denylist, MMseqs was used to query against the full
  set of training databases" (p47) — the denylist is the query and the training databases are the
  target, which is exactly the forward orientation. It is no longer only the fast choice, it is the
  stated one. It also makes D-105's hit-cap guard clearly necessary rather than precautionary: with
  the denylist as query, one seed matches very many corpus records, which is the regime a per-query
  cap truncates.
- **Rejected:** Adopting the validation purge's flags for the filter because they are the closest
  published analogue — tempting, and wrong: the purge runs the opposite way round, with the filtered
  set as query, so its `--max-accept 3` and `--max-seqs 300` are sound for its per-query existence
  test and would truncate badly in the filter's stated orientation. Treating the JGI contradiction
  as a typographical slip now that it has appeared twice — it is a dated snapshot of a set whose
  membership changes, so the day matters, and it has now survived review.
- **Consequence:** D-106's open item is closed. Every ESM3 claim can now cite the version of record;
  `S-ESM3-SCIENCE-SM` is registered as retrieved with its sha256, so quotes against it are
  machine-verified. The Phase A write-up should lead this finding with the four-procedure table
  rather than with the bare word "unpublished".

### D-108 — The pass splits by denylist, not by corpus: the narrow arm exhaustive, the broad arm sampled
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** D-101 made the pass sampled on cost, D-104 made it exhaustive when the cost came
  down, and the question was put to the project owner a third time as a choice between cutting the
  corpus and sampling it. That framing was wrong and the owner rejected it. Cost is linear in the
  size of the **query** set — the reconstructed denylist — as much as in the target, and the two
  denylists differ in size by orders of magnitude. The expensive arm and the high-stakes arm are
  not the same arm, which neither D-101 nor D-104 noticed.
- **Decision — scope by which question each arm answers, and spend accordingly.** A1.6 splits into
  three claims with three different methods:

  | claim | method | why this method |
  |---|---|---|
  | could a filter of this design work at all | already answered, no alignment | A4.3's ceilings — filter scope against corpus composition, and label coverage — cap what any filter built this way achieves regardless of what leaked |
  | did anything on the narrow denylist survive | **exhaustive, whole corpus** | the arm that needs an all-clear rather than a rate, and its query set is small enough that the whole corpus is affordable even pessimistically |
  | how much ordinary viral material survived | **sampled, rate with interval** | an aggregate quantity, where a rate with an interval is the honest form and the project's house style everywhere else |

  The reconstructed 3.16M-cluster viral denylist (D-100) is the expensive query set and buys an
  aggregate number, so it is sampled. The narrow denylist is a small subset of it and buys the
  statement the audit rests on, so it is scored against every record. **Neither the corpus cut nor
  a uniform sample is taken.** D-101's sampled design returns for the broad arm only; D-104's
  exhaustive design stands for the narrow arm only.
- **Consequence:** the two arms report in different forms and must not be pooled. The broad arm's
  output is a survival rate with an interval and no per-record manifest, so A2.* and B3.* consume
  A1.4's manifest shape from the narrow arm and a rate from the broad one — every downstream
  consumer needs telling which it is reading, as D-101 already required. The sampling design for
  the broad arm is not fixed here and is its own entry: the clustering and denominator problems
  D-104 named as reasons against a corpus sample are real and have to be answered before the broad
  arm runs, not after.
- **Still open, and not resolved by this entry:** the handling and reporting rules for the narrow
  arm. Its scope is now settled — exhaustive — but it is the output the §4 reporting limits and the
  X3.1 gate are written for, and what may be said about it, at what granularity, and what waits on
  disclosure is a separate decision the project owner has not yet made. The arm is not built until
  that exists.
- **Rejected:** Cutting the corpus to one component — a proportional saving that gives up coverage
  of a stated component of the training data, for a saving the query-side split makes unnecessary.
  Sampling both arms — cheapest, and it forfeits the all-clear statement on exactly the arm that
  needs it. Keeping both arms exhaustive — defensible, roughly four figures, and the broad arm's
  extra precision buys an aggregate number no downstream task has asked to be per-record.

### D-109 — The broad arm's sampling design: 2.5% by accession hash, three sensitivities, $26 of a $30 ceiling
- **Date:** 2026-10-16
- **Task:** A1.6
- **Context:** D-108 made the broad arm sampled. Two constraints from the project owner: total spend
  of about $30, and a sweep over parameters rather than a single setting, because the filter's own
  parameters are unpublished (D-105, D-107) and a result at one setting would hide how much of it
  rests on our inference. A sweep multiplies cost by the number of cells, so the first question is
  which parameters genuinely need their own search.
- **Decision — three parameters come free, one costs, and that sets the sample size.**

  **Free: the identity threshold.** D-105 parameter 6 already commits to reporting in identity
  bands. One search at the lowest threshold of interest emits every higher threshold by binning
  `fident` from `convertalis`. The entire threshold range — including the literal reading's
  undetermined cut and the charitable 0.70 — is one search, not one per value. This was already
  implied by banded reporting and is stated here because it is the single largest saving available.

  **Free: coverage mode.** D-107 made `--cov-mode` a three-way reading rather than recovered
  guidance. It is recoverable by post-filter: search with coverage filtering relaxed, emit `qcov`
  and `tcov` alongside `fident`, and each of the three modes is a predicate over those two columns
  at `-c 0.8`. One search, three readings. **Not free of risk, and the one unmeasured item here:**
  relaxing the filter admits more rows into alignment and into the output, so it raises both cost
  and the chance the hit cap binds. That cost is folded into the hit-cap measurement already on
  A1.6's list, and the design is provisional on it. If relaxing coverage turns out to cost more than
  running three cov-modes separately, three cells is the fallback and this entry is superseded.

  **Costs: sensitivity.** `-s` cannot be post-filtered — it changes what is found, and D-105 measured
  that the settings are not nested: `-s 7.5` finds 31 records `-s 5.7` misses and loses 51 it finds.
  So the sweep over sensitivity is the real multiplier, and it is the one worth paying for, because
  `-s` is **our** parameter rather than the publisher's, and the sweep is what distinguishes a
  property of the filter from a property of our instrument.

  **The arithmetic, from D-104's fitted model and D-105's measured ratios.** At `c6i.2xlarge` spot,
  $0.16/hour for 8 vCPU, a core-hour is $0.02, so $30 is 1,500 core-hours. D-105's relative costs
  make the three-sensitivity sweep 4.14 cost units against 1.0 for `-s 5.7` alone — 0.48 at `-s 2.0`
  (2.08× faster) and 2.66 at `-s 7.5`. That leaves 362 core-hours per unit. Interpolating `g` from
  D-104's table at Q = 3,159,223 puts a 2.5% target sample at about 313 core-hours per unit, so the
  sweep is **about 1,296 core-hours, $26**, inside the ceiling with headroom for the cap measurement.
  The model is checked against its own endpoint: extrapolating `g` linearly from the 8,546 M-residue
  row to the full 288,000 M-residue target reproduces D-104's 11,800-core-hour figure, so the
  interpolation is being used inside the range it was fitted on.

  **The sample: 2.5% of records, selected by a seeded hash of the accession.** A prefix is not a
  sample, because UniRef is ordered by accession — already recorded in A1.6's state and restated
  because it is the error this design exists to avoid. The hash is deterministic and seeded through
  `amazebio.repro`, so the sample regenerates exactly.
- **The clustering and denominator problems, which D-104 raised as reasons against sampling and
  which D-108 declined to treat as solved.** Both are real and neither is answered by a larger
  sample:
  - **Design effect.** Binomial error at n ≈ 8.8M records is below 0.01% and is not the binding
    constraint. Viral material is clumped by family, so the effective sample size for any
    family-level statement is the number of distinct **families** drawn, not records. The pass
    therefore reports the realised family count alongside every rate, and intervals are computed
    with a design effect estimated from between-family variance rather than as binomial. **A rate
    whose interval is quoted as binomial would be wrong by whatever that factor is**, and quoting it
    is how this objection gets answered rather than dismissed.
  - **Denominator.** UniRef's is exact — 350,950,053 clusters, reconciling with the publisher's own
    count (D-100). MGnify's is not: its granularity is unstated (A1.5), so its denominator carries a
    reading. The two components are therefore **reported separately and never pooled into one rate**,
    which also keeps D-108's prohibition on pooling the two arms from being quietly broken one level
    down.
- **Consequence:** the broad arm ships a table of rates by identity band, by coverage reading and by
  sensitivity, per corpus component, each with a design-effect interval and its realised family
  count — not a single number. The parameter sweep is itself a finding in the shape D-105
  described: if the rate moves materially across settings the paper does not state, then the
  filter's effect is not determined by its published description, and the spread is the result.
- **Rejected:** One cell at the fixed `-s 5.7` and a 10% sample — four times the precision on a
  quantity whose error is already dominated by the design effect rather than by sample size, bought
  by giving up the only check on whether the number is a property of the filter or of our aligner
  settings. A threshold sweep as separate searches — unnecessary, and it would have consumed the
  budget that bought the sensitivity sweep. Pooling UniRef and MGnify into one rate — tidier to
  present and it would launder an unstated granularity into an exact-looking denominator.
  A larger sample inside the same budget by dropping to `-s 2.0` only — D-105 already refused that
  setting on measured recall loss that biases toward understating leakage, and the budget is not a
  reason to reopen it.

### D-110 — Evo 1's version of record is retrieved, and the procedure A2.1 re-executed is word-for-word the published one
- **Date:** 2026-10-17
- **Task:** A2.1 (bearing on A0.1, A0.3, A1.1, A7.1)
- **Context:** Every Phase A result against Evo rests on `policies/specs/evo1-*.yaml`, which are this
  project's machine-readable reading of **the preprint**. The version of record was registered as
  blocked since A1.1 (`S-EVO1-SCIENCE`: science.org 403; Europe PMC holds PMC12057570 but serves
  a reCAPTCHA behind an HTTP 200). A2.1 had re-executed all six rules over both releases and spent
  about twenty hours of compute on a ten-fold deepening on that footing. The project owner asked
  the obvious question — are the rules identical to the ones the developers used — and then
  supplied the four files.
- **Decision:** The version of record is retrieved, registered and checked, and the specs are
  **left unchanged**, because the check found nothing to change. What was verified, by machine
  rather than by eye:
  **The procedure is in the main text, not the supplement** — p12, "OpenGenome datasets". This is
  the opposite of ESM3 (D-106), where the main text deferred everywhere to an appendix, and it is
  why the supplement was not the file that settled this.
  **The procedure paragraph is character-for-character identical to the preprint's Appendix B.2**,
  after normalising whitespace and the hyphenation the PDF extractor inserts, **except for two
  copy-edits**: `High-confidence` is lowercased to `high-confidence`, and an `and` is inserted
  before the last of the twelve orders. Nothing else differs across 1,169 characters.
  **All three enumerations match in both directions.** Every one of the 19 families, 12 orders and
  8 stop taxa in the specs appears in both sources; and every taxon name in either source's
  procedure paragraph — 39 of them — is carried by the specs. No name is in the papers and absent
  from our rules; none is in our rules and absent from the papers. The stated counts, "19
  families" and "12 orders", match the lists they introduce.
  **The one lowercased word is checked against the database rather than the prose.** The rule reads
  IMG/VR's `Confidence` column, and the staged release's own values are `High-confidence`,
  capitalised and hyphenated, in all 9,720 rows of the sample read. So the specs match the
  database token; the version of record's prose does not, and an implementation built from that
  prose with a case-sensitive comparison would retain nothing. Recorded because it is exactly the
  kind of difference that looks like nothing and is not.
  **Scope is confirmed as the literal reading has it.** The three pretraining sources are GTDB
  v214.1, IMG/VR v4 and IMG/PR; the exclusion steps are described for IMG/VR alone, GTDB gets
  species-representative dereplication and IMG/PR one representative per plasmid taxonomic unit,
  and **no viral screening step is described for either**. A4.3's scope finding stands on the
  version of record now, not on the preprint.
  **The data availability statement names the release this audit staged** —
  `huggingface.co/datasets/LongSafari/open-genome`, "including training, validation, and test
  splits" — which is what A1.2 staged and A1.4 and A2.1 read. The A1.1 gate's premise is confirmed
  by the version of record.
  **Table S2 independently confirms A7.1's census.** The supplement publishes the IMG/VR subset as
  2,653,046 genomes, 36,236 M bases, average length 13,658; A7.1 counted 2,653,047 records,
  36,236,025,613 bases, mean 13,658.4. One record apart, and agreeing at published precision
  otherwise. Note the table is **S2 in the version of record and S3 in the preprint**, so D-055's
  citation of "Table S3" resolves only against the preprint.
- **Rejected:** Repointing the specs' rule citations from the preprint to the version of record.
  The preprint is CC-BY and committed, every quotation in the specs is machine-verified against it
  (60 quotations, 0 problems), and the version of record is a subscription article whose
  redistribution here is already flagged for review before publication. Citing the paywalled
  version for text that is identical would buy nothing and cost reproducibility for any reader
  without access. The specs keep the preprint; this entry is what records that the version of
  record agrees.
  Also rejected: treating the two copy-edits as immaterial and not writing them down. One of them
  is a database token.
- **Consequence:** **A2.1's findings stand on the published procedure.** The phage result — that
  what survives in Evo 1's released viral component is overwhelmingly prokaryote-infecting, which
  the policy keeps deliberately — is now anchored in the version of record's own words: the
  component is introduced as "curated prokaryotic viruses", and the host rule's stated purpose is
  "to remove potential eukaryotic viruses". The eukaryotic-family detections in Evo 2 are
  untouched by this check, because that component ships no taxonomy for any rule to act on.
  The write-up may now say "the procedure as published in the version of record" rather than "as
  published in the preprint", which matters for a paper that names laboratories.
  What is still open: Fig. S1B (supplement p4) is the developers' own pie chart of host kingdoms in
  the *filtered* IMG/VR subset. If it shows eukaryotic-host viruses surviving, that is their own
  published figure of leakage, and A2.5 should read it against this project's result rather than
  rediscovering it. The figure is an image, so reading it needs a person or a different tool.

### D-111 — The developers' own figure says the host kingdom is unknown for 89.5% of what their filter kept
- **Date:** 2026-10-17
- **Task:** A2.1 (the finding belongs to A4.1 and A2.5)
- **Context:** `S-EVO1-SCIENCE-SM` p4, Fig. S1, captioned "We excluded viruses that are likely to
  infect eukaryotic hosts (Materials and Methods)", is the developers' own breakdown of the
  corpus their filter produced. D-110 flagged it as needing a person because it is an image. It
  does not: the figure is one 3422x1841 RGB raster, and **the legends print each category's N**,
  so the numbers are read rather than estimated and no wedge was measured.
- **Decision:** The figure's numbers are recorded here as published values, reconciled against
  Table S2 before being believed.
  **Panel A, realm:** Duplodnaviria 2,628,512 (99.075%), Monodnaviria 17,781 (0.670%),
  **Riboviria 6,105** (0.230%), Other 648 (0.024%).
  **Panel B, host kingdom:** **Unknown 2,374,733 (89.510%)**, Bacteria 276,569 (10.425%),
  Archaea 1,744 (0.066%).
  **Both panels sum to exactly 2,653,046**, which is Table S2's IMG/VR count and one record below
  A7.1's census of the staged release. So these describe the whole filtered corpus, not a sample,
  and they are consistent with what this project staged.
  **The Archaea legend is a typo in the paper and the intended value is recoverable.** It prints
  `N = 17,44`. 17,440 would overshoot the corpus by 15,696; 1,744 closes the three categories to
  2,653,046 exactly. Recorded as the publisher's error with the arithmetic that settles it, rather
  than quoted as printed or silently corrected.
- **Rejected:** Measuring the pie wedges by counting pixels per colour, which was the plan before
  the legends turned out to carry N. It would have been a worse number for no reason — a wedge
  angle recovers a share to about a tenth of a degree, while the legend gives the count exactly.
  Also rejected: leaving this for A4.1 to rediscover. It sits on page 4 of a 60 MB subscription
  PDF that the audit could not retrieve at all until today.
- **Consequence:** **A4.1's question is partly answered by the developers themselves.** The rule
  that was supposed to remove eukaryotic viruses keeps "only sequences whose assigned taxonomic
  classification was found within a prokaryotic host at least twice" — and their own figure says
  the host kingdom is **unknown for 89.5% of the records that survived it**. Whatever that rule
  did, it did not establish a prokaryotic host for nine records in ten. A4.1 should treat this as
  the published figure to reconcile against, and say so.
  **A2.5 gets a target with a count.** 6,105 Riboviria survived, and `r:Riboviria` is one of the
  eight stop taxa the unspecificity rule names. Some are genuinely phage — A2.1 detected
  Leviviricetes in its own sample — so this is a population to audit record by record, not a
  leakage claim, and now it has a size.
  **A2.1 is unaffected.** Its figures stand as reported; this entry adds context from the primary
  source rather than changing a number. The 24,534 non-Duplodnaviria survivors (0.92%) are the
  obvious place for the structural and problem-taxa detectors to look first.

### D-112 — A2.4's geNomad is the audit's instrument, and it is pinned apart from A4.2's object of study
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** `feature.genomad` already exists and already works: geNomad 1.1.0 against marker
  database v1.1, with mmseqs2 13.45111, numpy 1.23 and Python 3.10 pinned around it to make a
  2022 tool runnable in 2026. A2.4 needs geNomad too, and reusing that environment is the obvious
  move — it is installed, it is pinned, and A4.2 has already measured how it errs. But the two
  tasks are using the tool for opposite purposes. A4.2 pins 1.1.0 because it is *benchmarking the
  version IMG/VR's own labels came out of*: there, geNomad is the object of study, and any other
  version would be benchmarking a tool the filter cannot have used (D-085, D-096). A2.4 is using
  geNomad as the audit's *instrument*, and `DESIGN.md` §A2 opens by ruling exactly this out: "The
  filter uses taxonomy; the audit must not, or it will reproduce the filter's own blind spots."
  Detecting proviruses with the same 2022 build against the same 2022 markers is that failure in
  its sharpest available form. An integrated element whose markers were absent from the v1.1
  database is invisible to the filter's labelling *and* to the audit's detection, and A2.4 would
  report its own blind spot as an absence of prophage — a false null, in the one direction
  `AGENTS.md` says the pipeline may never be designed to favour.
- **Decision:** Two pins, for two roles, in two solve groups that are not to be unified.
  `feature.genomad` keeps geNomad 1.1.0 and remains A4.2's alone. A2.4 runs `feature.proviruses`:
  **geNomad 1.12.0 against marker database v1.9**.
  1.12.0 rather than 1.13.0, which is the newest build on bioconda but was published three days
  before this pin and which the publisher's own `releases.txt` does not yet pair with any marker
  database. Database v1.9 with package 1.12 is the newest pairing the publisher attests, and the
  package/database pairing is part of the pin rather than a detail around it — the residual gap
  D-085 recorded for A4.2 is precisely a pairing that had to be inferred, and there is no reason
  to manufacture a second one when an attested pairing is available.
- **Rejected:** Running A2.4 on 1.1.0 for consistency with A4.2. Consistency between a benchmark's
  subject and an audit's instrument is not a virtue; it is the confound, and §A2 names it.
  Pinning 1.13.0 as simply the newest. `AGENTS.md` requires results to regenerate from pinned
  inputs, and an unattested package/database pairing is a guess wearing a version number.
  Carrying A4.2's measured misassignment rate across as A2.4's error term. It was measured on
  `genomad annotate`'s taxonomy step at 1.1.0; A2.4 runs `find-proviruses` at 1.12.0. Different
  module, different version, different failure mode — A2.4 characterises its own error through the
  concordance criterion (D-114) instead of inheriting a number that does not apply.
- **Consequence:** geNomad appears in this repository twice, at two versions, and that looks like
  an oversight unless the reason is written down — which is what this entry is for. Nothing in
  A4.2 changes. A2.4's figures and A4.2's figures are **not comparable as statements about
  geNomad**: one is a 2022 tool under test, the other a 2026 tool doing the testing. Any write-up
  touching both says so.

### D-113 — A2.4 establishes where the element is; the family identity comes from A2.1's registries
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** The frozen detection schema is family-keyed — `amazebio.survival.Detection`
  requires `family_id`, `registry` and `registry_version`, and refuses an id outside the pinned
  universe — because family-level survival is `DESIGN.md` §A3's headline and D-022 froze it. A
  provirus call carries no family. `genomad find-proviruses` returns an interval inside a host
  contig with a score; the only family-like label it offers is the marker-consensus taxonomy, and
  that is taxonomy — the one input §A2 says the audit must not rest on, and the one A4.2 measured
  failing to place 36% of the genomes the denylist targets. So A2.4 has an instrument that answers
  a different question from the one the schema asks.
- **Decision:** Split localisation from identity, and take each from the method that can support
  it.
  **Where** comes from the provirus finders. geNomad (and VIBRANT, D-114) say which surviving
  bacterial records carry an integrated element and over what coordinates. This, and only this, is
  what licenses `element_kind = PROPHAGE` — the kind D-079 explicitly reserved for A2.4 to
  establish rather than for A2.1 to guess.
  **Which family** comes from the registries A2.1 already pinned: Pfam 38.2's viral selection and
  RVDB-prot 32.0 (D-075), searched over the proteins falling inside the delineated interval, at
  **D-076's thresholds unchanged**.
  Detections are emitted with `detector: provirus-genomad`, distinct from A2.1's `profile-hmmer`,
  so `metrics/detections.md`'s no-pooling rule keeps the two separable in A3.2.
- **Rejected:** Keying on geNomad's own taxonomic assignment, with the pinned ICTV VMR as the
  registry. It is the path of least resistance — `amazebio.ictv` is already there and already
  pinned — and it would make the audit's family axis a function of the same marker-consensus
  taxonomy whose error rate A4.2 exists to measure. §A2 forbids it in its first sentence.
  Emitting provirus calls with no family and leaving A3.2 to cope. `metrics/survival.md` is frozen
  and the schema does not permit it; a detector that cannot meet the contract is a reason to
  change the contract deliberately, not to route around it.
  Loosening D-076's thresholds on the grounds that prophage proteins are diverged and will score
  lower. A threshold that differs between two detectors makes their survival figures
  incomparable, and comparing them is the whole of A3.2.
- **Consequence:** Thresholds and registries are identical to A2.1's, so an A2.4 table and an A2.1
  table differ only in route, element kind and the records searched — A3.2's cross-tabulation is a
  join rather than a reconciliation.
  The search loop is A2.1's, so it moves out of `tools/detect_profiles.py` and into the library
  for both tools to call. That is a refactor of a `done` task's code, recorded here as one; it
  changes no threshold, no registry and no output.
  **A2.4's survival figure is survival inside delineated proviruses, not inside GTDB genomes at
  large.** A viral-family protein sitting in a bacterial genome outside any provirus call is not
  counted. That is deliberate and it is a lower bound in the same direction as the sampling one:
  the alternative is an unbounded claim about every viral-looking gene in a prokaryotic genome,
  which is a different question and not this task's.

### D-114 — The concordance criterion, fixed before any call is looked at
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** A2.4's Done-when requires two-tool concordance "measured on a documented sample",
  and §A2 names geNomad, VIBRANT and CheckV. `AGENTS.md` requires the analysis spec fixed before
  results are inspected, and an agreement threshold chosen after the overlap distribution is in
  hand is not a criterion, it is a result selected to be reportable.
- **Decision:** **VIBRANT 1.2.1** is the second tool, in `feature.vibrant`. Its mechanism is
  independent of geNomad's in the way the criterion needs: HMM scoring against KEGG, Pfam and VOG
  with a metabolic-signature rule, against geNomad's marker consensus plus neural classifier.
  The criterion, fixed here:
  **Record level.** Every record in the concordance subsample is geNomad-positive, VIBRANT-positive,
  both or neither. Reported as a 2x2 with Cohen's kappa and its 95% interval, per the house rule
  that no point estimate ships without one.
  **Interval level.** Two calls on the same record agree when their **reciprocal overlap is at
  least 0.5** — each interval covers at least half of the other. Fixed at 0.5 now, not tuned later.
  **The sample.** The concordance subsample is the *same* hash under the *same* seed 20261015 at
  one tenth the main rate, so it is nested inside the main sample, declarable in advance, and
  checkable per record afterwards (D-078).
  **Disagreement is reported by direction** — geNomad-only and VIBRANT-only counted separately,
  never pooled into a single disagreement rate, and never resolved by preferring a tool.
- **Rejected:** CheckV as the second tool. Its contamination module trims host flanks off sequences
  that have *already* been called viral; it is not a prophage finder over host genomes, so it
  cannot disagree with geNomad about whether a genome carries one. It would produce a concordance
  number that measures nothing.
  Taking concordance as a filter — keeping only the calls both tools make. It reads as rigour and
  it is the opposite: it converts disagreement between instruments into a quiet reduction in the
  headline, in the direction that makes the filter under audit look better. `AGENTS.md` forbids
  designing any part of the pipeline so a null is harder to see.
  Choosing the overlap threshold once the distribution is visible.
- **Consequence:** The headline comes from geNomad alone and VIBRANT measures how far that headline
  depends on the instrument. The kappa travels with the headline wherever it is reported; a
  prophage survival figure quoted without it is quoting one tool's opinion as a measurement.

### D-115 — A2.4 samples genomes by the same hash, and what that supports is a lower bound
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** The bacterial target is OpenGenome2's GTDB v220 component: 109 GB staged across
  four tar archives. `genomad annotate` plus `find-proviruses` over all of it is not something the
  session container does, and the cost is not yet measured. The sampling *design*, though, has to
  be fixed before any output exists, and D-078 already settled the shape for A2.1.
- **Decision:** A2.4 samples by the same deterministic hash of the record identifier, under the
  **same seed 20261015**, with nested rates — so a deeper pass is a superset of a shallower one
  and re-searches nothing. `estimate_kind` is `lower_bound` for every sampled table, with the same
  reading A2.1's carries: a family detected is detected; a family absent may survive in the
  records not read.
  The **rate** is deliberately not fixed here. It is set by a calibration that measures the
  per-genome cost in region, the way D-104 set A1.6's, and it is recorded in its own entry when it
  has a number behind it rather than guessed now.
  **The sampling unit is the genome record, and that is a declared limitation, not a neutral
  choice.** GTDB is species-clustered and the sequenced genomes are heavily unequal across
  species, so a uniform sample over records over-represents the organisms the world sequences
  most. A2.4 reports the record-level rate as what it is and does not reweight to a species
  denominator it cannot defend.
- **Rejected:** A new seed. Sharing 20261015 with A2.1 is what makes "was this record in both
  samples" answerable without storing either list.
  Taking a prefix of each archive instead of a hash sample. A1.6 learned this one the expensive
  way (D-101): the archives are ordered, so a prefix is not a sample.
  Fixing a rate now so the design looks complete. A rate chosen before the cost is measured is
  either unaffordable or needlessly shallow, and either way it would be revised after the fact,
  which is what pre-registration exists to prevent.
- **Consequence:** A2.4's family-level survival is a lower bound twice over — once from the record
  sample, once from counting only inside delineated proviruses (D-113) — and both directions are
  the same direction. If A2.4 reports that viral families survive in bacterial genomes the filter
  never examined, the true figure is at least that. A null from A2.4 is correspondingly weak and
  must be reported as weak.

### D-116 — A2.4 answers for Evo 2's bacterial component only, and does not substitute it for Evo 1's
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** `amazebio.opengenome` lists Evo 1's prokaryotic component, `stage1_gtdb`, as not
  staged, with the reason "130 GB, and OpenGenome2's GTDB component supersedes it for A2.4". Read
  at staging time that was a storage decision. Read now, as A2.4's scope, it is something else: it
  says A2.4's result will be a statement about one of the two corpora under audit, and the word
  "supersedes" invites the substitution of Evo 2's bacterial genomes for Evo 1's.
- **Decision:** A2.4 searches `gtdb` for the `opengenome2` release and **nothing for `opengenome`**.
  Evo 2's GTDB component is not treated as a proxy for Evo 1's. Every `opengenome` manifest gets a
  table with `estimate_kind: not_searched` and the reason on the source row — the convention
  `metrics/detections.md` fixed for exactly this, so that a structural zero is never read as a
  measured one. Whether to stage Evo 1's 130 GB prokaryotic component is a spend decision for the
  project owner, and it is put to them rather than settled inside this task.
- **Rejected:** Substituting Evo 2's GTDB for Evo 1's. The two releases pin different GTDB
  versions and Phase A exists to measure the difference between releases, not to average it away.
  `AGENTS.md` names the quiet proxy substitution as the failure mode A2.1 already committed once,
  and `DESIGN.md` §B1 step 0 forbids it outright.
  Reporting the `opengenome` tables as zero prophage detections. They would be arithmetically
  correct and completely misleading: a zero by construction is not evidence of absence, and this
  is the §A3 headline it would be feeding.
  Quietly omitting the `opengenome` manifests from A2.4's output, which is what would make the gap
  invisible — the same reasoning D-080 applied to A2.1's unsearched components.
- **Consequence:** **Phase A's prophage route is measured on Evo 2 and not on Evo 1 unless the
  owner buys the staging.** That is a coverage gap in a headline route and it belongs in the write-up
  as one, not in a footnote. A3.2 reads the `not_searched` tables and must not pool them with the
  searched ones.

### D-117 — A first calibration puts a full GTDB census in the same range as A1.6's pass, and the rate still waits on a better one
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-115 fixed A2.4's sampling *design* and deliberately left the *rate* open, to be
  set by a measured cost rather than guessed. This is the first measurement. It is also the point
  at which A2.1's history is worth remembering: D-078 assumed a census was arithmetically out of
  reach and sampled accordingly, and D-098 then found the figure wrong by a factor of thirty and
  a census affordable after all. A cost assumed is a design decision taken by accident.
- **Decision:** Record the measurement, and **do not fix the rate on it**.
  **Measured.** geNomad 1.12.0 against marker database v1.9, on *E. coli* K-12 MG1655
  (`NC_000913.3`, 4,641,652 bp), 4 vCPU, `--splits 8`: `annotate` 12 min 17 s CPU in 3 min 42 s
  wall, `find-proviruses` 22 s CPU in 20 s wall. **12.65 core-minutes for the genome, 2.73
  core-minutes per Mb.** Annotation is 97% of it; the provirus step itself is close to free, so
  the cost of this task is the cost of calling and marker-searching genes.
  **Extrapolated.** OpenGenome2's staged GTDB v220 component is 109 GB across four tar archives,
  so of order 107,000 Mbp, giving **about 4,900 core-hours for a full census**. That is the same
  order as A1.6's authoritative charitable pass (D-104), which the owner priced at $240-450 on
  spot. A census is therefore a real option and not an arithmetic impossibility, and D-115's
  sampled design is a choice about spend rather than a constraint.
  **Why the rate is still open.** This is *one* genome, and not a typical one. `annotate`'s cost
  tracks gene count rather than bases, and *E. coli* K-12 is a gene-dense, well-behaved, complete
  genome — GTDB v220 is mostly draft assemblies in many contigs, with a size distribution running
  from ~0.6 Mb symbionts to ~15 Mb myxobacteria. Per-Mb cost on fragmented assemblies is not
  assumed to match. The run also happened in the session container rather than in region.
  So the rate is fixed by a **size-stratified in-region calibration**, in its own entry, and this
  entry exists to stop the single-genome figure being quoted as if it were that.
- **Rejected:** Fixing a rate on this number because it is the number in hand. It is a
  one-genome extrapolation across two orders of magnitude of assembly quality.
  Declaring the census affordable and planning it. The figure supports "same order as a pass the
  owner has already priced", which is a reason to ask, not a reason to launch — and `AGENTS.md`
  is explicit that an instance costs money and that the question goes to the owner first.
  Discarding the measurement as too weak to record. It is the difference between a census being
  conceivable and not, and leaving it unrecorded is how D-078's assumption survived for weeks.
- **Consequence:** The spend question goes to the project owner with a range attached rather than
  as an open-ended ask. Whichever way it is answered, `estimate_kind` carries it: `population` for
  a census, `lower_bound` for a sample, and `metrics/detections.md` already forbids A3.2 pooling
  the two.

### D-118 — The sampled pass runs in nested bands inside a $20 ceiling, and its first band is the calibration
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-117 put a full GTDB census at about 4,900 core-hours and left the rate open,
  pending a size-stratified in-region calibration. Put to the project owner with that range, the
  answer was a **sampled pass only, about $10-20**, and no separately funded calibration. So the
  rate has to be fixed without the measurement D-117 asked for, and the one figure in hand comes
  from a single complete, gene-dense genome that GTDB's draft assemblies are not like.
- **Decision:** Do not fix one rate. Run the sample in **nested bands**, and let the first band be
  the calibration the budget did not buy.
  Membership is already nested by construction — D-078's hash sampler makes a deeper rate a strict
  superset of a shallower one, so a deepening re-reads nothing — and A2.1 has run exactly this
  shape before (D-099). The pass therefore starts at **2.5%**, matching A1.6's broad arm (D-109),
  measures realized per-genome cost on that band against the 2.73 core-minutes per Mb D-117
  extrapolated from, and deepens in further nested bands while the $20 ceiling allows.
  `estimate_kind` is `lower_bound` throughout and never `population`, whatever depth is reached.
  The **realized** rate is recorded per source, not the intended one, so a run stopped by the
  ceiling reports the sample it actually read — `metrics/detections.md` already requires this.
- **Rejected:** Fixing a single rate from D-117's figure and running it once. It is a one-genome
  extrapolation across two orders of magnitude of assembly quality; a rate set from it is either
  over the ceiling or needlessly shallow, and banding costs nothing to avoid both.
  Spending part of the $20 on a standalone calibration. The first band is a calibration that also
  produces results, and a separate one would buy the same number for a share of the budget.
  Reporting the deepest band alone. Every band's realized cost is kept, because the per-Mb figure
  on real draft assemblies is the number the next task needs and this is the only pass that will
  measure it.
- **Consequence:** A2.4's prophage figures are a lower bound and are reported as one. If the pass
  finds viral families surviving in bacterial genomes the filter never examined, the true figure
  is at least that; if it finds none, that is weak evidence of absence and must be written as
  weak. The nested design leaves the census of D-117 available later at no wasted work, should
  the result make it worth buying.

### D-119 — Evo 1's prokaryotic component is staged, so the prophage route covers both corpora
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-116 recorded that Evo 1's prokaryotic component, `stage1_gtdb`, is not staged —
  130 GB, marked at staging time as superseded by OpenGenome2's GTDB — and refused to substitute
  Evo 2's bacterial genomes for it, because Phase A exists to measure the difference between
  releases rather than to average it away. That left Phase A's prophage route measured on one of
  the two corpora under audit, which D-116 flagged as a coverage gap in a headline route and put
  to the project owner as a spend decision.
- **Decision:** The owner approved staging it. `stage1_gtdb` moves into the staging tier —
  `Component.tier1` becomes true, which is the flag that records what the owner has approved
  (D-031) — and A2.4 runs over both releases' bacterial components.
  D-116's `not_searched` outcome for the `opengenome` manifests **stands until the staging
  completes and verifies**, and is withdrawn only then. A table claiming coverage of a component
  that is still uploading would be the same error in a new place.
- **Rejected:** Leaving it unstaged and reporting the gap. It is the defensible cheap option and
  the owner declined it; a headline route measured on half the audit's subjects is a weak result
  to publish when the remedy is storage.
  Deciding after seeing Evo 2's result. It makes the scope of one release's pass contingent on
  another's outcome, which is the shape of thing the pre-registration discipline exists to prevent.
- **Consequence:** The two releases pin **different GTDB releases** — Evo 2's is v220, Evo 1's is
  not yet identified from its own metadata — so the comparison is between two filters applied to
  two different snapshots of the same database, and that difference travels with the result rather
  than being normalised away. Identifying Evo 1's GTDB release from the staged tree is part of this
  staging and belongs in its own entry if it turns out to be unrecoverable, as §A0 requires.

### D-120 — Spot is unavailable in this account, so every spot-priced figure in A1.6 is a price we cannot pay
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-110 and renumbered to D-120 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-104 priced the exhaustive charitable pass at $240-450 and D-109 priced the broad
  arm's three-sensitivity sweep at $26 against a $30 ceiling. Both are **spot** figures, and the
  launcher gained spot support on the strength of them. The first spot launch was refused.
- **What was measured.** `RunInstances` with `InstanceMarketOptions` returns
  `AuthFailure.ServiceLinkedRoleCreationNotPermitted`: a spot request needs the
  `AWSServiceRoleForEC2Spot` service-linked role, which EC2 creates on the caller's behalf on first
  use through `iam:CreateServiceLinkedRole`. `AGENTS.md` records that `iam:*` is denied in this
  account, and it is denied for this too — the role cannot be created, inspected or listed from
  here. Nothing launched and nothing was billed.
  **A dry run does not find this.** The same request authorized as `DryRunOperation` a minute
  earlier. `DryRun` never attempts the service-linked role, so this is a second instance of
  `AGENTS.md`'s rule that a dry run authorizes but does not execute — and the first one it names
  that cannot be caught by any check inside the instance's own script either, because the refusal
  happens before there is an instance.
- **Decision:** treat spot as unavailable rather than as a flag to retry, and keep the support in
  the launcher. The code is correct and one IAM action makes it work, so removing it would discard
  the cheaper option; what changes is that nothing may be *planned* against a spot price until that
  action exists. The launcher classifies this refusal apart from a capacity refusal, because a
  capacity refusal is a retry and this one cannot be retried into working.
- **The price consequence, which is the substance of this entry.** On-demand is roughly 3-4x spot
  for the permitted instance types. So D-109's $26 sweep is about $90-100 on demand and **does not
  fit the $30 ceiling it was designed against**, and D-104's $240-450 exhaustive charitable pass is
  roughly $1,000-1,500. The cap and coverage measurement is about $1 on demand and is unaffected in
  substance.
- **Rejected:** Re-pricing the broad arm's sample downward to fit $30 on demand — that would be
  about 0.7% of the corpus, and it trades the measurement's precision against an account
  configuration rather than against anything about the audit; it is also a decision the project
  owner should make rather than one taken quietly inside a task. Dropping the sensitivity sweep to
  one cell to fit — D-109 already rejected that for the reason that the sweep is the only check on
  whether the number is a property of the filter or of our aligner settings, and an IAM limitation
  is not a reason to reopen it. Bidding under the going rate with `MaxPrice` — unrelated to this
  refusal, and already rejected in the launcher's own notes.
- **Consequence:** **the broad arm's budget is back with the project owner**, with three real
  options: have someone with IAM permissions create `AWSServiceRoleForEC2Spot` once and run D-109's
  design as priced; raise the ceiling to about $100 and run the same design on demand; or shrink the
  sample and accept a wider interval. Until one is chosen the pass does not run. Every figure in
  D-104 and D-109 keeps its number but gains the qualifier **"on spot, which this account cannot
  currently request"**, and any future entry pricing work in this repo states which market it
  assumes.
### D-121 — The spot service-linked role is to be created, so A1.6's passes run at the prices they were designed against
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-111 and renumbered to D-121 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-120 established that spot is refused in this account and put three options to the
  project owner: create the service-linked role, raise the ceiling to about $100 for the same
  design on demand, or shrink the sample to fit $30 on demand.
- **Decision (project owner):** create `AWSServiceRoleForEC2Spot`. D-109's design runs unchanged
  and at the price it was designed against — about $26 of the $30 ceiling for the broad arm's
  2.5% sample across three sensitivities, and the cap and coverage measurement for well under a
  dollar rather than about $1 on demand.
- **Why this is the better of the three rather than merely the cheapest.** The other two both pay
  for the account's configuration with something that belongs to the audit. Raising the ceiling
  spends about $75 more for an identical measurement, which is defensible but buys nothing.
  Shrinking the sample to 0.7% looks like the frugal option and is the expensive one: the binding
  constraint on this estimate is the realised family count, not the record count (D-109), so a
  smaller sample widens the interval on every family-level statement in exchange for an IAM
  limitation. An audit should not have a number in it whose precision was set by a missing role.
- **Rejected:** the two priced alternatives above, for those reasons. Also rejected: running the
  cap and coverage measurement on demand first to avoid waiting — it is about $1, so the saving is
  real but trivial, and it would mean the first authoritative measurement in this arm was taken
  under a configuration the rest of the arm does not share.
- **Consequence:** A1.6's remaining work is **blocked on one external action** — someone with IAM
  permissions creating that role once. Nothing in the repo changes and no code is waiting: the
  launcher's spot path is already written and tested, and D-120's refusal classifier is what will
  report it if the role is still absent. On confirmation the order is: the cap and coverage
  measurement on spot, then the broad arm's sampled pass. `iam:*` is denied here, so this project
  cannot verify the role exists except by attempting a launch, which is also the launch it wants —
  so the attempt is the check.
### D-122 — D-109's $26 is a search price, not a run price: the pass is dozens of launches and each one currently re-reads the corpus
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-112 and renumbered to D-122 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-109 priced the broad arm's sweep at 1,296 core-hours, $26 of a $30 ceiling, from
  D-104's fitted model. That model prices **searches**. Neither entry converted the figure into
  launches, and the conversion is where the money is.
- **The arithmetic, which is all from D-109's own numbers.** 1,296 core-hours on an 8-vCPU instance
  is **162 instance-hours — 6.8 days**. The instance shutdown timer this task launches with is
  260 minutes, and `ec2:ModifyInstanceAttribute` is denied so it cannot be extended after launch.
  So the broad arm was never one run; it is dozens, and `tools/esm3_calibrate.py` rebuilds the
  target shards from the full 295 GB corpus on **every** run, because it has no way to load them.
  The corpus pass is therefore paid once per launch rather than once.
- **What the corpus pass actually costs, measured today.** The in-flight cap measurement is past
  2.5 hours on a pass that took 53 minutes in the rate-2000 run it was estimated from. The cause is
  not the corpus read, which is the same 295 GB either way, but the sample: at rate 50 the pass
  keeps 40x more records, and every one travels from a worker process to the parent over IPC and is
  written out by that single parent. **The corpus pass is sample-write-bound, not read-bound**, so a
  timing taken at one sample rate does not transfer to another. The authoritative pass samples
  denser still at rate 40, so 2.5-3 hours is the planning figure.
- **The consequence, as a table.** At a 4.33-hour run cap, 2.5-3 hours of each run is corpus pass
  and only ~1.6 hours is search, so 1,296 core-hours needs roughly **95 launches and about $66** —
  2.5x the quoted figure and over the ceiling it was designed against. Longer runs dilute the
  overhead: a 12-hour cap is roughly 15 launches and about $30. Staging the shards removes it
  entirely: one corpus pass ever, then launches that are pure search, which returns the figure to
  about $27.
- **Decision:** **stage the sampled target shards to object storage once, and have the search runs
  load them**, in the way the viral seed FASTA is already staged. D-109's $26 stands only with that
  change; without it the entry's figure is wrong by 2.5x and the ceiling is breached.
- **Why staging rather than simply longer runs, which is the cheaper-looking alternative.** Longer
  runs reduce the overhead but raise the exposure: a spot reclaim loses everything the run has done,
  and the corpus pass is the most expensive thing to lose. The first in-region run established this
  the hard way — 53 minutes of completed corpus pass went with the searches when it was cut short.
  With shards staged, a reclaim costs only the search in flight. The two are not exclusive and
  staging is what makes long runs safe rather than merely cheaper.
- **Rejected:** Leaving D-109's figure unqualified and reporting the overrun afterwards — the
  ceiling was a constraint from the project owner, and a 2.5x breach discovered in the invoice is
  not a measurement problem but a reporting failure. Re-reading the corpus per run as a way to avoid
  writing staging code — it is the most expensive possible way to save an afternoon. Sizing a bigger
  instance to shorten the pass — `AGENTS.md` is explicit that a memory or CPU bound is not the test
  for launching bigger, and the pass is bound by a single parent process writing samples, which more
  cores do not help.
- **Consequence:** staging is now a prerequisite for the broad arm's pass, not an optimisation.
  **Every future entry pricing work in this repo states whether its figure is core-hours of compute
  or the cost of the runs that deliver them**, since this entry exists because those two were
  conflated. The cap measurement in flight is unaffected in substance: it is one run, its overhead
  is one corpus pass, and the ratios it measures do not depend on how the pass is scheduled.
### D-123 — Correction to D-122: the corpus pass is not sample-write-bound, and the overrun is ~10% rather than 2.5x
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-113 and renumbered to D-123 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-122 explained a corpus pass running long by claiming it was sample-write-bound —
  that keeping 40x more records at rate 50 than at rate 2000 moved the cost, because every sampled
  record crosses from a worker to a single parent that writes it. That claim was reasoning from the
  code's shape rather than from a measurement, and the measurements were already in the repo's own
  preserved artefacts. They refute it.
- **What the artefacts say.** From the two preserved calibration grids, both over UniRef100 2023_02
  at 350,950,053 clusters:
  - rate 2000 — 175,010 sampled clusters, 0.066 G residues — corpus pass **3,070 s (51.2 min)**;
  - rate 10 — 35,092,626 sampled clusters, 13.351 G residues — corpus pass **3,267 s (54.4 min)**.
  **A 200-fold increase in sampled records costs 3 minutes, about 6%.** The pass is bound by the
  read, decompress and parse chain and lands near 52 minutes at any sample rate in this range. This
  is consistent with what was already recorded in `esm3_calibrate.py`'s own `--workers` note:
  decompression runs at 218 MB/s against 43.6 MB/s for the whole pass single-threaded, so parsing is
  the bottleneck and the workers are what spread it. Sample writing never entered it.
- **Correction to D-122's figures.** With a 52-minute pass rather than 2.5-3 hours, a 4.33-hour run
  spends 0.87 h on the pass and 3.46 h searching, which is 27.7 search core-hours per run. 1,296
  core-hours therefore needs about **47 launches and about $33** unstaged, against about **38
  launches and about $26.5** staged. So the overrun against the $30 ceiling is roughly **10%, not
  2.5x**, and the $66 in D-122 is wrong.
- **What survives in D-122, and why.** Its decision stands: stage the sampled shards once rather
  than rebuild them per launch. The reason is now mainly robustness rather than price — a spot
  reclaim destroys a 52-minute corpus pass along with the searches it was feeding, which is exactly
  what happened to the first in-region run — with the ~$6.50 as a secondary benefit. Its rule
  stands too, and this entry is an instance of why: a price must say whether it is core-hours of
  compute or the cost of the runs delivering them.
- **What this means for the run in flight.** It is not merely slow. Its pass was due at about 52
  minutes and it is past 2.5 hours with nothing published, and rate 50 sits between two rates that
  both completed in 52 minutes, so the sample rate cannot explain it. The only difference from
  every pass that has completed is the instance type: `m6i.2xlarge` here against `r6i.2xlarge` for
  all three successful passes, taken because spot capacity for `r6i.2xlarge` was refused. That is a
  hypothesis and not a finding — with `cloudwatch:GetMetricStatistics`,
  `ec2:GetConsoleScreenshot`, SSH and SSM all denied there is no way to confirm it from here, which
  is itself the reason the heartbeat was added.
- **Rejected:** Editing D-122 in place — the log is append-only and a wrong figure that was briefly
  load-bearing should stay visible with its correction next to it, not be quietly removed. Treating
  the slow run as evidence for the sample-write hypothesis — it is one run on an instance type that
  has never completed a pass here, against three completed passes that directly contradict it.
- **Consequence:** **a timing claim in this task cites the artefact it came from.** Both numbers in
  this entry were sitting in object storage while D-122 was being written, and the entry would not
  have been wrong if they had been read first.
### D-124 — The three coverage readings come from two aligner-filtered searches, exactly; D-109's relaxed search is withdrawn
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-114 and renumbered to D-124 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-109 bought the three `--cov-mode` readings of D-107 for the price of one search by
  relaxing coverage filtering and re-imposing it on the emitted `qcov`/`tcov` columns. It flagged
  one risk honestly — relaxing admits more rows, so it costs more and may make the hit cap bind —
  and named three separate cells as the fallback. Two things then landed against it. Rehearsing the
  path against the pinned aligner showed the post-filter does **not** reproduce the aligner's own
  `--cov-mode 1` exactly: 138 records against 137, with the post-filtered set a strict superset.
  And D-104's table shows cost is ~99.5% the per-query term at the broad arm's target size, so the
  rows a relaxed search adds are not free in the way "one search instead of three" implied.
- **Decision:** run **two** coverage-filtered searches, `--cov-mode 1` and `--cov-mode 2`, and
  derive all three readings from them. The construction is exact, and the argument is short enough
  to check rather than measure:
  - the mode-1 search returns every pair with `tcov >= c`;
  - reading 0 is `qcov >= c AND tcov >= c`, so **every** mode-0 pair has `tcov >= c` and is
    therefore in the mode-1 results, where the `qcov` column the search already emits identifies
    it. No second pass and no intersection of result sets is needed;
  - reading 1 is the mode-1 result set itself;
  - reading 2 is `qcov >= c` with no constraint on `tcov`, which is **not** a subset of the mode-1
    results, so it needs its own search.
  Implemented as `similarity.SEARCH_READINGS`, which maps each search to the readings it is
  authoritative for, with `RecordLedger.extend_from_search` as the only sanctioned call site. A
  test asserts the two searches reproduce, record for record, what one unfiltered search
  post-filtered three ways would have produced.
- **Why this is better than both of D-109's options.** Against the relaxed search: it is exact
  rather than approximate, and it keeps the aligner's own pruning — under `-c 0.8 --cov-mode 1` a
  target cannot match a seed shorter than 80% of it, which a relaxed search must align to
  discover for itself. Against the three-cell fallback: two cells rather than three.
- **The failure mode this guards.** A `--cov-mode 1` search cannot speak for reading 2, because it
  omits pairs with `qcov >= c` and `tcov < c`. Counting reading 2 from those rows would yield a
  floor presented as a measurement — and a floor biases toward understating leakage, which §2
  treats as the same failure as overstating it. `SEARCH_READINGS` exists so that which search may
  speak for which reading is one decision in one place, and the coverage predicate is still applied
  on top, so a misrouted feed narrows a count rather than inflating it.
- **Rejected:** Keeping the relaxed search and reporting the post-filter's disagreement as a caveat
  — it is avoidable at no extra cost, and a caveat on the central mechanism of the coverage sweep is
  worse than one more search. Taking the post-filter's strict-superset behaviour as safe because it
  errs toward overstating leakage — the direction was measured on 1,200 synthetic records and is not
  a property anything guarantees at corpus scale. Three separate cells per D-109's fallback — two
  suffice, and the third would have been bought by not noticing that mode 0 is recoverable from the
  mode-1 search's own columns.
- **Consequence:** D-109's coverage mechanism is superseded; its sampling design, identity banding,
  sensitivity sweep and interval treatment all stand. **The pending hit-cap measurement shrinks
  accordingly:** its relaxed-coverage half measured a question that no longer exists, so the re-run
  is the hit cap alone, against a staged sample rather than a fresh corpus pass. The project owner's
  standing direction is the cheap, provable efficiencies with sampling retained; this is the first
  of them.
### D-125 — The narrow arm's handling and reporting rules, fixed before the result exists
- **Date:** 2026-10-16
- **Task:** A1.6
- **Numbering:** appended as D-115 and renumbered to D-125 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-108 settled the narrow arm's scope — exhaustive against every corpus record — and
  explicitly left its handling open, because it is the output §4's reporting limits and the X3.1
  gate are written for. The arm was not to be built until this existed. The question had to be
  answered **now** rather than when the result lands: §2 and the working conventions fix analysis
  specs before results are inspected, and an empty result and a non-empty one invite very different
  rules once either is visible. This entry therefore covers both branches in advance.
- **Decision (project owner): report counts aggregated by survival route and homology class, never
  by organism or taxon.** Per-record detail goes to the disclosure package only — Arc Institute,
  EvolutionaryScale and SecureBio under §4 — and not to the preprint, which carries the aggregate
  and a pointer. This follows §4's existing precedent for cost curves, where the regime
  classification publishes by homology class and fold family while per-family curves stay in the
  disclosure package: the narrow arm's manifest is the same kind of object, and it is organism-
  attributable by construction because the denylist was reconstructed from an organism list.
- **Both branches.** An empty result is reported plainly — nothing on the narrow denylist survived,
  with the proxy qualifier A1.1 requires on every ESM3 result. A non-empty result is reported as
  counts by survival route (A3.1's frozen taxonomy) and by homology class, with its interval, and
  nothing finer.
- **Four consequences that follow rather than being separate choices.**
  1. **Where the manifest may live.** `artifacts/` is git-ignored and is where it goes. It is **not**
     committed, because deliverable 7 is a public repo, and it is **not** staged to the corpus
     bucket, which has no `DeleteObject` — a per-record narrow-arm manifest written there could
     never be withdrawn. The disclosure package is assembled separately.
  2. **Downstream inheritance.** D-108 has A2.* and B3.* consuming A1.4's manifest shape from this
     arm. They inherit this rule: their *published* outputs aggregate the same way. A restriction
     that stops at A1.6 while a downstream task republishes the detail is not a restriction.
  3. **Enforced in code, not remembered.** §4's limits are enforced in the harness per the
     non-negotiables. The narrow arm's reporting path emits aggregates; the per-record manifest is
     written only under the git-ignored artefacts path, and the upload helper refuses a narrow-arm
     manifest key. A harness that *could* publish the detail is the thing the non-negotiable
     forbids, independently of whether anyone would.
  4. **Nothing circulates before X3.1**, including the aggregate, per §4's disclosure requirement
     and §7's treatment of the window as substance.
- **Rejected:** A bare count with no breakdown until the window closes — more conservative, and it
  would leave the Phase A write-up unable to characterise what survived, which is the audit's
  actual contribution. The full per-record manifest as the deliverable with only a pointer in the
  preprint — strongest for the three recipients who can act on it, and it makes the preprint's
  central narrow-arm claim unverifiable by a reader. Deferring the non-empty branch until a result
  exists — this is exactly the "fix it before you look" rule, and the asymmetry of the two branches
  is what makes deferring it tempting and wrong.
- **Consequence:** **the narrow arm is unblocked.** What remains before it runs is not the owner's:
  the second seed set is still unbuilt, and two questions gate it, each needing its own entry — how
  the published organism list's names map to taxonomy ids, which the list does not do for you; and
  which version of that list was in force when the filter ran, since the source cites a 2024 access
  date and the retrievable page is live and undated. The reconstruction has a validation target:
  187K sequences, published in the source (D-106).
### D-126 — The narrow arm's exact result is retained, staged and permanent; D-125's storage call is reversed
- **Date:** 2026-10-17
- **Task:** A1.6
- **Numbering:** appended as D-116 and renumbered to D-126 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-125 fixed the narrow arm's reporting rule — counts by survival route and homology
  class, never by organism or taxon — and then drew a storage conclusion from it that went further
  than the rule required: that the per-record manifest lives only under the git-ignored artefacts
  path and is never staged, because an object that cannot be withdrawn is a liability. The project
  owner's clarification is that the **exact** result is to be held privately; only publication is
  restricted.
- **The distinction that was blurred, stated once:** aggregation happens at the **publication**
  boundary, not the computation boundary. The pass scores every record and keeps the per-record
  manifest. This is not merely permitted by the conventions, it is required by three of them —
  "artefacts before prose" means every published number traces to a machine-readable artefact;
  A3.3 must independently reimplement the headline counts, which cannot be done against a count;
  and D-108 has A2.* and B3.* consuming A1.4's manifest shape from this arm. A pipeline that only
  ever emitted aggregates would fail all three, and D-125's storage sentence pointed at exactly
  that pipeline.
- **Decision (project owner): stage the manifest to object storage and accept that it is
  permanent.** The bucket is private, so access is not the issue; the cost is that the copy can
  never be withdrawn, including if the disclosure process later asks for that. That cost is
  accepted deliberately rather than discovered, which is the point of recording it here.
- **Rejected:** Regeneration from pinned inputs as the durable form — the project's definition of
  done already requires exact regeneration and this arm is cheap to re-run, so it was the
  recommendation; rejected because a result that exists only as a recipe is not in hand when
  someone asks for it, and the disclosure package has to be assemblable without a compute run.
  A staged ciphertext with the key held outside the bucket — durable and retractable, and rejected
  as a key-management pattern this project has nowhere else and would have to maintain for one
  artefact.
- **What changes in D-125, precisely.** Its consequence 1 is reversed: the manifest is staged.
  Its consequence 3 moves rather than disappearing — enforcement in code is no longer "the upload
  helper refuses a narrow-arm manifest key", which would now be wrong, but:
  1. the reporting and write-up path emits aggregates only, by survival route and homology class;
  2. the manifest is never committed, because the public repo is deliverable 7;
  3. the manifest's staged key is recorded in the run manifest, so the disclosure package is
     assembled by reference and a later reader knows the exact result exists and where.
  Consequences 2 and 4 of D-125 stand unchanged: downstream published outputs inherit the
  aggregation rule, and nothing circulates before X3.1.
- **The key scheme, fixed before anything is written**, per `AGENTS.md`'s warning that a bucket
  with no `DeleteObject` makes a wrong key permanent and that A1.3 left four unremovable 0-byte
  objects behind: `corpora/results/a1-6/narrow-arm/<release>/<tier>/manifest-<commit>.jsonl`.
  The commit is in the key so that two runs cannot collide — an overwrite in this bucket is not a
  tidy replacement but the irreversible loss of the earlier object, which for this artefact would
  mean destroying a result we had committed to holding.
- **Consequence:** the narrow arm retains its exact output and publishes only aggregates. The
  permanence of the staged copy is a known, accepted limitation and belongs in the disclosure
  conversation at X3.1 rather than being presented as a safeguard.
### D-127 — The lost runs were a short payload and a shutdown that never fired, not the reader or the instance type; D-123's hypotheses are both refuted
- **Date:** 2026-10-17
- **Task:** A1.6
- **Numbering:** appended as D-117 and renumbered to D-127 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-123 recorded two candidate causes for an instance that spent four hours on a
  52-minute corpus pass and published nothing: a degrading S3 read retried without a global bound,
  or the instance type, since the three passes that completed all ran on `r6i.2xlarge` and that was
  the only `m6i.2xlarge` attempt. It named the second as weaker and the first as stronger. **Both
  are refuted.** A second launch failed the same way and its console — still readable, because the
  failure happens during boot — carried the answer: `ImportError: cannot import name 'shardstore'
  from 'amazebio'`.
- **What actually happened, in two faults.**
  1. **The payload was short.** `ec2_similarity.PAYLOAD` lists the files shipped to the instance and
     was maintained by hand. `similarity.py` was added to `esm3_calibrate.py`'s imports on
     2026-10-16 and never added to it; `shardstore.py` followed on 2026-10-17. So the tool died on
     an `ImportError` about 31 seconds in, having read nothing. The 2026-10-16 run used
     `--measure caps`, which is exactly the path that imports `similarity`, so it failed the same
     way — it was never slow, and nothing about rate 50 or the instance type was involved.
  2. **`shutdown -h now` does not fire while the boot-armed timer is pending.** `UserData` arms
     `shutdown -h +N` before anything that can fail, by design, and systemd then already has a
     shutdown scheduled; the immediate one does not replace it. So a script that failed in 31
     seconds sat idle until the +240 minute timer, burning the whole window. From outside — no
     console after boot, no artefact, process alive, status checks ok — that is indistinguishable
     from a four-hour corpus pass, which is why it was diagnosed as one.
- **Decision — fix both, and make the first unrepeatable rather than remembered.**
  `PAYLOAD` now lists every first-party module the shipped tools import, and
  `tests/test_ec2_similarity.py` derives that closure from the source with `ast` and fails if the
  list is short. `UserData` gains a `die` helper that runs `shutdown -c` before
  `shutdown -h now`, with `systemctl --no-block poweroff` and `halt -p` as fallbacks, and every
  exit path goes through it. And the script imports the shipped tool **before** the corpus pass, so
  a short payload costs two seconds rather than an hour and a launch.
- **What this says about the two fixes D-123 motivated.** Neither is withdrawn. The reader's global
  reconnect budget bounds a real unbounded retry loop that remains a bug whether or not it was this
  bug, and `S3RangeRead` had no tests at all before. The heartbeat is what made this diagnosis take
  thirty seconds instead of four hours: its absence from object storage after 30 minutes is what
  prompted looking at the console while the answer was still in it. Both were worth building; the
  entry that motivated them simply had the wrong cause.
- **Rejected:** Leaving D-123 standing as the explanation — it is wrong, it is cited from a commit
  message and from `AGENTS.md`, and a later worker would otherwise plan around a reader fault and an
  instance-type superstition that cost two launches to invent. Blaming the instance type, which was
  tempting twice: both failing runs were `m6i.2xlarge` purely because `r6i.2xlarge` spot capacity was
  refused both times, and the correlation was with the capacity refusal rather than with the machine.
- **Consequence:** the cost of the two lost launches was about $0.75 and most of a day. The general
  lesson is the one `AGENTS.md` already states and this breached from a direction it did not cover:
  a dead man's switch that cannot be superseded turns every fast failure into a full-window
  failure. **Both are now recorded in `AGENTS.md`** — that an immediate shutdown must cancel the
  pending one first, and that the payload is derived and tested rather than listed by hand.
### D-128 — The broad arm runs on one staged shard at 0.3125% with the cap unbound; D-109's 2.5% is superseded
- **Date:** 2026-10-17
- **Task:** A1.6
- **Numbering:** appended as D-118 and renumbered to D-128 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-109 sized the broad arm at 2.5% for $26, from D-104's cost model. The cap
  measurement priced the real thing and the model under-predicts by about 6x, because it was fitted
  with the charitable parameter set's `--min-seq-id 0.70` and the pass cannot use an identity floor
  — banded reporting needs the rows below the cut (D-105 parameter 6, D-124). Measured on a 417 M
  residue target with 31,381 seeds: 11,600 core-seconds filtered, 17,095 relaxed. Extrapolated to
  the full 3,159,223 seeds over 2.5% of the corpus with the sensitivity sweep, D-109's design is
  **$300-430, not $26**.
- **Decision (project owner): 0.25% of the corpus at the correct, unbinding hit cap.** Implemented
  as **one shard of the already-staged 2.5% sample**, which is 0.3125% — slightly more than asked,
  and free, because it is a hash partition of a sample already built, checksummed and staged
  (D-122). No new corpus pass. About **$50** with the full three-sensitivity sweep and all three
  coverage readings retained.
- **The cap stays at 100,000 and does not bind.** Measured: 5,078 hits for the worst seed against a
  417 M residue target, 5% of the cap, nothing truncated. At this target size the worst case is
  about 4,000, so the pass takes no recall loss from truncation. The alternative — capping at half
  the observed maximum for 2.8x — was available and is **declined**: it loses 0.9% of records, and
  a lost record is a missed survivor, which §2 treats as the same failure as overstating leakage.
  D-105 refused `-s 2.0`'s 2x saving on identical reasoning and this entry does not reopen it.
- **One shard, not eight.** The per-query coefficient is sub-linear in target size, so the sum over
  many small shards exceeds one search against their union. Sharding exists because no permitted
  instance can hold the whole corpus (D-094); at 0.3125% the target is about 334 MB and the reason
  does not apply.
- **What this costs in precision, stated rather than buried.** Eight times fewer records and
  correspondingly fewer families than D-109 planned. D-109 established that the binding constraint
  is the realised **family** count, not the record count, so the interval widens by roughly the
  square root of that factor and every rate must ship with its realised family count as that entry
  requires. UniRef and MGnify stay separate and unpooled.
- **Rejected:** The 2.5% design at its true price — defensible, and fifteen times the ceiling the
  owner set. One sensitivity at 2.5% — keeps precision, gives up the only check on whether the rate
  is a property of the filter or of our aligner settings, which D-109 already refused. A lower hit
  cap — priced at 2.8x for 0.9% of records and declined above.
- **Consequence:** D-109's sample size is superseded; its hash-sampling rule, identity banding,
  sensitivity sweep, design-effect intervals and denominator separation all stand. D-104's model is
  not to be used for any further estimate in this task without stating that it carries an identity
  floor the pass does not.
### D-129 — The narrow arm becomes A1.8; A1.6 keeps the broad arm only
- **Date:** 2026-10-17
- **Task:** A1.6 / A1.8
- **Numbering:** appended as D-119 and renumbered to D-129 on 2026-10-17. A2.1 and A2.4 held D-110..D-119 between them — D-110 and D-111 are A2.1's, D-112 to D-119 A2.4's — and these ten entries collided with that range [task attribution corrected in place 2026-10-19, D-175; the line originally said A2.4 held the whole range]: both tracks chose numbers at append time and the two appends merged cleanly while clashing semantically. A2.4's are already merged on `main`, and merged commit messages cannot be corrected, while this track's citations sit in `src/`, `tools/` and task files it could remap in the same commit — so this side is the cheaper one to move. PR #20 and the commits on `claude/fervent-hopper-8ht0h3` cite the old numbers; this line is how they resolve.
- **Context:** D-108 split the pass by denylist and both arms stayed inside A1.6. They have since
  diverged in every respect that matters: method (exhaustive against sampled), budget (roughly a
  seventeenth of the compute), what may be published (D-125's aggregation rules apply to one arm
  and not the other), and who is waiting on what. A1.6's own handoff flagged the split as the
  tidier option under the one-task-per-file rule and as the project owner's call, since ids are
  permanent and cited. The owner has now asked for it, so that another worker can take the narrow
  arm in parallel.
- **Decision:** the narrow arm is **A1.8**, `ready` and unassigned. A1.6 is the broad viral
  denylist only. `depends_on: [A1.4, A1.5]`, both `done`, so A1.8 is takeable immediately — it is
  deliberately **not** made to depend on A1.6, because its inputs are the staged proxy corpus and
  A1.4's manifest format rather than anything A1.6 still has to produce, and a dependency there
  would block the parallelism this split exists to allow.
- **What travels with it, explicitly, because a split is where governance gets lost.** D-125 and
  D-126 are A1.6 entries that now govern A1.8: counts by survival route and homology class and
  never by organism or taxon; the exact per-record result retained and staged at the key D-126
  fixes; nothing committed, since the public repo is deliverable 7; nothing circulated before
  X3.1; and the restriction inherited by A2.* and B3.* for their published outputs. D-106's
  published 187K is its validation target, and D-108's prohibition on pooling the two arms' outputs
  now spans two task files rather than sitting inside one.
- **What stays in A1.6:** the broad arm, now at 0.3125% of the corpus on one staged shard with the
  cap unbound (D-128), and the instrument both arms use.
- **Rejected:** Keeping both arms in A1.6 — it is the status quo and it was already the wrong
  shape; the file had three "waiting on the owner" blocks for two different questions and a reader
  could not tell which arm a given line governed. Making A1.8 depend on A1.6 — tidier as a graph
  and it would have left the new task `blocked`, which defeats the point. Renumbering anything —
  ids are never reused or renumbered.
- **Consequence:** one coordination point, recorded in A1.8's state block rather than left to be
  discovered: the instrument A1.8 builds on (`similarity.py`, `shardstore.py`,
  `tools/esm3_calibrate.py`, `tools/ec2_similarity.py`) is tested and green but sits on A1.6's
  feature branch and not on `main`. Whoever takes A1.8 should wait for that branch to land or
  branch from it rather than building a second copy. **That is an argument for landing A1.6's
  instrument on `main` sooner than its results.**

### D-130 — Both releases' GTDB versions are established, Evo 2's component contains Evo 1's, and D-119's premise was wrong
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-119 staged Evo 1's prokaryotic component on the reasoning that the two releases
  "pin different GTDB releases — Evo 2's is v220, Evo 1's is not yet identified from its own
  metadata", and said that identifying Evo 1's belonged in its own entry if it proved
  unrecoverable. The staging has finished; this is that entry, and it does not say what D-119
  expected.
- **What the staged data says.** Evo 1's `stage1_gtdb` Parquet carries **two columns and no
  version**: `record`, an INSDC contig accession (`JAHFAU010000149.1`), and `text`, the sequence.
  No GTDB release, no genome identifier, no taxonomy. So D-119 was right that the release is not
  recoverable from the component's own metadata, and wrong to leave it there.
- **What the publishers say.** Both releases state it, and the versions are more specific than
  D-119 assumed.
  **Evo 1 is GTDB v214.1**, stated twice in the **version of record** (`S-EVO1-SCIENCE`): "the
  OpenGenome pretraining dataset (table S2) was compiled from three different sources: (i)
  bacterial and archaeal genomes from the Genome Taxonomy Database (GTDB) v214.1", and again in
  the data-availability section. `.1` matters — GTDB publishes v214 and v214.1 — and D-119's "v220
  against unidentified" collapsed a stated minor version into an unknown.
  **Evo 2 is v214.1 plus a v220.0 delta, not v220.** It "used in its entirety" the OpenGenome
  dataset, "representative prokaryotic genomes available through GTDB release v214.1", and then
  added "new prokaryotic reference genomes made available through the GTDB release 220.0 update",
  selected as "all species' reference genomes that had no previously published (release 214.1)
  genomes within their species cluster, resulting in 28,174 additional genomes".
- **The staged tree corroborates this independently, and that is corpus-side evidence rather than a
  second source.** OpenGenome2's component is staged as
  `fasta/gtdb_v220/v214/batch{1,2,3}.tar` (83.5 GB) plus `fasta/gtdb_v220/v220_update.tar`
  (25.6 GB). The publisher's own path layout separates the reused v214 tree from the v220
  increment, under a directory named for the later release — so a reader who takes the directory
  name as the version gets it wrong, which is what D-119 did.
- **Decision:** Record v214.1 for Evo 1 and v214.1 + the 220.0 increment for Evo 2. Correct
  D-119's premise here rather than silently. **D-116's refusal to substitute stands, and its
  reason is now sharper**: substituting Evo 2's bacterial component for Evo 1's would not have
  substituted a different snapshot, it would have substituted a **superset** — v214.1 plus 28,174
  genomes Evo 1 never saw — for a subset, inflating the corpus Evo 1 is audited over with genomes
  published after its filter ran. That is a worse error than the one D-116 described, and it is
  the error the directory name invites.
- **The Evo 2 statements come from the preprint, and that is a live gap, not a footnote.**
  `S-EVO2-PREPRINT` is retrieved; the version of record `S-EVO2-NATURE` is
  `retrieved_not_stored`, so nothing may be quoted from it, and `S-EVO2-NATURE-METHODS` is
  registered **`unretrieved`** with the blocker that the Methods are absent from both the article
  HTML and the PDF. The GTDB-220.0 selection rule above is therefore a preprint claim. D-110
  found Evo 1's version of record agreed with its preprint word for word, which is grounds for
  expecting the same here and **not** grounds for asserting it — that is precisely the inference
  A2.1 made and was asked about. Flagged to the project owner in the same breath as this entry.
- **What the staging bought, stated plainly, because it bought less than D-119 assumed.** Not
  nothing: OG1's own train/valid/test splits, which A1.4's manifests are defined over, and its
  Parquet representation with contig accessions, which the tar tree does not carry. But Evo 2's
  `v214/` subtree is nominally the same genomes, already staged, so the 118.5 GiB is a second
  representation of a sequence set the audit partly held. Had this been established before the
  spend, the owner's choice would have been better informed, and the lesson is the ordinary one:
  the version was in the paper the whole time and the component's metadata was consulted first.
- **It also opens a sharper question than the one it answers.** "Used in its entirety" is a
  checkable claim about delivered data, and both sides of it are now staged. Whether OG2's `v214/`
  subtree is the sequence set of OG1's `stage1_gtdb` is measurable, and a discrepancy either way
  is an A7-class conformance finding. Opened as **A7.4** rather than absorbed into A2.4, which
  `AGENTS.md` forbids widening.
- **Rejected:** Leaving D-119's premise standing because its conclusion survives. The conclusion
  survives for a different and stronger reason, and a decision log whose reasoning is wrong where
  its outcome is right is worse than useless to the next reader.
  Treating the directory name `gtdb_v220` as the version. It is the trap this entry exists to mark.
  Asserting the Evo 2 selection rule from the preprint without saying so.

### D-131 — A2.4's ceiling is an on-demand ceiling, so the first band fits and the deepening does not
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-118 fixed A2.4's sampled pass against a $20 ceiling and compared it to A1.6's
  spend, which D-104 and D-109 priced on **spot**. D-120, appended by the A1.6 track while A2.4
  was in flight, establishes that spot cannot be launched from this account at all: a spot request
  needs the `AWSServiceRoleForEC2Spot` service-linked role, `iam:CreateServiceLinkedRole` is
  denied here, and a dry run does not catch it. D-121 records that the role is to be created. Until
  it is, every spot figure in this project is a price that cannot be paid, and A2.4's ceiling was
  set by analogy to two of them.
- **Decision:** Read A2.4's $20 as **on-demand**, and size the bands against on-demand rather than
  re-asking the owner for a number they have already given. On D-117's measured 2.73 core-minutes
  per Mb, the **2.5% first band is about 122 core-hours**, which is inside the ceiling on-demand
  with room to spare. A **10% band is about 490 core-hours and is not** — it is at or over $20 at
  on-demand rates where it would have been comfortable on spot. So the first band runs now and the
  deepening is contingent, not planned: it waits on either D-121's role being created or a fresh
  decision from the owner.
  Nothing about the design changes. Rates stay nested, so a later deepening still re-reads
  nothing, and `estimate_kind` stays `lower_bound` (D-118).
- **Rejected:** Keeping the spot figures and discovering the shortfall at launch, which is what
  D-120 describes happening to A1.6.
  Shrinking the first band to buy headroom for a deepening that is not authorised. The first band
  is also the calibration (D-118), and a band too small to price the real assemblies would fail at
  the one job that is certain.
  Treating the ceiling as elastic because the overrun is small. It is the owner's number.
- **Consequence:** A2.4's realized depth is likely to be 2.5% rather than the "deepen while the
  ceiling allows" of D-118, and the lower bound is correspondingly shallower. Stated with the
  result, since a lower bound's depth is what a reader needs to weigh it.

### D-132 — The spot role exists and is verified by a real launch, so D-131's on-demand ceiling is withdrawn
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-120 established that spot could not be launched from this account at all — a spot
  request needs the `AWSServiceRoleForEC2Spot` service-linked role, `iam:CreateServiceLinkedRole`
  is denied here, and the refusal arrives before any instance exists. D-121 recorded that the role
  was to be created. D-131 then re-read A2.4's $20 ceiling as an on-demand ceiling, which made the
  2.5% first band affordable and a 10% deepening not. The project owner has now created the role.
- **What was measured, and why a measurement was necessary.** D-120 is explicit that **no dry run
  finds this**: `DryRun` returns `DryRunOperation` without ever attempting the service-linked role,
  so a dry run would have reported success both before and after the fix and distinguished
  nothing. The only test is a real launch, so A2.4 made one — the smallest it could, a `c6i.large`
  on the stock Amazon Linux 2023 AMI with an 8 GB volume, `UserData` consisting of
  `shutdown -h now`, `InstanceInitiatedShutdownBehavior=terminate`, the one-time/terminate spot
  options D-120's launcher already uses, and a `terminate_instances` in a `finally`.
  **It was accepted.** `RunInstances` returned an instance with `InstanceLifecycle: spot`, and it
  was terminated immediately; a subsequent `DescribeInstances` over the `Project=ClaudeSpike` tag
  shows nothing running. Cost is of the order of a tenth of a cent.
- **Decision:** **D-131 is withdrawn.** A2.4 sizes its bands against spot again, which is what
  D-118's $20 ceiling was set by analogy to in the first place. The design does not otherwise
  change: the 2.5% first band still runs first and is still the calibration, because the reason
  for it was never the price — it is that D-117's 2.73 core-minutes per Mb comes from one
  complete, gene-dense genome and GTDB is mostly draft assemblies. The deepening to roughly 10%
  (about 490 core-hours) returns to being affordable inside the ceiling, and is taken **if and
  only if the first band's measured per-genome cost says it fits**, not on this entry's
  arithmetic.
- **Rejected:** Treating the owner's "the role is made" as sufficient and skipping the launch.
  It is a reasonable thing to believe and it was still worth one tenth of a cent to know, because
  the alternative is discovering it at the head of a real pass — which is exactly how D-120 was
  found, and it cost A1.6 a launch.
  Going straight to the deeper band now that spot is back. The calibration reason stands
  independently of the budget reason, and D-118 fixed the order before any result existed.
  Re-asking the owner for a ceiling. They gave $20 and the constraint that made it awkward is
  gone; nothing needs re-deciding.
- **Consequence:** A2.4's realized depth is no longer expected to stop at 2.5%, so the lower bound
  should be the stronger one D-118 planned for. Whatever depth is reached is reported with the
  result, since a lower bound's depth is what a reader needs in order to weigh it. The verification
  also stands for any other track: spot is live in this account as of 2026-10-17, confirmed by
  launch rather than by dry run.

### D-133 — A1.8 becomes a sampled proof-of-concept; D-108's exhaustive narrow arm and the all-clear it was built for are withdrawn
- **Date:** 2026-10-17
- **Task:** A1.8
- **Context:** D-108 split the similarity pass by denylist precisely so that the arm needing an
  all-clear would not be the expensive arm, and made this one exhaustive against every corpus
  record on the strength of that. A1.8's own cost note repeated the conclusion — "cheap, and that
  is why D-108 could afford to make it exhaustive" — and the staged-sample note in the task file
  exists specifically to stop a worker scoring 2.5% and reporting it as exhaustive.

  **The cost note was right about dollars and silent about wall clock, which is the binding
  constraint.** Priced against the only measurement that exists for the parameters the pass
  actually uses — 31,381 seeds against a 417 M residue target in 11,600 core-seconds, filtered
  coverage, A1.6's cap run on 2026-10-17 (D-128) — the arm's 187K seeds over the whole staged
  proxy corpus is about 13,600 core-hours. At the $0.16/hour 8-vCPU spot rate D-109 uses that is
  **about $272, and about 1,700 instance-hours**. The account's policy ceiling is `2xlarge`, eight
  vCPU, probed and recorded in `tools/ec2_similarity.py`: there is no larger machine to put it on.
  So the exhaustive pass is roughly seventy days on one instance, or seventy to a hundred separate
  launches, each of which is one-shot and unobservable — no shell, no SSM, console output
  best-effort — against a record of six launches in which two died thirty-one seconds in and one
  published nothing in four hours. D-108 weighed this arm's cost in dollars only, and a seventeenth
  of an unaffordable wall clock is still unaffordable.

  Two derived figures carry stated uncertainty rather than being presented as measurements. The
  corpus is taken as about 295 G residues, from shard 0's measured 417 M scaled by the sample's
  eight hash shards and 2.5% rate for UniRef100, then by the staged byte counts in A1.5 for the
  remaining components. And D-128 measured the per-query coefficient as sub-linear in target size,
  so a pass against larger shards costs somewhat less than this linear projection — the projection
  is the conservative bound, in the manner D-104 established, not a prediction.
- **Decision (project owner): the proof-of-concept is the deliverable, not a stage before the real
  pass.** A1.8 scores the reconstructed narrow seed set against the already-staged 2.5% hash sample
  of UniRef100 2023_02 (D-122), with one shard run first as a smoke test. About $3 and one launch of
  roughly nineteen hours, against $272 and seventy to a hundred. No new corpus pass: the sample is
  built, checksummed and staged, and `--sample-from` skips the fifty-two-minute pass.

  **D-108's exhaustive scope is withdrawn, and so is the claim it existed to support.** This arm
  reports a survival rate with an interval, in the same form as the broad arm, and **Phase A does
  not state that nothing on the narrow denylist survived.** A sample cannot support that sentence
  and this entry does not pretend otherwise.
- **What this costs, stated plainly because it is the expensive half of the trade.** The error runs
  in the direction that flatters the safeguard: a sample that happens to contain no surviving
  narrow-denylist material is evidence of a low rate, not of absence, and a survivor outside the
  sampled 2.5% is a survivor this audit does not see. §2 and D-128 both treat a missed survivor as
  the same class of failure as an overstated one, so this is a real reduction in what the audit
  detects and not a presentational matter. Every published form of this arm's result therefore
  carries the rate, its interval, its realised family count, and an explicit statement that no
  all-clear is made — enforced in the harness per the non-negotiables rather than left to the
  write-up to remember.
- **The corpus-scope gap this inherits, which the exhaustive design would have closed.** The staged
  sample is UniRef100 only, so at 2.5% this arm covers one of ESM3's stated components and leaves
  MGnify90 — 83.5 GB staged, and a component whose granularity is unstated (D-032) — scored not at
  all. The broad arm at 0.3125% has the same gap, so it is not introduced here, but D-108's
  "every corpus record" was the one place in the plan that would have closed it. It is named as an
  open limitation of Phase A rather than resolved inside this task, which is not the task to widen.
- **What does not change.** D-125's reporting rule in full: counts by survival route and homology
  class, never by organism or taxon, per-record detail to the disclosure package only. D-126's
  retention and its staged key, which a sampled pass satisfies unchanged — the manifest covers the
  records scored, so A3.3's independent reimplementation and the manifest A2.* and B3.* consume
  both still exist, now sampled and labelled as such. D-106's published 187K stays the validation
  target for the seed-set reconstruction, which is reconciled against a full-tier pass and not
  against the sample, because a seed set rebuilt from 2.5% of the corpus cannot be compared with a
  published total. D-105's parameters, D-128's unbinding cap with the saturation guard checked at
  this arm's own query scale, identity banding, D-109's design-effect intervals and denominator
  separation, the prohibition on pooling the two arms (D-108), and the X3.1 circulation bar.
- **Rejected:** The proof-of-concept as a first stage with the exhaustive pass to follow — keeps
  the all-clear, and defers rather than answers the seventy-launch problem. The exhaustive pass as
  D-108 fixed it — buys the strongest claim Phase A could make on this arm, at a wall clock and a
  launch-failure exposure the measurement did not exist to price when D-108 was written. A deeper
  sample than 2.5% — available, and it needs a fresh corpus pass and a new staging for a precision
  gain on a claim that is now a rate either way; revisit it if the realised family count turns out
  to be the binding constraint D-109 found it to be for the broad arm.

### D-134 — A1.6's broad arm runs as nested seed-sample bands reporting a lower bound; D-128's full-seed pass becomes its third band
- **Date:** 2026-10-17
- **Task:** A1.6
- **Numbering:** appended as D-133 and renumbered to D-134 on 2026-10-17. A1.8 took D-133 for
  its own sampled-proof-of-concept entry and that one is already on `main`, so this is the
  cheaper side to move. Nothing published cites this entry as D-133. **This number was also A1.8's D-137 before that entry was renumbered**, so a bare "D-134" in anything published before 2026-10-17 may mean D-137 rather than this entry. Cross-link added in place 2026-10-19, D-175.
- **Context:** D-128 fixed the broad arm as all 3,159,223 viral seeds against one staged shard —
  0.3125% of the corpus, six cells, about 413 instance-hours. Two things make that the wrong *next*
  step rather than the wrong destination. A full cell is about 40 hours, so it does not fit one
  instance run and needs the query sliced. And **band counts are per corpus record, so they are
  additive across shards but not across query slices**: the shards are a hash partition of the
  sample, so no record appears in two and summing cannot double count (`combine_cells` rests on
  exactly that), whereas a record matched by seeds in two different query slices would be counted
  once per slice, and its band is a max over all seeds rather than a sum. Slicing the query is
  therefore new machinery carrying a new correctness argument, built before any result exists, to
  buy a rate where a bound would do.
- **The measurement this design rests on.** The cap run (A1.6, 2026-10-17) already scored
  **31,381 seeds — 1/100 of the seed set by hash — against shard 0**, 417 M residues, at the pass's
  own parameters: 1,450 s wall for the `--cov-mode 1` search and 2,137 s for the relaxed one, on
  8 vCPU. With D-105's measured sensitivity ratios (2.08x faster at `-s 2.0`, 2.66x slower at
  `-s 7.5`) and the relaxed figure standing in for the `--cov-mode 2` search, six cells at 1/100
  come to about 14,850 s — **4.1 hours, one instance run**. Extrapolation is linear in query count,
  which is the conservative side: D-104 measured the marginal per-query exponent climbing from 0.5
  to 0.84 over a 200-fold range, so linear over-predicts. D-104's fitted *cost model* is not used
  here and must not be, because it carries a `--min-seq-id 0.70` floor the pass cannot use (D-128).
- **Decision (project owner): nested bands on the seed axis.**
  - **Band 1 — 1/100 of the seeds, 31,381.** Six cells, about 4.1 h, one instance run. Produces the
    banded, three-sensitivity, three-reading result with D-109's design-effect intervals.
  - **Band 2 — 1/10 of the seeds, about 315,922.** Six cells, about 41 h across six launches; the
    largest single cell is about 15.8 h, so **each cell still fits one instance run and the query
    is still not sliced**.
  - **Band 2 is taken if and only if band 1's measured per-seed cost and hit-table size say it
    fits** — not on this entry's arithmetic. D-132 set that discipline for A2.4's deepening and the
    reason is the same: these figures come from one measured point.
- **What sampling seeds does to the claim, and why this is the defensible direction.** A corpus
  record is counted if **any** seed matches it, so dropping seeds can only drop records, and a
  dropped seed can only lower a record's best identity. **Every band count at every band is a
  strict lower bound**, and the understatement is monotone in the sample fraction. That is the same
  direction D-105 took when it refused `-s 2.0`'s 2x saving and the same direction the coverage
  post-filter erred in, and §2's symmetry between overstating and understating leakage is why the
  bound has to be *reported* as one rather than quietly treated as a rate.
- **The two sampling axes stay separate and are reported separately.** The corpus axis is a
  0.3125% hash sample whose denominator is fully known, so D-109's design-effect interval applies to
  it unchanged. The seed axis contributes a **bound, not an interval**. So every figure reads "at
  least X%, interval from the corpus sample" and never as a point rate — collapsing the two into
  one number would be false precision in the direction of understating leakage.
- **Every rate ships its realised seed-family count**, alongside the realised corpus-family count
  D-109 and D-128 already require. 1/100 of the seeds covers materially fewer viral families than
  the full set, and the accumulation between band 1 and band 2 is the **only** evidence available
  about how far below the full-seed rate the bound sits.
- **Price, which is not what chose this design.** Spot is live and verified by a real launch
  (D-132), so band 1 is about **$0.50** and band 2 about **$5** on `m6i.2xlarge` spot, against
  $1.60 and $16 on demand. Either is inside any ceiling this task has had. The slicing correctness
  argument is what chose the design; the cost is why the nesting is free to have.
- **D-128 is not withdrawn — its pass becomes band 3**, about 413 instance-hours and about $50 on
  spot, and it is what the accumulation curve exists to decide on. Its target, parameters, hit cap,
  banding and interval treatment all stand for every band.
- **One indication already on the record, and it is not a result.** The cap run found 32,374
  records under `--cov-mode 1` at slack cap, against roughly 1.10M clusters in shard 0 — about 3%,
  from 1% of the denylist. It was a `RecordLedger` measurement rather than a pass: unbanded, one
  sensitivity, one reading, no interval, no family counts. It is the reason to expect band 1 to
  carry signal, not a number to cite.
- **Rejected:** Building query slicing and running D-128 now — a non-additive merge needs its own
  correctness argument and its own tests before any result exists, and it buys a rate where a bound
  is both cheaper and sufficient for the headline. Sampling the corpus deeper instead of the seeds —
  D-128 set the corpus depth deliberately, and deepening the corpus at full seed count is the
  expensive axis, not the cheap one. Band 1 alone — it leaves the gap to the full-seed rate
  unquantified, and at $0.50 a band the second one is not a real saving. Reporting a point rate from
  sampled seeds — rejected above.
- **Consequence:** a seed-sampled band's counts **may not be pooled with any full-seed result**, so
  D-108's no-pooling rule now has a third axis alongside the two arms and the two denominators. The
  per-record manifest a seed-sampled band produces is **incomplete by construction**, so A2.* and
  B3.* consuming it inherit a bound rather than a rate and must be told which band produced what
  they read. And the write-up carries "at least" in the sentence holding the number, not in a
  caveat further down.

### D-135 — Evo 2's version of record states the GTDB releases word for word, and it was open access all along
- **Date:** 2026-10-17
- **Task:** A2.4 / A7.4
- **Context:** D-130 established both releases' GTDB versions but flagged that the **Evo 2** side
  came from the preprint. `S-EVO2-NATURE-METHODS` was registered `unretrieved`, with the blocker
  that the Methods are absent from both the article HTML and the article PDF. `AGENTS.md` is
  emphatic about this exact situation — A2.1 spent twenty hours of compute on figures resting on
  a preprint — so it was escalated to the project owner rather than built on.
- **What it actually was.** Not a paywall. **The paper is open access, CC BY-NC-ND 4.0**, stated
  in the article's own XML, and deposited as `PMC13128491`. The obstruction was a *route*:
  `nature.com/articles/s41586-026-10176-5` returns `303` to `idp.nature.com/authorize`, a
  federated-login redirect, which from this environment is indistinguishable from a paywall if
  the only thing tried is the article URL. Europe PMC's REST API serves both the full text and
  the supplementary files without authentication.
  And the Methods were not missing from the article — they were never *in* it. They are in the
  Supplementary Information (`MOESM1`, captioned by the publisher "This file contains Methods,
  supplementary text and appendix", 45 pages), which is where `AGENTS.md` already says a methods
  appendix usually settles things, on the strength of ESM3's.
- **Decision:** Retrieve it, verify it, store it, and discharge D-130's caveat.
  Retrieved via `https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13128491/supplementaryFiles`.
  **Verified against the publisher's own digest**: the article XML states
  `md5 94fdc619ad34335e7051031447ec7100` and `1030230` bytes for `MOESM1`, and the retrieved file
  matches both exactly. Stored at `pdfs/s41586-026-10176-5_sm.pdf` on the owner's call, with the
  licence and attribution in the register, so the id is quotable.
- **What it says, which is what the preprint says.** §A.2.1 "Data curation": "Our previously
  published OpenGenome dataset was used in its entirety as part of the training data for this
  study. This included representative prokaryotic genomes available through GTDB release v214.1,
  and curated phage and plasmid sequences retrieved through IMG/VR and IMG/PR. As previously
  described, the OpenGenome dataset was curated to exclude genomic sequences of viruses which
  infect eukaryotic hosts." And: "New prokaryotic reference genomes made available through the
  GTDB release 220.0 update were added to the training data for this study. New genomes were
  identified by selecting all species' reference genomes that had no previously published
  (release 214.1) genomes within their species cluster, resulting in 28,174 additional
  prokaryotic genomes."
  The only difference from the preprint is the word "prokaryotic" in the final figure; the
  number, the releases and the selection rule are identical. **D-110 found the same for Evo 1,
  so both labs' versions of record now agree with their preprints on the corpus statements this
  audit rests on** — which is a result worth having rather than an absence of one, because it is
  what licenses using either.
- **Rejected:** Waiting for the owner once the ask had been made. The ask was right at the moment
  the blocker was believed, and withdrawing it the moment the blocker turned out to be a route
  problem is the same discipline, not a reversal of it. One check of an open-access mirror cost a
  minute and saved them the errand.
  Treating "the Methods are absent from the HTML and the PDF" as settled because it was already in
  the register. It was accurate and it was not the whole picture; a registered blocker is a record
  of what was tried, not a proof that nothing else works.
  Quoting from `S-EVO2-NATURE`, which stays `retrieved_not_stored` and therefore unquotable. The
  Methods are a separate deposit with its own licence note, and that is the id this entry cites.
- **Consequence:** **A7.4 is unblocked** and may assert against the version of record, which §7
  requires of any claim naming a laboratory. D-130's "currently preprint-sourced" caveat is
  discharged for the GTDB statements. The general lesson is cheap and worth recording: before
  escalating a publisher URL, check whether the paper is in PMC or Europe PMC — a `303` to an
  identity provider says nothing about the licence, and this one was openly licensed the whole time.

### D-136 — A2.4's record is the genome; Evo 2 publishes it and Evo 1's is derived, at a measured cost
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-115 fixed A2.4's sampling unit as "the genome record" before either component had
  been read. Reading them shows the two releases do not agree on what a record is, and fail to in
  opposite directions.
  **Evo 2's is already genome-shaped.** `fasta/gtdb_v220/...` is a tar whose every member is one
  gzipped FASTA named for its assembly — `batch1/GCF_017922435.1.fasta.gz` — so one member is one
  genome and the publisher supplies the identifier. Nothing is derived.
  **Evo 1's is contigs with no genome column.** `stage1/gtdb/*.parquet` carries `record` and
  `text`: an INSDC nucleotide accession and a sequence, and nothing else — no assembly accession,
  no organism, no grouping key of any kind. Taken literally the record unit would be the contig,
  which is wrong for this task twice: a provirus is a feature of a genome, and a per-contig
  denominator would let one 400-contig draft assembly count four hundred times a complete one.
- **Decision:** The record is the genome in both releases. Evo 2's comes from the member name.
  **Evo 1's is derived from the accessions, and `amazebio.gtdb.genome_key` reports that it is
  derived rather than returning a bare string.** An INSDC WGS accession encodes its project —
  `JAHFAU010000149.1` is contig `0000149` of project `JAHFAU01`, and a project is an assembly —
  so contigs are grouped on the project accession, with the optional RefSeq `NZ_` prefix ignored
  because it splits no assembly.
  **Measured, not assumed.** Over 40,000 contigs of `gtdb_train_shard_0`: **99.72% carry a WGS
  project accession** and group into genomes at a median of 43 contigs each. The remaining
  **0.28%** are complete replicons and scaffolds — `NZ_CP038213.1`, `NZ_GL890993.1`,
  `NZ_CM001022.1` — which carry no project and cannot be grouped. Each becomes a genome of one.
  **That under-groups**: a chromosome and its plasmids are counted as separate genomes. The error
  is bounded, measured, and enlarges the denominator, so the survival fraction it feeds is
  conservative — the direction to err in for a task whose null must stay visible.
  The pattern requires four to six letters before the two project digits, which is what separates
  a WGS contig from a complete replicon. A looser rule would read `CP038213` as project `CP03` and
  **merge unrelated genomes**, inflating per-genome content with nothing downstream to show it.
  That failure is tested for directly.
- **Rejected:** Using the contig as the record unit and reporting per-contig survival. Defensible
  only if the question were about contigs, and it is not; it would also make the two releases'
  figures incomparable, which is the one thing A3.2 has to be able to do.
  **Joining Evo 1's contigs to Evo 2's assemblies to recover the grouping exactly.** This would
  work and would be better: Evo 2's FASTA headers carry the same INSDC contig accessions Evo 1
  uses as its `record` column (`NZ_VDEZ01000001.1`, `JAHAXB010000057.1`), and Evo 2 reused Evo 1's
  genomes, so the assembly for most of Evo 1's contigs is recoverable from Evo 2's member names.
  It is not taken here for two reasons: it would make one release's record unit depend on the
  other's data, which is the cross-release coupling D-116 refused in a different guise; and it is
  **A7.4's join**, which has not run. If A7.4 establishes the mapping, A2.4 can adopt it and the
  0.28% shrinks — that is a strict improvement available later at no wasted work, and it is
  recorded here so the next worker does not have to rediscover that the headers carry it.
  Dropping accessions the rule cannot parse. It would shrink the corpus with nothing to show for
  it; they become genomes of one instead.
- **Consequence:** A2.4's denominator is genomes, comparable across releases, with Evo 1's
  carrying a declared 0.28% under-grouping and Evo 2's carrying none. The kind of key travels with
  the record (`wgs_project` against `accession`), so a reader can separate the derived grouping
  from the published one without re-deriving either. **And A7.4 gains a finding before it starts:
  its comparison key is a plain accession join, not the sequence-digest exercise its Steps allow
  for, because both releases carry the same INSDC contig accessions.**

### D-137 — The select-agent list's names map to taxonomy ids by curation, validated against the pinned taxonomy, never by name matching
- **Date:** 2026-10-17
- **Task:** A1.8
- **Numbering:** appended as D-134 and renumbered to D-137 on 2026-10-17. A1.6's broad-arm banding entry took D-134 first and is already merged on `main`, while this entry's citations sit in `src/amazebio/selectagents.py`, `policies/specs/` and this task's files, which the same commit can remap — so this side is the cheaper one to move. The commit "A1.8: reconstruct the select-agent list as taxa" on `ccr-51fc983f-tyojje` cites the old number; this line is how it resolves. **D-134 is now A1.6's banding entry** — so a bare "D-134" in anything published before 2026-10-17 may mean this entry, and after it means A1.6's. Cross-link added in place 2026-10-19, D-175.
- **Context:** ESM3-open's narrow denylist is "all sequences in UniProt belonging to organisms on
  the Select Agents and Toxins List" (D-106, version of record). The list does not carry taxonomy
  ids, so the mapping is A1.8's to decide and record — the first of the task's two open readings.
  The obvious implementation is to match each entry against `names.dmp` in the pinned 2023-04-01
  dump and descend what matches. Executed against the real list, that implementation is wrong in
  five independent ways, and the measurements below are why this entry exists rather than a line
  of code.
- **Decision: a committed, hand-curated table decides every entry; the pinned taxonomy only
  checks it.** `policies/specs/select-agents-2024-06-01.json` carries one record per list entry
  with its kind, its chosen taxa, whether descent is in scope, and the reasoning. 70 entries,
  one-to-one with the pinned regulation, enforced by a test. 53 entries name a taxon; under the
  literal reading those expand to 114,206 taxa.

  **What name matching does, measured on the real list.** Taken in the order they would bite:

  1. **It resolves into the wrong kingdom.** The five sub-entries under "South American
     hemorrhagic fever viruses" are bare words. In the pinned dump `Sabia` is the scientific name
     of taxid 13663, a genus of *flowering plants*; `Chapare` matches an orchid and four other
     plants; `Junin` matches a grass mouse and an Andes frog and no virus at all. Matching and
     descending would seed a plant genus into a select-agent denylist, and nothing downstream
     would notice.
  2. **It misses taxa that have been renamed, which is most of the viral entries.** Junín is
     "Argentinian mammarenavirus" in the pinned dump, with "Junin mammarenavirus" only an
     equivalent name and the older form carrying an accent an ASCII match drops. Lassa, Marburg,
     Newcastle disease and peste des petits ruminants all need a synonym or a reclassification.
     "Goat pox virus" fails on a space, the taxonomy spelling being one word.
  3. **It descends into material the regulation pointedly does not list.** There is no "SARS
     coronavirus" species: the containing node is 694009, "Severe acute respiratory
     syndrome-related coronavirus", whose 222 children include SARS-CoV-2. The regulation lists
     SARS-CoV and regulates SARS-CoV/SARS-CoV-2 chimeras *separately*, which only makes sense if
     SARS-CoV-2 is not itself listed. So descent here is refused — the one entry in the table
     where it is — because descending would import the largest viral sequence space in UniProt on
     the strength of a node name.
  4. **It silently invents taxa for entries that have none.** Nine entries name a toxin, which is
     a molecule; two name laboratory constructs (a reconstructed 1918 influenza virus, a defined
     chimera); one is a function over a genus rather than a taxon. Sixteen of the 70 entries
     contribute no taxon under the literal reading, and that is a number the write-up reports
     rather than a silent zero — `unresolved()` exists to produce it.
  5. **It cannot see where the taxonomy simply has no node.** `Sclerophthora rayssiae` is absent
     from the pinned dump under any name, including its genus's other species. `Coniothyrium
     glycines` exists only under the former name the regulation itself supplies parenthetically,
     which makes that parenthetical load-bearing. The Pasteur strain of *B. anthracis* has no node
     among 47 strain children, though that one costs nothing because the same section lists the
     species separately.
- **The readings that remain open are switches, not choices, following D-107's precedent.** Three
  were available and none is settled by the source, so each is a flag on `seed_taxa` and the
  sensitivity is run rather than argued: `include_toxin_producers` moves the nine toxins from the
  literal reading to their producing organisms (and for saxitoxin and tetrodotoxin even the
  producing set is undefined, recorded rather than guessed); `use_alternatives` takes the broader
  or narrower reading recorded against an entry. Measured: literal 53 named taxa expanding to
  114,206; toxin-producers 62 expanding to 125,008.
- **Three over-inclusions are taken deliberately and recorded, because the direction matters.**
  "Avian influenza virus" is not a taxon as worded — the regulation's scope is a virulence
  criterion on the isolate, a sequence-level property with no taxonomic expression at all, which
  is a §A0 under-specification in the *list* rather than in ESM3. It is taken as Influenza A virus
  with descent, which pulls in human seasonal influenza. Newcastle disease virus carries the same
  shape of criterion and is taken as the species. The two *Mycoplasma* entries are restricted by
  the regulation to one subspecies each and are taken as the species. In each case the taxonomy
  cannot express the restriction, and for an audit of a safeguard an over-inclusive denylist
  overstates what should have been removed rather than understating it — which is the side §2
  requires when the error cannot be eliminated. Tick-borne encephalitis virus is the one entry
  that cannot be made exact in either direction: the pinned dump has no node for either listed
  subtype, so the species is taken and it includes the unlisted Western subtype.
- **Consequence:** the reconstruction's provenance is a committed file a reviewer can read entry by
  entry, which §7's adversarial reader needs, and the error class in point 1 is a test
  (`test_no_viral_entry_is_mapped_outside_the_viruses`) rather than a near miss. The count of
  entries contributing no taxon travels with the result: an audit that says the filter should have
  removed these agents has to say which listed agents its own seed set could not represent.
- **Rejected:** Name matching with a hand-maintained exception list — the same table with the
  dangerous default left in place, so a re-pin that renames an agent fails open into the wrong
  kingdom instead of failing closed. Mapping only entries that resolve unambiguously — drops
  roughly half the viral entries and every plant pathogen, understating the denylist, which is the
  direction that flatters the filter. Per-strain enumeration for SARS-CoV instead of the named node
  without descent — considered and declined, because it would miss SARS-CoV isolates absent from
  the 2023-04 dump while buying nothing the refusal of descent does not already buy.

### D-138 — The list in force is the regulation at the access date, not the live page; and the gap costs nothing while the live page would have cost five agents
- **Date:** 2026-10-17
- **Task:** A1.8
- **Numbering:** appended as D-135 and renumbered to D-138 on 2026-10-17. A2.4's Evo 2 version-of-record entry took D-135 first and is already merged on `main`; same reasoning as D-137 above, and the same commit cites the old number.
- **Context:** A1.8's second open reading: which version of the Select Agents and Toxins List was
  in force when ESM3's filter ran. The task file recorded the problem as "the source cites a 2024
  access date; the retrievable page is live and undated", and the model card links
  `selectagents.gov/sat/list.htm`. Both halves of that premise turn out to be wrong, in opposite
  directions.
- **Decision: pin the regulation, not the page.** The list is codified — 42 CFR 73.3 and 73.4, 9
  CFR 121.3 and 121.4, 7 CFR 331.3 — and the webpage is a summary of it. The regulation is the
  authority and it has dated versions; eCFR's full-text API serves any date. A1.8 pins all three
  parts at 2024-06-01, stores the XML with digests (`policies/captures/cfr-*.xml`,
  `amazebio.selectagents.PINS_2024`), and takes 9 CFR 121.4 as a duplicate of 42 CFR 73.4 rather
  than counting the overlap agents twice.
- **The under-specification is real and its consequence is nil, which is the useful finding.** No
  amendment touched any of the three parts between **2022-05-27 and 2024-12-17**. Every date in
  2023 and in 2024 up to that December amendment therefore resolves to identical text, so the
  source's unstated version cannot change the reconstruction. §A0 asks for the consequence of
  under-specification to be measured rather than assumed, and here it measures as zero — recorded
  because a nil result is a result, and because it is the cheapest of A1.8's findings to lose.
- **The live page is a different version, and using it would have understated the denylist.** The
  page is not undated — it carries `cdc:last_reviewed` 2025-01-14 — and it reflects the amendments
  of 2024-12-17 and 2025-01-16, both of which postdate the filter. Against the 2024 text those
  amendments **delist five organism entries** that were in force when the filter ran: three
  *Brucella* species from the overlap list, African horse sickness virus from the veterinary list,
  and *Peronosclerospora philippinensis* from the plant list. They also widen one entry from a
  species to its genus, *Ebolavirus* — so the broader reading of that entry is the later
  regulation's own rather than ours (D-137).

  A seed set built from today's page would therefore be missing five agents the filter was supposed
  to have removed. For an audit of that filter the bias runs one way: a smaller denylist means less
  material we expect to have been removed, so leakage is understated and the safeguard looks more
  complete than it was. That is the same direction D-133 flagged for the sampled pass, and it is
  the direction §2 treats as the failure to avoid.
- **Consequence:** every A1.8 result cites the regulation at 2024-06-01, with the amendment
  actually in force recorded alongside (`CfrPin.effective`), so a reader can tell a re-pin from a
  re-run. Any later re-pin must re-check the mapping table, which a test enforces by failing on an
  entry with no recorded reading rather than skipping it. The five delistings are also a live
  example for A9.1, which measures denylist decay against taxonomy updates: the list itself decays,
  not only the taxonomy under it.
- **Rejected:** The live page, as the model card links it — wrong version, as measured above.
  A web-archive snapshot of the page at the access date — the archive is unreachable from this
  container (`web.archive.org` closes the tunnel mid-exchange, and the fetch tool refuses the host),
  and it would in any case be a dated copy of a summary when the dated authority is directly
  retrievable. Asking the project owner to retrieve the snapshot — the escalation AGENTS.md
  requires when a source is blocked for an agent, and not needed here: the blocked source was the
  inferior one, and the better source was never blocked.

### D-139 — The seed machinery's counters are renamed denylist-neutral, and the serialised keys accept both spellings because the staged manifest is permanent
- **Date:** 2026-10-17
- **Task:** A1.8 (changes code A1.6 owns)
- **Context:** `src/amazebio/seeds.py` was written for A1.6's viral arm and its generality was
  accidental: `ScanConfig.viral`, `SeedCounts.viral_seeded`, `viral_residues`,
  `representative_not_viral`, and `UniRefEntry.is_viral_seeded` all take or count an arbitrary
  taxid set, with nothing viral in the logic. A1.8 needs exactly that machinery for the
  select-agent denylist (D-137), so the names would have described the wrong thing for the second
  arm — and D-126 stages A1.8's per-record manifest permanently in a bucket with no
  `DeleteObject`, so a mislabelled field is a mislabelled field for good.
- **Decision (project owner): rename, rather than wrap the call or let it ride.**

  | was | is |
  |---|---|
  | `ScanConfig.viral` | `denylist_taxids` |
  | `SeedCounts.viral_seeded` | `seeded` |
  | `SeedCounts.viral_residues` | `seeded_residues` |
  | `SeedCounts.representative_not_viral` | `representative_not_seeded` |
  | `UniRefEntry.is_viral_seeded` | `is_seeded` |
  | `UniRefEntry.representative_is_viral` | `representative_is_seeded` |

  `to_dict`'s keys follow, so `viral_share` becomes `seeded_share` and
  `representative_not_viral_share` becomes `representative_not_seeded_share`.
- **What is deliberately *not* renamed, because "viral" is sometimes the correct word.** The
  rename covers the machinery that is generic over which denylist is in play, and nothing else.
  `VIRAL_ROOT` stays — it is the Viruses superkingdom. Every `viral` in `misassignment.py`,
  `ictv.py`, `genomad.py` and `survival.py` stays: those are about viruses, not about denylists,
  and a blanket rename would have been 270 occurrences across 54 files instead of the 11
  identifiers that were actually mislabelled. `ShardManifest.viral_seeded_clusters` also stays,
  with a comment recording why: it is not a generic counter but a fact about *one* staged sample,
  which the broad arm drew with viral seeds, and A1.8 reads that sample rather than drawing its
  own.
- **The serialisation boundary, which is the part with a permanence consequence.** The staged
  2.5% sample manifest (D-122) carries `viral_seeded` inside its `seed_counts`, it is the input
  A1.8's pass reads under D-133, and it cannot be rewritten. `ShardManifest.from_json` refuses
  any manifest whose `version` it does not recognise — deliberately, so that it never guesses
  which fields still mean what they did — so **bumping `MANIFEST_VERSION` would refuse exactly
  the manifest this arm needs.** The version therefore stays at 1 and
  `check_self_consistent` accepts either spelling, with tests for the legacy key, the new key,
  and a self-contradicting manifest under both. Accepting two spellings is a cost; refusing a
  permanent artefact the pass depends on is a larger one.
- **Consequence:** A1.6's call sites in `tools/esm3_seeds.py` and `tools/esm3_calibrate.py` are
  updated in the same commit, so nothing is left half-renamed for the other track to trip over.
  A1.6 is still `in-progress`, so whoever resumes it should expect these names rather than the
  ones its handoff notes quote; the counters mean exactly what they meant, and
  `tools/esm3_seeds.py` still prints "viral-seeded" because for that arm it is viral. Any future
  arm gets correctly-labelled provenance without a third naming decision.
- **Rejected:** A narrow-arm wrapper relabelling on output — zero risk to the in-progress broad
  arm, and it leaves a module whose internal names misdescribe both arms plus a relabelling step
  a later arm can get wrong. Passing the set through unchanged and explaining it in the write-up
  — smallest diff, and it writes a misleading field name into a staged object that cannot be
  withdrawn. A manifest version bump alongside the rename — the tidy-looking option, and
  `from_json`'s own refusal semantics turn it into a broken pipeline.

### D-140 — The interval's sampling unit is taxonomic family; published family counts stay with A2.1's registries
- **Date:** 2026-10-17
- **Task:** A1.6
- **Context:** D-109 committed the broad arm's rates to an interval estimated from
  between-family variance rather than a binomial one, because viral material is clumped by
  family and the binomial error at this sample size is under 0.01% — a confident-looking number
  for the wrong quantity. `rate_with_interval` has wanted one `(hits, records)` pair per family
  since it was written, and **nothing in the pass tooling produces a family for a UniRef
  cluster**: `grep -n famil tools/esm3_calibrate.py` returns nothing. So the interval D-109
  promised had no sampling unit, and band 1 could not have reported one.
- **Decision (project owner): split the label by what it is used for**, in the manner D-113
  split localisation from identity in A2.4.
  - **The variance unit is the taxonomic family**, from the taxonomy already pinned for the
    seed set — `taxdmp_2023-04-01`, contemporaneous with UniRef 2023_02 rather than current.
    A cluster's family is its `TaxID` climbed to family rank. Zero extra compute: the shard
    FASTA carries the taxid and the taxonomy is already a pinned input.
  - **Published family counts stay with A2.1's pinned profile registries**, which is what
    D-022's frozen detection schema requires and what D-125's reporting rule means by homology
    class. A1.6 does not publish a family-level survival claim from a taxonomic label.
- **Why this is not the thing §A2 forbids.** §A2 says the audit must not *rest* on taxonomy, and
  A4.2 measured that tool failing to place 36% of the genomes the denylist targets. The use here
  is strictly the sampling unit of a variance estimate: it affects how wide the interval is, not
  which records were found, not the rate, and not any statement about which families survived.
  Every detection and every published family count still comes from a curated registry. The
  distinction is recorded because it is exactly the kind of use that looks like the forbidden one
  from a distance.
- **An unplaced cluster is its own stratum, not attributed.** `ancestor_at_rank` returns `None`
  rather than substituting the nearest rank, because a lineage carrying no family node is not a
  member of some other family. Given A4.2's 36%, the unplaced set is expected to be large, and
  pooling it into one pseudo-family would understate between-family variance — the direction that
  makes the interval look tighter than the evidence supports. Each realised stratum is reported
  with the rate, as D-109 already requires of the family count.
- **Rejected:** Registry families for the interval as well — schema-consistent end to end and
  directly comparable with A2.1 and A2.4, but it adds a profile search over the hit set whose cost
  is unmeasured, which would stop band 1 being the one-run job that makes it worth running first.
  Revisit it if the realised stratum count turns out to be the binding constraint. Taxonomic
  families for the published counts too — cheapest, and it would put the weakest label in Phase A
  underneath a headline claim, which §A2 and A4.2 both refuse.
- **Consequence:** the interval's unit is a *reading* of the corpus rather than a measurement of
  it, so the write-up states which label produced the interval and which produced the family
  counts. The same split is available to A1.8, whose arm has the same gap, and it is not assumed
  there: that arm takes its own entry if it wants it.

### D-141 — Correction to D-140: pooling the unplaced clusters does not understate the interval, it destabilises it
- **Date:** 2026-10-17
- **Task:** A1.6
- **Context:** D-140 kept each unplaced cluster as its own stratum and justified it by claiming
  that pooling them into one pseudo-family "would understate between-family variance — the
  direction that makes the interval look tighter than the evidence supports". That reasoning was
  asserted, not measured. Measuring it refutes it as a general claim.
- **What the estimator actually does.** Against 64,000 records in 640 clumped families plus
  36,000 unplaced — A4.2's 36% unplaced fraction, which is why the magnitude matters:
  - unplaced set's hit rate **equal** to the overall rate: pooled standard error is **0.998x**
    the singleton one. D-140's direction, and negligible.
  - unplaced set's hit rate **different** from the overall rate (0.5 against 0.1): pooled standard
    error is **10.9x** the singleton one.

  The mechanism is visible in the formula. A pooled stratum contributes `(A - r*B)^2` for its own
  totals, which is **zero** when its rate happens to equal the overall rate and enormous when it
  does not. So pooling does not bias the interval in a direction; it makes the interval a function
  of one stratum's own rate, with a third of the data behind it.
- **Decision:** the singleton treatment stands, and **its justification is replaced**. Each
  unplaced cluster is its own stratum because that is the only treatment whose interval is stable
  against a quantity the audit has not measured — the hit rate of the records the taxonomy cannot
  place. Singletons contribute the binomial term for that portion, which is the honest statement
  that those records carry no family information, rather than a variance estimate driven by
  whether their rate coincides with the pooled one.
- **What does not change.** The split in D-140: taxonomic family for the variance unit, A2.1's
  registries for every published family count. `ancestor_at_rank` returning `None` rather than a
  nearest-rank substitute. The realised stratum count shipping with every rate.
- **Rejected:** Letting D-140's sentence stand because the implementation it justified is the one
  we keep. A reader checking the reasoning would find it false and have no way to tell whether the
  conclusion survived it, and §7's adversarial reader is the one who checks. Pooling after all —
  refuted above.
- **Consequence:** the write-up reports the realised stratum count **and the unplaced fraction**,
  because with singletons the design effect is diluted by exactly that fraction and a reader needs
  it to interpret the interval. One general lesson worth carrying past this entry: both of D-140's
  variance claims were checkable in about a minute, and the one that was asserted was wrong by a
  factor of eleven in the opposite direction.

### D-142 — The staged sample cannot describe its own strata, so band 1 owes one corpus pass; the cluster's family is its representative's
- **Date:** 2026-10-17
- **Task:** A1.6
- **Context:** D-140 made taxonomic family the interval's sampling unit and priced it at zero
  extra compute, on the reasoning that "the shard FASTA carries the taxid and the taxonomy is
  already a pinned input". The first half is false. `seeds.write_fasta` writes a bare cluster id
  with no description, deliberately — MMseqs2 keys results on the first whitespace-delimited
  token, so anything after it is carried through the whole pipeline for nothing — and the staged
  2.5% sample (D-122) was written by it. **The staged sample does not carry taxids.**

  It cannot be recovered afterwards from the hit table either, and this is the part worth being
  precise about: the interval's denominator is the records *searched* per stratum, not the records
  that matched, so it needs a family for every sampled cluster including every miss. The hit table
  contains no misses by construction. Looking up only the hit targets would give a numerator with
  no denominator.
- **Decision, three parts.**
  1. **The strata travel in a sidecar.** The corpus pass writes one `cluster_id\ttaxid` row per
     sampled cluster, per shard, beside the FASTA. A sample staged from here is self-describing
     and owes nothing later. The format states an unplaced cluster explicitly rather than omitting
     it, because an absent row and a row saying "no taxid" are different claims and only one of
     them survives a truncated file; and a malformed row raises rather than being skipped, since a
     row silently dropped is a record silently removed from the denominator, which moves the rate
     **up**.
  2. **A cluster's family is its representative's**, not a union over its members. A union would
     put one cluster in several families and break the partition the ratio estimator needs — a
     record in two strata is counted twice in the denominator, which `FamilyIndex.build` now
     refuses outright. The cost of the choice is already measured rather than argued: D-092 put
     the representative-versus-member gap at 1.06% of viral-seeded clusters on this tier, and that
     figure travels with the interval as it does with the seed count.
  3. **Band 1 owes one corpus pass**, about 52 minutes and roughly $0.20 on spot, to produce the
     sidecar for the already-staged sample. The selection is deterministic — `bucket_of` on the
     cluster id at the same rate and bucket count — so the pass reproduces exactly the clusters
     already staged, and the sidecar's per-shard row count is checked against the staged shard's
     record count before any rate is computed. D-122's "no new corpus pass" no longer holds for
     this arm, and saying so is cheaper than discovering it at the head of the band.
- **What this does to D-140's costing.** "Zero extra compute" becomes one 52-minute pass, once,
  shared by every band and by A1.8 if it takes the same split. Band 1 goes from about $0.50 to
  about $0.70 and from one launch to two. Neither changes the design, and D-134's figures are
  otherwise unaffected.
- **Rejected:** Putting the taxid in the FASTA header — it would be carried through every search,
  every hit table and every sort for the whole pass, to be used once at the end, and it would
  invalidate the staged sample's checksums for no gain. Re-staging the sample with taxids — a
  fresh corpus pass *and* a fresh staging into a bucket that cannot delete, where a sidecar costs
  the pass alone. Taking the family from the member taxids — breaks the partition, as above.
  Deriving strata for the hit targets only — gives a numerator with no denominator, as above.
- **Consequence:** the sidecar is a new input to the rate, so it is pinned and checksummed like
  any other, and the write-up states that the interval's strata come from a sidecar built by a
  later pass than the sample it describes. A1.8 inherits the same gap and the same fix if it takes
  D-140's split; it is not assumed there.

### D-143 — A run that read a limited sample publishes no survival figure at all
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** `tools/detect_proviruses.py` gained a `--limit` flag for exercising the path
  cheaply. Its first end-to-end run, `--limit 1 --rate 1.0` over Evo 1's GTDB, finished cleanly
  and wrote three tables reporting **`estimate_kind: population`, 0 of 1,719 Pfam viral families,
  Wilson interval [0, 0.0022]**. Every number in that is arithmetically correct. It was computed
  from **one genome and 25,792 bases**.
  The mechanism is ordinary and worth naming: `estimate_kind` is derived from the sampling rate,
  `--limit` does not change the rate, and the fact that the run stopped early lived in a
  `limited: true` field on the source row where nothing computing the estimate could see it. The
  exit code was 0 and the run looked successful; only reading the artefact showed it.
- **Decision:** A run with `--limit` prints its counts and **writes no table**, only the
  `run.json` that records what was done. The guard sits before the write, and a test pins that
  ordering structurally rather than by behaviour, because the failure is one of sequence.
  `--limit` is documented as exercising the path, not as a small pass.
- **Rejected:** Deriving a realized rate from the limited run and reporting a `lower_bound`.
  There is no honest realized rate: the population of the component is unknown — A1.4 does not
  enumerate GTDB — so the denominator of "one genome out of how many" does not exist, and an
  invented one would be a worse artefact than none.
  Keeping the table and adding a caveat to `notes`. `AGENTS.md` is explicit that a caveat at the
  end of a long run is not an ask and arrives after the damage; the same applies to a caveat
  beside a number that should not exist. A figure that must not be quoted should not be written.
  Removing `--limit`. Exercising the whole path against the real corpus for pennies is how this
  fault was found in the first place, and the probe is worth keeping — it just must not
  masquerade as a result.
- **Consequence:** The null this task is most likely to report — no viral families surviving in
  sampled bacterial genomes — can no longer be manufactured by a run that read almost nothing.
  `DESIGN.md` §2 makes the null publishable and `AGENTS.md` forbids designing the pipeline so a
  null is harder to see; this is the mirror of that rule, which the same sentence implies and
  which is easier to break: a null must not be *easier* to produce than it is to earn.
  The general lesson is the cheap one: a clean exit code and a plausible-looking table are not a
  verified run. This was found by reading the artefact, not by reading the log.

### D-144 — The corpus is 484 Gbp, not 107 Gbp: D-117's census figure was out by four and a half times
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-117 extrapolated a full GTDB census at about 4,900 core-hours from one genome's
  measured rate of 2.73 core-minutes per Mb. The base count in that arithmetic was the *staged
  byte* count, read as roughly one byte per base. That assumption was never checked, and it is
  wrong for one of the two components.
- **What was measured.** Reading the staged objects directly:
  **Evo 1's Parquet stores its sequence essentially uncompressed** — one row group of
  `gtdb_train_shard_0` holds 24,379,463 bases in 24,409,247 compressed bytes, **1.00 bases per
  byte**. So 127,261,074,759 staged bytes is about **127,000 Mb**, and the original reading
  happened to be right here.
  **Evo 2's tar members are gzipped FASTA**, and are not. Twenty-five genomes off `batch1.tar`
  carry 86,855,551 bases at a mean of 3.47 Mb per genome, against member sizes around 1 MB —
  about **3.27 bases per byte**. So 109,142,824,960 staged bytes is about **357,000 Mb**, not
  109,000.
  **Total: 484,000 Mb across both releases**, against the ~107,000 D-117 worked from. A full
  census is therefore about **22,000 core-hours**, not 4,900.
- **Decision:** Correct the figure and re-price every band from it. At 8 vCPU — the policy's
  2xlarge ceiling — and m6i.2xlarge spot at $0.12-0.21/hour as quoted today:
  **2.5% of both releases: ~550 core-hours, ~69 wall hours, $13-18.**
  **0.25%: ~55 core-hours, ~7 wall hours, about $1.50.**
  The spend was authorised against the old figure, so the new one goes back to the project owner
  rather than being absorbed: $13-18 is inside the $20 ceiling but it is not the $5-7 they were
  told, and 69 hours is a different operational proposition from an afternoon.
- **Rejected:** Proceeding at 2.5% on the grounds that it still fits the ceiling. The
  authorisation was "as long as the billing doesn't change", and a figure that moves by two and a
  half times has changed even when it stays under the cap.
  Treating the per-Mb rate as the remaining uncertainty. It is still a one-genome figure from a
  complete, gene-dense assembly, so the real cost on GTDB's draft assemblies could move this
  again in either direction. That is what the first band is for (D-118), and it is now a stronger
  argument for a *small* first band than it was when the census looked affordable.
- **Consequence:** D-117's "same order as A1.6's authoritative pass" no longer holds — a census
  here is several times that, and out of reach at this ceiling. The sampled design of D-115 and
  D-118 is now forced by cost rather than chosen, which is the opposite of what D-117 concluded
  and is worth saying plainly in any write-up that cites either.
  The general lesson is the one D-098 already taught this project once, in the other direction: a
  cost derived from a number nobody measured is a design decision taken by accident. Here it was
  bytes read as bases.

### D-145 — The first band is 0.25%, and D-118's 2.5% waits on what it measures
- **Date:** 2026-10-17
- **Task:** A2.4
- **Context:** D-118 fixed the first band at 2.5% when D-117 priced a full census at 4,900
  core-hours. D-144 corrected the corpus to 484,000 Mb and the census to about 22,000 core-hours,
  which puts 2.5% of both releases at roughly 550 core-hours — 69 wall hours at the policy's
  8 vCPU ceiling, and $13-18 on spot. The owner authorised the pass "as long as the billing
  doesn't change"; it changed, so the band went back to them.
- **Decision:** The first band is **0.25%**: about 55 core-hours, 7 wall hours, $1.50. 2.5%
  is not abandoned, it is sequenced behind the thing it depends on.
  This is what D-118 designed rather than a retreat from it. The first band exists to *be* the
  calibration, and the per-genome rate it calibrates is still a one-genome figure taken from a
  complete, gene-dense *E. coli* assembly. GTDB is mostly draft assemblies in many contigs, where
  gene density, contig count and the per-call overhead all differ, so the 69-hour figure rests on
  a number this band is meant to replace. Committing three days of wall clock to it first would
  invert the design.
  Membership is nested (D-078), so the 0.25% band is a strict subset of the 2.5% one and
  deepening re-reads nothing. `estimate_kind` stays `lower_bound`, and the realized rate is
  recorded per source, so the shallower depth is visible in the artefact rather than inferred.
- **Rejected:** 2.5% now because it still fits under $20. The authorisation was conditional on
  the figure, and $13-18 is not $5-7 even inside the cap. Spot reclaim across 69 hours is also
  likely, and per-object resumability does not exist yet — so the expensive option is the one
  most likely to need re-running.
  2.5% on Evo 1 alone, at a quarter the size. Cheaper and sooner, and it would leave the prophage
  route measured at full depth on one of the two corpora, which is the asymmetry D-116 exists to
  prevent. A shallower band on both is the better trade than a deeper band on half.
- **Consequence:** A2.4's first result is a lower bound at 0.25% of both releases, and must be
  reported as the shallow bound it is — at that depth a null is weak evidence and a detection is
  still a detection. What the band buys beyond its own result is the measured per-genome cost on
  real draft assemblies, which is the number every later decision about depth depends on, and
  which no amount of further arithmetic from D-117's single genome can supply.

### D-146 — One list entry carries 98.5% of the select-agent seed set; the reading stands and the reporting splits
- **Date:** 2026-10-17
- **Task:** A1.8
- **Context:** The full-tier seed pass finished (UniRef100 2023_02, all 118.68 GB of staged
  object, 54 minutes, commit `b00640f`) and returned **1,079,124 seeded clusters of
  350,950,053** — 5.8x the 187K ESM3 publishes for this denylist (D-106). D-137 had named both
  directions of expected discrepancy but no magnitude, so the artefact could report the gap and
  not decompose it.

  **It decomposes into one entry.** "Avian influenza virus" maps to Influenza A (taxid 11320),
  and descending it contributes **112,716 of the 114,467 expanded taxa — 98.5%**. The other 52
  taxon-naming entries contribute about 1,750 between them. Influenza A is also among the most
  heavily sequenced taxa in UniProt, so its share of *clusters* is larger still. The regulation
  restricts highly pathogenic avian influenza; the pinned taxonomy has no node for that, so
  D-137 took the species and recorded the over-inclusion. What is new is the size of it.

  **The lab's own figure says they did not read it this way.** ESM3 reports 147K non-viral plus
  40K viral. All of Influenza A does not fit in 40K viral sequences by any counting. So the
  denylist being audited and the denylist being reconstructed differ, and they differ almost
  entirely in this one entry.

  **It also breaks D-133's budget, twice over.** That entry priced the sampled pass at one
  launch, about nineteen hours and about $3. Two things are wrong with the figure, and they
  compound. It assumed 187K seeds, and the seed set is 1,079,124. And it costed a *single*
  search, where the pass runs six cells per shard — three sensitivities (D-105) against two
  coverage-filtered searches (D-124). On the same measurement D-133 used — 31,381 seeds against
  shard 0's 417 M residues, A1.6's cap run of 2026-10-17 (D-128) — the full 2.5% sample is about
  **1,135 instance-hours and $180**, not one launch. D-133's *comparison* against the exhaustive
  pass survives, because both sides of it were costed single-cell; its absolute figure does not.
- **Decision (project owner): measure the split, then report it as two strata. The reading in
  D-137 is not changed.**

  1. The seed pass is re-run with per-entry attribution, so the influenza share is a measured
     number rather than an inference from taxon counts. About an hour and under a dollar; it
     also closes a provenance gap the first pass exposed (below).
  2. The **primary** result is the seed set with the entry's exclusively-claimed clusters
     removed — the agents the list names that are not seasonal influenza. This is the figure
     expected to reconcile against the published 187K, and the one the scoring pass is sized
     against.
  3. The influenza contribution is reported as a **separate, named stratum**, not dropped and
     not pooled. It is a real consequence of a reading the regulation's own wording forces on
     the pinned taxonomy, and §A0 treats that as a finding.
- **Why the reading is not simply narrowed, which was the tidier option.** Restricting the entry
  to H5/H7 lineages would produce one clean reconciled number, and it would do it by overwriting
  a reading already recorded, argued and pinned — replacing a measured over-inclusion with a
  curated guess at what the lab meant, in the same artefact that is supposed to show where
  readings bite. The split keeps both numbers visible and costs an hour.
- **What "exclusively claimed" means, because the arithmetic depends on it.** A cluster is
  seeded if *any* member is on the list, so a cluster can be claimed by more than one entry.
  `claimed` counts a cluster once per claiming entry; `exclusive` counts only clusters a single
  entry claims alone. Removing an entry removes its exclusive clusters and no others, so
  `exclusive` is the only one of the two a decision can rest on. `seeds.EntryCounts` keeps them
  apart and the largest contributor is named from the measurement, so a later re-pin reports
  whichever entry then dominates rather than this one.
- **A provenance gap found in the same place, fixed in the same commit.** `repro.run` writes its
  manifest when its block exits, so `select_agent_seeds.py`'s upload — which sat inside that
  block — had no file to send. The first pass staged its results and left its `run.json` on an
  instance that then terminated. The instance has no checkout and no shell, so a manifest that
  does not leave by object storage does not leave at all, and AGENTS.md is explicit that an
  untraceable result is not citable. The first pass's figures are recoverable only through its
  code tarball key; the re-run supersedes it at the same keys.
- **Consequence for what A1.8 may say.** The arm already makes no all-clear (D-133). It now also
  may not report a single denylist survival figure without saying which stratum it is: a pooled
  rate over the reconstructed seed set would be a statement mostly about seasonal influenza
  wearing a select-agent label, which is precisely the kind of number §7's adversarial reader
  should catch. Per-stratum reporting is the default, as §B5 already requires elsewhere.
- **Rejected:** Narrowing the entry and rebuilding — above. Running the pass on the pooled seed
  set and explaining the composition in the write-up — it spends 1,135 instance-hours mostly on
  influenza and leaves the headline needing a paragraph of correction. Dropping the entry
  outright — it is on the list, and an audit that silently declines to look for a listed agent
  has chosen its own scope.

### D-147 — Correction to D-144: Evo 1 is 275 Gbp, not 127, and the running band measured it
- **Date:** 2026-10-17
- **Task:** A2.4
- **Numbering:** appended as D-146 and renumbered to D-147 on 2026-10-17. A1.8's D-146 was already on `main` when this was written and is the one cited elsewhere; this entry was cited only from its own commit message, so it is the cheaper one to move. The commit "A2.4: D-146 — Evo 1 is 275 Gbp" refers to this entry.
- **Context:** D-144 corrected D-117's corpus size and got one of its two halves wrong in the
  same way. It reported Evo 1's Parquet at **1.00 bases per byte**, concluding that the staged
  byte count was a fair proxy for its base count. That ratio came from comparing bases against
  `RowGroupMetaData.total_byte_size`, which is the **uncompressed** size. Comparing sequence
  bytes to the uncompressed size of the column holding them returns 1.00 by construction. It is
  not a measurement, it is a tautology, and it looked like a confirmation.
- **What the real figures are, from two independent directions.**
  Summing the per-column `total_compressed_size` on the same row group gives 11,288,188
  compressed bytes for 24,379,463 bases: **2.16 bases per compressed byte**. Evo 1's 127,261,074,759
  staged bytes are therefore about **274,850 Mb**, not 127,261.
  The first band measured it independently while this was being worked out: at rate 0.0025 it
  sampled **375 genomes and 699,031,198 bases** of Evo 1, implying **279,612 Mb**. The two agree
  to **1.7%**, which is the confirmation D-144 thought it had.
  **Corrected total: Evo 1 ~277,000 Mb plus Evo 2 ~357,000 Mb, about 634,000 Mb.** A full census
  is roughly **29,000 core-hours**; 0.25% is about 72 core-hours, and 2.5% about 720 — 90 wall
  hours at the 8 vCPU ceiling.
- **Decision:** Record the corrected figure and the method that produced it, and treat the
  *measured* number as authoritative over either byte-count derivation. The band exists to
  produce measurements; the first thing it measured was the size of the thing it is sampling.
- **Rejected:** Quietly amending D-144. It is append-only and its arithmetic was cited in the
  question that set this band's depth; a reader who finds 127,261 Mb there needs to find this
  entry too.
  Treating the 1.7% gap as disagreement. The sample is 375 genomes drawn by hash, so a couple of
  percent either way is what it should do; the point is that two derivations that share no step
  landed in the same place.
- **Consequence:** **The same mistake has now been made three times in this task** — D-117 read
  staged bytes as bases, D-144 half-corrected it and read an uncompressed size as a compressed
  one, and both times the wrong number looked right enough to act on. The common factor is
  deriving a quantity from a field whose meaning was assumed rather than checked. Any later
  figure here is measured from a pass or stated as an estimate with its derivation shown.
  Nothing about the band's depth changes: 0.25% was chosen because 2.5% was 69 hours, and at the
  corrected size 2.5% is 90 hours, so the decision is more right than it was, not less.

### D-148 — Band 1 lost its sixth cell to a spot reclaim; the five that survived are reusable and the skip is now implemented
- **Date:** 2026-10-17
- **Task:** A1.6
- **Context:** Band 1 launched on `i-0d81555e994423a79`, `m6i.2xlarge` spot, at 18:32 UTC. The
  corpus pass rebuilt the sample, `verify_rebuilt` confirmed it byte-identical to the staged
  manifest, and five of the six cells completed and published. At 23:15:04 the instance was
  terminated with `StateTransitionReason: Service initiated` — AWS-initiated, which is how a
  reclaim reads as against the `User initiated` that `AGENTS.md` records for a shutdown or a
  manual termination. About 4h45m at spot, roughly $0.55.
- **What was lost and what was not.** Only the `s7.5 cov2` cell, the most expensive in the grid.
  The other five are in the result object because the band publishes per cell rather than at the
  end, which is the design `AGENTS.md` demanded after the runs that published nothing in four
  hours. That part worked.
- **The defect the reclaim exposed, which is worse than the lost cell.** `CellKey`'s docstring has
  promised since it was written that a cell "is skipped if its artefact already exists", and
  **nothing implemented it**. The band rewrites one result object on every publish, so a re-run
  would have rebought all five surviving cells over about four hours *and then overwritten them
  with the single new cell* — losing paid work irreversibly, in a bucket where an overwrite
  destroys the earlier object. The reclaim is what surfaced it; the defect was there from the
  first commit of the band mode and would have fired on any interruption.
- **Decision:** the skip is implemented rather than the docstring softened. `cell_from_dict`
  rehydrates a published cell and refuses one whose slug contradicts its own fields, since a cell
  is reused on the strength of its slug and a disagreement would skip the wrong one.
  `--resume-band-from` reads an earlier `band.json` and reuses its cells for the same band and
  shard, after checking they searched the same record count — a different target is not a
  resumable run. The property that makes it safe is asserted directly: five published cells plus
  one new one give the same combined result as six computed in one run.
- **What this says about spot for this arm, and what it does not.** One reclaim in one run is not
  a rate, and the cost of this one was about $0.55 and one cell rather than the whole band, so
  nothing here argues for on demand. What it does argue is that **per-cell publishing without a
  resume is only half a design** — the publishing bought the five cells and the missing resume
  would have thrown them away. D-134's band 2 is six launches of about 15.8 hours each, where an
  interruption is likelier and a rebought cell costs far more, so the resume matters more there
  than here.
- **Rejected:** Re-running the whole band — four hours and about $0.55 to recover one cell, when
  five are already published and verified against the same target. Reporting band 1 from five
  cells and dropping `s7.5 cov2` — the sensitivity sweep is the only check on whether the rate is
  a property of the filter or of our aligner settings (D-109), and five cells leave `s7.5` with
  one reading of three. Switching band 2 to on demand on the strength of one reclaim — one
  observation, and the resume is the cheaper answer.
- **Consequence:** the missing cell is a resumed launch of about 50 minutes and roughly $0.10,
  and band 1 is not a result until it lands. `AGENTS.md` gains the general form of this: a
  per-cell publish is only half a design, and the half that reads it back is the half that gets
  forgotten, because nothing exercises it until something fails.

### D-149 — The measured cost is 0.996 core-min/Mb, 2.74x cheaper than the single-genome figure
- **Date:** 2026-10-18
- **Task:** A2.4
- **Context:** D-117 measured geNomad at 2.73 core-minutes per Mb on one complete, gene-dense
  *E. coli* K-12 assembly, and every band price since has rested on it. D-145 made the first band
  0.25% precisely because that figure was a one-genome extrapolation onto a corpus of draft
  assemblies, where gene density, contig count and per-call overhead all differ. This is the
  measurement it was run to get.
- **What was measured.** Evo 1's `stage1_gtdb`, 0.25% by genome hash: **375 genomes, 32,669
  contigs, 699,031,198 bases**. `genomad annotate` plus `find-proviruses` ran from 00:12:14Z to
  01:39:07Z — **87 minutes wall on 8 vCPU, 11.6 core-hours — 0.996 core-minutes per Mb.**
  **That is 2.74 times cheaper than D-117's figure**, and in the direction that makes the task
  affordable rather than the one that kills it. Draft assemblies are less gene-dense than a
  finished reference, which is the obvious explanation and is not established by this
  measurement; what is established is the rate.
  The sampling also reproduced exactly: an earlier instance, separately launched, sampled the
  same 375 genomes and the same 699,031,198 bases. D-078's design asks for membership to be a
  property of the record id and the seed alone, and that is now demonstrated across two machines
  rather than argued.
- **Decision:** 0.996 core-min/Mb is A2.4's working rate, measured, superseding D-117's 2.73 for
  every price from here. Against D-147's corrected 634,000 Mb corpus:
  **0.25% = 26 core-hours, ~3.3 wall hours. 2.5% = 263 core-hours, ~33 wall hours, about $7 on
  spot.** Both are per detection pass, and D-150's de-duplication is what makes "per detection
  pass" the same as "per band" rather than a third of it.
  D-117's figure stays on the record rather than being amended: it was correctly measured on what
  it was measured on, and the gap between it and this one is the whole argument for calibrating.
- **Rejected:** Treating the 2.74x as a reason to go straight to a census. 29,000 core-hours
  becomes 10,500 at the measured rate, which is still far beyond the ceiling and the budget.
  Reporting the rate without the sample that produced it. A rate from 375 genomes of one release
  is not yet known to hold for Evo 2, whose component is tar-packed and differently assembled;
  the band measures that too and the figure is revised if it differs.
- **Consequence:** The band did what D-118 designed it to do, and the answer changed the plan in
  the cheap direction. 2.5% is now an afternoon and $7 rather than three days and $13-18, so the
  depth question goes back to the project owner with a measured number behind it for the first
  time.

### D-150 — Correction to D-146: the 187K is counted in UniProtKB, not UniRef, and the published text says so
- **Date:** 2026-10-18
- **Task:** A1.8 (and a correction A1.6 must act on)
- **Context:** D-146 reported the select-agent seed set at 1,079,124 UniRef100 clusters against
  a published 187K, attributed 98.5% of the *taxon* expansion to the avian influenza entry, and
  predicted that entry would dominate the clusters too. The attributed re-run settled it and
  the prediction was wrong. By clusters the set is broad-based: *Burkholderia pseudomallei*
  331,065 (30.7%), avian influenza 273,715 (25.4%), *Ralstonia solanacearum* 158,953,
  *Xanthomonas oryzae* 71,777, *Bacillus anthracis* 49,623 — the top five are 82%. Taxon count
  and cluster count are different quantities, and the inference between them was unfounded:
  bacteria carry few taxa and thousands of sequenced strains each.

  **The reconciliation gap is not a reading problem at all.** ESM3's version of record,
  §A.6.1, p47: "To create the Select Agents Denylist we identify all sequences **in UniProt**
  belonging to organisms on the Select Agents and Toxins List (114). This process gives us 147K
  non-viral sequences and 40K additional viral sequences." The 187K counts UniProtKB sequences.
  A1.8 counts UniRef100 clusters. The two numbers were never comparable, and the whole 5.8x is
  that.

  Their stated method, executed directly against UniProtKB for the listed organisms and their
  strains, gives **140,591** against the published 187,000 — 0.75x, where the UniRef100
  comparison was 5.8x. The residual is unremarkable: the UniProt release differs from the one
  in force, and their treatment of toxin-producing organisms is unstated (D-137).
- **Decision: the seed set stands; the reconciliation target is replaced.** The UniRef100 set is
  not an attempt to reproduce their denylist object — it is the query set for searching the
  staged corpus, built that way because UniProtKB is not staged and because cluster members
  catch material a representative-only set misses (D-092). Breadth is the conservative choice
  for an audit. What was wrong is checking it against a figure that counts something else.
  `reconcile` therefore compares against the UniProtKB-level count of the same reading, and
  reports the UniRef100 total as the query set's size rather than as a candidate for the
  published figure. The one-line caveat already in `reconcile`'s output — "compared against
  UniRef clusters, not UniProtKB entries" — was correct and far too quiet to stop a worker
  building a hypothesis on top of it; a caveat that does not change the number it qualifies is
  not a safeguard.
- **The strain-descent hypothesis is withdrawn before it was run.** Faced with the gap, this
  task reasoned that ESM3 might have matched listed species without descending to strains, and
  priced a pass to test it. The arithmetic was sound — UniProtKB species-only counts predicted a
  7.5-8.0x reduction, and the effect sorted exactly where the mechanism says it should
  (*Xanthomonas oryzae* 255x, *Francisella tularensis* 186x, against *Bacillus anthracis* 1.1x
  and Ebola 1.0x). It was also a reading chosen because it would close a gap, which is the thing
  §B1 step 0 and AGENTS.md both warn against, and it was unnecessary: one sentence in the
  methods appendix names the database. The launch was not spent, because the project owner asked
  whether the published material already answered the question. It did.
- **A1.6 has the same defect and does not yet know.** Its viral arm reconciles 3,159,223
  UniRef100 viral-seeded clusters against ESM3's stated ~4M and reads the closeness as
  validation of the reconstruction (D-100 and its state block). The same paragraph of the same
  appendix says that figure is counted the same way: "we identify ∼4M sequences that are
  annotated as viral in UniProt". So that comparison is also UniRef clusters against UniProtKB
  sequences, and its agreement is a coincidence of scale rather than evidence. **This does not
  invalidate A1.6's seed set or the band run now in flight** — the seed set is a query set there
  too — but the "roughly 4M validates the reconstruction" claim must come out of the write-up,
  and A1.6's state block records a validation target that it does not have. Flagged in that
  task's file rather than only here.
- **What this costs, stated rather than buried.** Phase A loses a validation it believed it had
  for both arms. Neither reconstruction can be checked against a published size, because the
  only published sizes are of a different object; the available check is to execute the stated
  method against UniProtKB, which is what the 140,591 above is, and that validates the *reading*
  rather than the seed set. Under-specification is data (§A0), and "the paper's only stated
  denylist sizes cannot validate any corpus-level reconstruction" is a finding of exactly the
  kind §A0 asks for.
- **Reference (114) settles nothing further, and that is worth recording.** It is the live CDC
  summary page, dated 2024 and undated on its face — the page D-138 already assessed and
  declined in favour of the CFR at 2024-06-01. The citation confirms D-138's reasoning rather
  than changing it.
- **Rejected:** Rebuilding the seed set from UniProtKB to match their object exactly — it would
  reproduce their denylist and then search the corpus with a strictly narrower query set, which
  makes the audit less likely to find surviving material; the error would run in the direction
  that flatters the safeguard, which §2 forbids. Running the no-descent pass anyway as a
  sensitivity — it tests a hypothesis the text has already answered, and an hour spent
  confirming a withdrawn guess is an hour not spent on the scoring pass. Leaving D-146 standing
  with a correction appended inline — it is append-only, and D-146's headline claim is wrong
  rather than incomplete.

### D-151 — Detection is cached per release and component, because only the route varies by reading
- **Date:** 2026-10-18
- **Task:** A2.4
- **Numbering:** appended as D-150 and renumbered to D-151 on 2026-10-18. A1.8's D-150 was already on `main`; this entry was cited from nothing, so it is the cheaper to move. This is the second time A2.4 has done this — the number was written into the heredoc before the headings were re-read, which is the one thing `AGENTS.md`'s rule exists to prevent.
- **Context:** The first band at 0.25% ran overnight and produced, in eight hours, the charitable
  reading for both releases and nothing else. Watching it showed why: `tools/detect_proviruses.py`
  looped over A1.4's manifests and did the whole detection inside that loop — read the corpus,
  sample, run geNomad, search the registries — once per manifest. Evo 1 appears in three readings
  and Evo 2 in three, so that is **six detection passes where two would do**.
  The duplication is pure. The sampled genomes, the provirus calls and the profile hits are
  properties of the release and the component; **the only reading-specific part is the route** —
  `out_of_scope` under charitable and literal, where no rule reaches GTDB, and
  `retained_by_design` under strict's wildcard scope.
- **Decision:** Cache the detection on `(release, component)` and apply the route per manifest.
  The cache holds route-free hits, so a route can never be stamped onto a reading it did not come
  from; a reused source row carries `reused: true`, so a reader can tell a measured row from a
  carried-over one; and the concordance travels with the cache for the same reason the hits do.
  The reuse branch was **exercised before launch** rather than trusted: a local probe over Evo 1's
  three readings ran geNomad once and reused it twice, which is the behaviour and not just the
  code path.
- **Rejected:** Deriving the literal and strict tables from the charitable ones by hand. For GTDB
  the charitable and literal routes are identical, so literal's tables would be a copy — but
  `AGENTS.md` requires every number to trace to an artefact a pipeline produced, and a table
  assembled by editing another table is exactly what that forbids.
  Keeping the duplication and buying a bigger budget. The four remaining manifests of the first
  band would have cost about eleven hours and produced no measurement that the first two had not
  already made.
  Letting the running band finish. It had roughly eleven hours of work left against eleven and a
  half hours of its own shutdown timer, with the VIBRANT arm uncounted, so it would have been cut
  mid-manifest having spent the night on relabelling.
- **Consequence:** A 0.25% band over both releases is about seven hours including setup rather
  than about nineteen, and a 2.5% band is about 33 wall hours rather than a hundred. The
  arithmetic that made 2.5% look unaffordable in D-144 and D-145 was measuring a pipeline doing
  three times the work it needed to; with D-149's measured rate and this fix, the depth question
  is open again on much better terms.
  The first band's charitable results are preserved at
  `corpora/results/a2-4/band1-run1-20261018/` rather than being overwritten, because D-149 cites
  their numbers and the corpus bucket has no delete.

### D-152 — The taxonomy-unplaced share is 11.8% measured, not A4.2's 36%; D-141's conclusion stands on the measured figure
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** D-140 and D-141 both reason about what to do with corpus records the pinned
  taxonomy cannot place at family rank, and both took the magnitude of that set from A4.2 —
  "given A4.2's 36%, the unplaced set is expected to be large". A4.2 measured a different thing:
  the fraction of *genomes the denylist targets* that its taxonomy tool fails to place. Band 1
  has now measured the quantity those entries actually depend on, over shard 0's 1,097,174
  records: **129,113 unplaced, 11.8%**.
- **Decision:** the figure is replaced wherever those entries reason from it, and **both
  conclusions stand unchanged**. D-140's singleton treatment and D-141's refutation of the
  pooling argument do not depend on the share being large — D-141's point is that a pooled
  stratum contributes `(A - r*B)^2`, which is unstable in either direction whatever its size, and
  that singletons contribute the binomial term, which is the honest statement that those records
  carry no family information. A smaller unplaced set makes the choice matter less, not
  differently.
- **What it does change.** The design effect is diluted by exactly the unplaced fraction, so at
  11.8% rather than 36% the realised design effect is *higher* than those entries implied and the
  intervals correspondingly wider relative to binomial. Band 1's published cells report the
  realised figures directly, so nothing is inferred from this entry; it exists so a reader
  checking D-141's arithmetic is not working from a borrowed number.
- **Rejected:** Leaving the 36% in place as "the order of magnitude" — it is not this
  measurement, it is a different quantity from a different task, and §7's adversarial reader
  checks the provenance of a number before its plausibility. Re-deriving D-141's comparison at
  11.8% before band 1 completes — the entries' conclusions are insensitive to the share, and the
  measured intervals ship with every cell.
- **Consequence:** the write-up cites 11.8% from band 1 for this quantity and A4.2's 36% only for
  A4.2's own. One general point: both figures are about "things the taxonomy cannot place", which
  is what made the substitution feel safe, and they are not the same denominator.

### D-153 — Band 1 is complete, and the sensitivity sweep it paid for answers the question it was bought for
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** D-109 bought the three-sensitivity sweep for one reason, stated at the time: `-s` is
  our parameter rather than the publisher's, so the sweep is what separates a property of the
  filter from a property of our instrument. Band 1 is now complete — nine groups over shard 0's
  1,097,174 records, from 31,381 seeds (1/100), published across two launches and a resume
  (D-148). Every figure is a lower bound (D-134).
- **The answer, which is the finding.** At the charitable reading's 0.70 identity cut the figure is
  **almost invariant to our settings**: 0.6537% to 0.6844% across all nine cells, a relative spread
  of 4.7%. The any-identity figure over the same cells runs 1.5473% to 4.0975% — a factor of 2.6.
  So the sub-threshold tail is largely a property of our instrument, and **the quantity the
  charitable reading actually turns on is a property of the filter**. That is the cleanest form
  the sweep's result could have taken, and it is why the sweep was not optional.
- **Decision: the headline figure for this band is the banded one at 0.70, not the any-identity
  rate.** Both are published and both are lower bounds, but a single number quoted from this band
  is the 0.70 figure, because the any-identity rate is the one that moves with `-s` and would
  misattribute our aligner's reach to the filter's failure. Writing it up the other way round
  would be the more alarming presentation and the less defensible one.
- **The result does not balance on the inferred threshold as much as feared.** D-105 parameter 6
  separated the 0.70-0.75 band because 8.07% of hit *rows* fell in it. Measured per record at
  `-s 5.7 cov1`: of the 7,509 records at or above 0.70, only **255 (3.4%)** sit in 0.70-0.75,
  while **5,754 (77%)** are at 0.90 or above. The identity distribution is bimodal — a large
  sub-threshold tail, a trough, then a spike of near-identical matches — so the inferred cut falls
  in the trough rather than through the mass. The banding stays, because that is now a measured
  reassurance rather than an assumption.
- **D-109's refusal of a binomial interval is vindicated by a wider margin than it claimed.**
  It argued a design effect of 40 would make the honest interval six times the binomial one.
  Measured: **238.8 to 557.0** across the nine cells, so the honest intervals are 15 to 24 times
  binomial. A binomial interval here would have been wrong by more than an order of magnitude,
  and the design effect falls as sensitivity rises, which is itself consistent with the extra
  hits being spread rather than clumped.
- **What this is not.** Not a corpus-level claim: it is 0.3125% of the corpus, UniRef100 only,
  from 1% of the seed set, and MGnify90 is unscored (D-133 names that gap as Phase A's, not this
  task's). Not validated against any published size (D-150). Not a rate — a bound, in the
  direction §2 requires.
- **Rejected:** Quoting the any-identity rate as the headline — it is the number that moves 2.6x
  with a parameter of ours. Dropping the any-identity figures — the literal reading's threshold is
  undetermined (D-107), so the pass may not assume 0.70 is the floor of interest. Treating the
  0.70 invariance as grounds to stop sweeping in band 2 — one band at one depth, and the sweep is
  what made the claim available.
- **Consequence:** band 2's value is now mainly in the seed axis rather than the sensitivity axis,
  since the 0.70 figure is already stable across settings; what band 2 buys is how far the bound
  rises as the seed sample deepens, which is the only evidence available about the gap to a
  full-seed rate. The write-up leads with the 0.70 bound, reports the bands beneath it, and states
  the design effect, because a reader who assumes binomial will understate the interval by 15x.

### D-154 — Correction to D-153: band 1's figure is not a clean lower bound, because the seed set implements only the first clause of the rule
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** Raised by the project owner asking whether the matching material might simply be
  the parts of viruses that are not distinctive — shared with hosts, ubiquitous, uninformative.
  Checking rather than reasoning: `src/amazebio/seeds.py` says so in its own module docstring,
  and D-153 failed to carry it into the result.

  ESM3's viral denylist has **two** clauses: a sequence qualifies if it is (a) annotated as viral
  in UniProt **and** (b) "align[s] almost exclusively to other viral sequences in UniProt". Clause
  (b) is what excludes viral sequence that also resembles host protein. The seed set implements
  **clause (a) only** — clause (b) needs its own alignment pass and its own reading of
  "almost exclusively", which the source does not quantify. The seed set is therefore a
  **superset** of the denylist the source describes.
- **The error in D-153.** It states "every figure is a lower bound (D-134)" without qualification.
  That holds for the seed-*sampling* axis and not for the seed-*construction* axis. Two errors run
  in opposite directions:
  - **1/100 of the seeds → understates.** A record matched by an unsampled seed is not counted.
  - **Annotation-only seeds → overstates.** A record matching a viral sequence that clause (b)
    would have excluded is counted as surviving material the filter should have removed, when the
    filter never undertook to remove it.

  So band 1's figure is a floor in one respect and a ceiling in another, and **the net direction
  is not known**. "At least 0.6844%" is not a supportable phrasing and must not appear in the
  write-up. The honest form states both axes and claims neither direction.
- **Decision:** D-153's headline stands as a *measurement of the annotation-only reading*, not as
  a bound on the filter's failure rate. Every figure from this band is labelled with the reading
  it implements. The `lower_bound` flag in the artefact remains correct for what it was built to
  mark — the seed sample — and the write-up may not read it as a claim about the whole result;
  a flag that means one axis and is read as meaning the result is the D-150 failure again, one
  level down.
- **What would settle it, and it is not expensive.** Clause (b) is a restriction *on the seed
  set*, applied before the corpus pass: for each candidate seed, align it against UniProt and keep
  it only if its matches are almost exclusively viral. That is a seeds-against-UniProt pass, not a
  seeds-against-corpus pass, and A1.8 is staging UniProtKB 2023_02 permanently at
  `corpora/uniprotkb/2023_02/`, so it becomes an in-region job. The reading of "almost
  exclusively" needs its own entry and must be fixed before the result is inspected, per §2.
- **The owner's other question is not answered by this band at all.** Whether the matched records
  are genuinely viral material or host protein that merely resembles it is a question about what
  the records *are*, and this band only measures that they align. The 77%-at-≥0.90 figure in D-153
  rules out distant family resemblance; it does not distinguish a captured host gene from a viral
  one. That is the survival-route and homology-class work (A2.*, B3.*), and D-153 should not be
  read as bearing on it.
- **Rejected:** Reporting band 1 with the "at least" phrasing and a caveat further down — D-150
  established in this same task that a caveat which does not change the number it qualifies is not
  a safeguard. Narrowing the seed set now and rerunning — clause (b) is worth implementing, but
  band 1's measurement of the annotation-only reading is still the measurement of a reading, and
  §A0 treats the spread between readings as the result. Dropping the annotation-only arm once
  clause (b) exists — the spread between the two is exactly what §A0 asks for.
- **Consequence:** the write-up reports band 1 as the annotation-only reading and reports the
  clause-(b) reading beside it once it exists; the difference between them is a §A0 finding about
  how much of the apparent leakage rests on an unquantified phrase in the methods appendix. Band 2
  is not the next priority — clause (b) is, because it changes what the existing numbers mean
  rather than making them more precise.

### D-155 — A2.4's first band, complete: viral families survive as prophage in genomes the filter never examined
- **Date:** 2026-10-18
- **Task:** A2.4
- **Context:** The 0.25% band (D-145) over both releases, on the de-duplicated build (D-151),
  `i-0bbdd4b09995095ed`, 05:10Z to 10:38Z — **5 hours 28 minutes**, self-terminated with
  `run complete`. Twelve detection tables and six concordance artefacts, at
  `corpora/results/a2-4/`.
- **The result.** Every detection carries `element_kind: prophage`, `estimate_kind: lower_bound`,
  and a route that follows the reading rather than the biology:

  | release | genomes | bases | proviruses | Pfam viral | RVDB-prot |
  |---|---|---|---|---|---|
  | Evo 1 (v214.1) | 375 | 699 Mb | 128 | 203 / 1,719 = 11.8% (10.4-13.4) | 90 / 13,679 = 0.66% (0.54-0.81) |
  | Evo 2 (v214.1 + 220.0) | 300 | 946 Mb | 178 | 251 / 1,719 = 14.6% (13.0-16.4) | 153 / 13,679 = 1.12% (0.96-1.31) |

  **What this is.** Viral protein families, inside integrated elements, inside bacterial genomes
  that the filter's own rules never reached — `rules=0, uniform=True` for GTDB in every reading
  (A1.4). It is `out_of_scope` under the charitable and literal readings and
  `retained_by_design` under strict's wildcard scope, **with identical counts**, because the
  detection is the same and only the reading's scope differs. That is D-007's first-class route
  arriving as measurement rather than as an argument from published methods.
  **What this is not.** Not a conformance failure: no rule was broken, because no rule applied.
  Not an estimate of the population: a lower bound twice over (D-113, D-115), so the true figures
  are at least these.
- **The concordance (D-114), per release:** Evo 1, 40 records, both 6, geNomad-only 0,
  VIBRANT-only 1, neither 33, **kappa 0.908 (0.731-1.000)**. Evo 2, 28 records, both 6,
  geNomad-only 1, VIBRANT-only 3, neither 18, **kappa 0.652 (0.337-0.968)**.
  The two instruments agree strongly on Evo 1 and only moderately on Evo 2, and the disagreement
  is **directional**: VIBRANT calls elements geNomad does not, three times to one. Reported as
  direction rather than resolved, per D-114. A2.4's headline comes from geNomad, so on Evo 2 it
  is the more conservative of the two instruments — the bound is if anything safer there, not
  weaker.
- **Decision:** This is A2.4's reportable result at 0.25%. Every Done-when criterion is met: hit
  tables with route attribution, two-tool concordance on a documented nested subsample, and
  parameters and versions in the `run.json` and the pins. The cache's correctness was checked
  rather than assumed — literal matches charitable exactly on the shared route, strict carries
  `retained_by_design` with the same counts, and the four reused source rows say `reused: true`.
- **Rejected:** Reporting the Pfam and RVDB fractions together. Their membership criteria come
  from different authorities and D-022 forbids pooling the denominators; the 11.8% and the 0.66%
  are answers to different questions about the same detections.
  Calling the Evo 1 / Evo 2 difference a finding about the filters. Evo 2's component is a
  superset of Evo 1's (D-130) and its sampled genomes are larger on average, so more families is
  the expected direction and this band does not separate that from any difference in filtering.
- **Consequence:** Phase A has a measured prophage route for both releases, which A3.2 can
  cross-tabulate against A2.1's profile hits — same registries, same thresholds, different
  detector and kind, so the merge is a join. The depth question goes to the project owner: at
  D-149's measured rate with D-151's de-duplication, 2.5% is about 33 wall hours and $7, which
  exceeds one instance's window and so needs a longer timer or per-object resumability.

### D-156 — Correction to D-154: the annotation-only seed set is the strict reading's, by design; band 1 mixed two readings
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** D-154 treated the seed set's omission of clause (b) — "align almost exclusively to
  other viral sequences in UniProt" — as a gap to be closed, and named closing it the next
  priority. Reading `policies/specs/` before implementing it shows that is wrong, and that the
  readings were fixed on this exact point by D-015.
  - **`esm3-open-strict.yaml` deliberately drops the clause**, in its own words: "Drop the
    'almost exclusively' narrowing: everything annotated as viral in UniProt seeds the denylist,
    which is what 'data related to viruses' says." So the annotation-only seed set **is** the
    strict reading's seed set. It is not a defective charitable seed set.
  - **`esm3-open-charitable.yaml` keeps the clause and leaves it unquantified**, also explicitly:
    "'Almost exclusively' stays unquantified and is not reinterpreted here — the charitable
    reading supplies the one number it can argue for from the text, and leaves the other gap
    visible."
- **So the real defect in band 1 is a labelling error, not a missing computation.** It ran the
  **strict reading's seed set** against the **charitable reading's 0.70 threshold**, and D-153
  reported the 0.70 column as "the charitable reading". That combination is **not one of the three
  readings D-015 fixed**. The arithmetic is sound and the artefact is fine; what was wrong is the
  name attached to the column.
- **Decision — three parts.**
  1. **Band 1 is relabelled, not rerun.** Its nine groups are the strict seed set at three
     identity cuts, three coverage readings and three sensitivities. The 0.70 column is "the
     strict seed set at the charitable reading's threshold" and the any-identity column is the
     **strict reading proper**, since strict removes on any detected hit. On that reading band 1
     already reports a reading as fixed: ≥1.5473% to ≥4.0975% depending on our settings.
  2. **"At least" is restored for the strict reading, and only there.** Against the strict seed
     set the only sampling error is the 1/100 seed sample, which understates. D-154 was right that
     the figures are not clean bounds *for the charitable reading* and wrong to generalise it:
     for the strict reading they are clean lower bounds.
  3. **Clause (b) is not implemented.** Quantifying "almost exclusively" would add a number D-015
     deliberately declined to invent, and §A0 treats the unquantifiable gap as the finding. The
     charitable reading's seed set is **not executable**, and that is a result to report rather
     than a problem to solve. If the project owner later wants it quantified it is a **fourth**
     reading with its own entry, not a correction to the charitable one.
- **The owner's question is answered by the source, not by a pass.** Asked whether the matching
  material is simply the undistinctive parts of viruses, the charitable spec already records the
  authors' own consequence: because clause (b) requires near-exclusive viral alignment, "sequence
  with cellular homologs never entered the seed set, so virus-associated protein families with
  cellular relatives are outside this filter by construction, at any threshold." So under their
  own rule the answer is the reverse of the worry — the shared-with-hosts material was never
  targeted, which is why the strict reading exists and why §B is where that question is settled.
- **Rejected:** Implementing clause (b) as D-154 proposed — it invents the number D-015 declined,
  and it would have been spent before anyone noticed the readings already covered this. Rerunning
  band 1 — the computation is right. Leaving D-154 standing with this appended inline — the log is
  append-only and D-154's headline recommendation is wrong rather than incomplete.
- **Consequence:** A1.6's deliverable is the strict reading's surviving-record figures plus the
  finding that the charitable reading's seed set cannot be executed from the published text. One
  process point, the third of its kind in this task: D-150 was a quiet caveat in code, D-154 was a
  quiet qualifier in a docstring, and this was a decision already recorded in `policies/specs/`
  that nobody re-read. **Before treating a gap as work, check whether a fixed reading already
  governs it.**

### D-157 — The select-agent denylist cannot be reproduced from the regulation at ESM3's own release; the viral one can
- **Date:** 2026-10-18
- **Task:** A1.8 (the viral half is A1.6's to use)
- **Supersedes in part:** D-150, whose residual was called "unremarkable" and was not.
- **What was measured.** UniProtKB at release **2023_02** — the release ESM3 names, since UniProt
  numbers UniProtKB and UniRef together — read end to end from the staged archive, 249,877,975
  entries, both members matching the publisher's own release statistics exactly
  (569,516 and 249,308,459). 2.64 hours. The reading is D-137's, unchanged.

  | reading, at 2023_02 | UniProtKB sequences | vs published 187,000 |
  |---|---|---|
  | named organisms **and their strains** | 1,277,073 | 6.8x |
  | named organisms only | 321,669 | 1.7x |
  | named only, excluding avian influenza | 229,787 | 1.2x |

  **The published figure sits below every reading we can construct from the regulation.** The
  most conservative — exact listed taxa, no descent — is still 1.7x it.
- **Why the release mattered so much, and why the earlier check was misleading.** D-150 ran the
  same procedure against the current release and got 140,591, which is 25% *under* 187,000.
  UniProtKB has since lost 40% of its entries to redundant-proteome removal, and that loss falls
  hardest on the over-sequenced bacteria this list is largely made of — so the current-release
  count understates by far more than 40% for exactly these taxa. Measured at the release in
  force, the same reading overshoots sixfold. **A current-release count cannot distinguish a
  correct reading from a wrong one here, and D-150's "comfortably within release drift" was an
  assertion where a measurement was available.**
- **Strain descent is the largest single factor and still does not explain the gap.** Descending
  named organisms to their strains multiplies the count 4.0x. D-150 withdrew that hypothesis on
  the grounds that the methods appendix names the database; that was right about the database
  and wrong to treat descent as settled with it, and the dismissal rested on a current-release
  comparison that had already had the strain proteomes deleted out of it — correcting for the
  drift twice. Descent is now measured rather than hypothesised, from the per-taxid detail in
  the artefact, with no second pass.
- **The contrast with the viral denylist is what makes this a finding rather than a loose end.**
  The same pass counted the Viruses superkingdom at the same release: **5,379,748** against
  ESM3's stated ~4M, a 1.34x gap. For *that* list the paper describes a second step — sequences
  must also "align almost exclusively to other viral sequences in UniProt" — and a 26% reduction
  from a specificity filter is an ordinary consequence of it. "Almost exclusively" is
  unquantified, which §A0 already records as an open question.

  **No comparable step is described for the select-agent list.** Its stated procedure is "all
  sequences in UniProt belonging to organisms on the Select Agents and Toxins List", with
  nothing between the list and the count. So the viral figure is consistent with the stated
  method and the select-agent figure is not, at minimum by 1.7x and on the literal reading by
  6.8x.
- **What may be concluded, and what may not.** This is a gap between a stated method and a
  reported result, both now measured in the same units — UniProtKB sequences at the release the
  paper names — so it is not the apples-to-oranges artefact D-150 corrected. Either the denylist
  omitted material the stated procedure would include, or the description is incomplete; the
  published text does not let us choose, and A1.8 will not guess. It is **not** evidence about
  how much denylisted material survived into the corpus: that is the scoring pass, and this
  figure bounds the denylist's size rather than the filter's reach.
- **This validates the reading, not the seed set.** A1.8's UniRef100 query set counts a
  different object and nothing published can validate it (D-150 stands on that point). What is
  checked here is whether the regulation's 70 entries were resolved to the organisms the lab
  resolved them to, and the answer is that no resolution we can construct reproduces their
  total.
- **Consequence for A1.6.** Its "roughly 4M validates the viral seed set" claim is still wrong
  for the reason D-150 gave — 4M counts UniProt sequences, its 3,159,223 counts UniRef100
  clusters. But it now has the comparison it actually wanted: 5,379,748 taxonomically viral
  UniProtKB sequences at 2023_02, against a stated ~4M after a specificity filter. That checks
  A1.6's *reading*, and it passes in the sense that the difference has a described cause.
- **Rejected:** Re-running the pass with descent disabled to measure the no-descent reading —
  the per-taxid counts in the artefact answer it exactly and for nothing, and a 2.6-hour pass to
  re-derive a number already in hand is not a measurement, it is a habit. Reporting 1,277,073 as
  "the denylist at the correct release" without the decomposition — it is the literal reading's
  figure and 60% of it is one entry (avian influenza, 766,512), which an aggregate hides.
  Choosing the 229,787 reading because it is closest to 187,000 — fitting a reading to a target
  is what D-150 had to withdraw a hypothesis for, and the bracket is the honest output.

### D-158 — The clause-(b) exposure is measured descriptively from the staged UniRef90 and UniRef50 tiers, with no threshold invented
- **Date:** 2026-10-18
- **Task:** A1.6
- **Numbering:** appended as D-157 and renumbered to D-158 on 2026-10-18. A1.8's D-157 was
  already on `main` when this was written, so every track that pulls sees that number as
  A1.8's; and renumbering an entry another track is actively working from would create the
  ambiguity the rule exists to prevent. Note that the stated tie-breaker points the other
  way — this entry is cited from `src/`, A1.8's only from task files — but those citations
  are all in unmerged files on one branch and moved in a single pass. The commits
  "A1.6: D-157 — measure the clause-(b) exposure, inventing no threshold" and
  "A1.6: the exposure measurement, and one pass implementation rather than two" refer to
  this entry.
- **Context:** The project owner asked whether band 1's hits are unique to viruses. D-156 settled
  the half of that question the source answers: clause (b) — "align almost exclusively to other
  viral sequences in UniProt" — is deliberately dropped by the strict reading, so the
  annotation-only seed set is the strict reading's own seed set and not a defective one, and
  quantifying the clause would invent the number D-015 declined to invent.

  What D-156 leaves unmeasured is **how much of band 1's figure rests on seeds that clause (b)
  would have excluded.** That is answerable descriptively, from bytes already staged, without
  choosing a cut — so it is neither the fourth reading D-156 declined nor a correction to the
  charitable one.
- **The measurement.** UniRef90 and UniRef50 are the publisher's own homology groupings at 90%
  and 50% identity, both staged for 2023_02 beside the UniRef100 tier the seed set came from.
  For each seed — a UniRef100 cluster in the strict seed set — ask whether the UniRef90 cluster
  containing it has any non-viral member, and separately whether its UniRef50 cluster does. A
  seed whose homologues at 50% identity include cellular sequence is one clause (b) would
  plausibly have dropped.
- **Fixed now, before any result exists, per §2 and the non-negotiables.**
  1. **Two tiers, reported separately, as a two-point curve.** No single blended number, no
     interpolation between them, no chosen cut. A seed is *described* at two fixed identities,
     never classified as inside or outside the denylist.
  2. **Viral means a descendant of taxid 10239**, over the representative and every member,
     identical to `UniRefEntry.is_viral_seeded`, under the already-pinned
     `taxdmp_2023-04-01.zip`. The exclusivity test reuses the seed set's own test so the two
     cannot disagree.
  3. **Two denominators, both reported.** Over all realised band-1 sample seeds, and over those
     band-1 sample seeds that actually produced a hit record. The second is what bears on the
     headline; the first is what says whether the hit-producing seeds are unusual among the
     sampled ones.
  4. **A seed with no placed taxid is a third outcome**, counted and reported as its own share
     rather than folded into either — D-152's lesson, one level down.
  5. **Reported by survival route and homology class only, never by organism or taxon** (D-125),
     with per-seed detail in the disclosure package only.
- **Why these bytes rather than an alignment pass.** The tiers are publisher-computed,
  contemporaneous with the release the seed set was built from, already pinned and already
  staged, and they introduce **no parameter of ours** — which is the whole reason this is a
  descriptive measurement and not a reading. An alignment of seeds against UniProt would need a
  cut on "almost exclusively", which is exactly what D-015 and D-156 refuse.
- **Three schema facts, verified against the staged bytes rather than assumed.** This task has
  now been bitten three times by a field whose meaning was taken on trust, so these were read
  before the design rested on them:
  - Every `<member>` and `<representativeMember>` in **both** tiers carries a
    `UniRef100 ID` property and an `NCBI taxonomy` property, so each tier joins to the seed set
    directly by UniRef100 id and needs no separate mapping and no reconstruction from the other
    tier.
  - The `member count` property **includes the representative** — a cluster reporting 3,252 has
    3,251 `<member>` elements — so a count taken from the elements alone is short by one per
    cluster, and the taxid scan must cover the representative block as well.
  - `uniref.xsd` is staged but cannot answer either question: properties are generic
    `type`/`value` pairs in the schema, so only the entries themselves settle what is present.
- **What this does not do, and must never be labelled as.** It is not clause (b): clause (b) is
  a condition on alignment against the whole of UniProt, and UniRef membership is a proxy for it
  at two fixed identities. It does not make the charitable seed set executable — D-156 stands,
  and that inexecutability remains the §A0 finding. It bounds the *exposure* of band 1's figure
  to the dropped clause; it does not correct the figure, and no corrected figure is to be
  derived from it. And it says nothing about whether a matched *corpus record* is viral material
  or host protein that resembles it — that is about what the records are rather than that they
  align, and D-154 assigns it to A2.\* and B3.\*.
- **Cost, and why it is in-region.** 62.73 GB plus 30.39 GB of compressed stream. Scaling D-100's
  measured full-tier pass — UniRef100 2023_02, 118.68 GB in 3,202.5 s on 8 vCPU with 7 parsing
  workers — gives about 28 minutes for the 90 tier and 14 for the 50, so roughly 45 minutes
  sequentially on one instance, about **$0.10 on spot**. Read from the session container instead
  it is 93 GB of metered egress at the 42.5 MB/s this project has measured, which is both slower
  and two orders of magnitude dearer. This is the data-movement test in `AGENTS.md`, and it
  passes it.
- **Rejected:** Implementing clause (b) — D-156, and it remains rejected; this measurement exists
  *because* clause (b) is not to be implemented. A single share across both tiers, or a share at
  one tier only — either is a threshold by the back door, which is the thing being avoided.
  Reconstructing the 50 tier from the 90 pass, which is possible since every member carries its
  `UniRef50 ID` — reading the 50 tier directly is 30 GB and no join, against a 60M-key
  aggregation held in memory for no gain. Weighting by hit records rather than counting seeds —
  a seed's hit count is a property of the corpus sample, so weighting by it would fold two
  samples into one number.
- **Consequence:** band 1's figures ship with the two-tier exposure share beside them, and the
  write-up states the exposure rather than adjusting the figure. If the share at 50% is large,
  the §A0 finding about the unquantified phrase gets quantitative support; if it is small, band
  1's strict-reading figures stand with less of a caveat attached. Both outcomes are reportable
  and the direction is not known before the pass, which is why this entry exists before it.

### D-159 — What A1.8's scoring pass measures, and how it may be reported, fixed before any result is seen
- **Date:** 2026-10-18
- **Task:** A1.8
- **Why this is written now.** §2 and AGENTS.md require thresholds, parameters and analysis
  specs fixed before results are inspected. This arm has a sharper reason than the general one:
  D-154 found A1.6 reporting a figure as a lower bound when its seed set implemented only the
  first clause of the rule, and the phrasing had to be withdrawn after the number existed.
  A1.8's seed set has a larger version of the same problem (D-157), and the honest framing is
  much easier to agree to before anyone has seen a rate.
- **What the pass does.** The reconstructed select-agent seed set — 1,079,124 UniRef100 2023_02
  clusters, `corpora/results/a1-8/select-agent-seeds-2023_02-uniref100.faa` — is scored against
  the staged 2.5% hash sample of UniRef100 2023_02 (D-122), at the fixed parameters of D-105
  and D-107: `-c 0.8`, `--max-seqs 100000` behind the saturation guard, three sensitivities
  (2.0, 5.7, 7.5) against two coverage-filtered searches recovering all three coverage
  readings — the same six cells per shard A1.6's band 1 ran, so the two arms' instruments are
  identical and only the query set differs.
- **What the resulting rate is a rate *of*, stated precisely.** The share of sampled corpus
  records that align, at or above a given identity, to a sequence **belonging to an organism
  named on the Select Agents and Toxins List as this project reads it (D-137)**. It is **not**
  the share of records the filter undertook to remove and did not.

  The gap between those two is measured, not hypothetical. At ESM3's own release the reading
  yields 1,277,073 UniProtKB sequences where they report 187,000 — 6.8x, and still 1.7x on the
  narrowest reading the regulation permits (D-157). Our query set is broader again, being
  UniRef100 clusters rather than UniProt sequences. So a matched record may be material the
  filter never undertook to remove.
- **Two errors, running in opposite directions, and neither may be dropped.** This is D-154's
  structure and it applies here with the larger term:
  - **Sampling understates.** A 2.5% corpus sample and a 1/100 seed band both miss material: a
    record matched only by an unsampled seed, or sitting outside the sampled shards, is not
    counted.
  - **A query set broader than the denylist overstates.** A record matching select-agent
    material that ESM3's denylist did not contain is counted as survival of something the
    filter should have removed, when it undertook no such thing.

  **The net direction is not known, and no figure from this arm may be phrased as a bound in
  either direction.** "At least X%" and "no more than X%" are both unsupportable. The
  supportable form names the reading, the sample and both axes.
- **What may be published, carried forward unchanged.** Counts by survival route and homology
  class, never by organism or taxon (D-125). The per-record manifest to the disclosure package
  only, at the key D-126 fixes. Not pooled with A1.6's broad-arm rate (D-108). No all-clear:
  the pass is sampled and Phase A does not state that nothing on the narrow denylist survived
  (D-133). Every figure carries the proxy qualifier A1.1 requires on ESM3 results.
- **The sizing, fixed here so the result is not quietly rescoped to fit a budget.** On D-153's
  measurement — 31,381 seeds against shard 0 at six cells, 14,852 s wall on eight vCPU — this
  arm's 1,079,124 seeds give: band 1 (1/100 of seeds) on one shard **≈1.4 h and about $0.25**;
  band 1 across all eight shards ≈11.3 h; the whole seed set on one shard ≈142 h; the whole
  seed set on the whole sample ≈1,135 h. **Band 1 on shard 0 runs first**, both as the smoke
  test and because it is the cell-for-cell comparison with A1.6's band 1 — same shard, same
  six cells, different denylist. Widening is a separate decision taken with that result in
  hand, not an assumption built into this one.
- **Rejected:** Reporting a single survival percentage for "the select-agent denylist" — it
  names a denylist this arm does not implement, and D-157 measured how far off it is. Calling
  the figure a lower bound because the sampling axis is a floor — exactly the error D-154 had
  to correct one level up, and repeating it with a larger broadening term would be worse.
  Waiting for a clause-(b)-equivalent restriction before scoring — no such clause exists in the
  select-agent procedure to implement; the gap there is unexplained rather than unapplied
  (D-157), so there is nothing to wait for.

### D-160 — Band 1's artefact keeps no identifier, so D-158's hit-producing denominator needs a re-run that emits one
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** D-158 fixed two denominators for the clause-(b) exposure share: over all realised
  band-1 sample seeds, and over those sample seeds that actually produced a band-1 hit record. It
  named the second as the one that bears on the headline, with the first as the context that says
  whether the hit-producing seeds are unusual.

  The second has no input. Both published band artefacts were probed directly:
  `band-complete.json` carries six cells and `band.json` five — so the task file's rule of counting
  `band.cells` rather than trusting the name picks the right one, and it does — and **neither
  contains an identifier of any kind.** No `UniRef100_`, no `UniRef90_`, no `MGYP`, not even a
  `query` key: 9.5 MB of per-cell, per-stratum and per-family counts. That is exactly what D-108
  and D-134 designed the broad arm to publish, a rate rather than a manifest, so the hit table and
  its `query` column never left the instance.
- **The cause, named rather than absorbed.** D-158 asserted a denominator over an artefact whose
  contents it had assumed instead of read. That is the fifth time in this task a quantity has
  rested on a field taken on trust — D-117, D-144, D-150 and D-154 were the others — and the first
  four were inherited, where this one was written here, two hours after the entry for it said to
  check the staged bytes rather than assume them. The schema facts in D-158 were checked precisely
  this way; the artefact its own denominators would read was not.
- **Decision — the re-run, authorised by the project owner at about $0.50 and four hours on spot.**
  Band 1 re-runs on the same shard with query-side emission added. To a new key: the corpus bucket
  has no `DeleteObject`, so an overwrite destroys the earlier object irreversibly, and band 1's
  existing counts stay citable as they are.
- **The emission's design, fixed before the re-run rather than after it, per §2.**
  1. **Per cell, not per band.** Coverage mode and sensitivity change which seeds produce a hit at
     all, so one band-level set would silently adopt whichever reading happened to be read last.
     Each of the six cells emits its own set.
  2. **Membership only** — the set of seeds with at least one hit record under that cell's
     reading. Not hit counts: a seed's hit count is a property of the corpus sample, and weighting
     by it would fold two samples into one number (D-158 rejected that already).
  3. **Memory stays bounded by the query set**, which is known before the run at 31,381 seeds —
     the same argument `TargetStream` already makes for `stratum_hits`. This does not reintroduce
     the unbounded per-target structure that class exists to avoid, because the bound is the band's
     seed count rather than the corpus.
  4. **The emitted ids are identifier-bearing**, so they are staged in the disclosure package
     under D-125 as amended by D-126 and never committed or published. The published figure stays
     a share by survival route and homology class.
- **What this does not touch.** The exclusivity pass in flight is unaffected: its tier-level
  non-exclusive share is over every viral-covering cluster in each tier and needs no join at all,
  which also makes it the figure comparable to A1.8's residual. And D-158's first denominator was
  never at risk, because band 1's sample is the hash rule `bucket_of(id, 100) == 0` over the staged
  seed FASTA rather than a stored list — `band-complete.json` confirms 31,381 seeds realised at a
  denominator of 100, so that set regenerates from pinned inputs without any artefact.
- **Rejected:** Amending D-158 to require only the computable denominator. It would edit a fixed
  analysis spec after seeing what the data can support, which is the thing §2 exists to forbid, and
  the tidiness of the result is exactly what should make it suspect.
  Reporting the second denominator as not executable and shipping the rest — defensible, cheap, and
  with D-156's handling of the charitable seed set as precedent, but the precedent does not
  transfer: the charitable seed set is inexecutable because quantifying "almost exclusively" would
  invent a number, where this input is recoverable for four hours and $0.50. "Cannot" would have
  been "would rather not", and §A0's standing is built on the difference.
  Deriving the second denominator from the published per-family counts. `seed_families` is a count
  and the family arrays are a corpus-side stratum; no mapping from either to a seed survives, so
  any such derivation would be an inference dressed as a measurement.
- **Consequence:** the exposure share ships with both denominators as D-158 specified, and band 1
  gains a per-cell seed-hit set that A3.3's independent reimplementation and any later clause-(b)
  work can both read. The process point is the one worth carrying: checking the inputs a spec names
  belongs in writing the spec, not in executing it, and an entry that checks one of its inputs
  carefully is not thereby an entry that checked them all.

### D-161 — The two registries' survival fractions are not comparable, and the difference is measured
- **Date:** 2026-10-18
- **Task:** A2.4 (governs A3.2 and the Phase A write-up)
- **Context:** A2.4's first band reports **11.8% of Pfam's viral families** and **0.66% of
  RVDB-prot's** surviving as prophage in Evo 1, from the same proteins. Read side by side that
  looks like Pfam being eight times more permissive, and a reader will reach for one number as
  the headline. Both readings are wrong, and the reasons are separable and measurable.
- **What was measured**, on identical input — 5,314 genes, 1,201,328 residues, 128 proviruses:
  **The denominators answer different questions.** Pfam's 1,719 is *this project's derived*
  viral subset (D-075), weighted toward well-characterised phage domains, with the blind spot
  D-083 measured. RVDB-prot's 13,679 is the publisher's clustering of the whole known
  virosphere, overwhelmingly eukaryotic viruses that **cannot** occur in a bacterial prophage.
  RVDB's denominator therefore carries a large, structurally unreachable mass.
  **There is also a real sensitivity gap, and it is not a counting artefact.** Pfam returns
  **173 detections per 1,000 genes against RVDB's 33**, a 5.2x difference. Multi-domain
  inflation is ruled out: hits per family-record pair are 1.19 and 1.16.
  **The cause is the threshold regime (D-076).** Pfam is searched at its curators' per-model
  gathering cutoffs — median 26.2, ranging 20.3 to 39.1, so a diverged family can carry a lower
  bar. RVDB's thresholds derive from one pinned E-value against a pinned Z and are therefore
  **near-constant across all 13,679 models, spanning 29.4 to 31.5**. A uniform bar cannot be
  lenient where leniency is warranted, and it sits higher on average. Median best scores, 100.5
  against 70.8, say the same from the other side: Pfam's phage domain models fit these proteins
  better because that is what they were built to recognise.
- **Decision:** The two registries are **not interchangeable instruments**, and neither
  percentage is reportable on its own.
  **Pfam's fraction is never quoted as "the fraction of viral families".** Its denominator is
  this project's reading of "viral" in Pfam, not a published universe, and any use of it says so.
  **RVDB's fraction is never quoted as a measure of how much survived.** Its denominator
  includes families no prophage could contain, so the fraction understates by an amount this
  band does not quantify.
  What is reportable: **RVDB's absolute counts** — 90 families, 177 detections — and **Pfam's
  composition**, which is a prophage parts list (`Phage_integrase` 65, `Terminase_6N` 24,
  `Phage_capsid` 24, `PhageMin_Tail` 23, `Phage_portal` 19). The composition is the evidence
  that these are integrated phage rather than scattered homology, and it does not depend on
  either denominator.
- **Rejected:** Harmonising the thresholds so the registries compare. D-076 fixed them before
  results existed and A2.1's tables were produced under them; changing them now to make two
  numbers line up is choosing a threshold for its output, which is the thing the pre-registration
  discipline exists to prevent.
  Dropping one registry. They fail in opposite directions — Pfam's universe is ours and narrow,
  RVDB's is the publisher's and far too broad — and reporting both with this entry attached is
  more honest than picking the flattering one.
  Deriving a "phage-relevant subset" of RVDB to fix its denominator. That is a real improvement
  and it is a new reading of someone else's curation, so it belongs in its own task with its own
  pre-registration, not in a footnote to this band.
- **Consequence:** A3.2 must not pool or average the two registries' fractions (already required
  by D-022, and this entry says why in measured terms). The Phase A write-up carries the
  composition and the absolute counts; any percentage it quotes names its denominator in the
  same sentence.

### D-162 — Correction to D-157: the viral residual is not clause (b)'s effect, and two independent measurements now bracket it
- **Date:** 2026-10-18
- **Task:** A1.8 (the measurement is A1.6's, from D-158)
- **What D-157 said and should not have.** It reported 5,379,748 taxonomically viral UniProtKB
  sequences at release 2023_02 against ESM3's stated ~4M, and described the 1.34x gap as "a
  1.34x gap with a described cause", with the A1.6 task note going further: the difference "is
  accounted for by a step they describe". **That is an attribution, not a measurement**, and it
  was raised by A1.6 rather than caught here.

  The residual assumes the whole gap is clause (b) — "align[s] almost exclusively to other
  viral sequences in UniProt" — and that nothing else contributes. At least two other things
  plausibly do: annotation drift between 2023_02 and whatever snapshot the lab actually read,
  and the reading of "annotated as viral" itself. A residual is what is left over, and naming
  it after one of several possible causes is the same move D-154 had to correct one level up,
  and the same move D-150 corrected when a caveat under a number failed to stop the number
  being built on.
- **The count itself is confirmed, independently.** A1.6's exposure pass counted viral members
  carrying a UniRef100 id out of the UniRef90 and UniRef50 tiers — a different file, a
  different method, neither calibrated against the other — and got **5,405,462**, which is
  **0.48%** from this arm's 5,379,748. Both tiers emitted identically that figure, which is
  also an internal check since every member sits in exactly one cluster at each level, and
  both matched their release notes on cluster count (170,669,877 and 60,479,070). So the
  archive read is sound; it is only the interpretation of the gap that was overstated.
- **What the exposure measurement does and does not bound.** Over band 1's realised 31,381-seed
  sample, the share of seeds whose cluster holds at least one non-viral member is **13.61% at
  UniRef90 and 31.48% at UniRef50**. The 26% residual falls inside that range, near the 50%
  end. This is worth less than it looks, for two reasons A1.6 states and this entry adopts:
  the criterion is "the cluster holds at least one non-viral member", which fails seeds that
  clause (b) would keep — one cellular cluster-mate among hundreds is still "almost
  exclusively" viral — so it is an **upper bound rather than an estimate**; and it is cluster
  co-membership over UniRef100 seeds at two fixed identities, not a residual over UniProtKB
  sequences, so the two are different objects landing in the same region rather than one
  confirming the other.
- **Decision: the supportable wording, which replaces D-157's.** Two unrelated proxies falling
  in the same region is evidence that the underlying quantity is of that order, and nothing
  more. The line A1.8 and A1.6 both use is: *an independent exposure measurement at 50%
  identity puts an upper bound of 31.5% on the share of viral seeds with cellular homologues,
  consistent with but not confirming this residual.* **"Clause (b) removes 26%" may not appear
  anywhere**, in either task's write-up.
- **What survives of D-157's finding, which is the part that matters.** The asymmetry is
  untouched. The viral denylist has a second clause that could account for a gap of roughly
  this size, and the select-agent denylist has no such clause — its stated procedure runs
  straight from the list to the count — yet no reading of the regulation reproduces its
  published total, by 1.7x at the narrowest and 6.8x literal. That contrast does not depend on
  attributing the viral residual to anything in particular, and it is the finding.
- **Rejected:** Leaving D-157 as written with this entry as a footnote — its A1.6 task note
  says the difference "is accounted for", which a reader will carry forward as settled; the
  note is corrected in place and points here. Treating the 13.61%-31.48% range as a
  measurement of clause (b) and quoting a midpoint — it is an upper bound by construction, and
  a midpoint of a bound is not an estimate of anything.

### D-163 — A2.2's 3Di prediction is 173x the cost of a profile search, so it runs on a GPU instance
- **Date:** 2026-10-18
- **Task:** A2.2
- **Context:** §A2 names Foldseek for three virus-characteristic folds, but neither side of that
  search exists yet, and the query side is the problem: the surviving corpora are nucleotide
  (Evo) and sequence-only (the ESM3 proxy), so there are no structures to search. Foldseek needs
  3Di, which for sequence input means predicting it with ProstT5. D-098 warned this task by name
  that "any later task costing a pass over the corpora — A2.2's structural search above all,
  which has the same shape — should take its throughput from a run of realistic size or not quote
  one", so the figure below was measured before anything was planned around it.
  **Measured, on real corpus input.** 50 records of Evo 1's viral component
  (`stage2/test_stage2.parquet`), genes called with the same `pyrodigal` metagenomic mode D-077
  pins, giving 1,725 proteins of 375,687 residues, median length 141 aa. `foldseek createdb
  --prostt5-model`, foldseek 10.941cd33 from bioconda, 4 threads, no GPU:

  | proteins | residues | wall | s/residue |
  |---|---|---|---|
  | 100 | 26,430 | 7m 49.9s | 0.017779 |
  | 500 | 113,549 | 31m 38.4s | 0.016719 |

  The two agree within 6% across a 4.3x size step, so this is the linear regime and not D-098's
  fixed-cost trap. Taking the larger run: **0.0669 core-s per residue = 18.58 core-hours per
  million residues.** A2.1's RVDB-prot profile search cost 386 core-s/Maa (D-098), so **3Di
  prediction is 173x more expensive per residue than the search it is meant to feed**.
  What that buys at the depths this project already works at: a full census of both releases
  (24,691 Maa across `stage2`, `imgvr` and `imgpr`) is **458,800 core-hours**; merely matching
  A2.1's existing sample depth (363 Maa searched) is **6,745 core-hours**, which on this
  container's 4 cores is 1,686 wall-hours, about 70 days, against a two-hour ceiling per run.
  CPU is therefore not a slow route to this result, it is not a route to it.
- **Decision:** A2.2's 3Di prediction runs on a **GPU instance**, which the project owner
  authorized on 2026-10-18 after being shown the figures above. Four things were verified rather
  than assumed, because each would have cost a launch:
  **The instance types.** `RunInstances` with `DryRun=True` returns `DryRunOperation` for
  **`g5.xlarge`** and **`g6.xlarge`** and `UnauthorizedOperation` for `g5.2xlarge` and
  `g6.2xlarge`. So the GPU allowance landed on the 4-vCPU types only — the owner's "up to 8
  cores" holds for CPU (`c6i.2xlarge` still authorizes) but not for GPU, and a tool that assumes
  a GPU 2xlarge will be refused with the bare `UnauthorizedOperation` that AGENTS.md records as
  reading like having no permission at all.
  **The driver.** The base AL2023 AMI every existing `tools/ec2_*.py` uses carries no NVIDIA
  driver, and `ssm:GetParameter` reaches the Deep Learning base AMI that does:
  `/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-amazon-linux-2023/latest/ami-id`.
  That is the AMI A2.2 launches, not the one the other tools launch.
  **The build.** bioconda ships one `linux-64` build of foldseek 10.941cd33 with no CUDA variant,
  so whether the packaged binary can use a GPU at all was open. `--gpu 1` on a machine with no
  GPU answers it: it reports **"No GPU devices found"**, not "compiled without CUDA", so the
  packaged build is CUDA-capable and the pin stays a lockfile entry rather than a side-channel
  binary — which is what AGENTS.md requires of a tool that produces a result.
  **The weights.** `foldseek databases ProstT5` retrieves a 2.3 GB f16 GGUF from
  `huggingface.co/Rostlab/ProstT5`, unauthenticated, so this is not one of the blocked
  acquisitions that need a human.
- **Rejected:** CPU at census depth (458,800 core-hours) and CPU at A2.1 parity (6,745
  core-hours, ~70 days of this container) — both arithmetically out of reach, which is the
  reason, not a preference. A deliberately tiny CPU band inside the two-hour limit — about 0.02%
  of the census, roughly 100x shallower than A2.1's sample, and A2.1's own bounds were still
  rising steeply at 10x more depth (+18% Pfam, +45% RVDB on Evo 2 at the last doubling), so a
  null at that depth would carry no weight and a count would not be comparable with the other
  A2 tables A3.2 has to merge. Deferring A2.2 and recording the infeasibility as the finding —
  defensible before the GPU existed, and it was one of the four options put to the owner, but it
  gives up a route §A2 calls part of the methodological core while the obstacle turned out to be
  an instance type.
- **Consequence:** A2.2's cost model is now 3Di prediction on one GPU, and the GPU speedup over
  these 4 cores is the next thing to measure rather than to assume — it is the number that sets
  what depth A2.2 can pre-register, and it must be measured on the instance, since nothing here
  has a GPU to measure it on. The depth target is A2.1 parity, because A3.2 merges these tables
  and a structural table far shallower than the profile table is not comparable with it.
  Two constraints follow from the verification above and belong in whatever tool launches this:
  the instance type is a GPU **xlarge** or the launch is refused, and the AMI is the Deep
  Learning base one or the GPU is invisible to a binary that can otherwise use it.
  This entry records a **probe, not a result**: the throughput above came from a scratch
  measurement outside `amazebio.repro.run`, with no `run.json`, and no number from it may appear
  in a write-up. What it is for is sizing, which is exactly what D-098 said to measure first.

### D-164 — The GPU speedup is 64x measured, so A2.2 pre-registers A2.1's depth and not a census
- **Date:** 2026-10-18
- **Task:** A2.2
- **Context:** D-163 established that 3Di prediction, not the search, is A2.2's entire cost, and
  that on CPU it is out of reach at any depth this project works at. The project owner then
  authorized a GPU instance. What that buys had to be measured rather than assumed, because the
  depth A2.2 pre-registers follows from it, and because D-098's throughput estimate was wrong by
  a factor of a thousand for never leaving the fixed-cost regime.
  **Measured on one `g6.xlarge`** (NVIDIA L4, driver 595.91.07, 23,034 MiB, 4 vCPU), both devices
  on the same machine over the identical protein set — Evo 1 viral records from the pinned staged
  object, genes called by the Prodigal metagenomic mode D-077 pins. Artefacts and `run.json` at
  `corpora/results/a2-2/throughput/20261018T170641Z-9303d375d237/`, commit passed in by the
  launcher because the instance has no checkout.

  | rung | residues | CPU | GPU | GPU s/residue |
  |---|---|---|---|---|
  | 100 | 26,430 | 461.9 s | 8.1 s | 0.000306 |
  | 500 | 113,549 | 1,896.1 s | 29.4 s | 0.000259 |
  | 1,725 | 375,687 | — | 96.7 s | 0.000257 |
  | 6,000 | 1,241,827 | — | 316.1 s | 0.000255 |
  | 20,000 | 3,765,328 | — | 923.6 s | **0.000245** |

  **The headline is 64.48x**, at rung 500 — the largest rung both devices ran, so the ratio is
  one machine's measurement and not an instance figure divided by a container figure. Both arms
  are linear with no outliers at a 25% tolerance; the GPU's own rate still improves slightly with
  size (0.000259 at 500 against 0.000245 at 20,000), so against the CPU reference the asymptotic
  ratio is 68x. The conservative paired figure is the one to quote.
  **The container's figure reproduced on the instance.** CPU rung 100 took 461.9 s here against
  D-163's 469.9 s in the session container — 1.7% apart on 4 cores each. That is the cheapest
  available evidence that the two environments measure the same thing, and it is what licenses
  reading D-163's CPU projections and this entry's GPU ones off the same scale.
  **The GPU was proved present before anything was timed on it.** `nvidia-smi` reported the L4
  and a one-sequence foldseek probe returned `usable: true`. This is not ceremony: with no usable
  GPU, foldseek falls back to the CPU and returns a believable number, so an unproved GPU arm
  could have been CPU timings wearing a label, and the error would have been invisible in the
  artefact and in any test.
- **Decision:** **A2.2's pre-registered depth is A2.1 parity — 363 Maa, the depth A2.1 actually
  searched — and explicitly not a census.** At the measured 0.000245 s/residue that is **24.7 GPU
  instance-hours** (wall clock on one instance, not core-hours). A census of both releases is
  24,691 Maa, which is **1,682 GPU instance-hours**, about seventy days on the one GPU type the
  policy permits; a 64x speedup moves the census from impossible to merely unaffordable, and
  pretending otherwise would be the same error D-163 made about CPU one rung down.
  Parity is the right target for a reason that is not budget: A3.2 merges A2.2's table with
  A2.1's, A2.4's and A2.5's, and `metrics/detections.md` forbids pooling a `lower_bound` table
  with a `population` one. A structural table far shallower than the profile table would not be
  comparable with it, and one far deeper would not buy comparability either.
- **Rejected:** A census on GPU — 1,682 instance-hours, and the cost question would have to go
  back to the owner for something A2.1 itself did not do. A depth set by what fits one run window
  — that is letting the instrument choose the measurement, and it is how A2.1's first pass ended
  up at a rate it later had to deepen tenfold. A single number from the 500-rung GPU rate — it is
  6% pessimistic against the 20,000-rung rate, and quoting the warm-up is the specific mistake
  D-098 recorded.
- **Consequence:** 24.7 instance-hours **exceeds one instance's window**, so A2.2's detection pass
  needs either a longer timer or per-object resumability before it can run — the same conclusion
  A2.4 reached about deepening, and it should reuse that shape rather than reinvent it. The
  measurement also leaves one weakness in `tools/fold_throughput.py` worth fixing before the real
  pass: the heartbeat publishes between rungs, not on an interval, so the 32-minute CPU rung was
  32 minutes of silence. AGENTS.md requires a heartbeat on an interval precisely because silence
  cannot distinguish a dead process from a slow one, and this run only half-honoured that.
  Three launches were spent getting here and none of them to the measurement itself: a pixi URL
  re-derived by eye, then a payload guard that failed on a complete payload, then success. Both
  failures died in about forty seconds through their own `die` path with their logs in object
  storage, rather than idling away a 150-minute window, which is the behaviour AGENTS.md's
  shutdown rules exist to produce. The lasting fix was not either patch but simulating the
  instance's bootstrap locally — build the real payload, unpack it, run both precheck steps
  against it — which would have caught both for nothing.

### D-165 — A2.2's spending ceiling is $30, enforced as the shutdown timer
- **Date:** 2026-10-18
- **Task:** A2.2
- **Context:** Shown D-164's figures — 24.7 GPU instance-hours for the pre-registered depth,
  against 1,682 for a census — the project owner authorized the pass with a ceiling of **$30**.
  Measured prices, read from the account the same day: `g6.xlarge` spot quoted $0.503-$0.760/h
  across availability zones, `g5.xlarge` spot $0.434-$0.532/h. On-demand could not be verified
  from here at all: `pricing:GetProducts` is denied, so the only on-demand figure available is a
  remembered one, which is not a figure.
- **Decision:** The ceiling lives in `tools/ec2_folds.py` as `DEFAULT_MAX_SPEND_USD`, and the
  launcher derives the instance's shutdown timer from it and the live price. The reason it is
  code and not a note: the timer baked into `UserData` at launch is the *only* spend control
  that survives the launch, because `ec2:ModifyInstanceAttribute` is denied and there is no
  shell on the instance. An instance that outlives its budget cannot be reined in, only killed —
  and only by a launcher that is still alive to do it. A ceiling that cannot buy a window long
  enough to clear setup (about three minutes of boot, environment build and weights) refuses to
  launch rather than burning it.
  **The price is read, never remembered.** Spot comes from `describe_spot_price_history` and
  takes the *worst* recent quote on purpose: the launch does not pin an availability zone, so
  budgeting from the cheapest under-reserves precisely when it lands in the dear one. With
  `--no-spot` the tool demands an explicit `--price-per-hour`, because budgeting against a rate
  it cannot look up is how a ceiling silently becomes a guess.
  **Spot is the default**, one-time and terminate-on-interruption, matching the other launchers.
- **Rejected:** Treating $30 as guidance and launching with the previous fixed 150-minute
  timer — it happens to be well inside budget, but it is inside by luck rather than by
  construction, and the next person to raise the timer would not know what they were spending.
  Budgeting against a remembered on-demand price — unverifiable here, and the direction of a
  wrong guess is unknowable. Reserving the whole ceiling as one window — at $0.76/h it is
  39 hours, longer than the pass needs and long enough that a spot reclaim late in it would
  waste most of the budget; resumability, not a longer timer, is what protects the money.
- **Consequence:** The ceiling is not the binding constraint — at the quoted price it buys about
  39 instance-hours against a pass that needs 25. **What blocks the pass is method, not money**,
  and three things have to exist first: the fold reference set and its stated membership rule,
  the thresholds declared before any hit is looked at, and A1.4's manifests regenerated, since
  `artifacts/` is empty in a fresh container and nothing in object storage holds them.
  Resumability is the fourth, and it is what makes spot safe to rely on for a 25-hour pass.

### D-166 — A2.2's fold universe is selected at ECOD's family level, and one of the three folds has no node to borrow
- **Date:** 2026-10-18
- **Task:** A2.2
- **Context:** §A2 names three folds in prose — jelly-roll capsid, viral RdRp, class I fusion
  glycoprotein — and names no identifier for any of them. D-083 says this membership rule is "a
  finding about the registry, not a detail of the pipeline" and named A2.2 as facing the
  question; D-097 adds that the id-to-label mapping is an artefact with a stated rule. A2.1's
  precedent is to borrow somebody else's curation wherever one exists and to say so where it
  does not.
  **Registry:** ECOD **v295.2** (generated 2026-08-27), 2,943,253 classified domains, retrieved
  unauthenticated from the publisher. Chosen over SCOPe 2.08 (last released 2021, so five years
  of structures missing) and CATH 4.4 because ECOD's family level is keyed to Pfam names, which
  makes the selection auditable against the registry A2.1 already pinned.
  **Three things were measured in it, and each changes the rule.**
  **1. The architecture level is useless here.** `jelly-roll` holds 16,690 domains of
  `Nucleoplasmin-like/VP (viral coat and capsid proteins)` — the fold §A2 means — beside 15,544
  Concanavalin A-like lectins, 9,881 galactose-binding domains, 1,801 CUB domains and a calcium
  ATPase transduction domain. Selecting "jelly-roll" would make lectins count as viral capsids.
  **2. The topology level is useless for RdRp.** Viral RdRp sits under T-groups named
  `Adenylyl and guanylyl cyclase catalytic domain-like` and
  `helical bundle domain in reverse transcriptase-like polymerases`, so selecting at that level
  imports adenylyl cyclases and reverse transcriptases. Worse, searching the literal phrase
  "RNA-dependent RNA polymerase" in ECOD's names returns **81 domains**, all birnavirus
  subdomains — the canonical RdRp families are named for Pfam (`RdRP_1`, `RdRP_3`, `RdRP`) and
  would have been missed entirely. The same family name also recurs under different topologies,
  because RdRp is multidomain and its palm and helical bundle are classified apart.
  **3. "Class I fusion glycoprotein" is a virology category, not a structural group.** Its
  members are in unrelated branches: `Hemagglutinin HA2 chain` (influenza), `MPER trimer` with
  family `GP41` (HIV), `S2 subunit of coronavirus spike glycoprotein`, and two paramyxovirus F
  groups. **No single ECOD node means it.** Name matching is also actively unsafe here: the
  family name `GP41` matches HIV's envelope *and* a phage tail protein (`E217_GP41`) *and* a
  Wiskott-Aldrich protein, while `Hemagglutinin` spans both the jelly-roll receptor-binding head
  and the HA2 fusion stalk, which are different folds doing different jobs.
- **Decision:** **Select at ECOD's F-group (family) level, by an enumerated list of group
  identifiers rather than by regex over names**, and ship that list as an artefact with the
  table, as D-097 requires. Names are evidence for building the list and must not be the
  mechanism that applies it — finding 3 is the proof.
  Per fold:
  **Jelly-roll capsid** — the `Nucleoplasmin-like/VP (viral coat and capsid proteins)` group
  under `jelly-roll`. Borrowed curation, 16,690 domains, **119 manually curated representatives**.
  **Viral RdRp** — the enumerated RdRp families (`RdRP_1`, `RdRP_3`, `RdRP`, `Birna_RdRp_palm`,
  `Birna_RdRp_C`, `CoV_RPol_N`), 1,907 domains, **31 representatives**, explicitly **excluding
  the host RNAi polymerase families** that share the fold. A eukaryotic RNAi polymerase is not
  viral-derived content, and counting one as a surviving viral homolog would be a false positive
  of exactly the kind this audit exists to avoid — the same call A2.1 made excluding integrase
  and transposase from its viral family set.
  **Class I fusion glycoprotein** — enumerated by this project, because there is nothing to
  borrow: 9,606 domains, **16 representatives**. This is the one fold whose membership rule is
  ours rather than a curator's, and it ships labelled that way. It is also the weakest of the
  three and is the structural coverage gap A2.2's Done-when criterion asks to be documented.
  **The reference set is the representatives, not every domain** — 166 structures in total,
  fetched from RCSB by accession and cut to ECOD's residue ranges. Fold search is the point, so
  representatives are the right reference; and it keeps the reference side the small side, which
  AGENTS.md requires to be worked out before anything is sized.
- **Rejected:** Selecting by architecture or topology — findings 1 and 2 measure what that
  costs. Selecting by regex over family names — finding 3 shows it imports phage tail proteins
  under the HIV envelope's name. SCOPe 2.08 — five years stale, and this audit's corpora are
  current. Foldseek's prebuilt PDB or CATH50 databases as the reference — they are whole chains
  and whole-chain classifications, and a capsid fold inside a larger protein is the case that
  matters. BFVD, the predicted viral structure database — it is predictions over sequences that
  may themselves descend from the corpora under audit, and a reference set has to be independent
  of the thing it measures. Every domain rather than representatives — 28,203 structures to
  gain fold-level sensitivity that representatives already provide.
- **Consequence:** The fold universe is a denominator of **three folds and 166 reference
  structures**, with its membership rule stated per fold and one of the three marked as this
  project's own construction. That asymmetry is itself reportable: the audit can borrow a
  curator's definition of a viral capsid, can assemble a defensible one for RdRp from Pfam-keyed
  families, and cannot borrow one at all for the fusion class §A2 names. Thresholds come next and
  are not set here; nothing in this entry looks at a hit.

### D-167 — A2.2 searches corpus-as-query against the pinned reference set, and cannot report a TM-score at all
- **Date:** 2026-10-18
- **Task:** A2.2
- **Context:** The threshold had to be fixed before any hit was inspected, and the plan going in
  was the obvious one: TM-score, the field's standard fold-similarity measure, cut at the
  literature's same-fold convention, with the small reference side as the query per AGENTS.md's
  rule about which side of a search to make the query. Testing that plan against foldseek
  10.941cd33 rather than declaring it found three things, each of which changed it.
  **1. `--tmscore-threshold` can be silently disabled.** With TM alignment foldseek prints
  `Cannot use --tmscore-threshold with --sort-by-structure-bits 0` followed by
  `Disabling --tmscore-threshold`, and continues. A declared threshold the tool discards is
  worse than none, because the run still produces a plausible table.
  **2. A ProstT5 database holds 3Di strings and no coordinates.** There is no `_ca` file, so
  `--alignment-type 1` dies outright, and `convertalis` refuses to report at all — not merely
  for coordinate-derived columns. That was checked: requesting only `query,target,bits,evalue,
  prob,fident,alnlen,qlen,tlen` still fails on the missing `_ca`, in both directions. The
  publisher states the same thing: such a database "supports monomer search and clustering, but
  does not enable features requiring Ca information, such as `--alignment-type 1`, TM-score or
  LDDT output".
  **3. The supported direction is the inverse of the one AGENTS.md's rule would pick.** The
  documented path is `easy-search QUERY.fasta <structureDB> res tmp --prostt5-model weights`:
  sequence as **query**, structures as **target**. Verified end to end here — 18 rows, exit 0 —
  and the C-alpha message is then a warning, not an error. The usual "query the small side"
  reasoning does not apply because the tool decides it: only the structure side has
  coordinates, so only it can be the target.
- **Decision:** **The corpus is the query and the 166-structure reference set (D-166) is the
  target.** Coverage floor on the **target**, `--cov-mode 1`, because the reference domain is
  now the target and the requirement is that at least half of the reference *fold* is matched —
  A2.1's `MIN_MODEL_COVERAGE` of 0.5 carried over to this geometry. Getting this backwards
  would let a sliver of a capsid fold inside a large corpus protein count as a detection, and
  `--cov-mode 2` was the intended setting until the direction inverted.
  **The score is the bit score, not the E-value.** Both are available and coordinate-free; the
  bit score is chosen because it does not depend on database size at all, which satisfies
  D-076's rule directly rather than by argument. Worth recording that the rule would be
  satisfied either way here: D-076 rejected E-values because they scale with the number of
  targets searched, so a headline would drift with how much corpus a run happened to read — but
  under this inversion the target database is the *fixed* reference set and the varying quantity,
  corpus size, is the query count, which the E-value does not depend on. The bit score needs no
  such reasoning to be safe, so it is what the detection records.
  **Reported, so a reviewer can re-cut without re-searching:** bit score, E-value, target
  coverage, alignment length, query and target length, and fraction identical. `alntmscore`,
  `qtmscore`, `ttmscore` and `lddt` are structurally unavailable and are recorded as such rather
  than as nulls that look like missing data.
- **Rejected:** TM-score at the literature same-fold cut — impossible here, on the publisher's
  own statement, not merely unmeasured. Predicting full 3D structures for the corpus so that
  TM-score becomes available — the publisher puts ProstT5 at 400-4000x faster than ColabFold
  structure prediction, and D-163 already measured the 3Di step alone at 173x the cost of a
  profile search; full structures are orders of magnitude beyond any budget this project has.
  `--alignment-type 0` (3Di only) over the default 3Di+AA, which was tempting for independence
  from sequence — deferred to the threshold calibration rather than chosen here, since it
  changes the score distribution and therefore the cut.
- **Consequence:** **A2.2 can never state a TM-score or an LDDT for a hit in the Evo corpora.**
  That is a limit on how strongly the fold claim may be worded — the evidence is a structural
  alphabet alignment against a reference fold, not a superposition — and it belongs in the
  write-up as a stated limitation rather than being discovered by a reviewer. It also partly
  undercuts the independence §A2 wants from the structural route: the 3Di string is predicted
  from sequence, so this detector is not as independent of sequence as a search over real
  structures would be, and the default alignment mode scores amino acids alongside 3Di.
  **The threshold's value is still open and is the next step**, deliberately: it needs a decoy
  calibration — the reference set searched against shuffled or unrelated queries — to pick a
  bit score at a stated false-discovery rate, with its two bracketing values fixed in the same
  breath, as `metrics/survival.md` requires. Nothing in this entry has looked at a corpus hit.

### D-168 — A deferred gate keeps `gate: true` with empty `blocks`, and the second lockfile goes
- **Date:** 2026-10-18
- **Task:** X1.1 (repo audit)
- **Context:** A quality audit of the repo turned up two things needing a recorded call rather
  than a silent fix. First, `AGENTS.md`'s gate table said "Five tasks carry `gate: true`" and
  listed C2.2 as a live gate holding leakage-score results, while omitting C6.3 entirely. Six
  tasks carry the flag. C2.2 was deferred in DESIGN v0.4 and superseded by C5.1–C7.1 (D-009),
  and it carries `blocks: []` with nothing depending on it — so the gate the operating manual
  described as structurally impossible to walk past held nothing, while C6.3, which actually
  holds C7.1 and X4.1, was undocumented. Second, the repo root carries both `pixi.lock` and a
  129-byte `uv.lock` containing one editable root entry and no dependencies, referenced by
  nothing and git-ignored nowhere. It arrived on `main` in `2ffeab5`, whose message reads
  "Project management only."
- **Decision:** A gate that `DESIGN.md` has declined keeps `gate: true` and carries `blocks: []`
  deliberately, and the gate table says so in its own row. The flag is what keeps a declined
  commitment visible as deliberately not run — the same reason `deferred` exists — so removing
  it would erase the commitment rather than record its supersession. The table now lists all
  six, names C6.3 as the live gate on Phase C results, and states that `tasks/BOARD.md`'s
  generated Gates section is authoritative where the two disagree. `uv.lock` is deleted and
  `uv` artefacts are git-ignored.
- **Rejected:** Dropping `gate: true` from C2.2 — it passes `board.py --check` either way, and
  the flag is the only thing marking C2.2 as a commitment that was made and then declined
  rather than a task that was never a gate; the paper names it as future work and needs that
  distinction. Adding a `board.py --check` rule that a gate must carry non-empty `blocks` —
  it would fail on exactly this legitimate case, and the owner declined it when offered.
  Keeping `uv.lock` on the grounds that it is harmless — it pins nothing and cannot reproduce
  the environment (the conda-side toolchain has no PyPI path this project pins), so a second
  lockfile in the root invites a contributor to resolve from the one that pins nothing, against
  the pin-everything non-negotiable.
- **Consequence:** Neither is a finding; both are repo hygiene. The gate table change is
  documentation catching up with D-009 and does not move any gate: A3.3, B5.1, C6.3 and X3.1
  all stay `HOLDING`, A1.1 stays `PASSED`, and C2.2 stays `deferred`. One thing the audit
  surfaced is *not* resolved here and is left to the owner: `AGENTS.md`'s gate table is
  hand-maintained against generated frontmatter with nothing checking the two agree, so it can
  drift again. The new line pointing at `BOARD.md` as authoritative is a mitigation, not a
  mechanism.

### D-169 — A2.2's fold universe is re-derived at family level, because D-166's list was never shipped and its capsid set contradicted its own rule
- **Date:** 2026-10-18
- **Task:** A2.2
- **Numbering:** appended as D-168 and renumbered to D-169 before pushing — the repo audit's
  D-168 landed on `main` in between and is already cited from `AGENTS.md`. Commit messages on
  branch `ccr-7a87e8bd-9ow1h1` citing D-168 for the fold universe mean this entry.
- **Context:** D-166 fixed the three folds §A2 names at **166 ECOD representatives** and required
  the enumerated identifier list to ship as an artefact with the table. **That artefact was never
  written.** The list existed only in the session that derived it, so the universe had to be
  re-derived from the pinned release before anything could be searched — and re-deriving it
  turned up two things.
  The pin itself re-verifies exactly. ECOD **v295.2**, generated 2026-08-27, retrieved
  unauthenticated. One correction of record: the publisher keeps **no per-version filename** for
  the current release — the distribution listing stops at `develop292` while `ecod.latest.domains.txt`
  *is* v295.2 — so the pin cannot be a URL and is now the version string plus a sha256
  (`cd3abc43…afe8`). The file holds **2,943,252** classified domain rows; D-166's 2,943,253 is
  that count plus the header line.
  **1. The capsid fold was selected one level up, and that contradicts D-166's own finding.**
  D-166 established that ECOD's `jelly-roll` X-group mixes Concanavalin A lectins and
  galactose-binding domains with viral capsids, and concluded that selection must be at **family**
  level by enumerated identifier. It then selected the capsid fold at the **H-group**
  `Nucleoplasmin-like/VP (viral coat and capsid proteins)` — 16,690 domains, 119 curated
  representatives, both of which reproduce exactly. But that group is nucleoplasmin-*like*: it
  carries **867 plainly cellular domains** — nucleoplasmin itself (132), peptide-N-glycanase and
  PNGaseA (64), Cu(2+) monooxygenase (162), TGF-beta propeptide (201), NPL (141) and others — and
  **12 of the 119 representatives are cellular**. A further 665 domains and 10 representatives sit
  in ECOD's two *unnamed* families of the group, and `10.2.1.0` holds peptide-N-glycanase outright
  (`e1pgsA1`, PDB 1pgs). Admitting any of those as a reference structure manufactures the exact
  false positive the family-level rule was adopted to prevent: a corpus protein matching the
  nucleoplasmin or N-glycanase jelly-roll would be reported as a surviving viral capsid fold.
  **2. D-166's RdRp list was illustrative, not exhaustive.** Its prose names six families
  (`RdRP_1`, `RdRP_3`, `RdRP`, `Birna_RdRp_palm`, `Birna_RdRp_C`, `CoV_RPol_N`). Applied literally,
  with the host set excluded, those six select **1,441 domains and 18 representatives** — not the
  1,907 and 31 recorded — and they miss influenza PB1, flavivirus NS5, the mononegavirus and
  bunyavirus L polymerases, the coronavirus nsp12 thumb, `RdRP_4`, `RdRP_5` and the permutotetra
  and cypovirus polymerases. Every one of those is a canonical viral RdRp. Two mechanical traps
  explain part of the gap: ECOD's family names are **comma-joined Pfam lists**, so `CoV_RPol_N`
  appears only as `RdRP_1,CoV_RPol_N` and an exact-string match never finds it; and RdRp's palm
  and thumb are filed under two different topologies, so a list drawn from one topology silently
  covers half the fold.
- **Decision:** **Apply D-166's family-level rule consistently to all three folds, and ship the
  enumerated lists as code and as an artefact.** `src/amazebio/folds.py` holds them; the artefact
  is `fold-universe.json`, and it carries the **excluded** identifiers beside the included ones,
  because what a denominator leaves out is as much a part of its membership rule as what it admits.
  **Jelly-roll capsid** — the 64 demonstrably viral families of the H-group: **15,158 domains, 97
  representatives**. The 25 cellular families and 2 unnamed families are listed by identifier and
  excluded. Put to the project owner as a three-way choice between this strict set (97), keeping
  the unnamed family (107), and holding D-166's whole H-group as recorded (119); **the owner chose
  the strict set.**
  **Viral RdRp** — the complete enumeration across both topologies: **27 families, 2,583 domains,
  30 representatives**, against D-166's recorded 31. Host RNAi polymerase families stay excluded
  exactly as D-166 decided, and they are listed by identifier too (269 domains), since they are
  this fold's sharpest decoys and D-170 uses them as such.
  **Class I fusion glycoprotein** — **15 families, 7,361 domains, 14 representatives**, against
  D-166's recorded 9,606 and 16. **The gap is deliberately not padded.** Reaching 9,606 needs
  either the coronavirus S1 beta domain, which is receptor binding and not fusion, or ECOD's
  unnamed families in the `MPER trimer` topology — a topology that carries HIV gp41 beside
  bZIP transcription factors, GATA domains, syntaxin, fungal rhodopsin, mitochondrial carriers
  and a phage fibritin trimerisation domain. Guessing which of those D-166 counted would be
  inventing a denominator.
  **The reference set is therefore 141 structures, not 166**, all 141 fetched from RCSB and cut to
  ECOD's ranges without a single drop.
- **Rejected:** Holding the recorded 166 — the capsid component of it demonstrably admits cellular
  reference structures, and a false positive in the largest of the three folds is the costliest
  error this detector can make. Re-deriving by regex over family names — D-166's finding 3 already
  measured what that costs, and the comma-joined names found here are a second, independent reason.
  Reconstructing D-166's exact lists by searching for combinations that reproduce 1,907 and 9,606 —
  that fits a number rather than stating a rule, and the rule is the thing a reviewer checks.
- **Consequence:** The three folds' membership rules are now in code, in an artefact, and
  checkable against the registry by identifier, with the asymmetry D-166 identified preserved and
  sharpened: the capsid fold borrows a curator's grouping **minus a correction of ours**, RdRp
  borrows families and assembles them across topologies, and the fusion class is ours outright.
  That last one remains the structural coverage gap A2.2's Done-when criterion asks to be
  documented, and it is now also the fold whose denominator differs most from what D-166 recorded.
  **Nothing in this entry looks at a corpus hit.** The threshold is D-170.
### D-170 — A1.6's Done-when criteria are amended to the deliverable D-134 and D-150 left it, and the task goes to review
- **Date:** 2026-10-18
- **Task:** A1.6
- **Context:** A1.6's code is entirely on `main` and no instance is running, but the task was
  still `in-progress` and the project owner's reading was that it was finished. Checked against
  its own Done-when, it was not, and the reason was not unfinished work: two of its four criteria
  had stopped describing the task. "Both manifests exist in A1.4's format" was written when the
  arm was a corpus-wide pass; D-134 replaced that with nested seed-sample bands reporting a rate
  with an interval, and D-156 established that the charitable reading's seed set is not executable
  from the published text at all, so there is no charitable manifest to produce and never will
  be. "The comparison against the paper's reported 10.6M is written up" was overtaken by D-150:
  no published denylist size can validate a corpus-level reconstruction, because every published
  size counts a different object. Its "written up" also has nowhere to land — there is no Phase A
  write-up in the repo; A6.1 owns it and the A3.3 gate holds it. So the criteria could neither be
  met nor honestly waived, which is the state in which a task gets marked `done` with its own
  conditions unmet.
- **Decision:** The criteria are amended, in place, with the originals kept and struck beside
  them. The deliverable is now stated as: the strict reading's rate on at least one band with its
  interval, realised family count and design effect; every figure naming which reading it belongs
  to per D-156; the charitable reading's non-executability recorded as a §A0 finding; the seed-set
  construction pinned and checksummed; the absence of any valid published-size comparison recorded
  as a §A0 finding; and a `run.json`. Against those, A1.6 is met and goes to `review`. Band 1's
  reading labels are restated as the task's settled position in a closing block rather than left
  in a mid-file note: the any-identity column is the strict reading proper (≥1.5473% to ≥4.0975%),
  the 0.70 column is the strict seed set at the charitable threshold (0.6537% to 0.6844%) and is
  a hybrid of none of D-015's three readings, and D-153's "charitable" label on that column is
  withdrawn. The withdrawn ~4M validation sentence is struck in place rather than deleted, because
  it was acted on and the correction is only legible against it. Bands 2 and 3 and the strata
  sidecars stay unauthorised and are named as owner decisions, not as outstanding work.
- **Rejected:** Moving A1.6 to `done` — `review` is the honest state, because the amendment is
  itself a change a reviewer should see, and because the arm's reporting into the write-up is real
  work that A6.1 owns rather than work that has happened. Leaving the criteria as written and
  closing against them anyway — that is marking a task done with unmet conditions, and the
  Definition of done exists to prevent exactly that. Leaving the criteria as written and the task
  `in-progress` indefinitely — it reads as a fourth in-flight task on the board when nothing is
  in flight, and it hides a finished measurement behind a stale specification. Deleting the
  superseded criteria instead of striking them — the original specification is the record of what
  this task was bought to produce, and the gap between that and what it produced is itself part of
  the §A0 story. Rewriting the earlier state blocks to remove the withdrawn 4M claim, which an
  earlier block instructed — it was acted on for days, and a file that shows no trace of a
  withdrawn claim cannot explain why the correction exists.
- **Consequence:** Phase A's ESM3 broad arm now has a reportable result with its interval, and two
  §A0 findings that are results in their own right. **A6.1 inherits two hard constraints:** it must
  take the reading labels verbatim and must not offer the ~4M as corroboration, in any hedged form.
  The amendment is not a precedent for loosening criteria to fit an outcome: it is admissible here
  only because D-134, D-150 and D-156 each changed the deliverable *before* this entry, for
  recorded reasons, and each is cited. A criterion amended after results are seen and *without* such
  a prior entry would be the thing the non-negotiables forbid. One thing this does not resolve: the
  task reached `review` with its original criteria unmeetable for three days before anyone noticed,
  because nothing checks Done-when against the decisions that supersede it — `board.py` validates
  the graph, not the criteria.

### D-171 — A2.2's threshold is 500 bits with brackets [400, 600] and 3Di+AA scoring, and the near-fold decoys are a finding in their own right
- **Date:** 2026-10-18
- **Task:** A2.2
- **Numbering:** appended as D-170 and renumbered to D-171 before pushing — A1.6's D-170 landed
  on `main` while this branch was running the calibration. Commit messages on branch
  `ccr-7a87e8bd-9ow1h1` citing D-170 for A2.2's threshold mean this entry.
- **Context:** D-167 fixed everything about A2.2's score except its value — corpus as query, the
  141 pinned reference structures as target, coverage floor on the target at `--cov-mode 1 -c
  0.5`, bit score rather than E-value — and deferred one option, `--alignment-type 0` (3Di only)
  against foldseek's default 3Di+amino-acid scoring, "to the threshold calibration". Both are
  settled here, from decoys, before any corpus hit was seen; `amazebio.repro` enforces the order.
  **The decoy design, declared before the run.** A shuffled sequence is not a test here: three
  shuffled reference domains returned no hit at all at `-e 1000` in the probe. The decoys that
  matter are real proteins that *share the fold and are not viral* — and D-166 and D-169
  enumerated precisely those while deciding what to exclude. Four classes, 400 queries each:
  `near_fold_nonviral` (the excluded cellular capsid families and the host RNAi polymerases),
  `unrelated_fold` (ECOD X-groups disjoint from the universe's), `shuffled` (the positives'
  sequences shuffled at a pinned seed), and `positive` (held-out non-representative domains of
  the fold families). A positive sharing a PDB entry with any reference structure was dropped —
  393 of them — because the same deposition re-scored against itself measures nothing.
  Every query took the corpus's own path: amino acids through ProstT5, then the search, so the
  prediction error sits inside the threshold rather than outside it. 1,567 queries, 385,185
  residues; 3Di predicted once in 1h39m on four cores and both modes searched against the same
  query database. Target false-positive rate **1% on `near_fold_nonviral`**, declared in advance.
- **Decision:** **Declared threshold 500 bits; brackets 400 and 600; alignment mode 3Di+AA.**
  Realised at the declared cut: `near_fold_nonviral` 3/389 (0.8%), `unrelated_fold` 0/394,
  `shuffled` 0/392, `positive` 242/392 (61.7%).
  **The grid was extended upward once and the declared value did not move.** The rule — the
  lowest grid value holding the target on the binding class — and the target were both fixed
  beforehand. The first grid stopped at 500, which is where the rule's answer fell, so the value
  had no upper neighbour and `metrics/survival.md` requires *two* bracketing values. Nothing was
  inserted below 500, so the selection provably could not change: 400 gives 4/389 = 0.0103, which
  misses 1%, and 500 gives 3/389 = 0.0077, which holds. This is the declared procedure being
  completed, not a threshold re-picked after seeing results, and it is recorded rather than done
  quietly.
  **The mode choice was made after seeing the sweep, and is recorded as such.** D-167 deferred
  the option without fixing a rule, so unlike the threshold this one was not pre-registered. The
  rule applied: among modes whose declared threshold holds the target, take the higher
  true-positive rate. 3Di+AA gives 61.7% against 3Di-only's 11.2% at the same cut and the same
  false-positive target. The margin is a factor of five, so no defensible rule chooses otherwise.
- **Rejected:** `--alignment-type 0`, despite being the more attractive option on independence
  grounds — it scores 3Di alone, so it does not re-use the amino-acid signal A2.1 already
  searches. At the declared cut it finds one fifth as many true fold members. On the probe it also
  scored a shuffled decoy at 58 bits above a genuine domain at 17. Calibrating on shuffles alone,
  which would have put the cut near 60 bits and left the near-fold false-positive rate at 60%.
- **Consequence, and this is the substantive one:** **the near-fold non-viral decoys are detected
  at a rate that no bit score separates from the true positives until most sensitivity is gone.**
  At 100 bits they run at 56% while unrelated folds and shuffles are already at 0.8% — seventy
  times apart — and the near-fold curve tracks the positive curve closely (0.56 against 0.79 at
  100 bits, 0.51 against 0.78 at 140) before separating above 160. Holding them to 1% costs
  sensitivity: 61.7% at the declared cut against 78.8% at 100 bits. **And it never reaches zero:
  3 of 389 cellular near-fold proteins pass at 500 bits.**
  That is the method working, not failing. Nucleoplasmin, peptide-N-glycanase and Cu(2+)
  monooxygenase genuinely have the jelly-roll capsid fold. What the curve measures is that
  *"carries this fold"* and *"is viral-derived"* are different claims, and this instrument cannot
  fully separate them. Three things follow. It is the quantitative justification for D-169
  excluding those families from the reference set. It is a stated limitation for the write-up,
  not a parameter to tune — and a sharper one than §A2 anticipated for this route. And it means
  the dominant false-positive source in the real pass will be cellular proteins carrying these
  folds, which bacterial and metagenomic records do contain, rather than chance alignments.
  **A second ceiling:** 13% of held-out true fold members never hit their own fold at all, even
  at 20 bits. Predicted-3Di fold search misses them outright, which caps what any threshold here
  can achieve and belongs beside the survival figures as a sensitivity bound.
  **Two corrections to D-167**, both found by running the chain rather than trusting the note.
  `convertalis` does **not** refuse against a ProstT5 database in the direction D-167 itself
  chose — ProstT5 as query, structures as target — and reports every requested column; 34,822
  rows in 3Di+AA and 71,689 in 3Di-only. The refusal D-167 recorded must have been with the
  ProstT5 database as the *target*; read literally, that entry says this pipeline is impossible.
  And foldseek silently disables `--sort-by-structure-bits` for want of C-alpha data, the same
  shape of trap D-167 found with `--tmscore-threshold`. Harmless here because the calibration and
  the real search share one geometry, but it means the reported `bits` is the plain alignment bit
  score and not a structure-weighted one, which a reviewer comparing to published foldseek
  figures needs to know.

### D-172 — A2.2's searches run exhaustively, because foldseek's prefilter silently returns nothing against a 141-structure target
- **Date:** 2026-10-19
- **Task:** A2.2
- **Context:** A smoke run of the finished search tool over real corpus records — six IMG/VR
  records, 77 called proteins, searched against the pinned 141-structure reference database —
  returned **no hits at all**. Investigated rather than accepted, because the calibration (D-171)
  had just measured ~50% of *unrelated* ECOD domains hitting something at 20 bits, so zero from
  77 viral proteins was not a plausible result.
  The cause is in foldseek's own log: `Index table k-mer threshold: 78 at k-mer size 6`,
  `0 median result list length`, **`76 sequences with 0 size result lists`** — and exit status 0.
  The prefilter is mis-tuned against a target database this small and discards essentially every
  candidate without failing. The identical query and target databases, searched with
  `--exhaustive-search 1`, produced **49 hits**. Zero against 49.
  **What shipping that would have produced.** A complete set of well-formed shards, correct
  provenance, a `run.json`, and a headline of *no surviving folds anywhere in either Evo release*
  — a clean, publishable-looking null manufactured entirely by a heuristic. `AGENTS.md` forbids
  designing any part of the pipeline so that a null is harder to see; a prefilter that deletes
  every candidate is the strongest possible version of that, and it is the one result this audit
  must never reach by accident.
  **Why neither the calibration nor a dry run could have caught it.** The failure is
  **scale-dependent**. At the calibration's 1,567 queries the prefilter dropped about 7% of rows
  (3Di+AA 34,822 against 37,286 exhaustive; 3Di-only 71,689 against 83,310) and the threshold
  still came out right; at 77 queries it dropped nearly everything. So a threshold calibrated at
  one query count and applied at another hides it completely, and a real shard is around 30,000
  proteins while a smoke shard is 77 — the pass would have straddled both regimes. Only running
  the real tool over real corpus records at a realistic small scale exposed it.
- **Decision:** **Every A2.2 search runs `--exhaustive-search 1`, in the calibration and in the
  pass alike.** This removes the heuristic rather than retuning it: with 141 targets, every query
  is aligned against every reference, which is exact, free of any scale dependence, and
  negligible beside 3Di prediction — the step D-163 measured at 173x the profile search it feeds
  and which dominates the cost completely. `EXHAUSTIVE_SEARCH` is a module constant in
  `tools/detect_folds.py` with this reasoning attached, not a command-line knob, because a
  geometry a run can opt out of is a geometry some run will.
  The search geometry now enters the shard's `params` fingerprint, so shards produced under the
  old geometry cannot merge with new ones (`load_shards` refuses a mixed set).
- **The threshold is re-derived and does not move.** D-171's declared 500 bits, its brackets
  [400, 600] and its 3Di+AA mode all stand: near-fold false-positive rate 3/389 either way, and
  sensitivity 0.617 to **0.622**. The prefilter's lost rows were weak alignments concentrated far
  below the cut, which is visible at the low end of the sweep (at 20 bits the positive rate moves
  0.867 to 0.939, unrelated 0.513 to 0.602). **This is not a threshold re-picked after seeing
  results:** D-171's rule and its 1% target were pre-registered and are unchanged, the instrument
  was broken, and re-applying an unchanged rule to a corrected measurement is the only defensible
  response. That the answer is identical is a robustness result, not the justification.
- **One D-171 figure is corrected.** D-171 recorded that 13% of held-out true fold members never
  hit their own fold at any threshold. Exhaustively that is **6.1%** (positive rate 0.939 at 20
  bits). The missing half was the prefilter, not the method, so A2.2's sensitivity ceiling is
  better than D-171 states and the write-up should quote 6.1%.
- **Rejected:** Raising `--max-seqs` or lowering `--k-score` to make the prefilter behave — that
  tunes a heuristic until it stops hiding results on the inputs tested, and leaves it free to
  hide them on inputs not tested; the failure mode is silence, so there is no signal that the
  tuning was insufficient. Accepting the zero as a finding — it contradicted the calibration's own
  measured decoy rates, which is what prompted the investigation. Keeping the prefilter for the
  pass and exhaustive search for the calibration, or the reverse — a threshold must be measured
  under the geometry it is applied under, which is the whole reason this entry re-derives it.
- **Consequence:** the instrument is now deterministic with respect to how much corpus a run
  happens to read, which is a property the audit needs anyway: D-076 rejected E-values for
  drifting with database size, and a prefilter whose behaviour depends on query count is the same
  defect one layer down. The lasting lesson is the one `AGENTS.md` already draws for instances and
  which applies just as well in the container: **a step that reports nothing has not told you it
  found nothing.** The free smoke tier — the real tool over real corpus records, bounded by
  `--max-records` so a 16.9 GB object costs 15 seconds — is what turned this up for a fraction of
  a cent, before $19 of GPU time and before a number reached a write-up.

### D-173 — The detection contract carries each registry's denominator rule and its composition, so D-161 lives in the artefact rather than in this log
- **Date:** 2026-10-19
- **Task:** A2.4 (changes `metrics/detections.md`, so A2.1–A2.5 and A3.2 all see it)
- **Context:** D-161 ruled that the two registries' survival fractions are not comparable and
  neither is reportable on its own, and that what *is* reportable is the absolute counts plus
  Pfam's composition — the prophage parts list. It changed no code and produced no artefact. A
  repo audit found its measured quantities (5,314 genes, 1,201,328 residues, 173 against 33
  detections per 1,000 genes, the threshold spans, the composition list) existing **only in this
  log**: `tools/detect_proviruses.py` emitted no composition and named no denominator, and none
  of those figures appeared under `src/`, `tools/` or any artefact. "Artefacts before prose" is a
  non-negotiable — every number in a write-up traces to a machine-readable artefact — so as it
  stood the Phase A write-up could source D-161's numbers from nothing but a decisions entry.
  A2.4's state block was meanwhile presenting the two fractions side by side, which is exactly
  the reading D-161 forbids.
- **Decision:** Every detection table gains two fields, in `metrics/detections.md` and therefore
  for all five A2 detectors. **`denominator`** names the universe's authority and the restriction
  on quoting its fraction: Pfam's is never quoted as "the fraction of viral families", RVDB's is
  never quoted as a measure of how much survived, and a registry the rule does not name still
  gets a restriction plus `comparable_across_registries: false` — a new registry must not arrive
  with none, which is how D-074's defect happened. **`composition`** is the families carrying the
  detections, most first, ties broken by accession so a quoted parts list reproduces from pinned
  inputs. The per-registry restriction also travels in `notes`, and `reading_this_table` sends a
  quoter to `denominator` before `survival.fraction`.
- **Rejected:** Leaving it in prose and relying on the write-up to carry D-161 — that is the
  arrangement the audit found, and it had already failed once: A2.4's own state block published
  the forbidden presentation 85 minutes after D-161 landed in the same pull request. Putting the
  fields only in `detect_proviruses.py` — the rule is about registries, not about prophage, so
  A2.1's tables need it identically and a second copy would drift. Emitting D-161's
  cross-registry comparison itself (detections per 1,000 genes, hits per family-record pair,
  median best scores) — those are a *comparison between two tables* and a per-registry table
  structurally cannot hold them; that belongs in its own emitter and is not built here.
  Computing a "phage-relevant subset" of RVDB to fix its denominator — D-161 already declined
  it as a new reading of someone else's curation needing its own task and pre-registration.
- **Consequence:** Additive to the contract: both fields derive from `families[]` and `registry`,
  so A3.3's independent reimplementation gains no measurement to reproduce, and no existing
  figure changes. A3.2 still must not pool or average the two registries' fractions (D-022,
  D-161). **A2.4's existing twelve tables predate this and do not carry the fields** — they would
  need a re-run to gain them, which is not worth the spend for a field derivable from rows the
  tables already hold; the task file records the gap instead. What this does not resolve: D-161's
  cross-registry figures are still prose, and a write-up quoting them still has no artefact to
  cite.

### D-174 — A7.1's criterion 1 is amended to the one-model, coverage-stated deliverable D-047 and D-049 left it
- **Date:** 2026-10-19
- **Task:** A7.1
- **Context:** Auditing the three `review` tasks' criteria the way A1.6's were audited (D-170)
  found A7.1 carrying "conformance diff computed per model × reading". The deliverable is one
  model at 3/6 coverage with the readings identical by construction. That is not a shortfall:
  D-047 established that every rule the three readings differ over reads an input the release
  withholds, so `readings_agree_by_construction` asserts identity from the specs rather than
  reporting three columns as agreement; D-049 put the converse direction and Evo 2's arm outside
  this task; and ESM3-open has neither corpus nor threshold published, so it has no arm at all.
  The restriction is derived mechanically from the specs, not hand-picked. The criterion was
  written before those entries narrowed the deliverable and was never amended.
- **Decision:** Criterion 1 is replaced by three that describe what the task produces — the diff
  for every model whose release carries the inputs its own rules read, with coverage stated per
  count; the readings reported as identical by construction rather than as agreement, naming the
  withheld input; and the models with no arm named with their reason. The original is struck in
  place. A7.1 **stays at `review`**: its remaining open criterion is the A3.3 gate, which is
  blocked behind A3.2 and cannot be discharged from this task.
- **Rejected:** Leaving it stale because A7.1 cannot move past A3.3 anyway — the gate will open,
  and at that point the criterion would be read as met against a result it does not describe,
  which is how A1.6 sat for days. Amending it to "one model" without the coverage and
  by-construction clauses — the 3/6 coverage and the withheld input *are* the finding, and a
  criterion that omits them invites a later reader to treat identical readings as evidence the
  readings do not matter. Widening A7.1 to cover the missing models — D-049 placed them
  elsewhere deliberately and A7.2 closed them.
- **Consequence:** No number changes and no artefact is touched. Phase A's conformance claim is
  unaffected: it was always one model with its coverage stated, and the write-up's wording was
  already bounded by A1.1's verdict and by the A3.3 and X3.1 holds. The audit's general finding
  stands and is not fixed by this entry: nothing checks a task's Done-when against the decisions
  that supersede it, so `board.py --check` passes on criteria that have stopped describing their
  task. This is the third instance found in two days — A1.6, A2.4, A7.1.

### D-175 — Two documentary defects in this log are corrected in place, against its append-only rule
- **Date:** 2026-10-19
- **Task:** X1.1 (repo audit)
- **Context:** An audit of this log found the ID space clean — no duplicates, no gaps, no
  dangling citations, no missing or future dates — and two factual defects in its renumbering
  notes. The ten `Numbering:` lines on D-120 to D-129 each state that "A2.4 took the whole
  D-110..D-119 range first"; D-110 and D-111 are **A2.1's** entries, and only D-112 to D-119 are
  A2.4's. And "D-134" resolves two ways: it is a live A1.6 entry *and* the number A1.8's D-137
  was renumbered away from, with no cross-link between them, so a reader meeting the number in a
  published commit message cannot tell which is meant without finding D-137's note.
- **Decision:** Both are corrected **in place** — the misattribution in the ten notes, and a
  reciprocal cross-link added at D-134 and D-137 — rather than only by appending this entry. The
  project owner decided this explicitly when the alternatives were put. The append-only rule
  exists so that a *decision* cannot be quietly rewritten after it was acted on; a wrong task
  attribution inside a renumbering note is not a decision and nothing was ever acted on because
  of it. A correction fifty entries later does not reach the reader who is standing at D-120,
  which is the only reader it was for.
- **Rejected:** Appending this entry alone and leaving the notes untouched — strictly
  append-only, and useless to the reader it exists to serve. Rewriting the `Numbering:` lines
  without recording that they were changed — that *would* be the thing the rule forbids, so each
  correction is marked and points here. Deleting the D-134/D-137 ambiguity by renumbering one of
  them now — both are cited from several places and from published commit messages, and moving
  either would strand those citations to fix a readability problem a cross-link solves.
- **Consequence:** No decision's substance changes and no citation resolves differently. The
  precedent is narrow and worth stating so it is not stretched: **a factual error in an entry's
  metadata may be corrected in place, marked; an entry's Context, Decision, Rejected or
  Consequence may not** — those are corrected by a new entry, as D-154, D-156 and D-162 were.
  `tools/decisions.py` now fails CI on a duplicate ID, so the collision these notes record is
  caught deterministically rather than by git happening to notice.

### D-176 — A2.4 is done: D-161 binds A3.2 and the write-up, not A2.4's tables, so yesterday's withdrawal of its completion claim is itself withdrawn
- **Date:** 2026-10-19
- **Task:** A2.4
- **Context:** Yesterday's repo audit withdrew A2.4's "every Done-when criterion is met" claim, on
  the grounds that D-161 had changed what may be reported from its tables after that claim was
  written, and recommended amending criterion 1 the way A1.6's (D-170) and A7.1's (D-174) were.
  Re-read against D-161 itself, that was over-cautious. **D-161's own header reads "A2.4 (governs
  A3.2 and the Phase A write-up)" and its Consequence names only those two**: A3.2 must not pool
  the registries' fractions, and the write-up carries the composition and absolute counts with
  any percentage naming its denominator. It places no requirement on A2.4's tables. A2.4's three
  criteria — hit tables with route attribution, two-tool concordance on a documented sample,
  parameters and versions recorded — are met as written, and D-161 is a constraint on the
  consumers of those tables rather than a change to the deliverable. That is the material
  difference from A1.6 and A7.1, where the deliverable itself had changed.
- **Decision:** A2.4 moves to `done`. Criterion 1 is **not** amended. The two gaps the audit found
  are real and are tracked where they belong rather than held against this task: D-173 records
  that D-161's cross-registry figures still have no emitter and that A2.4's twelve published
  tables predate the `denominator` and `composition` fields, and A3.2 and A6.1 are the tasks the
  rule binds. Depth stays at 0.25% as the shipped result, on this task's own standing framing that
  deepening to 2.5% "is an improvement to the strength of the claim rather than a missing
  criterion" — so the open depth question is not a completion blocker either, and it lapses with
  the task rather than carrying forward as an owner decision.
- **Rejected:** Amending criterion 1 to require denominator-named reporting, as the audit
  proposed — it would import a downstream constraint into an upstream task's criteria, and the
  consequence would be that A2.4 could not close until a write-up that does not yet exist had
  consumed its tables correctly. Leaving A2.4 at `review` until D-161's cross-registry emitter is
  built — that work is tracked in D-173, it is not in A2.4's criteria, and parking a finished
  measurement behind it keeps a fourth task showing as in-flight when nothing is. Re-running the
  twelve tables so they carry the new fields — both fields derive from rows the tables already
  hold, so the re-run buys a format change for real spend, and D-173 already declined it.
  Deciding depth now in order to close — the depth question was never a criterion, and answering
  it under time pressure to tidy a status is the wrong reason to spend $7 and 33 wall hours.
- **Consequence:** Phase A's prophage result is final at 0.25% of both releases, as a lower bound
  on two registries whose fractions are not comparable. **The whole of D-161 now rests on A3.2 and
  A6.1**, and neither has yet consumed an A2.4 table: A3.2 is blocked, A6.1 is behind the A3.3
  gate, and the tables they will read do not carry the restriction in-band. That is the live risk
  this entry creates and it is stated rather than hidden — D-173's fields will be present only on
  tables produced after that code merges. The audit's general finding also stands uncorrected by
  this entry: nothing checks a task's Done-when against the decisions that supersede it, and this
  is the fourth task in two days where that question had to be asked by hand — A1.6, A2.4, A7.1,
  and now A2.4 again in the other direction. Being wrong in *this* direction is the cheaper error,
  but it is still an error: the check was a judgement call made twice, two days running, by
  reading prose.

### D-177 — Correction to D-172: the prefilter did not manufacture a false null, and exhaustive search is a robustness choice rather than a rescue
- **Date:** 2026-10-19
- **Task:** A2.2
- **Context:** D-172 recorded that foldseek's prefilter "silently returns nothing" against the
  141-structure reference set, citing a smoke run where 77 called proteins produced
  `76 sequences with 0 size result lists` against 49 hits from the same databases searched
  exhaustively. It concluded that shipping the prefilter "would have produced a complete set of
  well-formed shards reporting no surviving folds anywhere in either Evo release — a false null,
  manufactured". **That conclusion is not supported by the evidence, and this entry withdraws
  it.** Two measurements, both made after D-172 was written:
  **1. The 49 hits are noise.** Their bit scores run from **2 to 6**, every one of them against
  a `class_i_fusion` reference. A2.2 stores hits only at or above 15 bits and declares detections
  at **500** (D-171), so not one of the 49 would have survived either cut. The prefilter was
  discarding alignments that this pipeline discards anyway. `hits=0` was the correct answer for
  those records, and the tool returning it was the tool working.
  **2. At the declared threshold the two geometries agree.** Re-scoring the full 1,567-query
  calibration both ways: prefiltered 34,822 rows, exhaustive 37,286 — and at 500 bits the
  near-fold decoy rate is **3/389 either way** and the true-positive count is **242 against
  244 of 392**, a difference of two queries, or 0.5%. The declared threshold, its brackets and
  the chosen alignment mode are identical. There is no false null in that comparison, and D-172's
  own observation that "the threshold re-derives unchanged" should have been read as evidence
  against its headline rather than as a robustness footnote to it.
- **Decision:** **Exhaustive search stays**, and `EXHAUSTIVE_SEARCH` keeps its place as a module
  constant rather than a flag — but it is recorded as a *robustness and determinism* choice, not
  as a fix for a result-destroying bug. The reasons that survive scrutiny: the prefilter's
  behaviour depends on query count, so a threshold measured at one scale and applied at another
  rests on an assumption nobody is checking; with 141 targets the heuristic buys nothing, because
  aligning every query against every reference is exact and negligible beside 3Di prediction,
  which D-163 measured at 173x the profile search it feeds; and D-076 already rejected E-values
  for drifting with database size, so a prefilter whose behaviour drifts with query count is the
  same defect one layer down. Those justify the choice on their own.
- **Rejected:** Leaving D-172 as written. It is an append-only log, so the entry stands, but an
  overstatement about a result-destroying bug is exactly the kind of claim §7's adversarial
  reader would check first — and finding it unsupported would cost more credibility than the
  correction does. `AGENTS.md` asks for the audit to be airtight against a reviewer who wants
  the result to be wrong; that cuts both ways, and an alarming claim of ours is as much in scope
  as a convenient one.
- **Consequence:** the pipeline is unchanged and no number moves — D-171's threshold, brackets and
  mode were already measured under the exhaustive geometry. What changes is the claim attached to
  it. Also worth carrying forward: the 2-to-6-bit noise was **entirely** against
  `class_i_fusion` references, the one fold this project assembled itself (D-166) and already
  flagged as the weakest of the three. That is a second, independent reason to treat that fold's
  rows cautiously, and it is a reason the decoy calibration could not have surfaced, since the
  calibration's queries were ECOD domains rather than full-length corpus proteins.

### D-178 — A1.8's figures carry intervals that include zero, so the count and the rate become separate claims
- **Date:** 2026-10-19
- **Task:** A1.8
- **Context.** The band artefact's interval was computed over any-identity hits while the
  figure being quoted was the ≥0.70 band — different sets of records, so the headline had no
  uncertainty attached at all, in breach of the non-negotiable that uncertainty travels with
  the estimate. The per-family hit counts restricted to a threshold had never been recorded,
  so this needed a fourth pass over shard 0 rather than a recomputation (`a9e369a`,
  `corpora/results/a1-8/band-select-agent-intervals.json`, all six cells, nine groups).
- **The measurement.** Over 1,097,174 records and **34 seed families**:

  | reading | ≥0.70 | 95% CI | design effect | exact 1.00 | 95% CI |
  |---|---|---|---|---|---|
  | mode 0 | 0.8362% | 0.2978% – 1.3747% | 999 | 0.01048% | 0 – 0.02486% |
  | mode 1 | 0.9135% | 0.3526% – 1.4745% | 993 | 0.01130% | 0 – 0.02606% |
  | mode 2 | 0.9086% | 0.3488% – 1.4685% | 994 | 0.01167% | 0 – 0.02762% |

  Identical across all three sensitivities, as every other figure in this band has been.
- **A design effect near 1,000 is the finding, not an inconvenience.** The honest interval is
  about 31 times the binomial one. Matches are clumped into so few families that 1,097,174
  searched records buy an effective sample of a few dozen. D-104 raised exactly this as the
  objection to sampling and D-140 chose the family as the sampling unit because of it; this
  is what that choice costs when the denylist names 53 taxa collapsing to 34 families.
- **Decision: the count and the rate are separate claims and are written separately.**
  - **The count is an observation.** 115 to 128 records in this shard match select-agent seed
    material at identity 1.00. They were found and counted; no inference is involved, and the
    interval does not bear on it. This may be stated.
  - **The rate is an estimate whose interval includes zero.** 0.0105% to 0.0117% with a lower
    bound of 0 at 95%. Generalising it to the corpus is **not supported**, and no sentence
    may imply the exact-match rate is reliably above zero.

  So "material identical to sequences from organisms on the list is present in the sampled
  corpus, and we counted it" is supportable; "the corpus contains exact matches at a rate of
  0.011%" is not. The ≥0.70 figure is better placed — its interval excludes zero — but it
  spans a factor of 4.9 and must always be quoted with it, never as "about 0.9%".
- **What would and would not narrow these.** More shards add corpus and not families, so they
  would barely move the intervals: the variance is between families, and shard 0 already
  contains all 34. **A wider seed band is the only thing that helps**, because it adds seeds
  and therefore families. Band 2 at 1/10 would draw roughly ten times the seeds; whether that
  multiplies families is an empirical question this band cannot answer, since the 34 come from
  53 named taxa and the ceiling may be near. **Nobody should buy more shards expecting a
  tighter interval.**
- **Rejected:** Quoting the point estimate with the interval in a footnote — an interval that
  includes zero is not a footnote to its estimate, it is the main thing known about it.
  Reporting the binomial interval, which is 31 times narrower and would be false precision of
  exactly the kind D-104 warned of. Dropping the exact-match result because its rate is not
  significant — the count is an observation and remains the sharpest thing this arm has, since
  it needs no threshold argument (D-107's unpublished threshold does not touch identity 1.00).

### D-179 — D-164's GPU throughput does not survive a real shard: A2.2 at pre-registered depth costs multiples of the project's compute budget
- **Date:** 2026-10-19
- **Task:** A2.2
- **Context:** D-164 measured a 64x GPU speedup from a ladder of called proteins and projected
  **24.7 instance-hours** for A2.2's pre-registered depth (363 Maa), which is the figure the $30
  ceiling in D-165 was judged affordable against. The first real shard contradicts it.
  **What was run.** One shard at the pre-registered depth — Evo 2's viral component at rate
  0.001, no caps — on a `g6.xlarge`, 180-minute window, GPU proved present and in use
  (`prostt5-f16.gguf` digest-verified, 57x this container on identical input, so no CPU
  fallback). 3Di prediction ran for **more than 175 minutes and did not finish**. The hard-stop
  timer fired, the instance terminated as designed, and **no shard was written** — there is no
  checkpoint inside a shard, so the compute is simply lost. Cost: about $2.41.
  **How far off that is.** The shard's residue count is not measured — the heartbeat only gained
  its size fields after this launch, which is its own lesson — but it can be bounded from the
  object: 11.2 GB gzipped over 2,957,495 records, so at ordinary nucleotide compression and
  viral coding density the 0.001 sample is roughly **12 to 15 Maa**. D-164's rate predicts
  **41 to 61 minutes** for that. It took over 175 and was unfinished, so the real rate is worse
  by **at least a factor of three**, and the factor cannot be pinned from this run.
  **What that does to the bill.** At three times D-164's rate the pre-registered depth is
  upwards of **70 instance-hours**, or **$55-60** on demand — against a $30 ceiling of which
  about $7 is already spent. A2.2 at A2.1 parity is not short of budget by a margin; it is over
  by a multiple.
- **Decision:** **D-164's projection is withdrawn as a basis for planning, and no further A2.2
  compute is committed until the rate is measured on a real shard rather than a ladder.** The
  specific thing to measure, and it is cheap: relaunch the same shard with a short window so it
  reads, calls genes, publishes `records`, `genes` and `residues` from the now-fixed heartbeat,
  and dies — about $0.40 for the exact denominator plus a partial rate. Only then is a price
  quotable.
  Recorded as the reason the ladder misled, for whoever sizes the next one: D-098 warned that a
  benchmark which never leaves the fixed-cost regime is wrong by orders of magnitude, and the
  response was a ladder up to 20,000 proteins. That escaped *fixed* cost and still did not
  resemble the job — a real shard is hundreds of thousands of proteins of corpus-realistic
  length, and whatever degrades between the two (batching, memory pressure, length
  distribution) is exactly what the projection needed to capture. **The lesson D-098 taught was
  applied one notch short: the benchmark has to resemble the job in size as well as in regime.**
- **Rejected:** Quoting a revised figure from this run alone — the residue count is estimated
  from a compressed file size, so the factor is a bound and not a measurement, and this task has
  already produced one overstated claim (D-177) from reasoning past the available evidence.
  Scaling the container's CPU rate by the measured 57x — that 57x came from a 61,297-residue
  input where model load dominates, which is the same fixed-cost error one level down.
  Pressing on with the remaining four shards on the strength of D-164 — that is $55-60 of
  compute authorised against a projection a real shard has already falsified.
- **Consequence:** A2.2's affordability is now the open question, not its method. The fold
  universe, the threshold, the shard contract and the assembly are all finished and tested; what
  is unproven is that the pre-registered depth can be bought. Three ways forward exist and the
  choice is the project owner's: a shallower sample, which is reportable but weakens the
  comparison with A2.1 that parity was chosen for; more budget; or recording the cost itself as
  the finding, which D-163 already set the precedent for when it turned the CPU route's
  infeasibility into a result. Worth weighing alongside the separate observation that §A2's
  three folds are concentrated in virus groups that are a minority of a phage-dominated IMG/VR,
  so the depth being bought may be buying a near-certain null.

### D-180 — A2.2 does not buy the pre-registered depth; the cost is the finding, and the tables ship as `not_searched`
- **Date:** 2026-10-19
- **Task:** A2.2
- **Context:** D-179 established that one real shard at the pre-registered depth did not finish
  3Di prediction inside a 180-minute GPU window, bounding the true rate at **three times or
  worse** than D-164's ladder projection and the full depth at **70+ instance-hours, $55-60 on
  demand** — against a $30 ceiling (D-165) with about $7 already spent. Put to the project owner
  with four options: measure the exact rate first, buy the depth with a raised budget, reduce the
  depth to what the budget allows, or record the cost as the finding. **The owner chose to record
  the cost and not buy the depth.**
  Two things made that the sensible call rather than a retreat. The arithmetic is not close — the
  shortfall is a multiple of the whole budget, not a margin, so no amount of tightening reaches
  it. And the depth would most likely have bought a **null that reflects corpus composition
  rather than the filter**: IMG/VR is dominated by tailed bacteriophages, which carry the HK97
  capsid fold rather than a jelly-roll, have no RdRp because they are DNA viruses, and have no
  class I fusion glycoprotein at all. All three folds §A2 names are concentrated in virus groups
  that are a minority of the corpora they would be searched against. D-163 set the precedent for
  this shape of outcome when it turned the CPU route's infeasibility into a result rather than a
  blocker.
- **Decision:** **A2.2 ships without a searched corpus**, and the seven per-manifest tables are
  emitted with `estimate_kind: not_searched`. That is not a placeholder: `metrics/detections.md`
  defines `not_searched` for precisely this case — "every count is zero *by construction* and
  none of it is evidence of absence" — and `amazebio.detect` derives it from the absence of any
  searched source, so A3.2 **cannot** pool these tables with a `population` or `lower_bound` one
  even by accident. The per-source rows distinguish two reasons that would otherwise collapse
  into one: components this detector never covers (GTDB's genomes are A2.4's, the ESM3 proxy is
  A1.6's reader) and components **in scope and not bought**, which is the finding.
  **What A2.2 does deliver, and it is most of the task.** The fold universe, re-derived at family
  level, corrected and shipped as an artefact with its exclusions (D-169). The threshold,
  calibrated against decoys that are real non-viral proteins sharing the folds, with its two
  bracketing values and its alignment mode fixed before any corpus hit was seen (D-171, D-177).
  The structural coverage gap §A2's Done-when criterion asks for — the fusion class has no ECOD
  node and is this project's own construction. A measured sensitivity ceiling: 61.7% of held-out
  true fold members detected at the declared cut, 6.1% missed at any threshold. The cost of the
  route itself, measured twice (D-163 on CPU, D-179 on GPU). And a tested, resumable pipeline
  that would run the pass if the depth were ever bought.
- **Rejected:** Reducing the depth to fit the budget — a shallower sample is reportable, but it
  weakens the comparison with A2.1 that parity was chosen for (D-164), and it makes an already
  near-certain null still less informative; paying for a weaker version of a result that was
  unlikely to say anything about the filter is the worst of both. Raising the budget — the owner
  declined, and the composition argument says the instrument is probably wrong for this corpus
  regardless of price. Leaving the tables unwritten, or writing them with no rows — the schema
  has a kind for "not searched" exactly so that this situation is expressible rather than
  silent, and `AGENTS.md` forbids any arrangement that makes a null harder to see; an absent
  table is the strongest possible version of that.
- **Consequence:** Phase A's structural route contributes no detections to A3.2, and the reason
  is recorded in the artefacts rather than only in prose. The open question this leaves is not
  A2.2's method but **whether §A2 named the right folds**: a phage-dominated corpus argues for
  HK97 capsid, large terminase and portal folds, which would measure what the audit cares about
  in the corpora it actually has. That is a `DESIGN.md` question and a new task, not a widening
  of this one — `AGENTS.md` is explicit that an adjacent problem gets a new file and a new id.

### D-181 — Correction to D-157: both halves of the published denylist fall inside the span of readings, and comparing sums hid it
- **Date:** 2026-10-19
- **Task:** A1.8
- **Supersedes in part:** D-157, whose headline — "the published figure sits below every
  reading we can construct from the regulation" — does not survive the decomposition below.
- **Context.** Reading PR #24, the project owner asked whether removing the material that
  aligns to things other than viruses would bring the count closer to the paper's. Nothing
  A1.8 had produced could answer it, because A1.8 had only ever compared **totals**:
  1,277,073 / 321,669 / 229,787 against 187,000. ESM3 does not publish 187,000. It publishes
  *"147K non-viral sequences and 40K additional viral sequences"* (version of record A.6.1
  p47) — two figures, which D-106 recorded faithfully, D-146 added together, and D-150 and
  D-157 then compared as a sum without re-reading the sentence they were quoting.
- **Measured for nothing, from the artefact already in hand.** The 2.64-hour pass over the
  182.7 GB archive recorded per-taxon counts, and the Viruses superkingdom is in the same
  pinned taxonomy (2023-04-01) the reading was resolved against. So the split is a
  regrouping of a measurement already taken, needing no second pass — the same argument
  D-157 used to measure strain descent. `tools/select_agent_decomposition.py` produces it;
  both readings still sum to D-157's figures exactly, which a test asserts.

  | reading, UniProtKB at 2023_02 | viral | vs 40K | non-viral | vs 147K |
  |---|---|---|---|---|
  | named organisms **and their strains**, all three parts | 828,606 | 20.7x | 448,467 | 3.05x |
  | …less the avian influenza entry | 62,094 | 1.55x | 448,467 | 3.05x |
  | **named organisms only**, all three parts | 137,429 | 3.44x | 184,240 | **1.25x** |
  | …less the avian influenza entry | 45,547 | **1.14x** | 184,240 | **1.25x** |
  | named organisms only, **42 CFR 73 alone** | 18,327 | **0.46x** | 92,225 | **0.63x** |

- **The hypothesis is inverted by the data, and usefully so.** The published denylist is 79%
  non-viral, and the non-viral half is the one that nearly reconciles — 184,240 against
  147,000, 1.25x, on the narrowest full-list reading. The excess is *viral*, and it is one
  entry: avian influenza, which D-137 deliberately read as Influenza A entire, on the stated
  grounds that for an audit an over-inclusive denylist overstates what should have been
  removed rather than understating it. Set that one entry aside and the viral half is 1.14x.
  Removing non-viral material moves away from the published figures, not toward them.
- **Both published halves sit inside the bracket, and that is what overturns D-157.** "The
  Select Agents and Toxins List" is three codified parts, and the source cites the summary
  page that covers all three — but 42 CFR 73 alone is a reading the same regulation admits,
  and D-138 recorded the version question without reaching the scope question. Read narrowly
  it gives 18,327 viral and 92,225 non-viral: **below both published halves**. Read as all
  three parts without descent it gives 137,429 and 184,240: above both. Each published half
  is therefore bracketed by readings constructible from the regulation, and the published
  text does not say which was taken. D-157 reported that the published figure sat below
  everything; it does not.
- **Why the sum hid it.** The pooled ratio for the named-only reading is 1.72x, which
  resembles neither half — 3.44x viral and 1.25x non-viral. A total can be matched, or
  missed, by two errors of opposite sign, so a sum is the weakest form of this test and the
  source had already supplied the strong one. Checking a published decomposition against its
  own sum discards the constraint that makes it evidence.
- **What may now be claimed, and what may not.** The honest statement is an
  under-specification finding (§A0): the regulation admits a span of readings whose viral
  halves run 0.46x–3.44x and whose non-viral halves run 0.63x–3.05x of the published figures,
  both published halves fall inside that span, and neither the paper nor the regulation says
  which reading was taken. D-157's stronger conclusion — "either the denylist omitted
  material the stated procedure would include, or the description is incomplete" — is **not
  supported** by the counting evidence and is withdrawn. It remains true that no single
  reading reproduces both halves exactly, and that is unremarkable at this precision.
- **What D-157 keeps.** Its measurements, all of which stand. Its correction of D-150's
  "comfortably within release drift", which was the substantive error. And its contrast with
  the viral denylist, which is untouched: that list's 1.34x gap has a described cause in the
  paper's second clause, and no comparable step is described for this one. What changes is
  that the select-agent gap is now attributable to our own reading latitude rather than left
  as an unexplained discrepancy in the source.
- **Rejected:** Adopting "named only, 42 CFR 73 alone, avian influenza read narrowly" as the
  reading, on the grounds that it would land closest on both halves — fitting a reading to a
  target is what D-150 withdrew a hypothesis for, and two targets instead of one does not
  make it inference. Promoting the HHS-only reading to primary: D-138 pinned all three parts,
  the model card cites the page covering all three, and the narrow reading is a sensitivity
  that is now measured rather than argued about. Withdrawing D-157 entirely — one claim it
  drew is wrong, the rest is sound, and the log is append-only. Re-running the archive pass:
  the per-taxid detail answers this exactly and for nothing.
- **Process point, the fourth of this kind in this task.** D-150 was a quiet caveat in code,
  D-154 a quiet qualifier in a docstring, D-156 a reading already fixed in `policies/specs/`
  that nobody re-read — and this is a published figure quoted as a sum for three decision
  entries while its own decomposition sat in the sentence being quoted. In every case the
  information was already in the repository. **Re-read the source sentence when you cite the
  number, not only when you first record it.**

### D-182 — A2.3's corpus is one release's eukaryotic genomes, staged as a hash-sampled set of whole assemblies
- **Date:** 2026-10-19
- **Task:** A2.3
- **Context:** `DESIGN.md` §A2 asks for endogenous elements in "surviving host genomes", and two
  facts settle what that means before any instrument is chosen.
  **A2.3 is structurally a one-release task**, where A2.4 was a two-release one. Evo 1's release
  exposes no eukaryotic genomes at all — `OG1_COMPONENTS` is `stage2`, `stage1_gtdb` and
  `stage1_imgpr` — which D-019 already recorded as "the scope gap opens with Evo 2's additions
  rather than with Evo 1".
  **Evo 2's eukaryotic component is not staged, and staging it was explicitly left to this
  task.** `opengenome.OG2_COMPONENTS` declares `ncbi_eukaryotic_genomes` (2.17 TB) and
  `eukaryotic_genic_windows` (129 GB) with `tier1=False`. D-031 costed four staging tiers, chose
  134.2 GiB, rejected the 2.88 TB tier that would have covered this one, and left the
  consequence: "A2.3 and A4.1 must each stage their own component before they can run". The
  corpus bucket has no `s3:DeleteObject`, so every staged byte is permanent and recurring, which
  is why D-031 escalated the tier rather than deciding it and why D-119 is the precedent for an
  A2 detector getting its corpus staged.
  Put to the project owner with three costed options: the full 2.17 TB at about $50/month
  forever; a hash-sampled set of whole assemblies at about $0.13/month for 0.25% and $0.50/month
  for 1%; or stage nothing and ship `not_searched` as A2.2 did under D-180. **The owner chose the
  sampled set.**
  **The component's layout was measured before the sampling unit was chosen, not assumed.** The
  pinned tree (`opengenome.fetch_tree(OG2)`, 1,126 files and 5,523,240,795,932 bytes, matching
  the pin exactly) puts `fasta/ncbi_eukaryotic_genomes` in **90 tar files of 20-44 GB**, and a
  Range walk of `batch1.tar`'s header chain shows members of the form
  `batch1/GCA_018245875.1.fasta.gz` — one gzipped FASTA per assembly, named for its NCBI
  assembly accession, ranging from 4.7 MB to 428 MB compressed. That is the **same shape as Evo
  2's GTDB component**, which `amazebio.gtdb` already reads: `assembly_of_member` and
  `iter_og2_genomes` transfer unchanged. The first design this task considered — sampling
  per-assembly files by name — was not available, and the measurement is what replaced it.
- **Decision:** A2.3's corpus is Evo 2's `ncbi_eukaryotic_genomes` only, and the sampling unit is
  the **tar member**, which is one assembly.
  **Selection** is the project's existing hash rule, `blake2b(key=seed, id)[:8] < rate · 2⁶⁴` at
  seed **20261015**, keyed on the assembly accession recovered from the member name. The record
  is the genome (D-136), so the sampling unit is the unit a detection is attributed to; the rate
  is nested (D-078), so a deeper band is a superset and nothing already staged is re-staged or
  re-searched; and membership is checkable per accession afterwards without re-running anything.
  **Rate is 1%**, inside the figure the owner approved, for about 22 GB and $0.50/month.
  **Acquisition is a two-pass design, and the first pass is cheap enough to be worth having on
  its own.** Pass one walks all 90 tars' header chains over HTTP Range reads and emits an
  **assembly index** — accession, tar, byte offset, compressed size — transferring 512 bytes per
  member rather than the member. Pass two ranged-GETs only the sampled members, verifies, and
  uploads them to the corpus bucket. Neither pass reads the 2.17 TB, which is what makes a
  sampled stage of an unstaged component possible at all.
  **`eukaryotic_genic_windows` is not staged.** Its 129 GB is seven parts of one split gzip
  stream (`windows_5kb.fasta.gz.aa` … `.ag`), so it is not independently samplable at the
  assembly level; it is cut from the genomes above, so it adds no independent sequence; and it is
  cut around genes, which biases against exactly the intergenic, pseudogenized relics the EVE
  arms look for.
  **`tier1` stays `False` on both components.** Flipping it would make `tools/stage_opengenome.py
  --stage` take the whole 2.17 TB on its next run against a bucket that cannot be emptied. A2.3
  stages its sample through its own path, and `tier1` keeps meaning "what A1.2's staging tier
  covers".
- **Rejected:** **The full 2.17 TB** — the owner declined the $50/month, and it is not the
  binding constraint anyway: detection compute sits on top of it and is uncalibrated, and
  D-117/D-149 established that assuming that rate is how a design decision gets taken by
  accident.
  **Staging nothing and shipping `not_searched`** — defensible, and it is what A2.2 did
  yesterday, but the two situations differ in the direction that matters. A2.2's null was near
  certain on composition grounds, because the folds §A2 names are concentrated in virus groups
  that are a minority of its corpora. Here composition argues the other way: endogenous
  retroelements are near-universal in eukaryotic genomes, so a sampled pass is expected to detect
  rather than to report a null, and the route §A2 names first for host genomes would otherwise
  contribute nothing at all to A3.2.
  **Sampling contigs, windows or bytes rather than assemblies** — would require reading the
  component to sample it, and would attribute detections to fragments of a genome rather than to
  the genome, breaking D-136's record definition and the per-genome denominator the retroelement
  arm needs.
  **Substituting an external genome set** (Ensembl, a RefSeq query) for the component — the audit
  is of a named corpus, and a different set of assemblies is a different corpus. D-116's rule
  that neither release substitutes for the other applies with more force to a set the release
  does not contain.
- **Consequence:** Evo 1's A2.3 tables are `not_searched` **by construction, and for a reason
  that is not A2.2's**: the component does not exist in that release, where A2.2's existed and
  was not bought. Those two must not collapse into one row, so the per-source reason strings
  carry the difference into the artefact rather than leaving it in this log.
  A2.3's figures are lower bounds (D-115), and the 1% band is nested, so depth can be bought
  later without re-staging or re-searching. The assembly index is reusable: A4.1 still has its
  own 252 GB metagenomic component to stage and this decision does not cover it, but the
  header-walk pass is the same instrument if that component is also tarred.
  One thing this decision does **not** settle, deliberately: no reading's rules reach this
  component, because D-016 withdrew the strict reading's endogenous-element rule. So every
  detection here is `out_of_scope` under the literal and charitable readings and
  `retained_by_design` under the strict one — structurally the same situation as GTDB, which is
  why A2.4's route handling transfers. The instruments, their thresholds and the false-positive
  modes are a separate pre-registration, taken before anything is searched.

### D-183 — A2.3's retroelement arm: registry, selection rule and threshold, fixed before anything is searched
- **Date:** 2026-10-19
- **Task:** A2.3
- **Context:** D-182 settled what A2.3 searches. This settles what it searches *with*, and it is
  written before a single genome has been read, because `AGENTS.md` requires thresholds and
  analysis specs to be fixed before results are inspected.
  §A2 names two instrument classes for host genomes: Dfam/RepeatMasker and LTR finders for the
  retroelement route, and a separate search for the non-retroviral route. This entry covers the
  **retroelement arm only**. The other arm needs a different registry with a different authority
  and a different denominator rule, and bundling an arm whose cost and universe have not been
  measured into a pre-registration would make this one weaker rather than the other one stronger.
  It gets its own entry when it is built.
  Four things were measured first, and each changed the design that preceded it.
  **The registry does not ship as a profile library.** Dfam is a partitioned HDF5 database, so
  the profiles have to be exported from it. The reader is `famdb`, and the pairing is the
  publisher's own: Dfam 4.0's `FamDB/README.txt` states "This new format is compatible with FamDB
  tool v3.0.0, and RepeatMasker 4.2.4." The previous release's files are format 2.0.0 and
  `famdb` 3.0.0 refuses them outright — confirmed by trying it — so the tool and the release are
  one pin, on D-112's principle that an attested pairing is what a pin needs.
  **RepeatMasker is not needed and was dropped.** Dfam's profiles are nucleotide HMMs, and
  `pyhmmer.hmmer.nhmmer` — already pinned for A2.1 — searches them directly against genomic DNA.
  That matters for more than dependency hygiene: it means no gene calling and no six-frame
  translation, which is the right instrument for a degraded, pseudogenised relic that no gene
  caller will call. It also avoids a second search engine with its own thresholds and its own
  cost model. The conda package was checked and ships **no** repeat library — 25 MB of annotation
  data and no database — so it would not have saved the export step either.
  **The curated component is 30,621 families and the uncurated one is two orders of magnitude
  larger.** Measured from the pinned release: curated HMMs are 688 (root) + 29,933 (Bilateria),
  about 2.1 GB compressed, while the uncurated HMM partitions run to 10-18 GB *each* across more
  than a hundred partitions.
  **Dfam's own thresholds do not cover every family, and the gap is measurable.** Of the 8,593
  curated LTR-class models in the Bilateria partition, **7,831 (91.1%) carry a general GA/TC/NC
  threshold and 762 (8.9%) do not**. Most families instead carry per-species `TH` lines — 1,448
  of them across the 688 root families alone — which is a better threshold for one named species
  and unusable as a fixed universe, because a per-species cut makes the denominator change from
  genome to genome.
- **Decision:** **Registry.** Dfam **4.0** (release date 2026-05-22), the **curated HMM**
  component only: `dfam40.0.h5` (the required root metadata), `dfam40.curated.hmm.0.h5` (root,
  688 families) and `dfam40.curated.hmm.1.h5` (Bilateria, 29,933 families), each pinned by the
  md5 the publisher serves beside it and verified on acquisition.
  **Selection rule.** The registry universe is the curated families whose Dfam Type is `LTR`,
  and the arm's headline is the **ERV subtypes** within it: `ERV1`, `ERVK`, `ERVL`, `ERVL-MaLR`,
  `ERV` and `ERV-Foamy` — **5,565 of the 8,593** LTR-class Bilateria models, counted before any
  search. The remaining LTR subtypes (`Gypsy` 2,041, `Pao` 567, `Copia` 97, `Ngaro` 38, `DIRS`
  29, and 256 classified `LTR` with no subtype) are **retained in the universe and reported as
  their own rows**, never merged into the ERV count: they are LTR retrotransposons rather than
  integrated retroviruses, so a figure that pooled them would overstate the viral-derived
  fraction. The selection runs in this project's own tested code against the class string the
  export carries, not through the reader's `--class` flag, for the reason D-075 derived Pfam's
  viral subset here rather than trusting a label and D-166 re-derived A2.2's fold universe.
  **Threshold.** Dfam's **own general GA cutoff, per model**, exactly as A2.1 took Pfam's own
  per-model gathering cutoffs under D-076 rather than an E-value this project picked. A family
  with no general GA is **excluded from the universe and reported as excluded, by accession**,
  rather than given a threshold this project invented: 762 models, 8.9% of the LTR class, and
  that number is this arm's declared sensitivity blind spot in the same way D-083 is A2.1's.
  **Element kind and route.** Every detection on this arm is `ENDOGENOUS_RETROELEMENT`, assigned
  from the instrument rather than from the component — which is the one place A2.3 differs from
  D-079's rule, and legitimately: D-079 says a *profile* hit cannot distinguish element kinds and
  leaves the stronger claim to "A2.3 (EVEs) and A2.4 (prophage)", so making that claim is this
  task's deliverable rather than an inference it is forbidden. Route comes from
  `amazebio.apply.route_for` as for every other detector, and on this component it is
  `out_of_scope` under the literal and charitable readings and `retained_by_design` under the
  strict one (D-016, D-182).
  **Depth is not fixed here, and deliberately.** The cost of one genome against this registry has
  not been measured, and D-117 and D-149 between them establish that the measured rate came in
  2.74x off a single-genome extrapolation while D-098 found an *assumed* rate wrong by thirty
  times. "A cost assumed is a design decision taken by accident." So depth is pre-registered in
  a separate entry, after calibration on real assemblies and before any hit is inspected.
- **Rejected:** **The uncurated component.** It is where most of Dfam's families are, and taking
  it would raise sensitivity. Declined on three grounds: its partitions are 10-18 GB each against
  a 29 GB working disk; its families are de novo products with no curated thresholds, so the
  threshold policy above would have nothing to read; and a de novo family is not an independent
  authority on what a retroelement is, which is what the registry is here to supply. The
  consequence is a lower bound, which is the direction D-115 requires.
  **A threshold of this project's own choosing for the 762 models without one.** Any value would
  be invented, and an invented cut on 8.9% of the universe would be indistinguishable in the
  output from a curated one. Excluding them and naming them keeps the gap visible and keeps every
  reported hit attributable to the publisher's own cutoff.
  **Per-species `TH` thresholds.** More sensitive for a named species, and the export can extract
  them. Declined because the sample spans thousands of species, so the universe would differ per
  genome and `metrics/detections.md`'s one-universe-per-registry rule would be broken — the
  denominator would stop meaning the same thing between two rows of the same table.
  **RepeatMasker, and LTR finders.** RepeatMasker for the reasons above. Structural LTR finders
  are the other instrument §A2 names, and they are genuinely independent — they detect by
  structure rather than by homology — but they return candidate elements with no family identity,
  so they cannot produce the per-family table `metrics/detections.md` specifies and A3.2 merges.
  They are the natural second instrument for a concordance check of the kind D-114 fixed for
  A2.4, which A2.3's Done-when does not require; recorded here as the obvious extension rather
  than silently dropped.
- **Consequence:** The retroelement arm's universe, threshold and element kind are fixed and
  countable before any genome is read, and the two numbers a reader needs to judge its
  sensitivity — 5,565 ERV-subtype models searched, 762 LTR-class models excluded for want of a
  curated threshold — are already on the record. The figures this arm produces will be lower
  bounds for three compounding reasons, all declared in advance: a sampled corpus (D-182), the
  curated component only, and the excluded 8.9%.
  What is still open and is this task's next step: the cost of one assembly against this
  registry, and therefore the depth. Nothing else about the arm moves after calibration — that is
  what makes the calibration safe to run and look at.

### D-184 — The eukaryotic component holds 15,044 assemblies, which is the third number published for it
- **Date:** 2026-10-19
- **Task:** A2.3 (affects A3.2, A4.3, A6.1)
- **Context:** Every figure A2.3 reports is a fraction of "the assemblies in Evo 2's eukaryotic
  component", and nothing in this project had counted them. The release states a file count and
  a byte total, not a genome count, because the component is 90 tars rather than 15,000 files
  (D-182). The index pass built for the sampling design counts them as a by-product, so the
  count came for free once the walker existed.
  Two figures were already on the record and neither is this one. The developers' own words,
  quoted in `policies/corpora.md` §4, are an **acquisition** figure: "All available eukaryotic
  reference genomes were downloaded from NCBI on May 31, 2024 … This resulted in **16,704
  genomes** including an estimated 10.7 trillion nucleotides." D-007 then records **15,148
  deduplicated** eukaryotic reference genomes as what Evo 2 added, after Mash deduplication at
  distance < 0.01 and contig filtering. D-019 had already corrected one confusion between these
  two — 16,704 is the NCBI download, not corpus contents — so the distinction was live before
  this measurement.
- **Decision:** The component's measured population is **15,044 assemblies** across 90 tars,
  totalling **2,174,531,002,595 bytes** compressed, with **no duplicated accession**. Recorded as
  the denominator every A2.3 figure is a fraction of, in
  `artifacts/a2-3/component-summary.json` with the per-assembly index beside it.
  The measurement is complete rather than sampled: all 90 of 90 tars walked, `complete: true`,
  and the byte total agrees with the component's own size in the pinned tree exactly. So the
  **104-assembly shortfall against D-007's 15,148 is a real stated-versus-delivered gap, not a
  staging gap** — nothing is missing from the acquisition, and the released component simply
  carries 0.69% fewer genomes than the release's stated deduplicated count. It is reported as
  such and is deliberately *not* reconciled by guesswork: the published text gives no
  per-assembly accounting between the dedup step and the release, so which 104 and why cannot be
  recovered from it. This is §A0's "under-specification is data" at the scale of a denominator.
  Three properties of the size distribution are recorded with the count because the sampling
  design depends on them: the median assembly is 26.4 MB compressed, the 95th percentile is 636
  MB, and **the largest single member is 28,857,222,864 bytes** — a compressed member of 28.9 GB.
  The minimum is **2,030 bytes**, which is a genome file too small to be a genome and is flagged
  rather than dropped.
- **Rejected:** Taking 15,148 as the denominator because it is the published figure. It is the
  publisher's count of what it deduplicated to, and the audit's subject is the corpus as
  released; using a stated number in place of a measured one is the substitution §A7 exists to
  detect. Both numbers are reported, and the one in the denominator is the measured one.
  Reconciling the 104 by re-running a Mash deduplication against the NCBI snapshot. It would be a
  reconstruction of the publisher's step rather than a reading of the release, it needs an NCBI
  snapshot from May 2024 that is not pinned here, and A2.3 is not the task for it. If it is worth
  doing it is a new task with a new id, per `AGENTS.md`.
  Dropping the 2,030-byte member, or any of the small ones, from the denominator. A near-empty
  assembly is part of the corpus as released and a detector that found nothing in it found
  nothing in it. Excluding it would quietly improve every rate A2.3 reports.
- **Consequence:** A2.3's denominator is fixed and measured, and the 1% band D-182 approved is
  **167 assemblies totalling 16,782,960,377 bytes** — 0.77% of the component by bytes rather
  than 1%, because the hash samples assemblies and the size distribution spans 2 KB to 28.9 GB.
  That is inside the figure the owner approved and is the number the staging pass will write.
  A4.3 maps filter scope against corpus composition and should use 15,044 rather than 15,148 for
  this component, with the gap named. The index is reusable for that and for any later deepening:
  the band is nested at the same seed, so buying depth re-reads nothing.
  The 28.9 GB member is also the reason the walker reads GNU base-256 size fields at all — four
  of the 90 tars carry a member above the octal field's 8 GiB ceiling, and an octal-only reader
  indexed 86 of 90.

### D-185 — Correction to D-183: the ERV headline is 5,420 searched, not 5,565, and both counts now travel
- **Date:** 2026-10-19
- **Task:** A2.3
- **Context:** D-183 fixed the retroelement arm's universe and, in the same entry, two things
  that interact: the arm's headline is the ERV subtypes, **5,565 of the 8,593** curated LTR-class
  models; and a family with no curated general threshold is excluded from the universe and named.
  Both statements are true. Their product was not stated, and it is not 5,565.
  Running the export is what surfaced it. **145 of the 5,565 ERV-subtype models carry no general
  GA cutoff**, so the searched ERV universe is **5,420**. D-183 calls 5,565 "the arm's headline"
  and "counted before any search", which reads as the number of models the arm searches. It is
  the number the class *holds*. A reader quoting the entry would have overstated the search by
  2.6%, and — worse than the size of the error — would have been quoting a denominator that no
  artefact contains.
  This is the D-074 shape rather than a measurement error: a figure that was correct about one
  thing and was going to be cited as another, with nothing in the pipeline positioned to notice.
  The module's own expectation constant was `EXPECTED_ERV_MODELS = 5565` while the function it
  guarded returned 5,420, and strict mode did not compare them, so the inconsistency sat between
  a constant and a return value where no test looked.
- **Decision:** **Both counts are reported, always, and neither is "the" ERV count.**
  `amazebio.dfam.universe` emits `erv_models` (searched: **5,420**), `erv_models_in_class`
  (held by the class: **5,565**) and `erv_excluded_no_threshold` (their difference: **145**).
  Strict mode checks both against `EXPECTED_ERV_SEARCHABLE` and `EXPECTED_ERV_IN_CLASS`, so a
  re-export cannot move either one silently — which is the half D-183's guard was missing.
  **D-183's phrasing is superseded on this point only.** Its registry, selection rule, threshold
  policy, element kind, route handling and its refusal to fix depth all stand unchanged. Where it
  says the arm's headline is 5,565, read 5,420 searched of 5,565 held.
  **The reportable figure is the searched count**, with the held count beside it. The 145 belong
  in the same sentence as the 762: the arm's blind spot is 8.9% of the LTR class overall and
  **2.6% of the ERV subtypes specifically**, and the second number is the one that matters for
  this arm because the ERV subtypes are what it is for.
- **Rejected:** Giving the 145 a threshold so they could be searched, which is the same
  invention D-183 rejected for the 762 and no more defensible restricted to the families the arm
  cares about most.
  Correcting D-183 in place. The log is append-only; D-175 did edit it in place once and said so
  against the rule, and that was for defects that made entries unresolvable rather than for a
  figure that is simply superseded. A correction entry leaves both the original claim and its
  replacement citable, which matters because D-183 was pushed and may already be cited.
  Reporting only the searched count and dropping 5,565. It is the right denominator for "how
  much of Dfam's curated ERV content can this arm see at all", which is a sensitivity question a
  reviewer will ask, and D-183's own blind-spot framing needs it.
- **Consequence:** A2.3's retroelement arm searches **5,420 ERV-subtype models** of 5,565 held,
  within a universe of 7,831 searchable models of 8,593 in the LTR class. Those four numbers are
  in `artifacts/a2-3/registries/dfam-curated-ltr.json` with the 762 excluded accessions listed,
  so every one of them traces to an artefact rather than to this log — which is the gap D-173
  found in D-161 and this entry avoids repeating.
  The pattern generalises past this arm, and is the reason this is an entry rather than a commit
  message: **a count taken before a filter and a count taken after it are different numbers, and
  a pre-registration that states one while implying the other will be read as stating both.**
  A2.1's `families_without_a_hit`, A2.2's excluded fold nodes and A2.4's twelve tables all have
  the same two-sided shape. Where a later entry gives a universe size, it should say which side
  of its own exclusions the number falls on.

### D-186 — The retroelement arm switches to a seeded aligner over model consensus, at 0.25%
- **Date:** 2026-10-19
- **Task:** A2.3
- **Context:** D-183 pinned the arm to profile search and deliberately left the depth to a
  post-calibration entry. The calibration says the profile route cannot have one.
  **The first projection was wrong and this entry supersedes it.** It reported a unit rate of
  14.4 core-seconds per model-megabase and about 480,000 core-hours for the 1% band, and that
  figure was put to the project owner. Two errors, both inflating it, and the calibration's own
  linearity check is what exposed them — `linear_within_10_percent: false`, spread 6.06 — which
  is the whole reason D-183 insisted the measurement be taken at more than one point.
  *Cost does not scale with model count.* Wall time was identical at 4 and 8 models (652.2 s
  against 651.7 s on one assembly, 122.3 s against 121.9 s on another). The right unit is
  model **residues** times megabases, not models times megabases.
  *The timed models were the longest in the library.* The first four in file order total 22,439
  residues, a mean of 5,610 against the registry's ERV **median of 566** and mean of 1,208. The
  calibration had sampled roughly the longest models available.
  **Re-measured across 4, 32 and 256 models** on a 25.6 Mb assembly: 126.0 s, 372.1 s and
  1,656.7 s, so wall rose x2.95 then x13.15 while model residues rose x7.10 then x23.25 —
  sublinear at first where fixed overhead dominates, then roughly linear. Fitted at the
  256-model point, whose mean model length is closest to the registry's,
  **4.962e-4 core-seconds per model-residue-megabase**.
  That puts the full ERV registry over the 1% band at **48,040 core-hours (about $960)** and
  over a 0.25% band at **12,010 core-hours (about $240)** — ten times cheaper than the figure
  first reported, and still one to two orders over anything this project has spent on a single
  pass. A $30 ceiling, A2.2's under D-165, buys 3.1% of the 1% band.
  Put to the owner with three options — switch instrument, buy a thin slice, or report the cost
  as the finding. **The owner chose to switch instrument**, and on being shown the corrected
  figure confirmed it and set the depth at **0.25%**.
- **Decision:** **The arm searches consensus sequences with a seeded aligner.** This is what
  RepeatMasker does and the reason it exists, so D-183's rejection of that whole approach is
  reversed on its cost premise while its registry, selection rule and element kind stand.
  **The consensus comes from the pinned models, not from a new download.** Each curated HMM
  carries a match-state consensus of its own length, read with `pyhmmer`'s `HMM.consensus`. So
  the query set is derived from the registry already acquired and verified under D-183, with no
  second acquisition and no second pin: **5,420 ERV-subtype consensus sequences, 6,545,678 bp**.
  This also sidesteps a real obstacle — Dfam 4.0's *curated consensus* component ships the root
  partition only, so these families' consensus sequences are not in it, and the alternative was
  the per-partition flat files at tens of gigabytes.
  **The aligner is `mmseqs2`, already in `[dependencies]`** for A1.6, so the switch pins no new
  tool. **Consensus is the query and the genomes are the target**, which is the direction
  `AGENTS.md` records as measured rather than assumed: on identical data the small side as query
  took 335 s where the corpus as query had not left the prefilter after 45 minutes.
  **Threshold, fixed here before any hit is seen, and it is this project's own.** Dfam's `GA`
  cutoffs are profile bit scores and do not transfer to an aligner, so they cannot be reused:
  **E-value ≤ 1e-10, alignment length ≥ 100 bp, sequence identity ≥ 0.70.** Declared as a
  choice rather than borrowed from a convention this project has not retrieved from its primary
  source. Every table carries the cut and the per-hit identity and length, so it can be re-cut
  stricter without re-searching — which is what `metrics/detections.md` already requires of the
  `threshold` column.
  **Depth is 0.25% of the component**, a nested sub-band of the 1% D-182 approved at the same
  seed: about 38 assemblies and roughly 13,300 Mb. Nested, so the 1% remains a superset and
  nothing searched here is searched again.
  **The band is fetched to ephemeral scratch and not staged.** D-182 committed to staging the
  sampled assemblies, and that commitment stands for a depth that is actually bought; it is
  deferred here. The corpus bucket has no `s3:DeleteObject`, so staging is permanent, and
  writing 4 GB of it before the arm has produced a single table would be paying for a pin the
  run does not need: the assembly index pins which bytes were read, `fetch_member` verifies each
  member against its own gzip CRC, and a fetch costs 7.5 s for 20 MB. Each assembly is fetched,
  searched and deleted, per D-103.
- **Rejected:** **Keeping the profile instrument at a depth that fits a budget.** At $30 it
  reaches 3.1% of the 1% band, which is 0.03% of the component. A detection would still be a
  detection, but the per-family denominator would be a small fraction of the registry and a null
  would carry no information at all.
  **Reporting the cost as the finding**, which is what A2.2 did under D-180. Declined because
  unlike A2.2's case a cheaper instrument exists, is already pinned, and needs no new data — so
  the cost here is a fact about one instrument rather than about the question.
  **Downloading Dfam's per-partition flat files for consensus sequences.** Tens of gigabytes
  against 20 GB of working disk, to obtain what the models already carry.
  **Reusing Dfam's `GA` cutoffs as an aligner score.** They are bit scores from a different
  instrument; carrying the number across would look like the publisher's threshold while being
  this project's invention, which is worse than declaring a cut outright.
- **Consequence:** The arm becomes affordable and the 0.25% band is a short run rather than a
  purchase. Its figures are lower bounds for four compounding reasons, all declared in advance:
  a sampled corpus, the curated component only, the 762 LTR-class models with no curated
  threshold (145 of them ERV-subtype, D-185), and now a consensus search in place of a profile
  search — a single consensus is less sensitive than the profile it was derived from, and that
  direction is the safe one for an audit reporting survival.
  **The profile route's cost is itself a result and is kept**, in
  `artifacts/a2-3/calibration.json`, because §A2 names Dfam profiles as an instrument and what
  they cost on a corpus this size is a finding a later task can cite rather than re-measure.
  One thing this entry does **not** settle: whether the consensus search and the profile search
  agree where both can run. That is the concordance question D-114 fixed for A2.4, A2.3's
  Done-when does not require it, and the profile route is now priced well enough that a small
  paired comparison is affordable if the owner ever wants the sensitivity gap measured rather
  than asserted.

### D-187 — A2.5's three problem categories are ICTV-anchored taxon predicates, fixed before any survival was counted
- **Date:** 2026-10-19
- **Task:** A2.5
- **Context:** `DESIGN.md` §A2's last detection bullet names "giant viruses and NCLDV, segmented
  genomes, satellite viruses" and nothing in the repository defines any of the three. A2.5's
  first step is to "enumerate the problem categories from §A2 into an explicit checklist", and
  `AGENTS.md` requires the specification fixed before results are inspected. Three categories
  named in prose are exactly the under-specification §A0 turns into a result, so they are
  resolved here against an external authority rather than by this project's judgement of what
  counts as a giant virus.
  The authority is the **pinned ICTV VMR, MSL37.3** (`VMR_20-190822_MSL37.3.xlsx`, sha256
  `66791e9b…bf32`, 1,563,522 bytes, verified against `amazebio.ictv`'s pin on retrieval). It is
  already the benchmark ground truth for A4.2 and it is the taxonomy in force when IMG/VR v4 was
  built, so using it here adds no pin and introduces no taxonomic revision that A9.1 measures
  separately.
  **Retrieval note, because it will recur:** `ictv.global` returns **HTTP 403** to `urllib`'s
  default user-agent and **HTTP 200** to a browser one. The file is free and public; this is a
  user-agent block, not a paywall, and it is recorded so the next task does not escalate it as
  one.
- **Decision:** Three predicates over a record's taxonomic lineage, disjoint on this release
  (the NCLDV and segmented sets do not intersect), each naming its rank so a lineage truncated
  above that rank is **unlabelled for the category rather than negative** for it:

  **1. Giant viruses and NCLDV** — lineage phylum is `Nucleocytoviricota`, which at MSL37.3 is
  **7 families** over 149 exemplar species: Ascoviridae, Asfarviridae, Iridoviridae,
  Marseilleviridae, Mimiviridae, Phycodnaviridae, Poxviridae. Matched at **phylum**, so a record
  labelled only to a higher rank cannot answer the category either way.
  **Plus a second, label-independent handle specific to this corpus.** IMG/VR names its
  giant-virus metagenome-assembled genomes in the accession itself — `IMGVR_UViG_GVMAG-M-…` —
  and A7.2 counted 2,055 of them in the input release while recording them only as an
  accession-shape anomaly. `GVMAG` membership is therefore tested as its own signal, and it does
  not depend on the lineage column being populated.

  **2. Segmented genomes** — the family of a VMR exemplar species whose accession cell carries
  **more than one accession with at least one segment label**. **48 families** over 1,058
  exemplar species. Matched at **family**.
  **The label is the discriminator and it is load-bearing.** Multi-accession alone is wrong:
  Adenoviridae (`Y09598`, `AC_000004`), Poxviridae (four partial records) and Phycodnaviridae
  (`M96366`, `X06618`) all list several accessions for a **monopartite** genome and would enter a
  naive set, while Cystoviridae (`L`/`M`/`S`), Orthomyxoviridae (`RNA1`…`RNA8`) and Geminiviridae
  (`DNA-A`/`DNA-B`) carry labels and are genuinely segmented. Requiring one label admits 48
  families and excludes those three. `amazebio.ictv`'s own docstring warns that the VMR labels
  segments inconsistently, so the rule is "**at least one** labelled exemplar in the family",
  which is robust to a family whose other rows are unlabelled — 22 families have unlabelled
  multi-accession rows as well and are kept or dropped on their labelled ones.
  One labelled multi-segment species carries **no family** and so contributes to no family set;
  it is counted here rather than dropped silently.

  **3. Satellite viruses** — two sets, reported separately and never summed, because §A2 says
  satellite *viruses* and ICTV's satellites are mostly not viruses:
  *Satellite viruses* (encode their own capsid): genera `Albetovirus`, `Aumaivirus`,
  `Papanivirus`, `Virtovirus` — family-unassigned within Riboviria — plus family
  `Sarthroviridae`. **7 exemplar species.** Matched at **genus**, except Sarthroviridae at family.
  *Satellite nucleic acids* (no capsid, helper-dependent): families `Alphasatellitidae` and
  `Tolecusatellitidae`. **216 exemplar species.** Matched at **family**. These carry no realm,
  kingdom, phylum, class or order in the VMR at all, which is why a realm-level sweep cannot see
  them and why they are named explicitly.
  **`Ribozyviria` / `Kolmioviridae` (15 species) is deliberately excluded**, with the boundary
  stated rather than left to a reader: deltavirus-like agents are satellite-*like* and
  helper-dependent, but ICTV ratifies them as a realm in their own right and does not classify
  them as satellites. Excluding them keeps the category ICTV's rather than ours; the count is
  recorded so a later task can include them without re-deriving anything.
- **Disclosure, because it bears on what "fixed before results were inspected" means here.**
  The category definitions were fixed **after** two census artefacts had already been opened and
  **before** any per-category count was taken. What had been seen: A7.1's `stage2` census — that
  Evo 1's surviving component is 2,628,513 Duplodnaviria of 2,653,047 records, that its only
  Riboviria are 6,105 Leviviricetes, and that no `Nucleocytoviricota` appears among its 181
  lineage tags; and, in A7.2's input scan, that `f__Alphasatellitidae` and `g__Dinodnavirus`
  occur in IMG/VR's input classifications and in its `released_by_classification` block. So it
  was known that satellites survive somewhere in Evo 2 and that Evo 1's component is
  overwhelmingly phage before these predicates were written. What the predicates cannot have
  been tuned to is any category's count, which is computed only after this entry is pushed.
  The honest summary is that the **sets are an external authority's and the ranks follow from
  them**, not that this was a blind pre-registration. Stating which it was is cheaper than
  implying the stronger one.
- **Rejected:** *Defining giant viruses by genome size* (the common informal rule, >300 kb or
  >500 kb). It would make the category a property of the contig rather than of the taxon, so a
  fragmentary giant-virus contig would fall out of it while a long phage genome fell in, and the
  threshold would be this project's invention at exactly the point §A2 is asking about taxa.
  *Treating `>1 accession` as segmented* — wrong on Adenoviridae, Poxviridae and Phycodnaviridae,
  as above; the error is in the admitting direction and would have inflated every segmented count.
  *Folding satellite nucleic acids in with satellite viruses* — they differ in whether a capsid
  is encoded, which is the whole reason a filter might reach one and not the other, and §A2 names
  only the viruses. They are both measured and kept apart.
  *Pfam or RVDB family sets as the category definition.* The registries' families are protein
  clusterings with no rank, so `Nucleocytoviricota` is not expressible in them; and a registry
  universe is a denominator whose membership rule is a finding about the registry (D-157's rule,
  carried from D-075). The categories are taxon sets; where the registries enter is the
  sequence-side arm, and that is a separate entry.
- **Consequence:** A2.5 has an explicit checklist, so "every §A2 category has a recorded result
  per manifest" is now a criterion that can be met rather than interpreted. Every category match
  is at a named rank, which makes **unlabelled** a third outcome beside present and absent — and
  that is the result that matters most for Evo 1, where 2,543,536 of 2,653,047 surviving records
  carry no label below class. A zero from this arm is a zero **about labels**, and the artefact
  must say so in the same field that reports it. The label-independent arm is the owner's
  standing decision of 2026-10-19: ship the label census first, then measure a small slice of the
  marker pass before committing to any of it.

### D-188 — Nine finished tasks had no surviving result artefact, and `repro.run` now refuses a local-only result
- **Date:** 2026-10-19
- **Task:** X (cross-cutting; found from A2.5, affects every task that produces an artefact)
- **Context:** A2.5 went looking for A1.4's manifests, which `metrics/manifests.md` says live in
  `artifacts/a1-4/`, and found nothing: `artifacts/` is git-ignored, the session container that
  produced them had been reclaimed, and nothing had been uploaded. Auditing the other finished
  tasks found the same thing in eight more.
  **The audit, over all 24 finished tasks (21 `done`, 3 `review`).** The mechanism is entirely
  mechanical: 24 tools in `tools/` upload to the object store and 19 write only to `artifacts/`.
  Every task served by the first group is intact; every task served only by the second lost its
  tables.
  *Results safe because the deliverable is committed:* A0.1 (`policies/sources.json`,
  `policies/captures/`), A0.2, A0.3 (`policies/specs/`), A1.1 (a verdict recorded in this log),
  A3.1 (`metrics/survival.md`, `src/amazebio/survival.py`), X1.1, X1.4.
  *Results safe in object storage:* A1.3 (UniRef composition), A1.6 (29 objects, 1.63 GB),
  A1.8 (13 objects, 820 MB), A2.2 (25 objects), A2.4 (32 objects), A7.1 (2 objects — the
  `stage2` census), A7.2 (6 objects, 34 MB).
  *Results absent, regeneration needed:* **A2.1** (profile detection tables, both registries,
  the ten-fold deepened pass — about 20 hours of compute), **A4.2** (the taxonomy-tool
  misassignment benchmark — a geNomad run, hours), A1.4 (the seven manifests, about an hour),
  A4.1, A4.3, A1.2, A1.5, A1.7, B1.1, B2.1 (all cheap; B1.1 is re-derived by a CI step).
  **What was not lost, stated so the scale is not overstated either.** All 1.02 TB of staged
  corpora are intact and that bucket has no `s3:DeleteObject`, which is why. No code, decision,
  task record, policy spec or evidence capture was lost. And no *finding* was lost as a recorded
  number: A2.1's family counts and intervals, A4.2's error rates by direction and the rest are
  written into their task files and this log.
  **That last point is the defect, not the consolation.** `AGENTS.md` makes "artefacts before
  prose" a non-negotiable — every number in a write-up traces to a machine-readable artefact
  produced by a pipeline — so a figure whose only surviving form is prose is a figure the Phase A
  write-up cannot cite. D-173 had already recorded one instance of this for D-161's
  cross-registry numbers. This entry is the general case: it was not a lapse in one task, it was
  the default behaviour of three quarters of the tools.
- **Decision:** **`amazebio.repro.run` refuses to complete a run that recorded a local output
  and named no durable destination.** The guard goes there because `AGENTS.md` already requires
  every pipeline to wrap its work in `repro.run`, so it is the one chokepoint that cannot be
  bypassed by a new tool written next month — which is the actual requirement, not fixing the
  nine.
  `durable="s3://bucket/prefix"` uploads every local output on a clean exit, records each as an
  object URI in `run.json`, and uploads `run.json` itself — a durable copy with no provenance
  beside it is not citable, which is the whole point. `durable_exempt="<reason>"` is the other
  way out, and it is a **string rather than a flag** so the reason lands in the manifest and is
  greppable across the tree. `tests/test_repro.py` holds the inventory of exempt call sites and
  asserts it matches what is on disk, so the set can shrink but cannot silently grow.
  Three properties the guard needs and has: it fires only on a **clean** exit, so a failing run
  reports its own exception rather than this one; it ignores a run whose outputs went straight to
  object storage, which is already durable; and it ignores a run with no outputs, so a probe or a
  dry run is not made harder.
  **The cheap seven are regenerated and stored durably** under this entry. A2.1 and A4.2 are not:
  they cost real compute, and the remaining local-only tools still need converting, so both go to
  a task of their own rather than being absorbed into A2.5.
- **Rejected:** *Committing `artifacts/` to git.* `artifacts/README.md` is right that a result
  which cannot be regenerated is a pipeline defect rather than a reason to commit the file, and
  the tables run to hundreds of megabytes. Durability and version control are different problems.
  *A warning instead of a refusal.* The nine tasks are what a convention achieves. The project
  owner's instruction was that this cannot happen again, and a warning in a log nobody re-reads
  is not that.
  *A CI check that greps the tools.* It would catch today's 19 and miss the first tool written
  after it, because nothing would make a new author aware of it. The guard is in the code path
  the result actually travels, so the failure arrives at the moment of producing a result.
  *Making `durable` a required positional argument.* It would break every call site at once
  including ones mid-flight in parallel sessions, and it offers no place to record *why* a run
  legitimately needs no copy.
  *Uploading on every `output_file` call rather than at exit.* A run that fails midway would
  leave a partial result in permanent storage, and the corpus bucket has no delete.
- **Consequence:** Any new tool that writes a result and forgets to persist it now fails on its
  first real run, with the reason and both remedies in the message. The nine tasks' status is
  recorded above rather than quietly repaired, because a `done` task whose artefact needs
  regenerating is a thing a reader of the board should be able to see. **A2.1 and A4.2 are the
  two that cost meaningful compute to restore, and neither blocks A2.5.** Whoever picks up A3.2
  or A6.1 needs A2.1's tables first, and that is now a named task rather than a discovery.

### D-189 — A test run overwrote four A1.6 objects in the no-delete bucket; two are unrecoverable and both are small
- **Date:** 2026-10-19
- **Task:** X (cross-cutting; caused while implementing D-188, damage is A1.6's)
- **Context:** D-188 gave every tool a durable destination. Several tests drive a tool's `main()`
  end-to-end against a real client and no mock — deliberately, because the on-instance path is the
  one thing a `DryRun` cannot check (`AGENTS.md`). So the full test suite, run once at 15:18 UTC
  to verify the D-188 change, uploaded its **synthetic fixtures** to `corpora/results/a1-6/`.
  The corpus bucket has no `s3:DeleteObject` and versioning is disabled, so the writes are
  permanent and the prior contents are gone. `AGENTS.md` says in as many words that a bug which
  writes junk there writes it forever, and A1.6's own task file and `esm3_calibrate.py`'s module
  docstring each warn about a collision under this exact prefix. The warnings were read and the
  consequence was not.
  **Nine keys were written; four collided.** The five that were new are flat names
  (`exclusivity-rows-2023_02-uniref90.tsv.gz`, `exclusivity-counts-…`, `run-exclusivity-uniref90.json`,
  `exposure-q100.json`, `run-exposure-q100.json`) whose real equivalents are nested under
  `exclusivity/2023_02/…` and `exposure/2023_02/…` with content hashes. The four that collided are
  recorded below.
- **Decision:** The accounting, because the apparent size and the real loss differ by two orders
  of magnitude and the first report of this overstated it.

  **`viral-seeds.faa`, 1,249,029,570 bytes — not lost.** The destroyed object was a *duplicate*.
  The canonical copy is `corpora/samples/a1-6/uniref100/2023_02/rate40/viral-seeds.faa`, intact,
  and it is the key that sample's own manifest names as `seed_fasta` with
  sha256 `8a23f5ea10ac9413671bd8753c4c33778a9692f5c64090c18cc22b0a8f845632` — the same digest the
  two surviving exposure manifests cite as their input. So 95% of the bytes that disappeared from
  the results prefix were never at risk, and **no in-region pass is needed to restore them**.

  **`band.json`, about 65.6 MB — superseded, and held elsewhere.** It was the five-cell state of
  the band 1 run, published before the resumed sixth cell landed.
  `band-viral-arm-5cells-backup-20261018.json` is intact at 65,743,883 bytes and carries the same
  per-cell structure (identity bands, coverage mode, per-family hit counts). `band-complete.json`,
  which A1.6 names as authoritative, was never touched.

  **`run-calibration.json` — lost, and its critical field survives.** The provenance manifest for
  the caps run. The code commit is recoverable as `8200f2f8a107c252d3350d54399a7f0d31078aa4`, from
  `progress-caps.json` and from the sample manifest, and it is a real commit in this repository
  dated 2026-10-17. What is gone is the consolidated record: the pinned input digests, the tool
  versions actually invoked, and the declared parameters as one attested object.

  **`cap-measurement.json` — the one real loss.** No copy exists anywhere in the bucket. Per cell
  it held `bands_by_reading`, `records_by_reading` across all three coverage readings,
  `search_core_seconds`, `hit_rows`, the `saturation` distributions and `reading1_agreement`.
  **Its headline figures survive verbatim** in A1.6's task file — the six cells as three caps
  (slack/50%/20%) by two coverage modes, with wall seconds and records lost — together with all
  four findings, including the 6x-over-D-104 result that moved the broad arm's price from $26 to
  $300-430 and then to D-128's 0.3125% for about $50. **Nothing downstream consumed it**: no
  surviving manifest references it.

  **The fix.** No upload is attempted from a test process unless the test injected the client
  itself (`repro.in_test_run`, and `AMAZEBIO_NO_UPLOAD=1` for a manual run), and the manifest
  records `upload_skipped` so a `run.json` produced under test cannot be read as one whose outputs
  persisted. The durable destination is also validated at `run()` entry now rather than at exit,
  so a malformed one fails before the compute.
- **Rejected:** **Re-running `esm3_calibrate.py` to repair the damaged keys.** Proposed twice and
  wrong both times, which is the part of this worth recording. `--curve` writes `calibration.json`,
  which *survived* and holds published figures, so re-running it would destroy a survivor.
  `--caps` writes the published `cap-measurement.json`, so it substitutes a fresh measurement under
  a cited key — and the published run "ended before the second target size", so a new one would not
  even be structurally comparable. `--band` cannot restore `band.json` at all, because A1.6's own
  rule is to pass `--artefact-name` something new. **No mode can restore a damaged key; each can
  only write new numbers under an old name.** That is worse than an honest gap, and it is the
  silent substitution this project's own notes warn about.
  Also rejected: a tombstone object over the test junk. It would replace a hazard with a signpost,
  but it is another irreversible write to a bucket already carrying two of them, and the junk is
  documented here instead.
- **Consequence:** `corpora/results/a1-6/` carries four objects whose contents are test fixtures,
  permanently. A reader of that prefix cannot tell by inspection; this entry and A1.6's task file
  are the only things that say so, which is why both say it. **A1.6 is in `review` and its caps
  measurement no longer has a machine-readable artefact** — under "artefacts before prose" that is
  a real gap in its deliverable, and whoever closes that review decides whether a re-measurement
  under a new key is worth two hours. X1.6 holds that re-run alongside A2.1's and A4.2's.
  The wider lesson is narrow and specific: **a test that exercises a real code path needs its
  side effects injected, and adding a side effect to a tool adds it to every test that drives the
  tool.** The durability guard was sound; the blast radius of switching it on was not thought
  through.

### D-190 — A2.5's marker arm: the segmented-family set is derived from three pinned authorities, and the satellite arm cannot be run this way
- **Date:** 2026-10-19
- **Task:** A2.5
- **Context:** The label-side census (D-187) leaves two of A2.5's four categories resting on
  2.6% of Evo 1's surviving records — only that share carries a family-level label — so "no
  segmented genomes" and "no satellite nucleic acids" there are statements about labels, not
  about content. The project owner asked for the label-free arm to be **priced before being
  committed to**, which is the pattern D-183 and D-186 set for A2.3.
  **D-187 overstated one thing and this entry corrects it.** D-187 says segmented-genome
  membership "has no sequence marker at all, so no marker pass can strengthen that category's
  zero". The *property* has no marker — a single contig cannot show that a genome is split — but
  the **48 families** do: Orthomyxoviridae, Bunyavirales' families, the reovirus families,
  Geminiviridae, Cystoviridae and the rest all have ordinary marker proteins. So the category is
  reachable by the same profile search as any other, and D-187's sentence should be read as
  applying to the property only.
  **The cost was measured, and the first figure given to the owner was wrong by about twenty
  times.** `tools/marker_throughput.py` (artefact `corpora/results/a2-5/marker-throughput.json`)
  timed a 1,500-record prefix of Evo 1's stage 2: gene calling **1.608 core-seconds per Mbp**, so
  **16.2 core-hours** over the component's 36,236,025,613 bases, charged once whatever the marker
  set. Search was timed at 50 and 200 profiles. Two approximations are stated in the tool and
  stand here: it reads a **prefix, not a sample** (D-046 — valid for throughput, invalid for any
  count), and it times **synthetic single-sequence profiles**, whose per-profile rate ran 26x,
  then 10.6x, then 5.56x above D-098's published rate over curated models as the profile count
  rose — the fixed-overhead amortisation D-186 was corrected for. **At the scale this arm
  actually runs, D-098's rate is the applicable one** and the synthetic figure is the
  conservative bound.
  An estimate of "about a dollar" was given on the assumption of a handful of hand-picked marker
  genes. A *derived* set is not that: see below.
- **Decision:** **Membership is derived, never recalled.** Three pinned authorities and one rule:
  1. the **ICTV VMR MSL37.3** gives the 48 segmented families (D-187's labelled-segment rule);
  2. the **NCBI taxonomy** `taxdmp_2023-04-01.zip` (`amazebio.seeds.TAXDUMP_2023_04`, sha256
     `6afaee95…71d07`, verified on retrieval) resolves each family name to a taxid and expands it
     to its descendants — **48 of 48 resolved, no misses**, giving 145,376 taxids;
  3. **RVDB-prot 32.0**'s annotation database (md5 `4179c579…ace7`, verified) gives each of its
     13,679 families an `LCAtaxid`, and a family is selected when that taxid falls inside the
     expanded set.
  **1,285 families** are selected. The set is an artefact, not a list in this entry, for the
  reason D-075 gives for Pfam's universe: a denominator a reviewer cannot check is not a
  denominator.
  **Threshold: RVDB's published rule, unchanged.** E ≤ `PINNED_E_VALUE` (1e-5) against
  `PINNED_Z` = 1,000,000 (D-076). RVDB-prot ships no curated per-model cutoffs, and pinning `Z`
  is what makes the E-value a fixed per-model bit score — so the same hit means the same thing at
  every depth, which is the property this arm needs since its depth is not yet fixed.
  **Depth is deliberately left to a follow-up entry**, exactly as D-183 left A2.3's: it is fixed
  from a measured in-container throughput, declared before any hit is inspected. What is fixed
  *now* is the family set and the threshold, which are the things that could otherwise be tuned
  to a result.
  **Scope: the segmented arm only.** The owner's call, on these grounds:
  - *Segmented* is the weak zero and the one worth buying: ~106 core-hours, about **$5** at
    D-098's rate (about $30 at the conservative one).
  - *NCLDV* is **not run.** Its label-side zero is already *established* rather than merely
    unobserved — 2,652,952 records refuted at phylum against 95 unlabelled, 99.996% of the
    component — so a 3,690-family pass at about $15 would confirm what is already solid. The
    cost is recorded here so a later task can buy it without re-measuring.
  **The satellite arm cannot be run on this selection, and that is a method finding rather than
  a scope cut.** Both satellite categories select **zero** RVDB families. That is not evidence of
  anything: RVDB labels a family with the **lowest common ancestor** of its sequences, so a
  family holding satellite sequences beside their helper viruses carries an LCA *above* the
  satellite taxon and drops out. A zero from this rule would be zero **by construction** — the
  manufactured null `AGENTS.md` forbids designing for. The satellite question therefore needs a
  different instrument and is not attempted; it stays an open limitation of A2.5.
- **Rejected:** *Hand-picking marker accessions* — the NCLDV core gene set, alphasatellite Rep,
  and so on. It would have been the actual dollar, and it is not defensible: the accessions would
  come from memory rather than from a pinned source, and §A2's whole concern is a selection
  nobody can check. Pfam cannot supply the selection either: its families carry no ICTV taxon
  annotation, and D-083 already records that selecting Pfam families *by taxon* is precisely that
  registry's blind spot.
  *Running the satellite arm anyway and reporting its zero* with a caveat. A zero that the
  selection rule guarantees is worse than no measurement, because it reads as a result.
  *Using the synthetic per-profile rate for the budget.* It is the conservative bound and is
  reported, but D-098's measurement over real models at 13,679 profiles is the applicable one at
  this scale, and quoting the higher figure would have made an affordable pass look unaffordable.
- **Consequence:** A2.5 gains a label-independent arm for the one category where its census is
  weak, at a cost measured rather than guessed, with membership a reviewer can check family by
  family. Two things are now on the record that were not: **D-187's "no sequence marker" sentence
  applies to the property and not to the families**, and **LCA-based selection cannot answer a
  satellite question** — which bears on any later task that reaches for RVDB to find satellites,
  A2.1's registries included.

### D-191 — A2.5's segmented arm runs as three nested bands, declared before any hit was inspected
- **Date:** 2026-10-19
- **Task:** A2.5
- **Context:** D-190 fixed the family set (1,285 RVDB-prot families, derived) and the threshold
  (E ≤ 1e-5 at a pinned `Z`, RVDB's published rule) and deliberately left the **depth** to this
  entry, as D-183 left A2.3's — because depth is the one parameter that should follow a measured
  rate rather than a guess, and because the project owner asked that the pass be run "in bits so
  if the money goes up we still have our results".
  **The measured rate, on real models.** A 120-record probe (`--limit 120`, declared below) put
  the search at **109 core-seconds per million residues for 1,285 models**, i.e. 0.085
  core-seconds per profile per Maa. That sits between the two bounds D-190 recorded: 3x D-098's
  0.0282 over 13,679 curated models, and about half the 0.157 the synthetic profiles of
  `marker_throughput.py` suggested. Gene calling measured 1.6 core-seconds per Mbp and is
  single-threaded in the shared code path, which is what actually bounds a band's wall clock.
  Projected over the component's 10,494 Maa of called protein, a census is about **320
  core-hours** of search plus **16** of calling — about $17 at the instance rate A2.4 used, not
  the $5 first quoted from D-098's rate alone. The read is **not** amortised across bands: hash
  selection has to scan the whole 16.9 GB object to find a band's members, so each band pays its
  own read of about $1.50.
- **Decision:** **Three nested bands, in this order**, on the seed D-078 fixed and every A2.1
  band has used (20261015), so this arm's samples are the same samples A2.1 drew and a later
  deepening re-reads nothing:
  1. `[0, 0.02)` — 2% of the surviving component. **Matches A2.1's own deepened depth for this
     component**, so the two arms' figures are drawn over the same records and are comparable
     family by family. About 1.5 wall hours.
  2. `[0.02, 0.10)` — out to 10%, five times deeper than A2.1 ever searched here.
  3. `[0.10, 1.0)` — the remainder, which makes the result a census.
  **Each band is a deliverable on its own.** `estimate_kind` is `lower_bound` for bands 1 and 2
  and `population` only for the full `[0, 1)` span, so a stopped ladder reports what it measured
  rather than what it intended. A family detected in band 1 is detected, full stop; a family
  absent is absent *from the records read*, and the interval says so.
  **Band 3 is conditional and the condition is stated now, before any result could influence
  it:** it is bought only if bands 1 and 2 leave the question open *and* the measured rate still
  puts the census under about $25 all-in. If band 1 or 2 finds segmented families, the question
  is answered in the direction that matters — material survives — and a census buys precision
  on a number rather than the answer. If the rate comes in worse than that, the cost becomes the
  finding, as it did for A2.2 under D-180.
- **Disclosure, because "before results were inspected" has to mean something.** A 120-record
  probe was run to smoke-test the tool end to end before this entry was written, and it returned
  **zero hits**. That is 0.005% of the component, it was run with `--limit` as an explicit probe
  rather than as a band, and it is recorded here rather than left out: a null over 120 records of
  a phage-dominated corpus carries no information about the categories, but the honest statement
  is that the ladder was declared *after* that probe and not in total ignorance. No band figure
  and no family identity was seen before this entry.
- **Rejected:** *A census in one pass.* 320 core-hours is 40 wall hours at eight threads and the
  gene-calling arm is single-threaded, so one run cannot finish inside this environment's window
  — the same constraint D-099's bands were invented for. Bands are not a compromise here, they
  are the only shape that fits.
  *Fewer, wider bands* to save the per-band read. Cheaper in total, but it banks nothing until
  late, which is the opposite of what was asked for. Three bands is the compromise: one read's
  worth of overhead buys a quotable result at 2%.
  *Starting deeper than 2%.* A2.1's depth is the one that makes the two arms comparable, and a
  first band that cannot be set beside the label-side census is worth less than one that can.
- **Consequence:** A2.5's weak zero gets a label-independent measurement at a depth matching
  A2.1's, and the ladder above it is costed. Whatever band the ladder stops at, the artefact
  states its own depth and interval, so no reader has to know how far it got to read it
  correctly.

### D-192 — The three lost measurements re-ran and every published figure reproduced; two defects in the tools that produce them did not
- **Date:** 2026-10-19
- **Task:** X1.6
- **Context:** D-188 and D-189 left three measurements with no machine-readable artefact: A2.1's
  profile detection tables, A4.2's misassignment benchmark, and A1.6's caps measurement. Their
  figures survived only as prose in the task files, which under `AGENTS.md`'s "artefacts before
  prose" is a gap in three deliverables rather than a cosmetic one. This entry records what the
  re-runs found, because it is the first occasion on which any of these numbers could be checked
  against the committed code at all.
  **Every figure reproduced, and most of them exactly.** Nothing was adjusted to match; the
  comparison is in X1.6's own file in full.
  *A2.1, at the pre-registered shallow depth.* Pfam 470 and RVDB 572 on Evo 1, 492 and 1,456 on
  Evo 2 — all four identical to the published first pass, across all three readings, with
  `esm3-proxy` correctly `not_searched`. The registries re-staged to their pinned digests and
  both denominators reproduced: Pfam viral 1,719 of 30,134, RVDB-prot 13,679 counted against
  13,679 stated. 32 objects, 40 MB, with run manifests.
  *A4.2.* The evaluation set rebuilt from the pinned VMR to exactly 3,149 sequences, 1,507 in
  scope across 44 families, 1,642 controls across 189. Escape 546/1,507 = 36.23% (33.80-38.72%)
  and spurious removal 50/1,642 = 3.05% (2.27-4.00%), identical to the digit including intervals,
  with the cause split unchanged at 344 unclassified, 119 shallower than the rule, 52 misassigned
  order, 28 absent at the rule's ranks, 3 misassigned family. The dependency pass reproduced
  15,677,623 records, 181,530 denylist hits and 38.5573% geNomad-assigned, so the propagation
  recomputed to 109,760 in scope and 39,767 (35,736-44,218) escaping.
  *A1.6's caps measurement, under the new key `cap-measurement-rerun-20261019.json`.* All six
  cells, against a query and target identical to the published run's (31,381 seeds, 417 M
  residues). Record-loss fractions agree to two decimals — 0.88/2.28% relaxed and 3.31/9.72%
  filtered, against the published 0.9/2.3% and 3.3/9.7% — and wall clocks within 0.5-3.5%. The
  hit-count figures are identical: max 5,078 hits/seed relaxed and 1,444 filtered against a
  100,000 cap, and the reading-1 agreement check at 32,644 post-filtered against 32,374 from the
  aligner, 270 found only by the post-filter and none only by the aligner. Relaxed coverage costs
  1.476x filtered, against the 1.47x published. So all four of A1.6's findings stand, and this
  run also wrote the `cap_summary` the published one ended too early to produce.
- **Decision:** Two defects found while using the tools are fixed here rather than noted, because
  both are in the path a re-measurement takes and one of them is the hazard X1.6 was written to
  avoid.
  **`detect_profiles.py --plan` was broken on `main`.** It passed one argument to a two-argument
  `searched_sources` and indexed the result as a mapping, so the flag raised `TypeError`. The
  search paths were never affected, which is why nothing caught it: a reporting path runs only
  when somebody asks what a run *would* read, which is exactly the cheap pre-flight check before
  a multi-hour search. The branch body moves into a tested `plan_lines`.
  **`esm3_calibrate.py --artefact-name` moved the result and not its manifest.** The flag exists
  so a re-measurement does not write a key whose figures are cited, and the caps re-run duly
  wrote its measurement to a new name — then wrote its provenance to `run-calibration.json`, the
  manifest key of the run it was replacing, in a bucket with no `DeleteObject`. Nothing citable
  was lost, because D-189 records that object as already destroyed by the 15:18 test-fixture
  writes, but the next use of the flag would have destroyed a live manifest. The manifest name
  now follows the artefact name.
  **Two corrections to D-189's accounting, both narrowing it.** `corpora/results/a1-6/viral-seeds.faa`
  no longer holds test fixtures: the caps re-run re-published it at 1,249,029,570 bytes, the same
  length as the canonical copy under `corpora/samples/`, derived from a staged sample the tool
  verified against its manifest digests on load ("verified 9 objects"). It was not re-derived by
  a corpus pass, so A1.6's "do not rebuild it" was not violated, but the upload was a write this
  session did not predict from reading the tool and should have. And `run-calibration.json` now
  holds the re-run's provenance rather than test junk — honest content under a name that does not
  say which run it describes, which is what the fix above prevents repeating. Of D-189's four
  damaged keys, two now hold genuine content and `band.json` and `cap-measurement.json` still
  hold fixtures.
- **Rejected:** *Deepening A2.1 to D-099's ten-fold depth in the same sitting.* The shallow pass
  is a superset relationship and a backed artefact in two hours; the deepening is about eighteen
  more and a separate decision, which is how X1.6 framed it and how the project owner chose it.
  *Re-measuring A1.6's caps at two target sizes.* `--cap-shard-points 1` reproduces exactly the
  six cells the published run completed, and the published run "ended before the second target
  size" so there was never a linearity check to compare against. Paying for a second size would
  have measured something new under cover of restoring something old.
  *Writing the caps result to `cap-measurement.json`.* A1.6 and D-189 both rejected this twice
  already; the new key is the whole point.
  *Patching the caps heartbeat.* In caps mode `_progress` is written once before a reading's
  slack cell and the interval heartbeat covers only the corpus-pass reader, so during a
  35-minute cell the heartbeat does not move — `written_at` stood at 18:46 while the run was
  plainly alive at 19:43. `AGENTS.md` cites this tool as the worked example for writing "a
  heartbeat to object storage on an interval", and for this mode that is not what it does. It
  cost nothing here because the artefact itself grows as each cell publishes, which is the other
  half of the same instruction and does work. Recorded rather than fixed, so it is a named gap
  for whoever needs a long caps cell to be observable rather than a change made in passing to a
  tool this task was only using.
- **Consequence:** A2.1, A4.2 and A1.6's caps measurement each have an artefact in object storage
  with a run manifest, so the Phase A write-up can cite them. X1.2 and X1.3 are unblocked. The
  wider result is the reassuring one: nine tasks lost their tables and the three expensive ones
  came back identical, so the loss was a durability failure and not a reproducibility failure.
  A1.6's caps figures now trace to an artefact again, which is the gap its review was left
  holding — under a new key, with the published measurement's loss stated beside it.

### D-193 — Segmented virus families do survive in Evo 1's released viral component, and taxonomy could not have found them
- **Date:** 2026-10-20
- **Task:** A2.5
- **Context:** A2.5's label-side census (D-187) reported **zero** segmented genomes in Evo 1's
  surviving component — and reported, in the same artefact, that only **2.6%** of those records
  carry a label at the family rank the category is keyed on. A zero over 2.6% of a corpus is a
  statement about labels. D-190 fixed the family set and threshold and D-191 the depth ladder,
  both pushed before anything was searched.
- **Decision:** The result, over the hash span `[0, 0.10)` of Evo 1's surviving stage 2 — four
  nested bands, assembled with the overlap-and-gap check in `tools/detect_segmented.py`:
  **265,062 records, 5,005,711 genes, 1,128 Maa over 3.6 Gbp. 7 of 1,285 families, 57 hits.**
  `estimate_kind: lower_bound`; family-level share 0.54% (0.26–1.12%, Wilson).

  | family | records | ICTV family | genome |
  |---|---|---|---|
  | FAM000422 | **29** | Polydnaviriformidae | segmented dsDNA |
  | FAM007500 | 6 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |
  | FAM022414 | 2 | Nanoviridae (*Babuvirus*) | 6-segment ssDNA |
  | FAM003906 | 1 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |
  | FAM005477 | 1 | Geminiviridae (*Grablovirus*) | bipartite ssDNA |
  | FAM023047 | 1 | Bromoviridae (*Ilarvirus*) | tripartite ssRNA |
  | FAM033562 | 1 | Spinareoviridae (*Orthoreovirus*) | 10-segment dsRNA |

  **Five distinct ICTV segmented families, every one eukaryote-infecting**, in a component whose
  host rule's published purpose is "to remove potential eukaryotic viruses" (D-110).

  **Three independent things make this more than a threshold artefact**, and they are the reason
  this entry states a finding rather than a count:
  1. **FAM000422 appears in all four bands** — 5, 7, 8, 9 records. The bands are disjoint hash
     samples, so an artefact of the cutoff would not distribute evenly across them.
  2. **Three separately-built RVDB families converge on *Orthoreovirus*.** Independent
     clusterings of the same genus hitting the same corpus corroborate each other in a way seven
     unrelated singletons would not.
  3. **The models are not all short.** FAM003906 is 310 residues from 613 sequences; FAM000422 is
     170 from 102. Every hit also cleared 50% model coverage on top of the E-value.

  **What is weak, named rather than averaged in.** FAM033562 (83-residue model, 7 sequences) and
  FAM022414 (66 residues, 8) are short models and are the least safe of the seven; a short model
  is where a spurious hit is most likely even at this coverage. The seven are not seven
  equivalent findings and must not be quoted as such.

  **Route is `unresolved` for all 265,062 records**, from `apply.route_for` over A1.4's manifest,
  and **no table asserts a conformance failure** — §7 reserves that for A7.1. Eight records that
  the reading removes were subtracted before anything was called, per band: 0, 3, 2, 3.

  **The methodological point, which is the part that generalises.** §A2 opens by warning that an
  audit using taxonomy reproduces the filter's blind spots. This is that warning measured: the
  label-side arm and the sequence-side arm ran over the *same* records — band 1's 53,140 matches
  A2.1's published figure exactly — and returned **zero** and **seven**. The difference is not
  depth or threshold; it is that one arm reads a label 2.6% of records carry and the other reads
  the sequence every record carries.
- **Rejected:** *Reporting the seven as a fraction of "viral families".* The denominator is
  D-190's segmented selection and nothing else; D-161's rule applies and the artefact carries the
  restriction in-band.
  *Buying the census.* The owner authorised it at ~$9.60, and it was then declined on the
  measurement rather than the price: 2% took 55 minutes, so the remaining 90% is about 28
  sequential runs inside this environment's two-hour cap — a scheduling cost, not a money one.
  D-191 had also pre-registered that band 3 was conditional on the question still being open, and
  after band 1 it was not. **A census would refine how much, not whether.** The route to it, if
  anyone wants it, is one in-region instance rather than 28 session runs.
  *Calling the satellite arm's zero a result.* It selects zero families by construction (D-190)
  and is not run.
- **Consequence:** **A2.5's segmented zero is withdrawn and replaced.** Its task file carries the
  measured result, and D-187's sentence that "no marker pass can strengthen that category's zero"
  is wrong as written — D-190 corrected it for the property-versus-families distinction and this
  entry settles it with data. The surviving weak zeros in A2.5 are the two satellite categories,
  for a reason that is now a named method limitation rather than an unexamined gap.
  Two incidents on the way, both recorded because the second is mine twice over. **The container
  restarted mid-ladder**: three completed bands were intact in object storage and the in-flight
  band lost 50 minutes of compute and **no results** — the first real test of D-188's guard and of
  banding, and both held. And **a scratch-directory probe of `--assemble` published to the real
  prefix**, because `repro.run` derives `durable` from the task id and cannot see `--out`. The
  file is honest and self-labelling and overwrote nothing, but it is permanent, and the fix is in
  the tool: a run writing anywhere but the canonical directory declares `durable_exempt` and says
  so. That is D-189's lesson arriving by a second route, which is the argument for putting such
  guards in the code path rather than in a person's care.

### D-194 — A3.2's merge rules: the headline is a union over families and a sum over disjoint components, and the disjointness is checked rather than assumed
- **Date:** 2026-10-20
- **Task:** A3.2
- **Context:** A3.2 merges four detectors' tables into one headline. Two of the metrics combine
  differently and getting that wrong produces a number that looks right. M1 asks whether a family
  has at least one surviving homolog, which is a **union** and is safe under any overlap between
  detectors. M2 is the per-family count of surviving records, which is a **sum**, and a sum over
  two detectors that read the same corpus records double-counts every record they share.
  The A2 detectors do partition the corpus — profile search reads the viral and metagenome
  components, provirus detection the bacterial genomes, element detection the eukaryotic genomes
  — and `metrics/detections.md` already requires every table to list each component with
  `searched: false` and a reason where it did not read it. So the partition is stated in the
  artefacts.
- **Decision:** The merge **verifies** the partition from each table's own `sources[]` and
  refuses a group where two detectors both report having searched the same component. Counts are
  then summed across detectors and families are unioned. Three further rules travel with it:
  *Universes are never pooled, and a restriction is part of a universe's identity.* RVDB-prot
  32.0 at 13,679 families and RVDB-prot 32.0 cut to D-190's 1,285 segmented families are two
  universes, keyed apart, for the same reason Pfam and RVDB are (D-022, D-161).
  *A table may attribute routes per family row or as one uniform route for every record it
  searched, and both are checked against the table's own totals.* A row's route counts must sum
  to its hits; a table with no per-row routes must declare exactly one. Two table-level routes
  with no per-row tagging leaves each detection's route undetermined, and the merge refuses it
  rather than picking one — which is what D-042 moved into this task.
  *Where a family carries detections on more than one route, its record count is split across
  routes in proportion to the detections on each.* The split is reported as a per-route figure
  only; the overall M1 and M2, which are the headline, never pass through it.
- **Rejected:** *Assuming the partition because the A2 task files describe it.* A detector
  widened to a second component later would inflate every per-family count in its group with
  nothing in the output saying so, and the check costs one pass over `sources[]`.
  *De-duplicating on record id instead.* A2.4 publishes no record-level file, so a record-id
  merge would silently exclude the provirus detector from M2 — the arm carrying the largest
  single block of detections.
  *Pooling the three policy readings, which return identical counts for Pfam and RVDB.* They are
  identical because the readings remove few records, and that equality is itself A0.4's result.
  Pooling would delete it.

### D-195 — M3 diversity coverage cannot be computed from the A2 artefacts and becomes task A3.4
- **Date:** 2026-10-20
- **Task:** A3.2
- **Context:** `metrics/survival.md` §4 specifies three headline metrics. M1 and M2 are computed
  from the per-family rows the A2 tables publish. M3 asks, for each surviving family, which of
  that family's diversity bins the surviving sequence covers — where the bins are the family's
  reference members clustered at 50% identity over 80% of the shorter sequence. Computing it
  needs each detection **placed** against those bins, and the A2 detection records carry a
  record id, a score, a route and an element kind and no sequence, no alignment and no
  coordinates. There is no depth at which M3 falls out of these artefacts: the measurement was
  not taken.
- **Decision:** A3.2 ships M1 and M2, and M3 becomes **A3.4**, a new task with its own id rather
  than a widening of this one (`AGENTS.md`: a task that turns out to be two tasks is split). The
  A3.2 artefact names M3 in `metrics_not_computed_here` with this reason, so a reader of the
  headline sees the gap in the file rather than in a log. A3.4 is `ready` and blocks A6.1: the
  Phase A write-up either carries M3 or records it as deliberately not run, and that is the
  project owner's call once its cost is measured, not a judgement to make mid-task.
- **Rejected:** *Approximating M3 from the per-family record counts.* A count of surviving
  records is not a count of covered diversity bins — one family's twelve records can be twelve
  near-identical sequences in one bin — and the approximation would read as the metric.
  *Re-running the A2 searches with sequence output inside A3.2.* That is a second corpus pass
  with its own cost and its own pre-registered depth, which is a task.
  *Quietly dropping M3 and reporting two metrics as the headline.* The specification is frozen
  and names three; a headline silently missing one of them is the kind of gap `AGENTS.md`
  requires to be visible as a named commitment rather than forgotten.

### D-196 — The denylist's taxonomy error rate is measured over 16.93% of the removals it actually makes, and the other 83% cannot be measured from this corpus
- **Date:** 2026-10-20
- **Task:** A4.4
- **Context:** D-091 committed Phase A to not publishing a leakage figure that covers a minority
  of the filter's hazard-relevant removals. A4.2 measured geNomad and recorded that it assigns
  **38.56%** of the 181,530 records Evo 1's denylist removes. A4.4 owns the rest. A full pass
  over the pinned IMG/VR v4.1 release reproduced A4.2's two headline counts exactly — 181,530
  denylist hits, 116,327 after the confidence gate — which is a free cross-check that the two
  tools read the release the same way.
  **The 38.56% is the wrong figure to hold D-091 against.** The confidence gate runs *before*
  the denylist (A4.1, D-081), so the removals the filter actually makes are the 116,327, and
  over those geNomad's share is **16.93%**, not 38.56%. The share does not fall because geNomad
  is less used; it falls because 50,302 of geNomad's hits do not survive the gate while every
  one of RVMT's 89,872 does. RVMT therefore carries **77.26%** of the operative removals.
- **Decision:** A4.4 reports that **no non-circular benchmark exists** for the catalogues
  carrying the other 83.07%, and reports that as a bound on *this audit* rather than as a
  measurement of the filter. The test applied is concrete and countable: inside this corpus the
  only ground truth independent of the label under test is `MIUViG quality: Reference`, which
  the release note gives to RefSeq-derived sequences. Counted over the denylist's own hits:
  **RVMT 89,872 hits, 0 with independent ground truth**; vOTU consensus 10,246 and 0; vOTU with
  RefSeq genome 25 and 0; geNomad 157 of 69,993; NR 13 of 7,753. RefSeq's 3,641 are all
  `Reference` and all **circular** — the release note makes its label and its ground truth the
  same fact, so scoring it would measure a lookup against itself. The two methods with a
  non-zero count are reported with the interval and not as a rate: 157 records cannot carry an
  error estimate that D-091 would accept.
  **What stands in place of a number, from RVMT's own methods (S-RVMT-CELL, digest verified
  against the register).** RVMT is not a classifier. Of its contig set, 2,765 took ICTV labels
  by MEGA-BLAST against VMR MSL36 at identity >=98% and coverage >=95% both ways, and 6,878 more
  from NCBI NR; every other label was *erected* — an approximate-maximum-likelihood RdRp tree,
  taxa propagated from the last common ancestor of labelled leaves, clades outside existing taxa
  dissected at a depth threshold and named as new taxa — and contigs were then affiliated
  through four similarity levels. The authors publish no accuracy and no interval, only that
  they "estimate that the majority contigs affiliated in this manner, would roughly share the
  same taxonomic ranks down to genus level". They also record that the assumption the procedure
  rests on, that existing taxonomy is non-contradictory with respect to the tree, "is violated
  in multiple places", resolved mostly by stripping the conflicting labels.
  **Two further facts the pass settled.** No IMG/VR lineage on a denylist hit carries a name the
  pinned VMR does not ratify (4 RefSeq records aside), so the labels RVMT supplies to the
  denylist are ratified names produced by that tree inference, not RVMT's own novel taxa. And
  **96.2% of RVMT's hits are removals on `order` alone** — 78,617 of the 89,872 on
  `Picornavirales` by itself. So roughly two thirds of everything this filter removes rests on
  one coarse-rank call, inherited from one catalogue, with no published error rate.
- **Rejected:** *Benchmarking RVMT against ICTV anyway.* RVMT's ratified labels were themselves
  produced by matching to ICTV, so scoring them against ICTV measures the coincidence being
  used as ground truth. That is the circularity `AGENTS.md` and §A4 both warn about, and it
  would produce a flattering number with no content.
  *Quoting geNomad's 38.56% as the coverage.* It is the pre-gate share and the filter does not
  act pre-gate. Carrying it into the write-up would overstate the audit's reach by a factor of
  more than two.
  *Scoring geNomad's 157 and NR's 13 Reference-flagged hits as the remaining coverage.* The
  intervals span most of the range; a precise statement about 170 records is not a measurement
  of 181,530.
  *Treating the gap as a Phase A result about the filter.* It is a fact about what can be
  measured from published artefacts, and the write-up must say so in those words. What it does
  license is the generalisable point for §10: a filter that inherits taxonomy from catalogues
  that publish no error rate cannot be audited for taxonomic error by anyone, including its
  authors.

### D-197 — Phase B's limit is the design, not the assay count: the retained arm is seven phage assays and family is confounded with exclusion status by construction
- **Date:** 2026-10-20
- **Task:** B2.2
- **Context:** D-010 narrowed B2.2 to one question asked before any curation: do published
  collections already give sufficient n for §B5's homology regression? "Sufficient" is not a
  total. §B5's result *is* the interaction between homology and model-exclusion-status, with
  random effects for assay and protein family and covariates for Neff, readout type, length
  and variant count. What has to be sufficient is therefore both arms of that contrast at
  every level the plan adjusts for.
  B2.2 placed all 31 of ProteinGym v1.3's viral assays in the pinned NCBI taxonomy of
  2023-04-01 — via UniProt, or, for four entries UniProt has since **deleted** as "not part of
  a reference proteome", via the benchmark's own organism string — and applied the Evo
  denylists.
- **Decision:** B2.2 reports that the published collections do **not** give a usable design,
  and that curating more assays does not fix it. Three findings, each fixed before any score
  was computed:
  **Family is perfectly confounded with exclusion status, by construction.** The denylist *is*
  a family rule, so no family can appear in both arms — and §B5 pre-registers a random effect
  for protein family alongside a fixed exclusion term. Those two cannot both be estimated. No
  amount of curation changes this; it follows from what exclusion means.
  **The retained arm is seven assays and nearly one readout.** 24 excluded against 7 retained,
  and the seven are all bacteriophage: five cDNA-display proteolysis assays on 40–63-residue
  domains from a single study, and two FACS assays on one repressor. The excluded arm is 20
  Growth assays, 2 Binding and 1 proteolysis. Only `cDNA display proteolysis` occurs in both
  arms, at 5 against 1. Readout type is a covariate the plan adjusts for and it is very nearly
  determined by the arm.
  **Exclusion status is not one variable.** Evo's policies remove by taxon, so the register
  settles them. ESM3-open's remove by similarity to a seed set, so no family name settles an
  assay's status there and the register refuses to report one. §B5's single interaction term
  covers two differently-derived quantities and B5.1 must say which it means.
  **The extension search is recorded whatever it found** (`extension_search` in the artefact).
  MaveDB's full-text search over 83 score sets yields Bruynoghevirus LUZ24, Lactococcus virus
  P2 and Xipdecavirus Xp10 — three more families for the retained arm and **not one new readout
  class**, all from the same proteolysis study. ViroGym (arXiv 2603.06740) has 79 assays with 7
  readouts but states them as eukaryotic viruses, which enlarges the arm that is already large;
  its release and licence are unstated and it is registered as a candidate, not a source.
- **Rejected:** *Curating an extension anyway, to raise n.* It would raise the excluded arm,
  which is not the constraint, and spend the schedule on a design that still cannot identify
  its own interaction term.
  *Dropping the family random effect quietly so the model fits.* The confound is the finding
  and must reach B5.1 as one; a model that runs is not a model that identifies anything.
  *Treating the seven phage assays as a sufficient positive control.* §B2 does intend phage as
  the within-study control, which is B2.3's subject, but a control that shares no readout class
  with the arm it is being compared to measures the readout as much as the exclusion.
  *Reporting ESM3-open's assays as retained because no denylist names them.* Its filter was
  never evaluated on them; "not excluded by a rule that was not run" is not a status.
- **Consequence:** B5.1's pre-registration cannot be written against §B5 as drafted. What it
  must settle is named here rather than left for the freeze: what replaces the family random
  effect, whether readout type can be adjusted for at all, and whether the two models' exclusion
  statuses are one term or two. B2.3 and B2.4 proceed on the register as it stands.

### D-198 — A8.1's common corpus is UniRef, and the similarity side is the publisher's own clustering
- **Date:** 2026-10-20
- **Task:** A8.1
- **Context:** §A8 says to run both filters' predicates over the same records. The two
  predicates are different machines: Evo's reads taxon labels, ESM3-open's reads alignment to
  a seed set at a threshold its authors never published (D-015). Any common corpus has to be
  one both can act on, and the similarity side has to be executable without inventing the
  missing threshold.
- **Decision:** The corpus is UniRef100 of the pinned 2023_02 release, read through UniRef90
  and UniRef50. Four consequences, each declared in the artefact rather than left to the
  write-up:
  **The similarity predicate is cluster co-membership, and the tier is the threshold.**
  UniRef90 and UniRef50 are the publisher's own homology groupings at 90% and 50% identity
  over exactly these records, so a record whose cluster holds a seed is within that identity
  of a seed. Running both tiers is §A8's "report across a range, not at one assumed value",
  and the range is the publisher's rather than ours. A1.6's banded curve sweeps our stated
  range; neither is presented as the other, and neither is ESM3's own threshold.
  **Only Evo's taxon rules run.** Four of its six rules read IMG/VR metadata — a confidence
  label, a vOTU, a host count — that a protein record does not carry. They are named in the
  artefact's `rules_not_runnable` rather than silently skipped.
  **A non-viral record is out of scope, not retained.** Evo's filter runs over a virus
  database; the taxon rules say nothing about a bacterial protein, and scoring one as "neither
  filter removed it" would manufacture agreement from a question never asked. The table is
  therefore 3x2, with `out_of_scope_removed` split from `out_of_scope_kept` because the first
  is the collateral the similarity mechanism takes and the second is the corpus it leaves
  alone.
  **`label_only` is empty before the pass, not as a result of it.** Every record the taxon
  rules remove is viral by NCBI taxonomy; every viral-annotated record is a seed under the
  reading in force (D-156); a seed's own cluster contains it. `check_dominance` refuses a
  result where that cell is non-zero, because a stray record there means one of those three
  premises is false and the number means something else.
- **Rejected:** *Re-running the alignment to get ESM3's threshold properly.* A1.6's pass is
  the worked example of what that costs, and it would still need a threshold nobody published.
  *Using A1.6's banded artefacts instead of a new pass.* They carry per-stratum counts with no
  stratum identity, so the corpus records removed by similarity cannot be joined to their
  taxonomy at all — the same shape of gap D-195 found for M3.
  *Treating the three Evo readings separately.* All three carry identical taxon rules and
  differ only in rules this corpus cannot run, so on this corpus they are one predicate. The
  pass verifies that from the specs at run time rather than asserting it here, because a later
  spec edit would otherwise make the artefact quietly wrong about what it covers.
- **Consequence:** The result measures the predicates, not the deployments — the two filters
  were applied to different corpora in their original use — and that sentence travels in the
  artefact, not only in the paper.

### D-199 — Two of Evo's own rule names do not resolve against the pinned taxonomy as written
- **Date:** 2026-10-20
- **Task:** A8.1
- **Context:** Executing the taxon rules against NCBI's 2023-04-01 dump, two of them do not
  land. Both were found by a refusal rather than by reading the spec, which is the argument for
  the refusal.
  **`Reoviridae`**, one of the nineteen families the rule names, is not a scientific name in
  that dump at all. It survives only as a synonym of **`Reovirales`**, which is an *order*.
  **`require_rank: realm`** asks for a rank NCBI does not use. In the pinned dump no node
  anywhere carries rank `realm`, and Riboviria — a realm in the ICTV scheme the rule is written
  against — is a `clade`. Run literally, the specificity rule finds no realm on any record and
  removes the entire viral corpus: 100% of 236,541 viral taxa, which is a unit mismatch
  reported as a filter result.
- **Decision:** The rules are executed as written and the gaps are reported, not patched over.
  `Reoviridae` matches nothing, because the rule names a family and the dump carries no family
  by that name; what a looser reading would have reached is counted separately as
  `loose_only_members` and never folded into a cell. `require_rank: realm` is resolved to
  descent from one of the six ICTV realms by name, because the alternative — removing every
  viral record — measures the rank vocabulary and not the filter; the substitution is recorded
  in the artefact's `name_resolution` beside the first.
- **Rejected:** *Resolving `Reoviridae` through the synonym.* It would silently widen a family
  rule into an order rule, and on this corpus that is 90,530 records at 90% identity.
  *Dropping the specificity rule as not runnable.* It is runnable; it is the rank vocabulary
  that does not match, and dropping the rule would understate what the filter removes.
  *Updating the specs to the taxonomy's current names.* The specs record what the authors
  published; correcting them would erase the finding.
- **Consequence:** This is the decay A9.1 measures, caught a task early and on a different
  axis: not a taxonomy that moved under a static list, but a static list that never matched the
  taxonomy a protein corpus is placed in. A9.1 should read this before choosing its baseline.

### D-200 — A8.1's result: the disagreement is one-sided, and only its collateral moves with the threshold
- **Date:** 2026-10-20
- **Task:** A8.1
- **Context:** D-198 fixed the method before the pass ran. The pass read UniRef 2023_02 at
  both of the publisher's identities — 305 GB of the 90 tier and 231 GB of the 50 tier — and
  cross-tabulated the two predicates over all 404,113,639 records.
- **Decision:** Reported as follows, because the obvious summary of the table would be wrong
  in two directions at once.
  **Agreement is 62.43%, and the number means less than it looks.** Of the 5,405,462 records
  Evo's taxon rules are in a position to judge, both filters remove 3,374,679 and the
  similarity predicate alone removes the other 2,030,783. `neither` is empty and so is
  `label_only`. The similarity predicate removes **every** viral record, because under the
  reading in force every viral-annotated record is itself a seed; the taxon rules remove 62%
  of them. So "62% agreement" is not two filters converging on a definition — it is one
  filter being a strict subset of the other, and the 37.6% gap is entirely viral material no
  rule in the published list names.
  **Neither identity changes any of that.** Both tiers give the same five numbers on the
  viral side, to the record, which follows from the seed set rather than from the data.
  **What the threshold does change is the collateral.** Non-viral records sitting within the
  tier's identity of a seed: **2,173,029 at 90%, 6,955,858 at 50%** — 3.2x for one step of
  the threshold. That is the only quantity in the table the unpublished threshold moves, and
  it is a quantity about the corpus the filter keeps rather than the material it removes.
- **Rejected:** *Leading with the 62% figure.* On its own it reads as two labs roughly
  agreeing. The structure underneath it — strict containment, one-sided gap — is the §A8
  finding and the percentage is a consequence of it.
  *Reporting the collateral as a filter error.* Nothing here says those 2.2M or 7.0M records
  are not worth removing; a cellular homologue of a viral protein may be exactly what a
  similarity filter should take. What the number settles is that the two mechanisms differ in
  kind, not degree: one cannot touch a record the taxonomy calls cellular and the other
  removes millions of them.
  *Pooling the two tiers into one figure.* The viral side is identical and the collateral is
  not, so a pooled number would hide the only thing that moved.
- **Consequence:** §A8's question has an answer: the two filters do not denote the same
  operation. One removes by what a record is called and reaches 62% of the viral corpus; the
  other removes by what a record resembles, reaches all of it, and takes between 2.2 and 7.0
  million non-viral records with it depending on where its unpublished threshold sits. The
  write-up leads with the containment, not the percentage.

### D-201 — A9.1's replay window, cadence and what counts as decay, fixed before any of it is run
- **Date:** 2026-10-20
- **Task:** A9.1
- **Context:** §A9 replays the frozen denylist against successive taxonomy releases. Every
  number it produces depends on choices that would be easy to make after seeing the curve —
  which releases, how far back, and what separates decay from renaming — so they are fixed
  here first, per `AGENTS.md`'s rule on parameters.
- **Decision:**
  **Releases.** NCBI's `taxdump_archive` carries 144 monthly dumps from 2014-08-01 to
  2026-10-01. The replay uses **quarterly dumps from 2020-01-01 to 2026-10-01**, 28 releases.
  Quarterly because monthly costs five times the download for a curve nobody will read at
  monthly resolution; from 2020 because the window has to start well before the denylist's own
  vintage, or a rising curve could not be told apart from the taxonomy simply growing.
  **Baseline.** 2023-04-01, the taxonomy already pinned by this project and roughly the vintage
  of the corpora the filter was applied to. Releases before it are reported as the pre-vintage
  rate, not as decay.
  **Four quantities, per release.** (1) *Reach*: viral taxa the frozen names resolve to.
  (2) *Unreachable names*: names in the list that are not a scientific name at the rank the
  rule declares — `Reoviridae` is already one of these in the baseline itself (D-199), so the
  curve starts at one, not zero. (3) *New diversity not named*: viral taxa absent from the
  baseline, not reachable from it through `merged.dmp`, and outside the frozen names.
  (4) *Nomenclature churn*: taxa present in both, same taxid or reachable through
  `merged.dmp`, whose scientific name or rank changed.
  **(3) and (4) are never added together**, which is the separation §A9 asks for: a rename that
  moves no sequence is not decay, and pooling them would inflate the result by whatever the
  ICTV happened to be renaming that quarter.
  **The static-versus-computed contrast** is the frozen family and order list against the
  specificity rule. The list is an enumeration fixed in 2024 prose; the specificity rule asks a
  question each release answers for itself. Both are measured against the same viral taxa of
  the same release, which is what makes the contrast a measurement rather than an argument.
- **Rejected:** *Starting the window at the denylist's vintage.* With no pre-vintage stretch
  there is no way to show the slope is the filter ageing rather than the taxonomy growing.
  *Monthly resolution.* Five times the download and five times the parse for a curve reported
  by year.
  *Counting the realm-rank mismatch as decay.* `require_rank: realm` asks for a rank NCBI has
  never used, in any release in the window (D-199). It is a vocabulary mismatch present from
  the first day, not something that decayed, and it is reported separately so the curve is not
  made to carry it.
  *Measuring in-scope diversity by host.* §A9's "in scope by the policy's stated intent" means
  eukaryote-infecting, and NCBI carries no host. The replay measures what the names reach
  against what the taxonomy holds; the host-conditioned question stays with the charitable
  reading's own rule and is named as not answered here.

### D-202 — A9.1's result: the list loses about three points of the viral taxonomy a year, and has done so since before it was written
- **Date:** 2026-10-20
- **Task:** A9.1
- **Context:** The replay fixed in D-201 ran over all 28 quarterly dumps, 2020-01-01 to
  2026-10-01, baseline 2023-04-01. Every dump carried a merge table, so no release had to
  guess at renumbering. Artefacts: `artifacts/a9-1/decay.json` and `decay.md`, with each
  dump's SHA-256 recorded in the first.
- **Decision:** Record the following as A9.1's measured result, and report it as a property of
  label-based filters rather than of these two models.

  **Reach.** The 19 family and 12 order names resolve to 75.83% of the viral taxonomy at the
  baseline and 65.17% at 2026-10-01. Over the whole window: 85.56% in 2020-01 to 65.17%.

  **The slope is the same before and after the filter was written** — 3.00 points of the viral
  taxonomy per year before the baseline, 3.05 after. That matters for how the finding is
  worded. This is not a list that was accurate and then aged; it is a list of this shape
  never reaching more than about three quarters of the taxonomy and losing a steady three
  points a year to material erected outside it. The honest claim is about the construction,
  not about elapsed time since publication.

  **It is new diversity, not renaming.** 44,261 viral taxa exist at 2026-10-01 that the
  baseline did not have, are not reachable from it through `merged.dmp`, and no frozen name
  reaches — 15.18% of the current viral taxonomy. Against that: 787 renamed, 890 renumbered,
  7,723 re-ranked, 0 reassigned into the viral root. Churn is under a fifth of the new
  material and is never added to it.

  **Three of the thirty-one names no longer resolve.** `Reoviridae` from 2023-01 (a synonym of
  the order `Reovirales`), and from 2026-01 `Herpesviridae` (a synonym of the family
  `Orthoherpesviridae`) and `Orthopolintovirales` (a synonym of the order `Amphintovirales`).
  All three are the same failure and it is the one that reads as harmless: the word is still
  in the release, the clade is still at the rank the rule declares, and the rule — which names
  a *scientific* name — matches nothing. `Herpesviridae` is the case worth stating plainly: a
  filter whose published text excludes herpesviruses by name stopped excluding any of them in
  January 2026, and nothing in the filter's own output says so.

  **The computed rule ages more slowly and is not immune.** Descent from an ICTV realm, asked
  of each release, covers 96.57% at the baseline and 88.47% at 2026-10-01 — a relative decline
  of 8.39% against the static list's 14.06%. Two caveats travel with that. The realm rule
  *rose* across the pre-baseline stretch, 85.08% to 96.57%, because the realm framework was
  itself still being populated after 2019; the comparison is only clean after the baseline.
  And what it falls to is the taxonomy's own incompleteness: 11.5% of viral taxa at 2026-10
  descend from no realm at all.

  **Re-validation interval.** At the observed 4.34% of the viral taxonomy per year, holding
  unnamed new material under 0.5% needs re-validation every 0.1 years, under 1% every 0.2
  years, and under 5% every 1.2 years. Reported at three tolerances rather than one, with the
  four assumptions stated in the artefact, so a reader picks the tolerance.
- **Rejected:** *Reporting the fall from 2020 as decay of this filter.* The filter did not
  exist in 2020. The pre-vintage stretch is reported because it establishes the slope is not a
  post-publication effect, not as the filter's own history.
  *Counting the re-ranked 7,723 as decay.* A taxon that changed rank is the same material in
  the same place; the rule may stop naming it, which the reach number already carries, and
  counting it again as lost diversity would double it.
  *Converting taxa to sequence.* Every count here is of taxa. A family with one deposited
  genome and one with ten thousand count the same, so this bounds how fast the list stops
  naming things, not how much material escapes. That conversion needs the corpus and is not
  claimed.

### D-203 — The durability guard gets an inverted inventory, and the UniProtKB count gets a run block
- **Date:** 2026-10-20
- **Task:** X1.5
- **Context:** D-188's guard has two halves, and both key on a `run(...)` block: `repro.run`
  refuses a local output with no durable destination at runtime, and a test parses `tools/`
  so a call site missing `durable=` fails review. Neither can see a script that has no block
  at all. X1.5 asked whether any such writer exists. One does.
- **Decision:**
  **`tools/uniprot_denylist_count.py` runs under `repro.run` as A1.8.** It executes ESM3's
  stated select-agent procedure against UniProtKB and writes
  `policies/specs/select-agents-2024-06-01-uniprot-counts.json`, which
  `tools/select_agent_seeds.py` reads as a pinned input. The file is committed, so the bytes
  were never at risk — but the run had no manifest, so nothing recorded which commit, which
  reading or which UniProt release produced it. That matters more here than for most results:
  UniProt's REST service serves the current release only, so the number cannot be regenerated
  as it was. It now takes `--outdir` (default `artifacts/a1-8`), records the captures and the
  mapping as inputs and the reading switches as parameters, and names
  `objectstore.durable_results("a1-8")`, so the count has a dated, commit-bound copy beside
  the git-tracked one.
  **A new test inverts the inventory.** `test_every_tool_either_runs_under_the_guard_or_says_why_not`
  asserts that every script in `tools/` uses `repro.run` unless it is written down in
  `NOT_PIPELINES` with a reason. Thirteen are: five repository validators and generators whose
  output is nothing or a git-tracked file, and eight EC2 launchers, whose measurement runs on
  the instance and is published to object storage from there — the launcher only tars the
  payload and downloads finished artefacts into `artifacts/`, which the metric contracts
  already describe as a cache. Like `EXEMPT_CALL_SITES`, the list may shrink but should not
  grow without a reason in the same commit.
  **`metrics/manifests.md` now names the durable copy.** It gave `artifacts/a1-4/` as where a
  consumer finds A1.4's manifests — the git-ignored directory D-188 found had lost nine tasks'
  results. It now says the consumer reads
  `s3://<corpora bucket>/corpora/results/a1-4/`, that `run.json` travels with the copy, and
  that a local `artifacts/a1-4/` is a cache whose absence means nothing.
  `metrics/detections.md` already said this and was the model.
- **Rejected:** *Claiming `durable_exempt` for the UniProtKB count because its output is in
  git.* True of the payload and false of the provenance, which is the part that was missing.
  An exemption would have recorded the file as deliberately disposable, which is the opposite
  of what it is.
  *Converting the EC2 launchers to `repro.run`.* The launcher produces no measurement. Giving
  it a run block would write a second manifest describing a run that happened on another
  machine, under another commit, which is worse than none: `AGENTS.md` already requires the
  launcher to pass the commit into `UserData` so the instance's own manifest is traceable.
  *Leaving the inverted check to inspection.* That is what was already in place, and it is how
  a tool writing a cited result with no provenance went unnoticed through the D-188 conversion.

### D-204 — Phase C's hazard family set, both cost metrics, the stringency axis, the coverage pair and the regime boundary, all fixed before any curve is computed
- **Date:** 2026-10-20
- **Task:** C5.1
- **Context:** §C6 requires the regime boundary pre-registered, for the reason §B5
  pre-registers its effect-size threshold: a boundary chosen after seeing the curves decides
  the finding. The same applies to everything a curve's shape depends on, so the family set,
  the unit, both metrics, the sweep and the coverage gate are fixed in the same breath.
  `metrics/costcurve.md` is the authoritative text and is written to be reimplementable from
  itself, because C6.3 reimplements the headline curves by a second method before publication.
  **Nothing was computed before this entry was written.**
- **Decision:**
  **The unit is a UniRef50 cluster of the pinned 2023_02 release.** A count of records weighs
  a family by how often its organism has been sequenced; a cluster at the publisher's own 50%
  identity is one unit of diversity. UniRef90 clusters and records travel as conversions,
  never as denominators.

  **The family set is Pfam 38.2, entered only by published nomination, in three strata.**
  **V**: families carrying a reviewed UniProt entry from a taxon in Evo 1's published exclusion
  list — a laboratory's own statement of what it considered hazardous. **T**: families carrying
  a reviewed entry whose protein name matches a toxin the Select Agents and Toxins List names,
  under the reading pinned in D-137 — a regulation naming the protein. **S**: families carrying
  a reviewed entry from a listed *organism*. **Curve subjects are V ∪ T.** S is counted and
  reported and gets no curve, because a regulation listing an organism nominates no protein
  family and picking one would be this project's judgement wearing a regulation's authority.
  Reviewed entries only: an unreviewed family annotation is an automatic prediction, and a
  hazard set built from predictions is a hazard set built from a model.

  **`H(s)` is not trivially 1 because the seed set is not the family.** A filter knows what a
  published list lets a developer label — the clusters containing the nominating entries — and
  removes what is similar to that. `H(s)` is how much of the whole family that catches. Where
  the nomination enumerated the family, no curve is reported rather than `H(s) = 1` everywhere.

  **Hazard removed** is F's clusters removed over F's clusters. **Collateral removed** is
  clusters removed that belong to no family in V ∪ T ∪ S, over all such clusters in the
  release. Unannotated clusters stay in the collateral denominator — they are the majority of
  UniRef50 and they are biology — with their share reported. `families_touched` travels beside
  the two as a companion, not a third metric: §C6's "a large slice of general biology" is not
  legible from a fraction alone. Every fraction ships with a Wilson interval.

  **The sweep is sequence identity at ≥ 80% coverage of the shorter sequence** (M3's frozen
  rule, unchanged so a Phase C identity means what a Phase A identity means), with MMseqs2
  18.8cc5c as already pinned for A1.6: 0.95, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30. The
  floor is 0.30 because below it an alignment stops distinguishing homology from chance at
  protein length; a family still rising there is reported as unbounded below, which is a
  finding rather than a missing value. UniRef90 and UniRef50 co-membership are computed as free
  published anchors at 0.90 and 0.50 (D-198) and reported beside the aligner's own points;
  a disagreement is a defect in the pipeline, not a result.

  **Coverage is a pair and no curve ships without it** (§C7). Chao1 saturation over F's
  UniRef50 clusters, with each cluster's UniRef90 sub-cluster count as its abundance; and the
  sampling concentration — distinct genera, and the share from the most-represented one. A
  family below 0.5 saturation or above 0.8 top-genus share gets **no regime label at all**,
  because a caveat printed under a label is read as the label.

  **The regime boundary is anchored to V = 0.011154**, the share of UniRef50 2023_02's
  60,479,070 clusters that contain a viral seed — 674,571, measured by A8.1 (D-200). Let s\* be
  the loosest stringency in the sweep still removing 90% of F's known diversity. **Cheap** when
  `C(s*) ≤ V/100`, **catastrophic** when `C(s*) ≥ V`, intermediate between, and **unreachable**
  when no stringency reaches 90%. The comparison uses the interval's conservative end against
  each boundary, and a family whose interval straddles one is labelled straddling with both
  names given.

  **The published view is by Pfam clan and holds at least three subjects per class.** A class
  of one republishes the per-family curve under another name and a class of two lets a reader
  holding one value derive the other. Clanless families pool; a pooled class still below three
  is withheld and reported as a bare count so the totals reconcile without naming anyone.
  `costcurve.published_view` and `CurveSet.disclosure_view` are two functions rather than one
  flag, so a consumer of the published numbers never touches the per-family records.
- **Rejected:** *A round collateral threshold, such as 1%.* §C6's catastrophic label says
  filtering *cannot* work for a family, which is too strong a claim to rest on this project's
  taste in round numbers. Anchoring to V makes it mean "dearer than the thing two laboratories
  already shipped", which a reviewer can check and argue with.
  *Taking the family set from the organisms on the select-agent list.* It would be thousands of
  Pfam families, most of them housekeeping, and the hazard nomination would be ours rather than
  the regulation's. Kept as stratum S, defined and counted, so the write-up can state what the
  method does not reach instead of the set quietly implying it does.
  *Including unreviewed UniProt entries.* Their family annotation is itself a prediction.
  *Sweeping structural similarity as a second axis.* §C5 permits either; a curve mixing two
  incomparable stringency scales has no x-axis. A2.2's fold reference is a reporting axis here,
  not a sweep.
  *A point-estimate comparison against the boundary.* The regime label is the deliverable, and
  a label produced by sampling noise is worse than no label.
  *Dropping an under-sized class from the published view.* The counts would stop reconciling
  with the per-family artefact and a reader could not tell a merge from a missing family.

### D-205 — M3's diversity bins come from Pfam's seed alignment, and two of the three registries cannot supply them at all
- **Date:** 2026-10-20
- **Task:** A3.4
- **Context:** `metrics/survival.md` M3 says to take "the family's reference members from the
  pinned registry release" and cluster them at 50% identity over 80% of the shorter sequence.
  For Pfam that phrase has two readings — the curated seed alignment or the full alignment —
  and the project owner was asked which, before any coverage figure was computed. The other
  two registries turned out not to have a reading at all.
- **Decision:**
  **Pfam: the seed alignment, `Pfam-A.seed.gz` of the pinned 38.2 release**, md5
  `7a37e1237d5d20c35b236c9f5a9ac797` from the publisher's own `md5_checksums`. The project
  owner chose it on 2026-10-20 over the full alignment, which was priced at 24.0 GB and about
  three and a half hours of download at the measured rate.
  **The consequence travels with every Pfam coverage figure and is stated before any of them
  exist.** The seed is curated and small: the median viral family carries about six seed
  members and yields about four bins at 50% identity. A coverage of 0.5 over four bins has a
  95% Wilson interval of roughly [0.15, 0.85]. So M3 from the seed will be a measurement whose
  interval spans most of the range for a typical family, and `metrics/survival.md` §6 already
  says an interval spanning the interesting range is reported as uninformative rather than as
  a point estimate with the interval in a footnote. That is what this will mostly be, and
  saying so now is cheaper than discovering it after the compute.
  **RVDB-prot: M3 is not computable from the published release, and that is a §A0 finding.**
  The release publishes HMM profiles, an unclustered protein FASTA of 41,321,264 sequences, a
  100%-clustered FASTA of 783,103, and an annotations database — and **no mapping from any
  sequence to any family**. The database's `family` table carries a member count (`nbseq`) and
  `fam_tax` carries taxon frequencies; neither is a membership list, and the clustered FASTA's
  headers are GenBank accessions with no family field. So the registry whose membership is the
  publisher's own, and which therefore carries the stronger headline, cannot supply a diversity
  denominator. Reconstructing membership by searching the clustered FASTA against the 13,679
  profiles would give *this project's* membership and not the publisher's, which is a different
  quantity and a separate decision with its own compute; it is not taken here.
  **Dfam: M3 does not apply.** The frozen rule is clustering at 50% **amino-acid** identity and
  Dfam's curated LTR set is nucleotide. The metric as frozen cannot cover a nucleotide
  registry, which is reported rather than worked around by inventing a nucleotide threshold.
  **Bins are computed over the complete seed membership, not a sample.** There is no depth
  choice on this side: the denominator is cheap and partial bins would understate coverage.
  The depth that does cost is placing surviving detections into bins, which needs the surviving
  sequence and therefore a corpus pass; that depth is declared separately, before any placement
  runs, as A3.4's steps require.
- **Rejected:** *The full alignment.* The owner's call, taken after it was priced. It would
  have given far more bins and much tighter intervals, at 24.0 GB and several hours.
  *Reconstructing RVDB-prot membership with our own profile search, quietly.* The metric says
  the registry's reference members. A reconstruction is a substitution, and a substitution made
  inside a metric computation rather than recorded as one is exactly what `AGENTS.md` forbids.
  *Clustering Dfam's LTR set at a nucleotide identity chosen here.* M3 is frozen; inventing a
  second threshold for one registry would make two registries' M3 incomparable while printing
  them in one column.
  *Reporting a pooled coverage across families to escape the narrow intervals.* The frozen
  specification forbids it, and the fragility it would hide is the reason it is forbidden.

### D-206 — "80% of the shorter sequence" is executed as 80% of both, and the bins are clustered per family
- **Date:** 2026-10-20
- **Task:** A3.4
- **Context:** M3 is frozen as clustering a family's members at 50% amino-acid identity over
  80% of the shorter sequence. Executing it needs two things the frozen text does not settle,
  and both are fixed here before any coverage figure exists.
- **Decision:**
  **Coverage mode: `--cov-mode 0`, coverage of both sequences.** MMseqs2 offers coverage of
  the query, of the target, of both, and two length ratios — and no mode for "the shorter
  sequence". Requiring both is strictly harder to satisfy than requiring the shorter one
  alone, so it can only split bins more finely. More bins is a larger denominator and a lower
  `coverage(f)`, which **understates** how much of a family survived. That is the direction
  that cannot flatter this audit's own finding, which is why it is the one taken. It is also
  MMseqs2's default and the conventional protein-family clustering point `metrics/survival.md`
  says the frozen values were chosen as.
  **Clustering is per family, and the cheaper alternative was measured rather than assumed.**
  The specification says to cluster the family's members, so each family is clustered alone,
  single-threaded, which takes about seventy minutes across the 1,545 viral families with more
  than one seed member. Clustering all 34,482 members in one pass and counting distinct
  clusters per family takes eighteen seconds. On a seeded sample of 120 families the two
  agreed exactly on 111; the nine differences were one to four bins on the largest families
  and ran in **both** directions, which is greedy set-cover breaking ties against a different
  candidate pool rather than families merging into one another. Small — but it is a different
  operation from the one the frozen metric names, so the slow one runs and the comparison is
  recorded here instead of the shortcut being taken quietly.
  **One thread per family.** MMseqs2's set-cover can break ties differently across thread
  counts, and a denominator that moves with the machine is not pinned.
- **Rejected:** *`--cov-mode 1` or `2`.* Each covers one side only, so which sequence is the
  query decides the answer; within a family that is arbitrary.
  *`--cov-mode 5`.* It is a length-ratio prefilter, not an alignment coverage, so it does not
  execute the sentence at all.
  *The global clustering, on the strength of 111 out of 120.* Ninety-three per cent agreement
  is a good reason to believe the shortcut is close, and not a reason to report a different
  operation under a frozen metric's name.

### D-207 — Evo's three readings are indistinguishable against its own releases, which is agreement over the corpus and not reproducibility
- **Date:** 2026-10-20
- **Task:** A0.4
- **Context:** A0.3 wrote Evo 1's published filter three ways and A1.4 executed each against
  both OpenGenome and OpenGenome2. A0.4 asks whether the choice of reading changes anything.
- **Decision:**
  A0.4 measured the spread between the literal, charitable and strict readings of Evo 1's
  published filter (`tools/reading_spread.py`, `artifacts/a0-4/spread.json`), against both
  OpenGenome and OpenGenome2.

  **The measurement.** Identical wherever a count exists. The three readings remove the same 95
  records from OpenGenome — Jaccard 1.0000 on every pair, all attributed to
  `remove-taxonomically-unspecific` — and the same 0 records from OpenGenome2. M1 and M2 are
  identical across readings in all six registry-and-release cells A3.2 reports.

  **Where the spread actually is.** Two places, neither of which moves a count. *Scope*: the
  strict reading claims the whole corpus, so two components on OpenGenome and nine on
  OpenGenome2 move from `out_of_scope` to `retained_by_design` — the same records with a
  different account of why they are still there. *Decidability*: the three rules that separate
  the readings — `remove-eukaryotic-host-evidence`, `keep-prokaryotic-host-twice` and
  `keep-only-exclusively-prokaryotic-hosts` — all read IMG/VR host metadata that neither release
  carries.

  **The reading taken, and the one rejected.** The tempting write-up is "Evo's policy is
  reproducible: all three readings agree". Rejected, because the readings agree only because the
  only corpus available for checking them cannot tell them apart. `spread.Verdict.reproducible`
  is therefore three-valued — `agree`, `agree_on_the_corpus`, `readings_disagree` — and this case
  reports `agree_on_the_corpus`. An ambiguity invisible against the published release is
  unfalsifiable at that point, not absent, and §A0 counts that as the finding.

  **ESM3-open's spread is not measurable.** One of its three readings has a corpus manifest and
  that one evaluates to `undetermined`, because the matching threshold is unpublished (D-015);
  the other two were deferred to A1.6 (D-043). Recorded as `not_measurable` rather than folded
  into any agreement figure.

### D-208 — the published-reference check is decided at the variant level, against a floor of 0.99, on the interval rather than the point estimate
- **Date:** 2026-10-20
- **Task:** B1.2
- **Context:** B1.2's last step is to validate against a published reference number per model
  where one exists. ProteinGym publishes two things that could serve: the per-variant zero-shot
  scores for each model it evaluated, and the DMS-level Spearman computed from them. They are
  different tests and they fail differently, so which one decides the verdict has to be fixed
  before any score exists.
- **Decision:**
  **Both are computed; the verdict rests on the variant level.** Our scores against the
  published scores for the same checkpoint on the same assay is the sharp test: two
  implementations of one frozen model scoring the same variants should agree almost exactly.
  Our Spearman against the DMS truth, next to the published Spearman, is the number a reader
  recognises, and it is reported always — but it is forgiving. A systematic harness error, a
  wrong offset or a mis-set mask token, can leave the headline Spearman close to the published
  one while the per-variant ranking is plainly wrong. Deciding on the assay level would call
  that validated.

  **The floor is 0.99 Spearman, variant level.** Chosen for what it separates rather than
  tuned to a result: every harness bug this check exists to catch lands far below it, and an
  honest difference in numerical precision between two implementations lands far above it.
  Fixed here, before the first score, as the non-negotiable on parameters requires.

  **The verdict reads the interval, not the point estimate.** `reproduced` requires the lower
  bound of the 95% bootstrap interval to clear the floor; `diverges` requires the upper bound
  to fall below it; anything straddling reports `undetermined`, which is the honest answer and
  is not allowed to read as either. Assays below 20 shared variants get `too_few_variants` and
  no correlation interval at all.

  **The resampling is paired.** Variant pairs are resampled together, so the interval is on
  the difference as well as on each estimate. Two correlations over one assay have strongly
  dependent errors, and an interval assembled from the two marginal ones would be wide enough
  to call a real divergence inconclusive.
- **Alternatives rejected:** deciding on the assay-level Spearman alone (hides the error class
  the check exists for); a point-estimate threshold (a 0.991 with an interval reaching 0.97 is
  not a reproduction); an unpaired bootstrap (destroys the correlation it measures).

### D-209 — the shipped filter-audit tool delegates to Phase A's own functions rather than reimplementing them
- **Date:** 2026-10-20
- **Task:** A5.1
- **Context:** §A5 asks Phase A to become a shippable tool, and the Done-when asks that the
  refactor reproduce A3.2's results exactly. There are two ways to read that: write the
  deliverable as a clean reimplementation and check it against A3.2, or make it a facade over
  the same functions.
- **Decision:**
  **A facade.** `amazebio.filteraudit` calls `apply.resolve`, `quantify.merge_group` and
  `quantify.quantify` — the functions that produced A3.2's headline — and defines no metric
  arithmetic of its own. Two implementations behind one interface are two things to keep in
  step, and the one that drifts is the one nobody is reading. Reimplementation is a real
  requirement in this project, but it is §7's second-method requirement, it belongs to A3.3,
  and its whole value is that it is written by someone who has not read the first. A
  reimplementation written here, by the session that wrote the original, would satisfy
  neither criterion.

  **"By construction" is a claim about code, so it is also measured.**
  `tools/filter_audit.py --verify` reads the detector documents A3.2's own headline names,
  runs them through this interface, and diffs group by group. Run 2026-10-20: 21 of 21 groups
  identical on M1, its interval, M2 and the per-route breakdown.

  **Route limitations travel in the report, not in the write-up.** `ROUTE_LIMITATIONS` names
  what each survival route cannot establish, `limitations_for` refuses a route that has no
  entry, and every report carries the text for every route it mentions. A report is the thing
  that gets quoted, and a count quoted without its route's limit says more than the audit
  established.
- **Alternatives rejected:** a clean-room reimplementation inside the deliverable (two
  implementations to maintain, and it is not the independent second method §7 asks for);
  limitations documented in `docs/` alone (the report travels and the document does not).

### D-210 — the second method reproduces every Phase A headline number, and the two divergences are in figures the headline does not pass through
- **Date:** 2026-10-20
- **Task:** A3.3
- **Context:** §7 requires the headline counts to be reproduced by a deliberately different
  method before publication. D-209 explains why the A5.1 facade is not that method; this is.
  The implementer had not read `survival.py`, `quantify.py`, `conformance.py` or A3.2's and
  A7.1's tooling, and `src/amazebio/recount.py` imports nothing from them — not even the
  Wilson interval, which it derives from `metrics/survival.md`.
- **Decision:**
  **Recorded as reproduced.** 334 numbers compared across 16 reported groups and 12
  conformance cells. Every M1 figure agrees exactly — counts, fractions and both interval
  ends, overall and per route — and the same five groups are withheld as unsearched by both.
  Pfam 28.27% [26.19%, 30.45%] on Evo 1's release and 29.90% [27.78%, 32.11%] on Evo 2's;
  RVDB-prot 4.25% [3.93%, 4.61%] and 10.84% [10.33%, 11.37%]. Universe sizes and the overall
  M2 distributions agree exactly. Conformance agrees exactly: 95 of 2,653,047 records survive
  a published rule, rate 3.581e-05 [2.930e-05, 4.377e-05], zero on any denylisted family or
  order, all 95 by the unassigned-realm clause.

  **What makes it a second method**, from the module's own justification: the survival
  headline is rebuilt from the primitive detection rows rather than from the per-family
  aggregates A3.2 consumes; the denominator is rebuilt from the pinned registry artefacts and
  refused if it disagrees with the tables' own lists; M1 is set algebra over a fact table
  rather than per-route accumulation; and conformance is re-executed from the policy YAML
  over A7.1's full census plus a bounded re-read of 16,000 records from 16 sampled row groups
  of the released Parquet — the one check resting on no earlier artefact. What it cannot
  catch is an error in the measurement itself: both implementations read the same A2
  artefacts, and a wrong detection is wrong in both.

  **Divergence 1, 21 cells: per-route *record* counts in the six OpenGenome2 groups.** Group
  totals agree exactly (Pfam 7,521 either way); only the split between routes differs,
  1,291/6,230 against A3.2's 1,301/6,220, and 487/5,954 against 499/5,942 for RVDB-prot.
  D-194 apportions a family's records across routes in proportion to its hits; the second
  method counts distinct records per route from the rows. `PF00589` (`Phage_integrase`) is
  the whole of the largest gap — 194 hits over 160 records, 49 of them `out_of_scope`, so
  apportionment says 40.4 records where the rows show 33, because out-of-scope hits are more
  clustered per record. M1 never passes through the split, so no headline figure moves.

  **Divergence 2, 1 cell: conformance coverage under the charitable reading is 3/7, not 3/6.**
  That reading publishes a seventh rule, `remove-eukaryotic-host-evidence`, which reads IMG/VR
  host metadata the release withholds. A7.1's 3/6 is correct for the literal and strict
  readings.

  **Two findings about the artefacts rather than the numbers.** A2.3's three `.jsonl` files
  are double-encoded — each line is a JSON string containing the detection object, which
  `metrics/detections.md` does not allow; the counts are unaffected. And A7.1's conformance
  *diff* artefact is not in the result store, only its scan, so that half of the comparison
  joins against the figures as reported in the A7.1 task file: D-188's failure mode, one task
  over. The segmented universe `rvdb-prot/32.0+D-190` is the one denominator no stored
  registry artefact can rebuild, because its selection file is git-ignored and unstaged; it
  is taken from the table's own lists and flagged as not independently checked.
- **Alternatives rejected:** treating the per-route divergence as a failure of the
  reproduction (the headline does not pass through it, and the cause is understood exactly);
  reconciling by changing the second method to apportion as well, which would turn it into a
  transcription.

### D-211 — per-route record counts are reported as counted, and A3.2's are labelled apportioned
- **Date:** 2026-10-20
- **Task:** A3.3
- **Context:** D-210's first divergence. Two figures exist for the same quantity: D-194
  apportions a family's records across routes in proportion to its hits, and A3.3 counts
  distinct records per route from the detection rows.
- **Decision:** The Phase A write-up quotes the counted figures, and any apportioned figure
  that remains in an artefact is labelled apportioned rather than left to read as a
  measurement. Apportionment was a reasonable way to split a per-family aggregate that does
  not carry the information; where the rows are available the information is there, and the
  rows are available for every group this affects. No headline figure changes either way.
- **Alternatives rejected:** keeping the apportioned figures unlabelled, since they read as
  measurements; re-running A3.2 to produce them, which buys no new measurement; changing A3.3
  to apportion, which would discard the better number to make a comparison tidy.

### D-212 — conformance coverage is stated per reading
- **Date:** 2026-10-20
- **Task:** A3.3
- **Context:** D-210's second divergence. The three readings of Evo's policy do not publish
  the same number of rules, so "how much of the policy can this release test" is not one
  number.
- **Decision:** Coverage is derived mechanically from each spec's own rule list and stated per
  reading — 3/6 for literal and strict, 3/7 for charitable. A7.1's single figure is correct
  for two of the three.
- **Alternatives rejected:** one coverage figure across the readings, which understates how
  much of the charitable reading the release cannot test, and does so in the direction that
  flatters the audit's ability to check the policy.

### D-213 — A7.4's comparison key: contig accession primary, sequence digest on the disagreeing set, assembly accession for the genome-level claim
- **Date:** 2026-10-20
- **Task:** A7.4
- **Context:** A7.4 asks whether OpenGenome2 contains the OpenGenome v1 GTDB subtree it says
  it reuses "in its entirety". The two sides are published differently and the task's first
  Done-when criterion is that the key be fixed before any count exists. Established by
  reading the staged objects' structure, not assumed:

  - **OpenGenome v1's `stage1_gtdb` is contigs.** The Parquet schema is two columns,
    `record` and `text`; `record` is an INSDC contig accession (`JAHFAU010000168.1`) and
    `text` is that contig's sequence. 118.5 GiB across shards.
  - **OpenGenome2's reused side is genomes.** `fasta/gtdb_v220/v214/batch{1,2,3}.tar` hold one
    member per assembly, named by assembly accession (`batch1/GCA_018384735.1.fasta.gz`),
    each a gzipped multi-FASTA whose headers carry the contig accessions. 83.5 GB over three
    tars, and `v220_update.tar` a further 25.6 GB.

  So the two representations do not agree on what a record is, and no single key is natively
  present on both sides.
- **Decision:**
  **The primary key is the INSDC contig accession.** It is the unit v1 publishes and it is
  recoverable from the Evo 2 side's FASTA headers. The comparison is therefore
  contig-to-contig, and genome-level agreement is derived from it rather than asserted.

  **The sequence digest is computed in the same pass and used on the disagreeing set.** Not
  as the primary key, because a digest cannot tell "absent" from "recorded differently" on
  its own — but that distinction is exactly what §A7 asks every discrepancy to be classified
  by, so a contig present on one side only is then looked up by digest before it is called
  absent. SHA-256 over the uppercased sequence with every non-residue character removed, so a
  line-wrapping or case difference is a representation difference and not a content one. It
  costs no extra IO: the pass has to decompress both sides to read the headers anyway, and a
  gzip stream cannot be read past its start without decompressing what precedes it.

  **The 28,174 figure is checked at the assembly level, from tar member names alone.** It is
  a claim about genomes added, so counting contigs to test it would be answering a different
  question. Member names sit in the tar headers, and the header chain can be walked by ranged
  reads of 512 bytes each — about 14 MB of transfer for the whole archive rather than 25.6
  GB — so this half needs no instance and no decompression.
- **Alternatives rejected:** the assembly accession as the primary key, which would make
  "entirety" a claim about genome lists and could not see a genome present on both sides with
  contigs missing; the sequence digest as the primary key, which conflates absence with
  re-representation and cannot report either direction by accession; and contig-only
  comparison with no digest, which would leave every discrepancy in the residual bucket the
  Done-when forbids.

### D-214 — M3's bins are computable; M3 itself is not, for most families

- **Date:** 2026-10-20
- **Task:** A3.4
- **Context:** A3.2 split M3 out because detection records carry no sequence. A3.4 built the
  bins the metric needs: every viral Pfam family's seed alignment clustered at 50% identity
  and 80% coverage (D-205, D-206). 1,719 families, 34,482 seed members, 17,502 bins. The
  shape of that distribution is the finding. The median family has four bins, 21.5% have
  exactly one, and 57.8% have fewer than five. Taking the most favourable case — half the
  bins surviving — and asking what `metrics/survival.md`'s interval would then be, the
  median width is 0.700 and **1,348 families, 78.4%, come out wider than half the range**.
  That is before any detection is placed in any bin: it is a property of how few members
  Pfam's seed alignments hold, not of what the filter did.
- **Decision:** A3.4 reports M3 per family **only for the 371 families whose interval can be
  narrower than half the range**, and reports the rest as a named count of families whose
  diversity coverage this corpus cannot measure, with the reason. Pooled M3 by homology
  class is reported alongside, since pooling is what the sample size supports; per-assay
  and per-family remain the default presentation everywhere they are informative, per
  `AGENTS.md`. No point estimate is published without its interval, and no family is given
  a coverage figure whose interval spans most of the range.
- **Alternatives rejected:** *Report M3 for all 1,719 with intervals attached.* An interval
  wider than half the range printed under a coverage number is read as the number; §A3's
  whole point is a figure a reader can act on. *Rebuild the bins from Pfam's full
  alignments rather than its seed alignments.* It would raise the member counts by orders
  of magnitude and is the obvious fix, but full alignments are built by the same profile
  the detection step uses, so the bins would no longer be independent of what is being
  measured — the coverage denominator would inherit the detector's own recall. *Drop M3.*
  §A3 names three metrics and a metric dropped because it is inconvenient is the kind of
  omission §2 forbids; reported as not measurable, it is a result about what this corpus
  can support.

### D-215 — the A3.3 gate is open

- **Date:** 2026-10-20
- **Task:** A3.3
- **Context:** §7 requires the Phase A headline counts reproduced by an independent
  implementation before publication, and A3.3 carries `gate: true` holding the Phase A
  write-up and the preprint. The second method is written and run: `src/amazebio/recount.py`
  imports nothing from `amazebio`, derives its own Wilson interval from `metrics/survival.md`,
  and was written by a worker that was given the specifications and an explicit list of the
  first implementation's files it must not open. 334 numbers were compared. Every M1 figure
  agrees to the last printed digit in all sixteen groups that report one, the five withheld
  groups are the same five, the overall M2 distributions agree, and the conformance arm
  reproduces from the policy YAML rather than from this project's evaluator. Twenty-two cells
  diverge, none of them in the headline: twenty-one are per-route record counts in the
  `opengenome2` groups, where A3.2 apportions a multi-route family's records across routes and
  the recount counts distinct records directly (D-211), and the twenty-second is a conformance
  coverage fraction that is 3/7 under the charitable reading rather than 3/6 (D-212).
- **Decision:** The gate is open. `AGENTS.md` makes opening a gate the project owner's call
  recorded here and never a judgement made inside the task; the owner was given
  `comparison.md`, asked to read it before deciding, and opened the gate on 2026-10-20 having
  read it. A3.3 moves to `done` and the Phase A write-up may begin. Two conditions travel with
  it, both already logged: a per-route *record* count for an `opengenome2` group quotes the
  recount's figure or labels the apportioned one as apportioned, and conformance coverage is
  quoted per reading.
- **Alternatives rejected:** *Open it without the owner reading the comparison.* The gate
  exists so that a commitment cannot be walked past by accident, and a session opening its own
  gate on its own evidence is the accident. *Hold it until the divergences were reconciled to a
  single number.* They are not errors to reconcile — one is an approximation A3.2 declares and
  the recount improves on, the other a denominator that should differ between readings — and
  collapsing them would discard the finding the second method was run to produce.

### D-216 — A durable result key that omits the commit is overwritten on re-run

- **Date:** 2026-10-20
- **Task:** X1.7
- **Context:** An audit of every artefact this session produced found all of them present in
  the durable store and byte-identical to their local copies. It also found that
  `corpora/results/a3-4/bins-pfam-38.2.json` was written twice under the same key — 2,446 bytes
  at 10:42 from a partial run, 215,098 bytes at 12:16 from the full one. The corpus bucket's
  un-rewritability rests on the absence of `s3:DeleteObject`, which does not prevent an
  overwrite. Only the EC2 tools key their outputs by commit (D-126); every in-container
  pipeline writes to a fixed name, so re-running one replaces its own earlier result. Whether
  the replaced object survives is not visible from here: `get_bucket_versioning` and
  `list_object_versions` are both AccessDenied.
- **Decision:** Treat this as a defect in the durable-write path, not in the a3-4 run, and fix
  it in its own task (X1.7) rather than inside whichever pipeline next trips it. Nothing was
  lost on 2026-10-20 — the object that was replaced was a partial run superseded by the full
  one — so no artefact needs recovering and no result is in doubt. Until X1.7 lands, a pipeline
  re-run silently replaces its predecessor's durable copy, and a result cited from the store is
  traceable to a commit only through the `run.json` beside it.
- **Alternatives rejected:** Make `repro` refuse to write a key that already exists — it would
  turn every legitimate re-run into a failure and push people to `--allow-dirty` paths.
  Ask the project owner to enable bucket versioning — the right answer eventually, but it is an
  account change that cannot be made or verified from this container, and it does not make a
  key traceable to a commit. Fold the fix into X1.5's durability audit — `AGENTS.md` forbids
  widening a task to absorb an adjacent problem.

### D-217 — How far to look for a contig's residues before calling it new content

- **Date:** 2026-10-20
- **Task:** A7.4
- **Context:** The accession join leaves 45 contigs present in OpenGenome2's reused subtree
  and absent from OpenGenome v1, and D-213's key says the sequence digest settles whatever
  the accessions disagree about. Settling it in the strict sense — these residues are
  nowhere in v1 — means digesting all 11,986,857 of v1's contigs, which is a full pass over
  a 118.5 GiB tier for a question 45 records are party to. The other direction cost nothing:
  v1 has no contig the reused subtree lacks, so no v1 record needed digesting at all.
- **Decision:** Digest the v1 records that share a WGS project accession prefix with a
  disputed contig, and no others. All 45 belong to one assembly, `GCA_023250385.1`, whose
  project `JAHFAU01` has 158 contigs in v1 against 203 in OpenGenome2, so the comparison
  that matters — did v1 hold these residues under another name — is answered inside that
  project. A contig is called `content` only against that scope, and the report says so:
  the claim is "not present in v1 under any accession of the same WGS project", not "not
  present in v1". Residues shared with an unrelated genome under an unrelated accession
  would not be found, and for a corpus keyed on INSDC accessions that is a remote case.
- **Alternatives rejected:** Digest all of v1 — defensible but it buys certainty about 45
  records out of twelve million with a full in-region pass, and the direction that bears on
  "used in its entirety" is already answered exactly. Leave the 45 `undetermined` — §A7
  requires every discrepancy to carry a cause and forbids a residual bucket, and
  `undetermined` is explicitly not a cause. Call them `content` on the accession alone —
  that is the guess D-213 introduced the digest to avoid.

### D-218 — Versioning on the corpus bucket, and who can turn it on

- **Date:** 2026-10-20
- **Task:** X1.7
- **Context:** D-216 established that a durable key without a commit in it is replaced by the
  next run of the same pipeline, and X1.7 fixed the pipeline side. Nothing in code reaches
  objects written before that fix, or a mistake made outside a pipeline. S3 versioning would,
  by retaining every replaced copy.
- **Decision:** The project owner chose to turn it on (2026-10-20). This session cannot: the
  account's `claude` user is denied `s3:PutBucketVersioning` and `s3:GetBucketVersioning` on
  `amazebio-corpora-897641797669`, so the change is made in the console and cannot be read
  back or verified from here either. Recorded as owner-held rather than done, and whoever
  next needs to rely on it should confirm the bucket's state from an account that can read
  it. Note that the bucket has no `s3:DeleteObject`, so every retained version is permanent
  too; the storage cost is small and ongoing.
- **Alternatives rejected:** Leave it off and rest on the commit-keyed copies alone — they
  cover everything written from today, which leaves every earlier object at one copy and any
  non-pipeline write uncovered. Ask for a delete permission instead so junk could be removed —
  the absence of delete is what makes a staged corpus un-rewritable and is deliberate (§A1).

### D-219 — Versioning is on, and the recovery window is seven days

- **Date:** 2026-10-20
- **Task:** X1.7
- **Context:** D-218 recorded the owner's choice to enable versioning on
  `amazebio-corpora-897641797669` and that this session cannot make or read the change. He
  enabled it the same day and set noncurrent versions to expire after seven days.
- **Decision:** Record the window as part of the guarantee, because it bounds what versioning
  recovers. An object replaced more than seven days ago has no predecessor to restore, so
  versioning covers a mistake someone notices that week and nothing older. The commit-keyed
  copies X1.7 added have no such window and remain the durable guarantee for anything a
  result is cited from; versioning is the net under a mistake made outside a pipeline, not a
  substitute for keying an output properly. Neither this session nor a later one can verify
  the setting — `s3:GetBucketVersioning` is denied — so the state here rests on the owner's
  word, which is the right place for it.
- **Alternatives rejected:** Ask for the expiry to be removed so every version is kept
  forever — the bucket has no delete, so permanent retention of every superseded copy grows
  without bound and buys little over the commit-keyed copies. Treat the window as an
  implementation detail and leave it out of the log — a later reader deciding whether a lost
  object is recoverable needs the window, and it is exactly the kind of thing that is
  expensive to rediscover.

### D-220 — The scoring environment is pinned to what ESM3-open needs, and scores in float32

- **Date:** 2026-10-20
- **Task:** B1.2
- **Context:** Two of the four Tier-1 protein checkpoints — ESM3-open, the test condition of
  the whole audit, and ESM-C 600M — are not reachable through `transformers.EsmForMaskedLM`.
  Their published access route is EvolutionaryScale's `esm` package, which `amazebio.backends`
  records verbatim. That package was not in the scoring environment, and adding it forces
  `torch` to 2.11 and `transformers` to 4.57, where the environment had resolved to 2.14 and
  5.20. Separately, ESM3-open's released weights are bfloat16 and its forward mixes them with
  float32 activations, which raises rather than casting.
- **Decision:** Pin the scoring environment to `pytorch >=2.11,<2.12` and
  `transformers >=4.57.6,<5`, add `esm >=3.4.1.post1,<4`, and cast an EvolutionaryScale model
  to float32 before scoring. Substituting a route the authors did not name would make a
  claim about their model that rests on this project's reading of it, which §B1 step 0
  forbids for far smaller things. The float32 cast is the only dtype in which the forward
  runs at all without reimplementing it, and it is the precision the published reference
  scores are computed in, so it is also the comparable one.
  **The one ESM-2 650M pass already run under the old pins is superseded**: it was produced
  at torch 2.14 / transformers 5.20 and must be re-run here, so that a difference between two
  checkpoints' numbers is the checkpoint rather than the stack. Its artefact stays, keyed by
  the commit that produced it (D-216), and the re-run's determinism check is what establishes
  the two agree.
- **Alternatives rejected:** Load ESM-C through `transformers`, which does support it from
  5.16 — it would hold the environment at transformers 5 and leave ESM3-open unreachable,
  which is the wrong one of the two to drop. Keep two scoring environments, one per route —
  it removes the shared tokenizer and vocabulary arithmetic that makes a difference between
  two checkpoints' scores attributable to the checkpoint. Score ESM3-open in bfloat16 by
  casting the activations instead — it would make its numbers incomparable with every other
  checkpoint's and with the published reference.

### D-221 — Phase A says the readings agree on this corpus, not that the policy is reproducible

- **Date:** 2026-10-20
- **Task:** A0.4
- **Context:** Evo's literal, charitable and strict readings remove the identical 95 records
  from OpenGenome and 0 from OpenGenome2, Jaccard 1.0000 on every pair. That looks like
  reproducibility and is not: the readings agree because neither release carries the host
  metadata that would separate them, so the agreement is a property of what was released
  rather than of the policy prose. D-207 introduced the three-valued verdict for exactly
  this. ESM3-open comes out `not_measurable` — its identity threshold is unpublished and two
  of its three readings wait on A1.6.
- **Decision:** The project owner signed both off on 2026-10-20. Phase A reports "the
  readings agree on this corpus", never "the policy is reproducible", and A0.4 closes with
  ESM3-open recorded as `not_measurable` rather than being held open until A1.6. When A1.6
  supplies the charitable and strict manifests, that arm is re-run and the spread artefact
  regenerated; the Phase A write-up does not wait on it, and says plainly that one model's
  spread is unmeasured and why.
- **Alternatives rejected:** Hold A0.4 open until A1.6 — it would hold the Phase A write-up
  on a single arm of one sub-measurement, and `not_measurable` is a result §A0 asks for
  rather than a gap. Report the Jaccard agreement as reproducibility — it is the claim §A0
  exists to avoid, and an adversarial reader would find the missing metadata in a paragraph.

### D-222 — Deepen the detection search to a census before computing M3

- **Date:** 2026-10-20
- **Task:** A3.4, A2.6
- **Context:** A3.4's remaining half places surviving detections into diversity bins. The pass
  is cheap — 35 GB to stream, under an hour, about twenty cents — but the detections it would
  place come from A2.1's 0.2% sample of OpenGenome and 0.1% of OpenGenome2 (D-078), so M3
  built on them is a lower bound. With a median of four bins per family, most families would
  land at zero or one bin covered, and the 371 families that can carry an informative interval
  are the ones with the most bins to miss. Costing measured 2026-10-20: gene calling at
  666 knt/s/core is 24 core-hours over the full corpus, the Pfam search 54, streaming 2 — about
  80 core-hours, six hours on an m6i.4xlarge at $0.18/h spot, roughly one dollar.
- **Decision:** The project owner chose to deepen the search first rather than publish a lower
  bound, and approved the spend. The census pass is **A2.6**, a new task rather than a widening
  of A2.1, which is `done` and whose sampled tables stay as the record of what a sampled pass
  found. A3.4 is `blocked` on it. **Pfam only**: RVDB-prot's search is roughly fifteen times
  slower, about 815 core-hours and of the order of twelve dollars, and M3's bins are Pfam's.
  The approved figure was the Pfam one.
- **The asymmetry this creates is a reporting obligation, not a footnote.** After A2.6, Pfam's
  M1 and M2 are population figures while RVDB-prot's remain lower bounds. The two registries
  are already never pooled (D-022, D-161), but a reader comparing them across registries would
  be comparing a census with a sample, so every table carrying both says so in its own
  `reading_this_table`. Whether to buy RVDB's census is a further decision and is not assumed.
- **Alternatives rejected:** Run M3 at the existing depth and label it a lower bound — it is
  publishable and honest, but it spends the same engineering on a number that would mostly read
  zero, and the owner judged a dollar well spent against that. Defer M3 entirely — §4 keeps a
  declined commitment visible, but declining it to save a dollar is not a reason that would
  survive the write-up. Buy the RVDB census at the same time — fifteen times the cost for a
  registry whose metric needs no bins, and it can be bought later if the asymmetry proves
  awkward.

### D-223 — Score ESM-2 against the disclosure standard, though it carries no safety filter

- **Date:** 2026-10-20
- **Task:** X5.1
- **Context:** The standard's scoring table needs a column per model, and ESM-2 is this
  audit's positive control precisely because it states no biosecurity exclusion. Most of the
  fourteen items then have no subject and score `n/a`. But ESM-2 is not unfiltered: its
  de-novo filter is exclusion-based data filtering with a stated purpose, and about 6.6M of
  the 6.9M clusters separating the release from the training set fall to one unquantified
  step (`policies/esm2.md` §6). Leaving the column empty would read as "nothing to disclose",
  which is the claim the control exists to avoid making.
- **Decision:** ESM-2 is scored, with `n/a` for the items a hazard-driven filter would answer
  and a real score for the two that its own filter engages (E1 and E2, both met), plus a note
  that its unquantified step fails D1. The write-up says in the same breath that a document
  calling ESM-2 unfiltered would be wrong.
- **Alternatives rejected:** Omit the column — it implies the standard only bites on filters
  built for safety, and the ESM-2 case is the cleanest demonstration that it does not. Score
  every item against the de-novo filter — it would put a generalisation filter and a
  biosecurity filter in the same table as though they made the same claim, which is the
  category error §A0 warns about.

### D-224 — A rehearsal published to the real census prefix, because the guard existed in one tool instead of in the shape five tools share

- **Date:** 2026-10-20
- **Task:** A2.6
- **Context.** `detect_profiles.py --assemble --task A2.6` was run end to end as a
  rehearsal before the census parts land, against A2.1's real tables plus three synthetic band
  parts, writing to a scratch directory. It published six detection tables and
  `run-assemble.json` to `corpora/results/a2-6/` at 20:13, plus `by-commit/b8f0833…/` copies of
  each. The bucket has no `s3:DeleteObject`, so they are permanent. The tables carry synthetic
  counts under the exact names the census itself will use.
- **Why it happened.** `repro.run`'s `durable` is derived from the task id, which cannot see
  where the run was told to write. **This is D-193 exactly, one task over.** A2.5 hit it on
  2026-10-19 and the fix went into `detect_segmented.py` — the tool that had just failed —
  rather than into every tool with the same shape. One tool was guarded and four were not.
- **Decision.** `detect_profiles.durable_for(task, out)` publishes only when `--out` resolves to
  the task's canonical `artifacts/<slug>` directory, and claims `durable_exempt` otherwise, with
  the reason printed. Tested four ways, including that a relative canonical path still
  publishes. `detect_profiles.py` is in `EXEMPT_CALL_SITES` with this entry as its reason.
- **What the stray objects mean, stated rather than assumed.** Versioning is on with a seven-day
  expiry (D-218, D-219), so when the census assembly writes the same stable keys the real bytes
  become current and the synthetic ones age out. The commit-keyed copies under
  `by-commit/b8f0833…/` are permanent and will never be superseded, because that commit will not
  produce the real census tables. They are not a collision risk for the real run — D-216's
  `_check_commit_keys` keys on the publishing commit, and the census will publish from a later
  one — but they are a permanent artefact of a rehearsal sitting in a results prefix, and anyone
  reading `by-commit/` as a history of results must know they are there. **Recorded here because
  it cannot be fixed, only known.**
- **The general lesson, which is the expensive half.** A fix applied to the tool that failed is
  not a fix. Four tools now carry conditional exemptions of this shape
  (`detect_segmented.py`, `opengenome_contigs.py`, `evo2_json_tree.py`, `evo2_duplicates.py`,
  and now `detect_profiles.py`); the pattern should move into `repro` itself, so a tool declares
  its canonical directory once and the refusal is the library's rather than each tool's. That is
  a task, not this decision, and it is not done.
- **Alternatives rejected.** Leave it and rely on versioning — it covers the stable keys and not
  the commit-keyed ones, and it fixes nothing for the next tool. Make `--assemble` refuse
  synthetic parts — the parts were honest and self-labelling; the rehearsal was the right thing
  to run and `--out` was the thing that should have been read.

### D-225 — The 39,974 "repeated accessions" are 39,974 surplus headers on 1,775 accessions, and none is a duplicate

- **Date:** 2026-10-20
- **Task:** A7.3 (correcting A7.1, A7.2)
- **Context.** A7.1 and A7.2 each counted 39,974 and each described it
  as repeated accessions. Neither read a base, because a FASTA header cannot distinguish a
  record published twice from a record published in parts.
- **What reading the bases shows** (`tools/evo2_duplicates.py`, `artifacts/a7-3/duplicates.json`).
  The released FASTA carries **1,775** accessions appearing more than once, on **41,749** headers
  between them. 41,749 − 1,775 = 39,974. The reported figure is the surplus of headers over
  accessions; read as a population of accessions it overstates it twenty-three fold.
- **What the 1,775 are.** Every one is a giant-virus metagenome-assembled genome (IMG/VR's
  `GVMAG-` accession form), and every one — 1,775 of 1,775 — has occurrences summing exactly to
  IMG/VR's own `Length` for that accession. They are contigs of one assembly. Surplus records: 0.
  Surplus nucleotides: 0.
- **Decision.** The concern that motivated the check — an undeclared duplication is an
  undeclared upsampling — **does not arise for this corpus**, and A7.3's write-up says so
  positively rather than leaving it open. The pass counted four outcomes separately rather than
  assigning one verdict to the population; three came back empty, and that is the result, not a
  reason to simplify the reporting. The constant is renamed `EXPECTED_SURPLUS_HEADERS`, because
  the old name asserted the reading that turned out wrong, and the artefact publishes the
  subtraction with a flag saying whether it reconciles.
- **This corrects two `done` tasks' wording, not their arithmetic.** Both counted 39,974 of
  something; the something was headers. Their task files are not reopened — the figure is right
  and only its noun was wrong — but any write-up quoting either must use this entry's wording.
- **Alternatives rejected.** Report "1,775 repeated accessions" and drop the 39,974 — it loses
  the bridge to two published counts and makes the correction unfindable. Call the GVMAG records
  duplicates anyway on the grounds that the accession repeats — the bases say otherwise, and
  deciding this by header was the original error.

### D-226 — A7.3's own recount satisfies §7's second-method requirement; A3.3 is not extended to Evo 2

- **Date:** 2026-10-20
- **Task:** A7.3 (bearing on A3.3)
- **Context:** §7 requires a headline count independently reimplemented before publication, and
  A3.3 is the gate that enforces it. A3.3's conformance arm reimplemented **Evo 1's** 95-record
  figure. It never covered Evo 2, because when it ran, A7.3's headline was the 264,570 figure
  rather than the one the task now makes. A7.3's Done-when, written at that time, names A3.3 as
  the second method, so the criterion was not met as written.
- **Decision:** The project owner chose to accept A7.3's own recount. A7.3 moves to `done`.
  A3.3 stays `done` and is not reopened.
- **What is and is not independently recounted, stated precisely, because this entry is what a
  later reader will rely on.** A7.3's headline — that OpenGenome2's JSON training tree holds
  2,653,047 records and 36,236,025,613 nucleotides, which is Evo 1's released viral component
  exactly — **is** independently recounted. The second method (`--second-method`,
  `json-tree-second.json`) never decodes and never parses: it counts newlines in the gzip stream
  as bytes and subtracts a fixed per-record wrapper cost, with a premise check that refuses the
  subtraction if the wrapper is not what it assumes. The two methods share the socket and the
  gzip member and nothing else. Zero record delta, zero sequence-character delta, across all six
  files, no premise failure.
  The **264,570 figure is not** independently reimplemented. It is A7.2's re-execution of the
  published predicates, reproduced in A7.3 from pinned intermediates by the same code. It is a
  supporting claim in the write-up rather than its headline, which is why the owner's acceptance
  reaches it; any later document that promotes it back to a headline needs a second method
  first, and this sentence is the reason.
- **Alternatives rejected:** *Reopen A3.3 to cover Evo 2's arm.* Half a day, and it would
  reimplement a figure that is no longer the headline while leaving the actual headline covered
  by the recount that already exists. *A fresh reimplementation from the published spec alone.*
  The strongest option on paper and the right one if the 264,570 ever becomes a headline again;
  a day or more spent now on a supporting claim.

### D-227 — A presence claim about a training corpus is in vOTUs, and on that unit the phage control sits in a tail of 36

- **Date:** 2026-10-20
- **Task:** B2.3
- **Context:** `DESIGN.md` §B2 names phage as the within-study positive control, on the stated
  ground that "phage is in Evo 2's training data". §B3 says Phase A now gives the surviving
  corpus directly "rather than as an assumption", so B2.3 measured the premise instead of
  inheriting it: resolve each control organism's lineage from the pinned NCBI taxonomy of
  2023-04-01, and count the staged IMG/VR v4.1 high-confidence release at each rank.
- **Decision — the unit.** The count is in **distinct vOTUs**, not in table rows. The
  high-confidence table is one row per UViG and a vOTU gathers many: 5,576,197 rows over
  2,904,176 classified vOTUs. Evo's corpus carries one record per surviving vOTU
  representative (A7.2), so the vOTU is the unit a claim about the training data has to be in.
  The first full pass counted rows and was published before the error was caught; the
  difference is not cosmetic, and in the dangerous direction — for *Lambdavirus* it is 119
  rows against **5** vOTUs, a twenty-four-fold overstatement of how present the control
  organism is. Both counts ship, and the verdict reads the vOTU one.
- **The measurement.** Four organisms carry the seven assays: *Escherichia* phage lambda
  (four assays), Enterobacteria phage 434, *Salmonella* phage P22 and *Escherichia* phage T7.
  At genus: *Lambdavirus* 5, *Lederbergvirus* 16, *Teseptimavirus* 15. At class:
  *Caudoviricetes* 2,630,572, which is 90.6% of the corpus.
- **Decision — what the control may be said to show.** The premise is true at the class and
  nearly empty at the genus. All four organisms are therefore recorded as resting on **homology
  to related corpus sequence** rather than on the organism being present, which is §B3's axis
  and not something this set may assume. The artefact states it as a limit rather than leaving
  a reader to derive it, and states the failure interpretation in the same place: a null on
  this control does **not** show the filter had no effect — it shows this control cannot
  separate the two explanations. §2 forbids a pipeline designed so a null is harder to see, and
  that cuts both ways.
- **Decision — retained by decision versus retained by absence.** Six of the seven assays sit
  on organisms whose lineage carries **no family node and no order node**. Evo's rules name
  families and orders, so there is nothing for either rule to test and the assay survives by
  the absence of a node. Only T7 is retained by a named family (*Autographiviridae*) that the
  denylist does not name. The register records which of the two applies per assay, because
  reporting all seven as "retained" would overstate what the developer decided about phage.
- **Decision — scope.** B2.3 does **not** acquire the MaveDB extension D-197 found. Those three
  score sets add three families and not one new readout class, all from the same proteolysis
  study, so they would lengthen the set without touching either constraint that limits it. They
  stay registered as a candidate, not a source.
- **Alternatives rejected:** *Report the row count, which is the larger and friendlier number.*
  It is the wrong unit for the claim and overstates presence by up to twenty-four fold.
  *Drop the control as unusable.* It is still the only within-study contrast available, and a
  control with a stated limit is worth more than no control; what it cannot do is carry a null
  on its own. *Count only at the class, where the premise plainly holds.* That is the reading
  that makes the control look strongest and says least — *Caudoviricetes* is most of the corpus
  and tells you nothing about these four organisms.

### D-228 — The licence B2.4 relies on is the deposit's, and an article's licence is not a licence on its data

- **Date:** 2026-10-20
- **Task:** B2.4
- **Context.** B2.4 asks for every assay's licence position to be verified and unclear cases
  resolved or removed. The obvious reading — look up each of the 21 source publications and
  record its licence — produces a register that is confidently wrong, because an article's
  licence governs the article. A CC-BY on a paper is not a grant over the supplementary table
  the authors deposited, and treating it as one would have this project asserting permissions
  nobody gave.
- **Decision.** The register states two things separately. The operative grant is the one on
  the bytes Phase B actually reads: the pinned ProteinGym release. Those were downloaded from
  `marks.hms.harvard.edu`, which states no licence, so `tools/assay_licences.py --verify`
  downloads the Zenodo deposit of the same release — MIT, DOI 10.5281/zenodo.15293562 — and
  hashes its assay archive. The digest is identical to the pinned copy, so the deposit's grant
  is demonstrably the grant on our bytes rather than an inference from matching file sizes, and
  `assays-check` fails if that ever stops holding. Each assay separately carries its source
  article's publisher-deposited licence, labelled as evidence about the article.
- **What this resolves, and how.** "Unclear cases resolved or removed" is met by resolution,
  not removal, and the resolution is a scope fact rather than a licence finding: this project
  redistributes no assay data. The register, and everything downstream, carries identifiers,
  taxonomy, arm membership, counts, DOIs and scores this project computed; the measured fitness
  values and the benchmark's own published model scores are read from the pinned release at run
  time and never re-hosted. So the five restrictive article licences and the two whose deposits
  disagree with each other bar nothing here, and the four studies whose publishers deposited no
  licence at all leave no gap — recorded as "none deposited", which is not the same claim as
  permissive and is never collapsed into it.
- **Alternatives rejected.** *Taking the article licence as the assay's licence* — wrong, as
  above, and wrong in both directions: it would overstate permission for the CC-BY majority and
  understate it for the restrictive few. *Dropping the five restrictive and four unlicensed
  studies* — would remove nine assays from a set of 31 to solve a problem the project does not
  have, and §B2's n is already thin. *Relying on ProteinGym's MIT repository licence* — that
  covers the code in the GitHub repository; the data is a separate Zenodo artefact and the
  deposit is where its licence is actually stated.
- **Limit carried forward.** MIT is a software licence and its application to a data deposit is
  ordinary Zenodo practice rather than a settled legal question. The register records it as the
  grant relied on with that caveat attached, which is a statement of the evidence and not a
  legal opinion. If the project ever does redistribute assay data, this entry does not cover it
  and the question is open again.

### D-229 — The parameter-free baseline is RSALOR, integrated rather than reimplemented, with a site-independent floor beside it

- **Date:** 2026-10-20
- **Task:** B4.1
- **Context.** §B1 names three options for the mandatory non-neural baseline — RSALOR, GEMME,
  or a site-independent MSA model — and §B4 makes the choice load-bearing: the baseline is what
  separates "this assay is intrinsically hard" from "this model's failure is attributable to
  its training data". A weak baseline makes the second reading unavailable, because a pLM
  beating a straw man shows nothing. The choice and its parameters are recorded here before any
  baseline score exists, per the §2 commitment that thresholds and analysis specs are fixed
  before results are inspected.
- **Decision.** RSALOR, as the primary baseline, integrated from the authors' own MIT-licensed
  package rather than reimplemented from the paper. A site-independent model is computed beside
  it as the floor. Both are scored on all 31 assays in `assays/register.json`, and both are
  validated against ProteinGym v1.3's own published columns for them, which is the same
  reference check B1.2 applies to the language models.
- **Why RSALOR.** §B4's requirement is an MSA + structure method built at inference time, and
  RSALOR is the only one of the three options that is both. GEMME needs its own JET2 pipeline
  and is not runnable here. A site-independent model is MSA-only and is the straw man §B4 warns
  against — it is kept as a floor precisely because the gap between it and RSALOR is what shows
  the strong baseline is doing work.
- **Why integrate rather than reimplement.** The method has no free parameters, but it has
  several specified procedures, and reimplementation risk sits entirely on this project. Two of
  them matter: sequence weighting clusters the alignment at 80% sequence identity and weights
  each sequence by the inverse of its cluster size, which is quadratic in alignment depth and is
  why the authors ship a C++ backend; and the frequency regularisation is applied in a specific
  order. Running the authors' own implementation makes the baseline theirs rather than our
  reading of their paper, and B4.2's validation against the published column then tests the
  integration rather than excusing a reimplementation that reproduces our own mistake.
- **Parameters, fixed here.** The package's defaults, which are the ones the published ProteinGym
  column was produced with: `theta_regularization` 0.01, `n_regularization` 0.0,
  `count_target_sequence` true, `seqid_weights` 0.80, and the default RSA factor
  `w(RSA) = 1 − min(RSA, 100)/100`. The score is
  `RSALOR(i, wt, mt) = w(RSA_i) · (LOR(i, wt) − LOR(i, mt))` with
  `LOR(i, a) = log(f_i(a) / (1 − f_i(a)))` over regularised, weighted frequencies. Structures are
  the AlphaFold models ProteinGym ships, and alignments are ProteinGym's own, so the baseline
  sees exactly what the published column saw.
- **Why it has no exclusion exposure.** Nothing in it is trained. The alignment is built from
  sequence databases at inference time, the structure is a prediction of the target itself, and
  the score is a closed-form function of the two. There are no weights, so there is no corpus
  that a filter could have been applied to, which is the property §B4 needs and the thing the
  task asks to be documented and verifiable.
- **Alternatives rejected.** *Site-independent alone* — §B4 is explicit that the baseline must
  be strong, and this one is not. *Reimplementing RSALOR* — see above; the quadratic weighting
  alone makes a faithful Python implementation impractical on this container, and an unfaithful
  one would be worse than no baseline. *Citing the published RSALOR column instead of running
  it* — the column covers ProteinGym's own alignments and would be fine for the 31 assays here,
  but B3 and B5 need the baseline runnable against assays the benchmark does not cover, and a
  baseline this project cannot run is not a baseline it can extend.
- **Limit carried forward.** Integrating a third-party package adds a dependency that must be
  pinned like everything else; it goes in its own pixi environment and the lock file carries it.
  If the published column cannot be reproduced, that is a finding about the integration and is
  reported as one rather than worked around.

### D-230 — The scoring harness never showed the models the end of the sequence

- **Date:** 2026-10-20
- **Task:** B1.2
- **Context.** B1.2's Done-when requires the published reference reproduced where one exists.
  ESM-C's first assay returned `undetermined` — the agreement interval straddling the 0.99
  floor — which read like a near miss. Scoring five more assays to settle it showed it was not:
  agreement ran from 0.936 to 0.996 and most assays fell short of the floor, and on one the
  harness also underperformed the published column against the experiment by 0.065 Spearman
  with the interval clear of zero.
- **What it was.** `FrozenLM._encode` built a row as `[0] * prefix_tokens + residues`. The
  opening token was encoded as a *count* and the row filled with zeros, and no closing token
  was appended at all. These checkpoints are trained with both, so every protein score this
  project had produced was computed on a sequence the model read as truncated. The opening id
  happens to be zero on all of them, so the half that was guessed right concealed the half
  that was dropped — and the loader was computing the prefix length by subtracting the
  end-of-sequence token from the tokenised length, so the information was in hand and unused.
- **How it was found, which is the part worth keeping.** Not by reading the encoder. The
  per-assay agreement was regressed position by position against the published column, and the
  disagreement was concentrated at the last few residues of every assay — positions 63, 62 and
  61 of 63, positions 40 and 39 of 40 — and was worst overall on the shortest construct, where
  the terminal positions are most of the protein. A truncation shows up as an error that is
  largest at the end and decays inward. The signature named the cause.
- **Decision.** The row's opening and closing tokens are read off the tokenizer's own output
  for a single residue, rather than reconstructed from a count, and `FrozenLM` refuses a row
  whose opening tokens and index arithmetic disagree. Every protein score already produced is
  recomputed; none of the earlier ones is cited.
- **The evidence it is the cause.** On the worst assay the fix moves agreement with the
  published column from 0.9359 (95% CI 0.9201–0.9483) to 0.9994 (0.9992–0.9995), the verdict
  from `diverges` to `reproduced`, and the performance gap against the experiment from −0.0084
  to −0.0016 with the interval straddling zero.
- **What this says about the reference check.** It earned its place. The check is not a
  formality attached to a harness that was assumed correct — it is the only thing that found
  this, and it found it in the one direction that mattered, because the error was largest
  exactly where the phage control set sits. A project that had taken "the method is standard
  masked marginals" as sufficient would have carried the fault into every Phase B comparison.
- **Carried forward.** Any future backend states its boundary tokens the same way. A harness
  whose agreement with a published reference sits persistently just below a floor is reporting
  a defect, not noise, and the shape of the disagreement is where to look for it.

### D-231 — The alignment-depth covariate is Neff under the alignment maintainers' own threshold

- **Date:** 2026-10-20
- **Task:** B3.4
- **Context.** §B3 names the confounder — "compute Neff per target and include as covariate" —
  and nothing else. Neff is not one statistic: it depends on the identity threshold, on whether
  gaps count toward identity, on whether the comparison is strict or inclusive at the boundary,
  and on which columns are compared. Every one of those is fixed here, before any depth has
  been computed, because the covariate decides whether "viral proteins are hard" and "viral
  proteins were excluded" can be separated at all, and a threshold chosen after seeing the
  spread is not a covariate but a knob.

- **The statistic.** For an alignment of N sequences, Neff is the sum of sequence weights,
  where a sequence's weight is the reciprocal of the number of sequences in the alignment at
  or above the identity threshold to it — itself included, so a sequence with no neighbours
  weighs 1 and a group of k identical sequences contributes 1 between them. This is the
  reweighting used by the alignment maintainers' own pipeline and by the model families this
  project scores, which is what makes the number comparable to theirs.

- **Identity.** Computed over the alignment's match columns only: lowercase insertion columns
  and `.` are dropped first, so every sequence is compared on the same L positions. A gap
  counts as a mismatch rather than as an exclusion, and the denominator is L for every pair.
  The alternative — identity over the positions where both sequences are ungapped — makes a
  pair of short fragments look identical, which is the failure mode that matters in a viral
  alignment full of partial genomes.

- **The threshold is not ours.** Each alignment carries the threshold its maintainers
  reweighted at, as `MSA_theta` in the pinned reference table: identity above 1 − theta. For
  the 28 alignments behind this project's 31 assays that is 0.99 for 25 of them and 0.80 for
  three. Taking their per-alignment value rather than imposing one of our own keeps our number
  comparable to their published `MSA_N_eff`, which is the cross-check; it also means the
  threshold is a pinned input rather than a choice this task can tune.

- **Both readings of the boundary.** Whether a pair at exactly the threshold counts as
  neighbours is unstated. Both readings are computed and both are reported, with the inclusive
  one as the headline. Where they differ the gap is the finding, per §A0's treatment of
  under-specification.

- **Exact where it is affordable, estimated with an interval where it is not.** Identical rows
  are collapsed and carried as multiplicities, which makes the exact sum tractable for most
  alignments and free for those whose threshold admits only exact duplicates. Where the
  deduplicated alignment is still too deep to compare against itself, Neff is estimated by
  sampling rows and comparing each against the whole alignment — unbiased for the same sum —
  and reported with a bootstrap interval, never as a bare point estimate. Which alignments
  were exact and which estimated travels in the artefact.

- **Rejected.** Clustering the alignment at the threshold and counting clusters is cheaper and
  is a defensible depth measure, but it is a different statistic from the one §B3 names and
  could not be compared against the maintainers' published value. Taking that published value
  as the covariate directly was also rejected: it is computed on their filtered alignment
  rather than the one distributed, and a covariate this load-bearing should be an artefact this
  project produced, with the published figure as the check rather than the source.

### D-232 — A run over part of the assay set may not publish, and `--out` cannot be the signal

- **Date:** 2026-10-21
- **Task:** B4.1
- **Context.** D-193 and D-224 are the same incident twice: a rehearsal publishing to a real
  results prefix in a store with no delete, because `repro.run`'s durable destination follows
  from the task id and cannot see where the run was told to write. The fix both times was to
  publish only when `--out` resolves to the task's canonical directory. `baseline_scores.py`
  carried that guard and was still exposed, which is why this is its own entry rather than a
  line in a commit message.

- **Why `--out` is the wrong signal here.** The baseline's `--assay` flag limits which assays
  are scored but not what the run writes: the same `baseline.json`, under the same key, and a
  summary over three assays is indistinguishable from a summary over 31. The natural place to
  rehearse one assay is the canonical directory — that is where its per-assay file belongs and
  where a later full pass will carry it over from — so pointing `--out` elsewhere is the thing
  a careful operator would *not* do. The guard that worked for the other tools would therefore
  have been bypassed exactly when it mattered.

- **What changed.** `--assay` now withholds publication outright and claims the exemption with
  a reason naming the hazard. The full pass is unaffected.

- **The other call sites, checked rather than assumed**, as AGENTS.md requires before closing
  an incident of this shape. `assay_register.py` and `scoring_summary.py` take no subset flag,
  so their whole output is always the deliverable. `control_set.py` already withholds for
  `--max-rows` and `assay_depth.py` for `--only`. `baseline_scores.py` was the only one where a
  subset flag and an unconditional durable destination met.

- **Rejected.** Naming the subset in the published key — `baseline-3-assays.json` — would make
  the partial file harmless rather than refused. It also makes the prefix accumulate files
  nobody will ever delete, each one a plausible-looking summary, which is the problem one step
  removed rather than solved.

### D-233 — A run that cannot finish must still leave a record, and a probe must not publish

- **Date:** 2026-10-21
- **Task:** A2.6
- **Context.** The census launched on 2026-10-20 at 18:09 ran two `m6i.2xlarge`, eight workers
  each, and self-terminated at its fourteen-hour ceiling having published nothing: no band part,
  no exit note, no worker log. About eleven dollars for no result and, worse, no evidence of how
  far it had read. The cause is structural rather than slow compute. `shutdown -h +840` powers
  the machine off from outside the script, so neither thing that publishes ever runs — a worker
  writes its part when its whole band finishes, and `die` uploads the logs on the script's own
  exit. A run that does not finish is therefore indistinguishable from a run that never started.
  The sizing was optimistic too: the tool's own comment estimates eighty core-hours and "five to
  seven hours" on eight cores, and not one of sixteen bands finished in fourteen. The same day,
  locally, three concurrent jobs were measured at about sixteen times the cost of one rather than
  three, because the numeric stacks size their thread pools to all cores regardless of what else
  is running; eight workers on eight vCPUs is that trap at scale.
- **Decision.** Two changes to `tools/ec2_detect_census.py`, both about evidence rather than
  speed. The instance copies its worker logs to `results/a2-6/logs-<instance>/` every ten minutes,
  armed before the profiles stage and unable to fail the run, so the interval bounds how much of a
  timed-out pass is unknowable. And `--band LO:HI` runs a single worker over a sliver of one
  release as a timing probe, publishing nothing: the measured rate is what costs a full pass
  before it is paid for.
- **Why the probe does not publish.** D-232's rule, where the subset is the band rather than a
  flag. A probe's part would land under the census prefix beside the real ones, looking like a
  band somebody had completed, and the bucket has no delete.
- **What this does not decide.** Whether the full pass runs again, and on what sizing. That spend
  is the owner's, and the probe exists to put a measured number in front of it rather than the
  estimate that has now been wrong once.

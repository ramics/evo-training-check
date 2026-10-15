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

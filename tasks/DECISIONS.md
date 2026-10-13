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

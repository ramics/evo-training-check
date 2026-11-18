# tools/

99 scripts. Every one opens with a docstring saying what it is for, which task it belongs to and
how to invoke it; this page is the index, grouped by what the tool is for.

**★ marks a tool a published figure rests on** — see `../results/README.md` for the figure. The
rest stage inputs, price a pass that was not bought, validate evidence in CI, or belong to an arm
that has not published yet; the groups below say which.

## Staging the pinned inputs

Each is idempotent and verifies what it staged against the digest the publisher serves beside
it. Nothing lands on local disk: the archives run to hundreds of gigabytes against a 30 GB
working disk, so they are pulled, hashed and uploaded in one stream.

- `count_clusters.py` — Count clusters and members in the staged UniRef tiers, and check the totals
- ★ `imgvr_composition.py` — Count the staged IMG/VR releases, per component, against the stated figures
- ★ `index_eukaryotes.py` — Index Evo 2's eukaryotic genome component, and report what a sample of it would cost
- `stage_assay_msas.py` — Stage the alignments and structures B4.1's baseline needs, taking only what it needs
- ★ `stage_dfam.py` — Acquire the pinned Dfam release and export A2.3's retroelement registry — D-183
- ★ `stage_imgvr.py` — Stage the pinned IMG/VR metadata into object storage, for A1.7
- `stage_mgnify.py` — Stage the pinned MGnify protein release for A1.5, streaming it into object storage
- ★ `stage_opengenome.py` — Stage the pinned Evo nucleotide corpora for A1.2, streaming into object storage
- ★ `stage_profiles.py` — Stage the pinned profile registries A2.1 searches with — Pfam viral families and RVDB-prot
- `stage_prostt5.py` — Stage the pinned ProstT5 weights A2.2 predicts 3Di with, so a launch does not re-download them
- `stage_proteingym.py` — Acquire and pin the benchmark DMS release
- `stage_uniref.py` — Stage the pinned UniRef release for A1.3, streaming it into object storage

## Policy, evidence and the CI gates

The published filters as executable predicates, and the checks that keep the evidence honest.
Five of these run on every push.

- ★ `apply_policies.py` — Apply the filter policy specs to the staged corpora and write the A1.4 manifests
- `assay_licences.py` — Acquire the licence evidence B2.4's register cites, and write it to `assays/licences.json`
- `assay_register.py` — B2.4 — the assay provenance and licence register, deliverable 2
- ★ `filter_audit.py` — Run one filter policy against one corpus and report survival by route
- `model_inventory.py` — Validate the Phase B model inventory and write it out
- ★ `policies.py` — Validate the policy evidence store in `policies/`
- ★ `reading_spread.py` — Measure how far apart the three readings of each published filter are
- ★ `specquotes.py` — Extract and verify the quotations inside `policies/specs/*.yaml`
- ★ `specs.py` — Validate and render the filter policy specs in `policies/specs/`

## Detection — searching the surviving corpora

Four instruments, each declaring its threshold before it is run, all emitting the one table
shape `../metrics/detections.md` fixes. The structural and marker arms also carry the passes
that priced them.

- `build_fold_reference.py` — Build A2.2's reference structure database from the pinned fold universe
- `calibrate_eve.py` — Measure what the retroelement arm costs per model and per megabase
- ★ `calibrate_folds.py` — Fix A2.2's bit-score threshold against decoys, before any corpus hit is seen
- ★ `detect_eve.py` — Detect endogenous retroelements in the surviving host-genome component
- ★ `detect_folds.py` — Structure-based detection of surviving folds
- ★ `detect_profiles.py` — Profile-search the surviving corpora and write the per-family hit tables
- ★ `detect_proviruses.py` — Detect integrated elements in the surviving bacterial genomes
- ★ `detect_segmented.py` — Search Evo 1's surviving component for the segmented-genome families
- ★ `detected_families.py` — Build the declared detected-family lists A4.5 restricts its background table to
- `fold_throughput.py` — Measure 3Di prediction throughput, on CPU and on GPU
- ★ `marker_throughput.py` — Price a marker-profile pass over Evo 1's surviving viral component
- ★ `sweep_problem_taxa.py` — Sweep the §A2 known-problem taxa across every A1.4 manifest

## Quantification — the headline numbers

`../metrics/survival.md` defines these; `recount.py` is the independent second implementation
and shares no code with the first.

- `diversity_bins.py` — Build M3's diversity denominator from Pfam's seed alignment
- ★ `equal_rate_pair.py` — Compare the two registries at the sampling rate they share
- ★ `extract_matched_regions.py` — Per-region match statistics for a named record set and a named profile set
- `place_detections.py` — Place the surviving detections into M3's diversity bins
- ★ `quantify_survival.py` — Merge the A2 detection tables into the headline survival quantification
- ★ `recount.py` — A3.3 — recompute Phase A's headline counts by the second method and compare

## The taxonomy ceiling

What taxonomy has not labelled, and what that puts a ceiling on.

- ★ `family_background.py` — Measure the pinned viral families' occurrence outside viruses
- ★ `scope_map.py` — Map filter scope against corpus composition
- `taxonomy_benchmark.py` — A4.2 — benchmark geNomad's taxonomic misassignment against ratified taxonomy
- ★ `taxonomy_catalogues.py` — A4.4 — can the imported taxonomy catalogues the denylist depends on be benchmarked at all?
- ★ `taxonomy_dependency.py` — A4.2 step 1 — which taxonomy assignment tool the filter actually depends on, and how much
- ★ `unfilterable.py` — Measure what taxonomy has not labelled, and the ceiling that puts on the filter

## Conformance — did the filter do what its authors said?

Re-executing the published rules against the released corpora, in both directions, and auditing
the releases against each other. Each pass is split into an expensive half that decides nothing
and a cheap half that decides everything.

- ★ `conformance_close.py` — Close A7.2's conformance gaps: both directions, both Evo releases, all three readings
- ★ `conformance_diff.py` — Compute A7.1's conformance diff from a scan artefact, and write it up
- ★ `conformance_scan.py` — Scan a released Evo corpus for the fields A7.1's conformance diff needs
- ★ `evo2_accessions.py` — Inventory the accessions in Evo 2's released IMG/VR component — the join key A7.2 needs
- ★ `evo2_denylist_detail.py` — Which taxa the denylist rules account for in Evo 2's release, for A7.3
- ★ `evo2_duplicates.py` — What the 39,974 repeated accessions in Evo 2's released FASTA are, for A7.3
- ★ `evo2_json_tree.py` — Count Evo 2's viral component in its *other* representation, for A7.3
- ★ `imgvr_conformance_scan.py` — Reduce a staged IMG/VR release to the sufficient statistic A7.2's conformance diff needs
- ★ `opengenome_compare.py` — Compare OpenGenome2's GTDB subtree against OpenGenome v1
- ★ `opengenome_contigs.py` — Enumerate OpenGenome2's GTDB contigs, in region
- ★ `opengenome_reuse.py` — Which genomes OpenGenome2's GTDB subtree holds
- ★ `opengenome_v1_contigs.py` — Enumerate OpenGenome v1's GTDB contigs, by accession alone
- ★ `training_accessions.py` — Produce the accession list for OpenGenome2's *training* representation

## Hazard and denylist naming

Two instruments for one question, deliberately: one reads family names, one reads biology. A
family's name records where its curators built the model, not what a record is, so the rule is
published with the number.

- ★ `denylist_label_records.py` — Which detected Evo 2 records carry a label naming a denylisted group
- ★ `denylist_named_families.py` — Regenerate the table of detected families whose Pfam name refers to a denylisted group
- `hazard_family_set.py` — Build the hazard family set by database cross-reference — `metrics/costcurve.md` §3
- `hazard_record_membership.py` — Which detected records belong to a hazard family *by biology* — the second instrument
- `select_agent_decomposition.py` — Decompose A1.8's UniProtKB release count into the two halves the source publishes
- `select_agent_seeds.py` — Build ESM3-open's select-agent denylist seed set from a staged UniRef tier
- `uniprot_denylist_count.py` — Execute ESM3's stated select-agent denylist procedure against UniProtKB, and pin the count
- `uniprot_release_count.py` — Execute ESM3's stated select-agent procedure against UniProtKB at the release it names

## Decay and cross-filter agreement

Does a denylist keep working, and do two labs mean the same thing by "viral"?

- `agreement_report.py` — Put A8.1's two tiers side by side — DESIGN.md §A8
- ★ `denylist_decay.py` — Replay the frozen denylist against successive taxonomy releases
- `filter_agreement.py` — Apply both filters' predicates to one corpus and cross-tabulate

## The protein-model arm

ESM3-open's filter is similarity-based rather than label-based, so re-executing it needs the
denylists it queries against, neither of which is published. This arm is staged and priced; it
publishes no figure yet.

- `esm3_calibrate.py` — Price ESM3-open's alignment pass by measuring it in region
- `esm3_composition.py` — Emit ESM3-open's stated corpus composition, and what reconciles against it
- `esm3_seeds.py` — Build ESM3-open's viral denylist seed set from a staged UniRef tier
- `exposure_report.py` — Join the exposure pass to band 1 and report the two-tier curve
- `seed_exclusivity.py` — Measure how much of the viral seed set has cellular homologues

## Phase B — capability

The scoring harness, the parameter-free baseline that separates "the assay is hard" from "this
model was filtered", and the homology axis. Contracts in `../metrics/homology.md` and
`../metrics/depth.md`.

- `assay_depth.py` — Compute B3.4's alignment-depth covariate for every assay target
- `baseline_knob_probe.py` — Sample the baseline's sequence-filtering knobs on one assay, as a diagnostic
- `baseline_reference_audit.py` — Explain the baseline's disagreement with the published column
- `baseline_scores.py` — B4.1 — score every in-scope assay with the parameter-free baseline
- `control_set.py` — Assemble B2.3's within-study positive-control assay set, and test its premise
- `homology_pass.py` — Search the §B3 homology axis against one release's surviving records
- `homology_rows.py` — Assemble the §B3 homology axis into `metrics/homology.md` rows
- `homology_structures.py` — The structural side of §B3's homology axis
- `homology_targets.py` — Build the target side of §B3's homology axis — tasks B3.1 and B3.2
- `proteingym_check.py` — Reproduce the benchmark's published per-assay numbers
- `score_variants.py` — Score one assay's variants through the B1.2 harness
- `scoring_summary.py` — Collect B1.2's per-checkpoint score artefacts into one reference-check table

## In-region launchers

A thin launcher for a named tool in the list above, because a full pass over the staged corpora
is free inside us-east-1 and metered out of it. The measurement lives in the tool, not here.
Read `../docs/runbooks/ec2.md` before using any of them.

- `ec2_agreement.py` — Run A8.1's filter-agreement pass in us-east-1 — DESIGN.md §A8
- `ec2_capability.py` — Measure which EC2 instance types this account may launch
- `ec2_count.py` — Run the composition count on an EC2 instance in us-east-1, and report back
- `ec2_detect_census.py` — Run A2.6's census-depth profile search in us-east-1 — DESIGN.md §A2
- `ec2_exclusivity.py` — Run A1.6's clause-(b) exposure pass in us-east-1 — D-158
- `ec2_folds.py` — Launch one GPU instance to measure A2.2's 3Di throughput, then bring it down
- ★ `ec2_opengenome_contigs.py` — Run A7.4's contig enumeration in us-east-1 — DESIGN.md §A7
- ★ `ec2_proviruses.py` — Run A2.4's prophage pass in region, where reading the corpus is free
- `ec2_select_agent_seeds.py` — Run A1.8's select-agent seed pass in-region on EC2
- `ec2_similarity.py` — Run A1.6's alignment calibration in us-east-1, and report back
- `ec2_uniprot_count.py` — Stage UniProtKB 2023_02 and count it by taxon, in-region on EC2

## Repository machinery

- `board.py` — Generate tasks/BOARD.md from the frontmatter of tasks/*.md
- `decisions.py` — Validate `tasks/DECISIONS.md` — the log's identifiers, not its judgement

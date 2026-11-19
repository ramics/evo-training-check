# Results

One row per published figure: what it says, what defines it, what computed it, where the
artefact is, and which task and decision fixed it. Every claim on this page resolves to a stored
artefact.

**Internal until disclosure.** `../AGENTS.md` holds findings inside the project until the
responsible-disclosure task (X3.1) has run. That gate is closed.

Each row cites the task (`A2.1`) and decision (`D-245`) ids it was fixed under.
`../docs/working-record.md` says how to read one: the task cards and the append-only decision log
left the tree on 19 November 2026 and are in git history, with a copy in the project's own files.

Artefacts live in the project's result store, `s3://amazebio-corpora-897641797669/` under
`corpora/results/<task>/`, each beside the `run-*.json` manifest recording its inputs, their
digests, the declared parameters and the commit that produced it. A few are committed instead,
where the file is small and quoted often; those are named by repository path.

Three qualifications apply to everything below, so they are stated once here:

- **Survival counts are lower bounds.** Phase A searched a 0.2% hash sample of Evo 1's
  component and 0.1% of Evo 2's. Searching ten times deeper raised the count and showed no sign
  of a ceiling, so "at least" matters in every sentence that uses one of these numbers. The two
  releases were also searched at rates ten-fold apart: do not compare their counts without
  saying so (D-245, D-246).
- **The two registries are reported separately and never pooled.** The denominator depends on
  where each one draws family boundaries, which is a choice (`../metrics/survival.md` §1).
- **Every hazard figure is Evo 2's.** Evo 1's released records carry no source accession, so
  37,278 of 57,487 hit records resolve to nothing and the question cannot be put to that
  release at all.

---

## 1. What survived the filter

| Figure | Defined by | Produced by | Artefact | Task · decisions |
|---|---|---|---|---|
| **At least 597 of 1,719 viral Pfam families in Evo 1's released component, 812 in Evo 2's** — both routes merged, both lower bounds | `../metrics/survival.md` (M1, M2, frozen before any detection ran) | `../tools/quantify_survival.py` over the A2 detection tables | `corpora/results/a3-2/headline.json`, `headline.md` | A3.2 · D-245, D-246 |
| Profile route alone: 590 and 811 families | `../metrics/detections.md` | `../tools/detect_profiles.py` | `corpora/results/a2-1/` | A2.1 · D-075, D-076 |
| Integrated-element route: 203 and 251 families from 375 and 300 sampled bacterial genomes | `../metrics/detections.md` | `../tools/detect_proviruses.py`, in region via `../tools/ec2_proviruses.py` | `corpora/results/a2-4/` | A2.4 |
| Endogenous-element route: 1,294 of 5,420 Dfam families in Evo 2's eukaryotic component (0.228–0.250%); Evo 1 `not_searched` | `../metrics/eve-detection.md` | `../tools/detect_eve.py`, registry from `../tools/stage_dfam.py` | `corpora/results/a2-3/` (19 objects) | A2.3 · D-182, D-183, D-185, D-186 |
| Structural route contributes nothing, and **the cost of the route is the finding**: 70+ instance-hours against a $30 ceiling; seven tables ship as `not_searched` | `../metrics/detections.md` (the `not_searched` kind) | `../tools/detect_folds.py`, threshold from `../tools/calibrate_folds.py` | `corpora/results/a2-2/` | A2.2 · D-171, D-179, D-180 |
| Deepening tenfold: 470 → 590 and 492 → 811, accumulation still rising | `../metrics/survival.md` | `../tools/detect_profiles.py` at both bands | `corpora/results/a2-1/` | A2.1 · D-245 |
| Equal-rate pair, both registries at the rate they share: 470 of 1,719 against 572 of 13,679 (Evo 1); 492 against 1,456 (Evo 2) | `../metrics/survival.md` | `../tools/equal_rate_pair.py` | `corpora/results/a3-2/` | A3.2 · D-161, D-247 |
| Labels report zero segmented-virus records where sequence recovers markers of five eukaryote-infecting families — 7 of 1,285 families, 57 hits, 0.54% (0.26–1.12%) | `../metrics/detections.md` | `../tools/detect_segmented.py`, `../tools/sweep_problem_taxa.py` | `corpora/results/a2-5/` | A2.5 · D-187, D-190, D-193 |
| Per-hit quality: 82% of matched regions full length against their family's model; the one complete genome scores 737.8 against a threshold of 25.0 | `../metrics/detections.md` | `../tools/extract_matched_regions.py` | `corpora/results/a7-5/regions-denylist-named-family-records-imgvr-pfam-38.2.tsv` | A7.5 |
| **Second implementation agrees**: 334 numbers across 16 groups, every figure identical | `../metrics/survival.md`, written to be reimplementable from that file alone | `../tools/recount.py` (shares no code with `survival.py`) | `corpora/results/a3-3/` | A3.3 · D-215 |

## 2. Why it survived — the metadata ceiling

The two rules that name organisms key on a record's taxonomic family or order, and the source
database fills those fields on very few records. This is the result most likely to apply to
other filters.

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| Family labels present on 6.25% of IMG/VR's 15,677,623 records, order on 8.67%; per-rank table for all eight ranks, two independent implementations agreeing on every one | `../tools/unfilterable.py` | `corpora/results/a4-1/` | A4.1 · D-081, D-082 |
| 2.62% of Evo 1's released component carries a family label; a final rule removes 599,507 records (3.82%) for having no realm or stopping at one of eight high-level taxa | `../tools/scope_map.py`, `../tools/conformance_close.py` | `corpora/results/a4-3/`, `corpora/results/a7-2/` | A4.3, A7.2 |
| Which taxonomy tool the removals actually rest on, and the 13.71% of records where the host-association rule can be evaluated at all | `../tools/taxonomy_dependency.py` | `corpora/results/a4-2/` | A4.2 · D-081 |
| geNomad's misassignment rate by direction, against ratified ICTV taxonomy | `../tools/taxonomy_benchmark.py` | `corpora/results/a4-2/` | A4.2 · D-085, D-086, D-096 |
| The denominator: IMG/VR v4.1 staged from the publisher's primary table and counted against its stated figures | `../tools/stage_imgvr.py`, `../tools/imgvr_composition.py` | `corpora/results/a1-7/` | A1.7 |

## 3. Are the detected families specific to viruses?

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| Of 1,719 families, 1,265 have no curated non-viral occurrence, 212 do, 242 admit no verdict — **85.6% of the 1,477 judgeable are virus-only**; the median shared family appears in one non-viral organism | `../tools/family_background.py` | `../artifacts/a4-5/background-pfam-38.2.json` (committed) | A4.5 · D-250 |
| InterPro at EBI as an independent second instrument, agreeing on all 1,719 | `../tools/family_background.py` | `../artifacts/a4-5/interpro.json` (committed) | A4.5 · D-250 |
| **Weighted by what was detected, the figure drops**: 69.7% virus-only across Evo 1's detections and 77.4% across Evo 2's, because a family with cellular members is easier to find. Evo 1's 597 becomes 310–462, Evo 2's 812 becomes 498–667 | `../tools/detected_families.py` with `../tools/family_background.py` | `../artifacts/a4-5/detected/` (committed) | A4.5 · D-251 |
| Of seven families admitted only because a keyword sits inside a host word, none is detected on Evo 1 and two on Evo 2 — both on plasmid records the filter never claimed to cover | `../tools/family_background.py` | `../artifacts/a4-5/` | A4.5 · D-252 |

## 4. Does the surviving material look hazardous?

No hazard assessment was performed. What can be said rests on labels, and the bounds in the
preamble apply to every row here.

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| All 19,646 detected Evo 2 records join to their source-database entry; **31 carry a family label the policy itself names for removal and 308 a named order**; only 6.47% carry a family label at all | `../tools/denylist_label_records.py` | `corpora/results/x1-9/denylist-named-family-records-imgvr.tsv` | X1.9 · D-261 |
| 41 of 1,719 families carry a Pfam name referring to a denylisted group — 9 detected on Evo 1, all 41 on Evo 2, 173 and 388 hits. The rule is published with the number, because a family's name records where its curators built the model | `../tools/denylist_named_families.py` | `corpora/results/x1-8/denylist-named-families.tsv` | X1.8 · D-261 |
| The same question answered from biology instead of from names: a second instrument that reads no family name | `../tools/hazard_record_membership.py`, family set from `../tools/hazard_family_set.py` | `corpora/results/c5-1/` | C5.1 · D-261 |
| No detected record names a regulated select agent, against the list as codified 2024-06-01 | `../tools/policies.py`, `../tools/specs.py` over `../policies/specs/select-agents-2024-06-01.json` | validated in CI | A4.6 · X1.4 |

A worked example, one record end to end, is in `../docs/phase-a-worked-example-papillomavirus.md`.
Record identifiers, accessions, coordinates and alignments are not committed here. They stay in
the project's own files.

## 5. Did the filter do what its authors said?

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| Re-executing the published predicates against the released corpora: 95 of 2,653,047 Evo 1 records non-conformant, all through one clause | `../tools/conformance_scan.py` then `../tools/conformance_diff.py` | `corpora/results/a7-1/scan-opengenome-stage2.json` | A7.1 |
| Evo 2's released component carries 264,570 records the adopted procedure removes, split by rule | `../tools/imgvr_conformance_scan.py`, `../tools/conformance_close.py`, `../tools/evo2_denylist_detail.py` | `corpora/results/a7-2/` | A7.2, A7.3 |
| **The filter cannot be checked against the artefact it produced**: the training-format copy matches the filtered output exactly, while the only copy carrying source accessions holds 304,448 more records; 39,974 repeated accessions | `../tools/evo2_json_tree.py`, `../tools/evo2_duplicates.py`, `../tools/training_accessions.py` | `corpora/results/a7-3/`, `corpora/results/a7-6/` | A7.3, A7.6 · see `../docs/evo2-two-representations.md` |
| Evo 2's reuse of OpenGenome v1, checked by enumerating contigs on both sides | `../tools/opengenome_contigs.py`, `../tools/opengenome_v1_contigs.py`, `../tools/opengenome_compare.py` | `corpora/results/a7-4/` | A7.4 · D-213 |
| The three readings of each published rule — literal, charitable, strict — agree exactly, which makes the spread a finding in itself | `../tools/reading_spread.py`, specs validated by `../tools/specs.py` | `corpora/results/a0-4/` | A0.4 · D-221 |
| Two labs' filters compared on one corpus: where "viral" means the same thing and where it does not | `../tools/filter_agreement.py`, `../tools/agreement_report.py` | `corpora/results/a8-1/` | A8.1 |

## 6. Does a denylist keep working?

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| Reach of the 31 names fell from 75.83% to 65.17% of viral taxonomy, **−4.34% a year**; 3 of 31 no longer resolve; 44,261 taxa (15.18%) are new material unreachable through merge records | `../tools/denylist_decay.py` over 28 quarterly taxonomy dumps | `corpora/results/a9-1/` | A9.1 · D-199, D-201, D-202 |
| Whether the imported catalogues the denylist depends on can be benchmarked at all | `../tools/taxonomy_catalogues.py` | `corpora/results/a4-4/` | A4.4 |

Churn and new diversity are reported separately and never summed: 787 renames, 890 renumberings
and 7,723 re-ranks are a different thing from 44,261 taxa that no merge record reaches. Following
a synonym can also change what a rule means. Where a rule cannot execute at all, it is fixed and
the fix declared. Where it executes and gets the wrong answer, it is reported as it stands.

## 7. Phase B — does surviving capability track homology?

Phase B's instruments are built and validated; the analysis is pre-registered and not yet run
(B5.1 is the gate).

| Figure | Produced by | Artefact | Task · decisions |
|---|---|---|---|
| The scoring harness reproduces the benchmark's published numbers on 27 of 27 comparisons, lowest 0.9957, 36 runs bitwise reproducible | `../tools/score_variants.py`, `../tools/scoring_summary.py` | `corpora/results/b1-2/` | B1.2 · D-249 |
| Across all 31 assays: 19 reproduce at or above the 0.99 floor, 3 on it, 9 below | `../tools/baseline_scores.py` | `corpora/results/b4-1/` | B4.1 |
| **The nine disagreements are not our implementation**: the two sides disagree about what the alignment contains, in one direction only. Deliberately not tuned | `../tools/baseline_reference_audit.py`, `../tools/baseline_knob_probe.py` | `corpora/results/b4-2/` | B4.2 · D-248 |
| Benchmark contamination: 19 of 31 assay targets have a sequence-profile homologue in Evo 2's surviving records and 10 in Evo 1's; of 71 annotated domain families, 62 and 12 | `../metrics/homology.md`; `../tools/homology_targets.py`, `../tools/homology_pass.py`, `../tools/homology_rows.py` | `corpora/results/b3-pass/`, `b3-homology/` | B3.1, B3.2 |
| The alignment-depth covariate, so "viral proteins are hard" and "viral proteins were excluded" stay separable | `../metrics/depth.md`; `../tools/assay_depth.py` | `corpora/results/b3-4/` | B3.4 |
| Assay provenance and licences, one traceable entry per assay | `../tools/assay_register.py`, `../tools/assay_licences.py` | `../assays/register.json` (committed), validated in CI | B2.4 |

## 8. What was measured and not bought

Each of these was measured and costed before it was declined, and the price is part of what the
project has to report.

| Limitation | What it would take | Recorded in |
|---|---|---|
| Census-depth search of both corpora | ~3,000 core-hours, tens of dollars at spot; the sampling design was pre-registered | A2.6, `../docs/a2-6-census-runbook.md` · D-098 |
| Structural detection at the pre-registered depth | 70+ instance-hours, $55–60 on demand against a $30 ceiling | A2.2 · D-179, D-180 |
| Equal-depth search of the protein registry | declined on reasoning, not cost: both registries were already searched at matched per-release rates | `/mnt/project-files/decisions/rvdb-prot-depth-tradeoffs.md` · D-236 |
| A sequence-level structural pass for Phase B's homology axis | declined for good; the sequence measure stays secondary | B3.3 |

The retracted figure, for anyone reading old notes: an early estimate of 40,000 core-hours for a
census understated throughput by about three orders of magnitude and must not be reused (D-098).

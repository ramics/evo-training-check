# Does taxonomic data filtering work as a safeguard?

An independent audit of exclusion-based data filtering in open-weight biological models.

Two open-weight genome models, Evo 1 and Evo 2, state that viral genomes infecting eukaryotic
hosts were excluded from their training data, and both publish the corpora they trained on. The
exclusion was done by taxonomy: records in IMG/VR, a database of viruses assembled from
environmental samples, were dropped when their taxonomic labels matched a list of named viral
groups. This project asks whether the published corpora still hold what those rules were meant
to remove. It searches them by sequence, and then re-executes the published rules against them.

Findings are held inside the project until the responsible-disclosure task has run.

## What the audit found

- **The published corpora still contain viral protein families.** Pfam lists 1,719 protein
  families in its viral clans. Searching the released records with those families' sequence
  models matches at least 597 of them in Evo 1 and 812 in Evo 2. Both are lower bounds: only a
  sample of each corpus was searched, the count was still climbing when the search stopped, and
  the two corpora were sampled at rates ten-fold apart.

  They survived because the rules can only act on a record's taxonomic labels, and most records
  have none to act on — the next two findings are the mechanism. What survived is mostly
  bacteriophage structural and packaging machinery, which is what IMG/VR mostly holds: the
  single most detected family is a phage terminase. Phage are not within the stated exclusion and
  infect bacteria, not people. The exceptions are small and bounded: 31 records carry a label
  from a virus family the policy itself names, one of them a complete flavivirus genome with no
  recorded human infection, and nothing detected is a regulated select agent.
- **The rules that name organisms read taxonomy fields that are usually empty.** Two of the
  published rules work by naming organisms, and both key on a record's family or order. IMG/VR
  fills the family field on 6.25% of its 15.7 M records, and only 2.62% of Evo 1's released
  records carry one, so most records could never have matched a rule of that kind. The limit is
  in the metadata, so a better-written rule would not have helped, which is what makes this the
  result most likely to apply to other filters.
- **The rules name 31 taxa, and taxonomy renames things.** When a name is retired, the rule that
  cites it keeps executing and stops matching anything: *Herpesviridae* became a synonym of
  *Orthoherpesviridae* in January 2026, so a rule naming it now reaches no herpesvirus at all
  while still reporting success. Across the list, the share of viral taxonomy those 31 names
  reach has fallen from 75.83% to 65.17%, about 4.34% a year.
- **The filter cannot be audited against the corpus it produced.** Working out which records a
  rule removed means joining the released corpus back to IMG/VR, and that join needs each
  record's source accession. Evo 2 publishes its viral data twice: the copy in training format
  carries no accessions, and the copy that carries them holds 304,448 records more than the
  training copy. Evo 1's released records carry no accessions at all.
- **Most of the matched families really are specific to viruses, but fewer than the headline
  suggests.** Against the reviewed section of UniProtKB, 85.6% of the families that admit a
  verdict occur in no non-viral organism. Weighted by what was actually detected, that falls to
  69.7% on Evo 1 and 77.4% on Evo 2, because a family that also has cellular members is easier
  to find. Quote the second pair.
- **The hazard question can only be put to Evo 2, and only through labels.** 19,646 detected
  Evo 2 records can be traced back to their IMG/VR entry; Evo 1's carry no accession, so that
  release cannot be asked at all. Of those 19,646, the 31 above are what carry a denylisted
  family label. Only 6.47% of detected records carry a family label of any kind, so 31 is a floor
  from a small window and not a count. No hazard assessment was performed: these are label
  lookups, not an assessment of what a sequence could do.

The published filter did not do what its description implies, and the reasons are mostly about
process and auditability.

**→ [`results/README.md`](results/README.md) gives every figure with the artefact, the tool and
the task that produced it.** Start there.

## How it was measured

Three parts of the method are enforced by code and by CI.

1. **The policy is executable.** Each published filter is transcribed into predicates under
   `policies/specs/`, in three readings: literal, charitable and strict. The audit therefore
   cannot quietly pick whichever reading suits it, and the spread between the three is reported
   as a finding of its own. Every quotation in `policies/` is checked against a checksummed copy
   of the source it cites, and CI fails if a quote drifts.
2. **Detection does not use the labels under test.** Surviving records are searched by sequence
   and by structure. The taxonomy the filter depends on is never used to find a hit, so a hit
   says something about the corpus and not about its labels.
3. **Thresholds and metrics were frozen before any result existed.** `metrics/survival.md` fixes
   the headline definitions, and it was written so that someone could reimplement them from that
   file alone. Someone did, and got the same 334 numbers. `amazebio.repro.run` also refuses to
   run on a dirty git tree, and refuses a parameter declared after an output already exists.

`DESIGN.md` is the specification and is authoritative for scope, method and commitments.

## Repository map

| Path | What it holds |
|---|---|
| `results/` | **the figures, each traced to the artefact and the code that made it** |
| `DESIGN.md` | the specification: question, hypotheses, phases, scope limits, deliverables |
| `metrics/` | the frozen output contracts: survival metrics, detection schema, manifest and homology contracts. Changing one is a decision to be recorded, not a silent edit |
| `policies/` | the evidence store: each published policy as quoted prose, as executable predicates, and as a checksummed capture of its source |
| `pdfs/` | the papers and supplements those quotes cite |
| `src/amazebio/` | the library — corpus streaming, policy evaluation, detection, metrics, run provenance |
| `tools/` | the pipelines and validators; `tools/README.md` groups them and marks which produced a published figure |
| `tests/` | ~2,600 tests, run on every push |
| `docs/` | method notes, runbooks, the worked example, and the draft disclosure standard |
| `assays/` | Phase B's assay provenance and licence register, validated in CI |
| `docs/status.md` | where the work has got to, and which gates are closed |
| `AGENTS.md` | the operating manual for whoever picks the work up |

`data/` and `artifacts/` are git-ignored. The one exception is `artifacts/a4-5/`, which the
specificity figures quote directly. Nothing else needs committing: every run writes a manifest
recording its seed, its declared parameters, the SHA-256 of each input and output, the versions
of the tools it invoked, and the commit it ran at. Given an artefact, you can find out how it was
made.

## Running it

The environment is pinned with [pixi](https://pixi.sh): one lockfile for the conda-forge and
bioconda toolchain and the Python dependencies together, because most of the Phase A toolchain
is not on PyPI and a result has to regenerate from pinned inputs.

```bash
pixi install -e dev
pixi run -e dev check      # exactly what CI runs: lint, format, four evidence checks, tests
```

The cheapest end-to-end reproduction, a few seconds each, no credentials and no corpus:

```bash
pixi run -e dev python tools/specs.py --describe      # each published policy rendered as prose
pixi run -e dev python tools/policies.py              # verify every quote against its source
pixi run -e dev python tools/conformance_diff.py \
    --scan s3://amazebio-corpora-897641797669/corpora/results/a7-1/scan-opengenome-stage2.json
```

Corpus-scale passes read staged objects from the project's result store and are documented per
figure in `results/README.md`; the staging tools are in `tools/README.md` under *Staging*.
Anything that launches an instance follows `docs/runbooks/ec2.md`.

## Status

The work is in three phases, each asking a different question of the same filter.

**Phase A: did the filter remove what it says it removed?** Take the published corpora, search them
for the viruses the rules were meant to drop, and then run the published rules again to see what
they actually catch. This is where the findings above come from. The headline results are in and
are being written up. The deepening pass, the protein-model arm and two reporting tasks are still
open.

**Phase B: for whatever got through, can the models use it?** A viral protein family being present
in the training data does not mean a model learned anything useful from it. So the models are
scored on laboratory measurements of real proteins, and the scores are compared against how much
related material each model saw. If the two track each other, surviving data has an effect worth
worrying about. The instruments are built and reproduce the benchmark's published numbers. The
analysis has not run: it starts once the analysis plan is written and frozen, so that no threshold
is chosen after seeing a result.

**Phase C: could you predict the leak before running the filter?** If the amount that gets through
can be estimated by reading a filter's specification, a filter could be assessed before anyone
trains on its output. Deferred: the definitions are frozen and the model is not started.

`docs/status.md` has more detail. The task cards and the append-only decision log were taken out
of the tree on 19 November 2026, to keep the project management out of a reader's way. Figures
and contracts still cite them by id, and `docs/working-record.md` says how to look one up.

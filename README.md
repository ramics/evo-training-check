# Does taxonomic data filtering work as a safeguard?

An independent audit of exclusion-based data filtering in open-weight biological models.

Two open-weight genome models, Evo 1 and Evo 2, state that viral genomes infecting eukaryotic hosts were excluded from their training data, and both publish the corpora they trained on. The exclusion was done by taxonomy: records in IMG/VR, a database of viruses assembled from environmental samples, were dropped when their taxonomic labels matched a list of named viral groups. This project asks whether the published corpora still hold what those rules were meant to remove — searching them by sequence, then re-executing the published rules against them.

Findings are held inside the project until the responsible-disclosure task has run.

## What the audit found

**The published corpora still contain viral protein families.** Pfam lists 1,719 families in its viral clans; searching the released records with those families' sequence models matches at least 597 in Evo 1 and 812 in Evo 2. Both are lower bounds — only a sample of each corpus was searched, the count was still climbing when the search stopped, and the two corpora were sampled at rates ten-fold apart.

What survived is mostly bacteriophage structural and packaging machinery, which is what IMG/VR mostly holds; the single most detected family is a phage terminase. Phage fall outside the stated exclusion and infect bacteria rather than people. The exceptions are small and bounded: 31 records carry a label from a virus family the policy itself names, one of them a complete flavivirus genome with no recorded human infection, and nothing detected is a regulated select agent.

The mechanism is where the result generalises:

- **The rules that name organisms read taxonomy fields that are usually empty.** Both such published rules key on a record's family or order. IMG/VR fills the family field on 6.25% of its 15.7 M records, and only 2.62% of Evo 1's released records carry one, so most records could never have matched a rule of that kind. The limit sits in the metadata, so a better-written rule would not have helped — which makes this the finding most likely to apply to other filters.
- **The rules name 31 taxa, and taxonomy renames things.** When a name is retired the rule citing it keeps executing and stops matching anything: *Herpesviridae* became a synonym of *Orthoherpesviridae* in January 2026, so a rule naming it now reaches no herpesvirus at all while still reporting success. Across the list, the share of viral taxonomy those 31 names reach has fallen from 75.83% to 65.17%, about 4.34% a year.
- **The filter cannot be audited against the corpus it produced.** Working out which records a rule removed means joining the released corpus back to IMG/VR, and that join needs each record's source accession. Evo 2 publishes its viral data twice: the training-format copy carries no accessions, and the copy that carries them holds 304,448 records more. Evo 1's released records carry no accessions at all.

Two qualifications on the headline, both of which should be quoted with it:

- **Most matched families really are virus-specific, though fewer than the headline suggests.** Against the reviewed section of UniProtKB, 85.6% of the families that admit a verdict occur in no non-viral organism. Weighted by what was actually detected that falls to 69.7% on Evo 1 and 77.4% on Evo 2, because a family with cellular members is easier to find. Quote the second pair.
- **The hazard question can only be put to Evo 2, and only through labels.** 19,646 detected Evo 2 records trace back to their IMG/VR entry; Evo 1's carry no accession, so that release cannot be asked. Of those 19,646, the 31 above are what carry a denylisted family label — and only 6.47% of detected records carry a family label of any kind, so 31 is a floor from a small window rather than a count. No hazard assessment was performed: these are label lookups.

The published filter did not do what its description implies, and the reasons are mostly about process and auditability.

**→ [`results/README.md`](results/README.md) gives every figure with the artefact, the tool and the task that produced it.** Start there.

## How it was measured

Three parts of the method are enforced by code and by CI.

1. **The policy is executable.** Each published filter is transcribed into predicates under `policies/specs/` in three readings — literal, charitable and strict — so the audit cannot quietly pick whichever suits it, and the spread between them is reported as a finding of its own. Every quotation in `policies/` is checked against a checksummed copy of the source it cites, and CI fails if a quote drifts.
2. **Detection avoids the labels under test.** Surviving records are searched by sequence and by structure, so a hit says something about the corpus rather than about its labels.
3. **Thresholds and metrics were frozen before any result existed.** `metrics/survival.md` fixes the headline definitions, written so that someone could reimplement them from that file alone. Someone did, and got the same 334 numbers. `amazebio.repro.run` also refuses a dirty git tree, and refuses a parameter declared after an output exists.

`DESIGN.md` is the specification and is authoritative for scope, method and commitments.

## Status

Three phases, each asking a different question of the same filter.

| Phase | Question | Where it stands |
|---|---|---|
| **A** | Did the filter remove what it says it removed? | Headline results in and being written up. The deepening pass, the protein-model arm and two reporting tasks are open. |
| **B** | For whatever got through, can the models use it? | Instruments built and reproducing the benchmark's published numbers. Analysis starts once the plan is written and frozen, so that no threshold is chosen after seeing a result. |
| **C** | Could you predict the leak from the filter's spec alone? | Definitions frozen, model not started. |

Phase B scores the models on laboratory measurements of real proteins and compares those scores against how much related material each model saw: if the two track each other, surviving data has an effect worth worrying about. `docs/status.md` has the detail.

## Repository map

| Path | What it holds |
|---|---|
| `results/` | **the figures, each traced to the artefact and the code that made it** |
| `DESIGN.md` | the specification: question, hypotheses, phases, scope limits, deliverables |
| `metrics/` | the frozen output contracts. Changing one is a decision to be recorded |
| `policies/` | each published policy as quoted prose, executable predicates, and a checksummed capture of its source |
| `src/amazebio/` | corpus streaming, policy evaluation, detection, metrics, run provenance |
| `tools/` | the pipelines and validators; `tools/README.md` marks which produced a published figure |
| `tests/` | ~2,600 tests, run on every push |
| `assays/`, `docs/`, `pdfs/` | Phase B provenance, method notes and runbooks, the cited papers |
| `AGENTS.md` | the operating manual for whoever picks the work up |

Every run writes a manifest recording its seed, declared parameters, the SHA-256 of each input and output, the tool versions it invoked, and the commit it ran at. Given an artefact, you can find out how it was made.

## Running it

The environment is pinned with [pixi](https://pixi.sh): one lockfile for the conda-forge and bioconda toolchain and the Python dependencies together, since most of the Phase A toolchain is absent from PyPI and a result has to regenerate from pinned inputs.

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

Corpus-scale passes read staged objects from the project's result store and are documented per figure in `results/README.md`. Anything that launches an instance follows `docs/runbooks/ec2.md`.

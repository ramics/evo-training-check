# Does taxonomic data filtering work as a safeguard?

An independent audit of exclusion-based data filtering in open-weight biological models.

Two open-weight genome models, Evo 1 and Evo 2, state that viral genomes infecting eukaryotic
hosts were excluded from their training data, and publish those corpora. This project asks
whether the released artefacts contain what the filter says it removed, by searching them by
sequence and then re-executing the published policy against them.

Findings are held inside the project until the responsible-disclosure task has run.

## What the audit found

- **Profile search finds at least 597 of 1,719 viral protein families in Evo 1's released
  component and 812 in Evo 2's.** Both are lower bounds from a 1–2% sample whose accumulation
  curve is still rising, and the two releases were searched at rates differing tenfold.
- **The two rules that name organisms read ranks the source database mostly leaves empty.**
  Family labels are present on 6.25% of IMG/VR's 15.7 M records, and on 2.62% of Evo 1's
  released component. The limit is in the metadata, so writing a better rule would not have
  helped. This is the result most likely to apply to other filters.
- **Names expire.** Reach of the denylist's 31 names fell from 75.83% to 65.17% of viral
  taxonomy, 4.34% a year, and a rule naming *Herpesviridae* now reaches no herpesvirus while
  reporting success.
- **The filter cannot be checked against the artefact it produced.** Evo 2 publishes its viral
  data twice; only the copy that carries source accessions can be joined to the source
  database, and it holds 304,448 records more than the training-format copy.
- **85.6% of the matched families have no curated occurrence outside viruses.** Weighted by what
  was actually detected, that drops to 69.7% on Evo 1 and 77.4% on Evo 2, because families with
  cellular members are easier to find. The lower pair is the one to quote.
- **Of 19,646 detected Evo 2 records, 31 carry a label belonging to a virus family the policy
  itself names for removal**; none names a regulated select agent. No hazard assessment was
  performed and 6.47% of detected records carry a family label at all, so that is a floor over
  a small window.

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

Phase A's headline results are in and are being written up; the deepening pass, the protein-model
arm and two reporting tasks are still open. Phase B's instruments are built and validated, with
the analysis pre-registration as the next gate. Phase C is deferred.
`docs/status.md` has more detail. The task cards and the append-only decision log were taken out
of the tree on 19 November 2026 to keep the project management out of a reader's way; figures and
contracts still cite them by id, and `docs/working-record.md` says how to look one up.

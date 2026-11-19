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
- **The two rules that name organisms read ranks the source database mostly leaves empty** —
  family labels are present on 6.25% of IMG/VR's 15.7 M records, and on 2.62% of Evo 1's
  released component. This is the most transferable result: the ceiling is in the metadata,
  not in the rule.
- **Names expire.** Reach of the denylist's 31 names fell from 75.83% to 65.17% of viral
  taxonomy, 4.34% a year, and a rule naming *Herpesviridae* now reaches no herpesvirus while
  reporting success.
- **The filter cannot be checked against the artefact it produced.** Evo 2 publishes its viral
  data twice; only the copy that carries source accessions can be joined to the source
  database, and it holds 304,448 records more than the training-format copy.
- **85.6% of the matched families have no curated occurrence outside viruses** — but weighted by
  what was actually detected that falls to 69.7% and 77.4%, because families with cellular
  members are easier to find. The figure that runs against the finding is reported with it.
- **Of 19,646 detected Evo 2 records, 31 carry a label belonging to a virus family the policy
  itself names for removal**; none names a regulated select agent. No hazard assessment was
  performed and 6.47% of detected records carry a family label at all, so that is a floor over
  a small window.

The finding is about process and auditability: the published filter did not do what its
description implies.

**→ [`results/README.md`](results/README.md) gives every figure with the artefact, the tool and
the task that produced it.** Start there.

## How it was measured

Three commitments do the work, and they are enforced rather than described.

1. **The policy is executable.** Each published filter is transcribed into predicates under
   `policies/specs/`, in three readings — literal, charitable and strict — so the audit cannot
   quietly pick the reading that favours it. The spread between readings is reported as a
   result. Every quotation in `policies/` is machine-verified against a checksummed capture of
   the source it cites; CI fails if a quote drifts.
2. **Detection is independent of the labels under test.** Surviving records are searched by
   sequence and structure, never by the taxonomy the filter relies on, which is what makes a
   hit evidence rather than a restatement.
3. **Thresholds and metrics are frozen before results exist.** `metrics/survival.md` fixes the
   headline definitions and was written to be reimplementable from itself alone, because a
   second implementation then has to reproduce the numbers without reading the first. It did:
   334 numbers, all identical. `amazebio.repro.run` refuses to run on a dirty tree and refuses
   a parameter declared after an output exists.

`DESIGN.md` is the specification and is authoritative for scope, method and commitments.

## Repository map

| Path | What it holds |
|---|---|
| `results/` | **the figures, each traced to the artefact and the code that made it** |
| `DESIGN.md` | the specification: question, hypotheses, phases, scope limits, deliverables |
| `metrics/` | the frozen output contracts — survival metrics, detection schema, manifest and homology contracts. A change to one is a logged decision, not an edit |
| `policies/` | the evidence store: each published policy as quoted prose, as executable predicates, and as a checksummed capture of its source |
| `pdfs/` | the papers and supplements those quotes cite |
| `src/amazebio/` | the library — corpus streaming, policy evaluation, detection, metrics, run provenance |
| `tools/` | the pipelines and validators; `tools/README.md` groups them and marks which produced a published figure |
| `tests/` | ~2,600 tests, run on every push |
| `docs/` | method notes, runbooks, the worked example, and the draft disclosure standard |
| `assays/` | Phase B's assay provenance and licence register, validated in CI |
| `docs/status.md` | where the work has got to, and which gates are closed |
| `AGENTS.md` | the operating manual for whoever picks the work up |

`data/` and `artifacts/` are git-ignored, with one deliberate exception (`artifacts/a4-5/`,
which the specificity figures quote). Nothing else needs committing, because every run writes a
manifest recording its seed, declared parameters, the SHA-256 of each input and output, tool
versions and the commit — so what produced an artefact is recoverable from the artefact.

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
`docs/status.md` carries the current state in more detail, and `docs/working-record.md` says how
to resolve the task and decision ids this repository cites — the task cards and the append-only
decision log left the tree on 19 November 2026 so that a reader meets the work rather than the
project management. They are in git history, and nothing that cites them stopped resolving.

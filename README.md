# Does taxonomic data filtering work as a safeguard?

An independent audit of exclusion-based data filtering in open-weight biological models.

Evo 1 and Evo 2 both state that viral genomes infecting eukaryotic hosts were excluded from
training, and both publish the corpora they trained on. The exclusion was done by taxonomy:
records in IMG/VR were dropped when their taxonomic labels matched a list of named viral
groups. This project searches those published corpora by sequence, then re-executes the
published rules against them.

**Findings are held inside the project until the responsible-disclosure task has run.**

## What the audit found

The published filter did not do what its description implies, for reasons that are mostly about
process and auditability.

- **Viral protein families survive in both corpora.** Of the 1,719 families in Pfam's viral
  clans, sequence models match at least 597 in Evo 1 and 812 in Evo 2 — lower bounds, from
  samples, still climbing when the search stopped. Most of it is bacteriophage machinery, which
  falls outside the stated exclusion; 31 records carry a label from a family the policy names,
  and no select agent was detected.
- **The rules that name organisms key on fields that are usually empty.** IMG/VR fills the
  family field on 6.25% of 15.7 M records, and 2.62% of Evo 1's released records carry one, so
  most records could never match. The limit lives in the metadata, which is why this finding is
  the one most likely to generalise to other filters.
- **Taxonomy renames things, and a stale rule reports success.** *Herpesviridae* became a
  synonym of *Orthoherpesviridae* in January 2026, so a rule naming it now reaches no
  herpesvirus while still executing cleanly. Across the 31 named taxa, reach has fallen from
  75.83% to 65.17% of viral taxonomy, roughly 4.34% a year.
- **The filter cannot be audited against the corpus it produced.** That join needs source
  accessions. Evo 2 publishes its viral data twice — the training-format copy carries none, and
  the copy that does holds 304,448 extra records. Evo 1's carry none at all.
- **Specificity is lower than the headline count suggests.** 85.6% of families that admit a
  verdict occur in no non-viral organism; weighted by what was actually detected that falls to
  69.7% (Evo 1) and 77.4% (Evo 2). Quote the second pair.
- **The hazard question reaches Evo 2 only, and only through labels.** 19,646 detected Evo 2
  records trace back to IMG/VR, 31 of them carrying a denylisted family label — a floor from a
  small window, since only 6.47% of detected records carry a family label at all. These are
  label lookups; no hazard assessment was performed.

**→ [`results/README.md`](results/README.md) gives every figure with the artefact, the tool and
the task that produced it.** Start there.

## How it was measured

Three properties are enforced by code and CI.

1. **The policy is executable.** Each published filter is transcribed into predicates under
   `policies/specs/` in three readings — literal, charitable, strict — so the audit cannot
   quietly pick the convenient one, and the spread between them is reported as a finding. Every
   quotation is checked against a checksummed copy of its source; CI fails on drift.
2. **Detection avoids the labels under test.** Surviving records are found by sequence and
   structure, so a hit speaks about the corpus rather than its metadata.
3. **Thresholds were frozen before any result existed.** `metrics/survival.md` fixes the
   headline definitions well enough that someone reimplemented them from that file alone and
   got the same 334 numbers. `amazebio.repro.run` refuses a dirty git tree, and refuses a
   parameter declared after an output exists.

[`DESIGN.md`](DESIGN.md) is authoritative for scope, method and commitments.

## Running it

The toolchain is pinned with [pixi](https://pixi.sh) — one lockfile for conda-forge, bioconda
and Python together, since most of the Phase A toolchain is off PyPI.

```bash
pixi install -e dev
pixi run -e dev check      # what CI runs: lint, format, four evidence checks, tests
```

The cheapest end-to-end reproduction — seconds each, no credentials, no corpus:

```bash
pixi run -e dev python tools/specs.py --describe      # each policy rendered as prose
pixi run -e dev python tools/policies.py              # verify every quote against its source
pixi run -e dev python tools/conformance_diff.py \
    --scan s3://amazebio-corpora-897641797669/corpora/results/a7-1/scan-opengenome-stage2.json
```

Corpus-scale passes read staged objects from the result store, documented per figure in
`results/README.md`; staging tools are in `tools/README.md`. Anything that launches an instance
follows `docs/runbooks/ec2.md`.

## Status

**Phase A — did the filter remove what it says it removed?** Search the published corpora for
what the rules targeted, then re-run the rules to see what they catch. The findings above come
from here. Headlines are in and being written up; the deepening pass, the protein-model arm and
two reporting tasks remain open.

**Phase B — can the models use what got through?** Presence in training data implies nothing
about capability, so the models are scored on laboratory measurements of real proteins and
those scores compared against how much related material each model saw. Instruments reproduce
the benchmark's published numbers; the analysis waits on a frozen analysis plan, so that no
threshold is chosen after seeing a result.

**Phase C — could you predict the leak from the specification alone?** If so, a filter could be
assessed before anyone trains on its output. Definitions frozen, model unstarted.

[`docs/status.md`](docs/status.md) has the detail. Task cards and the decision log left the tree
on 19 November 2026; figures still cite them by id, and `docs/working-record.md` says how to
look one up.

## Repository map

| Path | What it holds |
|---|---|
| `results/` | **the figures, each traced to its artefact and code** |
| `DESIGN.md` | the specification: question, hypotheses, phases, scope limits, deliverables |
| `metrics/` | the frozen output contracts; changing one is a recorded decision |
| `policies/` | each published policy as quoted prose, executable predicates, and a checksummed source capture |
| `src/amazebio/` | the library: corpus streaming, policy evaluation, detection, metrics, provenance |
| `tools/` | pipelines and validators, marked for which produced a published figure |
| `AGENTS.md` | the operating manual for whoever picks this up |

`pdfs/`, `assays/`, `docs/` and `tests/` hold the cited papers, Phase B assay provenance,
method notes and ~2,600 tests. `data/` and `artifacts/` are git-ignored, except
`artifacts/a4-5/`, which the specificity figures quote directly. Every run writes a manifest
with its seed, declared parameters, SHA-256 of each input and output, tool versions and commit,
so any artefact traces back to how it was made.

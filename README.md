# amazebio

An independent audit of exclusion-based data filtering as a safeguard in open-weight
biological models.

- **`DESIGN.md`** — the specification. Authoritative for scope, method and commitments.
- **`AGENTS.md`** — how the work is executed: process, conventions, non-negotiables.
- **`tasks/BOARD.md`** — current status, what is unblocked, which gates are holding.

If you are picking up work, read `AGENTS.md` first.

## Setup

The environment is pinned with [pixi](https://pixi.sh), which locks conda-forge and
bioconda packages alongside the Python dependencies in a single `pixi.lock`. Most of
the Phase A toolchain is distributed via bioconda rather than PyPI, and `AGENTS.md`
requires that a result regenerate from pinned inputs — so the compiled tools have to
be in the same lockfile as everything else, not installed by side-channel instructions.

```bash
# install pixi (see https://pixi.sh for other platforms)
curl -fsSL https://pixi.sh/install.sh | bash

# create the environment from the committed lockfile
pixi install -e dev
```

## Everyday commands

```bash
pixi run board              # regenerate tasks/BOARD.md from task frontmatter
pixi run -e dev check       # everything CI runs: lint, format, task graph, tests
pixi run -e dev test        # tests only
pixi run -e dev board-check # validate the task graph and board freshness
pixi run -e dev fmt         # format
```

Acquiring pinned inputs. Both are idempotent: they skip what is already staged, and `--verify`
re-checksums without downloading.

```bash
python3 tools/stage_proteingym.py           # stage the benchmark DMS release (B2.1, ~1.9 GB)
python3 tools/stage_proteingym.py --verify   # re-checksum what is staged
python3 tools/proteingym_check.py            # reproduce the published per-assay numbers
python3 tools/model_inventory.py --check     # validate the Phase B model inventory (B1.1)
python3 tools/ec2_capability.py --print      # what this account may launch; launches nothing
```

Re-executing a developer's own filter against their own release (A7.1). The scan reads 16.9 GB
of staged Parquet and emits lineage tags and counts only — no genomic sequence — in about two
and a half minutes; the diff then recomputes the headline numbers from that artefact in a
second, from a local path or straight out of the store.

```bash
python3 tools/conformance_scan.py --release opengenome-stage2 --workers 12 --upload-results
python3 tools/conformance_scan.py --release opengenome2-imgvr --max-headers 2000  # cheap probe
python3 tools/conformance_diff.py                                      # from the local scan
python3 tools/conformance_diff.py --scan s3://$BUCKET/corpora/results/a7-1/scan-opengenome-stage2.json
```

Benchmarking the taxonomy assignment tool the filter depends on (A4.2). The first pass reads
IMG/VR's own per-record method field and reports which tool the denylist's removals actually
rest on; the rest build a labelled set from the pinned ICTV taxonomy, run the 2022 geNomad the
release could have used, and score the error by direction.

```bash
python3 tools/taxonomy_dependency.py                  # which tool, over which records (~90 s)
python3 tools/taxonomy_benchmark.py build              # select the evaluation set from the VMR
python3 tools/taxonomy_benchmark.py fetch              # retrieve its sequences from NCBI
pixi run -e genomad genomad annotate \
    data/ictv/evalset.fna artifacts/a4-2/genomad \
    data/genomad/db/genomad_db --threads 4 --splits 8 --cleanup
python3 tools/taxonomy_benchmark.py score              # rates by direction, per family, strata
```

The `genomad` environment is pinned separately and deliberately: geNomad 1.1.0 is the newest
version that could have produced IMG/VR v4's labels, and it needs Python 3.10, numpy 1.23 and
mmseqs2 13 to run at all. `--splits 8` is not tuning — the marker search needs about 24 GB in
one pass and the container has 16. See DECISIONS.md D-085.

`pixi run -e dev check` is what CI runs, so a green local run means a green CI run.

## Layout

```
DESIGN.md             the specification
AGENTS.md             process and conventions — read before working
pixi.toml / pixi.lock the pinned environment
pyproject.toml        package metadata, lint and test config
src/amazebio/         library code
  repro.py            seeding, input pinning, run provenance
  survival.py         the frozen route taxonomy and headline metrics
  models.py           the verified Phase B model inventory (B1.1)
  proteingym.py       the benchmark DMS ingest, schema and metric (B2.1)
  conformance.py      released-tag parsing, policy restriction and the cause taxonomy (A7.1)
  ictv.py             the pinned ICTV Virus Metadata Resource: the benchmark's ground truth
  genomad.py          the tool A4.2 benchmarks: version bound, output parser, scope note
  misassignment.py    taxonomy-tool error by direction, exact intervals, leakage propagation
metrics/survival.md   the frozen survival metric specification (A3.1)
tools/board.py        regenerates tasks/BOARD.md from task frontmatter
tools/stage_proteingym.py  acquires and pins the benchmark DMS release
tools/proteingym_check.py  reproduces the benchmark's published per-assay numbers
tools/conformance_scan.py  scans a released corpus for the fields the conformance diff needs
tools/taxonomy_dependency.py  which taxonomy tool the denylist's removals rest on (A4.2)
tools/taxonomy_benchmark.py   builds the labelled set, scores geNomad's error (A4.2)
tools/conformance_diff.py  re-executes the published predicates against that scan
tasks/                one file per unit of work; BOARD.md is generated
tests/                tests
data/                 pinned inputs (git-ignored)
artifacts/            pipeline outputs and run manifests (git-ignored)
```

## Reproducibility

`data/` and `artifacts/` are git-ignored. Nothing in them is committed, because every
pipeline run writes a `run.json` manifest recording the seed, declared parameters,
SHA-256 of every input and output, invoked tool versions, and the git commit. What was
used is recoverable from the artefact, not from a directory's contents.

Pipelines wrap their work in `amazebio.repro.run`, which refuses to run on a dirty git
tree and refuses to accept a parameter declared after an output exists. Both refusals
implement commitments from `AGENTS.md`: an artefact built from uncommitted code cannot
be regenerated by anyone else, and a threshold chosen after seeing results is not a
pre-registered threshold.

## Status

Pre-Phase-A. See `tasks/BOARD.md` for what is ready to pick up.

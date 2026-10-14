# data/

Pinned inputs: corpora, databases, assay collections. **Git-ignored.**

Nothing here is committed. Each pipeline run records the SHA-256 of every input it
reads in its `run.json` manifest (see `src/amazebio/repro.py`), so what was used is
recoverable from the artefact rather than from this directory's contents.

Acquisition is the job of the task that needs the input — `A1.2` and `A1.3` for the
corpora, `B2.1`–`B2.3` for the assay collections. Each records its version pins and
any proxy substitution in `tasks/DECISIONS.md`, per `AGENTS.md`.

## What is staged, and how to get it back

| Path | Task | Contents |
|---|---|---|
| `proteingym/v1.3/` | B2.1 | the benchmark DMS release: 217 substitution assays, published zero-shot model scores, the assay reference file and the published per-assay leaderboard |

`python3 tools/stage_proteingym.py` re-acquires the benchmark release and
`--verify` re-checksums it without downloading. The hashes it checks against are in
`src/amazebio/proteingym.py`, because the publisher ships none of its own — so they
attest that the bytes have not changed since acquisition, not that they are the bytes
released. See DECISIONS.md.

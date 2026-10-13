# data/

Pinned inputs: corpora, databases, assay collections. **Git-ignored.**

Nothing here is committed. Each pipeline run records the SHA-256 of every input it
reads in its `run.json` manifest (see `src/amazebio/repro.py`), so what was used is
recoverable from the artefact rather than from this directory's contents.

Acquisition is the job of the task that needs the input — `A1.2` and `A1.3` for the
corpora, `B2.1`–`B2.3` for the assay collections. Each records its version pins and
any proxy substitution in `tasks/DECISIONS.md`, per `AGENTS.md`.

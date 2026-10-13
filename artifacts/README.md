# artifacts/

Pipeline outputs: result tables, intermediate indices, figures. **Git-ignored.**

Every run writes a `run.json` manifest alongside its outputs recording the seed,
declared parameters, input and output checksums, invoked tool versions and the git
commit. `AGENTS.md` requires that every number in a write-up trace to an artefact
here, and that the artefact regenerate from pinned inputs.

Regenerate rather than archive. If an artefact cannot be regenerated, that is a
defect in the pipeline, not a reason to commit the file.

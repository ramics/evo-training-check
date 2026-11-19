# docs/

Method notes and runbooks. The figures themselves are in `../results/README.md`; these are the
documents a reader needs when a figure's method is the question.

- **`status.md`** — where the work has got to, phase by phase, and which gates are closed.
- **`working-record.md`** — how to resolve a task id (`A2.1`) or a decision id (`D-245`): the
  task cards and the append-only decision log left the tree on 19 November 2026 and are in git
  history, with a copy in the project's own files.
- **`disclosure-standard.md`** — a checklist a model release could be held to if a data filter is
  to be auditable at all, the four models scored against it, and this project's own filter specs
  put in the same format. The generalisable output of the audit, and deliberately written so it
  survives the specific findings.
- **`phase-a-worked-example-papillomavirus.md`** — one record end to end: from the released
  corpus to the source database entry to the label and the matched region, with every step
  resolvable to a published artefact. The fastest way to see what a "detection" is.
- **`evo2-two-representations.md`** — why the filter cannot be checked against the artefact it
  produced: the same viral data published twice, one copy matching the filtered output exactly,
  the other carrying the only source accessions and 304,448 more records.
- **`training-data-membership-test.md`** — the join that decides whether a detected record is in
  the training data rather than merely in a release, and what it can and cannot settle.
- **`hazard-family-set-independent-instrument.md`** — the second instrument for the hazard
  question, which reads biology rather than family names, and why one instrument was not enough.
- **`filter-audit.md`** — the one interface the audit runs behind: a policy, a corpus, a set of
  detectors. What it takes to point it at a filter this project has never seen.
- **`a2-6-census-runbook.md`** — the pre-flight and watch procedure for the census-depth pass,
  written before it was priced and kept because the pass has not been bought.
- **`runbooks/ec2.md`** — the rules for anything that launches an instance: observability,
  teardown, account limits, spot handling, and the pre-launch checklist. Binding.

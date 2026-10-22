---
id: A7.5
title: Extract matched-region metrics for a named record set
phase: A
status: in-progress
gate: false
depends_on: [A2.1]
blocks: []
design_ref: "§A2"
deliverable: null
owner: claude
---

# A7.5 — Extract matched-region metrics for a named record set

**Design reference:** DESIGN.md §A2 · **Deliverable** — none; this is an instrument, and the
figures it produces belong to whichever task asks it a question.

## Goal

A2.1's tables answer *which families are present on which records*. Several later questions —
the hazard check's worked example among them — need the next level down: for a named handful of
records and a named handful of profiles, **how strong is each individual match**. That is four
numbers per matched region: the bit score, the profile's own curated threshold, the region's
percent identity to the model consensus, and how much of the model the region covers.

Three of the four exist inside A2.1's search and are thrown away at the artefact boundary
(D-195, D-103: no sequence, and the per-hit JSONL carries family, record, score, threshold,
route). The fourth, identity to consensus, is not computed anywhere in this repository. So the
measurement is a re-read of named records rather than a query against a stored result — and
A3.4 already established that shape of pass (`tools/place_detections.py`), which is why this
task is an instrument and not a finding.

**What it is not.** It is not a deeper search: the depth pre-registration (D-099) is untouched
because nothing new is sampled. The record set is supplied by the caller, from identifiers that
a published table already carries. It is not a hazard assessment either; it reports alignment
statistics and nothing about what a sequence does.

## Inputs

Two small text files and two pins.

| input | what it is |
|---|---|
| `--records FILE` | one record identifier per line, or a TSV whose first column is the identifier. A leading `record_id` header and `#` comments are skipped, so a published per-record table is passed as it stands. **Use X1.9's `denylisted-label-records-imgvr.tsv`** from `corpora/results/x1-9/`: 314 viral records, derived from pinned inputs with a digest. Not the hand-built 308-row copy under `/mnt/project-files/hazard-check/`, which X1.9 does not reproduce — it predates the rule that settled the family count, and the gap is explained there. |
| `--profiles FILE` | one Pfam accession per line, or a TSV whose first column is the accession. Same header handling, so `/mnt/project-files/hazard-check/denylist-named-families.tsv` (41 rows) is passed as it stands. |
| corpus pin | Evo 2's viral component, `…/fasta/plasmids_phage/imgvr.fasta.gz`, 11,220,266,895 bytes. |
| registry pin | Pfam 38.2 under `data/profiles/pfam/38.2/`: `Pfam-A.hmm.dat.gz` and `Pfam-A.hmm.gz`. |

Neither list is re-derived here. Whoever asks the question owns the selection rule; this tool
owns only what it measures, which is the division A4.5 kept and the reason the denylist name
rule lives beside its own output rather than inside a detector.

**One component per list.** This tool streams one staged object, so a record from another
component — Evo 2's plasmid component shares the detection tables and carries an `IMGPR_` prefix
— would be reported as missing from a corpus it was never in, which looks like a finding about
the corpus and is not one. X1.9 publishes one table per component for exactly this, so the
component is settled by the artefact rather than by a filter written here.

### How the pins are verified

- **The corpus object is resolved, never spelled out.** `corpora.sources_for("opengenome2")`
  narrowed to `component == "IMG/VR"`; the tool refuses if that selection is not exactly one
  source. A literal key in a second place is a second thing to keep in step.
- **The object's size is checked against the pin before a byte is read**, by `head_object`
  against `source.bytes`, with the refusal `tools/detect_profiles.py` already uses: a staged
  object of a different length is a different corpus and nothing measured on it may be reported
  beside A2.1's numbers.
- **Every requested accession must be in the viral selection** `profiles.select_viral_families`
  returns for the pinned `Pfam-A.hmm.dat.gz`. An accession outside it is a refusal naming the
  offenders, not a skip: it means the caller's list and the audit's family universe (D-075)
  disagree, and a silently shortened profile list would read as "no match" for the families
  dropped.
- **Thresholds come from the registry, not the caller.** Pfam's curated gathering cutoff,
  sequence half, exactly as `profilesearch.family_universe` reads it. The tool has no threshold
  flag; a hand-passed threshold is the one way this table could be made to say anything.
- `repro.run` records the pyhmmer and pyrodigal versions, the git commit and the input digests.

## Module layout

### Added

**`src/amazebio/seqstream.py` — `iter_fasta_selected`.** `iter_fasta_sampled` is the right loop
and the wrong selector: membership there is a hash band on the identifier (D-078), and here it
is an explicit set. The shared loop — chunked reads, header parsing, the discard of an unwanted
entry's residues as they stream, the trailing-fragment case — is factored into a private
`_iter_fasta(stream, *, component, keep, chunk)` taking a `keep(record_id) -> bool` predicate.
`iter_fasta_sampled` keeps its signature and its behaviour and delegates; `iter_fasta_selected`
is its sibling, taking `ids: set[str]`. Both yield `SampledRecord`. **Not a change to the
existing signature**: A2.1's and A3.4's calls are what they were, and `tests/test_seqstream.py`
covers the refactor as it stands.

`iter_fasta_selected` adds one thing a band selector cannot have: `stop_when_complete=True`
ends the stream once every requested identifier has been seen. Correctness does not depend on
it — the missing-identifier report is the same either way, since an identifier not seen by the
end of the stream and one not seen before the early stop are only equal when the stop happens
after the last wanted record, which is exactly its condition.

**`src/amazebio/profilesearch.py` — one refactor and one new measurement.**

- `best_domain(hit)` returns the single best-covering included domain. `best_model_coverage`
  and `best_domain_region` are re-expressed over it. They agree today by arithmetic accident —
  both maximise aligned model columns, one divided by a constant — and this makes it structural,
  because the output row here reports coverage, coordinates and identity as properties of *one*
  region and three independent scans is a sentence nobody could check.
- `consensus_identity(domain)` returns the region's identity to the model consensus, defined
  below.
- `search(..., with_identity=False)`. When true, each accepted row gains `identity`, `hmm_from`
  and `hmm_to`. Default off, so A2.1's rows are unchanged byte for byte and the published
  tables' digests cannot move under them (`repro`'s commit-keyed check would catch it, after a
  run rather than before).

**`tools/extract_matched_regions.py`** — the CLI. `tools/place_detections.py` is the structural
template: module docstring carrying the invocation, `build()` returning the document, a
`summarise()` for the `.md`, `main()` wrapping everything in `repro.run` with the inputs
declared as `input_file` and the outputs as `output_file`, refusals as `SystemExit` with the
reason spelled out.

    pixi run -e dev python tools/extract_matched_regions.py \
        --records  /mnt/project-files/hazard-check/denylisted-label-records.tsv \
        --profiles /mnt/project-files/hazard-check/denylist-named-families.tsv \
        --outdir   artifacts/a7-5

Order of work: read and validate both lists → resolve and verify the pins → pre-flight the
write path (below) → stream the object, keeping the listed records only → call genes per chunk
→ search the restricted model set → write the table.

### Reused unchanged

`objectstore.client` (the regional endpoint; a plain boto3 client resolves S3 to the legacy
global hostname, loses the proxy-injected credential and returns a bare `AccessDenied` that
reads as a permissions problem and is not one), `objectstore.durable_results`,
`corpora.sources_for`, `corpora.RangedObject(...).buffered()`, `uniref.GunzipStream`,
`profilesearch.call_genes` (metagenomic mode, D-077, including its count of records whose genes
cannot be called), `profilesearch.family_universe` / `RegistryView` / `hmm_path` / `search`,
`profiles.registry` and `MIN_MODEL_COVERAGE`, `repro.run`.

Records are gene-called and searched in chunks, as `detect_profiles.py` does, so peak memory is
bounded by the chunk and each chunk's progress line is a real heartbeat. At this record count
one chunk is the whole set; the chunking is kept because the tool takes an arbitrary list.

## Percent identity to the model consensus — fixed here, before any row is read

Over the best-covering included domain's alignment, considering every column where the model
consensus line carries a match-state residue (a letter, not the `.` of an insert relative to the
model):

    identity = (columns where the target residue equals the consensus letter, case-folded)
             / (match-state columns)

A gap on the target side counts in the denominator and not the numerator. The comparison is
case-folded because HMMER writes the consensus in upper case at the most conserved positions and
lower case elsewhere, which is an emphasis and not a different residue.

Read from `alignment.hmm_sequence` and `alignment.target_sequence` (pyhmmer 0.12.x; the
implementation asserts both attributes exist rather than discovering their absence mid-pass).
`alignment.identity_sequence` is deliberately not used: it marks positive-scoring substitutions
as well as identities, so it answers a different question.

**What the number is, and is not.** It is identity to a consensus string, which is a summary of
a family's model and not a sequence that exists. It is **not** identity to any member of the
family, and it is not a measure of how closely the record resembles any named organism. Wherever
it appears in prose it travels with that sentence. The bit score against the curated threshold
remains the detection claim; identity and coverage describe the shape of the match.

## Output schema

`artifacts/a7-5/regions-<records-stem>-pfam-38.2.tsv`, header row, one row per matched region
(one profile × one called gene), sorted by `record_id`, `accession`, `gene`:

| column | |
|---|---|
| `accession` | Pfam accession — the family id every survival count is keyed on |
| `profile` | the model's name, which is what a hit comes back under |
| `record_id` | the IMG/VR accession, from the FASTA header's first token |
| `gene` | gene index on the record, as `call_genes` names it |
| `score` | bit score of the hit |
| `threshold` | the profile's curated gathering cutoff, sequence half |
| `identity` | as defined above, 4 decimal places |
| `model_coverage` | best-covering domain's share of the model's length |
| `model_length` | the model's match-state count, so coverage is checkable |
| `hmm_from`, `hmm_to` | the region on the model, 1-based inclusive |
| `target_from`, `target_to` | the region on the called protein, 1-based inclusive |

The six columns the question asks for are `accession`, `record_id`, `score`, `threshold`,
`identity`, `model_coverage`; the rest are the context that makes each of them checkable, and
are additive.

Beside it, `regions-<stem>-pfam-38.2.json`: the parameters (pins, digests, `MIN_MODEL_COVERAGE`,
the identity definition as text), records requested / found / missing, records whose genes could
not be called, profiles requested / resolved, rows written, bytes read and whether the stream
stopped early, and a `reading_this_table` paragraph. And `regions-<stem>-pfam-38.2.md`, the
human summary. `run-regions-<stem>.json` is `repro.run`'s manifest.

**No residues anywhere** (D-103). Coordinates are not residues and A2.1 already records them.

**This table is internal.** It carries record identifiers and coordinates, which under the
disclosure posture stay with the project owner; what a write-up may carry is the aggregate and a
worst case named at group level (X3.1).

## The write path

The bucket has no `s3:DeleteObject` but `PutObject` on an existing key succeeds, so
un-rewritable is a property of deletion here and not of the key — D-216, which X1.7 is fixing
generally. This tool does not wait for that fix:

- Outputs go through `repro.run(durable=objectstore.durable_results("a7-5"))`, which writes each
  output to its stable key *and* to the commit-keyed twin under `by-commit/<commit>/`, and
  refuses before uploading anything if this commit already published different bytes for the
  same output.
- That check fires after the pass, which is 40 minutes too late to be the only guard, and it
  cannot see a stable key published by a *different* commit. So the tool **pre-flights the write
  path before it reads anything**: `head_object` on every stable key the run would write, and a
  refusal naming them if any exists. `--replace-durable "<reason>"` is the only way past, and
  the reason is threaded into `repro.run(replace_durable=...)` so it lands in the manifest
  rather than in a shell history. The same rule applies to the local files in `--outdir`.
- The output names carry the `--records` stem, so two different question sets write two
  different keys and neither needs the flag.
- **The pre-flight is a HEAD and never a PUT.** A4.5 left a 6-byte `.write-probe` permanently
  under a results prefix; a bucket that cannot delete is a bucket where a probe is a commitment.

## Steps

- Write `iter_fasta_selected` and the `_iter_fasta` factoring; keep `iter_fasta_sampled`'s
  signature and let the existing tests cover it.
- Write `best_domain`, `consensus_identity`, and `search(..., with_identity=...)`.
- Write the CLI, in the order given above, with the pin checks and the write-path pre-flight
  before the read rather than after it.
- Tests, including the offline fixture below. No test touches object storage or the network.
- Run `python3 tools/board.py --check` and keep this file's frontmatter current.
- Do **not** run the pass without the project owner's yes: it is ~40 minutes of container time
  (below), which is past the few-minutes line, even though it costs nothing.

## Tests — `tests/test_extract_matched_regions.py`

Module loaded by `importlib`, as `tests/test_place_detections.py` loads its tool.

1. **Selection by identifier.** A six-entry in-memory FASTA, three listed: those three come
   back, in file order, with sequence joined across wrapped lines; a header with a trailing
   description keys on its first token only; an identifier not in the stream is reported missing
   rather than dropped.
2. **Early stop.** A counting stream wrapper shows no read past the last wanted record with
   `stop_when_complete=True`, and a read to the end with it off, with the same records out of
   both.
3. **Identity arithmetic**, on a hand-built alignment: consensus and target strings chosen so the
   test pins the case folding, the exclusion of `.` insert columns, and the target gap that
   counts in the denominator only.
4. **One region, three statistics.** A hit stub with two included domains whose best-covering one
   is not the first: coverage, coordinates and identity all come from that one domain.
5. **End to end, offline.** A fixture of three short synthetic records under `tests/data/a7-5/`,
   and a two-model HMM built at test time with `pyhmmer.plan7.Builder` from a short alignment and
   written to `tmp_path` — deterministic, no committed binary, no network. Asserts one row per
   matched region with the six requested columns populated, no column holding residues, a
   requested-but-absent record in `records_missing`, and a requested accession absent from the
   HMM file as a refusal.
6. **The pin check.** A fake client reporting a `ContentLength` other than the pin is a refusal
   before any read.
7. **The write-path pre-flight.** A fake client whose `head_object` finds the stable key makes
   `main` exit non-zero with nothing uploaded; with `--replace-durable` the run proceeds and the
   reason is in the manifest.

## What the pass costs, and the basis for it

| step | basis | this pass |
|---|---|---|
| stream `imgvr.fasta.gz`, 11.22 GB | A2.6's measured ~2 core-hours over the 35 GB of staged components (`/mnt/project-files/a3-4/cost.md`), ≈0.057 core-h/GB | **~38 min, one core, read-bound** |
| gene calling | pyrodigal metagenomic, 1,103 genes/s/core measured; A2.1's density ≈19 genes/record over 308 records ≈ 6,000 genes | ~6 s |
| profile search | A2.1's measured 2.19 ms/gene on this release is against all 1,719 selected models; 41 models is 2.4% of that | under a minute, model loading included |
| **wall clock** | | **~40 minutes** |
| **money** | in-region GET traffic is unmetered; a few thousand requests | **nothing rented, a fraction of a cent** |

A gzip stream offers no index, so the one sequential pass is the floor and a single thread is
the ceiling: the 308 records are 0.0016% of the component, and reading to find them is the whole
cost. The early stop can only shorten it, by an amount nobody can predict from the identifiers,
so it is not counted here; the bytes actually read are recorded.

It must run in `us-east-1`. 11.22 GB is free in-region and metered out of it, which is the test
`AGENTS.md` sets for a pass of this shape.

### Whether the read can be narrowed — asked, and it cannot, today

The forty minutes is one sequential pass over an object with no index, so the question worth
asking before buying it is whether less of it could be read.

- **It is not block-compressed.** The object's gzip header was read — 20 bytes, `head_object`
  plus one ranged GET, no write — and carries `FLG=0x08`: a file name and no extra field, so it
  is plain gzip and not BGZF. A ranged GET into the middle of it cannot be inflated, which is
  what would have made a named-record read cheap.
- **Nothing maps an identifier to an offset.** IMG/VR accessions carry no position, the component
  is one object rather than shards, and A2.1's hit tables record the record id and not where in
  the object it sits.
- **The one real option is to pay this pass once and keep the index.** A zran-style access index
  — the inflate window captured every so often — makes later ranged reads of named records a
  matter of seconds. It is built *during* a pass, so the first pass still costs forty minutes,
  the index is a few megabytes staged beside the object, and it needs a dependency this project
  does not have (`indexed_gzip` or equivalent). It is worth buying only if more passes of this
  shape are coming; for one question it is forty minutes either way.

So: **no cheaper first pass exists.** Whether the second one should be cheap is a decision for
the project owner, and it belongs with the pass, not inside this tool.

## Done when

- `iter_fasta_selected`, `best_domain`, `consensus_identity` and the CLI exist, with the tests
  above green and CI green.
- The identity definition is in the shipped tool's own output, not only in this file.
- The pins are verified in code, with refusals, and demonstrated by test.
- The write path cannot overwrite a published key without a recorded reason, demonstrated by
  test.
- A pass over the hazard check's two lists produces the table, with every requested record
  either carrying rows or named in `records_missing`.
- Frontmatter current and `python3 tools/board.py --check` passes.

## State — 2026-10-22

`in-progress` on branch **`claude/project-thread-ff52l2`**. The design above was written first
and the implementation follows it:

- `amazebio.seqstream.iter_fasta_selected`, with the shared FASTA loop factored behind a
  `keep(record_id)` predicate. `iter_fasta_sampled`'s signature and behaviour are untouched and
  its existing tests cover the refactor.
- `amazebio.profilesearch.best_domain`, `consensus_identity`, and `search(..., with_identity=…)`
  default-off.
- `tools/extract_matched_regions.py`, with the pin checks and the write-path pre-flight before
  the read, and `durable_for` beside it: the pre-flight stops a *replacement*, and a first
  rehearsal reaching a clean prefix is not one. So publication happens only from the canonical
  `artifacts/a7-5`, and `--limit-records` does not publish at all — the two incidents
  `AGENTS.md` records as paid for twice in a bucket with no delete (D-193, then D-224; and the
  probe that reached A2.6's census prefix on 2026-10-20).
- `tests/test_extract_matched_regions.py` and a synthetic fixture under `tests/data/a7-5/`,
  whose profile is built at test time from the protein the fixture record encodes. No object
  storage and no network in any test.

**The corpus pin was verified live**: the staged object is 11,220,266,895 bytes, which is what
the source declares.

**The input list changed under this task while it was being written, and that is the point of
keeping the selection outside the tool.** X1.9 derived the record list from pinned inputs and
does not reproduce the hand-built 308: the nearest derived figure is 314 viral records, with five
plasmid records counted apart. So the pass reads X1.9's published per-component table, and this
file's Inputs section names it. Nothing in the tool changes, because the record set was always an
input.

**The pass has not been run.** It is ~40 minutes of container time and no money, and it waits on
the project owner.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

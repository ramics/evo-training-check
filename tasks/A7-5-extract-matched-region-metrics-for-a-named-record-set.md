---
id: A7.5
title: Extract matched-region metrics for a named record set
phase: A
status: review
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
| `--records FILE` | one record identifier per line, or a TSV whose first column is the identifier. A leading `record_id` header and `#` comments are skipped, so a published per-record table is passed as it stands. **Pass a published per-component table** — X1.9's `denylist-named-family-records-imgvr.tsv` under `corpora/results/x1-9/`, 314 viral records — and not an ad-hoc copy, so the record set carries a digest. Not the hand-built 308-row copy under `/mnt/project-files/hazard-check/`, which X1.9 does not reproduce: it predates the rule that settled the family count, and the gap is explained there. |
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
ends the stream once every requested identifier has been seen. **This tool does not use it, and
the reason is worth keeping.** It was defensible only while nothing a caller could observe
depended on it, which stopped being true when the `entry` column arrived: an accession repeats
in this object with different residues under it, so a pass that stops at the first sighting of
the last accession would report `entries_read`, `records_repeated` and `entries_per_record_max`
over however much of the object it happened to reach — a figure that looks like a census and is
truncated at an arbitrary byte. The saving was never predictable from the identifiers. The
selector keeps the capability for a caller that wants it; the deliverable reads through, and the
`read` parameter in the output says so.

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
        --records  artifacts/x1-9/denylist-named-family-records-imgvr.tsv \
        --profiles artifacts/a7-5-inputs/denylist-named-families.tsv \
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
| `entry` | which occurrence of that accession in the staged object this region sits on. **The released component repeats accessions and the repeats are not identical**, so `record_id` alone is not a key — see the finding below |
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

## A finding the first pass produced: the accession is not a key

The first real pass asked for 314 records and reported **551 found**, which is only possible
because the released component carries **repeated record identifiers**. The repeats are not
copies of one record either: two entries sharing one accession were searched against the same
model at the same gene index and scored **38.0** and **34.4**, with identities 0.275 and 0.200,
so they carry different proteins.

That broke the output contract rather than just the summary line. A row was keyed on
(`record_id`, `accession`, `gene`), and one pair of rows in that first table shares that key
with different numbers in every other column — a reviewer joining on it gets a fan-out, and the
"382 regions on 314 records" is only true if you know which entry each row sits on.

Three changes, all additive:

- an **`entry`** column: the accession's 1-based order of appearance in the object, so the
  unique key is (`record_id`, `entry`, `accession`, `gene`). The entry is tagged as the records
  stream, before their genes are called, and *not* inside `profilesearch.call_genes` — that
  function names A2.1's proteins and its published rows must not move.
- **`entries_read`**, `records_repeated` and `entries_per_record_max` beside `records_found`,
  because reporting the entry count as records found is what produced "551 of 314 requested
  records found".
- `ENTRY_NOTE` in the tool's own output, so a reader of the table meets the warning where the
  table is rather than here.

A7.3 measures repeated accessions in this release as a finding of its own. This task did not set
out to find them and has no business widening to measure them; what it owes is a table that
stays checkable in their presence, and a pointer.

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
| gene calling | pyrodigal metagenomic, 1,103 genes/s/core measured; A2.1's density ≈19 genes/record over ~315 records ≈ 6,000 genes | ~6 s |
| profile search | A2.1's measured 2.19 ms/gene on this release is against all 1,719 selected models; 41 models is 2.4% of that | under a minute, model loading included |
| **wall clock** | | **~40 minutes** |
| **money** | in-region GET traffic is unmetered; a few thousand requests | **nothing rented, a fraction of a cent** |

A gzip stream offers no index, so the one sequential pass is the floor and a single thread is
the ceiling: a few hundred records are a ten-thousandth of a percent of the
component, and reading to find them is the whole cost. The early stop can only shorten it, by an amount nobody can predict from the identifiers,
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

## Result — 2026-10-22

Ran, against X1.9's published record list (314 viral records) and X1.8's published family table
(41 accessions). The table, its document, its summary and `run.json` are at
`corpora/results/a7-5/`.

| | |
|---|---|
| records requested / found / missing | 314 / 314 / **0** |
| FASTA entries those records occupy | **551** — 12 accessions repeat, one of them 44 times |
| genes called | 15,722 |
| matched regions | **382**, on 314 records across all 41 families |
| rows sitting on a repeat entry | 19 |
| bytes read | 11.22 of 11.22 GB in 18.8 min, two reconnects, both resumed in place |

Every requested record carries at least one region, so `records_missing` is empty and the record
list and the corpus agree completely — which is itself worth stating, because the first derived
list mixed in five plasmid records and this one does not.

**The strongest matches are strong.** The top region scores 737.8 against a curated threshold of
25.0, over 99.3% of the model, at 0.616 identity to the model consensus. Identity and bit score
are not interchangeable: the five strongest regions run from 0.460 to 0.616 identity while all
clearing their thresholds by more than an order of magnitude, which is the distinction the
identity definition exists to keep visible.

**Key uniqueness, verified rather than assumed:** 382 rows, 382 distinct
(`record_id`, `entry`, `accession`, `gene`) keys, no collisions. The first pass had one
collision on that key without the `entry` column.

**The region counts did not move.** The first pass and this one both report 382 regions on 314
records across 41 families; the `entry` column is additive and nothing it fixed changed a
measurement. That is the check that the fix was a fix and not a rewrite.

### Two things the published summary says badly

Fixed in the tool, and **not re-run for them**, because the numbers in the table are right and
the prose is what was wrong — another pass is 19 minutes of reading and a second permanent
replacement of the published keys:

- The `.md` at `corpora/results/a7-5/` says "the stream stopped early". True and worth nothing:
  the early stop left **4.7 MB of 11.22 GB** unread, 0.04%, because the last wanted record sits
  almost at the end of the object. The tool now reports the remainder, so the reader can see
  whether the stop bought anything. `bytes_read` in the published document already allows the
  same arithmetic.
- The per-chunk progress line said "551/314 records read", the same entries-as-records
  conflation one level down from the summary. Now "551 entries read for 314/314 requested
  records".

### What the published prefix now holds

This run replaced the first pass's stable keys, with the reason recorded in the manifest
(`--replace-durable`). The first table — the one whose rows share a key — stays readable at its
`by-commit/` twin, which is what D-216's two-key scheme is for and the first time on this branch
that it has been the thing that saved a superseded result rather than an inconvenience.

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
keeping the selection outside the tool.** Two threads regenerated the label arm's per-record
table from pins within the hour, and between them the figures in circulation were 31, 308, 314,
315 and 319. They are **different axes of the same table, and neither set contains the other**:

- *label* axis, what the published rules read on the record's own label — 31 records carry a
  denylisted **family** label, 308 a denylisted **order** label, 24 both, so 315 carry either;
- *name* axis, what the detected Pfam family is **named** for — 319 records, 314 viral and 5
  plasmid.

So the hand-built 308 is reproduced, on the order axis; "308 is superseded by 314" compares two
axes and is not a correction. **Which axis the question is about is the caller's to state**, and
whichever table it names must be the published per-component one. This tool measures the record
set it is handed and asserts nothing about how it was chosen — which is why the selection stayed
outside it. Nothing in the tool changes.

**The pass has not been run.** It is ~40 minutes of container time and no money, and it waits on
the project owner.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

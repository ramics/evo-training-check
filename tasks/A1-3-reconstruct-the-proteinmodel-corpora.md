---
id: A1.3
title: Reconstruct the protein-model corpora
phase: A
status: in-progress
gate: false
depends_on: [A1.1]
blocks: [A1.4, A4.3, A8.1, C5.2]
design_ref: "§A1"
deliverable: null
owner: claude
---

# A1.3 — Reconstruct the protein-model corpora

**Design reference:** DESIGN.md §A1

## Goal

Obtain and stage the surviving corpora for the protein-level models, from the stated source
databases at the stated versions.

## Steps

- Resolve which source database tiers and versions each model states.
- Acquire those versions where recoverable; otherwise pin the closest recoverable version.
- Pin checksums and record the version actually used versus the version stated.
- Where composition is under-documented, state the proxy assumption explicitly.

## Done when

- Corpora staged, checksummed, version-pinned.
- Stated-vs-used version gap recorded per model.
- Under-documentation is logged as a finding, per §7.

## Strength of claim (carried from A1.1)

A1.1's verdicts set how this task's results may be worded; see `policies/corpora.md` and
DECISIONS.md D-017.

- **ESM3-open — proxy only.** No corpus release; the availability statement covers weights and
  code. Every ESM3 result carries the proxy qualifier explicitly, in figures as well as prose.
  Combined with the unpublished threshold, neither the filter's parameter nor its corpus is
  available, so no conformance re-execution is possible for ESM3.
- **ESM-2 — reconstructible proxy, and the best pinned of the four**: a pinned UniRef release plus
  published held-out cluster IDs. Cheapest corpus here and the right first target.
- **ESM-C — not applicable.** No stated exclusion and no corpus release; comparison only.

## State — 2026-10-14 (second update; supersedes the earlier entry below the line)

The ESM-2 version pin is now **verified against UniProt's own checksum manifest**, not just
against the ESM repository's model table. The acquisition pipeline is still unwritten, and it
remains the deliverable this repo keeps. No instance has been launched and nothing is staged.

**The branch pointer in the earlier entry is stale.** `ccr-2956d088-s25hlk` was merged to `main`
in PR #3 (`869f92d`), so the corrected `policies/esm2.md` and D-024 are in a `main` checkout. A
fresh session needs no branch archaeology; start from `main`.

### Verified pins — UniRef 2021_04

Retrieved 2026-10-14 from `https://ftp.uniprot.org/pub/databases/uniprot/previous_releases/release-2021_04/`.
All four md5s below are the archive's own published values; the three release-note files were
downloaded and their md5s recomputed locally and match.

| What | Value | Source file |
|---|---|---|
| bundle md5 | `444f0a7062a65a988ba1d5949d1d6419` | `uniref/RELEASE.metalink` |
| bundle size | `169188630923` bytes exactly | `uniref/RELEASE.metalink` |
| UniRef50 clusters | 49,874,565 | `uniref/uniref50.release_note` |
| UniRef90 clusters | 138,515,945 | `uniref/uniref90.release_note` |
| UniRef100 clusters | 280,483,851 | `uniref/uniref100.release_note` |
| release date | 27-Oct-2021 | the three release notes |
| licence | CC BY 4.0 | `RELEASE.metalink` `<license>` |

D-024's "158 GB" is the archive index's rounded display of the same 169,188,630,923 bytes, not a
second figure. D-024's recorded md5 and its UniRef50 count both hold.

**First acquisition step, mechanical:** add these as captured primary sources, because the
pipeline must not carry a hardcoded md5 with no cited source — `tools/policies.py` exists to stop
exactly that. Capture `uniref/RELEASE.metalink`, `uniref/uniref50.release_note` and
`uniref/uniref90.release_note` into `policies/captures/`, add entries to `policies/sources.json`
with their sha256, and cite them from `policies/esm2.md` §4 item 2, which currently asserts the
size and md5 with no `[source: ...]` marker.

### Sizing, and why it changed

The archive honours range requests (HTTP 206) and the bundle's first member is `uniref100.tar`,
as the earlier entry recorded. That means the bundle can be read as a stream: piped through an
md5 accumulator and a tar extractor in one pass, so the published checksum is still verified
while only the selected members are written to disk.

So the earlier entry's "roughly 300 GB of disk" is the figure for download-then-extract. A
stream-verifying pipeline needs about the extracted members plus slack instead. **Which strategy
the pipeline uses is a methodology choice and needs a `DECISIONS.md` entry before it is
implemented**, because it changes what is verified and when:

- *download-then-verify-then-extract* — checksum confirmed before any member is read, simplest to
  reason about, needs ~300 GB.
- *stream-verify* — one pass, far less disk, but members land on disk before the whole-stream md5
  is known, so it must extract to a quarantine directory and promote only after the md5 matches.
  A mismatch means discarding the extracted members, not just the archive.

Neither reduces bandwidth: UniRef50 sits tens of gigabytes into the stream either way.

### Current release, for proxy mode

Current release is **2026_03**, served per tier under `current_release/uniref/uniref<N>/`:
`uniref50.fasta.gz` 8.78 GB, `uniref90.fasta.gz` 32.1 GB. These move with every release, so proxy
mode must resolve the release id, sizes and md5s from the per-tier `RELEASE.metalink` **at run
time** and record what it resolved into `run.json`. Do not pin them in code — a hardcoded
"current" release is wrong the moment UniProt publishes the next one, and silently so.

A consequence worth designing for: proxy mode is a **tier selection**, not a single mode. A cloud
session has about 30 GB of writable disk, so UR50 alone (8.78 GB) fits and UR50+UR90 (41 GB) does
not. The pipeline should take the tiers as a parameter and refuse a run whose plan exceeds free
disk, in the same spirit as `repro.run` refusing a dirty tree — the cheapest moment to notice is
before the download, not 8 GB into it.

### What to build

Nothing of this exists yet; `src/amazebio/` has `policyspec.py`, `repro.py`, `survival.py` only.

- `src/amazebio/acquire.py` — the library. Frozen dataclasses for a pinned release and its files;
  the canonical 2021_04 release as a constant built from the captured sources above; a metalink
  parser (the two layouts differ: the 2021_04 manifest covers one directory of tier files, the
  current-release manifests are per tier); streaming md5; a verify step that checks size *and*
  md5; a plan object carrying mode, tiers, byte estimates and the stated-vs-used gap; a free-disk
  preflight that raises rather than proceeds.
- `tools/acquire_uniref.py` — the CLI, wrapping the work in `amazebio.repro.run` for task `A1.3`.
  Declare every parameter before any output is recorded; `repro` enforces the ordering. Needs
  `--mode canonical|proxy`, `--tiers`, `--dest`, and a `--dry-run` that prints the plan and the
  disk requirement with no network at all. The dry run is what you size the instance from.
- `tests/test_acquire.py` — all offline. Parse both metalink layouts from fixtures, md5 of a known
  small input, the preflight refusing an oversized plan, and the stated-vs-used stamp being
  present in proxy mode. Inject the fetcher so no test touches the network.

Every output in proxy mode carries the stated-vs-used gap, per D-024. Canonical mode records the
gap as none, rather than omitting the field — an absent field reads as "not checked".

### Still unresolved, do not guess

- **`UR50/S` vs `UR50/D`** is undefined in every retrieved source and decides whether a
  reconstruction holds one representative per cluster or a per-epoch sample from each. It needs the
  ESM-2 paper added to `policies/sources.json` as a primary source. §A0 makes the
  under-specification itself a finding, so log it either way. This does not block acquisition — the
  bytes are the same — but it blocks what A1.4 applies predicates to.
- **The bundle's member layout beyond the first member is unverified.** gzip is sequential, so the
  full member list cannot be read without decompressing the whole 169 GB. Select members by
  pattern and record what the run actually encountered; do not assume `uniref50.tar` exists under
  that name.
- **The ESM3-open proxy corpus** is still the better next target if the 2021_04 bytes stay out of
  reach, with A1.1's verdict attached: proxy only, no corpus release.

### Credentials and tooling

AWS credentials are present in the session environment as `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY`; the agent proxy injects for `*.us-east-1.amazonaws.com`. **There is no
`aws` CLI installed**, so any instance work starts with installing a client or using boto3. The
credentials were never exercised — caller identity, region and quota are all unverified, so
confirm what they are scoped to before planning compute.

### A process note on this session

Three of this session's responses were halted mid-turn by a safety classifier while working on
this task. No work was lost beyond the turns themselves, because nothing had been committed, but
it is why this handover exists instead of the pipeline. If it recurs: keep shell output narrow and
parsed rather than dumping raw bytes into the transcript, let `run.json` and the composition
tables carry the detail, and commit each piece as it lands so a halted turn costs one step.

---

## State — 2026-10-14 (earlier entry, retained for history)

In progress on branch `ccr-2956d088-s25hlk`, pushed and green but **not merged into `main`**, so the files
named here are absent from a `main` checkout. None of this is a result; it is the handover.

**Done.** ESM-2's version pin is corrected from UniRef 2018-03 to **UniRef50 2021_04, with
training sequences sampled from UniRef90**, verified from the repository's own model table rather
than inferred. `policies/esm2.md` is rewritten on the branch; the reasoning and the knock-on
effects are in DECISIONS.md D-024. Retrievability of that release is established: the archive
serves 2021_04 only as a single 158 GB `uniref2021_04.tar.gz`, published md5
`444f0a7062a65a988ba1d5949d1d6419`, whose first member is a 93.7 GB `uniref100.tar` — so UniRef50
sits tens of gigabytes into the stream. The release notes give UniRef50 at 49,874,565 clusters, so
the pin is exact even where the bytes are not local. The project owner's acquisition decision is
recorded in D-024: 2021_04 is canonical, and the current per-tier release is an explicit proxy
mode that stamps the stated-vs-used gap onto every output.

**Not done.**

- The acquisition pipeline itself, which is the artefact this repo keeps: `data/` is git-ignored
  and a cloud session's disk is ephemeral, so the recipe and the provenance are the deliverable
  and the bytes are regenerated wherever it runs. It should pin the release, verify the published
  md5, extract the UniRef50 and UniRef90 members, and write the composition table and `run.json`
  through `amazebio.repro.run`.
- The ESM3-open proxy corpus. This is the better next step while the ESM-2 bytes are out of
  reach, and A1.1's verdict already fixes how it must be worded: proxy only, no corpus release.
- `UR50/S` versus `UR50/D` is never defined in any retrieved source, and the difference decides
  whether a reconstruction holds one representative per cluster or a per-epoch sample from each.
  It needs the ESM-2 paper added to `policies/sources.json` as a primary source. Do not guess it;
  §A0 makes the under-specification itself a finding.

**Waiting on the project owner.** Staging the 2021_04 bundle needs a machine with roughly 300 GB
of disk — download, verify the md5, then extract, in that order. AWS credentials were to arrive as
an environment secret under names of the owner's choosing; until they do, the pipeline can only
run in proxy mode. Note that A1.1 expected ESM-2 to be the cheapest corpus here and the right
first target. D-024 withdraws that: the pin is exact, but the bytes are the most expensive of the
four.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

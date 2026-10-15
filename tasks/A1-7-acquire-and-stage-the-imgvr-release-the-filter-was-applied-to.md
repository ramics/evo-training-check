---
id: A1.7
title: Acquire and stage the IMG/VR release the filter was applied to
phase: A
status: done
gate: false
depends_on: [A1.1]
blocks: [A7.2]
design_ref: "§A1, §A7"
deliverable: 1
owner: claude
---

# A1.7 — Acquire and stage the IMG/VR release the filter was applied to

**Design reference:** DESIGN.md §A1, §A7 · **Deliverable 1**

## Goal

Stage IMG/VR v4 — the **input** side of the only published exclusion procedure in this audit —
at its pinned version, from its own publisher, with the metadata the published rules read.

A1.2 staged both Evo releases, which are the filter's *output*. A7.1 then re-executed the
published predicates against that output and found the input missing: `policies/corpora.md` §2
states IMG/VR v4 is independently available at its pinned version, which is true and is not the
same as acquired. It is not in `policies/sources.json`, no tool stages it, and nothing in the
corpus bucket holds it. This task closes that gap, and it is a corpus acquisition on the scale of
A1.2 and A1.3 rather than an item inside another task (DECISIONS.md D-049).

## Why this is worth its own task

It is the single blocker for four distinct things, three of which A7.1 had to decline:

1. **The converse conformance check** — records the filter *removed* that its published rule does
   not call for. An over-broad filter is as much a mismatch between rule and practice as a leaky
   one, and §A7 asks for both directions. Without the input there is no denominator: a count of
   what is absent from a corpus cannot be taken from that corpus.
2. **Evo 2's conformance arm.** Its released IMG/VR FASTA carries `IMGVR_UViG_<taxon_oid>_<n>`
   accessions and no taxonomic lineage, so no published rule can be re-executed against it at
   all. With the input in hand the accessions become a join key and that arm opens.
3. **The three rules no release can test** (D-047): the high-confidence gate, the vOTU
   representative, and the prokaryotic-host count. All three read IMG/VR metadata — confidence
   label, vOTU id, host assignment — which travels with the database and not with either
   release. They are two thirds of the published procedure.
4. **A1.4 and the A2 detectors**, which need the pre-filter population to say what survived
   rather than only what is present.

## Steps

- Register the release in `policies/sources.json` with its publisher, version and retrieval date.
  Follow the paper's own pointer to the artefact rather than guessing a URL — D-019 records an
  HTTP 401 from a guessed namespace being indistinguishable from an absent artefact, and D-020
  records an HTTP 200 serving a bot challenge. **Verify content, not status codes.**
- Pin by the publisher's own checksum where one is published, as A1.3 did for UniRef (D-026,
  D-027). Where none is, record our own SHA-256 and state plainly that it attests the bytes have
  not changed since *this* acquisition and not that they are the bytes released — the separation
  D-040 drew for the unversioned benchmark files.
- Confirm the release is the one Evo 1 applied its procedure to, from Evo 1's own words, and
  record stated-versus-used where they differ. Evo 1 names IMG/VR v4; `src/amazebio/models.py`
  records ESM3's viral content as IMG/VR release 7, so the version in a sentence is not
  interchangeable with the version in a pipeline.
- Stage selectively by component, as A1.2 did, and stage the **metadata** deliberately rather
  than as a side effect: the per-record confidence label, vOTU assignment and host taxonomy are
  the reason this task exists, and a sequence-only stage would leave all four uses above blocked.
- Stream into object storage with verification before the upload completes. The corpus bucket
  withholds `s3:DeleteObject`, so an object that completes is permanent and an object claiming to
  be a release it has not been shown to be is worse than no object at all (D-026).
- Record the composition against the publisher's own stated counts, and report the gap where
  they disagree. A1.5 found documented archive sizes wrong by more than an order of magnitude;
  size downloads from `content-length`, not from documentation (D-040).
- Measure before deciding where to run the pass. A7.1's own measurement declined an EC2 launch
  because the format was splittable and the container managed 178 MB/s across sixteen readers
  (D-050); a gzip stream cannot be split and the answer may differ here. AGENTS.md's test is the
  one to apply, not the precedent to copy.

## Done when

- The release is registered in `policies/sources.json` and staged at a recorded, verified
  checksum, with stated-versus-used explicit wherever it could not be verified against the
  publisher's own figure.
- The staged component carries the per-record confidence label, vOTU assignment and host
  taxonomy, demonstrated by reading them back — not merely by the files being present.
- A composition artefact records counts per component against the publisher's stated counts.
- Which release Evo 1's procedure was applied to is established from Evo 1's own words, with any
  gap between stated and available versions recorded as a finding rather than smoothed over.
- Whether this is the real input or a proxy is stated as plainly as A1.1 stated it for the
  corpora, because every claim that depends on this inherits that verdict.

## What this task is not

- **Not the conformance work itself.** A7.1 owns the diff and is at `review`; the converse check
  and Evo 2's arm are follow-on work that this task unblocks. Keep the acquisition separate from
  the analysis, as A1.2 and A1.3 were kept separate from A7.1.
- **Not a scope widening of A1.4.** A1.4 also wants filter inputs; AGENTS.md is explicit that a
  task which turns out to be two tasks is split rather than quietly widened.
- **Not an excuse to acquire more than is needed.** One release, the components the published
  rules read. `pixi.toml`'s rule about unused pinned tools applies to unused pinned data too.

## State — 2026-10-15

`done`. **Both releases are staged and verified and every Done-when criterion is met.**
The work merged to `main` in PR #10 (branch `claude/kind-wozniak-ec94y4`).

**Staged:** 12 objects, 15.84 GB, under
`s3://amazebio-corpora-897641797669/corpora/imgvr/{2022-09-20,2022-12-20}/`. Every file was
verified against the publisher's own md5 — pinned from the public inventory before this project
held any of the bytes, the A1.3 standard rather than D-040's weaker self-attestation — before
its upload began. The December release was on tape; the restore returned in minutes, not the
24 hours the endpoint's documentation allows for.

**The credential problem is closed.** The token reaches JGI, settled by the shape of the
refusals rather than by assertion: with the header the download host answers 404 or 405,
without it the *header absent* 401 (D-062). Nothing in D-061 needs revisiting.

**The endpoint moved once more and only a credential could show it** (D-062). The publisher's
documented single-file `GET /download_files/{jamo_id}/` answers 404 authenticated for every
IMG/VR file, the 4 KB README and the 696 MB host table alike. What serves bytes is
`POST /download_files/` keyed by organism id, returning one zip stream with a manifest. The
tape-restore endpoint takes the same organism-keyed body; a flat list of ids is refused as a
404 that reads like an absent endpoint.

**The releases are v4 and v4.1, not two v4s** (D-063). The December README says so in the
publisher's own words, and says what it corrects: "fixes issues with two files
(IMGVR_all_proteins.faa and IMGVR_all_Sequence_information.tsv) in which a few sequences/rows
were incorrect". That is exactly the difference set D-052 derived from md5sums alone, confirmed
independently by the publisher. Both version strings are now on the releases in
`amazebio.imgvr`, so no later task re-derives them from a file in a bucket.

**The counts** (D-064, `artifacts/a1-7/composition.json`): 15,677,623 records, 8,606,551
distinct vOTUs, 5,576,197 high-confidence against 10,101,426 putative, 0 malformed rows —
identical across both releases, which is what an in-place erratum predicts. The high-confidence
file matches the confidence label count exactly in both. Against Evo 1's own post-filter figure
of 2,653,046 (Table S3, D-055), **Evo 1's procedure retained 16.9% of IMG/VR v4**.

**Against the Done-when list:**

- *Registered and staged at a verified checksum* — yes, both releases, publisher's md5.
- *Confidence label, vOTU assignment and host taxonomy demonstrated by reading them back* —
  yes, out of the bucket: columns 9, 5 and 16 of the staged sequence-information table, and the
  host table's three columns. Not inferred from the files being present.
- *A composition artefact against stated counts* — `artifacts/a1-7/composition.json`, with the
  three reconciliations it carries.
- *Which release Evo 1's procedure was applied to, from Evo 1's own words* — established as far
  as Evo 1's words allow, which is not all the way, and recorded as a finding rather than
  smoothed over. Evo 1 cites "IMG/VR v4"; the publisher names one release v4 and the other
  v4.1; Evo 1's corpus build date is unstated. Both are staged for that reason.
- *Real input or proxy, stated plainly* — **the real input.** The publisher's own files at the
  publisher's own checksums. The one qualification is the v4/v4.1 ambiguity above: immaterial
  for aggregates, which are identical, and material for A7.2's row-level checks.

**What this unblocks:** A7.2 — the converse conformance check, Evo 2's arm, and the three
published rules no release could test. It becomes `ready` when this reaches `done`.

**One prediction for A7.2, recorded so it can be falsified** (D-064): the high-confidence gate
leaves 5,576,197 records, of which 2,917,521 are distinct vOTUs, and Evo 1 reports 2,653,046 —
a further 9.1% down, the order a prokaryotic-host requirement would remove. Suggestive, not
claimed. A7.2 computes it over joined accessions, not aggregates.

**For the reviewer:** the arithmetic is in `src/amazebio/imgvr.py`, the acquisition in
`tools/stage_imgvr.py`, the counting in `tools/imgvr_composition.py`, and their tests in
`tests/test_imgvr.py`, `tests/test_stage_imgvr.py` and `tests/test_imgvr_composition.py`.
Note that `pytest` on PATH in a fresh container may resolve to a shim without `pyyaml` or
`boto3`, which fails 39 unrelated tests; the pinned environment is what CI runs.

**Superseded branches.** `claude/upbeat-shannon-wd4its` (the disk-spooling transfer path) is
carried into the current branch. `claude/exciting-sagan-kqlqvf` holds D-060's code, which D-062
has replaced; nothing needs to be merged from it.

## Numbering

Opened as **A1.6** on 2026-10-15 and renumbered to **A1.7** the same day, before any other
file referenced it. The A1.4 track had already created an A1.6 — the ESM3 similarity-reading
pass, split out by their D-043 — and it reached `main` first. AGENTS.md forbids reusing a task
ID, so the collision had to be resolved one way or the other; theirs is the one cited from
`main`'s commits and from their D-043, which makes this the cheaper of the two to move. The
push that first created this file calls it A1.6; this section is how that commit resolves.

## Notes

`blocks` names **A7.2**, which is the task that consumes this one: the converse conformance
check, Evo 2's arm, and the three published rules no release can test. A7.2 was opened on
2026-10-15, after this file; an earlier version of this section said the follow-on work had no
task file yet, which is no longer true.

A7.2 depends on this task alone and not on A7.1, even though it builds on A7.1's code. A7.1 is
held at `review` by the A3.3 gate, which has nothing to do with whether A7.2 can start — so
A7.2 becomes `ready` the moment this task reaches `done`, and nothing else gates it.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

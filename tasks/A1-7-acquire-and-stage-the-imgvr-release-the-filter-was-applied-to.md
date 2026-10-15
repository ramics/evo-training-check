---
id: A1.7
title: Acquire and stage the IMG/VR release the filter was applied to
phase: A
status: in-progress
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

`in-progress`, and no longer blocked. The credential problem is closed and **the first release
is staged**. Work branch: `claude/kind-wozniak-ec94y4`.

**The token reaches JGI.** The project owner made `JGI_API_TOKEN` a plain environment variable
and dropped the proxy's claim on `*.jgi.doe.gov`, which is what D-061 asked for. Settled by the
shape of the refusals, not by assertion: with the header the download host answers 404 or 405,
without it the *header absent* 401. D-061 is closed; nothing in it needs revisiting.

**The endpoint moved once more, and only a credential could show it** (D-062). The publisher's
documented single-file read `GET /download_files/{jamo_id}/` — what D-060 corrected to —
answers 404 authenticated for every IMG/VR file, the 4 KB README and the 696 MB host table
alike, as nginx HTML rather than the API's own JSON. What serves bytes is
`POST /download_files/` keyed by organism id, returning one `application/zip` stream with a
manifest. `top_hit` is the id string; posting the object the search response nests there returns
500. `POST /request_archived_files/` takes the same organism-keyed body, and a flat list of ids
is refused as a 404 that reads like an absent endpoint.

**Staged: the 2022-09-20 release, 6 files, 7.92 GB**, under
`s3://amazebio-corpora-897641797669/corpora/imgvr/2022-09-20/`. Each file was verified against
the publisher's own md5 — pinned from the public inventory before this project held any of the
bytes — before its upload began. The three fields this task exists for were then read back out
of the bucket rather than assumed from the files being present: in the staged
sequence-information table, `Confidence` is column 9, `vOTU` column 5, and
`Host taxonomy prediction` column 16; the host table carries `UVIG`, `Prediction method` and
`Host taxonomy prediction`. Run provenance is in `artifacts/a1-7/run-2022-09-20.json`.

**What is left:**

- **The 2022-12-20 release.** `BACKUP_COMPLETE` on tape; the restore is asynchronous and can
  take up to 24 hours. Re-run `python3 tools/stage_imgvr.py --stage --release 2022-12-20` until
  it picks the files up — the tool requests and polls rather than failing, and a run that ends
  with files still on tape says so and is not an error. One caveat stands from before: the token
  is a browser *session* token, so a restore wait longer than its life needs a fresh one copied
  from the Data Portal avatar menu. Unlike the 401s this task spent two passes on, *that* one
  really would be expiry.
- **The composition artefact** — counts per component against the publisher's stated counts.
  Nothing blocks it for 2022-09-20; it is honest to produce it for both releases at once, since
  the point of auditing both is the disagreement between them (D-052).
- **Whether this is the real input or a proxy**, stated as plainly as A1.1 stated it for the
  corpora. The ingredients are all recorded — D-052 on the two releases, D-056 on auditing both —
  but the verdict itself is not yet written down in one place.

**Transfer path, as it now stands:** one file is requested per call, so the zip holds one member
and the spool is bounded by the largest single file rather than by the 7.9 GB release. The member
is verified by streaming it once and uploaded by streaming it again, so the extracted copy never
lands on disk. Verification strictly precedes upload — the corpus bucket withholds
`s3:DeleteObject`, so an object that completes is permanent. A zip that does not hold exactly one
member with the expected name refuses rather than guessing which member was meant. Tests cover
the match, the mismatch, the short read, the missing member, the spool cleanup and the dry run.

**Superseded branches.** `claude/upbeat-shannon-wd4its` (the disk-spooling transfer path) is
carried into the current branch. `claude/exciting-sagan-kqlqvf` holds D-060's code, which D-062
has since replaced; nothing needs to be merged from it.

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

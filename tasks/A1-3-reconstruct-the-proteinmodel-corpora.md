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

## State — 2026-10-14 (third pass)

Work continues on branch `claude/blissful-goldberg-a91zwz`, pushed and green, not yet merged. It
carries the second pass's branch (`claude/modest-davinci-mb4svs`, D-025) merged into it, so that
branch needs no separate review.

**The staging blocker is lifted.** The project owner provided an S3 bucket in the project account,
and the 300 GB machine the last pass asked for turns out not to be needed: the archive's endpoint
supports ranged reads, so the compressed stream is resumable, and it can be pulled, verified, split
and uploaded in one forward pass with nothing buffered to local disk. Measured pull rate 86.7 MB/s,
so the transfer is tens of minutes rather than a day. The acquisition decision, the cost figures it
was made on, and the commitments that came with it are in DECISIONS.md D-026.

**Done this pass.** The acquisition pipeline the last pass listed as missing now exists:
`src/amazebio/uniref.py` (streaming, resume, tar walk, object-storage sink) and
`tools/stage_uniref.py` (`--probe` to report the layout, `--stage` to upload), with 29 tests.
`amazebio.repro` gains `input_url` and `output_object`, because a 169 GB input is never a local file
here and the pin rests on the publisher's published md5 instead — `input_url` records whether the
run actually matched it, so a partial run cannot be cited as a verified one.

Two things the pipeline had to learn from the real archive rather than from its fixtures, both now
covered by tests:

- **Sizes use GNU base-256, not octal.** A tar size field is 12 bytes of octal and tops out just
  under 8 GiB; the archive's first member is a 93,719,050,240-byte `uniref100.tar`. The octal-only
  reader failed on the very first header. The 93.7 GB it decodes to matches what this file already
  recorded for that member, which is the cross-check that it is read correctly.
- **A nested tar's walk ends before its last byte.** The tiers are tars inside the outer archive,
  and a tar ends at a two-block marker followed by padding to its record size. Those bytes must be
  measured and skipped or the next outer header is read from inside the padding. The same fact makes
  the whole-archive md5 need an explicit drain: hashing only the bytes a walk happened to read
  verifies nothing.

**New finding: the release bundles XML, not FASTA.** `uniref100.tar` contains `README`,
`uniref100.release_note` and `uniref100.xml.gz` (87.3 GiB) — no FASTA anywhere. This suits D-025
rather than complicating it: D-025 requires cluster membership preserved, and UniRef XML states
membership explicitly, where a FASTA reconstruction would have to infer it. Expect the same shape
for the other two tiers; the run in flight will confirm it.

**In flight right now.** The full pass is running: retaining the archive verbatim and extracting
`uniref50` and `uniref90`. Whoever picks this up should check `artifacts/a1-3/run.json` and
`artifacts/a1-3/members.json` for whether it completed and whether the md5 matched. Both are
git-ignored, so if the container is gone, re-run
`python3 tools/stage_uniref.py --stage --raw --tier uniref50 --tier uniref90` — the recipe is the
deliverable and the bytes regenerate wherever it runs. The destination objects are listable under
`s3://amazebio-corpora-897641797669/corpora/uniref/2021_04/`.

**Not done.**

- The composition table. `amazebio.uniref.composition_check` compares counted clusters against the
  release notes' 49,874,565 for UniRef50 and 138,515,945 for UniRef90, but nothing counts them yet:
  counting means parsing the staged XML, which is the obvious next step now that the tiers are
  reachable and should be done in-region per D-026.
- The ESM3-open proxy corpus, unchanged from the last pass and still the right second target.
  A1.1's verdict already fixes the wording: proxy only, no corpus release. Step one is resolving
  which tiers and versions ESM3 states at all — the paper names PDB, UniRef, MGnify and JGI without
  versions, so expect the §A0 finding to be most of the result.
- Retry `S-ESM2-PREPRINT`. Still the first-party statement of ESM-2's training data that the pin
  lacks; the blocker was host rate limiting, which lifts.

**Waiting on the project owner.** Nothing. The previous pass's request — a machine with ~300 GB of
disk and AWS credentials — is resolved by the bucket plus streaming.

**One housekeeping note.** A one-byte `corpora/.probe` object from verifying bucket access is still
in the bucket; the IAM user has no `s3:DeleteObject`, so it cannot be removed from here. Harmless,
but it is not part of the corpus.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

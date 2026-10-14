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

**Done: the corpus is staged and verified.** One pass read all 169,188,630,923 bytes with zero
reconnects, and the md5 over the whole stream matches the published
`444f0a7062a65a988ba1d5949d1d6419`. So this is the released bytes, not a reconstruction resembling
them, and ESM-2 results no longer carry an acquisition proxy qualifier — see DECISIONS.md D-027.
Staged under `s3://amazebio-corpora-897641797669/corpora/uniref/2021_04/`: `uniref50.xml.gz`
(25,107,210,941 bytes), `uniref90.xml.gz` (50,350,462,472 bytes), and the archive verbatim
(169,188,630,923 bytes). The evidence is `artifacts/a1-3/run.json`, which records `verified: true`,
and `artifacts/a1-3/members.json`, which records the archive's 15-member layout. Both are
git-ignored, so re-run `python3 tools/stage_uniref.py --stage --raw --tier uniref50 --tier uniref90`
to regenerate them; the recipe is the deliverable. Took 54 minutes at ~50 MB/s, upload-bound.

**Not done.**

- **The composition check — the one piece left before this task can go to review.**
  `amazebio.uniref.composition_check` already compares counted clusters against the release notes'
  49,874,565 for UniRef50 and 138,515,945 for UniRef90, but nothing counts them yet: it is called
  with an empty mapping, so every row reads "unknown" rather than agreeing or disagreeing. Counting
  means parsing the staged XML. D-026 says that should run in us-east-1, where reads are free.
- The ESM3-open proxy corpus, unchanged and still the right next target. A1.1's verdict fixes the
  wording: proxy only, no corpus release. Step one is resolving which tiers and versions ESM3 states
  at all — the paper names PDB, UniRef, MGnify and JGI without versions, so expect the §A0 finding
  to be most of the result.
- Retry `S-ESM2-PREPRINT`. Still the first-party statement of ESM-2's training data that the pin
  lacks; the blocker was host rate limiting, which lifts.

**Waiting on the project owner.** Nothing blocking. Acquisition is done without it. An EC2 route
was explored to make the staging and the coming counting pass run in-region: `ec2:RunInstances` is
permitted with `Project=ClaudeSpike` and an `Owner` tag, but no instance profile resolves, and
`iam:*` is denied so it cannot be created or inspected from here. It would need a role with the
bucket's write permissions, an instance profile holding it, and `iam:PassRole` scoped to that role.
Worth having for the counting pass, which re-reads 75 GB; not worth blocking on.

**Housekeeping.** The bucket holds four 0-byte objects that are not part of the corpus: the two
nested container tars, which matched their own tier filter and uploaded empty before that was
fixed, and a `.probe` from verifying bucket access. The bucket withholds `s3:DeleteObject`, so they
are permanent.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

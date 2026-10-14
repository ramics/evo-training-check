---
id: A1.3
title: Reconstruct the protein-model corpora
phase: A
status: done
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

## State — 2026-10-14 — DONE (ESM-2); ESM3-open split out as A1.5

**Merged into `main`.** Branch `claude/blissful-goldberg-a91zwz` is merged; nothing is left in
flight. The acquisition and counting pipelines are `src/amazebio/uniref.py` with
`tools/stage_uniref.py`, `tools/count_clusters.py` and `tools/ec2_count.py`, 29 tests.

**Every Done-when criterion is met.**

- *Corpora staged, checksummed, version-pinned.* UniRef 2021_04 is staged at
  `s3://amazebio-corpora-897641797669/corpora/uniref/2021_04/`: `uniref50.xml.gz`
  (25,107,210,941 bytes), `uniref90.xml.gz` (50,350,462,472 bytes), and the release archive
  verbatim (169,188,630,923 bytes). One streaming pass read all 169,188,630,923 bytes with zero
  reconnects and matched UniProt's published md5 `444f0a7062a65a988ba1d5949d1d6419`, so these are
  the released bytes rather than a reconstruction claiming the same version. Evidence:
  `artifacts/a1-3/run.json` (`verified: true`) and `artifacts/a1-3/members.json` (the 15-member
  layout).
- *Composition table with stated-vs-used recorded.* UniRef50 counted **49,874,565** clusters and
  UniRef90 **138,515,945** — the release notes' figures exactly. This is the independent check the
  md5 cannot provide: the md5 covers the archive as a whole and says nothing about whether the
  extraction split the members correctly. Each tier's XML root also declares `version="2021_04"`
  from inside the data, independent of the path. Results at
  `s3://.../corpora/results/2021_04/composition-uniref{50,90}.json` with their manifests.
  UniRef50 carries 283,772,222 further members, which is the membership D-025 requires.
- *Under-documentation logged as a finding.* D-028 and D-029, summarised below.

**The stated-vs-used gap, which is the substantive finding.** ESM-2's paper (now retrieved,
S-ESM2-PREPRINT) confirms the 2021_04 pin on three first-party statements — the model table, "when
2021 04 was the most recent release", and "138 million UniRef90 sequences" matching 2021_04's
138,515,945 against 2021_03's 135,301,051 — while contradicting itself with a fourth, "UniRef50,
September 2021 version", a date matching no UniProt release. More consequentially, **ESM-2's
training set is not the release**: ~43 million training clusters against 49,874,565, a ~14% gap of
which the paper itemises only ~310,000. D-029 settles that A1.3 stages the release and carries the
gap as a documented limitation. The excluded portion was selected by similarity to an unpublished
validation split, so it is not a uniform sample and the gap is not noise — that belongs in the
Phase A write-up, not only in the log.

**For review.** Whether the wording of the stated-vs-used gap is strong enough for §7's adversarial
reader, and whether ESM-2's own de-novo filtering — exclusion-based data filtering with
reproducible parameters, though stated as serving generalisation work rather than biosecurity —
needs its own treatment in the write-up. ESM-2 remains the positive control, since it carries no
biosecurity exclusion, but it is not unfiltered.

**Not done, and deliberately out of scope here.**

- The ESM3-open proxy corpus. A1.1's verdict fixes the wording: proxy only, no corpus release.
  Step one is resolving which tiers and versions ESM3 states at all — the paper names PDB, UniRef,
  MGnify and JGI without versions, so expect the §A0 finding to be most of the result. This is the
  natural next task for whoever picks A1.3's successor up.
- `S-ESM2-SCIENCE`, the version of record, is still paywalled (HTTP 403). Quotes come from the
  preprint. The "September 2021" contradiction especially should be checked against it before
  publication, since review may have corrected it.

**Waiting on the project owner.** Nothing.

**Reusable beyond this task.** `src/amazebio/uniref.py` is named for UniRef but only `RELEASE`,
`ARCHIVE_URL`, `ARCHIVE_MD5` and `STATED_CLUSTERS` are UniRef-specific. The machinery — resumable
ranged reads, incremental gunzip with a verifying digest, a tar walk handling GNU base-256 sizes and
nested archives, a concurrent S3 multipart sink, and a chunk-boundary-safe counter — is generic.
A1.2 stages another large bulk-published corpus and should reuse it rather than rewrite it; it
would otherwise rediscover the same two silent bugs, the double-counted overlap window and the
uncounted stream head.

**Housekeeping.** The bucket holds four 0-byte objects that are not part of the corpus: the two
nested container tars, which matched their own tier filter and uploaded empty before that was
fixed, and a `.probe` from verifying bucket access. The bucket withholds `s3:DeleteObject`, so they
are permanent.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

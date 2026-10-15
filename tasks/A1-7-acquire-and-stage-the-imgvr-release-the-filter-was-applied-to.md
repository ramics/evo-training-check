---
id: A1.7
title: Acquire and stage the IMG/VR release the filter was applied to
phase: A
status: ready
gate: false
depends_on: [A1.1]
blocks: []
design_ref: "§A1, §A7"
deliverable: 1
owner: unassigned
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

## Numbering

Opened as **A1.6** on 2026-10-15 and renumbered to **A1.7** the same day, before any other
file referenced it. The A1.4 track had already created an A1.6 — the ESM3 similarity-reading
pass, split out by their D-043 — and it reached `main` first. AGENTS.md forbids reusing a task
ID, so the collision had to be resolved one way or the other; theirs is the one cited from
`main`'s commits and from their D-043, which makes this the cheaper of the two to move. The
push that first created this file calls it A1.6; this section is how that commit resolves.

## Notes

`blocks` is empty on purpose. A7.1 shipped one-directional and sits at `review`, so wiring this
task into its `depends_on` would mark a reviewed task as depending on unfinished work and
`tools/board.py --check` would — correctly — reject it. The dependency is real and forward-facing
rather than backward: it is the follow-on conformance work that needs this, and that work does
not have a task file yet. Whoever opens one should add `A1.7` to its `depends_on` and regenerate.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

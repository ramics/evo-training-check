# Handoff — session of 2026-10-26/27

Branch **`claude/jolly-allen-oahiqb`**, pushed. Four commits. `pixi run -e dev check` green at
each. Read this, then `tasks/DECISIONS.md` entries **D-260, D-261, D-262**.

## The question this session answered

Whether material the published Evo 1 filter removes is present in **Evo 2's training data**.
It is not, for every record tested. Earlier work in this repo had been read as saying it was;
that reading was already withdrawn by A7.3 before this session, and the withdrawal is what the
session re-established.

## Results, all committed

**1. One record traced end to end** — `docs/phase-a-worked-example-papillomavirus.md`.
`IMGVR_UViG_643677429_000001`, entry 1, in OpenGenome2's released **FASTA**. Corpus pin checked,
record found on a fresh read, protein re-derived and byte-identical to the one the owner
BLASTed, both Pfam rows reproduced to the digit, every input table named. Residue-free: the
protein is cited by digest and coordinates (D-103).

**2. The records the rule removes are absent from the training data** —
`docs/training-data-membership-test.md`. 48-mer exact search, both strands, over all six files
of `arcinstitute/opengenome2` `json/pretraining_or_both_phases/imgvr_untagged/` at pinned
revision `84d2a7e690c8bb395d1f4868822dfa031ea561c6`. 2,653,097 records read. **0 of the 17**
records whose `label_rule_outcome` is `removed` are present. Pre-registered in **D-260**; result
in **D-261**.

**3. The training format joins to the released FASTA by sequence** — same document, addendum.
Hash-join, both orientations, with a `(length, first-48, last-48)` fallback tier. **All
2,652,840 distinct training records resolve by exact sequence digest; one needed the fallback;
none unresolved.** 2,653,047 distinct accessions; **304,448** FASTA entries absent from the
training corpus. Both figures are A7.3's, reproduced by a method sharing no code with it.
Sequences are preserved verbatim or not present — there is no preprocessing transformation
between the two representations. **D-262.**

**4. Intersecting A2.1's detections with the training set.** Of 319 records A2.1 detected
carrying a denylist-named family, **237 were removed and 82 are in the training data** — and the
82 are all weak (median 1.4x the curated threshold, max 6.8x, none at 10x), while the removed
set runs to 29.5x. 81 of the 82 rows reached a denylisted group through `matched_on: identifier`
— the Pfam *name*, not the biology. **The name axis over-counts; the 314/319 is an upper bound**
(D-261).

## What is broken, and must be fixed before reuse

**The hazard family set build is defective. Do not use `hazard_family_set.json`.** Two
independent faults:

- **Too broad.** The stratum built from the published exclusion list collects families that are
  merely *present* in a reviewed entry of those taxa, which includes host-derived and
  host-mimicking families — 280 of 633 fall outside this project's own viral selection, among
  them actin, protein kinase and the immunoglobulin domain. Two large-genome families dominate
  the inflation. Restricting to genuinely viral families, and carrying the existing
  `specificity` measure per family, is the repair.
- **Incomplete, silently.** Taxa were resolved **by name**, and two of the nineteen families
  returned zero because ICTV has renamed them. 2,904 reviewed entries were dropped with no
  error. **D-137 forbids exactly this** — that list maps to taxonomy ids by curation, validated
  against a pinned taxonomy, never by name matching. Resolve by taxid, curated per family, so a
  rename surfaces as a note rather than a zero.

The **toxin stratum is sound and committed** — `policies/specs/hazard-toxins-2024-06-01.json`,
10 families from 4 of 9 entries, curated per entry against UniProt release 2026_03. Four entries
nominate nothing (no protein sequence); one is defined by a sequence motif in the regulation and
is declined rather than guessed; one family is kept but flagged as an accessory domain that is
not evidence of a toxin on its own. No decisions entry yet — **write one**.

## Open items

- **D-260, D-261 and D-262 sit on this branch.** `AGENTS.md` puts decisions on `main`, pushed
  immediately. This session was instructed to push only to its own branch. **Move them**, and
  re-check the numbers aren't taken (`AGENTS.md`, "Take the number when you append").
- **The accession list is scratch and dies with the container.** 2,653,047 lines, sha256
  `413b92e13df518b9cefa3bdeba99449a8298e41a40c98dd9aa39b735f16b0568`. Producing it citably
  through `repro.run` is a task of its own, and it unlocks running every published rule against
  the training corpus — which no task has ever done.
- **Wording to revisit before anything ships.** The join narrows the disclosure finding: "the
  only representation anyone can audit is the one that fails the audit" is no longer correct, the
  training representation being auditable through an undocumented sequence join. Affects
  `docs/phase-a-worked-example-papillomavirus.md` and `policies/evo.md` §10. D-262 says so.
- **Two defects in `tasks/A7-5-*.md`, which is in `review`:** its Result section reports three
  passes while the State section below says the pass has not been run; and it gives the registry
  path as `data/profiles/pfam/38.2/` where the code resolves `data/pfam/38.2/`.
- **A 96-record pointer, not a result.** 2,917,521 FASTA accessions minus 2,653,047 in training
  is 264,474, against the procedure's 264,570 removals. The gap is near A7.2's 95 forward
  failures. It chains counts measured on two IMG/VR releases and in three units, so it is
  enumerable now and not yet enumerated.
- **Two methods disagree on 8 of 314.** The needle search says 90 records present, the join says
  82, and the join found nothing the needles missed. The join is stricter, so D-261's 90 is
  probably 82 — unconfirmed.
- **A2.6 (census depth) is `deferred` by the owner (D-247).** Reactivating it is the owner's
  call. Its own costing is ~80 core-hours, about a dollar on spot; the $5.40 in D-234 was a
  failed launch. Note that a FASTA census now yields two results rather than one, because the
  join exists.

## Operational notes worth inheriting

- `curl -sSL --retry 6 --retry-all-errors` is the only reader that has survived the HuggingFace
  transfer; plain `urllib` died with `BrokenPipeError` mid-download. Put the fragile network step
  first and **persist its output**, so a later failure costs minutes rather than the download.
- `seqstream._iter_fasta(..., keep=lambda _: True)` is the full-sequence FASTA loop.
  `corpora.iter_fasta_records` carries no residues by design.
- `profilesearch.search(restrict_to=...)` keys on the profile **name**, not the accession;
  `view.universe[accession]` maps one to the other.
- Pfam 38.2 is staged locally at `data/pfam/38.2/`, verified against the publisher's md5.

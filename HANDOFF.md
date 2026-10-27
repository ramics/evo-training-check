# Handoff — session of 2026-10-27

Branch **`claude/jolly-allen-oahiqb`**, pushed. Read this, then
**`docs/a2-6-census-runbook.md`**, then decisions **D-263 to D-268**.

The previous handoff (session of 2026-10-26/27) is superseded; its unfinished items are carried
below rather than dropped.

## The job the owner has approved next

**Run the full census, over all 1,719 pinned viral families.** The runbook is
`docs/a2-6-census-runbook.md` and it is the first thing to read: the sizing in it is measured,
not estimated, and every trap in it has already cost this project a launch.

Two things to do before launching, both in the runbook:

1. **Probe OpenGenome's stage 2.** It is the one component whose rate is unmeasured, and it
   decides whether that release fits the timer. Ten minutes, publishes nothing.
2. **Rehearse the assembly against the shape the census will produce.** It has failed twice,
   both times after the compute was spent.

A2.6 is still marked `deferred` from the owner's earlier decision. Reactivating it means a
status change pushed to `main` and a decisions entry recording the reversal, since the deferral
was recorded as a decision.

## What this session established

**The hazard family set is rebuilt and usable.** The previous build was withdrawn for two
faults; both are fixed and one turned out to be a finding about the audited filter rather than
about this repo.

- Taxa now resolve by **curated taxid**, validated against the pinned taxonomy, with a refusal
  on any taxon that returns nothing uncurated. The old build matched names and silently lost
  **2,904 reviewed entries** across two taxa — reproduced here exactly, from the other
  direction, as Reovirales 807 plus Orthoherpesviridae 2,097.
- **The published filter names a virus family that did not exist at that rank when it was
  published.** ICTV had already elevated *Reoviridae* to an order and split it in two; in the
  pinned taxonomy the old name survives only as a synonym. A name-matching implementation of
  the filter's own rule removes nothing for it. (D-264)
- The set is **1,144 families from 14,673 reviewed entries**. The 12 denylisted *orders*, absent
  from the old build, are included.

**The independent instrument agrees with the name axis, which cuts against what this branch
inherited.** Measuring by biology — listed taxon → reviewed UniProt entry → Pfam
cross-reference, reading no family name — gives agreement on **318 of 319** detected records.
The Pox-named families the previous session singled out really are cross-referenced by reviewed
*Poxviridae* proteins. So "the name axis over-counts" needs restating: it over-counts in
**exclusivity and hit strength**, not in family identity. `Pox_VLTF3` carries 87 of the 319
records at **0.368** exclusivity — 7 of its 19 reviewed entries are *Poxviridae* and the rest
are other large DNA viruses and phages, which is what its own description says. 100 records are
`hazard_family_exclusive`, 218 `shared`. (D-264)

**The cost curve's subjects are fixed at the 646 viral, family-specific nominations**, by the
owner. `metrics/costcurve.md` §3 is amended in the open, with the direction of the bias it
removes stated: with the host-derived families left in, removing actin would have counted as
hazard *benefit* and dropped out of collateral *cost* at the same time. Nothing is deleted —
all 1,144 rows keep the columns that reverse the filter. C5.2 now indexes 646. (D-266)

**The census failure is diagnosed and fixed.** It was never throughput. `profilesearch.search`
defaulted to three HMMER threads and nothing overrode it, so "eight workers on eight vCPUs"
asked for **24 threads on eight cores**. The worker now takes `--search-cpus`, the launcher
defaults to one per worker and refuses an oversubscribed launch. (D-267)

**And the costing is now measured, not estimated.** A nine-cent probe corrected it twice: the
search rate is **4.56 ms/gene** single-threaded against a published 2.19 (that figure was
wall-clock at three threads), and streaming is **25× cheaper** than the table claimed, which
makes the eight-fold per-band re-read a rounding error. **OpenGenome2 alone is 79 core-hours**
— the whole budget that was supposed to cover both releases. (D-268)

## Open items

- **D-260 to D-268 all sit on this branch.** `AGENTS.md` puts decisions on `main`, pushed
  immediately. Move them, and re-check the numbers are still free — `main` was at D-259 when
  this session ended.
- **No task is claimed on the board** for any of this session's work. C5.1 is `done` and this is
  its deliverable; whether to reopen it or open a new id is the owner's call.
- **The accession list is still gone, and it is now a prerequisite.** The census searches
  essentially the whole released FASTA — 2,957,495 imgvr records against a training corpus of
  2,653,047 — so about a tenth of what it reads is material the model never trained on, and its
  "surviving corpus" figures cover a population that includes it. Restricting to training
  members needs the sequence join's accession list, which was scratch. Producing it citably
  through `repro.run` unlocks running every published rule against the training corpus, which
  no task has done. (D-262, measured again in D-268)
- **Three objects in the store are permanently mislabelled.** Under
  `results/c5-1/by-commit/02b1a45…/` sits a hazard family set whose manifest names a commit that
  does not contain the tool that produced it — published from a dirty tree by mistake. They are
  not cited by anything and must not be; the citable copies are under the clean commits. Nine
  other tools still carry the shape that allowed it, named in D-265, and fixing that properly is
  its own task on `repro`'s contract.
- **Wording that no longer holds.** "The only representation anyone can audit is the one that
  fails the audit" is withdrawn — the training representation is auditable through a sequence
  join. `docs/phase-a-worked-example-papillomavirus.md` and `policies/evo.md` §10 still carry
  the old claim.
- **Two defects in `tasks/A7-5-*.md`.** Its State block says the pass has not been run; it has —
  its region metrics are published and this session consumed them. And it gives the registry
  path as `data/profiles/pfam/38.2/` where the code resolves `data/pfam/38.2/`.
- **Two methods disagree on 8 of 314.** The needle search says 90 records are in the training
  data, the join says 82, and the join found nothing the needles missed. The join is stricter,
  so the 90 is probably 82 — unconfirmed.

## Reporting limit worth remembering before the write-up

DESIGN.md §4 restricts results to homology class, fold family and survival route, with no
per-pathogen ranking, and X3.1 holds external circulation until disclosure. A gap analysis of
which named pathogens a published denylist does not cover is exactly what that limit is for.
The scope question is real and belongs in the audit; it belongs there aggregated by class, not
as a list.

## Operational notes worth inheriting

- **The console is useless on these instances.** It returned 0 bytes for the whole of a
  34-minute probe. The 10-minute log upload to object storage is the only channel; read silence
  from the console as nothing at all.
- A probe's own log confirms the publish guard: `not publishing: … is a rehearsal`. Check for
  that line rather than trusting the code path.
- `curl -sSL --retry 6 --retry-all-errors` is the only reader that has survived the HuggingFace
  transfer; plain `urllib` dies with `BrokenPipeError` mid-download.
- `seqstream._iter_fasta(..., keep=lambda _: True)` is the full-sequence FASTA loop.
  `corpora.iter_fasta_records` carries no residues by design.
- `profilesearch.search(restrict_to=...)` keys on the profile **name**, not the accession;
  `view.universe[accession]` maps one to the other. A hazard-families-only search would need
  that mapping wired through.

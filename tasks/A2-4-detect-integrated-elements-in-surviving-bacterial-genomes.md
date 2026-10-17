---
id: A2.4
title: Detect integrated elements in surviving bacterial genomes
phase: A
status: in-progress
gate: false
depends_on: [A1.4]
blocks: [A3.2]
design_ref: "§A2"
deliverable: 1
owner: claude
---

# A2.4 — Detect integrated elements in surviving bacterial genomes

**Design reference:** DESIGN.md §A2 · **Deliverable 1**

## Goal

Identify integrated elements in the surviving bacterial component, another route taxonomy
labels do not capture.

## Steps

- Select and pin the detection tools named in §A2.
- Run over the surviving bacterial component of each manifest.
- Attribute hits to the 'integrated-element' survival route.
- Cross-check a sample of calls against a second tool for concordance.

## Done when

- Hit tables exist with route attribution.
- Two-tool concordance measured on a documented sample.
- Parameters and versions recorded.

## State — 2026-10-17

`in-progress`. **Branch `ccr-a062d0fd-ocvx60`** carries the work; `main` has this file, the
board and D-112 to D-117.

**Why this task.** Of the four ready A2 detectors it is the one whose inputs are already staged
— OpenGenome2's GTDB v220 component was staged with "A2.4 searches these genomes for integrated
elements" as its stated reason — and whose tool was already pinned. A2.3's eukaryotic inputs are
2.17 TB and deliberately unstaged; A2.2 needs a structure search tool the environment does not
carry.

**Pre-registered, before any output existed (D-112..D-116).** The instrument pin is separate
from A4.2's object of study — A4.2 benchmarks geNomad 1.1.0 because that is the version IMG/VR's
labels came out of, and detecting with the same 2022 build against the same 2022 markers would
make the audit's blind spot and the filter's the same one. A2.4 runs geNomad 1.12.0 against
marker database v1.9, the newest pairing the publisher attests. Localisation comes from the
provirus finders and family identity from A2.1's registries at D-076's thresholds unchanged, so
an A2.1 table and an A2.4 table differ only in route, element kind and records searched.
VIBRANT 1.2.1 is the second tool, with agreement fixed at 0.5 reciprocal overlap and
disagreement reported by direction. And A2.4 answers for Evo 2's bacterial component **without
standing in for Evo 1's**, which is not staged — so Evo 1's tables are `not_searched`, not zero.

**Done.** `src/amazebio/proviruses.py` and `tests/test_proviruses.py` — pins, both output
parsers, reciprocal overlap, the record-level 2x2 and Cohen's kappa. 40 tests, full `check`
green at 829 passed. The two environments are in the lockfile (`feature.proviruses`,
`feature.vibrant`) and both tools run.

**Both parsers are validated against real output, and it caught two errors.** geNomad 1.12.0 on
*E. coli* K-12 returns five proviruses at the known positions of its cryptic prophages, and that
run is pinned as `tests/data/genomad_1_12_0_ecoli_provirus.tsv`. The score column is
`v_vs_c_score`; the documented guess `virus_score` had been returning `None` for every call.
VIBRANT's header, read off the line of `VIBRANT_run.py` that writes it, puts its protein columns
*before* its nucleotide ones — the opposite of the first assumption here — and its databases
turn out to be versioned after all (KOfam 2019-08-10, Pfam 32.0, VOG 94, hard-coded in
`VIBRANT_setup.py`), so the pin records them instead of reporting a gap that does not exist.

**The owner's two answers are in, and both are recorded (D-118, D-119).** The pass is a
**sampled** one inside a $20 ceiling — read against spot, since the spot role now exists and is
verified by launch (D-132, withdrawing D-131) — run in nested bands so that the first band is the
calibration the budget did not separately buy — membership is already nested by construction,
so a deepening re-reads nothing. `estimate_kind` is `lower_bound` at every depth. And **Evo 1's
prokaryotic component is being staged**, so the prophage route covers both corpora rather than
one of the audit's two subjects; `stage1_gtdb` moved into the staging tier accordingly.

**The Evo 1 staging is finished and verified.** All 14 objects of `stage1_gtdb` are present,
118.5 GiB, no zero-byte objects — worth checking explicitly, since a permanently un-removable
zero-byte object is the one thing A1.3 left in this bucket. The release pin re-probes exactly:
22 files, 146,886,935,899 bytes.

**And it corrected the reason it was done (D-130).** Both releases' GTDB versions are stated by
their publishers: Evo 1 is **v214.1**, twice in the version of record; Evo 2 is **v214.1 plus a
220.0 increment of 28,174 genomes**, not v220. OpenGenome2's staged tree says the same thing
independently — `gtdb_v220/v214/batch{1,2,3}.tar` beside `gtdb_v220/v220_update.tar` — so the
directory name is not the version of what is under it, which is the trap D-119 fell into. D-116's
refusal to substitute **stands and is stronger**: the substitution would have put a superset in
place of a subset, adding genomes published after Evo 1's filter ran. The staging bought OG1's own
splits and representation and not a sequence set the audit lacked; D-130 says so plainly.

**Also opened:** **A7.4**, to test Evo 2's "used in its entirety" claim now that both sides are
staged. Not absorbed into A2.4.

**Also done.** A2.1's search loop is now `src/amazebio/profilesearch.py`, called by both
detectors (D-113), with thresholds, cutoffs and record naming unchanged — A2.1's own tests did
not move and still pass, which is the test of the refactor. It gains `proteins_from_fasta`,
A2.4's way in: the proteins geNomad already called inside a delineated provirus, attributed to
the host genome rather than to the fragment name the finder invented.

**The pipeline exists and runs end to end.** `tools/detect_proviruses.py` reads the staged
corpus, samples by genome, calls geNomad `annotate` and `find-proviruses`, searches the provirus
proteins against A2.1's registries at D-076's thresholds, and writes the
`metrics/detections.md` table with `element_kind: prophage`. Verified against Evo 1's GTDB:
14 min wall for one genome including the HMM load.

Scope is enforced rather than assumed — both releases' GTDB searched, every other component
reported `searched: false` with a reason, and a manifest with no bacterial component getting
`not_searched` instead of a column of zeros. The route comes from the manifest's
`uniform_outcome` and differs by reading: `out_of_scope` under charitable and literal (D-007's
headline), `retained_by_design` under strict's wildcard scope.

**Running it caught a fault that reading the log would not have.** `--limit 1 --rate 1.0`
produced `estimate_kind: population`, 0 of 1,719 families, Wilson [0, 0.0022] — a census over
the whole component computed from one genome and 25,792 bases, with exit code 0. A limited run
now writes no table (D-143).

**Prerequisites, all now in place.** A1.4's manifests are regenerated (the inventory guard
caught the undeclared GTDB objects first, and they are now declared). The profile registries are
staged and verified: RVDB-prot at 13,679 profiles against 13,679 stated, Pfam's viral universe
1,719 of 30,134. The geNomad marker database v1.9 is fetched and its md5 matches the publisher's.

**Left, in order.**
1. The VIBRANT arm. The concordance criterion is fixed (D-114) and its parser is written and
   tested, but nothing runs VIBRANT yet, and until it does every table carries the note saying
   the prophage count rests on one instrument.
2. The in-region launcher. Reading 109 GiB of Evo 2 and 118.5 GiB of Evo 1 is the data-movement
   case `AGENTS.md`'s EC2 test is written for, and spot is live and verified (D-132).
3. The first band at 2.5%, which is also the calibration (D-118) — the per-genome cost on real
   draft assemblies, which D-117's single-genome figure does not establish.

**Not blocked on anyone.**

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

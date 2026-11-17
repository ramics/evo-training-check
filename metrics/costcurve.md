# metrics/costcurve.md — the frozen cost-curve definitions

Task **C5.1** · `DESIGN.md` §C5, §C6, §C7, §4 · Deliverable 4 · frozen 2026-10-20,
DECISIONS.md D-204

This is the authoritative text for Phase C's cost curves. It is written to be reimplementable
from this file alone, because **C6.3** is required to reimplement the headline curves by a
second method before publication (`DESIGN.md` §7) and that check is worth nothing if the second
implementation is written by reading the first. C6.3 works from this document.
`src/amazebio/costcurve.py` is the first implementation; C5.2 onward compute at corpus scale.

Frozen means frozen. Every definition here — the family set, both cost metrics, the stringency
axis, the coverage metric and the regime boundary — was fixed **before any curve was computed**,
which is what §C6 requires and for the same reason §B5 pre-registers its effect-size threshold.
If one turns out to be wrong, the change is a `DECISIONS.md` entry saying what was known at the
time and what changed, not an edit.

**Nothing in this file requires training, fine-tuning or running a model** (§C5). Every quantity
comes from pinned public sequence databases and a pinned aligner.

---

## 1. What the curve answers

For a hazard protein family **F**: to remove F's capability from a training corpus, what else
must be removed?

A real filter does not know all of F. It knows the part a published hazard list lets a developer
label — a **seed set** — and removes whatever is similar enough to a seed. So the curve has two
sides, both swept over the filter's stringency **s**:

- **Hazard removed, `H(s)`** — how much of F's *known diversity* that filter actually catches.
- **Collateral removed, `C(s)`** — how much non-hazard biology it takes with it.

This is deliberately the same shape as the filters Phase A audited: ESM3-open removes sequences
by similarity to a denylist-derived seed set, and A8.1 measured both sides of exactly that
operation (D-200). The curve prices it for a family the filter's author never enumerated.

---

## 2. The unit: a UniRef50 cluster

Every count in a curve is a count of **UniRef50 clusters** of the pinned release
(`2023_02`, the release A1.5 staged and A8.1 measured).

A count of records would weigh a family by how often its organism has been sequenced, which is
the same distortion M2 avoids by reporting per-family counts rather than a pooled total. A
cluster at 50% identity is one unit of diversity at the identity the publisher itself defines,
so the denominator is a property of the release rather than of sampling effort.

Two conversions travel with every curve so a reader can move between units without recomputing:
the same quantity in **UniRef90 clusters** and in **records**. They are reported, never summed
with the cluster counts and never used as the denominator.

---

## 3. The hazard family set

A **family** is a Pfam-A family of the pinned release, **Pfam 38.2** (`profiles.PFAM_38_2`).
Pfam is used rather than RVDB-prot because the curve needs cellular and phage families in the
same registry as the viral ones — the collateral is the point — and RVDB-prot's membership is
viral by construction.

A family enters the set only by a **published nomination**. Three strata, each recorded on every
family so a reviewer can see which one put it there. Nothing enters by judgement, and no family
is added because it looked relevant.

| Stratum | Nominated by | The nomination is |
|---|---|---|
| **V** — virus-family | Evo 1's published exclusion list: 19 families and 12 orders (`policies/specs/evo1-literal.yaml`) | a laboratory's own published statement of what it considered hazardous enough to remove |
| **T** — toxin | the Select Agents and Toxins List, 2024-06-01, toxin entries of 42 CFR 73.3, 9 CFR 121.3 and 7 CFR 331.3, under the reading pinned in D-137 | a regulation naming the **protein** |
| **S** — select-agent organism | the same list's organism entries, under the same reading | a regulation naming the **organism**, and no protein |

**The curve's subjects are V ∪ T. S is defined, counted and reported, and no curve is computed
for it.** A regulation that lists *Bacillus anthracis* nominates no protein family: choosing
which of that organism's families carry the hazard would be this project's judgement wearing a
regulation's authority, and §C5's whole claim is that the family set comes from published lists.
S is carried rather than dropped so the write-up can state what the method does not reach, which
is the §A0 habit applied to Phase C.

### How a nomination reaches a Pfam family

By database cross-reference, in one direction only: **organism → reviewed UniProtKB entry →
Pfam**.

1. Resolve the nomination to NCBI taxids against the pinned taxonomy `taxdmp_2023-04-01.zip` —
   for V, the denylist's family and order names as `policyspec` already executes them; for T and
   S, the taxid mapping pinned in `policies/specs/select-agents-2024-06-01.json` (D-137).
2. Query UniProtKB for **reviewed (Swiss-Prot)** entries with `taxonomy_id` in that set.
   Reviewed only: an unreviewed entry's family annotation is itself an automatic prediction, and
   a hazard set assembled from predictions is a hazard set assembled from a model.
   `taxonomy_id` is the lineage-inclusive field, for the reason recorded in
   `tools/uniprot_denylist_count.py`.
3. For stratum **T**, keep only entries whose protein name matches the listed toxin, because the
   regulation names the protein. For **V** and **S**, keep every entry from the taxa.
4. The family set is every Pfam accession cross-referenced by a kept entry.

**The UniProt release is recorded, not pinned.** UniProt's REST service serves the current
release only — the same gap `tools/uniprot_denylist_count.py` records for the denylist count.
The release and its date go in the artefact so a reader sees the gap rather than inferring there
is none. Pfam, the taxonomy and UniRef are all pinned; this one input is dated.

### Which nominations carry a curve — amended 2026-10-27, D-266

The nomination above is the set. **The curve's subjects are the nominated families that are
both in the pinned viral selection (D-075) and `viral_only` by A4.5's background measure** —
646 of the 1,144 nominated. This is an amendment to a definition that §C6 fixed before any
computation, it is recorded as one, and it is the project owner's call rather than a tidying.

Why it was needed. Nominating by cross-reference admits every family a reviewed entry of a
listed taxon carries, and a large-genome virus carries host-derived and host-mimicking ones:
481 of the 1,144 fall outside the viral selection, almost all through *Poxviridae*,
*Herpesvirales*, *Lefavirales*, *Ortervirales* and *Retroviridae*, and they include actin,
protein kinases and the immunoglobulin domain. Leaving them in is not neutral. `H(s)` would
count removing actin as **hazard removed**, and because §5's collateral denominator excludes
every nominated family, the same nomination also takes actin out of **collateral removed**.
Both errors run the same way — they make filtering look cheaper than it is — which is the one
direction this audit may not be wrong in.

What the amendment does not do. It removes nothing from the family set: `tools/hazard_family_set.py`
publishes all 1,144 with `viral_selection` and `specificity` on every row, so the full
nomination stays readable and the curve's subject list is a filter over it that anyone can
recompute or reverse. The excluded 498 are reported as a count beside the curves, because a
reader is entitled to know what a published nomination contained and what this project did
with it.

---

## 4. The seed set, and why `H(s)` is not trivially 1

For each family F, the **seed set `S(F)`** is the UniRef50 clusters containing at least one of
the reviewed entries that nominated F in §3.

The **target** is all of F: every UniRef50 cluster containing at least one record annotated to F
in the pinned release.

A filter at stringency s removes a cluster when any of its members aligns to any member of a
seed cluster at ≥ s identity over ≥ 80% of the shorter sequence. Seed clusters are removed by
definition; the rest of F is removed only if the similarity reaches it, which is why `H(s)` is a
measurement and not a tautology. **If the seed set and the target are the same set, F reports no
curve** — the nomination enumerated the family, so there is nothing for a filter to generalise
to, and printing `H(s) = 1` at every s would read as a filter that works perfectly.

The 80% coverage rule is M3's, frozen in `metrics/survival.md`, used here unchanged so a Phase C
identity and a Phase A identity mean the same operation.

---

## 5. The two cost metrics

Let `R(s)` be the clusters a filter seeded on `S(F)` removes at stringency s.

| Metric | Numerator | Denominator |
|---|---|---|
| **Hazard removed `H(s)`** | clusters of F in `R(s)` | clusters of F |
| **Collateral removed `C(s)`** | clusters in `R(s)` annotated to **no** family in V ∪ T ∪ S | UniRef50 clusters of the release annotated to no family in V ∪ T ∪ S |

Three things about that table are load-bearing.

**The collateral denominator excludes every nominated family, not just F.** A cluster belonging
to another hazard family is neither collateral nor F's diversity, and counting it as collateral
would make two overlapping hazard families each look expensive because of the other.

**Clusters annotated to no Pfam family at all are in the collateral denominator.** They are the
majority of UniRef50 and they are biology; excluding them would shrink the denominator to the
annotated world and inflate every collateral fraction. Their share is reported alongside, since
a collateral set made mostly of unannotated clusters is a different finding from one made of
named families.

**A third quantity is reported beside the two, and is not a cost metric.** `families_touched(s)`
is the number of distinct non-nominated Pfam families with at least one cluster in `R(s)`, with
the share of each one's clusters removed. §C6's catastrophic regime is "deleting a large slice of
general biology", and a reader cannot tell a slice from a scattering out of a fraction alone.

Every fraction ships with a Wilson interval at 95%, per `AGENTS.md`: no point estimate travels
without its interval, in the paper, in the figures, or in the shipped tool.

---

## 6. The stringency axis

Sequence identity, computed with the aligner already pinned for A1.6 — **MMseqs2 18.8cc5c** —
at **≥ 80% coverage of the shorter sequence**, swept over:

```
0.95  0.90  0.80  0.70  0.60  0.50  0.40  0.30
```

**0.30 is the floor and the reason is stated rather than implied.** Below roughly 30% identity a
pairwise alignment stops distinguishing homology from chance at this length, and MMseqs2's
prefilter is not calibrated to be exhaustive there; a curve drawn past it would be reporting the
aligner's sensitivity, not biology. A family still rising at 0.30 is reported as **unbounded
below**, which is itself a §C6 finding — it is a family whose collateral has not stopped growing
at the lowest honest threshold.

**Two free anchors travel with every curve.** UniRef90 and UniRef50 co-membership execute the
same predicate at 0.90 and 0.50 using the publisher's own clustering, with no aligner at all —
the instrument A8.1 established (D-198). They are computed and reported beside the aligner's
0.90 and 0.50 points. A disagreement between the two is a defect in this pipeline, not a result,
and the artefact records both rather than the better-looking one.

**Structural similarity is not swept.** §C5 allows either axis; this project pins one, because a
curve mixing two incomparable stringency scales has no x-axis. A2.2's fold reference is used for
reporting (§8), not as a second sweep.

---

## 7. Coverage, which no curve ships without

§C7 is explicit: the curve is only as good as the databases' coverage of a family's diversity,
coverage is uneven across families, and **a curve is never reported without it**. Two numbers
per family, because they fail differently:

**Sampling saturation.** Chao1 over F's UniRef50 clusters, with each cluster's UniRef90
sub-cluster count as its abundance:

```
Chao1 = observed + f1² / (2 · f2)        f1 = clusters with exactly one UniRef90 sub-cluster
                                         f2 = clusters with exactly two
saturation = observed / Chao1            (1.0 when f1 = 0; undefined and reported as null when f2 = 0)
```

A published richness estimator rather than a threshold of this project's choosing. It answers
whether the database has stopped finding new diversity in F.

**Sampling concentration.** The number of distinct NCBI genera among F's members, and the share
of F's clusters from the single most-represented genus. A family known from one genus has an
unknown true diversity whatever Chao1 says, because every member came from the same sampling
effort.

A curve whose family reports `saturation < 0.5` or `top_genus_share > 0.8` is reported as
**coverage-limited**, and the regime classification in §9 is withheld for it rather than printed
with a caveat. A caveat under a regime label is read as the label.

---

## 8. The published view, and the per-family view

`DESIGN.md` §4: cost curves are published **aggregated by homology class, never as a per-family
hazard ranking**, with the regime classification by homology class and fold family, and
per-family curves kept in the disclosure package and out of the preprint. The limit is set
before Phase C runs, which is here.

| Axis | Is |
|---|---|
| **homology class** | the **Pfam clan** of the family, from the pinned `Pfam-A.clans.tsv` — Pfam's own curated grouping of families by structural and evolutionary relatedness |
| **fold family** | A2.2's pinned fold reference, used as it stands |

Two rules make the aggregate safe to publish, and both are part of the schema rather than of
anyone's care at write-up time:

**A family with no clan is not its own class.** Pfam leaves 1,127 viral families clanless
(`profiles`, D-075), and a singleton class republishes the per-family curve under another name.
Clanless families aggregate into one pooled class, `no_clan`, reported with its member count so
the reader sees how much is in there.

**A published class holds at least three curve subjects.** A class of one is a per-family curve;
a class of two lets a reader who knows one value derive the other. Classes below three merge
into `no_clan`, and the merge is recorded in the artefact.

`costcurve.published_view` produces this from the full artefact with no recomputation, and
`costcurve.CurveSet.disclosure_view` produces the per-family form. A consumer that wants the
published numbers never touches the per-family records, which is the point of having two
functions rather than one flag.

---

## 9. The regime boundary, pre-registered

§C6 requires the boundary fixed before anything is computed. It is fixed here, with its
reference quantity, on 2026-10-20.

Let **s\*** be the largest stringency in §6's sweep at which `H(s) ≥ 0.90` — the loosest filter
that still removes nine tenths of F's known diversity. Where no s in the sweep reaches 0.90, F is
**unreachable**: no filter in the honest range removes the family, which is a third finding and
not a missing value.

The boundary is anchored to a measured quantity rather than to a round number:

> **V = 0.011154** — the share of UniRef50 2023_02's 60,479,070 clusters that contain a viral
> seed, 674,571 of them, measured by A8.1 (`artifacts/a8-1/agreement-2023_02-uniref50.json`,
> D-200).

V is what the filters Phase A audited already cost: removing everything within 50% identity of a
viral seed removes 1.12% of UniRef50's clusters, and two laboratories shipped that. So:

| Regime | Condition at s\* | Reads as |
|---|---|---|
| **Cheap** | `C(s*) ≤ V / 100` | removing F costs less than a hundredth of what removing all of virology costs. Filtering works for F and a reviewer can reasonably require it. |
| **Intermediate** | between | filtering works at a price, and the price is the number |
| **Catastrophic** | `C(s*) ≥ V` | removing F costs at least as much general biology as removing every virus. **Filtering cannot work for F**; a different control is needed. |

Why anchor to V rather than pick a percentage: a round threshold would be this project's taste,
and §C6's claim — that a family is beyond filtering — is too strong to rest on taste. V is a
published operation's measured cost, so "catastrophic" means "more expensive than the thing the
field already does", which a reviewer can check and argue with.

**The comparison uses the lower bound of `C(s*)`'s interval against V, and its upper bound
against V/100.** A regime label is a claim; it is made at the conservative end of its own
interval, so neither label can be produced by sampling noise. A family whose interval straddles a
boundary is reported as **straddling**, with both labels named.

---

## 10. What this does not measure

- **Whether removing F removes the capability.** The curve measures what a filter removes, not
  what a model then cannot do. That is Phase B's premise and the curve inherits it: §C5 is built
  on "capability tracks homology", and if Phase B's answer is no, these curves price an operation
  whose effect on capability is unestablished. The write-up says so.
- **Structural homology below the identity floor.** A family whose relatives are detectable only
  by structure is reported as unbounded below, not as cheap.
- **Anything about a specific model.** No model is trained, fine-tuned or run anywhere in Phase C
  (§C5). The curves are a property of databases and a threshold.
- **Diversity the databases do not hold.** That is what §7's coverage pair is for, and why a
  coverage-limited family gets no regime label at all.

---

## Commands

```bash
pixi run -e dev test       # includes this file's worked examples, pinned as tests
```

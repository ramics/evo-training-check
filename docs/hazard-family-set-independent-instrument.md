# The hazard family set, rebuilt — and which detected records belong to a hazard family

**Task C5.1 · decisions D-263, D-264, D-265 · 2026-10-27**

Two things here. The hazard family set's virus stratum is rebuilt, because the previous build was
defective in two independent ways. Then it is used for the question it exists to answer: of the
records this audit detected in Evo 2's released viral component, which ones belong to a hazard
family when that is measured by biology rather than by a protein family's name.

Every number below comes from `artifacts/c5-1/`, published to `corpora/results/c5-1/`.

---

## 1. Why the previous build could not be used

**It resolved taxa by name.** Two of the nineteen denylisted virus families returned zero and
**2,904 reviewed UniProtKB entries were dropped with no error at all.** `D-137` forbids name
matching for a published list for exactly this reason. The two, and they fail by different
mechanisms:

| taxon | what happened | entries lost |
|---|---|---|
| **Reoviridae** | ICTV elevated it to the order *Reovirales* and split it into *Sedoreoviridae* and *Spinareoviridae*. In the pinned taxonomy `Reoviridae` survives **only as a synonym**, and no node of rank family bears the name. | 807 |
| **Herpesviridae** | Renamed to *Orthoherpesviridae*. Taxid 10292 still resolves, but holds **0** reviewed entries: they moved to node 3044472, which postdates the pinned taxonomy. | 2,097 |

807 + 2,097 = **2,904**, which reproduces the loss exactly and from the other direction.

The *Reoviridae* case is worth separating out, because it is a finding about the audited filter
rather than about this repo: **the published exclusion list names a virus family that did not
exist at that rank when the filter was published.** Any implementation of that rule which matches
family names removes nothing for it.

**It used only the 19 families.** `metrics/costcurve.md` §3 names 19 families **and 12 orders**.
The orders were absent.

**And it was broad in a way worth measuring rather than deleting** — see §3.

## 2. The repair

`policies/specs/hazard-virus-taxa-evo1.json` carries one curated entry per named taxon, 31 in
all. `tools/hazard_family_set.py` only *checks* the curation and never makes it:

- the recorded scientific name and rank must match `taxdmp_2023-04-01.zip`, whose digest is
  verified before it validates anything, or the run refuses;
- the spec must cover exactly the taxa the published rules name, read from
  `policies/specs/evo1-literal.yaml`, not retyped;
- **a taxon whose query returns no reviewed entries refuses the run** unless the spec curates it
  as a genuine zero. A silent zero and a real one are indistinguishable from the count alone,
  which is how the 2,904 went missing.

Each entry carries **two** taxids where the taxonomies disagree: `taxid_pinned`, validated
against the snapshot contemporaneous with the filter being audited, and `taxid_query`, the node
holding the entries today. One taxid would force a choice between validating the published name
and finding the proteins. Three taxa need both; a fourth, *Priklausovirales*, is a curated
genuine zero — stable name, stable node, no reviewed entries.

The set is **1,144 families** — 1,134 in the virus stratum, 10 in the toxin stratum (D-263), no
overlap — from **14,673 reviewed entries**.

## 3. The breadth is a column, not a deletion

481 of the 1,144 fall outside this project's pinned viral selection, and they arrive
overwhelmingly through the large-genome viruses:

| nominating taxon | families outside the viral selection |
|---|---|
| Poxviridae | 124 |
| Herpesvirales | 118 |
| Herpesviridae | 106 |
| Lefavirales | 90 |
| Ortervirales | 79 |
| Retroviridae | 73 |

These are host-derived and host-mimicking families — actin, protein kinases, the immunoglobulin
domain. Nominating by cross-reference admits them because a large-genome virus genuinely carries
them. 646 of the 1,144 are both in the viral selection and `viral_only` by the independent
background measure.

**They are reported and not removed.** §C6 fixed this set's definition *before* any computation,
and narrowing it after seeing its output is the thing that pre-registration exists to stop. But
the choice is real and it is not a formality: a hazard set containing actin counts removing actin
as hazard *benefit*, and because the collateral denominator excludes every nominated family, the
same nomination also removes actin from the collateral *cost*. Both errors point the same way,
and it is the way that flatters the safeguard. **Which reading the cost curve uses is the project
owner's call and is not made here.**

## 4. The independent instrument, and what it found

`tools/hazard_record_membership.py` asks whether a detected record's Pfam family is in this set —
whether some reviewed UniProtKB entry of a listed taxon cross-references it. **It reads no family
name.** X1.8/X1.9's axis asks whether a family's Pfam *identifier or description* refers to a
denylisted group. The two share the group list and nothing else: no matching rule, no Pfam
metadata, no code.

The classification was fixed before the join ran and **adds no threshold of this project's own**.
Every detection already clears Pfam's curated gathering cutoff; a second cutoff chosen after
seeing the scores would be this project deciding which hits count. Records are placed by
`exclusivity` — the fraction of a family's reviewed entries contributed by the listed taxa.

| class | records | of which the published rule removes |
|---|---|---|
| `hazard_family_exclusive` — exclusivity 1.0 | **100** | 16 |
| `hazard_family_shared` — nominated, below 1.0 | **218** | 1 |
| `not_nominated` | **0** | 0 |
| `unnominatable` — family has no reviewed entries | **1** | 0 |

**The independent instrument agrees with the name axis at family level, on 318 of 319 records.**
That cuts against the framing this session inherited. The Pox-named families D-261 singled out
are genuinely cross-referenced by reviewed *Poxviridae* entries: `Pox_A22` 7/7, `Pox_D5` 6/7,
`Pox_A32` 5/7. The single disagreement is not a disagreement either — `PF08284 RVP_2` has **zero**
reviewed entries, so no taxon *could* nominate it, which is a different statement from the listed
taxa not carrying it.

**So "the name axis over-counts" needs restating.** It over-counts in *strength* and
*exclusivity*, not in family identity. Two measured quantities separate the real cases:

- **Exclusivity.** `Pox_VLTF3`, the single largest contributor at 87 of the 319 records, is
  nominated and only **0.368** exclusive — 7 of its 19 reviewed entries are *Poxviridae* and the
  rest are other nucleocytoplasmic large DNA viruses and phages, which is what its own
  "VLTF3 **like**" description says.
- **Hit strength**, reported per record with no cut: median **2.70×** threshold and max **29.5×**
  in the exclusive class, against median 2.18× and max 10.7× in the shared one.

The worked example reproduces independently: `IMGVR_UViG_643677429_000001` lands in
`hazard_family_exclusive` on `PF00519` at **16.97×** threshold, identity **0.587**, coverage
**0.997** — the 17× / 0.59 / 0.997 already recorded for it. The strongest hit in the whole set,
29.5×, is `IMGVR_UViG_641201065_000001`, carrying fifteen families across a flavivirus-like
polyprotein at 0.42–0.64 identity, and the published rule removes it.

## 5. What this does not settle

**Which of these records survive into Evo 2's training data.** That needs D-262's accession list,
which was scratch and died with its container, so the per-record training column is **absent
rather than estimated**. The records in the training data are a subset of the 319 measured here,
so no record can become a hazard-family record by being in it — but the subset cannot be named
until the join is rebuilt as a citable artefact, which D-262 already records as a task of its own.

**And nothing here says a record is dangerous.** The strongest class says a record carries a
family whose reviewed membership is wholly from the listed taxa. It does not say the record is a
member of those taxa, and the region metrics show several are reached by distant homology.

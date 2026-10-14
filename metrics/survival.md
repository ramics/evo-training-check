# metrics/survival.md — the frozen survival metrics and route taxonomy

Task **A3.1** · `DESIGN.md` §A3 · Deliverable 1 · frozen 2026-10-14, DECISIONS.md D-022

This is the authoritative text for the Phase A headline numbers. It is written to be
reimplementable from this file alone, because **A3.3** is required to reimplement the headline
counts by a second method before publication (`DESIGN.md` §7) and that check is worth nothing if
the second implementation is written by reading the first. A3.3 works from this document.
`src/amazebio/survival.py` is the first implementation; A3.2 computes at corpus scale.

Frozen means frozen. These definitions were fixed before any detection ran. If one of them turns
out to be wrong, the change is a `DECISIONS.md` entry that says what was known at the time and
what changed, not an edit.

---

## 1. The unit: a viral protein family

Every headline number is per **family**, where a family is an entry in a pinned family registry.
Two registries are used and **the headline is reported once per registry and never pooled**:

| Registry key | What it is | Pinned as |
|---|---|---|
| `pfam_viral_clans` | Pfam families in the viral clans | release number + checksum |
| `rvdb` | RVDB protein clusters | release number + checksum |

Both, separately, because the denominator is a choice about where family boundaries fall and the
answer should not depend on ours. Pfam is small, curated and cleanly versioned, and families with
no Pfam profile are invisible to it — which biases family-level survival upward by an amount
Pfam alone cannot size. RVDB was built for exactly this screening purpose and covers far more,
with looser boundaries and more weakly-characterised families. Reporting both turns that
dependency into a measurement: **a gap between the two registries is itself a finding**, and the
spread between them is reported alongside the numbers in the same way A0.4 reports the spread
between policy readings. Pooling them would average away the one thing the pair is there to show.

The family universe `F_R` for registry `R` is the complete set of families in the pinned release
— not the families that happened to be detected. Every metric below takes its denominator from
`F_R`, zero-filled.

A family is a *protein* family in both registries, and nucleotide corpora are searched by
translated profile search rather than by a separate nucleotide metric, so that the Evo and ESM
results share one denominator and one headline. Taxonomic family — the unit Evo's own denylist
acts on — is a reporting axis under §4 reporting limits, never the metric's unit; the two senses
of "family" are never mixed in a table or a sentence without both being named.

## 2. Detection

A **detection** is one surviving corpus record region matched to one family by one detector at or
above that detector's declared threshold. The detectors are A2's: profile search, structural
search, element detection, and the problem-taxa sweep.

**The threshold contract.** Each detector declares, before it is run, the threshold it uses and
where that value comes from — the registry's own curated cutoff, a published benchmark, or a
choice recorded in `DECISIONS.md` with its justification. A3.2 refuses to compute any metric
while a threshold is undeclared, and refuses a threshold declared after a detection output
already exists, which is the same discipline `amazebio.repro.run` applies to pipeline parameters.
A3.1 fixes the metric definitions; each A2 task fixes its own detector's threshold, under that
contract, before it looks at results.

Thresholds are **not** swept to produce a favourable headline. Where sensitivity to the threshold
matters, it is reported as a curve over the declared value and two bracketing values fixed at the
same time, labelled as sensitivity analysis and never as the headline.

## 3. The route taxonomy

Every detection carries exactly one **route** — why that sequence is still in the corpus. Routes
partition the detections; the six are exhaustive and mutually exclusive by construction.

| Route | Meaning | How it is established |
|---|---|---|
| `out_of_scope` | The record's corpus component was never examined by the filter. | The policy spec's declared scope. Published methods only — no detection needed. |
| `retained_by_design` | In scope, examined, and the filter's stated rules keep it. | The policy predicate returns `retained` with a rule having reached the record. |
| `undetected` | In scope and the rule reaches it, but the mechanism could not see it: no label, a label too unspecific to place, or similarity below the policy threshold. | Policy evaluation plus the record's own metadata. |
| `misassigned` | In scope and labelled, but labelled wrongly, so the rule did not fire. | Detection disagrees with the record's label; A4.2 supplies the misassignment rate. |
| `conformance_failure` | In scope, labelled, the stated rule should have fired, and it did not. | A7.1, with record-level evidence attached. |
| `unresolved` | The route cannot be determined from the metadata that travels with the release. | Default when a rule's input is absent from the released records. |

Three separations in that table are deliberate and are not to be collapsed in any figure, table
or sentence:

**`out_of_scope` is first-class** (DECISIONS.md D-007). It is the strongest Phase A finding — the
filter was applied to one corpus component while the model trained on a corpus that later grew to
include whole eukaryotic genomes — and it is established from published methods, needing no new
bioinformatics. It is also the most sensitive, which is why A3.3's independent check covers the
scope claim and not only the counts.

**`retained_by_design` is not leakage.** IMG/VR's prokaryotic-host phage are retained because the
developers decided to retain them and said so. Counting that as a filter failure would be
misreading a published decision as a defect. It is reported because it is the within-corpus
contrast Phase B needs.

**`conformance_failure` is never merged** into `undetected` or `misassigned`. Those two are claims
about what taxonomy can do; this one is a claim about whether a named laboratory's implementation
matched its own published description. Different evidential standard, different remedy, and §7
requires it to be airtight.

`unresolved` is reported as its own row and never folded into another route or dropped. A1.2
established that three of Evo 1's published rules — the high-confidence gate, the vOTU
representative, and the prokaryotic-host count — cannot be checked against the released corpus
because their inputs are not in the records. Detections turning on those rules are `unresolved`,
and a table that hid them would claim more evidence than exists.

**Element kind** — `free_virus`, `prophage`, `endogenous_retroelement`, `non_retroviral_eve`,
`satellite`, `viral_derived_fragment`, `unclassified_element` — is a separate axis describing what
the sequence *is*. It is cross-tabulated against route and is never used as a route. A prophage
in a bacterial genome the filter never examined is `prophage` by kind and `out_of_scope` by route;
a prophage in a record the filter examined and kept is the same kind on a different route, and
that difference is the finding.

## 4. The metrics

### M1 — Family-level survival (the headline)

For registry `R`, let `n_f` be the number of surviving sequences detected for family `f ∈ F_R`.

```
survival(R) = |{ f ∈ F_R : n_f ≥ 1 }| / |F_R|
```

Reported with a **95% Wilson score interval** on that proportion, per registry, per model, and
per policy reading (literal / charitable / strict). Wilson rather than the normal approximation
because this proportion is expected near 0 or near 1 — a filter that works puts it near 0 — and
the normal interval is worthless there: it strays outside `[0, 1]` and its width collapses to zero
at exactly the values most likely to be reported.

**Per route.** M1 is also reported restricted to each route: survival computed over detections
carrying that route only. A family can survive by more than one route, so **the per-route figures
do not sum to the overall figure** and any table showing them carries that sentence. A reader who
adds them gets a number that means nothing.

**Worked example.** `F_R` has 5 families; detections give counts `{A: 3, B: 0, C: 1, D: 0, E: 0}`.
Then `survival(R) = 2/5 = 0.4`, Wilson 95% interval `[0.1176, 0.7693]`. Note the interval: at this
denominator the estimate carries almost no information, which is why coverage of the registry is
reported alongside it and why a small-`|F_R|` headline is not a headline.

### M2 — Surviving sequence count per family

The distribution of `n_f` over `f ∈ F_R`, reported as **median, inter-quartile range and
maximum**, with a 95% bootstrap percentile interval on the median over 10,000 resamples of
families at a declared seed. Not the mean: the distribution is expected to be heavy-tailed, a
mean would be set by a handful of large families, and §A3 is explicit that one good homolog is
what matters rather than bulk.

Reported per registry and broken down by route.

### M3 — Diversity coverage

For each surviving family, how much of that family's known diversity the surviving sequence
covers. Computed per family, with no family-level estimate pooled into a single corpus number:

1. Take the family's reference members from the pinned registry release.
2. Cluster them at **50% amino-acid identity over 80% of the shorter sequence** to give the
   family's diversity bins. Both values are part of this frozen specification; they are a
   conventional protein-family clustering point, chosen because the alternative — a tree-based
   diversity estimate — cannot be pinned to a reproducible artefact across registry releases.
3. `coverage(f) = |{ bins with ≥ 1 surviving detection }| / |bins(f)|`, with a 95% Wilson
   interval over bins.

Reported per family, per registry. The corpus-level summary is the distribution of `coverage(f)`
across surviving families — median and IQR — never a single pooled coverage figure, because a
pooled figure at this sample size is exactly the fragility `DESIGN.md` §B5 warns about and
`AGENTS.md` makes per-unit reporting the default for.

## 5. Why raw sequence volume is not the headline

Base pairs, or sequence counts, would be the obvious metric and they are the wrong one.

- **They answer a question nobody is asking.** The concern is whether the model can learn a
  capability, and §A3's one-line statement of it is that one good homolog teaches a fold. A
  corpus holding a single well-conserved representative of every viral protein family has lost
  almost all its viral bp and none of the capability.
- **The two metrics disagree in the direction that matters.** A filter removing 99.9% of viral bp
  while leaving one homolog per family reports a 0.1% survival rate on bp and near 100% on
  family-level survival. The bp figure would read as a filter that works.
- **Volume tracks corpus composition, not filter performance.** The denominator grows with every
  genome added to the corpus, so the same filter on the same viral content scores better the
  larger the corpus gets — which inverts the actual finding, since the scope gap opened precisely
  *because* the corpus grew.

Volume is reported, as context, alongside M1–M3 and never as the headline. Where a volume figure
appears it is labelled with what it does not mean.

## 6. Keeping a null result visible

`DESIGN.md` §2 and `AGENTS.md` both require that a null — the filter removes what it claims to —
be publishable and not harder to see than a positive. Three specific consequences bind here:

- **Zero-detection families stay in the denominator.** Counts are zero-filled across the whole
  pinned `F_R`. A count table assembled only from families that were detected would turn a null
  into missing data.
- **No minimum-count filtering of families, ever.** Dropping families below a count threshold
  raises M1 mechanically.
- **An interval that spans the interesting range is reported as such.** A headline whose interval
  includes both "filter works" and "filter does not work" is reported as uninformative in the
  abstract, not presented as a point estimate with the interval in a footnote.

## 7. What is reported, and what is not

Per `DESIGN.md` §4 reporting limits, every number here goes out broken down by homology class,
fold family and survival route. **No ranking of which model is most capable for which pathogen is
published**, and no table in this project is arranged so one could be read off it.

---

## Commands

```bash
pixi run -e dev test       # includes the worked examples in §4, pinned as tests
```

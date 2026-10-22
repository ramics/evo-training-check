# A4.5 — occurrence of the pinned viral families outside viruses

Universe: 1719 Pfam 38.2 families (the pre-registered viral selection, unchanged).
Background: UniProtKB reviewed section 2026_03, 575748 entries read (17529 of them viral).

| class | families | share of universe |
|---|---|---|
| `viral_only` | 1265 | 73.6% |
| `shared` | 212 | 12.3% |
| `unmeasurable` | 242 | 14.1% |

Of the 1477 families the curated section can speak to, 1265 (85.6%) have no curated occurrence outside viruses and 212 (14.4%) do.
Of those 212, 15 have every non-viral occurrence marked by the curators as integrated viral material, so the sharing is a host genome carrying the element rather than the family having cellular members.
Median distinct non-viral organisms behind a shared family: 1.0.

Second instrument: 1719 of 1719 families classed the same way by InterPro's own join (0 disagreements).

## What the selection vocabulary matched inside

7 families are in the universe only because a keyword is a substring of a word naming nothing viral (macrophage): PF01109, PF01187, PF01566, PF03523, PF05337, PF06761, PF22420.

113 families have no curated viral entry at all while having at least one curated cellular entry.

the 1,719 universe is pre-registered and is not corrected here. A cellular family in it contributes a near-certain zero, so it pushes the survival fraction down: the denominator is conservative, not inflated.

## The detected sets

**opengenome, profile-hmmer** — 590 detected families: 303 with no curated non-viral occurrence, 135 shared, 152 unjudgeable.

Among the 438 the curated section can judge, 30.8% are shared, against 14.4% over the whole universe — 2.15 times as often. Detected families are not a random draw from the universe, and this is the direction of the difference: a family with cellular members is easier to detect, so weighting by what was found makes the sharing commoner rather than rarer.

| variant | excluding unjudgeable | including unjudgeable |
|---|---|---|
| `headline` | 590 | 590 |
| `specific` | 303 | 455 |
| `specific_plus_endogenous` | 307 | 459 |

**opengenome, profile-hmmer+provirus-genomad** — 597 detected families: 310 with no curated non-viral occurrence, 135 shared, 152 unjudgeable.

Among the 445 the curated section can judge, 30.3% are shared, against 14.4% over the whole universe — 2.11 times as often. Detected families are not a random draw from the universe, and this is the direction of the difference: a family with cellular members is easier to detect, so weighting by what was found makes the sharing commoner rather than rarer.

| variant | excluding unjudgeable | including unjudgeable |
|---|---|---|
| `headline` | 597 | 597 |
| `specific` | 310 | 462 |
| `specific_plus_endogenous` | 314 | 466 |

**opengenome2, profile-hmmer** — 811 detected families: 497 with no curated non-viral occurrence, 145 shared, 169 unjudgeable.

Among the 642 the curated section can judge, 22.6% are shared, against 14.4% over the whole universe — 1.57 times as often. Detected families are not a random draw from the universe, and this is the direction of the difference: a family with cellular members is easier to detect, so weighting by what was found makes the sharing commoner rather than rarer.

| variant | excluding unjudgeable | including unjudgeable |
|---|---|---|
| `headline` | 811 | 811 |
| `specific` | 497 | 666 |
| `specific_plus_endogenous` | 506 | 675 |

**opengenome2, profile-hmmer+provirus-genomad** — 812 detected families: 498 with no curated non-viral occurrence, 145 shared, 169 unjudgeable.

Among the 643 the curated section can judge, 22.6% are shared, against 14.4% over the whole universe — 1.57 times as often. Detected families are not a random draw from the universe, and this is the direction of the difference: a family with cellular members is easier to detect, so weighting by what was found makes the sharing commoner rather than rarer.

| variant | excluding unjudgeable | including unjudgeable |
|---|---|---|
| `headline` | 812 | 812 |
| `specific` | 498 | 667 |
| `specific_plus_endogenous` | 507 | 676 |


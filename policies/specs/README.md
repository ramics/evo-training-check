# policies/specs/ — the frozen policy readings

Each published filter policy, encoded three times as an executable predicate: **literal**,
**charitable**, **strict**, as `DESIGN.md` §A0 requires. The schema is `amazebio.policyspec`
(task A0.2); these files are task A0.3.

The spread between the three readings *is* a finding. If they differ substantially in what
survives, the policy as published is not reproducible, and that matters for any governance
framework that would mandate it. A0.4 reports the spread; A1.4 applies the predicates to the
reconstructed corpora; A7.1 diffs them against what the developers actually released.

## The six readings

| Spec id | Model | Reading | Scope | Determined |
|---|---|---|---|---|
| `evo1-literal` | Evo 1, inherited by Evo 2 | literal | `IMG/VR` | yes |
| `evo1-charitable` | Evo 1, inherited by Evo 2 | charitable | `IMG/VR` | yes |
| `evo1-strict` | Evo 1, inherited by Evo 2 | strict | whole corpus | yes |
| `esm3-open-literal` | ESM3-open | literal | the 4 named databases | **no** — threshold unpublished |
| `esm3-open-charitable` | ESM3-open | charitable | whole corpus | yes — threshold read as 0.70 |
| `esm3-open-strict` | ESM3-open | strict | whole corpus | yes — any detected hit |

ESM-2 and ESM-C have no specs because they state no exclusion: ESM-2 is the positive control and
ESM-C is a viruses-included comparison (`policies/esm2.md`, `policies/esm-c.md`). A model with a
spec must have all three readings — `tools/specs.py` fails otherwise, and a test asserts the six
ids above, because downstream tasks reference readings by id and a rename silently rewires them.

## Where the readings differ, and where they deliberately do not

Each reading moves on a stated axis, and every move is traceable to published wording — the
per-rule `note` fields carry the argument and the file headers carry the reasoning in full.

**Evo.** The literal reading is the Evo 1 Appendix B.2 pipeline applied to the component it is
described as applied to. The charitable reading adds a direct host-range predicate, because the
stated aim is about viruses that infect eukaryotic hosts and the published implementation reaches
that aim only through a prokaryotic-host count and a clade enumeration. The strict reading takes
the authors' own statement of purpose — that the openly shared model should not disseminate a
capability — as a claim about the whole training corpus, so it runs corpus-wide, requires host
evidence that is positively and exclusively prokaryotic, and reaches viral-derived sequence that
carries no viral label at all (endogenous elements in host genomes, which no retrieved source
addresses in either direction).

**ESM3-open.** The literal reading is the paper's "sequences unique to viruses" against the four
named databases, and it is **not decidable**: the identity threshold that sets the filter's entire
reach is never published. The charitable reading applies the filter to "the full set of training
databases" as the same sentence says, and reads the threshold as 0.70 — the only identity figure
the paper ever ties to the Viral Denylist, which it uses to define its own held-out viral
evaluation set. The strict reading holds the developers to their model card's broader claim that
"data related to viruses has been removed", which drops the "aligns almost exclusively to viral
sequences" narrowing from the seed set and reads the threshold at its most inclusive. The three
thresholds bound the sweep A7.1 needs; none of them is the authors' value, and the charitable
0.70 is the weakest inference in this directory (DECISIONS.md D-015).

**What no reading does.** No reading adds a clade, an organism or a sequence that the published
source does not name. Every taxon in these files is quoted from the source; the readings differ in
how far the published words reach, never in our own view of which organisms are dangerous. A
denylist of our own authorship would be untraceable, outside `DESIGN.md` §4, and not the thing
under audit. Relatedly, the strict Evo reading does not touch phage: IMG/VR is described in the
source as curated prokaryotic viruses and their retention is deliberate, so removing them would
contradict a published decision rather than read it strictly — and phage retention is what gives
Phase A its within-corpus contrast. "Strict" means the broadest defensible reading of the stated
aim, not the largest filter expressible in the schema.

## Commands

```bash
python3 tools/specs.py              # validate every spec; check the three-readings contract
python3 tools/specs.py --describe   # render each reading as prose, to eyeball against the source
```

`tools/specs.py` fails if a rule cites a source that `policies/sources.json` does not record as
retrieved, which is the same guarantee `tools/policies.py` gives for quotes, one level up.

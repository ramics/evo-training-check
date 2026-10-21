# The paragraph nobody checks

**What happens when you take a model release's data-filtering claim and try to verify it against
the artefact it produced.**

Draft of 2026-10-21. Internal to the project: `AGENTS.md` holds findings inside the project until
the responsible-disclosure task (X3.1) has run, and that gate has not opened. Written for a
reader who is comfortable with software, statistics and the AI-safety literature, and who knows
no biology. Sources are listed at the end; claims about this project's own measurements are cited
to the task and decision identifiers that carry them, which are not yet public.

---

## A paragraph everyone trusts and nobody checks

Somewhere in the release materials of most frontier biological sequence models there is a short
paragraph about what was removed from the training data. It names a public database, names a list
of organisms the authors judged hazardous, and gives a rule or two for what counts as too close
to something on that list. The two Evo releases are the clearest case to work with, because both
state such a policy and both publish their training corpora openly, as `OpenGenome` and
`OpenGenome2` [1-4].

Both Evo releases state the exclusion in the same terms — "we excluded viral genomes that infect
eukaryotic hosts", with the stated aim that the openly shared model would not "disseminate the
capability to manipulate and design pathogenic human viruses" — and implement it, per the
methods, as a host-association rule followed by named lists of 19 families and 12 orders [1,2].

That paragraph is load-bearing. It is the reason a release can be described as having handled a
category of risk at the data layer, which is the cheapest and most durable place to handle it. It
gets cited in policy conversations, in governance frameworks, and in arguments about whether open
weights are safe to publish. A great deal of inference rests on a few sentences of prose.

Almost none of it is checked, and the reasons are mundane rather than sinister. The policy is
prose, not code, so there is nothing to run. The filter's implementation is usually not released.
The corpora are tens of millions of records, so nobody reads them. And the people best placed to
check — the authors — have already done the work once and have no reason to audit themselves.

So three questions sit open:

1. **Is the stated policy executable at all?** Prose admits more than one reading. Does the choice
   of reading change what gets removed?
2. **Does the released artefact match the stated policy?** If a category is said to be absent, is
   it absent from the files anyone can download?
3. **How much could the policy ever have removed?** A rule keyed on a metadata field can only act
   on records that carry that field. Nobody had measured that ceiling.

This project — Phase A of it — is an attempt to answer those three questions for real releases,
with every number traceable to an artefact that can be regenerated from pinned inputs. It is
measurement, not adversarial work: it builds nothing, attacks nothing, and treats a gap between a
stated procedure and a published artefact as a provenance and documentation problem.

## What it takes to check a sentence

The method has four parts, and the engineering in each is the kind that decides whether the
answer means anything.

**Turn the paragraph into a specification.** Each published statement was transcribed into a
machine-checkable spec whose quotations are verified byte-for-byte against a stored capture of the
source, so a quote cannot drift from what the source says. Each spec then becomes *three*
executable readings — literal, charitable and strict — because the prose genuinely admits all
three, and the spread between readings is reported as a result instead of being hidden inside a
choice.

**Stream the released corpus through the policy.** Every record is passed through each reading and
comes out labelled: removed by this rule, retained, or — the important third category —
*unresolved*, because the release does not carry the metadata that rule reads. Keeping "no
verdict" as its own outcome is the single most consequential design decision in the audit. The
tempting alternative, treating an absent metadata channel as empty rather than missing, would have
reported an entire component as cleanly removed by a rule whose input nobody can see: a pass
manufactured out of missing data.

**Search what survives for the material the policy says it excluded.** Surviving records are
translated into their protein content with a standard gene caller [5,6] and searched with profile
hidden Markov models [7] against two independent, version-pinned public registries of sequence
families: Pfam 38.2, of whose 30,134 families 1,719 are viral [8], and RVDB-prot v32.0, with
13,679 families [9]. Thresholds were fixed and recorded *before* any result was looked at. A
second detection route looks for material integrated into bacterial genomes rather than
free-standing.

**Re-derive the headline with a second implementation.** The project's own rule is that a headline
number is not a result until a module written without reading the first implementation reproduces
it from different intermediate objects: primitive detection rows rather than aggregates,
denominators rebuilt from the pinned registry files, the policy re-executed independently. 334
numbers were compared across 16 reported groups. Every headline figure agreed exactly, and the one
surviving disagreement — in how a family's records are apportioned between detection routes — is
published with the single family that accounts for most of it (A3.3, D-215).

## Finding 1: a filter can only see a sliver of its own input

The Evo exclusion rules name organism groups at two taxonomic ranks. The database they were
applied to, IMG/VR [10], labels its records richly at coarse ranks and sparsely at exactly the two
ranks the rules use. Across all 15,677,623 records in the release:

| rank | records labelled | share |
|---|---|---|
| realm | 15,157,100 | 96.68% |
| class | 14,965,115 | 95.46% |
| **order** | 1,359,211 | **8.67%** |
| **family** | 979,864 | **6.25%** |
| genus | 32,729 | 0.21% |

So the 19-family exclusion list can discriminate on 6.25% of the release and the 12-order list on
8.67%. Measured over the population those rules are actually handed — after an earlier confidence
step which keeps 5,576,197 records — the figures are 7.87% and 8.85%. A companion rule about host
association can be evaluated on 13.71% of that population and removes the remainder *for lacking
the evidence*, which is a different act from examining them (A4.1, D-081).

Note what the finding is not. 3.29% of records carry no label at all, and reporting *that* as the
headline would have been the easy mistake. The component is not badly annotated; it is annotated
at the wrong ranks for the rules written against it.

This is the most transferable result in Phase A. It does not depend on anything biological, it
applies to any exclusion filter keyed on third-party metadata, and computing it for a new filter
is an afternoon's work: take the rule's key field, count how many records in the target database
carry it, and report the share both over the database and over the population the rule actually
sees. Any release that states a metadata-keyed exclusion policy could publish that number
alongside it, and none does.

## Finding 2: material the policy excludes is detectably present in what was released

Searching the surviving records against the curated registry finds, at the depth sampled:

| release | records searched | viral families detected (of 1,719) |
|---|---|---|
| Evo 1 (`opengenome`) | 53,140 of 2,653,047 (2%) | **597** (34.7%) |
| Evo 2 (`opengenome2`) | 30,859 (1%) | **812** (47.2%) |

The profile search alone accounts for 590 and 811; the remainder come from the integrated-element
route (A2.1, A3.2, D-245, D-246). Three qualifications travel with these numbers wherever they go.

**They are lower bounds.** A family is counted only when a sampled record carried it. Whatever the
sample missed is missing from the count and present in the corpus. The honest form of the claim is
*at least this much, and the ceiling was not found*.

**The ceiling really was not found.** When the sample was deepened tenfold the counts rose steeply
instead of settling — Evo 1 from 470 families to 590, Evo 2 from 492 to 811 — and the accumulation
curve was still climbing on the last doubling of records searched (+9% and +18%). A quantity that
nearly doubles when you look twice as hard is a floor, not an estimate.

**The two releases are not comparable as rates.** Evo 2 reaches 812 families while being sampled
at a *tenth* of Evo 1's rate. Whatever differs between the releases, this table does not measure
it. (There is a structural reason the second corpus is richer per unit of sequence — the first
publishes a deduplicated subset of the same source database — and that explanation was in hand
before the measurement rather than invented to fit it.)

A deliberately stricter question is kept separate: how many records survive a rule the release's
own metadata is *sufficient* to evaluate? The answer is 95 of 2,653,047, all through a single
clause about unassigned classification (A7.1). Presence in the corpus and demonstrable
non-conformance with the written policy are different claims with different evidential bars, and
only the second is an inconsistency finding. It is small, and saying so is part of the result.

**A stated limitation on the second registry.** The two registries were searched at the same
per-release rates, but only the curated one has since been deepened tenfold. At equal depth the
pair reads:

| release (shared sampling rate) | Pfam viral, of 1,719 | RVDB-prot, of 13,679 |
|---|---|---|
| Evo 1, rate 0.002 | 470 (27.3%) | 582 (4.25%) |
| Evo 2, rate 0.001 | 492 (28.6%) | 1,483 (10.84%) |

That equal-depth pair is what any comparison between registries should be read from. The deepened
curated figures answer a different question — what happens to one registry's bound when you
sample ten times harder — and setting the deepened 34.7% beside the shallow 4.25% would read a
sampling artefact as a finding. The two registries were in any case never poolable: different
family definitions, different denominators, one nucleotide-derived and one protein-level. Depth is
a third reason on a list that already ruled out reading one against the other. Deepening the
second registry is costed and deliberately deferred; see §"What a funded continuation buys".

## Finding 3: the artefact you can audit is not the artefact that was trained on

This started as the project's most alarming number and ended as its most consequential one.

Evo 2's released viral component is published twice, in two different file formats. The arithmetic
between the two suggested that 264,570 records which the published procedure removes had
nonetheless reached the training data. Phase A's job was to rule that in or out, so it counted
both representations twice, the second time by newline counting and byte arithmetic that never
decodes or parses the content at all.

The alarming reading is **wrong, and the correct reading matters more**. The representation that
was trained on matches Evo 1's released filtered output exactly — to the record and to the
nucleotide, zero difference on both deltas. The filter's output was carried forward unchanged. But
the *other* representation, the only one carrying the source identifiers against which a filter
can be checked at all, holds **304,448 more records** and 2.64 billion more nucleotides, among
them the ones the published procedure removes (A7.3, A7.4).

So: the filter demonstrably did its job on what was trained, and the only artefact anyone can
verify that against is a different, larger set. The filter cannot be checked against the thing the
filter produced. Nothing in the data speaks to anyone's intent and the project says so explicitly
— two representations of one component is an ordinary engineering convenience, and the
consequence for auditability was probably invisible from inside.

Along the way a second apparent anomaly dissolved: 39,974 "repeated accessions" turned out to be
39,974 surplus FASTA headers on 1,775 large genomes published in contigs, with zero surplus
records (D-225). Reporting it as duplication would have been wrong, and checking it cost a day.

This is the finding most likely to change practice, because the remedy is nearly free: publish the
filtered artefact in the representation that carries identifiers, or publish the removal list.
Phase A's companion output is a fourteen-item disclosure standard in which every item exists
because a specific audit obstacle produced it (X5.1).

## Why you should believe any of this

The case for trusting these numbers is not that the work was careful. It is that the project has
caught its own serious errors, that the instruments which caught them were built before they were
needed, and that the corrections sit in an append-only log next to the claims they replace. Three
examples, all from the past two days, all embarrassing:

**A headline was 32% too high, and four internal checks passed over it.** The deepened search runs
in bands, and the code reassembling the bands named its output files by policy and registry but
not by release — so both releases' rows landed in one file and each release counted the other's
detections. The inflated figure passed the project's checks on band tiling, sample nesting,
per-source counts and denominator, because each of those asks whether a result has the right
*shape* and none asks whether a row belongs to the corpus the result is about. What caught it was
re-running the whole pass from its pins: the band parts reproduced exactly and the assembly did
not. A second, independent fault in the same area surfaced the same evening — commit-keyed
provenance copies of each table, written for a good reason, were being read back in and silently
restored superseded rows — and it was found by asking which objects the pass had read rather than
whether its output looked plausible. The corrected figures are those in Finding 2, and they turn
out to equal the project's own earlier prose figures, which an intervening correction had wrongly
withdrawn (D-245, D-246).

**Every protein score the project had produced was computed on a truncated sequence.** The
zero-shot scoring harness for the next phase built each model input by hand, encoded the opening
token as a *count* rather than an identifier, and never appended the token marking the end of the
sequence. The checkpoints are trained with both, so every protein had been scored as if it stopped
early. It was found by the project's requirement that the harness reproduce a published reference
column wherever one exists [11]: agreement sat persistently just below the acceptance floor, and
regressing the disagreement position by position showed it concentrated in the last few residues
of every assay and worst on the shortest construct — the signature of a truncation. On the worst
assay the fix moved agreement with the published column from 0.9359 to 0.9994. Every earlier score
was recomputed and none of the pre-fix numbers is cited anywhere (D-230).

**A compute failure that published nothing, written up as a failure.** An attempt at the full
census ran two machines for fourteen hours, cost about $5.40 and produced no output, because
results were written only when a whole band finished and the machines were powered off from
outside the script before any band did. It is in the log with its cost, its cause, and the
correction that a run which cannot finish must still leave a record (D-233, D-234).

The general rule the project works to is that a figure is prose until it can be regenerated from
pinned inputs, and all three of these were caught by instruments built to enforce it. The second
rule, learned the hard way this week, is that checks on a result's shape do not catch a result
assembled from the wrong rows, and re-running a pass from its pins is the only instrument that
does.

## What this does not show

- **Nothing about intent.** The measurements support a mismatch between a stated procedure and a
  published artefact. They say nothing about what anyone meant to do.
- **No claim that a filter failed to run.** On the one release where it can be checked, the
  filter's output was carried forward exactly.
- **No capability claim.** That a sequence family is present in a corpus is not a statement that a
  model trained on that corpus can do anything in particular. That is the next phase's question,
  measured against published benchmarks, and it is not answered here.
- **Not population figures.** Every survival count is a lower bound from a 1–2% sample.
- **One model family, properly.** The nucleotide work covers two releases of one family. The
  protein-model arm is a policy comparison and a staged proxy corpus, not an audit of a released
  protein corpus.
- **Agreement between readings is not reproducibility.** On these corpora the literal, charitable
  and strict readings return identical counts. That is a fact about this corpus's metadata, not a
  general finding about the prose (D-221).

## What a funded continuation buys

Phase A was built by one person with cloud compute measured in single-digit dollars. That is worth
stating plainly, because it sets the scale of what follows: the obstacles here are skilled time
and engineering discipline, not hardware. Four items, in the order I would spend on them.

**1. Turn the lower bounds into population figures.** The survival counts come from a 1–2% sample
of a corpus whose accumulation curve has not flattened. A full pass against the curated registry
is a few thousand core-hours — tens of dollars at spot prices. The obstacle is not money but the
engineering the failed attempt exposed: publish per chunk, sync logs on a timer, time one band
before launching sixteen. This converts the headline from "at least 34.7% and 47.2%" into a
measured value, and it is the highest-value purchase in the project.

**2. Deepen the second registry.** About ten hours of local compute and no money, deliberately
not spent yet: an equal-depth comparison already exists for free (Finding 2), and a second deep
number would carry exactly the structural risk that produced the 32% error, with no second
instrument available to catch it, since a ten-hour pass cannot be re-run from pins as a matter of
routine. Funded, it comes with the three guards that make it safe — a separate output directory
per release, an accession-prefix check of every published table against the release it claims to
describe, and retained band parts — and it raises a bound that is currently a tenth as deep as its
neighbour.

**3. Extend beyond one model family.** The audit is packaged behind a single interface that takes a
policy, a corpus and a set of detectors, and runs against a bundled fixture in one command. The
marginal cost of auditing the next release is staging its corpus and transcribing its policy. Both
the disclosure standard and the metadata-ceiling finding gain most of their force from breadth:
one release is an anecdote, six is a practice.

**4. Run the disclosure process properly.** Nothing here has left the project, by the project's own
rule, and nothing should until the organisations concerned have been contacted and given time to
respond. Doing that well takes weeks of calendar time and a person who will write carefully and
wait. It is the step that decides whether the work changes anything, and it is the least
automatable part of it.

### What the work demonstrates, as distinct from what it found

Three things, and they are the reason to fund the person rather than only the project. The audit
exists as reusable tooling with pinned inputs and a second-implementation requirement, rather than
as a notebook that produced a number once. Its most transferable finding is a method — count what
share of a database a rule's key field can even reach — that any lab can apply to any
metadata-keyed filter in an afternoon. And its error record shows the failure mode that actually
threatens this kind of evaluation: not a wrong model or a bad threshold, but an assembly step that
mixes two corpora while every check on the result's shape passes. Knowing where that bites, and
having built the instrument that catches it, is most of what evaluation competence consists of.

## Provenance

Every figure traces to a task file, a pinned artefact and a numbered entry in an append-only
decision log which records corrections as new entries rather than edits; the withdrawn versions
and the reasoning that withdrew them stay visible. Registries are pinned by release directory and
digest, the environment is pinned, and detection thresholds were recorded before any result was
inspected. The one set of figures quoted here that is still prose rather than a regenerated
artefact is the deepened second-registry pass, which is why it appears only as a direction and a
costed next step.

## References

1. Nguyen E. *et al.* Sequence modeling and design from molecular to genome scale with Evo.
   *Science* (2024). doi:[10.1126/science.ado9336](https://doi.org/10.1126/science.ado9336)
2. Brixi G. *et al.* Genome modelling and design across all domains of life with Evo 2.
   *Nature* (2026). doi:[10.1038/s41586-026-10176-5](https://doi.org/10.1038/s41586-026-10176-5);
   preprint doi:[10.1101/2025.02.18.638918](https://doi.org/10.1101/2025.02.18.638918)
3. `LongSafari/open-genome` dataset card, HuggingFace (OpenGenome v1), retrieved 2026-10-13 and
   stored with digest as source `S-OPENGENOME1-CARD`.
4. `arcinstitute/opengenome2` dataset card, HuggingFace, retrieved 2026-10-13 and stored with
   digest as source `S-OPENGENOME2-CARD`.
5. Hyatt D. *et al.* Prodigal: prokaryotic gene recognition and translation initiation site
   identification. *BMC Bioinformatics* **11**, 119 (2010).
   doi:[10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119)
6. Larralde M. Pyrodigal: Python bindings and interface to Prodigal. *Journal of Open Source
   Software* **7**(72), 4296 (2022). doi:[10.21105/joss.04296](https://doi.org/10.21105/joss.04296)
7. Eddy S. R. Accelerated profile HMM searches. *PLoS Computational Biology* **7**(10), e1002195
   (2011). doi:[10.1371/journal.pcbi.1002195](https://doi.org/10.1371/journal.pcbi.1002195)
8. Mistry J. *et al.* Pfam: the protein families database in 2021. *Nucleic Acids Research*
   **49**(D1), D412–D419 (2021). doi:[10.1093/nar/gkaa913](https://doi.org/10.1093/nar/gkaa913).
   This project pins release 38.2 (EMBL-EBI, 2026-01-22) by versioned release directory and digest
   (D-075).
9. Bigot T., Temmam S., Pérot P., Eloit M. RVDB-prot, a reference viral protein database and its
   HMM profiles. *F1000Research* **8**, 530 (2019; v2 2020).
   doi:[10.12688/f1000research.18776.2](https://doi.org/10.12688/f1000research.18776.2).
   This project pins v32.0, 13,679 profiles, against the release's own metadata file (D-075).
10. Camargo A. P. *et al.* IMG/VR v4: an expanded database of uncultivated virus genomes within a
    framework of extensive functional, taxonomic, and ecological metadata. *Nucleic Acids
    Research* (2023). doi:[10.1093/nar/gkac1037](https://doi.org/10.1093/nar/gkac1037)
11. Notin P. *et al.* ProteinGym: large-scale benchmarks for protein fitness prediction and
    design. *Advances in Neural Information Processing Systems* **36** (2023). Used here only as
    the published reference column the scoring harness is required to reproduce.

Internal identifiers of the form A2.1, A7.3, X5.1 (tasks) and D-075, D-230, D-245 (decisions)
refer to this project's own task files and decision log, which are not public.

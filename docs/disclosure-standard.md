# A disclosure standard for training-data filters

**Deliverable 8 · `DESIGN.md` §10 · task X5.1**

Exclusion-based data filtering is being written into governance as a primary safeguard for
open-weight biological models, and a reviewer asked to judge one has no criterion today. This
document proposes the minimum a developer must publish for a filter to be independently
auditable, scores the four models in this audit against it, and publishes this project's own
filter specifications in the same format.

Every requirement below is derived from an obstacle this audit actually hit. None is derived
from first principles, and the obstacle is named with each one so a reader can judge whether
the requirement earns its place. Where the obstacle is quoted, the quotation is in
`policies/`, checked against its source by `tools/policies.py`; this document cites the policy
file and the source id rather than re-quoting, so there is one place a quotation can be wrong.

**On tone, once and then not again.** Every gap recorded here is an absence of convention, not
misconduct. There is no standard for what a filter disclosure must contain, so no developer
has failed to meet one. Two of the four models here publish a filter at all, which is more
than the field asks of them. The point of the exercise is that a filter nobody can check is a
safeguard nobody can rely on, and that is a property of the convention rather than of the
people working inside it.

---

## 1. The checklist

Fourteen items in five groups. A filter disclosure meets the standard when a competent reader
with no access to the developer can, from published material alone, (a) say what the filter
would remove from a named input, (b) re-execute it, and (c) check the released artefact
against its own stated procedure.

Each item states the requirement, the obstacle that produced it, and what compliance costs —
because a standard nobody can afford is a standard nobody adopts, and almost all of these cost
a sentence.

### Group A — Scope

**A1. Enumerate every corpus component, and mark each one applied or not applied.**

*Obstacle.* Evo's published procedure operates on the IMG/VR viral component
(`policies/evo.md` §2). OpenGenome2 added whole eukaryotic reference genomes whose published
curation contains no viral screening step, and that component is 82% of the release while the
component the procedure acts on is 0.2% (`policies/evo.md` §5, §7). Nothing published says
whether the filter was extended; a reader cannot distinguish "not applied" from "applied and
not mentioned". ESM3 has the same gap in a different shape: its scope sentence names PDB,
UniRef, MGnify and JGI prefixed by *including*, leaving OAS, AlphaFoldDB and ESMAtlas — 439M
of 3,379M unique samples — unaddressed either way (`policies/esm3-open.md` §6, fourth
finding).

*Requirement.* A list of components, exhaustive, each marked applied or not applied. The word
"including" is not an enumeration.

*Cost.* A table with as many rows as the corpus has components.

**A2. Name the released artefacts the filter was applied to.**

*Obstacle.* This one is largely met and is listed because it is the item that makes every
other one actionable, and because it is cheap to lose. ESM3 states that the filtering applies
to ESM3-open specifically and reports a comparison against an unfiltered compute-matched model
(`policies/esm3-open.md` §3). Evo 2 states the exclusion as applied to the pretraining data of
the released model and releases the dataset alongside it (`policies/evo.md` §3).

*Requirement.* Name the checkpoints and the released datasets the filter produced, so the
audit has a subject.

*Cost.* A sentence.

### Group B — The rule

**B1. One operative predicate, stated once, over named fields.**

*Obstacle.* Across the two Evo papers the exclusion is stated ten distinct ways, and no two of
them delimit the same class: on whole viral genomes, on genomic sequences of or from viruses,
on a database subset, on a capacity to infect, on a likelihood of infecting
(`policies/evo.md` §1). One of the ten — the operational rule at Evo 1 p32 — is executable;
the other nine are prose that a reader may reasonably take as the policy. ESM3 has the same
problem across two documents rather than within one: the model card says "data related to
viruses", the paper says "sequences unique to viruses", and these denote materially different
sets (`policies/esm3-open.md` §1, §5 item 3).

*Requirement.* One statement is the operative one and is marked as such. The others are
subordinate to it, or they are not published.

*Cost.* A sentence identifying which statement governs. This project's own A0.3 readings exist
only because that sentence is missing.

**B2. Every threshold and parameter, with its value.**

*Obstacle.* ESM3's filter removes sequences that align to a denylist "at or above a given
sequence identity threshold", and the value is never stated. The whole filter's reach is that
one number, and without it the filter cannot be reproduced at all — the single largest
under-specification across all four policies (`policies/esm3-open.md` §5 item 1). The
denylist's own inclusion criterion depends on an unquantified "almost exclusively"
(`policies/esm3-open.md` §5 item 2). Evo's host-occurrence rule, by contrast, states its
threshold — "at least twice" — and is reproducible because of it (`policies/evo.md` §2).

*Requirement.* Every numeric parameter the rule turns on, with its value. A justification is
welcome and is not what this item asks for.

*Cost.* A number.

**B3. State the property the filter tests for, alongside the field it reads.**

*Obstacle.* Evo 1's rule removes records "with poor taxonomic specificity" and implements that
as a test on the finest assigned rank. A1.7 measured the divergence on real records: the
published realm test is not a specificity test, and the release proves it on 95 records
(D-051). The two readings coincide while a taxonomy is settled and diverge exactly where it is
not — which is where the records nobody has placed live.

*Requirement.* The intended property and the implemented test, both stated. A reader can then
see where they come apart instead of discovering it empirically.

*Cost.* A clause.

**B4. Publish the order of order-dependent steps.**

*Obstacle.* Evo's procedure is a sequence of filters over a set that earlier steps have already
reduced — high-confidence retention, one representative per vOTU, the host-occurrence rule,
two denylists, the specificity rule. A7.2 found the vOTU step order-dependent in a way that
changes what a re-execution produces, and the published text does not fix the order
(D-067).

*Requirement.* The order, and for each step what it consumes.

*Cost.* A numbered list, which the procedure very nearly is already.

### Group C — Inputs

**C1. Cite annotation sources as dated releases with digests, not as version strings.**

*Obstacle.* Evo 1's procedure cites "IMG/VR v4". That string names two releases, issued three
months apart, and they disagree on exactly the metadata field the procedure gates on; the
citation cannot distinguish them (D-052, D-063). A citation is not a pin.

*Requirement.* The dated release, and the digest the publisher provides for it where one
exists.

*Cost.* A date. Where the publisher serves no dated, checksummed release — as with JGI's IMG/M
v.7, which is why ESM3's largest sequence component is unreconstructible
(`policies/esm3-open.md` §6, third finding) — say that, which is item E2.

**C2. Name the evidence an exclusion criterion rests on, and what that evidence can express.**

*Obstacle.* Evo's exclusion is stated over host range, and the host-range evidence it reads —
IMG/VR's host metadata — names no eukaryotic host at all. A7.2 measured the consequence: the
reading spread across the charitable, literal and strict readings is exactly zero, because the
field cannot represent the excluded category (D-072). An exclusion criterion stated over a
field that cannot express the thing excluded is unauditable in a way no amount of re-execution
fixes.

*Requirement.* Which evidence source the criterion reads, and what categories that source is
able to express.

*Cost.* A sentence, and a moment's thought that is the real value of the item.

**C3. Tool versions and invocation.**

*Obstacle.* ESM3's filter is an MMseqs2 query, with no version and no flags
(`policies/esm3-open.md` §2). Alignment tool defaults move between versions, and coverage mode
and sensitivity change what a search finds; the count the paper reports cannot be reproduced
without them. The same paper shows the standard being met elsewhere in its own text, stating
`--cov-mode 1 -c 0.8` for its clustering (`policies/esm3-open.md` §6, second finding), so this
is a matter of applying one document's own convention to its filter section.

*Requirement.* Tool, version, and the invocation.

*Cost.* A command line.

### Group D — Evidence, and checkability

**D1. Report removal counts per component, against a denominator that reconciles to the named
release.**

*Obstacle.* ESM3 reports that the filter removes 10.6M sequences across all training sets
(`policies/esm3-open.md` §2). The corpus sizes the same paper states are 14.7M short of
UniRef90's published cluster count and 108.2M short of MGnify's — each shortfall on its own
larger than the total the filter is reported to have removed everywhere
(`policies/esm3-open.md` §6, second finding). Either the re-clustering produced different
counts or more was removed than the description accounts for, and the published text does not
choose. The consequence is concrete: this audit had proposed sweeping the unpublished
threshold until a reconstruction reproduced 10.6M, as the nearest available substitute for a
conformance re-execution, and had to withdraw the proposal (`policies/corpora.md` §5).

*Requirement.* Removals per component, and a denominator per component that reconciles to the
release named in A1.

*Cost.* A column added to a table the paper already has.

**D2. State the validation performed, on what held-out set, with the number.**

*Obstacle.* This one is largely met, by both filtering developers, and it is listed because it
is the item most likely to be dropped by someone adopting the rest. ESM3 publishes an efficacy
check — an average LDDT of 0.56 on a viral structure set it defines by a stated clustering
procedure — and compares against an unfiltered compute-matched model
(`policies/esm3-open.md` §3). Evo 2 publishes a performance comparison on eukaryotic viruses
as Figure S2 (`policies/evo.md` §1).

*Requirement.* What was measured, on what set, how that set was constructed, and the result.

*Cost.* What these two already pay.

**D3. Publish, with the output, the fields the filter's own rules read.**

*This is the item with the largest return and the lowest cost in the list, and the one the
audit most wishes had existed.*

*Obstacle.* A1.4 read Evo 2's released viral component in full — 2,957,495 records — checking
every record for the lineage tags Evo 1's rules act on. Not one carries one
(`policies/evo.md` §9). The consequence is exact: none of the six published rules can be
re-executed against Evo 2's release, because each needs a field the records do not carry —
confidence, vOTU, prokaryotic host occurrences, family, order, and the eight taxonomic ranks.
Every record is therefore `unresolved`. The filter's output is published and its own stated
procedure cannot be checked against it (D-047). Evo 1's release answers three of the six.
Neither carries the IMG/VR metadata the other three read.

The two releases are also complementary rather than jointly sufficient: Evo 1's carries
taxonomy and no accession, Evo 2's carries the accession and no taxonomy
(`policies/evo.md` §9). An accession is the more valuable of the two, because it is a join key
back to the filter's input and a lineage tag is not — so a developer who can publish only one
field should publish the input accession.

*Requirement.* For each rule, the field it reads, carried on the released records. Failing
that, the input accession, so the released record can be joined back to the input that carries
the fields.

*Cost.* Columns, not data. Evo 1's own release demonstrates the tags; the cost is not
re-deriving them for the next release.

### Group E — How it is communicated

**E1. The short artefact states the filter in the operative document's terms, or points at
it.**

*Obstacle.* In both labs the short public artefact diverges from the paper, and in both cases
it is the less accurate of the two documents (`policies/corpora.md` §8). ESM3's card says
"data related to viruses has been removed" where the paper says "sequences unique to viruses".
The OpenGenome2 card lists prokaryotic genomes as GTDBv220 where the paper describes v214.1
plus a v220 increment, so a developer reconstructing from the card alone pins the wrong
version. ESM3's card also says "some proteins" from the Select Agents list were removed where
the paper describes removing all UniProt sequences from those organisms
(`policies/esm3-open.md` §5 item 5). The card is the artefact a downstream developer actually
reads.

A related failure is cheaper to fix and worth naming separately: ESM-C's 6B and 600M model
cards are byte-identical, so neither can evidence any particular variant's training data
(`policies/esm-c.md` §5). A card shared across variants cannot carry a variant-level claim.

*Requirement.* The card restates the operative predicate in its own words only if the
restatement denotes the same set; otherwise it quotes or links. A card serving several
variants carries no variant-level claim.

*Cost.* A link.

**E2. Name withheld material as withheld, and say what is not known.**

*Obstacle.* ESM3's function-decoder keyword list is available on request rather than published,
so that measure is not independently checkable (`policies/esm3-open.md` §5 item 4). That is a
legitimate choice and it is published as one, which is the behaviour this item asks for — the
failure mode is the silent version. This audit has to keep "not applied", "applied but
undetectable" and "applied and retained" apart, and absence of mention supports none of the
three (`policies/esm3-open.md` §6, fourth finding). Every gap in this document had to be
established by exhaustive search — whole-document term counts recorded in `policies/evo.md` §4
and `policies/esm-c.md` §3 — because silence and absence are not distinguishable without them.

*Requirement.* Where something is withheld, say so and say why. Where something was not done,
say that. A reader must be able to tell a measure that does not exist from a measure that was
not described.

*Cost.* A sentence, and it is the sentence that converts an unanswerable question into a
answered one.

---

## 2. The four models, scored

`✓` the item is met. `~` partly met, or met in one document and contradicted in another. `✗`
not met. `n/a` the model states no hazard-driven filter, so the item has no subject.

| | Evo 1 | Evo 2 | ESM3-open | ESM-C | ESM-2 |
|---|---|---|---|---|---|
| **A1** components enumerated, each marked | ~ | ✗ | ~ | n/a | n/a |
| **A2** released artefacts named | ✓ | ✓ | ✓ | n/a | n/a |
| **B1** one operative predicate | ~ | ✗ | ✗ | n/a | n/a |
| **B2** every threshold stated | ✓ | ✓ | ✗ | n/a | n/a |
| **B3** property tested, not just field read | ✗ | ✗ | ~ | n/a | n/a |
| **B4** order of order-dependent steps | ~ | ~ | ✓ | n/a | n/a |
| **C1** dated releases, not version strings | ✗ | ✗ | ~ | n/a | n/a |
| **C2** evidence named, with its limits | ✗ | ✗ | ✓ | n/a | n/a |
| **C3** tool versions and invocation | ✗ | ✗ | ✗ | n/a | n/a |
| **D1** removals per component, reconciling | ✗ | ✗ | ~ | n/a | n/a |
| **D2** validation, set, number | ✓ | ✓ | ✓ | n/a | n/a |
| **D3** rule inputs published with output | ~ | ✗ | ✗ | n/a | n/a |
| **E1** card agrees with operative document | ✓ | ✗ | ✗ | ✗ | ✓ |
| **E2** withheld material named | ✓ | ✓ | ✓ | ✓ | ✓ |

Every cell is traceable. The justification for each is the obstacle cited under its item in §1;
the ones that are not obvious from there:

- **Evo 1, A1 `~`.** The corpus's three components are enumerated and the procedure is scoped
  to one of them explicitly, which is the enumeration this item asks for. It is not `✓`
  because the other two are not marked — a reader infers "not applied" from the procedure's
  silence rather than reading it.
- **Evo 2, A1 `✗`.** The eukaryotic component is 82% of the release, its curation is published
  in full, and that curation contains no viral screening step; whether the filter was extended
  to it is not stated either way (`policies/evo.md` §5).
- **Evo 1, B1 `~` and Evo 2 `✗`.** Evo 1 contains the one executable formulation among the ten
  and does not mark it as the operative one. Evo 2 contains none of its own and defers with
  "as previously described" (`policies/evo.md` §2), so the operative specification is in a
  different paper about a different corpus.
- **Evo, B4 `~`.** The procedure is written as a sequence and reads as ordered, which is most
  of the way there; it is not `✓` because the order is not stated as load-bearing and the vOTU
  step's dependence on it is not acknowledged (D-067).
- **ESM3, B3 `~`.** "Sequences unique to viruses" does state a property rather than a field,
  which is what this item asks for; the `~` is because the operationalisation —
  "align almost exclusively to other viral sequences in UniProt" — reintroduces the gap by
  leaving the test unquantified (`policies/esm3-open.md` §2, §5 item 2).
- **ESM3, C1 `~`.** Eight components each carry a stated release and several are exact; two of
  the eight are obtainable exactly as stated, four at the wrong granularity, and two not at all
  (`policies/esm3-open.md` §6). That is materially better than a bare version string and short
  of a pin.
- **ESM3, C2 `✓`.** The denylist's evidence is UniProt taxonomic annotation, named as such,
  and the paper characterises what that evidence supports — "as measured by UniProt taxonomic
  annotations" (`policies/esm3-open.md` §2). That parenthesis is exactly this item.
- **ESM3, D1 `~`.** A total is published, which is more than Evo publishes, and it does not
  reconcile to the named releases (`policies/esm3-open.md` §6).
- **ESM3, E1 `✗`.** Two divergences between card and paper, in opposite directions: "related
  to viruses" is broader than the paper, "some proteins" is narrower.
- **ESM-C, E1 `✗`.** Not about filtering — ESM-C states no exclusion — but the shared
  byte-identical card cannot evidence a variant's training data at all
  (`policies/esm-c.md` §5), which is the same failure this item is about.
- **ESM-2, E1 and E2 `✓`.** The repository documentation describes the corpus and its held-out
  split without claiming a safety filter, and the absence is established by search
  (`policies/esm2.md` §1). A model that claims nothing cannot overclaim.

**One note that belongs with the ESM-2 column and nowhere else.** ESM-2 is this audit's
positive control because it carries no biosecurity exclusion, and it remains so. It is not
unfiltered: its de-novo filter is exclusion-based data filtering with reproducible parameters
and a stated purpose, the purpose being generalisation work rather than biosecurity, and about
6.6 million of the 6.9 million clusters separating the release from the training set fall to
one unquantified step (`policies/esm2.md` §6). A write-up that calls ESM-2 unfiltered would be
wrong. Scored against D1, that step is `✗` — which is worth saying, because it shows the
standard bites on a filter nobody built for safety.

### What the table says

Three readings, in descending order of how confident this audit is in them.

**No model meets C3, and only ESM3 meets C2.** Tool version and invocation is the cheapest
item in the list and the one nobody publishes. It is probably the easiest thing to change.

**The two items that decide whether an audit is possible at all are B2 and D3**, and they fail
in opposite directions. ESM3 publishes an unauditable rule against an unreleased corpus: the
threshold is missing, so the rule cannot be run, and there is no release to run it against
(`policies/corpora.md` §5). Evo publishes a runnable rule against a released corpus that
carries none of the fields the rule reads: the rule can be run, and not on the artefact it
produced (D-047). Either failure alone makes conformance unmeasurable. They are independent,
and a standard has to ask for both.

**The short artefact is the weak point in both labs.** E1 fails for three of the four models
with a card, and in every case the card is the document a downstream developer reads.

---

## 3. This project's own filter specifications, in the same format

The reciprocal obligation in §10: publish ours in the format we are asking for, so the standard
is demonstrated rather than proposed. The specifications are
`policies/specs/*.yaml`, validated by `tools/specs.py` in CI.

A note on what is being scored. This project does not filter a training corpus; it
*re-executes* published filters, so some items read across differently — A2 names the audit's
outputs rather than a checkpoint, and D2 is validation of the re-execution rather than of a
safeguard. The items that do not translate are marked and not quietly scored as met.

| | `evo1-*` (3 readings) | `esm3-open-*` (3 readings) |
|---|---|---|
| **A1** components enumerated, each marked | ✓ `sources` lists every component of each release with `searched` true or false and a stated reason |
| **A2** released artefacts named | ✓ every table carries the manifest it was produced from, with its sha256 |
| **B1** one operative predicate | ✓ and more than the item asks: where the published prose admits several readings, all three are published as separate executable specs rather than one being chosen |
| **B2** every threshold stated | ✓ D-076's threshold regime and D-078's sampling rates are fixed in code and cited by id from every artefact |
| **B3** property tested, not just field read | ✓ each rule names the field it reads; where the field cannot express the property, the spec says so (the `evo1` host rule, D-072) |
| **B4** order of order-dependent steps | ✓ the specs are ordered rule lists and the order is part of the spec |
| **C1** dated releases, not version strings | ✓ both corpora pinned to commit SHAs with a published sha256 per file (`policies/evo.md` §7); profile registries pinned by version and digest |
| **C2** evidence named, with its limits | ✓ `policies/sources.json` carries retrieval status and blocker text per source, and a quote citing an unretrieved source fails CI |
| **C3** tool versions and invocation | ✓ `amazebio.repro` records tool versions in every `run.json`; the environment is `pixi.lock` |
| **D1** removals per component, reconciling | ✓ every count carries its denominator and its interval, and `estimate_kind` says whether it is a population figure or a lower bound |
| **D2** validation performed | ~ A3.3 and C6.3 are the second-method gates and neither has run yet; until they do this is a commitment rather than a result |
| **D3** rule inputs published with output | ✓ detection rows carry the record accession, so every published count joins back to the corpus it came from |
| **E1** short artefact agrees | ✓ `docs/filter-audit.md` is the short artefact and states what the tool is not |
| **E2** withheld material named | ✓ an unretrieved source is registered with its blocker in `sources.json`, and `tools/policies.py` bars every quote that cites one |

Two cells are honest rather than flattering. **D2 is `~`** and stays `~` until A3.3
reimplements the headline counts by a second method; a standard whose author scores himself
complete before his own gate opens is not worth proposing. And the whole column rests on this
project filtering nothing — it is easier to publish the inputs to a rule you are re-executing
than to publish the inputs to a rule you ran over five terabytes two years ago. The standard
should be read with that asymmetry in mind.

---

## 4. Against existing frameworks

A standard that duplicates an existing one is noise. Five frameworks were checked for whether
they already ask for any of the fourteen items: one binding instrument, two documentation
conventions, one biosecurity-specific community agreement, and one technical treatment of
filtering as a mitigation. Each was read from its primary text, retrieved and quoted below;
none was characterised from commentary.

**The short answer is that none of the five asks for any of the fourteen items in a form that
would have let this audit proceed.** Three ask adjacent questions. The binding one scopes
itself out. The one that treats filtering at length asks for nothing to be published about it.

### 4.1 EU AI Act Article 53(1)(d) — the public training-content summary template

*AI Office, template and explanatory notice annexed to Commission decision C(2025) 5235,
24 July 2025; GPAI obligations apply from 2 August 2025.* This is the only binding instrument
of the five, and the closest thing to a mandatory filter disclosure anywhere.

It has one field about removing content: §3.2, *Removal of illegal content*, which asks for a
"General description of measures taken". The scoping sentence is decisive:

> This Section concerns measures taken to avoid or remove illegal content under Union law from
> the training data (such as blacklists, keywords, and model-based classifiers) […] Such
> measures do not include data selection practices, for example to increase the capability of
> the model.

A biosecurity exclusion filter is neither of those things. It removes content that is not
illegal under Union law — viral sequence data is lawful and largely published by public
databases — and it is not data selection to increase capability; the whole point is that it
costs capability. So it falls outside the only field that could have carried it, and the
template requires nothing about it at all.

Two things follow, and the second is the more interesting.

First, even if a provider volunteered a biosecurity filter under §3.3 (*Other information,
optional*), the template's own standard for §3.2 is a general description. A general
description is what ESM3 and Evo already publish, and it is precisely what this audit found
insufficient: none of B2, C1, C3, D1 or D3 is asked for anywhere in the template.

Second, the template *is* demanding about provenance, and in exactly the shape item A1 asks
for. §2 requires "a comprehensive narrative description of the data scraped online […] and a
narrative description of all other data sources used […] to ensure completeness of the summary
regarding the content used for the model training". That is an exhaustiveness requirement on
components, and it is the one item of the fourteen a European provider is already obliged to
meet. It is for copyright rather than for safety, and it would have closed the Evo 2 scope gap
anyway. Worth saying plainly: the single most consequential disclosure gap this audit hit is
one a copyright instrument incidentally covers and no safety instrument does.

### 4.2 Datasheets for Datasets

*Gebru et al., arXiv:1803.09010.* The closest documentation convention, and the only framework
of the five with questions that overlap substantively. Its §3.4 asks three:

> Was any preprocessing/cleaning/labeling of the data done (e.g., discretization or bucketing,
> tokenization, part-of-speech tagging, SIFT feature extraction, removal of instances,
> processing of missing values)? If so, please provide a description.

> Was the "raw" data saved in addition to the preprocessed/cleaned/labeled data (e.g., to
> support unanticipated future uses)? If so, please provide a link or other access point to the
> "raw" data.

> Is the software that was used to preprocess/clean/label the data available? If so, please
> provide a link or other access point.

And in the collection process: "If the dataset is a sample from a larger set, what was the
sampling strategy (e.g., deterministic, probabilistic with specific sampling probabilities)?"

Three observations.

**It asks for more than item C3, in one direction.** "Is the software available?" is stronger
than naming a version and an invocation — published filter code would settle B1, B2, B4 and C3
at once, which is the single highest-value thing a developer could do and is not what any
developer here did.

**It does not substitute for D3.** "Was the raw data saved?" and D3 are adjacent and not the
same. Evo's raw input is saved — IMG/VR is a public database — and the audit is still unable to
check the release against its own procedure, because the join key from the released record back
to that input is what is missing (`policies/evo.md` §9). The datasheet question is answered
"yes" by a release that D3 fails.

**Its questions are free text, and the gaps here are specificity gaps.** ESM3's filter
description is a perfectly good answer to "please provide a description"; what makes it
unauditable is one unstated number. A framework of descriptions cannot ask for that number;
item B2 exists because a description-shaped question does not reach it.

And the practical point: Datasheets addresses whoever publishes a dataset, and the filters here
are steps inside a model's training pipeline. Neither Evo nor ESM3 publishes a datasheet, and
nothing obliges them to.

### 4.3 Model Cards for Model Reporting

*Mitchell et al., arXiv:1810.03993.* The card is the artefact item E1 is about, so the
convention's own expectation for it matters. §4.6 is explicit that training data is where the
card is expected to give way:

> Training Data. May not be possible to provide in practice. When possible, this section should
> mirror Evaluation Data. If such detail is not possible, minimal allowable information should
> be provided here, such as details of the distribution over various factors in the training
> datasets.

So the convention anticipates the card being thin on training data and asks for distributional
detail as the fallback. It does not ask the card to agree with the paper, which is the failure
E1 is derived from — and that failure is not thinness. ESM3's card is not vague about the
filter; it states it in terms that denote a different set from the paper's
(`policies/esm3-open.md` §5 item 3). A convention that expects the card to say less has no
provision for a card that says something else.

### 4.4 Responsible AI × Biodesign

*Community values, guiding principles and commitments, 2024, signed by roughly 180 developers
in this field — the community that builds the models in this audit.*

Ten commitments. **None concerns training data.** The hazard commitments are about physical
DNA synthesis: obtaining synthesis only from providers with "industry-standard biosecurity
screening practices", and supporting "the development of new strategies to improve DNA
synthesis screening". The nearest commitments to this document are the ninth, to "communicate
the benefits and risks of our research", with "appropriate disclosures of relevant benefits,
risks, and risk mitigation strategies when sharing or publishing new software", and the fifth,
to "continuously evaluate the capabilities of our protein design software".

That ninth commitment is a commitment to disclose risk mitigation strategies, with no shared
format for doing so. A signatory who publishes what ESM3 or Evo published has met it. This
document is one proposal for what meeting it could mean, and it is addressed to a community
that has already agreed to the obligation it specifies — which is the most favourable ground a
standard can be proposed on, and the reason this is a checklist rather than a rule.

### 4.5 Frontier Model Forum, Technical Report on Mitigations

*June 2025.* §2.1 is given over to data filtering: what it is ("removing content from training
datasets that could lead to dual-use or potentially harmful capabilities"), the methods
available, and two limitations — that dual-use knowledge cannot be removed without cost, and
that capabilities can re-emerge from combinations of benign data.

It asks for nothing to be documented, disclosed or published. That is not a criticism; it is a
taxonomy of mitigations, and a taxonomy is not a disclosure standard. What makes it the most
relevant of the five is how the section ends:

> Further research is needed to understand which harmful outputs can be effectively prevented
> through data filtering alone versus those requiring additional safeguards.

That sentence is this project's research question, written by the forum of the developers
deploying the mitigation. **A disclosure standard is a precondition for answering it.** The
efficacy of a safeguard cannot be studied across developers while each one's safeguard is
reconstructable only by the developer who built it — which is what Phase A spent its effort
establishing, and is the strongest argument for the checklist that this document can make.

One adjacent line of work, named because it bounds what this standard is for rather than
because it overlaps: BioRiskEval (arXiv:2510.27629) tests whether filtering survives
fine-tuning and linear probing of pretrained representations, and reports that it may not.
*Read from its abstract only.* That question — recovery of excluded capability — is explicitly
outside this project's scope under `DESIGN.md` §4, and it is complementary: it asks whether a
filter that worked can be undone, where this audit asks whether the filter did what it said.
Both questions need the same thing from a developer, which is a filter specification precise
enough to reproduce.

### 4.6 What the checklist adds

Collecting the above, the items no existing framework asks for in any form:

| Item | Asked anywhere? |
|---|---|
| **A1** components enumerated, each marked | EU template §2, for provenance, not for the filter |
| **A2** released artefacts named | no |
| **B1** one operative predicate | no |
| **B2** every threshold stated | no |
| **B3** property tested, not just field read | no |
| **B4** order of order-dependent steps | no |
| **C1** dated releases, not version strings | no |
| **C2** evidence named, with its limits | no |
| **C3** tool versions and invocation | Datasheets §3.4, and asks for more: the code |
| **D1** removals per component, reconciling | no |
| **D2** validation, set, number | no |
| **D3** rule inputs published with output | adjacent only — Datasheets asks whether raw data was saved |
| **E1** card agrees with operative document | no; Model Cards anticipates thinness, not divergence |
| **E2** withheld material named | no |

Eleven of fourteen are asked by nobody. The three that are asked are asked by instruments that
do not apply to these models, for purposes other than safety, and in free-text form.

A fair summary of the gap: existing frameworks ask **what** a dataset contains and **that**
processing happened. Auditing a safeguard requires knowing **what the rule was** and **whether
the artefact obeys it**, and no framework asks for either.

---

## 5. What this is not

It is not a compliance regime, and nothing here should be read as a basis for one. The items
are what an auditor needs, which is a lower bar than what a regulator would ask and a different
thing from what a developer owes.

It does not say that a filter meeting all fourteen items is a good filter. It says such a
filter can be checked. Whether it works is what the rest of this project measures, and the
answer for the filters here is the subject of the Phase A write-up, not of this document.

It says nothing about whether data filtering is the right safeguard. `DESIGN.md` §8 is explicit
that for some hazard families the answer may be that no filter can remove the capability at an
acceptable cost, and a disclosure standard is equally useful for establishing that.

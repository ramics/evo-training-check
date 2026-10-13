# ESM-2 — no exclusion; positive control

ESM-2 is the positive control: a protein language model trained without a hazard-driven data
filter. Its value here is a concrete version pin for corpus reconstruction (A1.3).

---

## 1. What was excluded

**Nothing.** No retrieved source states any hazard-driven exclusion for ESM-2. The repository
documentation describes the training corpus and its held-out split without reference to safety
filtering of any kind.

## 2. Corpus and version pin

[source: S-ESM2-REPO]
> The split files establishing which UniRef50 clusters were used as held-out evaluation set for pre-training

and the pinned release those IDs refer to:

[source: S-ESM2-REPO]
> These files only contain only the UniRef50 IDs and UniRef100 IDs corresponding to the

— the UniRef database 2018-03 release, linked from the same sentence, under CC BY 4.0. The
duplicated "contain only" is in the source.

This is the most precisely pinned corpus of the four policies, which is useful: it makes ESM-2
the cheapest model to reconstruct a surviving corpus for, and therefore a good first target
for the A1.3 pipeline.

## 3. Open questions

None material for A0.3. ESM-2 carries no policy to read three ways. The only live question is
whether the 2018-03 UniRef release is still retrievable at that version for A1.3 — the UniProt
previous-releases archive is reachable, so probably yes, but it is unverified.

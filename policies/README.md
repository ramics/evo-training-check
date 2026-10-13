# policies/ — the policy evidence store

What each model's developers actually published about filtering their training data, quoted
verbatim, with every quote traceable to a stored source.

This is the output of task A0.1 and the input to A0.2 (the policy specification schema) and
A0.3 (the three readings). It is deliberately evidence, not analysis: it records what was said
and what was not said, and leaves ambiguities open rather than resolving them.

```
sources.json   the citable source inventory — stable ids, URLs, checksums, retrieval status
captures/      stored copies of openly-licensed sources (repo docs, model cards, licences)
../pdfs/       the papers
corpora.md     released corpus vs actual training corpus, per model (A1.1)
evo.md         Evo 1 and Evo 2 — one policy lineage
esm3-open.md   ESM3-open
esm-c.md       ESM-C — included for the record; it states no exclusion
esm2.md        ESM-2 — positive control
```

## The one rule

**No quote goes in this store unless it was checked against the document it cites.**

`tools/policies.py` enforces it. For every blockquote in every policy file, it extracts the
text of the cited source — PDFs included — normalises away typography, and fails if the quoted
wording does not literally appear. It also fails if a source's file has changed since its
checksum was recorded, or if a quote cites a source that was never retrieved.

```bash
pixi run -e dev policies-check     # or: python3 tools/policies.py --verbose
```

This exists because the failure mode that would most damage this project is a plausible
paraphrase acquiring quote marks. `DESIGN.md` §B1 step 0 says to verify from primary sources
and trust no secondary source, `DESIGN.md` included — and a model's own recollection of a
paper is a secondary source. §7 requires Phase A to be airtight, because it names real
laboratories. A quotation nobody checked is the weakest link in that chain, so the check is
mechanical rather than a matter of care.

## Quote format

A blockquote must be preceded, within three lines, by a source marker:

```markdown
[source: S-EVO1-PREPRINT, p32]
> For IMG/VR, sequences were retained only if they were labeled as "High-confidence"
```

The locator after the id (`p32`, `Appendix A.6.1`) is for the reader; the checker uses the id.
Mentioning a source id in prose without a blockquote is not a quote and is not checked — use
that for pointing at a source you are describing rather than quoting.

Normalisation folds away PDF artefacts only: soft hyphenation across line breaks, ligatures,
curly quotes and dashes, and runs of whitespace. It does not fold away differences in wording.
Quotes cannot span a page break in a PDF, because publisher boilerplate sits between the pages
in extracted text — quote each page separately.

## Source status

- **retrieved** — stored in the repo at a recorded checksum. Quotable.
- **retrieved_not_stored** — read, but publisher content, so recorded by URL only. Not
  quotable: the checker cannot verify it. Use the stored preprint instead and note the
  difference.
- **unretrieved** — identified but not obtained. Not quotable. `sources.json` records why.

## Reading this store

Two kinds of entry carry weight, and they are not the same:

- **A statement.** The source says something. Quoted, with its locator.
- **A silence.** The source does not address something. Recorded as a search that came back
  empty, with the terms searched and the extent searched, never as bare assertion.

A silence is weaker evidence than a statement and is labelled as such throughout. "The paper
does not mention prophage" is a fact about the paper; "the filter ignored prophage" is an
inference from it. This store holds the former.

---
id: X1.4
title: Machine-verify quotations inside the policy specs
phase: X
status: review
gate: false
depends_on: [A0.3]
blocks: []
design_ref: "§A0, §7"
deliverable: null
owner: claude
---

# X1.4 — Machine-verify quotations inside the policy specs

**Design reference:** DESIGN.md §A0, §7

## Goal

Extend quote checking to `policies/specs/*.yaml`. `tools/policies.py` verifies every blockquote
in `policies/*.md` against the source it cites; the spec files quote the same published prose in
rule notes and file headers, and nothing checks those.

A0.3 verified its 20 quotations by hand. Two were wrong — a capitalised word and a transliterated
`≤` — and were fixed. Hand-verification found them this once; it will not keep finding them.

## Why it is not just a regex

The markdown store works because every quote is a blockquote with a `[source: ID]` marker above
it. In the specs, quotations are inline in YAML comments and in `note:` block scalars, with no
marker: the source is a field on the enclosing rule. A naive extractor pairs the closing quote of
one quotation with the opening quote of the next and reports nonsense (A0.3 hit this).

So the work is mostly extraction:

- quotations spanning several `#` comment lines, where `# ` prefixes must be stripped first;
- quotations inside folded block scalars, where YAML has already rewrapped the text;
- fragments quoted mid-sentence, which are verbatim but not sentence-initial;
- apostrophes, quote marks, dashes and `≤` appearing in either form, as `tools/policies.py`
  already normalises.

Attribute each quotation to the source of its enclosing rule, and fall back to the policy's own
`source` for ones in the file header.

## Steps

- Reuse `tools/policies.py`'s source extraction and normalisation rather than reimplementing it.
- Extract quotations from spec comments and `note:` fields, with the structure above in mind.
- Check each against the text of the source its rule cites. Fail on any that does not appear.
- Add the check to the `specs-check` task so CI runs it.
- Regression-test with the two errors A0.3 made by hand: a changed capital and `<=` for `≤`.

## Done when

- Every quotation in `policies/specs/*.yaml` is machine-checked against its cited source.
- The check runs in CI and fails on an unverifiable quotation.
- A deliberately corrupted quotation is shown to fail, in a test.

## State — 2026-10-14

`review`, on branch `ccr-2956d088-s25hlk` — pushed and green, **not merged into `main`**, so the files named
here are absent from a `main` checkout.

- `tools/specquotes.py` verifies every quotation in `policies/specs/*.yaml` against the source its
  rule cites, wired into `specs-check` so CI runs it. 60 quotations pass.
- Turning it on found two real defects rather than confirming the specs were clean: case was being
  folded away by `policies.normalise`, which had hidden a miscapitalised quote in
  `policies/corpora.md` whose own note blamed PDF extraction for it; and five double-quoted spans
  in the specs were our own phrasing or an earlier draft's words rather than quotation.
- DECISIONS.md D-023 records the three calls; the convention a later writer has to follow is in
  `policies/specs/README.md`.

Every Done-when criterion is demonstrably met, so this can move to `done` as soon as it is
reviewed.

## Notes

Same reasoning as `policies/README.md`: the failure mode that would most damage this project is a
plausible paraphrase acquiring quote marks. §7 requires Phase A to be airtight because it names
real laboratories, and the specs are what downstream tasks actually execute.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

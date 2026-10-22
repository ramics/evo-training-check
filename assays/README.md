# `assays/` — the assay provenance and licence register

Deliverable 2. Everything here is about *which assays Phase B analyses, where they came from,
and on what terms*. It is committed rather than left in `artifacts/` because the deliverable
asks for something published and citable, and a file in a git-ignored directory is neither.

| File | What it is |
|---|---|
| `register.json` | **GENERATED** — the register. One entry per assay, with provenance, arm, control tag and licence position. |
| `register.md` | **GENERATED** — the same thing as a table, for reading. |
| `licences.json` | **GENERATED** — the licence evidence the register cites: the deposit's grant, and each source article's publisher-deposited terms. |

Regenerate the register with `pixi run -e dev python tools/assay_register.py`, and re-acquire
the evidence with `tools/assay_licences.py` (which is the only part that touches the network).
`pixi run -e dev assays-check` validates the committed register and runs in CI. Do not hand-edit
any of the three.

## The two licence questions, which are not the same question

**What may this project pass on?** The pinned ProteinGym release is the bytes Phase B reads.
Those were downloaded from the maintainers' own server, which states no licence; the same
release is deposited on Zenodo under MIT, and `tools/assay_licences.py --verify` downloads the
deposit's assay archive and hashes it, so "the deposit's licence applies to our copy" is a
digest match rather than an inference from matching file sizes. That grant is what the project
relies on, and `assays-check` fails if the match ever stops holding.

**What may a reader do with the original study?** Each assay carries the DOI of the publication
that produced it and that publisher's own deposited licence. This is evidence about the
*article*, not about the supplementary data the article reports, and the register never treats
one as the other. A permissive article licence does not license somebody's data table, and a
restrictive one — there are five, and two more where the publisher deposited terms that
disagree with each other — is not a bar on anything this project does, because the project
redistributes no assay data. Both facts are in the register so that neither has to be guessed.

MIT is a software licence, and its application to a data deposit is ordinary Zenodo practice
rather than a settled legal question. The register records it as the grant relied on, with that
caveat stated, which is the honest position and not a legal opinion.

## What is published, and what is not

The register, and everything downstream of it, carries assay identifiers, taxonomy, arm
membership, per-assay counts, source DOIs, and scores this project computed. It does not carry
the measured fitness values, or the benchmark's own published model scores: both are read from
the pinned release at run time and never re-hosted. That is what makes the register publishable
whatever each source article's terms say.

## Citing it

Three citations, not one — the collection, the pinned release as data, and the study behind the
individual assay. `register.json`'s `citation` block has the exact form of each and says why
dropping any of them loses something. The register itself is cited by its task id and the commit
its run manifest records.

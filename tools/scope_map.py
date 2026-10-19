#!/usr/bin/env python3
"""Map filter scope against corpus composition — A4.3, DESIGN.md §A4, deliverable 1.

The leading Phase A result (DECISIONS.md D-007): a filter is a procedure pointed at *part* of a
corpus, and what it was never pointed at was never a candidate for removal. That claim needs no
new bioinformatics — only the published scope of each policy, set against the measured
composition of each corpus — which is why it leads and the survival quantification sizes it.

Everything here is assembly. The coverage arithmetic is `amazebio.scope`, the composition is
`amazebio.opengenome` and `amazebio.esm3`, and the policy readings are the six specs in
`policies/specs/`. No number is retyped from prose: the Evo composition rebuilds from the
committed per-file captures rather than from a live API call, and the OpenGenome2 token table
is parsed out of the committed dataset card.

**Three failure kinds, kept apart**, because they have different remedies:

* *not applied to a component* — the scope never reached it. Nothing about the filter's quality
  bears on it. For Evo this is 99.8% of OpenGenome2 by bytes.
* *applied but unable to detect* — in scope, and the published rule leaves a parameter
  unspecified, so what it removes cannot be computed at all (ESM3-open's literal reading).
* *applied and deliberately retaining* — in scope, reached by a rule, and the rule is stated to
  keep something a reader might expect it to remove.

And a fourth state that is not a failure kind at all: *not addressed*, where the source names a
list of components and does not say the list is exhaustive. Reporting those as out of scope
would assert a conclusion the source declines to make.

**Shares are volume figures.** `metrics/survival.md` §5 is frozen on this: volume tracks corpus
composition rather than filter performance, so every share here carries its denominator and a
statement of what it does not mean. The headline metrics remain M1-M3.

    python3 tools/scope_map.py            # artifacts/a4-3/scope.json + scope.md
    python3 tools/scope_map.py --print    # and the table to stdout
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import esm3, objectstore, opengenome, policyspec, scope
from amazebio.repro import ReproError, run

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "policies" / "specs"
CAPTURES = ROOT / "policies" / "captures"
OUTDIR = Path("artifacts/a4-3")

#: Which corpus release each policy family's scope is measured against, and the committed
#: capture the composition is rebuilt from. Evo 1's policy was written for OpenGenome v1 and
#: inherited unchanged by Evo 2 for OpenGenome2 ("As previously described"), so the same policy
#: is measured against both — and the difference between the two answers is the inheritance
#: finding this task owes §A4.
EVO_RELEASES = (
    ("opengenome", "hf-open-genome-manifest.json", "Evo 1"),
    ("opengenome2", "hf-opengenome2-manifest.json", "Evo 2 (policy inherited unchanged)"),
)

#: ESM3-open components the source's list neither names nor excludes. Supplied rather than
#: inferred: whether "including PDB, UniRef, MGnify, and JGI" is exhaustive is a reading of the
#: wording, and `amazebio.scope` does not read sources. `esm3.py`'s `unstated()` entry
#: `esm3-filter-scope-list-not-exhaustive` is where this comes from.
ESM3_NOT_ADDRESSED = frozenset({"OAS", "AlphaFoldDB", "ESMAtlas"})

#: Rules stated to keep something a reader might expect them to remove. The third failure kind
#: is a reading of each rule's published prose, so it is declared here with its locator rather
#: than guessed from the schema — the schema can represent an unspecified parameter, but not an
#: intention.
RETAINS_BY_DESIGN: dict[str, str] = {
    "keep-high-confidence": (
        "The gate keeps IMG/VR's high-confidence subset, so every putative record is removed "
        "whether or not it is eukaryote-infecting — and conversely the rule's own output is "
        "the population the later rules see. 10,101,426 of 15,677,623 records are putative "
        "(D-064), so this single step sets the denominator for everything after it."
    ),
    "keep-one-per-votu": (
        "Deduplication to one representative per vOTU retains a member of every vOTU rather "
        "than removing hazard-relevant ones: 8,606,551 vOTUs survive as representatives by "
        "design (D-064). A family with any surviving representative is a family the model "
        "still sees, which is exactly what M1 measures."
    ),
}


def evo_rows() -> list[dict[str, Any]]:
    """Scope by component and reading for the Evo policy, against both corpus releases."""
    policies = {
        pid: p for pid, p in policyspec.load_policy_dir(SPECS).items() if pid.startswith("evo")
    }
    rows: list[dict[str, Any]] = []
    for release_key, capture, label in EVO_RELEASES:
        release = opengenome.RELEASES[release_key]
        blobs = opengenome.blobs_from_capture(CAPTURES / capture)
        composition = opengenome.composition(release, blobs)
        # One row per component, not per representation: a component's scope does not depend
        # on whether its bytes are FASTA or JSON, and `policies/evo.md` warns that the two
        # trees are not a strict mirror, so their bytes must never be summed.
        staged_rep = release.staged_representation
        by_component: dict[str, dict[str, Any]] = {}
        for row in composition:
            if row["component"] == "(not corpus)":
                continue
            keep = by_component.get(row["component"])
            if keep is None or row["representation"] == staged_rep:
                by_component[row["component"]] = row
        # Renormalise within the chosen representation. `composition()` divides by the whole
        # release, which spans both the FASTA and the JSON tree, so a share taken from it for
        # one representation silently uses a denominator that includes the other — the very
        # summing across representations `policies/evo.md` §7 warns against. A1.2's published
        # "0.2% of OpenGenome2" is that figure; within the FASTA tree alone the filtered
        # component is about twice that, and the corrected number is the larger one.
        rep_total = sum(r["bytes"] for r in by_component.values())
        for component, comp_row in sorted(by_component.items()):
            within = round(comp_row["bytes"] / rep_total, 6) if rep_total else 0.0
            for policy in [policies[k] for k in sorted(policies)]:
                cell = scope.classify(policy, component, family="evo")
                rows.append(
                    _row(
                        cell,
                        corpus=release.key,
                        corpus_label=label,
                        role=comp_row["role"],
                        role_note=comp_row["role_note"],
                        bytes_=comp_row["bytes"],
                        representation=comp_row["representation"],
                        share=within,
                        share_of_whole_release=comp_row["share_of_release"],
                    )
                )
    return rows


def esm3_rows() -> list[dict[str, Any]]:
    """Scope by component and reading for ESM3-open, against its stated composition."""
    policies = {
        pid: p for pid, p in policyspec.load_policy_dir(SPECS).items() if pid.startswith("esm3")
    }
    stated = {c["component"]: c for c in esm3.scope_table()}
    total_tokens = esm3.STATED_TOTALS["total_unique_training_tokens_m"]
    rows: list[dict[str, Any]] = []
    for component, meta in sorted(stated.items()):
        for policy in [policies[k] for k in sorted(policies)]:
            cell = scope.classify(
                policy, component, family="esm3", not_addressed=ESM3_NOT_ADDRESSED
            )
            tokens = meta.get("unique_tokens_m")
            rows.append(
                _row(
                    cell,
                    corpus="esm3-open (stated)",
                    corpus_label="ESM3-open",
                    role=meta["track"],
                    role_note=f"{meta['track']} track; retrievability: {meta['retrievability']}",
                    bytes_=None,
                    representation=meta["retrievability"],
                    share=(round(tokens / total_tokens, 6) if tokens else None),
                    unique_tokens_m=tokens,
                    stated_in_filter_scope=meta["in_filter_scope"],
                )
            )
    return rows


def _row(cell: scope.ComponentScope, **extra: Any) -> dict[str, Any]:
    row = cell.to_dict()
    row["never_a_candidate"] = cell.never_a_candidate
    row["retains_by_design"] = [
        {"rule": rule, "detail": RETAINS_BY_DESIGN[rule]}
        for rule in cell.rules
        if rule in RETAINS_BY_DESIGN
    ]
    row.update(extra)
    return row


def build() -> dict[str, Any]:
    """The whole artefact: rows, the share summaries, and the inheritance record."""
    rows = evo_rows() + esm3_rows()
    card = (CAPTURES / "hf-opengenome2-README.md").read_text()
    tokens = opengenome.token_table(card)
    return {
        "task": "A4.3",
        "design_ref": "§A4, §2 HA",
        "rows": rows,
        "coverage_by_reading": _coverage_summary(rows),
        "evo_token_shares": _evo_token_shares(tokens),
        "share_note": scope.share_note("the stated denominator named on each figure"),
        "caveats": _caveats(),
    }


def _coverage_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per corpus and reading: how much of the corpus each coverage state accounts for."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["corpus"], row["reading"])
        acc = out.setdefault(
            key,
            {
                "corpus": row["corpus"],
                "corpus_label": row["corpus_label"],
                "reading": row["reading"],
                "components": dict.fromkeys(scope.STATES, 0),
                "share": dict.fromkeys(scope.STATES, 0.0),
                "denominator": (
                    f"bytes within the {row['representation']} tree of this "
                    "release (not the whole release: the trees are not a mirror and "
                    "must not be summed)"
                    if row["bytes_"] is not None
                    else "unique training tokens as stated in ESM3's Table S4"
                ),
            },
        )
        acc["components"][row["state"]] += 1
        if row["share"] is not None:
            acc["share"][row["state"]] = round(acc["share"][row["state"]] + row["share"], 6)
    return sorted(out.values(), key=lambda r: (r["corpus"], r["reading"]))


def _evo_token_shares(tokens: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The viral component's token share per training phase, with the card's own column kept.

    `policies/corpora.md` directs A4.3 to the card's token table and requires it to state the
    denominator, because the two phases weight the components differently. The card's own
    percentage column is kept beside the recomputed one because Phase 2's does not sum.
    """
    out: dict[str, Any] = {}
    for phase, phase_rows in tokens.items():
        stated_total = sum(float(r["stated_composition"].rstrip("%")) for r in phase_rows)
        viral = [r for r in phase_rows if "IMG/VR" in r["dataset"]]
        out[phase] = {
            "total_tokens_b": round(sum(r["tokens_b"] for r in phase_rows), 2),
            "stated_composition_column_totals_pct": round(stated_total, 2),
            "stated_composition_column_usable": abs(stated_total - 100.0) < 1.0,
            "filtered_component_tokens_b": sum(r["tokens_b"] for r in viral),
            "filtered_component_computed_share": round(sum(r["computed_share"] for r in viral), 6),
            "rows": phase_rows,
        }
    return out


def _caveats() -> list[dict[str, str]]:
    """Every limitation that must travel with these numbers, as its own record.

    A4.3's last Done-when criterion is that no claim about what a filter did not cover rests on
    absence of mention alone without that absence being stated as the evidence. These are that
    statement, in machine-readable form, so the write-up cannot quote a figure without them.
    """
    return [
        {
            "id": "absence-of-mention-is-the-evidence",
            "text": (
                "What is established: the published viral exclusion operates on the viral "
                "component, and the eukaryotic component's published curation contains no "
                "viral screening step. What is not established: that no unpublished screening "
                "occurred. The evidence for the former is a recorded search over the retrieved "
                "sources (policies/evo.md §4 and §5), not silence."
            ),
        },
        {
            "id": "evo2-nature-methods-unretrieved",
            "text": (
                "S-EVO2-NATURE-METHODS is unretrieved. It could add procedure the preprint "
                "omits, which would change Evo 2's scope row. Must be checked before the "
                "preprint (policies/evo.md open question 5)."
            ),
        },
        {
            "id": "denylist-currency-unaddressed",
            "text": (
                "Whether the denylist was revisited for Evo 2 against an evolving taxonomy is "
                "not addressed by any retrieved source. A9.1 measures the decay; this task "
                "records only that no source says."
            ),
        },
        {
            "id": "esm3-has-no-corpus-denominator",
            "text": (
                "JGI accounts for 265,070 of ESM3's 768,109 M stated unique training tokens "
                "and is unreconstructible, so no ESM3 figure may be stated as a share of the "
                "corpus as built. ESM3 shares here are over its own stated totals and are "
                "documentary, not measured (D-033)."
            ),
        },
        {
            "id": "representations-are-not-summable",
            "text": (
                "OpenGenome2's FASTA and JSON trees are not a strict mirror, so component "
                "bytes are quoted for one representation and never summed across them "
                "(policies/evo.md §7)."
            ),
        },
        {
            "id": "card-phase-2-percentages-broken",
            "text": (
                "The OpenGenome2 card's Phase 2 composition column totals about 252% and "
                "assigns 104% to one component. Shares here are recomputed from its token "
                "column; the published column is retained beside them as the finding."
            ),
        },
    ]


def summarise(doc: dict[str, Any]) -> str:
    """The human-readable table, built from the same dict as the JSON."""
    lines = [
        "# A4.3 — Filter scope against corpus composition",
        "",
        "Generated by `tools/scope_map.py`. Every figure traces to `artifacts/a4-3/scope.json`.",
        "",
        "## Coverage by corpus and reading",
        "",
        "`out_of_scope` is the filter never pointed at the component. `reached_no_rule` is a "
        "wildcard-scope reading that examines it and removes nothing. `not_addressed` is a "
        "component the source's list neither names nor excludes. Shares are volume figures; "
        "see the note at the foot.",
        "",
        "| corpus | reading | out of scope | reached, no rule | not addressed | in scope | "
        "share out of scope | share not addressed | denominator |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for acc in doc["coverage_by_reading"]:
        c = acc["components"]
        lines.append(
            f"| {acc['corpus_label']} | {acc['reading']} | {c[scope.OUT_OF_SCOPE]} | "
            f"{c[scope.REACHED_NO_RULE]} | {c[scope.NOT_ADDRESSED]} | {c[scope.IN_SCOPE]} | "
            f"{acc['share'][scope.OUT_OF_SCOPE]:.4f} | "
            f"{acc['share'][scope.NOT_ADDRESSED]:.4f} | {acc['denominator']} |"
        )

    lines += ["", "## The filtered component's token share, by training phase", ""]
    for phase, data in doc["evo_token_shares"].items():
        usable = "sums to 100%" if data["stated_composition_column_usable"] else "DOES NOT SUM"
        lines.append(
            f"- **{phase}** — {data['filtered_component_tokens_b']:g} B tokens of "
            f"{data['total_tokens_b']:g} B = **{data['filtered_component_computed_share']:.4%}**. "
            f"The card's own composition column {usable} "
            f"({data['stated_composition_column_totals_pct']:g}%)."
        )

    lines += ["", "## Per component", ""]
    lines.append("| corpus | component | role | reading | state | share | why |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in doc["rows"]:
        share = "—" if row["share"] is None else f"{row['share']:.4f}"
        lines.append(
            f"| {row['corpus_label']} | {row['component']} | {row['role']} | {row['reading']} | "
            f"`{row['state']}` | {share} | {row['why']} |"
        )

    limits = [(r, limit) for r in doc["rows"] for limit in r["limits"]]
    if limits:
        lines += ["", "## Applied but unable to detect", ""]
        seen = set()
        for row, limit in limits:
            key = (row["reading"], limit["rule"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- **{row['reading']} / {limit['rule']}** — {limit['detail']}")

    retains = [(r, item) for r in doc["rows"] for item in r["retains_by_design"]]
    if retains:
        lines += ["", "## Applied and deliberately retaining", ""]
        seen = set()
        for _row_unused, item in retains:
            if item["rule"] in seen:
                continue
            seen.add(item["rule"])
            lines.append(f"- **{item['rule']}** — {item['detail']}")

    lines += ["", "## Caveats that travel with every figure above", ""]
    lines += [f"- **{c['id']}** — {c['text']}" for c in doc["caveats"]]
    lines += ["", "## On the shares", "", doc["share_note"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(OUTDIR))
    ap.add_argument("--print", dest="show", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    try:
        with run(
            "A4.3",
            seed=None,
            outdir=outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-scope.json",
            durable=objectstore.durable_results("a4-3"),
        ) as m:
            m.parameter("esm3_not_addressed", sorted(ESM3_NOT_ADDRESSED))
            m.parameter("evo_releases", [r[0] for r in EVO_RELEASES])
            m.parameter("retains_by_design_rules", sorted(RETAINS_BY_DESIGN))
            for spec in sorted(SPECS.glob("*.yaml")):
                m.input_file(spec, role="policy-spec")
            for _, capture, _ in EVO_RELEASES:
                m.input_file(CAPTURES / capture, role="corpus-manifest")
            m.input_file(CAPTURES / "hf-opengenome2-README.md", role="dataset-card")
            m.note(
                "Shares are volume figures, reported as context and never as the headline "
                "(metrics/survival.md §5, frozen). The headline metrics are M1-M3."
            )

            doc = build()
            out = outdir / "scope.json"
            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            m.output_file(out, role="scope-table")

            md = outdir / "scope.md"
            md.write_text(summarise(doc))
            m.output_file(md, role="summary")

            for acc in doc["coverage_by_reading"]:
                if acc["share"][scope.OUT_OF_SCOPE]:
                    m.note(
                        f"{acc['corpus_label']} / {acc['reading']}: "
                        f"{acc['share'][scope.OUT_OF_SCOPE]:.2%} of the corpus is out of this "
                        f"policy's declared scope, by {acc['denominator']}."
                    )
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.show:
        print((outdir / "scope.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

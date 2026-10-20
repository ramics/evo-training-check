#!/usr/bin/env python3
"""B2.2 — the viral assay register, and whether its n is enough.

D-010 narrowed this task to one question asked before any extension is curated: do the
published collections already give sufficient n for §B5's homology regression? "Sufficient" is
not a total; §B5's result *is* the interaction between homology and model-exclusion-status, so
what has to be sufficient is both arms of that contrast, at every covariate level the plan
adjusts for. A covariate level present in only one arm is not a small cell — within it the arm
is determined, and the regression cannot separate the covariate from the effect being measured.

So this pass builds the register, places every viral assay in the pinned taxonomy, decides
each policy's verdict on it, and reports the cross-tabulation. It fixes nothing about the
analysis and computes no score: it is the input B5.1 freezes its plan against.

    pixi run -e dev python tools/assay_register.py --show
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import assays, objectstore, policyspec, proteingym, seeds
from amazebio.misassignment import Denylist
from amazebio.repro import ReproError, run

TASK = "B2.2"
SEED = 20261020

#: Policies whose verdict on an assay cannot be read from taxonomy, with the reason. ESM3-open
#: removes by sequence similarity to a seed set, so no family name settles it: an assay's
#: status there is a computation over the target sequence. Naming it here keeps the register
#: from quietly reporting "not excluded" for a model whose filter it never evaluated.
SIMILARITY_POLICIES: dict[str, str] = {
    "esm3-open-literal": (
        "removes by sequence similarity to a seed set, not by taxon, so an assay's exclusion "
        "status is a computation over its target sequence and is not settled by its lineage"
    ),
    "esm3-open-charitable": "as esm3-open-literal",
    "esm3-open-strict": "as esm3-open-literal",
}

#: The inclusion criteria, fixed here before any assay was screened and reported in the
#: artefact so the order is visible. §4 limits this project to published data on
#: well-characterised proteins, zero-shot scoring only.
INCLUSION_CRITERIA: tuple[dict[str, str], ...] = (
    {
        "criterion": "published, in a pinned release",
        "rule": (
            "the assay ships in ProteinGym v1.3, pinned by the digests in "
            "`amazebio.proteingym.RELEASE`. No assay enters the register from a paper alone."
        ),
    },
    {
        "criterion": "viral, by the benchmark's own taxon label",
        "rule": (
            "the maintainers' `taxon` column reads `Virus`. Using their label rather than "
            "ours keeps the subset comparable to the published leaderboard, which §B2 asks for."
        ),
    },
    {
        "criterion": "placeable in the pinned taxonomy",
        "rule": (
            "the target protein's organism resolves to an NCBI taxid, via UniProt or, where "
            "UniProt has deleted the entry, via the benchmark's organism string. An assay that "
            "cannot be placed is refused rather than defaulted into the retained arm."
        ),
    },
    {
        "criterion": "zero-shot scoreable, substitutions only",
        "rule": (
            "§4 permits zero-shot scoring and no fine-tuning, and the substitution benchmark is "
            "what the published comparison D-010 cites used. Indels are out of scope."
        ),
    },
)


#: The systematic search D-010 calls for, run 2026-10-20 and recorded whatever it found. The
#: register's own finding sets the specification: the binding constraint is not the total but
#: the **retained arm** — the assays whose families no denylist names — and within it the
#: readout type, which is what the §B5 plan adjusts for. So the search is for published viral
#: DMS assays on families the denylists do not name, with a readout other than cDNA-display
#: proteolysis on a small domain.
EXTENSION_SEARCH: dict[str, Any] = {
    "ran": "2026-10-20",
    "specification": (
        "published viral DMS assays whose protein's family is named by no denylist, with a "
        "readout other than cDNA-display proteolysis, so that the retained arm carries more "
        "than one readout class and more than one study"
    ),
    "sources_searched": [
        {
            "source": "ProteinGym v1.3",
            "how": "the pinned reference file's own taxon labels",
            "found": "31 viral assays, the set this register is built from",
        },
        {
            "source": "MaveDB (api.mavedb.org score-set search)",
            "how": "full-text queries 'phage', 'virus', 'viral'; 83 distinct score sets",
            "found": (
                "no viral assay outside the benchmark's own set that meets the "
                "specification. The phage score sets are Escherichia phage lambda, T7, phage "
                "434 and Lederbergvirus P22 — already in ProteinGym — plus Bruynoghevirus "
                "LUZ24 gp4, Lactococcus virus P2 Mep2 and Xipdecavirus Xp10 p7, every one of "
                "which is trypsin/chymotrypsin digestion from the same cDNA-display "
                "proteolysis study. They would add three families to the retained arm and "
                "**not one new readout class**."
            ),
        },
        {
            "source": "ViroGym (arXiv 2603.06740, NeurIPS 2026)",
            "how": "web search for published viral DMS collections",
            "found": (
                "79 DMS assays over 552,065 mutated sequences with 7 phenotypic readouts, "
                "stated as covering **eukaryotic viruses**. Those fall almost entirely inside "
                "the denylisted families, so it would enlarge the excluded arm and leave the "
                "retained arm as it is. Its data release and licence are not stated on the "
                "arXiv landing page, so acquisition and §4 licence screening are unresolved."
            ),
            "status": "candidate — availability and licence to establish",
        },
    ],
    "verdict": (
        "The extension D-010 contemplated does not exist in the published record as it "
        "stands. More assays are available, but every one of them enlarges an arm that is "
        "already large or adds a family to the retained arm without adding a readout class. "
        "The register's finding is therefore about the design and not about the curation "
        "effort, and it is B5.1's to act on."
    ),
}


def _uniprot_organism(entry_name: str, *, timeout: int = 45) -> dict[str, Any] | None:
    """The entry's own organism from UniProt, or None where UniProt no longer holds it."""
    url = (
        "https://rest.uniprot.org/uniprotkb/search?"
        f"query=id:{entry_name}&fields=organism_id,organism_name,accession&size=3&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as handle:
            payload = json.load(handle)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    live = [r for r in payload.get("results", []) if "organism" in r]
    if len(live) != 1:
        return None
    organism = live[0]["organism"]
    return {
        "taxid": int(organism["taxonId"]),
        "name": organism["scientificName"],
        "accession": live[0].get("primaryAccession"),
    }


def verify_pins(entry_names: list[str]) -> list[dict[str, Any]]:
    """Re-resolve each pinned organism against UniProt and report any disagreement.

    A silently changed taxid moves an assay between the arms of the contrast, so this refuses
    rather than adopts: the pin is the record, and a genuine upstream change is a decision to
    take deliberately, not one to absorb mid-run.
    """
    findings: list[dict[str, Any]] = []
    for name in entry_names:
        pinned = assays.VIRAL_ASSAY_ORGANISMS[name]
        live = _uniprot_organism(name)
        if live is None:
            findings.append(
                {
                    "uniprot_id": name,
                    "status": "not-in-uniprot",
                    "pinned_taxid": pinned.taxid,
                    "pinned_source": pinned.source,
                }
            )
            continue
        findings.append(
            {
                "uniprot_id": name,
                "status": "agrees" if live["taxid"] == pinned.taxid else "DISAGREES",
                "pinned_taxid": pinned.taxid,
                "live_taxid": live["taxid"],
                "live_name": live["name"],
            }
        )
    return findings


def lineages(taxids: set[int], taxdump: str | Path) -> dict[int, dict[str, str]]:
    """Family and order for each taxid, from the pinned NCBI dump."""
    names: dict[int, str] = {}
    parent: dict[int, int] = {}
    rank: dict[int, str] = {}
    with zipfile.ZipFile(Path(taxdump)) as archive:
        with archive.open("names.dmp") as handle:
            for raw in handle:
                fields = [c.strip() for c in raw.decode("utf-8", "replace").split("\t|")]
                if len(fields) > 3 and fields[3] == "scientific name":
                    names[int(fields[0])] = fields[1]
        with archive.open("nodes.dmp") as handle:
            taxonomy = seeds.Taxonomy.from_nodes_dmp(handle)
    parent, rank = taxonomy.parent, taxonomy.rank
    del parent, rank

    out: dict[int, dict[str, str]] = {}
    for taxid in sorted(taxids):
        placed: dict[str, str] = {}
        for level in ("family", "order"):
            node = taxonomy.ancestor_at_rank(taxid, level)
            if node is not None:
                placed[level] = names.get(node, str(node))
        out[taxid] = placed
    return out


def build(
    reference: str | Path,
    taxdump: str | Path,
    *,
    specs: Path,
    verify: bool,
) -> dict[str, Any]:
    all_assays = proteingym.load_reference(reference)
    viral = [a for a in all_assays if a.is_viral]

    denylists: dict[str, Denylist] = {}
    for spec in sorted(specs.glob("*.yaml")):
        if spec.stem in SIMILARITY_POLICIES:
            continue
        policy = policyspec.load_policy(str(spec))
        denylists[spec.stem] = Denylist.from_policy(policy, name=spec.stem)

    placed_lineage = lineages({o.taxid for o in assays.VIRAL_ASSAY_ORGANISMS.values()}, taxdump)
    placements = [
        assays.place(
            a,
            lineage=placed_lineage[assays.VIRAL_ASSAY_ORGANISMS[a.uniprot_id].taxid],
            denylists=denylists,
            similarity_policies=SIMILARITY_POLICIES,
        )
        for a in viral
    ]

    policies = sorted(denylists)
    return {
        "task": TASK,
        "design_ref": "§B2, §7",
        "question": (
            "Do the published collections already give sufficient n for the §B5 homology "
            "regression, or must the viral set be extended? (D-010)"
        ),
        "collection": {
            "name": "ProteinGym",
            "version": proteingym.RELEASE.version,
            "reference_file": proteingym.RELEASE.reference_file,
            "assays_total": len(all_assays),
            "assays_viral": len(viral),
            "licence": (
                "ProteinGym ships under its maintainers' terms and each assay's underlying "
                "data under its own publication's; the per-assay DOI is carried here and "
                "B2.4 publishes the licence register."
            ),
        },
        "inclusion_criteria": list(INCLUSION_CRITERIA),
        "organism_resolution": {
            "primary": "UniProt entry organism",
            "fallback": "benchmark source_organism matched against the pinned NCBI taxonomy",
            "taxonomy": {
                "date": seeds.TAXDUMP_2023_04.date,
                "sha256": seeds.TAXDUMP_2023_04.sha256,
                "url": seeds.TAXDUMP_2023_04.url,
            },
            "deleted_from_uniprot": sorted(
                name
                for name, o in assays.VIRAL_ASSAY_ORGANISMS.items()
                if o.source == "proteingym-name"
            ),
            "verification": verify_pins(sorted(assays.VIRAL_ASSAY_ORGANISMS)) if verify else [],
        },
        "policies_decidable_by_taxon": policies,
        "policies_not_decidable_by_taxon": dict(sorted(SIMILARITY_POLICIES.items())),
        "assays": [p.to_dict() for p in placements],
        "extension_search": EXTENSION_SEARCH,
        "n_assessment": {policy: assays.usable_n(placements, policy) for policy in policies},
        "cross_tabs": {
            policy: {
                attribute: assays.cross_tab(placements, policy, attribute)
                for attribute in ("selection_type", "msa_depth_category")
            }
            for policy in policies
        },
    }


def summarise(doc: dict[str, Any]) -> str:
    policy = doc["policies_decidable_by_taxon"][0]
    n = doc["n_assessment"][policy]
    col = doc["collection"]
    lines = [
        "# B2.2 — the viral assay register",
        "",
        f"{col['name']} {col['version']}: {col['assays_total']} assays, "
        f"**{col['assays_viral']} viral**. Organisms resolved against UniProt and the pinned "
        f"NCBI taxonomy of {doc['organism_resolution']['taxonomy']['date']}.",
        "",
        f"## The contrast §B5 needs, under `{policy}`",
        "",
        f"- excluded arm: **{n['excluded_arm']}** assays across "
        f"{n['distinct_families_excluded']} families",
        f"- retained arm: **{n['retained_arm']}** assays across "
        f"{n['distinct_families_retained']} families",
        "",
        "## Covariate overlap — what the design can and cannot identify",
        "",
    ]
    for attribute, overlap in n["covariate_overlap"].items():
        lines.append(f"**{attribute}**")
        lines.append(f"- in both arms: {overlap['in_both_arms'] or 'none'}")
        lines.append(f"- only in the excluded arm: {overlap['only_in_excluded_arm'] or 'none'}")
        lines.append(f"- only in the retained arm: {overlap['only_in_retained_arm'] or 'none'}")
        lines.append("")
    lines += [
        "## Models whose status this register cannot decide",
        "",
    ]
    for name, why in doc["policies_not_decidable_by_taxon"].items():
        lines.append(f"- **{name}** — {why}")
    lines += ["## The extension search", ""]
    for s in doc["extension_search"]["sources_searched"]:
        lines.append(f"- **{s['source']}** ({s['how']}) — {s['found']}")
    lines += ["", f"**Verdict.** {doc['extension_search']['verdict']}", ""]
    deleted = doc["organism_resolution"]["deleted_from_uniprot"]
    lines += [
        "",
        "## Provenance notes",
        "",
        f"- {len(deleted)} of the benchmark's viral entries have been **deleted from UniProt** "
        f'("not part of a reference proteome"): {", ".join(deleted)}. Their organisms come '
        "from the benchmark's own string, matched against the pinned taxonomy.",
        "",
        "| assay | family | order | readout | MSA depth | variants | DOI |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in sorted(doc["assays"], key=lambda a: (a["family"], a["dms_id"])):
        lines.append(
            f"| {a['dms_id']} | {a['family']} | {a['order']} | {a['selection_type']} | "
            f"{a['msa_depth_category']} | {a['n_variants']:,} | {a['doi']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default="data/proteingym/v1.3/DMS_substitutions.csv")
    parser.add_argument("--taxdump", required=True, help="the pinned taxdmp_2023-04-01.zip")
    parser.add_argument("--specs", default="policies/specs")
    parser.add_argument("--outdir", default="artifacts/b2-2")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip re-resolving the pinned organisms against UniProt (offline runs)",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        with run(
            TASK,
            seed=SEED,
            outdir=outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-register.json",
            durable=objectstore.durable_results("b2-2"),
        ) as manifest:
            manifest.parameter("proteingym_version", proteingym.RELEASE.version)
            manifest.parameter("taxdump_date", seeds.TAXDUMP_2023_04.date)
            manifest.parameter("similarity_policies", sorted(SIMILARITY_POLICIES))
            manifest.input_file(args.reference, role="proteingym-reference")
            manifest.input_file(args.taxdump, role="ncbi-taxdump")
            for spec in sorted(Path(args.specs).glob("*.yaml")):
                manifest.input_file(spec, role="policy-spec")

            doc = build(
                args.reference,
                args.taxdump,
                specs=Path(args.specs),
                verify=not args.no_verify,
            )
            disagreements = [
                f for f in doc["organism_resolution"]["verification"] if f["status"] == "DISAGREES"
            ]
            if disagreements:
                print(
                    "refused: UniProt now disagrees with the pinned organisms for "
                    f"{[f['uniprot_id'] for f in disagreements]}. Settle it as a decision "
                    "rather than adopting the new value mid-run.",
                    file=sys.stderr,
                )
                return 2

            path = outdir / "register.json"
            path.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n")
            manifest.output_file(path, role="assay-register")

            md = outdir / "register.md"
            md.write_text(summarise(doc))
            manifest.output_file(md, role="summary")

            policy = doc["policies_decidable_by_taxon"][0]
            n = doc["n_assessment"][policy]
            manifest.note(
                f"{doc['collection']['assays_viral']} viral assays: {n['excluded_arm']} in the "
                f"excluded arm and {n['retained_arm']} in the retained arm under {policy}."
            )
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except assays.AssayRegisterError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.show:
        print((outdir / "register.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

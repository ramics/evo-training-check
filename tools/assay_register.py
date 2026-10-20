"""B2.4 — the assay provenance and licence register, deliverable 2.

One file that says, for every assay Phase B analyses: where it came from, which pinned bytes it
was read out of, which study produced it, and under what terms any of that may be passed on.
B2.2 settled which assays are in and which arm each falls in; B2.3 settled the control set. This
consolidates both and adds the half neither covers, which is the licence position.

The register is committed rather than left in `artifacts/`, because "publish" and "citable" are
what the deliverable asks for and a file in a git-ignored directory is neither. It carries no
variant-level data — identifiers, taxonomy, counts and provenance only — so committing it is not
redistribution of anybody's assay.

**The licence position has two halves and the register keeps them apart.** The operative grant
is the one on the bytes this project actually read: the pinned ProteinGym release, whose Zenodo
deposit is MIT and whose assay archive is digest-identical to the pinned copy. Each assay also
carries its source article's publisher-deposited licence, which is evidence about the *article*
and not a statement about the supplementary data the article reports. Collapsing the two would
let a CC-BY article stand in for a licence the authors never granted over their data, and would
equally let one restrictive article licence look like a bar on work the MIT deposit plainly
permits. Both appear; the register says which one it relies on and why.

`--check` validates the committed register and its evidence, and CI runs it. It is offline and
reads nothing from `artifacts/`, because CI has no artifacts: the register is the record.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import objectstore  # noqa: E402
from amazebio.repro import run  # noqa: E402

TASK = "B2.4"
SEED = 20261020
CANONICAL_OUT = REPO / "artifacts" / "b2-4"

ASSAYS = REPO / "assays"
EVIDENCE = ASSAYS / "licences.json"
REGISTER = ASSAYS / "register.json"
REGISTER_MD = ASSAYS / "register.md"

B2_2 = REPO / "artifacts" / "b2-2" / "register.json"
B2_3 = REPO / "artifacts" / "b2-3" / "control-set.json"

#: What this project passes on, and what it does not. The distinction is the reason the register
#: can be published at all: every artefact downstream of here is either metadata about an assay
#: or a number this project computed, and neither is somebody else's measurement redistributed.
REDISTRIBUTION = {
    "published_by_this_project": [
        "assay identifiers, organism and taxonomy, family and order, and the arm each assay "
        "falls in under each reading of each filter policy",
        "per-assay counts: variants and sequence length, as the pinned release states them",
        "the DOI of the study that produced each assay",
        "scores this project computed, per variant and per assay, and the rank correlations "
        "derived from them",
    ],
    "not_published_by_this_project": [
        "the measured fitness values themselves — the assay data stays in the pinned release "
        "and is read from it, never re-hosted here",
        "the benchmark's own published model scores, which are read from the pinned release "
        "for the reference check and reported only as an agreement statistic",
    ],
    "why_it_matters": (
        "a register of metadata and of this project's own numbers is publishable under the "
        "deposit's grant whatever each source article's terms say. The source terms are carried "
        "anyway, because a reader going back to an assay needs them"
    ),
}

#: Licence URLs that permit redistribution with attribution, and the ones that do not. A URL not
#: listed is reported as unclassified rather than assumed either way.
PERMISSIVE = {
    "http://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/licenses/by/4.0",
    "https://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/licenses/by/3.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
}
RESTRICTIVE = {
    "https://creativecommons.org/licenses/by-nc-nd/4.0/": "no derivatives, non-commercial",
    "https://journals.asm.org/non-commercial-tdm-license": "non-commercial, text and data "
    "mining only",
    "https://www.elsevier.com/tdm/userlicense/1.0/": "text and data mining only",
    "http://www.elsevier.com/open-access/userlicense/1.0/": "publisher's own open-access terms, "
    "not a standard public licence",
    "https://www.elsevier.com/open-access/userlicense/1.0/": "publisher's own open-access terms, "
    "not a standard public licence",
    "https://www.elsevier.com/legal/tdmrep-license": "text and data mining only",
}


def classify(urls: list[str]) -> dict[str, Any]:
    """What the article's deposited licences permit, without resolving a disagreement silently.

    A publisher may deposit several, for different versions of the work, and they can disagree —
    an open-access CC-BY on the version of record beside a mining-only licence on the accepted
    manuscript. Reporting the most permissive one would overstate it and the most restrictive
    one would understate it, so both are named and the reader is told they differ.
    """
    if not urls:
        return {
            "position": "none deposited",
            "permits_redistribution": None,
            "note": "the publisher deposited no licence with Crossref, so the article's terms "
            "are not established from this evidence",
        }
    permissive = sorted(u for u in urls if u in PERMISSIVE)
    restrictive = sorted(u for u in urls if u in RESTRICTIVE)
    unclassified = sorted(u for u in urls if u not in PERMISSIVE and u not in RESTRICTIVE)
    if unclassified:
        return {
            "position": "unclassified",
            "permits_redistribution": None,
            "unclassified": unclassified,
            "note": "a licence URL this register does not recognise; read it before relying on "
            "the article's terms",
        }
    if permissive and restrictive:
        return {
            "position": "mixed",
            "permits_redistribution": None,
            "permissive": permissive,
            "restrictive": {u: RESTRICTIVE[u] for u in restrictive},
            "note": "the publisher deposited licences that disagree, usually across versions of "
            "the work. Which applies depends on which version is used",
        }
    if restrictive:
        return {
            "position": "restrictive",
            "permits_redistribution": False,
            "restrictive": {u: RESTRICTIVE[u] for u in restrictive},
        }
    return {"position": "permissive", "permits_redistribution": True, "permissive": permissive}


def deposit_position(evidence: dict[str, Any]) -> dict[str, Any]:
    """The grant on the bytes this project read, and how firmly it is established."""
    match = {row["file"]: row for row in evidence["deposit_match"]}
    assay_archive = match.get("DMS_ProteinGym_substitutions.zip", {})
    return {
        "licence": evidence["deposit"]["license"],
        "deposit_doi": evidence["deposit"]["doi"],
        "deposit_url": evidence["deposit"]["url"],
        "downloaded_from": evidence["release"]["downloaded_from"],
        "established_by": assay_archive.get("match"),
        "assay_archive": assay_archive,
        "every_pinned_file": evidence["deposit_match"],
        "limits": [
            "MIT is a software licence. Applying it to a data deposit is ordinary practice on "
            "Zenodo and it is the maintainers' own stated choice, but its effect on data is less "
            "settled than on code. Recorded as the grant relied on, not as a legal conclusion",
            "the deposit's grant is the maintainers'. It does not reach back and relicense the "
            "studies that produced the assays, which is why each study's own terms are carried "
            "per assay below",
        ],
    }


def build(b2_2: dict[str, Any], b2_3: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    works = {w["doi"]: w for w in evidence["works"]}
    control = {a["dms_id"]: a for a in b2_3["control_set"]["assays"]}

    assays = []
    for a in sorted(b2_2["assays"], key=lambda a: a["dms_id"]):
        doi = a.get("doi")
        work = works.get(doi, {"doi": doi, "retrieved": False, "blocker": "no DOI in B2.2"})
        urls = [entry["url"] for entry in work.get("licenses", []) if entry.get("url")]
        assays.append(
            {
                "dms_id": a["dms_id"],
                "uniprot_id": a["uniprot_id"],
                "organism": a["organism"],
                "family": a["family"],
                "order": a["order"],
                "arm": {
                    "excluded_by": a["excluded_by"],
                    "undecidable_by": sorted(a["undecidable_by"]),
                },
                "within_study_positive_control": a["dms_id"] in control,
                "control_because": control.get(a["dms_id"], {}).get("retained_because"),
                "measurement": {
                    "selection_type": a["selection_type"],
                    "msa_depth_category": a.get("msa_depth_category"),
                    "n_variants": a["n_variants"],
                    "seq_len": a["seq_len"],
                },
                "provenance": {
                    "collection": "ProteinGym",
                    "version": evidence["release"]["version"],
                    "read_from": "DMS_ProteinGym_substitutions.zip",
                    "key": f"{a['dms_id']}.csv",
                },
                "source": {
                    "doi": doi,
                    "url": f"https://doi.org/{doi}" if doi else None,
                    "publisher": work.get("publisher"),
                    "container": work.get("container"),
                    "title": work.get("title"),
                    "year": work.get("year"),
                    "deposited_licences": work.get("licenses", []),
                    "article_terms": classify(urls),
                },
            }
        )

    return {
        "task": TASK,
        "design_ref": "§5 deliverable 2, §B2",
        "what_this_is": (
            "the provenance and licence register for every assay Phase B analyses. Generated by "
            "tools/assay_register.py from B2.2's curation, B2.3's control set and the licence "
            "evidence in assays/licences.json. Do not hand-edit"
        ),
        "evidence_retrieved_on": evidence["retrieved_on"],
        "redistribution": REDISTRIBUTION,
        "licence_relied_on": deposit_position(evidence),
        "coverage": coverage(assays),
        "citation": citation(assays, evidence),
        "assays": assays,
    }


def coverage(assays: list[dict[str, Any]]) -> dict[str, Any]:
    positions: dict[str, int] = {}
    for a in assays:
        key = a["source"]["article_terms"]["position"]
        positions[key] = positions.get(key, 0) + 1
    return {
        "assays": len(assays),
        "studies": len({a["source"]["doi"] for a in assays}),
        "organisms": len({a["organism"]["taxid"] for a in assays}),
        "controls": sum(1 for a in assays if a["within_study_positive_control"]),
        "with_a_doi": sum(1 for a in assays if a["source"]["doi"]),
        "article_terms": dict(sorted(positions.items())),
        "note": (
            "every assay is covered by the deposit's grant, which is what this project relies "
            "on. The article-terms breakdown describes the source publications and is carried "
            "for the reader, not as a constraint this project is operating under"
        ),
    }


def citation(assays: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "cite_all_three": [
            "the collection: Notin et al., ProteinGym, Advances in Neural Information "
            "Processing Systems 36 (2023)",
            f"the pinned release as data: {evidence['deposit']['doi']} "
            f"(ProteinGym {evidence['release']['version']}, {evidence['deposit']['url']})",
            "the study that produced the assay, by the DOI carried on its entry below",
        ],
        "why": (
            "citing only the collection drops the groups whose experiments the analysis rests "
            "on, and citing only the studies loses the pinned release a result regenerates from"
        ),
        "this_register": (
            "cite the register by its task id and the commit it was generated at, which the run "
            "manifest in artifacts/b2-4 records"
        ),
    }


def markdown(reg: dict[str, Any]) -> str:
    cov, lic = reg["coverage"], reg["licence_relied_on"]
    lines = [
        "# The assay provenance and licence register",
        "",
        "Generated by `tools/assay_register.py`. Do not hand-edit.",
        "",
        f"{cov['assays']} assays, {cov['studies']} studies, {cov['organisms']} organisms, "
        f"{cov['controls']} of them the within-study positive control.",
        "",
        "## The licence this project relies on",
        "",
        f"The pinned release was downloaded from `{lic['downloaded_from']}`, which states no "
        f"licence. The same release is deposited at [{lic['deposit_doi']}]({lic['deposit_url']}) "
        f"under **{lic['licence']}**, and the assay archive's digest there is identical to the "
        f"pinned copy, so the deposit's grant is the grant on the bytes this project read.",
        "",
    ]
    lines += [f"- {limit}" for limit in lic["limits"]]
    lines += [
        "",
        "| pinned file | established as the deposit's bytes |",
        "|---|---|",
        *[f"| `{row['file']}` | {row['match']} |" for row in lic["every_pinned_file"]],
        "",
        "A file the deposit does not carry is one this project holds only from the maintainers' "
        "own server, where no licence is stated. Nothing downstream redistributes those files, "
        "but a reader should know the deposit's grant has not been shown to cover them.",
        "",
        "## What is published here, and what is not",
        "",
        "Published:",
        *[f"- {x}" for x in REDISTRIBUTION["published_by_this_project"]],
        "",
        "Not published:",
        *[f"- {x}" for x in REDISTRIBUTION["not_published_by_this_project"]],
        "",
        "## The assays",
        "",
        "| assay | organism | family | arm | control | n | study | article terms |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for a in reg["assays"]:
        excluded = a["arm"]["excluded_by"]
        arm = (
            "excluded"
            if all(excluded.values())
            else "retained"
            if not any(excluded.values())
            else "readings disagree"
        )
        doi = a["source"]["doi"] or "—"
        lines.append(
            f"| `{a['dms_id']}` | {a['organism']['name']} | {a['family']} | {arm} | "
            f"{'yes' if a['within_study_positive_control'] else '—'} | "
            f"{a['measurement']['n_variants']} | [{doi}](https://doi.org/{doi}) | "
            f"{a['source']['article_terms']['position']} |"
        )
    lines += [
        "",
        "## Article terms, by position",
        "",
        *[f"- {k}: {v}" for k, v in reg["coverage"]["article_terms"].items()],
        "",
        reg["coverage"]["note"][0].upper() + reg["coverage"]["note"][1:] + ".",
        "",
        "## How to cite",
        "",
        *[f"{i + 1}. {x}" for i, x in enumerate(reg["citation"]["cite_all_three"])],
        "",
        reg["citation"]["why"][0].upper() + reg["citation"]["why"][1:] + ".",
        "",
    ]
    return "\n".join(lines)


def check(reg: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    """Everything that would make the register wrong rather than merely incomplete."""
    problems = []
    if not reg["assays"]:
        problems.append("the register has no assays")

    seen: set[str] = set()
    for a in reg["assays"]:
        key = a["dms_id"]
        if key in seen:
            problems.append(f"{key}: listed twice")
        seen.add(key)
        if not a["source"]["doi"]:
            problems.append(f"{key}: no source DOI, so the assay cannot be traced to a study")
        if a["source"]["article_terms"]["position"] == "unclassified":
            problems.append(
                f"{key}: an unrecognised licence URL "
                f"{a['source']['article_terms']['unclassified']}, which has to be read and "
                f"classified rather than left for a reader to interpret"
            )
        if a["within_study_positive_control"] and not a["control_because"]:
            problems.append(f"{key}: tagged a control with no reason recorded")

    archive = next(
        (r for r in evidence["deposit_match"] if r["file"] == "DMS_ProteinGym_substitutions.zip"),
        None,
    )
    if archive is None:
        problems.append("the licence evidence does not cover the assay archive")
    elif archive["match"] != "digest":
        problems.append(
            "the assay archive is not established to be the deposit's bytes "
            f"({archive['match']}), so the deposit's licence is not shown to apply to it. "
            "Re-run tools/assay_licences.py with --verify DMS_ProteinGym_substitutions.zip"
        )

    if reg["licence_relied_on"]["licence"] != "mit-license":
        problems.append(
            f"the deposit's licence is now {reg['licence_relied_on']['licence']!r}, not the MIT "
            "grant this register was written against. Re-read it before relying on the register"
        )
    unreadable = [w["doi"] for w in evidence["works"] if not w.get("retrieved")]
    if unreadable:
        problems.append(f"licence evidence unreadable for: {', '.join(unreadable)}")
    return problems


def durable_for(out: Path) -> str | None:
    """The durable prefix, **or None for a run that is not the deliverable** (D-224)."""
    if out.resolve() == CANONICAL_OUT.resolve():
        return objectstore.durable_results("b2-4")
    print(f"not publishing: --out {out} is not {CANONICAL_OUT}", file=sys.stderr)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the committed register")
    parser.add_argument("--out", default=CANONICAL_OUT, type=Path)
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    evidence = json.loads(EVIDENCE.read_text())

    if args.check:
        if not REGISTER.exists():
            print(f"{REGISTER} is missing; run tools/assay_register.py", file=sys.stderr)
            return 1
        problems = check(json.loads(REGISTER.read_text()), evidence)
        for problem in problems:
            print(f"problem: {problem}", file=sys.stderr)
        print(f"checked {REGISTER.name}, {len(problems)} problems")
        return 1 if problems else 0

    reg = build(json.loads(B2_2.read_text()), json.loads(B2_3.read_text()), evidence)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    destination = durable_for(out)
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-register.json",
        durable=destination,
        durable_exempt=None if destination else "rehearsal: --out is not the canonical directory",
    ) as m:
        for path in (B2_2, B2_3, EVIDENCE):
            m.input_file(path, role="input")
        m.parameter("zenodo_record", evidence["deposit"]["record"])
        REGISTER.write_text(json.dumps(reg, indent=1, sort_keys=True) + "\n")
        REGISTER_MD.write_text(markdown(reg) + "\n")
        m.output_file(REGISTER, role="register")
        m.output_file(REGISTER_MD, role="register-markdown")

    problems = check(reg, evidence)
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    print(json.dumps(reg["coverage"], indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

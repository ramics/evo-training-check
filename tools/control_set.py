"""Assemble B2.3's within-study positive-control assay set, and test its premise.

`DESIGN.md` §B2 names phage as the internal contrast: "phage is in Evo 2's training data, so
phage performance is a within-study positive control." That sentence has two halves and only
the first is a curation job. The second is a claim about a corpus, and Phase A measured that
corpus, so this tool checks it rather than inheriting it — §B3's whole premise is that Phase A
gives the surviving corpus directly "rather than as an assumption".

What it does, in order: take B2.2's register as the pinned input, select the arm no Evo reading
excludes, resolve each control organism's lineage from the pinned NCBI taxonomy dump, and count
how many of the staged IMG/VR release's high-confidence vOTUs sit at each rank of that lineage.
The counts come back with the corpus denominator attached, because a presence claim without one
is not a measurement.

Two things this does not do, stated because a reader will reasonably wonder. It does not join
the control organisms to the corpus by accession: IMG/VR's vOTUs are metagenomic and carry no
accession these isolates share, so a rank-name count is the strongest honest statement. And it
does not decide ESM3-open's status for any assay, because that filter removes by sequence
similarity rather than by taxon and B2.2's register already refuses to report one.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import imgvr, objectstore, seeds
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent
TASK = "B2.3"
SEED = 20261020
CANONICAL_OUT = REPO / "artifacts" / "b2-3"

#: B2.2's register, which this task curates a subset of rather than re-deriving. Reading it as
#: a file rather than re-running its logic is the point: if the two ever disagreed about which
#: assays are retained, the contrast B5 estimates would depend on which tool a reader ran.
REGISTER = REPO / "artifacts" / "b2-2" / "register.json"

#: The staged IMG/VR release the Evo procedure's input was identified as (D-071), and the
#: high-confidence table, which is the one the released accessions come from.
IMGVR_KEY = "corpora/imgvr/2022-12-20/IMGVR_all_Sequence_information-high_confidence.tsv"

#: The ranks a presence count is reported at, coarsest last. Genus is the tightest rank an
#: IMG/VR lineage string carries that a named isolate can be placed in; class is reported
#: because for most of these organisms it is the only rank with a node at all.
PRESENCE_RANKS = ("genus", "subfamily", "family", "order", "class")

#: IMG/VR's lineage field is eight `;`-separated rank-prefixed fields, the same shape Evo 1's
#: release carries inline (`amazebio.imgvr`). The prefix for each rank this tool reads.
RANK_PREFIX = {
    "genus": b"g__",
    "subfamily": b"sf__",
    "family": b"f__",
    "order": b"o__",
    "class": b"c__",
}


def canonical_out() -> Path:
    return CANONICAL_OUT


def durable_for(out: Path) -> str | None:
    """The durable prefix, **or None for a run that is not the deliverable** (D-224).

    `repro.run`'s `durable` follows from the task id and cannot see where the run was told to
    write, which published a rehearsal to a real results prefix twice in two days. `--out` is
    the signal that separates them.
    """
    if out.resolve() == canonical_out().resolve():
        return objectstore.durable_results("b2-3")
    print(
        f"not publishing: --out {out} is not {canonical_out()}, so this run is a rehearsal",
        file=sys.stderr,
    )
    return None


# --------------------------------------------------------------------------------------
# The control set
# --------------------------------------------------------------------------------------


def retained(register: dict[str, Any]) -> list[dict[str, Any]]:
    """The assays no Evo reading excludes — B2.2's retained arm, which is the control set.

    "Retained by every reading" rather than "retained by one": an assay the readings disagree
    about is not a control, because its membership would depend on which reading B5 used.
    """
    out = []
    for assay in register["assays"]:
        verdicts = assay["excluded_by"]
        if verdicts and not any(verdicts.values()):
            out.append(assay)
    return out


def why_retained(assay: dict[str, Any], no_rank: str) -> str:
    """Whether the denylists spared this assay by decision or could not reach it at all.

    This is the distinction the control's strength turns on. Evo's rules name families and
    orders. An organism whose lineage has no node at either rank is not a member of some
    family the list omits — there is nothing for the rule to test, so it survives by the
    absence of a node. Reporting that as "retained" without the reason would overstate what
    the developer decided about phage.
    """
    family, order = assay.get("family"), assay.get("order")
    if family == no_rank and order == no_rank:
        return "no family node and no order node, so neither denylist rule can fire"
    named = [f"{r} {v}" for r, v in (("family", family), ("order", order)) if v != no_rank]
    return f"has {' and '.join(named)}, which no denylist names"


def control_set(register: dict[str, Any], no_rank: str) -> dict[str, Any]:
    """The curated set, and what it actually spans.

    §B2 asks for an assay set; the thing that governs what the control can show is narrower
    than the assay count, so the breadth is reported in the same object rather than left for
    a reader to derive from a list.
    """
    assays = retained(register)
    organisms: dict[int, dict[str, Any]] = {}
    for assay in assays:
        org = assay["organism"]
        entry = organisms.setdefault(
            org["taxid"],
            {"taxid": org["taxid"], "name": org["name"], "assays": [], "proteins": set()},
        )
        entry["assays"].append(assay["dms_id"])
        entry["proteins"].add(assay["uniprot_id"])
    for entry in organisms.values():
        entry["proteins"] = sorted(entry["proteins"])

    studies = sorted({a["doi"] for a in assays if a.get("doi")})
    readouts = collections.Counter(a.get("selection_type") or "(not stated)" for a in assays)
    return {
        "assays": [
            {
                "dms_id": a["dms_id"],
                "uniprot_id": a["uniprot_id"],
                "organism": a["organism"],
                "family": a["family"],
                "order": a["order"],
                "readout": a.get("selection_type"),
                "n_variants": a.get("n_variants"),
                "seq_len": a.get("seq_len"),
                "msa_depth_category": a.get("msa_depth_category"),
                "doi": a.get("doi"),
                "retained_because": why_retained(a, no_rank),
            }
            for a in sorted(assays, key=lambda a: a["dms_id"])
        ],
        "spans": {
            "assays": len(assays),
            "organisms": len(organisms),
            "proteins": len({a["uniprot_id"] for a in assays}),
            "studies": len(studies),
            "readout_classes": len(readouts),
            "readouts": dict(sorted(readouts.items())),
            "why_this_is_reported": (
                "the assay count is the loosest of these and the only one §B2 names. A control "
                "of seven assays over three organisms and two studies has the independence of "
                "two studies, not of seven assays"
            ),
        },
        "organisms": [organisms[t] for t in sorted(organisms)],
        "studies": studies,
    }


# --------------------------------------------------------------------------------------
# The premise
# --------------------------------------------------------------------------------------


def taxon_names(taxdump: Path) -> dict[int, str]:
    """Scientific name per taxid, from the pinned dump's `names.dmp`."""
    names: dict[int, str] = {}
    with zipfile.ZipFile(taxdump) as archive, archive.open("names.dmp") as handle:
        for raw in handle:
            fields = raw.split(b"\t|\t")
            if len(fields) > 3 and fields[3].startswith(b"scientific name"):
                names[int(fields[0])] = fields[1].decode()
    return names


def lineage_of(taxid: int, taxonomy: seeds.Taxonomy, names: dict[int, str]) -> dict[str, str]:
    """The named ancestor at each reported rank, omitting ranks with no node.

    A rank absent here is absent in the taxonomy, which is itself the finding for most of
    these organisms — so it is left out rather than filled with a placeholder that would
    later be matched against the corpus as if it were a name.
    """
    out: dict[str, str] = {}
    for rank in PRESENCE_RANKS:
        node = taxonomy.ancestor_at_rank(taxid, rank)
        if node and node in names:
            out[rank] = names[node]
    return out


def corpus_presence(
    bucket: str,
    key: str,
    wanted: dict[str, set[str]],
    *,
    max_rows: int | None = None,
    progress: int = 500_000,
) -> dict[str, Any]:
    """Count high-confidence vOTUs whose lineage names each wanted taxon, by rank.

    One pass over the table, matching on the rank-prefixed fields rather than on the line, so
    a genus name that happens to be a substring of a species name cannot inflate a count.
    """
    counts: dict[str, collections.Counter] = {r: collections.Counter() for r in wanted}
    rows = 0
    classified = 0
    raw = objectstore.S3RandomRead(objectstore.client(), bucket, key)
    buf = b""
    header: list[bytes] | None = None
    column = None
    for chunk in iter(lambda: raw.read(1 << 22), b""):
        buf += chunk
        *lines, buf = buf.split(b"\n")
        for line in lines:
            if header is None:
                header = line.split(b"\t")
                column = header.index(imgvr.SEQ_COLUMNS["classification"].encode())
                continue
            rows += 1
            fields = line.split(b"\t")
            if column is None or len(fields) <= column:
                continue
            lineage = fields[column]
            if not lineage.strip(b";"):
                continue
            classified += 1
            parts = lineage.split(b";")
            for rank, names in wanted.items():
                prefix = RANK_PREFIX[rank]
                for part in parts:
                    if part.startswith(prefix):
                        name = part[len(prefix) :].decode()
                        if name in names:
                            counts[rank][name] += 1
                        break
            if max_rows is not None and rows >= max_rows:
                buf = b""
                break
            if rows % progress == 0:
                print(f"  {rows:,} rows", flush=True)
        if max_rows is not None and rows >= max_rows:
            break
    return {
        "rows": rows,
        "rows_with_a_classification": classified,
        "partial": max_rows is not None and rows >= max_rows,
        "counts": {r: dict(sorted(c.items())) for r, c in counts.items()},
    }


def premise(
    organisms: list[dict[str, Any]],
    lineages: dict[int, dict[str, str]],
    presence: dict[str, Any],
) -> dict[str, Any]:
    """Whether each control organism's own lineage is represented in the corpus, and how far.

    The verdict per organism is the tightest rank at which the corpus holds anything, with the
    count. "Present" at class and "present" at genus are different claims and the control's
    strength depends on which one holds, so the rank is part of the answer rather than a
    footnote to it.
    """
    denominator = presence["rows_with_a_classification"]
    out = []
    for org in organisms:
        lineage = lineages.get(org["taxid"], {})
        at_rank = {}
        for rank in PRESENCE_RANKS:
            name = lineage.get(rank)
            if name is None:
                continue
            at_rank[rank] = {
                "name": name,
                "votus": presence["counts"].get(rank, {}).get(name, 0),
            }
        tightest = next((r for r in PRESENCE_RANKS if at_rank.get(r, {}).get("votus", 0) > 0), None)
        out.append(
            {
                "taxid": org["taxid"],
                "name": org["name"],
                "assays": org["assays"],
                "lineage": lineage,
                "at_rank": at_rank,
                "tightest_rank_present": tightest,
                "votus_at_that_rank": at_rank.get(tightest, {}).get("votus") if tightest else 0,
            }
        )
    return {
        "denominator": {
            "votus_with_a_classification": denominator,
            "votus_scanned": presence["rows"],
            "release": "IMG/VR v4.1, 2022-12-20, high-confidence table",
        },
        "by_organism": out,
        "how_this_was_matched": (
            "a name match between the pinned NCBI taxonomy of 2023-04-01 and IMG/VR's own "
            "rank-prefixed lineage field, both of which follow ICTV at these ranks. It is not "
            "an accession join: IMG/VR's vOTUs are metagenomic and these are cultivated "
            "isolates, so no shared accession exists to join on"
        ),
    }


# --------------------------------------------------------------------------------------
# The write-up the artefact carries with it
# --------------------------------------------------------------------------------------


def control_logic(spans: dict[str, Any], premise_block: dict[str, Any]) -> dict[str, Any]:
    """What the control shows, what a null on it means, and where it stops.

    §B2's Done-when asks for the failure interpretation in the artefact rather than only in a
    write-up, because a control whose failure mode is undocumented gets read after the fact as
    whichever reading suits the result.
    """
    thin = [
        o["name"]
        for o in premise_block["by_organism"]
        if (o["tightest_rank_present"] != "genus") or (o["votus_at_that_rank"] or 0) < 100
    ]
    return {
        "what_it_controls_for": (
            "whether poor performance on the excluded arm is attributable to exclusion rather "
            "than to viral proteins being intrinsically hard. Phage is retained by Evo's "
            "procedure, so a model that scores the retained arm well and the excluded arm "
            "poorly separates those two explanations; one that scores both poorly does not"
        ),
        "what_a_null_means": (
            "a null on the control — the retained arm scoring no better than the excluded arm "
            "— does not show the filter had no effect. It shows this control cannot separate "
            "the two explanations, and the most likely reason is in `limits` below. Reporting "
            "a null here as evidence that exclusion does not matter would be the error §2 "
            "names: nothing in the pipeline may be designed so a null is harder to see, and "
            "that cuts both ways"
        ),
        "limits": [
            f"the set spans {spans['organisms']} organisms, {spans['proteins']} proteins and "
            f"{spans['studies']} studies across {spans['assays']} assays, so its independence "
            "is that of the studies, not of the assays",
            "readout is very nearly determined by the arm (D-197), so a difference between "
            "arms measures the readout as much as the exclusion",
            "most of these organisms are retained because their lineage has no family or order "
            "node for Evo's rules to test, not because phage was decided to be in scope",
        ]
        + (
            [
                "the corpus holds little or nothing at the tightest rank for: "
                + ", ".join(thin)
                + " — so for those the control rests on homology to related corpus sequence "
                "rather than on the organism being present, which is §B3's axis and not an "
                "assumption this set may make"
            ]
            if thin
            else []
        ),
        "separable_in_b5": {
            "tag": "within_study_positive_control",
            "rule": (
                "these assays enter B5 as their own stratum and are never pooled with the "
                "excluded arm into a single estimate. §B5's per-assay reporting is the default "
                "everywhere, and the control is reported beside the contrast rather than "
                "inside it"
            ),
            "dms_ids": sorted({a for o in premise_block["by_organism"] for a in o["assays"]}),
        },
    }


def markdown(report: dict[str, Any]) -> str:
    spans = report["control_set"]["spans"]
    lines = [
        "# B2.3 — the within-study positive-control assay set",
        "",
        "Generated by `tools/control_set.py`. Do not hand-edit.",
        "",
        f"{spans['assays']} assays, {spans['organisms']} organisms, {spans['proteins']} "
        f"proteins, {spans['studies']} studies.",
        "",
        "## The set",
        "",
        "| assay | organism | readout | n | len | retained because |",
        "|---|---|---|---:|---:|---|",
    ]
    for a in report["control_set"]["assays"]:
        lines.append(
            f"| `{a['dms_id']}` | {a['organism']['name']} | {a['readout']} | "
            f"{a['n_variants']} | {a['seq_len']} | {a['retained_because']} |"
        )
    lines += [
        "",
        "## Is the premise true? Corpus presence by organism",
        "",
        f"Denominator: {report['premise']['denominator']['votus_with_a_classification']:,} "
        "classified vOTUs in "
        f"{report['premise']['denominator']['release']}.",
        "",
        "| organism | tightest rank present | name | vOTUs |",
        "|---|---|---|---:|",
    ]
    for o in report["premise"]["by_organism"]:
        rank = o["tightest_rank_present"] or "(none)"
        name = o["at_rank"].get(rank, {}).get("name", "—")
        lines.append(f"| {o['name']} | {rank} | {name} | {o['votus_at_that_rank']:,} |")
    lines += ["", "## Control logic", "", report["control_logic"]["what_it_controls_for"], ""]
    lines += ["### What a null means", "", report["control_logic"]["what_a_null_means"], ""]
    lines += ["### Limits", ""] + [f"- {x}" for x in report["control_logic"]["limits"]]
    lines += ["", "### In B5", "", report["control_logic"]["separable_in_b5"]["rule"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=CANONICAL_OUT, type=Path)
    parser.add_argument("--register", default=REGISTER, type=Path)
    parser.add_argument("--taxdump", required=True, type=Path, help="the pinned taxdmp zip")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="stop the corpus scan early; marks the artefact partial and refuses to publish",
    )
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    register = json.loads(args.register.read_text())
    no_rank = register.get("organism_resolution", {}).get("no_rank") or "(no node at this rank)"
    cset = control_set(register, no_rank)

    taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
    names = taxon_names(args.taxdump)
    lineages = {o["taxid"]: lineage_of(o["taxid"], taxonomy, names) for o in cset["organisms"]}

    wanted: dict[str, set[str]] = {r: set() for r in PRESENCE_RANKS}
    for lineage in lineages.values():
        for rank, name in lineage.items():
            wanted[rank].add(name)
    print(f"looking for {sum(len(v) for v in wanted.values())} taxon names in the corpus")

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    destination = None if args.max_rows is not None else durable_for(out)
    with run(
        TASK,
        seed=SEED,
        outdir=out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        manifest_name="run-control-set.json",
        durable=destination,
        durable_exempt=None
        if destination
        else "bounded or rehearsal run: the scan did not cover the release",
    ) as m:
        m.input_file(args.register, role="b2-2 register")
        m.input_file(args.taxdump, role="pinned ncbi taxonomy")
        m.parameter("imgvr_key", IMGVR_KEY)
        m.parameter("presence_ranks", list(PRESENCE_RANKS))
        m.parameter("max_rows", args.max_rows)
        presence = corpus_presence(
            objectstore.CORPORA_BUCKET, IMGVR_KEY, wanted, max_rows=args.max_rows
        )
        premise_block = premise(cset["organisms"], lineages, presence)
        report = {
            "task": TASK,
            "design_ref": "§B2",
            "control_set": cset,
            "premise": premise_block,
            "control_logic": control_logic(cset["spans"], premise_block),
            "corpus_scan": {k: v for k, v in presence.items() if k != "counts"},
            "corpus_counts": presence["counts"],
        }
        path = out / "control-set.json"
        path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        m.output_file(path, role="control-set")
        md = out / "control-set.md"
        md.write_text(markdown(report) + "\n")
        m.output_file(md, role="control-set-markdown")

    print(json.dumps(report["premise"]["by_organism"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""A4.2 — benchmark geNomad's taxonomic misassignment against ratified taxonomy.

Three subcommands, in the order they run. They are separate because the middle one is a
multi-hour compute and a pipeline that cannot be resumed at the step that failed is a pipeline
that gets run with its checks skipped.

    build   select the evaluation set from the pinned VMR, deterministically (D-087)
    fetch   retrieve its sequences from NCBI and write one FASTA
    score   read geNomad's taxonomy output, classify, and emit the artefact (D-088)

The geNomad run between `fetch` and `score` is a single documented command rather than a
subcommand that shells out, so that what produced the labels is visible in the artefact and in
the shell history rather than buried in a `subprocess` call:

    pixi run -e genomad genomad annotate \\
        data/ictv/evalset.fna artifacts/a4-2/genomad \\
        data/genomad/db/genomad_db --threads 4 --splits 8 --cleanup

Everything about *why* this benchmark is shaped as it is lives in D-084 through D-088 and in
`amazebio.genomad`'s module docstring. The short version: geNomad assigns 38.56% of the
denylist's hits and is the only one of the eight assigning methods this audit can run; the
ground truth is the ICTV taxonomy in force when the corpus was built; the unit is the sequence
because that is what a filter acts on; and the headline rate is a lower bound because the
evaluation set is complete genomes and the corpus is assembly fragments.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import genomad, ictv, misassignment, policyspec
from amazebio.repro import run

TASK = "A4.2"
SEED = 20261015

#: Per-family caps, fixed in D-087. In-scope families get more because that is where the
#: leakage rate is measured and where per-family intervals have to be reportable; controls get
#: enough to cover the breadth of what the corpus actually contains (189 families).
IN_SCOPE_CAP = 40
CONTROL_CAP = 8

#: NCBI's E-utilities. Batched because a 2,000-accession GET is refused, and paced because the
#: service asks for it; `tool` and `email` are the identification NCBI's usage policy requires.
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH = 150
PAUSE = 0.4
TOOL_NAME = "amazebio-a4-2"


# --------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------


def _hash_key(accession: str) -> str:
    """Deterministic ordering key, per D-078's precedent.

    A hash of the accession rather than a seeded shuffle: the same set is selected on every
    run from the pinned VMR, with no seed to lose and no dependence on dict ordering.
    """
    return hashlib.sha256(accession.encode()).hexdigest()


def _family_key(exemplar: ictv.Exemplar) -> str:
    """The group a cap applies to.

    Falls back to the order for an exemplar the ICTV has not placed in a family. Those exist
    and they matter here: a record denylisted *by order* with no family of its own is precisely
    the shape the order rules were written for.
    """
    family = exemplar.rank("family")
    if family:
        return family
    order = exemplar.rank("order")
    return f"(order:{order})" if order else "(unplaced)"


def build_evalset(vmr_path: Path, denylist: misassignment.Denylist) -> dict[str, Any]:
    """Select the evaluation set from the pinned VMR, per D-087."""
    table = ictv.read_vmr(vmr_path)

    usable: list[ictv.Exemplar] = []
    excluded: collections.Counter = collections.Counter()
    for item in table.exemplars:
        if not item.accessions:
            excluded["no_accession"] += 1
            continue
        if any(label == "?" for label, _ in item.accessions):
            # Kept visible rather than silently filtered: an unparseable accession is an
            # anomaly in the release, and a shorter evaluation set should never be the way we
            # find out about one.
            excluded["unparseable_accession"] += 1
            continue
        if not item.complete:
            excluded["not_complete"] += 1
            continue
        usable.append(item)

    grouped: dict[str, list[ictv.Exemplar]] = {}
    for item in usable:
        grouped.setdefault(_family_key(item), []).append(item)

    records: list[dict[str, Any]] = []
    per_family: dict[str, dict[str, int]] = {}
    for family, members in sorted(grouped.items()):
        in_scope = denylist.covers(members[0].lineage)
        # Scope is a property of the taxon, so it is constant within a family group — but the
        # order-keyed groups could in principle mix, so it is checked rather than assumed.
        if any(denylist.covers(m.lineage) != in_scope for m in members):
            raise ValueError(f"family group {family!r} mixes in-scope and out-of-scope lineages")
        cap = IN_SCOPE_CAP if in_scope else CONTROL_CAP
        ordered = sorted(members, key=lambda m: _hash_key(m.accessions[0][1]))
        chosen = ordered[:cap]
        per_family[family] = {
            "available": len(members),
            "selected": len(chosen),
            "cap": cap,
            "in_scope": in_scope,
        }
        for item in chosen:
            for label, accession in item.accessions:
                records.append(
                    {
                        "accession": accession,
                        "segment": label,
                        "species": item.species,
                        "family_group": family,
                        "in_scope": in_scope,
                        "lineage": dict(item.lineage),
                        "coverage": item.coverage,
                        "host_source": item.host_source,
                        "vmr_row": item.row,
                    }
                )

    release = ictv.release(ictv.BENCHMARK_RELEASE)
    return {
        "task": TASK,
        "ground_truth": {
            "release": ictv.BENCHMARK_RELEASE,
            "msl": release.msl,
            "published": release.published,
            "filename": release.filename,
            "sha256": release.sha256,
            "note": release.note,
        },
        "selection": {
            "unit": "sequence",
            "unit_reason": (
                "A filter acts on one record at a time and an assembly yields a segmented "
                "virus's segments as separate contigs, so the unit of evaluation is the "
                "sequence, not the species (D-087)."
            ),
            "in_scope_cap": IN_SCOPE_CAP,
            "control_cap": CONTROL_CAP,
            "ordering": "sha256 of the first accession, ascending",
            "completeness_required": True,
            "excluded": dict(excluded),
            "vmr_exemplars": len(table.exemplars),
            "usable_exemplars": len(usable),
        },
        "denylist": {
            "policy": denylist.policy,
            "families": sorted(denylist.families),
            "orders": sorted(denylist.orders),
        },
        "counts": {
            "families": len(per_family),
            "in_scope_families": sum(1 for v in per_family.values() if v["in_scope"]),
            "control_families": sum(1 for v in per_family.values() if not v["in_scope"]),
            "exemplars": sum(v["selected"] for v in per_family.values()),
            "sequences": len(records),
            "in_scope_sequences": sum(1 for r in records if r["in_scope"]),
            "control_sequences": sum(1 for r in records if not r["in_scope"]),
        },
        "per_family": per_family,
        "records": records,
    }


# --------------------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------------------


def _efetch(accessions: list[str], email: str) -> str:
    query = urllib.parse.urlencode(
        {
            "db": "nuccore",
            "id": ",".join(accessions),
            "rettype": "fasta",
            "retmode": "text",
            "tool": TOOL_NAME,
            "email": email,
        }
    ).encode()
    request = urllib.request.Request(EFETCH, data=query)
    last: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
            time.sleep(2**attempt)
    raise RuntimeError(f"efetch failed for {len(accessions)} accessions: {last}")


def _parse_fasta(text: str) -> dict[str, tuple[str, str]]:
    """`{bare_accession: (header, sequence)}` from a FASTA stream."""
    out: dict[str, tuple[str, str]] = {}
    header: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header is not None:
                out[_bare(header)] = (header, "".join(chunks))
            header = line[1:].strip()
            chunks = []
        elif header is not None:
            chunks.append(line.strip())
    if header is not None:
        out[_bare(header)] = (header, "".join(chunks))
    return out


def _bare(header: str) -> str:
    """The accession from a FASTA header, without its version suffix.

    NCBI answers `MK064563` with `MK064563.1`, and the VMR cites both shapes across its rows,
    so the join has to be on the unversioned form or a tenth of the set silently goes missing.
    """
    first = header.split()[0] if header.split() else header
    return first.split(".")[0]


def fetch_sequences(evalset: dict[str, Any], out_fasta: Path, *, email: str) -> dict[str, Any]:
    wanted = sorted({r["accession"] for r in evalset["records"]})
    retrieved: dict[str, tuple[str, str]] = {}
    for start in range(0, len(wanted), BATCH):
        batch = [a.split(".")[0] for a in wanted[start : start + BATCH]]
        retrieved.update(_parse_fasta(_efetch(batch, email)))
        print(f"  fetched {min(start + BATCH, len(wanted)):,}/{len(wanted):,}", flush=True)
        time.sleep(PAUSE)

    lengths: dict[str, int] = {}
    missing: list[str] = []
    with out_fasta.open("w") as handle:
        for accession in wanted:
            key = accession.split(".")[0]
            if key not in retrieved:
                missing.append(accession)
                continue
            _, sequence = retrieved[key]
            if not sequence:
                missing.append(accession)
                continue
            # Written under the accession the evaluation set keys on, not NCBI's header, so
            # the join back from geNomad's output needs no second mapping.
            handle.write(f">{accession}\n")
            for offset in range(0, len(sequence), 70):
                handle.write(sequence[offset : offset + 70] + "\n")
            lengths[accession] = len(sequence)

    return {
        "requested": len(wanted),
        "written": len(lengths),
        "missing": missing,
        "bases": sum(lengths.values()),
        "lengths": lengths,
    }


# --------------------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------------------


def _call_index(
    calls: dict[str, genomad.TaxonomyCall],
) -> dict[str, genomad.TaxonomyCall]:
    """Index the tool's calls by both the name it used and that name without its version.

    The join is the one place in this pipeline where a mistake produces a spectacular result
    rather than an obviously broken one. geNomad echoes the FASTA name it was given; the
    evaluation set keys on the VMR's accession, which is usually unversioned while NCBI's own
    FASTA headers are not. Join the two strictly and every record comes back unclassified —
    which this pipeline would report, perfectly consistently, as a 100% escape rate.

    So both forms are indexed, and :func:`score` refuses a run where nothing joined at all.
    """
    index: dict[str, genomad.TaxonomyCall] = {}
    for name, call in calls.items():
        index.setdefault(name, call)
        index.setdefault(name.split(".")[0], call)
    return index


def score(
    evalset: dict[str, Any],
    fetched: dict[str, Any],
    calls: dict[str, genomad.TaxonomyCall],
    denylist: misassignment.Denylist,
    *,
    dependency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify every record and assemble the artefact, per D-088."""
    lengths: dict[str, int] = fetched["lengths"]
    index = _call_index(calls)
    matched = 0
    judgements: list[misassignment.Judgement] = []
    anomalies: list[dict[str, Any]] = []
    not_submitted = 0

    for record in evalset["records"]:
        accession = record["accession"]
        if accession not in lengths:
            # Never retrieved, so never offered to the tool. Counted, and excluded from every
            # denominator: a sequence the benchmark could not obtain is not a sequence the tool
            # failed on, and folding the two together would invent leakage.
            not_submitted += 1
            continue
        call = index.get(accession) or index.get(accession.split(".")[0])
        if call is not None:
            matched += 1
        if call is not None and call.anomalies:
            anomalies.append({"accession": accession, "anomalies": list(call.anomalies)})
        judgements.append(
            misassignment.classify(
                record=accession,
                species=record["species"],
                true_lineage=record["lineage"],
                predicted_lineage=dict(call.lineage) if call else {},
                denylist=denylist,
                # Always True: `annotate` makes no virus call, so absence of a taxonomy row is
                # an unclassified record rather than a non-viral one. See genomad.SCOPE_NOTE.
                called_viral=True,
                length=lengths.get(accession),
            )
        )

    if calls and judgements and matched == 0:
        # Loud rather than plausible. Every record unclassified is indistinguishable, in the
        # arithmetic, from a tool that classified nothing — and it would be published as a
        # 100% escape rate. The names are shown so the mismatch is diagnosable.
        raise ValueError(
            "no evaluation-set accession matched any sequence in the taxonomy output: "
            f"{len(judgements)} records scored, {len(calls)} calls read. "
            f"Example record {judgements[0].record!r}; example call "
            f"{next(iter(calls))!r}. This is a join failure, not a 100% escape rate."
        )

    rates = misassignment.rates(judgements)
    per_family = misassignment.per_family(judgements)
    strata = misassignment.length_strata(
        judgements,
        edges=(0, 2_500, 5_000, 10_000, 20_000, 40_000, 80_000, 200_000),
    )

    propagation: dict[str, Any] | None = None
    if dependency and "escape" in rates:
        hits = dependency["denylisted_records"]["records"]
        genomad_share = dependency["denylisted_records"]["genomad_share"] or 0.0
        corpus = dependency["release"]["records"]
        propagation = misassignment.propagate(
            escape=rates["escape"],
            corpus_records=corpus,
            removed_records=int(round(hits * genomad_share)),
            label=(
                "Leakage implied by the measured escape rate, from the records the denylist "
                "removed on a geNomad-assigned label. Covers the geNomad share of the "
                "denylist's hits only."
            ),
        )
        propagation["coverage"] = {
            "denylist_hits": hits,
            "genomad_share_of_hits": genomad_share,
            "unmeasured_share_of_hits": 1.0 - genomad_share,
            "unmeasured_reason": (
                "The remaining hits rest on taxonomies imported from other datasets (RVMT, "
                "NCBI NR, vOTU consensus, RefSeq, GVMAG), which are not tools this audit can "
                "run. A4.4 owns them (D-084)."
            ),
        }

    # Where the escape rate is 0 the artefact must still say what the data excludes, so the
    # interval is reported rather than a bare zero. `clopper_pearson` guarantees a non-zero
    # upper bound, which is the whole reason D-088 chose the exact method.
    return {
        "task": TASK,
        "question": (
            "What is geNomad's taxonomic misassignment rate on viral sequence, by error "
            "direction, and how much filter leakage does it imply?"
        ),
        "tool_under_test": {
            **genomad.PIN.to_dict(),
            "version_evidence": genomad.VERSION_EVIDENCE,
            "scope": genomad.SCOPE_NOTE,
        },
        "ground_truth": evalset["ground_truth"],
        "evaluation_set": {
            **evalset["counts"],
            "selection": evalset["selection"],
            "sequences_submitted": len(judgements),
            "sequences_with_a_taxonomy_row": matched,
            "sequences_not_retrieved": not_submitted,
            "bases_submitted": fetched["bases"],
            "accessions_missing": fetched["missing"],
            "bias": [
                "Complete reference genomes, which is the easiest case for a marker-based "
                "classifier; the corpus is 84.67% assembly fragments. Every rate here is "
                "therefore a lower bound on the corpus-side rate.",
                "ICTV exemplars are the best-studied isolate of each species, so their marker "
                "genes are the ones most likely to be represented in a marker database built "
                "from reference genomes.",
                "One isolate per species, so the rate is not weighted by how many isolates of "
                "a virus have been sequenced — but it is still shaped by which species the "
                "ICTV has ratified, which is why per-family results are the default "
                "presentation and the pooled figure is secondary.",
            ],
        },
        "rates": rates,
        "per_family": per_family,
        "length_strata": strata,
        "propagation": propagation,
        "lineage_anomalies": anomalies,
        "judgements": [j.to_dict() for j in judgements],
    }


def render(result: dict[str, Any]) -> str:
    """The artefact as prose, for a reader who will not open the JSON."""
    lines: list[str] = []
    rates = result["rates"]
    pin = result["tool_under_test"]
    out = lines.append

    out("# A4.2 — taxonomy-tool misassignment")
    out("")
    out(f"**Tool under test:** geNomad {pin['genomad']}, marker database v{pin['marker_database']}")
    out(f"(mmseqs2 {pin['mmseqs2']}, split {pin['mmseqs2_splits']} ways).")
    out("The version is a bound, not a statement by the publisher — see D-085.")
    out("")
    gt = result["ground_truth"]
    out(f"**Ground truth:** ICTV {gt['msl']}, {gt['filename']} (published {gt['published']}).")
    out("")
    out(f"**Scope.** {pin['scope']}")
    out("")

    counts = result["evaluation_set"]
    out("## Evaluation set")
    out("")
    out(
        f"- {counts['sequences_submitted']:,} sequences scored, "
        f"{counts['bases_submitted']:,} bases, from {counts['exemplars']:,} ICTV exemplars"
    )
    out(
        f"- {counts['in_scope_families']} denylisted families/orders, "
        f"{counts['control_families']} control families"
    )
    if counts["sequences_not_retrieved"]:
        out(
            f"- {counts['sequences_not_retrieved']:,} sequences could not be retrieved and are "
            "excluded from every denominator"
        )
    out("")

    out("## Error rates, by direction")
    out("")
    out("| direction | numerator | denominator | rate | 95% CI |")
    out("|---|---|---|---|---|")
    for key in ("escape", "spurious_removal"):
        if key not in rates:
            continue
        entry = rates[key]
        out(
            f"| {key} | {entry['numerator']:,} | {entry['denominator']:,} | "
            f"{entry['point']:.2%} | {entry['ci_lower']:.2%}-{entry['ci_upper']:.2%} |"
        )
    out("")
    if "escape" in rates:
        out("### Escape, by cause")
        out("")
        out("| cause | records |")
        out("|---|---|")
        for cause, count in sorted(rates["escape"]["causes"].items(), key=lambda kv: -kv[1]):
            out(f"| {cause} | {count:,} |")
        out("")

    if result["per_family"]:
        out("## Escape rate per family")
        out("")
        out("Per family before pooled: a pooled rate over this set is weighted by how many")
        out("species the ICTV has ratified in each family.")
        out("")
        out("| family | escapes | records | rate | 95% CI |")
        out("|---|---|---|---|---|")
        ordered = sorted(
            result["per_family"].items(), key=lambda kv: (-kv[1]["point"], -kv[1]["denominator"])
        )
        for family, entry in ordered:
            out(
                f"| {family} | {entry['numerator']} | {entry['denominator']} | "
                f"{entry['point']:.1%} | {entry['ci_lower']:.1%}-{entry['ci_upper']:.1%} |"
            )
        out("")

    if result["length_strata"]:
        out("## Escape rate by length")
        out("")
        out("| bases | escapes | records | rate | 95% CI |")
        out("|---|---|---|---|---|")
        for entry in result["length_strata"]:
            out(
                f"| {entry['label']} | {entry['numerator']} | {entry['denominator']} | "
                f"{entry['point']:.1%} | {entry['ci_lower']:.1%}-{entry['ci_upper']:.1%} |"
            )
        out("")

    prop = result["propagation"]
    if prop:
        out("## Propagation into filter leakage")
        out("")
        cov = prop["coverage"]
        out(
            f"- The denylist removed {cov['denylist_hits']:,} records; "
            f"{cov['genomad_share_of_hits']:.2%} of them on a geNomad-assigned label."
        )
        if prop["escaping_records"]["point"] is None:
            out("- Escaping records are undefined at an escape rate of 1: nothing in scope was")
            out("  removed, so the removals carry no information about how many there were.")
        else:
            out(
                f"- That implies an in-scope population of "
                f"{prop['implied_in_scope_records']:,.0f} records, of which "
                f"{prop['escaping_records']['point']:,.0f} escaped "
                f"({prop['escaping_records']['ci_lower']:,.0f}-"
                f"{prop['escaping_records']['ci_upper']:,.0f})."
            )
            out(f"- Arithmetic: {prop['arithmetic']}")
        out(f"- **This is a {prop['bound']} bound.** {prop['bound_reason']}")
        out(
            f"- {cov['unmeasured_share_of_hits']:.2%} of the hits are unmeasured. "
            f"{cov['unmeasured_reason']}"
        )
        out("")

    out("## Bias in the evaluation set")
    out("")
    for item in counts["bias"]:
        out(f"- {item}")
    out("")

    if result["lineage_anomalies"]:
        out(f"## Lineage anomalies ({len(result['lineage_anomalies'])})")
        out("")
        out("Positional rank reads that disagreed with the ICTV suffix. Recorded, not resolved.")
        out("")
        for item in result["lineage_anomalies"][:20]:
            out(f"- `{item['accession']}`: {'; '.join(item['anomalies'])}")
        out("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["build", "fetch", "score"])
    parser.add_argument("--vmr", default="data/ictv/vmr_msl37.3.xlsx")
    parser.add_argument("--policy", default="policies/specs/evo1-literal.yaml")
    parser.add_argument("--outdir", default="artifacts/a4-2")
    parser.add_argument("--fasta", default="data/ictv/evalset.fna")
    parser.add_argument("--taxonomy", default="artifacts/a4-2/genomad/evalset_annotate")
    parser.add_argument("--email", default="imostuartwright@gmail.com")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    policy = policyspec.load_policy(args.policy)
    denylist = misassignment.Denylist.from_policy(policy, name=Path(args.policy).stem)
    evalset_path = outdir / "evalset.json"
    fetched_path = outdir / "fetched.json"

    if args.step == "build":
        with run(
            TASK,
            seed=SEED,
            outdir=outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-build.json",
        ) as manifest:
            manifest.parameter("in_scope_cap", IN_SCOPE_CAP)
            manifest.parameter("control_cap", CONTROL_CAP)
            manifest.parameter("ground_truth_release", ictv.BENCHMARK_RELEASE)
            manifest.parameter("unit", "sequence")
            manifest.input_file(args.vmr, role="ictv/vmr")
            manifest.input_file(args.policy, role="policy-spec")
            built = build_evalset(Path(args.vmr), denylist)
            evalset_path.write_text(json.dumps(built, indent=1) + "\n")
            manifest.output_file(evalset_path, role="evalset")
        counts = built["counts"]
        print(f"{counts['exemplars']:,} exemplars -> {counts['sequences']:,} sequences")
        print(
            f"  in scope: {counts['in_scope_sequences']:,} "
            f"across {counts['in_scope_families']} families"
        )
        print(
            f"  controls: {counts['control_sequences']:,} "
            f"across {counts['control_families']} families"
        )
        print(f"wrote {evalset_path}")
        return 0

    evalset = json.loads(evalset_path.read_text())

    if args.step == "fetch":
        fasta = Path(args.fasta)
        fasta.parent.mkdir(parents=True, exist_ok=True)
        fetched = fetch_sequences(evalset, fasta, email=args.email)
        fetched_path.write_text(json.dumps(fetched, indent=1) + "\n")
        print(
            f"{fetched['written']:,}/{fetched['requested']:,} sequences, "
            f"{fetched['bases']:,} bases -> {fasta}"
        )
        if fetched["missing"]:
            print(f"  {len(fetched['missing'])} not retrieved")
        return 0

    fetched = json.loads(fetched_path.read_text())
    taxonomy = Path(args.taxonomy)
    if taxonomy.is_dir():
        candidates = sorted(taxonomy.glob("*_taxonomy.tsv"))
        if not candidates:
            raise SystemExit(f"no *_taxonomy.tsv under {taxonomy}")
        taxonomy = candidates[0]
    dependency_path = outdir / "dependency.json"
    dependency = json.loads(dependency_path.read_text()) if dependency_path.exists() else None

    with run(
        TASK,
        seed=SEED,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        # See the note in tools/taxonomy_dependency.py: one manifest per step, or the last
        # pipeline to finish erases the provenance of the artefacts it did not produce.
        manifest_name="run-score.json",
    ) as manifest:
        manifest.parameter("confidence", 0.95)
        manifest.parameter("interval_method", "clopper-pearson")
        manifest.parameter("genomad_version", genomad.PIN.version)
        manifest.parameter("genomad_database", genomad.PIN.database_version)
        manifest.input_file(evalset_path, role="evalset")
        manifest.input_file(taxonomy, role="genomad/taxonomy")
        if dependency:
            manifest.input_file(dependency_path, role="dependency")
        calls = genomad.read_taxonomy(taxonomy)
        result = score(evalset, fetched, calls, denylist, dependency=dependency)
        json_path = outdir / "misassignment.json"
        md_path = outdir / "misassignment.md"
        json_path.write_text(json.dumps(result, indent=1) + "\n")
        md_path.write_text(render(result))
        manifest.output_file(json_path, role="result")
        manifest.output_file(md_path, role="report")

    rates = result["rates"]
    if "escape" in rates:
        entry = rates["escape"]
        print(
            f"escape: {entry['numerator']}/{entry['denominator']} = {entry['point']:.2%} "
            f"({entry['ci_lower']:.2%}-{entry['ci_upper']:.2%})"
        )
    if "spurious_removal" in rates:
        entry = rates["spurious_removal"]
        print(
            f"spurious removal: {entry['numerator']}/{entry['denominator']} = "
            f"{entry['point']:.2%} ({entry['ci_lower']:.2%}-{entry['ci_upper']:.2%})"
        )
    print(f"wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

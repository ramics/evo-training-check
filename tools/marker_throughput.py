#!/usr/bin/env python3
"""Price a marker-profile pass over Evo 1's surviving viral component — A2.5's label-free arm.

    pixi run -e dev python tools/marker_throughput.py --records 1500

A2.5's label-side census (D-187) leaves two of its four categories resting on 2.6% of Evo 1's
surviving records: only that share carries a family-level label, so "no segmented genomes" and
"no satellite nucleic acids" are statements about labels rather than about content. The arm that
would not depend on labels is a marker-profile search over the records themselves, and the
standing decision is to **measure what it would cost before committing to any of it** — the
pattern D-183 and D-186 set for A2.3, where the first projection was wrong by a factor of ten and
only a second measurement point exposed it.

This tool is that measurement and nothing more. **It produces no biological result and must not be
read as one.**

**Two things about the method are deliberate and limit what the numbers mean.**

**It reads a prefix, not a sample.** Hash-band selection is a property of the record id, so
drawing even a 0.1% band still reads the whole 16.9 GB object to find its members — which is the
cost this run exists to avoid paying twice. So it reads the first `--records` rows and stops.
D-046 is explicit that a prefix of this corpus is not a sample of it, and that stands: these
figures are throughput, and no count here is an estimate of anything in the corpus. Throughput is
the one quantity a prefix measures honestly, because gene calling and search cost scale with bases
and residues rather than with which records they came from.

**The timed profiles are synthetic, and that is a stated approximation.** A real pass would search
curated models, and none are staged — A2.1's registries were written to a git-ignored directory
and did not survive (D-188), and re-downloading Pfam to time a search would cost more than the
search. So the profiles are built from the called proteins themselves with `pyhmmer`'s own
builder. For a *timing* measurement the content of a profile is close to irrelevant: `hmmsearch`
cost is driven by model length times residues searched, and the models built here are drawn from
the same length distribution the pass would actually meet. What this cannot capture is a curated
model's entropy, which changes how early the filters discard a sequence. So the per-profile rate
is cross-checked against the one published measurement over real models — A2.1's 386 core-seconds
per million residues against RVDB-prot's 13,679 profiles (D-098) — and both are reported. **If
they disagree, the published figure wins and this one is the artefact of the approximation.**

The extrapolation targets Evo 1's `stage2` component because that is where the weak zeros are:
2,652,952 surviving records over 36,236,025,613 bases, from A1.4's manifest and A7.1's census.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from amazebio import corpora, objectstore, profilesearch, seqstream
from amazebio.repro import run

SEED = 20261019

#: Evo 1's surviving viral component, from A1.4's manifest (2,653,047 released less the 95 the
#: readings remove) and A7.1's census of the same object. Named rather than recomputed: this run
#: reads a prefix and must not appear to have counted the corpus.
EVO1_SURVIVING_RECORDS = 2_652_952
EVO1_TOTAL_BASES = 36_236_025_613

#: A2.1's measured search rate over **real** models, as `metrics/detections.md` records it from
#: D-098: 386 core-seconds per million residues against RVDB-prot's 13,679 profiles. The
#: per-profile figure this implies is the yardstick for the synthetic measurement below.
A2_1_CORE_SECONDS_PER_MAA = 386.0
A2_1_PROFILES = 13_679

#: Marker-set sizes the extrapolation is reported at. The lower end is what the categories
#: actually have: NCLDV's core gene set is a handful of models, and the satellite arm has one
#: (alphasatellite Rep). The upper end is a Pfam-viral-scale pass, for contrast.
MARKER_COUNTS = (5, 10, 50, 200, 1719)

#: On-demand price of the instance class A1.6's and A2.4's passes used, for turning core-hours
#: into money. Approximate and only ever quoted as "about".
USD_PER_CORE_HOUR = 0.0504


def read_prefix(client: Any, records: int) -> tuple[list[Any], dict[str, Any]]:
    """The first `records` rows of Evo 1's stage 2, with sequence. A prefix, not a sample."""
    source = next(
        s
        for s in corpora.sources_for("opengenome")
        if s.corpus_component == "stage2" and s.readable and "train" in s.key
    )
    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if source.bytes and live != source.bytes:
        raise SystemExit(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}."
        )
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes or live,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,}: {exc}", file=sys.stderr
        ),
    )
    started = time.monotonic()
    out: list[Any] = []
    # hi=1.0 takes every row, so the band does no selecting: the limit is what bounds the read.
    for sampled in seqstream.iter_stage2_sampled(
        obj.buffered(),
        component=source.component,
        record_prefix=source.corpus_component + ":" + Path(source.key).name,
        seed=SEED,
        lo=0.0,
        hi=1.0,
    ):
        out.append(sampled)
        if len(out) >= records:
            break
    read_seconds = time.monotonic() - started
    bases = sum(len(r.sequence) for r in out)
    return out, {
        "key": source.key,
        "records": len(out),
        "bases": bases,
        "mean_record_bases": (bases / len(out)) if out else None,
        "read_seconds": round(read_seconds, 2),
        "selection": "prefix of the object, not a sample (D-046)",
    }


def time_gene_calling(records: list[Any], threads: int) -> dict[str, Any]:
    """Wall and core seconds for `profilesearch.call_genes` over the prefix.

    The same call A2.1 and A2.5's own arm would make, in metagenomic mode (D-077), so the figure
    is the one a real pass would pay rather than a reimplementation's.
    """
    started = time.monotonic()
    proteins, stats = profilesearch.call_genes(records)
    wall = time.monotonic() - started
    bases = sum(len(r.sequence) for r in records)
    return {
        "proteins": len(proteins),
        "wall_seconds": round(wall, 2),
        # pyrodigal's finder here is single-threaded, so core-seconds are wall-seconds. Recorded
        # explicitly rather than assumed, because the search below is not.
        "core_seconds": round(wall, 2),
        "threads_used": 1,
        "core_seconds_per_mbp": round(wall / (bases / 1e6), 3) if bases else None,
        "residues_per_base": round(stats["residues"] / bases, 4) if bases else None,
        **stats,
    }, proteins


def synthetic_profiles(proteins: list[Any], count: int) -> list[Any]:
    """`count` HMMs built from the called proteins, for timing only.

    Single-sequence models, so they carry none of a curated family's information content. They
    exist to put a realistic model-length distribution in front of `hmmsearch`; see this module's
    docstring for what that does and does not license.
    """
    from pyhmmer.plan7 import Background, Builder

    alphabet = proteins[0].alphabet
    background = Background(alphabet)
    builder = Builder(alphabet, seed=SEED)
    built = []
    # Longest first so a small count is not a set of unrepresentative short models.
    for i, protein in enumerate(sorted(proteins, key=lambda p: -len(p.sequence))[:count]):
        named = protein.copy()
        named.name = f"synthetic{i}".encode()
        hmm, _, _ = builder.build(named, background)
        built.append(hmm)
    return built


def time_search(proteins: list[Any], counts: tuple[int, ...], threads: int) -> list[dict[str, Any]]:
    """`hmmsearch` timings at several profile counts, so the rate can be fitted rather than
    assumed linear — the error D-186 was corrected for."""
    import pyhmmer

    residues = sum(len(p.sequence) for p in proteins)
    rows = []
    for count in counts:
        if count > len(proteins):
            rows.append({"profiles": count, "skipped": "fewer proteins than profiles requested"})
            continue
        models = synthetic_profiles(proteins, count)
        started = time.monotonic()
        hits = 0
        for top in pyhmmer.hmmsearch(models, proteins, cpus=threads):
            hits += len(top)
        wall = time.monotonic() - started
        maa = residues / 1e6
        rows.append(
            {
                "profiles": count,
                "model_length_mean": round(sum(m.M for m in models) / len(models), 1),
                "residues_searched": residues,
                "wall_seconds": round(wall, 2),
                "core_seconds": round(wall * threads, 2),
                "threads": threads,
                "core_seconds_per_maa": round(wall * threads / maa, 3) if maa else None,
                "core_seconds_per_profile_per_maa": (
                    round(wall * threads / maa / count, 6) if maa else None
                ),
                "hits": hits,
            }
        )
        print(
            f"  search {count:>5} profiles: {wall:.1f}s wall, "
            f"{rows[-1]['core_seconds_per_maa']} core-s/Maa",
            file=sys.stderr,
        )
    return rows


def project(gene: dict[str, Any], search: list[dict[str, Any]]) -> dict[str, Any]:
    """Cost of the full pass over Evo 1's surviving component, per marker-set size.

    Gene calling is charged once; it does not scale with the marker set and it is expected to
    dominate at the set sizes these categories actually have.
    """
    calling_core_hours = (
        gene["core_seconds_per_mbp"] * (EVO1_TOTAL_BASES / 1e6) / 3600
        if gene["core_seconds_per_mbp"]
        else None
    )
    measured = [r for r in search if "core_seconds_per_profile_per_maa" in r]
    # Fit at the largest measured point: the small ones are dominated by fixed overhead, which is
    # exactly the sublinearity D-186 had to correct for.
    anchor = max(measured, key=lambda r: r["profiles"]) if measured else None
    per_profile_maa = anchor["core_seconds_per_profile_per_maa"] if anchor else None
    total_residues_maa = EVO1_TOTAL_BASES * (gene["residues_per_base"] or 0) / 1e6

    rows = []
    for count in MARKER_COUNTS:
        search_core_hours = (
            per_profile_maa * count * total_residues_maa / 3600 if per_profile_maa else None
        )
        total = (
            (calling_core_hours or 0) + (search_core_hours or 0)
            if calling_core_hours is not None and search_core_hours is not None
            else None
        )
        rows.append(
            {
                "markers": count,
                "gene_calling_core_hours": round(calling_core_hours, 1)
                if calling_core_hours
                else None,
                "search_core_hours": round(search_core_hours, 1) if search_core_hours else None,
                "total_core_hours": round(total, 1) if total else None,
                "approx_usd": round(total * USD_PER_CORE_HOUR, 2) if total else None,
            }
        )
    return {
        "target": {
            "component": "opengenome/stage2",
            "surviving_records": EVO1_SURVIVING_RECORDS,
            "bases": EVO1_TOTAL_BASES,
            "projected_residues_maa": round(total_residues_maa, 1),
            "source": "A1.4's manifest and A7.1's census; not counted by this run",
        },
        "anchor_profiles": anchor["profiles"] if anchor else None,
        "by_marker_count": rows,
        "cross_check": {
            "a2_1_core_seconds_per_maa": A2_1_CORE_SECONDS_PER_MAA,
            "a2_1_profiles": A2_1_PROFILES,
            "a2_1_per_profile_per_maa": round(A2_1_CORE_SECONDS_PER_MAA / A2_1_PROFILES, 6),
            "this_run_per_profile_per_maa": per_profile_maa,
            "ratio_this_over_published": (
                round(per_profile_maa / (A2_1_CORE_SECONDS_PER_MAA / A2_1_PROFILES), 2)
                if per_profile_maa
                else None
            ),
            "reading": (
                "The published figure is over curated models and wins where they disagree; a "
                "ratio far from 1 is the cost of this run's synthetic profiles, not a correction "
                "to D-098."
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=1500, help="prefix size to time")
    parser.add_argument("--out", default="artifacts/a2-5", type=Path)
    parser.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--profile-counts", default="5,25,100")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    counts = tuple(int(x) for x in args.profile_counts.split(",") if x)

    client = objectstore.client()
    with run(
        "A2.5",
        seed=SEED,
        outdir=args.out,
        allow_dirty=args.allow_dirty,
        manifest_name="run-marker-throughput.json",
        durable=objectstore.durable_results("a2-5"),
    ) as m:
        m.parameter("records_timed", args.records)
        m.parameter("threads", args.threads)
        m.parameter("profile_counts", list(counts))
        m.parameter("selection", "prefix of the object, not a sample (D-046)")
        m.parameter("profiles", "synthetic single-sequence models, for timing only")
        m.parameter("target_records", EVO1_SURVIVING_RECORDS)
        m.parameter("target_bases", EVO1_TOTAL_BASES)
        m.note(
            "A throughput measurement. It produces no biological result: the read is a prefix "
            "rather than a sample, and the timed profiles are synthetic. Cost figures only."
        )

        import pyhmmer
        import pyrodigal

        m.tools["pyhmmer"] = pyhmmer.__version__
        m.tools["pyrodigal"] = pyrodigal.__version__
        m.tools["hmmer"] = getattr(pyhmmer, "HMMER_VERSION", None)

        print(f"reading a {args.records}-record prefix of Evo 1 stage 2 ...", file=sys.stderr)
        records, read_stats = read_prefix(client, args.records)
        print(
            f"  {read_stats['records']:,} records, {read_stats['bases']/1e6:.1f} Mbp "
            f"in {read_stats['read_seconds']}s",
            file=sys.stderr,
        )

        print("calling genes ...", file=sys.stderr)
        gene, proteins = time_gene_calling(records, args.threads)
        print(
            f"  {gene['genes']:,} genes, {gene['residues']/1e6:.1f} Maa, "
            f"{gene['core_seconds_per_mbp']} core-s/Mbp",
            file=sys.stderr,
        )

        search = time_search(proteins, counts, args.threads)
        projection = project(gene, search)

        payload = {
            "task": "A2.5",
            "measurement": "marker-pass throughput",
            "decision": "D-187",
            "read": read_stats,
            "gene_calling": gene,
            "search": search,
            "projection": projection,
            "caveats": [
                "A prefix of the object, not a sample: no count here estimates anything in the "
                "corpus (D-046).",
                "Timed against synthetic single-sequence profiles; the per-profile rate is "
                "cross-checked against D-098's measurement over curated models, which wins.",
                "Gene calling is single-threaded here and is charged once, since it does not "
                "scale with the marker set.",
                "Segmented-genome membership has no sequence marker at all, so no marker pass "
                "can strengthen that category's zero however cheap it is (D-187).",
            ],
        }
        out = args.out / "marker-throughput.json"
        out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        m.output_file(out, role="marker-throughput")

        print("\n--- projected cost over Evo 1's surviving component ---", file=sys.stderr)
        for row in projection["by_marker_count"]:
            print(
                f"  {row['markers']:>5} markers: {row['total_core_hours']} core-h "
                f"(~${row['approx_usd']})  [calling {row['gene_calling_core_hours']}, "
                f"search {row['search_core_hours']}]",
                file=sys.stderr,
            )
        print(
            f"\ncross-check vs D-098 (curated models): ratio "
            f"{projection['cross_check']['ratio_this_over_published']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Search Evo 1's surviving component for the segmented-genome families — A2.5's marker arm.

    pixi run -e dev python tools/detect_segmented.py --band 0:0.02
    pixi run -e dev python tools/detect_segmented.py --band 0.02:0.10

A2.5's label-side census (D-187) leaves this category resting on 2.6% of Evo 1's surviving
records — only that share carries a family-level label — so "no segmented genomes" there is a
statement about labels, not about content. **D-190** fixes what this arm searches and at what
threshold, before any hit was inspected, and `tools/marker_throughput.py` priced it first.

**Membership is derived, and this tool does not decide it.** D-190's rule runs the ICTV VMR's 48
segmented families through the pinned NCBI taxonomy and intersects the result with RVDB-prot's
per-family LCA taxid, selecting **1,285** of its 13,679 families. That selection arrives here as
an artefact — `--selection` — rather than as a list in this file, for the reason D-075 gives for
Pfam's universe: a denominator a reviewer cannot check is not a denominator.

**The registry is RVDB-prot 32.0 itself, not a new one**, and that matters for more than tidiness.
`profilesearch.search` takes `restrict_to`, which is the designed way to search part of a pinned
registry: the thresholds, the version and the publisher's digests all stay the real ones. Minting
a `rvdb-prot-segmented` registry would have meant inventing a publisher checksum for a file this
project derived, and `RegistryFile`'s own contract forbids exactly that — "a checksum taken from
the bytes you already have verifies nothing". So the subset HMM file is passed as `--hmm-file`,
a **speed** measure that avoids decompressing 2.7 GB per band, while `restrict_to` is what makes
the search correct. The two are cross-checked: the models actually searched are counted and the
run fails if that count is not the selection's size.

**Bands, because a result has to be bankable.** The sample is a hash of the record id (D-078), so
bands are nested: `0:0.02` then `0.02:0.10` then `0.10:1.0` re-read no record twice, and each one
that finishes is a usable lower bound with its interval. The depth is therefore a decision taken
once per band and recorded, not a parameter this tool guesses. A band's own read is not amortised
across bands — hash selection has to scan the whole object to find its members — so fewer, wider
bands are cheaper and more, narrower ones bank sooner.

**What this arm cannot do, stated here because the number would otherwise look complete.** The
satellite categories select **zero** RVDB families under the same rule, because RVDB labels a
family with the lowest common ancestor of its sequences and a family holding satellites beside
their helper viruses carries an LCA above the satellite taxon. A zero there would be zero by
construction, so no satellite arm is run (D-190). And NCLDV is not searched here: its label-side
zero is already established at phylum over 99.996% of the component.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from amazebio import corpora, objectstore, policyspec, profiles, profilesearch, seqstream
from amazebio.apply import resolve, route_for
from amazebio.detect import ManifestRef
from amazebio.policyspec import load_policy_dir
from amazebio.repro import run
from amazebio.survival import wilson_interval

#: The sampling seed A2.1 fixed in D-078 and every later band has used. Shared on purpose: a
#: band drawn under a different seed is a different sample and could re-read what A2.1 read.
SEED = 20261015

SPECS = Path("policies/specs")

#: The one component this arm searches. Evo 2's released records carry no taxonomy and its
#: label-side census already found all four categories there, so the question this arm exists
#: to answer is Evo 1's.
COMPONENT = "stage2"
RELEASE = "opengenome"


def load_selection(path: Path) -> tuple[set[str], dict[str, Any]]:
    """The D-190 family selection, as an artefact rather than a literal in this file."""
    payload = json.loads(path.read_text())
    families = payload.get("segmented") if isinstance(payload, dict) else None
    if not families:
        raise SystemExit(
            f"{path} carries no `segmented` family list. The selection is D-190's and is derived "
            "by the rule recorded there; this tool does not decide membership."
        )
    return set(families), {
        "path": str(path),
        "families": len(families),
        "decision": "D-190",
        "rule": (
            "ICTV VMR MSL37.3's 48 labelled-segment families, expanded through the pinned NCBI "
            "taxdump 2023-04-01, intersected with RVDB-prot 32.0's per-family LCA taxid"
        ),
    }


def manifest_for(manifest_dir: Path, policy_id: str) -> tuple[dict[str, Any], Path]:
    index = manifest_dir / "index.json"
    if not index.exists():
        raise SystemExit(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. This arm "
            "consumes the manifests rather than re-deriving a surviving set (D-059)."
        )
    for entry in json.loads(index.read_text()).get("manifests", []):
        if entry.get("policy") == policy_id and entry.get("release") == RELEASE:
            path = manifest_dir / (entry.get("manifest") or entry.get("file"))
            return json.loads(path.read_text()), path
    raise SystemExit(f"{index} lists no manifest for {policy_id} x {RELEASE}")


def removed_ids(manifest_dir: Path, manifest: dict[str, Any]) -> set[str]:
    removed = manifest.get("removed", {}).get("file")
    if not removed:
        return set()
    path = manifest_dir / Path(removed).name
    if not path.exists():
        raise SystemExit(f"manifest names a removed set that is not there: {path}")
    return {json.loads(line)["record_id"] for line in path.read_text().splitlines() if line}


def band_records(
    client: Any,
    *,
    lo: float,
    hi: float,
    removed: set[str],
    limit: int | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Surviving records of Evo 1 stage 2 in the hash band `[lo, hi)`, with sequence.

    The manifest's removed set is subtracted here, so a record the reading removes is never
    gene-called, let alone searched.
    """
    sources = [
        s for s in corpora.sources_for(RELEASE) if s.corpus_component == COMPONENT and s.readable
    ]
    if not sources:
        raise SystemExit(f"no readable {COMPONENT} source declared for {RELEASE}")

    out: list[Any] = []
    stats = Counter({"records_in_band": 0, "records_removed_by_reading": 0, "bases": 0})
    per_source = []
    for source in sources:
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
        here = 0
        for sampled in seqstream.iter_stage2_sampled(
            obj.buffered(),
            component=source.component,
            # **`<component>:<filename>#<row>`, which is A1.4's scheme and A2.1's.** The first
            # run of this arm used the object key instead, and the damage was not only that no
            # id matched the manifest's removed set: band membership is a hash *of the id*, so
            # the wrong prefix drew an entirely different 2% of the corpus. The D-059 guard
            # caught it — a record resolving to `removed` while apparently surviving — which is
            # exactly the disagreement it exists to refuse. Note that 0 of the 95 removed
            # records fall in band 1 under the correct ids, so "0 subtracted" is right here and
            # is not a symptom of anything.
            record_prefix=f"{source.corpus_component}:{Path(source.key).name}",
            seed=SEED,
            lo=lo,
            hi=hi,
        ):
            stats["records_in_band"] += 1
            if sampled.id in removed:
                stats["records_removed_by_reading"] += 1
                continue
            out.append(sampled)
            stats["bases"] += len(sampled.sequence)
            here += 1
            if here % 5000 == 0:
                print(f"    {source.corpus_component}: {here:,} in band", file=sys.stderr)
            if limit is not None and len(out) >= limit:
                break
        per_source.append(
            {
                "key": source.key,
                "records_kept": here,
                "read_seconds": round(time.monotonic() - started, 1),
            }
        )
        if limit is not None and len(out) >= limit:
            break
    return out, {**dict(stats), "sources": per_source}


def table(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    hits: list[dict[str, Any]],
    selection: dict[str, Any],
    universe: set[str],
    routes: Counter[str],
    gene_stats: dict[str, Any],
    read_stats: dict[str, Any],
    band: tuple[float, float],
    models_searched: int,
    search_seconds: float,
) -> dict[str, Any]:
    by_family: dict[str, dict[str, Any]] = {}
    for hit in hits:
        row = by_family.setdefault(
            hit["profile"],
            {"family_id": hit["profile"], "hits": 0, "records": set(), "best_score": None},
        )
        row["hits"] += 1
        row["records"].add(hit["record_id"])
        row["best_score"] = max(row["best_score"] or hit["score"], hit["score"])

    families = sorted(
        (
            {
                "family_id": r["family_id"],
                "hits": r["hits"],
                "records": len(r["records"]),
                "best_score": r["best_score"],
                "threshold": f"E<={profiles.PINNED_E_VALUE} at Z={profiles.PINNED_Z}",
            }
            for r in by_family.values()
        ),
        key=lambda r: (-r["hits"], r["family_id"]),
    )
    detected = {r["family_id"] for r in families}
    searched = gene_stats.get("records", 0)
    interval = wilson_interval(len(detected), len(universe)) if universe else None

    return {
        "task": "A2.5",
        "detector": "profile-hmmer",
        "arm": "segmented-genome families",
        "decision": "D-190",
        "registry": {
            "id": profiles.RVDB_PROT_32_0.id,
            "version": profiles.RVDB_PROT_32_0.version,
            "profiles_in_release": profiles.RVDB_PROT_32_0.profile_count,
            "restricted_to": len(universe),
            "models_searched": models_searched,
            "membership": profiles.RVDB_PROT_32_0.membership,
            "selection": selection,
        },
        "manifest": ManifestRef(
            policy_id=manifest["policy"]["id"],
            release=manifest["release"],
            path=manifest_path.name,
            sha256=_digest(manifest_path),
            removed_records=manifest.get("removed", {}).get("records", 0),
        ).to_dict(),
        "sample": {
            "seed": SEED,
            "band": {"lo": band[0], "hi": band[1]},
            "method": "blake2b of the record id against a pinned seed (D-078); bands are nested",
            "is_census": band == (0.0, 1.0),
        },
        # A band is a sample, so a family absent from it may survive in records not read. Only
        # the full band is a population figure.
        "estimate_kind": "population" if band == (0.0, 1.0) else "lower_bound",
        "read": read_stats,
        "gene_calling": gene_stats,
        "search": {
            "seconds": round(search_seconds, 1),
            "accepted_hits": len(hits),
            "min_model_coverage": profilesearch.MIN_MODEL_COVERAGE,
            "threshold": f"E<={profiles.PINNED_E_VALUE} at Z={profiles.PINNED_Z} (D-076)",
        },
        "survival": {
            "families_detected": len(detected),
            "families_in_universe": len(universe),
            "interval": (
                {"estimate": interval.estimate, "low": interval.low, "high": interval.high}
                if interval
                else None
            ),
            "denominator": (
                "RVDB-prot 32.0 restricted to D-190's segmented selection. This is not 'the "
                "fraction of viral families': the universe is the segmented families only, and "
                "D-161 forbids quoting a registry fraction without naming its denominator."
            ),
        },
        "composition": [{"family_id": r["family_id"], "records": r["records"]} for r in families],
        "routes": dict(sorted(routes.items())),
        "families": families,
        "families_without_a_hit": sorted(universe - detected),
        "notes": [
            "Searched records: "
            f"{searched:,} surviving records of Evo 1's stage 2 in band "
            f"[{band[0]}, {band[1]}).",
            "A band is nested, so a deeper band re-reads nothing: a zero here is a zero over the "
            "records read, and `estimate_kind` says which.",
            "No route is `conformance_failure`: route_for refuses it and §7 reserves that claim "
            "for A7.1.",
            "The satellite categories select zero families under D-190's rule and are not "
            "searched; NCLDV is not searched because its label-side zero is already established "
            "at phylum over 99.996% of this component.",
        ],
    }


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", default="0:0.02", help="hash band as LO:HI, fractions of 1")
    parser.add_argument("--policy", default="evo1-charitable")
    parser.add_argument("--manifests", default=Path("artifacts/a1-4"), type=Path)
    parser.add_argument("--selection", type=Path, required=True, help="D-190's family selection")
    parser.add_argument("--hmm-file", type=Path, required=True, help="the subset HMM, for speed")
    parser.add_argument("--out", default=Path("artifacts/a2-5"), type=Path)
    parser.add_argument("--cpus", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="probing only")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    lo_s, _, hi_s = args.band.partition(":")
    lo, hi = float(lo_s), float(hi_s)
    if not 0 <= lo < hi <= 1:
        raise SystemExit(f"--band {args.band} is not a half-open band inside [0, 1]")

    universe, selection = load_selection(args.selection)
    policies = load_policy_dir(SPECS)
    policy = policies[args.policy]
    client = objectstore.client()
    manifest, manifest_path = manifest_for(args.manifests, args.policy)
    removed = removed_ids(args.manifests, manifest)
    stem = f"segmented-{args.policy}-{RELEASE}-band{lo}-{hi}"

    with run(
        "A2.5",
        seed=SEED,
        outdir=args.out,
        allow_dirty=args.allow_dirty,
        manifest_name=f"run-{stem}.json",
        durable=objectstore.durable_results("a2-5"),
    ) as m:
        m.parameter("decision", "D-190")
        m.parameter("band", {"lo": lo, "hi": hi})
        m.parameter("seed", SEED)
        m.parameter("policy", args.policy)
        m.parameter("registry", f"{profiles.RVDB_PROT_32_0.id} {profiles.RVDB_PROT_32_0.version}")
        m.parameter("restricted_to_families", len(universe))
        m.parameter("threshold", f"E<={profiles.PINNED_E_VALUE} at Z={profiles.PINNED_Z}")
        m.parameter("min_model_coverage", profilesearch.MIN_MODEL_COVERAGE)
        m.parameter("cpus", args.cpus)
        m.input_file(args.selection, role="d190-family-selection")
        m.input_file(args.hmm_file, role="rvdb-subset-hmm (speed; restrict_to is the guarantee)")
        m.input_file(manifest_path, role="a1-4-manifest")

        import pyhmmer
        import pyrodigal

        m.tools["pyhmmer"] = pyhmmer.__version__
        m.tools["pyrodigal"] = pyrodigal.__version__

        print(f"band [{lo}, {hi}) of {RELEASE}/{COMPONENT} ...", file=sys.stderr)
        records, read_stats = band_records(client, lo=lo, hi=hi, removed=removed, limit=args.limit)
        print(
            f"  {len(records):,} surviving records, {read_stats['bases']/1e6:.1f} Mbp "
            f"({read_stats['records_removed_by_reading']} removed by the reading)",
            file=sys.stderr,
        )
        if not records:
            raise SystemExit("the band selected no records; nothing to search")

        print("calling genes ...", file=sys.stderr)
        started = time.monotonic()
        proteins, gene_stats = profilesearch.call_genes(records)
        gene_stats = {
            **gene_stats,
            "seconds": round(time.monotonic() - started, 1),
            "bases": read_stats["bases"],
        }
        print(
            f"  {gene_stats['genes']:,} genes, {gene_stats['residues']/1e6:.2f} Maa "
            f"in {gene_stats['seconds']}s",
            file=sys.stderr,
        )

        # Routes are recomputed per record against the same evidence A1.4 used, and a record that
        # resolves to `removed` while absent from the removed set stops the run: the manifest and
        # this pass would then disagree about what survived.
        routes: Counter[str] = Counter()
        source = next(
            s
            for s in corpora.sources_for(RELEASE)
            if s.corpus_component == COMPONENT and s.readable
        )
        for sampled in records:
            # `SampledRecord` wraps the policy-side record plus its residues; `resolve` wants the
            # record, which is the same object A1.4 resolved its outcome from.
            decision = resolve(policy, sampled.record, evidence=source.evidence)
            if decision.outcome is policyspec.Outcome.REMOVED:
                raise SystemExit(
                    f"{sampled.id} resolves to `removed` under {args.policy} but is not in the "
                    "manifest's removed set (D-059); every count below would be unsafe."
                )
            routes[route_for(decision.outcome).value] += 1

        print(f"searching {len(universe):,} restricted models ...", file=sys.stderr)
        started = time.monotonic()
        hits = profilesearch.search(
            profiles.RVDB_PROT_32_0,
            proteins,
            restrict_to=universe,
            hmm_file=args.hmm_file,
            cpus=args.cpus,
        )
        search_seconds = time.monotonic() - started
        models_searched = _count_models(args.hmm_file, universe)
        if models_searched != len(universe):
            raise SystemExit(
                f"the subset HMM holds {models_searched} of the {len(universe)} selected "
                "families. The subset is a speed measure and must be complete, or the universe "
                "the figures are reported against is not the one that was searched."
            )
        print(f"  {len(hits):,} accepted hits in {search_seconds:.0f}s", file=sys.stderr)

        payload = table(
            manifest=manifest,
            manifest_path=manifest_path,
            hits=hits,
            selection=selection,
            universe=universe,
            routes=routes,
            gene_stats=gene_stats,
            read_stats=read_stats,
            band=(lo, hi),
            models_searched=models_searched,
            search_seconds=search_seconds,
        )
        out = args.out / f"{stem}.json"
        out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        m.output_file(out, role=stem)

        if hits:
            rows = args.out / f"{stem}.jsonl"
            rows.write_text(
                "".join(
                    json.dumps(
                        {
                            "record_id": h["record_id"],
                            "family_id": h["profile"],
                            "registry": profiles.RVDB_PROT_32_0.id,
                            "registry_version": profiles.RVDB_PROT_32_0.version,
                            "detector": "profile-hmmer",
                            "score": h["score"],
                            "evalue": h["evalue"],
                            "coverage": h["coverage"],
                        },
                        sort_keys=True,
                    )
                    + "\n"
                    for h in hits
                )
            )
            m.output_file(rows, role=f"{stem}-detections")

        s = payload["survival"]
        print(
            f"\n{s['families_detected']} of {s['families_in_universe']} segmented families "
            f"detected ({payload['estimate_kind']})",
            file=sys.stderr,
        )
        for row in payload["composition"][:10]:
            print(f"  {row['family_id']}  {row['records']} records", file=sys.stderr)
    return 0


def _count_models(hmm_file: Path, universe: set[str]) -> int:
    """How many of the selected families the subset file actually holds."""
    names = set()
    with profiles.open_profiles(hmm_file) as handle:
        for line in handle:
            text = line.decode() if isinstance(line, bytes) else line
            if text.startswith("NAME "):
                names.add(text.split(None, 1)[1].strip())
    return len(names & universe)


if __name__ == "__main__":
    raise SystemExit(main())

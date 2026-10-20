#!/usr/bin/env python3
"""A3.3 — recompute Phase A's headline counts by the second method and compare.

Reads the A2 detection artefacts, the A1.4 removed sets, the pinned registry artefacts and
A7.1's lineage census straight out of the result store, recomputes M1, M2 and the conformance
numbers with `amazebio.recount` — which shares no code with the first implementation — and
writes `recount.json` and `comparison.md`.

A3.2's own answers are fetched **last**, after the recount is complete, and only to build the
comparison table. Nothing in the recount reads them.

    pixi run -e dev python tools/recount.py
    pixi run -e dev python tools/recount.py --allow-dirty --resamples 200   # local iteration

What is read, and the rule that decides it:

* every `detections-*.json` lying directly under `corpora/results/a2-1|a2-3|a2-4/`, with its
  `.jsonl` where one exists — "directly under" excludes a superseded band's rerun directory;
* `corpora/results/a2-5/segmented-assembled.json`, the one A2.5 table keyed on a family
  registry. A2.5's `sweep-*` tables are keyed on ICTV category members rather than on a family
  universe (`metrics/detections.md`), and M1 is defined over a family registry, so they are
  named in the output as excluded rather than silently dropped;
* `corpora/results/a1-4/removed-*.jsonl`, the records each reading removes;
* the registry artefacts that rebuild each universe;
* `corpora/results/a7-1/scan-opengenome-stage2.json`, and a bounded re-read of the released
  Parquet it was taken from.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from amazebio import objectstore, recount, repro

TASK = "A3.3"
SEED = 20261020
DETECTION_PREFIXES = ("a2-1", "a2-3", "a2-4")
SEGMENTED_KEY = "corpora/results/a2-5/segmented-assembled.json"
SCAN_KEY = "corpora/results/a7-1/scan-opengenome-stage2.json"
HEADLINE_KEY = "corpora/results/a3-2/headline.json"
REGISTRY_KEYS = {
    "pfam": "corpora/results/a2-1/pfam-viral-families.json",
    "rvdb-prot": "corpora/results/a2-1/rvdb-families.json",
    "dfam-curated-ltr": "corpora/results/a2-3/dfam-curated-ltr.json",
}
#: The released object A7.1's census was taken from, re-read here in part.
STAGE2_KEY = (
    "corpora/opengenome/84369c058d192dcb607086d71679b877421e3250/stage2/train_stage2.parquet"
)
EVO1_SPECS = ("evo1-literal", "evo1-charitable", "evo1-strict")

#: Written by hand once the generated table had been read and every divergence investigated,
#: and kept in the tool so `comparison.md` regenerates whole rather than being edited in place.
NARRATIVE = """
## What was compared, and what diverged

**The headline reproduces exactly.** Every M1 figure — the count of surviving families, the
fraction, and both ends of its Wilson interval — agrees with A3.2 to the last digit printed, in
all sixteen groups where a figure is reported, overall and on every route. So do the universe
sizes, the overall M2 distributions, and the five groups both implementations withhold because
no source in them was searched. The four numbers the Phase A write-up would lead with are:
Pfam's viral subset 28.27% [26.19%, 30.45%] of families surviving Evo 1's released corpus and
29.90% [27.78%, 32.11%] of Evo 2's; RVDB-prot 4.25% [3.93%, 4.61%] and 10.84% [10.33%, 11.37%].
Neither registry's fraction is quotable on its own and the two are not comparable (D-161);
both restrictions travel with them here as they do in the tables.

**The conformance numbers reproduce exactly too**, from the policy YAML rather than from any
of this project's evaluator code: 95 records of 2,653,047 survive a rule Evo 1 published, a
rate of 3.581e-05 [2.930e-05, 4.377e-05], and **not one** record assigned to any of the 19
denylisted families or 12 denylisted orders survives. The 95 are a single mechanism — every one
of them carries a family and no rank above it, so the published "no assigned realm at all"
clause reaches them — which is independently what D-051 recorded. The three readings return
identical counts because the rules they differ over read inputs the release withholds; the
recount reaches that by executing all three rather than by assuming it.

### The one divergence, and why the recount's number is the better one

Twenty-two cells differ. Twenty-one are of one kind: **per-route record counts in the six
`opengenome2` groups** — three readings over two protein registries — and the per-route maximum
that follows from them. (The twenty-second is a coverage string, below.) Overall M2 agrees
exactly in every
group — for Pfam against Evo 2's release both implementations report 7,521 surviving records —
and the divergence is entirely in how that total is split between `out_of_scope` and
`unresolved` (or, under the strict reading, `retained_by_design` and `unresolved`): 1,291 /
6,230 here against 1,301 / 6,220 in A3.2, and 487 / 5,954 against 499 / 5,942 for RVDB-prot.

The cause is not an error in either implementation. Where a family's detections fall on more
than one route, A3.2 splits that family's record count across routes **in proportion to its
detections** — an approximation it declares, in D-194 and in its own artefact, and one it had
little choice about while reading per-family aggregates. This recount reads the detection rows,
so it counts the distinct records carrying each route directly.

The two differ exactly where hits per record differ between routes. `PF00589`
(`Phage_integrase`) in A2.1's Evo 2 table is the whole of the maximum divergence: 194 hits over
160 records, 49 of those hits on the `out_of_scope` route. Apportionment gives that route
160 x 49/194 = 40.4 records; the rows show the 49 hits sitting on **33** distinct records. The
out-of-scope detections are more clustered per record than the unresolved ones, which is the
heavy tail `metrics/survival.md` §4 chose a median over a mean for in the first place — and an
apportionment is blind to it by construction.

Nothing was tuned to produce this. The recount counts distinct `record_id`s because
`metrics/detections.md` defines `records` as "distinct surviving records carrying the family",
and that definition was implemented before A3.2's answers were fetched.

**What it means for the write-up.** The headline is unaffected: M1 does not pass through the
split at all, and overall M2 agrees. Where a per-route *record* count is quoted for an
`opengenome2` group, the exact figures here should be preferred to the apportioned ones, or the
apportioned ones labelled as apportioned. Per-route **detection** counts, and every per-route
M1, are unaffected.

### The twenty-second cell: coverage under the charitable reading is 3/7, not 3/6

A7.1 reports conformance coverage as `3/6`, and that is right for the literal and strict
readings, which publish six rules each. The charitable reading publishes **seven** — it adds
`remove-eukaryotic-host-evidence`, which reads IMG/VR host metadata the release withholds — so
the same three executable rules are three of seven there. This recount derives the denominator
from each spec's own rule list rather than carrying one number across all three readings, which
is what the A7.1 criterion asks for ("the restriction derived mechanically from the specs rather
than chosen"). Nothing about the 95 or the zero changes; the fraction describing how much of the
policy could be tested does, and it should be quoted per reading.

### What this check does not establish

Both implementations read the same A2 detection artefacts, and the conformance arm rests on the
same A7.1 scan (its bounded re-read above aside). A second count cannot stand in for a second
*measurement*: a missed homolog, a wrong gene call or a mis-set threshold inside the detectors
would be reproduced identically by both. What §7 asks for is that the counting be independent,
and that is what is demonstrated here.
"""


class Store:
    """Fetch-and-cache over the result store, recording every object as a pinned input."""

    def __init__(self, client: Any, cache: Path, manifest: repro.RunManifest) -> None:
        self.client, self.cache, self.manifest = client, cache, manifest
        self.cache.mkdir(parents=True, exist_ok=True)
        self.fetched: list[str] = []

    def list(self, prefix: str) -> list[str]:
        pages = self.client.get_paginator("list_objects_v2")
        keys = []
        for page in pages.paginate(Bucket=objectstore.CORPORA_BUCKET, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)

    def path(self, key: str, *, role: str) -> Path:
        local = self.cache / key.replace("/", "__")
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(objectstore.CORPORA_BUCKET, key, str(local))
        if key not in self.fetched:
            self.manifest.input_url(
                f"s3://{objectstore.CORPORA_BUCKET}/{key}",
                role=role,
                bytes=local.stat().st_size,
                checksum=repro.sha256_file(local),
                checksum_type="sha256",
                verified=True,
            )
            self.fetched.append(key)
        return local

    def json(self, key: str, *, role: str) -> Any:
        return json.loads(self.path(key, role=role).read_text())


def detection_inputs(
    store: Store,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    """Every detection table that enters the recount, with its detections where published.

    Returns the inputs, the artefacts deliberately excluded with the reason, and any deviation
    from the published detection contract met on the way — a deviation is a finding about the
    artefact, not a reason to drop it.
    """
    inputs: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    deviations: list[dict[str, str]] = []
    for prefix in DETECTION_PREFIXES:
        root = f"corpora/results/{prefix}/"
        for key in store.list(root):
            tail = key[len(root) :]
            if "/" in tail:
                excluded.append({"key": key, "why": "not directly under the task prefix"})
                continue
            if not tail.startswith("detections-") or not tail.endswith(".json"):
                continue
            if tail == "detections-index.json":
                excluded.append({"key": key, "why": "an index of tables, not a table"})
                continue
            doc = store.json(key, role="detection table")
            rows_key = key[: -len(".json")] + ".jsonl"
            rows = None
            if rows_key in store.list(key[: -len(".json")]):
                text = store.path(rows_key, role="detection rows").read_text()
                lines = text.splitlines()
                rows = recount.parse_detection_rows(lines, where=rows_key)
                if lines and lines[0].lstrip().startswith('"'):
                    deviations.append(
                        {
                            "key": rows_key,
                            "deviation": (
                                "each line is a JSON string holding the detection object, not "
                                "the object itself. metrics/detections.md specifies one JSON "
                                "object per line. Read through the extra layer here; the counts "
                                "are unaffected, the contract is not met."
                            ),
                        }
                    )
            inputs.append({"doc": doc, "rows": rows, "source": key})
    inputs.append(
        {
            "doc": store.json(SEGMENTED_KEY, role="detection table"),
            "rows": None,
            "source": SEGMENTED_KEY,
        }
    )
    for key in store.list("corpora/results/a2-5/sweep-"):
        excluded.append(
            {
                "key": key,
                "why": (
                    "A2.5's sweep is keyed on ICTV category members, not on a family registry; "
                    "M1 is defined over a family universe (metrics/survival.md §1)"
                ),
            }
        )
    return inputs, excluded, deviations


def removed_sets(store: Store) -> dict[str, set[str]]:
    """`policy|release` to the records that reading removes. Absent file means none removed."""
    removed: dict[str, set[str]] = {}
    for key in store.list("corpora/results/a1-4/removed-"):
        rows = recount.parse_detection_rows(
            store.path(key, role="A1.4 removed set").read_text().splitlines(), where=key
        )
        for row in rows:
            removed.setdefault(f"{row['policy']}|{row['release']}", set()).add(row["record_id"])
    return removed


def rebuild_universes(store: Store) -> dict[str, set[str]]:
    """`F_R` per universe name, from each registry's own pinned artefact."""
    universes: dict[str, set[str]] = {}
    for registry, key in REGISTRY_KEYS.items():
        doc = store.json(key, role="registry universe")
        families = recount.universe_from_registry(registry, doc)
        version = doc.get("registry_version") or str(doc["registry"]).split("/")[-1]
        universes[f"{registry}/{version}"] = families
    return universes


def reread_scan_sample(
    store: Store, scan: dict[str, Any], *, row_groups: int, seed: int
) -> dict[str, Any]:
    """Re-read sampled row groups of the released Parquet and check the census against them."""
    import pyarrow.parquet as pq

    reader = io.BufferedReader(
        objectstore.S3RandomRead(store.client, objectstore.CORPORA_BUCKET, STAGE2_KEY),
        buffer_size=1 << 22,
    )
    parquet = pq.ParquetFile(reader)
    chosen = recount.sample_row_groups(parquet.num_row_groups, row_groups, seed=seed)
    store.manifest.input_url(
        f"s3://{objectstore.CORPORA_BUCKET}/{STAGE2_KEY}",
        role="released corpus, sampled row groups re-read",
        bytes=reader.raw.size,
        verified=False,
    )

    def records() -> Any:
        for index in chosen:
            table = parquet.read_row_group(index)
            yield from (value.as_py() for value in table.column("text"))

    result = recount.verify_scan_sample(
        records(), scan, block_chars=scan["structure"]["block_chars"]
    )
    result["row_groups_read"] = chosen
    result["row_groups_in_object"] = parquet.num_row_groups
    result["seed"] = seed
    return result


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def interval(value: dict[str, Any] | None) -> str:
    if value is None:
        return "—"
    return f"{pct(value['estimate'])} [{pct(value['low'])}, {pct(value['high'])}]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="artifacts/a3-3")
    parser.add_argument("--cache", default=None, help="where fetched inputs are kept")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--resamples", type=int, default=recount.BOOTSTRAP_RESAMPLES)
    parser.add_argument(
        "--scan-row-groups",
        type=int,
        default=16,
        help="row groups of the released Parquet to re-read; 0 skips the re-read",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "do not copy the outputs to the result store. For iteration only: the corpora "
            "bucket has no DeleteObject, so a junk upload is permanent."
        ),
    )
    args = parser.parse_args(argv)

    outdir = Path(args.outdir)
    cache = Path(args.cache) if args.cache else outdir / "inputs"
    client = objectstore.client()

    with repro.run(
        TASK,
        seed=args.seed,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        durable=None if args.local_only else objectstore.durable_results("a3-3"),
        durable_exempt=(
            "local iteration only; the run whose numbers are cited uploads to a3-3"
            if args.local_only
            else None
        ),
        manifest_name="run-recount.json",
    ) as manifest:
        manifest.parameter("confidence_level", 0.95)
        manifest.parameter("wilson_z", recount.Z_95)
        manifest.parameter("bootstrap_resamples", args.resamples)
        manifest.parameter("bootstrap_chunk", recount.BOOTSTRAP_CHUNK)
        manifest.parameter("bootstrap_seed", args.seed)
        manifest.parameter("scan_row_groups_reread", args.scan_row_groups)
        manifest.parameter("method", "relational pass over detection rows; set algebra over routes")
        manifest.note(
            "Second-method reimplementation (DESIGN.md §7). Written from metrics/survival.md, "
            "metrics/detections.md, metrics/manifests.md and policies/specs/ alone; the first "
            "implementation's modules were not read."
        )

        store = Store(client, cache, manifest)
        inputs, excluded, deviations = detection_inputs(store)
        universes = rebuild_universes(store)
        removed = removed_sets(store)
        survival = recount.recount_groups(
            inputs,
            universes=universes,
            removed_records=removed,
            seed=args.seed,
            resamples=args.resamples,
        )

        scan = store.json(SCAN_KEY, role="A7.1 lineage census")
        specs = {
            policy: yaml.safe_load(
                manifest.input_file(
                    Path("policies/specs") / f"{policy}.yaml", role="policy spec"
                ).read_text()
            )
            for policy in EVO1_SPECS
        }
        conformance = recount.conformance_from_scan(scan, specs)
        if args.scan_row_groups:
            conformance["census_reread"] = reread_scan_sample(
                store, scan, row_groups=args.scan_row_groups, seed=args.seed
            )

        # A3.2's answers are fetched only now, with the recount complete.
        headline = store.json(HEADLINE_KEY, role="A3.2 answers, for comparison only")
        comparison = build_comparison(survival, conformance, headline, deviations)

        result = {
            "task": TASK,
            "method": recount.__doc__.strip().splitlines()[0],
            "seed": args.seed,
            "inputs_excluded": excluded,
            "contract_deviations": deviations,
            "divergent_numbers": comparison["divergent"],
            "survival": survival,
            "conformance": conformance,
            "comparison": comparison["rows"],
        }
        (outdir / "recount.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        (outdir / "comparison.md").write_text(comparison["markdown"])
        manifest.output_file(outdir / "recount.json", role="the second method's answers")
        manifest.output_file(outdir / "comparison.md", role="side-by-side with A3.2 and A7.1")

    print(f"wrote {outdir}/recount.json and {outdir}/comparison.md")
    return 0


#: A7.1's headline conformance numbers as that task reports them. Its diff artefact was never
#: copied to the result store — only the scan it is computed from was — so there is no machine
#: readable copy to join against, and these are transcribed from the task's own state block
#: (`tasks/A7-1-reexecute-published-predicates-against-released-corpora.md`, D-051). That gap
#: is itself reported in the comparison.
A7_1_AS_REPORTED = {
    "records_in_release": 2653047,
    "conformance_failures": 95,
    "denylist_survivors": 0,
    "coverage": "3/6",
    "mechanism": "all 95 are assigned at family rank and no rank above it; no realm assigned",
}

TOLERANCE = 1e-9


def _agree(mine: Any, theirs: Any) -> str:
    if theirs is None and mine is None:
        return "both withheld"
    if theirs is None or mine is None:
        return "**ONLY ONE REPORTS**"
    if isinstance(mine, int | float) and isinstance(theirs, int | float):
        return "yes" if abs(float(mine) - float(theirs)) <= TOLERANCE else "**NO**"
    return "yes" if mine == theirs else "**NO**"


def _cells(group: dict[str, Any], other: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Every number of one group, beside A3.2's answer for it."""
    other = other or {}
    m1 = group["m1"]
    m2 = group["m2"]
    out: list[dict[str, Any]] = [
        {
            "quantity": "families in universe",
            "recount": group["families_in_universe"],
            "a3_2": other.get("families_in_universe"),
        },
        {
            "quantity": "M1 families detected",
            "recount": None if m1 is None else m1["families_detected"],
            "a3_2": other.get("m1_families_with_a_hit"),
        },
        {
            "quantity": "M1 fraction",
            "recount": None if m1 is None else m1["interval"]["estimate"],
            "a3_2": other.get("m1_fraction"),
        },
        {
            "quantity": "M1 Wilson low",
            "recount": None if m1 is None else m1["interval"]["low"],
            "a3_2": other.get("m1_ci_low"),
        },
        {
            "quantity": "M1 Wilson high",
            "recount": None if m1 is None else m1["interval"]["high"],
            "a3_2": other.get("m1_ci_high"),
        },
    ]
    their_m2 = other.get("m2") or {}
    mine_m2 = (m2 or {}).get("records_zero_filled")
    out += [
        {
            "quantity": "M2 surviving records, total",
            "recount": None if mine_m2 is None else mine_m2["total"],
            "a3_2": their_m2.get("detections_total"),
        },
        {
            "quantity": "M2 median n_f",
            "recount": None if mine_m2 is None else mine_m2["median"]["estimate"],
            "a3_2": their_m2.get("median"),
        },
        {
            "quantity": "M2 q1",
            "recount": None if mine_m2 is None else mine_m2["q1"],
            "a3_2": their_m2.get("q1"),
        },
        {
            "quantity": "M2 q3",
            "recount": None if mine_m2 is None else mine_m2["q3"],
            "a3_2": their_m2.get("q3"),
        },
        {
            "quantity": "M2 maximum n_f",
            "recount": None if mine_m2 is None else mine_m2["max"],
            "a3_2": their_m2.get("maximum"),
        },
    ]
    their_routes = other.get("routes") or {}
    mine_routes = (m1 or {}).get("per_route") or {}
    for route in sorted(set(their_routes) | set(mine_routes)):
        mine_route = mine_routes.get(route)
        their_route = their_routes.get(route, {})
        their_m2_route = their_route.get("m2") or {}
        mine_m2_route = ((m2 or {}).get("per_route") or {}).get(route)
        out += [
            {
                "quantity": f"M1 families detected, route {route}",
                "recount": None if mine_route is None else mine_route["families_detected"],
                "a3_2": their_route.get("m1_families_with_a_hit"),
            },
            {
                "quantity": f"M1 fraction, route {route}",
                "recount": None if mine_route is None else mine_route["interval"]["estimate"],
                "a3_2": their_route.get("m1_fraction"),
            },
            {
                "quantity": f"M2 surviving records, route {route}",
                "recount": None if mine_m2_route is None else mine_m2_route["total"],
                "a3_2": their_m2_route.get("detections_total"),
            },
            {
                "quantity": f"M2 maximum n_f, route {route}",
                "recount": None if mine_m2_route is None else mine_m2_route["max"],
                "a3_2": their_m2_route.get("maximum"),
            },
        ]
    for cell in out:
        cell["agrees"] = _agree(cell["recount"], cell["a3_2"])
    return out


def a32_groups(headline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A3.2's groups, keyed the way this module keys its own.

    Read by the field names A3.2's artefact actually uses, checked rather than guessed: a
    consumer that guesses at another task's shape reports a parse error as a divergence, which
    is what `metrics/manifests.md` records A2.1 doing with `file` for `manifest`.
    """
    groups = headline.get("groups")
    if not isinstance(groups, list) or not groups:
        raise SystemExit("A3.2's headline carries no `groups` list; the comparison cannot join")
    keyed: dict[str, dict[str, Any]] = {}
    for group in groups:
        missing = {"policy_id", "release", "universe"} - set(group)
        if missing:
            raise SystemExit(f"A3.2 group is missing {sorted(missing)}; the join is not safe")
        keyed[recount.group_key(group["policy_id"], group["release"], group["universe"])] = group
    return keyed


def format_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def build_comparison(
    survival: dict[str, Any],
    conformance: dict[str, Any],
    headline: dict[str, Any],
    deviations: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    """Every headline number of both implementations, side by side, cell by cell."""
    theirs = a32_groups(headline)
    rows: list[dict[str, Any]] = []
    unmatched = sorted(set(theirs) - {g["group"] for g in survival["groups"]})
    for group in survival["groups"]:
        other = theirs.get(group["group"])
        for cell in _cells(group, other):
            rows.append({"group": group["group"], "joined": other is not None, **cell})

    conformance_rows = []
    for policy, reading in sorted(conformance["readings"].items()):
        conformance_rows += [
            {
                "reading": policy,
                "quantity": "records in the released component",
                "recount": reading["records_in_release"],
                "a7_1": A7_1_AS_REPORTED["records_in_release"],
            },
            {
                "reading": policy,
                "quantity": "conformance failures",
                "recount": reading["conformance_failures"],
                "a7_1": A7_1_AS_REPORTED["conformance_failures"],
            },
            {
                "reading": policy,
                "quantity": "records surviving a denylist rule",
                "recount": sum(
                    count
                    for rule, count in reading["by_rule"].items()
                    if rule.startswith("remove-denylisted-")
                ),
                "a7_1": A7_1_AS_REPORTED["denylist_survivors"],
            },
            {
                "reading": policy,
                "quantity": "rules executed, of those published",
                "recount": reading["coverage"]["stated"],
                "a7_1": A7_1_AS_REPORTED["coverage"],
            },
        ]
    for row in conformance_rows:
        row["agrees"] = _agree(row["recount"], row["a7_1"])

    disagreements = [r for r in rows if r["agrees"].startswith("**")] + [
        r for r in conformance_rows if r["agrees"].startswith("**")
    ]

    lines = [
        "# A3.3 — the second method, beside A3.2 and A7.1",
        "",
        "Generated by `tools/recount.py`; every number here is in `recount.json` beside it, and",
        "`run-recount.json` pins the inputs each was computed from. The method, and what it",
        "would and would not catch, is the docstring of `src/amazebio/recount.py`.",
        "",
        f"**{len(rows) + len(conformance_rows)} numbers compared, "
        f"{len(disagreements)} divergent.**",
        "",
        "## M1 — family-level survival, per registry x release x policy reading",
        "",
        "Per-route figures are over the detections carrying that route only. A family can",
        "survive by more than one route, so they do not sum to the overall figure.",
        "",
        "| group | \\|F_R\\| | recount: families | recount: M1 [95% Wilson] | A3.2: families |"
        " A3.2: M1 [95% Wilson] | agree |",
        "|---|---|---|---|---|---|---|",
    ]
    for group in survival["groups"]:
        other = theirs.get(group["group"], {})
        mine = group["m1"]
        their_interval = (
            None
            if other.get("m1_fraction") is None
            else {
                "estimate": other["m1_fraction"],
                "low": other["m1_ci_low"],
                "high": other["m1_ci_high"],
            }
        )
        cells = _cells(group, other)
        agree = (
            "**NO**" if any(c["agrees"].startswith("**") for c in cells) else "yes (all numbers)"
        )
        their_count = other.get("m1_families_with_a_hit")
        lines.append(
            f"| `{group['group']}` | {group['families_in_universe']} | "
            f"{'withheld' if mine is None else mine['families_detected']} | "
            f"{'withheld' if mine is None else interval(mine['interval'])} | "
            f"{'withheld' if their_count is None else their_count} | "
            f"{'withheld' if their_interval is None else interval(their_interval)} | {agree} |"
        )
    lines += [
        "",
        "A group every detector reports as `not_searched` is withheld rather than printed as a",
        "zero: a Wilson interval over an unsearched corpus reads as a filter that removed",
        "everything (`metrics/detections.md`). Both implementations withhold the same five.",
        "",
        "## Every compared number",
        "",
        "| group | quantity | recount | A3.2 | agree |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['group']}` | {row['quantity']} | {format_number(row['recount'])} | "
            f"{format_number(row['a3_2'])} | {row['agrees']} |"
        )
    lines += [
        "",
        "## Conformance — Evo 1's released viral component",
        "",
        "Re-executed from `policies/specs/evo1-*.yaml` over A7.1's complete lineage census: all",
        f"{conformance['readings']['evo1-literal']['records_in_release']:,} released records",
        "collapsed onto their 181 distinct tags, which is exact rather than sampled for a",
        "predicate that reads only the lineage.",
        "",
        "| reading | failures | rate [95% Wilson] | coverage | by rule |",
        "|---|---|---|---|---|",
    ]
    for policy, reading in sorted(conformance["readings"].items()):
        by_rule = ", ".join(f"{rule}: {n}" for rule, n in sorted(reading["by_rule"].items()))
        lines.append(
            f"| {policy} | {reading['conformance_failures']} | "
            f"{reading['rate']['estimate']:.3e} [{reading['rate']['low']:.3e}, "
            f"{reading['rate']['high']:.3e}] | {reading['coverage']['stated']} | {by_rule} |"
        )
    lines += [
        "",
        "| reading | quantity | recount | A7.1 as reported | agree |",
        "|---|---|---|---|---|",
    ]
    for row in conformance_rows:
        lines.append(
            f"| {row['reading']} | {row['quantity']} | {format_number(row['recount'])} | "
            f"{format_number(row['a7_1'])} | {row['agrees']} |"
        )
    if unmatched:
        lines += ["", "## A3.2 groups this recount did not produce", ""]
        lines += [f"- `{group}`" for group in unmatched]
    reread = conformance.get("census_reread")
    if reread:
        lines += [
            "",
            "### The one check that does not rest on A7.1's artefact",
            "",
            f"{reread['records_read']:,} records re-read from "
            f"{len(reread['row_groups_read'])} row groups of the released Parquet, sampled at "
            f"seed {reread['seed']} from the {reread['row_groups_in_object']:,} it holds: "
            f"{reread['distinct_tags']} distinct lineage tags, "
            f"{len(reread['tags_not_in_the_census'])} of them absent from the census, "
            f"{len(reread['tags_exceeding_their_census_count'])} occurring more often than the "
            f"census allows, {reread['records_with_more_than_one_tag']} records carrying more "
            f"than one tag. {reread['reading']}",
        ]
    if survival["findings"] or deviations:
        lines += ["", "## What the recount found in the artefacts themselves", ""]
        lines += [f"- {finding}" for finding in survival["findings"]]
        lines += [f"- `{d['key']}`: {d['deviation']}" for d in deviations]
    lines += ["", NARRATIVE.strip(), ""]
    return {
        "rows": rows,
        "conformance_rows": conformance_rows,
        "divergent": disagreements,
        "unmatched_a3_2_groups": unmatched,
        "markdown": "\n".join(lines) + "\n",
    }


if __name__ == "__main__":
    raise SystemExit(main())

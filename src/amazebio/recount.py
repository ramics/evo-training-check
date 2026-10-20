"""A3.3 — the independent second method for Phase A's headline counts.

`DESIGN.md` §7 requires the headline numbers to be reproduced by a second method before
anything is published. This module is that second method. It was written from
`metrics/survival.md`, `metrics/detections.md`, `metrics/manifests.md`, `policies/specs/*.yaml`
and the task files alone, by a worker that did not read the first implementation — not
`survival.py`, not `quantify.py`, not `conformance.py`, nor their tools or tests. Nothing here
imports a module that computes a metric; `amazebio.repro` and `amazebio.objectstore` are
imported for provenance and IO, which is all they do.

Why this is a second *method* and not a transcription
-----------------------------------------------------

Three choices make the arithmetic structurally different from merging the published tables.

**1. The survival headline is rebuilt from the primitive detection rows, not from the tables'
own per-family aggregates.** `metrics/detections.md` publishes two views of the same
measurement: the `families[]` rows of the `.json` table, and the one-object-per-detection
`.jsonl`. The first implementation consumes tables (A3.2's own state block says so: it "read
all 35 A2 detection tables"). This one reads every `.jsonl` that exists, counts hits as lines
and records as **distinct `record_id`s**, and uses a table's aggregate rows only for the tables
that published no record-level file (all of A2.4, A2.3's `opengenome` arm, A2.5's assembled
band and the unsearched ESM3-proxy tables). Twenty of the thirty-five tables, carrying the bulk
of the detections, are therefore recomputed from the rows rather than copied from a sum.

**2. The denominator is rebuilt from the pinned registry artefacts, not from the tables'
`families_without_a_hit` list.** `|F_R|` is the whole pinned universe, and a table states it
twice over — in `survival.families_in_universe` and in the two family lists. Both are the
detector's own statement. This module derives the universe independently (Pfam's viral subset
from `pfam-viral-families.json`, RVDB-prot's 13,679 ids from `rvdb-families.json`, Dfam's ERV
models with a curated threshold from `dfam-curated-ltr.json`) and refuses a table whose stated
universe does not match it, accession for accession. A wrong denominator moves every fraction
in the headline and no amount of care over the numerator catches it.

**3. Family survival is set algebra over routes, not per-route accumulation.** M1 for a route
is `|{families with at least one detection carrying that route}| / |F_R|` — a union of family
sets, computed from the fact table by filtering rows, never by accumulating counters as the
detections are read. The overall figure is the union over all routes, which is why the
per-route figures do not sum to it (`metrics/survival.md` §4) and why this shape makes that
impossible to get wrong by construction. The Wilson interval is the closed form, written from
the definition.

**4. The conformance numbers are re-executed from the policy YAML against the scan's tag
census.** A7.1's scan publishes `tag_counts`: all 2,653,047 released records of Evo 1's viral
component collapsed onto their 181 distinct lineage tags, which is a complete and exact
summary for any predicate that reads only the lineage. The three rules the release can decide
are evaluated over those 181 rows, straight from `policies/specs/evo1-*.yaml`, with the rank
grammar read off the tag rather than from any of this project's parsers.

What this would and would not catch
-----------------------------------

It catches: a wrong denominator; a per-family aggregate that does not match its own detection
rows; double counting across detectors that read the same corpus component; a detection
counted on a record the reading removed; a route accumulated into the wrong bucket; an
arithmetic or interval error in M1, M2 or the conformance rate; a misreading of the published
exclusion rules.

It does not catch: an error in the *measurement* — a missed homolog, a wrong gene call, a
threshold applied wrongly inside HMMER — because both implementations read the same A2
artefacts; an error in the A1.4 manifests themselves, beyond the removed-set cross-check below;
or an error in the A7.1 scan's traversal of the Parquet, except to the extent of the bounded
re-read :func:`verify_scan_sample` performs over sampled row groups. Those are independent
*measurements*, not independent counts, and a second count cannot stand in for them.

Checks this module refuses on
-----------------------------

Each is a condition under which the headline would be wrong rather than merely different:

* a group whose tables state different manifest sha256 for the same policy and release — the
  tables were computed against different surviving sets (`metrics/detections.md`);
* two detectors in one group that both report having searched the same corpus component — M2
  sums record counts across detectors and a shared component double counts them;
* a detection on a record the reading removes — that record is not in the surviving set, and
  `metrics/manifests.md` makes it a candidate conformance failure instead;
* a route outside the frozen taxonomy, or a table asserting `conformance_failure`;
* a stated universe that disagrees with the registry artefact.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

__all__ = [
    "BOOTSTRAP_RESAMPLES",
    "DECIDABLE_RULE_KINDS",
    "ROUTES",
    "Z_95",
    "Fact",
    "RecountError",
    "bootstrap_median_interval",
    "conformance_from_scan",
    "distribution",
    "facts_from_detection_rows",
    "facts_from_table",
    "group_key",
    "parse_detection_rows",
    "quantile",
    "recount_groups",
    "split_tag",
    "universe_from_registry",
    "wilson_interval",
]


class RecountError(RuntimeError):
    """A condition under which the recount would be wrong rather than merely different."""


#: The frozen route taxonomy, `metrics/survival.md` §3. Exhaustive and mutually exclusive.
ROUTES = (
    "out_of_scope",
    "retained_by_design",
    "undetected",
    "misassigned",
    "conformance_failure",
    "unresolved",
)

#: `conformance_failure` is A7.1's to establish with record-level evidence; no detection table
#: may assert it (`metrics/survival.md` §3, `metrics/detections.md`).
ROUTE_NOT_ASSERTABLE_BY_A_DETECTOR = "conformance_failure"

#: z for a two-sided 95% interval. The A2 tables name the same constant in `survival.method`,
#: which is how two Wilson implementations are comparable at all.
Z_95 = 1.959964

#: `metrics/survival.md` §4, M2.
BOOTSTRAP_RESAMPLES = 10_000

#: The rank grammar of Evo 1's released lineage tag, in order. Read off the released records
#: (`r__…;k__…;p__…;c__…;o__…;f__…;g__…;s__…`) and matching the `ranks` list every
#: `remove_if_unspecific` rule in `policies/specs/evo1-*.yaml` declares.
TAG_RANKS = ("realm", "kingdom", "phylum", "class", "order", "family", "genus", "species")
TAG_PREFIXES = {rank: rank[0] + "__" for rank in TAG_RANKS}

#: The rule kinds a released record can decide on its own. Everything else reads IMG/VR
#: metadata the release does not carry (D-047), and is reported as coverage rather than run.
DECIDABLE_RULE_KINDS = ("remove_if_taxon_in", "remove_if_unspecific")


# --------------------------------------------------------------------------------------
# statistics, from the definitions
# --------------------------------------------------------------------------------------


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> dict[str, float]:
    """The Wilson score interval on a proportion, closed form.

    Centre `(k + z^2/2) / (n + z^2)`, half-width `z/(n + z^2) * sqrt(k(n-k)/n + z^2/4)`. Chosen by
    `metrics/survival.md` §4 because the proportion is expected near 0 or 1, where the normal
    interval leaves `[0, 1]` and collapses to zero width.
    """
    if trials <= 0:
        raise RecountError("a Wilson interval needs a non-empty denominator")
    if not 0 <= successes <= trials:
        raise RecountError(f"{successes} successes in {trials} trials is not a proportion")
    n, k, zz = float(trials), float(successes), z * z
    denom = n + zz
    centre = (k + zz / 2.0) / denom
    halfwidth = (z / denom) * math.sqrt(k * (n - k) / n + zz / 4.0)
    return {
        "estimate": k / n,
        "low": max(0.0, centre - halfwidth),
        "high": min(1.0, centre + halfwidth),
        "method": f"wilson_z{z:.6f}",
    }


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile on the sorted sample (the `numpy.quantile` default)."""
    if not values:
        raise RecountError("no values to take a quantile of")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


#: Resamples drawn at a time. Part of the interval's identity: the stream of random numbers,
#: and so the interval, depends on it. 10,000 x 13,679 draws do not fit in memory at once.
BOOTSTRAP_CHUNK = 200


def bootstrap_median_interval(
    values: Sequence[float],
    *,
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
    chunk: int = BOOTSTRAP_CHUNK,
) -> dict[str, Any]:
    """95% bootstrap percentile interval on the median, resampling families with replacement.

    `metrics/survival.md` §4 fixes the resample count and requires the seed to be declared.
    The generator is built here from that seed alone, so the interval does not depend on what
    else in the run drew a number first, and it is drawn in fixed-size chunks so the result is
    reproducible rather than dependent on how much memory the machine had.
    """
    import numpy as np

    if not values:
        raise RecountError("no values to bootstrap")
    sample = np.asarray(values, dtype=np.float64)
    n = sample.size
    rng = np.random.default_rng(seed)
    medians = np.empty(resamples, dtype=np.float64)
    done = 0
    while done < resamples:
        take = min(chunk, resamples - done)
        idx = rng.integers(0, n, size=(take, n))
        medians[done : done + take] = np.median(sample[idx], axis=1)
        done += take
    ordered = medians.tolist()
    return {
        "estimate": quantile(sample.tolist(), 0.5),
        "low": quantile(ordered, 0.025),
        "high": quantile(ordered, 0.975),
        "method": f"bootstrap_percentile_{resamples}_chunk{chunk}",
        "seed": seed,
    }


def distribution(
    values: Sequence[float], *, seed: int, resamples: int = BOOTSTRAP_RESAMPLES
) -> dict[str, Any]:
    """M2's reported shape: median with its interval, IQR, maximum and the sample size."""
    return {
        "n": len(values),
        "median": bootstrap_median_interval(values, seed=seed, resamples=resamples),
        "q1": quantile(values, 0.25),
        "q3": quantile(values, 0.75),
        "max": float(max(values)),
        "total": float(sum(values)),
    }


# --------------------------------------------------------------------------------------
# the fact table
# --------------------------------------------------------------------------------------


class Fact(NamedTuple):
    """One row of the relational table everything downstream is a grouping over.

    `hits` is detections and `records` is distinct surviving records, per
    `metrics/detections.md`. `basis` says which view of the measurement the row came from:
    `detection-rows` for a row rebuilt from the `.jsonl`, `table-rows` for one taken from the
    table's own per-family aggregate because no record-level file was published.
    """

    group: str
    policy: str
    release: str
    universe: str
    detector: str
    task: str
    family_id: str
    route: str
    hits: int
    records: float
    basis: str


def group_key(policy: str, release: str, universe: str) -> str:
    """One group is one policy reading x release x family universe — never pooled."""
    return f"{policy}|{release}|{universe}"


def universe_name(doc: dict[str, Any]) -> str:
    """The universe a table counts against, including any restriction on it.

    A restriction is part of a universe's identity: RVDB-prot 32.0 and RVDB-prot 32.0 cut to
    A2.5's segmented selection answer different questions over different denominators, and
    pooling them would be the error `metrics/survival.md` forbids between registries.
    """
    registry = doc["registry"]
    if isinstance(registry, dict):
        name = f"{registry['id']}/{registry['version']}"
        if registry.get("restricted_to"):
            selection = registry.get("selection", {})
            return f"{name}+{selection.get('decision', 'restricted')}"
        return name
    return f"{registry}/{doc['registry_version']}"


def _check_route(route: str, where: str) -> str:
    if route == ROUTE_NOT_ASSERTABLE_BY_A_DETECTOR:
        raise RecountError(
            f"{where}: a detection table asserts {route!r}. That claim is A7.1's, established "
            "with record-level evidence (metrics/survival.md §3)."
        )
    if route not in ROUTES:
        raise RecountError(f"{where}: route {route!r} is outside the frozen taxonomy")
    return route


def _apportion(records: float, hits_by_route: dict[str, int]) -> dict[str, float]:
    """Split a family's record count across its routes in proportion to its detections.

    Only reached for a table that published no record-level file and whose family carries more
    than one route. The per-route record count is then an apportionment and is reported as one;
    the overall M2, which is the headline, never passes through this function.
    """
    total = sum(hits_by_route.values())
    if total <= 0:
        raise RecountError("cannot apportion records across routes with no hits")
    return {route: records * hits / total for route, hits in hits_by_route.items()}


def facts_from_table(doc: dict[str, Any], *, where: str) -> list[Fact]:
    """Rows from a table's own `families[]` aggregates — the fallback view."""
    group = group_key(doc["manifest"]["policy_id"], doc["manifest"]["release"], universe_name(doc))
    out: list[Fact] = []
    for row in doc["families"]:
        routes = {
            _check_route(route, where): int(hits)
            for route, hits in (row.get("routes") or {}).items()
        }
        if not routes:
            table_routes = {r: h for r, h in (doc.get("routes") or {}).items() if h}
            if len(table_routes) != 1:
                raise RecountError(
                    f"{where}: family {row['family_id']} carries no route and the table declares "
                    f"{len(table_routes)} table-level routes. With none or several, each "
                    "detection's route is undetermined and the merge must refuse it."
                )
            routes = {_check_route(next(iter(table_routes)), where): int(row["hits"])}
        if sum(routes.values()) != int(row["hits"]):
            raise RecountError(
                f"{where}: family {row['family_id']} has {row['hits']} hits but its route counts "
                f"sum to {sum(routes.values())}"
            )
        records = _apportion(float(row["records"]), routes)
        for route, hits in routes.items():
            out.append(
                Fact(
                    group=group,
                    policy=doc["manifest"]["policy_id"],
                    release=doc["manifest"]["release"],
                    universe=universe_name(doc),
                    detector=doc["detector"],
                    task=doc["task"],
                    family_id=row["family_id"],
                    route=route,
                    hits=hits,
                    records=records[route],
                    basis="table-rows",
                )
            )
    return out


def parse_detection_rows(lines: Iterable[str], *, where: str) -> list[dict[str, Any]]:
    """Parse a detection `.jsonl`, one object per line.

    A2.3's files are written double-encoded — each line is a JSON *string* holding the object —
    which `metrics/detections.md` does not allow for. Accepting it here rather than failing is
    deliberate: the deviation is recorded in the output as a contract finding, and refusing it
    would throw away the only record-level view of that arm.
    """
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        value = json.loads(text)
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise RecountError(f"{where}: line {lineno} is not a detection object")
        rows.append(value)
    return rows


def facts_from_detection_rows(
    doc: dict[str, Any], rows: Sequence[dict[str, Any]], *, where: str
) -> list[Fact]:
    """Rows rebuilt from the primitive detections: hits are lines, records are distinct ids."""
    group = group_key(doc["manifest"]["policy_id"], doc["manifest"]["release"], universe_name(doc))
    hits: dict[tuple[str, str], int] = defaultdict(int)
    records: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = (row["family_id"], _check_route(row["route"], where))
        hits[key] += 1
        records[key].add(row["record_id"])
    return [
        Fact(
            group=group,
            policy=doc["manifest"]["policy_id"],
            release=doc["manifest"]["release"],
            universe=universe_name(doc),
            detector=doc["detector"],
            task=doc["task"],
            family_id=family,
            route=route,
            hits=count,
            records=float(len(records[(family, route)])),
            basis="detection-rows",
        )
        for (family, route), count in sorted(hits.items())
    ]


# --------------------------------------------------------------------------------------
# universes, rebuilt from the pinned registry artefacts
# --------------------------------------------------------------------------------------


def universe_from_registry(registry: str, doc: dict[str, Any]) -> set[str]:
    """`F_R` for one registry, from that registry's own pinned artefact.

    Pfam: the viral subset this project selected (D-075), by accession. RVDB-prot: every family
    in the release. Dfam: the curated LTR export restricted to ERV models that carry a curated
    threshold — the universe A2.3's own denominator note describes, rebuilt from the per-model
    rows rather than taken from the summary count beside them.
    """
    if registry == "pfam":
        return {row["accession"] for row in doc["families"]}
    if registry == "rvdb-prot":
        return {row["family_id"] for row in doc["entries"]}
    if registry == "dfam-curated-ltr":
        return {
            row["family_id"]
            for row in doc["families"]
            if row.get("is_erv") and row.get("threshold") is not None
        }
    raise RecountError(f"no independent universe rule for registry {registry!r}")


# --------------------------------------------------------------------------------------
# the grouping pass
# --------------------------------------------------------------------------------------


def _searched_components(doc: dict[str, Any]) -> set[str]:
    return {
        source.get("corpus_component") or source.get("component")
        for source in doc.get("sources", [])
        if source.get("searched")
    }


def check_component_partition(tables: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
    """Refuse a group where two detectors report searching the same corpus component.

    M2 sums record counts across detectors, so a component read twice counts its records twice.
    `metrics/detections.md` requires every table to list each component with `searched` and a
    reason, which makes the partition checkable rather than assumed.
    """
    by_component: dict[str, list[str]] = defaultdict(list)
    for doc in tables:
        for component in _searched_components(doc):
            by_component[component].append(doc["detector"])
    for component, detectors in sorted(by_component.items()):
        if len(detectors) > 1:
            raise RecountError(
                f"component {component!r} is reported searched by {sorted(detectors)}: record "
                "counts would be summed twice over the same records"
            )
    return {component: sorted(d) for component, d in sorted(by_component.items())}


def _manifest_pins(tables: Sequence[dict[str, Any]]) -> dict[str, str]:
    pins: dict[str, str] = {}
    for doc in tables:
        manifest = doc["manifest"]
        key = f"{manifest['policy_id']}|{manifest['release']}"
        sha = manifest.get("sha256")
        if sha is None:
            continue
        if key in pins and pins[key] != sha:
            raise RecountError(
                f"tables in group {key} were computed against different A1.4 manifests "
                f"({pins[key][:12]}… vs {sha[:12]}…): the numbers would line up and mean "
                "different things"
            )
        pins[key] = sha
    return pins


def recount_groups(
    inputs: Sequence[dict[str, Any]],
    *,
    universes: dict[str, set[str]],
    removed_records: dict[str, set[str]],
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    """Compute M1 and M2 for every group, overall and per route.

    `inputs` is one entry per detection table: `{"doc": <table>, "rows": <detections or None>,
    "source": <where it came from>}`. `universes` maps a universe name to the set of family ids
    that is `F_R`; a universe absent from it is taken from the table's own two family lists and
    flagged, since nothing independent could rebuild it. `removed_records` maps
    `policy|release` to the records the reading removes, which no detection may fall on.
    """
    facts: list[Fact] = []
    tables_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    findings: list[str] = []

    for entry in inputs:
        doc, rows, where = entry["doc"], entry.get("rows"), entry["source"]
        group = group_key(
            doc["manifest"]["policy_id"], doc["manifest"]["release"], universe_name(doc)
        )
        tables_by_group[group].append(doc)
        if rows is None:
            facts.extend(facts_from_table(doc, where=where))
            continue
        pinned = doc["manifest"]
        removed = removed_records.get(f"{pinned['policy_id']}|{pinned['release']}")
        if removed:
            on_removed = sorted({r["record_id"] for r in rows if r["record_id"] in removed})
            if on_removed:
                raise RecountError(
                    f"{where}: {len(on_removed)} detections fall on records this reading "
                    f"removes, e.g. {on_removed[0]}. Those records are not in the surviving "
                    "set (metrics/manifests.md)."
                )
        from_rows = facts_from_detection_rows(doc, rows, where=where)
        from_table = facts_from_table(doc, where=where)
        hits_rows = sum(f.hits for f in from_rows)
        hits_table = sum(f.hits for f in from_table)
        if hits_rows != hits_table:
            findings.append(
                f"{where}: the detection rows carry {hits_rows} hits and the table's family "
                f"aggregates {hits_table}. The recount uses the rows."
            )
        facts.extend(from_rows)

    results = []
    for group in sorted(tables_by_group):
        results.append(
            _recount_one_group(
                group,
                tables_by_group[group],
                [f for f in facts if f.group == group],
                universes=universes,
                seed=seed,
                resamples=resamples,
                findings=findings,
            )
        )
    return {"groups": results, "findings": findings}


def _universe_for(
    group: str,
    tables: Sequence[dict[str, Any]],
    universes: dict[str, set[str]],
    findings: list[str],
) -> tuple[set[str], str]:
    universe = tables[0]["universe_name"]
    stated = {
        family
        for doc in tables
        for family in (
            [row["family_id"] for row in doc["families"]] + list(doc["families_without_a_hit"])
        )
    }
    independent = universes.get(universe)
    if independent is None:
        findings.append(
            f"{group}: no registry artefact can rebuild the universe {universe!r}; it is taken "
            "from the tables' own family lists and is therefore not independently checked."
        )
        return stated, "table-stated"
    missing = sorted(independent - stated)
    extra = sorted(stated - independent)
    if missing or extra:
        raise RecountError(
            f"{group}: the universe rebuilt from the registry artefact has {len(independent)} "
            f"families and the tables state {len(stated)}: {len(missing)} missing, "
            f"{len(extra)} unexpected (e.g. {(missing or extra)[0]})"
        )
    return independent, "registry-artefact"


def _recount_one_group(
    group: str,
    tables: Sequence[dict[str, Any]],
    facts: Sequence[Fact],
    *,
    universes: dict[str, set[str]],
    seed: int,
    resamples: int,
    findings: list[str],
) -> dict[str, Any]:
    for doc in tables:
        doc["universe_name"] = universe_name(doc)
    pins = _manifest_pins(tables)
    components = check_component_partition(tables)
    universe, universe_basis = _universe_for(group, tables, universes, findings)
    kinds = sorted({doc["estimate_kind"] for doc in tables})
    policy, release, universe_key = group.split("|")

    entry: dict[str, Any] = {
        "group": group,
        "policy": policy,
        "release": release,
        "universe": universe_key,
        "families_in_universe": len(universe),
        "universe_basis": universe_basis,
        "detectors": sorted({doc["detector"] for doc in tables}),
        "tasks": sorted({doc["task"] for doc in tables}),
        "tables": len(tables),
        "manifest_sha256": pins,
        "components_searched": components,
        "estimate_kinds": kinds,
        "estimate_kind": (
            "not_searched"
            if kinds == ["not_searched"]
            else ("lower_bound" if "lower_bound" in kinds else "population")
        ),
        "basis": sorted({f.basis for f in facts}) or ["none"],
    }

    if entry["estimate_kind"] == "not_searched":
        entry["m1"] = None
        entry["m2"] = None
        entry["withheld"] = (
            "No source in this group's manifest was searched, so every count is zero by "
            "construction and none of it is evidence of absence (metrics/detections.md). A "
            "Wilson interval over it would read as a filter that removed everything."
        )
        return entry

    unknown = sorted({f.family_id for f in facts} - universe)
    if unknown:
        raise RecountError(
            f"{group}: {len(unknown)} detected families are outside the pinned universe, "
            f"e.g. {unknown[0]}"
        )

    # M1: set algebra over the fact rows. The overall figure is the union over routes, which is
    # why the per-route figures do not sum to it.
    detected = {f.family_id for f in facts if f.hits > 0}
    entry["m1"] = {
        "families_detected": len(detected),
        "interval": wilson_interval(len(detected), len(universe)),
        "per_route": {
            route: {
                "families_detected": len(
                    {f.family_id for f in facts if f.route == route and f.hits > 0}
                ),
                "interval": wilson_interval(
                    len({f.family_id for f in facts if f.route == route and f.hits > 0}),
                    len(universe),
                ),
            }
            for route in ROUTES
            if any(f.route == route for f in facts)
        },
        "reading": (
            "Per-route figures are computed over the detections carrying that route only. A "
            "family can survive by more than one route, so they do not sum to the overall "
            "figure (metrics/survival.md §4)."
        ),
    }

    # M2: the distribution of n_f over the whole zero-filled universe, and — because
    # `surviving sequence count per family` does not say which of the two published counts is
    # `n_f` — the same over hits, and over the detected families only.
    records_by_family: dict[str, float] = defaultdict(float)
    hits_by_family: dict[str, int] = defaultdict(int)
    records_by_route: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in facts:
        records_by_family[f.family_id] += f.records
        hits_by_family[f.family_id] += f.hits
        records_by_route[f.route][f.family_id] += f.records
    ordered_universe = sorted(universe)
    zero_filled = [records_by_family.get(family, 0.0) for family in ordered_universe]
    entry["m2"] = {
        "records_zero_filled": distribution(zero_filled, seed=seed, resamples=resamples),
        "records_detected_only": distribution(
            sorted(records_by_family.values()), seed=seed, resamples=resamples
        )
        if records_by_family
        else None,
        "hits_zero_filled": distribution(
            [float(hits_by_family.get(family, 0)) for family in ordered_universe],
            seed=seed,
            resamples=resamples,
        ),
        "per_route": {
            route: distribution(
                [records_by_route[route].get(family, 0.0) for family in ordered_universe],
                seed=seed,
                resamples=resamples,
            )
            for route in ROUTES
            if route in records_by_route
        },
        "reading": (
            "`n_f` is the number of surviving sequences detected for family f. The headline "
            "takes a surviving sequence to be a surviving corpus record, counted distinct where "
            "a record-level file exists; `hits_zero_filled` is the same distribution over "
            "detections, which exceed records where one record carries several genes of a "
            "family. Zero-filled over the whole pinned universe, per metrics/survival.md §6."
        ),
    }
    entry["detections"] = {
        "hits": sum(f.hits for f in facts),
        "records": sum(records_by_family.values()),
        "by_route": {
            route: sum(f.hits for f in facts if f.route == route)
            for route in ROUTES
            if any(f.route == route for f in facts)
        },
        "by_detector": {
            detector: sum(f.hits for f in facts if f.detector == detector)
            for detector in sorted({f.detector for f in facts})
        },
    }
    entry["composition"] = [
        {"family_id": family, "records": records_by_family[family], "hits": hits_by_family[family]}
        for family in sorted(records_by_family, key=lambda k: (-hits_by_family[k], k))[:10]
    ]
    return entry


# --------------------------------------------------------------------------------------
# the conformance arm
# --------------------------------------------------------------------------------------


def split_tag(tag: str) -> dict[str, str]:
    """The assigned taxa of one released lineage tag, by rank.

    The released form is eight `;`-separated fields, each either empty or prefixed with its
    rank's initial. A field whose prefix is not the one its position calls for is a malformed
    tag and stops the run rather than being guessed at.
    """
    fields = tag.split(";")
    if len(fields) != len(TAG_RANKS):
        raise RecountError(f"lineage tag {tag!r} has {len(fields)} fields, expected 8")
    assigned: dict[str, str] = {}
    for rank, field in zip(TAG_RANKS, fields, strict=True):
        if not field:
            continue
        prefix = TAG_PREFIXES[rank]
        if not field.startswith(prefix):
            raise RecountError(f"lineage tag {tag!r}: field {field!r} is not a {rank}")
        assigned[rank] = field[len(prefix) :]
    return assigned


def _rule_removes(rule: dict[str, Any], assigned: dict[str, str]) -> str | None:
    """Why this rule removes a record with these assigned taxa, or None."""
    kind, params = rule["kind"], rule.get("params") or {}
    if kind == "remove_if_taxon_in":
        rank = params["rank"]
        name = assigned.get(rank)
        if name is not None and name in set(params["names"]):
            return f"{rank} {name} is on the published denylist"
        return None
    if kind == "remove_if_unspecific":
        required = params["require_rank"]
        if required not in assigned:
            return f"no {required} assigned"
        deepest_rank = [r for r in TAG_RANKS if r in assigned][-1]
        if assigned[deepest_rank] in set(params["stop_taxa"]):
            return f"assigned only up to {deepest_rank} {assigned[deepest_rank]}"
        return None
    raise RecountError(f"rule kind {kind!r} cannot be decided from a lineage tag alone")


def conformance_from_scan(scan: dict[str, Any], specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Re-execute each reading's published rules over the scan's complete tag census.

    The scan collapses every released record of Evo 1's viral component onto its lineage tag.
    For a predicate that reads only the lineage that is exact, not a sample: a tag's count is
    the number of records the predicate decides identically. A record still in the released
    corpus that a published rule removes is a **candidate** conformance failure, attributed to
    the first rule in published order that removes it — the rule a conformance claim would
    cite.
    """
    tag_counts: dict[str, int] = scan["tag_counts"]
    total = sum(tag_counts.values())
    if total != scan["rows"]:
        raise RecountError(
            f"the tag census covers {total} records and the scan read {scan['rows']}: the "
            "census is not complete and no rate drawn from it is a rate over the release"
        )
    structure = scan.get("structure", {})
    if not structure.get("one_row_one_record", False):
        raise RecountError(
            "the scan's structure check failed, so every count in it is a count of rows rather "
            "than of records (metrics/manifests.md); no conformance count may be quoted from it"
        )

    readings: dict[str, Any] = {}
    for policy_id, spec in sorted(specs.items()):
        rules = spec["policy"]["rules"]
        decidable = [r for r in rules if r["kind"] in DECIDABLE_RULE_KINDS]
        undecidable = [r["id"] for r in rules if r["kind"] not in DECIDABLE_RULE_KINDS]
        by_rule: dict[str, int] = {r["id"]: 0 for r in decidable}
        by_cause: dict[str, int] = defaultdict(int)
        failures = 0
        for tag, count in tag_counts.items():
            assigned = split_tag(tag)
            for rule in decidable:  # published order; first to remove is the one attributed
                why = _rule_removes(rule, assigned)
                if why is not None:
                    failures += count
                    by_rule[rule["id"]] += count
                    by_cause[why] += count
                    break
        readings[policy_id] = {
            "records_in_release": total,
            "conformance_failures": failures,
            "rate": wilson_interval(failures, total),
            "by_rule": by_rule,
            "by_cause": dict(sorted(by_cause.items())),
            "coverage": {
                "rules_total": len(rules),
                "rules_executed": len(decidable),
                "rules_not_executed": undecidable,
                "stated": f"{len(decidable)}/{len(rules)}",
                "why": (
                    "The rules not executed read IMG/VR metadata — the high-confidence flag, "
                    "the vOTU and the prokaryotic-host count — that does not travel with the "
                    "released records (D-047). The restriction is derived from each rule's own "
                    "kind, not chosen by hand."
                ),
            },
        }

    distinct = {
        policy: (
            reading["conformance_failures"],
            tuple(sorted(reading["by_rule"].items())),
        )
        for policy, reading in readings.items()
    }
    identical = len(set(distinct.values())) == 1
    return {
        "release": scan.get("release"),
        "readings": readings,
        "readings_identical": identical,
        "why_identical": (
            "Identical by construction, not by agreement: every rule the three readings differ "
            "over reads an input the release withholds, so the readings cannot differ here "
            "(D-047)."
        )
        if identical
        else None,
    }


# --------------------------------------------------------------------------------------
# a bounded independent re-read of the scan's own input
# --------------------------------------------------------------------------------------


def sample_row_groups(num_row_groups: int, take: int, *, seed: int) -> list[int]:
    """Which row groups the scan re-read samples. Deterministic from the declared seed."""
    rng = random.Random(seed)
    take = min(take, num_row_groups)
    return sorted(rng.sample(range(num_row_groups), take))


def tags_in_record(text: str) -> list[str]:
    """The lineage tags of one released record, from the `|tag|block` form it is stored in."""
    if not text.startswith("|"):
        return []
    parts = text.split("|")
    return parts[1::2]


def verify_scan_sample(
    records: Iterable[str], scan: dict[str, Any], *, block_chars: int
) -> dict[str, Any]:
    """Re-extract lineage tags from sampled released records and check them against the scan.

    This is the one part of the conformance arm that does not rest on A7.1's artefact. It is
    bounded and it is a check, not a measurement: it can show that the scan's tag census is
    wrong about the records it re-reads, and it cannot show that the census is complete.
    """
    seen: dict[str, int] = defaultdict(int)
    rows = multi_tag = untagged = at_budget = 0
    for text in records:
        rows += 1
        tags = tags_in_record(text)
        if not tags:
            untagged += 1
            continue
        if len(set(tags)) > 1:
            multi_tag += 1
        blocks = text.split("|")[2::2]
        if blocks and len(blocks[-1]) >= block_chars:
            at_budget += 1
        seen[tags[0]] += 1
    census: dict[str, int] = scan["tag_counts"]
    unknown = sorted(tag for tag in seen if tag not in census)
    over = sorted(tag for tag, n in seen.items() if n > census.get(tag, 0))
    return {
        "records_read": rows,
        "distinct_tags": len(seen),
        "tags_not_in_the_census": unknown,
        "tags_exceeding_their_census_count": over,
        "records_with_more_than_one_tag": multi_tag,
        "records_with_no_tag": untagged,
        "records_whose_last_block_is_full": at_budget,
        "agrees": not unknown and not over and multi_tag == 0 and untagged == 0,
        "reading": (
            "A bounded re-read of the released Parquet, independent of A7.1's pass over it. It "
            "checks that every tag found is in the census, that no tag occurs more often in the "
            "sample than the census allows in the whole release, and that the one-row-one-record "
            "reading holds on the rows read. It cannot establish that the census is complete."
        ),
    }

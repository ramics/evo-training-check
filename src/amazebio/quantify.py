"""Merging the A2 detection tables into the headline quantification — task A3.2.

`metrics/survival.md` is the authoritative specification and this module implements it at
corpus scale. `amazebio.survival` holds the frozen definitions and a reference implementation
small enough to pin the specification's worked examples; this module is the part that reads
five detectors' artefacts and produces M1 and M2 per model, reading, registry and route.

Read `metrics/survival.md` before changing anything here. The definitions are frozen (D-022):
a metric redefined after the counts are in is not a metric.

**Three things this module refuses to do**, each because doing it would produce a number that
looks right and means something else:

*Pool across universes.* A group is one policy reading, one release and one **registry
universe**, where a universe is a registry id, its version and any restriction applied to it.
RVDB-prot at 13,679 families and RVDB-prot restricted to D-190's 1,285 segmented families are
two universes and never one, for the same reason Pfam and RVDB are two (D-022, D-161).

*Sum counts across detectors that read the same corpus component.* Family-level survival (M1)
is a union and is safe under any overlap, but the per-family sequence count (M2) is a sum, and
a sum over two detectors that read the same records double-counts. The A2 detectors partition
the corpus by construction — profile search reads the viral and metagenome components, provirus
detection reads the bacterial genomes, element detection reads the eukaryotic genomes — and
:func:`check_component_disjointness` **verifies** that partition from each table's own
`sources[]` rather than trusting it. A detector set that overlaps raises; it does not get
silently added up.

*Accept an untagged detection.* Every detection carries exactly one route from the A3.1
taxonomy, checked here rather than assumed (D-042). A table tags routes one of two ways and
both are checked against the table's own totals: per family row, where the row's route counts
must sum to its hits, or as a single uniform route the table declares for every record it
searched. An unknown route, a missing route or counts that do not reconcile all raise.

The independent reimplementation in A3.3 works from `metrics/survival.md`, not from this file.
"""

from __future__ import annotations

import dataclasses
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from amazebio.survival import Interval, Route, wilson_interval

__all__ = [
    "GroupKey",
    "MergeError",
    "MergedGroup",
    "QuantifiedGroup",
    "RegistryUniverse",
    "SourceTable",
    "bootstrap_median_interval",
    "check_component_disjointness",
    "group_tables",
    "load_table",
    "merge_group",
    "quantify",
]

#: Resamples for M2's bootstrap interval. Part of the frozen specification (metrics/survival.md
#: §4, M2), not a caller's choice: a median interval quoted at two different resample counts is
#: two different estimates wearing one label.
BOOTSTRAP_RESAMPLES = 10_000

#: Element-kind key for a detector that reports no kind at all. Distinct from
#: `unclassified_element`, which is a detector saying it looked and could not place the element.
#: Collapsing the two would turn "not measured" into "measured as unclassifiable".
KIND_NOT_REPORTED = "not_reported"


class MergeError(RuntimeError):
    """Raised when the merge is asked to combine tables it cannot combine honestly."""


@dataclasses.dataclass(frozen=True, slots=True)
class RegistryUniverse:
    """The family universe a group's denominator comes from.

    `restriction` is part of the identity, not an annotation. D-190's segmented selection is
    RVDB-prot 32.0 cut down to 1,285 families, and a survival fraction over it answers a
    different question from one over the full 13,679 — so the two are different universes and
    the group key keeps them apart.
    """

    registry: str
    version: str
    restriction: str | None
    size: int

    @property
    def key(self) -> str:
        return f"{self.registry}/{self.version}" + (
            f"+{self.restriction}" if self.restriction else ""
        )


@dataclasses.dataclass(frozen=True, slots=True)
class GroupKey:
    """One policy reading, one release, one registry universe — the unit everything reports at."""

    policy_id: str
    release: str
    universe: RegistryUniverse

    @property
    def slug(self) -> str:
        uni = self.universe.key.replace("/", "-").replace("+", "-")
        return f"{uni}-{self.policy_id}-{self.release}"


@dataclasses.dataclass(frozen=True, slots=True)
class SourceTable:
    """One A2 detection table, loaded and checked.

    `counts` and `routes` are per family and already reconciled against the table's own totals.
    `searched_components` is what the disjointness check reads; a component the detector
    declares it did not search does not appear.
    """

    task: str
    detector: str
    source: str
    universe: RegistryUniverse
    policy_id: str
    release: str
    manifest_sha256: str
    estimate_kind: str
    searched_components: tuple[str, ...]
    #: family_id -> number of surviving corpus records carrying a detection for that family.
    counts: Mapping[str, int]
    #: family_id -> route -> detections on that route.
    routes: Mapping[str, Mapping[str, int]]
    #: family_id -> element kind -> detections of that kind.
    element_kinds: Mapping[str, Mapping[str, int]]
    #: How the table attributed routes: `per_family` or `uniform`.
    route_attribution: str
    notes: tuple[str, ...] = ()


def _universe_of(doc: Mapping[str, Any], *, source: str) -> RegistryUniverse:
    registry = doc.get("registry")
    version = doc.get("registry_version")
    restriction = None
    if isinstance(registry, Mapping):
        # A2.5's segmented arm carries the whole registry description inline, with the
        # restriction that makes it a different universe (D-190) inside it.
        restriction = (registry.get("selection") or {}).get("decision") or "restricted"
        version = registry.get("version", version)
        registry = registry.get("id")
    if not registry or not version:
        raise MergeError(
            f"{source}: no registry universe on the table. A survival fraction with no named "
            "denominator is not quotable (D-161) and cannot be grouped."
        )
    size = len(doc.get("families", [])) + len(doc.get("families_without_a_hit", []))
    if size <= 0:
        raise MergeError(
            f"{source}: the family universe is empty. A zero-filled universe is what makes a "
            "null visible (metrics/survival.md §6); an empty one means the registry was not "
            "pinned."
        )
    return RegistryUniverse(
        registry=str(registry), version=str(version), restriction=restriction, size=size
    )


def _checked_routes(name: str, counts: Mapping[str, Any], *, source: str) -> dict[str, int]:
    known = {r.value for r in Route}
    out: dict[str, int] = {}
    for route, n in counts.items():
        if route not in known:
            raise MergeError(
                f"{source}: {name} carries route {route!r}, which is not in the A3.1 taxonomy "
                f"({', '.join(sorted(known))}). The merge fails on an unknown route rather "
                "than dropping it, because a dropped detection lowers the headline silently."
            )
        out[route] = int(n)
    return out


def load_table(doc: Mapping[str, Any], *, source: str) -> SourceTable:
    """Load and check one A2 detection table.

    Raises :class:`MergeError` on an untagged detection, an unknown route, or route counts that
    do not reconcile with the table's own hit totals — the three ways a merged headline can be
    wrong without looking wrong.
    """
    universe = _universe_of(doc, source=source)
    manifest = doc.get("manifest")
    if not manifest:
        raise MergeError(
            f"{source}: no manifest on the table, so the surviving corpus it describes "
            "cannot be identified"
        )

    rows = list(doc.get("families") or [])
    counts: dict[str, int] = {}
    routes: dict[str, dict[str, int]] = {}
    kinds: dict[str, dict[str, int]] = {}

    per_family = all("routes" in r for r in rows) if rows else True
    uniform = _checked_routes("the table", doc.get("routes") or {}, source=source)

    # A2.5's segmented arm attributes one route to every record it searched rather than to each
    # detection. That is a stronger statement than a per-detection tag, not a weaker one, but
    # only when it names exactly one route — two would leave each detection's route
    # undetermined and the merge must not pick one.
    if not per_family and len(uniform) != 1:
        raise MergeError(
            f"{source}: family rows carry no route and the table declares "
            f"{len(uniform)} table-level routes. A detection with no determinable route is "
            "exactly what D-042 requires this merge to refuse."
        )

    uniform_route = next(iter(uniform)) if len(uniform) == 1 else None

    for row in rows:
        fid = row["family_id"]
        hits = int(row["hits"])
        # `records` is the number of distinct surviving corpus records, which is the unit M2
        # counts; `hits` can exceed it when one record carries two matches to the same family.
        counts[fid] = int(row.get("records", hits))
        if "routes" in row:
            rr = _checked_routes(f"family {fid}", row["routes"], source=source)
            if sum(rr.values()) != hits:
                raise MergeError(
                    f"{source}: family {fid} has {hits} hits but its route counts sum to "
                    f"{sum(rr.values())}. Untagged detections are hidden in that gap."
                )
        else:
            rr = {uniform_route: hits}  # type: ignore[dict-item]
        routes[fid] = rr
        kk = {str(k): int(v) for k, v in (row.get("element_kinds") or {}).items()}
        kinds[fid] = kk or {KIND_NOT_REPORTED: hits}

    searched = tuple(
        sorted(
            {
                str(s.get("corpus_component") or s.get("component"))
                for s in doc.get("sources", [])
                if s.get("searched")
            }
        )
    )
    return SourceTable(
        task=str(doc["task"]),
        detector=str(doc["detector"]),
        source=source,
        universe=universe,
        policy_id=str(manifest["policy_id"]),
        release=str(manifest["release"]),
        manifest_sha256=str(manifest.get("sha256", "")),
        estimate_kind=str(doc["estimate_kind"]),
        searched_components=searched,
        counts=counts,
        routes=routes,
        element_kinds=kinds,
        route_attribution="per_family" if per_family else "uniform",
        notes=tuple(str(n) for n in doc.get("notes", [])),
    )


def check_component_disjointness(tables: Sequence[SourceTable]) -> None:
    """Refuse a group whose detectors read the same corpus component.

    M1 is a union over families and survives overlap; M2 sums per-family record counts across
    detectors and does not. The A2 detectors partition the corpus — `metrics/detections.md`
    requires each table to list every component with `searched: false` and a reason for the
    ones it did not read — so the partition is stated in the artefacts and checkable here.
    Checked rather than assumed: a detector widened to a second component later would otherwise
    inflate every per-family count in this group with nothing in the output saying so.
    """
    seen: dict[str, SourceTable] = {}
    for t in tables:
        for component in t.searched_components:
            prior = seen.get(component)
            if prior is not None and prior.detector != t.detector:
                raise MergeError(
                    f"{t.detector} and {prior.detector} both searched component "
                    f"{component!r} for {t.policy_id}/{t.release}. Per-family counts are summed "
                    "across detectors, so overlapping components would double-count. Either the "
                    "detectors' scopes changed or a table's sources[] is wrong; both need "
                    "settling before a headline is computed."
                )
            seen.setdefault(component, t)


@dataclasses.dataclass(frozen=True, slots=True)
class MergedGroup:
    """Every detector's contribution to one group, combined and zero-filled."""

    key: GroupKey
    tables: tuple[SourceTable, ...]
    #: family_id -> surviving record count, summed over detectors. Only families with a hit.
    counts: Mapping[str, int]
    #: route -> family_id -> surviving record count on that route.
    by_route: Mapping[str, Mapping[str, int]]
    #: route -> element kind -> detections, the cross-tabulation metrics/survival.md §3 requires.
    route_by_kind: Mapping[str, Mapping[str, int]]
    estimate_kind: str

    def zero_filled(self, counts: Mapping[str, int] | None = None) -> list[int]:
        """Counts over the whole pinned universe, absent families filled with zero.

        Zero-filling is load-bearing: a family with no surviving homolog is the result this
        audit is testing for, and a distribution built only from detected families would render
        a null as missing data (metrics/survival.md §6).
        """
        c = self.counts if counts is None else counts
        if len(c) > self.key.universe.size:
            raise MergeError(
                f"{self.key.slug}: {len(c)} families carry detections but the pinned universe "
                f"holds {self.key.universe.size}. The denominator and the detections come from "
                "different registry releases."
            )
        return [0] * (self.key.universe.size - len(c)) + sorted(c.values())


def _combine_estimate_kind(tables: Sequence[SourceTable]) -> str:
    """The weakest claim any contributing table makes is the claim the group can make.

    `not_searched` where no detector read anything, `lower_bound` where any did so on a sample.
    A group mixing a census with a sample is a lower bound: the sampled detector's families may
    survive in the records it did not read, and calling the group a population figure would
    assert evidence of absence nobody has (metrics/detections.md).
    """
    searched = [t for t in tables if t.estimate_kind != "not_searched"]
    if not searched:
        return "not_searched"
    return (
        "lower_bound" if any(t.estimate_kind == "lower_bound" for t in searched) else "population"
    )


def merge_group(key: GroupKey, tables: Sequence[SourceTable]) -> MergedGroup:
    """Combine one group's tables, de-duplicating by the rule the module docstring states."""
    if not tables:
        raise MergeError(f"{key.slug}: no tables")
    for t in tables:
        if (t.policy_id, t.release, t.universe) != (key.policy_id, key.release, key.universe):
            raise MergeError(f"{t.source}: does not belong to group {key.slug}")
    check_component_disjointness(tables)

    counts: dict[str, int] = {}
    by_route: dict[str, dict[str, int]] = {}
    route_by_kind: dict[str, dict[str, int]] = {}

    for t in tables:
        for fid, n in t.counts.items():
            if n:
                counts[fid] = counts.get(fid, 0) + n
        for fid, rr in t.routes.items():
            total = sum(rr.values()) or 1
            kinds = t.element_kinds.get(fid, {})
            for route, hits in rr.items():
                if not hits:
                    continue
                # A family's record count is split across its routes in proportion to the
                # detections on each, because a record's route is a property the detector
                # reports per detection and not per record. The split is reported as such; the
                # overall figure, which is the headline, never passes through it.
                share = max(1, round(t.counts.get(fid, 0) * hits / total))
                # Element kinds are apportioned the same way and stay in detections, not
                # records, which is why the key says so: a family's kinds and its record
                # count are different units and adding them is meaningless.
                by_route.setdefault(route, {})
                by_route[route][fid] = by_route[route].get(fid, 0) + share
                tally = route_by_kind.setdefault(route, {})
                for kind, kn in (kinds or {KIND_NOT_REPORTED: hits}).items():
                    tally[kind] = tally.get(kind, 0) + round(kn * hits / total)

    return MergedGroup(
        key=key,
        tables=tuple(tables),
        counts=counts,
        by_route={r: dict(v) for r, v in sorted(by_route.items())},
        route_by_kind={r: dict(sorted(v.items())) for r, v in sorted(route_by_kind.items())},
        estimate_kind=_combine_estimate_kind(tables),
    )


def group_tables(tables: Iterable[SourceTable]) -> dict[GroupKey, list[SourceTable]]:
    """Partition loaded tables into the groups that are reported, never pooled across."""
    out: dict[GroupKey, list[SourceTable]] = {}
    for t in tables:
        out.setdefault(GroupKey(t.policy_id, t.release, t.universe), []).append(t)
    for v in out.values():
        v.sort(key=lambda t: (t.task, t.detector))
    return out


def bootstrap_median_interval(
    values: Sequence[int],
    *,
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Interval:
    """95% bootstrap percentile interval on the median, resampling families with replacement.

    Resampled by drawing multinomial counts over the distinct values rather than by drawing
    `len(values)` indices. The two are the same distribution — a bootstrap resample is exactly
    a multinomial draw over the sample's own empirical distribution — and the multinomial form
    is what makes 10,000 resamples of a 13,679-family universe cheap enough to run for every
    group and every route rather than only for the headline.
    """
    if not values:
        raise MergeError("a bootstrap over an empty family universe is undefined")

    import numpy as np

    arr = np.asarray(values, dtype=np.int64)
    point = float(np.median(arr))
    distinct, freq = np.unique(arr, return_counts=True)
    if distinct.size == 1:
        # Every family has the same count, so every resample has that median. Reported as a
        # zero-width interval rather than skipped: for a filter that worked, this is the
        # headline — every family at zero — and it must print.
        return Interval(point, point, point, f"bootstrap_percentile_p{resamples}_seed{seed}")

    rng = np.random.default_rng(seed)
    n = int(arr.size)
    draws = rng.multinomial(n, freq / n, size=resamples)
    cum = np.cumsum(draws, axis=1)

    # Median of each resample, read off its cumulative counts. Even n takes the mean of the
    # two central order statistics, matching statistics.median on the direct resample.
    def _order_stat(k: np.ndarray) -> np.ndarray:
        idx = (cum < k[:, None]).sum(axis=1)
        return distinct[np.clip(idx, 0, distinct.size - 1)]

    half = np.full(resamples, (n + 1) // 2)
    if n % 2:
        med = _order_stat(half).astype(np.float64)
    else:
        med = (_order_stat(half).astype(np.float64) + _order_stat(half + 1).astype(np.float64)) / 2

    low, high = (float(x) for x in np.percentile(med, [2.5, 97.5]))
    return Interval(point, low, high, f"bootstrap_percentile_p{resamples}_seed{seed}")


def _distribution(values: Sequence[int], *, seed: int, resamples: int) -> dict[str, Any]:
    ordered = sorted(values)
    quartiles = (
        statistics.quantiles(ordered, n=4, method="inclusive")
        if len(ordered) > 1
        else [0.0, 0.0, 0.0]
    )
    median = bootstrap_median_interval(ordered, seed=seed, resamples=resamples)
    return {
        "median": median.estimate,
        "median_ci_low": median.low,
        "median_ci_high": median.high,
        "median_method": median.method,
        "q1": quartiles[0],
        "q3": quartiles[2],
        "iqr": quartiles[2] - quartiles[0],
        "maximum": ordered[-1],
        "families_in_universe": len(ordered),
        "detections_total": sum(ordered),
    }


def _detector_rows(merged: MergedGroup) -> list[dict[str, Any]]:
    return [
        {
            "task": t.task,
            "detector": t.detector,
            "estimate_kind": t.estimate_kind,
            "searched_components": list(t.searched_components),
            "route_attribution": t.route_attribution,
            "manifest_sha256": t.manifest_sha256,
            "source": t.source,
        }
        for t in merged.tables
    ]


def _unsearched_document(merged: MergedGroup) -> dict[str, Any]:
    """The group's record when no detector read anything: no fraction, and why there is none."""
    key = merged.key
    return {
        "task": "A3.2",
        "policy_id": key.policy_id,
        "release": key.release,
        "registry": key.universe.registry,
        "registry_version": key.universe.version,
        "registry_restriction": key.universe.restriction,
        "universe": key.universe.key,
        "families_in_universe": key.universe.size,
        "estimate_kind": "not_searched",
        "detectors": _detector_rows(merged),
        "m1_families_with_a_hit": None,
        "m1_fraction": None,
        "m1_ci_low": None,
        "m1_ci_high": None,
        "m1_method": None,
        "m2": None,
        "routes": {},
        "composition": [],
        "reading_this_table": [
            "No detector searched any source in this manifest, so every count is zero by "
            "construction and none of it is evidence of absence (metrics/detections.md).",
            "M1 and M2 are withheld rather than reported as zero. A Wilson interval over "
            "zero detections prints as a filter that removed everything, which is the "
            "strongest claim in this audit, and nothing here supports it.",
            "What this group records is a gap in coverage, and closing it is a measurement "
            "someone has to buy, not a number to be derived.",
        ],
    }


@dataclasses.dataclass(frozen=True, slots=True)
class QuantifiedGroup:
    """M1 and M2 for one group, overall and per route."""

    key: GroupKey
    merged: MergedGroup
    document: Mapping[str, Any]


def quantify(
    merged: MergedGroup, *, seed: int, resamples: int = BOOTSTRAP_RESAMPLES
) -> QuantifiedGroup:
    """Compute M1 and M2 for one group, overall and restricted to each route.

    The per-route figures **do not sum to the overall figure** — a family can survive by more
    than one route — and every table this produces carries that sentence, because a reader who
    adds them gets a number that means nothing (metrics/survival.md §4).
    """
    key = merged.key
    universe = key.universe
    overall_counts = merged.zero_filled()
    survived = sum(1 for n in overall_counts if n >= 1)

    if merged.estimate_kind == "not_searched":
        # Every count in this group is zero *by construction*: no detector read anything.
        # A Wilson interval on that prints as 0.0000 [0.0000, 0.0007], which reads as a filter
        # that removed everything — the strongest possible claim, from no evidence at all.
        # `metrics/detections.md` is explicit that a not_searched table is not evidence of
        # absence, so the fraction is withheld here rather than qualified in a footnote.
        return QuantifiedGroup(key=key, merged=merged, document=_unsearched_document(merged))

    m1 = wilson_interval(survived, universe.size)

    routes: dict[str, Any] = {}
    for route, counts in merged.by_route.items():
        filled = merged.zero_filled(counts)
        hit = sum(1 for n in filled if n >= 1)
        iv = wilson_interval(hit, universe.size)
        routes[route] = {
            "m1_families_with_a_hit": hit,
            "m1_fraction": iv.estimate,
            "m1_ci_low": iv.low,
            "m1_ci_high": iv.high,
            "m1_method": iv.method,
            "m2": _distribution(filled, seed=seed, resamples=resamples),
            "element_kinds_detections": merged.route_by_kind.get(route, {}),
        }

    document = {
        "task": "A3.2",
        "policy_id": key.policy_id,
        "release": key.release,
        "registry": universe.registry,
        "registry_version": universe.version,
        "registry_restriction": universe.restriction,
        "universe": universe.key,
        "families_in_universe": universe.size,
        "estimate_kind": merged.estimate_kind,
        "detectors": _detector_rows(merged),
        "m1_families_with_a_hit": survived,
        "m1_fraction": m1.estimate,
        "m1_ci_low": m1.low,
        "m1_ci_high": m1.high,
        "m1_method": m1.method,
        "m2": _distribution(overall_counts, seed=seed, resamples=resamples),
        "routes": routes,
        "composition": [
            {"family_id": f, "records": n}
            for f, n in sorted(merged.counts.items(), key=lambda kv: (-kv[1], kv[0]))[:25]
        ],
        "reading_this_table": [
            "The per-route figures do not sum to the overall figure: a family can survive by "
            "more than one route, and a reader who adds them gets a number that means nothing.",
            "M2 is the distribution over the whole pinned universe, zero-filled, so a median of "
            "zero means most families carry no surviving homolog and is a result, not a gap.",
            f"estimate_kind is {merged.estimate_kind}: a lower_bound group was searched on a "
            "sample, so a family with no detection may still survive in the records not read.",
            "The survival fraction is not quotable without its registry: the universes answer "
            "different questions and are never pooled (D-022, D-161).",
        ],
    }
    return QuantifiedGroup(key=key, merged=merged, document=document)

"""How far apart the three readings of a published filter actually are — task A0.4, §A0.

A0.3 wrote each published filter policy three ways: literal, charitable, strict. A1.4 executed
them against the released corpora and A3.2 turned the survivors into the headline metrics. This
module asks the question that makes those three readings worth having: **does it matter which
one you pick?**

The answer is not a single number, because a reading can differ from its neighbour in four
places and only one of them moves a count:

1. **What it removes.** The exclusion sets, compared record by record. This is the question
   §A0 asks first and the only one where "the readings disagree" means the published policy is
   genuinely ambiguous about an outcome.
2. **What the metrics say.** M1 and M2 per registry and release, from A3.2's groups. A
   difference here is a difference a reader of the paper would see.
3. **What is in scope.** A reading that claims a wider corpus does not remove more; it
   reclassifies what it leaves behind, moving records from `out_of_scope` to
   `retained_by_design`. Same count, different account of why the record is still there.
4. **What the release leaves undecidable.** A rule can only disagree with its neighbour if the
   corpus carries the field it reads. Where it does not, two readings that say different things
   do the same thing, and the policy's ambiguity is invisible against the only corpus available
   for checking it.

The fourth is the one that needs saying out loud, because it is how a measurement of agreement
turns into a false reassurance. Readings that agree *because neither can act* have not been
shown to agree. `Verdict.reproducible` is therefore three-valued, and `undecidable_rules` is
reported next to every agreement so a reader can see which kind they have.

Nothing here recomputes a metric. It reads A1.4's manifests and A3.2's groups and compares
them, so a change to the metric definitions cannot be absorbed silently here.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "ComponentSpread",
    "MetricCell",
    "PairSpread",
    "PolicyManifest",
    "SpreadError",
    "Verdict",
    "component_spreads",
    "metric_cells",
    "pair_spreads",
    "verdict_for",
]


class SpreadError(RuntimeError):
    """A refusal: the spread cannot be measured as asked."""


#: What a manifest calls a component whose verdict is uniform over every record in it.
_UNIFORM = "uniform"
_PER_RECORD = "per-record"


@dataclasses.dataclass(frozen=True, slots=True)
class PolicyManifest:
    """One reading, executed against one release — A1.4's manifest, reduced to what A0.4 reads.

    `removed` is `None` when the manifest did not enumerate its removals, which is not the same
    as removing nothing: an empty frozenset is a measured zero and `None` is an unmeasured one.
    Conflating them would let a deferred arm read as perfect agreement.
    """

    policy_id: str
    model: str
    reading: str
    scope: tuple[str, ...]
    release: str
    records_enumerated: int
    removed: frozenset[str] | None
    component_verdicts: Mapping[str, str]
    undecidable: Mapping[str, frozenset[str]]

    @classmethod
    def from_document(
        cls, doc: Mapping[str, object], *, removed: Iterable[str] | None = None
    ) -> PolicyManifest:
        policy = doc.get("policy")
        if not isinstance(policy, Mapping):
            raise SpreadError("a manifest with no policy block")
        sources = doc.get("sources")
        if not isinstance(sources, Sequence):
            raise SpreadError(f"{policy.get('id')}: a manifest with no sources")

        verdicts: dict[str, str] = {}
        undecidable: dict[str, frozenset[str]] = {}
        for source in sources:
            if not isinstance(source, Mapping):  # pragma: no cover - defensive
                raise SpreadError("a source entry that is not a mapping")
            component = str(source.get("component") or source.get("corpus_component") or "?")
            outcome = source.get("uniform_outcome")
            verdicts[component] = str(outcome) if outcome else _PER_RECORD
            rules = source.get("rules_undecidable") or {}
            undecidable[component] = frozenset(rules) if isinstance(rules, Mapping) else frozenset()

        declared = doc.get("removed")
        enumerated = declared.get("records") if isinstance(declared, Mapping) else None
        ids = None if removed is None else frozenset(removed)
        if ids is not None and enumerated is not None and len(ids) != int(enumerated):
            raise SpreadError(
                f"{policy.get('id')}/{doc.get('release')}: the manifest declares "
                f"{enumerated} removed records and {len(ids)} were supplied; comparing "
                "exclusion sets across readings needs both sides complete"
            )
        return cls(
            policy_id=str(policy.get("id")),
            model=str(policy.get("model")),
            reading=str(policy.get("reading")),
            scope=tuple(str(s) for s in (policy.get("scope") or ())),
            release=str(doc.get("release")),
            records_enumerated=int(doc.get("records_enumerated") or 0),
            removed=ids,
            component_verdicts=verdicts,
            undecidable=undecidable,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class PairSpread:
    """Two readings' exclusion sets, compared on the same release."""

    release: str
    left: str
    right: str
    shared: int
    only_left: int
    only_right: int

    @property
    def symmetric_difference(self) -> int:
        return self.only_left + self.only_right

    @property
    def union(self) -> int:
        return self.shared + self.symmetric_difference

    @property
    def jaccard(self) -> float:
        """1.0 for two empty sets: they exclude the same thing, which is nothing."""
        return 1.0 if self.union == 0 else self.shared / self.union

    @property
    def identical(self) -> bool:
        return self.symmetric_difference == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "left": self.left,
            "right": self.right,
            "shared": self.shared,
            "only_left": self.only_left,
            "only_right": self.only_right,
            "symmetric_difference": self.symmetric_difference,
            "jaccard": self.jaccard,
            "identical": self.identical,
        }


def pair_spreads(manifests: Sequence[PolicyManifest]) -> list[PairSpread]:
    """Every pair of readings of the same model on the same release, compared record by record.

    A reading whose removals were never enumerated is left out of the pairing rather than
    treated as empty, and the caller is expected to report it as unmeasured.
    """
    out: list[PairSpread] = []
    keyed = [m for m in manifests if m.removed is not None]
    for (model, release), group in _grouped(keyed, lambda m: (m.model, m.release)).items():
        del model
        for left, right in itertools.combinations(sorted(group, key=lambda m: m.policy_id), 2):
            assert left.removed is not None and right.removed is not None
            out.append(
                PairSpread(
                    release=release,
                    left=left.policy_id,
                    right=right.policy_id,
                    shared=len(left.removed & right.removed),
                    only_left=len(left.removed - right.removed),
                    only_right=len(right.removed - left.removed),
                )
            )
    return out


@dataclasses.dataclass(frozen=True, slots=True)
class MetricCell:
    """One registry and release, with every reading's headline metrics side by side."""

    release: str
    universe: str
    m1: Mapping[str, float]
    m2: Mapping[str, Mapping[str, object]]
    routes: Mapping[str, tuple[str, ...]]

    @property
    def readings(self) -> tuple[str, ...]:
        return tuple(sorted(self.m1))

    @property
    def m1_span(self) -> float:
        return max(self.m1.values()) - min(self.m1.values()) if self.m1 else 0.0

    @property
    def m1_identical(self) -> bool:
        return len(set(self.m1.values())) <= 1

    @property
    def m2_identical(self) -> bool:
        return len({_canonical(v) for v in self.m2.values()}) <= 1

    @property
    def routes_identical(self) -> bool:
        return len(set(self.routes.values())) <= 1

    @property
    def route_names(self) -> dict[str, tuple[str, ...]]:
        """Which survival routes each reading used. Differs where scope differs."""
        return {pid: tuple(sorted(r)) for pid, r in self.routes.items()}

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "universe": self.universe,
            "readings": list(self.readings),
            "m1": dict(self.m1),
            "m1_span": self.m1_span,
            "m1_identical": self.m1_identical,
            "m2_identical": self.m2_identical,
            "routes": {k: list(v) for k, v in self.route_names.items()},
            "routes_identical": self.routes_identical,
        }


def metric_cells(groups: Iterable[Mapping[str, object]]) -> list[MetricCell]:
    """A3.2's groups, regrouped so the readings of one cell sit next to each other."""
    cells: dict[tuple[str, str], dict[str, object]] = {}
    for group in groups:
        key = (str(group.get("release")), str(group.get("universe")))
        slot = cells.setdefault(key, {"m1": {}, "m2": {}, "routes": {}})
        pid = str(group.get("policy_id"))
        fraction = group.get("m1_fraction")
        if fraction is None:
            continue  # not_searched: no metric to compare, and A3.2 says so in the group
        slot["m1"][pid] = float(fraction)  # type: ignore[index]
        slot["m2"][pid] = group.get("m2") or {}  # type: ignore[index]
        routes = group.get("routes") or {}
        slot["routes"][pid] = tuple(sorted(routes))  # type: ignore[index]
    return [
        MetricCell(
            release=release,
            universe=universe,
            m1=slot["m1"],  # type: ignore[arg-type]
            m2=slot["m2"],  # type: ignore[arg-type]
            routes=slot["routes"],  # type: ignore[arg-type]
        )
        for (release, universe), slot in sorted(cells.items())
        if slot["m1"]
    ]


@dataclasses.dataclass(frozen=True, slots=True)
class ComponentSpread:
    """One corpus component, with each reading's verdict on it and what it could not decide."""

    release: str
    component: str
    verdicts: Mapping[str, str]
    undecidable: Mapping[str, tuple[str, ...]]

    @property
    def verdict_differs(self) -> bool:
        return len(set(self.verdicts.values())) > 1

    @property
    def undecidable_differs(self) -> bool:
        return len(set(self.undecidable.values())) > 1

    @property
    def disputed_rules(self) -> tuple[str, ...]:
        """Rules at least one reading could not decide and at least one did not name.

        These are where the readings differ in what they *claim*, over a corpus that cannot
        tell them apart. Every one is an ambiguity the release is incapable of exposing.
        """
        sets = [set(r) for r in self.undecidable.values()]
        if not sets:
            return ()
        return tuple(sorted(set.union(*sets) - set.intersection(*sets)))

    def to_dict(self) -> dict[str, object]:
        return {
            "release": self.release,
            "component": self.component,
            "verdicts": dict(self.verdicts),
            "verdict_differs": self.verdict_differs,
            "undecidable": {k: list(v) for k, v in self.undecidable.items()},
            "undecidable_differs": self.undecidable_differs,
            "disputed_rules": list(self.disputed_rules),
        }


def component_spreads(manifests: Sequence[PolicyManifest]) -> list[ComponentSpread]:
    out: list[ComponentSpread] = []
    for (model, release), group in _grouped(manifests, lambda m: (m.model, m.release)).items():
        del model
        components = sorted({c for m in group for c in m.component_verdicts})
        for component in components:
            out.append(
                ComponentSpread(
                    release=release,
                    component=component,
                    verdicts={
                        m.policy_id: m.component_verdicts.get(component, "absent") for m in group
                    },
                    undecidable={
                        m.policy_id: tuple(sorted(m.undecidable.get(component, ()))) for m in group
                    },
                )
            )
    return out


@dataclasses.dataclass(frozen=True, slots=True)
class Verdict:
    """What can be said about one model's published policy, and no more than that."""

    model: str
    readings_compared: tuple[str, ...]
    readings_not_executed: Mapping[str, str]
    removals_identical: bool | None
    metrics_identical: bool | None
    scope_differs: bool
    rules_disputed_but_undecidable: tuple[str, ...]

    @property
    def reproducible(self) -> str:
        """Three-valued, because "the readings agree" has two very different causes.

        `not_measurable` — fewer than two readings were executed, so there is nothing to
        compare. `agree_on_the_corpus` — the readings remove the same records and report the
        same metrics, but at least one rule they word differently is one the release cannot
        decide, so the agreement is a property of the corpus as much as of the policy.
        `agree` — they agree and every rule that separates them was decidable.
        """
        if self.removals_identical is None or len(self.readings_compared) < 2:
            return "not_measurable"
        if not self.removals_identical or self.metrics_identical is False:
            return "readings_disagree"
        if self.rules_disputed_but_undecidable:
            return "agree_on_the_corpus"
        return "agree"

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "readings_compared": list(self.readings_compared),
            "readings_not_executed": dict(self.readings_not_executed),
            "removals_identical": self.removals_identical,
            "metrics_identical": self.metrics_identical,
            "scope_differs": self.scope_differs,
            "rules_disputed_but_undecidable": list(self.rules_disputed_but_undecidable),
            "reproducible": self.reproducible,
        }


def verdict_for(
    model: str,
    manifests: Sequence[PolicyManifest],
    cells: Sequence[MetricCell],
    components: Sequence[ComponentSpread],
    *,
    not_executed: Mapping[str, str] | None = None,
) -> Verdict:
    """Fold one model's measurements into the claim they support — and no stronger one."""
    mine = [m for m in manifests if m.model == model]
    if not mine:
        raise SpreadError(f"no manifest for {model!r}; its spread was not measured")
    releases = {m.release for m in mine}
    pairs = pair_spreads(mine)
    ids = {m.policy_id for m in mine}
    mine_cells = [c for c in cells if c.release in releases and set(c.m1) & ids]
    disputed = sorted(
        {r for c in components if c.release in releases for r in c.disputed_rules},
    )
    return Verdict(
        model=model,
        readings_compared=tuple(sorted(ids)),
        readings_not_executed=dict(not_executed or {}),
        removals_identical=(None if not pairs else all(p.identical for p in pairs)),
        metrics_identical=(
            None if not mine_cells else all(c.m1_identical and c.m2_identical for c in mine_cells)
        ),
        scope_differs=len({m.scope for m in mine}) > 1,
        rules_disputed_but_undecidable=tuple(disputed),
    )


def _grouped(items, key):  # type: ignore[no-untyped-def]
    out: dict[object, list] = {}
    for item in items:
        out.setdefault(key(item), []).append(item)
    return out


def _canonical(value: object) -> str:
    """A stable string for an M2 block, so two blocks can be compared without a JSON import."""
    if isinstance(value, Mapping):
        return "{" + ",".join(f"{k}:{_canonical(value[k])}" for k in sorted(value)) + "}"
    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    return repr(value)

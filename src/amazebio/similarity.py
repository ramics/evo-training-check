"""The instrument for A1.6's similarity pass: parameters, readings, and rates with intervals.

Everything here is logic that can be tested without an aligner and without spend, which is
why it lives in the library rather than in the tool that launches the pass. The tools call
it; `tests/test_similarity.py` pins it.

Three things it owns.

**The parameter sets, as fixed by D-105 and amended by D-107.** The aligner, sensitivity,
coverage, hit cap and banded reporting are all decided; this module is where those decisions
stop being prose. Sensitivity is swept rather than fixed (D-109) because `-s` is our
parameter rather than the publisher's, and the sweep is what separates a property of the
filter from a property of our instrument.

**The three coverage readings as post-filters over one search.** D-107 established that
`--cov-mode` is a three-way reading of ESM3's description rather than recovered guidance, and
D-109 bought all three for the price of one by relaxing coverage filtering in the search and
re-imposing it on the emitted `qcov`/`tcov` columns. That trade is measured, not assumed:
relaxing the filter admits more rows, so it costs more, and `tools/esm3_hitcap.py` is what
decides whether it costs less than running three searches.

**Rates with intervals that do not lie about their precision.** D-109 committed to a design
effect estimated from between-family variance rather than a binomial interval, because viral
material is clumped by family and the binomial error at this sample size is under 0.01% —
which would be a confident-looking number for the wrong quantity. `rate_with_interval` is a
cluster-sampling ratio estimator and it reports the design effect it found, so the gap between
the honest interval and the binomial one is visible rather than argued about.
"""

from __future__ import annotations

import bisect
import itertools
import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import IO, Any

from amazebio.seeds import bucket_of

#: The columns the pass asks `convertalis` for, in order. `fident` carries the identity the
#: threshold reading needs; `qcov` and `tcov` are what make the three coverage readings
#: recoverable from one search (D-109). Nothing else is emitted: at full corpus scale the hit
#: table is the largest artefact the pass produces, and every unused column is paid for once
#: per row.
CONVERTALIS_COLUMNS: tuple[str, ...] = ("query", "target", "fident", "qcov", "tcov")
CONVERTALIS_FORMAT = ",".join(CONVERTALIS_COLUMNS)

#: D-105 parameter 4: the coverage figure ESM3 states for its own clustering, which is the
#: only parameter guidance the source gives at all.
COVERAGE = 0.8

#: D-105 parameter 5. Not a tuned value — a cap high enough that the saturation guard, not the
#: number, is what protects the result. `Saturation` is the guard.
HIT_CAP = 100_000

#: D-109: the one axis that cannot be post-filtered, because D-105 measured that the settings
#: are not nested — `-s 7.5` finds records `-s 5.7` misses *and* loses records it finds. The
#: tool's default sits in the middle and is the one D-105 fixed; the other two bracket it.
SENSITIVITIES: tuple[float, ...] = (2.0, 5.7, 7.5)

#: The three readings of ESM3's coverage description (D-107), by the `--cov-mode` they
#: correspond to. Names are the paper's vocabulary, not MMseqs2's.
COVERAGE_READINGS: tuple[int, ...] = (0, 1, 2)

#: Which searches the pass actually runs, and which readings each one is authoritative for.
#:
#: Two aligner-filtered searches recover all three readings **exactly**, which D-109's relaxed
#: search plus post-filter did not. The argument is short enough to check: the `--cov-mode 1`
#: search returns every pair with `tcov >= c`, and mode 0 is `qcov >= c AND tcov >= c`, so
#: every mode-0 pair is in those results and is identified by the `qcov` column the search
#: already emits. Mode 1 is the result set itself. Mode 2 — `qcov >= c` with no constraint on
#: `tcov` — is not a subset of it, so it needs its own search.
#:
#: This replaces relaxing coverage for two reasons beyond exactness. Relaxing discards the
#: aligner's own pruning: under `-c 0.8 --cov-mode 1` a target cannot match a seed shorter
#: than 80% of it, and a relaxed search must align those pairs to discover the same thing.
#: And two cells beat the three-cell fallback D-109 named for the case where relaxing proved
#: too expensive.
SEARCH_READINGS: dict[int, tuple[int, ...]] = {1: (0, 1), 2: (2,)}

#: D-105 parameter 6. The lowest edge is the charitable reading's inferred 0.70 (D-015); the
#: 0.70-0.75 band is separated because 8.07% of hit rows fall in it and the records on which
#: two sensitivity settings disagree are 98% inside it. Rows below 0.70 are still emitted and
#: still counted — the literal reading's threshold is undetermined (D-107), so the pass may
#: not assume the charitable cut is the floor of interest.
IDENTITY_BAND_EDGES: tuple[float, ...] = (0.0, 0.70, 0.75, 0.80, 0.90, 1.0)

#: D-134's bands on the **seed** axis, as denominators of a hash sample: 1/100, 1/10, all.
#:
#: The pass samples seeds rather than slicing them because band counts are per corpus record.
#: They are additive across shards — the shards are a hash partition of the corpus sample, so
#: no record is in two — but **not** across query slices: a record matched by seeds in two
#: slices would be counted once per slice, and its band is a max over all seeds rather than a
#: sum. Sampling needs no such merge, and the thing it costs is stated rather than hidden, in
#: `lower_bound` below.
#:
#: Band 1's denominator of 100 reproduces the query set the cap measurement already ran, which
#: is what prices band 2 (D-134).
SEED_BANDS: tuple[int, ...] = (100, 10, 1)


def select_seeds(identifiers: Iterable[str], denominator: int) -> Iterator[str]:
    """The seeds in a 1/`denominator` hash sample, in input order.

    The same `bucket_of(ident, denominator) == 0` rule the cap measurement used, so a band at
    100 re-runs exactly that query set and the two are comparable. A denominator of 1 is the
    whole set and is not a sample.
    """
    if denominator < 1:
        raise ValueError(f"seed denominator must be at least 1, got {denominator!r}")
    for ident in identifiers:
        if denominator == 1 or bucket_of(ident, denominator) == 0:
            yield ident


def band_labels() -> tuple[str, ...]:
    """Human labels for the bands, in order, as they appear in the reported table."""
    edges = IDENTITY_BAND_EDGES
    return tuple(f"{lo:.2f}-{hi:.2f}" for lo, hi in itertools.pairwise(edges))


def band_of(fident: float) -> int:
    """Which identity band a row falls in, as an index into `band_labels()`.

    Bands are half-open on the right so a row sits in exactly one, with the top band closed
    so that an exact 1.0 identity — a seed matching itself through the corpus, which happens
    whenever the seed's cluster is also a corpus record — is counted rather than dropped.
    """
    edges = IDENTITY_BAND_EDGES
    if not edges[0] <= fident <= edges[-1]:
        raise ValueError(f"identity {fident!r} outside [{edges[0]}, {edges[-1]}]")
    index = bisect.bisect_right(edges, fident) - 1
    return min(index, len(edges) - 2)


def coverage_passes(mode: int, qcov: float, tcov: float, coverage: float = COVERAGE) -> bool:
    """Whether a row satisfies `-c coverage --cov-mode mode`, from the emitted columns.

    MMseqs2's modes, which is the mapping the post-filter stands or falls on: mode 0 requires
    coverage of query *and* target, mode 1 coverage of the target, mode 2 coverage of the
    query. `convertalis`'s `qcov` and `tcov` are those two coverages, so each mode is a
    predicate over the pair and all three come out of one relaxed search (D-109).
    """
    if mode == 0:
        return qcov >= coverage and tcov >= coverage
    if mode == 1:
        return tcov >= coverage
    if mode == 2:
        return qcov >= coverage
    raise ValueError(f"unknown --cov-mode {mode!r}")


def search_argv(
    *,
    sensitivity: float,
    cap: int = HIT_CAP,
    coverage_mode: int | None = None,
    coverage: float = COVERAGE,
    min_identity: float | None = None,
) -> tuple[str, ...]:
    """The flags for one `mmseqs search`, built from the decided parameters.

    `coverage_mode=None` is the relaxed search D-109 buys the three readings with: coverage
    filtering is left off in the aligner and re-imposed by `coverage_passes` afterwards.
    Passing a mode gives the un-relaxed search, which is the fallback if relaxing costs more
    than running the three modes separately.

    `min_identity` is deliberately not defaulted to the charitable 0.70. Banded reporting
    needs every row at and above the lowest edge of interest, and a search that pre-filters at
    0.70 cannot emit the bands below it — including the undetermined literal reading.
    """
    argv: list[str] = ["-s", f"{sensitivity:g}", "--max-seqs", str(cap)]
    if coverage_mode is not None:
        argv += ["-c", f"{coverage:g}", "--cov-mode", str(coverage_mode)]
    if min_identity is not None:
        argv += ["--min-seq-id", f"{min_identity:g}"]
    return tuple(argv)


@dataclass
class HitRow:
    """One `convertalis` row, in the columns `CONVERTALIS_FORMAT` asks for."""

    query: str
    target: str
    fident: float
    qcov: float
    tcov: float

    @classmethod
    def parse(cls, line: str) -> HitRow:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < len(CONVERTALIS_COLUMNS):
            raise ValueError(f"expected {len(CONVERTALIS_COLUMNS)} columns, got {len(parts)}")
        return cls(parts[0], parts[1], float(parts[2]), float(parts[3]), float(parts[4]))


def parse_hits(lines: Iterable[str]) -> Iterator[HitRow]:
    """Rows from a `convertalis` table, skipping blanks. Malformed rows are an error.

    Not tolerant on purpose: a truncated hit table is the failure that would quietly lower
    every rate this pass reports, and it looks exactly like a corpus with less leakage in it.
    """
    for line in lines:
        if line.strip():
            yield HitRow.parse(line)


@dataclass
class Saturation:
    """The guard D-105 chose instead of defending a hit-cap number across shard sizes.

    The cap truncates per seed, and it truncates worst for the corpus records that match the
    most seeds — the most viral-like ones, which is to say the ones the whole audit is about.
    So the pass records hits per seed on every shard and refuses to publish counts as a result
    if any seed reached the cap: the numbers are then a lower bound, not a measurement.
    """

    cap: int = HIT_CAP
    per_query: dict[str, int] = field(default_factory=dict)

    def observe(self, query: str) -> None:
        self.per_query[query] = self.per_query.get(query, 0) + 1

    @property
    def max_hits(self) -> int:
        return max(self.per_query.values(), default=0)

    @property
    def queries_at_cap(self) -> int:
        return sum(1 for n in self.per_query.values() if n >= self.cap)

    @property
    def saturated(self) -> bool:
        return self.queries_at_cap > 0

    def headroom(self) -> float | None:
        """Observed maximum as a fraction of the cap. 1.0 or above means it bound."""
        if self.cap <= 0:
            return None
        return self.max_hits / self.cap

    def to_dict(self) -> dict[str, object]:
        return {
            "cap": self.cap,
            "queries": len(self.per_query),
            "max_hits_per_query": self.max_hits,
            "queries_at_cap": self.queries_at_cap,
            "saturated": self.saturated,
            "headroom": self.headroom(),
        }


@dataclass
class RecordLedger:
    """Per corpus record, the best identity seen under each coverage reading.

    The unit of the reported rate is the corpus record, not the hit row: a record matching
    forty seeds is one surviving record, and counting rows would inflate every rate by the
    seed set's own redundancy. Keeping the best identity per record per reading is what lets
    one relaxed search produce the full banded table for all three readings.
    """

    coverage: float = COVERAGE
    best: dict[str, list[float]] = field(default_factory=dict)

    def observe(self, row: HitRow, derive: Iterable[int] = COVERAGE_READINGS) -> None:
        """Fold one row in, for the readings its search is authoritative for.

        `derive` matters and defaulting it to all three is only right for a search that was
        not coverage-filtered. A `--cov-mode 1` search cannot speak for reading 2: it omits
        pairs with `qcov >= c` but `tcov < c`, so counting reading 2 from its rows would
        produce a number that looks like a measurement and is a floor. `SEARCH_READINGS` is
        the mapping the pass feeds in, and the predicate is still applied on top, so a
        misrouted feed narrows the count rather than inflating it.
        """
        slot = self.best.get(row.target)
        if slot is None:
            slot = [-1.0] * len(COVERAGE_READINGS)
            self.best[row.target] = slot
        for mode in derive:
            i = COVERAGE_READINGS.index(mode)
            if coverage_passes(mode, row.qcov, row.tcov, self.coverage) and row.fident > slot[i]:
                slot[i] = row.fident

    def extend(
        self, rows: Iterable[HitRow], derive: Iterable[int] = COVERAGE_READINGS
    ) -> RecordLedger:
        derive = tuple(derive)
        for row in rows:
            self.observe(row, derive)
        return self

    def extend_from_search(self, rows: Iterable[HitRow], cov_mode: int) -> RecordLedger:
        """Fold in one coverage-filtered search's rows, under `SEARCH_READINGS`.

        The call site should name the search rather than the readings, so that which readings
        a search may speak for stays one decision in one place.
        """
        if cov_mode not in SEARCH_READINGS:
            raise ValueError(
                f"--cov-mode {cov_mode!r} is not one of the searches the pass runs "
                f"({sorted(SEARCH_READINGS)}); reading 0 comes from the mode-1 search"
            )
        return self.extend(rows, SEARCH_READINGS[cov_mode])

    def counts_by_band(self, mode: int) -> list[int]:
        """Records per identity band under one reading, as a list parallel to `band_labels()`."""
        out = [0] * (len(IDENTITY_BAND_EDGES) - 1)
        i = COVERAGE_READINGS.index(mode)
        for slot in self.best.values():
            if slot[i] >= 0:
                out[band_of(slot[i])] += 1
        return out

    def counts_at_or_above(self, mode: int, threshold: float) -> int:
        """Records whose best identity under one reading is at or above a threshold.

        The threshold sweep is free from here: one search, one ledger, every cut (D-109).
        """
        i = COVERAGE_READINGS.index(mode)
        return sum(1 for slot in self.best.values() if slot[i] >= threshold)

    def records(self, mode: int) -> set[str]:
        i = COVERAGE_READINGS.index(mode)
        return {rec for rec, slot in self.best.items() if slot[i] >= 0}


@dataclass
class TargetStream:
    """Per-reading band counts from rows **sorted by target**, in constant memory.

    `RecordLedger` holds one entry per corpus record that hit — measured at 172 bytes each,
    so 1.51 GB if 8.8M sampled records all hit. The reason to avoid it in the pass is not that
    figure, which is the pathological end: the ledger grows with the number of *hit* records,
    and the hit rate is precisely the quantity the pass exists to measure. **A pass whose
    memory requirement is a function of its own unknown result cannot be sized in advance**,
    and the failure mode is an out-of-memory kill hours into a run that has published nothing.
    Constant memory removes the question instead of guessing an answer.

    The trade is an external sort of the hit table by target, which is cheap on disk and
    bounded, against a data structure that is neither. Rows for one target then arrive
    contiguously, so the best identity per reading can be reduced as they stream past.

    **Order is verified, not trusted.** If the input is not sorted by target, a record's rows
    arrive in several runs and each run is counted separately — inflating every band count,
    silently, in the direction of more apparent leakage. Since remembering which targets have
    been seen is the memory this class exists to avoid, it instead requires the target key to
    be non-decreasing and raises when it is not.

    `RecordLedger` stays for the cap measurement, which needs set differences between runs and
    operates at a scale where holding them is free.
    """

    coverage: float = COVERAGE
    derive: tuple[int, ...] = COVERAGE_READINGS
    bands: dict[int, list[int]] = field(default_factory=dict)
    records: dict[int, int] = field(default_factory=dict)
    rows: int = 0
    #: The strata of the shard being searched. Given one, the stream also counts hit records
    #: per stratum, which is the numerator side of D-140's interval. This does **not**
    #: reintroduce the unbounded structure the class exists to avoid: `stratum_hits` is
    #: bounded by the number of strata in the target shard, which is known before the run
    #: from the shard itself, rather than by the hit rate, which is the unknown result.
    index: FamilyIndex | None = None
    stratum_hits: dict[int, dict[str, int]] = field(default_factory=dict)
    _target: str | None = None
    _best: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.derive = tuple(self.derive)
        for mode in self.derive:
            if mode not in COVERAGE_READINGS:
                raise ValueError(f"unknown coverage reading {mode!r}")
            self.bands.setdefault(mode, [0] * (len(IDENTITY_BAND_EDGES) - 1))
            self.records.setdefault(mode, 0)
            self.stratum_hits.setdefault(mode, {})

    @classmethod
    def for_search(cls, cov_mode: int, coverage: float = COVERAGE) -> TargetStream:
        """The readings one coverage-filtered search may speak for (D-124)."""
        if cov_mode not in SEARCH_READINGS:
            raise ValueError(
                f"--cov-mode {cov_mode!r} is not one of the searches the pass runs "
                f"({sorted(SEARCH_READINGS)})"
            )
        return cls(coverage=coverage, derive=SEARCH_READINGS[cov_mode])

    def observe(self, row: HitRow) -> None:
        if self._target is not None and row.target != self._target:
            if row.target < self._target:
                raise ValueError(
                    f"hit rows are not sorted by target: {row.target!r} follows "
                    f"{self._target!r}. Aggregating unsorted rows counts a record once per "
                    "run it appears in, which inflates every band count."
                )
            self._flush()
        if self._target is None or row.target != self._target:
            self._target = row.target
            self._best = [-1.0] * len(self.derive)
        self.rows += 1
        for i, mode in enumerate(self.derive):
            if (
                coverage_passes(mode, row.qcov, row.tcov, self.coverage)
                and row.fident > self._best[i]
            ):
                self._best[i] = row.fident

    def extend(self, rows: Iterable[HitRow]) -> TargetStream:
        for row in rows:
            self.observe(row)
        return self

    def _flush(self) -> None:
        target = self._target
        for i, mode in enumerate(self.derive):
            best = self._best[i]
            if best >= 0:
                self.bands[mode][band_of(best)] += 1
                self.records[mode] += 1
                if self.index is not None and target is not None:
                    key = self.index.of.get(target)
                    if key is None:
                        raise ValueError(
                            f"hit target {target!r} is not in the shard's strata; the hit "
                            "table and the target shard describe different records"
                        )
                    counts = self.stratum_hits[mode]
                    counts[key] = counts.get(key, 0) + 1
        self._target = None
        self._best = []

    def close(self) -> TargetStream:
        """Fold in the final target. Idempotent, so calling it twice cannot double-count."""
        if self._target is not None:
            self._flush()
        return self

    def counts_at_or_above(self, mode: int, threshold: float) -> int:
        """Records at or above a threshold, from the bands — exact only on a band edge.

        The identity sweep is free from banded counts (D-109) but only at the edges the bands
        were cut on, which is why `IDENTITY_BAND_EDGES` carries the charitable reading's 0.70
        and the 0.70-0.75 split. A threshold inside a band has no answer here and saying so is
        better than interpolating one.
        """
        edges = IDENTITY_BAND_EDGES
        if threshold not in edges:
            raise ValueError(
                f"threshold {threshold!r} is not a band edge {edges}; a count inside a band "
                "cannot be recovered from banded counts"
            )
        start = edges.index(threshold)
        return sum(self.bands[mode][start:])

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "bands": {str(m): self.bands[m] for m in self.derive},
            "records": {str(m): self.records[m] for m in self.derive},
            "band_labels": list(band_labels()),
        }


@dataclass(frozen=True)
class CellKey:
    """One unit of the pass: a shard, a sensitivity, a coverage-filtered search.

    The pass is incremental because this is the atom. A cell costs roughly $6-17, writes its own
    artefact, and is skipped if its artefact already exists — so the spend decision is taken
    once per cell rather than once for the whole arm, and "carry on" costs nothing already paid.
    """

    shard: int
    sensitivity: float
    cov_mode: int
    seed_denominator: int = 1

    def __post_init__(self) -> None:
        if self.seed_denominator < 1:
            raise ValueError(f"seed denominator must be at least 1, got {self.seed_denominator!r}")

    def slug(self) -> str:
        """A stable key for the cell's artefact. Must not change once results exist.

        The seed band is in the key, because the corpus bucket has no `DeleteObject` and two
        bands against the same shard would otherwise collide on a name — the second one
        silently reading as the first. A full-seed cell keeps D-128's original slug, so band 3
        is not renamed by this having been added.
        """
        base = f"shard{self.shard:02d}-s{self.sensitivity:g}-cov{self.cov_mode}"
        return base if self.seed_denominator == 1 else f"{base}-q{self.seed_denominator}"

    @property
    def readings(self) -> tuple[int, ...]:
        return SEARCH_READINGS[self.cov_mode]

    @property
    def lower_bound(self) -> bool:
        """Whether this cell's counts understate the truth, which a sampled seed set does.

        A corpus record is counted if **any** seed matches it, so dropping seeds can only drop
        records and can only lower a record's best identity. The understatement is monotone in
        the sample fraction and runs toward less apparent leakage, which §2 treats as the same
        class of failure as overstating it — hence a flag that travels with the number rather
        than a note in the write-up (D-134).
        """
        return self.seed_denominator > 1


@dataclass
class CellResult:
    """What one cell contributes to the aggregate, and nothing more.

    Band counts per reading, plus per-family `(hits, records)` pairs for the interval. Both are
    **additive across shards**, which is the property the whole incremental design rests on:
    the shards are a hash partition of the sample, so no corpus record appears in two of them
    and summing cannot double count. Summing across *sensitivities* would double count, and
    `combine` refuses it.
    """

    key: CellKey
    bands: dict[int, list[int]]
    families: dict[int, list[tuple[int, int]]]
    searched_clusters: int = 0
    searched_residues: int = 0
    #: The realised size of the seed sample, and the number of families it drew from. Both are
    #: properties of the *query* set, so they are identical across shards and **summing them
    #: would be meaningless** — `combine_cells` requires agreement instead. `seed_families` is
    #: load-bearing: D-134 makes it ship with every rate, because 1/100 of the seeds covers
    #: materially fewer families than the full set and that, not the record count, is what
    #: limits anything said at family level.
    seeds_searched: int = 0
    seed_families: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "shard": self.key.shard,
            "sensitivity": self.key.sensitivity,
            "cov_mode": self.key.cov_mode,
            "seed_denominator": self.key.seed_denominator,
            "lower_bound": self.key.lower_bound,
            "seeds_searched": self.seeds_searched,
            "seed_families": self.seed_families,
            "slug": self.key.slug(),
            "bands": {str(m): self.bands[m] for m in sorted(self.bands)},
            "families": {
                str(m): [list(p) for p in self.families[m]] for m in sorted(self.families)
            },
            "searched_clusters": self.searched_clusters,
            "searched_residues": self.searched_residues,
        }


def combine_cells(cells: Sequence[CellResult]) -> dict[str, Any]:
    """Aggregate completed cells into banded counts and rates, per sensitivity and reading.

    Grouped by `(sensitivity, reading)` and summed over shards only. The denominator is the
    clusters actually searched, never the corpus or the sample as designed: a run that has done
    three shards of eight must report a rate over three shards, or the number is a fiction about
    work not yet paid for.

    **Seed bands are not pooled.** Band counts from two seed samples cover overlapping seed
    sets, so adding them double counts every record both bands found; and a band's counts mean
    "at least this many, from this fraction of the seeds", which is not a quantity that
    survives addition. D-134 makes that a third no-pooling axis alongside D-108's two arms and
    D-109's two denominators, and this function refuses it rather than trusting a caller to
    remember.
    """
    denominators = {cell.key.seed_denominator for cell in cells}
    if len(denominators) > 1:
        raise ValueError(
            "cells span seed bands "
            + ", ".join(f"1/{d}" for d in sorted(denominators))
            + "; their counts cover overlapping seed sets, so summing them double counts "
            "every record both bands found. Combine each band on its own (D-134)."
        )
    seen: set[tuple[int, float, int]] = set()
    groups: dict[tuple[float, int], dict[str, Any]] = {}
    for cell in cells:
        for mode in cell.bands:
            token = (cell.key.shard, cell.key.sensitivity, mode)
            if token in seen:
                raise ValueError(
                    f"shard {cell.key.shard} already contributed reading {mode} at "
                    f"sensitivity {cell.key.sensitivity:g}; summing it twice would inflate "
                    "every count"
                )
            seen.add(token)
            slot = groups.setdefault(
                (cell.key.sensitivity, mode),
                {
                    "bands": [0] * (len(IDENTITY_BAND_EDGES) - 1),
                    "families": [],
                    "shards": [],
                    "searched_clusters": 0,
                    "searched_residues": 0,
                    "seeds_searched": cell.seeds_searched,
                    "seed_families": cell.seed_families,
                },
            )
            # The query set is the same on every shard, so these agree rather than add. A
            # disagreement means two cells ran against different seed sets and their record
            # counts are not summable at all, which is worth failing on.
            for name, value in (
                ("seeds_searched", cell.seeds_searched),
                ("seed_families", cell.seed_families),
            ):
                if slot[name] != value:
                    raise ValueError(
                        f"shard {cell.key.shard} reports {name}={value} against "
                        f"{slot[name]} from an earlier shard at the same sensitivity and "
                        "reading; the seed set must be identical across shards for their "
                        "record counts to be summable"
                    )
            slot["bands"] = [a + b for a, b in zip(slot["bands"], cell.bands[mode], strict=True)]
            slot["families"].extend(cell.families.get(mode, []))
            slot["shards"].append(cell.key.shard)
            slot["searched_clusters"] += cell.searched_clusters
            slot["searched_residues"] += cell.searched_residues

    denominator = denominators.pop() if denominators else 1
    out: dict[str, Any] = {
        "band_labels": list(band_labels()),
        "seed_denominator": denominator,
        "lower_bound": denominator > 1,
        "groups": [],
    }
    for (sensitivity, mode), slot in sorted(groups.items()):
        rate = rate_with_interval(slot["families"], lower_bound=denominator > 1)
        out["groups"].append(
            {
                "sensitivity": sensitivity,
                "reading": mode,
                "shards": sorted(slot["shards"]),
                "bands": slot["bands"],
                "records": sum(slot["bands"]),
                "searched_clusters": slot["searched_clusters"],
                "searched_residues": slot["searched_residues"],
                "seeds_searched": slot["seeds_searched"],
                "seed_families": slot["seed_families"],
                "rate": rate.to_dict(),
            }
        )
    return out


@dataclass(frozen=True)
class Rate:
    """A rate with the interval D-109 requires, and the evidence for its own precision."""

    rate: float | None
    standard_error: float | None
    low: float | None
    high: float | None
    design_effect: float | None
    families: int
    records: int
    hits: int
    #: True when the seed set was sampled, so the rate understates the truth. It sits on the
    #: estimate rather than beside it because the two qualifiers on this number are different
    #: in kind and a reader has to keep them apart: the interval is the **corpus** axis, a
    #: 0.3125% hash sample whose denominator is fully known, while this flag is the **seed**
    #: axis, which contributes a bound and no interval at all. Collapsing them into one figure
    #: would be false precision in the direction of understating leakage (D-134).
    lower_bound: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "rate": self.rate,
            "lower_bound": self.lower_bound,
            "standard_error": self.standard_error,
            "ci95": [self.low, self.high],
            "design_effect": self.design_effect,
            "families": self.families,
            "records": self.records,
            "hits": self.hits,
        }

    def describe(self) -> str:
        """The rate as a sentence, with "at least" in it when that is what it is.

        The non-negotiables require the reporting limits enforced in the harness rather than
        left to the write-up, and this is that for the bound: a figure formatted from here
        cannot lose the qualifier on its way into prose.
        """
        if self.rate is None:
            return "no records searched"
        lead = "at least " if self.lower_bound else ""
        body = f"{lead}{self.rate:.4%}"
        if self.low is not None and self.high is not None:
            body += f" (95% CI {self.low:.4%}-{self.high:.4%} from the corpus sample)"
        else:
            body += " (no interval: one family is not a sample of families)"
        return f"{body}, {self.families} families"


def rate_with_interval(
    clusters: Sequence[tuple[int, int]], z: float = 1.96, lower_bound: bool = False
) -> Rate:
    """A hit rate and its interval, treating families as the sampling unit.

    `clusters` is one `(hits, records)` pair per family drawn into the sample. The estimator
    is the standard ratio estimator for cluster sampling, with its between-family variance:

        r   = sum(a) / sum(b)
        var = k / ((k - 1) * sum(b)^2) * sum((a_i - r * b_i)^2)

    which reduces to the binomial variance only when hits are spread evenly across families.
    They are not — viral material is clumped by family, which is the whole reason D-104 raised
    this as an objection to sampling at all — so the ratio of the two is reported as
    `design_effect`. A design effect of 40 means the honest interval is six times the binomial
    one, and quoting the binomial would have understated the uncertainty by that factor.

    `families` travels with every rate because it, not the record count, is the effective
    sample size for anything said at family level.


    `lower_bound` marks the estimate as understating the truth, which it does whenever the
    seed set was sampled. It is a property of the query set rather than of this arithmetic,
    so it is passed in rather than inferred.
    """
    k = len(clusters)
    total_hits = sum(a for a, _ in clusters)
    total_records = sum(b for _, b in clusters)
    if total_records == 0:
        return Rate(None, None, None, None, None, k, 0, total_hits, lower_bound)

    r = total_hits / total_records
    if k < 2:
        # One family is not a sample of families. A point estimate with no interval is the
        # honest output, and it is what makes the realised family count load-bearing.
        return Rate(r, None, None, None, None, k, total_records, total_hits, lower_bound)

    residual = sum((a - r * b) ** 2 for a, b in clusters)
    var = k * residual / ((k - 1) * total_records**2)
    se = math.sqrt(var)
    binomial_var = r * (1 - r) / total_records
    deff = var / binomial_var if binomial_var > 0 else None
    return Rate(
        rate=r,
        standard_error=se,
        low=max(0.0, r - z * se),
        high=min(1.0, r + z * se),
        design_effect=deff,
        families=k,
        records=total_records,
        hits=total_hits,
        lower_bound=lower_bound,
    )


#: How a stratum id is spelled. Placed clusters share their family's id; an unplaced cluster is
#: its own stratum (D-140, for the reason D-141 establishes), so its id carries the cluster.
#: Two prefixes rather than a bare int because the two kinds must never collide in a dict, and
#: a reader of a published stratum count needs to see which kind they are looking at.
PLACED_PREFIX = "f:"
UNPLACED_PREFIX = "u:"


def stratum_id(cluster_id: str, family: int | None) -> str:
    """The stratum a corpus record belongs to, for the interval's sampling unit."""
    return f"{PLACED_PREFIX}{family}" if family is not None else f"{UNPLACED_PREFIX}{cluster_id}"


@dataclass
class FamilyIndex:
    """Which stratum each searched corpus record is in, and how many records each holds.

    The interval needs one `(hits, records)` pair per stratum, and `records` counts every
    record **searched** in that stratum rather than every record that hit — so it cannot come
    from the hit table, which only ever shows the hits. It comes from the target shard, which
    is the only place the misses appear at all.

    `totals` is therefore the denominator side of the ratio estimator and `of` is what turns a
    hit row's target into the stratum it contributes to.
    """

    of: dict[str, str] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)

    @classmethod
    def build(
        cls, entries: Iterable[tuple[str, int | None]], taxonomy: Any, rank: str = "family"
    ) -> FamilyIndex:
        """Index a shard from its `(cluster_id, taxid)` pairs.

        `taxonomy` is an `amazebio.seeds.Taxonomy`; it is typed loosely to keep this module
        importable without one, which is what lets the tests run the estimator on synthetic
        strata. A cluster with no taxid is unplaced, the same as one whose lineage carries no
        node at `rank` — in both cases the taxonomy does not assert a family for it, which is
        the only thing the distinction would be used for.
        """
        index = cls()
        for cluster_id, taxid in entries:
            family = None if taxid is None else taxonomy.ancestor_at_rank(taxid, rank)
            key = stratum_id(cluster_id, family)
            if index.of.setdefault(cluster_id, key) != key:
                raise ValueError(
                    f"{cluster_id!r} appears twice in the shard with different families; a "
                    "record in two strata would be counted twice in the denominator"
                )
            index.totals[key] = index.totals.get(key, 0) + 1
        return index

    @property
    def unplaced_records(self) -> int:
        return sum(n for k, n in self.totals.items() if k.startswith(UNPLACED_PREFIX))

    @property
    def searched_records(self) -> int:
        return sum(self.totals.values())

    def pairs(self, hits: dict[str, int]) -> list[tuple[int, int]]:
        """One `(hits, records)` pair per stratum, for `rate_with_interval`.

        Every searched stratum is included, **including those with no hits**: a family that
        was searched and matched nothing is evidence about the rate, and dropping it would
        divide by a denominator the search did not use. That is the same error as reporting a
        rate over the sample as designed rather than the shards actually run.
        """
        unknown = set(hits) - set(self.totals)
        if unknown:
            raise ValueError(
                f"{len(unknown)} strata have hits but were never searched, e.g. "
                f"{sorted(unknown)[0]!r}; the hit table and the target shard disagree"
            )
        out = []
        for key, records in self.totals.items():
            got = hits.get(key, 0)
            if got > records:
                raise ValueError(
                    f"stratum {key!r} has {got} hit records against {records} searched; a "
                    "record counted more than once inflates the rate"
                )
            out.append((got, records))
        return out


def cell_from_stream(
    key: CellKey,
    stream: TargetStream,
    index: FamilyIndex,
    *,
    seeds_searched: int,
    seed_families: int,
    searched_residues: int,
) -> CellResult:
    """Assemble one cell's artefact from the search it just read.

    `searched_clusters` is taken from the index rather than passed in, because the denominator
    has to be the records the search actually ran against and the index is the only thing that
    counted them. Passing it separately is how a rate ends up quoted over the sample as
    designed instead of the shard that ran.
    """
    if tuple(stream.derive) != key.readings:
        raise ValueError(
            f"the search read readings {tuple(stream.derive)} but cell {key.slug()} speaks "
            f"for {key.readings}; a cell must not report a reading its search cannot support"
        )
    return CellResult(
        key=key,
        bands={mode: list(stream.bands[mode]) for mode in stream.derive},
        families={mode: index.pairs(stream.stratum_hits[mode]) for mode in stream.derive},
        searched_clusters=index.searched_records,
        searched_residues=searched_residues,
        seeds_searched=seeds_searched,
        seed_families=seed_families,
    )


#: What an unplaced cluster's taxid field holds in the sidecar. A cluster whose representative
#: carries no taxid is written explicitly rather than omitted: an absent row and a row saying
#: "no taxid" are different claims, and only one of them survives a truncated file.
NO_TAXID = "-"


def write_taxid_row(handle: IO[bytes], cluster_id: str, taxid: int | None) -> None:
    """Append one `cluster_id\\ttaxid` row to a shard's strata sidecar."""
    value = NO_TAXID if taxid is None else str(taxid)
    handle.write(f"{cluster_id}\t{value}\n".encode("ascii"))


def parse_taxid_rows(lines: Iterable[str | bytes]) -> Iterator[tuple[str, int | None]]:
    """Read a strata sidecar back as `(cluster_id, taxid)` pairs.

    A malformed row raises rather than being skipped. The sidecar is the denominator of every
    rate this arm publishes, so a row quietly dropped is a record quietly removed from the
    denominator, which moves the rate up.
    """
    for number, raw in enumerate(lines, start=1):
        line = raw.decode("ascii", "replace") if isinstance(raw, bytes) else raw
        line = line.rstrip("\n")
        if not line:
            continue
        cluster_id, _, value = line.partition("\t")
        if not cluster_id or not value:
            raise ValueError(f"strata sidecar line {number} is not a cluster/taxid pair: {line!r}")
        if value == NO_TAXID:
            yield cluster_id, None
            continue
        try:
            yield cluster_id, int(value)
        except ValueError as exc:
            raise ValueError(
                f"strata sidecar line {number} has a non-numeric taxid: {value!r}"
            ) from exc

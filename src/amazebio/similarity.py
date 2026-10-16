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

    def to_dict(self) -> dict[str, object]:
        return {
            "rate": self.rate,
            "standard_error": self.standard_error,
            "ci95": [self.low, self.high],
            "design_effect": self.design_effect,
            "families": self.families,
            "records": self.records,
            "hits": self.hits,
        }


def rate_with_interval(clusters: Sequence[tuple[int, int]], z: float = 1.96) -> Rate:
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
    """
    k = len(clusters)
    total_hits = sum(a for a, _ in clusters)
    total_records = sum(b for _, b in clusters)
    if total_records == 0:
        return Rate(None, None, None, None, None, k, 0, total_hits)

    r = total_hits / total_records
    if k < 2:
        # One family is not a sample of families. A point estimate with no interval is the
        # honest output, and it is what makes the realised family count load-bearing.
        return Rate(r, None, None, None, None, k, total_records, total_hits)

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
    )

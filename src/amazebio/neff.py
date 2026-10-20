"""Alignment depth: Neff, under the definition D-231 pins.

Neff is the sum of sequence weights over an alignment, where a sequence's weight is the
reciprocal of how many sequences sit at or above an identity threshold to it, itself included.
A sequence with no neighbours weighs 1; a group of k identical sequences weighs 1 between them.
The identity is over the alignment's match columns, with a gap counting as a mismatch and the
denominator the full column count, so a pair of short fragments does not look identical.

The arithmetic is simple and the cost is not: the sum is over every pair, and the alignments
behind this project's assays run to 820,000 sequences. Three paths carry it, and which one ran
travels with the number rather than being an implementation detail:

* **duplicates** — when the threshold is tight enough that only an exact match counts as a
  neighbour, every group of identical rows contributes exactly 1 and Neff is the number of
  distinct rows. Hashing, no pairs.
* **exact** — identical rows are collapsed and carried as multiplicities, and the deduplicated
  rows are compared against each other. Exact, and affordable when the deduplicated alignment
  is small, or when the threshold is tight enough that the pigeonhole principle finds the
  candidate pairs without comparing everything to everything.
* **sampled** — rows are drawn and each is compared against the whole alignment. The mean
  reciprocal neighbour count times the alignment's size is an unbiased estimator of the same
  sum, and it comes back with a bootstrap interval, never as a bare point estimate.
"""

from __future__ import annotations

import collections
import itertools
import math
import string
from dataclasses import dataclass, field

import numpy as np

#: Element comparisons a deduplicated self-comparison may cost before the sampled path takes
#: over. Set from what this project's container does in about a minute per alignment; it moves
#: an alignment between two paths that compute the same quantity, so it is a performance knob
#: and not a parameter of the statistic.
EXACT_BUDGET = 2.0e10

#: Rows drawn for the sampled path. Large enough that the interval on these alignments is a
#: couple of percent wide, small enough that the pass is a minute rather than an hour.
SAMPLE_ROWS = 4000

#: Resamples behind the reported interval.
BOOTSTRAP = 2000

#: Rows of the alignment held against the query block at once. Bounds the working set; it
#: changes nothing about the result.
DB_BLOCK = 20_000

#: Element comparisons the block-narrowed sum over every row may cost before the sampled path
#: takes over. Measured against this container: the deepest alignment that fits runs a few
#: minutes. Like `EXACT_BUDGET` this moves an alignment between two routes to the same number,
#: and is not a parameter of the statistic.
VERIFY_BUDGET = 4.0e10


#: The characters a2m uses for an insertion, which are not part of any column.
_INSERTIONS = str.maketrans("", "", string.ascii_lowercase + ".")


class DepthError(RuntimeError):
    """The depth of an alignment could not be computed as specified."""


@dataclass(frozen=True)
class Depth:
    """One alignment's depth, and how it was arrived at."""

    sequences: int
    columns: int
    distinct_rows: int
    threshold: float
    inclusive: bool
    floor: int
    method: str
    neff: float
    interval: tuple[float, float] | None = None
    sample: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def neff_per_column(self) -> float:
        return self.neff / self.columns

    def as_dict(self) -> dict:
        return {
            "sequences": self.sequences,
            "columns": self.columns,
            "distinct_rows": self.distinct_rows,
            "threshold": self.threshold,
            "boundary": "inclusive" if self.inclusive else "strict",
            "neighbour_floor_columns": self.floor,
            "method": self.method,
            "neff": round(self.neff, 3),
            "neff_per_column": round(self.neff_per_column, 5),
            "interval": None if self.interval is None else [round(v, 3) for v in self.interval],
            "sampled_rows": self.sample,
            "notes": list(self.notes),
        }


def match_columns(sequence: str) -> str:
    """The match columns of one a2m row: insertions dropped, so every row has the same length.

    a2m writes an insertion as a lowercase residue or a `.`, and those columns exist only for
    the rows that have them. Comparing rows on them would compare different positions.

    Done by translation table rather than by a comprehension because it runs over every
    character of every row of alignments with hundreds of thousands of them, where the
    per-character Python call is most of the wall clock.
    """
    return sequence.translate(_INSERTIONS)


def neighbour_floor(columns: int, threshold: float, *, inclusive: bool) -> int:
    """How many columns two rows must match on to count as neighbours.

    Identity is matches / columns, so the floor is the smallest integer meeting the threshold.
    The two readings of the boundary differ only where the threshold lands exactly on an
    integer, which is why D-231 asks for both rather than choosing.
    """
    if columns <= 0:
        raise DepthError("an alignment with no match columns has no identity to measure")
    if not 0.0 < threshold <= 1.0:
        raise DepthError(f"an identity threshold of {threshold} is not a fraction above zero")
    exact = threshold * columns
    if inclusive:
        return min(columns, math.ceil(exact - 1e-9))
    floor = math.floor(exact + 1e-9) + 1
    return min(columns, floor)


def encode(rows: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Collapse identical rows, returning the distinct rows as codes and their multiplicities.

    Collapsing is exact rather than an approximation: identical rows have identical neighbour
    sets, so each group's contribution is its size over its neighbour count.
    """
    if not rows:
        raise DepthError("an empty alignment has no depth")
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise DepthError("the rows are not all the same length; they are not one alignment")
    counts = collections.Counter(rows)
    distinct = sorted(counts)
    codes = np.frombuffer("".join(distinct).encode("ascii"), dtype=np.uint8).reshape(
        len(distinct), width
    )
    return codes, np.array([counts[r] for r in distinct], dtype=np.int64)


def _neighbours(
    queries: np.ndarray, codes: np.ndarray, multiplicity: np.ndarray, floor: int
) -> np.ndarray:
    """For each query row, how many alignment sequences are neighbours of it.

    Counted against the alignment rather than against the distinct rows, so the reciprocal is
    the weight D-231 defines. The column loop keeps the working set to one query block by one
    database block; the alternative, a one-hot product, is faster and does not fit.
    """
    total = np.zeros(len(queries), dtype=np.int64)
    for start in range(0, len(codes), DB_BLOCK):
        block = codes[start : start + DB_BLOCK]
        matches = np.zeros((len(queries), len(block)), dtype=np.int16)
        for column in range(codes.shape[1]):
            matches += queries[:, column, None] == block[None, :, column]
        total += ((matches >= floor) * multiplicity[start : start + DB_BLOCK]).sum(axis=1)
    return total


class Blocks:
    """The alignment cut into column blocks, with its rows bucketed by each block's content.

    Two rows within `columns - floor` mismatches must match exactly on at least one whole
    block when the alignment is cut into that many plus one of them: there are more blocks
    than mismatches to go round. So a row's possible neighbours are the rows it shares a
    bucket with somewhere, and at the thresholds these alignments were reweighted at that is a
    small fraction of the alignment rather than all of it.

    The same structure serves both of the paths that need it. Asking it for every row's
    candidates gives the exact sum; asking it for a sample's gives an unbiased estimate of the
    same sum at a fraction of the cost, and the per-row answer is exact either way.
    """

    def __init__(self, codes: np.ndarray, floor: int) -> None:
        self.codes = codes
        self.floor = floor
        self.rows, self.columns = codes.shape
        count = self.columns - floor + 1
        self.usable = count <= self.columns
        self.blocks: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        if not self.usable:
            return
        edges = np.linspace(0, self.columns, count + 1).astype(int)
        for start, stop in itertools.pairwise(edges):
            if stop <= start:
                self.usable = False
                self.blocks = []
                return
            block = np.ascontiguousarray(codes[:, start:stop])
            _, inverse, sizes = np.unique(
                block.view([("", block.dtype)] * block.shape[1]).ravel(),
                return_inverse=True,
                return_counts=True,
            )
            order = np.argsort(inverse, kind="stable").astype(np.int32)
            ends = np.cumsum(sizes)
            self.blocks.append((inverse.astype(np.int32), order, ends - sizes, ends))

    def upper_bound_on_pairs(self) -> float:
        """How many candidate pairs the blocks hold, counted before any are built."""
        total = 0.0
        for _, _, starts, ends in self.blocks:
            sizes = (ends - starts).astype(np.float64)
            total += float((sizes * (sizes - 1) / 2).sum())
        return total

    def candidates(self, row: int) -> np.ndarray:
        """Every row that could be a neighbour of `row`, itself included."""
        found = [
            order[starts[inverse[row]] : ends[inverse[row]]]
            for inverse, order, starts, ends in self.blocks
        ]
        return np.unique(np.concatenate(found))


def _counts_by_blocks(
    codes: np.ndarray,
    multiplicity: np.ndarray,
    floor: int,
    queries: np.ndarray,
    blocks: Blocks,
) -> np.ndarray:
    """Neighbour counts for `queries`, exact, using the blocks to skip the hopeless pairs."""
    counts = np.zeros(len(queries), dtype=np.int64)
    for position, row in enumerate(queries):
        candidates = blocks.candidates(int(row))
        matches = (codes[candidates] == codes[row]).sum(axis=1)
        counts[position] = int(multiplicity[candidates[matches >= floor]].sum())
    return counts


def _bootstrap(
    weights: np.ndarray, sequences: int, rng: np.random.Generator, resamples: int
) -> tuple[float, float]:
    draws = rng.integers(0, len(weights), size=(resamples, len(weights)))
    means = weights[draws].mean(axis=1) * sequences
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def depth(
    rows: list[str],
    threshold: float,
    *,
    inclusive: bool = True,
    seed: int,
    budget: float = EXACT_BUDGET,
    verify_budget: float = VERIFY_BUDGET,
    sample_rows: int = SAMPLE_ROWS,
    resamples: int = BOOTSTRAP,
) -> Depth:
    """The depth of one alignment, by whichever of the three paths its size allows."""
    codes, multiplicity = encode(rows)
    distinct, columns = codes.shape
    sequences = int(multiplicity.sum())
    floor = neighbour_floor(columns, threshold, inclusive=inclusive)
    common = {
        "sequences": sequences,
        "columns": columns,
        "distinct_rows": distinct,
        "threshold": threshold,
        "inclusive": inclusive,
        "floor": floor,
    }

    if floor >= columns:
        return Depth(
            **common,
            method="duplicates",
            neff=float(distinct),
            notes=[
                "at this threshold only an identical row is a neighbour, so each group of "
                "identical rows weighs 1 and the sum is the number of distinct rows"
            ],
        )

    if distinct * distinct * columns <= budget:
        counts = _neighbours(codes, codes, multiplicity, floor)
        if (counts <= 0).any():
            raise DepthError("a row is not its own neighbour; the comparison is wrong")
        return Depth(**common, method="exact", neff=float((multiplicity / counts).sum()))

    blocks = Blocks(codes, floor)
    if blocks.usable and blocks.upper_bound_on_pairs() * columns <= verify_budget:
        counts = _counts_by_blocks(codes, multiplicity, floor, np.arange(distinct), blocks)
        if (counts <= 0).any():
            raise DepthError("a row is not its own neighbour; the comparison is wrong")
        return Depth(
            **common,
            method="exact",
            neff=float((multiplicity / counts).sum()),
            notes=[
                "too deep to compare against itself, but the threshold is tight enough that "
                "the pigeonhole principle narrows each row's possible neighbours to the rows "
                "it matches a whole column block with"
            ],
        )

    rng = np.random.default_rng(seed)
    draw = min(sample_rows, sequences)
    # Sampled from the alignment, not from the distinct rows: the estimator is the mean weight
    # of a sequence, and a sequence in a large identical group must be as likely to be drawn as
    # a singleton or the mean is of the wrong population.
    picks = rng.choice(distinct, size=draw, replace=True, p=multiplicity / sequences)
    if blocks.usable:
        counts = _counts_by_blocks(codes, multiplicity, floor, picks, blocks)
        how = "each row's neighbours found exactly through the column blocks"
    else:
        counts = _neighbours(codes[picks], codes, multiplicity, floor)
        how = "each row compared against the whole alignment"
    if (counts <= 0).any():
        raise DepthError("a sampled row is not its own neighbour; the comparison is wrong")
    weights = 1.0 / counts
    return Depth(
        **common,
        method="sampled",
        neff=float(weights.mean() * sequences),
        interval=_bootstrap(weights, sequences, rng, resamples),
        sample=draw,
        notes=[
            "too deep to sum over every row within the budget, so the sum is estimated from "
            f"sampled rows, {how}"
        ],
    )

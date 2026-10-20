"""Check our zero-shot scores against the benchmark's own published ones — task B1.2, §B1.

B1.2's last step is "validate against a published reference number per model where one
exists". ProteinGym publishes two things that make that possible without re-running anybody
else's model: the per-variant zero-shot scores for each model it evaluated, and the DMS-level
Spearman it computed from them. So the check has two levels, and they fail differently:

**Variant level.** Our scores against the published scores for the same checkpoint on the same
assay. This is the sharp test — two implementations of the same frozen model scoring the same
variants should agree very closely, and a Spearman of 0.9 here means something is wrong with
the harness, not with the model.

**Assay level.** Our Spearman against the DMS truth, next to the published Spearman for that
model and assay. This is the number a reader recognises, and it is the looser test: it can
agree while the variant-level correlation is poor, because rank correlation against a noisy
assay is forgiving of a systematic error that the variant-level comparison exposes at once.

Both are reported, always, and `ReferenceCheck.verdict` is decided on the variant level. A
harness that reproduced the headline Spearman while disagreeing per variant would otherwise
read as validated.

**Intervals.** Every Spearman here carries a bootstrap interval over the variants, because the
assays are small — a few thousand variants at best, a few hundred at worst — and a difference
of 0.02 between our Spearman and the published one means nothing at all without knowing how
wide either is. The resampling is paired: the same resampled variant set scores both sides, so
the interval is on the *difference* as well as on each estimate, which is the quantity the
verdict actually rests on.

This module imports nothing that loads a model. It compares numbers.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from amazebio.proteingym import spearman
from amazebio.survival import Interval

__all__ = [
    "AGREEMENT_FLOOR",
    "BOOTSTRAP_RESAMPLES",
    "ReferenceCheck",
    "ReferenceError",
    "check_against_published",
    "paired_spearman_interval",
]


class ReferenceError(RuntimeError):
    """A refusal: the comparison would not mean what it appears to."""


#: Below this, two implementations of the same frozen checkpoint on the same variants are not
#: the same computation. It is deliberately high and deliberately not tuned to a result: the
#: point of the check is to catch a harness bug — a wrong offset, a mis-set mask token, a
#: dropped prefix — and every one of those lands far below this, while an honest difference in
#: numerical precision lands far above it. D-208 records the choice; it is fixed before any
#: score exists, as the non-negotiable on thresholds requires.
AGREEMENT_FLOOR = 0.99

#: Matches `quantify.BOOTSTRAP_RESAMPLES`, so an interval here reads on the same scale as one
#: in the survival tables.
BOOTSTRAP_RESAMPLES = 10_000

#: Fewer variants than this and a rank correlation is not worth an interval, let alone a
#: verdict. ProteinGym's smallest substitution assays are in the low hundreds.
MIN_VARIANTS = 20


@dataclasses.dataclass(frozen=True, slots=True)
class ReferenceCheck:
    """One checkpoint on one assay: ours, theirs, and the truth, with intervals."""

    checkpoint: str
    assay: str
    variants_compared: int
    variants_ours_only: int
    variants_published_only: int
    ours_vs_published: Interval
    ours_vs_truth: Interval
    published_vs_truth: Interval
    difference_vs_truth: Interval
    published_assay_spearman: float | None

    @property
    def verdict(self) -> str:
        """`reproduced`, `diverges`, or `too_few_variants`.

        Decided on the variant-level agreement and on its interval, not on the point
        estimate: a check whose interval straddles the floor has not established either
        answer, and saying so is the honest output.
        """
        if self.variants_compared < MIN_VARIANTS:
            return "too_few_variants"
        if self.ours_vs_published.low >= AGREEMENT_FLOOR:
            return "reproduced"
        if self.ours_vs_published.high < AGREEMENT_FLOOR:
            return "diverges"
        return "undetermined"

    @property
    def assay_level_gap(self) -> float | None:
        """Our Spearman against the truth, minus the one the benchmark published.

        `None` when the benchmark publishes no number for this checkpoint and assay, which is
        common: the published score archive covers more models than the summary table does.
        """
        if self.published_assay_spearman is None:
            return None
        return self.ours_vs_truth.estimate - self.published_assay_spearman

    def to_dict(self) -> dict[str, object]:
        def interval(value: Interval) -> dict[str, object]:
            return {
                "estimate": value.estimate,
                "low": value.low,
                "high": value.high,
                "method": value.method,
            }

        return {
            "checkpoint": self.checkpoint,
            "assay": self.assay,
            "variants_compared": self.variants_compared,
            "variants_ours_only": self.variants_ours_only,
            "variants_published_only": self.variants_published_only,
            "ours_vs_published": interval(self.ours_vs_published),
            "ours_vs_truth": interval(self.ours_vs_truth),
            "published_vs_truth": interval(self.published_vs_truth),
            "difference_vs_truth": interval(self.difference_vs_truth),
            "published_assay_spearman": self.published_assay_spearman,
            "assay_level_gap": self.assay_level_gap,
            "agreement_floor": AGREEMENT_FLOOR,
            "verdict": self.verdict,
        }


def paired_spearman_interval(
    x: Sequence[float],
    y: Sequence[float],
    *,
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> Interval:
    """95% bootstrap percentile interval on Spearman, resampling variant pairs together.

    Pairs, not values: a resample that drew the two sides independently would destroy the
    correlation it is meant to measure. Ranks are recomputed inside each resample, because a
    rank is a property of the sample and carrying the full sample's ranks into a resample
    would understate the spread.
    """
    if len(x) != len(y):
        raise ReferenceError(f"paired resampling needs equal lengths, got {len(x)} and {len(y)}")
    point = spearman(x, y)
    if len(x) < MIN_VARIANTS:
        return Interval(point, float("nan"), float("nan"), "too_few_variants")

    import numpy as np

    rng = np.random.default_rng(seed)
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    n = xs.size
    draws = rng.integers(0, n, size=(resamples, n))
    values = np.empty(resamples, dtype=np.float64)
    for i in range(resamples):
        idx = draws[i]
        values[i] = _fast_spearman(xs[idx], ys[idx])
    finite = values[np.isfinite(values)]
    if finite.size == 0:  # pragma: no cover - every resample degenerate
        return Interval(point, float("nan"), float("nan"), "degenerate")
    low, high = (float(v) for v in np.percentile(finite, [2.5, 97.5]))
    return Interval(point, low, high, f"bootstrap_percentile_p{resamples}_seed{seed}")


def _fast_spearman(x, y):  # type: ignore[no-untyped-def]
    """Spearman on arrays, average ranks for ties — the same definition as `proteingym`."""
    import numpy as np

    rx, ry = _rank(np.asarray(x)), _rank(np.asarray(y))
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denominator = float(np.sqrt((rx * rx).sum() * (ry * ry).sum()))
    return float((rx * ry).sum() / denominator) if denominator else float("nan")


def _rank(values):  # type: ignore[no-untyped-def]
    import numpy as np

    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = np.arange(1, values.size + 1, dtype=np.float64)
    # Average the ranks within each tied run, which argsort has made contiguous.
    sorted_values = values[order]
    start = 0
    for end in range(1, values.size + 1):
        if end == values.size or sorted_values[end] != sorted_values[start]:
            if end - start > 1:
                ranks[order[start:end]] = ranks[order[start:end]].mean()
            start = end
    return ranks


def check_against_published(
    checkpoint: str,
    assay: str,
    ours: Mapping[str, float],
    published: Mapping[str, float],
    truth: Mapping[str, float],
    *,
    seed: int,
    published_assay_spearman: float | None = None,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> ReferenceCheck:
    """Compare one checkpoint's scores with the benchmark's own, on the variants both hold.

    Variants only one side scored are counted and excluded rather than imputed. A missing
    score is usually a variant the published run dropped, and filling it with anything at all
    would make the comparison partly our invention.
    """
    if not truth:
        raise ReferenceError(f"{assay}: no DMS scores, so there is nothing to validate against")
    shared = sorted(set(ours) & set(published) & set(truth))
    if not shared:
        raise ReferenceError(
            f"{assay}: our scores and the published ones share no variant with a DMS score. "
            "That is a join failure — check the mutant notation and the assay id — not a "
            "result of zero agreement."
        )
    ours_v = [ours[m] for m in shared]
    theirs_v = [published[m] for m in shared]
    truth_v = [truth[m] for m in shared]

    return ReferenceCheck(
        checkpoint=checkpoint,
        assay=assay,
        variants_compared=len(shared),
        variants_ours_only=len(set(ours) - set(published)),
        variants_published_only=len(set(published) - set(ours)),
        ours_vs_published=paired_spearman_interval(
            ours_v, theirs_v, seed=seed, resamples=resamples
        ),
        ours_vs_truth=paired_spearman_interval(ours_v, truth_v, seed=seed, resamples=resamples),
        published_vs_truth=paired_spearman_interval(
            theirs_v, truth_v, seed=seed, resamples=resamples
        ),
        difference_vs_truth=_difference_interval(
            ours_v, theirs_v, truth_v, seed=seed, resamples=resamples
        ),
        published_assay_spearman=published_assay_spearman,
    )


def _difference_interval(
    ours: Sequence[float],
    theirs: Sequence[float],
    truth: Sequence[float],
    *,
    seed: int,
    resamples: int,
) -> Interval:
    """Interval on (our Spearman with the truth) minus theirs, resampled on the same variants.

    Paired on purpose. The two correlations are computed over one assay, so their errors are
    strongly dependent and an interval built from the two marginal intervals would be far too
    wide — wide enough to call a real divergence inconclusive.
    """
    point = spearman(ours, truth) - spearman(theirs, truth)
    if len(ours) < MIN_VARIANTS:
        return Interval(point, float("nan"), float("nan"), "too_few_variants")

    import numpy as np

    rng = np.random.default_rng(seed)
    a = np.asarray(ours, dtype=np.float64)
    b = np.asarray(theirs, dtype=np.float64)
    t = np.asarray(truth, dtype=np.float64)
    n = a.size
    values = np.empty(resamples, dtype=np.float64)
    draws = rng.integers(0, n, size=(resamples, n))
    for i in range(resamples):
        idx = draws[i]
        values[i] = _fast_spearman(a[idx], t[idx]) - _fast_spearman(b[idx], t[idx])
    finite = values[np.isfinite(values)]
    if finite.size == 0:  # pragma: no cover - every resample degenerate
        return Interval(point, float("nan"), float("nan"), "degenerate")
    low, high = (float(v) for v in np.percentile(finite, [2.5, 97.5]))
    return Interval(point, low, high, f"bootstrap_percentile_p{resamples}_seed{seed}")

# The alignment-depth covariate — the contract

**Status: binding on B3.5 and B5.** A change to this file is a `DECISIONS.md` entry.

`DESIGN.md` §B3 makes alignment depth a confounder rather than an extra: "Without it, 'viral
proteins are hard' and 'viral proteins were excluded' are not separable." That is the whole of
Phase B's claim, so this file states the contract the covariate must meet rather than leaving
it to whichever analysis reads the artefact first.

## What the number is

Neff, exactly as D-231 pins it: the sum of sequence weights over an alignment, where a
sequence's weight is the reciprocal of how many sequences sit at or above the identity
threshold to it, itself included. Identity is over the alignment's match columns, a gap counts
as a mismatch, and the denominator is the full column count. The threshold is the one that
alignment's own maintainers reweighted at, carried per alignment rather than chosen here.

Produced by `tools/assay_depth.py` into `artifacts/b3-4/depth.json`. Both readings of the
identity boundary are in the artefact; the inclusive one is the covariate.

## What the analysis must do with it

- **Mandatory, not optional.** Every assay entering a B5 model carries a depth, and a model
  specification that omits the covariate is not a specification this project will run. An
  assay whose depth could not be computed does not enter the model; it is reported as
  excluded, with the reason, rather than entered with a filled-in value.
- **Never imputed.** No mean, no zero, no nearest neighbour. The artefact's `depth` is `null`
  exactly when there is no alignment for the target, and that `null` must stay visible.
- **On the scale it is used at.** Depth spans orders of magnitude across these targets, so the
  covariate enters on the log scale unless B5.1's pre-registration says otherwise in writing.
- **With its uncertainty.** Where the artefact carries an interval, the depth was estimated
  rather than summed, and any sensitivity analysis B5.3 runs on the covariate uses the
  interval rather than the point.
- **Per assay before pooled**, as everywhere else in §B5.

## What a reader may not conclude from it

The figure the alignment's maintainers publish for the same target is in the artefact beside
ours as a ratio. It is a check on our arithmetic, not a target: theirs is computed after their
coverage filters and ours on the alignment as distributed, so the two count slightly different
populations by construction. A ratio near one is reassurance. A ratio far from one is a
finding to chase, not a number to correct ours toward.

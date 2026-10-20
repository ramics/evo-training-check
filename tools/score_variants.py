#!/usr/bin/env python3
"""Score one assay's variants through the B1.2 harness — task B1.2, §B1.

    pixi run -e dev python tools/score_variants.py --checkpoint esm2_t33_650M_UR50D \
        --assay <DMS_id> --reference data/proteingym/v1.3/DMS_substitutions.csv --plan

Two modes, because the work splits across two machines and the split is the point:

`--plan` builds the scoring request, enforces the §4 limits, and writes what the pass would
cost — forward passes, masked positions, batches — without loading a model. It runs anywhere,
including CI, and it is what makes the request itself reviewable before a GPU is billed.

Without `--plan` it scores, which needs the weights and therefore a machine with an
accelerator. The deep-learning import lives inside one function here and nowhere in
`src/amazebio/`, so the harness's refusals stay testable in an environment that has no torch.

Where ProteinGym publishes the same checkpoint's own scores, `--published` adds the B1.2
validation step: our scores against theirs, variant by variant, with intervals (D-208).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import backends, objectstore, proteingym, reference, repro, scoring

TASK = "B1.2"

#: Fixed before any score exists, as the non-negotiable on parameters requires. 10,000 to
#: match the survival tables' resampling, and the seed is the date the choice was made.
SEED = 20261020


def plan(
    checkpoint: str,
    assay: proteingym.Assay,
    variants,
    *,
    batch_size: int,
    variants_source: str,
) -> dict[str, Any]:
    """What the pass would do, costed, without loading anything."""
    spec = backends.recipe(checkpoint)
    request = scoring.ScoringRequest(
        checkpoint=checkpoint,
        wild_type=assay.target_sequence,
        variants=variants,
    )
    positions = request.positions
    batches = backends.mask_batches(positions, batch_size=batch_size)
    forward_passes = (
        len(batches)
        if spec.mode in scoring.MARGINAL_MODES
        else len(variants) + 1  # every mutant sequence, plus the wild type once
    )
    return {
        "checkpoint": checkpoint,
        "mode": spec.mode.value,
        "modality": spec.modality,
        "loader": spec.loader,
        "assay": assay.dms_id,
        "sequence_length": len(assay.target_sequence),
        "variants": len(variants),
        "variants_source": variants_source,
        "masked_positions": len(positions),
        "batch_size": batch_size,
        "forward_passes": forward_passes,
        "scope": {
            "request_fields": list(scoring.request_fields()),
            "note": (
                "the request carries a wild type and a variant list and nothing else, so "
                "there is no field an in-context example could be supplied in (§4)"
            ),
        },
    }


def _forward_from_weights(
    spec: backends.Recipe, weights: Path
) -> backends.Forward:  # pragma: no cover - needs an accelerator
    """Load the checkpoint and return its forward pass, frozen.

    The only place in this repository that imports a deep-learning stack. It puts the model in
    evaluation mode and disables gradients, which is belt and braces over the harness's own
    refusals rather than a substitute for them: `scoring.enforce_scope` still runs, and still
    rejects a backend that exposes a training entry point.
    """
    import torch

    module, _, attribute = spec.loader.rpartition(".")
    loaded = getattr(__import__(module, fromlist=[attribute]), attribute)
    model = loaded.from_pretrained(str(weights))
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)

    def forward(rows):  # type: ignore[no-untyped-def]
        with torch.inference_mode():
            out = model(torch.tensor(list(rows))).logits
        return out.to(torch.float32).cpu().tolist()

    return forward


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--assay", required=True, help="a ProteinGym DMS_id")
    ap.add_argument("--reference", type=Path, required=True, help="DMS_substitutions.csv")
    ap.add_argument("--assays", type=Path, help="DMS_ProteinGym_substitutions.zip")
    ap.add_argument("--published", type=Path, help="zero_shot_substitutions_scores.zip")
    ap.add_argument("--published-column", help="the model's column in the score archive")
    ap.add_argument("--weights", type=Path, help="local checkpoint; omit for --plan")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--plan", action="store_true", help="cost the pass; load nothing")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/b1-2"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    assays = {a.dms_id: a for a in proteingym.load_reference(args.reference)}
    if args.assay not in assays:
        raise SystemExit(f"{args.assay!r} is not in {args.reference}")
    assay = assays[args.assay]

    if not args.plan and (args.weights is None or args.assays is None):
        raise SystemExit("scoring needs --weights and --assays; use --plan to cost it instead")

    args.outdir.mkdir(parents=True, exist_ok=True)
    slug = f"{args.checkpoint}-{assay.dms_id}".replace("/", "_")
    try:
        with repro.run(
            TASK,
            seed=SEED,
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-{slug}.json",
            durable=objectstore.durable_results("b1-2"),
        ) as manifest:
            manifest.parameter("checkpoint", args.checkpoint)
            manifest.parameter("assay", assay.dms_id)
            manifest.parameter("batch_size", args.batch_size)
            manifest.parameter("mode", "plan" if args.plan else "score")
            manifest.parameter("proteingym_release", proteingym.RELEASE.version)
            manifest.input_file(args.reference, role="proteingym reference")

            if args.plan:
                mutants, source = _mutants(args, assay)
                doc = plan(
                    args.checkpoint,
                    assay,
                    scoring.variants_from_mutants(mutants),
                    batch_size=args.batch_size,
                    variants_source=source,
                )
            else:
                doc = _score(args, assay, manifest)

            out = args.outdir / f"{'plan' if args.plan else 'scores'}-{slug}.json"
            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="plan" if args.plan else "scores")
    except (repro.ReproError, scoring.ScoringError, reference.ReferenceError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(doc, indent=2, sort_keys=True)[:2000])
    return 0


def _mutants(args: argparse.Namespace, assay: proteingym.Assay) -> tuple[list[str], str]:
    """The assay's variant names, from the assay archive when it is here.

    Without the archive a plan still has something to cost — the single-substitution
    saturation of the sequence is the upper bound on what the assay can contain, and a plan
    that overstates the work is the safe direction for a cost estimate. It is labelled as
    such in the artefact rather than passed off as the real list.
    """
    if args.assays is not None:
        return sorted(proteingym.load_assay(args.assays, assay)), "assay archive"
    sequence = assay.target_sequence
    return (
        [f"{a}{i + 1}G" for i, a in enumerate(sequence) if a != "G"],
        "one substitution per position, the archive being absent: an upper bound on the "
        "work, not this assay's variant list",
    )


def _score(
    args: argparse.Namespace, assay: proteingym.Assay, manifest: Any
) -> dict[str, Any]:  # pragma: no cover - needs an accelerator
    spec = backends.recipe(args.checkpoint)
    truth = proteingym.load_assay(args.assays, assay)
    request = scoring.ScoringRequest(
        checkpoint=args.checkpoint,
        wild_type=assay.target_sequence,
        variants=scoring.variants_from_mutants(sorted(truth)),
    )
    backend = backends.FrozenLM(
        checkpoint_id=spec.checkpoint_id,
        mode=spec.mode,
        modality=spec.modality,
        forward=_forward_from_weights(spec, args.weights),
        batch_size=args.batch_size,
    )
    scoring.enforce_scope(backend)
    scores = scoring.score_request(backend, request)
    determinism = scoring.determinism_evidence(backend, request)

    doc: dict[str, Any] = {
        "checkpoint": args.checkpoint,
        "assay": assay.dms_id,
        "variants_scored": len(scores),
        "determinism": determinism,
        "scores": scores,
    }
    if args.published is not None and args.published_column:
        manifest.input_file(args.published, role="published zero-shot scores")
        published = proteingym.load_model_scores(args.published, assay, args.published_column)
        doc["reference_check"] = reference.check_against_published(
            args.checkpoint,
            assay.dms_id,
            scores,
            published,
            truth,
            seed=SEED,
        ).to_dict()
    return doc


if __name__ == "__main__":
    raise SystemExit(main())

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
import time
from collections.abc import Callable
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


def is_evolutionaryscale(spec: backends.Recipe) -> bool:
    """Whether this checkpoint loads through EvolutionaryScale's package rather than
    `transformers`.

    ESM3-open and ESM-C are not reachable as `transformers.EsmForMaskedLM`: their published
    access route is the `esm` package, and `amazebio.backends` records that route verbatim
    rather than substituting one the authors did not name. The two routes differ in how the
    model is constructed and in what its output object calls the sequence logits, and in
    nothing else — the tokenizer, the vocabulary and the prefix arithmetic are shared, so a
    difference between two checkpoints' scores is the model and not the reader.
    """
    return spec.loader.startswith("esm.models.")


def _masked_lm_logits(model, rows):  # type: ignore[no-untyped-def]
    """Logits from a `transformers` masked language model."""
    return model(input_ids=rows).logits


def _sequence_logits(model, rows):  # type: ignore[no-untyped-def]
    """Logits over the sequence track of an EvolutionaryScale model.

    ESM3 is multi-track and generative; only the sequence track is read and only through
    this one call. Nothing here hands the model itself to the harness — `FrozenLM` closes
    over a forward function — so `scoring.enforce_scope` still has nothing to reject and
    the generation entry points §4 forbids stay out of reach by construction, not by
    agreement.
    """
    return model(sequence_tokens=rows).sequence_logits


def load_backend(
    spec: backends.Recipe,
    weights: str,
    *,
    batch_size: int,
    progress: Callable[[int, int], None] | None = None,
) -> backends.FrozenLM:  # pragma: no cover - loads weights
    """Load the checkpoint and wrap it as a frozen backend.

    The only place in this repository that imports a deep-learning stack. It puts the model in
    evaluation mode and clears every gradient flag, which is belt and braces over the
    harness's own refusals rather than a substitute for them: `scoring.enforce_scope` still
    runs against the object this returns, and still rejects a backend that exposes a training
    entry point.

    The vocabulary and the prefix length are read from the tokenizer rather than assumed. Both
    are the kind of thing that is right on one checkpoint and silently wrong on the next, and
    `FrozenLM` has no way to detect either: a one-token shift produces perfectly plausible
    numbers.
    """
    import torch

    module, _, attribute = spec.loader.rpartition(".")
    loaded = getattr(__import__(module, fromlist=[attribute]), attribute)

    if is_evolutionaryscale(spec):
        from esm.tokenization import EsmSequenceTokenizer

        tokenizer = EsmSequenceTokenizer()
        extra = {} if attribute == "ESM3" else {"use_flash_attn": False}
        model = loaded.from_pretrained(weights, device=torch.device("cpu"), **extra)
        # The released weights are bfloat16 and the forward mixes them with float32
        # activations, which raises rather than casting. Scoring in float32 is both what
        # resolves that and what the published reference numbers are in (D-220).
        model = model.to(torch.float32)
        logits_of = _sequence_logits
    else:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(weights)
        model = loaded.from_pretrained(weights)
        logits_of = _masked_lm_logits

    model.eval()
    model.requires_grad_(False)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    vocabulary = {r: tokenizer.convert_tokens_to_ids(r) for r in scoring.AMINO_ACIDS}
    prefix = len(tokenizer("A")["input_ids"]) - 1 - int(tokenizer.eos_token_id is not None)

    def forward(rows):  # type: ignore[no-untyped-def]
        with torch.inference_mode():
            out = logits_of(model, torch.tensor(list(rows)))
        return out.to(torch.float64).cpu().tolist()

    return backends.FrozenLM(
        checkpoint_id=spec.checkpoint_id,
        mode=spec.mode,
        modality=spec.modality,
        trainable_parameters=trainable,
        vocabulary=vocabulary,
        encoder=dict(vocabulary),
        mask_token_id=int(tokenizer.mask_token_id),
        prefix_tokens=prefix,
        forward=forward,
        batch_size=batch_size,
        progress=progress,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--assay", required=True, help="a ProteinGym DMS_id")
    ap.add_argument("--reference", type=Path, required=True, help="DMS_substitutions.csv")
    ap.add_argument("--assays", type=Path, help="DMS_ProteinGym_substitutions.zip")
    ap.add_argument("--published", type=Path, help="zero_shot_substitutions_scores.zip")
    ap.add_argument(
        "--published-column",
        help="override the column pinned on the recipe; normally omitted",
    )
    ap.add_argument("--weights", help="checkpoint path or hub id; omit for --plan")
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

            out = args.outdir / f"{'plan' if args.plan else 'scores'}-{slug}.json"
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
                doc = _score(
                    args,
                    assay,
                    manifest,
                    checkpoint=lambda partial: out.write_text(
                        json.dumps(partial, indent=2, sort_keys=True) + "\n"
                    ),
                )

            out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="plan" if args.plan else "scores")
    except (
        repro.ReproError,
        scoring.ScoringError,
        reference.ReferenceError,
        proteingym.ProteinGymError,
    ) as exc:
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


def resolve_published_column(requested: str | None, spec: Any) -> str | None:
    """Which published column this run checks itself against, or None for no check.

    One line, and it has its own name because the bug it prevents cost a forty-minute
    scoring pass on 2026-10-20: the resolved value was computed and then the unresolved one
    was passed on, so a checkpoint whose column comes from its recipe looked for a column
    named `None` and the whole run was discarded at the last step.
    """
    return requested or getattr(spec, "published_column", None)


def _score(
    args: argparse.Namespace,
    assay: proteingym.Assay,
    manifest: Any,
    *,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:  # pragma: no cover - needs an accelerator
    """Score the assay's variants, then check them against the published column.

    `checkpoint` is called with the scores the moment they exist and before the reference
    check runs. The forward passes are the expensive part — three quarters of an hour for
    one assay on a CPU — and the check that follows reads a file and can fail on it, as it
    did on 2026-10-20 when a column name resolved to None. Losing the pass to a failure in
    what verifies it is the wrong way round, so the scores are on disk before the check is
    attempted and the failure is still raised.
    """
    spec = backends.recipe(args.checkpoint)
    truth = proteingym.load_assay(args.assays, assay)
    request = scoring.ScoringRequest(
        checkpoint=args.checkpoint,
        wild_type=assay.target_sequence,
        variants=scoring.variants_from_mutants(sorted(truth)),
    )
    started = time.time()

    def progress(done: int, total: int) -> None:
        if done % 10 and done != total:
            return
        rate = done / max(time.time() - started, 1e-9)
        print(
            f"  {done}/{total} batches, {rate:.2f}/s, "
            f"{(total - done) / max(rate, 1e-9) / 60:.1f} min left",
            flush=True,
        )

    backend = load_backend(spec, str(args.weights), batch_size=args.batch_size, progress=progress)
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
    if checkpoint is not None:
        checkpoint(doc)

    column = resolve_published_column(args.published_column, spec)
    # A missing `reference_check` is indistinguishable from a check that was skipped by
    # accident, and that is not hypothetical: ESM3-open's first pass carried no reference
    # block, which read as "no published column exists" when the truth was that the run was
    # invoked without `--published`. ProteinGym v1.3 publishes an `ESM3` column. So the
    # absence is stated with its reason — an operator who omitted the input and a benchmark
    # that never published the number are different facts, and only one of them is a finding.
    if args.published is None or not column:
        doc["reference_check"] = {
            "checkpoint": args.checkpoint,
            "assay": assay.dms_id,
            "compared": False,
            "why_not": (
                "no published zero-shot scores were supplied for this run"
                if args.published is None
                else f"{args.checkpoint} has no column in the published score table, so there "
                "is no reference to reproduce"
            ),
        }
        doc["published_column"] = column
    if args.published is not None and column:
        manifest.input_file(args.published, role="published zero-shot scores")
        published = proteingym.load_model_scores(args.published, assay, column)
        doc["reference_check"] = reference.check_against_published(
            args.checkpoint,
            assay.dms_id,
            scores,
            published,
            truth,
            seed=SEED,
        ).to_dict()
        doc["published_column"] = column
    return doc


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage the pinned ProstT5 weights A2.2 predicts 3Di with, so a launch does not re-download them.

    pixi run -e dev python tools/stage_prostt5.py            # upload if absent, then verify
    pixi run -e dev python tools/stage_prostt5.py --verify   # re-checksum what is staged

A2.2's 3Di prediction is the whole cost of the task (D-163), and the weights that do it were
being fetched on every launch from a third-party Cloudflare worker, unauthenticated and
unchecksummed, by `foldseek databases ProstT5`. Two things wrong with that, one of which stopped a
launch.

**The host rate-limits.** Measured 2026-10-19 on a real instance: all three download attempts
came back `status=429` from `foldseek.steineggerlab.workers.dev`, about fifteen minutes after the
same file downloaded cleanly in the session container. A 429 is not a transient a short retry
clears, and it sits on the critical path of a 24.7-hour pass that may need relaunching — so a
launch could fail for a reason that has nothing to do with the work and everything to do with
somebody else's bandwidth budget.

**It was an unpinned input.** `AGENTS.md` is explicit that a result which cannot be regenerated
from pinned inputs is not a result yet, and the published command names no digest at all. That is
not hypothetical here: D-171's threshold — 500 bits, with its decoy false-positive rate and its
sensitivity — was measured with *these* weights. If an instance later fetched a different build
under the same name, the threshold would be a number measured on one instrument and applied to
another, and nothing in the pipeline would notice. Staging the bytes with their digest is what
makes the calibration and the pass the same experiment.

So the weights are staged once into the corpus bucket and fetched in region thereafter: free,
fast, and identical on every launch. The bucket has no `s3:DeleteObject`, which is the usual
caveat about writing to it — and here it is the point, because an un-rewritable pinned input is
exactly what this is for.

Attribution: ProstT5 is published by Rostlab (huggingface.co/Rostlab/ProstT5). This stages a
copy into a private bucket for reproducibility; it redistributes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, folds, objectstore
from amazebio.repro import run

REPO = Path(__file__).resolve().parent.parent

#: The staged key. Carries the digest's first 12 characters so a different build cannot land on
#: the same key and be fetched in its place — the bucket is append-only, so a key is a promise.
#: The pin itself lives in `amazebio.folds` so the launcher reads the same one this tool wrote
#: to — two copies of a digest is one copy too many.
WEIGHTS_SHA256 = folds.PROSTT5.sha256
WEIGHTS_BYTES = folds.PROSTT5.bytes
WEIGHTS_NAME = folds.PROSTT5.name
WEIGHTS_KEY = folds.PROSTT5.key

#: Where `foldseek databases ProstT5` fetches from, recorded so the provenance of the staged copy
#: is not just "it was on disk".
UPSTREAM = folds.PROSTT5.upstream
UPSTREAM_PUBLISHER = folds.PROSTT5.publisher

#: Read in 8 MiB blocks: the file is 2.3 GB and is never held in memory.
CHUNK = 8 << 20


class StageError(RuntimeError):
    """Raised when the weights cannot be staged or verified as specified."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def staged_size(client: Any, bucket: str, key: str) -> int | None:
    """The staged object's size, or `None` when it is not there."""
    try:
        return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
    # Any failure here means "treat it as absent"; the caller then uploads or reports.
    except Exception:
        return None


def verify_local(path: Path) -> str:
    """Check the local weights against the pin before anything is uploaded or trusted."""
    if not path.exists():
        raise StageError(
            f"{path} is not there. Fetch it once with:\n"
            "  pixi run -e foldseek foldseek databases ProstT5 data/prostt5 /tmp/pt5tmp\n"
            f"  (upstream is rate-limited; it is {UPSTREAM})"
        )
    size = path.stat().st_size
    if size != WEIGHTS_BYTES:
        raise StageError(f"{path} is {size} bytes, the pin says {WEIGHTS_BYTES}")
    digest = sha256_of(path)
    if digest != WEIGHTS_SHA256:
        raise StageError(
            f"{path} has sha256 {digest}, the pin says {WEIGHTS_SHA256}. These are not the "
            "weights D-171's threshold was measured with, so the calibration would not apply."
        )
    return digest


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--weights", type=Path, default=Path("data/prostt5") / WEIGHTS_NAME)
    ap.add_argument("--out", type=Path, default=Path("artifacts/a2-2/weights"))
    ap.add_argument("--bucket", default=None)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="re-checksum the local file and report what is staged; upload nothing",
    )
    ap.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bucket = args.bucket or corpora.BUCKET
    client = objectstore.client()

    digest = verify_local(args.weights)
    print(f"local weights verified: {args.weights} ({WEIGHTS_BYTES:,} bytes, {digest[:16]}…)")

    size = staged_size(client, bucket, WEIGHTS_KEY)
    if args.verify:
        print(
            f"staged: {'absent' if size is None else f'{size:,} bytes'} at s3://{bucket}/{WEIGHTS_KEY}"
        )
        if size is not None and size != WEIGHTS_BYTES:
            raise StageError(f"staged object is {size} bytes, expected {WEIGHTS_BYTES}")
        return 0

    if size == WEIGHTS_BYTES:
        print(f"already staged, unchanged: s3://{bucket}/{WEIGHTS_KEY}")
    elif size is not None:
        raise StageError(
            f"s3://{bucket}/{WEIGHTS_KEY} exists at {size} bytes, not {WEIGHTS_BYTES}, and this "
            "bucket has no DeleteObject. Stage under a key derived from the real digest instead "
            "of overwriting a pinned input."
        )
    else:
        print(f"uploading {WEIGHTS_BYTES / 1e9:.2f} GB to s3://{bucket}/{WEIGHTS_KEY}", flush=True)
        client.upload_file(str(args.weights), bucket, WEIGHTS_KEY)
        landed = staged_size(client, bucket, WEIGHTS_KEY)
        if landed != WEIGHTS_BYTES:
            raise StageError(f"upload landed {landed} bytes, expected {WEIGHTS_BYTES}")
        print("upload verified by size")

    args.out.mkdir(parents=True, exist_ok=True)
    with run(
        "A2.2",
        seed=20261015,
        outdir=args.out,
        allow_dirty=args.allow_dirty,
        repo=REPO,
        durable=objectstore.durable_results("a2-2"),
    ) as m:
        m.parameter("weights_sha256", WEIGHTS_SHA256)
        m.parameter("weights_bytes", WEIGHTS_BYTES)
        m.parameter("upstream", UPSTREAM)
        m.parameter("publisher", UPSTREAM_PUBLISHER)
        m.input_file(args.weights, role="prostt5-weights")
        body = {
            "task": "A2.2",
            "what": "ProstT5 f16 GGUF weights, as foldseek's 3Di predictor consumes them",
            "sha256": WEIGHTS_SHA256,
            "bytes": WEIGHTS_BYTES,
            "staged_uri": f"s3://{bucket}/{WEIGHTS_KEY}",
            "upstream": UPSTREAM,
            "publisher": UPSTREAM_PUBLISHER,
            "why_staged": (
                "the upstream host returned 429 to all three attempts from an instance on "
                "2026-10-19, and the published download names no digest — so the weights were "
                "both a rate-limited dependency on the critical path and an unpinned input. "
                "D-171's threshold was measured with these exact bytes."
            ),
            "decision": "D-173",
        }
        out = args.out / "prostt5.json"
        out.write_text(json.dumps(body, indent=2) + "\n")
        m.output_file(out, role="weights-pin")
    print(f"wrote {args.out / 'prostt5.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

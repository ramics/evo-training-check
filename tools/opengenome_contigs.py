#!/usr/bin/env python3
"""Enumerate OpenGenome2's GTDB contigs, in region — task A7.4, §A7.

    python tools/opengenome_contigs.py --archive v214/batch1.tar --upload-results

D-213 makes the contig accession A7.4's primary comparison key, with a sequence digest
settling whatever the accessions disagree about. The genome-level half reads only tar member
names and needs no instance; this half does not have that option. A contig accession lives
inside a member's gzip stream, so every one of the four archives has to be decompressed in
full — about 109 GB read and some 380 GB decompressed — and that is the data movement
`AGENTS.md` says belongs inside `us-east-1`. `tools/ec2_opengenome_contigs.py` launches it.

**Why it streams the archive rather than seeking through it.** The genome pass walks the
header chain with one ranged read per member, which is right when the names are all it
wants. Here the bytes are read anyway, so a single sequential `GET` per archive costs the
same transfer with none of the per-member latency, and `tarfile`'s stream mode needs no
index. The member's own gzip is what bounds a worker: one member is one gzip stream and a
gzip stream cannot be split, so parallelism is across archives, four ways.

**What it writes, and when.** One JSON line per contig — assembly, accession, length,
digest — gzipped as it goes, so a killed run leaves a readable prefix rather than nothing,
and a heartbeat object every interval carrying members and contigs so far. A step with no
heartbeat is a step whose silence means nothing (D-127), and this one runs for an hour.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import contigs as contiglib
from amazebio import objectstore, repro, uniref

TASK = "A7.4"

S3_REGION = "us-east-1"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"

#: The staged tree, pinned by the content hash the release was staged under. The same
#: constant as the genome pass, repeated rather than imported so that the two halves of the
#: comparison cannot drift onto different prefixes without a test noticing.
PREFIX = "corpora/opengenome2/84d2a7e690c8bb395d1f4868822dfa031ea561c6/fasta/gtdb_v220"

#: Which archive holds which side of Evo 2's claim.
ARCHIVES = {
    "v214/batch1.tar": "reused",
    "v214/batch2.tar": "reused",
    "v214/batch3.tar": "reused",
    "v220_update.tar": "added",
}


def slug(archive: str) -> str:
    """`v214/batch1.tar` -> `v214-batch1`, for a file name and an object key."""
    return archive.replace("/", "-").removesuffix(".tar")


class Heartbeat:
    """Where this archive's pass has got to, published where a reader outside can see it.

    It carries a monotonically growing contig count rather than only a timestamp, because a
    `written_at` that advances tells a reader the heartbeat thread is alive and nothing
    about whether the work is (D-192).
    """

    def __init__(self, client: Any, bucket: str, key: str, *, every: float) -> None:
        self.client, self.bucket, self.key, self.every = client, bucket, key, every
        self.started = time.monotonic()
        self.last = 0.0

    def publish(self, state: dict[str, Any], *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last < self.every:
            return
        self.last = now
        body = json.dumps(
            {
                "task": TASK,
                "elapsed_seconds": round(now - self.started, 1),
                "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **state,
            },
            indent=2,
            sort_keys=True,
        ).encode()
        if self.client is None:
            return
        try:
            self.client.put_object(Bucket=self.bucket, Key=self.key, Body=body)
        except Exception as exc:  # A heartbeat that fails must not end the pass.
            print(f"    heartbeat failed: {type(exc).__name__}: {str(exc)[:100]}", flush=True)


def members(stream: Any) -> Any:
    """Yield `(TarInfo, fileobj)` for each regular file of a tar read forward-only."""
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for info in archive:
            if not info.isfile():
                continue
            handle = archive.extractfile(info)
            if handle is None:  # pragma: no cover - a file member always extracts
                continue
            yield info, handle


def scan(
    stream: Any,
    archive: str,
    write: Any,
    *,
    heartbeat: Heartbeat | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read one archive through, writing a line per contig and returning its totals."""
    genomes = 0
    records = 0
    residues = 0
    skipped: list[str] = []
    for info, handle in members(stream):
        try:
            assembly = contiglib.strain_of(info.name)
        except contiglib.ContigError:
            # Counted and named rather than dropped: a member this pass cannot place is a
            # change in how the publisher lays the archive out, which is a finding.
            if len(skipped) < 20:
                skipped.append(info.name)
            continue
        with gzip.GzipFile(fileobj=handle) as plain:
            for contig in contiglib.parse_fasta(
                io.TextIOWrapper(plain, encoding="ascii", errors="replace"), source=info.name
            ):
                write(
                    json.dumps(
                        {
                            "assembly": assembly,
                            "accession": contig.accession,
                            "length": contig.length,
                            "sha256": contig.sha256,
                        }
                    )
                    + "\n"
                )
                records += 1
                residues += contig.length
        genomes += 1
        if heartbeat is not None:
            heartbeat.publish(
                {
                    "archive": archive,
                    "genomes": genomes,
                    "contigs": records,
                    "residues": residues,
                }
            )
        if limit is not None and genomes >= limit:
            break
    return {
        "archive": archive,
        "side": ARCHIVES.get(archive, "unknown"),
        "genomes": genomes,
        "contigs": records,
        "residues": residues,
        "unplaceable_members": len(skipped),
        "unplaceable_examples": skipped[:5],
    }


def _open(client: Any, bucket: str, key: str, source: str | None) -> Any:
    if source:
        return open(source, "rb")
    return uniref.S3RangeRead(
        client,
        bucket,
        key,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at {pos:,} bytes: {type(exc).__name__}", flush=True
        ),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--archive", choices=sorted(ARCHIVES), required=True)
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--source", help="a local tar to read instead of the staged object")
    ap.add_argument("--outdir", type=Path)
    ap.add_argument("--limit", type=int, help="stop after this many genomes; for a smoke test")
    ap.add_argument("--heartbeat-seconds", type=float, default=120.0)
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--code-commit", help="the commit the payload was built from")
    args = ap.parse_args(argv)

    if args.limit and args.upload_results:
        # The corpus bucket has no DeleteObject, so a truncated table published under a
        # commit's key is permanent and indistinguishable from a complete one.
        raise SystemExit("--limit is a smoke test; it may not publish. Drop --upload-results.")

    bucket = prefix = ""
    client = None
    if not args.source or args.upload_results:
        if not args.s3_uri:
            raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
        bucket, _, prefix = args.s3_uri[5:].partition("/")
        prefix = prefix.strip("/")
        from botocore.config import Config

        client = objectstore.client(config=Config(retries={"max_attempts": 10, "mode": "standard"}))

    args.outdir = args.outdir or Path("artifacts/a7-4")
    args.outdir.mkdir(parents=True, exist_ok=True)
    stamp = args.code_commit or "local"
    name = f"contigs-{slug(args.archive)}-{stamp}"

    try:
        with repro.run(
            TASK,
            seed=None,  # an enumeration; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-{name}.json",
            durable=objectstore.durable_results("a7-4") if args.upload_results else None,
            durable_exempt=None if args.upload_results else "a smoke test, read back locally",
        ) as manifest:
            manifest.parameter("prefix", PREFIX)
            manifest.parameter("archive", args.archive)
            manifest.parameter("side", ARCHIVES[args.archive])
            manifest.parameter("decisions", ["D-130", "D-213"])
            manifest.parameter("limit", args.limit)
            if args.code_commit:
                manifest.parameter("code_commit", args.code_commit)
            elif not manifest.git.get("available"):
                manifest.note(
                    "no git checkout and no --code-commit: this manifest cannot be traced "
                    "to the code that produced it, so the numbers are not citable"
                )
            manifest.note(
                "Accession and digest are derived by amazebio.contigs, which both sides of "
                "the comparison use, so a difference here is a difference in the data "
                "rather than in how the two representations were read."
            )

            # The staged prefix is absolute within the bucket, so `--s3-uri`'s own prefix
            # does not prepend to it; it names the bucket and nothing more here.
            key = f"{PREFIX}/{args.archive}"
            heartbeat = None
            if args.upload_results:
                hb_bucket, hb_prefix = objectstore.split_uri(objectstore.durable_results("a7-4"))
                heartbeat = Heartbeat(
                    client,
                    hb_bucket,
                    f"{hb_prefix}/heartbeat-{slug(args.archive)}-{stamp}.json",
                    every=args.heartbeat_seconds,
                )

            out = args.outdir / f"{name}.jsonl.gz"
            started = time.monotonic()
            stream = _open(client, bucket, key, args.source)
            try:
                with gzip.open(out, "wt", encoding="ascii") as handle:
                    document = scan(
                        stream,
                        args.archive,
                        handle.write,
                        heartbeat=heartbeat,
                        limit=args.limit,
                    )
            finally:
                if hasattr(stream, "close"):
                    stream.close()
            document["elapsed_seconds"] = round(time.monotonic() - started, 1)
            if heartbeat is not None:
                heartbeat.publish({**document, "finished": True}, force=True)

            summary = args.outdir / f"{name}.json"
            summary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="contig table")
            manifest.output_file(summary, role="archive summary")
    except (repro.ReproError, contiglib.ContigError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    print(
        f"{document['archive']}: {document['genomes']:,} genomes, "
        f"{document['contigs']:,} contigs, {document['residues']:,} residues "
        f"in {document['elapsed_seconds']:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

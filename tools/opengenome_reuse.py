#!/usr/bin/env python3
"""Which genomes OpenGenome2's GTDB subtree holds — task A7.4, §A7.

    pixi run -e dev python tools/opengenome_reuse.py --measure genomes

Evo 2 states that OpenGenome "was used in its entirety" and that genomes from GTDB 220.0 were
then added — "all species' reference genomes that had no previously published (release 214.1)
genomes within their species cluster, resulting in 28,174 additional genomes"
(`S-EVO2-NATURE-METHODS` §A.2.1, D-130). This is the genome-level half of checking that:
enumerate the assemblies each staged archive actually holds.

D-213 fixes why this half is separate. The 28,174 figure is a claim about genomes, so counting
contigs would answer a different question; and an assembly accession is a tar member's name,
so the whole archive can be enumerated by walking its header chain — about 14 MB of transfer
for a 25.6 GB archive — with nothing decompressed and no instance needed. The contig-level
comparison that D-213 makes A7.4's primary key is a full pass over both releases and is not
this tool.

**It is latency-bound, not bandwidth-bound.** A member's header can only be found from the
one before it, so the chain within an archive is strictly sequential; measured from this
container at about 4 members a second. The four archives are therefore walked in parallel
with each other and never within themselves, and progress is published as each archive
finishes a batch of members, because a walk with no heartbeat is a walk whose silence means
nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, repro, tarindex

TASK = "A7.4"

#: The staged tree, pinned by the content hash the release was staged under.
PREFIX = "corpora/opengenome2/84d2a7e690c8bb395d1f4868822dfa031ea561c6/fasta/gtdb_v220"

#: Which archive holds which side of the claim. `v214` is the subtree Evo 2 says it reused in
#: its entirety; `v220_update` is the addition the 28,174 figure counts.
ARCHIVES = {
    "v214/batch1.tar": "reused",
    "v214/batch2.tar": "reused",
    "v214/batch3.tar": "reused",
    "v220_update.tar": "added",
}

#: The published figure this tool checks, from the version of record's Methods (D-130).
STATED_ADDED = 28_174

#: How often a walk publishes its position, in members.
HEARTBEAT = 500


def accession(member_name: str) -> str | None:
    """`batch1/GCA_018384735.1.fasta.gz` -> `GCA_018384735.1`, or None for a non-genome.

    Returns None rather than guessing: a directory member and anything not named like an
    assembly accession is counted separately, so a change in how the publisher lays the
    archive out shows up as a count instead of as a silently smaller genome list.
    """
    leaf = member_name.rsplit("/", 1)[-1]
    if not leaf.endswith(".fasta.gz"):
        return None
    stem = leaf[: -len(".fasta.gz")]
    head, _, version = stem.partition(".")
    if head[:4] not in {"GCA_", "GCF_"} or not version.isdigit():
        return None
    return stem


class Progress:
    """Where each archive's walk has got to, written where a reader can see it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.state: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.started = time.time()

    def update(self, archive: str, members: int, offset: int, size: int) -> None:
        with self.lock:
            self.state[archive] = {
                "members": members,
                "bytes_position": offset,
                "bytes_total": size,
                "fraction": round(offset / size, 4) if size else None,
            }
            self.path.write_text(
                json.dumps(
                    {
                        "task": TASK,
                        "elapsed_seconds": round(time.time() - self.started, 1),
                        "archives": self.state,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )


def _checkpoint_path(outdir: Path, archive: str) -> Path:
    return outdir / f"members-{archive.replace('/', '-')}.jsonl"


def _resume_from(path: Path) -> tuple[list[str], list[str], int, int]:
    """What a previous run of this archive got through: names, members, next offset.

    Each line also carries the member's own offset and length, which is what lets the
    contig-level pass read members in parallel: a gzip stream cannot be decompressed in
    parallel, but one member is one stream, so the member list is the parallelism.

    The checkpoint is append-only JSON lines, so a run killed mid-write leaves at most one
    malformed trailing line. That line is dropped rather than parsed, and the walk restarts
    from the last line that did parse — which costs at most one member, where the
    alternative is two hours.
    """
    if not path.exists():
        return [], [], 0, 0
    accessions: list[str] = []
    other: list[str] = []
    members = offset = 0
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        members, offset = row["members"], row["next_offset"]
        (accessions if row["accession"] else other).append(row["accession"] or row["name"])
    return accessions, other, members, offset


def walk(archive: str, progress: Progress, *, outdir: Path, resume: bool) -> dict[str, Any]:
    client = objectstore.client()
    bucket = objectstore.CORPORA_BUCKET
    key = f"{PREFIX}/{archive}"
    size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]

    def read(offset: int, length: int) -> bytes:
        end = offset + length - 1
        return client.get_object(Bucket=bucket, Key=key, Range=f"bytes={offset}-{end}")[
            "Body"
        ].read()

    checkpoint = _checkpoint_path(outdir, archive)
    accessions, other, members, start = _resume_from(checkpoint) if resume else ([], [], 0, 0)
    if not resume and checkpoint.exists():
        checkpoint.unlink()
    if start:
        print(f"{archive}: resuming at member {members:,}, byte {start:,}", flush=True)

    with checkpoint.open("a") as log:
        for member in tarindex.walk_members(read, size, start=start):
            members += 1
            if not member.is_file:
                continue
            found = accession(member.name)
            (accessions if found else other).append(found or member.name)
            log.write(
                json.dumps(
                    {
                        "members": members,
                        "next_offset": member.next_offset,
                        "offset": member.offset,
                        "size": member.size,
                        "name": member.name,
                        "accession": found,
                    }
                )
                + "\n"
            )
            if members % HEARTBEAT == 0:
                log.flush()
                progress.update(archive, members, member.offset, size)
    progress.update(archive, members, size, size)
    return {
        "archive": archive,
        "side": ARCHIVES[archive],
        "bytes": size,
        "members": members,
        "genomes": len(accessions),
        "distinct_genomes": len(set(accessions)),
        "non_genome_members": len(other),
        "non_genome_examples": sorted(other)[:5],
        "accessions": sorted(accessions),
    }


def measure(workers: int, progress: Progress, *, outdir: Path, resume: bool) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(lambda a: walk(a, progress, outdir=outdir, resume=resume), ARCHIVES)
        )

    by_side: dict[str, set[str]] = {"reused": set(), "added": set()}
    for result in results:
        by_side[result["side"]].update(result["accessions"])
    overlap = sorted(by_side["reused"] & by_side["added"])

    added = len(by_side["added"])
    return {
        "task": TASK,
        "design_ref": "§A7",
        "decisions": ["D-130", "D-213"],
        "prefix": f"s3://{objectstore.CORPORA_BUCKET}/{PREFIX}",
        "archives": [{k: v for k, v in r.items() if k != "accessions"} for r in results],
        "reused_genomes": len(by_side["reused"]),
        "added_genomes": added,
        "stated_added": STATED_ADDED,
        "added_difference": added - STATED_ADDED,
        "genomes_in_both_sides": len(overlap),
        "genomes_in_both_examples": overlap[:5],
        "reading_this_file": [
            "These are assembly accessions read from tar member names. Nothing was "
            "decompressed, so this says which genomes are present and nothing about their "
            "contents (D-213).",
            "The addition figure is checked against the version of record's Methods; a "
            "difference is reported as a difference and is not reconciled here.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--measure", choices=("genomes",), default="genomes")
    ap.add_argument("--workers", type=int, default=len(ARCHIVES))
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a7-4"))
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="continue each archive from its checkpoint rather than from the start",
    )
    args = ap.parse_args(argv)

    args.outdir.mkdir(parents=True, exist_ok=True)
    progress = Progress(args.outdir / "progress-genomes.json")
    try:
        with repro.run(
            TASK,
            seed=None,  # an enumeration; nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-genomes.json",
            durable=objectstore.durable_results("a7-4"),
        ) as manifest:
            manifest.parameter("prefix", PREFIX)
            manifest.parameter("archives", sorted(ARCHIVES))
            manifest.parameter("stated_added", STATED_ADDED)
            manifest.parameter("decisions", ["D-130", "D-213"])
            manifest.parameter("resumed", args.resume)
            document = measure(args.workers, progress, outdir=args.outdir, resume=args.resume)
            out = args.outdir / "genomes.json"
            out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
            manifest.output_file(out, role="genome enumeration")
    except (repro.ReproError, tarindex.TarIndexError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    print(
        f"reused side: {document['reused_genomes']:,} genomes\n"
        f"added side:  {document['added_genomes']:,} genomes against a stated "
        f"{STATED_ADDED:,} ({document['added_difference']:+,})\n"
        f"present on both sides: {document['genomes_in_both_sides']:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

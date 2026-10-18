#!/usr/bin/env python3
"""Execute ESM3's stated select-agent procedure against UniProtKB at the release it names.

ESM3's denylist is "all sequences in UniProt belonging to organisms on the Select Agents and
Toxins List", giving "147K non-viral sequences and 40K additional viral sequences" (version of
record, A.6.1 p47). A1.8 ran that against the current release and got 140,591 — but UniProtKB
has lost 40% of its entries since 2023_02 to redundant-proteome removal, concentrated in the
over-sequenced bacteria the non-viral half of the list is made of. So the current-release
figure cannot distinguish a correct reading from a wrong one: the drift is the same size as
the gap.

This reads the release ESM3 actually names. UniProt numbers UniProtKB and UniRef together, so
`release-2023_02` is the UniProtKB contemporaneous with the UniRef component the paper cites.

**Everything about the shape of this run is forced by the archive.** Old releases are served
as one 182.7 GB tarball whose only data members are `uniprot_sprot.dat.gz` and
`uniprot_trembl.dat.gz` — no FASTA, and tar is sequential, so the archive is read end to end
once and there is nothing to skip. Both gzip layers are single-threaded by construction, so a
bigger instance buys nothing (AGENTS.md); what the instance buys is a direct, un-proxied
download of 182.7 GB, which the session container cannot sustain.

**The integrity check is the point, not a nicety.** A truncated stream returns a smaller count
and no error, which would read as "our reading over-counts" and would understate how much
denylisted material UniProt held — the direction §2 treats as the same failure as overstating
leakage. So each member's entry count is checked against the publisher's own release
statistic, and a mismatch fails the run.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from amazebio import objectstore, repro, seeds, selectagents, uniprotkb, uniref  # noqa: E402
from amazebio.repro import ReproError  # noqa: E402

SECTION_FILES = {
    "73.3": "cfr-title42-part73-2024-06-01.xml",
    "73.4": "cfr-title42-part73-2024-06-01.xml",
    "121.3": "cfr-title9-part121-2024-06-01.xml",
    "331.3": "cfr-title7-part331-2024-06-01.xml",
}
DEFAULT_CAPTURES = REPO_ROOT / "policies" / "captures"
DEFAULT_MAPPING = REPO_ROOT / "policies" / "specs" / "select-agents-2024-06-01.json"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
S3_REGION = "us-east-1"
PUBLISHED_SEQUENCES = 187_000


def required_data_files() -> tuple[str, ...]:
    """The non-import files the instance needs, asked of this tool by its launcher.

    Same trap as A1.8's seed pass: these are data, so no import-closure derivation can notice
    them missing, and the instance dies half a minute in having downloaded nothing.
    """
    names = sorted({f"policies/captures/{name}" for name in SECTION_FILES.values()})
    return (*names, str(DEFAULT_MAPPING.relative_to(REPO_ROOT)))


class _Counted:
    """A read-only wrapper that records how much compressed stream has gone past.

    Plain duck typing rather than `io.RawIOBase`: gzip needs only `read`, and a `RawIOBase`
    subclass without `readinto` raises `NotImplementedError` from inside the buffering layer,
    which is a confusing way to learn that.
    """

    def __init__(self, fh: Any) -> None:
        self.fh = fh
        self.read_bytes = 0

    def read(self, n: int = -1) -> bytes:
        chunk = self.fh.read(n if n is not None and n >= 0 else 1 << 20)
        self.read_bytes += len(chunk)
        return chunk


def _heartbeat(client: Any, bucket: str, prefix: str) -> Any:
    """Publish progress to one key on an interval. A step with no heartbeat says nothing.

    One key, overwritten: the corpus bucket has no `DeleteObject`, so a key per beat is
    permanent litter (A1.3 left four such objects that cannot be removed).
    """
    key = f"{prefix}/heartbeat/a1-8/uniprotkb-release-count.json"
    started = time.time()

    def beat(payload: dict[str, Any]) -> None:
        if client is None:
            return
        try:
            body = dict(payload)
            body["run_started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
            body["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            client.put_object(
                Bucket=bucket, Key=key, Body=json.dumps(body, indent=2, sort_keys=True).encode()
            )
        except Exception as exc:  # losing the diagnosis must not lose the run
            print(f"    heartbeat failed: {type(exc).__name__}: {exc}", flush=True)

    return beat


def load_reading(
    captures: Path, mapping_path: Path
) -> tuple[tuple[selectagents.ListEntry, ...], dict[str, selectagents.MappedEntry]]:
    """Parse the pinned captures and the curated table, refusing anything off-digest."""
    for pin in selectagents.PINS_2024:
        stored = captures / Path(pin.capture).name
        if not stored.exists():
            raise SystemExit(f"missing pinned CFR capture: {stored}")
        if repro.sha256_file(stored) != pin.sha256:
            raise SystemExit(f"{stored.name} does not match its recorded digest; refusing")
    if not mapping_path.exists():
        raise SystemExit(f"missing the curated reading table at {mapping_path} (D-137)")

    entries = selectagents.parse_all(
        (section, (captures / name).read_bytes()) for section, name in SECTION_FILES.items()
    )
    mapping = selectagents.load_mapping(mapping_path)
    return entries, mapping


def resolve(
    captures: Path,
    mapping_path: Path,
    taxdump: Path,
    *,
    toxin_producers: bool,
    alternatives: bool,
) -> tuple[frozenset[int], seeds.Attribution, frozenset[int], dict[str, Any]]:
    entries, mapping = load_reading(captures, mapping_path)
    taxonomy = seeds.Taxonomy.from_taxdump_zip(taxdump)
    taxa = selectagents.seed_taxa(
        entries, mapping, include_toxin_producers=toxin_producers, use_alternatives=alternatives
    )
    denylist = taxa.expand(taxonomy)
    by_entry = selectagents.expand_by_entry(
        entries,
        mapping,
        taxonomy,
        include_toxin_producers=toxin_producers,
        use_alternatives=alternatives,
    )
    # A1.6's number, carried on this pass rather than paid for with a second 182.7 GB read.
    viral = frozenset(taxonomy.descendants(seeds.VIRAL_ROOT))
    provenance = {
        "viral_taxa": len(viral),
        "list_as_of": "2024-06-01",
        "taxdump_pin": "2023-04-01",
        "named_taxa": len(taxa.named),
        "expanded_taxa": len(denylist),
        "reading": {"toxin_producers": toxin_producers, "alternatives": alternatives},
        "cfr_parts": [
            {"title": p.title, "part": p.part, "sha256": p.sha256, "as_of": p.as_of}
            for p in selectagents.PINS_2024
        ],
    }
    return denylist, seeds.Attribution.from_entry_taxa(by_entry), viral, provenance


#: Where the archive is staged. Fixed here rather than derived, because the corpus bucket
#: withholds `s3:DeleteObject`: a key written once is written for good, so it is chosen
#: deliberately and reviewed before the first run rather than discovered afterwards.
STAGED_KEY = "uniprotkb/2023_02/knowledgebase2023_02.tar.gz"


def stage(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> dict[str, Any]:
    """Copy the release archive into the corpus bucket, once, checksummed on the way through.

    Staging rather than re-fetching is what makes the reading switches affordable. The
    toxin-producer and alternative readings (D-137) each want their own count, and without a
    staged copy each one is another 182.7 GB pulled from UniProt; with it, each is an
    in-region read that costs nothing to move. It also pins the bytes: the archive is dated
    and served by its publisher today, but "dated and still served" is a property of their
    FTP server rather than of this audit.

    The digest is computed as the bytes pass, so the object and its checksum come from the
    same read — a second pass to checksum could not prove the first one was of these bytes.
    """
    key = f"{prefix}/{STAGED_KEY}" if prefix else STAGED_KEY
    release = uniprotkb.RELEASE_2023_02
    existing = _staged_size(client, bucket, key)
    if existing == int(release["bytes"]):
        print(f"already staged: s3://{bucket}/{key} ({existing:,} bytes)", flush=True)
        return {"uri": f"s3://{bucket}/{key}", "bytes": existing, "skipped": True}
    if existing is not None:
        raise SystemExit(
            f"s3://{bucket}/{key} exists at {existing:,} bytes, expected {release['bytes']:,}. "
            "The bucket has no DeleteObject, so this cannot be overwritten safely by a "
            "partial earlier run — investigate before writing anything else to this key."
        )

    print(f"staging {release['url']}\n     -> s3://{bucket}/{key}", flush=True)
    started = time.monotonic()
    beat = _heartbeat(client, bucket, prefix)
    request = urllib.request.Request(
        str(release["url"]), headers={"User-Agent": "amazebio-audit/1.0"}
    )
    with (
        urllib.request.urlopen(request, timeout=180) as response,
        uniref.S3PartSink(
            client, bucket, key, part_bytes=args.part_bytes, concurrency=args.upload_concurrency
        ) as sink,
    ):
        last = time.monotonic()
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            sink.write(chunk)
            now = time.monotonic()
            if now - last >= args.heartbeat_seconds:
                done = sink.bytes_written
                beat(
                    {
                        "phase": "stage",
                        "bytes_written": done,
                        "share": done / int(release["bytes"]),
                        "elapsed_seconds": round(now - started, 1),
                    }
                )
                print(
                    f"    staged {done / 2**30:.1f} GiB of "
                    f"{int(release['bytes']) / 2**30:.0f} GiB "
                    f"({done / (now - started) / 2**20:.0f} MiB/s)",
                    flush=True,
                )
                last = now
    described = sink.describe()
    if described["bytes"] != int(release["bytes"]):
        raise SystemExit(
            f"staged {described['bytes']:,} bytes, the publisher serves "
            f"{release['bytes']:,}. A short archive would undercount every taxon in it."
        )
    print(f"  staged {described['bytes']:,} bytes, sha256 {described['sha256']}", flush=True)
    described["skipped"] = False
    return described


@dataclass
class _Source:
    label: str
    handle: Any


def _open_archive(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> _Source:
    """Prefer the staged copy; fall back to the publisher only when told to.

    Reading the staged object keeps the count repeatable and in-region, which is what makes
    a second reading affordable. `--from-url` exists so the very first run can work before
    anything is staged, and so a staging failure does not block the measurement entirely.
    """
    release = uniprotkb.RELEASE_2023_02
    if not args.from_url and client is not None:
        key = f"{prefix}/{STAGED_KEY}" if prefix else STAGED_KEY
        if _staged_size(client, bucket, key) == int(release["bytes"]):
            reader = objectstore.S3RandomRead(client, bucket, key)
            return _Source(f"s3://{bucket}/{key}", reader)
    request = urllib.request.Request(
        str(release["url"]), headers={"User-Agent": "amazebio-audit/1.0"}
    )
    return _Source(str(release["url"]), urllib.request.urlopen(request, timeout=180))


def _staged_size(client: Any, bucket: str, key: str) -> int | None:
    if client is None:
        return None
    try:
        return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
    except Exception:
        return None


def run(args: argparse.Namespace, client: Any, bucket: str, prefix: str) -> int:
    denylist, attribution, viral, provenance = resolve(
        args.captures,
        args.mapping,
        args.taxdump,
        toxin_producers=args.toxin_producers,
        alternatives=args.alternatives,
    )
    print(
        f"the list names {provenance['named_taxa']:,} taxa, expanding to "
        f"{provenance['expanded_taxa']:,}",
        flush=True,
    )
    if args.check_inputs:
        print(json.dumps(provenance, indent=2, sort_keys=True))
        print("inputs resolve; exiting before the archive read as asked", flush=True)
        return 0

    release = uniprotkb.RELEASE_2023_02
    expected = {
        "uniprot_sprot.dat.gz": release["sprot_entries"],
        "uniprot_trembl.dat.gz": release["trembl_entries"],
    }
    args.outdir.mkdir(parents=True, exist_ok=True)
    out_path = args.outdir / "uniprotkb-release-count.json"
    manifest_name = "run-uniprotkb-release-count.json"

    with repro.run(
        "A1.8",
        seed=None,  # one forward read of a pinned archive; nothing here is random
        outdir=args.outdir,
        allow_dirty=args.allow_dirty,
        manifest_name=manifest_name,
    ) as manifest:
        if args.code_commit:
            manifest.parameter("code_commit", args.code_commit)
        manifest.parameter("uniprot_release", release["release"])
        manifest.parameter("uniprot_release_date", release["date"])
        manifest.parameter("archive_url", release["url"])
        manifest.parameter("archive_bytes", release["bytes"])
        manifest.parameter("published_sequences", PUBLISHED_SEQUENCES)
        for key, value in provenance.items():
            manifest.parameter(key if key != "reading" else "list_reading", value)
        manifest.input_file(args.taxdump, role="taxonomy")
        manifest.input_file(args.mapping, role="select-agent-reading-table")

        beat = _heartbeat(client, bucket, prefix)
        per_member: dict[str, Any] = {}
        totals = uniprotkb.TaxonCounts()
        started = time.monotonic()

        source = _open_archive(args, client, bucket, prefix)
        print(f"reading {source.label}", flush=True)
        manifest.parameter("archive_source", source.label)
        with source.handle as stream:
            counted = _Counted(stream)
            outer = gzip.GzipFile(fileobj=counted)
            # Not a `with`: the tar is consumed inside this block and closing it early would
            # close the member handles the scan is still reading from.
            archive = tarfile.open(fileobj=outer, mode="r|")  # noqa: SIM115
            for member in archive:
                if member.name not in expected:
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    raise SystemExit(f"{member.name} is not a readable tar member")
                print(f"reading {member.name} ({member.size:,} bytes)", flush=True)
                counts = uniprotkb.TaxonCounts()
                inner = gzip.GzipFile(fileobj=handle)
                last = time.monotonic()
                for chunk in uniprotkb.iter_member_chunks(inner, args.chunk_bytes):
                    uniprotkb.scan_chunks([chunk], denylist, attribution, counts, viral)
                    now = time.monotonic()
                    if now - last >= args.heartbeat_seconds:
                        elapsed = now - started
                        beat(
                            {
                                "member": member.name,
                                "elapsed_seconds": round(elapsed, 1),
                                "archive_bytes_read": counted.read_bytes,
                                "archive_share": counted.read_bytes / int(release["bytes"]),
                                "entries": counts.entries,
                                "seeded": counts.seeded,
                                "viral": counts.viral,
                            }
                        )
                        print(
                            f"    {counted.read_bytes / 2**30:.1f} GiB of archive, "
                            f"{counts.entries:,} entries, {counts.seeded:,} seeded",
                            flush=True,
                        )
                        last = now
                uniprotkb.verify_whole(counts, expected[member.name], member.name)
                print(
                    f"  {member.name}: {counts.entries:,} entries (matches the release "
                    f"statistic), {counts.seeded:,} seeded",
                    flush=True,
                )
                per_member[member.name] = counts.to_dict()
                totals.merge(counts)
                if len(per_member) == len(expected):
                    break

        missing = sorted(set(expected) - set(per_member))
        if missing:
            raise SystemExit(f"archive ended before these members were read: {missing}")

        elapsed = time.monotonic() - started
        delta = totals.seeded - PUBLISHED_SEQUENCES
        payload: dict[str, Any] = {
            "uniprot_release": release["release"],
            "uniprot_release_date": release["date"],
            "archive_bytes_read": counted.read_bytes,
            "elapsed_seconds": round(elapsed, 1),
            "list_provenance": provenance,
            "published_sequences": PUBLISHED_SEQUENCES,
            "published_source": "D-106, ESM3 version of record: 147K non-viral + 40K viral",
            "sequences": totals.seeded,
            "delta": delta,
            "delta_share": delta / PUBLISHED_SEQUENCES,
            "entries_in_release": totals.entries,
            "by_member": per_member,
            "totals": totals.to_dict(),
            "viral_entries_for_a1_6": {
                "entries": totals.viral,
                "published": "roughly 4M, ESM3 version of record A.6.1 p47",
                "note": (
                    "Carried on this pass because it reads every OX line anyway; a separate "
                    "run would mean a second 182.7 GB read. A1.6 owns what this means for "
                    "its arm. Like the select-agent figure, it validates the reading and not "
                    "that task's UniRef100 seed set."
                ),
            },
            "what_this_checks": (
                "whether the regulation's entries were resolved to the same organisms the lab "
                "resolved them to, at the release the lab used. It does not validate A1.8's "
                "UniRef100 seed set, which counts a different object (D-150)."
            ),
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        manifest.output_file(out_path, role="uniprotkb-release-count")

        print(
            f"\n{totals.seeded:,} UniProtKB sequences at release {release['release']} "
            f"against the published {PUBLISHED_SEQUENCES:,} "
            f"({delta:+,}, {100 * payload['delta_share']:+.1f}%)",
            flush=True,
        )

        if args.upload_results and client is not None:
            key = f"{prefix}/results/a1-8/{out_path.name}"
            client.put_object(Bucket=bucket, Key=key, Body=out_path.read_bytes())
            manifest.output_object(
                f"s3://{bucket}/{key}", bytes=out_path.stat().st_size, role="release-count"
            )
            print(f"  uploaded s3://{bucket}/{key}", flush=True)

    # Outside the block: `repro.run` writes the manifest on exit, so an upload inside it has
    # no file to send. The instance has no shell and nobody can fetch it afterwards (D-150).
    if args.upload_results and client is not None:
        local = args.outdir / manifest_name
        key = f"{prefix}/results/a1-8/{manifest_name}"
        client.put_object(Bucket=bucket, Key=key, Body=local.read_bytes())
        print(f"  uploaded s3://{bucket}/{key}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--captures", type=Path, default=DEFAULT_CAPTURES)
    ap.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    ap.add_argument("--taxdump", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-8"))
    ap.add_argument("--toxin-producers", action="store_true")
    ap.add_argument("--alternatives", action="store_true")
    ap.add_argument("--check-inputs", action="store_true")
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--code-commit")
    ap.add_argument("--chunk-bytes", type=int, default=8 << 20)
    ap.add_argument("--part-bytes", type=int, default=128 << 20)
    ap.add_argument("--upload-concurrency", type=int, default=8)
    ap.add_argument(
        "--stage",
        action="store_true",
        help="copy the release archive into the corpus bucket before counting. Permanent: "
        "the bucket withholds DeleteObject",
    )
    ap.add_argument(
        "--from-url",
        action="store_true",
        help="read from the publisher even if a staged copy exists",
    )
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--heartbeat-seconds", type=float, default=120.0)
    args = ap.parse_args(argv)

    client = None
    bucket = prefix = ""
    if args.s3_uri:
        bucket, _, prefix = args.s3_uri[5:].partition("/")
        prefix = prefix.strip("/")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT,
            config=Config(retries={"max_attempts": 10, "mode": "standard"}),
        )
    try:
        if args.stage or args.stage_only:
            staged = stage(args, client, bucket, prefix)
            if args.stage_only:
                print(json.dumps(staged, indent=2, sort_keys=True))
                return 0
        return run(args, client, bucket, prefix)
    except ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

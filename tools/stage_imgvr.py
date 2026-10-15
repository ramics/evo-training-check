#!/usr/bin/env python3
"""Stage the pinned IMG/VR metadata into object storage, for A1.7.

Two halves, and only one of them needs a credential.

`--inventory` re-fetches JGI's public file listing and checks it against
`policies/captures/jgi-imgvr-inventory.json` and the pins in `amazebio.imgvr`. No token, and
worth running before any staging pass: the listing is dated and mutable, so a changed md5 means
the publisher re-cut a release and the pins are stale.

`--stage` downloads the metadata files for a release, verifies each against the md5 the
publisher published, and uploads it. This needs `$JGI_API_TOKEN`. Four things about it are
dictated by the publisher or by this project's own rules rather than chosen:

**Bearer token in the `Authorization` header.** JGI's API declares exactly one security scheme
(`swagger.json`: apiKey named `Authorization`, in header). The token is read from the
environment and never logged — not in the manifest, not in an error.

**Some releases are on tape.** Every file carries a `file_status`: `RESTORED` means on disk and
directly downloadable, `BACKUP_COMPLETE` means on tape and unavailable until restored by
`POST /request_archived_files/`, which is asynchronous. As of the 2026-10-15 listing the
**2022-09-20** release is `RESTORED` and the **2022-12-20** release is `BACKUP_COMPLETE`, so
auditing both releases — which is what the project owner chose (D-056) — means one of them has
to be requested and waited for. This tool requests and polls rather than failing, because a run
that dies on a tape file would otherwise look like a permissions problem.

**Metadata only.** `amazebio.imgvr.conformance_inputs` decides what is staged: both
sequence-information tables, both host-information tables, the READMEs. 7.9 GB rather than
128.7 GB, because every conformance check is a set operation over accessions and metadata and
none of them reads a base (D-053). `--include-sequence` exists for a later task that needs the
nucleotides, and prints what it would cost before doing it.

**Verify before the upload completes.** The corpus bucket withholds `s3:DeleteObject`, so an
object that completes is permanent and an object claiming to be a release it has not been shown
to be is worse than no object at all. The md5 is computed over the stream and the upload is
aborted on a mismatch — the commitment D-026 made for UniRef, with the difference that here the
expected digest was recorded before this project held any of the bytes (D-054).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import imgvr
from amazebio.repro import run

SEARCH_URL = "https://files.jgi.doe.gov/search/?datasets=Custom_MPI-IMG_VR&x=50"
RESTORE_URL = "https://files.jgi.doe.gov/request_archived_files/"
S3_ENDPOINT = "https://s3.us-east-1.amazonaws.com"
REGION = "us-east-1"
TOKEN_ENV = "JGI_API_TOKEN"

CAPTURE = (
    Path(__file__).resolve().parent.parent / "policies" / "captures" / ("jgi-imgvr-inventory.json")
)

#: File statuses the listing uses. Named here because the difference decides whether a staging
#: pass is a download or a request-and-wait, and because a run that treats the second as a
#: failure reports a tape file as an access problem.
ON_DISK = "RESTORED"
ON_TAPE = "BACKUP_COMPLETE"

_CHUNK = 1 << 22


def _token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(
            f"${TOKEN_ENV} is not set. JGI publishes the IMG/VR inventory without "
            "authentication and withholds the files: every download endpoint returns HTTP 401. "
            "Add the token to the environment's secrets as "
            f"{TOKEN_ENV} and start a new session; see DECISIONS.md D-054."
        )
    return token


def _request(url: str, *, token: str | None = None, data: bytes | None = None) -> Any:
    req = urllib.request.Request(url, data=data)
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=120)


# --------------------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------------------


def fetch_catalog() -> tuple[str, str, list[dict[str, Any]]]:
    """The publisher's current listing, plus the two organism-level ids the download needs.

    `POST /download_files/` is keyed by the organism id and wants the organism's `top_hit` as
    an id *string*; both come from the same search response as the file listing, so they are
    read here rather than hard-coded. Passing the nested `top_hit` object instead of its `_id`
    returns HTTP 500 (D-062).
    """
    with _request(SEARCH_URL) as resp:
        raw = json.loads(resp.read())
    orgs = raw.get("organisms") or []
    if not orgs:
        raise SystemExit(
            "JGI returned no organisms for dataset Custom_MPI-IMG_VR. The dataset identifier "
            "may have changed; it came from the portal's own redirect, not from a guess, so "
            "re-derive it rather than guessing a new one (D-054)."
        )
    out = []
    for f in orgs[0]["files"]:
        out.append(
            {
                "added_date": f["added_date"][:10],
                "directory": f["file_path"].split("/")[-1],
                "file_name": f["file_name"],
                "file_size": f["file_size"],
                "md5sum": f["md5sum"],
                "file_status": f.get("file_status"),
                "_id": f.get("_id"),
            }
        )
    org = orgs[0]
    top_hit = (org.get("top_hit") or {}).get("_id")
    if not org.get("id") or not top_hit:
        raise SystemExit(
            "The search response carries no organism id or no top_hit._id. Both are required "
            "by POST /download_files/ and neither can be guessed; re-derive them from the "
            "portal rather than inventing them (D-062)."
        )
    files = sorted(out, key=lambda x: (x["added_date"], x["directory"], x["file_name"]))
    return org["id"], top_hit, files


def fetch_inventory() -> list[dict[str, Any]]:
    """Just the file listing, for the paths that do not download anything."""
    return fetch_catalog()[2]


def check_inventory() -> int:
    """Compare the live listing against the capture and the pins. Returns a problem count."""
    live = fetch_inventory()
    captured = json.loads(CAPTURE.read_text())["files"]

    def key(f: dict[str, Any]) -> tuple[str, str, str]:
        # Directory is part of the identity, not decoration: AUTO-141612 and AUTO-141623 share
        # the release date 2018-01-24 *and* four file names between them, so a (date, name) key
        # compares one release's file against another's and reports four phantom changes. The
        # first run of this check did exactly that.
        return (f["added_date"], f["directory"], f["file_name"])

    cap = {key(f): f for f in captured}
    problems = 0
    for f in live:
        k = key(f)
        was = cap.get(k)
        if was is None:
            print(f"NEW      {k}: in the listing, absent from the capture")
            problems += 1
            continue
        if was["md5sum"] != f["md5sum"] or was["file_size"] != f["file_size"]:
            print(
                f"CHANGED  {k}: captured {was['md5sum']} ({was['file_size']}) -> "
                f"live {f['md5sum']} ({f['file_size']})"
            )
            problems += 1
    live_keys = {key(f) for f in live}
    for k in cap:
        if k not in live_keys:
            print(f"GONE     {k}: in the capture, absent from the listing")
            problems += 1
    # The pins are the thing that actually matters; the capture is how they are traced.
    cap_live = {key(f): f for f in live}
    for date, release in imgvr.RELEASES.items():
        for pinned in release.files:
            got = cap_live.get((date, pinned.directory, pinned.name))
            if got is None:
                print(f"UNPINNED {date}/{pinned.name}: pinned but not in the live listing")
                problems += 1
            elif got["md5sum"] != pinned.md5:
                print(
                    f"STALE    {date}/{pinned.name}: pinned {pinned.md5}, live {got['md5sum']} "
                    "— the publisher re-cut this release; do not stage against a stale pin"
                )
                problems += 1
    print(f"inventory: {len(live)} files live, {len(captured)} captured, {problems} problems")
    return problems


# --------------------------------------------------------------------------------------
# Tape restore
# --------------------------------------------------------------------------------------


def request_restore(ids: list[str], *, token: str) -> str | None:
    """Ask JGI to bring files back from tape. Returns a request id, or None if not needed."""
    if not ids:
        return None
    body = json.dumps({"ids": ids}).encode()
    try:
        with _request(RESTORE_URL, token=token, data=body) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"restore request failed: HTTP {exc.code}. {exc.read()[:300]!r}. A tape restore is "
            "asynchronous and can take hours; it is not a permissions failure."
        ) from exc
    rid = payload.get("request_id") or payload.get("id")
    print(f"[imgvr] restore requested for {len(ids)} file(s); request_id={rid}")
    return rid


def wait_for_restore(rid: str, *, token: str, timeout_minutes: float, poll: float) -> bool:
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        with _request(f"{RESTORE_URL}requests/{rid}", token=token) as resp:
            state = json.loads(resp.read())
        status = str(state.get("status", "")).upper()
        print(f"[imgvr] restore {rid}: {status}", flush=True)
        if status in ("READY", "COMPLETE", "COMPLETED", "RESTORED"):
            return True
        if status in ("FAILED", "CANCELLED"):
            return False
        time.sleep(poll)
    print(
        f"[imgvr] restore {rid} not ready within {timeout_minutes:g} min. This is normal for "
        "tape; re-run --stage later and it will pick up the restored files."
    )
    return False


# --------------------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------------------


def stage_key(date: str, name: str, *, prefix: str) -> str:
    return f"{prefix}/imgvr/{date}/{name}" if prefix else f"imgvr/{date}/{name}"


def download_verify_upload(
    file: imgvr.ReleaseFile,
    file_id: str,
    *,
    date: str,
    token: str,
    client: Any,
    bucket: str,
    prefix: str,
    dry_run: bool,
    spool: Path,
    organism_id: str,
    top_hit: str,
) -> dict[str, Any]:
    """Fetch one file, verify it against the publisher's md5, and upload only on a match.

    The publisher serves files as a zip stream and not as raw bytes: `POST /download_files/`
    returns `application/zip` holding the requested files plus a manifest, and the documented
    single-file `GET /download_files/<id>/` answers 404 for every IMG/VR file (D-062). One file
    is requested per call anyway, so the zip holds one member and the spool stays bounded by
    that file rather than by the 7.9 GB release.
    """
    key = stage_key(date, file.name, prefix=prefix)
    url, body = imgvr.download_request([file_id], organism_id=organism_id, top_hit=top_hit)
    if dry_run:
        return {"key": key, "bytes": file.bytes, "verified": None, "skipped": "dry-run"}

    # Spool to disk rather than to a list of chunks. The largest file staged here is the
    # 5.0 GB sequence-information table, and accumulating it in memory and then joining it
    # peaks at roughly twice that — more than the session container has. Disk is the cheap
    # resource and the file is deleted as soon as it is uploaded.
    with tempfile.NamedTemporaryFile(dir=spool, suffix=".zip", delete=False) as tmp:
        spooled = Path(tmp.name)
        try:
            with _request(url, token=token, data=json.dumps(body).encode()) as resp:
                while chunk := resp.read(_CHUNK):
                    tmp.write(chunk)
            tmp.flush()
            with zipfile.ZipFile(spooled) as zf:
                members = [
                    n for n in zf.namelist() if PurePosixPath(n).name == file.name
                ]
                if len(members) != 1:
                    raise SystemExit(
                        f"{date}/{file.name}: the download zip holds {len(members)} members "
                        f"with that name, out of {zf.namelist()}. Nothing uploaded."
                    )
                member = members[0]
                # Two passes over the member, both streaming: verify first, upload second.
                # The order is not a preference. The corpus bucket has no s3:DeleteObject, so
                # an object claiming to be a release it has not been shown to be is permanent
                # and worse than no object at all.
                #
                # md5 because that is the digest the publisher publishes; a sha256 of ours is
                # recorded alongside it so later passes can verify without re-deriving theirs.
                md5 = hashlib.md5()
                sha = hashlib.sha256()
                read = 0
                with zf.open(member) as fh:
                    while chunk := fh.read(_CHUNK):
                        md5.update(chunk)
                        sha.update(chunk)
                        read += len(chunk)
                got = md5.hexdigest()
                if got != file.md5:
                    raise SystemExit(
                        f"{file.name}: md5 {got} does not match the publisher's published "
                        f"{file.md5}. Nothing uploaded."
                    )
                if read != file.bytes:
                    raise SystemExit(
                        f"{file.name}: {read} bytes read, listing says {file.bytes}. "
                        "Nothing uploaded."
                    )
                # upload_fileobj, not put_object: a single PUT is capped at 5 GiB and the
                # largest file here is within a few hundred megabytes of that ceiling. This
                # splits into a multipart upload on its own, and an interrupted multipart
                # upload never becomes a visible object — which is what the no-delete bucket
                # requires. Streaming the member also keeps the extracted copy off disk.
                with zf.open(member) as fh:
                    client.upload_fileobj(fh, bucket, key)
        finally:
            spooled.unlink(missing_ok=True)
    print(f"[imgvr] staged {key}  {read/1e9:.3f} GB  md5 ok", flush=True)
    return {
        "key": key,
        "bytes": read,
        "md5": got,
        "sha256": sha.hexdigest(),
        "verified": True,
        "verified_against": "publisher md5 (JGI file listing)",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--inventory",
        action="store_true",
        help="check the live listing against the capture and pins; needs no token",
    )
    ap.add_argument("--stage", action="store_true", help="download, verify and upload")
    ap.add_argument(
        "--release",
        action="append",
        choices=sorted(imgvr.RELEASES),
        help="repeatable; default is both v4 candidates, per D-056",
    )
    ap.add_argument(
        "--include-sequence",
        action="store_true",
        help="also stage nucleotides and proteins (D-053 argues against)",
    )
    ap.add_argument("--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"))
    ap.add_argument("--outdir", default="artifacts/a1-7")
    ap.add_argument("--restore-timeout-minutes", type=float, default=20.0)
    ap.add_argument("--poll-seconds", type=float, default=60.0)
    ap.add_argument(
        "--spool-dir",
        default=os.environ.get("TMPDIR") or "/tmp",
        help="where each file is spooled while its md5 is checked; needs room for the "
        "largest single file (5.0 GB), not for the whole release",
    )
    ap.add_argument("--dry-run", action="store_true", help="resolve and plan; transfer nothing")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    if not (args.inventory or args.stage):
        ap.error("pass --inventory or --stage")

    if args.inventory and not args.stage:
        return 1 if check_inventory() else 0

    releases = args.release or list(imgvr.V4_CANDIDATES)
    if not args.s3_uri:
        raise SystemExit("need --s3-uri or $AMAZEBIO_S3_URI")
    bucket, _, prefix = args.s3_uri[5:].partition("/")
    prefix = prefix.rstrip("/")
    token = _token()

    import boto3

    client = boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT)
    organism_id, top_hit, live = fetch_catalog()
    outdir = Path(args.outdir)

    # Fail before the first byte rather than part-way through the 5 GB table. Only one file
    # is on disk at a time, so the requirement is the largest file plus headroom — not the
    # 7.9 GB release total.
    spool = Path(args.spool_dir)
    spool.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        need = max(
            f.bytes
            for date in releases
            for f in (
                imgvr.release_on(date).files
                if args.include_sequence
                else imgvr.conformance_inputs(date)
            )
        )
        free = shutil.disk_usage(spool).free
        if free < need + (1 << 30):
            raise SystemExit(
                f"{spool} has {free/1e9:.1f} GB free; the largest single file is "
                f"{need/1e9:.1f} GB and this spools one at a time. Point --spool-dir at a "
                "filesystem with room, or free some."
            )

    with run("A1.7", seed=None, outdir=outdir, allow_dirty=args.allow_dirty) as m:
        m.parameter("releases", releases)
        m.parameter("spool_dir", str(spool))
        m.parameter("include_sequence", args.include_sequence)
        m.parameter("verified_against", "publisher md5 recorded before acquisition (D-054)")
        m.note(
            "Metadata only unless --include-sequence: every conformance check is a set "
            "operation over accessions and metadata (D-053)."
        )
        staged = []
        for date in releases:
            release = imgvr.release_on(date)
            wanted = release.files if args.include_sequence else imgvr.conformance_inputs(date)
            index = {(f["added_date"], f["directory"], f["file_name"]): f for f in live}
            on_tape = [
                index[(date, f.directory, f.name)]["_id"]
                for f in wanted
                if index.get((date, f.directory, f.name), {}).get("file_status") == ON_TAPE
            ]
            if on_tape and not args.dry_run:
                rid = request_restore(on_tape, token=token)
                if rid and not wait_for_restore(
                    rid,
                    token=token,
                    timeout_minutes=args.restore_timeout_minutes,
                    poll=args.poll_seconds,
                ):
                    m.note(
                        f"{date}: {len(on_tape)} file(s) still on tape when this run ended; "
                        "re-run --stage to pick them up. Not an error."
                    )
                    continue
            elif on_tape:
                print(f"[imgvr] {date}: {len(on_tape)} file(s) on tape, would be requested")
            for f in wanted:
                rec = index.get((date, f.directory, f.name))
                if rec is None:
                    raise SystemExit(f"{date}/{f.name} is pinned but absent from the listing")
                if rec["md5sum"] != f.md5:
                    raise SystemExit(
                        f"{date}/{f.name}: live md5 {rec['md5sum']} != pinned {f.md5}; the "
                        "publisher re-cut this release. Refusing to stage against a stale pin."
                    )
                row = download_verify_upload(
                    f,
                    rec["_id"],
                    date=date,
                    token=token,
                    client=client,
                    bucket=bucket,
                    prefix=prefix,
                    dry_run=args.dry_run,
                    spool=spool,
                    organism_id=organism_id,
                    top_hit=top_hit,
                )
                row["release"] = date
                row["role"] = f.role
                staged.append(row)
                if row.get("verified"):
                    m.output_object(
                        f"s3://{bucket}/{row['key']}",
                        bytes=row["bytes"],
                        sha256=row.get("sha256"),
                        role=f.role,
                    )
        manifest = outdir / "staged.json"
        manifest.write_text(json.dumps({"staged": staged}, indent=2, sort_keys=True) + "\n")
        m.output_file(manifest, role="staging-manifest")
        total = sum(r["bytes"] for r in staged)
        print(f"[imgvr] {len(staged)} file(s), {total/1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

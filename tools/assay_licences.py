"""Acquire the licence evidence B2.4's register cites, and write it to `assays/licences.json`.

This is the online half of B2.4 and it is deliberately separate from the register itself.
`assay_register.py` runs offline against the file this writes, so the register regenerates from
pinned inputs the way `AGENTS.md` requires; a tool that fetched the web inside `repro.run` would
produce a different artefact every time the publishers changed their metadata.

Two kinds of evidence, because the licence question has two halves and conflating them is the
error this file exists to prevent:

**What we actually downloaded.** The pinned ProteinGym release is a Zenodo deposit, and the
deposit's own licence field is the grant under which its bytes reached this project. That is the
licence the pipeline relies on. It is recorded with the deposit's file list so the pinned files
can be matched against it by name and size.

**What each assay came from originally.** Every assay carries the DOI of the study that produced
it, and Crossref holds the licence the *publisher itself* deposited for that article. That is not
the same statement as a licence on the data — an article's CC-BY says nothing directly about the
supplementary table the authors uploaded — and the register says so rather than quietly treating
one as the other. It is recorded because a reader tracing an assay to its source needs it, and
because a restrictive one (the no-derivatives and non-commercial cases here) is worth seeing.

Crossref's licence block is the publisher's own deposited metadata rather than a third party's
summary of it, which is why it is used in place of scraping article pages — several of these
publishers serve a challenge or a 403 to this container, and a scrape that worked today would
not be reproducible anyway.

Run it by hand when the assay set changes; CI never does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from amazebio import proteingym  # noqa: E402

EVIDENCE = REPO / "assays" / "licences.json"
REGISTER = REPO / "artifacts" / "b2-2" / "register.json"

#: The Zenodo record the pinned release was downloaded from. ProteinGym's GitHub repository
#: carries the code; the data lives here, and this is the deposit whose licence governs it.
ZENODO_RECORD = "15293562"

CROSSREF = "https://api.crossref.org/works/"
ZENODO = "https://zenodo.org/api/records/"

#: Sent so the publishers' APIs can identify the caller, as Crossref's terms of use ask.
AGENT = "amazebio/0.1 (independent audit of training-data filtering)"


def fetch(url: str, *, timeout: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def zenodo_deposit(record: str, *, verify: set[str] | None = None) -> dict[str, Any]:
    """The deposit's licence and file list, as Zenodo publishes them.

    `verify` names files to download and hash. That matters more than it looks: the pinned
    release was fetched from the maintainers' own server, which states no licence, while the
    deposit that does state one is a different URL. Matching sizes make them *probably* the same
    bytes; a matching digest makes the deposit's grant demonstrably the grant on the files this
    project holds, which is the whole claim B2.4 rests on.
    """
    doc = fetch(ZENODO + record)
    meta = doc.get("metadata", {})
    files = []
    for entry in doc.get("files", []):
        name = entry.get("key")
        row: dict[str, Any] = {"name": name, "size": entry.get("size")}
        link = (entry.get("links") or {}).get("self")
        if verify and name in verify and link:
            print(f"  hashing {name} ({entry.get('size')} bytes)", file=sys.stderr)
            row["sha256"] = sha256_url(link)
        files.append(row)
    return {
        "record": record,
        "url": f"https://zenodo.org/records/{record}",
        "doi": doc.get("doi"),
        "title": meta.get("title"),
        "publication_date": meta.get("publication_date"),
        "access_right": meta.get("access_right"),
        "license": (meta.get("license") or {}).get("id"),
        "files": sorted(files, key=lambda f: f["name"] or ""),
    }


def sha256_url(url: str, *, chunk: int = 1 << 20) -> str:
    """Stream a file and return its digest, without holding it in memory."""
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=600) as response:
        while block := response.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def crossref_work(doi: str) -> dict[str, Any]:
    """One article's publisher-deposited metadata, or the reason it could not be read."""
    try:
        msg = fetch(CROSSREF + urllib.parse.quote(doi, safe=""))["message"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        return {"doi": doi, "retrieved": False, "blocker": f"{type(exc).__name__}: {exc}"}
    issued = (msg.get("issued") or {}).get("date-parts") or [[None]]
    return {
        "doi": doi,
        "retrieved": True,
        "publisher": msg.get("publisher"),
        "container": (msg.get("container-title") or [None])[0],
        "title": (msg.get("title") or [None])[0],
        "year": issued[0][0],
        # Every licence the publisher deposited, with the version of the work it applies to.
        # `vor` is the version of record, `am` the accepted manuscript, `tdm` text and data
        # mining; a deposit can carry several and they can disagree, so none is collapsed away.
        "licenses": sorted(
            (
                {"url": entry.get("URL"), "content_version": entry.get("content-version")}
                for entry in (msg.get("license") or [])
            ),
            key=lambda entry: (entry["url"] or "", entry["content_version"] or ""),
        ),
    }


def dois(register: dict[str, Any]) -> list[str]:
    return sorted({a["doi"] for a in register["assays"] if a.get("doi")})


def pinned_digests() -> dict[str, str]:
    """Every file the pinned release names, by name, whether or not it carries a version."""
    return {**proteingym.RELEASE.files, **proteingym.RELEASE.unversioned}


def deposit_match(deposit: dict[str, Any], pinned: dict[str, str]) -> list[dict[str, Any]]:
    """Per pinned file, how strongly the deposit is established to be the same bytes."""
    by_name = {f["name"]: f for f in deposit["files"]}
    rows = []
    for name, digest in sorted(pinned.items()):
        there = by_name.get(name)
        if there is None:
            rows.append({"file": name, "in_deposit": False, "match": "not in the deposit"})
            continue
        if there.get("sha256"):
            same = there["sha256"] == digest
            rows.append(
                {
                    "file": name,
                    "in_deposit": True,
                    "match": "digest" if same else "DIGESTS DIFFER",
                    "deposit_sha256": there["sha256"],
                    "pinned_sha256": digest,
                }
            )
            continue
        rows.append(
            {
                "file": name,
                "in_deposit": True,
                "match": "size only",
                "deposit_size": there.get("size"),
                "caveat": "not hashed, so the deposit is the same file by name and size only",
            }
        )
    return rows


def acquire(
    register: dict[str, Any], *, pause: float = 0.4, verify: set[str] | None = None
) -> dict[str, Any]:
    works = []
    for doi in dois(register):
        works.append(crossref_work(doi))
        print(f"  {'ok  ' if works[-1]['retrieved'] else 'FAIL'} {doi}", file=sys.stderr)
        time.sleep(pause)
    deposit = zenodo_deposit(ZENODO_RECORD, verify=verify)
    pinned = pinned_digests()
    return {
        "retrieved_on": dt.date.today().isoformat(),
        "what_this_is": (
            "licence evidence for B2.4, acquired by tools/assay_licences.py. The deposit block "
            "is the grant under which the pinned release reached this project; the works block "
            "is each source article's publisher-deposited licence, which is evidence about the "
            "article and not directly about the assay data it reports"
        ),
        "deposit": deposit,
        "release": {
            "name": "ProteinGym",
            "version": proteingym.RELEASE.version,
            "downloaded_from": proteingym.RELEASE.base_url,
            "note": (
                "the pinned files were fetched from the maintainers' own server, which states "
                "no licence. The deposit above is the licensed publication of the same release; "
                "`deposit_match` is the evidence that they are the same bytes"
            ),
            "files": [{"name": n, "sha256": d} for n, d in sorted(pinned.items())],
        },
        "deposit_match": deposit_match(deposit, pinned),
        "works": works,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=EVIDENCE, type=Path)
    parser.add_argument("--register", default=REGISTER, type=Path)
    parser.add_argument(
        "--verify",
        action="append",
        default=None,
        help=(
            "a deposit file to download and hash, so the licensed deposit is established to be "
            "the same bytes as the pinned copy rather than the same name and size. Repeatable."
        ),
    )
    args = parser.parse_args(argv)

    register = json.loads(args.register.read_text())
    evidence = acquire(register, verify=set(args.verify or ()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=1, sort_keys=True) + "\n")

    unread = [w["doi"] for w in evidence["works"] if not w["retrieved"]]
    print(f"wrote {args.out}: {len(evidence['works'])} works, {len(unread)} unreadable")
    for doi in unread:
        print(f"  unreadable: {doi}")
    for row in evidence["deposit_match"]:
        print(f"  {row['file']}: {row['match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

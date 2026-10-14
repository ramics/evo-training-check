#!/usr/bin/env python3
"""Validate the policy evidence store in `policies/`.

`DESIGN.md` §B1 step 0 says to verify every exclusion policy from primary sources and to
trust no secondary source, `DESIGN.md` included. The failure mode that rule guards against
is a quotation that was never checked against the document it claims to come from — a
paraphrase hardening into a citation, or a half-remembered sentence acquiring quote marks.
`DESIGN.md` §7 requires Phase A to be airtight because it names real laboratories.

So this tool does three things:

1. Every source in `policies/sources.json` must exist on disk at the recorded SHA-256, or be
   explicitly marked as not retrieved.
2. Every quote in a policy file must cite a source id that exists and is retrieved.
3. **Every quote must literally appear in the source it cites.** Quotes are matched against
   the captured bytes — PDF text included — after normalisation. A quote that cannot be found
   fails the build.

Rule 3 is the one that matters. It means no claim in this store can drift from its evidence
without CI noticing.

    python3 tools/policies.py            # validate
    python3 tools/policies.py --verbose  # also list what was checked

Quotes are written in policy files as a blockquote preceded by a citation marker:

    [source: S-EVO1-PREPRINT, p32]
    > For IMG/VR, sequences were retained only if they were labeled as "High-confidence"

A `[source: ...]` marker must appear within 3 lines above each blockquote block. Prose may
mention a source id inline without a blockquote; that is not a quote and is not checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

REPO = pathlib.Path(__file__).resolve().parent.parent
POLICIES = REPO / "policies"
SOURCES = POLICIES / "sources.json"

MARKER = re.compile(r"\[source:\s*([A-Z0-9\-]+)((?:\s*,\s*[^\]]+)?)\]")
MARKER_LOOKBACK = 3

# PDF text extraction introduces artefacts that are not differences in wording: soft
# hyphenation across line breaks, ligatures, and non-ASCII punctuation. Normalising both
# sides lets the check catch wording errors without drowning in typography.
# Written as escapes: a table of ambiguous characters is the one place where spelling them
# literally hides the intent (and trips the linter's ambiguous-character rule).
LIGATURES = {
    "\ufb01": "fi",  # fi
    "\ufb02": "fl",  # fl
    "\ufb00": "ff",  # ff
    "\ufb03": "ffi",  # ffi
    "\ufb04": "ffl",  # ffl
    "\ufb05": "ft",  # long s-t
    "\ufb06": "st",  # st
}
PUNCT = {
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
    "\u00a0": " ",  # no-break space
    "\u2032": "'",  # prime
}


class PolicyError(Exception):
    pass


def normalise(text: str) -> str:
    """Fold away typography so a quote matches the source's wording, not its layout.

    Case is significant, and used to be folded. X1.4 removed the fold: the one error
    hand-verification caught in A0.3's quotations was a changed capital, and a check that
    lowercases both sides cannot catch the class of error that has actually occurred here.
    Turning it on found a second instance in `corpora.md` that nobody had noticed
    (DECISIONS.md D-023). Layout artefacts do not change case, so nothing is lost.
    """
    text = unicodedata.normalize("NFKC", text)
    for a, b in {**LIGATURES, **PUNCT}.items():
        text = text.replace(a, b)
    # join words hyphenated across a line break: "classifi- cation" -> "classification"
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def match_key(text: str) -> str:
    """`normalise`, with every space removed. Use this to compare a quote to a source.

    PDF extraction from justified type drops spaces between words — Evo 1's appendix comes out
    as `thoseonlyassigneduptothelevelof`. A quote written as the paper *renders* then fails
    against a source that extracts run-together, which pushed `corpora.md` into quoting the
    mangled form and apologising for it in a parenthetical. Spacing is layout, so it is folded
    here and a quotation may be written as it reads on the page.

    Case is not folded, and nor is wording: `at least twice` still differs from `at least
    three times`, and `19 families` from `18 families`. What is lost is the ability to detect a
    missing or added space, which is not a difference in wording.
    """
    return re.sub(r"\s+", "", normalise(text))


def extract(path: pathlib.Path) -> str:
    """Full text of a capture. PDFs are extracted page by page."""
    if path.suffix.lower() != ".pdf":
        return path.read_text(errors="replace")
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        raise PolicyError(
            "pypdf is required to verify quotes against PDF sources; it is pinned in pixi.toml"
        ) from exc
    import logging
    import warnings

    # pypdf logs font-encoding complaints for every embedded Type1 font. They say nothing
    # about whether the text extracted correctly, and they bury the actual result in CI.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources() -> dict[str, dict]:
    if not SOURCES.exists():
        raise PolicyError(f"missing {SOURCES.relative_to(REPO)}")
    raw = json.loads(SOURCES.read_text())
    sources: dict[str, dict] = {}
    for entry in raw["sources"]:
        for field in ("id", "status", "title", "url"):
            if field not in entry:
                raise PolicyError(f"source {entry.get('id', '?')}: missing field {field!r}")
        if entry["status"] not in ("retrieved", "retrieved_not_stored", "unretrieved"):
            raise PolicyError(f"{entry['id']}: unknown status {entry['status']!r}")
        if entry["id"] in sources:
            raise PolicyError(f"duplicate source id {entry['id']}")
        sources[entry["id"]] = entry
    return sources


def find_quotes(path: pathlib.Path) -> list[tuple[int, str, str, str]]:
    """Return (line_no, source_id, locator, quote_text) for each blockquote in a policy file."""
    lines = path.read_text().splitlines()
    quotes: list[tuple[int, str, str, str]] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith(">"):
            i += 1
            continue
        start = i
        block: list[str] = []
        while i < len(lines) and (lines[i].startswith(">") or not lines[i].strip()):
            if lines[i].startswith(">"):
                block.append(lines[i].lstrip("> ").rstrip())
            elif block and i + 1 < len(lines) and lines[i + 1].startswith(">"):
                block.append("")  # blank line inside a multi-paragraph quote
            else:
                break
            i += 1
        marker = None
        for back in range(1, MARKER_LOOKBACK + 1):
            if start - back < 0:
                break
            m = MARKER.search(lines[start - back])
            if m:
                marker = m
                break
        if marker is None:
            raise PolicyError(
                f"{path.name}:{start + 1}: blockquote with no [source: ...] marker within "
                f"{MARKER_LOOKBACK} lines above it. Every quote must cite its source."
            )
        locator = marker.group(2).lstrip(", ").strip()
        quotes.append((start + 1, marker.group(1), locator, " ".join(block).strip()))
    return quotes


def validate(verbose: bool = False) -> list[str]:
    problems: list[str] = []
    sources = load_sources()

    # 1. sources resolve and match their recorded checksum
    text_cache: dict[str, str] = {}
    for sid, entry in sources.items():
        if entry["status"] != "retrieved":
            continue
        capture = entry.get("capture")
        if not capture:
            problems.append(f"{sid}: status 'retrieved' but no capture path")
            continue
        path = REPO / capture
        if not path.exists():
            problems.append(f"{sid}: capture {capture} does not exist")
            continue
        if "sha256" in entry:
            actual = sha256_file(path)
            if actual != entry["sha256"]:
                problems.append(
                    f"{sid}: {capture} has changed since it was recorded "
                    f"(sha256 {actual[:12]}... != {entry['sha256'][:12]}...). "
                    "Re-verify every quote citing it before updating the checksum."
                )
                continue
        try:
            text_cache[sid] = match_key(extract(path))
        except PolicyError as exc:
            problems.append(f"{sid}: {exc}")

    # 2 and 3. quotes cite a usable source, and literally appear in it
    checked = 0
    for policy in sorted(POLICIES.glob("*.md")):
        if policy.name == "README.md":
            continue
        try:
            quotes = find_quotes(policy)
        except PolicyError as exc:
            problems.append(str(exc))
            continue
        for line_no, sid, locator, quote in quotes:
            where = f"{policy.name}:{line_no}"
            if sid not in sources:
                problems.append(f"{where}: cites unknown source {sid}")
                continue
            status = sources[sid]["status"]
            if status != "retrieved":
                problems.append(
                    f"{where}: quotes {sid}, whose status is '{status}'. A quote may only "
                    "cite a source that was actually retrieved and stored."
                )
                continue
            if sid not in text_cache:
                continue  # already reported above
            if not quote:
                problems.append(f"{where}: empty quote")
                continue
            if match_key(quote) not in text_cache[sid]:
                problems.append(
                    f"{where}: quoted text does not appear in {sid}"
                    + (f" ({locator})" if locator else "")
                    + ". Either the wording is wrong or the source is. Check the capture."
                )
            else:
                checked += 1
                if verbose:
                    print(f"  ok {where} -> {sid} {locator}".rstrip())

    if verbose:
        retrieved = sum(1 for e in sources.values() if e["status"] == "retrieved")
        pending = sorted(k for k, e in sources.items() if e["status"] == "unretrieved")
        print(f"\n{len(sources)} sources ({retrieved} retrieved), {checked} quotes verified")
        if pending:
            print("still unretrieved: " + ", ".join(pending))

    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    try:
        problems = validate(args.verbose)
    except PolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("policies: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

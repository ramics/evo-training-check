#!/usr/bin/env python3
"""Validate `tasks/DECISIONS.md` — the log's identifiers, not its judgement.

    python3 tools/decisions.py            # validate
    python3 tools/decisions.py --verbose  # also list every citation site

CI runs this. `tools/board.py --check` validates the task graph and never looks at the
decisions log, which is how the log's one silent failure mode survived: two tracks appending at
once both take the next free number, and because the appends are to different parts of the file
they can merge cleanly while colliding semantically. `AGENTS.md` documents the renumbering
protocol for exactly that, and it is a protocol a person has to remember at push time, after the
entry is written and its number is already in a commit message. This check makes the collision
deterministic rather than a thing git happens to notice.

Three failures are fatal, because none of them has a legitimate instance:

* **A duplicate ID.** Every citation of that number becomes ambiguous, and `AGENTS.md`'s fix is
  to move the entry cited from fewer places — which can mean rewriting citations in `src/`. The
  cost of the fix rises with every commit, so it needs catching on the push that causes it.
* **A dangling citation.** A `D-NNN` cited from the repo with no entry behind it. Usually a typo
  or a citation of a number that was renumbered away; either way the reasoning a reader is sent
  to find is not there.
* **A missing or future date.** The log is a chronology and several entries are expected to be
  cited in the write-up; an entry that cannot be placed in time cannot be cited as evidence of
  when a threshold was fixed, which is the whole point of recording it before looking.

Two things are reported but do not fail, deliberately. A **gap** in the sequence is a smell
rather than an error, and in an append-only log it cannot be filled, so failing on one would
block work to no purpose. An entry **out of numeric order** is a renumbering artefact — D-041
is the worked example — and the `Numbering:` line is what resolves it.

What this does not check: whether an entry records its rejected alternatives, or carries a
`Consequence`, or uses the template's field names. Those are matters of judgement that the
later entries vary on deliberately, and a checker that failed on them would be enforcing a
house style rather than catching a defect.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LOG = REPO / "tasks" / "DECISIONS.md"

#: Where a decision may be cited from. `.pixi/` is excluded because vendored package data
#: contains version strings shaped like a decision id that cite nothing. Note the shape is not
#: written out anywhere in this file: this checker scans the repo including `tools/`, so an
#: example id in a comment here is a citation, and it reported itself as dangling when it was.
CITING_DIRS = ("src", "tools", "tasks", "metrics", "policies")
#: `tests/` is deliberately NOT scanned for citations. A test of this checker has to be free to
#: name ids that do not exist — that is what it is testing — and `tests/test_decisions.py`
#: reported itself as dangling when the directory was in scope. The cost is accepted: a test
#: citing a decision in a docstring is not checked, and a dangling citation there is the least
#: harmful kind, because no reader is sent to the log by a fixture.
CITING_FILES = ("DESIGN.md", "README.md", "AGENTS.md")

HEADING = re.compile(r"^### (D-\d+)\b(.*)$", re.M)
CITATION = re.compile(r"\bD-(\d{3,})\b")
DATE = re.compile(r"^- \*\*Date:\*\*\s*(\S+)", re.M)
#: The `Numbering:` line names a number this entry used to carry. It is a historical pointer,
#: not a citation, so it must not be required to resolve to an entry.
NUMBERING = re.compile(r"^- \*\*Numbering:\*\*", re.M)


def _strip_fenced(text: str) -> str:
    """Drop fenced code blocks, so the entry-format template's `D-00N` is not read as a cite."""
    return re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)


def entries(text: str) -> list[tuple[str, str]]:
    """Each entry as `(id, body)`, in file order. Body runs to the next heading or the end."""
    marks = [(m.group(1), m.start(), m.end()) for m in HEADING.finditer(text)]
    out = []
    for i, (eid, _, end) in enumerate(marks):
        stop = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append((eid, text[end:stop]))
    return out


def citation_sites(verbose: bool = False) -> dict[str, list[str]]:
    """Every `D-NNN` cited from the repo, mapped to the places citing it."""
    sites: dict[str, list[str]] = {}
    paths: list[pathlib.Path] = []
    for d in CITING_DIRS:
        root = REPO / d
        if root.is_dir():
            paths.extend(p for p in root.rglob("*") if p.is_file())
    paths.extend(REPO / f for f in CITING_FILES if (REPO / f).is_file())

    for path in sorted(paths):
        if path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"}:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_log = path == LOG
        for line_no, line in enumerate(_strip_fenced(body).splitlines(), start=1):
            # Inside the log itself, a Numbering line points at a retired number on purpose.
            if is_log and NUMBERING.match(line):
                continue
            for m in CITATION.finditer(line):
                where = f"{path.relative_to(REPO)}:{line_no}"
                sites.setdefault(f"D-{m.group(1)}", []).append(where)
    if verbose:
        for eid, where in sorted(sites.items()):
            print(f"  {eid} cited from {len(where)} place(s)")
    return sites


def validate(text: str, sites: dict[str, list[str]], today: dt.date) -> tuple[list[str], list[str]]:
    """`(fatal, notes)`. Fatal fails CI; notes are reported and do not."""
    fatal: list[str] = []
    notes: list[str] = []
    found = entries(text)

    seen: dict[str, int] = {}
    for eid, _ in found:
        seen[eid] = seen.get(eid, 0) + 1
    for eid, n in sorted(seen.items()):
        if n > 1:
            cited = len(sites.get(eid, []))
            fatal.append(
                f"{eid} appears {n} times — every citation of it is ambiguous, and it is cited "
                f"from {cited} place(s). Renumber one per AGENTS.md: move the entry cited from "
                f"fewer places, and leave a `Numbering:` line in it."
            )

    for eid, body in found:
        m = DATE.search(body)
        if not m:
            fatal.append(f"{eid} has no `**Date:**` line, so it cannot be placed in time")
            continue
        try:
            when = dt.date.fromisoformat(m.group(1))
        except ValueError:
            fatal.append(f"{eid} has an unparseable date {m.group(1)!r}; expected YYYY-MM-DD")
            continue
        if when > today:
            fatal.append(f"{eid} is dated {when}, which is in the future (today is {today})")

    known = set(seen)
    for eid, where in sorted(sites.items()):
        if eid not in known:
            shown = ", ".join(where[:4]) + (" …" if len(where) > 4 else "")
            fatal.append(f"{eid} is cited but has no entry — cited from {shown}")

    numbers = sorted(int(e[2:]) for e in known)
    if numbers:
        missing = [n for n in range(1, numbers[-1] + 1) if n not in set(numbers)]
        if missing:
            notes.append(
                "gaps in the sequence: "
                + ", ".join(f"D-{n:03d}" for n in missing)
                + " — not an error, and not fillable in an append-only log"
            )
        order = [int(e[2:]) for e, _ in found]
        out_of_order = [f"D-{n:03d}" for a, n in itertools.pairwise(order) if n < a]
        if out_of_order:
            notes.append(
                "out of numeric order (renumbering artefact; the `Numbering:` line resolves it): "
                + ", ".join(out_of_order)
            )
    return fatal, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true", help="list every citation site")
    args = ap.parse_args()

    if not LOG.is_file():
        print(f"problem: {LOG} not found", file=sys.stderr)
        return 1

    text = LOG.read_text(encoding="utf-8")
    sites = citation_sites(verbose=args.verbose)
    fatal, notes = validate(text, sites, dt.date.today())

    for p in fatal:
        print(f"problem: {p}", file=sys.stderr)

    count = len(entries(text))
    cited = sum(1 for e in sites if e.startswith("D-"))
    print(f"checked {count} decisions, {cited} cited, {len(fatal)} problems")
    for n in notes:
        print(f"  note: {n}")

    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())

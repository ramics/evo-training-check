"""Tests for `tools/decisions.py` — the decisions log's identifier checks.

The failure this guards against is specific and it happened twice in one day: two tracks append
an entry at the same time, both take the next free number, and the appends merge cleanly while
colliding semantically. `AGENTS.md` has a renumbering protocol for it, and a protocol a person
has to remember at push time is not a mechanism. So what is tested here is that the collision is
caught, and — just as important — that the checker does not fail on the log's several legitimate
oddities, because a checker that cries wolf on a renumbering artefact gets switched off.

The real log is also run through the checker in one test, so a change that would start failing
CI on the committed log fails here first, with a readable diff instead of a red pipeline.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "decisions.py"
_spec = importlib.util.spec_from_file_location("decisions_under_test", _PATH)
decisions = importlib.util.module_from_spec(_spec)
sys.modules["decisions_under_test"] = decisions
_spec.loader.exec_module(decisions)

TODAY = dt.date(2026, 10, 19)


def _entry(eid: str, date: str = "2026-10-01", body: str = "") -> str:
    return f"\n### {eid} — a title\n- **Date:** {date}\n- **Task:** X1.1\n{body}"


def _log(*entries: str) -> str:
    return "# Decisions\n\nAppend-only. Newest at the bottom.\n" + "".join(entries)


def test_a_clean_log_passes() -> None:
    fatal, notes = decisions.validate(_log(_entry("D-001"), _entry("D-002")), {}, TODAY)
    assert fatal == []
    assert notes == []


def test_a_duplicate_id_is_fatal() -> None:
    """The one failure that must never ship: every citation of that number is ambiguous."""
    log = _log(_entry("D-001"), _entry("D-002"), _entry("D-002"))
    fatal, _ = decisions.validate(log, {}, TODAY)
    assert any("D-002 appears 2 times" in f for f in fatal)


def test_the_duplicate_message_says_which_entry_to_move() -> None:
    """AGENTS.md's rule is to move the entry cited from fewer places, so the count is the
    actionable part of the message — not a detail to leave to the reader."""
    log = _log(_entry("D-001"), _entry("D-001"))
    sites = {"D-001": ["src/amazebio/seeds.py:12", "tasks/A1-6.md:40"]}
    fatal, _ = decisions.validate(log, sites, TODAY)
    assert any("cited from 2 place(s)" in f for f in fatal)
    assert any("Numbering:" in f for f in fatal)


def test_a_dangling_citation_is_fatal() -> None:
    """A cited number with no entry sends a reader to reasoning that is not there."""
    log = _log(_entry("D-001"))
    fatal, _ = decisions.validate(log, {"D-001": ["x.md:1"], "D-099": ["src/x.py:3"]}, TODAY)
    assert any("D-099 is cited but has no entry" in f for f in fatal)
    assert not any("D-001 is cited" in f for f in fatal)


def test_a_dangling_citation_names_where_it_came_from() -> None:
    log = _log(_entry("D-001"))
    sites = {"D-042": ["tools/a.py:1", "tools/b.py:2"]}
    fatal, _ = decisions.validate(log, sites, TODAY)
    assert any("tools/a.py:1" in f for f in fatal)


def test_a_missing_date_is_fatal() -> None:
    """The log is a chronology, and entries are cited as evidence of when a threshold was fixed."""
    log = "# Decisions\n\n### D-001 — no date here\n- **Task:** X1.1\n"
    fatal, _ = decisions.validate(log, {}, TODAY)
    assert any("has no `**Date:**`" in f for f in fatal)


def test_a_future_date_is_fatal() -> None:
    fatal, _ = decisions.validate(_log(_entry("D-001", date="2027-01-01")), {}, TODAY)
    assert any("in the future" in f for f in fatal)


def test_an_unparseable_date_is_fatal() -> None:
    fatal, _ = decisions.validate(_log(_entry("D-001", date="16/10/2026")), {}, TODAY)
    assert any("unparseable date" in f for f in fatal)


def test_todays_date_is_not_in_the_future() -> None:
    """Off-by-one on the boundary would fail every entry written today, which is most of them."""
    fatal, _ = decisions.validate(_log(_entry("D-001", date=TODAY.isoformat())), {}, TODAY)
    assert fatal == []


def test_a_gap_is_reported_but_does_not_fail() -> None:
    """In an append-only log a gap cannot be filled, so failing on one blocks work to no end."""
    fatal, notes = decisions.validate(_log(_entry("D-001"), _entry("D-003")), {}, TODAY)
    assert fatal == []
    assert any("D-002" in n for n in notes)


def test_out_of_numeric_order_is_reported_but_does_not_fail() -> None:
    """D-041 sits between D-032 and D-033 in the real log, as a renumbering artefact."""
    fatal, notes = decisions.validate(_log(_entry("D-002"), _entry("D-001")), {}, TODAY)
    assert fatal == []
    assert any("out of numeric order" in n for n in notes)


def test_a_numbering_line_is_not_read_as_a_citation() -> None:
    """It names a number the entry used to carry. Requiring it to resolve would fail on every
    renumbered entry — 24 of them — which is the checker crying wolf on correct practice."""
    log = _log(_entry("D-002", body="- **Numbering:** appended as D-900 and renumbered\n"))
    sites = decisions.citation_sites()
    fatal, _ = decisions.validate(log, {k: v for k, v in sites.items() if k == "D-002"}, TODAY)
    assert not any("D-900" in f for f in fatal)


def test_the_entry_format_template_is_not_read_as_a_citation() -> None:
    """The log opens with a fenced template whose placeholder id cites nothing."""
    fenced = "# Decisions\n\n```markdown\n### D-00N — <short title>\n- **Date:** YYYY-MM-DD\n```\n"
    assert "D-00N" not in decisions._strip_fenced(fenced)


def test_entries_are_parsed_in_file_order_with_bodies() -> None:
    found = decisions.entries(_log(_entry("D-001"), _entry("D-002", date="2026-10-02")))
    assert [eid for eid, _ in found] == ["D-001", "D-002"]
    assert "2026-10-02" in found[1][1]


def test_the_committed_log_passes_its_own_check() -> None:
    """The point of the checker is the committed log, so assert on it directly: a change that
    would turn CI red fails here first, with a readable assertion instead of a pipeline."""
    log = pathlib.Path(decisions.LOG).read_text(encoding="utf-8")
    fatal, _ = decisions.validate(log, decisions.citation_sites(), dt.date.today())
    assert fatal == [], f"the committed decisions log does not pass: {fatal}"


def test_every_citation_in_the_repo_resolves() -> None:
    """Stated separately from the log's own validity, because this is the half that catches a
    typo'd `D-NNN` in src/ or a citation of a number that was renumbered away."""
    log = pathlib.Path(decisions.LOG).read_text(encoding="utf-8")
    known = {eid for eid, _ in decisions.entries(log)}
    dangling = {e: w for e, w in decisions.citation_sites().items() if e not in known}
    assert dangling == {}, f"dangling decision citations: {dangling}"

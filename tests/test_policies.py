"""Tests for tools/policies.py.

The real evidence store is validated by `pixi run -e dev policies-check` in CI, which reads
the actual PDFs. These tests cover the logic that check depends on, on fixtures, so a
regression in quote matching is caught here rather than by a silently passing validation.

The normalisation tests are the important ones. Normalisation has to fold away PDF typography
without folding away differences in wording — if it over-normalises, a wrong quote passes.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

SPEC = importlib.util.spec_from_file_location(
    "policies", pathlib.Path(__file__).resolve().parent.parent / "tools" / "policies.py"
)
policies = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policies)


class TestNormalise:
    """Folds away typography. Must not fold away wording."""

    def test_collapses_whitespace(self):
        assert policies.normalise("a   b\n\tc") == "a b c"

    def test_is_case_insensitive(self):
        assert policies.normalise("Viral Denylist") == policies.normalise("viral denylist")

    def test_joins_words_hyphenated_across_a_line_break(self):
        assert policies.normalise("classifi-\ncation") == "classification"
        assert policies.normalise("Vi- ral Denylist") == "viral denylist"

    def test_keeps_genuine_hyphens(self):
        assert policies.normalise("High-confidence") == "high-confidence"

    def test_folds_ligatures(self):
        assert policies.normalise("ﬁlter") == "filter"
        assert policies.normalise("ﬂavour") == "flavour"

    def test_folds_curly_quotes_and_dashes(self):
        assert policies.normalise("\u201cHigh-confidence\u201d") == '"high-confidence"'
        assert policies.normalise("a \u2013 b") == "a - b"  # en dash

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("unique to viruses", "related to viruses"),
            ("at least twice", "at least three times"),
            ("19 families", "18 families"),
            ("length ≤ 1024", "length <= 1024"),
            ("eukaryotic hosts", "eukaryotic host"),
        ],
    )
    def test_does_not_fold_away_differences_in_wording(self, a, b):
        # Each pair is a real near-miss this project could plausibly introduce.
        assert policies.normalise(a) != policies.normalise(b)


class TestFindQuotes:
    def _write(self, tmp_path, body):
        p = tmp_path / "x.md"
        p.write_text(body)
        return p

    def test_finds_a_quote_and_its_marker(self, tmp_path):
        p = self._write(tmp_path, "intro\n\n[source: S-A, p32]\n> hello world\n")
        quotes = policies.find_quotes(p)
        assert len(quotes) == 1
        _, sid, locator, text = quotes[0]
        assert (sid, locator, text) == ("S-A", "p32", "hello world")

    def test_joins_a_wrapped_quote(self, tmp_path):
        p = self._write(tmp_path, "[source: S-A]\n> hello\n> world\n")
        assert policies.find_quotes(p)[0][3] == "hello world"

    def test_marker_may_sit_a_couple_of_lines_above(self, tmp_path):
        p = self._write(tmp_path, "[source: S-A]\n\n> hello\n")
        assert policies.find_quotes(p)[0][1] == "S-A"

    def test_quote_without_a_marker_is_refused(self, tmp_path):
        p = self._write(tmp_path, "some prose\n\n\n\n> orphan quote\n")
        with pytest.raises(policies.PolicyError, match="no \\[source: ...\\] marker"):
            policies.find_quotes(p)

    def test_locator_is_optional(self, tmp_path):
        p = self._write(tmp_path, "[source: S-A]\n> hello\n")
        assert policies.find_quotes(p)[0][2] == ""

    def test_prose_mention_without_a_quote_is_not_a_quote(self, tmp_path):
        p = self._write(tmp_path, "see [source: S-A] for detail, no blockquote here\n")
        assert policies.find_quotes(p) == []

    def test_finds_several_quotes(self, tmp_path):
        p = self._write(
            tmp_path,
            "[source: S-A]\n> first\n\ntext\n\n[source: S-B, Appendix A]\n> second\n",
        )
        got = [(q[1], q[3]) for q in policies.find_quotes(p)]
        assert got == [("S-A", "first"), ("S-B", "second")]


class TestExtract:
    def test_reads_a_text_capture(self, tmp_path):
        p = tmp_path / "a.md"
        p.write_text("plain text")
        assert policies.extract(p) == "plain text"


class TestRealStore:
    """Cheap structural checks on the committed store. Quote verification runs in CI."""

    def test_sources_load_and_every_id_is_unique(self):
        sources = policies.load_sources()
        assert len(sources) > 10
        assert all(sid == entry["id"] for sid, entry in sources.items())

    def test_every_retrieved_source_has_a_capture_and_checksum(self):
        for sid, entry in policies.load_sources().items():
            if entry["status"] == "retrieved":
                assert entry.get("capture"), f"{sid} has no capture"
                assert len(entry.get("sha256", "")) == 64, f"{sid} has no sha256"

    def test_every_unretrieved_source_records_why(self):
        for sid, entry in policies.load_sources().items():
            if entry["status"] == "unretrieved":
                assert entry.get("blocker"), f"{sid} does not say why it is unretrieved"

    def test_every_policy_quote_cites_a_retrieved_source(self):
        sources = policies.load_sources()
        for policy in policies.POLICIES.glob("*.md"):
            if policy.name == "README.md":
                continue
            for line_no, sid, _, _ in policies.find_quotes(policy):
                assert sid in sources, f"{policy.name}:{line_no} cites unknown {sid}"
                assert sources[sid]["status"] == "retrieved", (
                    f"{policy.name}:{line_no} quotes {sid}, which is " f"{sources[sid]['status']}"
                )

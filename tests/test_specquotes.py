"""Tests for tools/specquotes.py — task X1.4.

The real specs are verified by `pixi run -e dev specs-check` in CI, against the actual PDFs.
These tests cover the logic that check depends on, on fixtures, so a regression in extraction
or matching is caught here rather than by a silently passing validation.

Extraction is where the risk sits. A naive extractor pairs one quotation's closing mark with
the next one's opening mark and reports nonsense — A0.3 hit exactly that by hand — so the
pairing, the odd-mark guard and the source attribution all have tests of their own.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "specquotes.py"
_spec = importlib.util.spec_from_file_location("specquotes_under_test", _PATH)
specquotes = importlib.util.module_from_spec(_spec)
sys.modules["specquotes_under_test"] = specquotes
_spec.loader.exec_module(specquotes)


SPEC_TEMPLATE = """\
# Header comment quoting the source: "the quick brown fox".

policy:
  id: fixture-literal
  model: Fixture
  reading: literal
  source: S-FIXTURE

  scope:
    components: [Everything]
    note: >-
      Scope note quoting {scope_quote}

  rules:
    - id: a-rule
      kind: keep_if_attribute_in
      source: S-FIXTURE
      locator: p1
      params:
        attribute: x
        values: ["y"]
      note: >-
        Rule note quoting {rule_quote}
"""


def write_spec(tmp_path, *, scope_quote='"jumps over"', rule_quote='"the lazy dog"'):
    path = tmp_path / "fixture-literal.yaml"
    path.write_text(
        SPEC_TEMPLATE.format(scope_quote=scope_quote, rule_quote=rule_quote), encoding="utf-8"
    )
    return path


class TestQuotedSpans:
    def test_pairs_marks_left_to_right(self):
        spans = specquotes.quoted_spans('say "one" then "two"', context="t")
        assert [s for s, _ in spans] == ["one", "two"]

    def test_does_not_pair_across_two_quotations(self):
        """The failure A0.3 hit by hand: 'then' is not a quotation."""
        spans = specquotes.quoted_spans('"one" then "two"', context="t")
        assert "then" not in [s for s, _ in spans]

    def test_an_odd_number_of_marks_is_an_error(self):
        with pytest.raises(specquotes.SpecQuoteError, match="odd number"):
            specquotes.quoted_spans('"one" then "two', context="t")

    def test_single_quotes_inside_a_quotation_are_not_delimiters(self):
        spans = specquotes.quoted_spans("\"labeled as 'High-confidence' here\"", context="t")
        assert [s for s, _ in spans] == ["labeled as 'High-confidence' here"]

    def test_our_own_phrasing_in_single_quotes_is_not_extracted(self):
        """The convention that keeps the check meaningful."""
        spans = specquotes.quoted_spans("the floor is 'a hit exists' here", context="t")
        assert spans == []

    def test_an_inline_marker_overrides_the_source(self):
        spans = specquotes.quoted_spans('the card [source: S-CARD] "removed"', context="t")
        assert spans == [("removed", "S-CARD")]

    def test_a_marker_does_not_leak_onto_a_later_quotation(self):
        spans = specquotes.quoted_spans('[source: S-CARD] "one" and "two"', context="t")
        assert spans == [("one", "S-CARD"), ("two", None)]


class TestFold:
    def test_folds_quote_characters_together(self):
        assert specquotes.fold("labeled as 'x'") == specquotes.fold('labeled as "x"')

    def test_folds_run_together_pdf_text(self):
        """Evo 1's appendix extracts as `thoseonlyassigneduptothelevelof`."""
        assert specquotes.fold("those only assigned up to the level of") == specquotes.fold(
            "thoseonlyassigneduptothelevelof"
        )

    def test_does_not_fold_case(self):
        """The error hand-verification caught in A0.3 was a changed capital."""
        assert specquotes.fold("Viral Denylist") != specquotes.fold("viral denylist")

    def test_does_not_fold_the_two_errors_a0_3_made_by_hand(self):
        # A transliterated inequality and a changed capital. Both must remain visible.
        assert specquotes.fold("length ≤ 1024") != specquotes.fold("length <= 1024")
        assert specquotes.fold("High-confidence") != specquotes.fold("high-confidence")

    def test_does_not_fold_away_differences_in_wording(self):
        assert specquotes.fold("at least twice") != specquotes.fold("at least three times")
        assert specquotes.fold("unique to viruses") != specquotes.fold("related to viruses")


class TestSpecQuotations:
    def test_finds_quotations_in_comments_notes_and_rules(self, tmp_path):
        found = specquotes.spec_quotations(write_spec(tmp_path))
        assert {q.text for q in found} == {
            "the quick brown fox",
            "jumps over",
            "the lazy dog",
        }

    def test_a_note_quotation_is_attributed_to_its_rule_source(self, tmp_path):
        found = specquotes.spec_quotations(write_spec(tmp_path))
        rule_quote = next(q for q in found if q.text == "the lazy dog")
        assert rule_quote.sources[0] == "S-FIXTURE"
        assert rule_quote.where == "note"

    def test_a_scope_note_falls_back_to_the_policy_source(self, tmp_path):
        found = specquotes.spec_quotations(write_spec(tmp_path))
        scope_quote = next(q for q in found if q.text == "jumps over")
        assert scope_quote.sources[0] == "S-FIXTURE"

    def test_an_inline_marker_wins_over_the_rule_source(self, tmp_path):
        path = write_spec(tmp_path, rule_quote='[source: S-OTHER] "the lazy dog"')
        found = specquotes.spec_quotations(path)
        rule_quote = next(q for q in found if q.text == "the lazy dog")
        assert rule_quote.sources[0] == "S-OTHER"

    def test_line_numbers_point_at_the_note(self, tmp_path):
        found = specquotes.spec_quotations(write_spec(tmp_path))
        assert all(q.line >= 1 for q in found)
        comment = next(q for q in found if q.where == "comment")
        assert comment.line == 1


class TestVerifyAgainstASource:
    """End-to-end on a fixture source, including a deliberately corrupted quotation."""

    def _setup(self, tmp_path, monkeypatch, *, rule_quote):
        source = tmp_path / "source.txt"
        source.write_text(
            "The quick brown fox jumps over the lazy dog. "
            "Sequences were retained only if labeled as High-confidence, with length ≤ 1024.",
            encoding="utf-8",
        )
        specs = tmp_path / "specs"
        specs.mkdir()
        spec = write_spec(tmp_path, rule_quote=rule_quote)
        spec.rename(specs / spec.name)
        monkeypatch.setattr(specquotes, "REPO", tmp_path)
        monkeypatch.setattr(
            specquotes.policies,
            "load_sources",
            lambda: {
                "S-FIXTURE": {
                    "id": "S-FIXTURE",
                    "status": "retrieved",
                    "capture": "source.txt",
                    "title": "fixture",
                    "url": "https://example.invalid",
                }
            },
        )
        return specs

    def test_faithful_quotations_verify(self, tmp_path, monkeypatch):
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"the lazy dog"')
        problems, verified = specquotes.verify(specs)
        assert problems == []
        assert verified == 3

    def test_a_corrupted_quotation_fails(self, tmp_path, monkeypatch):
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"the sleepy dog"')
        problems, _ = specquotes.verify(specs)
        assert len(problems) == 1
        assert "does not appear" in problems[0]
        assert "the sleepy dog" in problems[0]

    def test_a_changed_capital_fails(self, tmp_path, monkeypatch):
        """Regression: the first of the two errors A0.3 caught by hand."""
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"labeled as high-confidence"')
        problems, _ = specquotes.verify(specs)
        assert len(problems) == 1
        assert "does not appear" in problems[0]

    def test_a_transliterated_inequality_fails(self, tmp_path, monkeypatch):
        """Regression: the second. `<=` is not `≤`."""
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"with length <= 1024"')
        problems, _ = specquotes.verify(specs)
        assert len(problems) == 1
        assert "does not appear" in problems[0]

    def test_the_same_quotation_with_the_published_characters_verifies(self, tmp_path, monkeypatch):
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"with length ≤ 1024"')
        problems, _ = specquotes.verify(specs)
        assert problems == []

    def test_a_sentence_initial_capital_is_tolerated(self, tmp_path, monkeypatch):
        """`"Sequences were retained" is how the fragment reads mid-sentence in the source.`"""
        specs = self._setup(tmp_path, monkeypatch, rule_quote='"Jumps over the lazy dog"')
        problems, _ = specquotes.verify(specs)
        assert problems == []

    def test_an_unretrieved_source_cannot_be_quoted(self, tmp_path, monkeypatch):
        specs = self._setup(tmp_path, monkeypatch, rule_quote='[source: S-MISSING] "anything"')
        problems, _ = specquotes.verify(specs)
        assert len(problems) == 1
        assert "retrieved" in problems[0]

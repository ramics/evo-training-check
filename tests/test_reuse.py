"""Joining the two OpenGenome contig tables, and the discipline around the causes.

The comparison can be wrong in two directions and only one of them is obvious. Missing
material that is really there — a renamed contig read as a loss — overstates the finding.
Material counted as present when the evidence for it has not been read understates it.
Both are tested here, because A7.4 reports against a named laboratory.
"""

from __future__ import annotations

import pytest

from amazebio.reuse import CAUSE_MEANING, Cause, Side, classify, join, tally, wilson


def og2(*rows: tuple[str, Side]) -> list[tuple[str, Side]]:
    return list(rows)


def test_a_corpus_that_carries_every_v1_contig_has_no_gap() -> None:
    result = join(["A.1", "B.1"], og2(("A.1", Side.REUSED), ("B.1", Side.REUSED)))
    assert result.shared_with_reused == 2
    assert result.only_v1 == ()
    assert result.claims_entirety


def test_the_two_sides_are_kept_apart_so_additions_cannot_cover_a_gap() -> None:
    """The one way this comparison could flatter the claim: letting a genome added in
    220.0 stand in for a 214.1 contig the reused subtree does not carry."""
    result = join(["A.1", "B.1"], og2(("A.1", Side.REUSED), ("B.1", Side.ADDED)))
    # B.1 is in OpenGenome2, so no accession has gone missing...
    assert result.only_v1 == ()
    # ...but it arrived on the added side, so the reuse carries one of v1's two.
    assert result.shared_with_reused == 1
    assert result.reused_coverage[0] == 0.5


def test_coverage_comes_with_its_interval() -> None:
    point, low, high = join(["A.1", "B.1"], og2(("A.1", Side.REUSED))).reused_coverage
    assert point == 0.5
    assert low < point < high


def test_a_rate_over_no_records_is_refused() -> None:
    with pytest.raises(ValueError, match="not a rate"):
        wilson(0, 0)


def test_wilson_matches_the_headline_metric() -> None:
    """Derived here rather than imported from `survival`, so that this module's rates and
    the headline's cannot drift apart without a test saying so."""
    from amazebio import survival

    for hits, total in ((0, 10), (1, 3), (28, 100), (674_571, 60_479_070)):
        mine = wilson(hits, total)
        theirs = survival.wilson_interval(hits, total)
        assert round(mine[1], 12) == round(theirs.low, 12)
        assert round(mine[2], 12) == round(theirs.high, 12)


def test_a_contig_only_on_the_added_side_is_not_a_gap_in_the_reuse() -> None:
    result = join(["A.1"], og2(("A.1", Side.REUSED), ("N.1", Side.ADDED)))
    assert result.only_reused == ()
    assert result.added_accessions == 1


def test_a_renamed_contig_is_a_representation_difference_not_a_loss() -> None:
    result = join(["OLD.1"], og2(("NEW.1", Side.REUSED)))
    found = classify(
        result,
        og2_digests={"NEW.1": "deadbeef"},
        v1_digests={"OLD.1": "deadbeef"},
    )
    causes = {d.accession: d.cause for d in found}
    assert causes["OLD.1"] is Cause.DEDUPLICATION  # same residues under another accession
    assert causes["NEW.1"] is Cause.REPRESENTATION
    assert all("same residues" in d.evidence for d in found)


def test_a_contig_whose_residues_are_nowhere_on_the_other_side_is_content() -> None:
    result = join(["GONE.1"], og2(("X.1", Side.REUSED)))
    found = classify(
        result, og2_digests={"X.1": "aaaa"}, v1_digests={"GONE.1": "bbbb", "X.1": "cccc"}
    )
    assert {d.cause for d in found} == {Cause.CONTENT}


def test_a_record_with_no_digest_read_is_undetermined_not_missing() -> None:
    """A missing digest and a missing sequence look identical to a join and mean opposite
    things. Collapsing them is how this comparison would overstate its finding."""
    result = join(["GONE.1"], og2(("X.1", Side.REUSED)))
    found = classify(result, og2_digests={"X.1": "aaaa"}, v1_digests={})
    assert {d.cause for d in found} == {Cause.UNDETERMINED}
    assert tally(found)["content"] == 0


def test_an_added_contig_v1_already_had_contradicts_the_stated_selection_rule() -> None:
    result = join(["A.1"], og2(("A.1", Side.ADDED)))
    found = classify(result, og2_digests={"A.1": "aaaa"}, v1_digests={"A.1": "aaaa"})
    assert [d.cause for d in found] == [Cause.CONTENT]
    assert "selection rule does not predict" in found[0].evidence


def test_a_reused_contig_with_no_digest_is_a_truncated_table_not_a_finding() -> None:
    result = join([], og2(("X.1", Side.REUSED)))
    with pytest.raises(ValueError, match="truncated table"):
        classify(result, og2_digests={}, v1_digests={})


def test_every_discrepancy_gets_a_cause_and_none_is_left_over() -> None:
    """§A7 asks for no residual bucket, so the count in equals the count out."""
    result = join(["A.1", "B.1", "C.1"], og2(("C.1", Side.REUSED), ("D.1", Side.REUSED)))
    found = classify(
        result,
        og2_digests={"C.1": "c", "D.1": "d"},
        v1_digests={"A.1": "a", "B.1": "d", "C.1": "c"},
    )
    assert len(found) == len(result.only_v1) + len(result.only_reused)
    assert sum(tally(found).values()) == len(found)


def test_the_tally_writes_down_the_zeroes() -> None:
    """A cause missing from a report reads as a cause nobody looked for."""
    counts = tally([])
    assert set(counts) == {c.value for c in Cause}
    assert set(counts.values()) == {0}


def test_every_cause_says_what_it_does_and_does_not_license() -> None:
    assert set(CAUSE_MEANING) == set(Cause)
    assert "used in its entirety" in CAUSE_MEANING[Cause.CONTENT]

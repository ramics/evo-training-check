"""Tests for `amazebio.uniprotkb` — counting a pinned past UniProtKB release by taxon.

This scanner reads 182.7 GB once, on an instance nobody can log into, and the ways it could
be plausibly wrong all produce a number rather than an error:

* **An `OX` match inside free text.** `CC` and `RL` lines carry prose, and prose contains the
  string `OX`. An unanchored pattern counts those and inflates every taxon it touches.
* **A record split across a read boundary.** Blocks are fixed-size and records are not, so a
  record straddling two blocks is the normal case. Counting it twice or not at all changes the
  answer by an amount no later check would reveal.
* **The first record of a member.** Entry starts are found by the newline before `ID`, and the
  first record has no newline in front of it — so the obvious implementation undercounts every
  member by exactly one, which against 249M looks like nothing and means the scanner is wrong.
* **A truncated stream.** It returns a smaller count and no exception. Here that understates
  how much denylisted material UniProt held, making the filter look more complete than it was
  — the direction §2 treats as equivalent to overstating leakage.

The entry-count invariant is also checked against the real archive, not only these fixtures:
the Swiss-Prot member of release 2023_02 reads as exactly 569,516 entries, which is the figure
UniProt publishes for it.
"""

from __future__ import annotations

import pytest

from amazebio.seeds import Attribution
from amazebio.uniprotkb import (
    RELEASE_2023_02,
    TaxonCounts,
    iter_member_chunks,
    scan_chunks,
    verify_whole,
)


def _entry(accession: str, taxid: int, extra: str = "") -> str:
    return (
        f"ID   {accession}_TEST              Reviewed;         100 AA.\n"
        f"AC   {accession};\n"
        f"OS   Some organism.\n"
        f"OC   Bacteria; Pseudomonadota.\n"
        f"OX   NCBI_TaxID={taxid};\n"
        f"{extra}"
        f"SQ   SEQUENCE   100 AA;  11000 MW;\n"
        f"     MKVLAAAA\n"
        f"//\n"
    )


FLAT = (
    _entry("P00001", 632)  # Yersinia pestis: on the list
    + _entry("P00002", 9606)  # human: not
    + _entry("P00003", 1392)  # Bacillus anthracis: on the list
    + _entry("P00004", 10244)  # Monkeypox: on the list, and viral
).encode()


DENYLIST = frozenset({632, 1392, 10244})
VIRAL = frozenset({10244})


def test_counts_entries_including_the_very_first_one() -> None:
    counts = scan_chunks([FLAT], DENYLIST)
    assert counts.entries == 4, "the first record has no newline before it"
    assert counts.with_taxon == 4
    assert counts.seeded == 3


def test_the_result_does_not_depend_on_the_block_size() -> None:
    """Records straddle blocks; that must not change the answer."""
    reference = scan_chunks([FLAT], DENYLIST, None, None, VIRAL).to_dict()
    for size in (1, 7, 64, 255, 1024, len(FLAT) - 1, len(FLAT), len(FLAT) * 2):
        blocks = [FLAT[i : i + size] for i in range(0, len(FLAT), size)] or [b""]
        assert scan_chunks(blocks, DENYLIST, None, None, VIRAL).to_dict() == reference, size


def test_ox_inside_free_text_is_not_counted() -> None:
    """`OX` appears in prose. Only a line that starts with it is a taxon."""
    noisy = _entry(
        "P00005",
        9606,
        extra=(
            "CC   -!- SIMILARITY: Resembles OX   NCBI_TaxID=632; in passing.\n"
            "RL   Journal of OX   NCBI_TaxID=1392; Studies 1:1(2001).\n"
        ),
    ).encode()
    counts = scan_chunks([noisy], DENYLIST)
    assert counts.entries == 1
    assert counts.with_taxon == 1, "the prose lines must not register as taxa"
    assert counts.seeded == 0


def test_a_taxon_is_counted_for_both_the_denylist_and_the_viral_set() -> None:
    """A1.6's count rides along; the two are independent, not exclusive."""
    counts = scan_chunks([FLAT], DENYLIST, None, None, VIRAL)
    assert counts.seeded == 3
    assert counts.viral == 1
    assert counts.by_taxid[10244] == 1


def test_the_viral_count_is_skipped_when_not_asked_for() -> None:
    assert scan_chunks([FLAT], DENYLIST).viral == 0


def test_attribution_names_the_entry_each_taxon_came_from() -> None:
    attribution = Attribution.from_entry_taxa(
        {"Yersinia pestis": frozenset({632}), "Bacillus anthracis": frozenset({1392})}
    )
    counts = scan_chunks([FLAT], DENYLIST, attribution)
    assert counts.by_entry.claimed == {"Yersinia pestis": 1, "Bacillus anthracis": 1}


def test_counts_merge_additively_across_members() -> None:
    a = scan_chunks([FLAT], DENYLIST, None, None, VIRAL)
    b = scan_chunks([FLAT], DENYLIST, None, None, VIRAL)
    a.merge(b)
    assert a.entries == 8
    assert a.seeded == 6
    assert a.viral == 2
    assert a.by_taxid[632] == 2


def test_empty_blocks_are_ignored_rather_than_breaking_the_remainder() -> None:
    blocks = [b"", FLAT[:50], b"", FLAT[50:], b""]
    assert scan_chunks(blocks, DENYLIST).entries == 4


def test_a_short_read_is_refused_rather_than_reported() -> None:
    """The failure that looks like a result, and the direction it errs in."""
    counts = TaxonCounts(entries=249_000_000)
    with pytest.raises(ValueError, match="did not arrive whole"):
        verify_whole(counts, RELEASE_2023_02["trembl_entries"], "uniprot_trembl.dat.gz")
    verify_whole(TaxonCounts(entries=10), 10, "member")  # exact: no raise


def test_member_chunks_stop_at_the_end_of_the_stream() -> None:
    import io

    chunks = list(iter_member_chunks(io.BytesIO(FLAT), 16))
    assert b"".join(chunks) == FLAT
    assert all(len(c) <= 16 for c in chunks)


def test_the_pinned_release_names_the_members_the_archive_actually_holds() -> None:
    """Probed against the live archive: there are no FASTA members, only the flat files."""
    assert RELEASE_2023_02["members"] == ("uniprot_sprot.dat.gz", "uniprot_trembl.dat.gz")
    assert RELEASE_2023_02["bytes"] == 182_691_908_438
    assert RELEASE_2023_02["sprot_entries"] == 569_516


def test_a_token_split_across_a_block_boundary_is_still_counted() -> None:
    """The bug that cost a three-hour pass, reduced to its mechanism.

    `\\nID   ` is six bytes. A block boundary landing inside it leaves neither block holding
    the whole token, so the entry vanishes — unless the remainder is carried across, which is
    what `scan_chunks` does and what calling it once per block throws away. Over 249,308,459
    entries and 162,000 boundaries the real run lost 126, which no output revealed; only the
    publisher's own total did.
    """
    for offset in range(1, 6):
        cut = FLAT.index(b"\nID   ", 10) + offset
        blocks = [FLAT[:cut], FLAT[cut:]]
        assert scan_chunks(blocks, DENYLIST).entries == 4, offset


def test_an_ox_line_split_across_a_block_boundary_is_still_counted() -> None:
    for offset in range(1, 16):
        cut = FLAT.index(b"OX   NCBI_TaxID=") + offset
        blocks = [FLAT[:cut], FLAT[cut:]]
        counts = scan_chunks(blocks, DENYLIST)
        assert counts.with_taxon == 4, offset
        assert counts.seeded == 3, offset


def test_calling_once_per_block_is_what_loses_them() -> None:
    """Pinned as a property of the API, so the misuse is documented rather than rediscovered.

    This is not an endorsement of the pattern — it is the demonstration that it is wrong, and
    the reason `on_chunk` exists so a caller never needs it.
    """
    cut = FLAT.index(b"\nID   ", 10) + 3
    blocks = [FLAT[:cut], FLAT[cut:]]

    whole = scan_chunks(blocks, DENYLIST)
    per_block = TaxonCounts()
    for block in blocks:
        scan_chunks([block], DENYLIST, None, per_block)

    assert whole.entries == 4
    assert per_block.entries == 3, "the split token is lost when state is not carried"


def test_on_chunk_reports_progress_without_breaking_the_stream() -> None:
    seen: list[int] = []
    counts = scan_chunks(
        [FLAT[i : i + 40] for i in range(0, len(FLAT), 40)],
        DENYLIST,
        on_chunk=lambda running: seen.append(running.entries),
    )
    assert counts.entries == 4
    assert seen and seen[-1] == 4
    assert seen == sorted(seen), "the running count only goes up"

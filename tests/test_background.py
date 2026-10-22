"""A4.5's background measurement — the flat-file parse, the classes, the refusals.

The fixture is a hand-written reviewed-section fragment rather than a slice of the real file:
every property under test here is a property of the parse, and a real slice would make the
expected counts unreadable.
"""

from __future__ import annotations

import gzip

from amazebio import background

ENTRIES = """\
ID   VIRAL_ONE               Reviewed;         100 AA.
AC   P00001;
DE   RecName: Full=Capsid protein;
OC   Viruses; Duplodnaviria; Heunggongvirae.
OX   NCBI_TaxID=11111;
DR   Pfam; PF00001; Toy_capsid; 1.
DR   Pfam; PF00001; Toy_capsid; 1.
//
ID   HOST_ONE                Reviewed;         200 AA.
AC   P00002;
DE   RecName: Full=Some host protein;
OC   Eukaryota; Metazoa; Chordata.
OX   NCBI_TaxID=9606;
DR   Pfam; PF00001; Toy_capsid; 1.
DR   Pfam; PF00002; Toy_other; 1.
//
ID   HOST_TWO                Reviewed;         200 AA.
AC   P00003;
DE   RecName: Full=Endogenous retrovirus group K member;
OC   Eukaryota; Metazoa; Chordata.
OX   NCBI_TaxID=9606;
KW   Endogenous retrovirus.
DR   Pfam; PF00002; Toy_other; 1.
//
ID   HOST_THREE              Reviewed;         200 AA.
AC   P00004;
OC   Bacteria; Pseudomonadati.
OX   NCBI_TaxID=562;
DR   Pfam; PF00002; Toy_other; 1.
CC   -!- SIMILARITY: Belongs to the Pfam; PF99999; not a cross-reference.
//
"""


def _fixture(tmp_path):
    path = tmp_path / "sprot.dat.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(ENTRIES.encode("ascii"))
    return path


def test_entries_parse_one_record_each(tmp_path):
    entries = list(background.iter_entries(_fixture(tmp_path)))
    assert [e.accession for e in entries] == ["P00001", "P00002", "P00003", "P00004"]
    assert [e.viral for e in entries] == [True, False, False, False]
    assert [e.taxid for e in entries] == ["11111", "9606", "9606", "562"]


def test_repeated_cross_reference_counts_once():
    """A family on two `DR` lines of one entry is one occurrence, not two."""
    entry = background.ReviewedEntry("P0", True, "1", ("PF00001",), False)
    table = background.measure(["PF00001"], [entry])
    assert table["PF00001"].reviewed_viral == 1


def test_pfam_inside_free_text_is_not_a_cross_reference(tmp_path):
    """`Pfam` appears on `CC` lines; an unanchored match would count a comment."""
    entries = {e.accession: e for e in background.iter_entries(_fixture(tmp_path))}
    assert entries["P00004"].families == ("PF00002",)


def test_curator_phrase_marks_integrated_viral_material(tmp_path):
    entries = {e.accession: e for e in background.iter_entries(_fixture(tmp_path))}
    assert entries["P00003"].endogenous is True
    assert entries["P00002"].endogenous is False


def test_measure_splits_by_the_entrys_own_lineage(tmp_path):
    table = background.measure(["PF00001", "PF00002"], background.iter_entries(_fixture(tmp_path)))
    capsid = table["PF00001"]
    assert (capsid.reviewed_viral, capsid.reviewed_non_viral) == (1, 1)
    assert capsid.non_viral_taxa == {"9606"}
    other = table["PF00002"]
    assert (other.reviewed_viral, other.reviewed_non_viral) == (0, 3)
    assert other.non_viral_endogenous == 1
    assert other.non_viral_taxa == {"9606", "562"}


def test_families_outside_the_universe_are_ignored(tmp_path):
    """The table's rows are the pinned universe, so the denominator cannot drift."""
    table = background.measure(["PF00002"], background.iter_entries(_fixture(tmp_path)))
    assert set(table) == {"PF00002"}


def test_absence_of_curation_is_never_viral_only():
    """The whole point of the third class: an unmeasured family must not read as a result."""
    assert background.classify(background.FamilyBackground("PF0", 0, 0)) == "unmeasurable"
    assert background.classify(background.FamilyBackground("PF0", 3, 0)) == "viral_only"
    assert background.classify(background.FamilyBackground("PF0", 3, 1)) == "shared"
    assert background.classify(background.FamilyBackground("PF0", 0, 1)) == "shared"


def test_non_viral_fraction_is_none_when_nothing_was_measured():
    assert background.FamilyBackground("PF0", 0, 0).non_viral_fraction is None
    assert background.FamilyBackground("PF0", 3, 1).non_viral_fraction == 0.25


def test_summary_counts_every_family_once(tmp_path):
    table = background.measure(
        ["PF00001", "PF00002", "PF00003"], background.iter_entries(_fixture(tmp_path))
    )
    summary = background.summarise(table)
    assert summary["families"] == 3
    assert sum(summary["classes"].values()) == 3
    assert summary["classes"] == {"unmeasurable": 1, "viral_only": 0, "shared": 2}
    assert summary["measured"] == 2


def test_record_state_does_not_leak_across_the_terminator(tmp_path):
    """An entry whose header this parser does not read must not inherit the previous one."""
    text = ENTRIES.replace("ID   HOST_ONE                Reviewed;         200 AA.\n", "")
    path = tmp_path / "odd.dat.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(text.encode("ascii"))
    entries = list(background.iter_entries(path))
    assert [e.accession for e in entries] == ["P00001", "P00002", "P00003", "P00004"]
    assert entries[1].families == ("PF00001", "PF00002")


def test_admitting_words_separates_bacteriophage_from_macrophage():
    """The selection rule matches `phage` with no word boundary; this is what finds that."""
    import re

    keywords = re.compile("phage|virus|coat protein", re.IGNORECASE)
    assert background.admitting_words("Phage_capsid Bacteriophage capsid", keywords) == (
        "bacteriophage",
        "phage",
    )
    assert background.admitting_words(
        "Nramp Natural resistance-associated macrophage protein-like", keywords
    ) == ("macrophage",)
    assert background.admitting_words("Toy_one A family of nothing", keywords) == ()


def test_a_host_substring_word_is_recognised_as_naming_nothing_viral():
    assert "macrophage" in background.HOST_SUBSTRING_WORDS


SINGLE_ELEMENT_LINEAGE = """\
ID   SCAF_TOY                Reviewed;         180 AA.
AC   Q00001;
OC   Viruses.
OX   NCBI_TaxID=12392;
DR   Pfam; PF00002; Toy_other; 1.
//
"""


def test_a_single_element_lineage_ends_in_a_full_stop(tmp_path):
    """`OC   Viruses.` is a whole lineage. Splitting on `;` alone leaves `Viruses.`, which
    read as cellular and classed five families shared when they are not."""
    path = tmp_path / "root.dat.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(SINGLE_ELEMENT_LINEAGE.encode("ascii"))
    entry = next(iter(background.iter_entries(path)))
    assert entry.viral is True
    table = background.measure(["PF00002"], [entry])
    assert (table["PF00002"].reviewed_viral, table["PF00002"].reviewed_non_viral) == (1, 0)

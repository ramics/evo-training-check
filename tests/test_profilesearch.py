"""Tests for `amazebio.profilesearch` — the search A2.1 and A2.4 share (D-113).

The moved code is covered by A2.1's own tests, which did not change: the point of the refactor
is that A2.1's numbers do not move. What is new here is :func:`proteins_from_fasta`, A2.4's way
into the same search, and the thing it has to get right is *attribution* — a protein called
inside a provirus is counted on the bacterial genome that carries it, not on the fragment name
the provirus finder invented. Getting that wrong attributes a prophage's families to the wrong
bacterium, and no downstream artefact would show it.
"""

from __future__ import annotations

from amazebio.profilesearch import proteins_from_fasta, text_of


def host_of(name: str) -> str:
    """How A2.4 maps a geNomad provirus protein back to its host record.

    geNomad names a provirus `<source>|provirus_<start>_<end>` and its proteins
    `<provirus>_<n>`, so the host record is everything before the first pipe.
    """
    return name.split("|")[0]


def test_proteins_are_named_for_the_host_record_not_the_fragment():
    entries = [("NC_000913.3|provirus_1000_2000_1", "MKV")]
    proteins, _ = proteins_from_fasta(entries, record_of=host_of)
    name = text_of(proteins[0].name)
    assert name.startswith("NC_000913.3|gene")
    # `search` recovers the record by partitioning on the first pipe, so the tagged name must
    # survive that round trip.
    assert name.partition("|")[0] == "NC_000913.3"


def test_proteins_from_several_proviruses_count_as_one_record():
    """Two prophages in one genome are two elements and one surviving record."""
    entries = [
        ("g1|provirus_1_100_1", "MKV"),
        ("g1|provirus_5000_6000_1", "MKA"),
    ]
    _, stats = proteins_from_fasta(entries, record_of=host_of)
    assert stats["records"] == 1
    assert stats["genes"] == 2


def test_distinct_genomes_count_separately():
    entries = [("g1|provirus_1_100_1", "MKV"), ("g2|provirus_1_100_1", "MKA")]
    _, stats = proteins_from_fasta(entries, record_of=host_of)
    assert stats["records"] == 2


def test_residues_are_counted():
    _, stats = proteins_from_fasta([("g1|p_1", "MKVLA")], record_of=host_of)
    assert stats["residues"] == 5


def test_a_trailing_stop_codon_is_stripped_and_not_counted():
    _, stats = proteins_from_fasta([("g1|p_1", "MKV*")], record_of=host_of)
    assert stats["residues"] == 3


def test_a_protein_the_mapping_cannot_place_is_counted_not_dropped():
    """Dropping it silently would shrink the searched set without shrinking the denominator."""
    entries = [("g1|p_1", "MKV"), ("nonsense", "MKA")]
    proteins, stats = proteins_from_fasta(
        entries, record_of=lambda n: "" if n == "nonsense" else host_of(n)
    )
    assert stats["proteins_unplaced"] == 1
    assert stats["genes"] == 1
    assert len(proteins) == 1


def test_an_empty_protein_is_skipped_without_being_called_unplaced():
    _, stats = proteins_from_fasta([("g1|p_1", "*")], record_of=host_of)
    assert stats["genes"] == 0
    assert stats["proteins_unplaced"] == 0


def test_no_entries_is_an_empty_search_rather_than_an_error():
    """A sampled genome with no provirus contributes no proteins, and that is the common case."""
    proteins, stats = proteins_from_fasta([], record_of=host_of)
    assert proteins == []
    assert stats["records"] == 0

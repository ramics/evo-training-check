"""Tests for `amazebio.profilesearch` — the search A2.1 and A2.4 share (D-113).

The moved code is covered by A2.1's own tests, which did not change: the point of the refactor
is that A2.1's numbers do not move. What is new here is :func:`proteins_from_fasta`, A2.4's way
into the same search, and the thing it has to get right is *attribution* — a protein called
inside a provirus is counted on the bacterial genome that carries it, not on the fragment name
the provirus finder invented. Getting that wrong attributes a prophage's families to the wrong
bacterium, and no downstream artefact would show it.
"""

from __future__ import annotations

import dataclasses

from amazebio import profilesearch
from amazebio.profilesearch import proteins_from_fasta, text_of


@dataclasses.dataclass(frozen=True)
class _Alignment:
    hmm_from: int
    hmm_to: int
    target_from: int
    target_to: int


@dataclasses.dataclass(frozen=True)
class _Domain:
    """Enough of a pyhmmer domain for the coordinate arithmetic, and no more."""

    hmm_from: int
    hmm_to: int
    target_from: int
    target_to: int
    included: bool = True

    @property
    def alignment(self) -> _Alignment:
        return _Alignment(self.hmm_from, self.hmm_to, self.target_from, self.target_to)


@dataclasses.dataclass(frozen=True)
class _Hit:
    domains: list[_Domain]


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


class TestBestDomainRegion:
    """The target-side coordinates A3.4 places (D-241). The model side is `best_model_coverage`."""

    def test_the_region_belongs_to_the_best_covering_domain(self) -> None:
        hit = _Hit(
            [
                _Domain(hmm_from=1, hmm_to=10, target_from=5, target_to=14),
                _Domain(hmm_from=1, hmm_to=50, target_from=100, target_to=149),
            ]
        )
        assert profilesearch.best_domain_region(hit) == (100, 149)

    def test_an_excluded_domain_is_not_a_region(self) -> None:
        hit = _Hit([_Domain(hmm_from=1, hmm_to=50, target_from=1, target_to=50, included=False)])
        assert profilesearch.best_domain_region(hit) is None

    def test_a_hit_with_no_domains_has_no_region(self) -> None:
        assert profilesearch.best_domain_region(_Hit([])) is None

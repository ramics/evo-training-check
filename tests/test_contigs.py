"""Identity and digest for a contig, and the shapes that are refused rather than guessed."""

from __future__ import annotations

import hashlib

import pytest

from amazebio.contigs import (
    ContigError,
    accession_of,
    digest_sequence,
    parse_fasta,
    strain_of,
)


def test_the_accession_is_the_first_token_not_the_whole_header() -> None:
    assert accession_of(">JAHFAU010000168.1 Pseudomonas sp., wgs") == "JAHFAU010000168.1"
    assert accession_of("JAHFAU010000168.1") == "JAHFAU010000168.1"


def test_a_header_with_no_accession_is_refused() -> None:
    """An empty key joins against every other empty key, so a parse failure would read as
    agreement — the one way this comparison can be wrong in the flattering direction."""
    with pytest.raises(ContigError, match="no accession"):
        accession_of(">")
    with pytest.raises(ContigError, match="no accession"):
        accession_of(">   ")


def test_the_digest_ignores_line_wrapping_and_case() -> None:
    """FASTA wraps where the publisher chose and Parquet does not wrap at all. A digest
    over the stored bytes would report every contig as different."""
    wrapped = ["ACGT\n", "acgt\n", "AC\n"]
    flat = ["ACGTACGTAC"]
    assert digest_sequence(wrapped) == digest_sequence(flat)
    assert digest_sequence(flat)[0] == hashlib.sha256(b"ACGTACGTAC").hexdigest()
    assert digest_sequence(flat)[1] == 10


def test_the_digest_takes_bytes_or_text_alike() -> None:
    assert digest_sequence([b"ACGT"]) == digest_sequence(["ACGT"])


def test_the_digest_covers_the_residues_and_not_the_header() -> None:
    """A renamed contig with identical sequence has to come out as a renaming."""
    one = list(parse_fasta([">A1.1 one\n", "ACGT\n"]))
    two = list(parse_fasta([">B9.9 quite another\n", "ACGT\n"]))
    assert one[0].accession != two[0].accession
    assert one[0].sha256 == two[0].sha256


def test_every_record_in_a_multifasta_is_yielded_with_its_length() -> None:
    records = list(parse_fasta([">A.1\n", "ACGT\n", "AC\n", ">B.1\n", "GGGG\n"]))
    assert [c.accession for c in records] == ["A.1", "B.1"]
    assert [c.length for c in records] == [6, 4]


def test_an_accession_repeated_within_one_member_is_refused() -> None:
    with pytest.raises(ContigError, match="appears twice"):
        list(parse_fasta([">A.1\n", "ACGT\n", ">A.1\n", "TTTT\n"], source="GCA_1.1"))


def test_residues_before_a_header_are_refused_rather_than_skipped() -> None:
    with pytest.raises(ContigError, match="before any header"):
        list(parse_fasta(["ACGT\n", ">A.1\n", "ACGT\n"]))


def test_an_empty_stream_yields_nothing_and_does_not_raise() -> None:
    assert list(parse_fasta([])) == []
    assert list(parse_fasta(["\n", "  \n"])) == []


def test_a_member_name_gives_the_assembly_the_genome_pass_named() -> None:
    assert strain_of("batch1/GCA_018384735.1.fasta.gz") == "GCA_018384735.1"
    assert strain_of("GCF_017922435.1.fna") == "GCF_017922435.1"


def test_a_member_not_named_for_an_assembly_is_refused() -> None:
    with pytest.raises(ContigError, match="not named for an assembly"):
        strain_of("batch1/README.txt")

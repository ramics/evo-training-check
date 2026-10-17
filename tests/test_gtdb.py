"""Tests for `amazebio.gtdb` — what counts as a genome in each release's prokaryotic component.

The accessions used here are real ones, taken from the staged objects rather than invented, so
the grouping rule is tested against the shapes it will actually meet. The distinction that
matters is between a WGS contig, whose accession encodes the project it belongs to, and a
complete replicon, whose accession does not — a rule loose enough to blur the two would merge
unrelated genomes, and nothing downstream would show it.
"""

from __future__ import annotations

import gzip
import io
import tarfile

import pytest

from amazebio.gtdb import (
    GtdbError,
    assembly_of_member,
    genome_key,
    iter_og2_genomes,
)

# Real ids from `stage1/gtdb/gtdb_train_shard_0.parquet` and `gtdb_test.parquet`.
WGS_CONTIGS = {
    "JAHFAU010000149.1": "JAHFAU01",
    "JAHFAU010000080.1": "JAHFAU01",
    "NZ_LIXJ01000001.1": "LIXJ01",
    "NZ_LIXJ01000014.1": "LIXJ01",
    "JAEZYW010000001.1": "JAEZYW01",
    "CADDZC010000005.1": "CADDZC01",
}

# Real ids that carry no project accession: complete replicons and scaffolds.
UNGROUPABLE = ["NZ_CP038213.1", "NZ_GL890993.1", "NZ_CM001022.1"]


# --------------------------------------------------------------------------------------
# genome_key
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("accession", "project"), sorted(WGS_CONTIGS.items()))
def test_wgs_contigs_group_on_their_project_accession(accession, project):
    key = genome_key(accession)
    assert key.key == project
    assert key.kind == "wgs_project"
    assert key.is_derived_grouping


def test_contigs_of_one_assembly_share_a_key():
    assert genome_key("JAHFAU010000149.1").key == genome_key("JAHFAU010000080.1").key


def test_contigs_of_different_assemblies_do_not():
    assert genome_key("JAHFAU010000149.1").key != genome_key("JAEZYW010000001.1").key


@pytest.mark.parametrize("accession", UNGROUPABLE)
def test_a_complete_replicon_is_its_own_genome_rather_than_a_merge(accession):
    """`CP038213` must not be read as project `CP03`: that would merge unrelated genomes.

    Standing alone under-groups instead — a chromosome and its plasmids count separately — which
    enlarges the denominator and makes the survival fraction conservative. That is the direction
    to err in.
    """
    key = genome_key(accession)
    assert key.kind == "accession"
    assert key.key == accession
    assert not key.is_derived_grouping


def test_two_complete_replicons_never_collapse_together():
    assert genome_key("NZ_CP038213.1").key != genome_key("NZ_CM001022.1").key


def test_the_refseq_prefix_does_not_split_an_assembly():
    """`NZ_LIXJ01...` and a hypothetical INSDC-prefixed sibling are the same project."""
    assert genome_key("NZ_LIXJ01000001.1").key == genome_key("LIXJ01000002.1").key


def test_an_unparseable_id_is_a_genome_of_one_not_an_error():
    """Dropping it would shrink the corpus with nothing to show for it."""
    assert genome_key("something-odd").kind == "accession"


def test_an_empty_id_is_refused():
    with pytest.raises(GtdbError, match="no accession"):
        genome_key("   ")


# --------------------------------------------------------------------------------------
# Evo 2's tar: the genome is published, not derived
# --------------------------------------------------------------------------------------


def test_assembly_accession_comes_off_the_member_name():
    assert assembly_of_member("batch1/GCF_017922435.1.fasta.gz") == "GCF_017922435.1"
    assert assembly_of_member("batch1/GCA_018384735.1.fasta.gz") == "GCA_018384735.1"


def test_a_member_that_is_not_a_genome_fasta_stops_the_run():
    with pytest.raises(GtdbError, match="layout has changed"):
        assembly_of_member("batch1/README.txt")


def _tar_of(members: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    buf.seek(0)
    return buf


def test_each_tar_member_yields_one_genome_with_its_contigs():
    fasta = b">contig1 desc\nACGT\nACGT\n>contig2\nTTTT\n"
    stream = _tar_of({"batch1/GCF_000001.1.fasta.gz": gzip.compress(fasta)})
    genomes = list(iter_og2_genomes(stream))
    assert len(genomes) == 1
    accession, contigs = genomes[0]
    assert accession == "GCF_000001.1"
    assert contigs == [("contig1 desc", "ACGTACGT"), ("contig2", "TTTT")]


def test_several_members_are_several_genomes():
    stream = _tar_of(
        {
            "batch1/GCF_000001.1.fasta.gz": gzip.compress(b">c\nAC\n"),
            "batch1/GCF_000002.1.fasta.gz": gzip.compress(b">c\nGT\n"),
        }
    )
    assert [a for a, _ in iter_og2_genomes(stream)] == ["GCF_000001.1", "GCF_000002.1"]


def test_an_uncompressed_member_is_read_too():
    stream = _tar_of({"batch1/GCF_000003.1.fasta": b">c\nAAAA\n"})
    ((accession, contigs),) = iter_og2_genomes(stream)
    assert accession == "GCF_000003.1"
    assert contigs == [("c", "AAAA")]


def test_a_stray_member_stops_the_run_rather_than_being_skipped():
    """A silently skipped member is a genome missing from the denominator."""
    stream = _tar_of({"batch1/notes.txt": b"hello"})
    with pytest.raises(GtdbError):
        list(iter_og2_genomes(stream))

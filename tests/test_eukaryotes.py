"""Indexing Evo 2's eukaryotic component, and sampling assemblies out of it.

Every test here drives the walker with a tar built by the standard library, not with a captured
fixture. The walker's whole job is to agree with the tar format about where a member starts, so a
fixture that drifted from the format would make these tests agree with the bug.
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile

import pytest

from amazebio.detect import in_band
from amazebio.eukaryotes import (
    BLOCK,
    EukaryoteError,
    Member,
    index_to_rows,
    rows_to_index,
    sampled_members,
    size_summary,
    walk_index,
)

SEED = 20261015


def genome(accession: str, contigs: int = 2, length: int = 120) -> bytes:
    """A gzipped FASTA for one assembly, as the component's members are."""
    text = "".join(f">{accession}_contig{i}\n{'ACGT' * (length // 4)}\n" for i in range(contigs))
    return gzip.compress(text.encode())


def build_tar(members: dict[str, bytes], *, batch: str = "batch1", dirs: bool = True) -> bytes:
    """A real tar laid out the way the publisher lays the component out."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        if dirs:
            info = tarfile.TarInfo(f"{batch}/")
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for accession, payload in members.items():
            info = tarfile.TarInfo(f"{batch}/{accession}.fasta.gz")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def reader_for(blobs: dict[str, bytes]):
    """A `RangeReader` over in-memory archives, recording what it transferred."""
    transferred = []

    def read_range(path: str, start: int, end: int) -> bytes:
        transferred.append(end - start + 1)
        return blobs[path][start : end + 1]

    read_range.transferred = transferred  # type: ignore[attr-defined]
    return read_range


# --- the walk ------------------------------------------------------------------------------


def test_walk_recovers_every_member_and_its_coordinates_address_it():
    """The index is only useful if its offsets really locate the member's bytes."""
    payloads = {f"GCA_{i:09d}.1": genome(f"GCA_{i:09d}.1", contigs=i % 3 + 1) for i in range(1, 8)}
    blob = build_tar(payloads)
    read = reader_for({"t.tar": blob})

    members = list(walk_index("t.tar", len(blob), read))

    assert [m.accession for m in members] == list(payloads)
    # The round-trip is the real assertion: read each member back by its recorded range and
    # require the exact bytes. An off-by-one in the header arithmetic survives a count check and
    # dies here.
    for member in members:
        assert read("t.tar", member.offset, member.end) == payloads[member.accession]
        assert member.size == len(payloads[member.accession])
        assert member.tar == "t.tar"


def test_walk_transfers_one_block_per_member_not_the_member():
    """The reason the design is affordable: the data is seeked past, never read.

    Payloads are incompressible here on purpose. A gzipped repetitive FASTA is a few hundred
    bytes, which would let this pass on a tar barely larger than its own headers and prove
    nothing about a 20 GB archive.
    """
    payloads = {f"GCA_{i:09d}.1": os.urandom(100_000) for i in range(1, 6)}
    blob = build_tar(payloads)
    read = reader_for({"t.tar": blob})

    members = list(walk_index("t.tar", len(blob), read))

    assert len(members) == 5
    assert set(read.transferred) == {BLOCK}
    assert sum(read.transferred) < len(blob) // 100


def test_a_single_zero_block_does_not_end_the_archive():
    """One zero block is not a terminator; reading it as one would truncate the denominator."""
    payloads = {"GCA_000000001.1": genome("GCA_000000001.1")}
    blob = build_tar(payloads)
    # Splice one zero block between the member and the real two-block terminator.
    body = blob[: -2 * BLOCK] + b"\0" * BLOCK + blob[-2 * BLOCK :]
    spliced = body + build_tar({"GCA_000000002.1": genome("GCA_000000002.1")})

    members = list(walk_index("t.tar", len(spliced), reader_for({"t.tar": spliced})))

    assert [m.accession for m in members] == ["GCA_000000001.1"]


def test_directory_entries_are_skipped_not_counted():
    blob = build_tar({"GCA_000000001.1": genome("GCA_000000001.1")}, dirs=True)
    members = list(walk_index("t.tar", len(blob), reader_for({"t.tar": blob})))
    assert [m.accession for m in members] == ["GCA_000000001.1"]


# --- the failure modes, each of which must fire -----------------------------------------------


def test_a_corrupted_header_checksum_stops_the_walk():
    """The check that catches a lost block boundary at the earliest possible member."""
    payloads = {f"GCA_{i:09d}.1": genome(f"GCA_{i:09d}.1") for i in range(1, 4)}
    blob = bytearray(build_tar(payloads))
    # Corrupt the size field of the second member's header without fixing its checksum.
    second = blob.index(b"GCA_000000002.1")
    blob[second + 124 : second + 136] = b"00000000777\0"

    with pytest.raises(EukaryoteError, match="checksum mismatch"):
        list(walk_index("t.tar", len(blob), reader_for({"t.tar": bytes(blob)})))


def test_a_member_that_is_not_a_genome_fasta_raises():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        info = tarfile.TarInfo("batch1/README.txt")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"hi\n"))
    blob = buf.getvalue()

    with pytest.raises(EukaryoteError, match="does not end in"):
        list(walk_index("t.tar", len(blob), reader_for({"t.tar": blob})))


def test_an_unexpected_tar_type_raises():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        info = tarfile.TarInfo("batch1/GCA_000000001.1.fasta.gz")
        info.type = tarfile.SYMTYPE
        info.linkname = "elsewhere"
        archive.addfile(info)
    blob = buf.getvalue()

    with pytest.raises(EukaryoteError, match="tar type"):
        list(walk_index("t.tar", len(blob), reader_for({"t.tar": blob})))


def test_a_truncated_archive_is_not_read_as_a_short_complete_one():
    """A member whose data runs past the pinned size is a truncated object, not a short member."""
    payload = os.urandom(100_000)
    blob = build_tar({"GCA_000000001.1": payload}, dirs=False)
    # Ten bytes short of the single member's data: header at 0, data at BLOCK, size 100,000.
    cut = BLOCK + len(payload) - 10

    with pytest.raises(EukaryoteError, match="truncated relative to its pin"):
        list(walk_index("t.tar", cut, reader_for({"t.tar": blob})))


def test_a_short_header_read_raises():
    payloads = {"GCA_000000001.1": genome("GCA_000000001.1")}
    blob = build_tar(payloads)

    def short(path: str, start: int, end: int) -> bytes:
        return blob[start : end + 1][:100]

    with pytest.raises(EukaryoteError, match="short read"):
        list(walk_index("t.tar", len(blob), short))


# --- sampling ------------------------------------------------------------------------------


def members_for(n: int) -> list[Member]:
    return [
        Member(accession=f"GCA_{i:09d}.1", tar=f"batch{i % 7}.tar", offset=i * BLOCK, size=i + 1)
        for i in range(1, n + 1)
    ]


def test_the_sample_is_the_projects_hash_rule_on_the_accession():
    members = members_for(500)
    chosen = sampled_members(members, seed=SEED, hi=0.2)
    assert [m.accession for m in chosen] == sorted(
        m.accession for m in members if in_band(m.accession, seed=SEED, lo=0.0, hi=0.2)
    )


def test_a_deeper_rate_is_a_superset_so_nothing_is_staged_twice():
    """D-078's nesting property, which is what lets the owner buy depth later."""
    members = members_for(1000)
    shallow = {m.accession for m in sampled_members(members, seed=SEED, hi=0.01)}
    deep = {m.accession for m in sampled_members(members, seed=SEED, hi=0.1)}
    assert shallow <= deep


def test_bands_tile_without_gap_or_overlap():
    members = members_for(1000)
    whole = {m.accession for m in sampled_members(members, seed=SEED, hi=0.1)}
    first = {m.accession for m in sampled_members(members, seed=SEED, hi=0.01)}
    rest = {m.accession for m in sampled_members(members, seed=SEED, lo=0.01, hi=0.1)}
    assert first | rest == whole
    assert not (first & rest)


def test_the_sample_is_keyed_on_the_accession_not_the_batch():
    """A re-batched release must move members between tars without changing the sample."""
    members = members_for(300)
    rebatched = [dataclass_replace(m, tar="other.tar") for m in members]
    assert [m.accession for m in sampled_members(members, seed=SEED, hi=0.3)] == [
        m.accession for m in sampled_members(rebatched, seed=SEED, hi=0.3)
    ]


def dataclass_replace(member: Member, **kw) -> Member:
    import dataclasses

    return dataclasses.replace(member, **kw)


# --- the index artefact --------------------------------------------------------------------


def test_rows_round_trip_and_are_ordered_for_a_tar_reader():
    members = members_for(20)
    rows = index_to_rows(members)
    assert rows == sorted(rows, key=lambda r: (r["tar"], r["offset"]))
    assert {m.accession for m in rows_to_index(rows)} == {m.accession for m in members}


def test_a_duplicated_accession_in_the_index_raises():
    rows = index_to_rows(members_for(3))
    with pytest.raises(EukaryoteError, match="appears twice"):
        rows_to_index([*rows, rows[0]])


def test_a_malformed_index_row_raises():
    with pytest.raises(EukaryoteError, match="not a member"):
        rows_to_index([{"accession": "GCA_1", "tar": "t.tar"}])


def test_size_summary_reports_the_spread_a_samples_cost_depends_on():
    members = [
        Member(accession=f"GCA_{i:09d}.1", tar="t.tar", offset=0, size=i * 1_000_000)
        for i in range(1, 101)
    ]
    summary = size_summary(members)
    assert summary["assemblies"] == 100
    assert summary["bytes"] == sum(i * 1_000_000 for i in range(1, 101))
    assert summary["min"] == 1_000_000
    assert summary["max"] == 100_000_000
    assert summary["p25"] < summary["median"] < summary["p75"] < summary["p95"]


def test_size_summary_of_nothing_is_not_an_error():
    assert size_summary([]) == {"assemblies": 0, "bytes": 0}

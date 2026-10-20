"""Walking a tar's header chain, and the shapes it refuses rather than mis-naming."""

from __future__ import annotations

import io
import tarfile

import pytest

from amazebio.tarindex import BLOCK, TarIndexError, walk_members


def build(members: dict[str, bytes], *, fmt: int = tarfile.USTAR_FORMAT) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=fmt) as archive:
        for name, body in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


def reader(blob: bytes):  # type: ignore[no-untyped-def]
    """A ranged reader that records how much it was asked for."""
    calls: list[tuple[int, int]] = []

    def read(offset: int, length: int) -> bytes:
        calls.append((offset, length))
        return blob[offset : offset + length]

    read.calls = calls  # type: ignore[attr-defined]
    return read


def test_every_member_is_named_in_order() -> None:
    blob = build({"batch1/GCA_1.fasta.gz": b"x" * 10, "batch1/GCF_2.fasta.gz": b"y" * 2000})
    members = list(walk_members(reader(blob), len(blob)))
    assert [m.name for m in members] == ["batch1/GCA_1.fasta.gz", "batch1/GCF_2.fasta.gz"]
    assert [m.size for m in members] == [10, 2000]


def test_a_member_offset_points_at_its_contents() -> None:
    body = b"gzipped-bytes-here"
    blob = build({"one.gz": body})
    member = next(iter(walk_members(reader(blob), len(blob))))
    assert blob[member.offset : member.offset + member.size] == body


def test_the_walk_reads_a_small_fraction_of_a_large_archive() -> None:
    """The whole reason this exists: a 25 GB archive is walked for megabytes."""
    blob = build({f"m{i}.gz": b"z" * 50_000 for i in range(20)})
    read = reader(blob)
    assert len(list(walk_members(read, len(blob)))) == 20
    requested = sum(length for _, length in read.calls)  # type: ignore[attr-defined]
    assert requested < len(blob) // 50


def test_a_directory_member_is_named_but_not_a_file() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo("batch1/")
        info.type = tarfile.DIRTYPE
        archive.addfile(info)
    blob = buffer.getvalue()
    member = next(iter(walk_members(reader(blob), len(blob))))
    assert member.name == "batch1/" and not member.is_file


def test_the_end_of_archive_marker_ends_the_walk_without_an_error() -> None:
    blob = build({"one.gz": b"x"})
    assert len(list(walk_members(reader(blob), len(blob)))) == 1


def test_a_corrupt_header_is_refused_rather_than_skipped() -> None:
    blob = bytearray(build({"one.gz": b"x" * 10, "two.gz": b"y" * 10}))
    blob[2 * BLOCK] ^= 0xFF  # corrupt the second header
    with pytest.raises(TarIndexError, match="does not checksum"):
        list(walk_members(reader(bytes(blob)), len(blob)))


def test_a_long_name_format_is_refused_rather_than_truncated() -> None:
    """GNU and pax put the real name in the member body. A placeholder name joins wrongly
    and silently, which is worse than failing."""
    long_name = "batch1/" + "a" * 160 + ".fasta.gz"
    for fmt in (tarfile.GNU_FORMAT, tarfile.PAX_FORMAT):
        blob = build({long_name: b"x"}, fmt=fmt)
        with pytest.raises(TarIndexError, match="real name in"):
            list(walk_members(reader(blob), len(blob)))


def test_a_ustar_prefix_name_is_rejoined_not_dropped() -> None:
    """ustar splits a long path across two fields; reading only the first loses the leading
    directories, and two genomes in different batches can share a basename."""
    name = "a" * 120 + "/GCA_1.fasta.gz"
    blob = build({name: b"x"})
    member = next(iter(walk_members(reader(blob), len(blob))))
    assert member.name == name

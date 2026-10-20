"""Reading a tar archive's member list without reading the archive — task A7.4, §A7.

OpenGenome2 publishes its reused GTDB subtree as four tars totalling 109 GB, one gzipped
multi-FASTA member per genome assembly. A7.4's claim about the 28,174 genomes Evo 2 says it
added is a claim about *which assemblies are present*, and that is in the member names.

A tar has no index. Each member is a 512-byte header followed by its contents padded to a
512-byte boundary, so the headers form a chain: read one, take its size, skip to the next.
Walking that chain over object storage costs one ranged read per member — about 14 MB of
transfer for an archive of 28,000 members, against the 25.6 GB a sequential read would move.
That is the difference between a check this container can run and a check that needs an
instance in-region, so the chain walk is worth writing down rather than reaching for the
obvious `tarfile.open`.

**What it does not do.** It never decompresses a member and never reads a sequence. A member
name is an assembly accession, so this answers genome-level questions only; the
contig-level comparison D-213 fixes as A7.4's primary key needs the full pass and belongs
elsewhere.

**The formats it refuses.** GNU long names (`././@LongLink`, typeflag `L`) and pax extended
headers (typeflag `x`) store the real name in the member body, which this reader skips. It
raises on both rather than returning the placeholder name, because a truncated accession is
a name that looks right and joins wrongly.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any

__all__ = ["BLOCK", "TarIndexError", "TarMember", "walk_members"]


#: Every tar structure is a multiple of this.
BLOCK = 512

_LONG_NAME_TYPES = {b"L", b"K", b"x", b"g"}


class TarIndexError(RuntimeError):
    """A refusal: the archive is not in a shape this reader can name members from."""


@dataclasses.dataclass(frozen=True, slots=True)
class TarMember:
    """One member, named and located, with nothing of its contents read."""

    name: str
    size: int
    offset: int
    typeflag: str

    @property
    def is_file(self) -> bool:
        return self.typeflag in {"0", "\0", ""}


def _octal(field: bytes, *, what: str) -> int:
    """A tar numeric field. Octal, NUL- or space-terminated; empty means zero."""
    text = field.split(b"\0")[0].strip()
    if not text:
        return 0
    try:
        return int(text, 8)
    except ValueError as exc:
        if field and field[0] & 0x80:  # pragma: no cover - base-256, only past 8 GB
            raise TarIndexError(
                f"{what}: a base-256 numeric field, which means a member over 8 GB. "
                "This reader is for an archive of genomes and will not guess at it."
            ) from exc
        raise TarIndexError(f"{what}: {field!r} is not an octal tar field") from exc


def _checksum_ok(header: bytes) -> bool:
    """The header's own checksum, with the checksum field read as spaces, as tar defines it."""
    stated = _octal(header[148:156], what="checksum")
    blanked = header[:148] + b" " * 8 + header[156:]
    return stated in (sum(blanked), sum(bytearray(blanked)))


def walk_members(read: Any, size: int) -> Iterator[TarMember]:
    """Yield every member of a tar, reading only its headers.

    Args:
        read: `read(offset, length) -> bytes`, a ranged reader over the archive.
        size: the archive's length in bytes, which bounds the walk.

    Raises:
        TarIndexError: on a header that does not checksum, or on an extended-name format
            whose real name is in a body this reader does not read.
    """
    offset = 0
    seen = 0
    while offset + BLOCK <= size:
        header = read(offset, BLOCK)
        if len(header) < BLOCK:  # pragma: no cover - a truncated archive
            raise TarIndexError(f"offset {offset}: {len(header)} bytes where a header belongs")
        if header == b"\0" * BLOCK:
            return  # the end-of-archive marker; trailing padding is not an error
        if not _checksum_ok(header):
            raise TarIndexError(
                f"offset {offset}: the header does not checksum. The chain is only as good "
                f"as the sizes it followed, so this is a refusal rather than a skip "
                f"({seen} members read so far)."
            )
        typeflag = header[156:157]
        if typeflag in _LONG_NAME_TYPES:
            raise TarIndexError(
                f"offset {offset}: typeflag {typeflag!r} stores the member's real name in "
                "its body, which this reader skips. A placeholder name joins wrongly and "
                "silently, so the archive needs a reader that decompresses."
            )
        name = header[:100].split(b"\0")[0].decode("utf-8", "replace")
        prefix = header[345:500].split(b"\0")[0].decode("utf-8", "replace")
        member_size = _octal(header[124:136], what=f"size at offset {offset}")
        yield TarMember(
            name=f"{prefix}/{name}" if prefix else name,
            size=member_size,
            offset=offset + BLOCK,
            typeflag=typeflag.decode("ascii", "replace"),
        )
        seen += 1
        offset += BLOCK + ((member_size + BLOCK - 1) // BLOCK) * BLOCK

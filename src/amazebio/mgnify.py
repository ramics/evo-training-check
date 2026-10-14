"""Streaming acquisition of a pinned MGnify protein release.

Why this is separate from `amazebio.uniref`
-------------------------------------------

The two releases A1.5 stages are the same problem in different packaging. UniRef
serves one tarball of tarballs, so `uniref` has to walk tar members inside a gzip
stream it cannot seek; MGnify serves each file separately, with an md5 per file in
a published `md5sum.txt`. That removes the hard part and adds a better guarantee:
the verification is per object rather than over the whole release, so a file can be
checked *before* its upload is made permanent.

Which matters more than it sounds. The corpus bucket withholds `s3:DeleteObject`,
so a completed upload is forever. Here the ordering is sound by construction: the
digest is computed as the bytes pass through, and `complete_multipart_upload` is
only reached if it matches, because a mismatch raises inside the sink's `with`
block and the sink aborts on an exception. A1.3 could not get that ordering for
UniRef's extracted members, and said so.

Everything else is reused rather than rewritten, as A1.5's task file asks:
`uniref.ResumableRead` is the resume, `uniref.S3PartSink` is the upload, and
`uniref.VerificationError` is the failure. This module is the loop between them
and the pins it runs over.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from amazebio.uniref import VerificationError

_READ_CHUNK = 1 << 22  # 4 MiB, matching uniref's socket read size.


@dataclass(frozen=True)
class Staged:
    """What one verified transfer produced. Goes straight into a run manifest."""

    url: str
    expected_bytes: int
    expected_md5: str
    bytes_read: int
    md5: str
    sha256: str
    reconnects: int
    verified: bool
    partial: bool = False

    def as_manifest(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "bytes": self.bytes_read,
            "expected_bytes": self.expected_bytes,
            "md5": self.md5,
            "expected_md5": self.expected_md5,
            "sha256": self.sha256,
            "reconnects": self.reconnects,
            "verified": self.verified,
            "partial": self.partial,
        }


def stream_verified(
    reader: Any,
    sink: Any,
    *,
    expected_bytes: int,
    expected_md5: str,
    url: str = "",
    chunk: int = _READ_CHUNK,
    progress: Callable[[int], None] | None = None,
    max_bytes: int | None = None,
) -> Staged:
    """Copy `reader` into `sink`, and refuse to let a wrong transfer be completed.

    Raises `VerificationError` on a short read or an md5 mismatch. Call this inside
    the sink's `with` block: the raise is what makes the sink abort, and aborting is
    the only way to not write bytes to a bucket that cannot delete them.

    `max_bytes` stops early, for a smoke test of the whole path — network, resume,
    credentials, multipart — for a minute of transfer rather than an hour. A run
    stopped that way cannot be verified and says so: `verified` is False and
    `partial` is True, so no manifest can later be read as a verified transfer.
    """
    # MGnify publishes md5 per file; the algorithm is the publisher's choice, not ours.
    digest = hashlib.md5()
    read = 0
    while True:
        if max_bytes is not None and read >= max_bytes:
            break
        want = chunk if max_bytes is None else min(chunk, max_bytes - read)
        data = reader.read(want)
        if not data:
            break
        digest.update(data)
        sink.write(data)
        read += len(data)
        if progress is not None:
            progress(read)

    partial = max_bytes is not None and read >= max_bytes
    result = Staged(
        url=url or getattr(reader, "url", ""),
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
        bytes_read=read,
        md5=digest.hexdigest(),
        sha256=getattr(sink, "sha256", ""),
        reconnects=getattr(reader, "reconnects", 0),
        verified=False,
        partial=partial,
    )
    if partial:
        return result

    if read != expected_bytes:
        raise VerificationError(
            f"{result.url}: read {read} bytes, the release publishes {expected_bytes}. "
            "Aborting rather than completing the upload: the bucket has no delete, so "
            "a truncated object written here could never be removed."
        )
    if result.md5 != expected_md5:
        raise VerificationError(
            f"{result.url}: md5 {result.md5} does not match the published "
            f"{expected_md5}. Aborting rather than completing the upload."
        )
    return Staged(**{**result.__dict__, "verified": True})

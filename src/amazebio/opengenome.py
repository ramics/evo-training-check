"""Reconstruct and stage the Evo nucleotide corpora for A1.2.

Two releases, one lineage. `LongSafari/open-genome` (OpenGenome, Evo 1) is where
the only published exclusion procedure was applied; `arcinstitute/opengenome2`
(OpenGenome2, Evo 2) carries that corpus forward whole and adds components the
filter never saw. A1.1 verified both are stated to be the training corpora, so
Phase A audits the released artefacts rather than proxies — see
`policies/corpora.md` §2-3 and DECISIONS.md D-017, D-019, D-020.

Three things about these releases shape every function here.

**They are enormous and mostly irrelevant to the filter.** OpenGenome2 is 5.52 TB
across 1,126 files, of which 2.17 TB is eukaryotic reference genomes added after
the filter was designed and 252 GB is metagenomic sequence that taxonomy has
never labelled. The component the published procedure actually acts on — IMG/VR
viral sequence — is 11.2 GB, 0.2% of the release. So staging is *selective by
component*, and :data:`COMPONENTS` records which role each component plays in the
audit rather than leaving that judgement to whoever writes the next pipeline.

**The same sequences are published twice, and only one copy is traceable.**
OpenGenome2 ships a `fasta/` tree and a `json/` tree. The FASTA keeps source
accessions in the record headers — `IMGVR_UViG_2505313053_000001` and the like —
while the JSON is the preprocessed training format, whose viral records carry a
bare `text` field with no accession and no lineage tag (the component is named
`imgvr_untagged`, and the name is accurate). A7.1 has to diff released records
against IMG/VR v4, and an untraceable record cannot be diffed, so the FASTA is
the representation this module stages. :func:`representation_of` is how that
choice is applied rather than assumed.

**Every file publishes its own SHA-256.** HuggingFace exposes the Git LFS oid for
each blob, which is a SHA-256 over the file's contents. That makes the pin exact
per file, with no reliance on a URL outliving the project, and it means a staged
object can be verified before it is made permanent. :func:`stage_blob` hashes the
stream as it passes and completes the upload only on a match — the corpus bucket
withholds `s3:DeleteObject`, so an object that completes is forever, and an
object claiming to be a release it has not been shown to be is worse than no
object at all (the same commitment D-026 made for UniRef).

The HTTP and object-storage plumbing is shared with the UniRef staging path:
:class:`~amazebio.uniref.ResumableRead` for a forward-only reader that survives a
dropped connection, and :class:`~amazebio.uniref.S3PartSink` for a concurrent
multipart upload that aborts rather than half-finishes.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from amazebio.uniref import ResumableRead, S3PartSink, VerificationError

_READ_CHUNK = 1 << 22  # 4 MiB off the socket at a time.
_API = "https://huggingface.co/api/datasets"
_RESOLVE = "https://huggingface.co/datasets"


# --------------------------------------------------------------------------- #
# The pins
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Release:
    """A pinned dataset release.

    `revision` is a commit SHA rather than `main` deliberately. Both releases have
    moved since publication — OpenGenome2 twice in September 2026 — and a branch
    name is not a pin. `data_frozen_at` records when the sequence files themselves
    last changed, which is the figure that matters: later commits touched only
    documentation and a species metadata CSV.
    """

    key: str
    dataset: str
    revision: str
    stated_files: int
    stated_bytes: int
    data_frozen_at: str
    #: Which published representation is staged. Both representations appear in
    #: the composition table, because both are part of the release; only this one
    #: is uploaded. Separating the two is the point: the table describes what was
    #: published and the selection records what we chose to hold.
    staged_representation: str
    note: str


OG1 = Release(
    key="opengenome",
    dataset="LongSafari/open-genome",
    revision="84369c058d192dcb607086d71679b877421e3250",
    stated_files=22,
    stated_bytes=146_886_935_899,
    data_frozen_at="2024-07-06",
    staged_representation="parquet",
    note=(
        "Evo 1's corpus, and the artefact the published exclusion procedure produced. "
        "All 20 data files landed in a single commit on 2024-07-06; the 11 commits since "
        "are README edits only."
    ),
)

OG2 = Release(
    key="opengenome2",
    dataset="arcinstitute/opengenome2",
    revision="84d2a7e690c8bb395d1f4868822dfa031ea561c6",
    stated_files=1126,
    stated_bytes=5_523_240_795_932,
    data_frozen_at="2025-02-18",
    staged_representation="fasta",
    note=(
        "Evo 2's corpus. All 1,123 sequence files were committed on 2025-02-17 and "
        "2025-02-18, alongside the preprint, and none has changed since: the only later "
        "commits add species_metadata.csv and edit the README. So pinning this revision "
        "pins the publication-time sequence content."
    ),
)

RELEASES = {release.key: release for release in (OG1, OG2)}


# --------------------------------------------------------------------------- #
# Components and their role in the audit
# --------------------------------------------------------------------------- #

#: What part each component plays. These are not descriptive labels; each one
#: determines whether a component is evidence for a Phase A claim, and which.
ROLES = {
    "viral": (
        "IMG/VR sequence — the component the published exclusion procedure acts on. "
        "A7.1 diffs it against IMG/VR v4; A2 looks for survivors in it."
    ),
    "plasmid": (
        "IMG/PR plasmid sequence, carried over from Evo 1. Adjacent to the filter's "
        "target rather than its subject; the procedure's host-count rule reads it."
    ),
    "prokaryotic": (
        "GTDB prokaryotic genomes. Not the filter's target, but where A2.4 looks for "
        "integrated elements, and what the prokaryotic-host rule counts against."
    ),
    "eukaryotic": (
        "Eukaryotic reference genomes and genic windows, added after the filter was "
        "designed and with no viral screening step in their published curation "
        "(policies/corpora.md §4). A2.3's target for endogenous elements."
    ),
    "metagenomic": (
        "Metagenomes and MAGs. Taxonomy has never labelled this sequence, so a "
        "taxonomy-based filter cannot act on it at all; A4.1 measures the fraction."
    ),
    "organelle": "Organelle genomes.",
    "transcript_regulatory": (
        "mRNA, ncRNA, transcripts, splice and promoter sequence. Derived from the "
        "eukaryotic material rather than independently screened."
    ),
}


@dataclass(frozen=True)
class Component:
    """One named component of a release, and where its files live."""

    name: str
    role: str
    #: Path prefixes, relative to the release root, that belong to this component.
    prefixes: tuple[str, ...]
    #: True if the staging tier the project owner approved includes it.
    tier1: bool
    why: str


#: OpenGenome2, FASTA representation. The `json/` tree holds the same sequences
#: and is deliberately unlisted for staging — see this module's docstring.
OG2_COMPONENTS = (
    Component(
        "imgvr",
        "viral",
        (
            "fasta/plasmids_phage/imgvr",
            "json/pretraining_or_both_phases/imgvr_untagged/",
        ),
        True,
        "The filter's output. Without it there is no Phase A.",
    ),
    Component(
        "imgpr",
        "plasmid",
        (
            "fasta/plasmids_phage/imgpr",
            "json/midtraining_specific/imgpr/",
        ),
        True,
        "Small, and the host-count rule reads plasmid-host associations.",
    ),
    Component(
        "gtdb",
        "prokaryotic",
        (
            "fasta/gtdb_v220",
            "json/pretraining_or_both_phases/gtdb_v220_imgpr/",
            "json/midtraining_specific/gtdb_v220_stitched/",
        ),
        True,
        "A2.4 searches these genomes for integrated elements.",
    ),
    Component(
        "promoters",
        "transcript_regulatory",
        (
            "fasta/promoters",
            "json/pretraining_or_both_phases/promoters/",
        ),
        True,
        "0.1 GB; no reason to defer it.",
    ),
    Component(
        "ncrna",
        "transcript_regulatory",
        (
            "fasta/ncrna",
            "json/pretraining_or_both_phases/ncrna/",
        ),
        True,
        "4.2 GB, and ncRNA is where A2.5's problem taxa are hardest to label.",
    ),
    Component(
        "organelles",
        "organelle",
        (
            "fasta/organelles",
            "json/pretraining_or_both_phases/organelle/",
        ),
        True,
        "0.8 GB; cheaper to stage now than to decide twice.",
    ),
    Component(
        "metagenomes",
        "metagenomic",
        (
            "fasta/metagenomes",
            "json/pretraining_or_both_phases/metagenomes/",
        ),
        False,
        "252 GB, and A4.1 is not started. Deferred to that task.",
    ),
    Component(
        "ncbi_eukaryotic_genomes",
        "eukaryotic",
        (
            "fasta/ncbi_eukaryotic_genomes",
            "json/midtraining_specific/ncbi_eukaryotic_genomes/",
        ),
        False,
        "2.17 TB. Deferred to A2.3, which is the only task that needs it.",
    ),
    Component(
        "eukaryotic_genic_windows",
        "eukaryotic",
        (
            "fasta/eukaryotic_genic_windows",
            "json/pretraining_or_both_phases/eukaryotic_genic_windows/",
        ),
        False,
        "129 GB of windows cut from the genomes above; defer with them.",
    ),
    Component(
        "mrna",
        "transcript_regulatory",
        (
            "fasta/mrna",
            "fasta/mrna_splice",
            "fasta/transcripts",
            "json/pretraining_or_both_phases/mrna/",
            "json/pretraining_or_both_phases/mrna_splice_promoter/",
        ),
        False,
        "52 GB, eukaryote-derived; no Phase A task reads it yet.",
    ),
)

#: OpenGenome v1, Parquet. One representation only — there is no FASTA tree.
OG1_COMPONENTS = (
    Component(
        "stage2",
        "viral",
        ("stage2/",),
        True,
        (
            "The viral component, with a taxonomic lineage tag inline on every record "
            "(policies/corpora.md §3). A7.1 re-executes Evo 1's own procedure against it."
        ),
    ),
    Component(
        "stage1_gtdb",
        "prokaryotic",
        ("stage1/gtdb/",),
        False,
        "130 GB, and OpenGenome2's GTDB component supersedes it for A2.4.",
    ),
    Component(
        "stage1_imgpr",
        "plasmid",
        ("stage1/imgpr/",),
        False,
        "2.7 GB, superseded by OpenGenome2's IMG/PR component.",
    ),
)

COMPONENTS = {OG1.key: OG1_COMPONENTS, OG2.key: OG2_COMPONENTS}


def representation_of(path: str) -> str:
    """Which published representation a path belongs to.

    OpenGenome2 publishes `fasta/` and `json/` trees of the same sequences; v1
    publishes Parquet only. Named rather than inferred at each call site, because
    the choice between the two is a finding (the JSON viral records carry no
    accession) and not a file-extension detail.
    """
    if path.startswith("fasta/"):
        return "fasta"
    if path.startswith("json/"):
        return "json"
    if path.endswith(".parquet"):
        return "parquet"
    return "other"


def component_of(release: Release, path: str) -> Component | None:
    """The component a path belongs to, or None if it is not sequence data.

    README, `.gitattributes` and `species_metadata.csv` return None: they are part
    of the release but not part of the corpus, and conflating the two is how a
    composition table acquires a row nobody can explain.
    """
    for component in COMPONENTS[release.key]:
        if any(path.startswith(prefix) for prefix in component.prefixes):
            return component
    return None


# --------------------------------------------------------------------------- #
# Reading the release manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Blob:
    """One file in a release, as the dataset API describes it."""

    path: str
    size: int
    #: Git LFS oid — a SHA-256 over the file's contents. None for the few small
    #: files committed to Git directly rather than to LFS.
    sha256: str | None
    last_commit: str | None

    @property
    def verifiable(self) -> bool:
        return self.sha256 is not None


def _get_json(url: str, opener: Callable[[urllib.request.Request], Any]) -> tuple[Any, str | None]:
    """Fetch JSON and the `Link: rel="next"` URL, if the response paginates."""
    request = urllib.request.Request(url, headers={"User-Agent": "amazebio/A1.2"})
    response = opener(request)
    payload = json.load(response)
    link = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        link = headers.get("Link", "") or ""
    following = None
    if 'rel="next"' in link:
        following = link.split("<", 1)[1].split(">", 1)[0]
    return payload, following


def fetch_tree(
    release: Release,
    *,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
) -> list[Blob]:
    """List every file in a pinned release, with size and published checksum.

    The tree endpoint pages at 1,000 entries and OpenGenome2 has 1,126 files, so
    following `Link: rel="next"` is not optional — a single-page read silently
    loses 126 files and every total computed from it is wrong.
    """
    url = f"{_API}/{release.dataset}/tree/{release.revision}?recursive=true&expand=true"
    blobs: list[Blob] = []
    while url:
        payload, url = _get_json(url, opener)
        for entry in payload:
            if entry.get("type") != "file":
                continue
            lfs = entry.get("lfs") or {}
            blobs.append(
                Blob(
                    path=entry["path"],
                    size=int(entry.get("size", 0)),
                    sha256=lfs.get("oid"),
                    last_commit=(entry.get("lastCommit") or {}).get("date"),
                )
            )
    return blobs


def verify_manifest(release: Release, blobs: Iterable[Blob]) -> list[dict[str, Any]]:
    """Compare a fetched tree against the release's recorded pin.

    Returned as rows rather than raised, on the same principle as
    `uniref.composition_check`: a release that has grown a file since the pin was
    taken is a finding to report, not a crash. The caller decides whether to stage
    on a mismatch — :func:`stage` refuses, because staging is irreversible.
    """
    blobs = list(blobs)
    found_files, found_bytes = len(blobs), sum(b.size for b in blobs)
    return [
        {
            "quantity": "files",
            "stated": release.stated_files,
            "found": found_files,
            "agrees": found_files == release.stated_files,
        },
        {
            "quantity": "bytes",
            "stated": release.stated_bytes,
            "found": found_bytes,
            "agrees": found_bytes == release.stated_bytes,
        },
    ]


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def composition(release: Release, blobs: Iterable[Blob]) -> list[dict[str, Any]]:
    """The composition table: one row per component and representation.

    This is A1.2's second deliverable, and the reason it is computed rather than
    transcribed is that A4.3 has to state what fraction of each corpus was never a
    candidate for removal. A hand-written table cannot be re-derived when the pin
    moves; this one can.
    """
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    unassigned: list[tuple[str, int]] = []
    for blob in blobs:
        component = component_of(release, blob.path)
        if component is None:
            unassigned.append((blob.path, blob.size))
            continue
        key = (component.name, representation_of(blob.path))
        row = buckets.setdefault(
            key,
            {
                "release": release.key,
                "component": component.name,
                "representation": key[1],
                "role": component.role,
                "role_note": ROLES[component.role],
                "staged": component.tier1 and key[1] == release.staged_representation,
                "tier1_component": component.tier1,
                "why": component.why,
                "files": 0,
                "bytes": 0,
                "unverifiable_files": 0,
            },
        )
        row["files"] += 1
        row["bytes"] += blob.size
        if not blob.verifiable:
            row["unverifiable_files"] += 1
    rows = sorted(buckets.values(), key=lambda r: (-r["bytes"], r["component"]))
    total = sum(r["bytes"] for r in rows)
    for row in rows:
        row["share_of_release"] = round(row["bytes"] / total, 6) if total else 0.0
    if unassigned:
        rows.append(
            {
                "release": release.key,
                "component": "(not corpus)",
                "representation": "other",
                "role": "none",
                "role_note": "Release metadata — README, .gitattributes, species metadata.",
                "staged": False,
                "tier1_component": False,
                "why": "Documentation, not sequence. Listed so the file count reconciles.",
                "files": len(unassigned),
                "bytes": sum(size for _, size in unassigned),
                "unverifiable_files": 0,
                "share_of_release": 0.0,
                "paths": sorted(path for path, _ in unassigned),
            }
        )
    return rows


def selection(release: Release, blobs: Iterable[Blob]) -> list[Blob]:
    """The blobs the approved staging tier covers, in a stable order.

    Two filters, and they are independent. The component must be in the approved
    tier, *and* the file must be in the representation this release is staged in
    — otherwise a release that publishes the same sequences twice would be staged
    twice, at double the permanent cost, with the untraceable copy included.

    Ordered by path so a resumed or repeated pass stages the same files in the
    same sequence, which is what makes "already staged, skipped" meaningful.
    """
    chosen = [
        blob
        for blob in blobs
        if (component := component_of(release, blob.path)) is not None
        and component.tier1
        and representation_of(blob.path) == release.staged_representation
    ]
    return sorted(chosen, key=lambda b: b.path)


# --------------------------------------------------------------------------- #
# Staging
# --------------------------------------------------------------------------- #


def resolve_url(release: Release, path: str) -> str:
    """The pinned download URL for one file."""
    return f"{_RESOLVE}/{release.dataset}/resolve/{release.revision}/{path}"


def stage_key(release: Release, path: str, *, prefix: str) -> str:
    """Where a file lands in object storage.

    The release key and revision are both in the path. A bucket that cannot
    delete will accumulate releases, and an object whose key does not say which
    revision it came from becomes unattributable the moment a second pin exists.
    """
    return f"{prefix.rstrip('/')}/{release.key}/{release.revision}/{path}"


@dataclass
class StagedFile:
    """The outcome of staging one file. Goes into the run manifest verbatim."""

    path: str
    uri: str
    bytes: int
    sha256: str
    expected_sha256: str | None
    verified: bool
    reconnects: int
    skipped: bool = False
    #: How the checksum was established: "stream" (hashed on the way up),
    #: "readback" (re-read from the bucket and hashed), or "none: <reason>".
    #: A bare `verified: false` invites exactly the question §7 says to expect,
    #: so the reason travels with it.
    verified_by: str = "stream"

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "uri": self.uri,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "expected_sha256": self.expected_sha256,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "reconnects": self.reconnects,
            "skipped": self.skipped,
        }


#: Below this size, an object already in the bucket is re-read and hashed rather
#: than taken on trust. Above it, the egress is charged per byte and a resumed
#: pass over the large files would pay to re-download what it just uploaded, so
#: the row records that it was not re-verified instead of quietly claiming it was.
READBACK_LIMIT = 1 << 30


def verify_staged_object(
    client: Any, *, bucket: str, key: str, blob: Blob, chunk: int = _READ_CHUNK
) -> tuple[bool, str]:
    """Re-read a staged object and hash it against the release's published SHA-256.

    Stronger evidence than the in-flight hash: it checks the bytes the bucket
    actually holds, rather than the bytes that went past on the way there.
    """
    if blob.sha256 is None:
        return False, "none: the release publishes no checksum for this file"
    digest = hashlib.sha256()
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        while True:
            piece = body.read(chunk)
            if not piece:
                break
            digest.update(piece)
    finally:
        close = getattr(body, "close", None)
        if close is not None:
            close()
    return digest.hexdigest() == blob.sha256, digest.hexdigest()


def stage_blob(
    release: Release,
    blob: Blob,
    client: Any,
    *,
    bucket: str,
    prefix: str,
    part_bytes: int = 64 << 20,
    concurrency: int = 8,
    on_progress: Callable[[int, int], None] | None = None,
    opener: Callable[[urllib.request.Request], Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> StagedFile:
    """Stream one file from the release into object storage, verifying as it goes.

    Nothing touches local disk: the working disk here is far smaller than the
    selection, and a staging path that needs scratch space equal to its output is
    a path that cannot run.

    The verification gate is the point of this function. The stream is hashed
    while it uploads, and `complete_multipart_upload` is called only once the
    digest matches the SHA-256 the release publishes for that file. On a mismatch
    the upload is aborted and :class:`VerificationError` is raised, so no object
    appears. That ordering is load-bearing: the corpus bucket withholds
    `s3:DeleteObject`, so there is exactly one chance to not write the wrong bytes.

    A file with no published checksum is refused rather than staged unverified.
    Both releases publish one for every sequence file, so this only ever fires on
    something that is not corpus data — which should not reach here at all.
    """
    if blob.sha256 is None:
        raise VerificationError(
            f"{blob.path} publishes no LFS checksum, so a staged copy could not be shown "
            "to be the released bytes. Refusing to stage it."
        )

    key = stage_key(release, blob.path, prefix=prefix)
    uri = f"s3://{bucket}/{key}"
    reader = ResumableRead(
        url=resolve_url(release, blob.path),
        expected_bytes=blob.size,
        opener=opener,
        sleep=sleep,
        on_reconnect=lambda attempt, pos, exc: print(
            f"    reconnect #{attempt} at byte {pos:,}: {type(exc).__name__}: {exc}",
            flush=True,
        ),
    )
    sink = S3PartSink(client, bucket, key, part_bytes=part_bytes, concurrency=concurrency).open()
    try:
        while True:
            chunk = reader.read(_READ_CHUNK)
            if not chunk:
                break
            sink.write(chunk)
            if on_progress is not None:
                on_progress(sink.bytes_written, blob.size)
        if sink.bytes_written != blob.size:
            raise VerificationError(
                f"{blob.path}: read {sink.bytes_written:,} bytes, release states "
                f"{blob.size:,}. Not completing the upload."
            )
        if sink.sha256 != blob.sha256:
            raise VerificationError(
                f"{blob.path}: SHA-256 {sink.sha256} does not match the published "
                f"{blob.sha256}. Upload aborted; no object was written."
            )
        sink.complete()
    except BaseException:
        sink.abort()
        raise
    finally:
        reader.close()

    return StagedFile(
        path=blob.path,
        uri=uri,
        bytes=sink.bytes_written,
        sha256=sink.sha256,
        expected_sha256=blob.sha256,
        verified=True,
        reconnects=reader.reconnects,
    )


@dataclass
class StagePlan:
    """What a staging pass will do, costed, before it does any of it."""

    release: Release
    blobs: list[Blob] = field(default_factory=list)

    @property
    def files(self) -> int:
        return len(self.blobs)

    @property
    def bytes(self) -> int:
        return sum(b.size for b in self.blobs)

    @property
    def monthly_usd(self) -> float:
        """S3 Standard at $0.023/GB-month. Storage is the standing cost here, not
        transfer: HuggingFace charges no egress and S3 charges no ingress."""
        return self.bytes / 1e9 * 0.023

    def unverifiable(self) -> list[Blob]:
        return [b for b in self.blobs if not b.verifiable]


def plan(release: Release, blobs: Iterable[Blob]) -> StagePlan:
    return StagePlan(release=release, blobs=selection(release, blobs))


def existing_keys(client: Any, *, bucket: str, prefix: str, release: Release) -> dict[str, int]:
    """Keys already staged for this release and revision, mapped to their size.

    A pass that cannot resume is a pass that has to be right first time over
    144 GB. Listing first makes a repeat run cheap and makes "skipped" a verified
    statement rather than an assumption.
    """
    found: dict[str, int] = {}
    token: str | None = None
    base = f"{prefix.rstrip('/')}/{release.key}/{release.revision}/"
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": base}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", ()):
            found[item["Key"]] = int(item["Size"])
        if not page.get("IsTruncated"):
            return found
        token = page.get("NextContinuationToken")


def stage(
    release: Release,
    blobs: Iterable[Blob],
    client: Any,
    *,
    bucket: str,
    prefix: str,
    manifest_rows: list[dict[str, Any]] | None = None,
    resume: bool = True,
    readback_limit: int = READBACK_LIMIT,
    on_file: Callable[[Blob, str], None] | None = None,
    **blob_kwargs: Any,
) -> Iterator[StagedFile]:
    """Stage the approved selection, one file at a time, skipping what is done.

    Yields rather than returns so a caller can record each file in the run
    manifest as it lands. A pass over this selection takes long enough that a
    container reclaim partway through is a real possibility, and a manifest
    written only at the end would lose the record of everything that succeeded.

    Refuses to start if the fetched tree disagrees with the recorded pin. Staging
    is irreversible, so a release that has changed under the pin is a question for
    the project owner, not something to resolve by uploading.
    """
    blobs = list(blobs)
    disagreements = [row for row in verify_manifest(release, blobs) if not row["agrees"]]
    if disagreements:
        detail = "; ".join(
            f"{row['quantity']}: pinned {row['stated']:,}, found {row['found']:,}"
            for row in disagreements
        )
        raise VerificationError(
            f"{release.dataset} at {release.revision[:12]} does not match its recorded "
            f"pin ({detail}). Refusing to stage: the bucket cannot delete, so the pin is "
            "resolved before anything is written, not after."
        )

    already = existing_keys(client, bucket=bucket, prefix=prefix, release=release) if resume else {}
    for blob in selection(release, blobs):
        key = stage_key(release, blob.path, prefix=prefix)
        if already.get(key) == blob.size:
            if blob.size <= readback_limit:
                ok, found = verify_staged_object(client, bucket=bucket, key=key, blob=blob)
                if not ok and found.startswith("none: "):
                    sha, verified, how = "", False, found
                elif not ok:
                    raise VerificationError(
                        f"{blob.path} is already staged at {key}, but re-reading it gives "
                        f"SHA-256 {found}, not the published {blob.sha256}. The object in the "
                        "bucket is not the released bytes."
                    )
                else:
                    sha, verified, how = found, True, "readback"
            else:
                sha, verified, how = (
                    "",
                    False,
                    f"none: already staged at the released size; re-reading {blob.size:,} "
                    "bytes to confirm it costs egress, so run a readback pass in-region "
                    "instead of trusting this row",
                )
            staged = StagedFile(
                path=blob.path,
                uri=f"s3://{bucket}/{key}",
                bytes=blob.size,
                sha256=sha,
                expected_sha256=blob.sha256,
                verified=verified,
                reconnects=0,
                skipped=True,
                verified_by=how,
            )
        else:
            if on_file is not None:
                on_file(blob, key)
            staged = stage_blob(release, blob, client, bucket=bucket, prefix=prefix, **blob_kwargs)
        if manifest_rows is not None:
            manifest_rows.append(staged.as_dict())
        yield staged

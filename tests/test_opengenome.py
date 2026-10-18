"""Tests for the Evo nucleotide corpus staging path (A1.2).

The expensive mistakes this path can make are all irreversible or silent, so
those are what these tests pin down: a paginated manifest read short, a staged
object completed without being checked against the release's own checksum, a
component selected that the approved tier excludes, and a composition table whose
totals do not reconcile with the release.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import pathlib

import pytest

from amazebio import opengenome as og
from amazebio.uniref import VerificationError

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class _Response(io.BytesIO):
    """A urlopen result: bytes plus the headers the paginating reader looks at."""

    def __init__(self, payload: bytes, headers: dict[str, str] | None = None):
        super().__init__(payload)
        self.headers = headers or {}
        self.status = 200


def _tree_opener(pages: list[tuple[list[dict], str | None]]):
    """An opener that serves successive tree pages, with `Link: rel="next"`."""
    calls: list[str] = []

    def opener(request):
        index = len(calls)
        calls.append(request.full_url)
        entries, following = pages[index]
        headers = {}
        if following:
            headers["Link"] = f'<{following}>; rel="next"'
        return _Response(json.dumps(entries).encode(), headers)

    opener.calls = calls  # type: ignore[attr-defined]
    return opener


def _entry(path: str, size: int, *, oid: str | None = "ab" * 32, date: str = "2025-02-17"):
    entry: dict = {"type": "file", "path": path, "size": size, "lastCommit": {"date": date}}
    if oid is not None:
        entry["lfs"] = {"oid": oid, "size": size}
    return entry


class FakeS3:
    def __init__(
        self,
        listing: dict[str, int] | None = None,
        objects: dict[str, bytes] | None = None,
    ):
        self.parts: dict[int, bytes] = {}
        self.completed = None
        self.aborted = False
        self.objects = objects or {}
        self.listing = listing or {k: len(v) for k, v in self.objects.items()}
        self.listing.update(listing or {})

    def create_multipart_upload(self, **kw):
        self.key = kw["Key"]
        return {"UploadId": "upload-1"}

    def upload_part(self, **kw):
        self.parts[kw["PartNumber"]] = kw["Body"]
        return {"ETag": f'"etag-{kw["PartNumber"]}"'}

    def complete_multipart_upload(self, **kw):
        self.completed = kw["MultipartUpload"]
        return {}

    def abort_multipart_upload(self, **kw):
        self.aborted = True
        return {}

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.objects[kw["Key"]])}

    def list_objects_v2(self, **kw):
        prefix = kw["Prefix"]
        contents = [{"Key": k, "Size": v} for k, v in self.listing.items() if k.startswith(prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def assembled(self) -> bytes:
        return b"".join(self.parts[n] for n in sorted(self.parts))


def _body_opener(payload: bytes):
    def opener(request):
        start = 0
        rng = request.get_header("Range")
        if rng:
            start = int(rng.split("=", 1)[1].split("-", 1)[0])
        response = _Response(payload[start:])
        response.status = 206 if rng else 200
        return response

    return opener


# --------------------------------------------------------------------------- #
# The pins
# --------------------------------------------------------------------------- #


def test_revisions_are_commit_shas_not_branch_names():
    """`main` is not a pin, and both releases have moved since publication."""
    for release in og.RELEASES.values():
        assert len(release.revision) == 40
        assert release.revision not in {"main", "master"}
        assert all(c in "0123456789abcdef" for c in release.revision)


def test_the_pinned_totals_are_the_ones_decisions_recorded():
    assert og.OG2.dataset == "arcinstitute/opengenome2"
    assert (og.OG2.stated_files, og.OG2.stated_bytes) == (1126, 5_523_240_795_932)
    assert og.OG1.dataset == "LongSafari/open-genome"
    assert (og.OG1.stated_files, og.OG1.stated_bytes) == (22, 146_886_935_899)


def test_every_component_names_a_role_that_exists():
    """A component whose role is not in ROLES has no documented place in the audit."""
    for components in og.COMPONENTS.values():
        for component in components:
            assert component.role in og.ROLES, component


# --------------------------------------------------------------------------- #
# Reading the manifest
# --------------------------------------------------------------------------- #


def test_a_paginated_tree_is_followed_to_the_end():
    """OpenGenome2 has 1,126 files and the endpoint pages at 1,000: a single-page
    read loses 126 files and silently understates every total computed from it."""
    opener = _tree_opener(
        [
            ([_entry("fasta/ncrna/a.fasta.gz", 10)], "https://example/next"),
            ([_entry("fasta/ncrna/b.fasta.gz", 20)], None),
        ]
    )
    blobs = og.fetch_tree(og.OG2, opener=opener)
    assert [b.path for b in blobs] == ["fasta/ncrna/a.fasta.gz", "fasta/ncrna/b.fasta.gz"]
    assert sum(b.size for b in blobs) == 30
    assert len(opener.calls) == 2  # type: ignore[attr-defined]


def test_the_pinned_revision_is_what_gets_requested():
    opener = _tree_opener([([], None)])
    og.fetch_tree(og.OG1, opener=opener)
    assert og.OG1.revision in opener.calls[0]  # type: ignore[attr-defined]


def test_directories_are_not_mistaken_for_files():
    opener = _tree_opener(
        [([{"type": "directory", "path": "fasta"}, _entry("README.md", 5)], None)]
    )
    assert [b.path for b in og.fetch_tree(og.OG2, opener=opener)] == ["README.md"]


def test_a_tree_that_disagrees_with_the_pin_is_reported_not_raised():
    """A release that changed under the pin is a finding; the caller decides."""
    rows = og.verify_manifest(og.OG2, [og.Blob("fasta/ncrna/a.gz", 1, "ab" * 32, None)])
    assert [row["agrees"] for row in rows] == [False, False]
    assert {row["quantity"] for row in rows} == {"files", "bytes"}


# --------------------------------------------------------------------------- #
# Components and composition
# --------------------------------------------------------------------------- #


def test_the_viral_component_is_separated_from_the_plasmid_one():
    """Both live under `fasta/plasmids_phage/`, and only one is the filter's target."""
    viral = og.component_of(og.OG2, "fasta/plasmids_phage/imgvr.fasta.gz")
    plasmid = og.component_of(og.OG2, "fasta/plasmids_phage/imgpr.fasta.gz")
    assert viral is not None and viral.role == "viral"
    assert plasmid is not None and plasmid.role == "plasmid"


def test_gtdb_subdirectories_both_land_in_the_prokaryotic_component():
    for path in ("fasta/gtdb_v220/all.fasta.gz", "fasta/gtdb_v220/v214/part.fasta.gz"):
        component = og.component_of(og.OG2, path)
        assert component is not None and component.name == "gtdb"


def test_release_metadata_is_not_corpus():
    for path in ("README.md", ".gitattributes", "species_metadata.csv"):
        assert og.component_of(og.OG2, path) is None


def test_representation_is_named_rather_than_guessed_from_the_extension():
    assert og.representation_of("fasta/ncrna/a.fasta.gz") == "fasta"
    assert og.representation_of("json/x/y.jsonl.gz") == "json"
    assert og.representation_of("stage2/train_stage2.parquet") == "parquet"
    assert og.representation_of("README.md") == "other"


def test_composition_reconciles_with_the_release_and_keeps_metadata_separate():
    blobs = [
        og.Blob("fasta/plasmids_phage/imgvr.fasta.gz", 300, "aa" * 32, None),
        og.Blob("fasta/ncrna/a.fasta.gz", 100, "bb" * 32, None),
        og.Blob("README.md", 7, None, None),
    ]
    rows = og.composition(og.OG2, blobs)
    corpus = [r for r in rows if r["component"] != "(not corpus)"]
    assert sum(r["files"] for r in corpus) == 2
    assert sum(r["bytes"] for r in corpus) == 400
    assert rows[0]["component"] == "imgvr"  # ordered by size
    assert rows[0]["share_of_release"] == pytest.approx(0.75)
    metadata = [r for r in rows if r["component"] == "(not corpus)"]
    assert metadata and metadata[0]["paths"] == ["README.md"]


def test_the_same_component_in_two_representations_stays_two_rows():
    """Both representations are part of the release, so both belong in the
    composition table — but only one is staged. Collapsing the rows would
    double-count the same sequences; dropping the JSON row would understate the
    release by 2.79 TB and file it under "not corpus" alongside the README."""
    blobs = [
        og.Blob("fasta/ncrna/a.fasta.gz", 100, "aa" * 32, None),
        og.Blob("json/pretraining_or_both_phases/ncrna/a.jsonl.gz", 90, "bb" * 32, None),
    ]
    rows = og.composition(og.OG2, blobs)
    assert [r["component"] for r in rows] == ["ncrna", "ncrna"]
    by_repr = {r["representation"]: r for r in rows}
    assert by_repr["fasta"]["staged"] is True
    assert by_repr["json"]["staged"] is False
    assert (
        by_repr["json"]["tier1_component"] is True
    ), "the component is approved; it is the representation that is not staged"


def test_json_sequence_files_are_corpus_even_though_they_are_not_staged():
    """The regression this guards: with only `fasta/` prefixes mapped, all 1,005
    of OpenGenome2's JSON files fell into the "(not corpus)" row with the README."""
    rows = og.composition(
        og.OG2,
        [
            og.Blob(
                "json/pretraining_or_both_phases/imgvr_untagged/data_imgvr_train.jsonl.gz",
                7,
                "aa" * 32,
                None,
            )
        ],
    )
    assert [r["component"] for r in rows] == ["imgvr"]
    assert rows[0]["role"] == "viral"


def test_the_unstaged_representation_is_excluded_from_the_selection():
    """OpenGenome2 publishes the same sequences twice. Staging both would double a
    permanent cost and include the copy that cannot be traced to IMG/VR."""
    blobs = [
        og.Blob("fasta/plasmids_phage/imgvr.fasta.gz", 1, "aa" * 32, None),
        og.Blob(
            "json/pretraining_or_both_phases/imgvr_untagged/data_imgvr_train.jsonl.gz",
            1,
            "bb" * 32,
            None,
        ),
    ]
    assert [b.path for b in og.selection(og.OG2, blobs)] == ["fasta/plasmids_phage/imgvr.fasta.gz"]


def test_opengenome_v1_stages_its_only_representation():
    """v1 publishes Parquet alone, so the representation filter must not exclude
    everything — the same rule has to work for a release with one tree."""
    blobs = [og.Blob("stage2/train_stage2.parquet", 1, "aa" * 32, None)]
    assert og.OG1.staged_representation == "parquet"
    assert [b.path for b in og.selection(og.OG1, blobs)] == ["stage2/train_stage2.parquet"]


def test_a_file_with_no_published_checksum_is_counted_as_unverifiable():
    rows = og.composition(og.OG2, [og.Blob("fasta/ncrna/a.fasta.gz", 10, None, None)])
    assert rows[0]["unverifiable_files"] == 1


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_selection_takes_the_approved_tier_only():
    """2.17 TB of eukaryotic genomes are excluded by decision, not by accident."""
    blobs = [
        og.Blob("fasta/plasmids_phage/imgvr.fasta.gz", 1, "aa" * 32, None),
        og.Blob("fasta/ncbi_eukaryotic_genomes/a.fasta.gz", 1, "bb" * 32, None),
        og.Blob("fasta/metagenomes/a.fasta.gz", 1, "cc" * 32, None),
        og.Blob("README.md", 1, None, None),
    ]
    assert [b.path for b in og.selection(og.OG2, blobs)] == ["fasta/plasmids_phage/imgvr.fasta.gz"]


def test_selection_is_ordered_so_a_repeated_pass_matches():
    blobs = [
        og.Blob("fasta/ncrna/b.fasta.gz", 1, "aa" * 32, None),
        og.Blob("fasta/ncrna/a.fasta.gz", 1, "bb" * 32, None),
    ]
    assert [b.path for b in og.selection(og.OG2, blobs)] == [
        "fasta/ncrna/a.fasta.gz",
        "fasta/ncrna/b.fasta.gz",
    ]


def test_opengenome_v1s_viral_and_prokaryotic_stages_are_both_selected():
    """The prokaryotic component joined the tier on the owner's approval (D-119).

    It was out while the reading was that OpenGenome2's GTDB superseded it. A2.4 established
    that this amounts to substituting one release's bacterial genomes for another's, and the two
    releases pin different GTDB snapshots — so without it the prophage route is measured on one
    of the two corpora under audit.
    """
    blobs = [
        og.Blob("stage2/train_stage2.parquet", 1, "aa" * 32, None),
        og.Blob("stage1/gtdb/gtdb_train_shard_0.parquet", 1, "bb" * 32, None),
    ]
    assert [b.path for b in og.selection(og.OG1, blobs)] == [
        "stage1/gtdb/gtdb_train_shard_0.parquet",
        "stage2/train_stage2.parquet",
    ]


def test_opengenome_v1s_plasmid_stage_stays_out_of_the_tier():
    """D-119 widened the tier by one component, not into everything OG1 publishes."""
    blobs = [og.Blob("stage1/imgpr/imgpr_train_shard_0.parquet", 1, "cc" * 32, None)]
    assert og.selection(og.OG1, blobs) == []


def test_the_plan_prices_storage_rather_than_transfer():
    staging_plan = og.plan(
        og.OG2, [og.Blob("fasta/ncrna/a.fasta.gz", 1_000_000_000, "aa" * 32, None)]
    )
    assert staging_plan.files == 1
    assert staging_plan.monthly_usd == pytest.approx(0.023)


def test_keys_record_the_release_and_revision():
    """The bucket cannot delete, so it will hold several pins at once; a key that
    does not name its revision becomes unattributable the moment it does."""
    key = og.stage_key(og.OG2, "fasta/ncrna/a.fasta.gz", prefix="corpora/evo/")
    assert key == f"corpora/evo/opengenome2/{og.OG2.revision}/fasta/ncrna/a.fasta.gz"


# --------------------------------------------------------------------------- #
# Staging: the verification gate
# --------------------------------------------------------------------------- #


def test_a_matching_file_is_verified_and_completed():
    payload = b"ACGT" * 4096
    digest = hashlib.sha256(payload).hexdigest()
    blob = og.Blob("fasta/ncrna/a.fasta.gz", len(payload), digest, None)
    client = FakeS3()
    staged = og.stage_blob(
        og.OG2,
        blob,
        client,
        bucket="b",
        prefix="corpora/evo",
        part_bytes=5 << 20,
        concurrency=1,
        opener=_body_opener(payload),
    )
    assert staged.verified and staged.sha256 == digest
    assert client.completed is not None and not client.aborted
    assert client.assembled() == payload


def test_a_checksum_mismatch_leaves_no_object_at_all():
    """The decisive test. The bucket withholds DeleteObject, so an object that
    completes is permanent — the digest has to gate `complete`, not follow it."""
    payload = b"ACGT" * 4096
    blob = og.Blob("fasta/ncrna/a.fasta.gz", len(payload), "00" * 32, None)
    client = FakeS3()
    with pytest.raises(VerificationError, match="does not match the published"):
        og.stage_blob(
            og.OG2,
            blob,
            client,
            bucket="b",
            prefix="corpora/evo",
            part_bytes=5 << 20,
            concurrency=1,
            opener=_body_opener(payload),
            sleep=lambda _: None,
        )
    assert client.completed is None
    assert client.aborted


def test_a_short_read_is_refused_before_completion():
    payload = b"ACGT" * 1024
    blob = og.Blob(
        "fasta/ncrna/a.fasta.gz", len(payload) + 4096, hashlib.sha256(payload).hexdigest(), None
    )
    client = FakeS3()
    with pytest.raises(VerificationError):
        og.stage_blob(
            og.OG2,
            blob,
            client,
            bucket="b",
            prefix="corpora/evo",
            part_bytes=5 << 20,
            concurrency=1,
            opener=_body_opener(payload),
            sleep=lambda _: None,
        )
    assert client.completed is None and client.aborted


def test_a_file_without_a_published_checksum_is_refused_rather_than_staged():
    client = FakeS3()
    with pytest.raises(VerificationError, match="publishes no LFS checksum"):
        og.stage_blob(
            og.OG2,
            og.Blob("fasta/ncrna/a.fasta.gz", 4, None, None),
            client,
            bucket="b",
            prefix="corpora/evo",
            opener=_body_opener(b"ACGT"),
            sleep=lambda _: None,
        )
    assert client.completed is None


# --------------------------------------------------------------------------- #
# Staging: the pass
# --------------------------------------------------------------------------- #


def test_staging_refuses_a_release_that_no_longer_matches_its_pin():
    client = FakeS3()
    with pytest.raises(VerificationError, match="does not match its recorded pin"):
        list(
            og.stage(
                og.OG2,
                [og.Blob("fasta/ncrna/a.fasta.gz", 1, "aa" * 32, None)],
                client,
                bucket="b",
                prefix="corpora/evo",
            )
        )


def _pinned_to(blobs: list[og.Blob]) -> og.Release:
    """OG2 with its pin set to exactly this tree, so `stage` gets past the pin
    check and the test is about the behaviour under test. The key is unchanged,
    so component lookup still resolves."""
    return dataclasses.replace(
        og.OG2, stated_files=len(blobs), stated_bytes=sum(b.size for b in blobs)
    )


def test_a_pass_stages_what_is_missing_and_records_each_file():
    payload = b"ACGT" * 4096
    blobs = [
        og.Blob("fasta/ncrna/a.fasta.gz", len(payload), hashlib.sha256(payload).hexdigest(), None)
    ]
    release = _pinned_to(blobs)
    client = FakeS3()
    rows: list[dict] = []
    staged = list(
        og.stage(
            release,
            blobs,
            client,
            bucket="b",
            prefix="corpora/evo",
            manifest_rows=rows,
            part_bytes=5 << 20,
            concurrency=1,
            opener=_body_opener(payload),
            sleep=lambda _: None,
        )
    )
    assert [s.verified for s in staged] == [True]
    assert client.assembled() == payload
    assert rows[0]["expected_sha256"] == blobs[0].sha256


def test_a_partially_uploaded_file_is_not_treated_as_done():
    """Matching on size as well as key: a key present at the wrong length is a
    half-finished upload, and skipping it would stage a truncated corpus."""
    key = og.stage_key(og.OG2, "fasta/ncrna/a.fasta.gz", prefix="corpora/evo")
    client = FakeS3(listing={key: 99})
    found = og.existing_keys(client, bucket="b", prefix="corpora/evo", release=og.OG2)
    assert found[key] != 4096


def test_existing_keys_are_scoped_to_the_release_and_revision():
    mine = og.stage_key(og.OG2, "fasta/ncrna/a.fasta.gz", prefix="corpora/evo")
    theirs = og.stage_key(og.OG1, "stage2/train_stage2.parquet", prefix="corpora/evo")
    client = FakeS3(listing={mine: 1, theirs: 1})
    assert list(og.existing_keys(client, bucket="b", prefix="corpora/evo", release=og.OG1)) == [
        theirs
    ]


# --------------------------------------------------------------------------- #
# Readback verification of what is already in the bucket
# --------------------------------------------------------------------------- #


def test_a_skipped_file_is_verified_by_reading_it_back():
    """This is also the resume test: 144 GB is long enough that a container
    reclaim partway through is real, and an interrupted pass must skip rather
    than re-upload. A resumed pass must not leave a row saying `verified: false`
    with no reason either. Re-reading is also better evidence than the in-flight hash: it
    checks the bytes the bucket holds, not the bytes that went past."""
    payload = b"ACGT" * 4096
    digest = hashlib.sha256(payload).hexdigest()
    blobs = [og.Blob("fasta/ncrna/a.fasta.gz", len(payload), digest, None)]
    release = _pinned_to(blobs)
    key = og.stage_key(release, blobs[0].path, prefix="corpora/evo")
    client = FakeS3(objects={key: payload})
    rows: list[dict] = []
    staged = list(
        og.stage(release, blobs, client, bucket="b", prefix="corpora/evo", manifest_rows=rows)
    )
    assert staged[0].skipped and staged[0].verified
    assert staged[0].verified_by == "readback"
    assert rows[0]["sha256"] == digest
    assert client.completed is None, "verifying must not re-upload"


def test_a_staged_object_that_is_not_the_released_bytes_is_an_error():
    """The case worth catching: right size, wrong contents. Skipping on size
    alone would carry a corrupt object into every downstream result."""
    payload = b"ACGT" * 4096
    wrong = b"TGCA" * 4096
    blobs = [
        og.Blob("fasta/ncrna/a.fasta.gz", len(payload), hashlib.sha256(payload).hexdigest(), None)
    ]
    release = _pinned_to(blobs)
    key = og.stage_key(release, blobs[0].path, prefix="corpora/evo")
    client = FakeS3(objects={key: wrong})
    with pytest.raises(VerificationError, match="not the released bytes"):
        list(og.stage(release, blobs, client, bucket="b", prefix="corpora/evo"))


def test_a_large_skipped_file_records_why_it_was_not_re_read():
    """Re-reading 27 GB to confirm what was just uploaded costs egress per byte,
    so the row says so rather than claiming a check that did not happen."""
    payload = b"ACGT" * 4096
    blobs = [
        og.Blob("fasta/ncrna/a.fasta.gz", len(payload), hashlib.sha256(payload).hexdigest(), None)
    ]
    release = _pinned_to(blobs)
    key = og.stage_key(release, blobs[0].path, prefix="corpora/evo")
    client = FakeS3(objects={key: payload})
    rows: list[dict] = []
    staged = list(
        og.stage(
            release,
            blobs,
            client,
            bucket="b",
            prefix="corpora/evo",
            manifest_rows=rows,
            readback_limit=16,
        )
    )
    assert staged[0].skipped and not staged[0].verified
    assert staged[0].verified_by.startswith("none: already staged at the released size")


def test_readback_reports_the_digest_it_found():
    payload = b"ACGT" * 16
    blob = og.Blob(
        "fasta/ncrna/a.fasta.gz", len(payload), hashlib.sha256(payload).hexdigest(), None
    )
    client = FakeS3(objects={"k": payload})
    ok, found = og.verify_staged_object(client, bucket="b", key="k", blob=blob)
    assert ok and found == blob.sha256


def test_a_truncated_manifest_read_is_retried_not_accepted():
    """What killed a real pass: an IncompleteRead partway through the tree
    listing. A truncated body is a failure, so the JSON decode has to sit inside
    the retry — otherwise a short read becomes a short manifest, and a short
    manifest understates the release and fails the pin check for the wrong reason."""
    good = json.dumps([_entry("fasta/ncrna/a.fasta.gz", 10)]).encode()
    attempts = []

    def opener(request):
        attempts.append(request.full_url)
        if len(attempts) < 3:
            return _Response(good[: len(good) // 2])  # truncated JSON
        return _Response(good)

    blobs = og.fetch_tree(og.OG2, opener=opener, sleep=lambda _: None)
    assert [b.path for b in blobs] == ["fasta/ncrna/a.fasta.gz"]
    assert len(attempts) == 3


def test_a_manifest_that_never_reads_refuses_rather_than_staging_a_partial_one():
    def opener(request):
        raise OSError("connection reset")

    with pytest.raises(VerificationError, match="could not read"):
        og.fetch_tree(og.OG2, opener=opener, sleep=lambda _: None)


# --------------------------------------------------------------------------- #
# The manifest only ever improves
# --------------------------------------------------------------------------- #


def test_a_resumed_pass_does_not_discard_the_proof_an_earlier_pass_recorded():
    """The provenance bug this guards, which happened once for real: a resumed
    pass skips the large files, so its rows are weaker than the rows written when
    those files were uploaded and hashed. Overwriting the manifest with them
    erased the evidence that the corpus had ever been checked."""
    first = [{"path": "a", "verified": True, "verified_by": "stream", "sha256": "ab"}]
    second = [{"path": "a", "verified": False, "verified_by": "none: skipped", "sha256": ""}]
    merged = og.merge_staged_rows(first, second)
    assert merged == first


def test_a_stronger_check_replaces_a_weaker_one():
    stream = [{"path": "a", "verified": True, "verified_by": "stream", "sha256": "ab"}]
    readback = [{"path": "a", "verified": True, "verified_by": "readback", "sha256": "ab"}]
    assert og.merge_staged_rows(stream, readback) == readback


def test_merging_keeps_files_only_one_pass_saw():
    merged = og.merge_staged_rows(
        [{"path": "a", "verified_by": "stream"}], [{"path": "b", "verified_by": "readback"}]
    )
    assert [r["path"] for r in merged] == ["a", "b"]


class TestOfflineCompositionForA43:
    """The composition A4.3 publishes must rebuild from committed bytes, not from an API."""

    CAPTURES = pathlib.Path(__file__).resolve().parent.parent / "policies" / "captures"

    def test_the_capture_rebuilds_the_published_component_shares(self):
        # The headline A4.3 inherits from A1.2: the filtered component is 0.2% of
        # OpenGenome2 and 11.5% of OpenGenome v1. A figure that regenerates only while a
        # third-party API is up and unchanged is not reproducible from pinned inputs.
        blobs = og.blobs_from_capture(self.CAPTURES / "hf-opengenome2-manifest.json")
        assert len(blobs) == 1126
        rows = og.composition(og.RELEASES["opengenome2"], blobs)
        imgvr = {r["representation"]: r for r in rows if r["component"] == "imgvr"}
        assert round(imgvr["fasta"]["share_of_release"], 3) == 0.002

        v1 = og.blobs_from_capture(self.CAPTURES / "hf-open-genome-manifest.json")
        rows_v1 = og.composition(og.RELEASES["opengenome"], v1)
        stage2 = next(r for r in rows_v1 if r["component"] == "stage2")
        assert round(stage2["share_of_release"], 3) == 0.115

    def test_the_cards_own_phase_2_percentages_do_not_sum_and_are_kept_as_published(self):
        # Phase 1's stated column is sound; Phase 2's totals about 252% and gives 104% to a
        # single component. Recomputing silently would hide a published error that belongs in
        # the under-specification record, so both columns survive into the table.
        card = (self.CAPTURES / "hf-opengenome2-README.md").read_text()
        table = og.token_table(card)
        assert set(table) == set(og.PHASES)

        def stated_total(phase):
            return sum(float(r["stated_composition"].rstrip("%")) for r in table[phase])

        assert 99.0 < stated_total("Phase 1: Pretraining") < 101.0
        assert stated_total("Phase 2: Context Extension") > 200.0

        # Tolerance, not exactness: the shares are rounded to 6dp individually, so a
        # fourteen-row phase can sum to 1.000001. That is rounding, unlike Phase 2's 252%.
        for rows in table.values():
            assert abs(sum(r["computed_share"] for r in rows) - 1.0) < 1e-5

    def test_the_viral_component_token_share_differs_between_the_two_phases(self):
        # Which phase is the denominator changes the answer by more than four-fold, which is
        # why `policies/corpora.md` requires A4.3 to name the phase it is quoting.
        table = og.token_table((self.CAPTURES / "hf-opengenome2-README.md").read_text())
        viral = {
            phase: next(r for r in rows if "IMG/VR" in r["dataset"])
            for phase, rows in table.items()
        }
        p1 = viral["Phase 1: Pretraining"]["computed_share"]
        p2 = viral["Phase 2: Context Extension"]["computed_share"]
        assert p1 > 4 * p2

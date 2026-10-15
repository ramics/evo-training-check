"""Tests for A1.7's IMG/VR release pins.

The pins here are unusual and the tests are shaped by it: every checksum was read from the
publisher's public listing *before* this project held any of the bytes, because JGI serves the
inventory without authentication and refuses the files without it. So there is nothing to verify
a digest against yet, and what these tests protect is the thing that would actually go wrong —
a hand-edited constant drifting from the capture it came from, and the two-release ambiguity
being quietly collapsed to one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amazebio import imgvr

CAPTURE = (
    Path(__file__).resolve().parent.parent / "policies" / "captures" / ("jgi-imgvr-inventory.json")
)


@pytest.fixture(scope="module")
def capture() -> dict:
    return json.loads(CAPTURE.read_text())


def test_every_pinned_file_matches_the_publishers_captured_listing(capture):
    # Keyed on directory as well as date and name: two 2018 directories share a release date
    # and four file names between them, so a (date, name) key compares across releases.
    listed = {
        (f["added_date"], f["directory"], f["file_name"]): (f["file_size"], f["md5sum"])
        for f in capture["files"]
    }
    for date, release in imgvr.RELEASES.items():
        for f in release.files:
            key = (date, f.directory, f.name)
            assert key in listed, f"{f.name} is pinned for {date} but absent from the capture"
            size, md5 = listed[key]
            assert f.bytes == size, f"{f.name}: pinned {f.bytes}, capture {size}"
            assert f.md5 == md5, f"{f.name}: pinned {f.md5}, capture {md5}"


def test_checksums_are_full_md5_digests_not_truncated():
    # A truncated digest looks like a pin and is not one. The first draft of this module carried
    # ten-character prefixes copied out of a console listing, which is how that gets in.
    for release in imgvr.RELEASES.values():
        for f in release.files:
            assert len(f.md5) == 32, f"{f.name}: {f.md5!r} is not a full md5"
            assert all(c in "0123456789abcdef" for c in f.md5)


def test_both_releases_answering_to_v4_are_pinned():
    assert set(imgvr.V4_CANDIDATES) == set(imgvr.RELEASES)
    assert all(imgvr.release_on(d).version == "v4" for d in imgvr.V4_CANDIDATES)


def test_the_two_v4_releases_agree_on_sequence_and_host_and_differ_on_the_metadata():
    # This is the whole of D-052, and the reason A7.2 cannot pick a release arbitrarily: the
    # files that differ are the ones carrying the confidence label and the vOTU assignment,
    # which two of the three rules A7.1 could not run read.
    diff = imgvr.differs_between(*imgvr.V4_CANDIDATES)
    for name, differs in diff.items():
        if "nucleotides" in name or "Host_information" in name:
            assert not differs, f"{name} was expected byte-identical across the two v4 releases"
        if "Sequence_information" in name:
            assert differs, f"{name} was expected to differ across the two v4 releases"


def test_conformance_inputs_are_metadata_only_and_include_the_unfiltered_variant():
    for date in imgvr.V4_CANDIDATES:
        files = imgvr.conformance_inputs(date)
        roles = {f.role for f in files}
        assert roles == {"sequence_information", "host_information", "readme"}
        assert "nucleotides" not in roles and "proteins" not in roles
        # Auditing a gate that keeps high-confidence records needs records that fail it.
        seq = [f for f in files if f.role == "sequence_information"]
        assert any(
            not f.high_confidence for f in seq
        ), "the high-confidence file cannot show a record the gate should have removed"
        assert any(f.high_confidence for f in seq)


def test_conformance_inputs_are_a_small_fraction_of_the_release():
    for date in imgvr.V4_CANDIDATES:
        needed = sum(f.bytes for f in imgvr.conformance_inputs(date))
        total = imgvr.release_on(date).total_bytes
        assert needed < 0.1 * total, (
            "if this ever fails, the scoping argument in D-053 — metadata not sequence — needs "
            "re-checking before anything is staged"
        )


def test_every_role_is_documented():
    documented = set(imgvr.FILE_ROLES)
    used = {f.role for r in imgvr.RELEASES.values() for f in r.files}
    assert used <= documented, f"undocumented role(s): {sorted(used - documented)}"


def test_an_unpinned_release_is_refused_with_the_reason():
    with pytest.raises(KeyError, match="no pinned IMG/VR release"):
        imgvr.release_on("2020-09-11")


def test_the_capture_contains_colliding_date_and_name_pairs_across_directories(capture):
    # The reason every lookup here is keyed on directory too. If this ever stops being true the
    # key could be simplified — but it was true on acquisition and the simpler key reported four
    # phantom changes on the first run of the inventory check.
    seen: dict[tuple[str, str], set[str]] = {}
    for f in capture["files"]:
        seen.setdefault((f["added_date"], f["file_name"]), set()).add(f["directory"])
    collisions = {k: v for k, v in seen.items() if len(v) > 1}
    assert collisions, "expected at least one (date, name) pair spanning two directories"


def test_the_download_url_is_the_hosts_documented_single_file_read():
    # Pinned because the first version of the staging tool used the search host's
    # `filedownload/?_id=` form, which answers `Allow: POST, OPTIONS` — a GET there would have
    # failed on the method once a token existed, and reported itself as an auth failure. The
    # documented read is a path segment on the download host, and it is the only shape that
    # survived being checked against the live API.
    url = imgvr.download_url("632a1b312de7c323533daac5")
    assert url == "https://files-download.jgi.doe.gov/download_files/632a1b312de7c323533daac5/"
    assert "?" not in url, "the id is a path segment, not a query parameter"
    assert url.startswith(imgvr.DOWNLOAD_BASE)

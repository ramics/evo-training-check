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
    # Both are candidates for Evo 1's "IMG/VR v4" citation; only one of them is called v4.
    # The publisher's own READMEs name the September release v4 and the December one v4.1,
    # an erratum of it (D-063). Pinned here because a later task that re-derives the version
    # from a README is a later task that can get it wrong, and because the asymmetry is the
    # finding: the citation points at September, and the erratum touches exactly the table
    # September's confidence and vOTU rules read.
    assert imgvr.release_on("2022-09-20").version == "v4"
    assert imgvr.release_on("2022-12-20").version == "v4.1"


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


def test_the_download_request_is_the_route_that_actually_serves_bytes():
    # Pinned because two earlier versions had this wrong in ways no measurement could catch
    # without a credential. The search host's `filedownload/?_id=` form answers
    # `Allow: POST, OPTIONS` (D-060), and the download host's documented single-file
    # `GET /download_files/<id>/` answers 404 for every IMG/VR file once authenticated — both
    # of which are indistinguishable from a missing token while unauthenticated (D-062). What
    # returns bytes is a POST keyed by organism id, verified end to end against the live API.
    url, body = imgvr.download_request(
        ["632a1b312de7c323533daac5"], organism_id="Custom_MPI-IMG_VR", top_hit="63a22c8a"
    )
    assert url == "https://files-download.jgi.doe.gov/download_files/"
    assert url == imgvr.DOWNLOAD_BASE
    assert body == {
        "ids": {
            "Custom_MPI-IMG_VR": {
                "file_ids": ["632a1b312de7c323533daac5"],
                "top_hit": "63a22c8a",
            }
        }
    }
    # top_hit is the id string. The search response nests an object there, and posting the
    # object rather than its `_id` returns HTTP 500.
    assert isinstance(body["ids"]["Custom_MPI-IMG_VR"]["top_hit"], str)

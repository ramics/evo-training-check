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


# --------------------------------------------------------------------------------------
# A7.2 — reading the metadata tables
# --------------------------------------------------------------------------------------


def test_the_canonical_host_domain_agrees_with_a1_7s_own_copy():
    # `tools/imgvr_composition.py` carries its own `_host_domain` from A1.7 and this module now
    # carries the canonical one. Two implementations of the word "host" across two passes is how
    # a composition artefact and a conformance artefact come to disagree about the same column,
    # so the agreement is asserted rather than assumed. If this ever fails, the fix is one
    # implementation, not two adjusted ones.
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "imgvr_composition_for_agreement",
        pathlib.Path(__file__).resolve().parent.parent / "tools" / "imgvr_composition.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    battery = [
        "",
        "   ",
        ";;;",
        ";",
        "d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria",
        "d__Archaea;p__Thermoproteota",
        "d__Eukaryota;p__Chordata",
        "d__",
        "p__Proteobacteria;c__Gammaproteobacteria",
        "Bacteria",
        "d__Bacteria",
    ]
    for value in battery:
        assert imgvr.host_domain(value) == mod._host_domain(value), value


def test_host_class_keeps_an_unclassifiable_assignment_apart_from_an_absent_one():
    # The strict reading's exclusivity test turns on exactly this difference: a record with host
    # evidence this audit cannot classify is not a record with no host evidence, and folding the
    # first into the second would retain records the reading removes.
    assert imgvr.host_class("d__Bacteria;p__Proteobacteria") == "prokaryotic"
    assert imgvr.host_class("d__Archaea;p__Thermoproteota") == "prokaryotic"
    assert imgvr.host_class("d__Eukaryota;p__Chordata") == "eukaryotic"
    assert imgvr.host_class("d__Viruses") == "other"
    assert imgvr.host_class(";;;") is None
    assert imgvr.host_class("") is None


def test_both_published_accession_shapes_survive_the_join_key():
    # IMG/VR ships two accession shapes and the second one is the population a
    # eukaryote-infecting-virus filter is judged on: GVMAG is a giant-virus
    # metagenome-assembled genome. An earlier version of the packing dropped them from every
    # join silently, which would have removed exactly those records from the converse direction.
    numeric = "IMGVR_UViG_2504643025_000001"
    gvmag = "IMGVR_UViG_GVMAG-M-2140918012-1_000001"
    assert imgvr.uvig_key(numeric) == 2504643025 * 10**7 + 1
    with pytest.raises(imgvr.UvigNotPackable):
        imgvr.uvig_key(gvmag)
    assert imgvr.uvig_join_key(numeric) > 0
    assert imgvr.uvig_join_key(gvmag) < 0, "the fallback space must not collide with packed keys"
    assert imgvr.split_uvig(gvmag) == ("GVMAG-M-2140918012-1", 1)


def test_the_join_key_is_stable_across_passes_rather_than_a_local_id():
    # The two sides of every join in A7.2 are computed by different passes at different times,
    # so a vocabulary-assigned id would not match across them. The key has to be a function of
    # the accession alone, and this is what would catch it being replaced by a counter.
    gvmag = "IMGVR_UViG_GVMAG-S-3300000115-46_000001"
    assert imgvr.uvig_join_key(gvmag) == imgvr.uvig_fallback_key(gvmag)
    assert imgvr.uvig_fallback_key(gvmag) == imgvr.uvig_fallback_key(f"  {gvmag}  ")


def test_a_malformed_accession_raises_rather_than_being_carried_as_a_record():
    # A second accession shape and an unreadable row are different findings. The first is
    # carried under a hashed key; the second is counted and excluded, and must not be able to
    # masquerade as the first.
    for bad in ("", "IMGVR_UViG_", "IMGVR_UViG_2504643025", "scaffold_12345", "IMGVR_2504_1"):
        with pytest.raises(ValueError) as caught:
            imgvr.uvig_join_key(bad)
        assert not isinstance(caught.value, imgvr.UvigNotPackable), bad


def test_collision_free_reports_both_counts_rather_than_a_bare_flag():
    accessions = [
        "IMGVR_UViG_GVMAG-M-2140918012-1_000001",
        "IMGVR_UViG_GVMAG-M-2140918012-2_000001",
        "IMGVR_UViG_GVMAG-S-3300000101-140_000001",
    ]
    assert imgvr.collision_free(accessions) == (True, 3, 3)
    assert imgvr.collision_free(accessions + accessions) == (True, 3, 3)


def test_votu_identifiers_become_their_own_integer():
    assert imgvr.votu_id("vOTU_00000001") == 1
    assert imgvr.votu_id("vOTU_8606551") == 8606551
    for bad in ("", "vOTU", "OTU_1", "vOTU_abc"):
        with pytest.raises(ValueError):
            imgvr.votu_id(bad)


def test_the_columns_the_rules_read_are_named_not_indexed():
    # v4.1 is an in-place erratum of the sequence-information table (D-063), so a column index
    # is a guess about a file that has already been re-cut once.
    assert imgvr.SEQ_COLUMNS["classification"] == "Taxonomic classification"
    assert imgvr.SEQ_COLUMNS["confidence"] == "Confidence"
    assert imgvr.SEQ_COLUMNS["votu"] == "vOTU"
    assert set(imgvr.HOST_COLUMNS) == {"uvig", "method", "host"}

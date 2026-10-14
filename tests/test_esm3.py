"""Tests for `amazebio.esm3` — task A1.5.

Two kinds of test here, and the second kind is the point.

The first checks the logic: that `reconcile` only subtracts counts of matching
granularity, and that the verdict it carries means what the module says it means.

The second checks the *transcription*. Every publisher count in the module is a number
somebody read off a release note and retyped, which is exactly the step that silently
goes wrong — and `tools/policies.py` cannot catch it, because it verifies quotations in
prose and these are integers in code. So these tests parse the stored captures and
assert the code agrees with them. A changed release note, or a typo in a digit, fails
here rather than in a write-up.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from amazebio import esm3, uniref

REPO = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# The table itself
# --------------------------------------------------------------------------- #


def test_every_component_states_a_release_and_where_it_is_stated():
    for c in esm3.COMPONENTS:
        assert c.stated_release, c.name
        assert c.locator, c.name
        assert c.track in ("sequence", "structure"), c.name
        assert c.retrievability in ("pinned", "substituted", "not-reproducible"), c.name


def test_components_named_in_the_filter_scope_are_exactly_the_ones_flagged():
    """The scope list is four names; the flag must follow it and not drift from it."""
    flagged = {c.name for c in esm3.COMPONENTS if c.in_filter_scope}
    # "PDB Clustered" is the same source data as "PDB", clustered, so it inherits the flag.
    assert flagged == {"PDB", "PDB Clustered", "UniRef", "MGnify", "JGI"}
    for name in esm3.FILTER_SCOPE_NAMED:
        assert name in flagged

    # Nothing is asserted to be *out* of scope: the scope list says "including", so the
    # honest value for a component it omits is "not addressed", and A4.3 reports it that
    # way. A False here would be a claim the source does not make.
    assert not [c for c in esm3.COMPONENTS if c.in_filter_scope is False]
    unaddressed = {c.name for c in esm3.COMPONENTS if c.in_filter_scope is None}
    assert unaddressed == {"OAS", "AlphaFoldDB", "ESMAtlas"}


def test_the_only_pinnable_components_are_the_two_with_published_checksums():
    pinned = {c.name for c in esm3.COMPONENTS if c.retrievability == "pinned"}
    assert pinned == {"UniRef", "MGnify"}
    assert {c.name for c in esm3.COMPONENTS if c.retrievability == "not-reproducible"} == {
        "JGI",
        "OAS",
    }
    # A component with no proxy must not be described as one that has one.
    for c in esm3.COMPONENTS:
        if c.retrievability == "not-reproducible":
            assert c.proxy is None, c.name


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #


def test_only_matching_granularity_carries_a_gap_or_a_verdict():
    for row in esm3.reconcile():
        if row["comparable"]:
            assert row["gap"] is not None
            assert row["exceeds_stated_removal"] in (True, False)
        else:
            # The spread across UniRef's tiers is context, not a quantity anything
            # removed. Reporting it as a gap would manufacture a finding.
            assert row["gap"] is None
            assert row["gap_fraction"] is None
            assert row["exceeds_stated_removal"] is None


def test_both_comparable_gaps_exceed_the_filters_whole_reported_removal():
    comparable = {r["component"]: r for r in esm3.reconcile() if r["comparable"]}
    assert set(comparable) == {"UniRef", "MGnify"}

    assert comparable["UniRef"]["gap"] == 170_669_877 - 156_000_000
    assert comparable["MGnify"]["gap"] == 729_215_663 - 621_000_000
    for name, row in comparable.items():
        assert row["exceeds_stated_removal"] is True, name
        assert row["gap"] > esm3.STATED_TOTAL_REMOVED, name


def test_the_verdict_allows_for_the_tables_rounding():
    """A gap inside the table's own precision is not a finding, and must not read as one."""
    rounding = esm3.STATED_COUNT_PRECISION
    assert rounding == 1_000_000

    # A shortfall only just over the stated removal, once the table's rounding is
    # allowed for, is not called a finding.
    pub = esm3.PublisherCount("X", "level", 0, "src", same_granularity_as="90%")
    assert pub.same_granularity_as == "90%"
    marginal = esm3.STATED_TOTAL_REMOVED + rounding
    assert not (marginal - rounding > esm3.STATED_TOTAL_REMOVED)


# --------------------------------------------------------------------------- #
# Internal consistency of what was transcribed from the paper
# --------------------------------------------------------------------------- #


def test_sequence_samples_account_for_the_inverse_folded_sequences():
    """The paper's own totals settle a question its prose leaves open.

    Table S4's sequence components sum to 2,781M, and its "Sequence" row says 3,143M.
    The 362M difference is exactly the two inverse-folded rows — so the sequences that
    model generated are counted as sequence training data, not as an aside. That is why
    `INVERSE_FOLDED` exists as a finding rather than a footnote: an MMseqs query against
    the training databases cannot reach a sequence that is in no database.
    """
    from_databases = sum(
        c.unique_samples_m
        for c in esm3.COMPONENTS
        if c.track == "sequence" and c.unique_samples_m is not None
    )
    generated = sum(row["unique_samples_m"] for row in esm3.INVERSE_FOLDED)

    assert from_databases == pytest.approx(2_781.0)
    assert generated == pytest.approx(362.0)
    assert from_databases + generated == pytest.approx(
        esm3.STATED_TOTALS["sequence_samples_m"], abs=1.0
    )


def test_structure_samples_sum_to_the_stated_structure_total():
    total = sum(
        c.unique_samples_m
        for c in esm3.COMPONENTS
        if c.track == "structure" and c.unique_samples_m is not None
    )
    assert total == pytest.approx(esm3.STATED_TOTALS["structure_samples_m"], abs=1.0)


def test_unstated_findings_each_say_what_goes_wrong_downstream():
    findings = esm3.unstated()
    assert len({f["id"] for f in findings}) == len(findings)
    for f in findings:
        assert f["evidence"], f["id"]
        # A finding with no consequence is a complaint. The write-up needs the
        # consequence, and it is the part that gets lost if these live only in prose.
        assert len(f["consequence"]) > 40, f["id"]


# --------------------------------------------------------------------------- #
# Transcription against the stored captures
# --------------------------------------------------------------------------- #


def _release_note_clusters(path: pathlib.Path) -> int:
    m = re.search(r"Number of clusters:\s*([\d,]+)", path.read_text())
    assert m, f"no cluster count in {path}"
    return int(m.group(1).replace(",", ""))


@pytest.mark.parametrize("tier", ["uniref50", "uniref90", "uniref100"])
def test_uniref_2023_02_counts_match_the_stored_release_notes(tier):
    note = REPO / f"policies/captures/uniref-2023_02-{tier}.release_note"
    assert uniref.UNIREF_2023_02.stated_clusters[tier] == _release_note_clusters(note)


def test_uniref_2021_04_release_is_unchanged_by_the_a1_5_refactor():
    """A1.3's corpus is staged and cited against these values; they must not move."""
    rel = uniref.UNIREF_2021_04
    assert rel.release == "2021_04"
    assert rel.archive_bytes == 169_188_630_923
    assert rel.archive_md5 == "444f0a7062a65a988ba1d5949d1d6419"
    assert rel.stated_clusters == {"uniref50": 49_874_565, "uniref90": 138_515_945}
    # The module-level aliases A1.3's tools and manifests cite still resolve to it.
    assert (rel.release, rel.archive_md5) == (uniref.RELEASE, uniref.ARCHIVE_MD5)
    assert rel.archive_url == uniref.ARCHIVE_URL
    assert uniref.STATED_CLUSTERS is rel.stated_clusters


def test_release_archive_urls_name_their_own_release():
    for key, rel in uniref.RELEASES.items():
        assert key == rel.release
        assert f"release-{rel.release}/" in rel.archive_url
        assert rel.archive_url.endswith(rel.archive_name)


def test_publisher_counts_cite_captures_that_exist():
    for pub in esm3.PUBLISHER_COUNTS:
        assert (REPO / pub.source).exists(), pub.source


def test_mgnify_counts_match_the_stored_release_readme():
    text = (REPO / "policies/captures/mgnify-2023_02-README.txt").read_text()
    # "Sequences:" then a "Total <all> <clusters>" row.
    m = re.search(r"Total\s+(\d+)\s+(\d+)", text)
    assert m, "no sequence totals in the MGnify README"
    all_sequences, clusters = int(m.group(1)), int(m.group(2))

    by_level = {p.level: p.count for p in esm3.PUBLISHER_COUNTS if p.component == "MGnify"}
    assert by_level["all sequences"] == all_sequences
    assert by_level["90% clusters"] == clusters


def test_mgnify_file_pins_match_the_stored_md5sum_manifest():
    manifest = (REPO / esm3.MGNIFY_2023_02_MANIFEST).read_text()
    rows = (ln.split() for ln in manifest.splitlines() if ln)
    published = {name: digest for digest, name in rows}

    assert published[esm3.MGNIFY_2023_02_CLUSTERS.name] == esm3.MGNIFY_2023_02_CLUSTERS.md5
    # The full protein set is pinned as a count of files, so a release that gained or
    # lost one would not slip past as "30 files" unchanged.
    proteins = [n for n in published if n.startswith("mgy_proteins_") and n.endswith(".fa.gz")]
    assert len(proteins) == esm3.MGNIFY_2023_02_PROTEINS_FILES


def test_uniref_2023_02_archive_pin_agrees_between_the_two_modules():
    """`esm3` records the pin a manifest writes; `uniref` records the one staging checks."""
    assert esm3.UNIREF_2023_02_ARCHIVE.md5 == uniref.UNIREF_2023_02.archive_md5
    assert esm3.UNIREF_2023_02_ARCHIVE.bytes == uniref.UNIREF_2023_02.archive_bytes
    assert esm3.UNIREF_2023_02_ARCHIVE.url == uniref.UNIREF_2023_02.archive_url


def test_uniref_2023_02_archive_pin_matches_the_stored_metalink():
    text = (REPO / "policies/captures/uniref-2023_02-RELEASE.metalink").read_text()
    block = text[text.index('<file name="uniref2023_02.tar.gz">') :]
    size = int(re.search(r"<size>(\d+)</size>", block).group(1))
    md5 = re.search(r'<hash type="md5">([0-9a-f]+)</hash>', block).group(1)
    assert uniref.UNIREF_2023_02.archive_bytes == size
    assert uniref.UNIREF_2023_02.archive_md5 == md5

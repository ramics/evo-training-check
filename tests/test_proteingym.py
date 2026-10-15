"""Tests for the benchmark ingest — task B2.1.

The assertions that carry weight are the ones that would let a wrong number look right: the
metric's tie handling, the join being on the mutant string rather than row order, and the
taxon labels being rejected rather than coerced when the release moves. Everything else is
plumbing.

Tests that need the staged release skip when it is absent — `data/` is git-ignored, so CI has
the code but not the 1.9 GB of archives. The end-to-end agreement with the maintainers'
published values is checked by `tools/proteingym_check.py` against the staged data and
recorded in its artefact, which is where a 217-assay comparison belongs.
"""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import pytest

from amazebio.proteingym import (
    RELEASE,
    Assay,
    ProteinGymError,
    Taxon,
    _ranks,
    by_taxon,
    load_assay,
    load_model_scores,
    load_reference,
    paired,
    spearman,
    verify_release,
)

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "proteingym" / RELEASE.version
REFERENCE = DATA / RELEASE.reference_file

needs_data = pytest.mark.skipif(not REFERENCE.exists(), reason="benchmark release not staged")


# --- the metric ------------------------------------------------------------------------


def test_spearman_endpoints():
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_known_value():
    """Textbook case: one adjacent swap at each end of five points gives 0.8."""
    assert spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) == pytest.approx(0.8)


def test_spearman_is_rank_based_not_value_based():
    """A monotone transform of either input must not change the answer."""
    x = [1.0, 2.0, 3.0, 4.0, 9.0]
    y = [2.0, 1.0, 4.0, 3.0, 5.0]
    assert spearman(x, y) == pytest.approx(spearman([v**3 for v in x], y))


def test_ranks_average_ties():
    """Ties take the mean of the ranks they span — scipy's `rankdata` "average" convention.

    Pinned against literal expected values rather than against another call of the same
    function: an identity assertion passes under every tie convention, which is how a
    self-comparison here survived the first review.
    """
    assert _ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
    assert _ranks([5, 5, 5]) == [2.0, 2.0, 2.0]
    assert _ranks([3, 1, 2]) == [3.0, 1.0, 2.0]
    assert _ranks([1, 1, 2, 2]) == [1.5, 1.5, 3.5, 3.5]


def test_spearman_averages_ties():
    """The tie rule changes the answer, so the expected value is computed by hand.

    x = [1,2,3,4], y = [10,20,20,30]. Average ranks: rx = [1,2,3,4], ry = [1,2.5,2.5,4].
    Centred, that is dx = [-1.5,-0.5,0.5,1.5] and dy = [-1.5,0,0,1.5], giving
    cov = 2.25+0+0+2.25 = 4.5 over sqrt(5 * 4.5) = sqrt(22.5), i.e. 0.9486832980505138.
    An ordinal or min/max tie rule gives a different number, so this pins the convention
    the published values were computed with.
    """
    assert spearman([1, 2, 3, 4], [10, 20, 20, 30]) == pytest.approx(0.9486832980505138)
    # Swapping the tied pair's x values cannot change the result, because the tie carries no
    # order of its own.
    assert spearman([1, 3, 2, 4], [5, 7, 7, 9]) == pytest.approx(
        spearman([1, 2, 3, 4], [5, 7, 7, 9])
    )


@pytest.mark.parametrize(
    ("x", "y", "match"),
    [
        ([1, 2, 3], [1, 2], "length mismatch"),
        ([1.0], [2.0], "at least two"),
        ([1, 1, 1], [1, 2, 3], "constant"),
    ],
)
def test_spearman_refuses_degenerate_input(x, y, match):
    """A constant input has no defined rank correlation; 0.0 would read as a real null."""
    with pytest.raises(ProteinGymError, match=match):
        spearman(x, y)


# --- the join --------------------------------------------------------------------------


def test_paired_joins_on_mutant_not_position():
    """The regression this function exists to prevent.

    The score archive's row order is not guaranteed to match the assay file's. A positional
    join would pair the wrong variants and still return a plausible correlation, which is the
    kind of error that survives review and poisons every downstream number.
    """
    measured = {"A1B": 1.0, "C2D": 2.0, "E3F": 3.0}
    predicted = {"E3F": 3.0, "A1B": 1.0, "C2D": 2.0}  # same data, reversed order
    x, y, unscored = paired(measured, predicted)
    assert unscored == 0
    assert spearman(x, y) == pytest.approx(1.0)


def test_paired_counts_variants_the_model_did_not_score():
    measured = {"A1B": 1.0, "C2D": 2.0, "E3F": 3.0}
    predicted = {"A1B": 0.5, "C2D": 0.7}
    x, y, unscored = paired(measured, predicted)
    assert len(x) == len(y) == 2
    assert unscored == 1


# --- the reference file ----------------------------------------------------------------


def _write_reference(path: Path, rows: list[dict[str, str]]) -> Path:
    cols = [
        "DMS_id",
        "UniProt_ID",
        "taxon",
        "source_organism",
        "DMS_filename",
        "seq_len",
        "DMS_number_single_mutants",
        "DMS_number_multiple_mutants",
        "selection_assay",
        "selection_type",
        "MSA_Neff_L_category",
        "jo",
        "year",
    ]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


def _row(**kw: str) -> dict[str, str]:
    base = {
        "DMS_id": "TEST_ASSAY_2024",
        "UniProt_ID": "TEST_HUMAN",
        "taxon": "Human",
        "source_organism": "Homo sapiens",
        "DMS_filename": "TEST_ASSAY_2024.csv",
        "seq_len": "100",
        "DMS_number_single_mutants": "10",
        "DMS_number_multiple_mutants": "2",
        "selection_assay": "Growth",
        "selection_type": "Growth",
        "MSA_Neff_L_category": "Medium",
        "jo": "10.0/x",
        "year": "2024",
    }
    return base | kw


def test_load_reference_parses_taxon_and_counts(tmp_path):
    p = _write_reference(tmp_path / "ref.csv", [_row(), _row(DMS_id="V", taxon="Virus")])
    assays = load_reference(p)
    assert [a.taxon for a in assays] == [Taxon.HUMAN, Taxon.VIRUS]
    assert assays[0].n_variants == 12
    assert assays[1].is_viral and not assays[0].is_viral
    assert by_taxon(assays) == {"Virus": 1, "Prokaryote": 0, "Human": 1, "Eukaryote": 0}


def test_load_reference_rejects_an_unknown_taxon(tmp_path):
    """A new label means the release moved under the pin; coercing it would hide that."""
    p = _write_reference(tmp_path / "ref.csv", [_row(taxon="Archaea")])
    with pytest.raises(ProteinGymError, match="unknown taxon"):
        load_reference(p)


def test_load_reference_rejects_a_nonnumeric_count(tmp_path):
    p = _write_reference(tmp_path / "ref.csv", [_row(DMS_number_single_mutants="lots")])
    with pytest.raises(ProteinGymError, match="not a number"):
        load_reference(p)


def test_load_reference_refuses_an_empty_file(tmp_path):
    p = _write_reference(tmp_path / "ref.csv", [])
    with pytest.raises(ProteinGymError, match="no assays"):
        load_reference(p)


# --- the archives ----------------------------------------------------------------------


def _assay(filename: str = "TEST.csv") -> Assay:
    return Assay(
        dms_id="TEST",
        uniprot_id="T",
        taxon=Taxon.HUMAN,
        source_organism="x",
        filename=filename,
        seq_len=10,
        n_singles=3,
        n_multiples=0,
        selection_assay="Growth",
        selection_type="Growth",
        msa_depth_category="Low",
        doi="10.0/x",
        year="2024",
    )


def _zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return path


def test_load_assay_reads_the_nested_member(tmp_path):
    body = "mutant,DMS_score\nA1B,1.5\nC2D,-0.5\n"
    p = _zip(tmp_path / "s.zip", {"DMS_ProteinGym_substitutions/TEST.csv": body})
    assert load_assay(p, _assay()) == {"A1B": 1.5, "C2D": -0.5}


def test_load_assay_reports_a_missing_member(tmp_path):
    p = _zip(tmp_path / "s.zip", {"DMS_ProteinGym_substitutions/OTHER.csv": "mutant,DMS_score\n"})
    with pytest.raises(ProteinGymError, match="is not in"):
        load_assay(p, _assay())


def test_load_model_scores_reads_a_root_member_and_skips_blanks(tmp_path):
    """Blank or non-numeric scores are a fact about the published scores, not an ingest error."""
    body = "mutant,ESM2_650M\nA1B,-1.0\nC2D,\nE3F,NA\nG4H,2.5\n"
    p = _zip(tmp_path / "z.zip", {"TEST.csv": body})
    assert load_model_scores(p, _assay(), "ESM2_650M") == {"A1B": -1.0, "G4H": 2.5}


def test_load_model_scores_names_the_missing_column(tmp_path):
    p = _zip(tmp_path / "z.zip", {"TEST.csv": "mutant,ESM2_650M\nA1B,1.0\n"})
    with pytest.raises(ProteinGymError, match="no column"):
        load_model_scores(p, _assay(), "NoSuchModel")


# --- the staged release ----------------------------------------------------------------


@needs_data
def test_staged_release_has_the_expected_shape():
    """§B2 names 217 assays with taxon labels; this is the pin agreeing with the design."""
    assays = load_reference(REFERENCE)
    assert len(assays) == 217
    assert by_taxon(assays) == {"Virus": 31, "Prokaryote": 50, "Human": 96, "Eukaryote": 40}


@needs_data
def test_staged_assay_counts_match_the_reference():
    """A per-assay file holding a different number of variants than the reference claims would
    mean the archive and the reference file are from different cuts of the release."""
    assays = load_reference(REFERENCE)
    archive = DATA / "DMS_ProteinGym_substitutions.zip"
    if not archive.exists():
        pytest.skip("substitutions archive not staged")
    for assay in assays[:5]:
        assert len(load_assay(archive, assay)) == assay.n_variants


# --- the pin ---------------------------------------------------------------------------


def test_verify_release_detects_a_changed_file(tmp_path):
    """The negative case, because a check that cannot fail is not a check.

    `verify_release` had no caller at all until a review found it: the staging tool recorded
    fresh hashes and never compared them, while two READMEs claimed a check was happening.
    """
    import dataclasses

    (tmp_path / "a.bin").write_bytes(b"the staged bytes")
    good = "0dc1b7b1b5b1d8b2dcf0c4e3b3b8c1a0f2a7bb1a2f8a1b0f7a1ca2dc5f7bd1ab"
    release = dataclasses.replace(
        RELEASE, files={"a.bin": good}, unversioned={}, reference_file="a.bin"
    )
    assert verify_release(tmp_path, release) == {"a.bin": "CHECKSUM MISMATCH"}


def test_verify_release_reports_missing_and_unpinned(tmp_path):
    import dataclasses

    (tmp_path / "present.bin").write_bytes(b"x")
    release = dataclasses.replace(
        RELEASE,
        files={"present.bin": "", "absent.bin": "deadbeef"},
        unversioned={},
        reference_file="present.bin",
    )
    assert verify_release(tmp_path, release) == {
        "present.bin": "unpinned",
        "absent.bin": "missing",
    }


def test_verify_release_passes_on_the_real_bytes(tmp_path):
    """A file whose recorded hash is its own must verify, or the comparison is inverted."""
    import dataclasses

    from amazebio.proteingym import sha256_file

    path = tmp_path / "a.bin"
    path.write_bytes(b"the staged bytes")
    release = dataclasses.replace(
        RELEASE, files={"a.bin": sha256_file(path)}, unversioned={}, reference_file="a.bin"
    )
    assert verify_release(tmp_path, release) == {"a.bin": "ok"}


@needs_data
def test_every_mapped_model_column_exists_in_the_archive():
    """The bug this catches shipped: the leaderboard writes `Site-Independent` and the score
    archive writes `Site_Independent`, so that model choice raised on every assay."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pg_check", REPO / "tools" / "proteingym_check.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    archive = DATA / "zero_shot_substitutions_scores.zip"
    if not archive.exists():
        pytest.skip("score archive not staged")
    assays = load_reference(REFERENCE)
    for published, column in mod.MODEL_COLUMNS.items():
        scores = load_model_scores(archive, assays[0], column)
        assert scores, f"{published} -> {column} returned nothing"

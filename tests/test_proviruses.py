"""Tests for `amazebio.proviruses` — A2.4's instrument layer.

The parser tests are written around one failure mode in particular: a table read by column
position rather than by column name. D-090 is the worked example of what that costs — A4.2's
headline was inflated by reading geNomad's lineage positionally — and the same mistake in a
provirus table is a coordinate error that no downstream check would catch. So every parser is
tested against a reordered header and an added column, not only against the shape the pinned
version happens to emit today.
"""

from __future__ import annotations

import math
import pathlib

import pytest

from amazebio.proviruses import (
    GENOMAD,
    MIN_RECIPROCAL_OVERLAP,
    VIBRANT,
    ProvirusCall,
    ProvirusError,
    cohens_kappa,
    concordance,
    overlapping_pairs,
    read_genomad_proviruses,
    read_vibrant_proviruses,
    reciprocal_overlap,
)


def call(record="genome1", start=1000, end=2000, tool="genomad", fragment="f", score=None):
    return ProvirusCall(
        source_record=record, fragment=fragment, start=start, end=end, tool=tool, score=score
    )


# --------------------------------------------------------------------------------------
# The pins
# --------------------------------------------------------------------------------------


def test_the_instrument_pin_is_not_a4_2s_object_of_study():
    """D-112: the two geNomad pins exist for opposite purposes and must not converge."""
    from amazebio.genomad import PIN as OBJECT_OF_STUDY

    assert GENOMAD.version != OBJECT_OF_STUDY.version
    assert GENOMAD.database_version != OBJECT_OF_STUDY.database_version


def test_vibrant_s_database_versions_are_read_off_the_package_not_guessed():
    """VIBRANT_setup.py hard-codes all three releases by URL, so this is a pin and not a gap.
    The first draft of this module claimed the opposite — that VIBRANT does not version its
    databases — which would have reported a specification that exists as a missing one."""
    assert VIBRANT.database_version == "KOfam 2019-08-10 + Pfam 32.0 + VOG 94"


# --------------------------------------------------------------------------------------
# ProvirusCall
# --------------------------------------------------------------------------------------


def test_length_is_inclusive_of_both_endpoints():
    assert call(start=1000, end=2000).length == 1001


def test_a_start_below_one_is_a_column_misread_not_a_coordinate():
    with pytest.raises(ProvirusError, match="1-based"):
        call(start=0, end=10)


def test_an_end_before_its_start_is_refused():
    with pytest.raises(ProvirusError, match="before its start"):
        call(start=500, end=400)


# --------------------------------------------------------------------------------------
# Overlap
# --------------------------------------------------------------------------------------


def test_identical_calls_overlap_completely():
    assert reciprocal_overlap(call(), call()) == 1.0


def test_calls_on_different_records_never_overlap():
    """The shared coordinate space is an artefact of both records starting at 1."""
    assert reciprocal_overlap(call(record="a"), call(record="b")) == 0.0


def test_disjoint_calls_do_not_overlap():
    assert reciprocal_overlap(call(start=1, end=100), call(start=200, end=300)) == 0.0


def test_abutting_calls_do_not_overlap():
    assert reciprocal_overlap(call(start=1, end=100), call(start=101, end=200)) == 0.0


def test_a_short_call_nested_in_a_long_one_is_not_agreement():
    """The criterion takes the smaller covered fraction: a fragment cannot confirm an extent."""
    nested = call(start=1000, end=2999)  # 2000 bases
    wide = call(start=1, end=40000)  # 40000 bases
    assert reciprocal_overlap(nested, wide) == pytest.approx(2000 / 40000)
    assert reciprocal_overlap(nested, wide) < MIN_RECIPROCAL_OVERLAP


def test_half_overlapping_calls_sit_exactly_on_the_criterion():
    a = call(start=1, end=1000)
    b = call(start=501, end=1500)
    assert reciprocal_overlap(a, b) == pytest.approx(500 / 1000)


def test_overlapping_pairs_applies_the_threshold_and_sorts_best_first():
    g = [call(fragment="g1", start=1, end=1000), call(fragment="g2", start=5000, end=6000)]
    v = [
        call(fragment="v1", start=1, end=1000, tool="vibrant"),
        call(fragment="v2", start=501, end=1500, tool="vibrant"),
        call(fragment="v3", start=90000, end=91000, tool="vibrant"),
    ]
    pairs = overlapping_pairs(g, v)
    assert [(a.fragment, b.fragment) for a, b, _ in pairs] == [("g1", "v1"), ("g1", "v2")]
    assert pairs[0][2] == 1.0


def test_overlapping_pairs_reports_every_qualifying_pair_not_a_matching():
    """The tools split and merge elements differently; a matching would discard that."""
    g = [call(fragment="merged", start=1, end=10000)]
    v = [
        call(fragment="left", start=1, end=6000, tool="vibrant"),
        call(fragment="right", start=4001, end=10000, tool="vibrant"),
    ]
    assert len(overlapping_pairs(g, v)) == 2


# --------------------------------------------------------------------------------------
# Parsing — geNomad
# --------------------------------------------------------------------------------------

GENOMAD_HEADER = "seq_name\tsource_seq\tstart\tend\tlength\tn_genes\ttopology_score"
GENOMAD_ROW = "genome1|provirus_1000_2000\tgenome1\t1000\t2000\t1001\t12\t3.5"


def test_genomad_parser_reads_a_well_formed_table(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text(f"{GENOMAD_HEADER}\n{GENOMAD_ROW}\n")
    (one,) = read_genomad_proviruses(p)
    assert one.source_record == "genome1"
    assert one.fragment == "genome1|provirus_1000_2000"
    assert (one.start, one.end) == (1000, 2000)
    assert one.tool == "genomad"
    assert one.score == 3.5


def test_genomad_parser_reads_by_name_so_a_reordered_header_is_still_correct(tmp_path):
    """D-090's lesson, enforced: a release that reorders columns must not shift the coordinates."""
    p = tmp_path / "x_provirus.tsv"
    p.write_text("start\tend\tsource_seq\tseq_name\n1000\t2000\tgenome1\tfrag\n")
    (one,) = read_genomad_proviruses(p)
    assert (one.source_record, one.fragment, one.start, one.end) == ("genome1", "frag", 1000, 2000)


def test_genomad_parser_tolerates_an_added_column(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text(f"{GENOMAD_HEADER}\tsomething_new\n{GENOMAD_ROW}\tvalue\n")
    assert len(read_genomad_proviruses(p)) == 1


def test_genomad_parser_refuses_a_table_missing_a_required_column(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text("seq_name\tstart\tend\nfrag\t1\t2\n")
    with pytest.raises(ProvirusError, match="source_seq"):
        read_genomad_proviruses(p)


def test_genomad_parser_refuses_a_short_row(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text(f"{GENOMAD_HEADER}\ngenome1|p\tgenome1\t1000\n")
    with pytest.raises(ProvirusError, match="fields against"):
        read_genomad_proviruses(p)


def test_genomad_parser_refuses_a_non_integer_coordinate(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text("seq_name\tsource_seq\tstart\tend\nfrag\tgenome1\tNA\t2000\n")
    with pytest.raises(ProvirusError, match="not an integer"):
        read_genomad_proviruses(p)


def test_genomad_parser_refuses_an_empty_file(tmp_path):
    p = tmp_path / "x_provirus.tsv"
    p.write_text("")
    with pytest.raises(ProvirusError, match="not even a header"):
        read_genomad_proviruses(p)


def test_a_header_only_table_is_no_calls_rather_than_an_error(tmp_path):
    """A genome with no provirus is the measured result, and the common one."""
    p = tmp_path / "x_provirus.tsv"
    p.write_text(f"{GENOMAD_HEADER}\n")
    assert read_genomad_proviruses(p) == []


# --------------------------------------------------------------------------------------
# Parsing — against the pinned version's real output
# --------------------------------------------------------------------------------------

REAL = pathlib.Path(__file__).parent / "data" / "genomad_1_12_0_ecoli_provirus.tsv"

#: Where E. coli K-12 MG1655's cryptic prophages sit, to the nearest kilobase. The genome is a
#: positive control with a published answer, which is why it is the fixture: a parser tested
#: only against fixtures someone wrote by hand is tested against their assumptions.
KNOWN_PROPHAGE_STARTS_KB = (563, 1196, 1412, 1627, 2463)


def test_the_fixture_is_the_pinned_version_s_own_output():
    """Not a hand-written table. The first draft of this parser guessed a column name that the
    real output does not use, and only real output caught it."""
    assert REAL.read_text().splitlines()[0].split("\t")[:6] == [
        "seq_name",
        "source_seq",
        "start",
        "end",
        "length",
        "n_genes",
    ]


def test_real_output_parses_to_the_known_prophages():
    calls = read_genomad_proviruses(REAL)
    assert [c.start // 1000 for c in calls] == list(KNOWN_PROPHAGE_STARTS_KB)
    assert {c.source_record for c in calls} == {"NC_000913.3"}


def test_real_output_carries_scores_rather_than_a_column_of_none():
    """`v_vs_c_score` is the pinned version's name for it; guessing `virus_score` returned None
    for every call, which a score-free table would have carried silently into A3.2."""
    assert all(c.score is not None and c.score > 0 for c in read_genomad_proviruses(REAL))


def test_real_calls_have_plausible_prophage_lengths():
    assert all(10_000 <= c.length <= 60_000 for c in read_genomad_proviruses(REAL))


def test_real_calls_do_not_overlap_each_other():
    """Distinct elements in one genome; any pairing between them would be a parser artefact."""
    calls = read_genomad_proviruses(REAL)
    for i, a in enumerate(calls):
        for b in calls[i + 1 :]:
            assert reciprocal_overlap(a, b) == 0.0


# --------------------------------------------------------------------------------------
# Parsing — VIBRANT
# --------------------------------------------------------------------------------------

#: VIBRANT 1.2.1's exact header, copied from the line of `VIBRANT_run.py` that writes it
#: rather than from its documentation. Note that the protein columns come *before* the
#: nucleotide ones — the opposite of the order this test file first assumed. Parsing by name
#: is what makes that difference harmless, which is the whole argument for doing so.
VIBRANT_HEADER = (
    "scaffold\tfragment\tprotein start\tprotein stop\tprotein length"
    "\tnucleotide start\tnucleotide stop\tnucleotide length"
)


def test_vibrant_parser_reads_its_spaced_column_names(tmp_path):
    p = tmp_path / "VIBRANT_integrated_prophage_coordinates_x.tsv"
    p.write_text(f"{VIBRANT_HEADER}\ngenome1\tgenome1_fragment_1\t5\t20\t16\t1000\t2000\t1001\n")
    (one,) = read_vibrant_proviruses(p)
    assert one.source_record == "genome1"
    assert (one.start, one.end) == (1000, 2000)
    assert one.tool == "vibrant"


def test_vibrant_calls_carry_no_score_rather_than_a_defaulted_zero(tmp_path):
    """A missing score and a score of zero are different claims."""
    p = tmp_path / "v.tsv"
    p.write_text(f"{VIBRANT_HEADER}\ngenome1\tfrag\t1\t2\t2\t1\t100\t100\n")
    assert read_vibrant_proviruses(p)[0].score is None


def test_vibrant_parser_refuses_a_genomad_table(tmp_path):
    """Naming the columns as each tool writes them is what makes a swapped file visible."""
    p = tmp_path / "wrong.tsv"
    p.write_text(f"{GENOMAD_HEADER}\n{GENOMAD_ROW}\n")
    with pytest.raises(ProvirusError, match="scaffold"):
        read_vibrant_proviruses(p)


# --------------------------------------------------------------------------------------
# Kappa
# --------------------------------------------------------------------------------------


def test_kappa_matches_a_hand_computed_table():
    k = cohens_kappa(both=20, genomad_only=5, vibrant_only=10, neither=15)
    assert k.estimate == pytest.approx(0.4)
    assert k.low == pytest.approx(0.145960, abs=1e-5)
    assert k.high == pytest.approx(0.654040, abs=1e-5)
    assert "cohen_kappa" in k.method


def test_the_interval_never_runs_past_kappas_own_range():
    """The first band returned 0.91 with an upper bound of 1.086.

    The large-sample interval is a normal approximation and does not know the statistic's
    range; a bound above 1 invites a reader to think two tools might agree more than
    perfectly. Agreement worse than chance is real, so the floor is -1 rather than 0.
    """
    k = cohens_kappa(both=6, genomad_only=0, vibrant_only=1, neither=33)
    assert k.estimate == pytest.approx(0.9082568807339448)
    assert k.high <= 1.0
    assert k.low >= -1.0
    assert "clamped" in k.method


def test_perfect_agreement_with_variation_gives_kappa_one():
    k = cohens_kappa(both=25, genomad_only=0, vibrant_only=0, neither=25)
    assert k.estimate == pytest.approx(1.0)


def test_kappa_is_undefined_when_neither_tool_ever_varies():
    """Both tools silent on every record is 0/0, and reporting it as 1.0 would be an assertion."""
    k = cohens_kappa(both=0, genomad_only=0, vibrant_only=0, neither=40)
    assert math.isnan(k.estimate)
    assert "undefined" in k.method


def test_kappa_over_an_empty_subsample_is_refused():
    with pytest.raises(ProvirusError, match="empty concordance subsample"):
        cohens_kappa(0, 0, 0, 0)


def test_kappa_can_be_negative_and_is_not_clamped():
    """Agreement worse than chance is a real finding about two instruments."""
    assert cohens_kappa(both=0, genomad_only=20, vibrant_only=20, neither=0).estimate < 0


# --------------------------------------------------------------------------------------
# Concordance
# --------------------------------------------------------------------------------------


def test_concordance_builds_the_two_by_two_over_the_searched_denominator():
    searched = ["g1", "g2", "g3", "g4"]
    g = [call(record="g1"), call(record="g2")]
    v = [call(record="g1", tool="vibrant"), call(record="g3", tool="vibrant")]
    t = concordance(searched, g, v)
    assert (t.both, t.genomad_only, t.vibrant_only, t.neither) == (1, 1, 1, 1)
    assert t.records == 4


def test_the_neither_cell_comes_from_the_denominator_not_from_the_calls():
    """Two tools agreeing a genome is clean is a real agreement, and kappa needs it counted."""
    t = concordance([f"g{i}" for i in range(100)], [call(record="g0")], [])
    assert t.neither == 99


def test_a_call_outside_the_searched_set_stops_the_run():
    with pytest.raises(ProvirusError, match="different passes"):
        concordance(["g1"], [call(record="g2")], [])


def test_calls_agreeing_on_the_record_but_not_the_extent_are_counted_separately():
    searched = ["g1"]
    g = [call(record="g1", start=1, end=1000)]
    v = [call(record="g1", start=50000, end=51000, tool="vibrant")]
    t = concordance(searched, g, v)
    assert t.both == 1
    assert t.paired_calls == 0
    assert t.unpaired_calls_on_agreed_records == 2


def test_agreed_extent_pairs_and_leaves_nothing_unpaired():
    t = concordance(["g1"], [call(record="g1")], [call(record="g1", tool="vibrant")])
    assert (t.paired_calls, t.unpaired_calls_on_agreed_records) == (1, 0)


def test_the_table_serialises_with_the_criterion_and_the_reading_attached():
    d = concordance(["g1", "g2"], [call(record="g1")], []).to_dict()
    assert d["min_reciprocal_overlap"] == MIN_RECIPROCAL_OVERLAP
    assert "never resolved by preferring a tool" in d["reading"]
    assert set(d) >= {"records", "both", "genomad_only", "vibrant_only", "neither", "kappa"}


def test_the_genomad_database_pin_carries_a_digest():
    """A `None` digest cannot match, and the in-region guard refuses the run rather than
    detecting against an unverified database. That is the right failure, and it fired on a
    real launch because this field had been left unset."""
    assert GENOMAD.database_sha256 and len(GENOMAD.database_sha256) == 64
    assert GENOMAD.database_url.endswith(f"genomad_db_v{GENOMAD.database_version}.tar.gz")

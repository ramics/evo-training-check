"""M3's bin construction — the Stockholm parse, the clustering contract, the refusals.

The clustering tests shell out to the pinned MMseqs2, which is in the environment; they use
sequences short enough that the whole file runs in a couple of seconds.
"""

from __future__ import annotations

import gzip
import shutil

import pytest

from amazebio import diversity
from amazebio.diversity import DiversityError, FamilyBins, SeedFamily

MMSEQS = shutil.which("mmseqs")

STOCKHOLM = """# STOCKHOLM 1.0
#=GF ID   Toy_one
#=GF AC   PF99991.3
#=GF DE   A toy family
A1/1-8            MKTA.YIA
B2/1-8            MKTG-YIA
#=GC seq_cons     MKTaxYIA
//
# STOCKHOLM 1.0
#=GF ID   Toy_two
#=GF AC   PF99992.1
C3/1-4            WWWW
//
"""

INTERLEAVED = """# STOCKHOLM 1.0
#=GF AC   PF99993.1
A1/1-8            MKTA
B2/1-8            MKTG

A1/1-8            YIAC
B2/1-8            YIAC
//
"""


def write(tmp_path, text, name="seed.sto.gz"):  # type: ignore[no-untyped-def]
    path = tmp_path / name
    with gzip.open(path, "wt", encoding="latin-1") as handle:
        handle.write(text)
    return path


class TestTheStockholmParse:
    def test_members_are_ungapped_and_uppercased(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        families = list(diversity.iter_seed_families(write(tmp_path, STOCKHOLM)))
        assert [f.accession for f in families] == ["PF99991", "PF99992"]
        assert families[0].members == ("MKTAYIA", "MKTGYIA")

    def test_the_accession_loses_its_version_suffix(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        families = list(diversity.iter_seed_families(write(tmp_path, STOCKHOLM)))
        assert families[1].accession == "PF99992"

    def test_annotation_rows_are_not_members(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        families = list(diversity.iter_seed_families(write(tmp_path, STOCKHOLM)))
        assert len(families[0].members) == 2  # the #=GC consensus row is not a member

    def test_an_interleaved_alignment_is_joined_not_truncated(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Reading one block as the whole sequence would halve every member, silently."""
        families = list(diversity.iter_seed_families(write(tmp_path, INTERLEAVED)))
        assert families[0].members == ("MKTAYIAC", "MKTGYIAC")

    def test_a_family_with_no_members_is_refused(self) -> None:
        with pytest.raises(DiversityError, match="no members"):
            SeedFamily(accession="PF1", members=())

    def test_a_record_with_no_closing_marker_is_refused(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = write(tmp_path, "# STOCKHOLM 1.0\n#=GF AC   PF9.1\nA/1-2  MK\n")
        with pytest.raises(DiversityError, match="no closing"):
            list(diversity.iter_seed_families(path))


class TestTheFrozenParameters:
    def test_they_are_the_ones_metrics_survival_froze(self) -> None:
        assert diversity.IDENTITY == 0.50
        assert diversity.COVERAGE == 0.80

    def test_the_coverage_mode_is_the_strict_reading(self) -> None:
        """Mode 0 covers both sequences, which is harder than covering the shorter one, so
        bins split more finely and coverage is understated rather than flattered (D-206)."""
        assert diversity.COV_MODE == 0


@pytest.mark.skipif(MMSEQS is None, reason="the pinned MMseqs2 is not on PATH")
class TestClustering:
    def test_a_single_member_needs_no_aligner(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        assert diversity.cluster_members(["MKTAYIAKQR"], workdir=tmp_path) == (0,)

    def test_identical_members_land_in_one_bin(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        seq = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
        assignment = diversity.cluster_members([seq, seq, seq], workdir=tmp_path)
        assert len(set(assignment)) == 1

    def test_unrelated_members_land_in_separate_bins(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        a = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
        b = "WWWWCCCCYYYYHHHHPPPPGGGGNNNNQQQQDDDDEEEEKKKKRRRRSSSSTTTTIIIILLLLVVVVFFFFMMMMAA"
        assignment = diversity.cluster_members([a, b], workdir=tmp_path)
        assert len(set(assignment)) == 2

    def test_bin_indices_come_back_in_input_order(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        a = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
        b = "WWWWCCCCYYYYHHHHPPPPGGGGNNNNQQQQDDDDEEEEKKKKRRRRSSSSTTTTIIIILLLLVVVVFFFFMMMMAA"
        assignment = diversity.cluster_members([a, b, a], workdir=tmp_path)
        assert assignment[0] == assignment[2] != assignment[1]

    def test_clustering_nothing_is_refused(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(DiversityError, match="empty family"):
            diversity.cluster_members([], workdir=tmp_path)

    def test_a_missing_aligner_is_a_refusal_not_a_silent_zero(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((DiversityError, FileNotFoundError)):
            diversity.cluster_members(["MKTA", "MKTG"], workdir=tmp_path, mmseqs="mmseqs-nope")


class TestCoverage:
    def test_coverage_is_bins_hit_over_bins_with_its_interval(self) -> None:
        bins = FamilyBins(accession="PF1", members=4, assignment=(0, 1, 2, 3))
        interval = bins.coverage(2)
        assert bins.bins == 4
        assert interval.estimate == pytest.approx(0.5)
        assert interval.low < 0.2 and interval.high > 0.8  # the seed's narrow denominator

    def test_more_bins_covered_than_exist_is_an_upstream_join_error(self) -> None:
        bins = FamilyBins(accession="PF1", members=2, assignment=(0, 0))
        with pytest.raises(DiversityError, match="upstream join error"):
            bins.coverage(2)

    def test_a_one_bin_family_can_say_almost_nothing(self) -> None:
        bins = FamilyBins(accession="PF1", members=1, assignment=(0,))
        assert bins.bins == 1
        assert bins.widest_interval > 0.7

    def test_the_widest_interval_shrinks_as_bins_grow(self) -> None:
        small = FamilyBins("PF1", 4, tuple(range(4)))
        large = FamilyBins("PF2", 100, tuple(range(100)))
        assert large.widest_interval < small.widest_interval

    def test_a_family_with_detections_and_no_denominator_is_refused(self) -> None:
        bins = {"PF1": FamilyBins("PF1", 2, (0, 1))}
        with pytest.raises(DiversityError, match="disagree"):
            diversity.coverage_of(bins, {"PF1": 1, "PF404": 1})

    def test_coverage_of_returns_one_interval_per_family_with_detections(self) -> None:
        bins = {"PF1": FamilyBins("PF1", 2, (0, 1)), "PF2": FamilyBins("PF2", 2, (0, 0))}
        out = diversity.coverage_of(bins, {"PF1": 1})
        assert set(out) == {"PF1"}
        assert out["PF1"].estimate == pytest.approx(0.5)


@pytest.mark.skipif(MMSEQS is None, reason="the pinned MMseqs2 is not on PATH")
class TestPlacement:
    """The D-239 placement rule: the members' own criterion, every bin a detection meets."""

    A = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
    B = "WWWWCCCCYYYYHHHHPPPPGGGGNNNNQQQQDDDDEEEEKKKKRRRRSSSSTTTTIIIILLLLVVVVFFFFMMMMAA"
    C = "MSDNKLIVRFAPSPTGYLHIGNARTALFNWLYARHHGGEFILRIEDTDRERSTEEAIEAIMDGMKWLGLDWDEGPDVG"

    def test_a_detection_identical_to_a_member_covers_that_members_bin(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        placement = diversity.place_detections(
            [self.A, self.B],
            {"r1|gene0": self.A},
            (0, 1),
            accession="PF1",
            workdir=tmp_path,
        )
        assert placement.bins_hit == (0,)
        assert (placement.placed, placement.unplaced) == (1, 0)

    def test_a_detection_meeting_no_member_is_counted_apart(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        unrelated = (
            "GGGGGGGGGGSSSSSSSSSSAAAAAAAAAAPPPPPPPPPPTTTTTTTTTTGGGGGGGGGGSSSSSSSSSSAAAAAAAAAA"
        )
        placement = diversity.place_detections(
            [self.A],
            {"r1|gene0": unrelated},
            (0,),
            accession="PF1",
            workdir=tmp_path,
        )
        assert placement.bins_hit == ()
        assert (placement.placed, placement.unplaced) == (0, 1)

    def test_detections_in_different_bins_cover_both(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Two members in different bins, each with a detection: the rule counts every bin met
        # rather than one per detection, because M3 asks which parts of the family's diversity
        # are represented (D-239). `C` rather than `B` here: `B` is a synthetic low-complexity
        # run, and MMseqs2 masks low-complexity regions by default, so even a detection
        # identical to it does not align. That masking stays at its default — it can only lose
        # a placement, and a lost placement understates coverage, which is the direction this
        # audit is allowed to err in.
        placement = diversity.place_detections(
            [self.A, self.C],
            {"r1|gene0": self.A, "r2|gene0": self.C},
            (0, 1),
            accession="PF1",
            workdir=tmp_path,
        )
        assert placement.bins_hit == (0, 1)
        assert placement.detections == 2

    def test_members_sharing_a_bin_count_once(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        placement = diversity.place_detections(
            [self.A, self.A],
            {"r1|gene0": self.A},
            (0, 0),
            accession="PF1",
            workdir=tmp_path,
        )
        assert placement.bins_hit == (0,)

    def test_no_detections_is_a_measured_zero_not_a_run(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        placement = diversity.place_detections(
            [self.A], {}, (0,), accession="PF1", workdir=tmp_path
        )
        assert (placement.detections, placement.bins_hit) == (0, ())

    def test_an_assignment_that_does_not_fit_the_members_is_refused(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(DiversityError, match="bin assignments"):
            diversity.place_detections(
                [self.A, self.B],
                {"r1|gene0": self.A},
                (0,),
                accession="PF1",
                workdir=tmp_path,
            )

    def test_the_search_gates_are_open_so_the_frozen_criterion_decides(self) -> None:
        """D-240: the prefilter and the E-value are not in the metric, so neither may remove a
        candidate the frozen 50%/80% criterion would have admitted."""
        assert diversity.SEARCH_SENSITIVITY == 7.5
        assert diversity.SEARCH_EVALUE >= 1000

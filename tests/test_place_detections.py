"""The joins in `tools/place_detections.py` — task A3.4, D-239.

The placement rule itself is `test_diversity.py`'s. What is tested here is the part that can be
wrong without anything failing: which residues belong to which reading, and whether the corpus
summary is a distribution rather than a pooled figure. A reading's detections are selected out of
a FASTA set written by a search shared across all three readings, so a join that quietly keeps
too few records reports a lower coverage — which is indistinguishable from a finding.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "place_detections.py"
_spec = importlib.util.spec_from_file_location("place_detections_under_test", _PATH)
place_detections = importlib.util.module_from_spec(_spec)
sys.modules["place_detections_under_test"] = place_detections
_spec.loader.exec_module(place_detections)


def write_rows(path: pathlib.Path, rows: list[tuple[str, str]]) -> pathlib.Path:
    path.write_text(
        "".join(
            json.dumps({"family_id": family, "record_id": record}) + "\n" for family, record in rows
        )
    )
    return path


class TestReadingTheDetectionRows:
    def test_rows_group_into_record_sets_per_family(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        path = write_rows(
            tmp_path / "detections.jsonl",
            [("PF1", "r1"), ("PF1", "r2"), ("PF2", "r1")],
        )
        assert place_detections.read_detection_records(path) == {
            "PF1": {"r1", "r2"},
            "PF2": {"r1"},
        }

    def test_a_record_hitting_one_family_twice_is_one_record(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Rows are per hit, so a record with two genes in the same family appears twice. The
        record set is what selects residues; the genes are counted from the FASTA."""
        path = write_rows(tmp_path / "detections.jsonl", [("PF1", "r1"), ("PF1", "r1")])
        assert place_detections.read_detection_records(path) == {"PF1": {"r1"}}


class TestSelectingAReadingsResidues:
    def fasta(self, tmp_path: pathlib.Path) -> pathlib.Path:
        directory = tmp_path / "pfam"
        directory.mkdir()
        (directory / "PF1.faa").write_text(">r1|gene0\nMKVL\n>r2|gene0\nMKWW\n>r1|gene4\nMKYY\n")
        return directory

    def test_only_the_readings_own_records_are_kept(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """A record this reading removes is not a detection of this reading, so its residues are
        dropped here rather than placed and counted."""
        out = place_detections.read_hit_proteins(self.fasta(tmp_path), "PF1", {"r1"})
        assert out == {"r1|gene0": "MKVL", "r1|gene4": "MKYY"}

    def test_every_gene_of_a_kept_record_is_a_detection_of_its_own(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        out = place_detections.read_hit_proteins(self.fasta(tmp_path), "PF1", {"r1", "r2"})
        assert len(out) == 3

    def test_a_family_with_no_file_yields_nothing_rather_than_failing(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The caller turns this into a refusal with a count and an instruction; an exception
        per family would say nothing about how much of the set is missing."""
        assert place_detections.read_hit_proteins(self.fasta(tmp_path), "PF404", {"r1"}) == {}


class TestTheCorpusSummary:
    def test_the_summary_is_a_distribution_not_a_pooled_figure(self) -> None:
        out = place_detections._distribution([0.0, 0.25, 0.5, 0.75, 1.0])
        assert out["median"] == 0.5
        assert out["q1"] < out["median"] < out["q3"]
        assert out["families_at_zero"] == 1 and out["families_at_full_coverage"] == 1
        assert "mean" not in out

    def test_one_family_still_reports_a_distribution(self) -> None:
        out = place_detections._distribution([0.4])
        assert out["families"] == 1 and out["median"] == 0.4 == out["q1"] == out["q3"]

    def test_no_families_is_an_empty_distribution_not_a_zero(self) -> None:
        assert place_detections._distribution([]) == {"families": 0}

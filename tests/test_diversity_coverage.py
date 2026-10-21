"""Tests for `tools/diversity_coverage.py` — M3's numerator.

The placement itself is `amazebio.diversity.bins_hit_by`'s and is tested there. What is tested
here is everything around it that could be wrong without looking wrong: a denominator that
carries no assignment, a seed parse that does not reproduce the members the assignment is
positional over, a detection that reached no bin, and the summary's refusal to pool.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "diversity_coverage", _PATH.parent.parent / "tools" / "diversity_coverage.py"
)
assert _spec and _spec.loader
coverage_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage_tool)


class TestReadingRetainedDetections:
    def test_a_family_fasta_reads_back_as_name_and_sequence(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "PF00001.faa"
        path.write_text(">rec1|1\nMKTAYIA\n>rec2|3\nQRSTVWY\n")
        assert coverage_tool.read_detections(path) == (("rec1|1", "MKTAYIA"), ("rec2|3", "QRSTVWY"))

    def test_a_wrapped_sequence_is_joined(self, tmp_path: pathlib.Path) -> None:
        """The retention path writes one line, but a FASTA may be wrapped and half a protein
        placed against the bins would place it wrongly rather than fail."""
        path = tmp_path / "PF00001.faa"
        path.write_text(">rec1|1\nMKTA\nYIA\n")
        assert coverage_tool.read_detections(path) == (("rec1|1", "MKTAYIA"),)

    def test_an_empty_file_is_no_detections(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "PF00001.faa"
        path.write_text("")
        assert coverage_tool.read_detections(path) == ()


class TestTheDenominatorMustCarryItsAssignment:
    def _bins_file(self, tmp_path: pathlib.Path, entries: list[dict[str, object]]) -> pathlib.Path:
        path = tmp_path / "bins.json"
        path.write_text(json.dumps({"per_family": entries}))
        return path

    def test_an_assignment_is_loaded(self, tmp_path: pathlib.Path) -> None:
        path = self._bins_file(
            tmp_path,
            [{"accession": "PF00001", "members": 2, "assignment": [0, 1], "members_digest": "ab"}],
        )
        assert coverage_tool.load_bins(path)["PF00001"]["assignment"] == [0, 1]

    def test_counts_without_an_assignment_are_refused(self, tmp_path: pathlib.Path) -> None:
        """The first artefact published bin counts only; placing against it is not possible."""
        path = self._bins_file(tmp_path, [{"accession": "PF00001", "members": 2, "bins": 2}])
        with pytest.raises(SystemExit, match="no assignment"):
            coverage_tool.load_bins(path)


class TestTheMembersDigestIsChecked:
    def test_it_reproduces_the_builders_digest(self) -> None:
        """Both tools hash the members the same way, or every placement is against the wrong
        family's bins and nothing downstream could tell."""
        bins_spec = importlib.util.spec_from_file_location(
            "diversity_bins", _PATH.parent.parent / "tools" / "diversity_bins.py"
        )
        assert bins_spec and bins_spec.loader
        bins_tool = importlib.util.module_from_spec(bins_spec)
        bins_spec.loader.exec_module(bins_tool)
        members = ("MKTAYIA", "QRSTVWY", "GGSGGSG")
        assert coverage_tool.members_digest(members) == bins_tool.members_digest(members)


class TestTheCorpusSummary:
    def test_the_distribution_is_median_and_iqr(self) -> None:
        d = coverage_tool._distribution([0.1, 0.2, 0.3, 0.4, 0.5])
        assert d["median"] == 0.3
        assert d["q1"] is not None and d["q3"] is not None
        assert d["families"] == 5

    def test_too_few_families_for_an_iqr_says_so_rather_than_inventing_one(self) -> None:
        d = coverage_tool._distribution([0.4, 0.6])
        assert d["median"] == 0.5
        assert d["q1"] is None and d["q3"] is None

    def test_no_families_is_not_a_zero(self) -> None:
        """An absent distribution and a distribution centred on zero are different claims."""
        d = coverage_tool._distribution([])
        assert d["families"] == 0
        assert d["median"] is None

    def test_the_summary_says_it_does_not_pool(self) -> None:
        doc = {
            "label": "evo1-strict-opengenome",
            "families_in_universe": 1719,
            "families_with_a_detection": 2,
            "families_with_no_detection": 1717,
            "families_uninformative": 1,
            "detections_placed": 9,
            "detections_meeting_no_bin": 2,
            "parameters": {"uninformative_interval_width": 0.5},
            "distribution": coverage_tool._distribution([0.25, 0.75]),
            "distribution_informative_only": coverage_tool._distribution([0.75]),
        }
        text = coverage_tool.summarise(doc)
        assert "No pooled coverage figure" in text
        assert "1,717" in text
        assert "met no bin" in text


class TestAProbeMayNotPublish:
    def test_a_whole_run_publishes(self) -> None:
        durable, exempt = coverage_tool.durable_destination(None)
        assert durable and durable.endswith("a3-4")
        assert exempt is None

    def test_a_limited_run_does_not(self) -> None:
        assert coverage_tool.durable_destination(10)[0] is None
        assert coverage_tool.durable_destination(0)[0] is None


class TestOnlyPublishedDetectionsArePlaced:
    """The retention directory holds every protein that hit; the table holds what survived."""

    def test_the_table_reads_back_as_records_per_family(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "d.jsonl"
        path.write_text(
            '{"family_id": "PF00001", "record_id": "rec1"}\n'
            '{"family_id": "PF00001", "record_id": "rec2"}\n'
            '{"family_id": "PF00002", "record_id": "rec1"}\n'
        )
        assert coverage_tool.read_detection_table(path) == {
            "PF00001": {"rec1", "rec2"},
            "PF00002": {"rec1"},
        }

    def test_a_blank_line_is_not_a_record(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "d.jsonl"
        path.write_text('{"family_id": "PF00001", "record_id": "rec1"}\n\n')
        assert coverage_tool.read_detection_table(path) == {"PF00001": {"rec1"}}

    def test_a_protein_whose_record_the_table_omits_is_not_placed(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A reading removes records; a protein from a removed one is not a surviving
        detection, and placing it would raise coverage on evidence the table does not hold."""
        faa = tmp_path / "PF00001.faa"
        faa.write_text(">rec1|1\nMKTAYIAKQR\n>rec9|2\nMKTAYIAKQR\n")
        row = coverage_tool._place(
            ("PF00001", ("MKTAYIAKQR",), (0,), str(faa), frozenset({"rec1"}))
        )
        assert row["detections"] == 1
        assert row["proteins_not_in_the_table"] == 1

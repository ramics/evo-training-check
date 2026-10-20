"""B3.4's covariate builder: what it refuses, and what the artefact must carry.

The depth itself is `tests/test_neff.py`. What is tested here is everything around it — the
pinned inputs it will not proceed without, the published figure it sets its own number beside
without reconciling, and the check CI runs against the committed artefact.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

spec = importlib.util.spec_from_file_location("assay_depth", REPO / "tools" / "assay_depth.py")
assay_depth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assay_depth)

from amazebio import neff  # noqa: E402


def write_alignment(path: Path, rows: list[str]) -> str:
    body = "".join(f">seq{i}\n{row}\n" for i, row in enumerate(rows))
    path.write_bytes(gzip.compress(body.encode()))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def staged(tmp_path: Path) -> dict:
    """A two-assay, one-alignment world, pinned the way the real one is."""
    msa = tmp_path / "msa"
    msa.mkdir()
    path = msa / "TARGET_b01.a2m.gz"
    digest = write_alignment(path, ["ACDEFGHIKL", "ACDEFGHIKL", "ACDEFGHIKM", "MMMMMMMMMM"])
    inputs = {
        "alignment_for_assay": {
            "TARGET_One_2020": "TARGET_b01.a2m",
            "TARGET_Two_2021": "TARGET_b01.a2m",
        },
        "alignments": [
            {
                "name": "TARGET_b01.a2m",
                "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
                "sha256": digest,
            }
        ],
    }
    reference = tmp_path / "reference.csv"
    with reference.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["DMS_id", "MSA_theta", "MSA_N_eff", "MSA_Neff_L"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "DMS_id": "TARGET_One_2020",
                "MSA_theta": "0.2",
                "MSA_N_eff": "3.0",
                "MSA_Neff_L": "0.3",
            }
        )
        writer.writerow(
            {"DMS_id": "TARGET_Two_2021", "MSA_theta": "0.2", "MSA_N_eff": "", "MSA_Neff_L": ""}
        )
    register = {"assays": [{"dms_id": "TARGET_One_2020"}, {"dms_id": "TARGET_Two_2021"}]}
    return {
        "inputs": inputs,
        "reference": reference,
        "register": register,
        "path": path,
        "digest": digest,
    }


class TestThePinnedInputs:
    def test_an_alignment_that_does_not_hash_to_its_pin_is_refused(self, staged, tmp_path):
        write_alignment(staged["path"], ["AAAA", "CCCC"])
        inputs = json.loads(json.dumps(staged["inputs"]))
        inputs["alignments"][0]["path"] = str(staged["path"])
        with pytest.raises(neff.DepthError, match="not the pinned alignment"):
            assay_depth.staged_paths(inputs)

    def test_an_assay_missing_from_the_reference_table_is_refused(self, staged):
        with pytest.raises(neff.DepthError, match="no row for"):
            assay_depth.reference_rows(staged["reference"], {"TARGET_One_2020", "ABSENT_2019"})

    def test_two_assays_on_one_alignment_must_agree_about_its_threshold(self, staged):
        rows = assay_depth.reference_rows(
            staged["reference"], {"TARGET_One_2020", "TARGET_Two_2021"}
        )
        rows["TARGET_Two_2021"]["MSA_theta"] = "0.01"
        with pytest.raises(neff.DepthError, match="cannot have two thresholds"):
            assay_depth.thresholds(rows, staged["inputs"]["alignment_for_assay"])

    def test_the_threshold_is_one_minus_the_published_theta(self, staged):
        rows = assay_depth.reference_rows(
            staged["reference"], {"TARGET_One_2020", "TARGET_Two_2021"}
        )
        got = assay_depth.thresholds(rows, staged["inputs"]["alignment_for_assay"])
        assert got == {"TARGET_b01.a2m": pytest.approx(0.8)}


class TestReadingAnAlignment:
    def test_a_wrapped_row_is_read_as_one_sequence(self, tmp_path):
        path = tmp_path / "wrapped.a2m.gz"
        path.write_bytes(gzip.compress(b">a\nACDE\nFGHI\n>b\nACDE\nFGHM\n"))
        assert assay_depth.read_alignment(path) == ["ACDEFGHI", "ACDEFGHM"]

    def test_insertion_columns_are_gone_by_the_time_depth_sees_the_rows(self, tmp_path):
        path = tmp_path / "inserts.a2m.gz"
        path.write_bytes(gzip.compress(b">a\nACqqDE\n>b\nAC..DE\n"))
        assert assay_depth.read_alignment(path) == ["ACDE", "ACDE"]

    def test_an_alignment_with_no_sequences_is_refused(self, tmp_path):
        path = tmp_path / "empty.a2m.gz"
        path.write_bytes(gzip.compress(b""))
        with pytest.raises(neff.DepthError, match="no sequences"):
            assay_depth.read_alignment(path)


class TestAgainstThePublishedFigure:
    def test_the_ratio_is_reported_without_a_verdict(self):
        got = assay_depth.agreement(220.0, 200.0)
        assert got["ratio"] == pytest.approx(1.1)
        assert got["note"] is None

    def test_a_target_with_no_published_depth_says_so_rather_than_scoring_zero(self):
        got = assay_depth.agreement(220.0, None)
        assert got["ratio"] is None
        assert "no published depth" in got["note"]

    def test_a_blank_cell_reads_as_absent_rather_than_as_a_number(self):
        assert assay_depth.published({"MSA_N_eff": "", "MSA_Neff_L": "   "}) == {
            "neff": None,
            "neff_per_residue": None,
        }


class TestTheTableAndItsSanityBlock:
    def _table(self, staged, tmp_path):
        inputs = json.loads(json.dumps(staged["inputs"]))
        inputs["alignments"][0]["path"] = str(staged["path"])
        reference = assay_depth.reference_rows(
            staged["reference"], {"TARGET_One_2020", "TARGET_Two_2021"}
        )
        return assay_depth.depth_table(
            staged["register"],
            inputs["alignment_for_assay"],
            reference,
            {"TARGET_b01.a2m": staged["path"]},
            seed=1,
        )

    def test_every_assay_on_a_shared_alignment_gets_the_same_depth(self, staged, tmp_path):
        table = self._table(staged, tmp_path)
        depths = {t["dms_id"]: t["depth"] for t in table["targets"]}
        assert len(depths) == 2
        assert len(set(depths.values())) == 1

    def test_both_readings_travel_with_each_alignment(self, staged, tmp_path):
        table = self._table(staged, tmp_path)
        block = table["alignments"]["TARGET_b01.a2m"]
        assert set(block["readings"]) == {"inclusive", "strict"}

    def test_the_sanity_block_counts_what_was_computed_and_how(self, staged, tmp_path):
        s = assay_depth.sanity(self._table(staged, tmp_path))
        assert s["targets"] == 2
        assert s["targets_with_depth"] == 2
        assert s["targets_without_depth"] == []
        assert sum(s["methods"].values()) == 1
        assert s["depth_exceeding_sequence_count"] == []

    def test_a_target_with_no_alignment_is_carried_rather_than_dropped(self, staged, tmp_path):
        register = {"assays": [{"dms_id": "TARGET_One_2020"}, {"dms_id": "NOTHING_2022"}]}
        inputs = staged["inputs"]["alignment_for_assay"]
        reference = assay_depth.reference_rows(staged["reference"], {"TARGET_One_2020"})
        table = assay_depth.depth_table(
            register, inputs, reference, {"TARGET_b01.a2m": staged["path"]}, seed=1
        )
        missing = [t for t in table["targets"] if t["dms_id"] == "NOTHING_2022"]
        assert missing and missing[0]["depth"] is None
        assert "no alignment is distributed" in missing[0]["why"]


class TestWhatTheCheckRefuses:
    def _report(self, staged, tmp_path):
        inputs = json.loads(json.dumps(staged["inputs"]))
        reference = assay_depth.reference_rows(
            staged["reference"], {"TARGET_One_2020", "TARGET_Two_2021"}
        )
        table = assay_depth.depth_table(
            staged["register"],
            inputs["alignment_for_assay"],
            reference,
            {"TARGET_b01.a2m": staged["path"]},
            seed=1,
        )
        return {"table": table, "sanity": assay_depth.sanity(table)}

    def test_a_complete_table_passes(self, staged, tmp_path):
        assert assay_depth.check(self._report(staged, tmp_path)) == []

    def test_an_assay_without_a_depth_fails_because_the_covariate_is_mandatory(
        self, staged, tmp_path
    ):
        report = self._report(staged, tmp_path)
        report["sanity"]["targets_without_depth"] = ["TARGET_Two_2021"]
        problems = assay_depth.check(report)
        assert problems and "mandatory" in problems[0]

    def test_an_estimate_without_an_interval_fails(self, staged, tmp_path):
        report = self._report(staged, tmp_path)
        block = report["table"]["alignments"]["TARGET_b01.a2m"]["readings"]["inclusive"]
        block["method"] = "sampled"
        block["interval"] = None
        assert any("carries no interval" in p for p in assay_depth.check(report))

    def test_depth_above_the_sequence_count_fails(self, staged, tmp_path):
        report = self._report(staged, tmp_path)
        report["sanity"]["depth_exceeding_sequence_count"] = ["TARGET_b01.a2m"]
        assert any("do not sum" in p for p in assay_depth.check(report))

    def test_no_targets_at_all_fails(self, staged, tmp_path):
        report = self._report(staged, tmp_path)
        report["sanity"]["targets"] = 0
        assert "no targets" in assay_depth.check(report)


class TestTheRehearsalGuard:
    def test_the_canonical_directory_publishes(self):
        assert assay_depth.durable_for(assay_depth.CANONICAL_OUT) is not None

    def test_anywhere_else_does_not(self, tmp_path):
        assert assay_depth.durable_for(tmp_path) is None


class TestTheWriteUp:
    def test_the_markdown_names_the_check_as_a_check_rather_than_a_target(self, staged, tmp_path):
        report = self._full(staged, tmp_path)
        text = assay_depth.markdown(report)
        assert "check and not a target" in text
        assert "TARGET_One_2020" in text

    def test_a_problem_is_stated_in_the_write_up_rather_than_only_in_the_json(
        self, staged, tmp_path
    ):
        report = self._full(staged, tmp_path)
        report["problems"] = ["something is wrong"]
        assert "Unusable as it stands" in assay_depth.markdown(report)

    def _full(self, staged, tmp_path):
        reference = assay_depth.reference_rows(
            staged["reference"], {"TARGET_One_2020", "TARGET_Two_2021"}
        )
        table = assay_depth.depth_table(
            staged["register"],
            staged["inputs"]["alignment_for_assay"],
            reference,
            {"TARGET_b01.a2m": staged["path"]},
            seed=1,
        )
        report = {"table": table, "sanity": assay_depth.sanity(table)}
        report["problems"] = assay_depth.check(report)
        return report

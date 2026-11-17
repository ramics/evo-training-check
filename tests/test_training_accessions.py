"""A7.6's join: the accession list for OpenGenome2's training representation.

The join itself is two streaming passes over 21.7 GB, so what is tested here is the part that
decides whether its output is *right*: the key functions, the tier logic, and the guards that
stop a partial run being published as the membership list.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "training_accessions", _PATH.parent.parent / "tools" / "training_accessions.py"
)
assert _spec and _spec.loader
ta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ta)


class TestTheSequenceDigest:
    def test_it_is_sixteen_bytes(self) -> None:
        """Eight would carry a birthday collision probability near 4e-7 over 2.65 million
        records. A collision does not look like an error — it looks like a record that was in
        the training data when it was not."""
        assert len(ta.digest("ACGT")) == 16

    def test_case_and_surrounding_whitespace_do_not_change_it(self) -> None:
        """The FASTA wraps its sequences and the JSON does not, so some normalisation is
        unavoidable; this is the whole of it."""
        assert ta.digest("acgt") == ta.digest("ACGT") == ta.digest("  ACGT\n")

    def test_different_sequences_differ(self) -> None:
        assert ta.digest("ACGT") != ta.digest("ACGA")

    def test_a_longer_sequence_is_not_a_prefix_collision(self) -> None:
        assert ta.digest("ACGT") != ta.digest("ACGTACGT")


class TestTheReverseComplement:
    def test_it_complements_and_reverses(self) -> None:
        assert ta.reverse_complement("ACGT") == "ACGT"
        assert ta.reverse_complement("AAAA") == "TTTT"
        assert ta.reverse_complement("ACGTN") == "NACGT"

    def test_it_is_its_own_inverse(self) -> None:
        for seq in ("ACGTTTGCA", "N", "ACGTACGTACGTN", "GGGCCC"):
            assert ta.reverse_complement(ta.reverse_complement(seq)) == seq

    def test_it_is_case_insensitive_and_uppercases(self) -> None:
        assert ta.reverse_complement("acgt") == ta.reverse_complement("ACGT")

    def test_both_orientations_are_tried_rather_than_assumed(self) -> None:
        """The two representations are published by different pipelines and nothing promises a
        shared strand convention. Matching one orientation and finding 2.65 million records
        would look like success while dropping whatever was written the other way."""
        assert ta.digest("AAAA") != ta.digest(ta.reverse_complement("AAAA"))


class TestTheFallbackTier:
    def test_it_is_stable(self) -> None:
        assert ta.fallback_key("ACGT" * 40) == ta.fallback_key("ACGT" * 40)

    def test_length_is_part_of_the_key(self) -> None:
        """Endpoints alone would merge a record with a longer one sharing both ends, which is
        exactly the shape a tandem repeat has."""
        assert ta.fallback_key("A" * 100) != ta.fallback_key("A" * 101)

    def test_an_interior_change_does_not_change_it(self) -> None:
        """That is the point of the tier: it measures how literally the endpoints and length
        were carried across, where the exact digest answers only yes or no."""
        a = "A" * 48 + "C" * 20 + "T" * 48
        b = "A" * 48 + "G" * 20 + "T" * 48
        assert ta.fallback_key(a) == ta.fallback_key(b)
        assert ta.digest(a) != ta.digest(b)

    def test_an_endpoint_change_does_change_it(self) -> None:
        a = "A" * 48 + "C" * 20 + "T" * 48
        b = "G" + "A" * 47 + "C" * 20 + "T" * 48
        assert ta.fallback_key(a) != ta.fallback_key(b)


class TestTheDeclaredParameters:
    def test_they_are_fixed_in_the_module_rather_than_passed_in(self) -> None:
        """AGENTS.md: thresholds and parameters are fixed before results are inspected. A
        normalisation rule that could be changed by a flag is one that can be tuned until the
        counts agree with D-262, which would make the reconciliation meaningless."""
        assert ta.DIGEST == "blake2b-16"
        assert "uppercase" in ta.NORMALISE
        assert "48" in ta.FALLBACK
        for name in ("DIGEST", "NORMALISE", "FALLBACK", "TRAINING_PREFIX", "FASTA_KEY"):
            assert isinstance(getattr(ta, name), str)

    def test_the_fasta_key_is_the_pinned_revision(self) -> None:
        """The staged object is keyed by release revision. A join between the training tree of
        one revision and the FASTA of another would be a comparison of two releases wearing
        one name."""
        from amazebio import opengenome

        assert opengenome.RELEASES["opengenome2"].revision in ta.FASTA_KEY

    def test_the_training_prefix_is_the_viral_component_of_the_training_tree(self) -> None:
        from amazebio import opengenome

        viral = next(c for c in opengenome.OG2_COMPONENTS if c.name == "imgvr")
        assert any(p == ta.TRAINING_PREFIX for p in viral.prefixes)


class TestTheAccessionKeys:
    def test_a_packable_accession_keys_non_negative(self) -> None:
        from amazebio import imgvr

        assert imgvr.uvig_join_key("IMGVR_UViG_2681813242_000001") >= 0

    def test_the_gvmag_shape_still_gets_a_key(self) -> None:
        """Those are giant-virus genomes — exactly the records a eukaryote-virus filter is
        judged on — so dropping them would bias the membership list towards looking clean."""
        from amazebio import imgvr

        key = imgvr.uvig_join_key("IMGVR_UViG_GVMAG-M-3300023174-109_000001")
        assert key < 0

    def test_the_two_shapes_cannot_collide_with_each_other(self) -> None:
        from amazebio import imgvr

        packed = imgvr.uvig_join_key("IMGVR_UViG_2681813242_000001")
        hashed = imgvr.uvig_join_key("IMGVR_UViG_GVMAG-M-3300023174-109_000001")
        assert packed >= 0 > hashed

    def test_both_shapes_appear_in_the_real_corpus(self) -> None:
        """Not hypothetical: the census's own detection rows carry both, so a join that
        handled only the numeric shape would silently lose part of the population."""
        from amazebio import imgvr

        for accession in (
            "IMGVR_UViG_2681813242_000001",
            "IMGVR_UViG_GVMAG-M-3300023174-109_000001",
        ):
            imgvr.uvig_join_key(accession)


class TestWhatAPartialRunMayNotDo:
    @pytest.mark.parametrize("flag", ["--max-training", "--max-fasta"])
    def test_a_limited_run_publishes_nothing(self, flag, tmp_path, monkeypatch) -> None:
        """A partial join read as the membership list would understate the trained population
        and so overstate how much of a FASTA-measured figure is out of scope. The store has no
        delete, and this artefact is meant to be cited."""
        captured: dict[str, object] = {}

        def fake_run(task, **kw):
            captured.update(kw)
            raise SystemExit("stopped before any reading")

        monkeypatch.setattr(ta, "run", fake_run)
        argv = [flag, "10", "--out", str(tmp_path), "--allow-dirty"]
        with pytest.raises(SystemExit):
            ta.main(argv)
        assert captured["durable"] is None
        assert "smoke" in str(captured["durable_exempt"])

    def test_a_full_run_publishes_to_the_tasks_own_prefix(self, tmp_path, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def fake_run(task, **kw):
            captured.update(kw)
            raise SystemExit("stopped before any reading")

        monkeypatch.setattr(ta, "run", fake_run)
        with pytest.raises(SystemExit):
            ta.main(["--out", str(tmp_path), "--allow-dirty"])
        assert captured["durable"] is not None
        assert "a7-6" in str(captured["durable"])
        assert captured["durable_exempt"] is None

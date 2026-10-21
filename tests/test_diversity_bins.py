"""Tests for `tools/diversity_bins.py` — the half of A3.4 that builds M3's denominator.

The clustering itself is `amazebio.diversity`'s and is tested there. What is tested here is
the handover: the bin assignment is positional over the seed members, so a placement pass
that re-reads the seed has to land on the same list in the same order, and nothing in the
published record would say otherwise if it did not. The digest is what makes that provable,
and it is cheap to get subtly wrong.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "diversity_bins", _PATH.parent.parent / "tools" / "diversity_bins.py"
)
assert _spec and _spec.loader
bins_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bins_tool)

from amazebio import diversity  # noqa: E402


class TestTheMembersDigest:
    def test_the_same_members_in_the_same_order_give_the_same_digest(self) -> None:
        members = ("MKTAYIA", "MKTAYIAK", "GGSGGSG")
        assert bins_tool.members_digest(members) == bins_tool.members_digest(list(members))

    def test_a_different_order_is_a_different_digest(self) -> None:
        """Order is the whole point: entry `i` of the assignment is member `i`."""
        a = bins_tool.members_digest(("MKTAYIA", "GGSGGSG"))
        b = bins_tool.members_digest(("GGSGGSG", "MKTAYIA"))
        assert a != b

    def test_a_dropped_member_is_a_different_digest(self) -> None:
        a = bins_tool.members_digest(("MKTAYIA", "GGSGGSG"))
        b = bins_tool.members_digest(("MKTAYIA",))
        assert a != b

    def test_members_are_separated_so_a_boundary_cannot_move_unnoticed(self) -> None:
        """Concatenating would make ('AB', 'C') and ('A', 'BC') the same family."""
        assert bins_tool.members_digest(("AB", "C")) != bins_tool.members_digest(("A", "BC"))


class TestWhatAFamilyPublishes:
    @pytest.fixture
    def family(self) -> diversity.FamilyBins:
        return diversity.FamilyBins(accession="PF00001", members=4, assignment=(0, 1, 0, 2))

    def test_the_assignment_travels_with_the_counts(self, family: diversity.FamilyBins) -> None:
        entry = bins_tool.family_entry(family, "deadbeef")
        assert entry["assignment"] == [0, 1, 0, 2]
        assert entry["bins"] == 3
        assert entry["members"] == 4
        assert entry["accession"] == "PF00001"

    def test_the_digest_travels_with_the_assignment(self, family: diversity.FamilyBins) -> None:
        assert bins_tool.family_entry(family, "deadbeef")["members_digest"] == "deadbeef"

    def test_the_assignment_is_as_long_as_the_family_has_members(
        self, family: diversity.FamilyBins
    ) -> None:
        entry = bins_tool.family_entry(family, "deadbeef")
        assert len(entry["assignment"]) == entry["members"]

    def test_the_entry_is_json_shaped(self, family: diversity.FamilyBins) -> None:
        """A tuple serialises as a list either way; this pins it so a reader can index it."""
        entry = bins_tool.family_entry(family, "deadbeef")
        assert isinstance(entry["assignment"], list)
        assert all(isinstance(b, int) for b in entry["assignment"])


class TestAProbeMayNotPublish:
    """D-232: where a tool has a subset flag, the subset flag blocks publication.

    The result bucket has no delete, so a partial denominator published under the real
    artefact's name could not be withdrawn afterwards.
    """

    def test_a_whole_run_publishes(self) -> None:
        durable, exempt = bins_tool.durable_destination(None)
        assert durable and durable.endswith("a3-4")
        assert exempt is None

    def test_a_limited_run_does_not(self) -> None:
        durable, exempt = bins_tool.durable_destination(50)
        assert durable is None
        assert exempt and "50" in exempt

    def test_a_limit_of_one_is_still_a_limit(self) -> None:
        """`if args.limit` would let `--limit 0` through; zero families is the emptiest probe."""
        assert bins_tool.durable_destination(1)[0] is None
        assert bins_tool.durable_destination(0)[0] is None

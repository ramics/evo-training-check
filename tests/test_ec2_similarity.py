"""Tests for `tools/ec2_similarity.py` — A1.6's launcher, spot behaviour in particular.

Nothing here launches anything. What is tested is the part of the launcher that decides
what to ask EC2 for and how to read what comes back, because on a machine nobody can log
into those decisions are the whole interface and D-101 already cost this task a finished
corpus pass through one of them.

Three ways spot support can be plausible and wrong:

* **A persistent request.** A reclaim on a persistent spot request re-launches the
  instance, which restarts the pass with nobody watching and bills for it. One-time is the
  only safe shape here.
* **A reclaim read as a failure.** Spot reclaim and a broken run both end with no result
  key in S3. Treating the first as the second means re-examining working code; treating the
  second as the first means re-running a bug. EC2 distinguishes them in
  `StateTransitionReason` and the launcher has to read it.
* **Self-shutdown that stops rather than terminates.** `AGENTS.md` is explicit that
  `InstanceInitiatedShutdownBehavior=terminate` has to be set at launch, because it cannot
  be set afterwards and without it a self-shutdown keeps billing the volume. Going spot
  must not quietly drop it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "ec2_similarity.py"
_spec = importlib.util.spec_from_file_location("ec2_similarity_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["ec2_similarity_under_test"] = tool
_spec.loader.exec_module(tool)


class _Ec2:
    """Enough of the EC2 client to answer the two describe calls the launcher makes."""

    def __init__(self, reason: str = "", state: str = "terminated") -> None:
        self._reason = reason
        self._state = state

    def describe_instances(self, InstanceIds: list[str]) -> dict[str, Any]:
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "State": {"Name": self._state},
                            "StateTransitionReason": self._reason,
                        }
                    ]
                }
            ]
        }


def test_spot_request_is_one_time_and_terminates_on_interruption() -> None:
    opts = tool.market_options(spot=True)["SpotOptions"]
    assert opts["SpotInstanceType"] == "one-time"
    assert opts["InstanceInterruptionBehavior"] == "terminate"


def test_spot_is_requested_as_a_spot_market() -> None:
    assert tool.market_options(spot=True)["MarketType"] == "spot"


def test_no_max_price_is_bid() -> None:
    """A bid below the going rate is a launch that silently never happens.

    Omitting MaxPrice caps at the on-demand price, which is what this task wants: the
    saving comes from spot being cheaper than on demand, not from bidding under it.
    """
    assert "MaxPrice" not in tool.market_options(spot=True)["SpotOptions"]


def test_on_demand_asks_for_nothing() -> None:
    """`None`, not an empty dict: EC2 is told nothing at all about the market."""
    assert tool.market_options(spot=False) is None


def test_reclaim_is_reported_as_interruption_not_failure() -> None:
    ec2 = _Ec2(reason="Server.SpotInstanceTermination")
    assert "Server.SpotInstanceTermination" in tool._transition_reason(ec2, "i-1")


def test_transition_reason_is_empty_when_ec2_does_not_say() -> None:
    assert tool._transition_reason(_Ec2(), "i-1") == ""


def test_transition_reason_survives_an_api_failure() -> None:
    """The reason is diagnostic, so failing to get it must not mask the real outcome."""

    class _Broken:
        def describe_instances(self, InstanceIds: list[str]) -> dict[str, Any]:
            raise RuntimeError("throttled")

    assert tool._transition_reason(_Broken(), "i-1") == ""


def test_state_survives_an_api_failure() -> None:
    class _Broken:
        def describe_instances(self, InstanceIds: list[str]) -> dict[str, Any]:
            raise RuntimeError("throttled")

    assert tool._state(_Broken(), "i-1") == "unknown"

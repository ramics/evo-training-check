"""Tests for `amazebio.ec2` — the launch-time facts every launcher shares.

This module is small and it had no tests, which is the wrong way round: each function in it
encodes a lesson from `AGENTS.md`'s EC2 section that cost a launch or a day to learn, and it
is shared, so a regression here is a regression in every launcher at once. The functions are
also exactly the kind that look obviously correct and fail silently — a spot request that is
subtly the wrong shape still launches, and the bill arrives later.

So what is tested here is not that the code runs. It is the four properties that a plausible
edit would break without failing anything else:

* **One-time, terminate, no maximum price.** Each has a cheaper-looking alternative that is
  wrong: a persistent request re-launches a reclaimed multi-hour pass with nobody watching, a
  `stop` interruption behaviour keeps billing the volume, and a bid under the going rate
  converts a run into a launch that silently never happens.
* **Spot refusals are distinguished.** The service-linked-role refusal needs one IAM action
  from someone else; a capacity refusal needs a retry or another instance type. Collapsing
  them sends the next person down the wrong path, and no dry run finds either.
* **The read-only calls never raise.** Both are read on the way out of a launch, including
  from a `finally`, where an exception would mask the outcome being reported on.

Nothing here talks to EC2.
"""

from __future__ import annotations

from typing import Any

from amazebio import ec2


class _Ec2:
    """Enough of the EC2 client to answer `describe_instances`, or to fail like it."""

    def __init__(self, instance: dict[str, Any] | None = None, *, raises: bool = False) -> None:
        self._instance = instance if instance is not None else {}
        self._raises = raises
        self.calls: list[str] = []

    def describe_instances(self, InstanceIds: list[str]) -> dict[str, Any]:
        self.calls.append(InstanceIds[0])
        if self._raises:
            raise RuntimeError("throttled")
        return {"Reservations": [{"Instances": [self._instance]}]}


def test_region_and_ami_parameter_are_pinned() -> None:
    """The region is the one the corpora are staged in; being in it is the point."""
    assert ec2.REGION == "us-east-1"
    assert ec2.AMI_PARAMETER == (
        "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )


def test_on_demand_asks_for_no_market_options() -> None:
    """`None`, not an empty dict: the parameter is omitted entirely rather than sent empty."""
    assert ec2.market_options(False) is None


def test_spot_request_is_one_time_not_persistent() -> None:
    """A reclaim on a persistent request re-runs a multi-hour pass unwatched, and bills it."""
    opts = ec2.market_options(True)
    assert opts is not None
    assert opts["MarketType"] == "spot"
    assert opts["SpotOptions"]["SpotInstanceType"] == "one-time"


def test_spot_interruption_behaviour_terminates() -> None:
    """`stop` keeps billing the volume — the trap `InstanceInitiatedShutdownBehavior` avoids.

    This flag governs EC2's reclaim; the shutdown-behaviour flag governs the instance's own
    shutdown. Both have to say terminate, and this one is the one that lives here.
    """
    opts = ec2.market_options(True)
    assert opts is not None
    assert opts["SpotOptions"]["InstanceInterruptionBehavior"] == "terminate"


def test_spot_request_sets_no_maximum_price() -> None:
    """Omitting it caps the bid at on demand. A bid under the going rate launches nothing.

    The saving comes from spot being cheaper than on demand, not from bidding below the rate,
    and nobody is watching to notice a request that never becomes an instance.
    """
    opts = ec2.market_options(True)
    assert opts is not None
    assert "MaxPrice" not in opts["SpotOptions"]
    assert "MaxPrice" not in opts


def test_service_linked_role_refusal_is_named_as_such() -> None:
    """It needs one IAM action from someone else, and `iam:*` is denied here."""
    msg = ec2.spot_refusal(
        "An error occurred (ServiceLinkedRoleCreationNotPermitted) when calling RunInstances"
    )
    assert msg is not None
    assert "AWSServiceRoleForEC2Spot" in msg
    assert "nothing launched" in msg


def test_capacity_refusal_is_distinguished_from_the_role_refusal() -> None:
    """Same outcome, opposite response: retry or change type, rather than ask for an IAM action."""
    msg = ec2.spot_refusal("An error occurred (InsufficientInstanceCapacity) when calling ...")
    assert msg is not None
    assert "capacity" in msg
    assert "AWSServiceRoleForEC2Spot" not in msg
    assert "nothing launched and nothing billed" in msg


def test_capacity_refusal_is_recognised_in_either_case() -> None:
    """`InsufficientInstanceCapacity` and prose saying "capacity" both have to land."""
    assert ec2.spot_refusal("InsufficientInstanceCapacity") is not None
    assert ec2.spot_refusal("there is not enough capacity right now") is not None


def test_an_unrelated_error_is_not_claimed_as_a_spot_refusal() -> None:
    """`None` means "this is not one of the two I can explain" — the caller must not be told
    nothing was billed when that has not been established."""
    assert ec2.spot_refusal("UnauthorizedOperation") is None
    assert ec2.spot_refusal("") is None


def test_transition_reason_is_read_rather_than_inferred() -> None:
    """A boot-armed shutdown and a manual termination both say `User initiated` (D-148).

    So the field separates a spot reclaim from a shutdown, and does not separate a shutdown
    from a human. Reading it is the only way to tell the first apart.
    """
    client = _Ec2({"StateTransitionReason": "User initiated (2026-10-16 22:14:01 GMT)"})
    assert ec2.transition_reason(client, "i-abc") == "User initiated (2026-10-16 22:14:01 GMT)"
    assert client.calls == ["i-abc"]


def test_transition_reason_is_empty_when_ec2_does_not_say() -> None:
    assert ec2.transition_reason(_Ec2({}), "i-abc") == ""


def test_transition_reason_never_raises() -> None:
    """Read from a `finally`: an exception here would mask the outcome it reports on."""
    assert ec2.transition_reason(_Ec2(raises=True), "i-abc") == ""


def test_state_of_returns_the_state_name() -> None:
    client = _Ec2({"State": {"Name": "running"}})
    assert ec2.state_of(client, "i-abc") == "running"


def test_state_of_is_unknown_rather_than_raising() -> None:
    """ "unknown" is a reportable answer; an exception on the way out of a launch is not."""
    assert ec2.state_of(_Ec2(raises=True), "i-abc") == "unknown"
    assert ec2.state_of(_Ec2({}), "i-abc") == "unknown"

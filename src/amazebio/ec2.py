"""Launch-time facts about this account's EC2, shared by every launcher in the project.

`AGENTS.md`'s EC2 section is the operating manual; this module is the part of it that is
code. It was lifted out of `tools/ec2_similarity.py` when a second launcher needed the same
answers, because each of these functions encodes a lesson that cost a launch or a day to
learn, and a second copy of such a lesson is a copy that drifts from the first.

Nothing here talks to EC2 except to ask what state an instance is in. The launchers own
their own `UserData`, their own payloads and their own watch loops; what they share is what
to ask for and how to read a refusal.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AMI_PARAMETER",
    "REGION",
    "market_options",
    "spot_refusal",
    "state_of",
    "transition_reason",
]

REGION = "us-east-1"
AMI_PARAMETER = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"


def spot_refusal(text: str) -> str | None:
    """Why a spot launch was refused, in terms the next person can act on. `None` if unclear.

    Both refusals this distinguishes mean nothing launched and nothing was billed, and they
    need opposite responses — which is why they are not one message.

    *The service-linked role.* Measured 2026-10-16, and no dry run finds it: a spot request
    needs `AWSServiceRoleForEC2Spot`, which EC2 creates on the caller's behalf on first use
    via `iam:CreateServiceLinkedRole`. AGENTS.md records that `iam:*` is denied in this
    account, so spot is not a flag that can be turned on from here. It needs one IAM action
    from someone who has that permission. D-132 later verified spot by a real launch, so the
    role now exists; this message stays because the account's permissions are not this
    project's to guarantee and the refusal is unmistakable when it returns.

    *Capacity.* The ordinary spot refusal: the same request may succeed later, or on another
    permitted instance type.
    """
    if "ServiceLinkedRoleCreationNotPermitted" in text:
        return (
            f"spot is unavailable in this account: {text[:160]}\n"
            "  the EC2 Spot service-linked role does not exist and iam:* is denied, so it "
            "cannot be created from here.\n"
            "  nothing launched, nothing billed. Either someone with IAM permissions creates "
            "AWSServiceRoleForEC2Spot once, or the run goes on demand without --spot at "
            "roughly 3-4x the price.\n"
            "  that price difference is not a detail: D-104's $240-450 and D-109's $26 are "
            "spot figures."
        )
    if "Capacity" in text or "capacity" in text:
        return (
            f"spot capacity refused: {text[:200]}\n"
            "  nothing launched and nothing billed. Retry, try another permitted instance "
            "type, or run on demand without --spot at the higher price."
        )
    return None


def market_options(spot: bool) -> dict[str, Any] | None:
    """What to ask EC2 for, market-wise. `None` means say nothing and get on demand.

    Three choices, each of which has a cheaper-looking alternative that is wrong here:

    *One-time, not persistent.* A reclaim on a persistent request re-launches the instance,
    which restarts a multi-hour pass with nobody watching and bills for it. The pass is
    re-run deliberately or not at all.

    *Interruption behaviour terminate, not stop or hibernate.* Stop keeps billing the
    volume, which is the same trap `InstanceInitiatedShutdownBehavior` exists to avoid, and
    it leaves a resource to forget. That flag stays set independently: it governs the
    instance's own shutdown, this one governs EC2's reclaim, and both have to say terminate.

    *No maximum price.* Omitting it caps the bid at the on-demand price. The saving this
    task wants comes from spot being cheaper than on demand, not from bidding under the
    going rate — a bid below it converts a run that would have cost money into a launch that
    silently never happens, and nobody is watching to notice.
    """
    if not spot:
        return None
    return {
        "MarketType": "spot",
        "SpotOptions": {
            "SpotInstanceType": "one-time",
            "InstanceInterruptionBehavior": "terminate",
        },
    }


def transition_reason(ec2: Any, iid: str) -> str:
    """Why EC2 says the instance changed state. Empty when it does not say.

    Worth reading rather than inferring: `AGENTS.md` records that a boot-armed shutdown and a
    manual termination both report `User initiated`, while a spot reclaim reports
    `Service initiated` (D-148). So this field separates a reclaim from a shutdown, and does
    not separate a shutdown from a human.
    """
    try:
        inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
        return str(inst.get("StateTransitionReason", ""))
    except Exception:
        return ""


def state_of(ec2: Any, iid: str) -> str:
    """The instance's state name, or `"unknown"` when the call fails.

    Never raises: this is read on the way out of a launch, including from a `finally`, and a
    transient API failure there must not mask the outcome it is reporting on.
    """
    try:
        return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0][
            "State"
        ]["Name"]
    except Exception:
        return "unknown"

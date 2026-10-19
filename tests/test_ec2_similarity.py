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

import pytest

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


def test_each_measurement_has_its_own_result_key_and_they_match_the_tool() -> None:
    """A mismatch here reads as a run that produced nothing, having paid for everything."""
    path = _PATH.parent / "esm3_calibrate.py"
    spec = importlib.util.spec_from_file_location("esm3_calibrate_for_launcher_test", path)
    calibrate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = calibrate
    spec.loader.exec_module(calibrate)

    assert tool.RESULT_NAMES == calibrate.ARTEFACT_NAMES
    assert set(tool.SAMPLE_RATES) == set(tool.RESULT_NAMES)


def test_the_cap_measurement_asks_for_a_larger_target_than_the_cost_curve() -> None:
    """Opposite trades: the curve needs a small target to complete, the cap a large one to bind."""
    assert tool.SAMPLE_RATES["caps"] < tool.SAMPLE_RATES["curve"]


def test_user_data_passes_the_measurement_and_its_cap_parameters() -> None:
    import string

    fields = {f for _, f, _, _ in string.Formatter().parse(tool.USER_DATA) if f}
    assert {"measure", "cap_query_denominator", "cap_shard_points", "cap_fractions"} <= fields


def test_the_service_linked_role_refusal_is_named_as_such() -> None:
    """Measured 2026-10-16: this account cannot create the EC2 Spot service-linked role, and
    iam:* is denied so neither can we. It is not a capacity problem and the fix is not a
    retry, so the two must not collapse into one message."""
    message = tool.spot_refusal(
        "An error occurred (AuthFailure.ServiceLinkedRoleCreationNotPermitted) when calling "
        "the RunInstances operation: The provided credentials do not have permission to "
        "create the service-linked role for EC2 Spot Instances."
    )
    assert message is not None
    assert "AWSServiceRoleForEC2Spot" in message
    assert "nothing billed" in message
    assert "retry" not in message.lower(), "a retry cannot create an IAM role"


def test_a_spot_count_limit_is_not_mistaken_for_capacity() -> None:
    """Measured 2026-10-19: MaxSpotInstanceCountExceeded with zero spot instances in the account.

    A quota does not clear by retrying, so conflating it with capacity costs a retry loop that
    cannot win — and conflating it with the service-linked role sends somebody to the wrong IAM
    page. It needs its own message, and that message has to name the on-demand fallback, because
    pricing:GetProducts is denied here and the fallback needs an explicit --price-per-hour.
    """
    message = tool.spot_refusal(
        "An error occurred (MaxSpotInstanceCountExceeded) when calling the RunInstances "
        "operation: Max spot instance count exceeded"
    )
    assert message is not None
    assert "quota" in message.lower()
    assert "retrying will not clear it" in message
    assert "price-per-hour" in message
    assert "nothing billed" in message
    assert "AWSServiceRoleForEC2Spot" not in message, "this is not the IAM-role refusal"


def test_a_capacity_refusal_says_to_retry_instead() -> None:
    message = tool.spot_refusal("InsufficientInstanceCapacity: there is no Spot capacity")
    assert message is not None and "Retry" in message


def test_an_unrecognised_launch_failure_is_not_dressed_up_as_a_spot_problem() -> None:
    """Returning None re-raises the original, which is what an unknown failure deserves."""
    assert tool.spot_refusal("UnauthorizedOperation: you are not authorized") is None


class _Args:
    def __init__(self, hard_stop_minutes: int | None) -> None:
        self.hard_stop_minutes = hard_stop_minutes


class _Flags:
    def __init__(self, stage_sample: bool = False, sample_from: str | None = None) -> None:
        self.stage_sample, self.sample_from = stage_sample, sample_from


def test_a_launching_watcher_names_the_timer_it_armed() -> None:
    msg = tool._shutdown_bound(_Args(260))
    assert "260 min" in msg and "armed by this launch" in msg


def test_an_attached_watcher_does_not_invent_a_shutdown_figure() -> None:
    """Measured 2026-10-16: an --attach watcher reported a 400-minute bound on an instance
    launched with 260. Someone reads that line later to decide whether the instance is gone,
    and ec2:ModifyInstanceAttribute is denied so no later process can read the real value."""
    msg = tool._shutdown_bound(_Args(None))
    assert "400" not in msg and "260" not in msg
    assert "cannot read it back" in msg


def test_the_launch_still_arms_a_timer_when_none_is_given() -> None:
    """Dropping the argparse default must not mean launching without a dead man's switch."""
    assert isinstance(tool.DEFAULT_HARD_STOP_MINUTES, int)
    assert tool.DEFAULT_HARD_STOP_MINUTES > 0
    assert "{hard_stop_minutes}" in tool.USER_DATA


def test_staging_flags_reach_the_instance() -> None:
    assert tool._sample_flags(_Flags(stage_sample=True)) == "--stage-sample"
    assert tool._sample_flags(_Flags(sample_from="s3://b/k/manifest.json")) == (
        "--sample-from s3://b/k/manifest.json"
    )
    assert tool._sample_flags(_Flags()) == ""


def test_the_two_staging_flags_cannot_both_reach_the_instance() -> None:
    """One shot at UserData, and no way to ask the instance what it thought it was doing."""
    with pytest.raises(SystemExit, match="Pick one"):
        tool._sample_flags(_Flags(stage_sample=True, sample_from="s3://b/k/manifest.json"))


def test_a_non_s3_sample_uri_is_refused_before_launch() -> None:
    with pytest.raises(SystemExit, match="s3:// uri"):
        tool._sample_flags(_Flags(sample_from="/local/manifest.json"))


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from a shipped tool, transitively."""
    import ast

    src_root = _PATH.parent.parent / "src" / "amazebio"
    seen: set[str] = set()
    queue = [entry]
    while queue:
        path = queue.pop()
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("amazebio"):
                parts = (node.module or "").split(".")
                names = [a.name for a in node.names] if len(parts) == 1 else [parts[1]]
            elif isinstance(node, ast.Import):
                names = [a.name.split(".")[1] for a in node.names if a.name.startswith("amazebio.")]
            for name in names:
                candidate = src_root / f"{name}.py"
                if candidate.exists() and name not in seen:
                    seen.add(name)
                    queue.append(candidate)
    return seen


def test_payload_ships_every_module_the_tool_imports() -> None:
    """Keeping PAYLOAD by hand cost two launches: similarity.py and then shardstore.py were
    imported by the tool and not shipped, so the instance died on an ImportError about half a
    minute in. On the instance a missing import costs an hour and a launch; here it costs a
    second, so the closure is derived rather than trusted."""
    tool_path = _PATH.parent / "esm3_calibrate.py"
    needed = {f"src/amazebio/{m}.py" for m in _first_party_closure(tool_path)}
    shipped = set(tool.PAYLOAD)
    missing = sorted(needed - shipped)
    assert not missing, f"PAYLOAD is short: {missing}"
    assert "src/amazebio/__init__.py" in shipped, "the package itself has to go too"
    assert str(tool_path.relative_to(_PATH.parent.parent)) in shipped


def test_payload_files_all_exist() -> None:
    root = _PATH.parent.parent
    assert [p for p in tool.PAYLOAD if not (root / p).exists()] == []


def test_user_data_cancels_the_pending_timer_before_shutting_down() -> None:
    """`shutdown -h now` does nothing while the boot-armed timer is pending — systemd already
    has one scheduled. That is why a run which failed 31 seconds in sat idle until its
    240-minute timer fired and looked like a four-hour corpus pass."""
    assert "shutdown -c" in tool.USER_DATA
    assert "die()" in tool.USER_DATA
    # Every exit path goes through die(), which cancels first.
    body = tool.USER_DATA.split("die() {{", 1)[1]
    assert "shutdown -h now" not in body.replace(
        "shutdown -h now || systemctl --no-block poweroff || halt -p || true", ""
    ), "a bare immediate shutdown outside die() would silently not fire"


def test_user_data_imports_the_payload_before_the_corpus_pass() -> None:
    """The check that turns a short payload from an hour into two seconds."""
    data = tool.USER_DATA
    assert "PAYLOAD is short" in data
    assert data.index("PRECHECK") < data.rindex("tools/esm3_calibrate.py")


def test_resuming_without_an_artefact_name_is_refused_at_launch() -> None:
    """A resumed run that writes its own source key destroys the cells it is resuming, before
    it reads them, in a bucket with no DeleteObject. Caught at launch so it costs an error
    rather than a boot and a corpus pass."""
    with pytest.raises(SystemExit, match="needs --artefact-name"):
        tool.main(
            [
                "--measure",
                "band",
                "--resume-band-from",
                "s3://b/corpora/results/a1-6/band.json",
                "--dry-run",
            ]
        )

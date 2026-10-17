"""The launcher for A2.4's in-region pass — `tools/ec2_proviruses.py`.

Everything here tests something that, if wrong, is only discovered on a running instance that
cannot be inspected, logged into or corrected. The repository has paid for each of these
lessons once already, in A1.3 and A1.6, and they are listed in `AGENTS.md`:

- a payload short of a module the tool imports kills the instance half a minute in;
- `shutdown -h now` does nothing while the dead-man timer is pending, so a script that fails
  early sits idle for hours looking exactly like a long pass;
- an instance without terminate-on-shutdown becomes a stopped instance that still bills;
- a result that cannot be traced to a commit is not citable.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "ec2_proviruses.py"
_spec = importlib.util.spec_from_file_location("ec2_proviruses_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["ec2_proviruses_under_test"] = tool
_spec.loader.exec_module(tool)

ROOT = _PATH.parent.parent


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from a shipped tool, transitively."""
    src_root = ROOT / "src" / "amazebio"
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


# --------------------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["tools/detect_proviruses.py", "tools/stage_profiles.py"])
def test_payload_ships_every_module_each_shipped_tool_imports(tool_name):
    """Derived rather than trusted. On the instance a missing import costs a launch."""
    needed = {f"src/amazebio/{m}.py" for m in _first_party_closure(ROOT / tool_name)}
    missing = sorted(needed - set(tool.PAYLOAD))
    assert not missing, f"PAYLOAD is short: {missing}"


def test_payload_includes_the_package_itself_and_both_tools():
    assert "src/amazebio/__init__.py" in tool.PAYLOAD
    assert "tools/detect_proviruses.py" in tool.PAYLOAD
    assert "tools/stage_profiles.py" in tool.PAYLOAD


def test_payload_ships_the_lockfile_because_the_lockfile_is_the_pin():
    """The instance builds its environments from pixi.lock, not from a second set of pins."""
    assert "pixi.lock" in tool.PAYLOAD
    assert "pixi.toml" in tool.PAYLOAD


def test_every_payload_file_exists():
    assert [p for p in tool.PAYLOAD if not (ROOT / p).exists()] == []


# --------------------------------------------------------------------------------------
# UserData: the parts that cannot be fixed once it is running
# --------------------------------------------------------------------------------------


def test_the_dead_man_timer_is_armed_before_anything_that_can_fail():
    body = tool.USER_DATA
    assert body.index("shutdown -h +") < body.index("aws s3 cp")


def _die_body() -> str:
    """The `die` function's own text, without the prose above it that quotes the same commands."""
    body = tool.USER_DATA
    start = body.index("die() {{")
    return body[start : body.index("}}", start)]


def test_shutdown_cancels_the_pending_timer_before_going_down():
    """`shutdown -h now` is a no-op while a timer is pending. That cost two launches.

    Scoped to `die`'s own body: the comment above it quotes both commands in the opposite
    order, and the first version of this test matched the prose and failed on correct code.
    """
    die = _die_body()
    assert "shutdown -c" in die
    assert die.index("shutdown -c") < die.index("shutdown -h now")


def test_shutdown_has_fallbacks_because_it_is_the_path_that_must_not_fail():
    die = _die_body()
    assert "systemctl --no-block poweroff" in die
    assert "halt -p" in die


def test_the_genomad_database_is_checksummed_and_a_mismatch_is_fatal():
    """Detecting with a different database than the one recorded is untraceable."""
    body = tool.USER_DATA
    assert "sha256sum -c -" in body
    assert "refusing to detect with a different database" in body


def test_the_vibrant_database_failure_is_not_fatal():
    """D-114: the expensive pass must not be lost to the cheap second instrument."""
    body = tool.USER_DATA
    assert "continuing without the concordance arm" in body
    marker = body.index("download-db.sh")
    assert "die" not in body[marker : marker + 200]


def test_the_commit_is_passed_in_explicitly():
    assert "--code-commit {commit}" in tool.USER_DATA


def test_results_are_uploaded_because_object_storage_is_the_only_channel_back():
    assert "--upload-results" in tool.USER_DATA


def test_user_data_fits_the_sixteen_kilobyte_limit():
    rendered = tool.USER_DATA.format(
        bucket="b",
        region="us-east-1",
        code_key="k",
        results_prefix="p",
        rate=0.025,
        commit="c" * 40,
        extra_flags="--release opengenome2",
        hard_stop_minutes=600,
        genomad_db_url="u",
        genomad_db_sha256="s" * 64,
        pixi_url="u",
        pixi_sha256="p" * 64,
    )
    assert len(rendered.encode()) < 16 * 1024


# --------------------------------------------------------------------------------------
# Launch parameters
# --------------------------------------------------------------------------------------


def test_pixi_is_a_pinned_checksummed_binary_not_a_piped_installer():
    """The installer script failed on the first launch and the redirect silencing it hid why.

    It writes to shell profiles and depends on $HOME, which cloud-init does not reliably set.
    A pinned tarball with a digest is one moving part instead of three.
    """
    code = [line for line in tool.USER_DATA.splitlines() if not line.strip().startswith("#")]
    assert not [line for line in code if "install.sh | bash" in line]
    assert "{pixi_sha256}  pixi.tar.gz" in tool.USER_DATA
    assert len(tool.PIXI_SHA256) == 64


def test_no_step_that_can_fail_is_silenced():
    """`>/dev/null 2>&1` on a failing step is how the first launch lost its own error."""
    for line in tool.USER_DATA.splitlines():
        if "die " in line or line.strip().startswith("#"):
            continue
        assert ">/dev/null 2>&1" not in line or "|| true" in line, line


def test_spot_is_one_time_and_terminates_on_interruption():
    market = tool.market_options(True)
    assert market["SpotOptions"]["SpotInstanceType"] == "one-time"
    assert market["SpotOptions"]["InstanceInterruptionBehavior"] == "terminate"


def test_on_demand_says_nothing_about_the_market():
    assert tool.market_options(False) is None


def test_the_volume_stays_under_the_policy_cap():
    assert tool.DEFAULT_VOLUME_GB <= 200


def test_the_instance_type_is_within_the_allowed_ceiling():
    assert tool.DEFAULT_INSTANCE_TYPE.endswith("2xlarge")


def test_the_service_linked_role_refusal_is_explained_rather_than_raw():
    message = tool.spot_refusal("AuthFailure.ServiceLinkedRoleCreationNotPermitted ...")
    assert message and "no dry run detects" in message


def test_a_capacity_refusal_is_distinguished_from_a_permission_one():
    message = tool.spot_refusal("InsufficientInstanceCapacity")
    assert message and "nothing was billed" in message


def test_an_unrecognised_refusal_is_not_explained_away():
    assert tool.spot_refusal("something else entirely") is None


def test_a_watcher_that_dies_does_not_kill_a_healthy_instance():
    """A `| head -4` on the launcher's output was enough to do exactly that.

    head closed the pipe, the print raised BrokenPipeError, and the finally terminated an
    instance thirty seconds after launch that had not yet booted far enough to emit a console
    byte. The guard is now "did this process see the run end", not "did it time out", because
    a dead watcher is not a finished run.
    """
    source = _PATH.read_text()
    assert "observed_end" in source
    assert 'if not observed_end and state in ("running", "pending"):' in source


def test_the_terminate_guard_mentions_the_dead_man_timer():
    """Leaving an instance alone is only safe because UserData armed a timer before anything."""
    source = _PATH.read_text()
    guard = source.index("if not observed_end")
    assert "shutdown timer" in source[guard : guard + 800]

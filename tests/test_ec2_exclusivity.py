"""Tests for `tools/ec2_exclusivity.py` — the in-region launcher for A1.6's D-158 pass.

An instance here cannot be inspected once running: no shell, no SSM, no inbound connection,
and a dry run authorizes without executing any `UserData`. So every check that can be made
before launch has to be made before launch, and these are the ones that cost a launch when
they were skipped elsewhere in this task:

* **A payload short of a module the tool imports.** Twice a module was added to a tool's
  imports and not to its ship list, and the instance died on an `ImportError` about half a
  minute in, having read nothing. The closure is derived from the source, not trusted.
* **Result keys that drift from the tool that writes them.** The launcher waits on the keys
  it believes the instance will publish. If the tool's own upload template changes, the
  launcher waits for objects nobody writes and reports a healthy run as a failure.
* **A shutdown path that cannot run.** `shutdown -h now` does nothing while a boot-armed
  timer is pending, so every exit has to cancel the schedule first (D-127).
* **`UserData` over the 16 KiB cap**, which is refused at launch.
* **Tags omitted**, whose refusal is a bare `UnauthorizedOperation` that reads exactly like
  having no permission at all.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve()
_TOOL_PATH = _PATH.parent.parent / "tools" / "ec2_exclusivity.py"
_spec = importlib.util.spec_from_file_location("ec2_exclusivity", _TOOL_PATH)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from a shipped tool, transitively."""
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
    shipped = set(tool.PAYLOAD)
    needed = {
        f"src/amazebio/{m}.py"
        for m in _first_party_closure(_PATH.parent.parent / "tools" / "seed_exclusivity.py")
    }
    assert not sorted(needed - shipped), f"PAYLOAD is short: {sorted(needed - shipped)}"
    assert "src/amazebio/__init__.py" in shipped, "the package itself has to go too"
    assert "tools/seed_exclusivity.py" in shipped


def test_payload_files_all_exist() -> None:
    root = _PATH.parent.parent
    missing = [rel for rel in tool.PAYLOAD if not (root / rel).exists()]
    assert not missing, f"PAYLOAD names files that are not there: {missing}"


def test_result_keys_match_the_keys_the_tool_actually_writes() -> None:
    """The launcher waits on these, so a drift between the two templates stalls a good run."""
    keys = tool.result_keys("corpora", "2023_02", "abc123")
    assert set(keys) == set(tool.TIERS)
    for tier, key in keys.items():
        # Mirrors tools/seed_exclusivity.py's upload key, which is built as
        # results/a1-6/exclusivity/<release>/<tier>/<role>-<commit>.json
        assert key == f"corpora/results/a1-6/exclusivity/2023_02/{tier}/counts-abc123.json"


def test_the_commit_is_in_every_result_key() -> None:
    """The corpus bucket has no DeleteObject, so an overwrite destroys the earlier object
    irreversibly. Keying by commit is what makes a second run additive (D-126)."""
    first = tool.result_keys("corpora", "2023_02", "aaa")
    second = tool.result_keys("corpora", "2023_02", "bbb")
    assert set(first.values()).isdisjoint(second.values())


def _user_data(**over: object) -> str:
    base: dict[str, object] = dict(
        bucket="b",
        prefix="corpora",
        code_key="corpora/code/x.tar.gz",
        region="us-east-1",
        release="2023_02",
        tiers=" ".join(tool.TIERS),
        workers=7,
        commit="abc123",
        hard_stop_minutes=150,
        taxdump_url="https://example.invalid/taxdmp.zip",
        taxdump_sha256="0" * 64,
    )
    base.update(over)
    return tool.USER_DATA.format(**base)


def test_user_data_arms_the_timer_before_anything_that_can_fail() -> None:
    body = _user_data()
    armed = body.index("shutdown -h +150")
    assert armed < body.index("dnf install"), "the switch must be armed before the first risk"
    assert armed < body.index("aws s3 cp")


def test_every_exit_cancels_the_pending_timer_first() -> None:
    """`shutdown -h now` is a no-op while a timer is scheduled, so the cancel is the fix.

    Asserted inside `die`'s own body rather than over the whole script: the comment above
    `die` names `shutdown -h now` while explaining the trap, and a search over the file
    would match the prose and pass whatever the code did.
    """
    body = _user_data()
    die = body[body.index("die() {") : body.index("dnf install")]
    assert "shutdown -c" in die
    assert die.index("shutdown -c") < die.index("shutdown -h now")
    assert "systemctl --no-block poweroff" in die
    assert "halt -p" in die
    # Both the failure paths and the success path go through it, or one exit leaks.
    assert 'die "no python 3.11+ available; nothing to run"' in body
    assert 'die "taxdump checksum mismatch"' in body
    assert 'die "run complete" "$rc"' in body


def test_the_payload_is_imported_before_the_long_read() -> None:
    """Python collapses the `\\`-continued lines of USER_DATA, so the invocation is one
    long line by the time bash sees it — which is why this matches the bare tool name."""
    body = _user_data()
    assert body.index("PRECHECK") < body.index('( "$PYBIN" tools/seed_exclusivity.py')


def test_both_tiers_run_and_the_larger_one_goes_first() -> None:
    assert tool.TIERS == ("uniref90", "uniref50")
    body = _user_data()
    assert "for tier in uniref90 uniref50" in body


def test_user_data_passes_the_run_its_provenance_and_its_heartbeat() -> None:
    body = _user_data()
    assert "--code-commit abc123" in body
    assert "--heartbeat-seconds" in body
    assert "--upload-results" in body


def test_user_data_is_under_the_sixteen_kilobyte_cap() -> None:
    assert len(_user_data().encode()) < 16 * 1024


def test_the_interpreter_is_picked_by_name_not_trusted() -> None:
    """Amazon Linux 2023's `python3` is 3.9 and this project needs 3.12."""
    body = _user_data()
    assert "python3.12" in body
    assert 'if [ -z "$PYBIN" ]' in body

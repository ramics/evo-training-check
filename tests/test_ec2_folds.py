"""Tests for A2.2's GPU throughput launcher.

The one that matters is `test_payload_covers_the_import_closure`. AGENTS.md records two
launches lost on 2026-10-16 and 2026-10-17 to a `PAYLOAD` list that was one module short: the
instance died on an ImportError about half a minute in, having read nothing. The list is kept
by hand and the closure is derived from the source, so this test is the thing that notices
when the two drift. On the instance that costs an hour and a launch; here it costs a second.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def folds():
    return _load("ec2_folds", "tools/ec2_folds.py")


def _first_party_imports(path: Path) -> set[str]:
    """The `amazebio.*` submodules a source file imports, by name."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "amazebio":
                found.update(alias.name for alias in node.names)
            elif node.module.startswith("amazebio."):
                found.add(node.module.split(".", 1)[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("amazebio."):
                    found.add(alias.name.split(".", 1)[1])
    return found


def _closure(entry: Path) -> set[str]:
    seen: set[str] = set()
    todo = _first_party_imports(entry)
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        path = ROOT / "src" / "amazebio" / f"{module}.py"
        if path.exists():
            todo |= _first_party_imports(path)
    return seen


def test_payload_covers_the_import_closure(folds):
    needed = _closure(ROOT / "tools" / "fold_throughput.py")
    shipped = {
        Path(rel).stem
        for rel in folds.PAYLOAD
        if rel.startswith("src/amazebio/") and not rel.endswith("__init__.py")
    }
    missing = needed - shipped
    assert not missing, (
        f"PAYLOAD is short by {sorted(missing)} — the instance would die on an ImportError "
        "about half a minute in, having read nothing"
    )


def test_payload_files_all_exist(folds):
    for rel in folds.PAYLOAD:
        assert (ROOT / rel).exists(), f"{rel} is in PAYLOAD but not in the tree"


def test_payload_ships_the_lockfile_and_the_tool(folds):
    # pixi rebuilds the environment on the instance from the committed lockfile, so a payload
    # without it would solve freshly and could run a different foldseek than the pinned one.
    for required in ("pixi.toml", "pixi.lock", "tools/fold_throughput.py"):
        assert required in folds.PAYLOAD


def test_only_authorized_gpu_types_are_offered(folds):
    # Both 2xlarges return a bare UnauthorizedOperation (D-163), which reads like having no
    # permission at all, so they must not be reachable through this tool's interface.
    assert folds.ALLOWED_TYPES == ("g5.xlarge", "g6.xlarge")
    for refused in ("g5.2xlarge", "g6.2xlarge", "c6i.2xlarge"):
        assert refused not in folds.ALLOWED_TYPES


def test_ami_is_the_driver_bearing_one(folds):
    # The base AL2023 AMI the other ec2 tools use has no NVIDIA driver, and foldseek would
    # then fall back to the CPU and return a plausible fiction.
    assert "deeplearning" in folds.AMI_PARAMETER
    assert "nvidia-driver" in folds.AMI_PARAMETER


def test_user_data_renders_within_the_limit_and_shuts_down_safely(folds):
    text = folds.render_user_data(
        bucket="b",
        prefix="p",
        code_key="p/code.tar.gz",
        region="us-east-1",
        commit="deadbeef",
        devices="cpu,gpu",
        ladder="100,500",
        cpu_ladder="100",
        threads=4,
        hard_stop_minutes=180,
        pixi_url=folds.PIXI_URL,
        pixi_sha256=folds.PIXI_SHA256,
    )
    assert len(text.encode()) <= 16 * 1024
    # Comments in this script quote the very commands they warn about, so ordering is checked
    # over the commands alone — matching prose would pass while the script was wrong.
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    # The timer is armed before anything that can fail...
    assert "shutdown -h +180" in code
    assert code.index("shutdown -h +180") < code.index("nvidia-smi")
    # ...and `shutdown -c` precedes the immediate shutdown, because the immediate one does
    # nothing while the timer is pending. That trap cost two launches and most of a day.
    assert code.index("shutdown -c") < code.index("shutdown -h now")
    # Every failure path goes through `die`, so none of them idles away the window.
    assert code.count("|| die ") >= 5
    assert "nvidia-smi || die" in code
    # The payload import check runs before the weights download and the measurement.
    assert code.index("payload imports cleanly") < code.index("databases ProstT5")


def test_user_data_refuses_to_render_when_too_large(folds):
    with pytest.raises(SystemExit):
        folds.render_user_data(
            bucket="b" * 20000,
            prefix="p",
            code_key="k",
            region="us-east-1",
            commit="c",
            devices="cpu",
            ladder="1",
            cpu_ladder="1",
            threads=1,
            hard_stop_minutes=1,
            pixi_url="u",
            pixi_sha256="s",
        )


def test_results_go_to_a_task_scoped_prefix(folds):
    # The corpus bucket has no DeleteObject, so anything written there is permanent.
    assert folds.RESULT_PREFIX == "corpora/results/a2-2"

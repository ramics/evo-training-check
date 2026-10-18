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
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `@dataclass` resolves its own module through
    # `sys.modules[cls.__module__]`, so a module loaded this way without being registered
    # raises `AttributeError: 'NoneType' object has no attribute '__dict__'` the moment the
    # file defines a dataclass. That is exactly what killed one A2.2 launch — the instance's
    # payload precheck used this pattern and reported a complete payload as short.
    sys.modules[name] = module
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
    assert code.index("imports cleanly") < code.index("databases ProstT5")


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


def test_pixi_pin_agrees_with_the_other_launcher(folds):
    """The pin is shared, so it must not be re-derived by eye.

    This tool's first launch died on a checksum mismatch: the URL had been copied by hand and
    lost both the version — 0.82.0, misread off an f-string as 0.42.1 — and the `.tar.gz`
    suffix, so it fetched a real but different release asset. The pin caught it, which is the
    point of a pin, but the test is what stops it recurring.
    """
    proviruses = _load("ec2_proviruses", "tools/ec2_proviruses.py")
    assert folds.PIXI_VERSION == proviruses.PIXI_VERSION
    assert folds.PIXI_URL == proviruses.PIXI_URL
    assert folds.PIXI_SHA256 == proviruses.PIXI_SHA256
    # The asset is an archive, so the script has to unpack it rather than chmod it.
    assert folds.PIXI_URL.endswith(".tar.gz")


def test_user_data_unpacks_pixi_rather_than_chmodding_the_download(folds):
    text = folds.render_user_data(
        bucket="b",
        prefix="p",
        code_key="p/code.tar.gz",
        region="us-east-1",
        commit="deadbeef",
        devices="cpu,gpu",
        ladder="100",
        cpu_ladder="100",
        threads=4,
        hard_stop_minutes=10,
        pixi_url=folds.PIXI_URL,
        pixi_sha256=folds.PIXI_SHA256,
    )
    # Checksum before unpacking, and unpacking at all: the asset is a tarball containing a
    # single `pixi` binary, so writing the download straight to /usr/local/bin cannot work.
    assert text.index("sha256sum -c -") < text.index("tar xzf pixi.tar.gz")
    assert "install -m 0755 pixi /usr/local/bin/pixi" in text


def test_precheck_imports_through_the_normal_machinery(folds):
    """The payload guard must not be able to fail on a complete payload.

    One launch died here. The precheck used `spec_from_file_location` plus
    `module_from_spec` without registering the module in `sys.modules`, so the first
    `@dataclass` in the shipped tool raised `AttributeError` on
    `sys.modules.get(cls.__module__).__dict__` — and the guard reported a short PAYLOAD when
    the payload was complete. A false positive here costs a launch, exactly like the true
    positive it exists to catch.
    """
    text = folds.render_user_data(
        bucket="b",
        prefix="p",
        code_key="p/code.tar.gz",
        region="us-east-1",
        commit="deadbeef",
        devices="cpu,gpu",
        ladder="100",
        cpu_ladder="100",
        threads=4,
        hard_stop_minutes=10,
        pixi_url=folds.PIXI_URL,
        pixi_sha256=folds.PIXI_SHA256,
    )
    # Commands only: the comments above this guard quote the broken pattern by name in
    # order to explain it, and matching prose would fail on the explanation.
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "spec_from_file_location" not in code
    assert "module_from_spec" not in code
    # Every shipped first-party module, by name, and then the tool started the way the run
    # starts it — so the check exercises the import path the measurement will use.
    assert "importlib.import_module" in code
    assert "fold_throughput.py --help" in code


def test_results_go_to_a_task_scoped_prefix(folds):
    # The corpus bucket has no DeleteObject, so anything written there is permanent.
    assert folds.RESULT_PREFIX == "corpora/results/a2-2"


def test_budget_window_is_what_the_ceiling_buys(folds):
    # 30 USD at 0.50/h is 60 hours; at 1.50/h it is 20.
    assert folds.budget_window_minutes(30.0, 0.50) == 3600
    assert folds.budget_window_minutes(30.0, 1.50) == 1200
    with pytest.raises(SystemExit):
        folds.budget_window_minutes(30.0, 0.0)


def test_the_ceiling_is_the_owners_figure(folds):
    # Set by the project owner on 2026-10-18 after seeing D-164's cost figures. It lives in
    # code because the shutdown timer baked in at launch is the only spend control that
    # survives the launch: ec2:ModifyInstanceAttribute is denied.
    assert folds.DEFAULT_MAX_SPEND_USD == 30.0
    assert folds.MIN_USEFUL_WINDOW_MINUTES >= 20


def test_spot_is_one_time_and_terminates_on_interruption(folds):
    assert folds.market_options(False) is None
    opts = folds.market_options(True)
    # Persistent would relaunch a long pass unwatched; stop-on-interruption keeps billing
    # the volume, which is exactly what terminate-on-shutdown exists to prevent.
    assert opts["SpotOptions"]["SpotInstanceType"] == "one-time"
    assert opts["SpotOptions"]["InstanceInterruptionBehavior"] == "terminate"


def test_spot_price_takes_the_worst_recent_quote(folds):
    class FakeEc2:
        def describe_spot_price_history(self, **kw):
            return {
                "SpotPriceHistory": [
                    {"SpotPrice": "0.5031", "AvailabilityZone": "us-east-1a"},
                    {"SpotPrice": "0.7595", "AvailabilityZone": "us-east-1d"},
                ]
            }

    price, source = folds.spot_price_now(FakeEc2(), "g6.xlarge")
    # The launch does not pin an availability zone, so budgeting from the cheapest quote
    # would under-reserve precisely when the expensive zone is the one it lands in.
    assert price == 0.7595
    assert "us-east-1d" in source


def test_spot_price_failure_is_not_a_silent_zero(folds):
    class Broken:
        def describe_spot_price_history(self, **kw):
            raise RuntimeError("no")

    assert folds.spot_price_now(Broken(), "g6.xlarge") is None

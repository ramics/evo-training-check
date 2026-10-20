"""Tests for `tools/ec2_opengenome_contigs.py` — A7.4's in-region contig pass.

An instance here cannot be inspected once running: no shell, no SSM, no inbound connection,
and a dry run authorizes without executing any `UserData`. So every check that can be made
before launch is made here, and these are the ones that cost a launch when they were
skipped elsewhere in this project:

* **A payload short of a module the tool imports**, which dies on an `ImportError` about
  half a minute in, having read nothing. The closure is derived from the source.
* **Result keys that drift from what the worker writes**, which makes the launcher wait for
  objects nobody publishes and report a healthy run as a failure.
* **A shutdown path that cannot run**: `shutdown -h now` is a no-op while a boot-armed
  timer is pending, so every exit cancels the schedule first (D-127).
* **`UserData` over the 16 KiB cap**, and **tags omitted**, whose refusal is a bare
  `UnauthorizedOperation` that reads exactly like having no permission at all.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve()
_ROOT = _PATH.parent.parent


def _load(name: str, rel: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load("ec2_opengenome_contigs", "tools/ec2_opengenome_contigs.py")
worker = _load("opengenome_contigs", "tools/opengenome_contigs.py")


def _first_party_closure(entry: pathlib.Path) -> set[str]:
    """Every `amazebio.*` module reachable from a shipped tool, transitively."""
    src_root = _ROOT / "src" / "amazebio"
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


def test_payload_ships_every_module_the_worker_imports() -> None:
    shipped = set(tool.PAYLOAD)
    needed = {
        f"src/amazebio/{m}.py"
        for m in _first_party_closure(_ROOT / "tools" / "opengenome_contigs.py")
    }
    assert not sorted(needed - shipped), f"PAYLOAD is short: {sorted(needed - shipped)}"
    assert "src/amazebio/__init__.py" in shipped, "the package itself has to go too"
    assert "tools/opengenome_contigs.py" in shipped


def test_payload_files_all_exist() -> None:
    missing = [rel for rel in tool.PAYLOAD if not (_ROOT / rel).exists()]
    assert not missing, f"PAYLOAD names files that are not there: {missing}"


def test_the_launcher_and_the_worker_agree_on_the_archives_and_their_slugs() -> None:
    """The launcher waits on keys built from these; a drift stalls a finished run."""
    assert set(tool.ARCHIVES) == set(worker.ARCHIVES)
    for archive in tool.ARCHIVES:
        assert tool.slug(archive) == worker.slug(archive)


def test_result_keys_match_what_the_worker_publishes() -> None:
    """The worker's outdir file is `contigs-<slug>-<commit>.json` and `repro.run`'s durable
    upload keys it by its name under `results/a7-4/`."""
    keys = tool.result_keys("corpora", "abc123")
    assert keys["v214/batch1.tar"] == "corpora/results/a7-4/contigs-v214-batch1-abc123.json"
    assert keys["v220_update.tar"] == "corpora/results/a7-4/contigs-v220_update-abc123.json"
    assert set(keys) == set(tool.ARCHIVES)


def test_the_commit_is_in_every_result_key() -> None:
    """The corpus bucket has no DeleteObject, so an overwrite destroys the earlier object
    irreversibly. Keying by commit is what makes a second run additive (D-126)."""
    first = tool.result_keys("corpora", "aaa")
    second = tool.result_keys("corpora", "bbb")
    assert set(first.values()).isdisjoint(second.values())


def test_only_narrows_the_keys_the_launcher_waits_on() -> None:
    keys = tool.result_keys("corpora", "abc", ("v220_update.tar",))
    assert list(keys) == ["v220_update.tar"]


def _user_data(**over: object) -> str:
    base: dict[str, object] = dict(
        bucket="b",
        prefix="corpora",
        code_key="corpora/code/x.tar.gz",
        region="us-east-1",
        archives=" ".join(tool.ARCHIVES),
        commit="abc123",
        heartbeat=120.0,
        hard_stop_minutes=150,
    )
    base.update(over)
    return tool.USER_DATA.format(**base)


def test_user_data_arms_the_timer_before_anything_that_can_fail() -> None:
    body = _user_data()
    armed = body.index("shutdown -h +150")
    assert armed < body.index("dnf install"), "the switch must be armed before the first risk"
    assert armed < body.index("aws s3 cp")


def test_every_exit_cancels_the_pending_timer_first() -> None:
    """Asserted inside `die`'s own body: the comment above it names `shutdown -h now` while
    explaining the trap, so a search over the whole file would match the prose and pass."""
    body = _user_data()
    die = body[body.index("die() {") : body.index("dnf install")]
    assert "shutdown -c" in die
    assert die.index("shutdown -c") < die.index("shutdown -h now")
    assert "systemctl --no-block poweroff" in die
    assert "halt -p" in die
    assert 'die "no python 3.11+ available; nothing to run"' in body
    assert 'die "run complete" "$rc"' in body


def test_the_payload_is_imported_before_the_long_read() -> None:
    """Python collapses the `\\`-continued lines of USER_DATA, so the invocation is one
    long line by the time bash sees it — which is why this matches the bare tool name."""
    body = _user_data()
    assert body.index("PRECHECK") < body.index('( "$PYBIN" tools/opengenome_contigs.py')


def test_every_archive_runs_and_each_gets_its_own_worker() -> None:
    body = _user_data()
    assert "for archive in v214/batch1.tar v214/batch2.tar v214/batch3.tar v220_update.tar" in body
    # Backgrounded and waited on: four single-core workers, which is the whole of the
    # available parallelism because a gzip stream cannot be split.
    assert ") &" in body
    assert "\nwait\n" in body


def test_only_restricts_the_archives_the_instance_reads() -> None:
    """A reclaim publishes some archives and loses others, and the bucket has no delete, so
    a re-run has to be able to name just the ones that are missing."""
    body = _user_data(archives="v220_update.tar")
    assert "for archive in v220_update.tar" in body
    assert "batch1" not in body.split("for archive in")[1]


def test_user_data_passes_the_run_its_provenance_and_its_heartbeat() -> None:
    body = _user_data()
    assert "--code-commit abc123" in body
    assert "--heartbeat-seconds 120.0" in body
    assert "--upload-results" in body


def test_user_data_is_under_the_sixteen_kilobyte_cap() -> None:
    assert len(_user_data().encode()) < 16 * 1024


def test_the_interpreter_is_picked_by_name_not_trusted() -> None:
    """Amazon Linux 2023's `python3` is 3.9 and this project needs 3.12."""
    body = _user_data()
    assert "python3.12" in body
    assert 'if [ -z "$PYBIN" ]' in body

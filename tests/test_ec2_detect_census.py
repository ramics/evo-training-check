"""Tests for `tools/ec2_detect_census.py` — A2.6's in-region launcher.

What is tested here is everything that cannot be fixed after launch. `AGENTS.md`'s EC2
section is a list of failures this project has already paid for: a short payload, an
interpreter that turned out to be 3.9, a `shutdown -h now` that did nothing because a timer
was pending, a `wait` that reported success for a dead worker. Each of those costs an hour
and a launch on the instance and a second here.

The band arithmetic is tested hardest, because a gap in the bands is not discovered until
`--assemble` refuses the table, which is after the compute has been spent.
"""

from __future__ import annotations

import importlib.util
import itertools
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "ec2_detect_census", _PATH.parent.parent / "tools" / "ec2_detect_census.py"
)
assert _spec and _spec.loader
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)

_dspec = importlib.util.spec_from_file_location(
    "detect_profiles_for_launcher", _PATH.parent.parent / "tools" / "detect_profiles.py"
)
assert _dspec and _dspec.loader
detect_profiles = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(detect_profiles)


def rendered(**kw):
    workers = kw.pop("workers", None) or launcher.plan(("opengenome",), 2)
    return launcher.user_data(
        bucket="b",
        prefix="corpora",
        code_key="corpora/code/a2-6-abc.tar.gz",
        workers=workers,
        hard_stop_minutes=540,
        **kw,
    )


class TestTheBands:
    @pytest.mark.parametrize("workers", [1, 2, 3, 5, 7, 11, 16, 32])
    def test_they_tile_the_whole_remaining_range(self, workers) -> None:
        """`--assemble` refuses a table whose bands leave a gap, and it refuses it after
        the compute. The split has to be exact, not approximately exact."""
        for multiple in launcher.CENSUS_MULTIPLE.values():
            out = launcher.bands(multiple, workers)
            assert out[0][0] == 1
            assert out[-1][1] == multiple
            for (_, end), (start, _) in itertools.pairwise(out):
                assert end == start

    @pytest.mark.parametrize("workers", [1, 3, 7, 16])
    def test_no_band_is_empty(self, workers) -> None:
        """An empty band would start a worker that reads a whole component and keeps
        nothing, which is the most expensive way to do no work."""
        for multiple in launcher.CENSUS_MULTIPLE.values():
            assert all(lo < hi for lo, hi in launcher.bands(multiple, workers))

    def test_a_multiple_that_leaves_nothing_to_read_is_refused(self) -> None:
        with pytest.raises(ValueError, match="nothing to read"):
            launcher.bands(1, 4)

    def test_more_workers_than_the_range_can_split_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot split"):
            launcher.bands(5, 9)


class TestTheCensusMultiples:
    def test_each_one_takes_its_release_to_a_rate_of_exactly_one(self) -> None:
        """The multiple is in units of the component's own initial rate, so it is the
        reciprocal of that rate and nothing else. Hard-coding a number that drifted from
        the rate would read a fraction of the corpus and call it a census."""
        by_release = {"opengenome": "stage2", "opengenome2": "imgvr"}
        for release, component in by_release.items():
            rate = detect_profiles.SAMPLE_RATES[component]
            assert launcher.CENSUS_MULTIPLE[release] * rate == pytest.approx(1.0)

    def test_opengenome2s_two_components_share_a_rate(self) -> None:
        """One multiple per release only works while its components agree; if they ever
        diverge the launcher has to split by component instead."""
        assert detect_profiles.SAMPLE_RATES["imgvr"] == detect_profiles.SAMPLE_RATES["imgpr"]


class TestThePayload:
    def test_it_covers_the_tools_first_party_import_closure(self) -> None:
        """The failure this exists for: a module added to a tool's imports and not here,
        and the instance dying on an ImportError half a minute in, having read nothing."""
        root = _PATH.parent.parent
        shipped = set(launcher.PAYLOAD_MODULES)
        seen: set[str] = set()
        queue = ["tools/detect_profiles.py", "tools/stage_profiles.py"]
        while queue:
            rel = queue.pop()
            if rel in seen:
                continue
            seen.add(rel)
            text = (root / rel).read_text()
            for line in text.splitlines():
                line = line.strip()
                for prefix in ("from amazebio import ", "from amazebio."):
                    if not line.startswith(prefix):
                        continue
                    if prefix.endswith("import "):
                        names = line[len(prefix) :].split("#")[0]
                        mods = [n.strip() for n in names.split(",") if n.strip()]
                    else:
                        mods = [line[len(prefix) :].split()[0].split(".")[0]]
                    for mod in mods:
                        candidate = f"src/amazebio/{mod}.py"
                        if (root / candidate).exists():
                            assert candidate in shipped, f"{rel} imports {mod}, not shipped"
                            queue.append(candidate)

    def test_every_shipped_path_exists(self) -> None:
        root = _PATH.parent.parent
        for rel in launcher.PAYLOAD_MODULES:
            assert (root / rel).exists(), rel

    def test_the_payload_is_imported_before_the_long_read(self) -> None:
        text = rendered()
        assert text.index("PRECHECK") < text.index("tools/detect_profiles.py --task")


class TestTheShutdownPaths:
    def test_the_timer_is_armed_before_anything_that_can_fail(self) -> None:
        text = rendered()
        assert text.index("shutdown -h +540") < text.index("dnf install")

    def test_every_exit_cancels_the_pending_timer_first(self) -> None:
        """`shutdown -h now` is a no-op while a timer is pending, and the instance then
        idles for the whole window looking exactly like a long pass (D-127)."""
        text = rendered()
        die = text[text.index("die() {") : text.index("dnf install")]
        assert die.index("shutdown -c") < die.index("shutdown -h now")
        assert "systemctl --no-block poweroff" in die
        assert "halt -p" in die

    def test_a_failure_before_the_workers_still_goes_down(self) -> None:
        text = rendered()
        for step in ("no python 3.11+", "wheels did not install", "cannot import", "did not stage"):
            assert step in text


class TestTheWorkers:
    def test_each_worker_is_waited_on_by_pid(self) -> None:
        """`wait` with no arguments reports 0 whatever the jobs did, so a dead worker would
        be announced as a clean run."""
        text = rendered()
        assert 'wait "$pid"' in text
        assert 'pids="$pids $!"' in text

    def test_the_wait_loop_cannot_abort_the_script_before_die(self) -> None:
        text = rendered()
        assert text.index("set +e") < text.index('wait "$pid"') < text.index("set -e\n")

    def test_every_worker_names_the_task_so_a21s_tables_are_safe(self) -> None:
        workers = launcher.plan(("opengenome", "opengenome2"), 3)
        lines = launcher.worker_lines(workers)
        assert lines.count("--task A2.6") == len(workers)
        assert "--task A2.1" not in lines

    def test_one_worker_per_band_and_no_shared_output_directory(self) -> None:
        workers = launcher.plan(("opengenome", "opengenome2"), 4)
        outs = [w["slug"] for w in workers]
        assert len(set(outs)) == len(outs)

    def test_only_pfam_is_searched(self) -> None:
        """RVDB-prot is fifteen times slower and M3's bins are Pfam's. A census that
        quietly included it would spend twelve dollars nobody approved (D-222)."""
        assert launcher.REGISTRY == "pfam"
        assert "--registry rvdb-prot" not in rendered()


class TestTheRunInstancesCall:
    def test_the_hard_stop_covers_the_estimate_with_room(self) -> None:
        """Eighty core-hours over eight cores is five to seven hours of wall clock. A
        timer that fires on the estimate turns a slow run into no run at all."""
        assert launcher.DEFAULT_HARD_STOP_MINUTES >= 12 * 60

    def test_the_default_type_is_one_the_account_permits(self) -> None:
        """Measured by dry run on 2026-10-20: every 4xlarge and larger is refused, and the
        refusal is a bare UnauthorizedOperation that reads like having no permission at
        all. The first sizing of this launcher was a 4xlarge and died on exactly that."""
        assert launcher.DEFAULT_INSTANCE_TYPE in launcher.ALLOWED_TYPES
        assert all(t.endswith((".xlarge", ".2xlarge")) for t in launcher.ALLOWED_TYPES)

    def test_a_release_fits_on_one_permitted_machine(self) -> None:
        """Eight vCPU is the ceiling, so a worker count above it would oversubscribe the
        cores and the second release would wait on the first."""
        assert launcher.DEFAULT_WORKERS_PER_RELEASE <= 8

    def test_the_manifests_come_from_the_store_not_the_payload(self) -> None:
        """A1.4's manifests say which records survive. Shipping a copy inside the tarball
        would let the instance search a surviving set that `main` no longer agrees with."""
        assert "results/a1-4/" in rendered()
        assert not any("a1-4" in p for p in launcher.PAYLOAD_MODULES)

    def test_the_manifest_copy_names_the_whole_key(self) -> None:
        """This assertion used to be the substring above, and the first launch copied from
        `s3://bucket/results/a1-4/` with the prefix missing. `aws s3 cp --recursive` over a
        prefix with nothing under it exits 0, so eight workers started on an empty directory
        and the instance was down five minutes later."""
        assert "s3://b/corpora/results/a1-4/" in rendered()

    def test_an_empty_copy_cannot_reach_the_workers(self) -> None:
        """Because that copy succeeds when it brings nothing, the check is what turns the
        silence into a failure, and it has to come before the workers start."""
        text = rendered()
        assert "test -f artifacts/a1-4/index.json" in text
        assert text.index("test -f artifacts/a1-4/index.json") < text.index('pids=""')

    def test_the_reason_for_an_exit_is_written_where_it_can_be_read(self) -> None:
        """`GetConsoleOutput` was empty for ten minutes after the instance that needed
        reading had terminated. An object in the store is not best-effort."""
        die = rendered()
        die = die[die.index("die() {") : die.index("dnf install")]
        assert "aws s3 cp /tmp/why.txt" in die
        assert "results/a2-6/exit-" in die


class TestMainOnADryRun:
    """The launcher's own `main` up to the authorization call.

    The band arithmetic and the `UserData` are tested above as pure functions, which left
    `main` itself — the assembly of the `run_instances` keywords — exercised by nothing. A
    wrong argument there raises on the dry run, which is cheap, but only if someone runs
    one; `market_options` was called with no argument and the mistake survived the whole
    suite.
    """

    @staticmethod
    def _boto3(monkeypatch, calls):
        class S3:
            def put_object(self, **kw):
                calls.append(("put_object", kw))

        class SSM:
            def get_parameter(self, **kw):
                return {"Parameter": {"Value": "ami-0123456789abcdef0"}}

        class EC2:
            def run_instances(self, **kw):
                calls.append(("run_instances", kw))
                if not kw.get("DryRun"):
                    raise AssertionError("a dry run must not launch")
                raise RuntimeError("DryRunOperation: Request would have succeeded")

        class Boto3:
            @staticmethod
            def client(name, **kw):
                return {"s3": S3(), "ec2": EC2(), "ssm": SSM()}[name]

        monkeypatch.setitem(__import__("sys").modules, "boto3", Boto3)

    def run(self, monkeypatch, *argv):
        calls: list[tuple[str, dict]] = []
        self._boto3(monkeypatch, calls)
        assert (
            launcher.main(
                [
                    "--s3-uri",
                    "s3://bucket/corpora",
                    "--allow-dirty",
                    "--dry-run",
                    *argv,
                ]
            )
            == 0
        )
        return calls

    def test_it_authorizes_without_raising(self, monkeypatch) -> None:
        calls = self.run(monkeypatch)
        assert [name for name, _ in calls] == ["run_instances"]

    def test_spot_asks_for_a_one_time_request_that_terminates_on_reclaim(self, monkeypatch) -> None:
        calls = self.run(monkeypatch, "--spot")
        kw = dict(calls)["run_instances"]
        market = kw["InstanceMarketOptions"]
        assert market["MarketType"] == "spot"
        assert market["SpotOptions"]["SpotInstanceType"] == "one-time"
        assert market["SpotOptions"]["InstanceInterruptionBehavior"] == "terminate"

    def test_on_demand_says_nothing_about_the_market(self, monkeypatch) -> None:
        kw = dict(self.run(monkeypatch))["run_instances"]
        assert "InstanceMarketOptions" not in kw

    def test_a_dry_run_uploads_no_payload(self, monkeypatch) -> None:
        """The corpus bucket has no delete, so a tarball put here for a launch that never
        happens is permanent."""
        assert "put_object" not in [name for name, _ in self.run(monkeypatch)]

    def test_the_launch_carries_the_policys_tags_and_a_terminating_shutdown(
        self, monkeypatch
    ) -> None:
        """Omit either tag and the refusal is a bare UnauthorizedOperation, which reads
        exactly like having no permission at all."""
        kw = dict(self.run(monkeypatch))["run_instances"]
        tags = {t["Key"]: t["Value"] for t in kw["TagSpecifications"][0]["Tags"]}
        assert tags["Project"] == "ClaudeSpike"
        assert tags["Owner"]
        assert tags["Task"] == "A2.6"
        assert kw["InstanceInitiatedShutdownBehavior"] == "terminate"

    def test_the_volume_is_within_what_the_policy_allows(self, monkeypatch) -> None:
        kw = dict(self.run(monkeypatch))["run_instances"]
        ebs = kw["BlockDeviceMappings"][0]["Ebs"]
        assert ebs["VolumeType"] in {"gp2", "gp3"}
        assert ebs["VolumeSize"] <= 200


class TestDetaching:
    """`--detach` gives up the launcher's own `finally` terminate, so the two things that
    replace it have to hold: the boot timer, and a printed id that `--attach` can use."""

    @staticmethod
    def _run(monkeypatch, *argv):
        calls: list[tuple[str, dict]] = []
        printed: list[str] = []

        class S3:
            def put_object(self, **kw):
                calls.append(("put_object", kw))

        class SSM:
            def get_parameter(self, **kw):
                return {"Parameter": {"Value": "ami-0123456789abcdef0"}}

        class EC2:
            def run_instances(self, **kw):
                calls.append(("run_instances", kw))
                return {"Instances": [{"InstanceId": "i-0deadbeef0000001"}]}

            def describe_instances(self, **kw):
                raise AssertionError("a detached launcher does not watch")

            def terminate_instances(self, **kw):
                calls.append(("terminate_instances", kw))

        class Boto3:
            @staticmethod
            def client(name, **kw):
                return {"s3": S3(), "ec2": EC2(), "ssm": SSM()}[name]

        monkeypatch.setitem(__import__("sys").modules, "boto3", Boto3)
        monkeypatch.setattr(
            "builtins.print", lambda *a, **kw: printed.append(" ".join(map(str, a)))
        )
        code = launcher.main(
            ["--s3-uri", "s3://bucket/corpora", "--allow-dirty", "--detach", *argv]
        )
        return code, calls, "\n".join(printed)

    def test_it_launches_and_does_not_terminate(self, monkeypatch) -> None:
        code, calls, _ = self._run(monkeypatch)
        assert code == 0
        names = [n for n, _ in calls]
        assert "run_instances" in names
        assert "terminate_instances" not in names

    def test_it_prints_the_id_the_way_back_in(self, monkeypatch) -> None:
        """Detached, the id is the only handle on a running instance, and there is no
        shell on it to ask."""
        _, _, out = self._run(monkeypatch)
        assert "i-0deadbeef0000001" in out
        assert "--attach i-0deadbeef0000001" in out

    def test_the_boot_timer_is_what_is_left_holding_it(self, monkeypatch) -> None:
        _, calls, out = self._run(monkeypatch)
        kw = dict(calls)["run_instances"]
        assert f"shutdown -h +{launcher.DEFAULT_HARD_STOP_MINUTES}" in kw["UserData"]
        assert kw["InstanceInitiatedShutdownBehavior"] == "terminate"
        assert str(launcher.DEFAULT_HARD_STOP_MINUTES) in out

    def test_it_still_uploads_the_payload(self, monkeypatch) -> None:
        _, calls, _ = self._run(monkeypatch)
        assert "put_object" in [n for n, _ in calls]


def test_the_s3_client_names_the_regional_endpoint(monkeypatch) -> None:
    """boto3's default global endpoint is not `*.us-east-1.amazonaws.com`, which is what
    the session's credential proxy allow-lists. The put then fails as a bare `403
    Forbidden` that reads like a bucket policy, and both launches died on it."""
    built: list[dict] = []

    class Client:
        def put_object(self, **kw):
            pass

        def get_parameter(self, **kw):
            return {"Parameter": {"Value": "ami-0123456789abcdef0"}}

        def run_instances(self, **kw):
            return {"Instances": [{"InstanceId": "i-0deadbeef0000001"}]}

    class Boto3:
        @staticmethod
        def client(name, **kw):
            built.append({"service": name, **kw})
            return Client()

    monkeypatch.setitem(__import__("sys").modules, "boto3", Boto3)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)
    launcher.main(["--s3-uri", "s3://bucket/corpora", "--allow-dirty", "--detach"])

    s3 = next(c for c in built if c["service"] == "s3")
    assert s3["endpoint_url"].endswith(".us-east-1.amazonaws.com")


def test_a_spot_refusal_is_explained_rather_than_raised_raw(monkeypatch) -> None:
    """The three spot refusals need three different responses — an IAM action, a quota
    raise, or a retry — and botocore's message distinguishes none of them."""

    class Client:
        def put_object(self, **kw):
            pass

        def get_parameter(self, **kw):
            return {"Parameter": {"Value": "ami-0123456789abcdef0"}}

        def run_instances(self, **kw):
            raise RuntimeError("MaxSpotInstanceCountExceeded: Max spot instance count exceeded")

    class Boto3:
        @staticmethod
        def client(name, **kw):
            return Client()

    monkeypatch.setitem(__import__("sys").modules, "boto3", Boto3)
    monkeypatch.setattr("builtins.print", lambda *a, **kw: None)
    with pytest.raises(SystemExit) as caught:
        launcher.main(["--s3-uri", "s3://bucket/corpora", "--allow-dirty", "--detach", "--spot"])
    message = str(caught.value)
    assert "quota" in message
    assert "nothing launched" in message


class TestWhatTheImportClosureCannotSee:
    """Two of the three things a worker needs are read at runtime, not imported.

    The policy specs are one of them, and leaving them out cost a launch: eight workers
    started, each died on `no policy specs found in .../policies/specs`, and the instance
    was down six minutes later having read nothing. An import-closure check cannot catch
    that by construction, so these are named explicitly and the precheck loads them.
    """

    def test_the_policy_specs_ship(self) -> None:
        assert "policies/specs" in launcher.PAYLOAD_MODULES

    def test_they_are_actually_in_the_tarball(self, tmp_path) -> None:
        import io
        import tarfile

        root = _PATH.parent.parent
        with tarfile.open(fileobj=io.BytesIO(launcher.build_payload(root)), mode="r:gz") as tar:
            names = tar.getnames()
        specs = [n for n in names if n.startswith("policies/specs/") and n.endswith(".yaml")]
        assert specs, names[:20]
        # Every reading the census resolves routes against, not just one of them.
        assert any("evo1-literal" in n for n in specs)
        assert any("evo1-strict" in n for n in specs)
        assert any("evo1-charitable" in n for n in specs)

    def test_the_precheck_loads_them_rather_than_only_importing(self) -> None:
        text = rendered()
        assert "load_policy_dir" in text
        assert "load_manifests" in text
        assert text.index("load_policy_dir") < text.index("tools/detect_profiles.py --task")

    def test_the_precheck_loads_the_manifests_too(self) -> None:
        """The other runtime read. A copy that brought nothing is checked for existence
        earlier; this checks the files parse."""
        assert "load_manifests" in rendered()


def test_the_payload_alone_imports_and_loads_its_policies(tmp_path) -> None:
    """The payload unpacked on its own, as the instance has it: no checkout, no `src` on
    the path but its own, nothing else.

    This is the check the import-closure test cannot be. Three launches were spent on
    things an import closure cannot see — a module missing from the list, then the policy
    specs, which are read at runtime — and each cost an instance and most of an hour. Here
    it costs a second, and it fails for the same reasons.
    """
    import io
    import json
    import subprocess
    import sys
    import tarfile

    root = _PATH.parent.parent
    with tarfile.open(fileobj=io.BytesIO(launcher.build_payload(root)), mode="r:gz") as tar:
        tar.extractall(tmp_path, filter="data")

    probe = """
import importlib.util, json, sys
sys.path.insert(0, "src")
spec = importlib.util.spec_from_file_location("worker", "tools/detect_profiles.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from amazebio.policyspec import load_policy_dir
print(json.dumps(sorted(load_policy_dir(module.SPECS))))
"""
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    loaded = json.loads(done.stdout.strip().splitlines()[-1])
    assert "evo1-literal" in loaded
    assert "evo1-strict" in loaded
    assert "evo1-charitable" in loaded


class TestWhatAWorkerLeavesBehind:
    """Three launches were diagnosed from `GetConsoleOutput`, which truncated each time —
    the third console ended mid-way through staging the profiles and said nothing about why
    eight workers had failed. A worker's own output has to come back on its own."""

    def test_each_worker_writes_its_own_log(self) -> None:
        workers = launcher.plan(("opengenome",), 3)
        lines = launcher.worker_lines(workers)
        assert lines.count("> /opt/amazebio/log-") == len(workers)
        assert len({w["slug"] for w in workers}) == len(workers)

    def test_the_logs_are_uploaded_on_every_exit(self) -> None:
        text = rendered()
        die = text[text.index("die() {") : text.index("dnf install")]
        assert 'include "log-*.txt"' in die
        assert "results/a2-6/logs-" in die

    def test_the_chunk_is_small_enough_for_eight_on_one_machine(self) -> None:
        """Measured 2026-10-20: 20,000 stage-2 records peaked at 1.0 GB, and IMG/PR calls
        three times the genes per record. Eight of those would not fit the 16 GB machine
        the launcher can land on."""
        assert launcher.CHUNK_RECORDS <= 8_000
        assert f"--chunk-records {launcher.CHUNK_RECORDS}" in rendered()

    def test_the_chunk_size_is_the_launchers_call_not_the_tools_default(self) -> None:
        text = launcher.user_data(
            bucket="b",
            prefix="corpora",
            code_key="k",
            workers=launcher.plan(("opengenome",), 2),
            hard_stop_minutes=540,
            chunk=1234,
        )
        assert "--chunk-records 1234" in text


class TestTheWheels:
    """A deferred import is still a dependency.

    `policyspec` imports `yaml` inside `load_policy_dir` rather than at module scope, so
    the payload imported cleanly on the instance and died on the first policy read. The
    import-closure test walks `from amazebio` lines and could never have seen it; this
    walks every import in the shipped sources instead.
    """

    @staticmethod
    def _third_party() -> set[str]:
        import ast
        import sys

        root = _PATH.parent.parent
        names: set[str] = set()
        for rel in launcher.PAYLOAD_MODULES:
            path = root / rel
            if path.is_dir() or path.suffix != ".py":
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
        return {
            n for n in names if n not in sys.stdlib_module_names and n not in {"amazebio", "tools"}
        }

    def test_every_third_party_import_has_a_wheel(self) -> None:
        missing = sorted(n for n in self._third_party() if n not in launcher.WHEEL_IMPORTS)
        assert not missing, f"imported by the payload, not mapped to a wheel: {missing}"

    def test_every_mapped_wheel_is_installed_on_the_instance(self) -> None:
        for name in sorted(set(launcher.WHEEL_IMPORTS.values())):
            assert name in launcher.WHEELS, name

    def test_yaml_is_among_them(self) -> None:
        """Named, because this is the one that cost the launch and the one a reader will
        not expect: nothing imports it at module scope."""
        assert launcher.WHEEL_IMPORTS["yaml"] == "pyyaml"
        assert "pyyaml" in launcher.WHEELS


class TestTheWorkersMaySaySoAndARehearsalMayNot:
    """D-224. `detect_profiles` refuses to publish from a directory that is not the task's
    canonical one, which is what stops a rehearsal reaching the census prefix. The workers
    write to `/opt/amazebio/out-<band>` and are the deliverable, so the launcher has to say
    so explicitly — and if it ever stops saying so, a whole census publishes nothing."""

    def test_every_worker_line_declares_itself_the_deliverable(self) -> None:
        """Publication is a parameter now, for the probe D-233 added; the census default
        is still that a worker publishes, and that is what must not drift."""
        assert "--deliverable" in launcher.worker_lines(launcher.plan(("opengenome",), 1))

    def test_the_declaration_reaches_every_worker_in_the_rendered_user_data(self) -> None:
        workers = launcher.plan(("opengenome",), 8)
        text = rendered(workers=workers)
        assert text.count("--deliverable") == len(workers)

    def test_a_workers_out_directory_would_otherwise_refuse_to_publish(self) -> None:
        """The reason the flag has to exist, pinned so removing it fails here first."""
        out = pathlib.Path("/opt/amazebio/out-opengenome-1-63")
        assert detect_profiles.durable_for("A2.6", out) is None
        assert detect_profiles.durable_for("A2.6", out, deliverable=True) is not None


class TestWhatSurvivesAHardStop:
    """D-233. The 2026-10-21 census spent fourteen hours on two machines and published
    nothing — no part, no exit note, no log — because the hard stop powers the machine off
    from outside the script and both publishing paths run only when the work finishes. The
    heartbeat is the one thing that makes a run which never finishes diagnosable, so it is
    armed before anything slow and it is tested here rather than discovered next time."""

    def test_the_logs_are_copied_on_a_timer_not_only_on_exit(self) -> None:
        text = rendered()
        assert "hb_iid" in text
        assert text.count("logs-$hb_iid/") == 1

    def test_the_heartbeat_is_armed_before_the_profiles_are_staged(self) -> None:
        text = rendered()
        assert text.index("hb_iid=") < text.index("stage_profiles.py")

    def test_the_interval_is_shorter_than_the_stop_it_reports_against(self) -> None:
        assert launcher.HEARTBEAT_SECONDS * 2 < launcher.DEFAULT_HARD_STOP_MINUTES * 60

    def test_the_heartbeat_cannot_fail_the_run(self) -> None:
        """`set -e` is on; a copy that fails while the store is briefly unreachable must
        not be what ends a fourteen-hour pass."""
        line = next(ln for ln in rendered().splitlines() if "logs-$hb_iid/" in ln)
        assert line.rstrip().endswith("|| true")


class TestATimingProbeMayNotPublish:
    """D-232's rule, applied where the subset is the band rather than a flag. A probe reads
    a sliver of one band; its part would sit beside the real ones under the census prefix
    looking like a band somebody had done."""

    def test_a_probe_worker_does_not_declare_itself_the_deliverable(self) -> None:
        worker = launcher.probe(("opengenome2",), "1:4")
        assert "--deliverable" not in launcher.worker_lines([worker], deliverable=False)

    def test_a_census_worker_still_does(self) -> None:
        workers = launcher.plan(("opengenome",), 2)
        assert launcher.worker_lines(workers).count("--deliverable") == len(workers)

    def test_the_rendered_probe_carries_no_publication(self) -> None:
        worker = launcher.probe(("opengenome2",), "1:4")
        assert "--deliverable" not in rendered(workers=[worker], deliverable=False)

    def test_a_probe_times_one_release(self) -> None:
        with pytest.raises(SystemExit):
            launcher.probe(("opengenome", "opengenome2"), "1:4")

    def test_a_band_outside_the_release_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            launcher.probe(("opengenome",), "1:5000")

    def test_an_inverted_band_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            launcher.probe(("opengenome",), "9:4")

    def test_a_band_that_is_not_two_numbers_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            launcher.probe(("opengenome",), "first half")

    def test_the_probe_names_its_own_output_directory(self) -> None:
        assert launcher.probe(("opengenome2",), "1:4")["slug"] == "opengenome2-1-4"

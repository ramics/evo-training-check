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
        """Measured at about six hours. A timer that fires on the estimate turns a slow
        run into no run at all."""
        assert launcher.DEFAULT_HARD_STOP_MINUTES >= 8 * 60

    def test_the_manifests_come_from_the_store_not_the_payload(self) -> None:
        """A1.4's manifests say which records survive. Shipping a copy inside the tarball
        would let the instance search a surviving set that `main` no longer agrees with."""
        assert "results/a1-4/" in rendered()
        assert not any("a1-4" in p for p in launcher.PAYLOAD_MODULES)

"""A local smoke test of the instance path: the shipped tarball and the shell script.

Two launches were lost on 2026-10-16 and 2026-10-17 (D-127) and both failures lived in the
gap these tests close. The unit tests exercise functions, and the local rehearsals ran
`tools/esm3_calibrate.py` **from the repository**, where `src/amazebio` is present whether or
not the launcher ships it. Neither touched the two things that actually broke:

* the **payload tarball** — a module imported by the tool and absent from `PAYLOAD` is invisible
  until an instance tries to import it, half a minute into a run that has already been paid for;
* the **`UserData` script** — a `bash` program assembled by `str.format`, with `{{`/`}}`
  escaping, that nothing ever parsed before an instance ran it as root with no shell to debug it.

So these tests build the real tarball, extract it somewhere with no repository in sight, and run
the shipped tool from there in an isolated interpreter; and they render the real `UserData` and
hand it to `bash -n`. Both are seconds. On an instance the same two faults cost an hour and a
launch each, and `AGENTS.md`'s rule is that you get one shot at `UserData` and nothing else.

What is deliberately **not** simulated: `dnf`, the aligner download, `shutdown`, and the S3
round trip, all of which need root, network or a bucket. The staging and loading paths are
covered against a local stand-in elsewhere; what is unique here is that the code under test is
the *shipped copy*, reached the way the instance reaches it.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import pathlib
import random
import string
import subprocess
import sys
import tarfile
import zipfile

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PATH = _ROOT / "tools" / "ec2_similarity.py"
_spec = importlib.util.spec_from_file_location("ec2_similarity_smoke", _PATH)
launcher = importlib.util.module_from_spec(_spec)
sys.modules["ec2_similarity_smoke"] = launcher
_spec.loader.exec_module(launcher)


def _render_user_data(**over: object) -> str:
    """Render `UserData` with every field the launcher supplies, as it does at launch."""
    fields = {f for _, f, _, _ in string.Formatter().parse(launcher.USER_DATA) if f}
    values: dict[str, object] = {
        "bucket": "amazebio-corpora-000000000000",
        "prefix": "corpora",
        "code_key": "corpora/code/a1-6-caps-1.tar.gz",
        "region": "us-east-1",
        "commit": "0" * 40,
        "release": "2023_02",
        "tier": "uniref100",
        "sample_rate": 40,
        "buckets": 8,
        "strict_buckets": 3,
        "query_fractions": "1000,100",
        "shard_points": "1,2",
        "cap_query_denominator": 100,
        "cap_shard_points": "1,2",
        "cap_fractions": "0.5,0.2",
        "threads": 8,
        "workers": 7,
        "budget": 7200.0,
        "hard_stop_minutes": 240,
        "mmseqs_url": "https://example.invalid/mmseqs.tar.gz",
        "mmseqs_sha256": "0" * 64,
        "taxdump_url": "https://example.invalid/taxdmp.zip",
        "taxdump_sha256": "0" * 64,
        "measure": "caps",
        "sample_flags": "--stage-sample",
    }
    missing = fields - set(values)
    assert not missing, f"this test does not supply {missing}; add it rather than skipping"
    values.update(over)
    return launcher.USER_DATA.format(**values)


def test_user_data_is_valid_bash(tmp_path: pathlib.Path) -> None:
    """`bash -n` parses it. Nothing else ever did before an instance ran it as root.

    The brace escaping that `str.format` requires makes a shell function inside this template
    easy to break in a way no Python test notices — `die() {{ ... }}` renders to `die() { ... }`
    only if every brace is doubled correctly.
    """
    script = tmp_path / "user-data.sh"
    script.write_text(_render_user_data())
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, f"UserData is not valid bash:\n{proc.stderr}"


def test_user_data_has_no_unexpanded_placeholders() -> None:
    """A `{name}` left in the rendered script is a silent literal in a program run as root."""
    rendered = _render_user_data()
    for fragment in ("{bucket", "{prefix", "{commit", "{measure", "{sample_flags"):
        assert fragment not in rendered


def test_the_die_helper_is_a_function_and_cancels_before_shutting_down(
    tmp_path: pathlib.Path,
) -> None:
    """D-127's second fault. Exercised as shell rather than asserted as text: a stubbed
    `shutdown` records its arguments, so the order is observed, not hoped for."""
    rendered = _render_user_data()
    # Line-based extraction: the function opens with `die() {` and closes with a `}` in column
    # zero. Slicing on the first brace after `exit` found the wrong one.
    lines = rendered.splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.startswith("die() {"))
    last = next(i for i, ln in enumerate(lines[first:], first) if ln == "}")
    body = "\n".join(lines[first : last + 1])
    harness = tmp_path / "die.sh"
    calls = tmp_path / "calls"
    harness.write_text(
        "#!/bin/bash\n"
        f'shutdown() {{ echo "shutdown $*" >> {calls}; }}\n'
        f'systemctl() {{ echo "systemctl $*" >> {calls}; }}\n'
        "exit() { return 0; }\n" + body + '\ndie "smoke" 0\n'
    )
    subprocess.run(["bash", str(harness)], check=True, capture_output=True)
    recorded = calls.read_text().splitlines()
    assert recorded[0] == "shutdown -c", f"the pending timer must be cancelled first: {recorded}"
    assert any("now" in line for line in recorded[1:]), recorded


def _fixture_corpus(path: pathlib.Path, entries: int = 200) -> None:
    rng = random.Random(11)
    aa = "ACDEFGHIKLMNPQRSTVWY"
    motif = "".join(rng.choice(aa) for _ in range(40))
    blocks = []
    for i in range(entries):
        taxid = 11158 if i % 3 == 0 else 1280
        body = "".join(rng.choice(aa) for _ in range(90))
        if i % 2 == 0:
            body = motif + body[len(motif) :]
        blocks.append(
            f'<entry id="UniRef100_T{i:05d}" updated="2023-01-01">\n'
            f'<property type="member count" value="1"/>\n'
            f"<representativeMember>\n"
            f'  <dbReference type="UniProtKB ID" id="REP_T{i:05d}">\n'
            f'    <property type="NCBI taxonomy" value="{taxid}"/>\n'
            f"  </dbReference>\n"
            f'  <sequence length="{len(body)}" checksum="X">{body}</sequence>\n'
            f"</representativeMember>\n</entry>"
        )
    with gzip.open(path, "wt") as fh:
        fh.write("<UniRef100>\n" + "\n".join(blocks) + "\n</UniRef100>\n")


def _fixture_taxdump(path: pathlib.Path) -> None:
    rows = [(10239, 1), (11157, 10239), (11158, 11157), (2, 1), (1280, 2), (1, 1)]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("nodes.dmp", "".join(f"{c}\t|\t{p}\t|\tno rank\t|\n" for c, p in rows))


@pytest.fixture(scope="module")
def shipped(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """The real payload tarball, extracted where no repository is reachable."""
    out = tmp_path_factory.mktemp("shipped")
    with tarfile.open(fileobj=io.BytesIO(launcher.build_payload(_ROOT)), mode="r:gz") as tar:
        tar.extractall(out, filter="data")  # our own tarball, built two lines above
    return out


def test_the_shipped_payload_imports_on_its_own(shipped: pathlib.Path) -> None:
    """The exact failure that cost two launches, in two seconds.

    Isolated interpreter (`-I` drops PYTHONPATH, user site and the script directory) and a
    working directory with no repository above it, so nothing can satisfy an import that the
    tarball does not carry. The tool puts its own `src` on the path, which is what the instance
    relies on too.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import importlib.util, sys;"
            "spec = importlib.util.spec_from_file_location('cal', 'tools/esm3_calibrate.py');"
            "m = importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(m);"
            "print('imports cleanly')",
        ],
        cwd=shipped,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "the shipped payload cannot import itself — PAYLOAD is short:\n" + proc.stderr[-2000:]
    )


def test_the_shipped_payload_runs_a_whole_caps_measurement(
    shipped: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """End to end from the tarball: corpus pass, seed set, shards, searches, artefact.

    `--source` keeps it local, so no bucket and no boto3 are involved; everything else is the
    code the instance runs, reached the way the instance reaches it.
    """
    if not _which("mmseqs"):
        pytest.skip("mmseqs is not on PATH; the search half cannot run")
    corpus = tmp_path / "fixture.xml.gz"
    taxdump = tmp_path / "taxdmp.zip"
    _fixture_corpus(corpus)
    _fixture_taxdump(taxdump)

    proc = subprocess.run(
        [
            sys.executable,
            "-I",
            "tools/esm3_calibrate.py",
            "--measure",
            "caps",
            "--source",
            str(corpus),
            "--taxdump",
            str(taxdump),
            "--outdir",
            str(tmp_path / "out"),
            "--workdir",
            str(tmp_path / "work"),
            "--sample-rate",
            "1",
            "--buckets",
            "2",
            "--cap-shard-points",
            "1",
            "--cap-query-denominator",
            "2",
            "--cap-fractions",
            "0.5",
            "--threads",
            "2",
            "--workers",
            "1",
            "--allow-dirty",
            "--code-commit",
            "smoke",
        ],
        cwd=shipped,
        capture_output=True,
        text=True,
    )
    assert (
        proc.returncode == 0
    ), f"shipped run failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"

    import json

    payload = json.loads((tmp_path / "out" / "cap-measurement.json").read_text())
    assert payload["measure"] == "caps"
    assert payload["seed_counts"]["clusters"] == 200
    assert payload["seed_counts"]["seeded"] > 0
    done = [c for c in payload["searches"] if "search_wall_seconds" in c]
    assert done, "no search cell completed"
    assert any(c.get("saturation") for c in done), "the cap guard produced nothing"
    assert payload["cap_summary"]["published_cap"] == 100_000


def _which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _boto3_stub(root: pathlib.Path, bucket_dir: pathlib.Path) -> pathlib.Path:
    """A file-backed `boto3` the shipped tool imports instead of the real one.

    Shadowing the module rather than patching inside the process is what makes this a test of
    the *shipped* code: the subprocess imports `boto3`, builds its own client with its own
    config, and runs its own S3 paths. Patching from the test process would have exercised the
    repository copy and proved nothing about the tarball.
    """
    stub = root / "stub"
    pkg = stub / "boto3"
    pkg.mkdir(parents=True)
    (stub / "botocore").mkdir()
    (stub / "botocore" / "__init__.py").write_text("")
    (stub / "botocore" / "config.py").write_text(
        "class Config:\n    def __init__(self, *a, **k):\n        pass\n"
    )
    (pkg / "__init__.py").write_text(
        "import pathlib, json\n"
        f"ROOT = pathlib.Path({str(bucket_dir)!r})\n"
        "\n"
        "class _Body:\n"
        "    def __init__(self, data):\n"
        "        self.data = data\n"
        "    def read(self, size=-1):\n"
        "        if size is None or size < 0:\n"
        "            out, self.data = self.data, b''\n"
        "            return out\n"
        "        out, self.data = self.data[:size], self.data[size:]\n"
        "        return out\n"
        "\n"
        "class _Client:\n"
        "    def _p(self, key):\n"
        "        p = ROOT / key\n"
        "        p.parent.mkdir(parents=True, exist_ok=True)\n"
        "        return p\n"
        "    def put_object(self, Bucket, Key, Body):\n"
        "        self._p(Key).write_bytes(Body if isinstance(Body, bytes) else Body.encode())\n"
        "    def upload_file(self, filename, bucket, key):\n"
        "        self._p(key).write_bytes(pathlib.Path(filename).read_bytes())\n"
        "    def download_file(self, bucket, key, dest):\n"
        "        pathlib.Path(dest).write_bytes(self._p(key).read_bytes())\n"
        "    def get_object(self, Bucket, Key, Range=None):\n"
        "        data = self._p(Key).read_bytes()\n"
        "        if Range:\n"
        "            start = int(Range.split('=')[1].split('-')[0])\n"
        "            data = data[start:]\n"
        "        return {'Body': _Body(data), 'ContentLength': len(data)}\n"
        "    def head_object(self, Bucket, Key):\n"
        "        return {'ContentLength': self._p(Key).stat().st_size}\n"
        "    def list_objects_v2(self, Bucket, Prefix='', **kw):\n"
        "        hits = [q for q in ROOT.rglob('*') if q.is_file()\n"
        "                and str(q.relative_to(ROOT)).startswith(Prefix)]\n"
        "        return {'Contents': [{'Key': str(q.relative_to(ROOT))} for q in hits],\n"
        "                'IsTruncated': False}\n"
        "\n"
        "def client(*a, **k):\n"
        "    return _Client()\n"
    )
    return stub


def _run_shipped(
    shipped: pathlib.Path, stub: pathlib.Path, *extra: str
) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "PYTHONPATH": str(stub), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "tools/esm3_calibrate.py", *extra],
        cwd=shipped,
        capture_output=True,
        text=True,
        env=env,
    )


def test_the_shipped_payload_stages_and_reloads_a_sample(
    shipped: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The S3 paths, from the tarball, including the keys they write.

    This is the test that was missing: the other smoke test runs with `--source`, so no client
    is built and the staging code never executes. On 2026-10-17 that let a run reach an
    instance with staging keys that omitted the run's prefix — several gigabytes bound for the
    bucket root, permanently, in a bucket with no DeleteObject.
    """
    bucket = tmp_path / "bucket"
    stub = _boto3_stub(tmp_path, bucket)
    corpus_key = bucket / "corpora" / "uniref" / "2023_02" / "uniref100.tar" / "uniref100.xml.gz"
    corpus_key.parent.mkdir(parents=True)
    _fixture_corpus(corpus_key)
    taxdump = tmp_path / "taxdmp.zip"
    _fixture_taxdump(taxdump)

    common = [
        "--measure",
        "caps",
        "--s3-uri",
        "s3://buk/corpora",
        "--taxdump",
        str(taxdump),
        "--sample-rate",
        "1",
        "--buckets",
        "2",
        "--threads",
        "2",
        "--workers",
        "1",
        "--allow-dirty",
        "--code-commit",
        "smoke",
        "--upload-results",
        "--cap-shard-points",
        "1",
    ]
    staged = _run_shipped(
        shipped,
        stub,
        *common,
        "--outdir",
        str(tmp_path / "o1"),
        "--workdir",
        str(tmp_path / "w1"),
        "--stage-sample",
        "--skip-search",
    )
    assert (
        staged.returncode == 0
    ), f"staging run failed:\n{staged.stdout[-2500:]}{staged.stderr[-2500:]}"

    keys = sorted(str(p.relative_to(bucket)) for p in bucket.rglob("*") if p.is_file())
    sample_keys = [k for k in keys if "/samples/" in k or k.startswith("samples/")]
    assert sample_keys, f"nothing staged: {keys}"
    assert all(
        k.startswith("corpora/samples/a1-6/") for k in sample_keys
    ), f"staged keys escaped the run prefix: {sample_keys}"
    manifest = next(k for k in sample_keys if k.endswith("manifest.json"))

    # And the sample loads back, skipping the pass, with every digest verified.
    loaded = _run_shipped(
        shipped,
        stub,
        *common,
        "--outdir",
        str(tmp_path / "o2"),
        "--workdir",
        str(tmp_path / "w2"),
        "--sample-from",
        f"s3://buk/{manifest}",
        "--cap-shard-points",
        "1",
        "--cap-query-denominator",
        "2",
        "--cap-fractions",
        "0.5",
    )
    assert (
        loaded.returncode == 0
    ), f"load run failed:\n{loaded.stdout[-2500:]}{loaded.stderr[-2500:]}"
    assert "verified" in loaded.stdout
    assert "no corpus pass run" in loaded.stdout

    import json

    payload = json.loads((tmp_path / "o2" / "cap-measurement.json").read_text())
    assert payload["corpus_pass_seconds"] is None
    assert payload["sample_source"].endswith("manifest.json")
    assert [c for c in payload["searches"] if "search_wall_seconds" in c], "no cell ran"

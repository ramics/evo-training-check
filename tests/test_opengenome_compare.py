"""Tests for `tools/opengenome_compare.py` — the join driver for A7.4.

The arithmetic lives in `amazebio.reuse` and is tested there. What is tested here is the
plumbing that decides what the arithmetic is given: which archive counts as which side of
Evo 2's claim, that the digest pass reads only the row groups it needs, and that the
report says plainly what each of its numbers does and does not license.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import pathlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "opengenome_compare", _PATH.parent.parent / "tools" / "opengenome_compare.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

from amazebio.contigs import digest_sequence  # noqa: E402
from amazebio.reuse import Cause, Side  # noqa: E402


def write(path: pathlib.Path, rows: list[dict[str, object]]) -> pathlib.Path:
    with gzip.open(path, "wt", encoding="ascii") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


def test_each_archive_is_read_as_the_side_of_the_claim_it_speaks_to(tmp_path) -> None:
    write(
        tmp_path / "contigs-v214-batch1-abc.jsonl.gz",
        [{"assembly": "GCA_1.1", "accession": "A.1", "length": 4, "sha256": "a"}],
    )
    write(
        tmp_path / "contigs-v220_update-abc.jsonl.gz",
        [{"assembly": "GCA_9.1", "accession": "N.1", "length": 4, "sha256": "n"}],
    )
    rows, digests, genomes = tool.load_og2(sorted(tmp_path.glob("contigs-*.jsonl.gz")))
    assert dict(rows) == {"A.1": Side.REUSED, "N.1": Side.ADDED}
    assert digests == {"A.1": "a", "N.1": "n"}
    assert genomes == {"reused": 1, "added": 1}


def test_an_archive_with_no_recorded_side_is_refused(tmp_path) -> None:
    """Guessing would put material added in 220.0 into the reuse, which is the comparison
    flattering the claim it is testing."""
    write(
        tmp_path / "contigs-v999_mystery-abc.jsonl.gz",
        [{"assembly": "GCA_1.1", "accession": "A.1", "length": 4, "sha256": "a"}],
    )
    with pytest.raises(SystemExit, match="no side is recorded"):
        tool.load_og2(sorted(tmp_path.glob("contigs-*.jsonl.gz")))


def test_the_v1_index_keeps_where_each_record_sits(tmp_path) -> None:
    path = write(
        tmp_path / "v1-contigs.jsonl.gz",
        [{"accession": "A.1", "shard": "gtdb_train_shard_3", "row_group": 17}],
    )
    assert tool.load_v1(path) == {"A.1": ("gtdb_train_shard_3", 17)}


class FakeClient:
    """Serves one Parquet object by range and counts what it was asked for."""

    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.served = 0

    def head_object(self, **kw: object) -> dict[str, int]:
        return {"ContentLength": len(self.blob)}

    def get_object(self, **kw: object) -> dict[str, object]:
        start, _, end = str(kw["Range"]).removeprefix("bytes=").partition("-")
        chunk = self.blob[int(start) : int(end) + 1]
        self.served += len(chunk)
        return {"Body": io.BytesIO(chunk)}


def _parquet(records: list[str]) -> bytes:
    table = pa.table({"record": records, "text": [f"ACGT{name}" for name in records]})
    buffer = io.BytesIO()
    pq.write_table(table, buffer, row_group_size=2)
    return buffer.getvalue()


def test_the_digest_pass_reads_only_the_row_groups_that_hold_a_disputed_record() -> None:
    """The reason the index records a row group at all: the alternative is reading a
    118.5 GiB column to settle a question most of its rows are not party to."""
    names = [f"R{i}.1" for i in range(10)]
    client = FakeClient(_parquet(names))
    out = tool.digest_v1(client, {"R6.1": ("shard", 3)}, verbose=False)
    assert out == {"R6.1": digest_sequence(["ACGTR6.1"])[0]}


def test_the_digest_is_the_one_the_other_side_computed() -> None:
    """Both sides go through `amazebio.contigs`, so a mismatch is the data, not the reader."""
    client = FakeClient(_parquet(["X.1", "Y.1"]))
    out = tool.digest_v1(client, {"X.1": ("shard", 0)}, verbose=False)
    assert out["X.1"] == digest_sequence(["acgtx.1"])[0]


def test_the_report_carries_every_cause_and_what_each_one_means() -> None:
    from amazebio import reuse

    result = reuse.join(["A.1", "B.1"], [("A.1", Side.REUSED), ("N.1", Side.ADDED)])
    found = reuse.classify(
        result, og2_digests={"A.1": "a", "N.1": "n"}, v1_digests={"A.1": "a", "B.1": "b"}
    )
    document = tool.report(result, found, genomes={"reused": 1, "added": 1})
    assert set(document["discrepancies_by_cause"]) == {c.value for c in Cause}
    assert set(document["cause_meaning"]) == {c.value for c in Cause}
    assert document["reused_coverage"]["low"] < document["reused_coverage"]["estimate"]
    assert document["added_difference"] == 1 - tool.STATED_ADDED
    assert any("never pooled" in line for line in document["reading_this_file"])


def test_the_report_counts_the_two_sides_apart() -> None:
    from amazebio import reuse

    result = reuse.join(["A.1"], [("A.1", Side.ADDED)])
    document = tool.report(result, (), genomes={"added": 1})
    assert document["og2_reused_contigs"] == 0
    assert document["shared_with_reused"] == 0
    assert document["og2_added_contigs"] == 1


def test_the_siblings_of_a_disputed_contig_are_the_ones_sharing_its_wgs_project() -> None:
    """D-217. Looking for a contig's residues across all of v1 is a pass over 118.5 GiB
    for a question a few hundred rows answer."""
    v1 = {
        "JAHFAU010000004.1": ("shard_0", 3),
        "JAHFAU010000005.1": ("shard_1", 9),
        "AAAAAA010000001.1": ("shard_0", 1),
    }
    out = tool.sibling_records(v1, ["JAHFAU010000900.1"])
    assert set(out) == {"JAHFAU010000004.1", "JAHFAU010000005.1"}


def test_nothing_is_digested_when_nothing_is_disputed() -> None:
    assert tool.sibling_records({"A010000001.1": ("s", 0)}, []) == {}


def test_a_content_call_says_what_it_was_checked_against() -> None:
    """'not in v1' and 'not in the v1 contigs of this genome' are different claims, and
    a reader of the discrepancy table cannot tell them apart from the cause alone."""
    from amazebio import reuse

    result = reuse.join([], [("N.1", Side.REUSED)])
    found = reuse.classify(
        result,
        og2_digests={"N.1": "n"},
        v1_digests={"S.1": "s"},
        v1_scope="the 158 v1 contigs of WGS project JAHFAU01",
    )
    assert found[0].cause is Cause.CONTENT
    assert "WGS project JAHFAU01" in found[0].evidence


def test_the_report_carries_the_scope_so_the_artefact_does_not_need_the_log() -> None:
    from amazebio import reuse

    result = reuse.join(["A.1"], [("A.1", Side.REUSED)])
    document = tool.report(result, (), genomes={"reused": 1}, v1_digest_scope="a narrow scope")
    assert document["v1_digest_scope"] == "a narrow scope"
    assert any("D-217" in line for line in document["reading_this_file"])

"""Tests for `tools/opengenome_v1_contigs.py` — the v1 side of A7.4's contig comparison.

The point of this tool is that it reads one column of a 118.5 GiB tier, so the test that
matters is that it keeps doing that: a change that pulls `text` along turns a 77 MB read
into a corpus pass and the task's cheap half into another instance.
"""

from __future__ import annotations

import importlib.util
import io
import pathlib

import pyarrow as pa
import pyarrow.parquet as pq

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "opengenome_v1_contigs", _PATH.parent.parent / "tools" / "opengenome_v1_contigs.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def build(records: list[str], *, row_group: int = 2, residues: int = 10) -> bytes:
    """A Parquet file shaped like v1's: a `record` column and a much larger `text` one."""
    table = pa.table(
        {
            "record": records,
            # Distinct per row so the column does not compress away, which is what makes
            # the pruning test measure pruning rather than compression.
            "text": [("ACGT" * residues) + name for name in records],
        },
    )
    buffer = io.BytesIO()
    pq.write_table(table, buffer, row_group_size=row_group)
    return buffer.getvalue()


class FakeClient:
    """Serves one object by range, and counts the bytes it was asked for."""

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


def test_every_row_is_read_with_the_row_group_it_sits_in() -> None:
    client = FakeClient(build(["A.1", "B.1", "C.1", "D.1", "E.1"]))
    rows = tool.read_accessions(client, "b", "k")
    assert [r[0] for r in rows] == ["A.1", "B.1", "C.1", "D.1", "E.1"]
    assert [r[1] for r in rows] == [0, 0, 1, 1, 2]


def test_it_reads_a_fraction_of_the_file_because_it_asks_for_one_column() -> None:
    """The whole reason this half needs no instance. `text` is the bulk of every row."""
    blob = build([f"X{i}.1" for i in range(4000)], row_group=500, residues=1000)
    client = FakeClient(blob)
    tool.read_accessions(client, "b", "k")
    assert (
        client.served < len(blob) // 4
    ), f"read {client.served:,} of {len(blob):,} bytes — the text column is being pulled"


def test_the_split_travels_with_the_accession() -> None:
    assert tool.split_of("gtdb_train_shard_7") == "train"
    assert tool.split_of("gtdb_valid_small") == "valid"
    assert tool.split_of("gtdb_test") == "test"
    assert tool.split_of("something_else") == "unknown"


def test_a_repeated_accession_is_indexed_once_and_reported() -> None:
    """v1's own splits can carry the same contig twice; silently counting it twice would
    make the comparison's denominator disagree with its index."""

    class Multi(FakeClient):
        pass

    client = Multi(build(["A.1", "B.1", "A.1"]))
    document, index = tool.measure(client, "b", ["x/gtdb_test.parquet"], verbose=False)
    assert document["rows"] == 3
    assert document["distinct_accessions"] == 2
    assert document["repeated_accessions"] == 1
    assert document["repeated_examples"] == ["A.1"]
    assert sorted(index) == ["A.1", "B.1"]


def test_the_summary_says_what_it_did_not_read() -> None:
    client = FakeClient(build(["A.1"]))
    document, _ = tool.measure(client, "b", ["x/gtdb_test.parquet"], verbose=False)
    assert any("residues were not read" in line for line in document["reading_this_file"])
    assert document["decisions"] == ["D-119", "D-213"]


def test_shards_are_listed_in_a_stable_order_and_only_parquet() -> None:
    class Lister:
        def list_objects_v2(self, **kw: object) -> dict[str, object]:
            return {
                "Contents": [
                    {"Key": "p/b.parquet"},
                    {"Key": "p/a.parquet"},
                    {"Key": "p/notes.txt"},
                ],
                "IsTruncated": False,
            }

    assert tool.shards(Lister(), "b", "p") == ["p/a.parquet", "p/b.parquet"]

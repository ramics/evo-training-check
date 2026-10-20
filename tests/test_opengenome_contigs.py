"""Tests for `tools/opengenome_contigs.py` — A7.4's contig enumeration.

The pass runs for about an hour on an instance that cannot be inspected while it runs, so
everything checkable about it is checked here: that a member is read as the assembly it is
named for, that a member which is not a genome is counted rather than dropped silently,
that the heartbeat carries work done rather than only a clock, and that a truncated run
cannot publish.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import pathlib
import tarfile

import pytest

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "opengenome_contigs", _PATH.parent.parent / "tools" / "opengenome_contigs.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def build(members: dict[str, str]) -> bytes:
    """A tar of gzipped FASTA, as the staged archives are laid out."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, text in members.items():
            body = gzip.compress(text.encode()) if name.endswith(".gz") else text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


def scan(blob: bytes, **kw: object) -> tuple[dict[str, object], list[dict[str, object]]]:
    lines: list[str] = []
    summary = tool.scan(io.BytesIO(blob), "v214/batch1.tar", lines.append, **kw)
    return summary, [json.loads(line) for line in lines]


def test_every_contig_of_every_genome_is_written_with_its_assembly() -> None:
    blob = build(
        {
            "batch1/GCA_1.1.fasta.gz": ">A.1 one\nACGT\n>B.1\nGG\n",
            "batch1/GCF_2.1.fasta.gz": ">C.1\nTTTT\n",
        }
    )
    summary, rows = scan(blob)
    assert summary["genomes"] == 2
    assert summary["contigs"] == 3
    assert summary["residues"] == 10
    assert [r["assembly"] for r in rows] == ["GCA_1.1", "GCA_1.1", "GCF_2.1"]
    assert [r["accession"] for r in rows] == ["A.1", "B.1", "C.1"]


def test_the_digest_is_the_one_the_other_side_will_compute() -> None:
    """Both sides go through `amazebio.contigs`, so a mismatch is the data and not the
    reader. Asserted here because the comparison's whole value rests on it."""
    from amazebio.contigs import digest_sequence

    _, rows = scan(build({"batch1/GCA_1.1.fasta.gz": ">A.1\nac\ngt\n"}))
    assert rows[0]["sha256"] == digest_sequence(["ACGT"])[0]
    assert rows[0]["length"] == 4


def test_a_member_not_named_for_an_assembly_is_counted_and_named() -> None:
    """A change in how the publisher lays the archive out is a finding, not a silent drop."""
    blob = build({"batch1/README.txt": "notes\n", "batch1/GCA_1.1.fasta.gz": ">A.1\nAC\n"})
    summary, rows = scan(blob)
    assert summary["genomes"] == 1
    assert summary["unplaceable_members"] == 1
    assert summary["unplaceable_examples"] == ["batch1/README.txt"]
    assert len(rows) == 1


def test_the_side_of_the_claim_travels_with_the_counts() -> None:
    assert tool.ARCHIVES["v214/batch1.tar"] == "reused"
    assert tool.ARCHIVES["v220_update.tar"] == "added"
    summary, _ = scan(build({"batch1/GCA_1.1.fasta.gz": ">A.1\nAC\n"}))
    assert summary["side"] == "reused"


def test_a_repeated_accession_within_one_genome_is_refused() -> None:
    from amazebio.contigs import ContigError

    with pytest.raises(ContigError, match="appears twice"):
        scan(build({"batch1/GCA_1.1.fasta.gz": ">A.1\nAC\n>A.1\nGT\n"}))


def test_the_limit_stops_the_pass_at_a_whole_genome() -> None:
    blob = build({f"batch1/GCA_{i}.1.fasta.gz": f">X{i}.1\nACGT\n" for i in range(5)})
    summary, rows = scan(blob, limit=2)
    assert summary["genomes"] == 2
    assert len(rows) == 2


class FakeClient:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(self, **kw: object) -> None:
        self.puts.append(kw)


def test_the_heartbeat_carries_work_done_not_only_a_clock() -> None:
    """D-192: a `written_at` that advances says the heartbeat thread is alive and nothing
    about whether the pass is. The contig count is what distinguishes the two."""
    client = FakeClient()
    beat = tool.Heartbeat(client, "b", "k", every=0.0)
    blob = build({f"batch1/GCA_{i}.1.fasta.gz": f">X{i}.1\nACGT\n" for i in range(3)})
    scan(blob, heartbeat=beat)
    assert len(client.puts) == 3
    bodies = [json.loads(p["Body"]) for p in client.puts]
    assert [b["contigs"] for b in bodies] == [1, 2, 3]
    assert all(b["written_at"] for b in bodies)


def test_a_failing_heartbeat_does_not_end_the_pass() -> None:
    class Broken:
        def put_object(self, **kw: object) -> None:
            raise RuntimeError("no")

    beat = tool.Heartbeat(Broken(), "b", "k", every=0.0)
    summary, _ = scan(build({"batch1/GCA_1.1.fasta.gz": ">A.1\nAC\n"}), heartbeat=beat)
    assert summary["genomes"] == 1


def test_a_truncated_run_cannot_publish() -> None:
    """The corpus bucket has no DeleteObject, so a partial table under a commit's key is
    permanent and reads exactly like a complete one."""
    with pytest.raises(SystemExit, match="may not publish"):
        tool.main(["--archive", "v214/batch1.tar", "--limit", "3", "--upload-results"])


def test_the_slug_is_usable_as_a_file_name_and_an_object_key() -> None:
    assert tool.slug("v214/batch1.tar") == "v214-batch1"
    assert tool.slug("v220_update.tar") == "v220_update"


def test_the_staged_prefix_matches_the_genome_half() -> None:
    """The two halves of one comparison cannot read different prefixes."""
    other = importlib.util.spec_from_file_location(
        "opengenome_reuse", _PATH.parent.parent / "tools" / "opengenome_reuse.py"
    )
    assert other and other.loader
    reuse = importlib.util.module_from_spec(other)
    other.loader.exec_module(reuse)
    assert tool.PREFIX == reuse.PREFIX
    assert tool.ARCHIVES == reuse.ARCHIVES

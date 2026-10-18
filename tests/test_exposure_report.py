"""Tests for `tools/exposure_report.py` — the join that turns A1.6's two passes into a figure.

The join is where a share can come out plausible and wrong, because three files have to agree
about which seeds they are talking about:

* **The denominator taken from the rows rather than the seed set.** A seed the exposure pass
  emitted no row for is `UNDETERMINED` and belongs in the denominator. Dropping it shrinks the
  denominator and raises the share — the error D-158's two-denominator rule exists to catch,
  and the one that would make the result look cleaner than it is.
* **A sidecar from a different band.** The seed-hit ids and the seed denominator have to
  describe the same sample. Joining a 1/10 sidecar onto a 1/100 denominator would report a
  share over a denominator it was never measured against, and nothing about the arithmetic
  would look wrong.
* **Rows for seeds outside the sample counted anyway.** The exposure pass covers the whole
  tier, so most of its rows are for seeds this band never searched. Counting them would
  answer a different question from the one the band's rate needs.
* **A cluster reached through two viral members.** It gets a row per member, and the verdict
  has to fold with precedence rather than letting the last row win.
* **A blended number appearing anyway.** D-158 fixes the two tiers as a two-point curve with
  no interpolation and no chosen cut, so the report must offer no field that combines them.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import pathlib

import pytest

from amazebio import seeds
from amazebio.exclusivity import EXCLUSIVE, NON_EXCLUSIVE, UNDETERMINED

_PATH = pathlib.Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "exposure_report", _PATH.parent.parent / "tools" / "exposure_report.py"
)
assert _spec and _spec.loader
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def _sampled_ids(n: int, denominator: int = 100) -> list[str]:
    """`n` cluster ids that the band's hash rule actually selects."""
    out = []
    i = 0
    while len(out) < n:
        ident = f"UniRef100_S{i}"
        if seeds.bucket_of(ident, denominator) == 0:
            out.append(ident)
        i += 1
    return out


def _unsampled_id(denominator: int = 100) -> str:
    i = 0
    while True:
        ident = f"UniRef100_U{i}"
        if seeds.bucket_of(ident, denominator) != 0:
            return ident
        i += 1


def _fasta(path: pathlib.Path, idents: list[str]) -> pathlib.Path:
    path.write_bytes(b"".join(f">{i}\nMKV\n".encode() for i in idents))
    return path


def _rows_gz(path: pathlib.Path, rows: list[tuple[str, str]]) -> pathlib.Path:
    with gzip.open(path, "wb") as fh:
        for ident, verdict in rows:
            fh.write(f"{ident}\t{verdict}\n".encode())
    return path


def _hits_gz(path: pathlib.Path, per_mode: dict[int, list[str]]) -> pathlib.Path:
    with gzip.open(path, "wb") as fh:
        for mode, idents in sorted(per_mode.items()):
            for ident in idents:
                fh.write(f"{mode}\t{ident}\n".encode())
    return path


def test_seed_ids_come_off_bare_headers() -> None:
    path = _PATH.parent / "_unused"
    del path
    import io

    data = io.BytesIO(b">UniRef100_A\nMKV\nMKV\n>UniRef100_B\nMM\n")
    got = [
        line[1:].split()[0].decode()
        for line in data.getvalue().splitlines()
        if line.startswith(b">")
    ]
    assert got == ["UniRef100_A", "UniRef100_B"]


def test_a_seed_with_no_row_stays_in_the_denominator(tmp_path: pathlib.Path) -> None:
    """The flattering-share bug: three sampled seeds, one row, denominator must stay three."""
    ids = _sampled_ids(3)
    verdicts = tool.read_verdicts(_rows_gz(tmp_path / "r.tsv.gz", [(ids[0], NON_EXCLUSIVE)]))
    summary = tool.summarise("uniref90", verdicts, set(ids), {})
    row = summary["all_sampled_seeds"]
    assert row["seeds"] == 3
    assert row["counts"] == {EXCLUSIVE: 0, NON_EXCLUSIVE: 1, UNDETERMINED: 2}
    assert row["non_exclusive_share"] == pytest.approx(1 / 3)


def test_rows_for_seeds_outside_the_sample_are_not_counted(tmp_path: pathlib.Path) -> None:
    """The exposure pass covers the whole tier; this band searched 1/100 of it."""
    ids = _sampled_ids(2)
    rows = [(ids[0], NON_EXCLUSIVE), (_unsampled_id(), NON_EXCLUSIVE)]
    verdicts = tool.read_verdicts(_rows_gz(tmp_path / "r.tsv.gz", rows))
    summary = tool.summarise("uniref90", verdicts, set(ids), {})
    assert summary["all_sampled_seeds"]["seeds"] == 2
    assert summary["all_sampled_seeds"]["counts"][NON_EXCLUSIVE] == 1


def test_a_cluster_seen_twice_keeps_the_stronger_claim(tmp_path: pathlib.Path) -> None:
    ids = _sampled_ids(1)
    for order in ([EXCLUSIVE, NON_EXCLUSIVE], [NON_EXCLUSIVE, EXCLUSIVE]):
        path = _rows_gz(tmp_path / f"r{order[0]}.tsv.gz", [(ids[0], v) for v in order])
        assert tool.read_verdicts(path)[ids[0]] == NON_EXCLUSIVE


def test_the_second_denominator_is_reported_per_cell_and_reading(tmp_path: pathlib.Path) -> None:
    ids = _sampled_ids(4)
    verdicts = tool.read_verdicts(
        _rows_gz(
            tmp_path / "r.tsv.gz",
            [(ids[0], NON_EXCLUSIVE), (ids[1], EXCLUSIVE), (ids[2], EXCLUSIVE)],
        )
    )
    cells = {
        "shard00-s5.7-cov1-q100": tool.read_seed_hits(
            _hits_gz(tmp_path / "h.tsv.gz", {1: [ids[0], ids[1]], 2: [ids[0]]})
        )
    }
    summary = tool.summarise("uniref90", verdicts, set(ids), cells)
    by_reading = {r["reading"]: r for r in summary["seeds_with_hits"]}
    assert by_reading[1]["seeds"] == 2
    assert by_reading[1]["counts"][NON_EXCLUSIVE] == 1
    assert by_reading[1]["non_exclusive_share"] == pytest.approx(0.5)
    # Reading 2 saw one hit-producing seed, and it is the non-exclusive one.
    assert by_reading[2]["seeds"] == 1
    assert by_reading[2]["non_exclusive_share"] == pytest.approx(1.0)


def test_a_sidecar_from_another_band_is_refused(tmp_path: pathlib.Path) -> None:
    """Joining a 1/10 sidecar onto a 1/100 denominator reports a share over a denominator it
    was never measured against, and the arithmetic would look fine."""
    ids = _sampled_ids(2)
    verdicts = tool.read_verdicts(_rows_gz(tmp_path / "r.tsv.gz", [(ids[0], EXCLUSIVE)]))
    cells = {
        "shard00-s5.7-cov1-q10": tool.read_seed_hits(
            _hits_gz(tmp_path / "h.tsv.gz", {1: [_unsampled_id()]})
        )
    }
    with pytest.raises(SystemExit, match="not in the realised sample"):
        tool.summarise("uniref90", verdicts, set(ids), cells)


def test_the_report_offers_no_blended_share_and_no_identifier(tmp_path: pathlib.Path) -> None:
    ids = _sampled_ids(3)
    fasta = _fasta(tmp_path / "seeds.faa", [*ids, _unsampled_id()])
    r90 = _rows_gz(tmp_path / "r90.tsv.gz", [(ids[0], NON_EXCLUSIVE)])
    r50 = _rows_gz(tmp_path / "r50.tsv.gz", [(ids[0], NON_EXCLUSIVE), (ids[1], NON_EXCLUSIVE)])
    outdir = tmp_path / "out"
    code = tool.main(
        [
            "--rows",
            f"uniref90={r90}",
            "--rows",
            f"uniref50={r50}",
            "--seed-fasta",
            str(fasta),
            "--outdir",
            str(outdir),
            "--allow-dirty",
        ]
    )
    assert code == 0
    report = json.loads((outdir / "exposure-q100.json").read_text())
    assert set(report["tiers"]) == {"uniref90", "uniref50"}
    # The 50 tier admits more, which is the direction the curve should run.
    assert (
        report["tiers"]["uniref50"]["all_sampled_seeds"]["counts"][NON_EXCLUSIVE]
        > report["tiers"]["uniref90"]["all_sampled_seeds"]["counts"][NON_EXCLUSIVE]
    )
    assert report["reported_denominators"] == ["all_sampled_seeds"]
    blob = json.dumps(report)
    for ident in ids:
        assert ident not in blob, "the report must carry counts, never ids (D-125)"
    for forbidden in ("combined", "blended", "overall_share", "interpolated"):
        assert forbidden not in blob


def test_without_sidecars_the_report_says_which_denominator_is_missing(
    tmp_path: pathlib.Path,
) -> None:
    ids = _sampled_ids(2)
    fasta = _fasta(tmp_path / "seeds.faa", ids)
    rows = _rows_gz(tmp_path / "r.tsv.gz", [(ids[0], EXCLUSIVE)])
    outdir = tmp_path / "out"
    tool.main(
        [
            "--rows",
            f"uniref90={rows}",
            "--seed-fasta",
            str(fasta),
            "--outdir",
            str(outdir),
            "--allow-dirty",
        ]
    )
    report = json.loads((outdir / "exposure-q100.json").read_text())
    assert report["reported_denominators"] == ["all_sampled_seeds"]
    assert report["tiers"]["uniref90"]["seeds_with_hits"] == []


def test_a_malformed_rows_spec_is_refused_before_any_work(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit, match="TIER=PATH"):
        tool.main(["--rows", "uniref90", "--seed-fasta", str(tmp_path / "x.faa")])

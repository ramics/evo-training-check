"""Tests for `amazebio.exclusivity` — A1.6's clause-(b) exposure measurement (D-157).

The pass asks one question per seed — does the cluster containing it, at 90% and at 50%
identity, hold a non-viral member — and every way it can come out plausible and wrong is a
way of counting the wrong taxids or the wrong ids:

* **`common taxon ID` read as a member's taxid.** Every entry carries one and it names the
  lowest common ancestor, not a member. Counting it would turn an all-viral cluster
  non-exclusive the moment its common ancestor resolved above Viruses — which is exactly the
  direction that would manufacture the finding this measurement exists to test.
* **The representative skipped.** `member count` includes the representative, so a cluster
  reporting 2 has one `<member>`. A seed reached only through the representative is a seed
  the pass has to find, and skipping it would silently shrink the set under measurement.
* **`UniRef90 ID` or `UniRef50 ID` matched in place of `UniRef100 ID`.** Both tiers carry
  two of the three, so an id pattern not anchored on the property type picks up whichever
  appears first and the join lands on the wrong cluster — producing a verdict for a seed
  that was never asked about.
* **A seed with no row dropped from the denominator.** Dropping it rather than counting it
  `UNDETERMINED` shrinks the denominator and flatters the share, which is the error D-157's
  two-denominator rule exists to prevent.
* **A tie broken by stream order.** A seed reachable through two viral members must get the
  same verdict whichever is read first, or the result depends on the scheduler.
* **An entry split across a chunk boundary.** The pass streams 93 GB in chunks, so entries
  straddling one are the normal case; losing them loses a share of the measurement that no
  later count would reveal.
"""

from __future__ import annotations

from amazebio.exclusivity import (
    EXCLUSIVE,
    NON_EXCLUSIVE,
    UNDETERMINED,
    ExclusivityConfig,
    ExclusivityCounts,
    ExclusivityResult,
    Tally,
    cluster_rows,
    iter_member_blocks,
)
from amazebio.seeds import iter_entry_blocks, scan_parallel

#: Tobacco mosaic virus and Escherichia coli stand in for "viral" and "not"; only membership
#: of the set handed to the pass matters, so no taxonomy walk is needed here.
VIRAL = frozenset({12242, 10239})
CELLULAR = 562


def member(
    uniref100: str,
    taxid: int | None,
    *,
    representative: bool = False,
    extra_tier: str = "UniRef50",
) -> str:
    """One member block, shaped like the staged bytes: a tier id, then the taxonomy.

    `extra_tier` writes the *other* tier's cross-reference before the UniRef100 one, which
    is the ordering that catches an unanchored id pattern.
    """
    tag = "representativeMember" if representative else "member"
    taxon = f'<property type="NCBI taxonomy" value="{taxid}"/>' if taxid is not None else ""
    return (
        f"<{tag}>\n"
        f'<dbReference type="UniProtKB ID" id="SOME_ID">\n'
        f'<property type="UniProtKB accession" value="A00000"/>\n'
        f'<property type="{extra_tier} ID" value="{extra_tier}_WRONG"/>\n'
        f'<property type="UniRef100 ID" value="{uniref100}"/>\n'
        f"{taxon}\n"
        f'<property type="length" value="100"/>\n'
        f"</dbReference>\n"
        f"</{tag}>\n"
    )


def entry(cluster_id: str, members: str, *, common_taxon: int = 10239) -> bytes:
    """One cluster block, with the entry-level `common taxon ID` the real bytes carry."""
    return (
        f'<entry id="{cluster_id}" updated="2023-01-01">\n'
        f"<name>Cluster: something</name>\n"
        f'<property type="member count" value="2"/>\n'
        f'<property type="common taxon ID" value="{common_taxon}"/>\n'
        f"{members}"
    ).encode()


def test_common_taxon_id_is_not_counted_as_a_member() -> None:
    """An all-cellular cluster under a viral common ancestor must stay viral-free.

    The entry-level property sits before the first `<dbReference`, so the member split has
    to drop that leading piece. If it did not, this cluster would report a viral member and
    emit a verdict about a seed that does not exist.
    """
    block = entry(
        "UniRef90_X",
        member("UniRef100_A", CELLULAR, representative=True) + member("UniRef100_B", CELLULAR),
        common_taxon=10239,
    )
    reduced = cluster_rows(block, VIRAL)
    assert reduced is not None
    assert reduced.verdict is None
    assert reduced.viral_ids == ()
    assert reduced.placed == 2


def test_leading_piece_is_dropped_by_the_member_split() -> None:
    block = entry("UniRef90_X", member("UniRef100_A", 12242, representative=True))
    pieces = iter_member_blocks(block)
    assert len(pieces) == 1
    assert b"common taxon" not in pieces[0]


def test_representative_is_a_member_for_this_purpose() -> None:
    """A seed reachable only through the representative is still reached."""
    block = entry("UniRef90_X", member("UniRef100_V", 12242, representative=True))
    reduced = cluster_rows(block, VIRAL)
    assert reduced is not None
    assert reduced.verdict == EXCLUSIVE
    assert reduced.viral_ids == ("UniRef100_V",)


def test_uniref100_id_is_matched_on_its_property_type() -> None:
    """The other tier's id appears first in the block and must not be picked up."""
    for other in ("UniRef50", "UniRef90"):
        block = entry(
            "UniRef90_X",
            member("UniRef100_V", 12242, representative=True, extra_tier=other),
        )
        reduced = cluster_rows(block, VIRAL)
        assert reduced is not None
        assert reduced.viral_ids == ("UniRef100_V",)


def test_a_cellular_member_makes_the_cluster_non_exclusive() -> None:
    block = entry(
        "UniRef90_X",
        member("UniRef100_V", 12242, representative=True) + member("UniRef100_C", CELLULAR),
    )
    reduced = cluster_rows(block, VIRAL)
    assert reduced is not None
    assert reduced.verdict == NON_EXCLUSIVE
    assert reduced.viral_ids == ("UniRef100_V",)


def test_an_unplaced_member_neither_helps_nor_hurts() -> None:
    """A member with no taxid cannot make a cluster non-exclusive, and is not an unknown."""
    block = entry(
        "UniRef90_X",
        member("UniRef100_V", 12242, representative=True) + member("UniRef100_U", None),
    )
    reduced = cluster_rows(block, VIRAL)
    assert reduced is not None
    assert reduced.verdict == EXCLUSIVE
    assert reduced.placed == 1


def test_a_wholly_unplaced_cluster_is_counted_as_such() -> None:
    """No placed taxid means no verdict about any seed, but the cluster is still counted."""
    block = entry("UniRef90_X", member("UniRef100_U", None, representative=True))
    reduced = cluster_rows(block, VIRAL)
    assert reduced is not None
    assert reduced.placed == 0
    assert reduced.verdict is None

    counts = ExclusivityCounts()
    counts.observe(reduced)
    assert counts.to_dict()["unplaced_clusters"] == 1
    assert counts.to_dict()["viral_covering"] == 0


def test_a_block_that_is_not_an_entry_reduces_to_nothing() -> None:
    assert cluster_rows(b"<UniRef90 releaseDate='2023-05-03'>", VIRAL) is None


def test_tally_counts_an_unseen_seed_as_undetermined() -> None:
    """The denominator is the seed set, not the rows — dropping a seed flatters the share."""
    tally = Tally(name="sample", tier="uniref90")
    tally.observe("UniRef100_V", EXCLUSIVE)
    summary = tally.summarise(["UniRef100_V", "UniRef100_MISSING"])
    assert summary["seeds"] == 2
    assert summary["counts"] == {EXCLUSIVE: 1, NON_EXCLUSIVE: 0, UNDETERMINED: 1}
    assert summary["undetermined_share"] == 0.5
    assert summary["non_exclusive_share"] == 0.0


def test_tally_precedence_does_not_depend_on_order() -> None:
    """A seed reached twice gets the stronger claim, whichever row arrives first."""
    forward = Tally(name="s", tier="t")
    forward.observe("UniRef100_V", EXCLUSIVE)
    forward.observe("UniRef100_V", NON_EXCLUSIVE)

    backward = Tally(name="s", tier="t")
    backward.observe("UniRef100_V", NON_EXCLUSIVE)
    backward.observe("UniRef100_V", EXCLUSIVE)

    assert forward.verdicts == backward.verdicts == {"UniRef100_V": NON_EXCLUSIVE}


def test_undetermined_never_displaces_a_real_verdict() -> None:
    tally = Tally(name="s", tier="t")
    tally.observe("UniRef100_V", EXCLUSIVE)
    tally.observe("UniRef100_V", UNDETERMINED)
    assert tally.verdicts["UniRef100_V"] == EXCLUSIVE


def _stream(blocks: list[bytes], chunk: int) -> list[bytes]:
    """Re-cut a concatenated stream into fixed-size chunks, boundaries wherever they fall."""
    joined = b"</entry>\n".join(blocks) + b"</entry>\n"
    return [joined[i : i + chunk] for i in range(0, len(joined), chunk)]


def test_entries_split_across_chunks_are_not_lost() -> None:
    blocks = [
        entry("UniRef90_1", member("UniRef100_V1", 12242, representative=True)),
        entry(
            "UniRef90_2",
            member("UniRef100_V2", 12242, representative=True) + member("UniRef100_C", CELLULAR),
        ),
        entry("UniRef90_3", member("UniRef100_C2", CELLULAR, representative=True)),
    ]
    config = ExclusivityConfig(viral=VIRAL)

    whole = ExclusivityResult()
    for batch in iter_entry_blocks(_stream(blocks, 1 << 20)):
        result = config.scan(batch)
        whole.counts.merge(result.counts)
        whole.rows.extend(result.rows)
    assert whole.counts.clusters == 3
    assert dict(whole.rows) == {"UniRef100_V1": EXCLUSIVE, "UniRef100_V2": NON_EXCLUSIVE}

    # One byte at a time puts a boundary inside every tag in the file.
    rows: list[tuple[str, str]] = []
    clusters = 0
    for batch in iter_entry_blocks(_stream(blocks, 1), batch_bytes=1):
        result = config.scan(batch)
        rows.extend(result.rows)
        clusters += result.counts.clusters
    assert clusters == 3
    assert dict(rows) == {"UniRef100_V1": EXCLUSIVE, "UniRef100_V2": NON_EXCLUSIVE}


def test_parallel_path_agrees_with_the_serial_one_and_keeps_order() -> None:
    """`scan_parallel` drives this config too — that is why it is a protocol (D-157)."""
    blocks = [
        entry(f"UniRef90_{i}", member(f"UniRef100_V{i}", 12242, representative=True))
        for i in range(40)
    ]
    chunks = _stream(blocks, 512)
    config = ExclusivityConfig(viral=VIRAL)

    serial: list[tuple[str, str]] = []
    for batch in iter_entry_blocks(chunks, batch_bytes=1024):
        serial.extend(config.scan(batch).rows)

    parallel: list[tuple[str, str]] = []
    total = ExclusivityCounts()
    for result in scan_parallel(
        _stream(blocks, 512), config, workers=3, batch_bytes=1024, max_in_flight=2
    ):
        parallel.extend(result.rows)
        total.merge(result.counts)

    assert parallel == serial
    assert total.clusters == 40
    assert total.exclusive == 40

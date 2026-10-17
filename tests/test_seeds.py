"""Tests for `amazebio.seeds` — task A1.6's seed-set reconstruction.

Rebuilding a denylist nobody published is mostly a parsing job, so what needs pinning is
the set of ways it can come out plausible and wrong:

* **The sequence taken from the wrong element.** `<sequence>` appears inside
  `<representativeMember>`, and a member block can carry its own properties. Reading the
  first sequence anywhere in the entry works until an entry orders its children
  differently, and then the seed set holds sequences attributed to the wrong cluster.
* **`common taxon ID` read as a member's taxid.** Every UniRef entry carries one, and it
  names the lowest common ancestor rather than any member. Counting it would make a cluster
  of cellular proteins viral whenever its common ancestor happens to sit under Viruses, and
  would quietly inflate the seed set.
* **Viral membership tested on the representative alone.** 2.38% of viral-seeded clusters in
  the measured sample have a non-viral representative. Testing the representative would drop
  them, and dropping them makes the filter look like it reaches less than it does — an error
  in the audit's favour, which §2's commitment treats as the same failure as the opposite.
* **An entry split across a chunk boundary.** The pass streams a 400 GB file in chunks, so
  an entry straddling two of them is the normal case, not an edge case. Losing those loses a
  share of the seed set that no later count would reveal.
* **Descent computed by climbing.** Testing three million taxids by walking each one to the
  root is correct and slow enough to change how the pass is run; the children walk has to
  produce the same set, including for a root that is its own parent.
* **Whitespace left in a sequence.** UniRef wraps sequence lines. A seed carrying newlines
  is silently a different sequence to the aligner.
"""

from __future__ import annotations

import io
import zipfile

from amazebio.seeds import (
    VIRAL_ROOT,
    SeedCounts,
    Taxonomy,
    UniRefEntry,
    iter_entries,
    write_fasta,
)

NODES = "\n".join(
    [
        "1\t|\t1\t|\tno rank\t|",
        "10239\t|\t1\t|\tsuperkingdom\t|",
        "11157\t|\t10239\t|\tfamily\t|",
        "11158\t|\t11157\t|\tgenus\t|",
        "2\t|\t1\t|\tsuperkingdom\t|",
        "1280\t|\t2\t|\tspecies\t|",
    ]
)


def _taxonomy() -> Taxonomy:
    return Taxonomy.from_nodes_dmp(NODES.splitlines())


def test_descendants_walks_down_and_terminates_at_a_self_parented_root() -> None:
    tax = _taxonomy()
    assert tax.descendants(VIRAL_ROOT) == {10239, 11157, 11158}
    # taxid 1 is its own parent in nodes.dmp; the walk must not loop on it.
    assert tax.descendants(1) == {1, 2, 10239, 11157, 11158, 1280}


def test_descendants_matches_climbing_to_the_root() -> None:
    """The fast walk and the obvious slow one must agree."""
    tax = _taxonomy()
    walked = tax.descendants(VIRAL_ROOT)

    def climbs_to(taxid: int, root: int) -> bool:
        seen = set()
        node = taxid
        while node not in seen:
            if node == root:
                return True
            seen.add(node)
            parent = tax.parent.get(node)
            if parent is None or parent == node:
                return False
            node = parent
        return False

    climbed = {t for t in tax.parent if climbs_to(t, VIRAL_ROOT)}
    assert walked == climbed


def test_taxonomy_reads_nodes_dmp_out_of_a_dated_zip() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("nodes.dmp", NODES)
        archive.writestr("names.dmp", "ignored")
    buf.seek(0)
    assert Taxonomy.from_taxdump_zip(buf).descendants(VIRAL_ROOT) == {10239, 11157, 11158}


ENTRY = b"""<entry id="UniRef100_X1" updated="2023-01-01">
<property type="member count" value="2"/>
<property type="common taxon ID" value="11157"/>
<representativeMember>
  <dbReference type="UniProtKB ID" id="REP_X1">
    <property type="NCBI taxonomy" value="1280"/>
    <property type="length" value="8"/>
  </dbReference>
  <sequence length="8" checksum="AAAA">MKVL
AAAA</sequence>
</representativeMember>
<member>
  <dbReference type="UniProtKB ID" id="MEM_X1">
    <property type="NCBI taxonomy" value="11158"/>
    <property type="length" value="6"/>
  </dbReference>
</member>
</entry>"""


def test_entry_parsing_takes_the_representative_sequence_and_every_member_taxid() -> None:
    (entry,) = list(iter_entries([ENTRY]))
    assert entry.cluster_id == "UniRef100_X1"
    assert entry.sequence == "MKVLAAAA"  # newline inside the sequence is stripped
    assert entry.representative_taxid == 1280
    assert entry.member_taxids == (1280, 11158)


def test_common_taxon_id_is_not_counted_as_a_member_taxid() -> None:
    """11157 appears only as the common taxon, and must not reach member_taxids."""
    (entry,) = list(iter_entries([ENTRY]))
    assert 11157 not in entry.member_taxids


def test_a_cluster_is_viral_seeded_through_a_member_whose_representative_is_not() -> None:
    viral = _taxonomy().descendants(VIRAL_ROOT)
    (entry,) = list(iter_entries([ENTRY]))
    assert entry.is_viral_seeded(viral) is True
    assert entry.representative_is_viral(viral) is False
    assert entry.is_mixed(viral) is True


def test_entries_split_across_chunk_boundaries_are_recovered() -> None:
    stream = ENTRY + ENTRY.replace(b"X1", b"X2")
    for cut in (1, 7, 40, 160, len(ENTRY) - 1, len(ENTRY) + 3):
        chunks = [stream[i : i + cut] for i in range(0, len(stream), cut)]
        ids = [e.cluster_id for e in iter_entries(chunks)]
        assert ids == ["UniRef100_X1", "UniRef100_X2"], f"lost an entry at chunk size {cut}"


def test_blocks_without_a_representative_sequence_are_skipped() -> None:
    assert list(iter_entries([b'<entry id="UniRef100_Y"></entry>'])) == []
    empty = b'<entry id="UniRef100_Z"><representativeMember>' b"</representativeMember></entry>"
    assert list(iter_entries([empty])) == []


def test_write_fasta_emits_a_bare_identifier_header() -> None:
    out = io.BytesIO()
    assert write_fasta(out, "UniRef100_X1", "MKVL") == 4
    assert out.getvalue() == b">UniRef100_X1\nMKVL\n"


def test_seed_counts_separate_the_representative_gap_from_the_seed_count() -> None:
    viral = _taxonomy().descendants(VIRAL_ROOT)
    counts = SeedCounts()
    # viral through a member only, representative cellular
    assert counts.observe(next(iter(iter_entries([ENTRY]))), viral) is True
    # wholly cellular
    cellular = ENTRY.replace(b'value="11158"', b'value="1280"').replace(b"X1", b"X3")
    assert counts.observe(next(iter(iter_entries([cellular]))), viral) is False
    out = counts.to_dict()
    assert out["clusters"] == 2
    assert out["viral_seeded"] == 1
    assert out["representative_not_viral"] == 1
    assert out["mixed"] == 1
    assert out["viral_share"] == 0.5
    assert out["representative_not_viral_share"] == 1.0


def test_seed_counts_report_none_rather_than_dividing_by_zero() -> None:
    out = SeedCounts().to_dict()
    assert out["viral_share"] is None
    assert out["representative_not_viral_share"] is None
    assert out["mixed_share"] is None


def test_an_entry_with_no_taxids_at_all_is_not_viral() -> None:
    bare = b"""<entry id="UniRef100_W"><representativeMember>
      <sequence length="3" checksum="B">MKV</sequence>
      </representativeMember></entry>"""
    (entry,) = list(iter_entries([bare]))
    assert entry.member_taxids == ()
    assert entry.representative_taxid is None
    assert entry.is_viral_seeded(set()) is False
    assert entry.is_mixed(set()) is False
    assert UniRefEntry("x", "MKV", None, ()).is_viral_seeded({10239}) is False


# --- the parallel path -------------------------------------------------------------
#
# A faster pass that returns different results is not a faster pass. The risks are
# specific: a batch boundary that swallows an entry, a per-process hash that puts the
# same cluster in different shards in different workers, and results arriving in
# completion order rather than read order, which would make the artefact depend on how
# the scheduler interleaved things.

from amazebio.seeds import (  # noqa: E402
    ScanConfig,
    bucket_of,
    iter_entry_blocks,
    scan_parallel,
)

MANY = b"".join(ENTRY.replace(b"X1", f"X{i:05d}".encode()) for i in range(400))


def _config() -> ScanConfig:
    return ScanConfig(
        viral=frozenset(_taxonomy().descendants(VIRAL_ROOT)), sample_rate=3, buckets=4
    )


def _reduce(results: list) -> tuple:
    counts = SeedCounts()
    seeds_out: list = []
    samples_out: list = []
    for batch in results:
        counts.merge(batch.counts)
        seeds_out.extend(batch.seeds)
        samples_out.extend(batch.samples)
    return counts.to_dict(), seeds_out, samples_out


def test_entry_blocks_cover_every_entry_at_any_batch_size() -> None:
    for batch_bytes in (1, 500, 5000, len(MANY)):
        blocks = [b for batch in iter_entry_blocks([MANY], batch_bytes) for b in batch]
        parsed = [e.cluster_id for b in blocks if (e := _parse_one(b)) is not None]
        assert len(parsed) == 400, f"lost entries at batch size {batch_bytes}"


def _parse_one(block: bytes):
    found = list(iter_entries([block + b"</entry>"]))
    return found[0] if found else None


def test_parallel_matches_serial_exactly() -> None:
    cfg = _config()
    chunks = [MANY[i : i + 777] for i in range(0, len(MANY), 777)]
    serial = _reduce(list(scan_parallel(chunks, cfg, workers=1, batch_bytes=4096)))
    parallel = _reduce(list(scan_parallel(chunks, cfg, workers=4, batch_bytes=4096)))
    assert serial == parallel


def test_parallel_preserves_read_order() -> None:
    """Order is what makes the output byte-identical rather than merely equivalent."""
    cfg = _config()
    chunks = [MANY[i : i + 1024] for i in range(0, len(MANY), 1024)]
    ids = [
        s[0]
        for batch in scan_parallel(chunks, cfg, workers=4, batch_bytes=2048)
        for s in batch.seeds
    ]
    assert ids == sorted(ids, key=lambda cid: int(cid.rsplit("X", 1)[1]))


def test_parallel_is_bounded_in_flight() -> None:
    """A huge stream must not be submitted all at once; memory is the whole reason."""
    cfg = _config()
    chunks = [MANY] * 4
    out = list(scan_parallel(chunks, cfg, workers=2, batch_bytes=512, max_in_flight=3))
    assert sum(b.counts.clusters for b in out) == 1600


def test_sampling_and_shard_hashes_agree_across_processes() -> None:
    """The same cluster must land in the same shard wherever it is parsed."""
    cfg = _config()
    out = list(scan_parallel([MANY], cfg, workers=4, batch_bytes=1024))
    placed: dict[str, int] = {}
    for batch in out:
        for shard, cid, _seq in batch.samples:
            assert placed.setdefault(cid, shard) == shard
            assert shard == bucket_of(cid + "#shard", 4)


def test_counts_merge_is_additive() -> None:
    a, b = SeedCounts(clusters=3, viral_seeded=1), SeedCounts(clusters=4, viral_seeded=2)
    a.merge(b)
    assert (a.clusters, a.viral_seeded) == (7, 3)

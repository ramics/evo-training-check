"""The protein cache in `tools/detect_profiles.py` — task A2.1, D-103.

The cache exists so a deepened sample reads each release once rather than once per band. What is
tested here is the thing that went wrong twice: **keying**. Evo 1 publishes stage 2 as three
splits under one component name, and a cache keyed on the component alone fails in two different
directions — on write the splits overwrite each other, and on read each split loads the whole
component, so the same records are searched once per split and every family's hit count comes
out threefold while its record count stays right. Neither failure is visible in a finished table.

The search itself is not tested here: it is `pyhmmer` against a pinned registry, and the
registry's own behaviour is `test_profiles.py`'s.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "detect_profiles.py"
_spec = importlib.util.spec_from_file_location("detect_profiles_under_test", _PATH)
detect_profiles = importlib.util.module_from_spec(_spec)
sys.modules["detect_profiles_under_test"] = detect_profiles
_spec.loader.exec_module(detect_profiles)

from amazebio.detect import in_band  # noqa: E402  (after the tool, which sets up `src`)
from amazebio.policyspec import Record  # noqa: E402


def protein(name: str, sequence: str = "MKVLAT"):
    from pyhmmer.easel import Alphabet, TextSequence

    return TextSequence(name=name.encode(), sequence=sequence).digitize(Alphabet.amino())


#: `Record.taxonomy` is a **rank -> taxon mapping**, and these fixtures use the real shape
#: deliberately. The first version of them used a tuple because the cache wrote one, so the test
#: agreed with the bug: `list()` of a mapping yields its ranks and drops every taxon, and nothing
#: noticed until a policy rule reached for `.get(rank)` — after a 70-minute search.
TAXONOMY = {"realm": "Duplodnaviria", "class": "Caudoviricetes"}


def records_for(ids: list[str], component: str = "IMG/VR") -> dict[str, Record]:
    return {i: Record(id=i, component=component, taxonomy=dict(TAXONOMY)) for i in ids}


def test_the_stem_separates_splits_that_share_a_component():
    train = detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.014, 0.02)
    test = detect_profiles.cache_stem("stage2", "test_stage2.parquet", 0.014, 0.02)
    assert train != test
    # And the band bound survives: a stem ending `.02` must not lose it to a suffix replacement.
    assert train.endswith("0.014-0.02")


def test_a_split_reads_its_own_cache_and_not_its_siblings(tmp_path):
    # The duplication bug: globbing on the component made each split load all three, so the
    # band's records were searched once per split.
    ids = ["stage2:train#1", "stage2:train#2"]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.0, 1.0),
    )
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "valid_stage2.parquet", 0.0, 1.0),
        [],
        {},
        band=(0.0, 1.0),
    )

    proteins, records, stats = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    assert stats["records"] == 2
    assert stats["genes"] == 2
    assert set(records) == set(ids)

    empty, _, empty_stats = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="valid_stage2.parquet", lo=0.0, hi=1.0
    )
    assert empty == []
    assert empty_stats["genes"] == 0


def test_writing_two_splits_does_not_overwrite_either(tmp_path):
    # The destructive bug: one stem for three splits, and the last write — an empty one — won.
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"]),
        band=(0.0, 1.0),
    )
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "test_stage2.parquet", 0.0, 1.0),
        [],
        {},
        band=(0.0, 1.0),
    )
    proteins, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    assert len(proteins) == 1


def test_band_membership_is_recomputed_rather_than_trusted(tmp_path):
    """A wider cache yields exactly the band asked for — what stops a cache changing a result."""
    ids = [f"IMGVR_{i}" for i in range(600)]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("imgvr", "imgvr.fasta.gz", 0.0, 1.0),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.0, 1.0),
    )
    _, records, stats = detect_profiles.read_cache(
        tmp_path, component="imgvr", object_name="imgvr.fasta.gz", lo=0.1, hi=0.3
    )
    expected = {i for i in ids if in_band(i, seed=detect_profiles.SEED, lo=0.1, hi=0.3)}
    assert set(records) == expected
    assert 0 < stats["records"] < len(ids)


def test_the_cache_carries_what_the_route_resolution_needs(tmp_path):
    # A detection's route comes from the record's component and lineage, so a cache that lost
    # them would make a cached band unroutable — and the taxonomy is metadata, not sequence.
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"], component="IMG/VR"),
        band=(0.0, 1.0),
    )
    _, records, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
    )
    record = records["stage2:train#1"]
    assert record.component == "IMG/VR"
    # The mapping survives the round trip, rank by rank: this is what the taxonomy rules read.
    assert record.taxonomy == TAXONOMY
    assert record.taxonomy.get("realm") == "Duplodnaviria"


def test_no_nucleotide_sequence_is_written(tmp_path):
    # D-103 permits called proteins in scratch; the records sidecar carries accessions, lineage
    # and the band, and must not carry sequence of any kind.
    path = detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0),
        [protein("stage2:train#1|gene0")],
        records_for(["stage2:train#1"]),
        band=(0.0, 1.0),
    )
    sidecar = (path.parent / path.name.replace(".faa.gz", ".records.jsonl")).read_text()
    assert "sequence" not in sidecar
    assert "MKVLAT" not in sidecar
    # Lineage is metadata and travels; A1.4's own manifests carry the same tags.
    assert "Caudoviricetes" in sidecar


@pytest.mark.parametrize("component", ["stage2", "imgvr"])
def test_an_absent_cache_reads_as_empty_rather_than_raising(tmp_path, component):
    # The run decides what an empty band means — a split with no records in the band is normal,
    # a missing collect pass is not — so the reader reports and does not judge.
    proteins, records, stats = detect_profiles.read_cache(
        tmp_path, component=component, object_name="nothing.gz", lo=0.0, hi=1.0
    )
    assert (proteins, records, stats["genes"]) == ([], {}, 0)


def test_a_sub_band_search_finds_a_wider_collect_pass_cache(tmp_path):
    # A collect pass caches [0.014, 0.02); the searches take [0.014, 0.017) and [0.017, 0.02)
    # out of it. The reader must find the wide file and filter it, not look for a file named
    # after the sub-band — and a guard that looked for an exact stem match once discarded a
    # finished 70-minute search.
    ids = [f"stage2:train#{i}" for i in range(800)]
    detect_profiles.write_cache(
        tmp_path,
        detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.014, 0.02),
        [protein(f"{i}|gene0") for i in ids],
        records_for(ids),
        band=(0.014, 0.02),
    )
    wide = {i for i in ids if in_band(i, seed=detect_profiles.SEED, lo=0.014, hi=0.02)} or set(ids)
    first, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=0.5
    )
    second, _, _ = detect_profiles.read_cache(
        tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.5, hi=1.0
    )
    assert first and second
    assert len(first) + len(second) == len(ids)
    assert wide  # the cache's own band is recorded, and membership is recomputed on read


def test_a_cache_from_an_older_format_is_refused_with_an_instruction(tmp_path):
    # Format 1 wrote the taxonomy's ranks and dropped its taxa, which cannot be recovered — so a
    # stale cache must say to re-collect rather than raise a ValueError deep in a dict() call,
    # or crash at the routing stage after a long search.
    import json

    stem = detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0)
    (tmp_path / f"{stem}.faa.gz").write_bytes(b"")
    (tmp_path / f"{stem}.records.jsonl").write_text(
        json.dumps(
            {
                "record_id": "stage2:train#1",
                "component": "IMG/VR",
                "taxonomy": ["realm", "class"],
                "band": [0.0, 1.0],
            }
        )
        + "\n"
    )
    with pytest.raises(SystemExit, match="cache format"):
        detect_profiles.read_cache(
            tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
        )


def test_the_plan_path_reads_the_current_searched_sources_shape():
    """`--plan` must survive `searched_sources` changing shape (X1.6).

    It did not: the branch passed one argument to a two-argument function and indexed the
    result as a mapping, so the flag raised `TypeError` rather than reporting anything. The
    search paths were fine throughout, which is why nothing caught it — this test drives the
    reporting path against the real staged-source metadata, which is offline.
    """
    release = "opengenome"
    from amazebio import corpora

    sources = [
        s
        for s in corpora.sources_for(release)
        if s.readable and s.corpus_component in detect_profiles.SAMPLE_RATES
    ]
    assert sources, "fixture assumes opengenome has readable stage2 objects"
    manifest = {
        "release": release,
        "policy": {"id": "evo1-literal"},
        "sources": [{"key": s.key, "records": 1_000_000} for s in sources],
    }

    lines = detect_profiles.plan_lines(manifest, release)

    assert len(lines) == len(sources)
    # 0.2% of a million records, formatted — the number a reader checks the plan for.
    assert all("~2,000 sampled" in line for line in lines)
    assert all("stage2" in line for line in lines)


def test_the_plan_path_reports_unknown_rather_than_guessing_a_count():
    """A manifest row without `records` is reported as unknown, not as zero sampled."""
    release = "opengenome"
    from amazebio import corpora

    sources = [
        s
        for s in corpora.sources_for(release)
        if s.readable and s.corpus_component in detect_profiles.SAMPLE_RATES
    ]
    manifest = {
        "release": release,
        "policy": {"id": "evo1-literal"},
        "sources": [{"key": s.key} for s in sources],
    }

    assert all("unknown sampled" in line for line in detect_profiles.plan_lines(manifest, release))


class TestTheTaskTheRunBelongsTo:
    """D-222. A2.6 re-runs this search at census depth. Its tables and A2.1's sampled ones
    are two measurements, and the comparison between them is part of the result, so neither
    may land on the other's key."""

    def test_the_durable_prefix_follows_the_task(self) -> None:
        for task in ("A2.1", "A2.6"):
            out = detect_profiles.canonical_out(task)
            assert detect_profiles.durable_for(task, out).endswith(
                f"/results/{detect_profiles.task_slug(task)}"
            )

    def test_the_two_tasks_do_not_share_a_prefix(self) -> None:
        one = detect_profiles.durable_for("A2.1", detect_profiles.canonical_out("A2.1"))
        six = detect_profiles.durable_for("A2.6", detect_profiles.canonical_out("A2.6"))
        assert one != six

    def test_a_run_written_somewhere_else_publishes_nothing(self, tmp_path) -> None:
        """On 2026-10-20 a rehearsal of `--assemble` wrote six synthetic tables to the real
        census prefix, in a bucket with no delete. `--out` is what tells the two apart."""
        assert detect_profiles.durable_for("A2.6", tmp_path) is None

    def test_a_relative_canonical_path_still_publishes(self, monkeypatch) -> None:
        """The comparison is on resolved paths, so `--out artifacts/a2-6` from the repo root
        is the canonical directory and not a rehearsal."""
        monkeypatch.chdir(detect_profiles.REPO)
        assert detect_profiles.durable_for("A2.6", pathlib.Path("artifacts/a2-6")) is not None

    def test_the_default_is_the_task_that_owns_this_tool(self) -> None:
        """A run that forgets `--task` writes where it always did, rather than somewhere
        new and empty that nothing reads."""
        assert detect_profiles.TASK_DEFAULT == "A2.1"


class TestHowDeepATaskMayRead:
    """D-099 made the declared rate a pre-registration rather than a flag. A2.6 reads the
    whole corpus, which is a new declaration (D-222) and not a wider argument."""

    def test_a21_may_not_read_past_its_pre_registered_deepening(self) -> None:
        assert (
            detect_profiles.rate_ceiling("A2.1", "stage2") == detect_profiles.DEEP_RATES["stage2"]
        )

    def test_a26_reads_the_whole_corpus(self) -> None:
        for component in detect_profiles.SAMPLE_RATES:
            assert detect_profiles.rate_ceiling("A2.6", component) == 1.0

    def test_an_unknown_task_gets_the_narrow_ceiling(self) -> None:
        """A typo in --task must not widen what the run may read."""
        assert detect_profiles.rate_ceiling("A2.9", "imgvr") == detect_profiles.DEEP_RATES["imgvr"]

    def test_every_sampled_component_has_a_census_rate(self) -> None:
        assert set(detect_profiles.CENSUS_RATES) == set(detect_profiles.SAMPLE_RATES)


class TestSearchingInChunks:
    """A2.6 reads a band as a stream of chunks rather than one list.

    The reason is arithmetic: at census depth a single staged object is the whole release —
    OpenGenome's stage-2 split holds 2,652,947 records — so accumulating the band before
    calling genes puts the corpus in memory, and no instance the account permits has that
    memory. What has to be true is that chunking changes nothing: the detections are a union
    over records and every threshold is per protein, so the same proteins searched in
    pieces must give the same hits.
    """

    class Reg:
        def __init__(self, rid: str) -> None:
            self.id = rid
            self.key = rid

    class Source:
        component = "IMG/VR"
        corpus_component = "stage2"

    @staticmethod
    def _view():
        class View:
            restrict_to = None

        return View()

    def _fake_search(self, monkeypatch):
        """One hit per protein, so a hit's provenance is unambiguous."""

        def search(reg, proteins, *, restrict_to):
            return [
                {
                    "record_id": detect_profiles.profilesearch.text_of(p.name).split("|")[0],
                    "profile": f"PF{reg.id}",
                    "score": 10.0,
                }
                for p in proteins
            ]

        monkeypatch.setattr(detect_profiles, "search", search)

    def _run(self, proteins, chunk):
        regs = [self.Reg("pfam"), self.Reg("rvdb-prot")]
        views = {r.id: self._view() for r in regs}
        hits: dict[str, list] = {r.id: [] for r in regs}
        seconds = {r.id: 0.0 for r in regs}
        touched: set[str] = set()
        for i in range(0, len(proteins), chunk):
            touched |= detect_profiles.search_batch(
                regs,
                views,
                proteins[i : i + chunk],
                source=self.Source(),
                hits=hits,
                search_seconds=seconds,
            )
        return hits, touched, seconds

    @pytest.mark.parametrize("chunk", [1, 2, 3, 7, 100])
    def test_the_hits_do_not_depend_on_the_chunk_size(self, monkeypatch, chunk) -> None:
        self._fake_search(monkeypatch)
        proteins = [protein(f"stage2:train#{i}|gene0") for i in range(10)]
        whole, whole_touched, _ = self._run(proteins, 100)
        part, part_touched, _ = self._run(proteins, chunk)
        for rid in whole:
            assert sorted(h["record_id"] for h in part[rid]) == sorted(
                h["record_id"] for h in whole[rid]
            )
        assert part_touched == whole_touched

    def test_every_hit_carries_its_source(self, monkeypatch) -> None:
        """The chunk loop is where component and corpus_component are stamped on, and the
        route resolution downstream reads both."""
        self._fake_search(monkeypatch)
        hits, _, _ = self._run([protein("stage2:train#1|gene0")], 1)
        row = hits["pfam"][0]
        assert row["component"] == "IMG/VR"
        assert row["corpus_component"] == "stage2"

    def test_it_returns_only_the_records_that_hit(self, monkeypatch) -> None:
        """Those are the only ones the route resolution looks up, and keeping the rest puts
        the census back in memory by another door."""

        def search(reg, proteins, *, restrict_to):
            first = detect_profiles.profilesearch.text_of(proteins[0].name).split("|")[0]
            return [{"record_id": first, "profile": "PF0", "score": 1.0}]

        monkeypatch.setattr(detect_profiles, "search", search)
        proteins = [protein(f"stage2:train#{i}|gene0") for i in range(5)]
        _, touched, _ = self._run(proteins, 5)
        assert touched == {"stage2:train#0"}

    def test_an_empty_chunk_searches_nothing(self, monkeypatch) -> None:
        """A pass over Pfam's profile file costs 418 MB read to find nothing."""
        calls: list[int] = []

        def search(reg, proteins, *, restrict_to):
            calls.append(len(proteins))
            return []

        monkeypatch.setattr(detect_profiles, "search", search)
        _, touched, seconds = self._run([], 10)
        assert calls == []
        assert touched == set()
        assert set(seconds.values()) == {0.0}

    def test_the_time_is_summed_over_the_chunks(self, monkeypatch) -> None:
        self._fake_search(monkeypatch)
        _, _, seconds = self._run([protein(f"s:r#{i}|gene0") for i in range(6)], 2)
        assert all(v >= 0.0 for v in seconds.values())
        assert set(seconds) == {"pfam", "rvdb-prot"}


class TestTheChunkedCache:
    """`--collect` writes one file per chunk; `read_cache` has to read the set as one."""

    def test_two_chunks_of_one_object_read_back_as_one_cache(self, tmp_path) -> None:
        for chunk, ids in enumerate([["stage2:train#1", "stage2:train#2"], ["stage2:train#3"]]):
            detect_profiles.write_cache(
                tmp_path,
                detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0, chunk=chunk),
                [protein(f"{i}|gene0") for i in ids],
                records_for(ids),
                band=(0.0, 1.0),
            )
        proteins, records, stats = detect_profiles.read_cache(
            tmp_path, component="stage2", object_name="train_stage2.parquet", lo=0.0, hi=1.0
        )
        assert stats["records"] == 3
        assert len(proteins) == 3
        assert set(records) == {"stage2:train#1", "stage2:train#2", "stage2:train#3"}

    def test_a_chunk_does_not_overwrite_its_predecessor(self, tmp_path) -> None:
        """The failure this guards is the one the split keying already cost a read to: one
        stem for several writes, and the last — often a short tail chunk — wins."""
        stems = {
            detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.0, 1.0, chunk=c)
            for c in range(3)
        }
        assert len(stems) == 3

    def test_an_unchunked_stem_is_unchanged(self, tmp_path) -> None:
        """A2.1's caches on disk were written without a chunk index and must still read."""
        assert (
            detect_profiles.cache_stem("stage2", "train_stage2.parquet", 0.014, 0.02)
            == "stage2--train_stage2.parquet--0.014-0.02"
        )


class TestWhatParallelBandsMustNotShare:
    """Eight bands of one release run at once on one machine, and everything they publish
    goes to one durable prefix. Anything named for the release alone is written eight times.

    This is not hypothetical twice over: A1.5 lost a staging run's provenance to exactly
    this with two passes, and `repro`'s commit-keyed copy (D-216) refuses a second set of
    bytes under one key outright — so a collision here fails the worker *after* its six
    hours rather than before them.
    """

    @staticmethod
    def _scope(release: str, band) -> str:
        scope = release
        if band is not None:
            scope = f"{scope}-{band[0]:g}-{band[1]:g}"
        return scope

    def test_two_bands_of_one_release_do_not_share_a_name(self) -> None:
        names = {self._scope("opengenome", b) for b in [(1, 126), (126, 251)]}
        assert len(names) == 2

    def test_every_band_of_a_census_split_is_distinct(self) -> None:
        edges = [1, 126, 251, 376, 501, 625, 750, 875, 1000]
        bands = list(itertools.pairwise(edges))
        assert len({self._scope("opengenome2", b) for b in bands}) == len(bands)

    def test_an_unbanded_run_keeps_the_release_name(self) -> None:
        """A2.1's own artefacts are `run-opengenome.json` and `index-opengenome.json`, and
        they are cited."""
        assert self._scope("opengenome", None) == "opengenome"

    def test_the_tool_builds_the_scope_this_way(self) -> None:
        """Read from the source rather than restated, so the test moves when it does."""
        source = _PATH.read_text()
        assert 'scope = f"{scope}-{band[0]:g}-{band[1]:g}"' in source
        assert 'manifest_name=f"run-{scope}.json"' in source
        assert "index-{scope}.json" in source


class TestHowAManifestIsCited:
    """`--manifests artifacts/a1-4` is what the census workers are given, because the
    instance has no checkout at the repository root.

    `Path.relative_to` raises on a path outside the root rather than giving up, and the
    raise happened after the search: a worker would have read its whole band, searched it,
    and died with nothing written. A smoke test on 400 records found it; the instance would
    have found it six hours in.
    """

    def test_a_path_inside_the_repo_is_cited_relative_to_it(self) -> None:
        inside = pathlib.Path(detect_profiles.REPO) / "artifacts" / "a1-4" / "m.json"
        assert detect_profiles.manifest_ref_path(inside) == "artifacts/a1-4/m.json"

    def test_a_relative_path_resolves_rather_than_raising(self, monkeypatch) -> None:
        monkeypatch.chdir(detect_profiles.REPO)
        assert (
            detect_profiles.manifest_ref_path(pathlib.Path("artifacts/a1-4/m.json"))
            == "artifacts/a1-4/m.json"
        )

    def test_a_path_outside_the_repo_is_cited_absolutely(self, tmp_path) -> None:
        """The absolute path still says which file was read, and the digest beside it in
        the table is what pins the content."""
        outside = tmp_path / "a1-4" / "m.json"
        assert detect_profiles.manifest_ref_path(outside) == str(outside.resolve())

    def test_it_never_raises_on_any_shape_of_path(self, tmp_path) -> None:
        for path in [
            pathlib.Path("artifacts/a1-4/m.json"),
            pathlib.Path("/opt/amazebio/artifacts/a1-4/m.json"),
            tmp_path / "m.json",
            pathlib.Path(detect_profiles.REPO) / "m.json",
        ]:
            assert detect_profiles.manifest_ref_path(path)


class TestWhatAProbeMayNotPublish:
    """`--limit-records` with `--band` is refused.

    A band run publishes a part, and `--assemble` reads a part as *the* result for that
    band. A part made from twenty records claims the whole band, so the merge understates
    every family in it while the coverage check still passes — the bands tile correctly,
    which is all that check can see. This pair published a 20-record part into the census
    prefix once; the store has no delete.
    """

    def _main(self, *argv):
        return detect_profiles.main(["--manifests", "artifacts/a1-4", "--registry", "pfam", *argv])

    def test_a_limited_band_run_is_refused(self) -> None:
        with pytest.raises(SystemExit) as caught:
            self._main("--band", "1:2", "--limit-records", "20")
        assert "claiming the whole band" in str(caught.value)

    def test_the_refusal_says_what_to_do_instead(self) -> None:
        with pytest.raises(SystemExit) as caught:
            self._main("--band", "1:2", "--limit-records", "20")
        message = str(caught.value)
        assert "without --band" in message
        assert "durable" in message

    def test_a_limited_collect_is_allowed(self) -> None:
        """`--collect` searches nothing and writes no part, so there is nothing to
        misread; probing the read path is exactly what it is for.

        The assertion is that the probe guard did **not** fire, not that some later step
        did. Asserting the message of whatever stops the run next made this test depend on
        whether `artifacts/a1-4` happens to exist in the working tree: it passed locally,
        where it does, and failed in CI, where it does not.
        """
        with pytest.raises(SystemExit) as caught:
            self._main("--band", "1:2", "--limit-records", "20", "--collect", "--release", "nope")
        assert "claiming the whole band" not in str(caught.value)

    def test_an_unlimited_band_run_is_untouched(self) -> None:
        with pytest.raises(SystemExit) as caught:
            self._main("--band", "1:2", "--release", "nope")
        assert "claiming the whole band" not in str(caught.value)


class TestShelvingBandPartsForAssembly:
    """At census depth the parts do not fit in memory together, so assembly spills them.

    The risk the shelf introduces is routing: rows from the wrong part, or from the wrong
    table key, would produce a table that looks complete and counts the wrong records. These
    pin the routing, the ordering and the one-part-at-a-time property.
    """

    def _part(self, tmp_path, name, release, band, tables, sources=None):
        path = tmp_path / "parts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "release": release,
                    "band_multiple": band,
                    "sources": sources if sources is not None else [{"component": release}],
                    "tables": tables,
                }
            )
        )
        return path

    def test_each_key_gets_its_own_file_and_keeps_part_order(self, tmp_path):
        a = self._part(tmp_path, "part-a.json", "r1", [0, 1], {"p|pfam": [{"n": 1}, {"n": 2}]})
        b = self._part(tmp_path, "part-b.json", "r1", [1, 2], {"p|pfam": [{"n": 3}]})
        counts, shelf = detect_profiles._shelve_parts([a, b], tmp_path)
        assert [c["band_multiple"] for c in counts] == [[0, 1], [1, 2]]
        assert list(detect_profiles._shelved_rows(shelf, "p|pfam")) == [
            {"n": 1},
            {"n": 2},
            {"n": 3},
        ]

    def test_rows_do_not_leak_between_keys(self, tmp_path):
        a = self._part(
            tmp_path,
            "part-a.json",
            "r1",
            [0, 1],
            {"literal|pfam": [{"n": 1}], "strict|pfam": [{"n": 99}]},
        )
        _, shelf = detect_profiles._shelve_parts([a], tmp_path)
        assert list(detect_profiles._shelved_rows(shelf, "literal|pfam")) == [{"n": 1}]
        assert list(detect_profiles._shelved_rows(shelf, "strict|pfam")) == [{"n": 99}]

    def test_a_key_nothing_shelved_yields_nothing_rather_than_raising(self, tmp_path):
        _, shelf = detect_profiles._shelve_parts([], tmp_path)
        assert list(detect_profiles._shelved_rows(shelf, "absent|pfam")) == []

    def test_the_counts_are_kept_and_the_rows_are_not(self, tmp_path):
        """The whole point: the small half stays in memory, the large half does not."""
        a = self._part(
            tmp_path, "part-a.json", "r1", [0, 1], {"p|pfam": [{"n": i} for i in range(100)]}
        )
        counts, _ = detect_profiles._shelve_parts([a], tmp_path)
        assert counts == [
            {"release": "r1", "band_multiple": [0, 1], "sources": [{"component": "r1"}]}
        ]
        assert "tables" not in counts[0]

    def test_a_stale_shelf_is_cleared_rather_than_appended_to(self, tmp_path):
        a = self._part(tmp_path, "part-a.json", "r1", [0, 1], {"p|pfam": [{"n": 1}]})
        detect_profiles._shelve_parts([a], tmp_path)
        _, shelf = detect_profiles._shelve_parts([a], tmp_path)
        assert list(detect_profiles._shelved_rows(shelf, "p|pfam")) == [{"n": 1}]

    def test_a_part_with_no_tables_still_contributes_its_counts(self, tmp_path):
        a = self._part(tmp_path, "part-a.json", "r1", [0, 1], {})
        counts, shelf = detect_profiles._shelve_parts([a], tmp_path)
        assert len(counts) == 1
        assert shelf == {}

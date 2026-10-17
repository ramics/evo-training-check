"""The scope and attribution logic in `tools/detect_proviruses.py` — task A2.4.

Two things in this tool decide whether its numbers mean anything, and neither is visible in a
finished table:

**Scope.** Which sources it searched, and whether the ones it did not are reported. A table that
silently covered part of a release reads as a verdict on all of it (D-080, D-116).

**Attribution.** Which record a protein found inside a provirus is counted on. geNomad invents a
name for every provirus it delineates; counting on that name instead of on the host genome would
inflate the denominator and attribute a prophage's families to a sequence that exists nowhere
outside the run (D-113).

The search itself is `pyhmmer` against a pinned registry and is `test_profiles.py`'s; geNomad's
output parsing is `test_proviruses.py`'s.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "detect_proviruses.py"
_spec = importlib.util.spec_from_file_location("detect_proviruses_under_test", _PATH)
dp = importlib.util.module_from_spec(_spec)
sys.modules["detect_proviruses_under_test"] = dp
_spec.loader.exec_module(dp)

from amazebio.survival import ElementKind, Route  # noqa: E402


def source(component, outcome="out_of_scope", **extra):
    return {
        "component": component.upper(),
        "corpus_component": component,
        "uniform_outcome": outcome,
        **extra,
    }


# --------------------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------------------


def test_both_releases_bacterial_components_are_searched():
    for component in ("gtdb_v220", "stage1_gtdb"):
        searched, skipped = dp.source_rows({"sources": [source(component)]})
        assert len(searched) == 1, component
        assert skipped == []


def test_a_viral_component_is_skipped_and_says_why():
    searched, skipped = dp.source_rows({"sources": [source("imgvr")]})
    assert searched == []
    assert skipped[0]["searched"] is False
    assert "A2.1" in skipped[0]["why"]


def test_every_source_appears_in_exactly_one_list():
    """None is dropped: an omitted component is an invisible gap in coverage."""
    components = ["gtdb_v220", "imgvr", "imgpr", "ncrna", "mrna", "organelles"]
    manifest = {"sources": [source(c) for c in components]}
    searched, skipped = dp.source_rows(manifest)
    assert len(searched) + len(skipped) == len(components)
    assert {s["corpus_component"] for s in skipped} | {
        s["corpus_component"] for s in searched
    } == set(components)


def test_an_unknown_component_is_skipped_with_a_reason_not_silently():
    _, skipped = dp.source_rows({"sources": [source("something_new")]})
    assert skipped[0]["why"]


def test_a_protein_corpus_says_the_detector_is_not_defined_over_it():
    """ESM3's proxy is protein: not a coverage gap but a category A2.4 cannot act on."""
    _, skipped = dp.source_rows({"sources": [source("uniref_2023_02")]})
    assert "not defined over" in skipped[0]["why"]


def test_a_manifest_with_no_bacterial_component_searches_nothing():
    searched, skipped = dp.source_rows({"sources": [source("uniref_2023_02"), source("pdb")]})
    assert searched == []
    assert len(skipped) == 2


# --------------------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------------------


def test_the_route_is_read_from_the_manifest_not_recomputed():
    assert dp.route_of_source(source("gtdb_v220", "out_of_scope")) is Route.OUT_OF_SCOPE


def test_the_strict_readings_wildcard_scope_gives_a_different_route():
    """The same prophage sits on different routes in different readings. That is the finding."""
    assert dp.route_of_source(source("gtdb_v220", "retained")) is Route.RETAINED_BY_DESIGN


def test_a_source_without_a_uniform_outcome_stops_the_run():
    with pytest.raises(dp.RunError, match="uniform_outcome"):
        dp.route_of_source({"corpus_component": "gtdb_v220"})


# --------------------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------------------


def test_a_provirus_protein_is_counted_on_its_genome():
    assert dp.host_of_protein("GCF_000001.1~3|provirus_1000_2000_7") == "GCF_000001.1"


def test_two_proviruses_in_one_genome_are_one_record():
    a = dp.host_of_protein("GCF_000001.1~0|provirus_1_100_1")
    b = dp.host_of_protein("GCF_000001.1~9|provirus_5000_6000_1")
    assert a == b == "GCF_000001.1"


def test_proviruses_in_different_genomes_are_different_records():
    a = dp.host_of_protein("GCF_000001.1~0|provirus_1_100_1")
    b = dp.host_of_protein("GCF_000002.1~0|provirus_1_100_1")
    assert a != b


def test_an_evo_1_derived_genome_key_round_trips():
    """Evo 1's genome is a WGS project accession (D-136); it must survive the same path."""
    header = dp.contig_header("JAHFAU01", 42)
    assert header == "JAHFAU01~42"
    assert dp.host_of_protein(f"{header}|provirus_1_100_1") == "JAHFAU01"


def test_a_genome_id_containing_the_separator_is_refused():
    """Silently accepting it would make the attribution back to the host ambiguous."""
    with pytest.raises(dp.RunError, match="ambiguous"):
        dp.contig_header("odd~name", 0)


def test_a_name_without_the_separator_still_yields_something():
    """Defensive: a header geNomad rewrote should not resolve to the empty string."""
    assert dp.host_of_protein("plaincontig|provirus_1_2_1") == "plaincontig"


# --------------------------------------------------------------------------------------
# Detections
# --------------------------------------------------------------------------------------


def test_a_detection_is_a_prophage_regardless_of_which_family_was_hit():
    """D-079/D-113: the kind comes from the provirus finder, never from the families hit."""
    (detection,) = dp.detections_from_hits(
        [{"profile": "PF05505.16", "record_id": "GCF_1", "score": 40.0}],
        registry_id="pfam",
        registry_version="38.2",
        thresholds={"PF05505": 20.0},
        route=Route.OUT_OF_SCOPE,
        profile_to_family={"PF05505.16": "PF05505"},
    )
    assert detection.element_kind is ElementKind.PROPHAGE
    assert detection.route is Route.OUT_OF_SCOPE
    assert detection.detector == "provirus-genomad"
    assert detection.family_id == "PF05505"


def test_a_profile_outside_the_pinned_universe_stops_the_run():
    """An unknown family id would change the denominator without showing it."""
    with pytest.raises(dp.RunError, match="pinned universe"):
        dp.detections_from_hits(
            [{"profile": "PF99999.1", "record_id": "GCF_1", "score": 40.0}],
            registry_id="pfam",
            registry_version="38.2",
            thresholds={},
            route=Route.OUT_OF_SCOPE,
            profile_to_family={},
        )


def test_notes_warn_when_no_concordance_was_run():
    notes = dp.table_notes(genomes=10, proviruses=3, concordance=None)
    assert any("one instrument" in n for n in notes)
    assert any("lower bound" in n.lower() for n in notes)


# --------------------------------------------------------------------------------------
# A probe must not look like a result
# --------------------------------------------------------------------------------------


def test_limit_is_documented_as_writing_nothing():
    """The first end-to-end run wrote `estimate_kind: population` from one genome.

    `--limit 1 --rate 1.0` read 25,792 bases of a single genome and the table reported a census
    over the whole component, with a Wilson interval of [0, 0.0022] across 1,719 families. The
    number was arithmetically correct and completely misleading: a precise-looking null computed
    from almost no data, which is exactly what `AGENTS.md` forbids the pipeline to be able to
    produce. A limited run now prints its counts and writes no table.
    """
    parser_help = dp.main.__doc__ or ""
    source = pathlib.Path(dp.__file__).read_text()
    assert "--limit" in source
    assert "writes NO" in source or "not written" in source
    assert parser_help is not None


def test_max_objects_shares_the_probe_guard_with_limit():
    """Both read less than the rate says, so both must suppress the table.

    One condition rather than two checks, so a third flag with the same property cannot be
    added without the guard following it.
    """
    source = pathlib.Path(dp.__file__).read_text()
    assert "args.probe = bool(args.limit or args.max_objects)" in source
    assert "if args.probe:" in source


def test_the_probe_branch_precedes_any_write():
    """Structural: the `--limit` guard must come before `table.write`, not after it."""
    source = pathlib.Path(dp.__file__).read_text()
    guard = source.index("if args.probe:")
    write = source.index("table.write(")
    assert guard < write, "a probe must stop before anything is written"


# --------------------------------------------------------------------------------------
# The concordance arm
# --------------------------------------------------------------------------------------


def test_the_concordance_subsample_is_nested_inside_the_main_sample():
    """D-114: same hash, same seed, a tenth the rate — so it is a subset, not a second draw.

    A separate draw would not be nested, and the agreement would then be measured over records
    the main table never searched.
    """
    from amazebio.detect import in_sample

    rate = 0.025
    sub_rate = rate * dp.CONCORDANCE_FRACTION
    ids = [f"GCF_{n:09d}.1" for n in range(20000)]
    main = {i for i in ids if in_sample(i, seed=dp.SEED, rate=rate)}
    sub = {i for i in ids if in_sample(i, seed=dp.SEED, rate=sub_rate)}
    assert sub, "the subsample must not be empty at this size"
    assert sub <= main, "the concordance subsample must be a subset of the main sample"


def test_the_concordance_fraction_is_a_tenth():
    assert dp.CONCORDANCE_FRACTION == 0.1


def test_a_provirus_call_is_rekeyed_from_its_contig_to_its_genome():
    """The 2x2 is per record, and this pass's record is the genome (D-136)."""
    from amazebio.proviruses import ProvirusCall

    call = ProvirusCall(
        source_record="GCF_000001.1~7", fragment="f", start=10, end=20, tool="genomad"
    )
    assert dp._rehome(call).source_record == "GCF_000001.1"


def test_both_tools_calls_are_rekeyed_the_same_way():
    """Re-keying one and not the other would make every multi-contig genome a disagreement."""
    from amazebio.proviruses import ProvirusCall

    g = ProvirusCall(source_record="G~0", fragment="a", start=1, end=9, tool="genomad")
    v = ProvirusCall(source_record="G~4", fragment="b", start=1, end=9, tool="vibrant")
    assert dp._rehome(g).source_record == dp._rehome(v).source_record == "G"


def test_host_of_contig_survives_a_name_without_the_separator():
    assert dp.host_of_contig("plain") == "plain"


def test_the_corpus_read_beats_while_it_reads_not_only_when_it_starts():
    """The longest step published nothing between "reading" and the search after it.

    Evo 1's component alone is 127 GB, so that is over an hour of silence on an instance whose
    console cannot distinguish a dead process from a quiet one — the reading that cost A1.6
    four hours.
    """
    source = pathlib.Path(dp.__file__).read_text()
    read_loop = source[source.index("for index, key in enumerate(keys):") :]
    read_loop = read_loop[: read_loop.index("read_seconds =")]
    assert "args.heartbeat_seconds" in read_loop
    assert "objects_done" in read_loop and "genomes_sampled" in read_loop

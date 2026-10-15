"""Tests for `tools/taxonomy_benchmark.py` — selection, the NCBI join, and scoring.

The selection tests pin D-087's choices, because each of them moves the result and none is
recoverable from the artefact if it drifts: the per-family caps (without which Geminiviridae is
a fifth of the in-scope set and the pooled rate reports the ICTV's ratification effort), the
completeness filter, and the sequence-not-species unit.

`test_bare_strips_the_version_suffix` and `test_score_excludes_unretrieved_sequences` cover the
two ways this pipeline could invent leakage rather than measure it. NCBI answers `MK064563`
with `MK064563.1`, so a join on the versioned form drops records the tool classified perfectly;
and a sequence that was never retrieved was never offered to the tool, so counting it as an
escape would attribute a network failure to geNomad.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

from amazebio import genomad, ictv, misassignment

_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "taxonomy_benchmark.py"
_spec = importlib.util.spec_from_file_location("taxonomy_benchmark_under_test", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["taxonomy_benchmark_under_test"] = tool
_spec.loader.exec_module(tool)

CORONA = "Viruses;Riboviria;Orthornavirae;Pisuviricota;Pisoniviricetes;Nidovirales;Coronaviridae"
GEMINI = (
    "Viruses;Monodnaviria;Shotokuvirae;Cressdnaviricota;Repensiviricetes;Geplafuvirales;"
    "Geminiviridae"
)
TRUNCATED = "Viruses;Riboviria;Orthornavirae"
MISRANKED = "Viruses;Duplodnaviria;Heunggongvirae;Peploviricota;Herviviricetes;Herpesviridae"

DENYLIST = misassignment.Denylist(
    families=frozenset({"Coronaviridae", "Geminiviridae"}),
    orders=frozenset({"Picornavirales"}),
    policy="test",
)


def _exemplar(
    species: str,
    *,
    family: str = "Coronaviridae",
    order: str = "Nidovirales",
    accessions: tuple[tuple[str | None, str], ...] = ((None, "NC_000001"),),
    coverage: str = "Complete genome",
    row: int = 2,
) -> ictv.Exemplar:
    lineage = {"realm": "Riboviria"}
    if order:
        lineage["order"] = order
    if family:
        lineage["family"] = family
    return ictv.Exemplar(
        species=species,
        lineage=lineage,
        accessions=accessions,
        coverage=coverage,
        host_source="vertebrates",
        is_exemplar=True,
        row=row,
    )


def _build(monkeypatch: pytest.MonkeyPatch, exemplars: list[ictv.Exemplar]) -> dict:
    table = ictv.VMRTable(
        exemplars=exemplars, all_rows=len(exemplars), exemplar_rows=len(exemplars)
    )
    monkeypatch.setattr(tool.ictv, "read_vmr", lambda *a, **k: table)
    return tool.build_evalset(pathlib.Path("unused.xlsx"), DENYLIST)


# --------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------


def test_hash_key_is_deterministic_and_accession_dependent() -> None:
    """No seed to lose, and no dependence on dict ordering (D-078's precedent)."""
    assert tool._hash_key("NC_001806") == tool._hash_key("NC_001806")
    assert tool._hash_key("NC_001806") != tool._hash_key("NC_045512")


def test_family_key_falls_back_to_order_then_unplaced() -> None:
    """A record denylisted by order with no family is the shape the order rules exist for."""
    assert tool._family_key(_exemplar("a", family="Picornaviridae")) == "Picornaviridae"
    assert tool._family_key(_exemplar("b", family="", order="Picornavirales")) == (
        "(order:Picornavirales)"
    )
    assert tool._family_key(_exemplar("c", family="", order="")) == "(unplaced)"


def test_in_scope_cap_is_applied_per_family(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [
        _exemplar(f"sp{i}", accessions=((None, f"NC_{i:06d}"),))
        for i in range(tool.IN_SCOPE_CAP + 15)
    ]
    built = _build(monkeypatch, many)
    assert built["per_family"]["Coronaviridae"]["available"] == tool.IN_SCOPE_CAP + 15
    assert built["per_family"]["Coronaviridae"]["selected"] == tool.IN_SCOPE_CAP
    assert built["counts"]["sequences"] == tool.IN_SCOPE_CAP


def test_control_cap_is_smaller_than_the_in_scope_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Controls cover breadth; in-scope families carry the rate, so they get more."""
    controls = [
        _exemplar(f"sp{i}", family="Siphoviridae", order="", accessions=((None, f"NC_{i:06d}"),))
        for i in range(tool.CONTROL_CAP + 10)
    ]
    built = _build(monkeypatch, controls)
    entry = built["per_family"]["Siphoviridae"]
    assert entry["selected"] == tool.CONTROL_CAP
    assert entry["in_scope"] is False
    assert tool.CONTROL_CAP < tool.IN_SCOPE_CAP


def test_selection_is_stable_across_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [
        _exemplar(f"sp{i}", accessions=((None, f"NC_{i:06d}"),))
        for i in range(tool.IN_SCOPE_CAP + 15)
    ]
    first = {r["accession"] for r in _build(monkeypatch, many)["records"]}
    second = {r["accession"] for r in _build(monkeypatch, list(reversed(many)))["records"]}
    assert first == second, "selection must not depend on input order"


def test_incomplete_genomes_are_excluded_and_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(
        monkeypatch,
        [
            _exemplar("complete"),
            _exemplar("partial", coverage="Partial genome", accessions=((None, "NC_000002"),)),
        ],
    )
    assert built["selection"]["excluded"]["not_complete"] == 1
    assert built["counts"]["sequences"] == 1


def test_rows_without_an_accession_are_excluded_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build(monkeypatch, [_exemplar("none", accessions=())])
    assert built["selection"]["excluded"]["no_accession"] == 1
    assert built["counts"]["sequences"] == 0


def test_unparseable_accessions_are_excluded_visibly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shorter evaluation set must never be how we learn about a release anomaly."""
    built = _build(monkeypatch, [_exemplar("odd", accessions=(("?", "not-an-accession"),))])
    assert built["selection"]["excluded"]["unparseable_accession"] == 1


def test_each_segment_becomes_its_own_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unit is the sequence: a filter acts per record and segments arrive separately."""
    built = _build(
        monkeypatch,
        [_exemplar("segmented", accessions=(("A", "NC_000011"), ("B", "NC_000012")))],
    )
    assert built["counts"]["exemplars"] == 1
    assert built["counts"]["sequences"] == 2
    assert {r["segment"] for r in built["records"]} == {"A", "B"}
    assert {r["species"] for r in built["records"]} == {"segmented"}


def test_scope_is_recorded_per_record(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(
        monkeypatch,
        [
            _exemplar("in", family="Coronaviridae"),
            _exemplar("out", family="Siphoviridae", order="", accessions=((None, "NC_000003"),)),
        ],
    )
    scope = {r["species"]: r["in_scope"] for r in built["records"]}
    assert scope == {"in": True, "out": False}
    assert built["counts"]["in_scope_sequences"] == 1
    assert built["counts"]["control_sequences"] == 1


def test_order_denylist_puts_an_unnamed_family_in_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """Secoviridae is not on the family list; Picornavirales is on the order list."""
    built = _build(monkeypatch, [_exemplar("seco", family="Secoviridae", order="Picornavirales")])
    assert built["per_family"]["Secoviridae"]["in_scope"] is True


def test_mixed_scope_within_a_family_group_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checked rather than assumed, because the order-keyed groups could in principle mix."""
    built_ok = _build(monkeypatch, [_exemplar("a")])
    assert built_ok["counts"]["sequences"] == 1
    mixed = [
        _exemplar("a", family="Mixed", order="Picornavirales"),
        _exemplar("b", family="Mixed", order="Nidovirales", accessions=((None, "NC_000004"),)),
    ]
    with pytest.raises(ValueError, match="mixes in-scope and out-of-scope"):
        _build(monkeypatch, mixed)


def test_build_records_the_ground_truth_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch, [_exemplar("a")])
    assert built["ground_truth"]["msl"] == "MSL37"
    assert built["ground_truth"]["published"] < "2022-09-20"


# --------------------------------------------------------------------------------------
# The NCBI join
# --------------------------------------------------------------------------------------


def test_bare_strips_the_version_suffix() -> None:
    """NCBI answers `MK064563` with `MK064563.1`; joining on the versioned form loses rows."""
    assert tool._bare("MK064563.1 Sulfolobales Beppu filamentous virus 2") == "MK064563"
    assert tool._bare("NC_001806.2 Human herpesvirus 1") == "NC_001806"
    assert tool._bare("DQ665917") == "DQ665917"


def test_parse_fasta_reads_multiple_records() -> None:
    text = ">A.1 first\nACGT\nACGT\n>B.2 second\nTTTT\n"
    parsed = tool._parse_fasta(text)
    assert parsed["A"][1] == "ACGTACGT"
    assert parsed["B"][1] == "TTTT"


def test_parse_fasta_of_nothing() -> None:
    assert tool._parse_fasta("") == {}


def test_fetch_writes_under_the_accession_the_evalset_keys_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """So that scoring needs no second mapping back from NCBI's header."""
    evalset = {
        "records": [
            {"accession": "NC_001806"},
            {"accession": "NC_045512"},
            {"accession": "NC_999999"},  # never returned
        ]
    }
    monkeypatch.setattr(
        tool,
        "_efetch",
        lambda accessions, email: ">NC_001806.2 herpes\nACGTACGTAC\n>NC_045512.2 sars\nTTTT\n",
    )
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)
    out = tmp_path / "x.fna"
    fetched = tool.fetch_sequences(evalset, out, email="t@example.org")
    assert fetched["written"] == 2
    assert fetched["missing"] == ["NC_999999"]
    assert fetched["lengths"] == {"NC_001806": 10, "NC_045512": 4}
    assert ">NC_001806\n" in out.read_text()
    assert ">NC_001806.2" not in out.read_text()


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------


def _evalset(records: list[dict]) -> dict:
    return {
        "records": records,
        "counts": {
            "exemplars": len(records),
            "sequences": len(records),
            "families": len({r["family_group"] for r in records}),
            "in_scope_families": len({r["family_group"] for r in records if r["in_scope"]}),
            "control_families": len({r["family_group"] for r in records if not r["in_scope"]}),
            "in_scope_sequences": sum(1 for r in records if r["in_scope"]),
            "control_sequences": sum(1 for r in records if not r["in_scope"]),
        },
        "selection": {},
        "ground_truth": {"msl": "MSL37", "filename": "f", "published": "2022-08-19"},
    }


def _record(accession: str, family: str, species: str = "sp") -> dict:
    return {
        "accession": accession,
        "segment": None,
        "species": species,
        "family_group": family,
        "in_scope": DENYLIST.covers({"family": family}),
        "lineage": {"family": family},
        "coverage": "Complete genome",
        "host_source": "vertebrates",
        "vmr_row": 2,
    }


def _calls(mapping: dict[str, str]) -> dict[str, genomad.TaxonomyCall]:
    out = {}
    for name, raw in mapping.items():
        lineage, anomalies = genomad.parse_lineage(raw)
        out[name] = genomad.TaxonomyCall(
            sequence=name,
            genes_with_taxonomy=5,
            agreement=1.0,
            taxid="1",
            raw=raw,
            lineage=lineage,
            anomalies=anomalies,
        )
    return out


def test_score_classifies_each_direction() -> None:
    evalset = _evalset(
        [
            _record("a", "Coronaviridae"),
            _record("b", "Coronaviridae"),
            _record("c", "Siphoviridae"),
        ]
    )
    fetched = {"lengths": {"a": 30000, "b": 30000, "c": 50000}, "bases": 110000, "missing": []}
    calls = _calls(
        {
            "a": CORONA,
            "b": TRUNCATED,
            "c": GEMINI,
        }
    )
    result = tool.score(evalset, fetched, calls, DENYLIST)
    rates = result["rates"]
    assert rates["escape"]["numerator"] == 1
    assert rates["escape"]["denominator"] == 2
    assert rates["spurious_removal"]["numerator"] == 1
    assert rates["spurious_removal"]["denominator"] == 1


def test_an_absent_taxonomy_row_is_an_escape_not_an_error() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, {}, DENYLIST)
    assert result["rates"]["escape"]["numerator"] == 1
    assert result["rates"]["escape"]["causes"]["unclassified"] == 1


def test_score_excludes_unretrieved_sequences_from_every_denominator() -> None:
    """A sequence never offered to the tool is not a sequence the tool failed on."""
    evalset = _evalset([_record("a", "Coronaviridae"), _record("gone", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": ["gone"]}
    calls = _calls({"a": CORONA})
    result = tool.score(evalset, fetched, calls, DENYLIST)
    assert result["evaluation_set"]["sequences_not_retrieved"] == 1
    assert result["rates"]["escape"]["denominator"] == 1
    assert result["rates"]["escape"]["numerator"] == 0


def test_zero_escapes_still_ship_a_non_zero_upper_bound() -> None:
    """The reason D-088 chose the exact method: a clean result must still bound itself."""
    evalset = _evalset([_record(f"r{i}", "Coronaviridae") for i in range(20)])
    fetched = {"lengths": {f"r{i}": 30000 for i in range(20)}, "bases": 600000, "missing": []}
    result = tool.score(evalset, fetched, _calls({f"r{i}": CORONA for i in range(20)}), DENYLIST)
    escape = result["rates"]["escape"]
    assert escape["point"] == 0.0
    assert escape["ci_upper"] > 0.0


def test_score_collects_lineage_anomalies() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, _calls({"a": MISRANKED}), DENYLIST)
    assert result["lineage_anomalies"]
    assert result["lineage_anomalies"][0]["accession"] == "a"


def test_score_carries_the_tool_pin_and_the_version_bound() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, {}, DENYLIST)
    pin = result["tool_under_test"]
    assert pin["genomad"] == "1.1.0"
    assert pin["version_evidence"]["stated_by_publisher"] is None
    assert "not_viral" in pin["scope"]


def test_propagation_names_its_coverage_and_its_bound() -> None:
    """The headline number must not be quotable without the share it covers."""
    evalset = _evalset([_record("a", "Coronaviridae"), _record("b", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000, "b": 30000}, "bases": 60000, "missing": []}
    calls = _calls({"a": TRUNCATED, "b": CORONA})
    dependency = {
        "release": {"records": 15_677_623},
        "denylisted_records": {"records": 181_530, "genomad_share": 0.385573},
    }
    result = tool.score(evalset, fetched, calls, DENYLIST, dependency=dependency)
    prop = result["propagation"]
    assert prop["bound"] == "lower"
    assert prop["coverage"]["denylist_hits"] == 181_530
    assert prop["coverage"]["unmeasured_share_of_hits"] == pytest.approx(1 - 0.385573)
    assert "A4.4" in prop["coverage"]["unmeasured_reason"]
    # Escape rate is 1/2 here. The removals on geNomad labels are 69,993, so the implied
    # in-scope population is 69,993/(1-0.5) and the escapees are the other half of it.
    removed = round(181_530 * 0.385573)
    assert prop["removed_records"] == removed
    assert prop["escaping_records"]["point"] == pytest.approx(removed)


def test_no_propagation_without_the_dependency_pass() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    assert tool.score(evalset, fetched, {}, DENYLIST)["propagation"] is None


def test_score_reports_bias_of_the_evaluation_set() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    bias = tool.score(evalset, fetched, {}, DENYLIST)["evaluation_set"]["bias"]
    assert any("lower bound" in item for item in bias)
    assert any("fragment" in item for item in bias)


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def test_render_produces_the_tables_a_reader_needs() -> None:
    evalset = _evalset(
        [_record("a", "Coronaviridae"), _record("b", "Coronaviridae"), _record("c", "Siphoviridae")]
    )
    fetched = {"lengths": {"a": 30000, "b": 1000, "c": 50000}, "bases": 81000, "missing": []}
    calls = _calls(
        {
            "a": CORONA,
            "b": TRUNCATED,
        }
    )
    dependency = {
        "release": {"records": 15_677_623},
        "denylisted_records": {"records": 181_530, "genomad_share": 0.385573},
    }
    text = tool.render(tool.score(evalset, fetched, calls, DENYLIST, dependency=dependency))
    assert "# A4.2" in text
    assert "Error rates, by direction" in text
    assert "Escape, by cause" in text
    assert "Escape rate per family" in text
    assert "Escape rate by length" in text
    assert "Propagation into filter leakage" in text
    assert "lower bound" in text
    assert "Bias in the evaluation set" in text
    # The version bound must be visible to someone who reads only the report.
    assert "bound, not a statement" in text


def test_render_survives_a_result_with_no_controls() -> None:
    evalset = _evalset([_record("a", "Coronaviridae")])
    fetched = {"lengths": {"a": 30000}, "bases": 30000, "missing": []}
    text = tool.render(tool.score(evalset, fetched, {}, DENYLIST))
    assert "spurious_removal" not in text
    assert "escape" in text


def test_caps_match_the_preregistration() -> None:
    """D-087 fixed these numbers; a drift here silently changes the published denominators."""
    assert tool.IN_SCOPE_CAP == 40
    assert tool.CONTROL_CAP == 8


def test_evalset_json_roundtrips(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _build(monkeypatch, [_exemplar("a")])
    assert json.loads(json.dumps(built))["counts"]["sequences"] == 1


# --------------------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------------------


def test_call_index_accepts_versioned_and_bare_names() -> None:
    """geNomad echoes the FASTA name it was given; the VMR's accessions are unversioned."""
    calls = _calls({"NC_001806.2": CORONA})
    index = tool._call_index(calls)
    assert "NC_001806.2" in index
    assert "NC_001806" in index


def test_versioned_taxonomy_names_still_join() -> None:
    """The failure this prevents is not a crash, it is a publishable-looking 100% escape rate."""
    evalset = _evalset([_record("NC_001806", "Coronaviridae")])
    fetched = {"lengths": {"NC_001806": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, _calls({"NC_001806.2": CORONA}), DENYLIST)
    assert result["rates"]["escape"]["numerator"] == 0
    assert result["evaluation_set"]["sequences_with_a_taxonomy_row"] == 1


def test_bare_evalset_name_joins_a_versioned_call_and_vice_versa() -> None:
    evalset = _evalset([_record("NC_001806.2", "Coronaviridae")])
    fetched = {"lengths": {"NC_001806.2": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, _calls({"NC_001806": CORONA}), DENYLIST)
    assert result["rates"]["escape"]["numerator"] == 0


def test_a_total_join_failure_raises_instead_of_reporting_total_leakage() -> None:
    """Every record unclassified is arithmetically indistinguishable from a join failure.

    Reporting it would be the most flattering possible result for this audit, which is exactly
    why it has to be refused rather than printed. §2's commitment cuts both ways.
    """
    evalset = _evalset([_record("AAA111", "Coronaviridae")])
    fetched = {"lengths": {"AAA111": 30000}, "bases": 30000, "missing": []}
    with pytest.raises(ValueError, match="join failure, not a 100% escape rate"):
        tool.score(evalset, fetched, _calls({"ZZZ999": CORONA}), DENYLIST)


def test_a_genuinely_empty_taxonomy_output_is_not_mistaken_for_a_join_failure() -> None:
    """A tool that classified nothing at all is a real result; only a mismatch is an error."""
    evalset = _evalset([_record("AAA111", "Coronaviridae")])
    fetched = {"lengths": {"AAA111": 30000}, "bases": 30000, "missing": []}
    result = tool.score(evalset, fetched, {}, DENYLIST)
    assert result["rates"]["escape"]["numerator"] == 1
    assert result["evaluation_set"]["sequences_with_a_taxonomy_row"] == 0

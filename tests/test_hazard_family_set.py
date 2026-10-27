"""Tests for the hazard family set and the record-membership join.

The point of both tools is that they resolve taxa by curated taxid and read no family name, so
the tests that matter are the refusals: a curated taxid that has drifted from what the curation
claims, a taxon that silently returns nothing, and a table whose delimiter has moved. Each of
those three has already produced a wrong answer in this project — the first two in the build
this pair replaces (2,904 reviewed entries dropped with no error), the third in this tool's own
first run, where reading `|` as `,` classified every multi-family record as carrying no hazard
family at all.

The tests that need the 60 MB pinned taxonomy skip when it is not staged, following
`test_selectagents.py`; the rest run from committed files on every commit.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TAXDUMP = ROOT / "data" / "taxdmp_2023-04-01.zip"
TAXA_SPEC = ROOT / "policies" / "specs" / "hazard-virus-taxa-evo1.json"
TOXIN_SPEC = ROOT / "policies" / "specs" / "hazard-toxins-2024-06-01.json"

needs_taxonomy = pytest.mark.skipif(not TAXDUMP.exists(), reason="pinned taxonomy dump not staged")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hfs():
    return _load("hazard_family_set")


@pytest.fixture(scope="module")
def hrm():
    return _load("hazard_record_membership")


# --- the curated mapping, against the published list -------------------------------------


def test_spec_covers_exactly_the_published_taxa(hfs):
    """Nothing named may be unmapped, and nothing mapped may be unnamed."""
    published = hfs.published_taxa()
    curated = {e["entry"] for e in json.loads(TAXA_SPEC.read_text())["entries"]}
    assert curated == set(published)
    assert len(published) == 31, "19 families and 12 orders"


def test_every_entry_records_the_rank_the_list_names_it_at(hfs):
    published = hfs.published_taxa()
    for e in json.loads(TAXA_SPEC.read_text())["entries"]:
        assert e["published_rank"] == published[e["entry"]]


def test_renames_and_zeros_are_curated_not_implicit():
    """The three restructured taxa and the two genuine zeros carry their evidence."""
    entries = {e["entry"]: e for e in json.loads(TAXA_SPEC.read_text())["entries"]}
    assert entries["Reoviridae"]["rename"] == "elevated_and_split"
    assert entries["Reoviridae"]["pinned_name"] == "Reovirales"
    assert entries["Herpesviridae"]["taxid_query"] != entries["Herpesviridae"]["taxid_pinned"]
    for name in ("Orthopolintovirales", "Priklausovirales"):
        assert entries[name]["expect_zero"] is True
        assert entries[name]["note"]
    for e in entries.values():
        if e.get("rename") or e.get("expect_zero"):
            assert e.get("note"), f"{e['entry']} needs its reason recorded"


@needs_taxonomy
def test_curated_taxids_match_the_pinned_taxonomy(hfs):
    """The validation D-137 requires: the pin checks the curation, and refuses on drift."""
    names, rank = hfs.pinned_taxonomy(TAXDUMP)
    entries = hfs.load_taxa_spec(hfs.published_taxa(), names, rank)
    assert len(entries) == 31
    for e in entries:
        assert names[e["taxid_pinned"]] == e["pinned_name"]
        assert rank[e["taxid_pinned"]] == e["pinned_rank"]


@needs_taxonomy
def test_a_drifted_curated_taxid_refuses(hfs, tmp_path, monkeypatch):
    """A curated taxid that no longer carries the recorded name must fail, not be trusted."""
    names, rank = hfs.pinned_taxonomy(TAXDUMP)
    payload = json.loads(TAXA_SPEC.read_text())
    payload["entries"][0]["pinned_name"] = "Notaviridae"
    path = tmp_path / "drifted.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(hfs, "TAXA_SPEC", path)
    with pytest.raises(SystemExit, match="pinned taxonomy"):
        hfs.load_taxa_spec(hfs.published_taxa(), names, rank)


@needs_taxonomy
def test_a_missing_taxon_refuses(hfs, tmp_path, monkeypatch):
    names, rank = hfs.pinned_taxonomy(TAXDUMP)
    payload = json.loads(TAXA_SPEC.read_text())
    payload["entries"] = payload["entries"][:-1]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(hfs, "TAXA_SPEC", path)
    with pytest.raises(SystemExit, match="Missing"):
        hfs.load_taxa_spec(hfs.published_taxa(), names, rank)


def test_the_published_list_is_read_from_the_spec_not_retyped(hfs):
    """The 31 taxa come from the policy spec, so a change there moves this tool."""
    published = hfs.published_taxa()
    assert published["Reoviridae"] == "family"
    assert published["Herpesvirales"] == "order"
    assert sum(1 for v in published.values() if v == "family") == 19
    assert sum(1 for v in published.values() if v == "order") == 12


# --- stratum T, read rather than rebuilt -------------------------------------------------


def test_toxin_stratum_is_read_from_its_curation(hfs):
    nominated, meta = hfs.build_t()
    assert meta["entries"] == 9
    assert meta["entries_nominating"] == 4
    assert len(nominated) == 10
    assert nominated["PF00161"] == {"Abrin", "Ricin"}
    assert meta["flagged"], "PF00652 is kept but flagged; the flag must survive into the set"


def test_a_declined_toxin_entry_nominates_nothing():
    """The conotoxin entry is defined by a sequence motif and is declined, not guessed."""
    entries = {e["entry"]: e for e in json.loads(TOXIN_SPEC.read_text())["entries"]}
    declined = [e for e in entries.values() if not e["nominates"]]
    assert len(declined) == 5
    for e in declined:
        assert e["families"] == []


# --- the record join ---------------------------------------------------------------------


def test_delimiter_guard_refuses_a_mis_split(hrm):
    """Reading `|` as `,` is the bug that classified every multi-family record as clean."""
    assert hrm.split_families("PF00519|PF20450", "r") == ["PF00519", "PF20450"]
    with pytest.raises(SystemExit, match="Pfam accession"):
        hrm.split_families("PF00519,PF20450", "r")


def test_classification_is_by_exclusivity_and_takes_the_strongest(hrm):
    hazard = {
        "PF00001": {
            "accession": "PF00001",
            "name": "exclusive",
            "exclusivity": 1.0,
            "specificity": "viral_only",
            "viral_selection": True,
            "nominating_entries": 7,
            "reviewed_total": 7,
            "nominated_by_taxa": ["Poxviridae"],
        },
        "PF00002": {
            "accession": "PF00002",
            "name": "shared",
            "exclusivity": 0.37,
            "specificity": "viral_only",
            "viral_selection": True,
            "nominating_entries": 7,
            "reviewed_total": 19,
            "nominated_by_taxa": ["Poxviridae"],
        },
    }
    background = {
        "PF00003": {
            "accession": "PF00003",
            "name": "unreviewed",
            "class": "unmeasurable",
            "reviewed_total": 0,
        },
        "PF00004": {
            "accession": "PF00004",
            "name": "elsewhere",
            "class": "viral_only",
            "reviewed_total": 50,
        },
    }
    assert hrm.classify(["PF00002", "PF00001"], hazard, background)[0] == "hazard_family_exclusive"
    assert hrm.classify(["PF00002"], hazard, background)[0] == "hazard_family_shared"
    assert hrm.classify(["PF00003"], hazard, background)[0] == "unnominatable"
    assert hrm.classify(["PF00004"], hazard, background)[0] == "not_nominated"


def test_an_unnominatable_family_is_not_counted_as_a_disagreement(hrm):
    """A family with no reviewed entries cannot be nominated by anyone, which is not evidence
    against the name axis — the distinction the fourth class exists for."""
    background = {
        "PF08284": {
            "accession": "PF08284",
            "name": "RVP_2",
            "class": "unmeasurable",
            "reviewed_total": 0,
        }
    }
    cls, detail = hrm.classify(["PF08284"], {}, background)
    assert cls == "unnominatable"
    assert detail[0]["nominated"] is False
    assert detail[0]["reviewed_total"] == 0


# --- the publish guard --------------------------------------------------------------------


def test_allow_dirty_never_publishes(hfs, hrm, tmp_path, capsys):
    """`--allow-dirty` is the local-iteration flag; it must never reach the durable store.

    The combination that caused D-265: a canonical `--out` supplies a real `durable`, and
    `--allow-dirty` carries the run past `repro.run`'s dirty-tree refusal, so the artefact
    publishes with a manifest naming the previous commit — permanently, in a bucket with no
    delete. Guarding it at the tool means the refusal prints before any network work.
    """
    for mod in (hfs, hrm):
        assert mod.durable_for(mod.CANONICAL_OUT, allow_dirty=True) is None
        assert "allow-dirty" in capsys.readouterr().err
        assert mod.durable_for(tmp_path, allow_dirty=False) is None
        assert "probe" in capsys.readouterr().err
        published = mod.durable_for(mod.CANONICAL_OUT, allow_dirty=False)
        assert published and published.startswith("s3://")
